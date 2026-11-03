"""Real axis-endpoint sorting on JointMotion's one cancellable CAN worker.

The camera map addresses the shaft, while CAD drop coordinates address the
tool tip. Only drop conversion uses the configured 100/10 mm installation.
Optional gripper commands use the sole key/OLED service's exclusive lease.
"""
import copy
import json
import math
from pathlib import Path
import threading
import time

from . import kinematics as k
from .grasp_preview import COLORS, NAMES, fresh_targets, quantities, checked_pick_offset
from .six_item_catalog import DROP_BOX_FOR_ITEM, PICK_LABELS

BOX_LAYOUT = json.loads(Path(__file__).with_name('grasp_boxes.json').read_text(encoding='utf8'))
# Field correction: car-left is positive model Y; keep the measured CAD boxes.
DROP_LEFT_COMPENSATION_MM = 6.0
from .grasp_transfer import JOINT_SPEED_DEG_S, LINE_SPEED_MM_S, accelerations as line_accelerations

TARGET_POLL_SECONDS = .03


class RunControl:
    def __init__(self):
        self.paused = threading.Event()
        self.stopped = threading.Event()
        self._start_lock = threading.Lock()
        self._start_ready = self._start_consumed = False
        self.start_requested = threading.Event()

    @property
    def start_ready(self):
        with self._start_lock:
            return self._start_ready and not self.stopped.is_set() and not self.paused.is_set()

    def set_start_ready(self, ready):
        with self._start_lock:
            self._start_ready = bool(ready) and not self._start_consumed and not self.stopped.is_set() and not self.paused.is_set()

    def request_start(self):
        with self._start_lock:
            if not self._start_ready or self._start_consumed or self.stopped.is_set() or self.paused.is_set():
                return False
            self._start_ready = False
            self._start_consumed = True
            self.start_requested.set()
            return True

    def take_start_request(self):
        with self._start_lock:
            requested = self.start_requested.is_set()
            self.start_requested.clear()
            return requested and not self.stopped.is_set() and not self.paused.is_set()

    def disarm_start(self):
        with self._start_lock:
            self._start_ready = False
            self._start_consumed = True
            self.start_requested.clear()

    def cancel(self):
        self.stopped.set()
        self.disarm_start()

    def checkpoint(self, check):
        check()
        while self.paused.is_set():
            if self.stopped.wait(.05):
                raise RuntimeError('夹取任务已取消')
            check()
        if self.stopped.is_set():
            raise RuntimeError('夹取任务已取消')
        check()


def release_pose(color, rotation):
    box = BOX_LAYOUT['boxes'][DROP_BOX_FOR_ITEM[color]]
    tip = [*box['center_xy_mm'], box['rim_z_mm'] + 10.0]
    tip[1] += DROP_LEFT_COMPENSATION_MM
    return dict(position_mm=k.sub(tip, k.mv(rotation, BOX_LAYOUT['tool_local_mm'])),
                rotation=copy.deepcopy(rotation))


def cycle_steps(target, pick_rotation):
    from .drawing import rotation
    down = rotation('minus_z', pick_rotation)
    drop = release_pose(target['color'], down)
    x, _, z = target['endpoint_xyz_mm']
    # User-requested four-segment cadence. J targets use the existing precise
    # endpoint controller; Y strokes use a relaxed transit budget.
    return [dict(label=name, mode=mode, goal=dict(position_mm=list(xyz), rotation=copy.deepcopy(r)))
            for name, mode, xyz, r in (
                ('快速点到点 Y220', 'J', [x,220.,z], pick_rotation),
                ('前伸定位 Y330', 'L', [x,330.,z], pick_rotation),
                ('缩回 Y220', 'L', [x,220.,z], pick_rotation),
                ('%s投放至%s盒上方10mm' % (PICK_LABELS[target['color']], NAMES[DROP_BOX_FOR_ITEM[target['color']]]), 'J', drop['position_mm'], down))]


def line_request(step):
    return dict(mode='L', orientation='hold', required_direction='hold',
                goal=step['goal'], speed=LINE_SPEED_MM_S, joint_speed=JOINT_SPEED_DEG_S,
                clearance_confirmed=True)


