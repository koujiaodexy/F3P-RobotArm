"""Continuous Cartesian execution over the V9 bounded FIFO transport.

Feedback checks are a model-based software guard, not a collision detector or
an independent measurement of TCP accuracy. No legacy query is issued while
FPGA trajectory ownership is held.
"""
from __future__ import annotations
import copy
import math
import threading
import time
import uuid

NODES = tuple(range(1, 7))


def _segment_distance(point, a, b):
    delta = [y-x for x,y in zip(a,b)]
    size = sum(x*x for x in delta)
    u = max(0., min(1., sum((p-x)*d for p,x,d in zip(point,a,delta))/size)) if size else 0.
    return math.sqrt(sum((p-x-u*d)**2 for p,x,d in zip(point,a,delta)))


class CartesianTrajectoryMixin:
    TRAJECTORY_FEEDBACK_MAX_AGE = .40
    TRAJECTORY_STARTUP_GRACE = .20
    TRAJECTORY_POLL_SECONDS = .02
    TRAJECTORY_STOP_SECONDS = 5.
    TRAJECTORY_FINISH_GRACE_SECONDS = 15.
    TRAJECTORY_PATH_TOLERANCE_MM = 2.
    TRAJECTORY_ORIENTATION_TOLERANCE_DEG = 2.
    # Extra motor-angle margin outside the time-window following envelope.
    # This does not alter the independent final-arrival or TCP checks.
    TRAJECTORY_FOLLOW_MOTOR_MARGIN_DEG = 1.

    def _trajectory_reasons(self, motion_kind):
        if motion_kind == 'ptp':
            return []
        if motion_kind not in ('line', 'arc'):
            return ['未知运动模式']
        reasons = []
        if not getattr(self.controller.backend, 'supports_continuous_trajectory', False):
            reasons.append('连续直线/圆弧需要 V9 FPGA 轨迹接口；当前仍可离线预览或执行 PTP')
        if any(self.controller.nodes[n].acceleration == 0 for n in NODES):
            reasons.append('连续模式需要六轴加速度为 1～255；不会自动修改当前设置')
        return reasons

    def _preview_continuous(self, position_mm, callback, *, motion_kind, via_mm,
                            feed_mm_s, seed_deg, speed_limit_rpm, acceleration,
                            clearance_confirmed):
        def work():
            from .cartesian import _vector
            from .protocol import HOME_MAX_SPEEDS_RPM
            from .trajectory import plan_path
            model = self._get_model()
            position = _vector(position_mm, 3, 'XYZ')
            motor = self._read_axes() if seed_deg is None else model.joints_to_motor(_vector(seed_deg,6,'seed'))
            ppr = self._ppr()
            if ppr is None:
                raise ValueError('连续轨迹需要明确六轴每电机圈脉冲数')
            speeds = self._settings(speed_limit_rpm, 'speed_rpm', 1, 3000)
            accs = self._settings(acceleration, 'acceleration', 0, 255)
            caps = {n:min(speeds[n], HOME_MAX_SPEEDS_RPM[n]) for n in NODES}
            context = self._context()
            trajectory = plan_path(model,motor,position,kind=motion_kind,via_mm=via_mm,
                feed_mm_s=feed_mm_s,speed_caps_rpm=caps,acceleration=accs,
                pulses_per_rev=ppr,limits_deg=self._solver_limits(),check_cancel=self._check)
            self._check(force_profile=True)
            if self._context() != context:
                raise RuntimeError('计算期间零位、模型、限位或速度配置发生变化，请重新预览')
            target_motor = trajectory['final_motor_deg']
            reasons = self._live_reasons(clearance_confirmed) + self._trajectory_reasons(motion_kind)
            if seed_deg is not None:
                reasons.append('离线指定起点，仅可预览；执行须重新读取现场反馈')
            # UI copies at most 501 path vertices; execution retains every frame.
            frames = trajectory['frames']
            stride = max(1, math.ceil(len(frames)/500))
            chosen = frames[::stride]
            if chosen[-1]['seq'] != frames[-1]['seq']:
                chosen.append(frames[-1])
            path = [dict(fraction=f['reference_u'],joints_deg=f['reference_joints_deg'],
                         position_mm=f['reference_xyz_mm']) for f in chosen]
            plan = dict(id=str(uuid.uuid4()),created_monotonic=time.monotonic(),
                target_position_mm=position,target_rpy_deg=trajectory['rpy_deg'],
                joints_deg=model.motor_to_joints(target_motor),seed_deg=model.motor_to_joints(motor),
                motor_start_deg=motor,motor_target_deg=target_motor,
                target_pulses={n:trajectory['final_pulses'][n-1] for n in NODES},
                pulses_per_rev=ppr,path=path,trajectory=trajectory,
                predicted_pose=self._pose_accuracy(target_motor,position,trajectory['rpy_deg']),
                duration_seconds=trajectory['duration_s'],motor_speed_rpm=caps,motor_acceleration=accs,
                axis_motion_seconds={n:trajectory['duration_s'] for n in NODES},
                profile_digest=model.profile_digest,target_frame=model.target_frame,
                reference_only=model.reference_only,simulation=self._simulation(),
                live_eligible=not reasons,reasons=reasons,clearance_confirmed=clearance_confirmed is True,
                path_kind='cartesian_'+motion_kind,synchronized_start=True,
                cartesian_straight_line=motion_kind=='line',collision_checked=False,
                physical_accuracy_verified=False,context=context)
            self._plans = {plan['id']:copy.deepcopy(plan)}
            self._publish(plan=plan,trajectory_progress=None)
            return copy.deepcopy(plan)
        return self._start('轨迹预览',callback,work,result_callback=True,offline=seed_deg is not None)

    def _trajectory_feedback(self, status, plan, elapsed):
        """Validate bounded-age samples and track the local nominal path envelope."""
        from .kinematics import pose_error, rpy_to_matrix
        from .zero_home import RATIOS
        c = self.controller
        samples = status.get('feedback', {})
        valid = []
        for n in NODES:
            sample = samples.get(n, samples.get(str(n)))
            fields = ('position_counts_signed','motor_flags','home_flags','position_age_s',
                      'motor_age_s','home_age_s','position_seq','motor_seq','home_seq')
            if not isinstance(sample,dict) or any(sample.get(k) is None for k in fields):
                if not status.get('fired_seq') and elapsed < self.TRAJECTORY_STARTUP_GRACE:
                    return None
                raise RuntimeError('%d号连续轨迹反馈缺失' % n)
            if any(not math.isfinite(sample[k]) or sample[k] < 0 or
                   sample[k] > self.TRAJECTORY_FEEDBACK_MAX_AGE
                   for k in ('position_age_s','motor_age_s','home_age_s')):
                # Stale data must never be treated as an arrival confirmation.
                if not status.get('fired_seq') and elapsed < self.TRAJECTORY_STARTUP_GRACE:
                    return None
                raise RuntimeError('%d号连续轨迹反馈过期' % n)
            if sample['motor_flags'] & 0x8C or sample['home_flags'] & 0x3F != 3:
                raise RuntimeError('%d号连续轨迹电源或保护异常' % n)
            if not sample['motor_flags'] & 1:
                raise RuntimeError('%d号连续轨迹期间失能' % n)
            angle = sample['position_counts_signed']*360/65536
            if not math.isfinite(angle):
                raise RuntimeError('%d号位置反馈无效' % n)
            pair = c.joint_limits.bounds.get(n)
            if pair and not pair[0]-.001 <= angle/RATIOS[n] <= pair[1]+.001:
                raise RuntimeError('%d号实测位置超出限位' % n)
            valid.append((sample,angle))
        motor = [row[1] for row in valid]
        model = self._get_model()
        q = model.motor_to_joints(motor)
        if any(pair is not None and not pair[0]-.001 <= angle <= pair[1]+.001
               for angle,pair in zip(q,self._solver_limits())):
            raise RuntimeError('实测关节位置超出模型限位')
        trajectory = plan['trajectory']
        frames = trajectory['frames']
        index = max(0,min(len(frames)-1,int(status.get('fired_seq',0))-1))
        age = max(row[0]['position_age_s'] for row in valid)
        # Asynchronous CAN feedback has time skew. Search only a bounded local
        # time window, not the whole curve, so a frozen/lagging axis is rejected.
        radius = int(math.ceil((age+trajectory['lookahead_seconds']+.30)/trajectory['tick_seconds']))+1
        window = frames[max(0,index-radius):min(len(frames),index+radius+1)]
        for i in range(6):
            values = [f['reference_motor_deg'][i] for f in window]
            tolerance = max(self.TRAJECTORY_FOLLOW_MOTOR_MARGIN_DEG,360/plan['pulses_per_rev'][i+1])
            if not min(values)-tolerance <= motor[i] <= max(values)+tolerance:
                raise RuntimeError('%d号轴连续轨迹跟随偏差过大' % (i+1))
        transform = model.forward(q)
        xyz = [transform[i][3] for i in range(3)]
        points = [f['reference_xyz_mm'] for f in window]
        path_error = min([_segment_distance(xyz,a,b) for a,b in zip(points,points[1:])]
                         or [_segment_distance(xyz,points[0],points[0])])
        rotation = rpy_to_matrix(trajectory['rpy_deg'])
        expected = [rotation[i]+[xyz[i]] for i in range(3)]+[[0,0,0,1]]
        orientation = math.degrees(math.sqrt(sum(x*x for x in pose_error(transform,expected)[1])))
        skew_margin = trajectory['peak_feed_mm_s']*age
        if path_error > self.TRAJECTORY_PATH_TOLERANCE_MM+skew_margin:
            raise RuntimeError('连续轨迹模型路径偏差过大：%.3f mm' % path_error)
        if orientation > self.TRAJECTORY_ORIENTATION_TOLERANCE_DEG:
            raise RuntimeError('连续轨迹工具朝向偏差过大：%.3f 度' % orientation)
        with c._lock:
            for n,(sample,angle) in zip(NODES,valid):
                state = c.nodes[n]
                state.motor_angle = angle
                state.motor_flags = sample['motor_flags']
                state.home_flags = sample['home_flags']
                state.position_time = time.monotonic()-sample['position_age_s']
                state.online = '在线'
            self._state['trajectory_progress'] = dict(fired_seq=status.get('fired_seq',0),
                total_frames=len(frames),elapsed_s=elapsed,path_error_mm=path_error,
                feedback_max_age_s=age,orientation_error_deg=orientation,
                phase=frames[index].get('phase', 'path'))
        arrived = bool(status.get('final_sent'))
        seqs = []
        for i,(sample,angle) in enumerate(valid):
            tolerance = max(self.VERIFY_MOTOR_TOLERANCE_DEG,180/plan['pulses_per_rev'][i+1]+360/65536)
            arrived = arrived and bool(sample['motor_flags'] & 2) and abs(angle-plan['motor_target_deg'][i]) <= tolerance
            seqs.extend([sample['position_seq'],sample['motor_seq'],sample['home_seq']])
        return arrived,tuple(seqs)

    def _execute_continuous(self, plan, callback):
        frozen = copy.deepcopy(plan)
        def work():
            from .zero_home import RATIOS
            self._check_plan(frozen)
            kind = 'line' if frozen['path_kind']=='cartesian_line' else 'arc'
            reasons = self._trajectory_reasons(kind)
            if reasons:
                raise RuntimeError('；'.join(reasons))
            current = self._read_axes(require_enabled=True)
            self._check_plan(frozen)
            tolerances = self._start_tolerances(frozen,current) if hasattr(self,'_start_tolerances') else {
                n:max(.25,360/frozen['pulses_per_rev'][n]+360/65536) for n in NODES}
            if any(abs(current[n-1]-frozen['motor_start_deg'][n-1]) > tolerances[n] for n in NODES):
                raise RuntimeError('当前位置已离开轨迹预览起点，请重新计算')
            c = self.controller
            b = c.backend
            delay = max(0.,max(b.enable_delay-(time.monotonic()-c._enabled_at.get(n,0)) for n in NODES))
            if self._cancelled.wait(delay):
                self._check()
            with c._lock:
                self._check()
                # Conservative ownership covers even an ambiguous prepare/start.
                self._trajectory_owned = True
                self._participants.update(NODES)
                self._state['participants'] = list(NODES)
                c.active_node = 1
                for n in NODES:
                    c.nodes[n].moving = True
                    c.nodes[n].direction = '连续轨迹'
                b.trajectory_prepare()
                frames = frozen['trajectory']['frames']
                queued = 0
                for frame in frames[:min(24,len(frames))]:
                    self._check()
                    b.trajectory_enqueue(frame['seq'],frame['motor_target_pulses'],
                        frame['speed_rpm'],frame['acceleration'],final=frame['final'])
                    queued += 1
                self._check()
                b.trajectory_start()
            started = time.monotonic()
            deadline = started+frozen['duration_seconds']*1.5+self.TRAJECTORY_FINISH_GRACE_SECONDS
            stable,last_sequence = 0,None
            checked_context = started
            while time.monotonic() < deadline:
                self._check()
                now = time.monotonic()
                if now-checked_context >= .10:
                    if self._context() != frozen['context'] or frozen['id'] not in self._plans:
                        raise RuntimeError('执行期间零位、模型、限位或速度配置发生变化')
                    checked_context = now
                with c._lock:
                    self._check()
                    status = b.trajectory_status()
                    if status.get('fault') or status.get('error'):
                        from ..trajectory_runtime import fault_message
                        raise RuntimeError(fault_message(status))
                    if not status.get('owned') or status.get('stop_done'):
                        raise RuntimeError('连续轨迹执行权或运行状态意外丢失')
                    space = max(0,int(status['capacity'])-int(status['fifo_count'])-2)
                    for frame in frames[queued:queued+min(space,8)]:
                        self._check()
                        b.trajectory_enqueue(frame['seq'],frame['motor_target_pulses'],
                            frame['speed_rpm'],frame['acceleration'],final=frame['final'])
                        queued += 1
                sample = self._trajectory_feedback(status,frozen,now-started)
                if sample is not None:
                    arrived,seqs = sample
                    if not arrived:
                        stable,last_sequence = 0,None
                    elif last_sequence is None or all(a>b for a,b in zip(seqs,last_sequence)):
                        stable += 1
                        last_sequence = seqs
                    if stable >= self.VERIFY_SAMPLES:
                        break
                self._publish()
                if self._cancelled.wait(self.TRAJECTORY_POLL_SECONDS):
                    self._check()
            else:
                raise RuntimeError('连续轨迹终点未在预计时间内确认到位')
            self._start_stop()
            if not self._stop_done.wait(self.TRAJECTORY_STOP_SECONDS+1.) or not all(self._stop_results.values()):
                raise RuntimeError('连续轨迹结束停止未全部确认')
            self._check()
            if not self._verify(frozen,require_arrived=False):
                raise RuntimeError('连续轨迹停止后位置偏离目标')
            actual = self._pose_accuracy([c.nodes[n].motor_angle for n in NODES],
                frozen['target_position_mm'],frozen['target_rpy_deg'])
            self._plans.clear()
            self._publish(actual_pose=actual,actual_motor_degrees=[c.nodes[n].motor_angle for n in NODES],
                elapsed_seconds=time.monotonic()-started,message='轨迹终点与六轴停止已核验')
            return True
        return self._start('连续轨迹执行',callback,work)

    def _start_trajectory_stop(self, retry_failed=False):
        c = self.controller
        with c._lock:
            if self._stop_started:
                if not self._stop_done.is_set():
                    return
                ok = all(self._stop_results.get(n) is True for n in NODES)
                if not retry_failed or ok:
                    callbacks,self._stop_callbacks = self._stop_callbacks,[]
                    for cb in callbacks:
                        self._callback(cb,ok)
                    return
            self._stop_started = True
            self._stop_done.clear()
            self._stop_results = {n:False for n in NODES}
            def stop_worker():
                error = ''
                try:
                    c.backend.trajectory_cancel()
                    deadline = time.monotonic()+self.TRAJECTORY_STOP_SECONDS
                    while time.monotonic() < deadline:
                        status = c.backend.trajectory_status()
                        mask = status.get('stop_mask',0)
                        with c._lock:
                            self._stop_results = {n:bool(mask & (1<<(n-1))) for n in NODES}
                        if status.get('stop_done'):
                            if mask != 63 or status.get('moving_mask'):
                                raise RuntimeError('六轴停止未全部确认')
                            c.backend.trajectory_release()
                            with c._lock:
                                self._trajectory_owned = False
                                for n in NODES:
                                    c.nodes[n].moving = False
                                    c.nodes[n].direction = '停止'
                                c.active_node = None
                            break
                        time.sleep(self.TRAJECTORY_POLL_SECONDS)
                    else:
                        raise RuntimeError('连续轨迹停止确认超时')
                except Exception as exc:
                    error = str(exc)
                    # Any unconfirmed ownership/release keeps every motion lock.
                    with c._lock:
                        for n in NODES:
                            c.nodes[n].moving = True
                        self._stop_results = {n:False for n in NODES}
                finally:
                    with c._lock:
                        ok = not error and not self._trajectory_owned
                        self._state.update(stop_results=dict(self._stop_results),
                            message='六轴停止已确认' if ok else '停止未全部确认，可重试停止：'+error)
                        self._stop_done.set()
                        callbacks,self._stop_callbacks = self._stop_callbacks,[]
                        c._publish()
                    for cb in callbacks:
                        self._callback(cb,ok)
            threading.Thread(target=stop_worker,name='f3p-trajectory-stop',daemon=True).start()
