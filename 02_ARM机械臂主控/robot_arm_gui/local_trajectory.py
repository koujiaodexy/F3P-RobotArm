"""Incremental Cartesian geometry and C2 local timing; no hardware IO."""
import bisect
import math
import threading
import time
from . import fast_trajectory as f
from .rolling_trajectory import Curve,RollingFrames
from .native_math import PlanningModel,LIBRARY,array,flatten
from .reference_endpoint.kinematics import matrix_to_rpy,_solve_linear,KinematicsError


def polynomial(u,v,a,end,end_v,duration):
    c0=u;c1=v*duration;c2=a*duration*duration/2;delta=end-u;tail=end_v*duration
    return [c0,c1,c2,10*delta-6*c1-3*c2-4*tail,
            -15*delta+8*c1+3*c2+7*tail,6*delta-3*c1-c2-3*tail]


def evaluate(coeff,x,order=0):
    for _ in range(order):coeff=[i*v for i,v in enumerate(coeff)][1:]
    result=0.
    for v in reversed(coeff):result=result*x+v
    return result


def derivative_bound(coeff,lo,hi,order):
    """Bernstein convex-hull bound on a polynomial over a closed interval."""
    if LIBRARY is not None and hasattr(LIBRARY,'f3p_derivative_bound'):
        result=LIBRARY.f3p_derivative_bound(array(coeff),len(coeff),lo,hi,order)
        if not math.isfinite(result):raise f.TrajectoryError('原生多项式包络无效')
        return result
    for _ in range(order):coeff=[i*v for i,v in enumerate(coeff)][1:]
    degree=len(coeff)-1;width=hi-lo
    power=[sum(coeff[j]*math.comb(j,i)*lo**(j-i)*width**i
               for j in range(i,degree+1)) for i in range(degree+1)]
    controls=[sum(power[i]*math.comb(k,i)/math.comb(degree,i)
                  for i in range(k+1)) for k in range(degree+1)]
    return max(abs(v) for v in controls)


