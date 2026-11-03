"""Math-only fast commissioning transfers; strict endpoints, relaxed transit.

Only automatic grasp uses this profile. All frames are prepared and checked
before motion, then executed by the existing single-owner FIFO executor.
The response oracle is a model check, not a physical accuracy guarantee.
"""
import math
import time

from . import kinematics as k
from .native_grasp_prepare import prepare as prepare_native

PROFILE = 'grasp_endpoint_fast_v1'
JOINT_SPEED_DEG_S = 60.0
LINE_SPEED_MM_S = 200.0
NOMINAL_ACCEL_DEG_S2 = 100.0
FOLLOW_ACCEL_DEG_S2 = 200.0
TICK = .04
LOOKAHEAD = .20
J6_TRANSIT_TOLERANCE_DEG = 10.0
J6_ENDPOINT_TOLERANCE_DEG = 2.0


def _poses(model, joints, check):
    """Batch the existing FK ABI; keep the Python model as exact fallback."""
    from .native_math import LIBRARY, array
    output=[]
    for offset in range(0,len(joints),64):
        check();group=joints[offset:offset+64]
        if any(len(q)!=6 or any(not math.isfinite(v)for v in q)for q in group):
            raise ValueError('快速取放导引含无效关节角度')
        if LIBRARY is not None and getattr(model,'native_enabled',False):
            packed=array([v for q in group for v in q]);transforms=array([0.]*(16*len(group)))
            LIBRARY.f3p_fk_batch(model._native_geometry,packed,len(group),transforms)
            matrices=[[list(transforms[i+j:i+j+4])for j in (0,4,8,12)]for i in range(0,len(transforms),16)]
        else:matrices=[model.forward(q)for q in group]
        for transform in matrices:
            if any(not math.isfinite(v)for row in transform for v in row):
                raise ValueError('快速取放正解含非有限数值')
            native_rotation=[row[:3]for row in transform[:3]]
            # TOOL_ROTATION is a signed column permutation, not a general
            # matrix product. Retain both conventions without converting back.
            output.append(dict(position_mm=[row[3]for row in transform[:3]],
                rotation=[[-row[1],row[0],row[2]]for row in native_rotation],native_rotation=native_rotation))
        check()
    return output


def _angle_error(actual, expected):
    cosine=max(-1.,min(1.,(sum(actual[i][j]*expected[i][j]for i in range(3)for j in range(3))-1)/2))
    return 0. if cosine>=1.-1e-15 else math.degrees(math.acos(cosine))


def feedback_limits(trajectory):
    if trajectory.get('grasp_transfer_profile') != PROFILE:
        return None
    mode = trajectory.get('grasp_transfer_mode')
    if mode not in ('J', 'L') or not trajectory.get('complete_before_start'):
        raise ValueError('快速取放轨迹类型或整段校验无效')
    # Transit budgets only. Arrival flags and final motor tolerance are kept
    # by ContinuousMotion, and must never use these relaxed values.
    return (10.0, 5.0) if mode == 'L' else (20.0, 10.0)


def endpoint_tolerance(plan, node, normal):
    if node == 6 and feedback_limits(plan.get('trajectory',{})) is not None:
        from .zero_home import RATIOS
        return max(normal, J6_ENDPOINT_TOLERANCE_DEG * RATIOS[6])
    return normal


def accelerations():
    from .zero_home import RATIOS
    return [max(1,min(255,round(256-1/((FOLLOW_ACCEL_DEG_S2*RATIOS[n]/6)*50e-6))))
            for n in range(1,7)]


def plan_remote(start, step, bounds, hardware, check):
    from .planner_process import plan_remote as remote
    return remote('grasp_transfer',dict(start=start,step=step,bounds=bounds,hardware=hardware),check)


def plan_cycle_remote(start, steps, bounds, hardware, check):
    from .planner_process import plan_remote as remote
    first=remote('grasp_cycle',dict(start=start,steps=steps,bounds=bounds,hardware=hardware),check)
    return _decode_cycle(first)


def _decode_cycle(first):
    from .reference_endpoint.trajectory_frames import PackedFrames
    following=first.pop('following_transfers')
    for report in following:
        native=report['native_report'];native['frames']=PackedFrames(native['frames']['packed_bytes'])
        for key in ('planning_process_pid','math_backend','planner_source_identity'):
            native[key]=first['native_report'][key]
    return [first]+following


