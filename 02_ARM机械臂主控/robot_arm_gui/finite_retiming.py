"""Reuse checked Cartesian geometry with local C2 timing, before any motion."""
import time
from . import fast_trajectory as f


def try_local(curve,model,motor,args,check,rows,tracking):
    # Leave normal short routes on their established fast preparation path.
    old_duration=curve.duration
    if min(curve.acc)<200 or old_duration<20 or old_duration<3*1.875*curve.length/args['feed_mm_s']:
        return rows,tracking,None
    keys=('schedule','duration','steps','nominal','ahead','wire','reasons','drawing_timing','check')
    saved={key:getattr(curve,key) for key in keys}
    attempts=[]
    deadline=time.monotonic()+8.
    class BudgetExpired(ValueError):pass
    def bounded_check():
        check()
        if time.monotonic()>deadline:raise BudgetExpired('局部计时优化预算已用尽，保留完整原规划')
    curve.check=bounded_check
    from .driver_tracking import validate
    # High joint-speed requests favour the shorter response horizon first.
    # Every horizon still receives the complete frame and driver checks.
    horizons=(.12,.2,.08,.4,.8) if args['joint_speed_deg_s']>20 else (.2,.12,.08,.4,.8)
    for ahead in horizons:
        check();curve.configure_timing(ahead)
        curve.schedule=[];curve.drawing_timing=True
        curve.duration=f.MAX_TRAJECTORY_SECONDS;curve.steps=round(curve.duration/curve.tick)
        candidate=[];index=0
        try:
            from .native_finite_timing import enabled
            schedule_only=enabled(curve)
            if schedule_only:
                curve._finite_schedule_only=True
                try:curve.extend(f.MAX_TRAJECTORY_SECONDS,0,0)
                finally:curve._finite_schedule_only=False
                if curve.duration>=old_duration:raise f.TrajectoryError('局部计时未缩短总时长')
            while index<=curve.steps:
                check()
                count=200 if schedule_only else 50
                if not schedule_only:curve.extend((index+count)*curve.tick+curve.ahead,index,count)
                count=min(count,curve.steps+1-index)
                final=index+count==curve.steps+1
                reused=None if schedule_only else curve.take_timing_frames(index,count,final)
                nominal=curve.nominal
                if schedule_only:curve.nominal=[value*.9 for value in nominal]
                try:candidate.extend(reused if reused is not None else curve.frames(lambda dt:curve.normal(index*curve.tick+dt),index,count,final))
                finally:curve.nominal=nominal
                index+=count
                if not candidate[-1]['final'] and index*curve.tick>=old_duration:raise f.TrajectoryError('局部计时未缩短总时长')
            if not candidate or not candidate[-1]['final']:raise f.TrajectoryError('局部计时缺少完整终帧')
            if curve.duration>=old_duration:raise f.TrajectoryError('局部计时未缩短总时长')
            checked=validate(model,motor,candidate,bounded_check,args.get('kind','line'))
        except BudgetExpired as exc:
            attempts.append(dict(lookahead_seconds=ahead,error=str(exc)));break
        except ValueError as exc:
            attempts.append(dict(lookahead_seconds=ahead,error=str(exc)))
            continue
        else:
            curve.reasons=list(saved['reasons'])+['受限区局部降速，其余路径采用C2连续计时']
            curve.check=saved['check']
            from .local_trajectory import evaluate
            from .native_finite_timing import peak as native_peak
            peak=native_peak(curve)
            if peak is None:peak=max(evaluate(coeff,i/256,1)/duration for _,duration,coeff in curve.schedule for i in range(257))*curve.length
            return candidate,checked,dict(strategy='local_c2',old_duration_s=old_duration,
                                         duration_s=curve.duration,peak_feed_mm_s=peak,peak_feed_estimated=True,attempts=attempts)
    for key,value in saved.items():setattr(curve,key,value)
    return rows,tracking,dict(strategy='original_fallback',old_duration_s=old_duration,attempts=attempts)
