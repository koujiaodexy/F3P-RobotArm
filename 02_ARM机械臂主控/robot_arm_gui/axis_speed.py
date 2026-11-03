"""Independent axis limits and complete-before-motion response retries."""
import math,time

MOTOR_RATED_RPM=3000
RUN_MAX_JOINT_DEG_S=100.
# Operational ceilings below the motor-derived theoretical wrist maxima.
V10_TRAJECTORY_RPM={1:3000,2:3000,3:3000,4:700,5:373,6:16}

def theoretical_joint_speeds(ratios):
    return {n:MOTOR_RATED_RPM*6/abs(r) for n,r in ratios.items()}

def prepare_with_speed_retry(plan,model,motor,target,check_cancel,args):
    request=float(args['joint_speed_deg_s']);original=args['speed_caps_rpm']
    ratios=model.profile['motor_mapping']['ratios'];attempts=[];began=time.monotonic()
    for value in sorted({request,min(request,80.),min(request,60.),min(request,40.),min(request,20.)},reverse=True):
        from . import fast_trajectory as f
        if check_cancel is not None and check_cancel():raise f.TrajectoryError('局部规划已取消')
        if time.monotonic()-began>f.MAX_PLAN_SECONDS:raise f.TrajectoryError('提速重试规划超时')
        retry=dict(args,joint_speed_deg_s=value)
        caps=[original[n+1] if isinstance(original,dict) else original[n] for n in range(6)]
        retry['speed_caps_rpm']={n+1:min(caps[n],max(1,math.floor(value*abs(ratios[n])/6))) for n in range(6)}
        try:report=plan(model,motor,target,check_cancel=check_cancel,**retry)
        except ValueError as exc:
            if '驱动响应模型' not in str(exc):raise
            attempts.append(dict(joint_speed_deg_s=value,error=str(exc)))
            if value==min(request,20.):raise
        else:
            report.update(requested_joint_speed_deg_s=request,validated_joint_speed_deg_s=value,
                axis_speed_attempts=attempts,initial_planning_seconds=time.monotonic()-began)
            if attempts:report['slowdown_reasons'].append('提高关节速度后驱动响应朝向预算受限，整段重新降速核验')
            return report
