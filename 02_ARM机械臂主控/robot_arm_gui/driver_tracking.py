"""Bounded deterministic driver-response checks; not a physical accuracy claim."""
import math
from . import fast_trajectory as f

def orientation_error(pose,origin):
    # Reuse the FK already needed for position; this is the same trace norm
    # used by planning_residual and the fused native wrist check.
    if any(not math.isfinite(v) for row in pose for v in row):
        raise f.TrajectoryError('驱动响应位姿含非有限数值')
    trace=sum(pose[i][j]*origin[i][j] for i in range(3) for j in range(3))
    cosine=max(-1.,min(1.,(trace-1.)/2))
    return 0. if cosine>=1.-1e-15 else math.degrees(math.acos(cosine))

def assess(model,start,rows,check,rate_factor=1.,feedback_skew=.035,kind='line'):
    from .native_driver_tracking import assess as native_assess
    result=native_assess(model,start,rows,check,rate_factor,feedback_skew,kind)
    if result is not None:return result
    return assess_python(model,start,rows,check,rate_factor,feedback_skew,kind)

def assess_python(model,start,rows,check,rate_factor=1.,feedback_skew=.035,kind='line'):
    from .reference_endpoint.trajectory_service import _segment_distance
    motor=list(start);velocity=[0.]*6;history=[list(motor)]*8
    origin=model.forward(model.motor_to_joints(start))
    worst=0.;worst_skew=0.;worst_path=0.;worst_running_path=0.
    line_start=[r[3] for r in origin[:3]];line_end=rows[-1]['command_xyz_mm']
    for index,row in enumerate(rows):
        check();target=row['command_motor_deg'];caps=[6*v for v in row['speed_rpm']]
        rates=[6/((256-v)*50e-6)*rate_factor for v in row['acceleration']]
        for _ in range(8):
            for i in range(6):
                delta=target[i]-motor[i];direction=1 if delta>=0 else -1
                desired=direction*min(caps[i],math.sqrt(2*rates[i]*abs(delta)))
                change=max(-rates[i]*.005,min(rates[i]*.005,desired-velocity[i]))
                old=velocity[i];velocity[i]+=change;step=(old+velocity[i])*.0025
                if step*delta>=0 and abs(step)>=abs(delta):motor[i]=target[i];velocity[i]=0.
                else:motor[i]+=step
            history.append(list(motor));history=history[-9:]
        q=model.motor_to_joints(motor)
        pose=model.forward(q);xyz=[r[3] for r in pose[:3]]
        worst=max(worst,orientation_error(pose,origin))
        sampled=[history[-1-min(8,round(feedback_skew*i/5/.005))][i] for i in range(6)]
        sq=model.motor_to_joints(sampled)
        worst_skew=max(worst_skew,orientation_error(model.forward(sq),origin))
        if row.get('phase')=='wrist_preparation':
            worst_path=max(worst_path,math.dist(xyz,[r[3] for r in origin[:3]]))
        elif kind=='line':
            worst_running_path=max(worst_running_path,_segment_distance(xyz,line_start,line_end))
        else:
            window=rows[max(0,index-30):min(len(rows),index+31)]
            points=[r['reference_xyz_mm'] for r in window]+[window[-1]['command_xyz_mm']]
            worst_running_path=max(worst_running_path,min(_segment_distance(xyz,a,b) for a,b in zip(points,points[1:])))
    return dict(max_orientation_deg=worst,max_skewed_orientation_deg=worst_skew,
        max_preparation_drift_mm=worst_path,max_running_path_error_mm=worst_running_path,
        rate_factor=rate_factor,feedback_skew_s=feedback_skew,
        model_only=True)

def validate(model,start,rows,check,kind='line'):
    reports=[assess(model,start,rows,check,factor,kind=kind) for factor in (1.,.5)]
    if max(max(r['max_skewed_orientation_deg'],r['max_orientation_deg']) for r in reports)>1.:
        raise f.TrajectoryError('驱动响应模型朝向偏差超出1度预检预算')
    if max(r['max_preparation_drift_mm'] for r in reports)>1.:
        raise f.TrajectoryError('驱动响应模型预对齐位置偏差超出1mm预检预算')
    if max(r['max_running_path_error_mm'] for r in reports)>1.:
        raise f.TrajectoryError('驱动响应模型路径偏差超出1mm预检预算')
    return reports
