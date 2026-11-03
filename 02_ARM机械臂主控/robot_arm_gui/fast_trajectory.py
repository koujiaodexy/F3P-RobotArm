# Reviewed V16 fork of reference_endpoint/trajectory.py; vendor kept intact.
"""Bounded, hardware-free LIN/CIRC model planning with fixed tool orientation.

Targets are absolute motor pulses. A frame contains both a nominal reference
at t and a separate command at min(t + lookahead, duration). The lookahead
limits braking demand; it does not prove real-world tracking or collision
clearance. Motor acceleration bytes are copied unchanged.
"""
import math
import time
from collections import deque

from .reference_endpoint.trajectory_frames import FrameBuilder
from .native_math import PlanningModel
from .planning_residual import planning_pose_error

from .reference_endpoint.kinematics import ArmModel, KinematicsError, matrix_to_rpy, pose_error


class TrajectoryError(ValueError):
    pass


class _ContinuousIKError(TrajectoryError):
    """A continuous branch failed; only this permits a wrist-preparation probe."""
    pass


MAX_TRAJECTORY_SECONDS = 1800.0
MAX_FRAMES = int(MAX_TRAJECTORY_SECONDS / 0.04) + 1
MAX_PATH_MM = 1000.0


def _window_speeds(rows, tick, ahead_count):
    """Same forward-window peak rates, with each edge visited once per axis."""
    steps=len(rows)-1
    peaks=[[0.0]*6 for _ in rows]
    for axis in range(6):
        rates=[abs(b['motor'][axis]-a['motor'][axis])/(6*tick)
               for a,b in zip(rows,rows[1:])]
        queue=deque();end=0
        for k in range(steps):
            upper=min(steps,max(k+ahead_count,k+1))
            while end<upper:
                while queue and rates[queue[-1]]<=rates[end]:queue.pop()
                queue.append(end);end+=1
            while queue and queue[0]<k:queue.popleft()
            peaks[k][axis]=rates[queue[0]]
    return peaks
MAX_PLAN_SECONDS = 90.0  # bounded headroom for full validation of long paths on F3P
MAX_JOINT_STEP_DEG = 10.0
POSITION_TOLERANCE_MM = 0.1
ORIENTATION_TOLERANCE_DEG = 0.12
WRIST_ALIGNMENT_ELIGIBILITY_DEG = 0.05


def _v(values, size, name):
    if (not isinstance(values, (tuple, list)) or len(values) != size or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in values)):
        raise TrajectoryError('%s 必须包含 %d 个有限数值' % (name, size))
    return [float(x) for x in values]