class LocalCurve(Curve):
    native_frames=True
    def __init__(self,model,motor,target,args,check,ahead):
        self.model=PlanningModel(model.profile);self.motor=list(motor);self.args=args;self.check=check
        profile=self.model.profile
        self.ratios=list(profile['motor_mapping']['ratios'])
        self.tick=.04;self.ahead=ahead;self.q0=self.model.motor_to_joints(motor)
        self.origin=self.model.forward(self.q0);self.start=[r[3] for r in self.origin[:3]]
        path_start=args.get('nominal_start_mm')
        if path_start is None:path_start=self.start
        if len(path_start)!=3 or any(not math.isfinite(v) for v in path_start):
            raise f.TrajectoryError('绘图原始起点坐标无效')
        self.point,self.length,self.arc=f._path_geometry(path_start,target,args.get('kind','line'),args.get('via_mm'))
        if not .01<self.length<=f.MAX_PATH_MM:raise f.TrajectoryError('局部轨迹长度需要在0.01～1000mm之间')
        self.limits=self.model.joint_limits_deg
        self.ppr=f._six(args['pulses_per_rev'],1,0xffffffff,'PPR')
        self.acc=f._six(args['acceleration'],1,255,'ACC');self.caps=f._six(args['speed_caps_rpm'],1,3000,'RPM')
        self.rates=[1/((256-a)*50e-6) for a in self.acc]
        self.wire=[min(c,max(1,int(r*ahead*.35))) for c,r in zip(self.caps,self.rates)]
        self.nominal=[min(c*.7,args['joint_speed_deg_s']*abs(r)/6)
                      for c,r in zip(self.wire,self.ratios)]
        profile['solver'].update(position_tolerance_mm=.01,
            orientation_tolerance_deg=.01,max_seeds=1,max_iterations=80)
        self.solver=PlanningModel(profile);self.rpy=matrix_to_rpy(self.origin)
        self.ends=[];self.segments=[];self.guide_q=list(self.q0);self.guide_u=0.
        self.guide_derivatives={}
        self.row_cache={};self.error_cache={}
        self.adaptive=bool(args.get('allow_orientation_adjustment'))
        self.orientation_released=False
        self.guide_limits=[list(pair) if pair else None for pair in self.limits]
        if self.adaptive:
            for i,pair in enumerate(self.guide_limits):
                if pair:
                    margin=180/self.ppr[i]/abs(self.ratios[i])+1e-8
                    pair[0]+=margin;pair[1]-=margin
        self.path_budget=float(args.get('position_tolerance_mm',.1))
        self.drawing_timing=self.adaptive or self.path_budget>.1
        if not math.isfinite(self.path_budget) or not .1<=self.path_budget<=1:
            raise f.TrajectoryError('滚动路径误差预算须为0.1～1mm')
        self.tangent_cache={}
        self.native_fused=LIBRARY is not None and hasattr(LIBRARY,'f3p_q_pose_norms')
        self.native_origin=array(flatten(self.origin)) if self.native_fused else None
        self.schedule=[];self.duration=f.MAX_TRAJECTORY_SECONDS;self.steps=round(self.duration/self.tick)
        self.count=0;self.reasons=[]
        self.transitions=[]
        self.transition_tolerance=float(args.get('singularity_deviation_mm',.1))
        if not math.isfinite(self.transition_tolerance) or not .1<=self.transition_tolerance<=1:
            raise f.TrajectoryError('奇异区最大偏离须为0.1～1mm')
        if self.adaptive and args.get('orientation_released'):
            self.release_orientation(0.)

    def release_orientation(self,u):
        self.orientation_released=True
        self.tangent_cache.clear();self.error_cache.clear();self.row_cache.clear()
        print('DRAWING_ORIENTATION_RELEASED',dict(path_fraction=u,reason='fixed_orientation_continuation_failed'),flush=True)

    def position_budget(self,u):
        return self.transition_tolerance if any(lo<=u<=hi for lo,hi in self.transitions) else self.path_budget

    def bridge(self,left,q0,m0):
        """Find and validate an exit before committing any exceptional segment.

        Orientation remains held. Incoming/outgoing Hermite tangents match;
        ordinary geometry outside this interval keeps its strict budget.
        """
        profile=self.model.profile
        profile['solver'].update(position_tolerance_mm=.01,orientation_tolerance_deg=.01,
                                  max_seeds=4,max_iterations=120)
        solver=PlanningModel(profile)
        for distance in (.5,1.,2.,4.,8.,12.):
            self.check();right=min(1.,left+distance/self.length);span=right-left
            if span<=1e-9:continue
            try:
                q1=solver.solve(self.point(right),self.rpy,q0,limits_deg=self.limits)
                from .coupled_limits import nearest_legal_winding
                q1=nearest_legal_winding(self.model,q1,q0)
                if max(abs(a-b) for a,b in zip(q0,q1))>15:continue
                from . import kinematics as k
                transform,axes,origins,_=self.model._chain(q1)
                p=[r[3] for r in transform[:3]]
                jac=k.transpose([k.scale(k.cross(axis,k.sub(p,origin)),1/200)+axis
                                 for axis,origin in zip(axes,origins)])
                if k.singular_value(jac)<.01:continue
                m1=self.tangent(q1,right)
                coeff=[(2*a-2*b+span*(c+d),-3*a+3*b-span*(2*c+d),span*c,a)
                       for a,b,c,d in zip(q0,q1,m0,m1)]
                # Check analytic joint extrema, then dense FK samples. Frame and
                # lookahead checks subsequently validate the timed/quantized path.
                for (a,b,c,d),pair in zip(coeff,self.limits):
                    if not pair:continue
                    xs=[0.,1.]
                    if abs(a)>1e-15:
                        disc=4*b*b-12*a*c
                        if disc>=0:xs.extend(x for x in ((-2*b+math.sqrt(disc))/(6*a),(-2*b-math.sqrt(disc))/(6*a)) if 0<x<1)
                    elif abs(b)>1e-15:
                        x=-c/(2*b)
                        if 0<x<1:xs.append(x)
                    if any(not pair[0]<=((a*x+b)*x+c)*x+d<=pair[1] for x in xs):raise KinematicsError('过渡关节包络超限')
                for i in range(129):
                    self.check();x=i/128
                    qi=[((a*x+b)*x+c)*x+d for a,b,c,d in coeff]
                    pe,re=self.error(qi,self.point(left+span*x))
                    if pe>self.transition_tolerance-.02 or re>.05:raise KinematicsError('过渡路径偏离超限')
                from .coupled_limits import check_cubic
                check_cubic(self.model,coeff)
                self.segments.append((left,right,coeff));self.ends.append(right)
                self.transitions.append((left,right));self.guide_u=right;self.guide_q=q1;self.count+=1
                return True
            except KinematicsError:continue
        return False

    def error(self,q,xyz):
        key=(tuple(q),tuple(xyz))
        if key not in self.error_cache:
            if len(self.error_cache)>=8192:self.error_cache.clear()
            if self.native_fused:
                out=array([0.,0.]);LIBRARY.f3p_q_pose_norms(self.model._native_geometry,array(q),self.native_origin,array(xyz),out)
                self.error_cache[key]=tuple(out)
            else:self.error_cache[key]=super().error(q,xyz)
        pe,re=self.error_cache[key]
        return pe,0. if self.adaptive else re

    def row(self,u):
        self.check()
        if u not in self.row_cache:
            if len(self.row_cache)>=4096:self.row_cache.clear()
            self.row_cache[u]=super().row(u)
        return self.row_cache[u]

    def tangent(self,q,u):
        from . import kinematics as k
        key=(tuple(q),u)
        if key in self.tangent_cache:return self.tangent_cache[key]
        lo=max(0,u-1e-5);hi=min(1,u+1e-5)
        velocity=k.scale(k.sub(self.point(hi),self.point(lo)),1/(hi-lo))
        if self.adaptive and self.orientation_released:
            limits=[pair or [v-180,v+180] for pair,v in zip(self.guide_limits,q)]
            if LIBRARY is not None and hasattr(LIBRARY,'f3p_position_tangent'):
                out=array([0.]*6)
                if not LIBRARY.f3p_position_tangent(self.model._native_geometry,array(q),array(velocity),array(flatten(limits)),out):
                    raise f._ContinuousIKError('自动朝向位置切线无法求解')
                result=list(out)
            else:
                transform,axes,origins,_=self.model._chain(q);p=[r[3] for r in transform[:3]]
                jac=k.transpose([k.scale(k.cross(axis,k.sub(p,origin)),1/200) for axis,origin in zip(axes,origins)])
                path_scale=k.norm(velocity)*math.radians(.15)
                bias=[]
                for v,(lo,hi) in zip(q,limits):
                    margin=min(20.,(hi-lo)*.2)
                    low=max(0.,1-(v-lo)/margin);high=max(0.,1-(hi-v)/margin)
                    bias.append(path_scale*(low*low-high*high))
                active={}
                for _ in range(7):
                    columns=[[0. if i in active else jac[j][i] for j in range(3)] for i in range(6)]
                    normal=[[sum(c[i]*c[j] for c in columns)+(1e-8 if i==j else 0) for j in range(3)] for i in range(3)]
                    rhs=[velocity[j]/200-sum(jac[j][i]*active.get(i,bias[i]) for i in range(6)) for j in range(3)]
                    dual=_solve_linear(normal,rhs)
                    result=[math.degrees(active[i] if i in active else sum(c[j]*dual[j] for j in range(3))+bias[i]) for i,c in enumerate(columns)]
                    changed=False
                    for i,(v,(lo,hi),rate) in enumerate(zip(q,limits,result)):
                        lower=-max(0.,v-lo-.001)*k.norm(velocity)/5
                        upper=max(0.,hi-v-.001)*k.norm(velocity)/5
                        if i not in active and not lower<=rate<=upper:
                            active[i]=math.radians(max(lower,min(upper,rate)));changed=True
                    if not changed:break
            self.tangent_cache[key]=result;return result
        if self.native_fused:
            out=array([0.]*6)
            if not LIBRARY.f3p_path_tangent(self.model._native_geometry,array(q),array(velocity),out):
                raise f._ContinuousIKError('局部起点需要腕部预对齐')
            result=list(out);self.tangent_cache[key]=result;return result
        transform,axes,origins,_=self.model._chain(q);p=[r[3] for r in transform[:3]]
        columns=[k.scale(k.cross(axis,k.sub(p,origin)),1/200)+axis for axis,origin in zip(axes,origins)]
        jac=k.transpose(columns);lo=max(0,u-1e-5);hi=min(1,u+1e-5)
        rhs=k.scale(k.sub(self.point(hi),self.point(lo)),1/((hi-lo)*200))+[0.,0.,0.]
        jt=k.transpose(jac);normal=k.mm(jt,jac)
        for i in range(6):normal[i][i]+=1e-10
        try:
            result=[math.degrees(x) for x in _solve_linear(normal,k.mv(jt,rhs))]
            self.tangent_cache[key]=result;return result
        except ArithmeticError as exc:raise f._ContinuousIKError('局部起点需要腕部预对齐') from exc

    def q(self,u):
        u=max(0.,min(1.,u));self.check()
        while self.guide_u<u-1e-12:
            left=self.guide_u;q0=self.guide_q;span=min(2/self.length,1-left)
            if self.count>=5000:raise f.TrajectoryError('局部导引计算超过5000段，需调整姿态')
            try:m0=self.tangent(q0,left)
            except f._ContinuousIKError:
                if not self.adaptive:raise
                self.release_orientation(left);m0=self.tangent(q0,left)
            failure=''
            for _ in range(16):
                self.check();right=min(1.,left+span)
                seed=[a+b*span for a,b in zip(q0,m0)]
                seed=[min(pair[1],max(pair[0],v)) if pair else v for v,pair in zip(seed,self.guide_limits)]
                try:
                    relaxed=self.adaptive and self.error(q0,self.point(left))[0]>min(.25,self.path_budget/4)
                    if self.adaptive and self.orientation_released:
                        from .position_inverse import solve_position
                        try:
                            q1=solve_position(self.solver,self.point(right),seed,self.guide_limits,self.check,
                                              tolerance=min(.1,self.path_budget/8))
                        except KinematicsError:
                            # Use the explicitly allowed drawing budget only
                            # when the tighter position solve cannot continue.
                            q1=solve_position(self.solver,self.point(right),seed,self.guide_limits,self.check,
                                              tolerance=self.path_budget*.65)
                            relaxed=True
                    else:
                        from .analytic_inverse import fixed_pose
                        q1=fixed_pose(self.model,self.point(right),[r[:3] for r in self.origin[:3]],seed,self.guide_limits,self.check)
                        if q1 is None:q1=self.solver.solve(self.point(right),self.rpy,seed,limits_deg=self.guide_limits)
                    from .coupled_limits import nearest_legal_winding
                    q1=nearest_legal_winding(self.model,q1,q0)
                    changes=[abs(a-b) for a,b in zip(q0,q1)]
                    if max(changes)>6 and not self.orientation_released:
                        # At a wrist singularity the analytic nearest branch
                        # can flip 180 degrees. Try the same pose with a local
                        # numerical solve before subdividing. The search box
                        # cannot authorize a jump; all existing cubic, pose,
                        # quantization and driver checks still apply below.
                        nearby=[([max(pair[0],v-6),min(pair[1],v+6)] if pair else [v-6,v+6])
                                for v,pair in zip(q0,self.guide_limits)]
                        candidate=self.solver.solve(self.point(right),self.rpy,q0,limits_deg=nearby)
                        candidate=nearest_legal_winding(self.model,candidate,q0)
                        from .coupled_limits import check_model_box
                        try:check_model_box(self.model,candidate,candidate)
                        except ValueError as exc:raise KinematicsError(str(exc)) from exc
                        q1=candidate;changes=[abs(a-b) for a,b in zip(q0,q1)]
                    if max(changes)>6:
                        axis=max(range(6),key=changes.__getitem__)
                        raise KinematicsError('关节分支变化超过6度：模型J%d %.4f→%.4f度，限位%s'%
                            (axis+1,q0[axis],q1[axis],self.limits[axis]))
                    m1=self.tangent(q1,right)
                    coeff=[(2*a-2*b+span*(c+d),-3*a+3*b-span*(2*c+d),span*c,a)
                           for a,b,c,d in zip(q0,q1,m0,m1)]
                    for (a,b,c,d),pair in zip(coeff,self.limits):
                        if not pair:continue
                        roots=[0.,1.]
                        if abs(a)>1e-15:
                            disc=4*b*b-12*a*c
                            if disc>=0:roots.extend(x for x in ((-2*b+math.sqrt(disc))/(6*a),(-2*b-math.sqrt(disc))/(6*a)) if 0<x<1)
                        elif abs(b)>1e-15:
                            x=-c/(2*b)
                            if 0<x<1:roots.append(x)
                        if any(not pair[0]<=((a*x+b)*x+c)*x+d<=pair[1] for x in roots):
                            raise KinematicsError('局部导引关节包络超限')
                    from .native_finite_timing import guide_samples
                    sampled=guide_samples(self,coeff,left,span)
                    if sampled is not None:
                        code,(pe,re)=sampled
                        if code==1:raise KinematicsError('导引误差 %.5fmm/%.5f度'%(pe,re))
                        if code==2:raise KinematicsError('导引关节超限')
                    for x in (() if sampled is not None else (.25,.5,.75,1)):
                        qi=[((a*x+b)*x+c)*x+d for a,b,c,d in coeff]
                        pe,re=self.error(qi,self.point(left+span*x))
                        if self.adaptive and not self.orientation_released:
                            pe,re=super().error(qi,self.point(left+span*x))
                        guide_budget=(self.path_budget*.8 if relaxed else min(.25,self.path_budget/4)) if self.adaptive else .05
                        if pe>guide_budget or re>.05:raise KinematicsError('导引误差 %.5fmm/%.5f度'%(pe,re))
                        if any(pair and not pair[0]<=v<=pair[1] for v,pair in zip(qi,self.limits)):
                            raise KinematicsError('导引关节超限')
                    from .coupled_limits import check_cubic
                    try:check_cubic(self.model,coeff)
                    except ValueError as exc:raise KinematicsError(str(exc)) from exc
                except KinematicsError as exc:
                    failure=str(exc);span/=2
                    if span*self.length<.02 and self.adaptive and not self.orientation_released:
                        self.release_orientation(left);m0=self.tangent(q0,left);span=min(2/self.length,1-left);continue
                    if span*self.length<.02 and not self.args.get('allow_singularity_transition'):
                        raise f._ContinuousIKError('局部路径 %.3f%% 接续受限，细分已小于0.02mm：%s'%(100*left,failure)) from exc
                    continue
                from .coupled_limits import check_cubic
                check_cubic(self.model,coeff)
                self.segments.append((left,right,coeff));self.ends.append(right)
                self.guide_u=right;self.guide_q=q1;self.count+=1;break
            else:
                if self.args.get('allow_singularity_transition') and self.bridge(left,q0,m0):continue
                raise f._ContinuousIKError('局部路径 %.3f%% 无法连续接续，需预对齐：%s'%(100*left,failure))
        if not self.segments:return list(self.q0)
        i=min(len(self.segments)-1,bisect.bisect_left(self.ends,u));lo,hi,coeff=self.segments[i]
        x=(u-lo)/(hi-lo)
        return [((a*x+b)*x+c)*x+d for a,b,c,d in coeff]

    def frames(self,parameter,start_index,count,final=False):
        rows=super().frames(parameter,start_index,count,final)
        if self.adaptive:
            for row in rows:
                row['reference_rotation']=[r[:3] for r in self.model.forward(row['reference_joints_deg'])[:3]]
                row['command_rpy_deg']=matrix_to_rpy(self.model.forward(row['command_joints_deg']))
        return rows

    def state(self,t):
        if not self.schedule:return (0.,0.,0.)
        for start,duration,coeff in self.schedule:
            if t<=start+duration+1e-9:
                x=max(0.,min(1.,(t-start)/duration))
                return tuple(evaluate(coeff,x,n)/duration**n for n in range(3))
        start,duration,coeff=self.schedule[-1]
        return tuple(evaluate(coeff,1,n)/duration**n for n in range(3))

    def normal(self,t):
        if not self.schedule:return 0.
        for start,duration,coeff in self.schedule:
            if t<=start+duration+1e-9:return evaluate(coeff,max(0.,min(1.,(t-start)/duration)))
        return evaluate(self.schedule[-1][2],1.)

    def timing_frame_stamp(self):
        return (len(self.schedule),tuple(self.schedule[-1][2]),self.ahead,tuple(self.wire))

    def take_timing_frames(self,index,count,final):
        cache=getattr(self,'_validated_timing_frames',None)
        self._validated_timing_frames=None
        if cache is None:return None
        stamp,start,rows=cache
        if start!=index or len(rows)<count or stamp!=self.timing_frame_stamp():return None
        # These exact frames passed a stricter nominal ceiling in extend().
        result=rows[:count]
        result[-1]=dict(result[-1],final=bool(final))
        return result

    def reserve(self,index):
        t0=index*self.tick;begin=t0+self.ahead
        end_time=self.schedule[-1][0]+self.schedule[-1][1] if self.schedule else 0.
        if (self.schedule and end_time-begin<=1.6 and
                self.state(end_time)[0]>=1-1e-9 and abs(self.state(end_time)[1])<1e-9):
            count=max(1,round((self.schedule[-1][0]+self.schedule[-1][1]-t0)/self.tick)+1)
            return self.frames(lambda dt:self.normal(t0+dt),index,count,True)
        u,v,a=self.state(begin)
        for duration in (.4,.8,1.2,1.6,2.4,3.2):
            end=u+v*duration/2+a*duration*duration/12
            if not u<end<1:continue
            coeff=polynomial(u,v,a,end,0.,duration)
            if any(evaluate(coeff,k/100,1)<-1e-10 for k in range(101)):continue
            def parameter(dt):
                absolute=t0+dt
                return self.normal(absolute) if absolute<=begin else evaluate(coeff,min(1.,(absolute-begin)/duration))
            try:return self.frames(parameter,index,math.ceil((self.ahead+duration)/self.tick)+1,True)
            except f.TrajectoryError:continue
        raise f.TrajectoryError('局部轨迹无法生成保持已提交指令的制动段')

    def timing_envelope(self,coeff,duration,u0,u1):
        """Bound the whole new timing piece without generating its long FIFO.

        Guide cubics and timing quintics have analytic derivative envelopes.
        Subdivide by guide intervals so a slow region does not impose its
        derivative bound on the rest of this timing piece.
        """
        self.q(u1)
        from .native_finite_timing import envelope
        result=envelope(self,coeff,duration,u0,u1)
        if result is not None:
            if result==1:raise f.TrajectoryError('局部时间段速度解析包络超限')
            if result==2:raise f.TrajectoryError('局部时间段加速度解析包络超限')
            return
        inverse_cache={u0:0.,u1:1.}
        native_coeff=array(coeff)
        def inverse_u(value):
            if value in inverse_cache:return inverse_cache[value]
            if value<=u0:return 0.
            if value>=u1:return 1.
            if LIBRARY is not None and hasattr(LIBRARY,'f3p_inverse_u'):
                result=LIBRARY.f3p_inverse_u(native_coeff,value,u0,u1,32)
                inverse_cache[value]=result;return result
            lo=0.;hi=1.
            for _ in range(32):
                mid=(lo+hi)/2
                if evaluate(coeff,mid)<value:lo=mid
                else:hi=mid
            result=(lo+hi)/2;inverse_cache[value]=result;return result
        ratios=self.ratios
        for left,right,guide in self.guide_intervals(u0,u1):
            lo=max(left,u0);hi=min(right,u1)
            if hi<=lo:continue
            self.check();a=inverse_u(lo);b=inverse_u(hi)
            velocity=derivative_bound(coeff,a,b,1)/duration
            acceleration=derivative_bound(coeff,a,b,2)/duration**2
            xlo=(lo-left)/(right-left);xhi=(hi-left)/(right-left)
            for i,(first,second) in enumerate(self.guide_rates(left,right,guide,xlo,xhi)):
                motor_scale=abs(ratios[i])/6
                if first*velocity*motor_scale>self.nominal[i]*.9:
                    raise f.TrajectoryError('局部时间段速度解析包络超限')
                if (second*velocity**2+first*acceleration)*motor_scale>self.rates[i]*.7:
                    raise f.TrajectoryError('局部时间段加速度解析包络超限')

    def guide_intervals(self,lo,hi):
        # Append-only guide intervals are ordered. Avoid scanning the entire
        # completed geometry again for each local timing attempt.
        begin=bisect.bisect_right(self.ends,lo)
        stop=min(len(self.segments),bisect.bisect_left(self.ends,hi)+1)
        for index in range(begin,stop):
            segment=self.segments[index]
            if segment[0]<hi and segment[1]>lo:yield segment

    def guide_rates(self,left,right,guide,lo,hi):
        # Whole-interval bounds recur across timing retries and preview. The
        # immutable guide cubic and the Bernstein bound remain unchanged.
        whole=lo==0. and hi==1.
        if whole and right in self.guide_derivatives:return self.guide_derivatives[right]
        rates=[(derivative_bound([d,c,b,a],lo,hi,1)/(right-left),
                derivative_bound([d,c,b,a],lo,hi,2)/(right-left)**2) for a,b,c,d in guide]
        if whole:self.guide_derivatives[right]=rates
        return rates

    def extend(self,required,index,count):
        self._validated_timing_frames=None
        while not self.schedule or self.schedule[-1][0]+self.schedule[-1][1]<required-1e-9:
            start=self.schedule[-1][0]+self.schedule[-1][1] if self.schedule else 0.
            u,v,a=self.state(start)
            if u>=1-1e-9:return
            failure=''
            factors=(1.,.7,.5,.3,.15,.07,.03,.015,.007,.003)
            if self.drawing_timing:
                request=self.args['feed_mm_s']
                factors=sorted({min(request,speed)/request for speed in
                    (request,35.,25.,20.,15.,10.,7.5,5.,3.5,1.5,.75,.35,.15,request*.003)},reverse=True)
            for factor in factors:
                self.check();target_v=self.args['feed_mm_s']/self.length*factor
                duration=.8 if self.drawing_timing else max(2.8,required-start+.04)
                end=u+duration*(v+target_v)/2;end_v=target_v
                # Reserve distance to stop at the real endpoint before choosing
                # a nonzero exit speed for this local timing segment.
                if end+target_v*duration/2>=1:
                    end=1.;end_v=0.;duration=max(.2,1.875*(1-u)/max(target_v,1e-9))
                duration=math.ceil(duration/self.tick)*self.tick
                if start+duration>f.MAX_TRAJECTORY_SECONDS:
                    failure='轨迹时间超过1800秒';continue
                coeff=polynomial(u,v,a,end,end_v,duration)
                from .native_finite_timing import enabled,samples,envelope,chords
                guard=samples(coeff,u,end,duration,self.args['feed_mm_s']/self.length) if enabled(self) else None
                if guard==1 or (guard is None and any(evaluate(coeff,k/100,1)<-1e-10 or not u-1e-9<=evaluate(coeff,k/100)<=end+1e-9 for k in range(101))):continue
                if guard==2 or (guard is None and max(evaluate(coeff,k/100,1)/duration for k in range(101))>self.args['feed_mm_s']/self.length*1.001):
                    failure='局部进给峰值超过请求';continue
                self.schedule.append((start,duration,coeff))
                try:
                    self.timing_envelope(coeff,duration,u,end)
                    if self.drawing_timing:
                        # Anticipate geometry after this timing piece before
                        # committing its exit rate. A later tight joint region
                        # cannot safely lower an already committed boundary speed.
                        preview=min(1.,end+max(5./self.length,max(v,target_v)*.8))
                        self.q(preview)
                        ratios=self.ratios
                        preview_result=envelope(self,coeff,end_v,end,preview,preview=True)
                        if preview_result:raise f.TrajectoryError('后续几何需要提前降低接续速度')
                        for left,right,guide in ([] if preview_result is not None else self.guide_intervals(end,preview)):
                            if right<=end or left>=preview:continue
                            lo=max(0.,(end-left)/(right-left));hi=min(1.,(preview-left)/(right-left))
                            for i,(first,second) in enumerate(self.guide_rates(left,right,guide,lo,hi)):
                                scale=abs(ratios[i])/6
                                if first*end_v*scale>self.nominal[i]*.7 or second*end_v**2*scale>self.rates[i]*.5:
                                    raise f.TrajectoryError('后续几何需要提前降低接续速度')
                        # Motor derivatives alone miss a TCP bend/reversal:
                        # two feasible joint targets can cut across its corner.
                        # Test that future chord before committing the exit rate.
                        def future_rate(value):
                            if value>=end:return end_v
                            xl=0.;xr=1.
                            for _ in range(24):
                                xm=(xl+xr)/2
                                if evaluate(coeff,xm)<value:xl=xm
                                else:xr=xm
                            x=(xl+xr)/2;upper=min(1.,x+self.ahead/duration)
                            return max(derivative_bound(coeff,x,upper,1)/duration,
                                       end_v if upper==1. else 0.)
                        step=.5/self.length
                        values=[min(preview,u+n*step) for n in range(math.ceil((preview-u)/step)+1)]
                        rates=None
                        if LIBRARY is not None and hasattr(LIBRARY,'f3p_timing_rates'):
                            rates=array([0.]*len(values))
                            LIBRARY.f3p_timing_rates(array(coeff),duration,u,end,end_v,self.ahead,len(values),array(values),rates)
                        # Cover the WHOLE newly committed timing piece. Checking
                        # only its next FIFO block leaves its latter half fixed
                        # before a later producer discovers the bend.
                        chord_result=chords(self,values,rates) if rates is not None else None
                        if chord_result is False:raise f.TrajectoryError('后续转弯需要提前降低接续速度')
                        for n,lo in ([] if chord_result is not None else enumerate(values)):
                            rate=rates[n] if rates is not None else future_rate(lo)
                            if not math.isfinite(rate) or rate<0:raise f.TrajectoryError('原生前瞻速度无效')
                            hi=min(1.,lo+rate*self.ahead)
                            qa=self.q(lo);qb=self.q(hi)
                            for fraction in (.25,.5,.75):
                                qi=[a+fraction*(b-a) for a,b in zip(qa,qb)]
                                pe,_=self.error(qi,self.point(lo+fraction*(hi-lo)))
                                if pe>self.path_budget*.7:
                                    raise f.TrajectoryError('后续转弯需要提前降低接续速度')
                    if (start+duration>=required-1e-9 or end==1) and not getattr(self,'_finite_schedule_only',False):
                        nominal=self.nominal;self.nominal=[value*.9 for value in nominal]
                        try:
                            # Only check actual frames after this call's full
                            # time window is covered; intermediate timing pieces
                            # have already passed their analytic/chord envelopes.
                            checked=self.frames(lambda dt:self.normal(index*self.tick+dt),index,count)
                            if self.args.get('finite_complete') and not self.adaptive:
                                self._validated_timing_frames=(self.timing_frame_stamp(),index,checked)
                        finally:self.nominal=nominal
                        # This stricter ceiling covers the normal ceiling too.
                        if not self.args.get('finite_complete'):
                            reserve=self.reserve(index+count)
                            response=getattr(self,'response_guard',None)
                            if response is not None:response.preview(checked,reserve)
                except (f.TrajectoryError,KinematicsError) as exc:
                    failure=str(exc);self.schedule.pop();self._validated_timing_frames=None;continue
                break
            else:raise f.TrajectoryError('局部速度/前视/制动预检失败：'+failure)
            if end==1:
                self.duration=start+duration;self.steps=round(self.duration/self.tick);return


