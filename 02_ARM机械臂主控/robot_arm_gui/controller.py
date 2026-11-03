"""Serialized, address-aware control of six X42S motors on one CAN bus."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os
from .angle_capture import AngleRangeCapture
from .joint_limits import JointLimits
import threading
import time
from typing import Any, Callable

from .backend import Backend
from .recorder import TestRecorder
from .protocol import (CanFrame, DEFAULT_ACCELERATION, MAX_ACCELERATION,
    MAX_SPEED_RPM, MIN_ACCELERATION, MIN_SPEED_RPM, motor_can_id,
    disable_frame, enable_frame, is_valid_motor_reply, option_query_frame,
    speed_frame, stop_frame)


@dataclass
class DiagnosticSnapshot:
    connection: str = "未连接"
    state: str = "未使能"
    motor: str = "未知"
    direction: str = "停止"
    speed_rpm: int = 30
    acceleration: int = DEFAULT_ACCELERATION
    last_command: str = "-"
    tx_count: int = 0
    rx_count: int = 0
    rx_id: str = "-"
    rx_dlc: int = 0
    rx_data: str = "-"
    f3_reply: str = "-"
    f6_reply: str = "-"
    error: str = "无"
    online: str = "未探测"
    firmware: str = "未知"
    motor_angle: float | None = None
    zero_valid: bool = False
    position_time: float = 0.0
    motor_flags: int = 0
    home_flags: int = 0
    enabled: bool = False
    moving: bool = False  # Includes motion whose stop has not been confirmed.


class MotorController:
    RESPONSE_TIMEOUT = 1.5

    def __init__(self, backend: Backend, *, snapshot_interval: float = 0.0) -> None:
        if snapshot_interval < 0:
            raise ValueError('snapshot_interval must be nonnegative')
        self.backend = backend
        self.nodes = {n: DiagnosticSnapshot(connection=backend.name) for n in range(1, 7)}
        self.selected_node = 1
        self.active_node: int | None = None
        self.on_snapshot: Callable[[dict[str, Any]], None] = lambda _s: None
        self._pending = None
        self._switching = False
        self._all_stopping = False
        self.all_stop_results: dict[int, str] = {}
        self._all_queue: list[int] = []
        self._all_stop_callbacks = []
        self._lock = threading.RLock()
        self._shutdown = threading.Event()
        # Production UI publication is coalesced on its own thread. Transport
        # dispatch and transaction completion only mark the display dirty.
        self._snapshot_interval = snapshot_interval
        self._snapshot_dirty = threading.Event()
        self._snapshot_thread = None
        self._thread = None
        self._connected = False
        self.zero_home = None
        self.motion_task = None
        self.zero_check_pending: set[int] = set()
        # F3 has no transaction ID or enable/disable echo. After a timeout,
        # do not risk accepting an old F3 as a new enable confirmation.
        self._f3_uncertain: set[int] = set()
        self._enabled_at: dict[int, float] = {}
        self.recorder = TestRecorder()
        zero_config = os.environ.get('F3P_JOINT_CONFIG') or str(Path.home()/'.config/f3p-control/zero-home.json')
        self.angle_capture = AngleRangeCapture(zero_config)
        self.joint_limits = JointLimits(zero_config)
        self.limit_notice = ''
        self._limit_node = None
        self._limit_reverse = False
        self._limit_rpm = 0
        self._limit_acceleration = 0
        self._pending_started = 0.0
        self._angle_capture_node = None
        self._angle_capture_first = None
        self._angle_capture_due = 0.0
        self._angle_capture_id = None
        self._angle_capture_retries = 0
        self._recorded_status = {}
        backend.on_frame = self._on_frame
        backend.on_error = self._on_error
        backend.on_status = self._on_status
        backend.on_dispatched = self._on_dispatched

    @property
    def snapshot(self) -> DiagnosticSnapshot:
        return self.nodes[self.selected_node]

    @property
    def _enabled(self) -> bool:
        return self.snapshot.enabled

    @property
    def _moving(self) -> bool:
        return self.active_node is not None or any(s.moving for s in self.nodes.values())

    def connect(self) -> None:
        if self._snapshot_interval and self._snapshot_thread is None:
            self._snapshot_thread = threading.Thread(target=self._display_loop,
                name='arm-display', daemon=True)
            self._snapshot_thread.start()
        self.backend.connect()
        self._connected = True
        for s in self.nodes.values():
            s.connection = f"{self.backend.name} · 已连接"
        self._request("读取选项", option_query_frame(self.selected_node))
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def _monitor(self) -> None:
        while not self._shutdown.wait(0.05):
            self.tick()

    def tick(self, now: float | None = None) -> None:
        with self._lock:
            if self._pending and (time.monotonic() if now is None else now) >= self._pending[3]:
                self._complete(False, "回复超时；状态未确认")
            self._limit_tick()
            capture = self.angle_capture.active()
            if not capture or self._moving or capture['capture_id'] != self._angle_capture_id:
                self._angle_capture_node = None
                self._angle_capture_first = None
                if not capture or capture['capture_id'] != self._angle_capture_id:
                    self.angle_capture.pending.clear()
                self._angle_capture_id = capture['capture_id'] if capture else None
            if (capture and not self._pending and not self._moving
                    and not self._switching and not self._all_stopping
                    and not (self.zero_home is not None and self.zero_home.busy)
                    and not (self.motion_task is not None and self.motion_task.busy)):
                from .protocol import read_frame
                if self._angle_capture_node is not None:
                    node = self._angle_capture_node
                    if self._angle_capture_first is None:
                        self._request('范围采集位置一', read_frame(0x36, node))
                    elif time.monotonic() >= self._angle_capture_due:
                        self._request('范围采集位置二', read_frame(0x36, node))
                elif self.angle_capture.pending:
                    node = self.angle_capture.pending.pop(0)
                    self._angle_capture_node = node
                    self._angle_capture_retries = 0
                    self._request('范围采集状态', read_frame(0x3A, node))

    def set_speed(self, speed_rpm: int) -> None:
        with self._lock:
            if not MIN_SPEED_RPM <= int(speed_rpm) <= MAX_SPEED_RPM:
                raise ValueError(f"速度必须在 {MIN_SPEED_RPM}–{MAX_SPEED_RPM} RPM")
            self.snapshot.speed_rpm = int(speed_rpm)
            self._publish()

    def set_acceleration(self, acceleration: int) -> None:
        with self._lock:
            if not MIN_ACCELERATION <= int(acceleration) <= MAX_ACCELERATION:
                raise ValueError("加速度必须在 0–255")
            self.snapshot.acceleration = int(acceleration)
            self._publish()

    def select_motor(self, node: int) -> None:
        motor_can_id(node)
        with self._lock:
            if self.motion_task is not None and self.motion_task.busy:
                raise RuntimeError('定位或示教任务正在进行，不能切换电机')
            if self.zero_home is not None and self.zero_home.busy:
                raise RuntimeError('零位操作中不能切换电机')
            self.recorder.record('select_request', node=node, previous_node=self.selected_node)
            if node == self.selected_node:
                self._guard()
                if self.active_node is None:
                    self._request("读取选项", option_query_frame(node))
                return
            if self._switching or self._all_stopping:
                raise RuntimeError("正在停止或切换，请等待结果")
            if self.active_node is None and (not self._pending or self._pending[1] != "停止"):
                # Finish an in-flight non-motion command before reusing the
                # hardware mailbox. Failure on an idle address does not trap
                # selection: there is no motion context to stop.
                if self._pending:
                    self._switching = True
                    def idle_selected(_ok: bool) -> None:
                        self._switching = False
                        self.selected_node = node
                        self._request("读取选项", option_query_frame(node))
                    self._pending[4].append(idle_selected)
                    self._publish()
                    return
                self.selected_node = node
                self._request("读取选项", option_query_frame(node))
                return
            self._switching = True
            old = self.active_node or self.selected_node
            def selected(ok: bool) -> None:
                self._switching = False
                if ok:
                    self.selected_node = node
                    self._request("读取选项", option_query_frame(node))
                self._publish()
            self._stop_node(old, selected)

    def enable(self) -> None:
        with self._lock:
            self._guard()
            if self.selected_node in self._f3_uncertain:
                raise RuntimeError("此前 F3 未确认，请核对电机状态后点击“手动解除 F3 锁定”")
            self._request("使能", enable_frame(self.selected_node))

    def disable(self) -> None:
        with self._lock:
            self._guard()
            node = self.selected_node
            if node in self._f3_uncertain:
                raise RuntimeError("此前 F3 未确认，请核对电机状态后点击“手动解除 F3 锁定”")
            def disabled(ok: bool) -> None:
                if ok:
                    self._request("失能", disable_frame(node))
            if self.active_node is not None:
                self._stop_node(self.active_node, disabled)
            else:
                self._request("失能", disable_frame(node))

    def clear_f3_lock(self, node: int | None = None) -> None:
        """Operator-confirmed local reset; sends no CAN command."""
        with self._lock:
            self._guard()
            node = self.selected_node if node is None else node
            if node != self.selected_node:
                raise RuntimeError("所选电机已改变，请重新核对")
            if self.active_node is not None or any(s.moving for s in self.nodes.values()):
                raise RuntimeError("仍有电机未确认停止，不能解除锁定")
            if node not in self._f3_uncertain:
                raise RuntimeError("当前电机没有 F3 锁定")
            self._f3_uncertain.remove(node)
            self.recorder.record('manual_f3_unlock', node=node, result='仅解除软件锁定')
            self._enabled_at.pop(node, None)
            s = self.nodes[node]
            s.enabled = False
            s.online = "未探测"
            s.state = "锁定已解除，待重新使能"
            s.error = "无"
            s.f3_reply = "-"
            self._publish()

    def _guard(self) -> None:
        if self.motion_task is not None and self.motion_task.busy:
            raise RuntimeError('定位或示教任务正在进行，请等待或全部停止')
        if self.zero_home is not None and self.zero_home.busy:
            raise RuntimeError('零位操作正在进行，请等待或点击停止')
        if self._pending or self._switching or self._all_stopping:
            raise RuntimeError("上一条命令尚未完成")
        if not self._connected:
            raise RuntimeError("通信未连接")

    def move_forward(self) -> None:
        self._move(False)

    def move_reverse(self) -> None:
        self._move(True)

    def _move(self, reverse: bool) -> None:
        with self._lock:
            self._guard()
            if self._moving:
                raise RuntimeError("活动电机尚未确认停止")
            s = self.snapshot
            if not s.enabled or s.online != "在线":
                raise RuntimeError("电机尚未使能或通信状态未确认")
            if time.monotonic() - self._enabled_at.get(self.selected_node, 0) < self.backend.enable_delay:
                raise RuntimeError("使能后请等待 500 ms 再运行")
            if self.joint_limits.error:
                raise RuntimeError(self.joint_limits.error)
            if self.selected_node in self.joint_limits.bounds:
                if not self.backend.supports_jog_deceleration:
                    raise RuntimeError('当前FPGA不支持运行中限位减速，请更新FPGA')
                if not s.zero_valid or s.firmware != 'Emm':
                    raise RuntimeError('零点或角度读取未就绪，不能进行限位点动')
                self.limit_notice = ''
                self.active_node = self.selected_node  # Release cancels preflight too.
                self._limit_node = self.selected_node
                self._limit_reverse = reverse
                self._limit_acceleration = s.acceleration
                self._limit_read(self.selected_node, starting=True)
                return
            self.active_node = self.selected_node
            s.moving = True
            s.direction = "反向" if reverse else "正向"
            self._request(s.direction, speed_frame(s.speed_rpm, reverse,
                s.acceleration, self.selected_node))

    def _limit_abort(self, node, message):
        print('JOINT_LIMIT_STOP', dict(node=node, motor_angle=self.nodes[node].motor_angle,
              rpm=self._limit_rpm, reason=message), flush=True)
        self.limit_notice = message
        self._limit_node = None
        self._stop_node(node)
        self._publish()

    def _limit_read(self, node, starting=False, coupled_checked=False):
        from .protocol import read_frame
        if self.joint_limits.coupled and node in (3,4) and not coupled_checked:
            other = 7-node
            def coupled_position(ok):
                state = self.nodes[other]
                if (not ok or not state.zero_valid or state.motor_angle is None
                        or state.firmware != 'Emm' or state.moving):
                    self._limit_abort(node, 'J3/J4 条件限位参考未确认，已请求停止')
                    return
                self._limit_read(node, starting, coupled_checked=True)
            def coupled_status(ok):
                state=self.nodes[other]
                if not ok or not state.zero_valid or state.motor_flags & 0x8C:
                    self._limit_abort(node, 'J3/J4 条件限位关联轴状态异常，已请求停止')
                    return
                self._request('条件限位读取关联角度', read_frame(0x36,other),
                              coupled_position, timeout=self.joint_limits.RESPONSE_TIMEOUT)
            self._request('条件限位读取关联状态', read_frame(0x3A,other),
                          coupled_status, timeout=self.joint_limits.RESPONSE_TIMEOUT)
            return
        def status_read(ok):
            s = self.nodes[node]
            if not ok or not s.zero_valid or not s.motor_flags & 1 or s.motor_flags & 0x8C:
                self._limit_abort(node, f'{node}号限位：状态或通信异常，已请求停止')
                return
            def position_read(ok):
                if not ok or s.motor_angle is None or not s.zero_valid:
                    self._limit_abort(node, f'{node}号限位：角度未确认，已请求停止')
                    return
                from .zero_home import RATIOS
                angles = {n:state.motor_angle/RATIOS[n] for n,state in self.nodes.items()
                          if state.motor_angle is not None and state.zero_valid}
                distance = self.joint_limits.distance(node, s.motor_angle, self._limit_reverse, angles)
                requested = s.speed_rpm if starting else self._limit_rpm
                ceiling = self.joint_limits.allowed_speed(node, distance, MAX_SPEED_RPM, self._limit_acceleration)
                # Start at the requested speed whenever it fits the stop budget.
                # Headroom is only needed when an active jog must slow down,
                # to avoid sending a new F6 for every 1-RPM change.
                budget = ceiling if starting else ceiling*9//10
                rpm = min(requested, max(1, budget)) if ceiling else 0
                if rpm == 0:
                    self._limit_abort(node, f'{node}号已到软件限位，可向范围内退回')
                    return
                if starting or rpm < self._limit_rpm:
                    if not starting and ceiling >= self._limit_rpm:
                        return
                    print('JOINT_LIMIT_SPEED', dict(node=node, motor_angle=s.motor_angle,
                          remaining_deg=distance, requested_rpm=s.speed_rpm, rpm=rpm,
                          previous_rpm=self._limit_rpm, starting=starting), flush=True)
                    self._limit_rpm = rpm
                    s.moving = True
                    s.direction = '反向' if self._limit_reverse else '正向'
                    self._request(s.direction if starting else '限位减速',
                        speed_frame(rpm,self._limit_reverse,self._limit_acceleration,node),
                        timeout=self.joint_limits.RESPONSE_TIMEOUT)
            self._request('限位读取角度',read_frame(0x36,node),position_read,
                          timeout=self.joint_limits.RESPONSE_TIMEOUT)
        self._request('限位读取状态',read_frame(0x3A,node),status_read,
                      timeout=self.joint_limits.RESPONSE_TIMEOUT)

    def _limit_tick(self):
        node = self._limit_node
        if node is None or self._pending or self._switching or self._all_stopping:
            return
        if self.zero_home is not None and self.zero_home.busy:
            return
        if self.nodes[node].moving:
            self._limit_read(node)

    def stop(self, callback: Callable[[bool], None] | None = None) -> None:
        with self._lock:
            if self.motion_task is not None and self.motion_task.busy:
                self.stop_all(callback)
                return
            if self.zero_home is not None:
                self.zero_home.cancel()
                if self.zero_home.parallel_active or sum(s.moving for s in self.nodes.values()) > 1:
                    self.stop_all(callback)
                    return
            if self._all_stopping:
                return
            self._stop_node(self.active_node or self.selected_node, callback)

    def release_motion(self, node: int) -> None:
        """Release belongs to the node captured at press, never new selection."""
        with self._lock:
            if self.active_node == node and not self._all_stopping:
                self._stop_node(node)

    def _stop_node(self, node: int, callback=None) -> None:
        if self._pending and self._pending[0] == node and self._pending[1] == "停止":
            if callback:
                self._pending[4].append(callback)
            return
        if self._pending:
            old_node, name, _frame, _deadline, _callbacks = self._pending
            if name in ("使能", "失能"):
                self._f3_uncertain.add(old_node)
                self.nodes[old_node].enabled = False
            self.recorder.record("command_cancelled",node=old_node,operation=name,reason="stop",f3_locked=old_node in self._f3_uncertain)
            self.nodes[old_node].state = "命令被停止取消"
            self._pending = None
        self._request("停止", stop_frame(node), callback)

    def stop_all(self, callback=None) -> None:
        with self._lock:
            continuous=getattr(getattr(self.motion_task,'cartesian',None),'continuous',None)
            if continuous is not None and continuous._trajectory_owned:
                def completed(ok):
                    self.all_stop_results={n:'已确认停止' if ok else '未确认停止' for n in self.nodes}
                    if callback:callback(ok)
                continuous.stop(completed)
                return
            if self.motion_task is not None:
                self.motion_task.cancel()
            if callback:
                self._all_stop_callbacks.append(callback)
            if self.zero_home is not None:
                self.zero_home.cancel()
            if self._all_stopping:
                return
            if self._switching:
                self._switching = False  # Cancel destination, retain old target.
                if self._pending:
                    self._pending[4].clear()
            self._all_stopping = True
            self.all_stop_results = {}
            first = self.active_node or self.selected_node
            self._all_queue = [first] + [n for n in self.nodes if n != first and self.nodes[n].moving] + [n for n in self.nodes if n != first and not self.nodes[n].moving]
            self._next_stop()

    def _next_stop(self) -> None:
        if not self._all_queue:
            self._all_stopping = False
            self._publish()
            callbacks, self._all_stop_callbacks = self._all_stop_callbacks, []
            for callback in callbacks:
                callback(all(result == "已确认停止" for result in self.all_stop_results.values()))
            return
        node = self._all_queue.pop(0)
        self.all_stop_results[node] = "等待确认"
        def finished(ok: bool) -> None:
            self.all_stop_results[node] = "已确认停止" if ok else "未确认"
            self._next_stop()
        self._stop_node(node, finished)

    def _request(self, name: str, frame: CanFrame, callback=None, timeout=None) -> None:
        if self._pending:
            raise RuntimeError("总线事务尚未完成")
        node = frame.can_id >> 8
        s = self.nodes[node]
        s.last_command = f"{name}: {frame.payload_text()}"
        s.tx_count += 1
        s.state = "停止确认中" if name == "停止" else f"{name}中"
        if name.startswith('限位读取') and s.moving:
            s.state = f'{s.direction}点动（{self._limit_rpm}RPM）'
        s.error = "无"
        self._pending_started = time.monotonic()
        self._pending = [node, name, frame, self._pending_started + (self.RESPONSE_TIMEOUT if timeout is None else timeout),
                         [callback] if callback else []]
        self.recorder.record('command_request', node=node, operation=name,
            can_id=f'0x{frame.can_id:08X}', extended=frame.extended, dlc=len(frame.data),
            data=frame.payload_text(), speed_rpm=s.speed_rpm, acceleration=s.acceleration,
            software_request_count=s.tx_count)
        self._publish()
        try:
            self.backend.send(frame)
        except Exception as exc:
            self._complete(False, str(exc))

    def _on_dispatched(self, frame: CanFrame) -> None:
        with self._lock:
            p = self._pending
            if p and p[0] == frame.can_id >> 8 and p[2].data[0] == 0xFD and frame == p[2]:
                self._complete(True, confirmation='transmitted')

    def _on_frame(self, frame: CanFrame) -> None:
        with self._lock:
            self.recorder.record('reply_received', node=frame.can_id >> 8,
                can_id=f'0x{frame.can_id:08X}', extended=frame.extended,
                dlc=len(frame.data), reply=frame.payload_text())
            if not is_valid_motor_reply(frame):
                return
            node = frame.can_id >> 8
            s = self.nodes[node]
            s.rx_count += 1
            s.rx_id, s.rx_dlc, s.rx_data = f"0x{frame.can_id:08X}", len(frame.data), frame.payload_text()
            if frame.data[0] == 0xF3:
                s.f3_reply = frame.payload_text()
            elif frame.data[0] == 0xF6:
                s.f6_reply = frame.payload_text()
            p = self._pending
            if not p or p[0] != node or p[2].data[0] != frame.data[0]:
                self._publish()
                return
            if frame.data[0] == 0x1A:
                if len(frame.data) not in (3, 4):
                    return
                flags = frame.data[-2]
                s.firmware = 'Emm' if flags & 2 else 'X'
                s.motor = "闭环 X42S" if frame.data[-2] & 4 else "X42S"
                self._complete(True)
            elif frame.data[0] == 0x36:
                if len(frame.data) != 7 or frame.data[1] not in (0, 1) or s.firmware == '未知':
                    return
                value = int.from_bytes(frame.data[2:6], 'big')
                s.motor_angle = value * (360.0 / 65536 if s.firmware == 'Emm' else 0.1) * (-1 if frame.data[1] else 1)
                s.position_time = time.monotonic()
                self._complete(True)
            elif frame.data[0] in (0x3A, 0x3B):
                if len(frame.data) != 3:
                    return
                if frame.data[0] == 0x3A:
                    s.motor_flags = frame.data[1]
                    if s.motor_flags & 0x80:
                        s.zero_valid = False
                else:
                    s.home_flags = frame.data[1]
                self._complete(True)
            else:
                self._complete(frame.data[1] == 2 or (frame.data[0] == 0xFD and frame.data[1] == 0x9F),
                    f"{frame.data[0]:02X} 状态异常 0x{frame.data[1]:02X}")

    def _complete(self, ok: bool, error: str = "", confirmation: str = 'reply') -> None:
        if not self._pending:
            return
        node, name, _frame, _deadline, callbacks = self._pending
        self.recorder.record('command_result', node=node, operation=name,
            result=('已发送，待位置核验' if confirmation == 'transmitted' else '应答成功') if ok else '失败或未确认', error='' if ok else error,
            response_ms=round((time.monotonic()-self._pending_started)*1000,3))
        self._pending = None
        s = self.nodes[node]
        if ok:
            s.online, s.error = "在线", "无"
            if name in ('使能', '读取选项'):
                self.zero_check_pending.add(node)
            elif _frame.data[0] == 0x3A:
                self.zero_check_pending.discard(node)
            if name == "使能":
                s.enabled, s.state = True, "已使能"
                self._enabled_at[node] = time.monotonic()
            elif name == "失能":
                s.enabled, s.moving, s.state = False, False, "已失能"
            elif name == "停止":
                if self._limit_node == node:
                    self._limit_node = None
                s.moving, s.direction = False, "停止"
                s.state = "已停止（保持使能）"
                if self.active_node == node:
                    self.active_node = next((n for n, state in self.nodes.items() if state.moving), None)
            elif name == "读取选项":
                s.state = "已使能" if s.enabled else "未使能"
            elif _frame.data[0] in (0x36, 0x3A, 0x3B, 0x0A, 0x50):
                s.state = '已使能' if s.enabled else '未使能'
            else:
                s.state = "运行中"
            if s.moving and s.direction == '回零':
                s.state = '回0中'
            elif s.moving and self._limit_node == node:
                s.state = f'{s.direction}点动（{self._limit_rpm}RPM）'
        else:
            s.zero_valid = False
            s.online, s.error = "未确认", error
            s.state = "停止未确认" if name == "停止" else "命令未确认"
            if name in ("使能", "失能"):
                s.enabled = False
                self._f3_uncertain.add(node)
            # A lost F6 reply is not evidence that the motor did not start.
        if ok and name == '停止':
            control = self.angle_capture.active()
            self._angle_capture_id = control['capture_id'] if control else None
            self._angle_capture_node = None
            self._angle_capture_first = None
            self.angle_capture.stopped(node)
        if ok and name == '范围采集位置一':
            self._angle_capture_first = s.motor_angle
            self._angle_capture_due = time.monotonic() + 0.15
        if ok and name == '范围采集位置二':
            retry = False
            try:
                control = self.angle_capture.active()
                if control and control['capture_id'] == self._angle_capture_id:
                    reason = self.angle_capture.sample(node, s, self._angle_capture_first, stopped_pair=True)
                    retry = reason == '连续两次角度尚未稳定' and self._angle_capture_retries < 5
            except Exception as exc:
                print('ANGLE_RANGE_RECORD_FAILURE', str(exc), flush=True)
            self._angle_capture_node = node if retry else None
            self._angle_capture_retries += 1
            self._angle_capture_first = None
        if not ok and name.startswith('范围采集'):
            self._angle_capture_node = None
            self._angle_capture_first = None
        if ok and _frame.data[0] == 0x0A:
            self.angle_capture.invalidate('采集期间零点改变，请重新开始测量')
        self._publish()
        for callback in callbacks:
            callback(ok)
        if not ok and _frame.data[0] in (0xF6, 0xFD) and self._pending is None:
            self._stop_node(node)

    def _on_error(self, message: str) -> None:
        with self._lock:
            if self.motion_task is not None:
                self.motion_task.cancel()
            for state in self.nodes.values():
                state.zero_valid = False
            if self.zero_home is not None:
                self.zero_home.cancel()
            self.recorder.record('transport_error', node=self.active_node or self.selected_node, error=message)
            if self._pending:
                self._complete(False, message)
            else:
                self.nodes[self.active_node or self.selected_node].error = message
                self._publish()

    def _on_status(self, status: dict[str, Any]) -> None:
        with self._lock:
            node = status.get("node")
            if node not in self.nodes:
                return
            s = self.nodes[node]
            changed = {key: status.get(key) for key in ('busy','enabled','moving','error','watchdog_stop','state_code','error_code','tx_count','rx_count','command_ack','can_flags')}
            if changed == self._recorded_status.get(node):
                return
            if changed != self._recorded_status.get(node):
                self._recorded_status[node] = changed
                self.recorder.record('hardware_status', node=node, **changed)
            if status.get('watchdog_stop') and self.zero_home is not None and self.zero_home.parallel_active:
                self.zero_home.cancel()
            if status.get('watchdog_stop') and self.motion_task is not None:
                self.motion_task.cancel()
            # Never infer stop from a busy/idle bit alone. Watchdog completion
            # is accepted only after hardware clears its conservative motion.
            if status.get("watchdog_stop") and not status.get("moving") and not status.get("busy"):
                s.moving, s.direction, s.state = False, "停止", "看门狗已停止"
                if self.active_node == node:
                    self.active_node = next((n for n, state in self.nodes.items() if state.moving), None)
            if status.get("error") and not status.get("busy"):
                s.error = f"PL 错误 0x{int(status.get('error_code', 0)):08X}"
            self._publish()

    def _display_loop(self) -> None:
        while not self._shutdown.is_set():
            if not self._snapshot_dirty.wait(.1):
                continue
            if self._shutdown.is_set():
                break
            with self._lock:
                self._snapshot_dirty.clear()
                payload = self._snapshot_payload()
            # A slow or failed display consumer cannot hold the CAN lock.
            try:
                self.on_snapshot(payload)
            except Exception as exc:
                print('DISPLAY_SNAPSHOT_ERROR', str(exc), flush=True)
            if self._shutdown.wait(self._snapshot_interval):
                break

    def _publish(self) -> None:
        if self._snapshot_interval:
            self._snapshot_dirty.set()
        else:
            self.on_snapshot(self._snapshot_payload())

    def _snapshot_payload(self) -> dict[str, Any]:
        # DiagnosticSnapshot contains only immutable scalar fields. Avoid
        # dataclasses.asdict's recursive deepcopy on every CAN reply.
        payload = vars(self.snapshot).copy()
        payload.update(selected_node=self.selected_node, active_node=self.active_node,
            joint_limits=dict(self.joint_limits.bounds), limit_notice=self.limit_notice,
            parallel_home=bool(self.zero_home is not None and self.zero_home.parallel_active),
            f3_locked=self.selected_node in self._f3_uncertain,
            busy=bool(self._pending or self._switching or self._all_stopping or (self.zero_home is not None and self.zero_home.busy) or (self.motion_task is not None and self.motion_task.busy)),
            nodes={n: vars(s).copy() for n, s in self.nodes.items()},
            all_stop_results=dict(self.all_stop_results))
        payload['recording'] = self.recorder.status(include_recent=False)
        payload['joint_task'] = self.motion_task.status() if self.motion_task is not None else None
        return payload

    def start_recording(self):
        self.recorder.start(dict(backend=self.backend.name, selected_node=self.selected_node,
            software='F3P recording v1', mmio_version='0x00020001' if 'MMIO' in self.backend.name else None))
        self._recorded_status.clear()
        self._publish()

    def start_recording_async(self, callback):
        with self._lock:
            self._recorded_status.clear()
            metadata = dict(backend=self.backend.name, selected_node=self.selected_node,
                software='F3P recording v2', mmio_version='0x00020001' if 'MMIO' in self.backend.name else None)
        def started(ok, error):
            if ok:
                with self._lock:
                    self._recorded_status.clear()
                    self._publish()
            callback(ok, error)
        self.recorder.start_async(metadata, started)

    def record_observation(self, item, result, note, node=None):
        if not self.recorder.status()['active']:
            raise RuntimeError('请先开始记录')
        if node is not None and node != self.selected_node:
            raise RuntimeError('目标电机已改变，请重新填写观察')
        self.recorder.record('observation', node=self.selected_node, item=item, observation=result, note=note)

    def close(self) -> None:
        if self.motion_task is not None:
            self.motion_task.cancel()
        if self._connected and self._moving:
            self.stop()
            # Keep transport/heartbeat alive briefly for the final FE reply.
            deadline = time.monotonic() + self.RESPONSE_TIMEOUT
            while self._moving and time.monotonic() < deadline:
                time.sleep(0.01)
        self._shutdown.set()
        self._snapshot_dirty.set()
        if self._snapshot_thread is not None and self._snapshot_thread is not threading.current_thread():
            self._snapshot_thread.join(.5)
        self.recorder.stop('program_exit')
        if self.recorder.path:
            self.recorder.done.wait(2)
        self._connected = False
        self.backend.close()
