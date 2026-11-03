"""Offline MoveJ/L/C geometry and continuous-branch IK sampling.

Cartesian derivative/limit checks are discrete estimates, NOT a certificate
for streamed execution. Real execution remains gated by hardware capability.
"""
import math
from . import kinematics as k
from .joint_blend import plan as joint_plan, sample as joint_sample
from .coupled_limits import one_based


def circle(start, via, end):
    a,b,c=(k.finite_vector(v,3) for v in (start,via,end))
    u,w=k.sub(b,a),k.sub(c,a);length=k.norm(u);normal=k.cross(u,w)
    if min(length,k.norm(w),k.norm(k.sub(c,b)))<.01 or k.norm(normal)<1e-5*length*k.norm(w):
        raise ValueError('圆弧三点重复或近共线；整圆请拆成两段')
    u=k.scale(u,1/length);normal=k.scale(normal,1/k.norm(normal));v=k.cross(normal,u)
    wx,wy=k.dot(w,u),k.dot(w,v);cx=length/2;cy=(k.dot(w,w)-length*wx)/(2*wy)
    center=k.add(a,k.add(k.scale(u,cx),k.scale(v,cy)));radius=k.norm(k.sub(a,center))
    if radius<.1 or radius>1e6:raise ValueError('圆弧半径过小或数值不稳定')
    def angle(p):return math.atan2(k.dot(k.sub(p,center),v),k.dot(k.sub(p,center),u))
    first=angle(a);last=(angle(c)-first)%(2*math.pi);middle=(angle(b)-first)%(2*math.pi)
    span=last if middle<=last else last-2*math.pi
    def point(t):return k.add(center,k.add(k.scale(u,radius*math.cos(first+span*t)),k.scale(v,radius*math.sin(first+span*t))))
    # Analytic height extrema: the three defining points can all have Z>0
    # while the selected circular arc dips below the table between them.
    a=radius*(u[2]*math.cos(first)+v[2]*math.sin(first))
    b=radius*(-u[2]*math.sin(first)+v[2]*math.cos(first))
    phase=math.atan2(b,a);lo,hi=sorted((0.,span))
    angles=[0.,span]+[phase+n*math.pi for n in range(math.ceil((lo-phase)/math.pi),math.floor((hi-phase)/math.pi)+1)]
    minimum_z=min(center[2]+a*math.cos(t)+b*math.sin(t) for t in angles)
    return dict(point=point,length=abs(span)*radius,radius=radius,
                via_fraction=middle/span if span>0 else (middle-2*math.pi)/span,
                minimum_z_mm=minimum_z)


def validate_bounds(q,bounds):
    from .coupled_limits import check_box
    check_box(getattr(bounds,'rule',None),q,q)
    for i,v in enumerate(q):
        if i in bounds and not bounds[i][0]-1e-8<=v<=bounds[i][1]+1e-8:
            raise ValueError('J'+str(i+1)+' 轨迹超过模型限位')


class PathBranchError(ValueError):
    pass


