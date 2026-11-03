"""Power-on position zero, manual correction, and parallel return to zero."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

from .protocol import (HOME_MAX_SPEEDS_RPM, home_zero_frame, mark_power_session_frame, option_query_frame,
                       read_frame, stop_frame, zero_frame)

RATIOS = {1: 2000 / 7, 2: 2000 / 7, 3: 250, 4: 42, 5: 22.4, 6: 1}
TARGET_JOINT_SPEED_DEG_S = 20.0
DEFAULT_SPEEDS = {node: min(HOME_MAX_SPEEDS_RPM[node], max(1, round(ratio * TARGET_JOINT_SPEED_DEG_S / 6)))
                  for node, ratio in RATIOS.items()}
HOME_TARGET_TIME = 5.0
HOME_ACCELERATIONS = {n: max(1, min(255, round(256 - 1 / ((25 * ratio / 6) * 50e-6))))
                      for n, ratio in RATIOS.items()}
HOME_VERIFY_RESERVE = 1.2


def planned_home_speed(node, motor_angle, base_speed, motion_seconds):
    """Aim for the requested duration, clamp speed, and allow longer moves."""
    home_zero_frame(node, base_speed, HOME_ACCELERATIONS[node])
    limit = HOME_MAX_SPEEDS_RPM[node]
    distance = abs(motor_angle)
    if distance <= MOTOR_ZERO_TOLERANCE:
        return base_speed
    acceleration = 1 / ((256 - HOME_ACCELERATIONS[node]) * 50e-6)
    budget = max(0.1, motion_seconds)
    discriminant = budget ** 2 - 4 * distance / (6 * acceleration)
    required = limit if discriminant < 0 else math.ceil(
        acceleration * (budget - math.sqrt(discriminant)) / 2)
    return min(limit, max(base_speed, required, 1))


MOTOR_ZERO_TOLERANCE = 0.8  # Motor shaft degrees, not claimed joint accuracy.


class ZeroHome:
    def __init__(self, controller, config_path=None, boot_id=None):
        self.controller = controller
        controller.zero_home = self
        self.busy = False
        self.message = '等待自动设置上电零点'
        self.error = ''
        self.cancelled = threading.Event()
        self._home_started = None
        self.parallel_active = False
        self.lock = threading.Lock()
        self.speeds = dict(DEFAULT_SPEEDS)
        self.order = list(RATIOS)
        self.config_path = Path(config_path or os.environ.get('F3P_JOINT_CONFIG') or
            (Path.home() / '.config' / 'f3p-control' / 'zero-home.json'))
        self.load_error = ''
        self.session_path = self.config_path.with_name(self.config_path.stem + '-session.json')
        # Linux boot ID distinguishes restarting the UI from restarting the board.
        self.boot_id = boot_id or (Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            if Path('/proc/sys/kernel/random/boot_id').exists() else str(uuid.uuid4()))
        self.session_nodes = set()
        self.reference_ids = {}
        self.recovery_results = {}
        try:
            session = json.loads(self.session_path.read_text(encoding='utf-8'))
            nodes = session['nodes']
            if session['boot_id'] == self.boot_id and session.get('backend') == controller.backend.name and isinstance(nodes, list) and all(type(n) is int and n in RATIOS for n in nodes):
                self.session_nodes = set(nodes)
                refs = session.get('reference_ids', {})
                if not isinstance(refs, dict):
                    refs = {}
                self.reference_ids = {n: refs[str(n)] if isinstance(refs.get(str(n)), str) and refs[str(n)] else uuid.uuid4().hex for n in nodes}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        try:
            if self.config_path.exists():
                data = json.loads(self.config_path.read_text(encoding='utf-8'))
                speeds = {int(k): v for k, v in data['speeds'].items()}
                if set(speeds) != set(RATIOS) or any(type(v) is not int or not 1 <= v <= HOME_MAX_SPEEDS_RPM[n] for n, v in speeds.items()):
                    raise ValueError('invalid home speeds')
                order = data.get('order', [])
                if order and (len(order) != 6 or any(type(v) is not int for v in order) or set(order) != set(RATIOS)):
                    raise ValueError('invalid home sequence')
                self.speeds, self.order = speeds, order or list(RATIOS)
        except Exception as exc:
            self.speeds, self.order = dict(DEFAULT_SPEEDS), list(RATIOS)
            self.load_error = str(exc)
            self.message = '关节配置读取失败，请重新设置：' + self.load_error

    def _save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        staged = self.config_path.with_suffix('.new')
        payload = dict(version=2, speeds=self.speeds, order=self.order,
                       ratios=RATIOS, zero_policy='power_on_position',
                       target_time_seconds=HOME_TARGET_TIME, accelerations=HOME_ACCELERATIONS,
                       joint_speed_deg_s={n: rpm * 6 / RATIOS[n] for n, rpm in self.speeds.items()})
        with staged.open('w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        staged.replace(self.config_path)

    def _save_session(self):
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        staged = self.session_path.with_suffix('.new')
        with staged.open('w', encoding='utf-8') as handle:
            for node in self.session_nodes:
                self.reference_ids.setdefault(node, uuid.uuid4().hex)
            json.dump(dict(boot_id=self.boot_id, backend=self.controller.backend.name,
                nodes=sorted(self.session_nodes), reference_ids={n: self.reference_ids[n]
                    for n in self.session_nodes}), handle)
            handle.flush()
            os.fsync(handle.fileno())
        staged.replace(self.session_path)

    def configure(self, order, node, speed):
        if len(order) != 6 or any(type(n) is not int for n in order) or set(order) != set(RATIOS):
            raise ValueError('回零顺序必须包含1～6，每个编号恰好一次')
        if node not in RATIOS or type(speed) is not int or not 1 <= speed <= HOME_MAX_SPEEDS_RPM[node]:
            raise ValueError('回零速度超出该关节允许范围')
        with self.controller._lock:
            if self.busy or self.controller._pending or self.controller.active_node is not None:
                raise RuntimeError('请先完成当前操作并停止电机')
            old_order, old_speeds = list(self.order), dict(self.speeds)
            self.order = list(order)
            self.speeds[node] = speed
            try:
                self._save()
            except Exception:
                self.order, self.speeds = old_order, old_speeds
                raise
            self.message = '并行回0下发顺序：' + ' → '.join(map(str, self.order))

    def apply_ratio_speeds(self):
        with self.controller._lock:
            if self.busy or self.controller._pending or self.controller.active_node is not None:
                raise RuntimeError('请先完成当前操作并停止电机')
            previous = dict(self.speeds)
            self.speeds = dict(DEFAULT_SPEEDS)
            try:
                self._save()
            except Exception:
                self.speeds = previous
                raise
            self.message = '已按减速比提速：关节约20°/秒；大角度和超过5秒继续回0'

    def cancel(self):
        if self.busy:
            self.cancelled.set()

    def start(self, operation, node, callback, *, cad_reference_confirmed=False):
        if operation not in ('confirm_cad_zero', 'restore_session', 'verify_session_node', 'verify_sessions', 'initialize', 'initialize_pending', 'recover_zero', 'refresh', 'zero', 'home', 'home_all', 'shutdown') or node not in RATIOS:
            raise ValueError('invalid zero operation')
        if operation=='confirm_cad_zero' and cad_reference_confirmed is not True:
            raise ValueError('请明确确认驱动器已供电且实物处于原 CAD 零位')
        c = self.controller
        with c._lock:
            c._guard()
            if c.active_node is not None or any(s.moving for s in c.nodes.values()):
                raise RuntimeError('请先停止电机并等待停止确认')
            if not c.backend.supports_zero_home:
                raise RuntimeError('板卡需要MMIO v3启动文件，当前版本不支持零位功能')
            if operation in ('home_all', 'shutdown'):
                if not getattr(c.backend, 'supports_parallel_home', False):
                    raise RuntimeError('并行回0需要MMIO 0x00030006启动文件')
                if not self.order:
                    raise RuntimeError('请先设置回零顺序')
                if not any(s.zero_valid and s.online == '在线' for s in c.nodes.values()):
                    raise RuntimeError('没有在线且零点有效的关节，无法回0')
            self.busy = True
            self.error = ''
            self.cancelled.clear()
            c._publish()
        def work():
            error = ''
            try:
                if operation == 'restore_session':
                    self._restore_session()
                elif operation == 'verify_session_node':
                    self._verify_session_node(node)
                elif operation == 'verify_sessions':
                    self._verify_sessions()
                elif operation == 'confirm_cad_zero':
                    self._confirm_cad_zero()
                elif operation == 'initialize':
                    self._initialize()
                elif operation == 'initialize_pending':
                    self._initialize(pending_only=True)
                elif operation == 'recover_zero':
                    self._recover_zero(node)
                elif operation == 'refresh':
                    self._refresh(node)
                elif operation == 'zero':
                    self._zero(node)
                elif operation == 'home':
                    self._home(node)
                elif operation == 'home_all':
                    self._home_all()
                else:
                    self._shutdown()
            except Exception as exc:
                error = str(exc)
                # A failed or cancelled move remains conservative until FE reply.
                with c._lock:
                    if self.parallel_active:
                        c.stop_all()
                    elif c.active_node is not None and not c._pending:
                        c._stop_node(c.active_node)
                self.message = error
                print('ZERO_HOME_FAILURE', json.dumps(dict(operation=operation, error=error,
                    recent=c.recorder.status().get('recent', [])[-16:]), ensure_ascii=False), flush=True)
            finally:
                with c._lock:
                    self.error = error
                    self.parallel_active = False
                    self.busy = False
                    c._publish()
                callback(not error, error)
        threading.Thread(target=work, daemon=True, name='f3p-zero-home').start()

    def _check(self):
        if self.cancelled.is_set():
            raise RuntimeError('回零操作已取消，关机未执行')

    def _request(self, name, frame):
        self._check()
        done = threading.Event()
        result = []
        def finished(ok):
            # Automatic FE recovery may replace the node's error immediately.
            result.append((ok, c.nodes[frame.can_id >> 8].error))
            done.set()
        c = self.controller
        with c._lock:
            self._check()
            if c._pending:
                raise RuntimeError('总线仍有未完成事务')
            c._request(name, frame, finished)
        deadline = time.monotonic() + c.RESPONSE_TIMEOUT + 1
        while not done.wait(0.02):
            self._check()
            if time.monotonic() > deadline:
                raise RuntimeError(name + '未确认')
        self._check()
        if not result[0][0]:
            raise RuntimeError(name + '失败：' + result[0][1])

    def _refresh(self, node):
        self._request('读取选项', option_query_frame(node))
        self._request('读取电机状态', read_frame(0x3A, node))
        self._request('读取位置', read_frame(0x36, node))
        self.message = f'{node}号关节角度已刷新'

    def pending_initialization(self):
        # A communication failure never authorizes replacing an established zero.
        return [n for n in RATIOS if n not in self.session_nodes
                and self.controller.nodes[n].online == '在线']

    def _restore_session(self):
        """Read-only verification after a GUI restart, never establish a new zero."""
        nodes=sorted(self.session_nodes)
        if not nodes:
            raise RuntimeError('当前启动没有已保存的零点会话，请在零点窗口核对；未自动清零')
        refs=dict(self.reference_ids)
        for n in nodes:
            self._check();self._refresh(n)
            s=self.controller.nodes[n]
            if s.motor_flags & 0x80:
                raise RuntimeError(f'{n}号电机电源会话已变化，不能沿用旧零点；请手动核对')
            if s.motor_flags & 0x0C or s.motor_angle is None:
                raise RuntimeError(f'{n}号状态异常，零点恢复未通过')
        if refs!=self.reference_ids or set(nodes)!=self.session_nodes:
            raise RuntimeError('核对期间零点会话改变')
        for n in nodes:self.controller.nodes[n].zero_valid=True
        self.message='已只读核验并恢复保存的零点会话；未清零、未运动'

    def _recover_zero(self, node):
        s = self.controller.nodes[node]
        self._request('读取电机状态', read_frame(0x3A, node))
        if node not in self.session_nodes or s.motor_flags & 0x80:
            # A confirmed motor power cycle starts a new motor zero session.
            self._zero(node)
        elif not s.zero_valid:
            # A timeout alone does not replace the existing motor origin.
            self._refresh(node)
            if s.motor_flags & 0x80:
                self._zero(node)
            else:
                s.zero_valid = True
        self.message = ('六关节零点已就绪，可一键回0'
                        if all(s.zero_valid for s in self.controller.nodes.values())
                        else f'{node}号零点已恢复')

    def _verify_session_node(self,node):
        """Recover feedback validity only; never replace a motor origin."""
        reference=self.reference_ids.get(node)
        if node not in self.session_nodes or not reference:
            raise RuntimeError('本次启动无有效零点记录，不能只读恢复')
        self._refresh(node)
        s=self.controller.nodes[node]
        if s.motor_flags & 0x80:raise RuntimeError('电源会话已变化，不能沿用旧零点')
        if s.motor_flags & 0x0C:raise RuntimeError('驱动保护未解除，状态 0x%02X；请检查故障原因'%s.motor_flags)
        if s.motor_angle is None or s.firmware!='Emm':
            raise RuntimeError('状态或位置未确认，保持零点未就绪')
        if node not in self.session_nodes or self.reference_ids.get(node)!=reference:
            raise RuntimeError('读取期间零点记录发生变化')
        s.zero_valid=True
        self.message=f'{node}号原零点与位置已只读核验；未清零、未运动'

    def _verify_sessions(self):
        """Diagnose every axis independently without changing saved origins."""
        self.recovery_results={}
        for node in RATIOS:
            self._check()
            s=self.controller.nodes[node]
            s.zero_valid=False
            try:
                self._verify_session_node(node)
            except Exception as exc:
                self._check()
                s.zero_valid=False
                self.recovery_results[node]=dict(ok=False,error=str(exc))
            else:
                self.recovery_results[node]=dict(ok=True,error='',angle_deg=s.motor_angle/RATIOS[node])
            self.controller._publish()
        failures=['J%d：%s'%(n,v['error']) for n,v in self.recovery_results.items() if not v['ok']]
        if failures:raise RuntimeError('六轴恢复部分未通过；'+'；'.join(failures))
        self.message='六轴原零点和角度已核验，未清零、未使能、未运动'

    def _confirm_cad_zero(self):
        """Human-confirmed CAD posture; all-axis precheck before any zero write."""
        for n in RATIOS:
            self._check();self._refresh(n)
            s=self.controller.nodes[n]
            if s.firmware!='Emm' or s.motor_angle is None or s.motor_flags & 0x0C:
                raise RuntimeError('J%d 通信、位置或驱动保护未通过，未建立新零位'%n)
        for n in RATIOS:
            self._check();self._zero(n)
        self.message='已按人工确认的 CAD 姿态建立六轴零位；未使能、未运动'

    def _initialize(self, pending_only=False):
        failures = []
        for node in (self.pending_initialization() if pending_only else RATIOS):
            self._check()
            try:
                self.message = f'正在初始化{node}号上电零点'
                self._refresh(node)
                s = self.controller.nodes[node]
                if node in self.session_nodes and not s.motor_flags & 0x80:
                    s.zero_valid = True
                else:
                    self._zero(node)
            except Exception as exc:
                self._check()
                self.controller.nodes[node].zero_valid = False
                failures.append(f'{node}号：{exc}')
        if failures:
            raise RuntimeError('上电零点初始化未完成；' + '；'.join(failures))
        self.message = '六关节上电零点已就绪，可一键回0'

    def _zero(self, node):
        s = self.controller.nodes[node]
        s.zero_valid = False
        self.session_nodes.discard(node)
        self.reference_ids.pop(node, None)
        self._save_session()  # An interrupted correction must not restore the old validity.
        self._request('停止', stop_frame(node))
        self._refresh(node)
        self._request('当前位置清零', zero_frame(node))
        self._request('标记本次电源会话', mark_power_session_frame(node))
        self._request('读取电机状态', read_frame(0x3A, node))
        self._request('读取位置', read_frame(0x36, node))
        if s.motor_flags & 0x80 or s.motor_angle is None or abs(s.motor_angle) > MOTOR_ZERO_TOLERANCE:
            raise RuntimeError('清零后的实际位置或电源状态未确认')
        self.session_nodes.add(node)
        self.reference_ids[node] = uuid.uuid4().hex
        try:
            self._save_session()
        except Exception:
            self.session_nodes.discard(node)
            self.reference_ids.pop(node, None)
            raise
        s.zero_valid = True
        self.controller.recorder.record('zero_confirmed', node=node, motor_angle=s.motor_angle, ratio=RATIOS[node])
        self.message = f'{node}号当前位置已设为0°'

    def _home(self, node):
        started = time.monotonic()
        self._home_started = started
        try:
            self._home_move(node)
            print('HOME_TIME_VERIFIED', dict(node=node, elapsed=round(time.monotonic()-started, 3), target=HOME_TARGET_TIME), flush=True)
        finally:
            self._home_started = None

    def _prepare_home(self, node):
        c = self.controller
        s = c.nodes[node]
        # Validate before enable or motion, including direct in-memory changes.
        home_zero_frame(node, self.speeds[node], 50)
        if not s.zero_valid:
            raise RuntimeError(f'{node}号零位未确认')
        self._refresh(node)
        if not s.zero_valid:
            raise RuntimeError(f'{node}号发生过掉电，请重新对齐设零')
        if s.firmware != 'Emm':
            raise RuntimeError(f'{node}号不是已支持的Emm固件，回零已取消')
        self._request('读取回零及保护状态', read_frame(0x3B, node))
        if s.home_flags & 0x3F != 3 or s.motor_flags & 0x0C:
            raise RuntimeError(f'{node}号编码器、保护或回零状态异常')
        if node in c._f3_uncertain:
            raise RuntimeError(f'{node}号F3状态未确认')
        if not s.enabled:
            from .protocol import enable_frame
            self._request('使能', enable_frame(node))
        # Existing enable-to-motion gap is retained even when reply arrived early.
        delay = max(0, c.backend.enable_delay - (time.monotonic() - c._enabled_at.get(node, 0)))
        if self.cancelled.wait(delay):
            self._check()
        self._check()
        actual_speed = planned_home_speed(node, s.motor_angle, self.speeds[node],
            HOME_TARGET_TIME-HOME_VERIFY_RESERVE)
        return actual_speed, s.motor_angle

    def _dispatch_home(self, node, actual_speed, start_angle):
        c = self.controller
        s = c.nodes[node]
        self.message = f'正在让{node}号回0，电机轴{actual_speed} RPM；超过5秒继续等待到位'
        print('HOME_POSITION_START', dict(node=node, motor_angle=s.motor_angle,
            motor_flags=hex(s.motor_flags), home_flags=hex(s.home_flags),
            speed=actual_speed, acceleration=HOME_ACCELERATIONS[node], target_time=HOME_TARGET_TIME), flush=True)
        with c._lock:
            self._check()
            if c.active_node is None:
                c.active_node = node
            s.moving = True
            s.direction = '回零'
        self._request('绝对位置回0', home_zero_frame(node, actual_speed, HOME_ACCELERATIONS[node]))
        print('HOME_POSITION_DISPATCHED', dict(node=node, reply=s.rx_data), flush=True)
        acceleration_rate = 1 / ((256-HOME_ACCELERATIONS[node])*50e-6)
        expected_motion = abs(start_angle)/(actual_speed*6) + actual_speed/acceleration_rate
        # Fault timeout scales with travel; 5 seconds is only a speed target.
        deadline = time.monotonic() + expected_motion * 1.5 + 15
        return deadline

    def _home_move(self, node):
        c = self.controller
        s = c.nodes[node]
        speed, angle = self._prepare_home(node)
        deadline = self._dispatch_home(node, speed, angle)
        stable = 0
        next_trace = 0
        while time.monotonic() < deadline:
            self._request('读取回零及保护状态', read_frame(0x3B, node))
            self._request('读取电机状态', read_frame(0x3A, node))
            self._request('读取位置', read_frame(0x36, node))
            if time.monotonic() >= next_trace:
                print('HOME_POSITION_READBACK', dict(node=node, motor_angle=s.motor_angle,
                    motor_flags=hex(s.motor_flags), home_flags=hex(s.home_flags),
                    reply=s.rx_data), flush=True)
                next_trace = time.monotonic() + 1
            if not s.zero_valid or s.home_flags & 0x3F != 3 or s.motor_flags & 0x0C:
                raise RuntimeError(f'{node}号电源、编码器或保护状态异常，回零已取消')
            stable = stable + 1 if s.motor_flags & 2 and abs(s.motor_angle) <= MOTOR_ZERO_TOLERANCE else 0
            if stable >= 3:
                self._request('停止', stop_frame(node))
                self._request('读取位置', read_frame(0x36, node))
                if abs(s.motor_angle) > MOTOR_ZERO_TOLERANCE:
                    raise RuntimeError(f'{node}号停止后偏离零点')
                self.message = f'{node}号已回0并确认停止'
                c.recorder.record('home_verified', node=node, motor_angle=s.motor_angle)
                return
            if self.cancelled.wait(0.05):
                self._check()
        raise RuntimeError(f'{node}号长时间未到位（电机轴{s.motor_angle:.3f}°），回0故障停止')

    def _home_all(self, require_all=False):
        # Select and freshly check participants before the first motion.
        # Both one-click home and shutdown may skip unavailable nodes.
        targets = []
        skipped = {}
        for node in self.order:
            self._check()
            s = self.controller.nodes[node]
            if not require_all and (not s.zero_valid or s.online != '在线'):
                skipped[node] = '离线或零点未就绪'
                continue
            try:
                self._refresh(node)
                self._request('读取回零及保护状态', read_frame(0x3B, node))
            except Exception as exc:
                self._check()
                if require_all or self.controller._pending:
                    raise
                skipped[node] = str(exc)
                continue
            s = self.controller.nodes[node]
            if not s.zero_valid and not require_all:
                skipped[node] = '掉电后零点失效'
                continue
            if not s.zero_valid or s.firmware != 'Emm' or s.home_flags & 0x3F != 3 or s.motor_flags & 0x0C or node in self.controller._f3_uncertain:
                raise RuntimeError(f'{node}号零点、电源或保护状态异常，全部回0已取消')
            targets.append(node)
        self.controller.recorder.record('home_all_selection', targets=targets, skipped=skipped, require_all=require_all)
        if not targets:
            raise RuntimeError('没有可回0的关节；已跳过' + '、'.join(map(str, skipped)) + '号')
        plans = {node: self._prepare_home(node) for node in targets}
        self.parallel_active = True
        deadlines, started, stable = {}, {}, {node: 0 for node in targets}
        remaining = set(targets)
        for node in targets:
            self._check()
            started[node] = time.monotonic()
            deadlines[node] = self._dispatch_home(node, *plans[node])
        self.controller.recorder.record('parallel_home_dispatched', targets=targets)
        print('PARALLEL_HOME_DISPATCHED', dict(targets=targets,
            launch_span=round(max(started.values())-min(started.values()), 3)), flush=True)
        next_trace = {node: 0 for node in targets}
        while remaining:
            for node in targets:
                if node not in remaining:
                    continue
                self._check()
                s = self.controller.nodes[node]
                self._request('读取回零及保护状态', read_frame(0x3B, node))
                self._request('读取电机状态', read_frame(0x3A, node))
                self._request('读取位置', read_frame(0x36, node))
                now = time.monotonic()
                if now >= next_trace[node]:
                    print('PARALLEL_HOME_READBACK', dict(node=node, motor_angle=s.motor_angle,
                        motor_flags=hex(s.motor_flags), home_flags=hex(s.home_flags)), flush=True)
                    next_trace[node] = now+1
                if not s.zero_valid or s.home_flags & 0x3F != 3 or s.motor_flags & 0x0C:
                    raise RuntimeError(f'{node}号电源、编码器或保护异常，全部回0停止')
                stable[node] = stable[node]+1 if s.motor_flags & 2 and abs(s.motor_angle) <= MOTOR_ZERO_TOLERANCE else 0
                if stable[node] >= 3:
                    self._request('停止', stop_frame(node))
                    self._request('读取位置', read_frame(0x36, node))
                    if abs(s.motor_angle) > MOTOR_ZERO_TOLERANCE:
                        raise RuntimeError(f'{node}号停止后偏离零点，全部回0停止')
                    remaining.remove(node)
                    with self.controller._lock:
                        self.controller.active_node = next((n for n in targets if self.controller.nodes[n].moving), None)
                    self.controller.recorder.record('home_verified', node=node, motor_angle=s.motor_angle, parallel=True)
                    print('HOME_TIME_VERIFIED', dict(node=node,
                        elapsed=round(time.monotonic()-started[node], 3), target=HOME_TARGET_TIME, parallel=True), flush=True)
                elif now >= deadlines[node]:
                    raise RuntimeError(f'{node}号长时间未到位，全部回0故障停止')
            self.message = '并行回0：等待' + '、'.join(map(str, sorted(remaining))) + '号到位；超过5秒继续'
            if remaining and self.cancelled.wait(0.05):
                self._check()
        # Recheck every participant after the last joint reaches zero.
        for node in targets:
            self._refresh(node)
            self._request('读取回零及保护状态', read_frame(0x3B, node))
            s = self.controller.nodes[node]
            if not s.zero_valid or s.home_flags & 0x3F != 3 or s.motor_flags & 0x0C or abs(s.motor_angle) > MOTOR_ZERO_TOLERANCE:
                raise RuntimeError(f'{node}号最终零位检查失败，关机已取消')
        self._check()
        self.message = '、'.join(map(str, targets)) + '号已回0'
        if skipped:
            self.message += '；跳过' + '、'.join(map(str, skipped)) + '号（离线或零点无效）'
        self.controller.recorder.record('home_all_verified', targets=targets, skipped=skipped)

    def _shutdown(self):
        self._home_all()
        from .poweroff import finish_poweroff
        finish_poweroff(self.controller, preflight=self._check)
        self.message = '参与关节已回0，系统正在关机'