def prepare_cycle_remote(start, steps, bounds, hardware, check):
    from .planner_process import plan_remote as remote
    first=remote('grasp_prepare',dict(start=start,steps=steps,bounds=bounds,hardware=hardware),check)
    prepared=first.pop('prepared_steps')
    timing=first.pop('cycle_math_timing')
    reports=_decode_cycle(first)
    for report in reports:
        report['native_report']['math_execution']='isolated_process'
    return prepared,reports,timing


def prepare_cycle_inline(start, steps, bounds, hardware, check=lambda:None):
    from .grasp_motion import preflight_cycle
    began=time.monotonic()
    prepared=preflight_cycle(start,steps,bounds,check)
    preflight_seconds=time.monotonic()-began
    began=time.monotonic()
    report=plan_cycle_inline(start,prepared,bounds,hardware,check)
    report.update(prepared_steps=prepared,cycle_math_timing=dict(
        preflight_seconds=preflight_seconds,math_frames_seconds=time.monotonic()-began))
    return report


def plan_cycle_inline(start, steps, bounds, hardware, check=lambda:None):
    # One interpreter and one IPC round trip for the complete cycle. Each
    # transfer retains its own final frame, stop gate and endpoint check.
    reports=_plan_cycle_reports(start,steps,bounds,hardware,check)
    first=reports[0]
    first['following_transfers']=[dict(r,native_report=dict(r['native_report'],
        frames=dict(packed_bytes=r['native_report']['frames']._data)))for r in reports[1:]]
    return first


def _plan_cycle_reports(start, steps, bounds, hardware, check):
    reports=[];q=list(start)
    for step in steps:
        check();report=plan_inline(q,step,bounds,hardware,check)
        reports.append(report);q=list(report['target_angles_deg'])
    if not reports:raise ValueError('取放路径为空')
    return reports


def plan_cycle(start, steps, bounds, hardware, check):
    """Prepare on the existing task thread; batch native FK releases the GIL.

    No IPC/startup or frame serialization lies on this fast path. The caller
    still validates frozen context, fresh target and actual starts before CAN.
    """
    import os
    from .native_math import LIBRARY
    from .planner_process import source_identity
    reports=_plan_cycle_reports(start,steps,bounds,hardware,check)
    identity=source_identity()
    for report in reports:
        report['native_report'].update(planning_process_pid=os.getpid(),math_execution='joint_task_thread',
            math_backend='cpp-double-gil-released' if LIBRARY is not None else 'python',planner_source_identity=identity)
    return reports