def close_prepared_lines(steps):
    from .trajectory_preparation import close_report
    for step in steps:
        close_report(step.get('prepared_report'))


def prepare_cycle_lines(cart, start, steps, reference, check, reports=None):
    """Bind fully prepared transfers to the sole hardware task before motion."""
    from .grasp_transfer import plan_cycle
    context = copy.deepcopy(cart.continuous._context())
    if not getattr(cart.task.controller.backend,'supports_continuous_trajectory',False):
        raise RuntimeError('快速取放需要板卡连续轨迹接口')
    supplied = reports is not None
    reports = reports if supplied else []
    try:
        if not supplied:
            hardware = cart.planning_hardware(JOINT_SPEED_DEG_S)
            reports = plan_cycle(start, steps, cart.bounds(), hardware, check)
        if len(reports)!=len(steps):
            raise RuntimeError('取放整段准备数量不一致')
        for step,report in zip(steps,reports):
            check()
            request = dict(line_request(step),mode=step['mode'])
            step['prepared_report'] = report
            report.update(reference=copy.deepcopy(reference),
                          request_signature=cart.request_signature(request),
                          execution_context=copy.deepcopy(context))
        check()
        if context != cart.continuous._context():
            raise RuntimeError('准备期间现场配置变化，未启动取放')
    except BaseException:
        # Cancellation can occur after plan_cycle returns but before a
        # report is attached to its step. Release those reports as well.
        from .trajectory_preparation import close_report
        seen = set()
        for report in reports + [step.pop('prepared_report', None) for step in steps]:
            if report is not None and id(report) not in seen:
                seen.add(id(report))
                close_report(report)
        raise


def preflight_cycle(start, steps, bounds, check=lambda: None):
    """Solve the entire cycle before its first movement; fail closed.

    LIN is sampled here for early unreachable feedback and fully prepared
    before the first movement. The executor rechecks each addressed start.
    J steps keep the very same checked branch at execution.
    """
    from .analytic_inverse import solve
    from .reference_adapter import make_model
    from .coupled_limits import check_model_box
    from .collision import check_joint_box, check_target
    model = make_model(start, bounds, check=check)
    q = list(start)
    previous = k.forward(q)
    output = []
    for step in steps:
        check()
        goal = step['goal']
        check_target(goal['position_mm'])
        pe, ae = k.pose_error(goal, previous)
        if pe < .02 and ae < .02:
            continue
        if step['mode'] == 'L' and ae > .05:
            raise ValueError('直线段不能隐式转腕：' + step['label'])
        points = [goal]
        if step['mode'] == 'L':
            n = max(1, math.ceil(pe/5.))
            points = [dict(position_mm=[a+(b-a)*i/n for a,b in zip(previous['position_mm'],goal['position_mm'])],
                           rotation=goal['rotation'])for i in range(1,n+1)]
        guide = []
        for pose in points:
            answers = solve(pose, q, bounds, check, model=model, all_solutions=True)
            selected = None
            for answer in answers or ():
                trial = answer['angles_deg']
                try:
                    check_model_box(model, q, trial)
                    check_joint_box(q, trial, check)
                except ValueError:
                    continue
                if step['mode'] == 'L' and max(abs(a-b)for a,b in zip(q,trial)) > 25:
                    continue
                # The solver already orders candidates by seed distance.
                # Only the first fully checked legal branch is executed;
                # checking later unused branches cannot change that choice.
                selected = trial
                break
            if selected is None:
                raise ValueError('%s不可达或限位不通过：轴端 X%.1f Y%.1f Z%.1f mm；本轮未启动' %
                                 (step['label'], *pose['position_mm']))
            q = selected
            guide.append(list(q))
        output.append(dict(step, angles_deg=list(q), guide_angles_deg=guide))
        previous = goal
    return output


