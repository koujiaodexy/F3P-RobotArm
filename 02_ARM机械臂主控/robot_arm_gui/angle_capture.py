"""Record observed stationary joint angles; never issue a movement command."""
from pathlib import Path
import json
import os
import time

from .zero_home import RATIOS


class AngleRangeCapture:
    def __init__(self, zero_config):
        self.directory = Path(zero_config).parent
        self.control = self.directory / 'angle-range-capture.json'
        self.boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip() if Path('/proc/sys/kernel/random/boot_id').exists() else 'test'
        self.pending = []

    def active(self):
        try:
            control = json.loads(self.control.read_text(encoding='utf-8'))
            capture_id = control.get('capture_id', '')
            return control if control.get('enabled') and control.get('boot_id') == self.boot_id and isinstance(capture_id, str) and capture_id.isalnum() else None
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def stopped(self, node):
        control = self.active()
        if control:
            axes = control.get('nodes', list(RATIOS))
            axes = [axis for axis in axes if axis in RATIOS]
            if node in axes:
                if node in self.pending:
                    self.pending.remove(node)
                self.pending.insert(0, node)
            for axis in axes:
                if axis not in self.pending:
                    self.pending.append(axis)

    def sample(self, node, state, first_motor_angle=None, stopped_pair=False):
        control = self.active()
        if not control:
            return
        output = self.directory / ('angle-range-' + control['capture_id'] + '.json')
        if output.exists():
            result = json.loads(output.read_text(encoding='utf-8'))
        else:
            result = dict(capture_id=control['capture_id'], boot_id=self.boot_id, ratios=RATIOS, nodes={}, errors=[])
        reason = None
        if not state.zero_valid:
            reason = '零点无效'
        elif state.moving:
            reason = '停止未确认'
        elif state.motor_flags & 0x8C:
            reason = '电源重启或保护状态异常'
        elif state.firmware != 'Emm' or state.motor_angle is None:
            reason = '固件或角度无效'
        elif stopped_pair:
            if first_motor_angle is None or abs(state.motor_angle-first_motor_angle) > 0.8:
                reason = '连续两次角度尚未稳定'
        elif not state.motor_flags & 2:
            reason = '缺少停止后的稳定角度核验'
        if reason:
            rejected = dict(node=node, reason=reason, time=time.time(),
                            motor_deg=state.motor_angle, first_motor_deg=first_motor_angle,
                            motor_flags=state.motor_flags, zero_valid=state.zero_valid,
                            moving=state.moving, firmware=state.firmware)
            result['errors'].append(rejected)
            print('ANGLE_RANGE_REJECTED', json.dumps(dict(capture_id=control['capture_id'], **rejected), ensure_ascii=False), flush=True)
        else:
            angle = state.motor_angle / RATIOS[node]
            entry = result['nodes'].setdefault(str(node), dict(min_deg=angle, max_deg=angle, samples=0))
            entry.update(min_deg=min(entry['min_deg'], angle), max_deg=max(entry['max_deg'], angle),
                         last_deg=angle, motor_deg=state.motor_angle, samples=entry['samples']+1, time=time.time())
            print('ANGLE_RANGE_SAMPLE', json.dumps(dict(capture_id=control['capture_id'], node=node, joint_deg=angle, min_deg=entry['min_deg'], max_deg=entry['max_deg']), ensure_ascii=False), flush=True)
        staged = output.with_suffix('.new')
        with staged.open('w', encoding='utf-8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.flush(); os.fsync(handle.fileno())
        staged.replace(output)
        return reason

    def invalidate(self, reason):
        control = self.active()
        if control:
            control.update(enabled=False, invalid_reason=reason)
            self.control.write_text(json.dumps(control, ensure_ascii=False), encoding='utf-8')
            self.pending.clear()
            print('ANGLE_RANGE_INVALIDATED', reason, flush=True)
