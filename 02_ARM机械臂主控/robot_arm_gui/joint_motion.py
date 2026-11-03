"""Explicit joint targets and reference-bound teaching on the existing CAN owner.

All bus operations use the controller's transaction engine. No secondary MMIO
connection is opened, and no input-pulse scale is assumed for a live backend.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import threading
import time

from .backend import SimulatedBackend
from .protocol import HOME_MAX_SPEEDS_RPM, absolute_position_frame, option_query_frame, read_frame, stop_frame
from .zero_home import RATIOS, HOME_ACCELERATIONS, MOTOR_ZERO_TOLERANCE, ZeroHome

AUTO_NODES = (1, 2, 3, 4, 5, 6)
LEGACY_NODES = (1, 2, 3, 4, 5)


def atomic_json(path, payload):
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix('.new')
    with staged.open('w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    staged.replace(path)


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def motor_pulses_from_settings(step_angle, microsteps):
    """Calculate ordinary input pulses; never infer the live driver's settings."""
    if type(step_angle) not in (int, float) or step_angle not in (0.9, 1.8):
        raise ValueError('请选择电机步距角 1.8° 或 0.9°')
    if type(microsteps) is not int or not 1 <= microsteps <= 256:
        raise ValueError('驱动细分须为 1～256 的整数')
    return round(360 / step_angle) * microsteps


def parse_motor_pulses(text, node):
    value = text.strip()
    if not value.isdecimal() or not 1 <= int(value) <= 1000000:
        raise ValueError(f'J{node}：请填写 1～1000000 的整数电机脉冲数/圈')
    return int(value)