def _number(value, low, high, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise TrajectoryError('%s 须在 %g～%g 范围内' % (name, low, high))
    return float(value)


def _six(values, low, high, name):
    if not isinstance(values, dict):
        raise TrajectoryError('%s 必须逐轴指定' % name)
    result = []
    for n in range(1, 7):
        v = values.get(n, values.get(str(n)))
        if type(v) is not int or not low <= v <= high:
            raise TrajectoryError('%s：%d 号轴须为 %d～%d 的整数' % (name, n, low, high))
        result.append(v)
    return result


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _sub(a, b):
    return [x-y for x, y in zip(a, b)]


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _smooth(s):
    return s*s*s*(10.0+s*(-15.0+6.0*s))


def _path_geometry(start, end, kind, via):
    """Return arc-length parameterization; major arcs include the given via."""
    if kind == 'polyline':
        from .drawing import polyline
        return polyline(start,end,via)
    delta = _sub(end, start)
    if _norm(delta) < 0.01:
        raise TrajectoryError('起点与终点重合或相距不足 0.01 mm；整圆请拆成两段圆弧')
    if kind == 'line':
        if via is not None:
            raise TrajectoryError('直线模式不使用圆弧经过点')
        length = _norm(delta)
        return lambda u: [a+u*d for a, d in zip(start, delta)], length, {}
    if kind != 'arc':
        raise TrajectoryError('轨迹类型必须为 line 或 arc')
    middle = _v(via, 3, '圆弧经过点')
    a = _sub(middle, start)
    b = delta
    if min(_norm(a), _norm(_sub(end, middle))) < 0.01:
        raise TrajectoryError('圆弧三点不能重合或过近')
    normal = _cross(a, b)
    nn = _dot(normal, normal)
    if nn <= (_norm(a)*_norm(b)*1e-5)**2:
        raise TrajectoryError('圆弧三点共线或近似共线，无法确定稳定圆平面')
    bn = _cross(b, normal)
    na = _cross(normal, a)
    offset = [(bn[i]*_dot(a,a)+na[i]*_dot(b,b))/(2*nn) for i in range(3)]
    center = [start[i]+offset[i] for i in range(3)]
    radius = _norm(offset)
    # FK implementations may differ by a few ulps at an exact radius boundary.
    if not 0.5-1e-10 <= radius <= 10000+1e-8:
        raise TrajectoryError('圆弧半径须为 0.5～10000 mm，当前 %.6g mm' % radius)
    e1 = [(start[i]-center[i])/radius for i in range(3)]
    unit_n = [v/math.sqrt(nn) for v in normal]
    e2 = _cross(unit_n, e1)
    def angle(point):
        r = _sub(point, center)
        return math.atan2(_dot(r,e2), _dot(r,e1)) % (2*math.pi)
    mid_angle, end_angle = angle(middle), angle(end)
    sweep = end_angle if mid_angle < end_angle else end_angle-2*math.pi
    if abs(sweep) < 1e-7:
        raise TrajectoryError('圆弧角度退化')
    def point(u):
        theta = u*sweep
        return [center[i]+radius*(e1[i]*math.cos(theta)+e2[i]*math.sin(theta)) for i in range(3)]
    return point, radius*abs(sweep), dict(center_mm=center, radius_mm=radius,
        sweep_deg=math.degrees(sweep), via_fraction=mid_angle/sweep if sweep>0 else (mid_angle-2*math.pi)/sweep)


def _plan_path_candidate(model, start_motor_deg, target_xyz, *, kind='line', via_mm=None,
              feed_mm_s=5.0, speed_caps_rpm, acceleration, pulses_per_rev,
              limits_deg=None, tick_seconds=0.04, lookahead_seconds=0.8,
              check_cancel=None, _path_origin=None, _prepared_start=False, _geometry_cache=None,
              _joint_step_limit=MAX_JOINT_STEP_DEG, position_tolerance_mm=POSITION_TOLERANCE_MM,
              allow_orientation_adjustment=False):
    """Plan immutable packed frames and detached metadata, with no I/O or motor commands.

    Cancellation callback may raise; returning True also cancels. Limits use
    model joint coordinates, including None for explicitly continuous axes.
    Feed is requested *peak* TCP speed. Reported average is length/duration.
    """
    began = time.monotonic()
    def checkpoint():
        if check_cancel is not None and check_cancel():
            raise TrajectoryError('轨迹计算已取消')
        if time.monotonic()-began > MAX_PLAN_SECONDS:
            raise TrajectoryError('轨迹计算超过时间上限，请缩短路径或避开奇异姿态')
    checkpoint()
    start_motor = _v(start_motor_deg, 6, '起点电机角度')
    if any(abs(v)*65536/360 > 0xffffffff for v in start_motor):
        raise TrajectoryError('起点电机角度超出 0x36 反馈 uint32 可观测范围，请先核对多圈坐标')
    target = _v(target_xyz, 3, '目标 XYZ')
    feed = _number(feed_mm_s, 0.01, 100.0, '路径进给 mm/s')
    tick = _number(tick_seconds, 0.04, 0.04, '轨迹周期秒')
    ahead = _number(lookahead_seconds, tick, 0.8, '前视时间秒')
    ahead_count = int(round(ahead/tick))
    if abs(ahead_count*tick-ahead) > 1e-8:
        raise TrajectoryError('前视时间必须为 40 ms 的整数倍')
    caps = _six(speed_caps_rpm, 1, 3000, '电机速度上限 RPM')
    acc = _six(acceleration, 0, 255, '电机加速度')
    if any(v == 0 for v in acc):
        raise TrajectoryError('直线/圆弧要求六轴加速度为 1～255；0 表示直接起停，请手动设置后重试（点到点不受影响）')
    ppr = _six(pulses_per_rev, 1, 0xffffffff, '每圈脉冲数 PPR')
    # Use a stricter local solver to avoid staircase trajectories caused by the
    # normal endpoint-preview tolerance. Never mutate the installed model.
    profile = model.profile
    strict = profile['solver']
    strict['position_tolerance_mm'] = min(strict['position_tolerance_mm'], 0.01)
    strict['orientation_tolerance_deg'] = min(strict['orientation_tolerance_deg'], 0.0001)
    strict['max_seeds'] = 1
    strict['max_iterations'] = min(strict['max_iterations'], 80)
    solver = PlanningModel(profile)
    limits = model.joint_limits_deg if limits_deg is None else limits_deg
    if isinstance(limits, dict):
        limits = [limits.get(n, limits.get(str(n))) for n in range(1,7)]
    if not isinstance(limits, (list,tuple)) or len(limits)!=6:
        raise TrajectoryError('轨迹限位须显式包含六轴')
    checked_limits = []
    for i, pair in enumerate(limits):
        if pair is None:
            if i+1 not in model.continuous_joints:
                raise TrajectoryError('仅已声明连续转动的关节可以无限位')
            checked_limits.append(None)
        else:
            lo, hi = _v(pair,2,'关节限位')
            if lo >= hi:
                raise TrajectoryError('关节限位范围无效')
            checked_limits.append([lo,hi])
    limits = checked_limits
    inverse_limits=limits
    if allow_orientation_adjustment:
        # Include the half-pulse allowance in both IK and interpolation guides.
        ratios=model.profile['motor_mapping']['ratios']
        margins=[180/p/abs(r)+1e-8 for p,r in zip(ppr,ratios)]
        inverse_limits=[None if pair is None else [pair[0]+margin,pair[1]-margin] for pair,margin in zip(limits,margins)]
    q0 = model.motor_to_joints(start_motor)
    def check_joint(q):
        for i,pair in enumerate(limits):
            if pair is not None and not pair[0]-1e-9 <= q[i] <= pair[1]+1e-9:
                failure=TrajectoryError('%d 号轴轨迹超出关节限位' % (i+1))
                failure.failure_kind='joint_limit'
                raise failure
    check_joint(q0)
    transform0 = model.forward(q0) if _path_origin is None else _path_origin
    start = [transform0[i][3] for i in range(3)]
    rpy = matrix_to_rpy(transform0)
    point, length, arc = _path_geometry(start, target, kind, via_mm)
    if length > MAX_PATH_MM:
        raise TrajectoryError('单段轨迹超过 %.0f mm，请拆分路径' % MAX_PATH_MM)
    max_pe, max_re = 0.0, 0.0
    orientation_released=False
    def inverse(xyz,previous):
        nonlocal orientation_released
        if not orientation_released:
            try:
                from .analytic_inverse import fixed_pose
                q=fixed_pose(solver,xyz,[r[:3] for r in transform0[:3]],previous,inverse_limits,checkpoint)
                if q is None:q=solver.solve(xyz,rpy,previous,limits_deg=inverse_limits)
                if max(abs(a-b) for a,b in zip(q,previous))>_joint_step_limit:
                    raise KinematicsError('固定朝向关节分支不连续')
                return q
            except KinematicsError:
                if not allow_orientation_adjustment:raise
                orientation_released=True
        if allow_orientation_adjustment:
            from .position_inverse import solve_position
            try:return solve_position(solver,xyz,previous,inverse_limits,checkpoint,tolerance=.03)
            except KinematicsError:
                return solve_position(solver,xyz,previous,inverse_limits,checkpoint,tolerance=min(.25,position_tolerance_mm*.25))
        return solver.solve(xyz,rpy,previous,limits_deg=limits)
    def solve(u, previous, guide=None):
        nonlocal max_pe, max_re
        checkpoint()
        xyz = point(u)
        try:
            if guide is not None:
                q = guide
                expected = [transform0[i][:3]+[xyz[i]] for i in range(3)]+[[0,0,0,1]]
                pe,re = planning_pose_error(model.forward(q), expected)
                if (_norm(pe) > (min(.25,position_tolerance_mm*.25) if position_tolerance_mm>.1 else .03) or (not orientation_released and math.degrees(_norm(re)) > .02)
                        or max(abs(a-b) for a,b in zip(q,previous)) > _joint_step_limit
                        or any(pair is not None and not pair[0] <= v <= pair[1] for v,pair in zip(q,inverse_limits))):
                    q = inverse(xyz,previous)
            elif _prepared_start and u == 0:
                # Preserve the prepared joint endpoint, including measured
                # near-zero noise. Never redefine the original XYZ/R target.
                q = list(q0)
            else:
                q = inverse(xyz,previous)
        except KinematicsError as exc:
            # Retry only a failed local solve. A different branch still faces
            # the unchanged three-degree continuity and physical-bound checks.
            checkpoint()
            fallback_profile=solver.profile
            fallback_profile['solver']['max_iterations']=160
            fallback_profile['solver']['max_seeds']=4
            if position_tolerance_mm>.1:
                fallback_profile['solver']['position_tolerance_mm']=min(.25,position_tolerance_mm*.25)
                fallback_profile['solver']['orientation_tolerance_deg']=.02
                fallback_profile['solver']['max_seeds']=16
            try:
                if allow_orientation_adjustment:raise exc
                q=PlanningModel(fallback_profile).solve(xyz,rpy,previous,limits_deg=limits)
            except KinematicsError as retry_error:
                failure=_ContinuousIKError('路径 %.2f%% 处连续逆解未收敛；局部重试失败，需核对限位或调整姿态：%s' % (100*u,retry_error))
                failure.path_fraction=u;failure.failure_kind='ik_nonconvergence'
                raise failure from exc

        for n in model.continuous_joints:
            q[n-1] += 360*round((previous[n-1]-q[n-1])/360)
        joint_step = max(abs(a-b) for a,b in zip(q,previous))
        if joint_step > _joint_step_limit+1e-9:
            exc = _ContinuousIKError('路径 %.2f%% 处相邻关节变化 %.2f° 超过 %.1f°，需细分或调整逆解分支' % (100*u,joint_step,_joint_step_limit))
            exc.joint_step_degrees = joint_step
            exc.path_fraction = u
            raise exc
        check_joint(q)
        motor = model.joints_to_motor(q)
        pulses = [int(round(m*p/360)) for m,p in zip(motor,ppr)]
        if any(not -2147483648 <= p <= 2147483647 for p in pulses):
            raise TrajectoryError('轨迹绝对脉冲超出板卡 signed32 范围')
        quantized_motor = [p*360.0/r for p,r in zip(pulses,ppr)]
        if any(abs(v)*65536/360 > 0xffffffff for v in motor+quantized_motor):
            raise TrajectoryError('轨迹角度超出 0x36 反馈 uint32 可观测范围')
        quantized_q = model.motor_to_joints(quantized_motor)
        check_joint(quantized_q)
        expected = [transform0[i][:3]+[xyz[i]] for i in range(3)]+[[0,0,0,1]]
        pe, re = planning_pose_error(model.forward(quantized_q), expected)
        pe, re = _norm(pe), math.degrees(_norm(re))
        max_pe, max_re = max(max_pe,pe), max(max_re,re)
        if pe > position_tolerance_mm or (not allow_orientation_adjustment and re > ORIENTATION_TOLERANCE_DEG):
            raise TrajectoryError('量化后模型路径误差超限：%.5f mm / %.5f 度' % (pe,re))
        return dict(u=u,xyz=xyz,q=q,motor=motor,pulses=pulses,quantized_motor=quantized_motor)
    if _geometry_cache is not None and 'coarse' in _geometry_cache:
        coarse, count, slope, curvature = _geometry_cache['coarse']
        _geometry_cache['hits'] = _geometry_cache.get('hits', 0)+1
    else:
        # Geometric reconnaissance bounds derivatives before time resampling.
        count = max(16, int(math.ceil(length/0.25)))
        if count > 1600:
            raise TrajectoryError('路径采样过多，请拆分轨迹')
        while True:
            coarse = [dict(u=0,xyz=start,q=q0,motor=start_motor)]
            previous = q0
            try:
                for k in range(1,count+1):
                    row=solve(k/count,previous);coarse.append(row);previous=row['q']
            except _ContinuousIKError as exc:
                # A short curved path may turn its wrist faster than the original
                # 0.25 mm reconnaissance spacing. Refine uniformly, keeping the
                # Keep derivative formulas and the ten-degree final bound.
                step = getattr(exc, 'joint_step_degrees', float('inf'))
                if step < 45 and count*2 <= 1600:
                    count *= 2
                    continue
                raise
            break
        slope = [0.0]*6
        curvature = [0.0]*6
        for i in range(6):
            diffs = [(coarse[k+1]['motor'][i]-coarse[k]['motor'][i])*count for k in range(count)]
            slope[i] = max(abs(v) for v in diffs)
            curvature[i] = max([abs(diffs[k+1]-diffs[k])*count for k in range(count-1)]+[0])
        if _geometry_cache is not None:
            _geometry_cache['coarse'] = (coarse, count, slope, curvature)
    rates = [1/((256-a)*50e-6) for a in acc]  # motor RPM/s, vendor p57
    # Nominal continuous speed below integer command ceiling. 35% reserve keeps
    # braking time materially shorter than the finite lookahead window.
    wire_caps = [min(c,max(1,int(math.floor(rate*ahead*0.35)))) for c,rate in zip(caps,rates)]
    nominal_caps = [max(0.35, c*0.70) for c in wire_caps]
    if model.profile.get('trajectory_joint_speed_deg_s') is not None:
        nominal_caps = [min(v,model.profile['trajectory_joint_speed_deg_s']*abs(r)/6) for v,r in zip(nominal_caps,model.profile['motor_mapping']['ratios'])]
    requested_duration = 1.875*length/feed
    duration = max(tick*5, requested_duration)
    reasons=[]
    speed_duration=max(s*1.875/(6*v) for s,v in zip(slope,nominal_caps))
    accel_duration=max(math.sqrt((c*1.875**2+s*5.78)/(6*r*0.55))
                       for c,s,r in zip(curvature,slope,rates))
    if speed_duration>duration:
        reasons.append('为满足六轴速度上限和有限前视制动余量，路径进给已降低')
    if accel_duration>max(duration,speed_duration):
        reasons.append('为保留用户加速度并满足统一起停斜坡，轨迹时间已延长')
    duration=max(duration,speed_duration,accel_duration)
    tangents=[]
    for index in range(count+1):
        if index==0:
            tangent=[(-3*a+4*b-c)/2 for a,b,c in zip(coarse[0]['q'],coarse[1]['q'],coarse[2]['q'])]
        elif index==count:
            tangent=[(3*b-4*a+c)/2 for a,b,c in zip(coarse[-2]['q'],coarse[-1]['q'],coarse[-3]['q'])]
        else:
            tangent=[(b-a)/2 for a,b in zip(coarse[index-1]['q'],coarse[index+1]['q'])]
        tangents.append(tangent)
    def guide(u):
        # Cubic interpolation supplies a candidate, never an unchecked pose.
        # Every dense pose must meet the same strict IK residual, limits,
        # continuity, pulse quantization and blend checks. Otherwise use IK.
        f=u*count; index=min(count-1,int(f)); t=f-index
        p0,p1=coarse[index]['q'],coarse[index+1]['q']
        m0,m1=tangents[index],tangents[index+1]
        h0,h1,h2,h3=2*t**3-3*t*t+1,t**3-2*t*t+t,-2*t**3+3*t*t,t**3-t*t
        return [h0*a+h1*ma+h2*b+h3*mb for a,ma,b,mb in zip(p0,m0,p1,m1)]
    rows=[]
    # Final dense sampling uses previous IK solution for every nominal point.
    # Retry time scaling only if dense derivative checks reveal a sharper bend.
    for attempt in range(3):
        steps=int(math.ceil(duration/tick)); duration=steps*tick
        if steps+1>MAX_FRAMES:
            raise TrajectoryError('当前速度/加速度下轨迹超过 %d 帧（%.0f 秒），请缩短路径' % (MAX_FRAMES,MAX_FRAMES*tick))
        rows=[solve(0,q0)];previous=q0
        for k in range(1,steps+1):
            u=_smooth(k/steps)
            row=solve(u,previous,guide(u));rows.append(row);previous=row['q']
        vmax=[0.0]*6;amax=[0.0]*6
        for i in range(6):
            speeds=[(rows[k+1]['motor'][i]-rows[k]['motor'][i])/(6*tick) for k in range(steps)]
            vmax[i]=max(abs(v) for v in speeds)
            amax[i]=max([abs(speeds[0])/tick,abs(speeds[-1])/tick]+
                [abs(speeds[k+1]-speeds[k])/tick for k in range(steps-1)])
        factor=max([1.0]+[v/c for v,c in zip(vmax,nominal_caps)]+
                   [math.sqrt(a/(r*0.70)) for a,r in zip(amax,rates)])
        if factor<=1.015:
            break
        if attempt==2:
            raise TrajectoryError('连续关节速度或加速度无法满足当前时间约束，请缩短路径或避开奇异姿态')
        duration*=factor*1.05
        reasons.append('密集采样检测到关节变化较快，统一放慢整段路径')
    builder=FrameBuilder()
    window_speeds=_window_speeds(rows,tick,ahead_count)
    for k,row in enumerate(rows):
        checkpoint()
        ci=min(steps,k+ahead_count)
        command=rows[ci]
        speeds=[]
        for i in range(6):
            # Peak nominal rate through the ahead window, rounded UP because
            # the vendor accepts integer RPM. Absolute targets bound travel.
            required=window_speeds[k][i]
            speeds.append(min(wire_caps[i],max(1,int(math.ceil(required*1.10)))))
        builder.append(dict(seq=k+1,t_s=k*tick,phase='cartesian',reference_u=row['u'],
            reference_xyz_mm=list(row['xyz']),reference_joints_deg=list(row['q']),
            reference_motor_deg=list(row['motor']),command_t_s=ci*tick,
            command_xyz_mm=list(command['xyz']),command_joints_deg=list(command['q']),
            command_motor_deg=list(command['quantized_motor']),
            motor_target_pulses=list(command['pulses']),speed_rpm=speeds,
            acceleration=list(acc),final=k==steps))
    frames=builder.freeze()
    # This is geometric lookahead, not a real following-error bound.
    lookahead_distance=max(_norm(_sub(f['command_xyz_mm'],f['reference_xyz_mm'])) for f in frames)
    chord=max((_norm(_sub(point((rows[k]['u']+rows[k+1]['u'])/2),
             [(a+b)/2 for a,b in zip(rows[k]['xyz'],rows[k+1]['xyz'])])) for k in range(steps)),default=0)
    return dict(schema=1,kind=kind,start_xyz_mm=start,target_xyz_mm=target,
        via_mm=None if via_mm is None else list(via_mm),rpy_deg=rpy,
        path_length_mm=length,duration_s=duration,tick_seconds=tick,lookahead_seconds=ahead,
        requested_feed_mm_s=feed,effective_feed_mm_s=length/duration,
        peak_feed_mm_s=1.875*length/duration,slowdown_reasons=list(dict.fromkeys(reasons)),
        frames=frames,total_frames=len(frames),start_motor_deg=start_motor,
        final_motor_deg=rows[-1]['quantized_motor'],final_pulses=rows[-1]['pulses'],
        position_tolerance_mm=position_tolerance_mm,orientation_tolerance_deg=ORIENTATION_TOLERANCE_DEG,
        max_model_position_error_mm=max_pe,max_model_orientation_error_deg=max_re,
        max_reference_speed_rpm=vmax,max_reference_acceleration_rpm_s=amax,
        motor_acceleration_rpm_s=rates,motor_speed_caps_rpm=caps,wire_speed_caps_rpm=wire_caps,
        max_lookahead_distance_mm=lookahead_distance,max_sample_chord_error_mm=chord,
        arc=arc,orientation_policy='adaptive_position' if allow_orientation_adjustment else 'hold_start',path_validation='model_samples_only',
        collision_checked=False,physical_accuracy_verified=False)



def _prepared_candidate(model, start_motor_deg, target_xyz, *, kind, via_mm,
                        feed_mm_s, speed_caps_rpm, acceleration, pulses_per_rev,
                        limits_deg, tick_seconds, lookahead_seconds, checkpoint,
                        original_error):
    """Plan a visible fixed-TCP wrist stage, then rebuild one bounded stream.

    Preparation is tried only after the normal continuous solver fails. The
    geometric candidate is not sufficient: original-pose FK, quantization,
    global derivatives and cross-boundary lookahead are checked independently.
    """
    from .reference_endpoint.wrist_preparation import preparation_candidates
    start_motor = list(start_motor_deg)
    q0 = model.motor_to_joints(start_motor)
    origin = model.forward(q0)
    start = [origin[i][3] for i in range(3)]
    point, length, _arc = _path_geometry(start, target_xyz, kind, via_mm)
    small = min(1e-4, .001/length)
    tangent = [(b-a)/(small*length) for a, b in zip(start, point(small))]
    limits = model.joint_limits_deg if limits_deg is None else limits_deg
    if isinstance(limits, dict):
        limits = [limits.get(n, limits.get(str(n))) for n in range(1, 7)]
    # Resolve the bend plane on the exact aligned wrist, but preserve the
    # measured J5 in all executable samples. Eligibility alone never bypasses
    # the original-path FK, pulse, derivative or lookahead checks below.
    aligned = -model.profile['geometry']['offset_sign']*model.profile['geometry']['joint_offsets_deg'][4]
    aligned += 360*round((q0[4]-aligned)/360)
    geometry_q = list(q0)
    if abs(q0[4]-aligned) <= WRIST_ALIGNMENT_ELIGIBILITY_DEG+1e-12:
        geometry_q[4] = aligned
    candidates = preparation_candidates(model, geometry_q, tangent, limits, checkpoint)
    for candidate in candidates:
        candidate[4] = q0[4]
    if not candidates:
        raise original_error
    failures = []
    for prepared in candidates:
        checkpoint()
        try:
            # Only a tightly bounded near-zero wrist is eligible. A
            # genuinely bent wrist has no such self-motion; do not flatten J5.
            ideal_pe, ideal_re = 0., 0.
            checks = max(2, int(math.ceil(abs(prepared[3]-q0[3]))))
            for k in range(checks+1):
                checkpoint()
                q = [a+(b-a)*k/checks for a,b in zip(q0, prepared)]
                pe, re = planning_pose_error(model.forward(q), origin)
                ideal_pe = max(ideal_pe, _norm(pe))
                ideal_re = max(ideal_re, math.degrees(_norm(re)))
            if ideal_pe > .01 or ideal_re > .02:
                raise TrajectoryError('当前腕部并非足够接近零位，不能保持原 TCP 姿态进行预对齐')
            near_zero = ideal_pe > 1e-8 or ideal_re > 1e-8
            prepared_motor = model.joints_to_motor(prepared)
            guide_q = list(prepared)
            offset = 0.
            if near_zero:
                geometry = model.profile['geometry']
                aligned = -geometry['offset_sign']*geometry['joint_offsets_deg'][4]
                guide_q[4] = aligned+360*round((guide_q[4]-aligned)/360)
                offset = prepared[4]-guide_q[4]
            guide_origin = model.forward(guide_q)
            translation = [guide_origin[i][3]-origin[i][3] for i in range(3)]
            guide_target = [v+d for v,d in zip(target_xyz,translation)]
            guide_via = None if via_mm is None else [v+d for v,d in zip(via_mm,translation)]
            # Near-zero feedback can represent fractions of a motor pulse.
            # Solve a deterministic exact-singular guide, then add the measured
            # J5 offset back to EVERY output joint pose, including both ends.
            # The guide is never a user target: validate every restored pose
            # against the ORIGINAL XYZ/R below, with independent 0.01 mm / 0.02 degree ideal bounds.
            tail = _plan_path_candidate(model, model.joints_to_motor(guide_q), guide_target, kind=kind,
                via_mm=guide_via, feed_mm_s=feed_mm_s, speed_caps_rpm=speed_caps_rpm,
                acceleration=acceleration, pulses_per_rev=pulses_per_rev,
                limits_deg=limits, tick_seconds=tick_seconds,
                lookahead_seconds=lookahead_seconds, check_cancel=checkpoint,
                _path_origin=guide_origin, _prepared_start=True)
            tick = tail['tick_seconds']
            ppr = _six(pulses_per_rev, 1, 0xffffffff, '每圈脉冲数 PPR')
            acc = _six(acceleration, 0, 255, '电机加速度')
            wire_caps = tail['wire_speed_caps_rpm']
            nominal_caps = [max(.35, c*.70) for c in wire_caps]
            if model.profile.get('trajectory_joint_speed_deg_s') is not None:
                nominal_caps = [min(v,model.profile['trajectory_joint_speed_deg_s']*abs(r)/6) for v,r in zip(nominal_caps,model.profile['motor_mapping']['ratios'])]
            rates = tail['motor_acceleration_rpm_s']
            distances = [abs(b-a) for a,b in zip(start_motor, prepared_motor)]
            duration = max(tick*5,
                max(d*1.875/(6*v) for d,v in zip(distances, nominal_caps)),
                max(math.sqrt(d*5.78/(6*r*.55)) for d,r in zip(distances, rates)))
            steps = int(math.ceil(duration/tick))
            duration = steps*tick
            if steps+len(tail['frames']) > MAX_FRAMES:
                raise TrajectoryError('含腕部预对齐的轨迹超过 %d 帧（%.0f 秒），请缩短路径或手动调整姿态' %
                                      (MAX_FRAMES, MAX_FRAMES*tick))
            rows = []
            for k in range(steps):
                checkpoint()
                blend = _smooth(k/steps)
                q = [a+(b-a)*blend for a,b in zip(q0, prepared)]
                rows.append(dict(reference_u=0., reference_xyz_mm=list(start),
                    reference_joints_deg=q, reference_motor_deg=model.joints_to_motor(q),
                    phase='wrist_preparation'))
            for frame in tail['frames']:
                restored = list(frame['reference_joints_deg'])
                restored[4] += offset
                rows.append(dict(reference_u=frame['reference_u'],
                    reference_xyz_mm=point(frame['reference_u']),
                    reference_joints_deg=restored,
                    reference_motor_deg=model.joints_to_motor(restored),phase='cartesian'))
            maximum_pe, maximum_re = 0., 0.
            preparation_pe, preparation_re = 0., 0.
            restored_pe, restored_re = 0., 0.
            for k, row in enumerate(rows):
                checkpoint()
                q = row['reference_joints_deg']
                if k and max(abs(a-b) for a,b in zip(q, rows[k-1]['reference_joints_deg'])) > MAX_JOINT_STEP_DEG+1e-9:
                    raise TrajectoryError('预对齐与轨迹衔接的关节变化超过 3 度')
                pulses = [int(round(m*p/360)) for m,p in zip(row['reference_motor_deg'], ppr)]
                if any(not -2147483648 <= v <= 2147483647 for v in pulses):
                    raise TrajectoryError('预对齐轨迹绝对脉冲超出板卡 signed32 范围')
                quantized = [p*360/r for p,r in zip(pulses, ppr)]
                if any(abs(v)*65536/360 > 0xffffffff for v in row['reference_motor_deg']+quantized):
                    raise TrajectoryError('预对齐轨迹超出 0x36 反馈 uint32 可观测范围')
                quantized_q = model.motor_to_joints(quantized)
                if any(pair is not None and not pair[0]-1e-9 <= v <= pair[1]+1e-9
                       for pair, values in zip(limits, zip(q, quantized_q)) for v in values):
                    raise TrajectoryError('预对齐或量化后关节超出限位')
                expected = [origin[i][:3]+[row['reference_xyz_mm'][i]] for i in range(3)]+[[0,0,0,1]]
                for is_quantized, sample_q in ((False,q),(True,quantized_q)):
                    pe,re = planning_pose_error(model.forward(sample_q), expected)
                    pe,re = _norm(pe), math.degrees(_norm(re))
                    maximum_pe,maximum_re = max(maximum_pe,pe),max(maximum_re,re)
                    if not is_quantized:
                        restored_pe,restored_re = max(restored_pe,pe),max(restored_re,re)
                        if near_zero and (pe > .01 or re > .02):
                            raise TrajectoryError('近零反馈导引恢复后的原路径残差超过 0.01 mm / 0.02 度')
                    if k <= steps:
                        preparation_pe,preparation_re = max(preparation_pe,pe),max(preparation_re,re)
                    if pe > POSITION_TOLERANCE_MM or re > ORIENTATION_TOLERANCE_DEG:
                        raise TrajectoryError('预对齐量化后模型路径误差超限：%.5f mm / %.5f 度' % (pe,re))
                row['pulses'], row['quantized_motor'] = pulses, quantized
            vmax,amax = [],[]
            for i in range(6):
                speeds = [(b['reference_motor_deg'][i]-a['reference_motor_deg'][i])/(6*tick)
                          for a,b in zip(rows,rows[1:])]
                vmax.append(max(abs(v) for v in speeds))
                amax.append(max([abs(speeds[0])/tick,abs(speeds[-1])/tick]+
                    [abs(b-a)/tick for a,b in zip(speeds,speeds[1:])]))
            if any(v > cap*1.015 for v,cap in zip(vmax,nominal_caps)) or any(a > rate*.70*1.015 for a,rate in zip(amax,rates)):
                raise TrajectoryError('预对齐与轨迹衔接不能满足当前速度或加速度约束')
            ahead_count = int(round(lookahead_seconds/tick))
            builder = FrameBuilder()
            for k,row in enumerate(rows):
                checkpoint()
                ci = min(len(rows)-1,k+ahead_count)
                command = rows[ci]
                upper = min(len(rows)-1,max(ci,k+1))
                speeds = []
                for i in range(6):
                    required = max([abs(rows[j+1]['reference_motor_deg'][i]-rows[j]['reference_motor_deg'][i])/(6*tick)
                                    for j in range(k,upper)]+[0.])
                    speeds.append(min(wire_caps[i],max(1,int(math.ceil(required*1.10)))))
                builder.append(dict(seq=k+1,t_s=k*tick,phase=row['phase'],
                    reference_u=row['reference_u'],reference_xyz_mm=list(row['reference_xyz_mm']),
                    reference_joints_deg=list(row['reference_joints_deg']),
                    reference_motor_deg=list(row['reference_motor_deg']),command_t_s=ci*tick,
                    command_xyz_mm=list(command['reference_xyz_mm']),
                    command_joints_deg=list(command['reference_joints_deg']),
                    command_motor_deg=list(command['quantized_motor']),
                    motor_target_pulses=list(command['pulses']),speed_rpm=speeds,
                    acceleration=list(acc),final=k==len(rows)-1))
            frames = builder.freeze()
            total_duration = (len(rows)-1)*tick
            tail.update(frames=frames,total_frames=len(frames),duration_s=total_duration,
                start_motor_deg=start_motor,start_xyz_mm=list(start),target_xyz_mm=list(target_xyz),
                via_mm=None if via_mm is None else list(via_mm),arc=_arc,rpy_deg=matrix_to_rpy(origin),
                final_motor_deg=list(rows[-1]['quantized_motor']),final_pulses=list(rows[-1]['pulses']),
                effective_feed_mm_s=length/total_duration,
                max_reference_speed_rpm=vmax,max_reference_acceleration_rpm_s=amax,
                max_model_position_error_mm=maximum_pe,max_model_orientation_error_deg=maximum_re,
                max_lookahead_distance_mm=max(_norm(_sub(f['command_xyz_mm'],f['reference_xyz_mm'])) for f in frames),
                preparation=dict(kind='fixed_tcp_wrist_alignment',duration_s=duration,frames=steps,eligibility_angle_deg=WRIST_ALIGNMENT_ELIGIBILITY_DEG,
                    start_joints_deg=list(q0),end_joints_deg=list(prepared),
                    max_position_error_mm=preparation_pe,max_orientation_error_deg=preparation_re,
                    ideal_max_position_error_mm=ideal_pe,ideal_max_orientation_error_deg=ideal_re,
                    approximate_start=near_zero,near_zero_regularization=None if not near_zero else
                    dict(joint=5,offset_deg=offset,max_ideal_position_error_mm=restored_pe,
                         max_ideal_orientation_error_deg=restored_re,tolerance_mm=.01,tolerance_deg=.02)))
            tail['slowdown_reasons'].insert(0, '起点腕部接近奇异姿态，先保持原 TCP 姿态进行 J4/J6 预对齐（%.2f 秒），再执行路径' % duration)
            return tail
        except TrajectoryError as exc:
            # Deadline/cancellation is shared with every candidate and escapes
            # at the next checkpoint; no external state or motor I/O changes.
            failures.append(str(exc))
    checkpoint()
    raise TrajectoryError(str(original_error)+'；保持原 TCP 姿态的腕部预对齐也未通过：'+failures[0])


def plan_path(model, start_motor_deg, target_xyz, *, kind='line', via_mm=None,
              feed_mm_s=5.0, speed_caps_rpm, acceleration, pulses_per_rev,
              limits_deg=None, tick_seconds=0.04, lookahead_seconds=0.8,
              check_cancel=None,allow_stop_joint_transition=False,position_tolerance_mm=POSITION_TOLERANCE_MM,
              allow_orientation_adjustment=False):
    """Choose the longest tested bounded lookahead, without changing ACC.

    Each interval uses three interpolation samples, or seven for drawing. This is
    a sampled nominal joint-blend check, not a bound on real driver following,
    independent-axis lag, or continuous swept-volume/collision clearance.
    All candidates share one wall-clock computation limit and cancellation.
    """
    model = PlanningModel(model.profile)
    position_tolerance_mm=_number(position_tolerance_mm,.01,1.,'模型路径误差上限 mm')
    began = time.monotonic()
    def checkpoint():
        if check_cancel is not None and check_cancel():
            raise TrajectoryError('轨迹计算已取消')
        if time.monotonic()-began > MAX_PLAN_SECONDS:
            raise TrajectoryError('轨迹计算超过时间上限，请缩短路径或避开奇异姿态')
    checkpoint()
    requested = _number(lookahead_seconds, 0.04, 0.8, '前视时间秒')
    options = [requested] + [v for v in (.4,.2,.12) if v < requested-1e-9]
    reductions = []
    geometry_cache = {}
    for ahead in options:
        checkpoint()
        try:
            result = _plan_path_candidate(model,start_motor_deg,target_xyz,kind=kind,via_mm=via_mm,
                feed_mm_s=feed_mm_s,speed_caps_rpm=speed_caps_rpm,acceleration=acceleration,
                pulses_per_rev=pulses_per_rev,limits_deg=limits_deg,tick_seconds=tick_seconds,
                lookahead_seconds=ahead,check_cancel=checkpoint,_geometry_cache=geometry_cache,
                _joint_step_limit=10. if allow_stop_joint_transition or kind=='polyline' else 5.,
                position_tolerance_mm=position_tolerance_mm,allow_orientation_adjustment=allow_orientation_adjustment)
        except _ContinuousIKError as exc:
            if allow_orientation_adjustment or kind == 'polyline' or (allow_stop_joint_transition and hasattr(exc,'joint_step_degrees')):
                raise
            result = _prepared_candidate(model,start_motor_deg,target_xyz,kind=kind,via_mm=via_mm,
                feed_mm_s=feed_mm_s,speed_caps_rpm=speed_caps_rpm,acceleration=acceleration,
                pulses_per_rev=pulses_per_rev,limits_deg=limits_deg,tick_seconds=tick_seconds,
                lookahead_seconds=ahead,checkpoint=checkpoint,original_error=exc)
        point,_length,_arc = _path_geometry(result['start_xyz_mm'],result['target_xyz_mm'],kind,via_mm)
        t0 = model.forward(model.motor_to_joints(start_motor_deg))
        max_position, max_orientation = 0.,0.
        rejected = False
        frames = result['frames']
        ahead_count = int(round(ahead/tick_seconds))
        quantized=None
        if position_tolerance_mm>.1 or allow_orientation_adjustment:
            ppr=_six(pulses_per_rev,1,0xffffffff,'每圈脉冲数 PPR')
            quantized=[model.motor_to_joints([round(m*p/360)*360/p for m,p in zip(frame['reference_motor_deg'],ppr)]) for frame in frames]
        for index,frame in enumerate(frames):
            checkpoint()
            future_index=min(len(frames)-1,index+ahead_count)
            future = frames[future_index]
            for fraction in ((.125,.25,.375,.5,.625,.75,.875) if position_tolerance_mm>.1 else (.25,.5,.75)):
                first_joints=frame['reference_joints_deg'] if quantized is None else quantized[index]
                last_joints=future['reference_joints_deg'] if quantized is None else quantized[future_index]
                joints=[a+fraction*(b-a) for a,b in zip(first_joints,last_joints)]
                u=frame['reference_u']+fraction*(future['reference_u']-frame['reference_u'])
                xyz=point(u)
                expected=[t0[i][:3]+[xyz[i]] for i in range(3)]+[[0,0,0,1]]
                pe,re=planning_pose_error(model.forward(joints),expected)
                pe,re=_norm(pe),math.degrees(_norm(re))
                max_position,max_orientation=max(max_position,pe),max(max_orientation,re)
                if pe>position_tolerance_mm or (not allow_orientation_adjustment and re>.2):
                    rejected=True
                    break
            if rejected:
                break
        if rejected:
            reductions.append(dict(lookahead_seconds=ahead,
                nominal_joint_blend_position_error_mm=max_position,
                nominal_joint_blend_orientation_error_deg=max_orientation))
            continue
        result.update(requested_lookahead_seconds=requested,
            nominal_joint_blend_position_error_mm=max_position,
            nominal_joint_blend_orientation_error_deg=max_orientation,
            nominal_joint_blend_position_tolerance_mm=position_tolerance_mm,
            nominal_joint_blend_orientation_tolerance_deg=.2,
            nominal_joint_blend_samples_per_interval=7 if position_tolerance_mm>.1 else 3,lookahead_reductions=reductions)
        if reductions:
            result['slowdown_reasons'].append('前视区间的名义关节插值误差较大，前视时间从 %.2f 秒缩短至 %.2f 秒并重新限速' % (requested,ahead))
        result.update(planning_seconds=time.monotonic()-began,geometry_cache_hits=geometry_cache.get('hits',0),planner='v16-rolling-cartesian',ik_position_tolerance_mm=.01)
        if allow_orientation_adjustment:
            result['reference_rotations']=[[row[:3] for row in model.forward(q)[:3]] for q in quantized]
            result['final_rpy_deg']=matrix_to_rpy(result['reference_rotations'][-1])
            result['max_orientation_change_deg']=result.pop('max_model_orientation_error_deg')
            result['max_model_orientation_error_deg']=0.
        return result
    failure=TrajectoryError('最短前视下名义关节插值仍超过 %.3g mm / 0.2 度，请拆分路径或避开奇异姿态'%position_tolerance_mm)
    failure.failure_kind='interpolation_error';failure.path_fraction=u
    raise failure