def plan_local(model,motor,target,*,check_cancel=None,**args):
    if args.get('finite_complete') and args.get('joint_speed_deg_s',20)>20:
        from .axis_speed import prepare_with_speed_retry
        return prepare_with_speed_retry(_plan_local_once,model,motor,target,check_cancel,args)
    return _plan_local_once(model,motor,target,check_cancel=check_cancel,**args)

def _plan_local_once(model,motor,target,*,check_cancel=None,**args):
    defer_producer=args.pop('_defer_producer',False)
    if defer_producer and args.get('allow_singularity_transition'):
        raise f.TrajectoryError('完整奇异过渡不能延后后台规划')
    began=time.monotonic();cancel=threading.Event()
    block_began=[began]
    def check():
        if cancel.is_set():raise f.TrajectoryError('局部规划已取消')
        if check_cancel is not None and check_cancel():raise f.TrajectoryError('局部规划已取消')
        if time.monotonic()-block_began[0]>f.MAX_PLAN_SECONDS:raise f.TrajectoryError('局部计算超时')
    disabled=args.pop('_wrist_prefix_disabled',False)
    if (not disabled and args.get('kind','line') in ('line','arc')
            and not args.get('allow_singularity_transition') and not args.get('allow_orientation_adjustment')):
        from .wrist_rolling import prepare
        prefix=prepare(model,motor,target,args,check,lambda:block_began.__setitem__(0,time.monotonic()))
        if prefix is not None:
            prefix['initial_planning_seconds']=time.monotonic()-began
            return prefix
    if args.get('finite_complete'):
        from .finite_trajectory import prepare as prepare_finite
        return prepare_finite(model,motor,target,args,check,began)
    attempts=[]
    # A long horizon can force the initial block to crawl to satisfy
    # Cartesian interpolation. Each horizon enforces its own ACC/RPM envelope.
    horizons=(.8,.4,.2,.12,.08)
    if args.get('prefer_short_lookahead'):
        # The horizon already lowers wire/nominal RPM to the selected ACC.
        # Requiring it to support every *requested* cap previously switched
        # 30deg/s drawing back to .8s. Integer RPM on direct-drive J6 then
        # advances the wrist much farther than the geared arm axes.
        horizons=(.2,.12,.08,.4,.8)
    for ahead in horizons:
        check();curve=LocalCurve(model,motor,target,args,check,ahead)
        try:
            response=None
            if not curve.adaptive:
                from .streaming_response import ResponseGuard
                response=ResponseGuard(curve.model,motor,check)
                curve.response_guard=response
            if args.get('allow_singularity_transition'):curve.q(1.)
            initial=30 if curve.drawing_timing else 50
            curve.extend(initial*curve.tick+ahead+.04,0,initial)
            count=min(initial,curve.steps+1);head=curve.frames(curve.normal,0,count,count==curve.steps+1)
            reserve=[] if head[-1]['final'] else curve.reserve(count)
            if response is not None:response.accept(head,reserve)
        except ValueError as exc:attempts.append(dict(lookahead_seconds=ahead,error=str(exc)));continue
        break
    else:raise f.TrajectoryError('局部滚动起步未通过：'+attempts[-1]['error'])
    frames=RollingFrames(head,reserve,curve.duration,cancel)
    def produce():
        index=count
        try:
            while index<=curve.steps:
                check()
                with frames.lock:ready=len(frames.head);consumed=getattr(frames,'consumed',0)
                if ready-consumed>250 and not args.get('allow_singularity_transition'):
                    idle=time.monotonic();cancel.wait(.02);block_began[0]+=time.monotonic()-idle;continue
                block_began[0]=time.monotonic()
                batch=20 if curve.drawing_timing and index<count+40 else 50
                curve.extend((index+batch)*curve.tick+curve.ahead+.04,index,min(batch,curve.steps+1-index))
                size=min(batch,curve.steps+1-index)
                normal=curve.frames(lambda dt:curve.normal(index*curve.tick+dt),index,size,index+size==curve.steps+1)
                tail=[] if normal[-1]['final'] else curve.reserve(index+size)
                if response is not None:response.accept(normal,tail)
                # Completion and its metadata must be one atomic publication;
                # otherwise the IPC worker can send "done" with stale targets.
                with frames.lock:
                    if not frames.publish(normal,tail):break
                    if response is not None:native['streaming_response_checks']=response.report()
                    if normal[-1]['final']:
                        native.update(final_motor_deg=list(normal[-1]['command_motor_deg']),
                            final_pulses=list(normal[-1]['motor_target_pulses']),duration_s=normal[-1]['t_s'],
                            total_frames=index+size,final_target_pending=False)
                index+=size
        except Exception as exc:
            with frames.lock:frames.error='局部后续规划失败，沿已校验制动段停车：'+str(exc)
    frames.producer=threading.Thread(target=produce,name='cartesian-local-producer',daemon=True)
    native=dict(frames=frames,start_motor_deg=list(motor),start_xyz_mm=curve.start,target_xyz_mm=list(target),
        final_motor_deg=list(motor),final_pulses=[round(m*p/360) for m,p in zip(motor,curve.ppr)],
        final_target_pending=not frames.complete,requested_feed_mm_s=args['feed_mm_s'],
        duration_s=max(2.8,curve.length/args['feed_mm_s']*2),duration_estimated=True,total_frames=None,path_length_mm=curve.length,
        kind=args.get('kind','line'),rpy_deg=curve.rpy,tick_seconds=.04,lookahead_seconds=curve.ahead,
        lookahead_attempts=attempts,peak_feed_mm_s=max(evaluate(c,k/100,1)/d*curve.length
            for _t,d,c in curve.schedule for k in range(101)),effective_feed_mm_s=None,
        motor_speed_caps_rpm=curve.caps,wire_speed_caps_rpm=curve.wire,
        motor_acceleration_rpm_s=curve.rates,slowdown_reasons=['局部速度按关节与制动条件调整'],arc=curve.arc,
        rolling=True,local_planning=True,initial_planning_seconds=time.monotonic()-began,
        geometry_samples=curve.count+1,initial_geometry_fraction=curve.guide_u,
        collision_checked=False,physical_accuracy_verified=False)
    if response is not None:native['streaming_response_checks']=response.report()
    if curve.adaptive:
        native.update(orientation_policy='adaptive_position',orientation_reference_in_frames=True,
                      position_tolerance_mm=curve.path_budget,drawing_position_budget_mm=curve.path_budget)
    if frames.complete:
        native.update(final_motor_deg=list(head[-1]['command_motor_deg']),final_pulses=list(head[-1]['motor_target_pulses']),
            duration_s=head[-1]['t_s'],total_frames=len(head))
    if not defer_producer:frames.producer.start()
    if args.get('allow_singularity_transition'):
        # Exceptional geometry must have a validated exit and a complete timed
        # path before actual motion; do not start a bridge from a partial cache.
        try:
            while frames.producer.is_alive():check();frames.producer.join(.02)
            if frames.error:raise f.TrajectoryError(frames.error)
            if not frames.complete:raise f.TrajectoryError('奇异过渡完整轨迹未完成')
            native.update(singularity_transitions=list(curve.transitions),
                          singularity_deviation_mm=curve.transition_tolerance,
                          complete_before_start=True,duration_estimated=False)
        except Exception:frames.close();raise
    return native