def _plan_path(start_deg, goal, bounds, mode='L', via=None, speed=10., orientation='hold',
         joint_speed=5., acceleration=5., jerk=20., angular_speed=10.,check=lambda:None,joint_target=None):
    start=k.finite_vector(start_deg,6);goal=k.validate_pose(goal)
    from .collision import check_target
    check_target(goal['position_mm'])
    if mode not in ('J','L','C') or orientation not in ('hold','interpolate'):raise ValueError('轨迹方式或方向策略无效')
    for value,maximum in ((speed,1000),(joint_speed,20),(acceleration,100),(jerk,1000),(angular_speed,100)):
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=maximum:raise ValueError('轨迹速度、加速度或变化率无效')
    validate_bounds(start,bounds);origin=k.forward(start)
    if orientation=='hold':goal['rotation']=origin['rotation']
    if mode=='J':
        if joint_target is None:
            solution=k.inverse(goal,start,bounds,check=check)
            q=solution['angles_deg']
        else:
            q=k.finite_vector(joint_target,6);validate_bounds(q,bounds)
            pe,re=k.pose_error(goal,k.forward(q))
            if pe>.03 or re>.03:raise ValueError('所选入口分支与目标姿态不一致')
            sigma=k.singular_value(k.forward(q,True)['jacobian'])
            solution=dict(angles_deg=q,position_error_mm=pe,orientation_error_deg=re,
                singular_value=sigma,near_singularity=sigma<.01,algorithm='route-selected-analytic-mdh')
        check()
        from .collision import check_joint_box
        from .coupled_limits import check_box
        check_box(getattr(bounds,'rule',None),[min(a,b) for a,b in zip(start,q)],[max(a,b) for a,b in zip(start,q)])
        clearance=check_joint_box(start,q,check)
        report=joint_plan(dict(enumerate(start,1)),[dict(angles_deg=dict(enumerate(q,1)),speed_deg_s=joint_speed,dwell_seconds=0)],
                          one_based(bounds),radius=0,acceleration=acceleration,jerk=jerk)
        samples=joint_sample(report)
        stride=max(1,math.ceil(len(samples)/200))
        indices=sorted(set(range(0,len(samples),stride))|{len(samples)-1})
        from .reference_adapter import make_model,TOOL_ROTATION
        model=make_model(start,bounds)
        plotted=[]
        for i in indices:
            check();t,a=samples[i];transform=model.forward(a)
            pose=dict(position_mm=[row[3] for row in transform[:3]],rotation=k.mm([row[:3] for row in transform[:3]],TOOL_ROTATION))
            plotted.append(dict(time_s=t,angles_deg=a,pose=pose))
        return dict(mode=mode,samples=plotted,
                    target_angles_deg=q,total_seconds=report['total_seconds'],
                    derivative_bounds=report['derivative_bounds'],solution=solution,
                    execution_supported=False,validation='joint_convex_hull',orientation=orientation,
                    table_validation=clearance)
    geometry=circle(origin['position_mm'],via,goal['position_mm']) if mode=='C' else None
    length=geometry['length'] if geometry else k.norm(k.sub(goal['position_mm'],origin['position_mm']))
    angular=k.pose_error(goal,dict(position_mm=goal['position_mm'],rotation=origin['rotation']))[1]
    # Uniform time samples with quintic path progress; IK is seeded by prior point.
    count=max(40,math.ceil(length*2),math.ceil(angular*2))
    if count>1600:raise ValueError('轨迹过长，请分段规划')
    minimum_sigma=float('inf')
    while True:
        values=[];last=start;refine=False
        for i in range(count+1):
            check();t=i/count;s=10*t**3-15*t**4+6*t**5
            p=geometry['point'](s) if geometry else k.add(k.scale(origin['position_mm'],1-s),k.scale(goal['position_mm'],s))
            r=origin['rotation'] if orientation=='hold' else k.interpolate_rotation(origin['rotation'],goal['rotation'],s)
            pose=dict(position_mm=p,rotation=r)
            if i==0:
                q=start;sigma=k.singular_value(k.forward(q,True)['jacobian'])
            else:
                try:solution=k.inverse(pose,last,bounds,multistart=False,check=check)
                except ValueError as error:raise PathBranchError(str(error)) from error
                q=solution['angles_deg'];sigma=solution['singular_value']
            # A rank deficient wrist can still follow a compatible path. Require
            # pose residual, bounded joint increments and time scaling instead
            # of rejecting every singular pose, including the starting pose.
            minimum_sigma=min(minimum_sigma,sigma)
            if i and max(abs(v-w) for v,w in zip(q,last))>3:refine=True;break
            validate_bounds(q,bounds);values.append((q,pose));last=q
        if not refine:break
        count*=2
        if count>1600:raise PathBranchError('逆解变化过快或分支不连续，请调整路径')
    duration=max(.5,1.875*length/speed,1.875*angular/angular_speed)
    # Derivatives estimated in normalized time then one conservative stretch.
    derivatives=[q for q,_ in values];peaks=[]
    for _ in range(3):
        derivatives=[k.scale(k.sub(b,a),count) for a,b in zip(derivatives,derivatives[1:])]
        peaks.append(max((abs(v) for row in derivatives for v in row),default=0))
    duration=max(duration,peaks[0]/joint_speed,math.sqrt(peaks[1]/acceleration),(peaks[2]/jerk)**(1/3))*1.1
    samples=[dict(time_s=duration*i/count,angles_deg=q,pose=pose) for i,(q,pose) in enumerate(values)]
    return dict(mode=mode,samples=samples,target_angles_deg=values[-1][0],total_seconds=duration,
                path_length_mm=length,arc_radius_mm=geometry['radius'] if geometry else None,
                via_fraction=geometry['via_fraction'] if geometry else None,
                derivative_bounds=[v/duration**(i+1) for i,v in enumerate(peaks)],
                minimum_singular_value=minimum_sigma,orientation=orientation,
                execution_supported=False,validation='discrete_preview_only',
                warning='已检查离散逆解与限位；未证明采样间连续误差，未做碰撞检测，不可直接流式下发')


