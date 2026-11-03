"""Model-only rolling frame producer with a validated terminal-stop reserve.

Solve a bounded geometric guide first. Each published block includes checked
normal frames and an independently checked C2 braking tail. Only the consumer
chooses continuation or the reserve; a late producer never empties the FIFO.
"""
import copy
import math
import threading
import time
from collections.abc import Sequence
from . import fast_trajectory as f
from .native_math import PlanningModel
from .reference_endpoint.kinematics import matrix_to_rpy, KinematicsError


class RollingFrames(Sequence):
    def __init__(self, head, reserve, duration, cancel):
        self.lock=threading.RLock();self.head=list(head);self.reserve=list(reserve)
        self.duration=duration;self.cancel=cancel;self.closed=False;self.failed=''
        self.error='';self.complete=bool(head[-1]['final']);self.producer=None
        self.started=time.monotonic()
        self.discarded=0
    def __deepcopy__(self,memo):return self
    def __len__(self):
        with self.lock:return len(self.head)+len(self.reserve)
    def __getitem__(self,i):
        with self.lock:
            size=len(self.head)+len(self.reserve)
            if isinstance(i,slice):return [self[j] for j in range(*i.indices(size))]
            if i<0:i+=size
            if not 0<=i<size:raise IndexError(i)
            value=self.head[i] if i<len(self.head) else self.reserve[i-len(self.head)]
            if value is None:raise IndexError('past rolling feedback retention window')
            return value
    def publish(self,head,reserve):
        with self.lock:
            if self.closed:return False
            self.head.extend(head);self.reserve=list(reserve);self.complete=bool(self.head[-1]['final'])
            return True
    def take(self,index,count,plan):
        with self.lock:
            if count<=0:return []
            if not self.complete:
                plan['duration_seconds']=self.reserve[-1]['t_s'] if self.reserve else self.head[-1]['t_s']
            if self.complete:
                last=self.head[-1]
                plan.update(motor_target_deg=list(last['command_motor_deg']),
                    target_position_mm=list(last['command_xyz_mm']),duration_seconds=last['t_s'])
                if 'command_rpy_deg' in last:plan['target_rpy_deg']=list(last['command_rpy_deg'])
            if index>=len(self.head) and not self.complete and not self.closed:
                self.closed=True;self.cancel.set()
                self.failed=self.error or '后续规划未及时完成，已沿校验过的制动段停车；请核对当前位置后重试'
                last=self.reserve[-1]
                plan.update(motor_target_deg=list(last['command_motor_deg']),
                    target_position_mm=list(last['command_xyz_mm']))
                if 'command_rpy_deg' in last:plan['target_rpy_deg']=list(last['command_rpy_deg'])
            upper=len(self.head) if not self.closed else len(self.head)+len(self.reserve)
            result=copy.deepcopy(self[index:min(upper,index+count)])
            self.consumed=index+len(result)
            discard=max(0,index-256)
            for old in range(self.discarded,discard):self.head[old]=None
            self.discarded=discard
            return result
    def close(self):
        self.cancel.set()
        with self.lock:self.closed=True
        if self.producer and self.producer.is_alive() and self.producer is not threading.current_thread():self.producer.join(.5)


def _d(s):return 30*s*s*(1-s)*(1-s)
def _dd(s):return 60*s-180*s*s+120*s*s*s