def _refresh_target(telemetry, original, now, expected_session_id=None, pick_offset_mm=None):
    candidates = fresh_targets(telemetry, now, expected_session_id, pick_offset_mm)[original['color']]
    # No gripper is connected, so already tested objects may remain visible.
    # Match the distinct original snapshot locations instead of repeatedly
    # choosing the first remaining tracked object.
    nearest = sorted(candidates, key=lambda row: math.dist(row['pixel_uv'], original['pixel_uv']))
    if not nearest or math.dist(nearest[0]['pixel_uv'], original['pixel_uv']) > 20.:
        raise RuntimeError('所选%s目标已移动或消失，请重新开始识别任务' % PICK_LABELS[original['color']])
    return nearest[0]


def next_target(telemetry, color, consumed, now, expected_session_id=None, pick_offset_mm=None):
    if expected_session_id is not None:
        from .coco_grasp_targets import CocoFrameNotReady
        if telemetry is None:
            return None
        if not isinstance(telemetry, dict) or telemetry.get('session_id') != expected_session_id:
            raise ValueError('AI识别结果不属于本次会话')
        if telemetry.get('state') == 'loading':
            return None
        try:
            candidates = fresh_targets(telemetry, now, expected_session_id, pick_offset_mm)[color]
        except CocoFrameNotReady:
            return None
    else:
        if isinstance(telemetry, dict) and 'detections' in telemetry:
            raise ValueError('AI抓取结果必须绑定当前识别会话')
        if not isinstance(telemetry, dict) or telemetry.get('state') in ('opening', None):
            return None
        stamp = telemetry.get('timestamp', -1e30)
        if not telemetry.get('fresh') or type(stamp) not in (int,float) or not 0 <= now-stamp <= 1.2:
            return None
        candidates = fresh_targets(telemetry, now, pick_offset_mm=pick_offset_mm)[color]
    for target in candidates:
        if any(row['color']==color and (
                target['track_id'] is not None and target['track_id']==row['track_id'] or
                math.dist(target['pixel_uv'],row['pixel_uv']) <= 20.)for row in consumed):
            continue
        return target
    return None


def execute(task, params):
    """Hold one peripheral lease for the whole batch, including final home."""
    params = dict(params, pick_offset_mm=checked_pick_offset(params.get('pick_offset_mm')))
    if params.get('clearance_confirmed') is not True:
        raise RuntimeError('请先确认运动区域安全')
    session = params['session']
    if not session.running or getattr(session, 'stopping', False):
        raise RuntimeError('请先开始识别')
    gripper = None
    if params.get('use_gripper'):
        from .car_peripherals import GripperLease, SimulatedGripper
        from .backend import SimulatedBackend, MemoryMappedBackend
        backend = task.controller.backend
        if isinstance(backend, SimulatedBackend):
            gripper = SimulatedGripper()
        elif isinstance(backend, MemoryMappedBackend):
            gripper = GripperLease(task.cancel)
        else:
            raise RuntimeError('自动夹爪需要本机MMIO控制服务')
    try:
        return _execute(task, params, gripper)
    finally:
        if gripper is not None:
            gripper.close()


