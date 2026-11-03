"""Validated bounded near-zero wrist prefix followed by the existing rolling planner.

Only the existing prepared-candidate checks produce the prefix. Measured near-zero
feedback is restored and checked against the original TCP before publication.
"""
import math,os,threading,time

def trace(kind,data):
    if os.environ.get('F3P_TRACE_PLANNING')=='1':print(kind,data,flush=True)
from . import fast_trajectory as f
from .rolling_trajectory import RollingFrames
from .native_math import PlanningModel
from .reference_endpoint.kinematics import matrix_to_rpy

def prepare(model,motor,target,args,check,reset_clock=lambda:None):
    began=time.monotonic()
    q0=model.motor_to_joints(motor)
    geometry=model.profile['geometry']
    aligned=-geometry['offset_sign']*geometry['joint_offsets_deg'][4]
    aligned+=360*round((q0[4]-aligned)/360)
    offset=q0[4]-aligned
    if abs(offset)>f.WRIST_ALIGNMENT_ELIGIBILITY_DEG+1e-12:return None
    approximate=abs(offset)>1e-9
    geometry_q=list(q0);geometry_q[4]=aligned
    origin=model.forward(q0);xyz=[row[3] for row in origin[:3]]
    kind=args.get('kind','line')
    point,length,_=f._path_geometry(xyz,target,kind,args.get('via_mm'))
    if length<.2:return None
    from .analytic_inverse import fixed_pose
    probe=fixed_pose(model,point(.02/length),[row[:3] for row in origin[:3]],q0,model.joint_limits_deg,check)
    if probe is None or max(abs(a-b) for a,b in zip(probe,q0))<=6:return None
    from .reference_endpoint.wrist_preparation import preparation_candidates
    tangent=[(b-a)/.02 for a,b in zip(xyz,point(.02/length))]
    candidates=preparation_candidates(model,geometry_q,tangent,model.joint_limits_deg,check)
    chosen=None
    for q in candidates:
        check()
        guide_origin=model.forward(q)
        shift=[guide_origin[i][3]-origin[i][3] for i in range(3)]
        candidate=fixed_pose(model,[v+d for v,d in zip(point(.02/length),shift)],
            [row[:3] for row in guide_origin[:3]],q,model.joint_limits_deg,check)
        if candidate is not None and max(abs(a-b) for a,b in zip(candidate,q))<=6:
            chosen=q;break
    if chosen is None:return None
    guide_q=list(chosen);q=list(chosen);q[4]+=offset;prepared_motor=model.joints_to_motor(q)
    guide_origin=model.forward(guide_q)
    shift=[guide_origin[i][3]-origin[i][3] for i in range(3)]
    tail_target=[v+d for v,d in zip(target,shift)]
    tail_args=dict(args)
    if args.get('via_mm') is not None:tail_args['via_mm']=[v+d for v,d in zip(args['via_mm'],shift)]
    if args.get('nominal_start_mm') is not None:tail_args['nominal_start_mm']=[v+d for v,d in zip(args['nominal_start_mm'],shift)]
    from .wrist_restore import Residual,Restorer
    residual=Residual(model,origin)
    restorer=Restorer(model,origin,point,offset,args,check) if approximate else None
    from .rolling_trajectory import Curve
    from .planning_residual import planning_joint_error
    limits=model.joint_limits_deg
    # Same fixed-TCP eligibility and original-pose checks as the full planner.
    checks=max(2,math.ceil(abs(q[3]-q0[3])))
    ideal_p=ideal_r=0.
    for i in range(checks+1):
        check();angles=[a+(b-a)*i/checks for a,b in zip(q0,q)]
        pe,re=residual.error(angles,xyz)
        ideal_p=max(ideal_p,pe);ideal_r=max(ideal_r,re)
        if pe>.01 or re>.02:raise f.TrajectoryError('腕部预对齐原始姿态误差超过0.01mm / 0.02度')
    from .collision import check_joint_box
    from .coupled_limits import check_model_box
    check_model_box(model,q0,q)
    check_joint_box(q0,q,check)
    class WristCurve(Curve):
        native_frames=True
        strict_ideal=approximate
        def __init__(self):
            self.model=model;self.args=args;self.check=check;self.tick=.04;self.ahead=.8
            self.q0=list(q0);self.origin=origin;self.start=xyz;self.point=lambda u:list(xyz)
            self.length=0.;self.limits=limits
            self.ppr=f._six(args['pulses_per_rev'],1,0xffffffff,'PPR')
            self.acc=f._six(args['acceleration'],1,255,'ACC');self.caps=f._six(args['speed_caps_rpm'],1,3000,'RPM')
            self.rates=[1/((256-a)*50e-6) for a in self.acc]
            self.slopes=[abs(a-b) for a,b in zip(motor,prepared_motor)];self.curvatures=[0.]*6
            self.row_cache={}
            self.configure_timing(.8)
        def q(self,u):
            u=max(0.,min(1.,u));return [a+(b-a)*u for a,b in zip(q0,q)]
        def error(self,angles,point):
            return residual.error(angles,xyz)
        def row(self,u):
            self.check()
            if u in self.row_cache:return self.row_cache[u]
            row=super().row(u)
            if approximate:
                pe,re=self.error(row['q'],xyz)
                if pe>.01 or re>.02:raise f.TrajectoryError('近零预对齐理想姿态误差超过0.01mm / 0.02度')
            if len(self.row_cache)>=512:self.row_cache.clear()
            self.row_cache[u]=row
            return row
        def frames(self,*a,**kw):
            rows=super().frames(*a,**kw)
            for row in rows:
                row['phase']='wrist_preparation';row['reference_u']=0.
                if args.get('finite_complete'):
                    active=[i for i,d in enumerate(self.slopes) if d>1e-8]
                    if active:
                        # FD synchronizes start, not arrival. Integer RPMs
                        # must share the same joint progress during fixed-TCP
                        # wrist alignment, rather than ceil each axis alone.
                        base=min(active,key=self.slopes.__getitem__)
                        ceiling=min(self.caps[i]*self.slopes[base]/self.slopes[i] for i in active)
                        speed=min(row['speed_rpm'][base],math.floor(ceiling+1e-9))
                        if speed<1:raise f.TrajectoryError('腕部同步速度无法用整数RPM表示')
                        row['speed_rpm']=[max(1,min(self.caps[i],round(speed*self.slopes[i]/self.slopes[base])))
                            if i in active else 1 for i in range(6)]
            return rows
    curve=WristCurve();steps=curve.steps;duration=curve.duration
    if steps+50>f.MAX_FRAMES:raise f.TrajectoryError('腕部预对齐超过总帧数限制')
    # A 32-frame FIFO prefetches before reference time reaches the head end.
    # Keep four seconds of checked prefix so tail startup and the first block
    # can finish before the transport consumes the software lead.
    count=min(400 if args.get('finite_complete') else 100,steps)
    head=curve.frames(curve.normal,0,count,False)
    # Finite positioning cannot be consumed until the whole path is checked.
    # Only streaming preparation needs intermediate emergency braking tails.
    reserve=[] if args.get('finite_complete') else curve.reserve(count)
    cancel=threading.Event();first_tail=threading.Event();tail_checked=threading.Event();frames=RollingFrames(head,reserve,duration,cancel)
    finite=bool(args.get('finite_complete'))
    if not finite and approximate and steps>=100 and os.environ.get('F3P_PLANNER_CHILD')=='1':
        frames.background_ready=threading.Event()
    prep=dict(kind='fixed_tcp_wrist_alignment',duration_s=duration,frames=steps,start_joints_deg=list(q0),end_joints_deg=list(q),
        ideal_max_position_error_mm=ideal_p,ideal_max_orientation_error_deg=ideal_r,approximate_start=approximate,eligibility_angle_deg=f.WRIST_ALIGNMENT_ELIGIBILITY_DEG,measured_wrist_offset_deg=offset)
    native=dict(frames=frames,start_motor_deg=list(motor),start_xyz_mm=xyz,target_xyz_mm=list(target),
        final_motor_deg=list(motor),final_pulses=[round(m*p/360) for m,p in zip(motor,curve.ppr)],final_target_pending=True,
        duration_s=duration+max(2.8,length/args['feed_mm_s']*2),duration_estimated=True,total_frames=None,path_length_mm=length,
        kind=kind,rpy_deg=matrix_to_rpy(origin),tick_seconds=.04,lookahead_seconds=.8,lookahead_attempts=[],
        requested_feed_mm_s=args['feed_mm_s'],peak_feed_mm_s=0.,effective_feed_mm_s=None,
        motor_speed_caps_rpm=curve.caps,wire_speed_caps_rpm=curve.wire,motor_acceleration_rpm_s=curve.rates,
        slowdown_reasons=['腕部预对齐并保留实测零位偏差，随后滚动规划路径；ACC保持用户设置'],arc=None,
        rolling=True,local_planning=True,geometry_samples=checks+1,initial_geometry_fraction=0.,
        collision_checked=False,physical_accuracy_verified=False,preparation=prep)
    def shifted(rows):
        return [dict(row,seq=row['seq']+steps,t_s=row['t_s']+duration,command_t_s=row['command_t_s']+duration) for row in rows]
    def produce():
        inner=None
        try:
            def producer_check():
                if cancel.is_set():raise f.TrajectoryError('腕部滚动预对齐已取消')
                check()
            from .local_trajectory import plan_local
            reset_clock()
            trace('WRIST_TAIL_BEGIN',dict(seconds=time.monotonic()-began,prefix_frames=steps))
            tail=plan_local(model,model.joints_to_motor(guide_q),tail_target,check_cancel=producer_check,_wrist_prefix_disabled=True,_defer_producer=True,**tail_args)
            trace('WRIST_TAIL_READY',dict(seconds=time.monotonic()-began,initial_frames=len(tail['frames'].head)))
            inner=tail['frames'];index=count
            if restorer and not finite:
                with inner.lock:initial_rows=list(inner.head);initial_reserve=list(inner.reserve)
                restorer.check=producer_check;restorer.restore(initial_rows);restorer.restore(initial_reserve)
            tail_checked.set()
            gate=getattr(frames,'background_ready',None)
            if gate is not None:
                while not gate.wait(.01):producer_check()
            inner.producer.start()
            if not tail.get('duration_estimated',False) and duration+tail['duration_s']>f.MAX_TRAJECTORY_SECONDS:
                raise f.TrajectoryError('腕部预对齐加路径超过总时长限制')
            def wait_capacity():
                if finite:return
                while len(frames.head)-getattr(frames,'consumed',0)>250:
                    if cancel.is_set():raise f.TrajectoryError('腕部滚动预对齐已取消')
                    cancel.wait(.02);reset_clock()
            while index<steps:
                reset_clock();producer_check();wait_capacity();size=min(200 if finite else 50,steps-index)
                block_started=time.monotonic()
                trace('WRIST_PREFIX_BLOCK_BEGIN',dict(index=index,seconds=block_started-began))
                rows=curve.frames(lambda dt:curve.normal(index*.04+dt),index,size,False)
                trace('WRIST_PREFIX_BLOCK_FRAMES',dict(index=index,seconds=time.monotonic()-block_started))
                reserve=[] if finite else curve.reserve(index+size)
                trace('WRIST_PREFIX_BLOCK_READY',dict(index=index,seconds=time.monotonic()-block_started))
                frames.publish(rows,reserve);index+=size
            # Switch only at the checked zero-velocity alignment endpoint.
            index=0
            while not cancel.is_set():
                producer_check();wait_capacity()
                with inner.lock:
                    end=len(inner.head);rows=list(inner.head[index:end]);reserve=list(inner.reserve);error=inner.error;complete=inner.complete
                    inner.consumed=max(0,getattr(frames,'consumed',0)-steps)
                if error:raise f.TrajectoryError(error)
                if restorer:rows=restorer.restore(rows);reserve=restorer.restore(reserve)
                with frames.lock:
                    if rows:
                        shifted_rows=shifted(rows);shifted_reserve=shifted(reserve)
                        last=(shifted_reserve or shifted_rows)[-1]
                        if last['seq']>f.MAX_FRAMES or last['t_s']>f.MAX_TRAJECTORY_SECONDS:
                            raise f.TrajectoryError('腕部预对齐加路径超过总帧数或时长限制')
                        frames.publish(shifted_rows,shifted_reserve);index=end;first_tail.set()
                    if complete:
                        for key in ('final_target_pending','duration_estimated','peak_feed_mm_s','geometry_samples'):
                            if key in tail:native[key]=tail[key]
                        native['final_motor_deg']=list(frames.head[-1]['command_motor_deg']);native['final_pulses']=list(frames.head[-1]['motor_target_pulses'])
                        native['duration_s']=tail['duration_s']+duration;native['total_frames']=len(frames.head)
                        if restorer:prep.update(restored_max_position_error_mm=restorer.max_ideal_position,restored_max_orientation_error_deg=restorer.max_ideal_orientation)
                if complete:break
                cancel.wait(.005)
        except Exception as exc:
            trace('WRIST_PREFIX_PRODUCER_ERROR',str(exc))
            with frames.lock:frames.error='腕部后续规划失败，沿已校验备用制动段停车：'+str(exc)
            first_tail.set();tail_checked.set()
        finally:
            if inner:inner.close()
    frames.producer=threading.Thread(target=produce,name='wrist-prefix-producer',daemon=True);frames.producer.start()
    if finite:
        try:
            while frames.producer.is_alive():check();frames.producer.join(.01)
            if frames.error:raise f.TrajectoryError(frames.error)
            if not frames.complete:raise f.TrajectoryError('腕部加整段路径预检未完成')
            native.update(complete_before_start=True,duration_estimated=False)
            from .driver_tracking import validate as validate_tracking
            native['driver_response_checks']=validate_tracking(model,motor,frames.head,check,kind)
        except Exception:frames.close();raise
    elif steps<100 or approximate:
        # A short alignment alone may not cover even the hardware prefetch.
        # Publish readiness only after the first checked tail block is present.
        try:
            while not (first_tail if steps<100 else tail_checked).wait(.01):check()
            if frames.error:raise f.TrajectoryError(frames.error)
        except Exception:
            frames.close();raise
    return native