def wrist_candidates(start, tangent, bounds, check):
    """Reference handoff's geometric wrist alignment, adapted to this chain."""
    check();chain=k.forward(start,True);axes=chain['axes'];origins=chain['origins']
    if k.dot(axes[3],axes[5])<math.cos(math.radians(.00001)):return []
    if any(k.norm(k.cross(k.sub(p,origins[3]),axes[3]))>1e-6 for p in origins[4:]):return []
    cols=[k.cross(a,k.sub(origins[4],p)) for a,p in zip(axes[:3],origins[:3])]
    try:rates=k.solve(k.transpose(cols),tangent)
    except ValueError:return []
    if any(not math.isfinite(v) or abs(v)>100 for v in rates):return []
    omega=[-sum(axes[j][i]*rates[j] for j in range(3)) for i in range(3)]
    x=k.dot(omega,axes[4]);y=k.dot(omega,k.cross(axes[3],axes[4]))
    if math.hypot(x,y)<1e-10:return []
    delta=math.degrees(math.atan2(y,x));candidates=[]
    for turn in range(-4,5):
        change=delta+180*turn
        if not .01<abs(change)<=180+1e-9:continue
        q=list(start);q[3]+=change;q[5]-=change
        try:validate_bounds(q,bounds)
        except ValueError:continue
        candidates.append(q)
    return sorted(candidates,key=lambda q:(abs(q[3]-start[3]),q[3]))


def _legacy_plan(start_deg, goal, bounds, mode='L', via=None, speed=10., orientation='hold',
         joint_speed=5., acceleration=5., jerk=20., angular_speed=10.,check=lambda:None):
    params=dict(mode=mode,via=via,speed=speed,orientation=orientation,joint_speed=joint_speed,
                acceleration=acceleration,jerk=jerk,angular_speed=angular_speed,check=check)
    try:return _plan_path(start_deg,goal,bounds,**params)
    except PathBranchError as original:
        if mode not in ('L','C') or orientation!='hold':raise
        start=k.finite_vector(start_deg,6);origin=k.forward(start);target=k.validate_pose(goal)
        tangent=k.sub(target['position_mm'],origin['position_mm'])
        if mode=='C':
            arc=circle(origin['position_mm'],via,target['position_mm'])
            tangent=k.sub(arc['point'](.0001),arc['point'](0))
        if k.norm(tangent)<1e-9:raise
        tangent=k.scale(tangent,1/k.norm(tangent))
        for prepared in wrist_candidates(start,tangent,bounds,check):
            check()
            report=joint_plan(dict(enumerate(start,1)),[dict(angles_deg=dict(enumerate(prepared,1)),speed_deg_s=joint_speed,dwell_seconds=0)],
                              one_based(bounds),radius=0,acceleration=acceleration,jerk=jerk)
            preparation=[]
            for t,q in joint_sample(report):
                check();p=k.forward(q);pe,ae=k.pose_error(origin,p)
                if pe>1e-6 or ae>1e-6:break
                preparation.append(dict(time_s=t,angles_deg=q,pose=p,phase='wrist_preparation'))
            else:
                try:tail=_plan_path(prepared,target,bounds,**params)
                except PathBranchError:continue
                elapsed=report['total_seconds']
                tail['samples']=preparation+[dict(p,time_s=p['time_s']+elapsed,phase='cartesian') for p in tail['samples'][1:]]
                tail['total_seconds']+=elapsed
                tail['preparation']=dict(kind='fixed_tcp_wrist_alignment',start_angles_deg=start,
                                         end_angles_deg=prepared,duration_s=elapsed)
                tail['warning']='包含保持TCP位置和朝向的J4/J6腕部预对齐；'+tail['warning']
                return tail
        raise PathBranchError('直线/圆弧连续逆解失败，腕部预对齐也未找到满足限位的路径：'+str(original)) from original


def plan(start_deg,goal,bounds,mode='L',via=None,speed=10.,orientation='hold',
         joint_speed=5.,acceleration=5.,jerk=20.,angular_speed=10.,check=lambda:None,hardware=None,joint_target=None):
    from .reference_adapter import plan_cartesian
    if mode=='J':return _plan_path(start_deg,goal,bounds,mode=mode,via=via,speed=speed,
        orientation=orientation,joint_speed=joint_speed,acceleration=acceleration,jerk=jerk,angular_speed=angular_speed,check=check,joint_target=joint_target)
    if mode not in ('L','C'):raise ValueError('轨迹方式无效')
    if orientation!='hold':raise ValueError('交接包LIN/CIRC保持起点朝向，不支持目标朝向插补')
    start=k.finite_vector(start_deg,6);goal=k.validate_pose(goal);validate_bounds(start,bounds);check()
    if mode=='L' and k.norm(k.sub(goal['position_mm'],k.forward(start)['position_mm']))<1e-9:
        return dict(mode=mode,samples=[dict(time_s=0.,angles_deg=start,pose=k.forward(start))],
            target_angles_deg=start,total_seconds=0.,execution_supported=False,validation='discrete_preview_only',algorithm='handoff-v2')
    return plan_cartesian(start,goal,bounds,mode,via,speed,joint_speed,check,hardware)