class Curve:
    def __init__(self,model,motor,target,args,check):
        self.model=PlanningModel(model.profile);self.motor=list(motor);self.args=args;self.check=check
        self.tick=.04;self.ahead=.8;self.q0=self.model.motor_to_joints(motor)
        self.origin=self.model.forward(self.q0);self.start=[r[3] for r in self.origin[:3]]
        self.point,self.length,self.arc=f._path_geometry(self.start,target,args.get('kind','line'),args.get('via_mm'))
        if self.length>f.MAX_PATH_MM:raise f.TrajectoryError('路径超过 1000 mm')
        self.limits=self.model.joint_limits_deg
        self.ppr=f._six(args['pulses_per_rev'],1,0xffffffff,'PPR')
        self.acc=f._six(args['acceleration'],1,255,'ACC')
        self.caps=f._six(args['speed_caps_rpm'],1,3000,'RPM')
        self.rates=[1/((256-a)*50e-6) for a in self.acc]
        profile=self.model.profile;profile['solver'].update(position_tolerance_mm=.03,
            orientation_tolerance_deg=.02,max_seeds=3,max_iterations=120)
        solver=PlanningModel(profile);rpy=matrix_to_rpy(self.origin)
        count=max(16,int(math.ceil(self.length/2)))
        while count<=1600:
            check();qs=[self.q0];previous=self.q0;refine=False;failure=''
            for i in range(1,count+1):
                check()
                try:q=solver.solve(self.point(i/count),rpy,previous,limits_deg=self.limits)
                except KinematicsError as exc:
                    refine=True;failure='路径 %.3f%% 连续逆解失败：%s'%(100*i/count,exc);break
                from .coupled_limits import nearest_legal_winding
                try:q=nearest_legal_winding(self.model,q,previous)
                except KinematicsError as exc:
                    refine=True;failure='路径 %.3f%% 条件限位接续失败：%s'%(100*i/count,exc);break
                change=max(abs(a-b) for a,b in zip(q,previous))
                # Larger geometric increments trigger subdivision, never a
                # discontinuous executable command across a wrist branch.
                if change>6:
                    refine=True;failure='路径 %.3f%% 关节分支变化 %.3f度超过6度'%(100*i/count,change);break
                qs.append(q);previous=q
            if refine:
                if count==1600:raise f._ContinuousIKError('滚动导引细分至1600段仍不连续，需预对齐：'+failure)
                count=min(1600,count*2);continue
            self.count=count;self.coefficients=[]
            for i in range(count):
                p0,p1=qs[i],qs[i+1]
                m0=[(b-a)/2 for a,b in zip(qs[i-1],p1)] if i else [(-3*a+4*b-c)/2 for a,b,c in zip(p0,p1,qs[2])]
                m1=[(b-a)/2 for a,b in zip(p0,qs[i+2])] if i+1<count else [(3*b-4*a+c)/2 for a,b,c in zip(p0,p1,qs[i-1])]
                self.coefficients.append([(2*a-2*b+c+d,-3*a+3*b-2*c-d,c,a) for a,b,c,d in zip(p0,p1,m0,m1)])
            acceptable=True
            for i in range(count):
                for fraction in (.25,.5,.75,1):
                    check();u=(i+fraction)/count;q=self.q(u)
                    pe,re=self.error(q,self.point(u))
                    if pe>.08 or re>.08:
                        acceptable=False;failure='路径 %.3f%%，位置误差 %.5fmm，朝向误差 %.5f度'%(100*u,pe,re);break
                if not acceptable:break
            if acceptable:break
            if count==1600:raise f.TrajectoryError('滚动几何导引细分至1600段仍超出0.08mm/0.08度：'+failure)
            count=min(1600,count*2)
        else:raise f.TrajectoryError('滚动几何导引无法满足模型误差，需完整规划')
        slopes=[0.]*6;curvatures=[0.]*6;ratios=self.model.profile['motor_mapping']['ratios']
        for segment in self.coefficients:
            for j,(a,b,c,d) in enumerate(segment):
                roots=[0.,1.]
                if abs(a)>1e-15:
                    v=-b/(3*a)
                    if 0<v<1:roots.append(v)
                slopes[j]=max(slopes[j],max(abs((3*a*v*v+2*b*v+c)*count*ratios[j]) for v in roots))
                curvatures[j]=max(curvatures[j],max(abs((6*a*v+2*b)*count*count*ratios[j]) for v in (0,1)))
                extrema=[0.,1.]
                if abs(a)>1e-15:
                    disc=4*b*b-12*a*c
                    if disc>=0:extrema.extend(v for v in ((-2*b+math.sqrt(disc))/(6*a),(-2*b-math.sqrt(disc))/(6*a)) if 0<v<1)
                elif abs(b)>1e-15:
                    v=-c/(2*b)
                    if 0<v<1:extrema.append(v)
                pair=self.limits[j]
                if pair and any(not pair[0]<=((a*v+b)*v+c)*v+d<=pair[1] for v in extrema):
                    raise f.TrajectoryError('滚动导引的关节包络超过限位')
        self.slopes=slopes;self.curvatures=curvatures
        self.configure_timing(self.ahead)

    def configure_timing(self,ahead):
        # Reuse the checked geometry; shorter lookahead also reduces the wire
        # speed budget, rather than changing only the interpolation samples.
        self.ahead=ahead
        self.wire=[min(c,max(1,int(r*ahead*.35))) for c,r in zip(self.caps,self.rates)]
        self.nominal=[c*.7 for c in self.wire]
        requested=self.args.get('joint_speed_deg_s')
        if requested is not None:
            self.nominal=[min(v,requested*abs(r)/6) for v,r in zip(self.nominal,self.model.profile['motor_mapping']['ratios'])]
        requested_duration=1.875*self.length/self.args['feed_mm_s']
        speed_duration=max(s*1.875/(6*v) for s,v in zip(self.slopes,self.nominal))
        accel_duration=max(math.sqrt((c*1.875**2+s*5.78)/(6*r*.5)) for c,s,r in zip(self.curvatures,self.slopes,self.rates))
        self.duration=math.ceil(max(.2,requested_duration,speed_duration,accel_duration)/self.tick)*self.tick
        if self.duration>f.MAX_TRAJECTORY_SECONDS:raise f.TrajectoryError('轨迹时间超出上限')
        self.steps=round(self.duration/self.tick);self.reasons=[]
        if speed_duration>requested_duration:self.reasons.append('关节速度或ACC/前视制动上限限制进给')
        if accel_duration>max(requested_duration,speed_duration):self.reasons.append('统一起停与曲线加速度包络限制进给')
    def q(self,u):
        x=max(0.,min(1.,u))*self.count;i=min(self.count-1,int(x));v=x-i
        return [((a*v+b)*v+c)*v+d for a,b,c,d in self.coefficients[i]]
    def error(self,q,xyz):
        expected=[self.origin[i][:3]+[xyz[i]] for i in range(3)]+[[0,0,0,1]]
        pe,re=f.planning_pose_error(self.model.forward(q),expected)
        return f._norm(pe),math.degrees(f._norm(re))
    def normal(self,t):return f._smooth(max(0.,min(1.,t/self.duration)))
    def row(self,u):
        self.check();q=self.q(u);xyz=self.point(u);motor=self.model.joints_to_motor(q)
        pulses=[round(m*p/360) for m,p in zip(motor,self.ppr)]
        if any(not -2147483648<=p<=2147483647 for p in pulses):raise f.TrajectoryError('绝对脉冲超出signed32')
        quantized=[p*360/r for p,r in zip(pulses,self.ppr)];qq=self.model.motor_to_joints(quantized)
        for angles in (q,qq):
            if any(pair and not pair[0]-1e-9<=v<=pair[1]+1e-9 for v,pair in zip(angles,self.limits)):
                raise f.TrajectoryError('滚动帧量化或参考关节超过限位')
            pe,re=self.error(angles,xyz)
            if pe>self.position_budget(u) or re>.12:raise f.TrajectoryError('滚动帧模型误差超过允许路径偏离/0.12度')
        if any(abs(m)*65536/360>0xffffffff for m in motor+quantized):raise f.TrajectoryError('角度超出反馈范围')
        return dict(u=u,q=q,xyz=xyz,motor=motor,pulses=pulses,quantized=quantized)
    def frames(self,parameter,start_index,count,final=False):
        from .native_curve_frames import frames as native_frames
        batch=native_frames(self,parameter,start_index,count,final)
        if batch is not None:return batch
        # Extra future samples validate every command and all three internal
        # lookahead interpolation points before a block can be published.
        ahead=round(self.ahead/self.tick);rows=[self.row(parameter(k*self.tick)) for k in range(count+ahead)]
        for a,b in zip(rows,rows[1:]):
            if max(abs(x-y) for x,y in zip(a['q'],b['q']))>5:raise f.TrajectoryError('滚动帧关节连续性超限')
        for j in range(6):
            speeds=[(b['motor'][j]-a['motor'][j])/(6*self.tick) for a,b in zip(rows,rows[1:])]
            if max(abs(v) for v in speeds)>self.nominal[j]*1.015:raise f.TrajectoryError('滚动帧速度超过包络')
            if any(abs(b-a)/self.tick>self.rates[j]*.7*1.015 for a,b in zip(speeds,speeds[1:])):
                raise f.TrajectoryError('滚动帧加速度超过包络')
        window_speeds=f._window_speeds(rows,self.tick,ahead)
        result=[]
        for k in range(count):
            row=rows[k];command=rows[k+ahead]
            from .collision import check_joint_box
            from .coupled_limits import check_model_box
            check_model_box(self.model,row['q'],self.model.motor_to_joints(command['quantized']))
            check_joint_box(row['q'],self.model.motor_to_joints(command['quantized']),self.check)
            for fraction in (.25,.5,.75):
                q=[a+fraction*(b-a) for a,b in zip(row['q'],command['q'])]
                pe,re=self.error(q,self.point(row['u']+fraction*(command['u']-row['u'])))
                u=row['u']+fraction*(command['u']-row['u'])
                if pe>self.position_budget(u) or re>.2:raise f.TrajectoryError('滚动前视插值误差超限，需完整缩短前视规划')
            speeds=[min(cap,max(1,math.ceil(window_speeds[k][i]*1.1))) for i,cap in enumerate(self.wire)]
            result.append(dict(seq=start_index+k+1,t_s=(start_index+k)*self.tick,phase='cartesian',
                reference_u=row['u'],reference_xyz_mm=row['xyz'],reference_joints_deg=row['q'],reference_motor_deg=row['motor'],
                command_t_s=(start_index+k+ahead)*self.tick,command_reference_u=command['u'],command_xyz_mm=command['xyz'],command_joints_deg=command['q'],
                command_motor_deg=command['quantized'],motor_target_pulses=command['pulses'],speed_rpm=speeds,
                acceleration=list(self.acc),final=bool(final and k==count-1)))
        return result
    def position_budget(self,u):return .1

    def reserve(self,index):
        t0=index*self.tick;begin=min(self.duration,t0+self.ahead)
        # Commands already committed project forward by the selected horizon. Continue their
        # validated reference until that point, then make a C2 stop.
        if self.duration-begin<=1.6:
            count=self.steps-index+1
            return self.frames(lambda dt:self.normal(t0+dt),index,count,True)
        s=begin/self.duration;u0=self.normal(begin);v0=_d(s)/self.duration;a0=_dd(s)/self.duration**2
        for duration in (.8,1.2,1.6,2.4,3.2):
            end=u0+v0*duration/2+a0*duration*duration/12
            if not u0<end<1:continue
            c0=u0;c1=v0*duration;c2=a0*duration*duration/2
            delta=end-c0;c3=10*delta-6*c1-3*c2;c4=-15*delta+8*c1+3*c2;c5=6*delta-3*c1-c2
            def parameter(dt):
                absolute=t0+dt
                if absolute<=begin:return self.normal(absolute)
                x=min(1.,(absolute-begin)/duration)
                return c0+x*(c1+x*(c2+x*(c3+x*(c4+x*c5))))
            if any(parameter(self.ahead+duration*k/100)>parameter(self.ahead+duration*(k+1)/100)+1e-12 for k in range(100)):continue
            count=math.ceil((self.ahead+duration)/self.tick)+1
            try:return self.frames(parameter,index,count,True)
            except f.TrajectoryError:continue
        raise f.TrajectoryError('无法生成校验通过的滚动制动备用段，需完整规划')


