"""Validate finite fixed-pose paths before publishing any executable frames.

Whole-path joint derivative bounds choose one C2 timing law. A shorter horizon
or slower timing is retried over the entire path, never after motion starts.
"""
import math,threading,time
from . import fast_trajectory as f
from .rolling_trajectory import Curve,RollingFrames


def try_uniform(curve,model,motor,args,check):
    """C2 entry/exit ramps and constant arc-length feed in the middle.

    Reuse the whole checked guide. The existing frame and driver validators
    must accept the complete candidate before it can replace the original.
    """
    # Long restricted routes retain the existing local retiming optimizer.
    if not args.get('prefer_short_lookahead') or args['feed_mm_s']<15 or curve.duration>=20:return None
    saved=(curve.duration,curve.steps,list(curve.schedule))
    peak=4./3.;accel=8.
    duration=max(.32,peak*curve.length/args['feed_mm_s'],
        max(s*peak/(6*v) for s,v in zip(curve.slopes,curve.nominal)),
        max(math.sqrt((c*peak**2+s*accel)/(6*r*.5)) for c,s,r in zip(curve.curvatures,curve.slopes,curve.rates)))
    attempts=[]
    for factor in (1.,1.2,1.4):
        check();d=math.ceil(duration*factor/(4*curve.tick))*4*curve.tick
        if d>saved[0]*1.15 or d>f.MAX_TRAJECTORY_SECONDS:break
        curve.duration=d;curve.steps=round(d/curve.tick)
        curve.schedule=[(0.,d/4,[0.,0.,0.,1/3,-1/6,0.]),
                        (d/4,d/2,[1/6,2/3,0.,0.,0.,0.]),
                        (3*d/4,d/4,[5/6,1/3,0.,-1/3,1/6,0.])]
        rows=[]
        try:
            for index in range(0,curve.steps+1,200):
                check();count=min(200,curve.steps+1-index)
                rows.extend(curve.frames(lambda dt:curve.normal(index*curve.tick+dt),index,count,index+count==curve.steps+1))
            from .driver_tracking import validate
            tracking=validate(model,motor,rows,check,args.get('kind','line'))
        except ValueError as exc:
            attempts.append(dict(duration_s=d,error=str(exc)));continue
        else:
            return rows,tracking,dict(strategy='uniform_c2',old_duration_s=saved[0],duration_s=d,
                peak_feed_mm_s=peak*curve.length/d,cruise_feed_mm_s=peak*curve.length/d,
                cruise_path_fraction=2/3,ramp_duration_s=d/4,attempts=attempts)
    curve.duration,curve.steps,curve.schedule=saved
    return None


def prepare(model,motor,target,args,check,began):
    from .local_trajectory import LocalCurve
    curve=LocalCurve(model,motor,target,args,check,.8)
    curve.q(1.)
    from .native_finite_timing import guide_max_rates
    bounded=guide_max_rates(curve)
    slopes,curvatures=bounded if bounded is not None else ([0.]*6,[0.]*6)
    for left,right,guide in ([] if bounded is not None else curve.segments):
        check()
        for j,(first,second) in enumerate(curve.guide_rates(left,right,guide,0.,1.)):
            scale=abs(curve.ratios[j])
            slopes[j]=max(slopes[j],first*scale)
            curvatures[j]=max(curvatures[j],second*scale)
    curve.slopes=slopes;curve.curvatures=curvatures
    attempts=[];rows=None;retiming=None;retiming_attempted=False
    from .finite_retiming import try_local
    horizons=(.2,.12,.08,.4,.8) if args.get('prefer_short_lookahead') else (.8,.4,.2,.12,.08)
    for ahead in horizons:
        Curve.configure_timing(curve,ahead)
        base_duration=curve.duration
        uniform=try_uniform(curve,model,motor,args,check)
        if uniform is not None:
            rows,tracking,retiming=uniform;break
        if not retiming_attempted:
            retiming_attempted=True
            candidate,candidate_tracking,retiming=try_local(curve,model,motor,args,check,[],None)
            if candidate:
                rows=candidate;tracking=candidate_tracking;break
        for factor in ((1.,1.4,2.,3.) if ahead==.08 else (1.,)):
            check()
            curve.duration=math.ceil(base_duration*factor/curve.tick)*curve.tick
            curve.steps=round(curve.duration/curve.tick)
            if curve.duration>f.MAX_TRAJECTORY_SECONDS or curve.steps+1>f.MAX_FRAMES:
                rows=None;break
            curve.schedule=[(0.,curve.duration,[0.,0.,0.,10.,-15.,6.])]
            rows=[]
            try:
                for index in range(0,curve.steps+1,200):
                    check();count=min(200,curve.steps+1-index)
                    rows.extend(curve.frames(lambda dt:curve.normal(index*curve.tick+dt),
                        index,count,index+count==curve.steps+1))
                from .driver_tracking import validate as validate_tracking
                tracking=validate_tracking(model,motor,rows,check,args.get('kind','line'))
            except f.TrajectoryError as exc:
                reason=str(exc);attempts.append(dict(lookahead_seconds=ahead,
                    duration_seconds=curve.duration,error=reason))
                rows=None
                if not any(reason.startswith(prefix) for prefix in (
                    '滚动前视插值误差超限','滚动帧速度超过包络','滚动帧加速度超过包络','驱动响应模型')):
                    raise
                # The next horizon lowers wire speed as well. All frames are
                # checked again; no validated-start claim escapes this retry.
                continue
            else:break
        if rows is not None:break
    if rows is None:raise f.TrajectoryError('整段直线/圆弧预检失败：'+(attempts[-1]['error'] if attempts else '轨迹超过帧数或时长上限'))
    cancel=threading.Event();frames=RollingFrames(rows,[],curve.duration,cancel)
    frames.producer=threading.Thread(target=lambda:None,name='finite-path-complete',daemon=True)
    last=rows[-1]
    return dict(frames=frames,start_motor_deg=list(motor),start_xyz_mm=curve.start,
        target_xyz_mm=list(target),final_motor_deg=list(last['command_motor_deg']),
        final_pulses=list(last['motor_target_pulses']),final_target_pending=False,
        duration_s=curve.duration,duration_estimated=False,total_frames=len(rows),
        path_length_mm=curve.length,kind=args.get('kind','line'),rpy_deg=curve.rpy,
        tick_seconds=curve.tick,lookahead_seconds=curve.ahead,lookahead_attempts=attempts,
        requested_feed_mm_s=args['feed_mm_s'],peak_feed_mm_s=(retiming['peak_feed_mm_s'] if retiming and retiming['strategy'] in ('local_c2','uniform_c2') else 1.875*curve.length/curve.duration),
        effective_feed_mm_s=curve.length/curve.duration,motor_speed_caps_rpm=curve.caps,
        wire_speed_caps_rpm=curve.wire,motor_acceleration_rpm_s=curve.rates,
        slowdown_reasons=curve.reasons,arc=curve.arc,rolling=True,local_planning=False,
        complete_before_start=True,geometry_samples=curve.count+1,initial_geometry_fraction=1.,
        driver_response_checks=tracking,
        initial_planning_seconds=time.monotonic()-began,
        retiming=retiming,collision_checked=False,physical_accuracy_verified=False)