def _execute(task, params, gripper=None):
    pick_offset = checked_pick_offset(params.get('pick_offset_mm'))
    if params.get('clearance_confirmed') is not True:
        raise RuntimeError('请先确认运动区域安全')
    session = params['session']
    control = params['control']
    publish = params.get('progress', lambda _event: None)
    clock = params.get('clock', time.monotonic)
    requested = quantities(params['requested'])
    if not session.running or getattr(session, 'stopping', False):
        raise RuntimeError('请先开始识别')
    session_id = session.session_id
    ai_session_id = session_id if getattr(session, 'vision_kind', None) == 'coco_six' else None
    if set(requested) - set(COLORS) and ai_session_id is None:
        raise ValueError('六类物品任务需要当前AI识别会话')
    initialization_began = time.monotonic()
    cart = task.cartesian
    cart.require()
    reference = copy.deepcopy(task._reference(range(1,7)))
    from .drawing import rotation
    initial_read_began = time.monotonic()
    actual, _ = cart.read_start()
    initial_read_seconds = time.monotonic()-initial_read_began
    pick_rotation = rotation('plus_y', k.forward(cart.to_model(actual))['rotation'])
    completed = {c: 0 for c in requested}
    consumed = []
    print('GRASP_BATCH_INITIALIZED', dict(seconds=time.monotonic()-initialization_began,
          read_start_seconds=initial_read_seconds), flush=True)

    def check():
        task._check()
        if gripper is not None:
            gripper.check()
        if control.stopped.is_set():
            raise RuntimeError('夹取任务已取消')
        if not session.running or getattr(session, 'stopping', False) or session.session_id != session_id:
            raise RuntimeError('识别会话已停止或变化，夹取任务取消')
        if task._reference(range(1,7)) != reference or not cart.ready():
            raise RuntimeError('零点或运动学参考已变化，夹取任务取消')

    def event(**values):
        publish(dict(completed=dict(completed), requested=requested, **values))

    last_planning_context_check = [0.0]
    planning_task_check = getattr(getattr(task, '_shelf_guard', None), 'planning_check', task._check)
    def planning_check():
        # Cancellation/session changes are checked on every callback. The
        # same frozen reference/configuration is also compared at most 20ms
        # apart during pure math and checked in full again before execution.
        planning_task_check()
        if control.stopped.is_set() or not session.running or getattr(session, 'stopping', False) or session.session_id!=session_id:
            check()
        now=time.monotonic()
        if now-last_planning_context_check[0]>=.02:
            check();last_planning_context_check[0]=now

    def prepare_target(target, actual=None, read_seconds=0.0, overlap_check=lambda:None):
        """Pure preparation; the only peripheral work here is position reads."""
        check();overlap_check()
        if actual is None:
            began = time.monotonic()
            actual, current_ref = cart.read_start()
            read_seconds = time.monotonic()-began
            if current_ref != reference:
                raise RuntimeError('零点参考已变化')
        start = cart.to_model(actual)
        context = copy.deepcopy(cart.continuous._context())
        steps = []
        def prepare_check():
            planning_check();overlap_check()
        timing = dict(read_start_seconds=read_seconds)
        try:
            began = time.monotonic()
            backend = getattr(getattr(task, 'controller', None), 'backend', None)
            from .backend import MemoryMappedBackend
            if isinstance(backend, MemoryMappedBackend):
                # The main task keeps the live safety checks while a warmed
                # math-only process builds the complete cycle. No actuator
                # objects or commands are passed to the child.
                from .grasp_transfer import prepare_cycle_remote
                steps, reports, math_timing = prepare_cycle_remote(start,
                    cycle_steps(target, pick_rotation), cart.bounds(),
                    cart.planning_hardware(JOINT_SPEED_DEG_S), prepare_check)
                prepare_cycle_lines(cart, start, steps, reference, prepare_check, reports=reports)
                elapsed = time.monotonic()-began
                timing.update(math_timing, planning_execution='isolated_process',
                    frames_seconds=elapsed-math_timing['preflight_seconds'],
                    planning_overhead_seconds=max(0., elapsed-math_timing['preflight_seconds']-math_timing['math_frames_seconds']))
            else:
                steps = preflight_cycle(start, cycle_steps(target, pick_rotation), cart.bounds(), prepare_check)
                timing['preflight_seconds'] = time.monotonic()-began
                began = time.monotonic()
                prepare_cycle_lines(cart, start, steps, reference, prepare_check)
                timing['frames_seconds'] = time.monotonic()-began
            check();overlap_check()
            if context != cart.continuous._context():
                raise RuntimeError('准备期间现场配置变化，未启动取放')
            return dict(target=copy.deepcopy(target), actual=list(actual), context=context,
                        reference=copy.deepcopy(reference), steps=steps, timing=timing)
        except BaseException:
            close_prepared_lines(steps)
            raise

    prefetched = None
    def discard_prefetch():
        nonlocal prefetched
        if prefetched is not None:
            close_prepared_lines(prefetched['steps'])
            prefetched = None

    index = 0
    waiting_label = None
    search_began = time.monotonic()
    try:
        while any(completed[c] < requested[c]for c in requested):
            control.checkpoint(check)
            color = next(c for c in requested if completed[c] < requested[c])
            target = next_target(copy.deepcopy(session.telemetry), color, consumed, clock(), ai_session_id, pick_offset)
            if target is None:
                discard_prefetch()
                label = '等待%s新目标，还需%d个；可暂停或停止' % (PICK_LABELS[color], requested[color]-completed[color])
                if label != waiting_label:
                    event(state='waiting', label=label, index=index)
                    waiting_label = label
                control.stopped.wait(TARGET_POLL_SECONDS)
                continue
            waiting_label = None
            target_selected_at = time.monotonic()
            timing = dict(index=index, color=color, boundary='first_moving_event_before_dispatch',
                          search_seconds=target_selected_at-search_began, prefetch_hit=False)
            event(state='planning', target=target, label='准备四段高速路径；取料向画面左侧偏置60mm，Z无补偿', index=index)
            read_began = time.monotonic()
            actual, current_ref = cart.read_start()
            timing['read_start_seconds'] = time.monotonic()-read_began
            if current_ref != reference:
                raise RuntimeError('零点参考已变化')
            prepared = None
            if prefetched is not None:
                old_target = prefetched['target']
                valid = (prefetched['reference'] == current_ref
                         and prefetched['context'] == cart.continuous._context()
                         and prefetched['actual'] == list(actual)
                         and old_target['color'] == target['color']
                         and old_target['track_id'] == target['track_id']
                         and math.dist(old_target['pixel_uv'], target['pixel_uv']) <= 20.
                         and math.dist(old_target['endpoint_xyz_mm'], target['endpoint_xyz_mm']) <= 2.)
                if valid:
                    prepared, prefetched = prefetched, None
                    target = prepared['target']
                    timing.update(prefetch_hit=True, preflight_seconds=0.0, frames_seconds=0.0,
                                  prefetched_timing=prepared['timing'])
                else:
                    discard_prefetch()
                    timing['prefetch_discarded'] = True
            if prepared is None:
                prepared = prepare_target(target, actual, timing['read_start_seconds'])
                timing.update(prepared['timing'])
            steps = prepared['steps']
            next_error = None
            try:
                print('GRASP_CYCLE_PREPARED',dict(seconds=round(timing['preflight_seconds']+timing['frames_seconds'],3),
                      steps=len(steps), prefetch_hit=timing['prefetch_hit'],
                      joint_speed_deg_s=JOINT_SPEED_DEG_S,line_speed_mm_s=LINE_SPEED_MM_S),flush=True)
                latest = _refresh_target(copy.deepcopy(session.telemetry), target, clock(), ai_session_id, pick_offset)
                if math.dist(latest['endpoint_xyz_mm'],target['endpoint_xyz_mm']) > 2.:
                    raise RuntimeError('规划期间目标移动超过2mm，请重新开始')
                check()
                if gripper is not None:
                    control.checkpoint(check)
                    event(state='gripper', label='取料前确认夹爪张开状态', index=index)
                    open_began = time.monotonic()
                    timing['open_reused'] = gripper.ensure_open(check)
                    timing['open_seconds'] = time.monotonic()-open_began
                    latest = _refresh_target(copy.deepcopy(session.telemetry), target, clock(), ai_session_id, pick_offset)
                    if math.dist(latest['endpoint_xyz_mm'],target['endpoint_xyz_mm']) > 2.:
                        raise RuntimeError('张开期间目标移动超过2mm，请重新开始')
                for step_index, step in enumerate(steps):
                    control.checkpoint(check)
                    if gripper is not None and step_index==0:
                        latest = _refresh_target(copy.deepcopy(session.telemetry), target, clock(), ai_session_id, pick_offset)
                        if math.dist(latest['endpoint_xyz_mm'],target['endpoint_xyz_mm']) > 2.:
                            raise RuntimeError('启动前目标移动超过2mm，请重新开始')
                    task.phase = '全自动取放定位'
                    task.message = step['label']
                    if step_index == 0:
                        timing['target_to_first_motion_seconds'] = time.monotonic()-target_selected_at
                        print('GRASP_START_LATENCY', timing, flush=True)
                    event(state='moving', target=target, step=step, label=step['label'], index=index)
                    check()
                    segment_began = time.monotonic()
                    report = step['prepared_report']
                    if report['execution_context'] != cart.continuous._context():
                        raise RuntimeError('现场配置变化，取消剩余取放动作')
                    cart.continuous.bind_preview(report, report['execution_context'])
                    cart.preview = report
                    try:
                        cart.continuous.execute(report, dict(line_request(step),mode=step['mode']))
                    finally:
                        cart.preview = None
                    print('GRASP_SEGMENT_FINISHED',dict(label=step['label'],mode=step['mode'],
                          seconds=round(time.monotonic()-segment_began,3)),flush=True)
                    check()
                    if gripper is not None and step['mode']=='L' and step['goal']['position_mm'][1]==330.:
                        event(state='gripper', label='取料点闭合夹爪，稳定1秒后持续保持至投放', index=index)
                        gripper.move('close', check)
                if gripper is not None:
                    control.checkpoint(check)
                    event(state='gripper', label='盒口上方张开夹爪并等待1秒', index=index)
                    future_completed = dict(completed)
                    future_completed[target['color']] += 1
                    future_consumed = consumed + [copy.deepcopy(target)]
                    def prepare_next(overlap_check):
                        nonlocal prefetched, next_error
                        began = time.monotonic()
                        try:
                            check();overlap_check()
                            future_color = next(c for c in requested if future_completed[c] < requested[c])
                            future_target = next_target(copy.deepcopy(session.telemetry), future_color,
                                                        future_consumed, clock(), ai_session_id, pick_offset)
                            if future_target is None:
                                print('GRASP_NEXT_PREPARED', dict(index=index+1, prepared=False,
                                      reason='no_current_target', seconds=time.monotonic()-began), flush=True)
                                return
                            prefetched = prepare_target(future_target, overlap_check=overlap_check)
                            print('GRASP_NEXT_PREPARED', dict(index=index+1, prepared=True,
                                  color=future_color, seconds=time.monotonic()-began,
                                  **prefetched['timing']), flush=True)
                        except Exception as error:
                            discard_prefetch()
                            next_error = error
                            print('GRASP_NEXT_PREPARED', dict(index=index+1, prepared=False,
                                  error=str(error), seconds=time.monotonic()-began), flush=True)
                    drop_began = time.monotonic()
                    overlap = getattr(gripper, 'open_and_prepare', None)
                    if overlap is not None and any(future_completed[c] < requested[c] for c in requested):
                        drop_timing = overlap(check, prepare_next)
                    else:
                        gripper.move('open', check)
                        drop_timing = dict(overlap_seconds=0.0, remaining_wait_seconds=time.monotonic()-drop_began)
                    print('GRASP_DROP_OPEN', dict(index=index, total_seconds=time.monotonic()-drop_began,
                          **drop_timing), flush=True)
            finally:
                close_prepared_lines(steps)
            completed[target['color']] += 1
            consumed.append(copy.deepcopy(target))
            event(state='cycle_complete', target=target,
                  label='本轮取放命令完成；实物抓取结果待核对' if gripper else '本轮定位完成；夹爪开合未启用', index=index)
            if next_error is not None:
                raise RuntimeError('本轮投放已完成；下一件预规划失败：'+str(next_error)) from next_error
            index += 1
            search_began = time.monotonic()
        control.checkpoint(check)
        task.phase = '取放完成，自动回0'
        task.message = '全部取放定位已完成，正在自动回0'
        event(state='homing', label=task.message, index=index)
        check()
        try:
            # Return to the established motor zeros; never redefine the zero or
            # start a second worker. Existing endpoint/stop checks remain active.
            task._move({node: 0.0 for node in range(1,7)},20.0,reference)
            check()
        except Exception as error:
            raise RuntimeError('取放定位已完成，但自动回0未完成：' + str(error)) from error
        task.message = '全部取放命令完成并已回0；实物结果待核对' if gripper else '全部取放定位完成并已回0；夹爪开合全部跳过'
        event(state='complete', label=task.message, index=index)
    finally:
        discard_prefetch()