def plan_inline(start, step, bounds, hardware, check=lambda:None):
    from .reference_adapter import make_model
    from .reference_endpoint.kinematics import matrix_to_rpy
    from .reference_endpoint.trajectory_frames import FrameBuilder
    from .coupled_limits import check_model_box
    from .collision import check_joint_box
    from .driver_tracking import assess
    began = time.monotonic()
    def checkpoint():
        check()
        if time.monotonic()-began > 40:
            raise ValueError('快速取放整段准备超时；本轮未启动')
    mode = step['mode']
    if mode not in ('J','L'):
        raise ValueError('快速取放仅支持点到点和伸缩段')
    model = make_model(start,bounds,hardware.get('calibration'),checkpoint)
    def pose_of(q):
        return _poses(model,[q],checkpoint)[0]
    caps = hardware['speed_caps_rpm'];ppr = hardware['pulses_per_rev']
    from .axis_speed import V10_TRAJECTORY_RPM
    from .zero_home import RATIOS
    if len(caps)!=6 or len(ppr)!=6 or any(type(p) is not int or p<1 for p in ppr):
        raise ValueError('快速取放缺少六轴速度或脉冲当量')
    # These caps come from the connected backend, not from GUI request values.
    wire = [min(c,V10_TRAJECTORY_RPM[n],max(1,math.floor(JOINT_SPEED_DEG_S*RATIOS[n]/6)))
            for n,c in enumerate(caps,1)]
    if any(type(c) is not int or c<1 for c in caps):
        raise ValueError('快速取放电机速度上限无效')
    acc = accelerations()
    guide = [list(start)] + ([list(q) for q in step['guide_angles_deg']] if mode=='L'
                            else [list(step['angles_deg'])])
    # Smooth Hermite interpolation through the checked 5 mm LIN guide. A J
    # transfer is a synchronized joint interpolation with the same timing law.
    count = len(guide)-1
    if count<1 or math.dist(guide[-1],step['angles_deg'])>1e-8:
        raise ValueError('快速取放导引终点不一致')
    slopes = [[(guide[min(count,i+1)][j]-guide[max(0,i-1)][j])*count/(min(count,i+1)-max(0,i-1))
               for j in range(6)] for i in range(count+1)]
    native_curve = prepare_native(model, guide, slopes, ppr)
    def curve(u):
        u=max(0.,min(1.,u));index=min(count-1,int(u*count));v=u*count-index
        h00=2*v**3-3*v*v+1;h10=v**3-2*v*v+v
        h01=-2*v**3+3*v*v;h11=v**3-v*v
        return [h00*a+h10*sa/count+h01*b+h11*sb/count
                for a,b,sa,sb in zip(guide[index],guide[index+1],slopes[index],slopes[index+1])]
    origin=pose_of(start);goal=step['goal'];length=math.dist(origin['position_mm'],goal['position_mm'])
    path_budget,angle_budget=(10.,5.) if mode=='L' else (20.,10.)
    # Bound the actual guide derivatives, including curvature; quintic timing
    # has maximum du/ds=1.875 and |d2u/ds2|<5.774.
    grid=max(256,count*16)
    if native_curve is not None:
        first,second=native_curve.derivatives(grid,mode,origin,goal,checkpoint)
    else:
        samples=[curve(i/grid) for i in range(grid+1)]
        first=[max(abs(samples[i+1][j]-samples[i][j])*grid for i in range(grid)) for j in range(6)]
        second=[max(abs(samples[i+2][j]-2*samples[i+1][j]+samples[i][j])*grid*grid
                    for i in range(grid-1)) for j in range(6)]
    joint_caps=[min(JOINT_SPEED_DEG_S*.8,wire[j]*6/RATIOS[j+1]*.8)for j in range(6)]
    duration=max(.32,max(1.875*s/c for s,c in zip(first,joint_caps)),
                 max(math.sqrt((3.516*c+5.774*s)/NOMINAL_ACCEL_DEG_S2)for s,c in zip(first,second)))
    if mode=='L':duration=max(duration,1.875*length/LINE_SPEED_MM_S)
    duration *= 1.05
    if native_curve is None:
        for left,right in zip(samples,samples[1:]):
            checkpoint();check_model_box(model,left,right);check_joint_box(left,right,checkpoint)
    if native_curve is None and mode=='L':
        from .reference_endpoint.trajectory_service import _segment_distance
        for pose in _poses(model,samples,checkpoint):
            if (_segment_distance(pose['position_mm'],origin['position_mm'],goal['position_mm'])>.5
                    or _angle_error(pose['rotation'],goal['rotation'])>.2):
                raise ValueError('伸缩导引偏离目标直线或朝向；本轮未启动')
    cache={}
    def prepare_samples(us):
        missing=[u for u in dict.fromkeys(us)if u not in cache];values=[]
        if native_curve is not None:
            cache.update(zip(missing,native_curve.samples(missing,checkpoint)))
            return
        for u in missing:
            checkpoint();q=curve(u);motor=model.joints_to_motor(q);pulses=[round(a*p/360)for a,p in zip(motor,ppr)]
            if any(not -2147483648<=p<=2147483647 for p in pulses):
                raise ValueError('快速取放轨迹脉冲超出signed32范围')
            motor=[p*360/r for p,r in zip(pulses,ppr)];q=model.motor_to_joints(motor)
            if any(abs(a)*65536/360>0xffffffff for a in motor):
                raise ValueError('快速取放轨迹超出位置反馈范围')
            check_model_box(model,q,q);values.append((q,motor,pulses))
        for u,value,pose in zip(missing,values,_poses(model,[v[0]for v in values],checkpoint)):
            cache[u]=(*value,pose)
    def sample(u):
        if u not in cache:prepare_samples([u])
        return cache[u]
    final=sample(1.)
    pe,ae=k.pose_error(goal,final[3])
    if pe>.08 or ae>.12:
        raise ValueError('快速取放量化终点偏差超限；本轮未启动')
    start_motor=model.joints_to_motor(start);attempts=[]
    for factor in (1.,1.25,1.6,2.,2.6,3.4):
        checkpoint();travel=math.ceil(duration*factor/TICK)*TICK
        # Hold the exact final target for 400ms before the final FIFO frame.
        # The real executor then independently waits for fresh arrival flags.
        total=travel+.4;rows=[];rotations=[];previous=list(start)
        def timed(value):
            s=max(0.,min(1.,value/travel))
            return s*s*s*(10+s*(-15+6*s))
        times=[(i*TICK,timed(i*TICK),timed(i*TICK+LOOKAHEAD))for i in range(round(total/TICK)+1)]
        prepare_samples([u for _,u,cu in times]+[cu for _,u,cu in times])
        for index,(t,u,cu) in enumerate(times):
            checkpoint()
            q,motor,pulses,pose=sample(u)
            cq,cmotor,cpulses,cpose=sample(cu)
            check_model_box(model,previous,cq);previous=cq
            rows.append(dict(seq=index+1,t_s=t,command_t_s=min(travel,t+LOOKAHEAD),reference_u=u,
                reference_xyz_mm=pose['position_mm'],reference_joints_deg=q,reference_motor_deg=motor,
                command_xyz_mm=cpose['position_mm'],command_joints_deg=cq,command_motor_deg=cmotor,
                motor_target_pulses=cpulses,speed_rpm=wire,acceleration=acc,phase='cartesian',
                final=index==round(total/TICK)))
            # Executor FK uses the reference tool frame (UI tool X/Y differ
            # by a fixed 90 degree rotation); keep native rotations consistent.
            rotations.append(pose['native_rotation'])
        # Nominal timing is bounded by joint derivatives above. The initial
        # lookahead jump is a position target, not an instantaneous move; its
        # bounded speed and acceleration response is assessed below.
        tracking=[assess(model,start_motor,rows,checkpoint,f,kind='line' if mode=='L' else 'arc')for f in (1.,.5)]
        path=max(r['max_running_path_error_mm'] for r in tracking)
        orientation=max(max(r['max_orientation_deg'],r['max_skewed_orientation_deg'])for r in tracking)
        if path>path_budget or mode=='L' and orientation>angle_budget:
            attempts.append(dict(travel_seconds=travel,path_error_mm=path,orientation_error_deg=orientation));continue
        builder=FrameBuilder()
        for row in rows:builder.append(row)
        frames=builder.freeze()
        native=dict(frames=frames,start_motor_deg=start_motor,final_motor_deg=final[1],final_pulses=final[2],
            start_xyz_mm=origin['position_mm'],target_xyz_mm=goal['position_mm'],duration_s=total,
            tick_seconds=TICK,lookahead_seconds=LOOKAHEAD,path_length_mm=length,
            rpy_deg=matrix_to_rpy(model.forward(start)),
            final_rpy_deg=matrix_to_rpy(model.forward(final[0])),
            requested_feed_mm_s=LINE_SPEED_MM_S,peak_feed_mm_s=1.875*length/travel,
            requested_joint_speed_deg_s=JOINT_SPEED_DEG_S,wire_speed_caps_rpm=wire,
            rolling=False,complete_before_start=True,grasp_transfer_profile=PROFILE,grasp_transfer_mode=mode,
            orientation_policy='adaptive_position',reference_rotations=rotations,
            driver_response_checks=tracking,initial_planning_seconds=time.monotonic()-began,
            grasp_preparation_backend='cpp-batched-v1' if native_curve is not None else 'python',
            retiming_attempts=attempts,transit_position_budget_mm=path_budget,
            transit_orientation_budget_deg=angle_budget,endpoint_quantization_error_mm=pe,
            endpoint_quantization_orientation_error_deg=ae,physical_accuracy_verified=False)
        return dict(mode=mode,algorithm=PROFILE,native_report=native,total_seconds=total,
                    path_length_mm=length,target_angles_deg=final[0],execution_supported=False,
                    drawing_acceleration=acc)
    raise ValueError('快速取放驱动响应预检失败；本轮未启动')