class JointMotion:
    MAX_POINTS = 50
    POSITION_MAX_AGE = .1
    INPUT_EPSILON = 1e-9

    def __init__(self, controller):
        if controller.zero_home is None:
            raise RuntimeError('先创建零点管理器')
        self.controller = controller
        controller.motion_task = self
        self.busy = False
        self.phase = '空闲'
        self.message = '定位与示教就绪'
        self.error = ''
        self.cancelled = threading.Event()
        self.done = threading.Event()
        self.done.set()
        self.thread = None
        self.targets = {}
        self.plans = {}
        self.points = []
        self.revision = 0
        self.current_point = 0
        self.total_points = 0
        self.last_timing = {}
        self.blend_preview = None
        self._segment_communication = None
        self.path = controller.zero_home.config_path.with_name('joint-position.json')
        self.program_path = self.path.parent/'teaching-programs'/'basic-joint-program.json'
        self.pulses_per_rev = {}
        self.config_error = ''
        self.program_error = ''
        if isinstance(controller.backend, SimulatedBackend):
            self.pulses_per_rev = {n: 3200 for n in AUTO_NODES}
        else:
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('schema_version') != 1 or data.get('operator_confirmed') is not True:
                    raise ValueError('定位当量未确认')
                self.pulses_per_rev = self._scales(data['pulses_per_motor_rev'])
            except FileNotFoundError:
                pass
            except Exception as exc:
                self.config_error = str(exc)
        try:
            if self.program_path.exists():
                data = json.loads(self.program_path.read_text(encoding='utf-8'))
                if data.get('schema_version') != 1 or not isinstance(data.get('points'), list) or len(data['points']) > self.MAX_POINTS:
                    raise ValueError('示教文件格式无效')
                for p in data['points']:
                    self._validate_point(p)
                self.points = data['points']
        except Exception as exc:
            self.program_error = str(exc)
        from .cartesian_motion import CartesianMotion
        self.cartesian = CartesianMotion(self)
        from .ai_arm_control import ArmActions
        self.ai_actions = ArmActions(self)

    def status(self):
        return dict(busy=self.busy, phase=self.phase, message=self.message,
            error=self.error, targets=dict(self.targets), plans=copy.deepcopy(self.plans),
            revision=self.revision, points=copy.deepcopy(self.points),
            current_point=self.current_point, total_points=self.total_points,
            last_timing=copy.deepcopy(self.last_timing),
            available=bool(self.controller.backend.supports_position_targets),
            position_target_nodes=list(self.controller.backend.position_target_nodes),
            pulses_per_rev=dict(self.pulses_per_rev), config_error=self.config_error,
            program_error=self.program_error)

    @staticmethod
    def _scales(values):
        if not isinstance(values, dict):
            raise ValueError('定位当量必须为关节映射')
        scales = {int(n): value for n, value in values.items()}
        if set(scales) not in (set(AUTO_NODES), set(LEGACY_NODES)) or any(type(v) is not int or not 1 <= v <= 1000000 for v in scales.values()):
            raise ValueError('每个电机有效输入脉冲数/圈须为1～1000000整数')
        return scales

    @staticmethod
    def _validate_point(point):
        if not isinstance(point, dict) or not isinstance(point.get('name'), str) or not 1 <= len(point['name']) <= 64:
            raise ValueError('示教点名称无效')
        targets = point.get('angles_deg')
        if not isinstance(targets, dict) or set(targets) not in ({str(n) for n in AUTO_NODES}, {str(n) for n in LEGACY_NODES}) or any(not finite_number(v) for v in targets.values()):
            raise ValueError('示教点必须包含五轴或六轴有限角度')
        if not finite_number(point.get('dwell_seconds')) or not 0 <= point['dwell_seconds'] <= 30:
            raise ValueError('停留时间须为0～30秒')
        if not finite_number(point.get('speed_deg_s')) or not 1 <= point['speed_deg_s'] <= 20:
            raise ValueError('关节速度须为1～20°/秒')
        if not isinstance(point.get('reference'), dict):
            raise ValueError('示教点缺少零点参考')
        motion=point.get('motion')
        if motion is not None:
            if not isinstance(motion,dict) or motion.get('mode') not in ('J','L','C') or motion.get('orientation') not in ('hold','interpolate'):
                raise ValueError('示教轨迹类型或方向策略无效')
            if not finite_number(motion.get('tcp_speed_mm_s')) or not 0<motion['tcp_speed_mm_s']<=1000:
                raise ValueError('末端速度须大于0且不超过1000 mm/s')
            if motion['mode']=='C':
                from .kinematics import finite_vector
                finite_vector(motion.get('via_mm'),3)

    def cancel(self):
        if hasattr(self,'ai_actions'):self.ai_actions.invalidate()
        if hasattr(self,'cartesian'):self.cartesian.prepared.invalidate()
        if self.busy:
            self.cancelled.set()
        elif hasattr(self,'cartesian'):
            self.cartesian.clear_preview()

    def _check(self):
        shelf_guard=getattr(self,'_shelf_guard',None)
        if shelf_guard is not None:shelf_guard()
        if self.cancelled.is_set():
            raise RuntimeError('任务已取消')
        lease=getattr(self.cartesian,'jog_lease',None)
        if lease is not None:lease.check()

    def _request(self, name, frame):
        # Reuse the same bounded, cancellable transaction wait as zero/home.
        started = time.monotonic()
        try:
            return ZeroHome._request(self, name, frame)
        finally:
            if self._segment_communication is not None:
                key = f'{frame.data[0]:02X}'
                item = self._segment_communication.setdefault(key, dict(count=0, seconds=0.0))
                item['count'] += 1
                item['seconds'] += time.monotonic()-started

    def _reference(self, nodes):
        home = self.controller.zero_home
        if any(n not in home.session_nodes or n not in home.reference_ids or not self.controller.nodes[n].zero_valid for n in nodes):
            raise RuntimeError('零点参考未建立，请先完成零点初始化')
        return dict(boot_id=home.boot_id, backend=self.controller.backend.name,
            reference_ids={str(n): home.reference_ids[n] for n in nodes},
            ratios={str(n): RATIOS[n] for n in nodes},
            bounds={str(n): list(self.controller.joint_limits.bounds.get(n, ())) for n in nodes},
            pulses_per_rev={str(n): self.pulses_per_rev.get(n) for n in nodes})

    def point_valid(self, point):
        try:
            self._validate_point(point)
            return point['reference'] == self._reference([int(n) for n in point['angles_deg']])
        except Exception:
            return False

    def _read(self, node, require_enabled=True, position_only=False):
        # Motion reads position only; explicit refresh/capture still read health.
        if self.controller.nodes[node].firmware != 'Emm':
            self._request('读取选项', option_query_frame(node))
        if not position_only:self._read_state(node)
        self._request('定位读取位置', read_frame(0x36, node))
        self._healthy(node, require_enabled=require_enabled)

    def _read_state(self, node):
        self._request('定位读取电机状态', read_frame(0x3A, node))
        self._request('定位读取保护状态', read_frame(0x3B, node))

    def _read_completed(self, node):
        # Motion queries position only; health flags are last confirmed values.
        self._request('定位读取位置', read_frame(0x36, node))
        self._healthy(node)

    def _read_recent(self, node):
        # Reuse replies only inside this motion task, never across manual runs.
        if time.monotonic()-self.controller.nodes[node].position_time >= self.POSITION_MAX_AGE:
            self._request('定位读取位置', read_frame(0x36,node))
        self._healthy(node)

    def _read_running(self, node):
        self._request('定位读取位置', read_frame(0x36,node))
        self._healthy(node)

    def _healthy(self, node, require_enabled=True):
        s = self.controller.nodes[node]
        if (not s.zero_valid or s.firmware != 'Emm' or s.online != '在线'
                or (require_enabled and not s.motor_flags & 1) or s.motor_flags & 0x8C
                or s.home_flags & 0x3F != 3 or s.motor_angle is None
                or node in self.controller._f3_uncertain):
            raise RuntimeError(f'{node}号零点、电源、编码器、使能或保护未确认')
        if self.controller.joint_limits.error or (node != 6 and node not in self.controller.joint_limits.bounds):
            raise RuntimeError(f'{node}号软件限位未配置或无效')
        bounds = self.controller.joint_limits.bounds.get(node)
        # Driver feedback can straddle an endpoint by encoder quantization or
        # the existing 0.8 motor-degree arrival tolerance. Targets stay inside.
        if bounds and not self.feedback_within_bounds(node,s.motor_angle/RATIOS[node]):
            raise RuntimeError(f'{node}号当前角度超范围，请先回0或向内退回')

    def effective_bounds(self,node):
        angles={n:s.motor_angle/RATIOS[n] for n,s in self.controller.nodes.items()
                if s.motor_angle is not None and s.zero_valid}
        return self.controller.joint_limits.effective_bounds(node,angles)

    def feedback_within_bounds(self,node,angle):
        bounds=self.effective_bounds(node)
        margin=(MOTOR_ZERO_TOLERANCE+360/65536)/RATIOS[node]
        return not bounds or bounds[0]-margin<=angle<=bounds[1]+margin

    def _input(self, targets, speed):
        if not isinstance(targets, dict) or not targets or any(type(n) is not int or n not in AUTO_NODES for n in targets):
            raise ValueError('请选择1～6号参与关节')
        if not finite_number(speed) or not 1 <= speed <= 20:
            raise ValueError('关节速度须为1～20°/秒')
        normalized={}
        for n, angle in targets.items():
            bounds = self.controller.joint_limits.bounds.get(n)
            if n==4 and self.controller.joint_limits.coupled and finite_number(angle) and not any(abs(angle-v)<=self.INPUT_EPSILON for v in bounds):bounds=None
            if not finite_number(angle) or (not bounds and n != 6 and not (n==4 and self.controller.joint_limits.coupled)) or (bounds and not bounds[0]-self.INPUT_EPSILON <= angle <= bounds[1]+self.INPUT_EPSILON):
                raise ValueError(f'{n}号目标角度超出软件范围')
            normalized[n]=min(bounds[1],max(bounds[0],angle)) if bounds else angle
        return normalized

    def _preflight(self, targets, speed, reuse_recent=False):
        targets=self._input(targets, speed)
        if not self.controller.backend.supports_position_targets:
            raise RuntimeError('任意关节定位需要MMIO 0x00030008；旧版点动和回0可继续使用')
        if any(n not in self.controller.backend.position_target_nodes for n in targets):
            raise RuntimeError('J6 定位需要升级 FPGA 至 MMIO 0x00030009（v9）')
        if self.config_error or any(n not in self.pulses_per_rev for n in targets):
            raise RuntimeError('请先核对并配置电机有效输入脉冲数/圈')
        reference = self._reference(targets)
        limits=self.controller.joint_limits
        if limits.coupled and any(n in targets for n in (3,4)):
            for n in (3,4):self._read(n,require_enabled=False,position_only=True)
        for node in targets:
            if reuse_recent and self.controller.nodes[node].firmware=='Emm':
                self._read_recent(node)
            else:self._read(node,position_only=True)
            if not self.controller.nodes[node].enabled:
                raise RuntimeError(f'{node}号请先在手动控制中使能')
        if reference != self._reference(targets):
            raise RuntimeError('预检期间零点参考改变')
        if limits.coupled and any(n in targets for n in (3,4)):
            coupled_start={n:self.controller.nodes[n].motor_angle/RATIOS[n] for n in (3,4)}
            if coupled_start[3]>34 and self.feedback_within_bounds(4,coupled_start[4]):
                lo,hi=limits.bounds[4]
                coupled_start[4]=min(hi,max(lo,coupled_start[4]))
            limits.check_move(coupled_start,{**coupled_start, **targets})
        self.plans = {}
        for node, angle in targets.items():
            rpm = max(1, min(HOME_MAX_SPEEDS_RPM[node], math.floor(speed*RATIOS[node]/6)))
            scale = self.pulses_per_rev[node]
            pulses = round(angle*RATIOS[node]*scale/360)
            # Rounding must never make the encoded target leave its bounds.
            bounds = (limits.target_bounds(node,{**coupled_start,**targets})
                      if limits.coupled and node in (3,4) else self.effective_bounds(node))
            if bounds:
                low, high = bounds
                pulses = max(math.ceil(low*RATIOS[node]*scale/360),
                    min(math.floor(high*RATIOS[node]*scale/360), pulses))
            if abs(pulses) > 0xFFFFFFFF:
                raise ValueError(f'J{node} 目标超出驱动 32 位脉冲范围')
            quantized = pulses*360/scale/RATIOS[node]
            if abs(quantized*RATIOS[node])*65536/360 > 0xFFFFFFFF:
                raise ValueError(f'J{node} 目标超出驱动 32 位位置反馈范围')
            tolerance = max(MOTOR_ZERO_TOLERANCE/RATIOS[node], 180/scale/RATIOS[node])
            self.plans[node] = dict(rpm=rpm, actual_speed_deg_s=rpm*6/RATIOS[node],
                pulses=pulses, target_deg=quantized, tolerance_deg=tolerance,
                acceleration=HOME_ACCELERATIONS[node])
        if limits.coupled and any(n in targets for n in (3,4)):
            limits.check_move(coupled_start,{**coupled_start, **{n:p['target_deg'] for n,p in self.plans.items()}})
        self.targets = dict(targets)
        self.message = '预检通过 · ' + '；'.join(f'J{n} {p["target_deg"]:.2f}° / {p["rpm"]}RPM' for n,p in self.plans.items())
        return reference

    def _move(self, targets, speed, expected_reference=None, reuse_recent=False, *, acceleration=None):
        if acceleration is not None and (type(acceleration) is not int or not 1<=acceleration<=255):
            raise ValueError('定位加速度须为1～255整数')
        started_at = time.monotonic()
        self._segment_communication = {}
        targets=self._input(targets,speed)
        self.phase = '预检'
        reference = self._preflight(targets, speed,reuse_recent=reuse_recent)
        if acceleration is not None:
            for plan in self.plans.values():plan['acceleration']=acceleration
        preflight_at = time.monotonic()
        if expected_reference is not None and expected_reference != self._reference(targets):
            raise RuntimeError('示教点零点、传动、限位或定位当量已变化，请重新记录')
        deadlines, stable = {}, {n: 0 for n in targets}
        self.phase = '定位运行'
        delay = max((self.controller.backend.enable_delay - (time.monotonic()-self.controller._enabled_at.get(n, 0)) for n in targets), default=0)
        if delay > 0 and self.cancelled.wait(delay):
            self._check()
        for node, plan in self.plans.items():
            c = self.controller
            for started in deadlines:
                self._healthy(started)
            self._read_recent(node)
            if abs(c.nodes[node].motor_angle/RATIOS[node]-plan['target_deg']) <= plan['tolerance_deg']:
                c.recorder.record('joint_target_already_at_position', node=node, target_deg=plan['target_deg'])
                continue
            with c._lock:
                self._check()
                if reference != self._reference(targets):
                    raise RuntimeError('定位期间参考改变')
                start = c.nodes[node].motor_angle
                c.nodes[node].moving = True
                c.nodes[node].direction = '定位'
                c.active_node = c.active_node or node
            self._request('绝对位置定位', absolute_position_frame(node, plan['pulses'], plan['rpm'], plan['acceleration']))
            seconds = abs(plan['target_deg']*RATIOS[node]-start)/(plan['rpm']*6) + plan['rpm']*(256-plan['acceleration'])*50e-6
            deadlines[node] = time.monotonic()+seconds*1.5+15
            c.recorder.record('joint_target_dispatched', node=node, requested_deg=targets[node], **plan)
        remaining = set(deadlines)
        dispatched_at = time.monotonic()
        first_arrival_at = None
        first_inside_nodes = set(targets)-remaining
        all_seen_inside_at = dispatched_at if not remaining else None
        while remaining:
            self._check()
            for node in targets:
                if node in remaining:
                    self._read_running(node)
                else:
                    self._read_completed(node)
                if reference != self._reference(targets):
                    raise RuntimeError('定位期间零点或配置改变')
                plan, s = self.plans[node], self.controller.nodes[node]
                inside = abs(s.motor_angle/RATIOS[node]-plan['target_deg']) <= plan['tolerance_deg']
                if inside:
                    first_inside_nodes.add(node)
                    if all_seen_inside_at is None and first_inside_nodes == set(targets):
                        all_seen_inside_at = time.monotonic()
                if node not in remaining:
                    if not inside:
                        print('JOINT_COMPLETED_DRIFT',dict(node=node,target_motor_deg=plan['target_deg']*RATIOS[node],actual_motor_deg=s.motor_angle,motor_error_deg=s.motor_angle-plan['target_deg']*RATIOS[node],tolerance_motor_deg=plan['tolerance_deg']*RATIOS[node]),flush=True)
                        raise RuntimeError(f'{node}号已完成轴偏离目标')
                    continue
                arrived=False
                if inside:
                    # Position can enter the envelope while the driver is still
                    # decelerating. Read fresh completion flags before stopping.
                    self._read_state(node)
                    self._request('定位读取位置',read_frame(0x36,node))
                    self._healthy(node)
                    inside=abs(s.motor_angle/RATIOS[node]-plan['target_deg'])<=plan['tolerance_deg']
                    arrived=bool(s.motor_flags & 2)
                stable[node] = stable[node]+1 if inside and arrived else 0
                if inside and first_arrival_at is None:
                    first_arrival_at = time.monotonic()
                if stable[node] >= 3:
                    # Keep the absolute-position target active while other
                    # axes arrive; do not interrupt its position command near
                    # the edge of the arrival envelope.
                    remaining.remove(node)
                    self.controller.recorder.record('joint_target_verified',node=node,angle_deg=s.motor_angle/RATIOS[node])
                    if not remaining:
                        break  # The final fresh-position sweep covers all axes.
                elif time.monotonic() >= deadlines[node]:
                    raise RuntimeError(f'{node}号长时间未到位')
            self.message = '等待'+'、'.join(f'J{n}' for n in sorted(remaining))+'到位' if remaining else '参与关节已到位，保持目标并核验停止'
            if remaining and self.cancelled.wait(.02):
                self._check()
        # Stop only after every dispatched axis has settled. A short axis
        # continues holding the requested target until the slowest arrives.
        for node in deadlines:
            self._read_state(node)
            self._request('定位读取位置',read_frame(0x36,node))
            self._healthy(node)
            plan,s=self.plans[node],self.controller.nodes[node]
            if (not s.motor_flags & 2 or
                    abs(s.motor_angle/RATIOS[node]-plan['target_deg'])>plan['tolerance_deg']):
                raise RuntimeError(f'{node}号全轴到位核验失败')
        for node in deadlines:
            plan,s=self.plans[node],self.controller.nodes[node]
            self._request('停止',stop_frame(node))
            self._request('定位读取位置',read_frame(0x36,node))
            print('JOINT_STOP_POSITION',dict(node=node,target_motor_deg=plan['target_deg']*RATIOS[node],
                actual_motor_deg=s.motor_angle,motor_error_deg=s.motor_angle-plan['target_deg']*RATIOS[node],
                tolerance_motor_deg=plan['tolerance_deg']*RATIOS[node],motor_flags=s.motor_flags),flush=True)
            if abs(s.motor_angle/RATIOS[node]-plan['target_deg']) > plan['tolerance_deg']:
                raise RuntimeError(f'{node}号停止后偏离目标')
        # A completed axis is rechecked after the slowest participant arrives.
        stopped_at = time.monotonic()
        for node in targets:
            self._read_completed(node)
            if reference != self._reference(targets):
                raise RuntimeError('最终核验期间零点或配置改变')
            plan = self.plans[node]
            if abs(self.controller.nodes[node].motor_angle/RATIOS[node]-plan['target_deg']) > plan['tolerance_deg']:
                raise RuntimeError(f'{node}号最终角度核验失败')
        self.last_timing=dict(elapsed_seconds=round(time.monotonic()-started_at,3),
            preflight_seconds=round(preflight_at-started_at,3),
            dispatch_seconds=round(dispatched_at-preflight_at,3),
            arrival_confirmation_seconds=round(stopped_at-dispatched_at,3),
            final_verification_seconds=round(time.monotonic()-stopped_at,3),
            all_targets_seen_inside_to_complete_seconds=round(time.monotonic()-all_seen_inside_at,3) if all_seen_inside_at is not None else None,
            communication={k:dict(count=v['count'],seconds=round(v['seconds'],3)) for k,v in self._segment_communication.items()},
            first_arrival_to_complete_seconds=round(time.monotonic()-first_arrival_at,3) if first_arrival_at else 0,
            dispatched_nodes=list(deadlines), skipped_nodes=[n for n in targets if n not in deadlines])
        self.controller.recorder.record('joint_motion_timing', **self.last_timing)
        print('JOINT_MOTION_TIMING', self.last_timing, flush=True)
        self._segment_communication = None
        if not deadlines:self.message='参与关节已在目标位置，无需重复运动'

    def _capture(self):
        reference = self._reference(AUTO_NODES)
        angles = {}
        for node in AUTO_NODES:
            self._read(node, require_enabled=False)
            angles[node] = self.controller.nodes[node].motor_angle/RATIOS[node]
        if self.cancelled.wait(.05):
            self._check()
        for node in AUTO_NODES:
            self._read(node, require_enabled=False)
            if abs(self.controller.nodes[node].motor_angle/RATIOS[node]-angles[node]) > MOTOR_ZERO_TOLERANCE/RATIOS[node]:
                raise RuntimeError(f'{node}号角度尚未稳定')
        if reference != self._reference(AUTO_NODES):
            raise RuntimeError('录点期间零点或配置改变')
        result={}
        for n in AUTO_NODES:
            angle=self.controller.nodes[n].motor_angle/RATIOS[n]
            bounds=self.effective_bounds(n)
            # Record a legal commanded endpoint when stable feedback straddles it.
            result[str(n)]=min(bounds[1],max(bounds[0],angle)) if bounds else angle
        return result

    def _save_points(self, points):
        atomic_json(self.program_path, dict(schema_version=1, points=points))
        self.points = points
        self.program_error = ''
        self.revision += 1
        self.blend_preview = None
        self.cartesian.clear_preview()

    def _operate(self, operation, params):
        if operation=='ai_prepare':
            self.ai_actions.prepare(params['action'],params.get('direction','hold'),params.get('drawing_settings'))
        elif operation=='ai_execute':
            self.ai_actions.execute(params['token'],params.get('confirmed',False))
        elif operation == 'shelf_grasp_execute':
            from .shelf_executor import execute
            execute(self, params)
        elif operation == 'drive174_grasp_execute':
            from .drive174_grasp import execute
            execute(self, params)
        elif operation == 'grasp_execute':
            from .grasp_motion import execute
            execute(self, params)
        elif operation.startswith('cart_'):
            self.cartesian.operate(operation,params)
        elif operation == 'configure':
            scales = self._scales(params['scales'])
            if params.get('confirmed') is not True:
                raise ValueError('请核对驱动细分/步距角、缩小输入功能及方向后确认')
            atomic_json(self.path,dict(schema_version=1,operator_confirmed=True,pulses_per_motor_rev=scales))
            self.pulses_per_rev=scales
            self.blend_preview = None
            self.cartesian.clear_preview()
            if isinstance(self.controller.backend, SimulatedBackend):
                self.controller.backend.position_pulses_per_rev.update(scales)
            self.config_error=''
            self.message='定位脉冲当量已保存；旧示教点须重新核对'
        elif operation == 'blend_preview':
            from .joint_blend import plan, sample
            self.blend_preview = None
            points = copy.deepcopy(self.points)
            if not points or any(not self.point_valid(p) for p in points):
                raise RuntimeError('请先记录有效姿态；失效姿态须重新记录')
            if any(p.get('motion',{}).get('mode','J')!='J' for p in points):
                raise RuntimeError('含L/C段的程序请使用J/L/C整段预览；关节Blend仅支持J段')
            nodes = [int(n) for n in points[0]['angles_deg']]
            reference = self._reference(nodes)
            start = {}
            self.phase = '读取融合起点'
            for node in nodes:
                self._read(node, require_enabled=False, position_only=True)
                angle = self.controller.nodes[node].motor_angle/RATIOS[node]
                bounds = self.effective_bounds(node)
                start[node] = min(bounds[1],max(bounds[0],angle)) if bounds else angle
            if reference != self._reference(nodes):
                raise RuntimeError('预览期间零点参考改变')
            self._check()
            self.phase = '融合规划'
            report = plan(start, points, self.controller.joint_limits.blend_bounds(),
                radius=params.get('radius',.5),acceleration=params.get('acceleration',5),
                jerk=params.get('jerk',20))
            report['samples'] = sample(report)
            report['point_names'] = [p['name'] for p in points]
            report['reference'] = reference
            report['revision'] = self.revision
            self.blend_preview = report
            self.message = f'融合规划完成：{len(report["blended_points"])}个过渡点，{report["total_seconds"]:.2f}秒；仅预览'
        elif operation == 'preflight':
            self.phase='预检'
            self._preflight(params['targets'],params['speed'])
        elif operation == 'move':
            self._move(params['targets'],params['speed'])
        elif operation == 'refresh':
            nodes = params.get('nodes')
            if not isinstance(nodes, (list, tuple)) or not nodes or any(type(n) is not int or n not in AUTO_NODES for n in nodes) or len(set(nodes)) != len(nodes):
                raise ValueError('请选择要读取的 J1～J6 关节')
            self.phase = '刷新角度'
            reference = self._reference(nodes)
            angles = {}
            for node in nodes:
                self._read(node, require_enabled=False)
                angles[node] = self.controller.nodes[node].motor_angle / RATIOS[node]
            if reference != self._reference(nodes):
                raise RuntimeError('刷新期间零点参考改变')
            self.targets = angles
            self.message = '已刷新 ' + '、'.join(f'J{n}' for n in nodes) + '；未下发运动命令'
        elif operation == 'capture':
            self.targets={int(n):v for n,v in self._capture().items()}
            self.message='已读取六关节稳定角度'
        elif operation == 'record':
            if len(self.points)>=self.MAX_POINTS:
                raise ValueError('最多保存50个姿态')
            angles=self._capture()
            self.controller.zero_home._save_session()
            point=dict(name=params['name'].strip(),angles_deg=angles,dwell_seconds=params['dwell'],
                speed_deg_s=params['speed'],reference=self._reference(AUTO_NODES))
            if self.cartesian.ready():
                from .kinematics import forward,GEOMETRY_VERSION
                point['tcp_snapshot']=dict(geometry_version=GEOMETRY_VERSION,
                    pose=forward(self.cartesian.to_model([angles[str(n)] for n in AUTO_NODES])))
            self._validate_point(point)
            self._save_points(self.points+[point])
            self.message='姿态已保存：'+point['name']
        elif operation == 'delete':
            points=copy.deepcopy(self.points)
            points.pop(params['index'])
            self._save_points(points)
            self.message='示教点已删除'
        elif operation == 'edit':
            points=copy.deepcopy(self.points)
            point=points[params['index']]
            point.update(name=params['name'].strip(), speed_deg_s=params['speed'], dwell_seconds=params['dwell'])
            if 'motion' in params:point['motion']=copy.deepcopy(params['motion'])
            self._validate_point(point)
            self._save_points(points)
            self.message='示教点参数已保存'
        elif operation == 'reorder':
            points=copy.deepcopy(self.points)
            index, offset=params['index'], params['offset']
            if type(index) is not int or type(offset) is not int or offset not in (-1, 1) or not 0 <= index < len(points) or not 0 <= index+offset < len(points):
                raise ValueError('姿态顺序无效')
            points[index],points[index+offset]=points[index+offset],points[index]
            self._save_points(points)
            self.message='姿态顺序已保存'
        elif operation in ('return','play'):
            points=([self.points[params['index']]] if operation=='return' else self.points)
            if not points:
                raise ValueError('请先记录姿态')
            for point in points:
                if point.get('motion',{}).get('mode','J')!='J':
                    raise RuntimeError('程序含直线/圆弧段；当前板卡未开放连续轨迹执行，请使用整段规划预览')
                if not self.point_valid(point):
                    raise RuntimeError('示教点参考已失效，请在当前零点重新记录')
                self._input({int(n):v for n,v in point['angles_deg'].items()},point['speed_deg_s'])
                if not self.controller.backend.supports_position_targets or any(int(n) not in self.controller.backend.position_target_nodes for n in point['angles_deg']):
                    raise RuntimeError('回放参与轴需要对应 FPGA 定位能力，J6 需要 v9')
                if self.config_error or any(int(n) not in self.pulses_per_rev for n in point['angles_deg']):
                    raise RuntimeError('回放参与轴尚未配置定位脉冲当量')
            self.total_points=len(points)
            for i,point in enumerate(copy.deepcopy(points)):
                self.current_point=i+1
                self.message=f'执行姿态{i+1}/{len(points)}：{point["name"]}'
                self._move({int(n):v for n,v in point['angles_deg'].items()},point['speed_deg_s'],point['reference'],
                           reuse_recent=operation=='play' and i>0)
                if operation=='play':
                    self.phase='停留'
                    if self.cancelled.wait(point['dwell_seconds']):
                        self._check()
            self.message='姿态执行完成'
        else:
            raise ValueError('未知关节操作')

    def start(self, operation, callback, **params):
        c=self.controller
        with c._lock:
            c._guard()
            if c._moving:
                raise RuntimeError('请先停止所有电机并等待确认')
            if operation not in ('ai_prepare','ai_execute'):
                self.ai_actions.invalidate()
            # Validate plain input before allocating the worker; full preflight
            # is always repeated using fresh addressed replies before motion.
            if operation in ('preflight','move'):
                self._input(params.get('targets'),params.get('speed'))
            self.busy=True
            self.error=''
            self.phase='准备'
            self.current_point=0
            self.total_points=0
            self.cancelled.clear()
            self.done.clear()
            c._publish()
        def work():
            error=''
            try:
                self._operate(operation,params)
                self._check()
            except Exception as exc:
                error=str(exc)
                with c._lock:
                    if c._moving or c._all_stopping:
                        stopped=threading.Event()
                        c.stop_all(lambda _ok:stopped.set())
                    else:
                        stopped=None
                if stopped is not None:
                    self.phase='停止确认'
                    stopped.wait(c.RESPONSE_TIMEOUT*6+2)
                    if not stopped.is_set() or c._moving or any(v!='已确认停止' for v in c.all_stop_results.values()):
                        error+='；部分电机停止未确认'
                self.message=error
                c.recorder.record('joint_task_failure',operation=operation,error=error)
            finally:
                with c._lock:
                    self._segment_communication = None
                    self.error=error
                    self.busy=False
                    self.phase='故障/取消' if error else '空闲'
                    c._publish()
                    self.done.set()
                print('JOINT_TASK_RESULT',dict(operation=operation,ok=not error,error=error,
                      targets=self.targets,moving=c._moving,pending=bool(c._pending)),flush=True)
                callback(not error,error)
        self.thread=threading.Thread(target=work,daemon=True,name='f3p-joint-task')
        self.thread.start()