def plan_rolling(model,motor,target,*,check_cancel=None,**args):
    cancel=threading.Event();began=time.monotonic()
    def check():
        if cancel.is_set():raise f.TrajectoryError('滚动规划已结束或取消')
        if check_cancel is not None and check_cancel():raise f.TrajectoryError('滚动规划已取消')
        if time.monotonic()-began>f.MAX_PLAN_SECONDS:raise f.TrajectoryError('滚动计算超时')
    curve=Curve(model,motor,target,args,check)
    block=50;attempts=[]
    for ahead in (.8,.4,.2,.12,.08):
        check();curve.configure_timing(ahead)
        count=min(block,curve.steps+1)
        try:
            head=curve.frames(curve.normal,0,count,count==curve.steps+1)
            reserve=[] if head[-1]['final'] else curve.reserve(count)
        except f.TrajectoryError as exc:
            reason=str(exc)
            attempts.append(dict(lookahead_seconds=ahead,error=reason))
            if not (reason.startswith('滚动前视插值误差超限') or
                    reason.startswith('无法生成校验通过的滚动制动备用段')):
                raise
        else:break
    else:raise f.TrajectoryError('缩短前视后滚动起步仍未通过：'+attempts[-1]['error'])
    frames=RollingFrames(head,reserve,curve.duration,cancel)
    def produce():
        nonlocal began
        index=count
        try:
            while index<=curve.steps:
                check()
                # Bound software buffering to ten seconds, including the stop
                # reserve. The transport remains the sole CAN owner.
                with frames.lock:queued=getattr(frames,'consumed',0);ready=len(frames.head)
                if ready-queued>250:
                    idle_started=time.monotonic();cancel.wait(.02)
                    began+=time.monotonic()-idle_started
                    continue
                size=min(block,curve.steps+1-index)
                normal=curve.frames(lambda dt:curve.normal(index*curve.tick+dt),index,size,index+size==curve.steps+1)
                tail=[] if normal[-1]['final'] else curve.reserve(index+size)
                if not frames.publish(normal,tail):break
                index+=size
        except Exception as exc:
            with frames.lock:frames.error='后续规划失败，沿已校验制动段停车：'+str(exc)
    frames.producer=threading.Thread(target=produce,name='cartesian-frame-producer',daemon=True)
    final=curve.row(1)
    native=dict(frames=frames,start_motor_deg=list(motor),start_xyz_mm=curve.start,target_xyz_mm=list(target),
        final_motor_deg=final['quantized'],final_pulses=final['pulses'],duration_s=curve.duration,total_frames=curve.steps+1,
        path_length_mm=curve.length,kind=args.get('kind','line'),rpy_deg=matrix_to_rpy(curve.origin),
        tick_seconds=.04,lookahead_seconds=curve.ahead,lookahead_attempts=attempts,peak_feed_mm_s=1.875*curve.length/curve.duration,
        effective_feed_mm_s=curve.length/curve.duration,motor_speed_caps_rpm=curve.caps,wire_speed_caps_rpm=curve.wire,
        motor_acceleration_rpm_s=curve.rates,slowdown_reasons=curve.reasons,arc=curve.arc,
        rolling=True,initial_planning_seconds=time.monotonic()-began,geometry_samples=curve.count+1,
        collision_checked=False,physical_accuracy_verified=False)
    frames.producer.start()
    return native
