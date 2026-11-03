# Reviewed rolling executor based on V2; vendor file remains intact.
import copy
import math
import time
from .rolling_trajectory import RollingFrames
from .reference_endpoint.trajectory_service import NODES, _segment_distance


def rolling_take_count(frames,queued,status):
    """Wait for normal frames while the device still has a safe buffer.

    Taking beyond head commits the terminal braking reserve irreversibly.
    Eight 40ms frames leave 320ms for the existing 20ms poll/enqueue loop;
    status/feedback/lease checks continue while waiting, without blocking IO.
    """
    space=max(0,int(status['capacity'])-int(status['fifo_count'])-2)
    with frames.lock:
        available=len(frames.head)+(len(frames.reserve) if frames.closed else 0)-queued
        if available>0:return min(space,8,available)
        if not frames.complete and not frames.closed and int(status['fifo_count'])<=8:
            return min(space,8)
    return 0

class StreamingExecutorMixin:
    def _check_conditional_frame(self,frame,plan,model=None):
        from .coupled_limits import check_model_box
        if model is None:model=self._get_model()
        if not model._profile.get('j3_j4_rule'):return
        command=model.motor_to_joints(frame['command_motor_deg'])
        previous=(model.motor_to_joints(plan['motor_start_deg']) if frame['seq']==1
                  else self._conditional_previous)
        check_model_box(model,previous,command)
        check_model_box(model,frame['reference_joints_deg'],command)
        self._conditional_previous=command

    def _execute_continuous(self, plan, callback):
        if not isinstance(plan['trajectory']['frames'],RollingFrames):
            return super()._execute_continuous(plan,callback)
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
            tolerances=self._start_tolerances(frozen,current) if hasattr(self,'_start_tolerances') else {
                n:max(.25,360/frozen['pulses_per_rev'][n]+360/65536) for n in NODES}
            if any(abs(current[n-1]-frozen['motor_start_deg'][n-1]) > tolerances[n] for n in NODES):
                raise RuntimeError('当前位置已离开轨迹预览起点，请重新计算')
            c = self.controller
            b = c.backend
            conditional_model=self._get_model()
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
                for frame in frames.take(0,24,frozen):
                    self._check()
                    self._check_conditional_frame(frame,frozen,conditional_model)
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
                        from .trajectory_runtime import fault_message
                        raise RuntimeError(fault_message(status))
                    if not status.get('owned') or status.get('stop_done'):
                        raise RuntimeError('连续轨迹执行权或运行状态意外丢失')
                    count=rolling_take_count(frames,queued,status)
                    for frame in frames.take(queued,count,frozen):
                        self._check()
                        self._check_conditional_frame(frame,frozen,conditional_model)
                        b.trajectory_enqueue(frame['seq'],frame['motor_target_pulses'],
                            frame['speed_rpm'],frame['acceleration'],final=frame['final'])
                        queued += 1
                deadline = started+frozen['duration_seconds']*1.5+self.TRAJECTORY_FINISH_GRACE_SECONDS
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
            if frames.failed:raise RuntimeError(frames.failed)
            self._plans.clear()
            self._publish(actual_pose=actual,actual_motor_degrees=[c.nodes[n].motor_angle for n in NODES],
                elapsed_seconds=time.monotonic()-started,message='轨迹终点与六轴停止已核验')
            return True
        def pinned_work():
            import os,sys
            allowed=None
            if sys.platform.startswith('linux'):
                allowed=os.sched_getaffinity(0)
                if len(allowed)>1:os.sched_setaffinity(0,{min(allowed)})
            try:return work()
            finally:
                if allowed is not None:os.sched_setaffinity(0,allowed)
        # Cyclic GC pauses every Python thread. Defer automatic collection
        # only while this single-owner transport is active; the model worker
        # remains in its separate process and frame retention stays bounded.
        import gc
        collect_enabled=gc.isenabled()
        if collect_enabled:gc.disable()
        try:
            return self._start('滚动轨迹执行',callback,pinned_work)
        finally:
            try:frozen['trajectory']['frames'].close()
            finally:
                if collect_enabled:gc.enable()


    def _trajectory_feedback(self, status, plan, elapsed):
        """Validate bounded-age samples and track the local nominal path envelope."""
        from .reference_endpoint.kinematics import pose_error, rpy_to_matrix
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
            pair = None if n==4 and c.joint_limits.coupled else c.joint_limits.bounds.get(n)
            if pair and not pair[0]-.001 <= angle/RATIOS[n] <= pair[1]+.001:
                raise RuntimeError('%d号实测位置超出限位' % n)
            valid.append((sample,angle))
        motor = [row[1] for row in valid]
        c.joint_limits.check_move({n:motor[n-1]/RATIOS[n] for n in NODES},
                                  {n:motor[n-1]/RATIOS[n] for n in NODES})
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
        from .grasp_transfer import feedback_limits, endpoint_tolerance, J6_TRANSIT_TOLERANCE_DEG
        grasp_limits=feedback_limits(trajectory)
        for i in range(6):
            values = [f['reference_motor_deg'][i] for f in window]
            tolerance = self._follow_tolerance_deg(i,plan['pulses_per_rev'][i+1])
            if i==5 and grasp_limits is not None:
                tolerance=max(tolerance,J6_TRANSIT_TOLERANCE_DEG*RATIOS[6])
            if not min(values)-tolerance <= motor[i] <= max(values)+tolerance:
                raise RuntimeError('%d号轴连续轨迹跟随偏差过大' % (i+1))
        transform = model.forward(q)
        xyz = [transform[i][3] for i in range(3)]
        orientation_transform=transform
        if grasp_limits is not None:
            # J6 roll has its own loaded-wrist envelope. Do not count that
            # same allowed roll again as a J1-J5 orientation-follow failure.
            roll=min(window,key=lambda frame:abs(frame['reference_motor_deg'][5]-motor[5]))['reference_motor_deg'][5]
            orientation_transform=model.forward(model.motor_to_joints(motor[:5]+[roll]))
        points = [f['reference_xyz_mm'] for f in window]
        path_error = min([_segment_distance(xyz,a,b) for a,b in zip(points,points[1:])]
                         or [_segment_distance(xyz,points[0],points[0])])
        rotations=trajectory.get('reference_rotations')
        if trajectory.get('orientation_policy')=='adaptive_position':
            if trajectory.get('orientation_reference_in_frames'):
                rotations=[f.get('reference_rotation') for f in window]
                if not rotations or any(r is None for r in rotations):raise RuntimeError('自动朝向轨迹缺少逐帧朝向参考')
            else:
                if not rotations or len(rotations)!=len(frames):raise RuntimeError('自动朝向轨迹缺少完整朝向参考')
                rotations=rotations[max(0,index-radius):min(len(frames),index+radius+1)]
            orientation=min(math.degrees(math.sqrt(sum(x*x for x in pose_error(orientation_transform,[r[i]+[xyz[i]] for i in range(3)]+[[0,0,0,1]])[1])))
                            for r in rotations)
        else:
            rotation = rpy_to_matrix(trajectory['rpy_deg'])
            expected = [rotation[i]+[xyz[i]] for i in range(3)]+[[0,0,0,1]]
            orientation = math.degrees(math.sqrt(sum(x*x for x in pose_error(orientation_transform,expected)[1])))
        skew_margin = trajectory.get('requested_feed_mm_s',trajectory['peak_feed_mm_s'])*age
        path_limit=self.TRAJECTORY_PATH_TOLERANCE_MM
        if 'drawing_position_budget_mm' in trajectory:path_limit=min(path_limit,trajectory['position_tolerance_mm'])
        orientation_limit=self.TRAJECTORY_ORIENTATION_TOLERANCE_DEG
        if grasp_limits is not None:
            path_limit,orientation_limit=grasp_limits
        if path_error > path_limit+skew_margin:
            raise RuntimeError('连续轨迹模型路径偏差过大：%.3f mm' % path_error)
        if orientation > orientation_limit:
            print('TRAJECTORY_FOLLOW_FAILURE',dict(reason='orientation',orientation_error_deg=orientation,
                fired_seq=status.get('fired_seq'),motor_deg=motor,model_joints_deg=q,
                feedback_ages_s=[row[0]['position_age_s'] for row in valid],
                reference_motor_deg=frames[index]['reference_motor_deg'],
                command_motor_deg=frames[index]['command_motor_deg'],speed_rpm=frames[index]['speed_rpm'],
                phase=frames[index].get('phase')),flush=True)
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
            tolerance = endpoint_tolerance(plan,i+1,tolerance)
            arrived = arrived and bool(sample['motor_flags'] & 2) and abs(angle-plan['motor_target_deg'][i]) <= tolerance
            seqs.extend([sample['position_seq'],sample['motor_seq'],sample['home_seq']])
        return arrived,tuple(seqs)

