"""Reference V2 FIFO transport methods; legacy dispatch stays in backend.py."""
import threading
import time
from .reference_endpoint.protocol import trajectory_batch

class SimTrajectoryMixin:
    def trajectory_prepare(self):
        with self._trajectory_sim_lock:
            if not self.connected:
                raise RuntimeError('simulation backend is not connected')
            if self._trajectory_sim and self._trajectory_sim['owned']:
                raise RuntimeError('trajectory channel already owned')
            now = time.monotonic()
            self._trajectory_sim = dict(owned=True, running=False, draining=False, stop_done=False,
                fault=False, error=0, queue=[], accepted_seq=0, fired_seq=0, final_sent=False,
                final_queued=False, stop_mask=0, lease=now, next_tick=now, feedback_tick=now,
                feedback_seq=0, feedback={}, stopping=False)
        return self.trajectory_status()
    def _trajectory_sim_update(self):
        state = self._trajectory_sim
        if state is None:
            raise RuntimeError('prepare trajectory first')
        now = time.monotonic()
        if (state['running'] or state['draining']) and now - state['lease'] > 0.25:
            state.update(fault=True, error=0xFFFF3101, running=False, draining=False,
                         stop_done=True, stop_mask=63, queue=[])
        while state['running'] and now >= state['next_tick']:
            if not state['queue']:
                state.update(fault=True, error=0xFFFF3105, running=False,
                             stop_done=True, stop_mask=63, queue=[])
                break
            seq, targets, speeds, acceleration, final = state['queue'].pop(0)
            for node, target in enumerate(targets, 1):
                ppr = self.position_pulses_per_rev[node]
                magnitude = (abs(target) * 65536 + ppr // 2) // ppr
                self.positions[node] = -magnitude if target < 0 else magnitude
            state['fired_seq'] = seq
            state['next_tick'] += 0.04
            if final:
                state.update(running=False, draining=True, final_sent=True)
        if now >= state['feedback_tick']:
            state['feedback_tick'] = now + 0.04
            state['feedback_seq'] += 1
            state['feedback'] = {node: dict(position_counts_signed=self.positions[node],
                motor_flags=self.power_flags[node] | 3, home_flags=3,
                position_age_s=0.0, motor_age_s=0.0, home_age_s=0.0,
                position_seq=state['feedback_seq'], motor_seq=state['feedback_seq'],
                home_seq=state['feedback_seq']) for node in range(1, 7)}
        return state
    def trajectory_enqueue(self, seq, targets, speeds, acceleration, final=False):
        batch = trajectory_batch(seq, targets, speeds, acceleration, final,axis_speed_limits=getattr(self,'trajectory_speed_limits',None))
        with self._trajectory_sim_lock:
            state = self._trajectory_sim_update()
            if not state['owned'] or state['fault'] or state['stop_done'] or state['final_queued']:
                raise RuntimeError('trajectory queue is not accepting frames')
            if seq != state['accepted_seq'] + 1:
                raise ValueError('trajectory sequence must be contiguous from one')
            if len(state['queue']) >= 32:
                raise BufferError('trajectory FIFO is full')
            state['queue'].append(batch)
            state.update(accepted_seq=seq, final_queued=final, lease=time.monotonic())
        return seq
    def trajectory_start(self):
        with self._trajectory_sim_lock:
            state = self._trajectory_sim_update()
            if not state['owned'] or state['running'] or state['draining'] or state['fault'] or state['stop_done']:
                raise RuntimeError('trajectory is not in prefill state')
            if len(state['queue']) < 4 and not (state['queue'] and state['final_queued']):
                raise ValueError('prefill at least four frames, or a complete final batch')
            if any(self.power_flags[node] & 0x8C for node in range(1, 7)):
                state.update(fault=True, error=0xFFFF3204, queue=[], stop_done=True, stop_mask=63)
            else:
                state.update(running=True, lease=time.monotonic(), next_tick=time.monotonic() + 0.04)
        return self.trajectory_status()
    def trajectory_status(self):
        with self._trajectory_sim_lock:
            state = self._trajectory_sim_update()
            state['lease'] = time.monotonic()
            keys = ('owned', 'running', 'draining', 'stop_done', 'fault', 'error',
                    'accepted_seq', 'fired_seq', 'final_sent', 'stop_mask', 'stopping')
            result = {key: state[key] for key in keys}
            result.update(fifo_count=len(state['queue']), capacity=32, tick_seconds=0.04,
                full=len(state['queue']) >= 32, moving_mask=63 if state['running'] or state['draining'] else 0,
                feedback={n: dict(v) for n, v in state['feedback'].items()}, clock_ms=int(time.monotonic()*1000))
            return result
    def trajectory_cancel(self):
        with self._trajectory_sim_lock:
            state = self._trajectory_sim_update()
            state.update(running=False, draining=False, queue=[], stop_done=True, stop_mask=63, stopping=False)
        return self.trajectory_status()
    def trajectory_release(self):
        with self._trajectory_sim_lock:
            state = self._trajectory_sim_update()
            if state['owned'] and not state['stop_done']:
                raise RuntimeError('all-axis stop not confirmed')
            state['owned'] = False

class MMIOTrajectoryMixin:
    TR_CONTROL = 0x60
    TR_CONTROL_ACK = 0x64
    TR_STATUS = 0x68
    TR_ERROR = 0x6C
    TR_COMMIT_ACK = 0x70
    TR_ACCEPTED = 0x74
    TR_FIRED = 0x78
    TR_CAPACITY = 0x7C
    TR_STAGE_SEQ = 0x80
    TR_STAGE_FINAL = 0x84
    TR_COMMIT = 0x88
    TR_NOW_MS = 0x8C
    TR_HEARTBEAT = 0x90
    TR_STAGE_AXES = 0xA0
    TR_FEEDBACK = 0x100
    def _trajectory_heartbeat_locked(self):
        now=time.monotonic();previous=getattr(self,'_trajectory_heartbeat_at',None)
        gap=0. if previous is None else 1000*(now-previous)
        self._write32(self.TR_HEARTBEAT,1)
        self._trajectory_heartbeat_at=time.monotonic()
        self._trajectory_heartbeat_max_gap_ms=max(gap,getattr(self,'_trajectory_heartbeat_max_gap_ms',0.))
        return gap
    def _trajectory_require(self):
        if not self.supports_continuous_trajectory or self._map is None:
            raise RuntimeError('连续轨迹需要已连接的 V9 FPGA (0x00030009)')
    def _trajectory_control_locked(self, operation):
        self._trajectory_require()
        if self._trajectory_control_toggle is None:
            # Register bit 1 exposes the PS-written toggle; bit 0 is CAN ACK.
            # This remains valid when reconnecting during an in-flight command.
            self._trajectory_control_toggle = (self._read32(self.TR_CONTROL_ACK) >> 1) & 1
        deadline = time.monotonic() + 0.050
        while (self._read32(self.TR_CONTROL_ACK) & 1) != self._trajectory_control_toggle:
            if time.monotonic() >= deadline:
                self._trajectory_lease_valid = False
                raise RuntimeError('previous trajectory control is still pending; lease revoked')
            time.sleep(0.0002)
        self._write32(self.TR_CONTROL, operation)
        self._trajectory_control_toggle ^= 1
        deadline = time.monotonic() + 0.050
        while time.monotonic() < deadline:
            if (self._read32(self.TR_CONTROL_ACK) & 1) == self._trajectory_control_toggle:
                return
            time.sleep(0.0002)
        self._trajectory_lease_valid = False
        raise RuntimeError('trajectory control acknowledgement uncertain; lease revoked')
    def trajectory_prepare(self):
        with self._lock:
            self._trajectory_require()
            if self._read32(self.TR_STATUS) & 1:
                raise RuntimeError('已有轨迹占用通道；先完成停止和释放')
            if (self._read32(self.REG_STATUS) & 5 or self._queued_frame is not None
                    or self._pending_rx is not None or self._home_pending is not None
                    or (self._read32(self.REG_COMMAND_ACK) & 1) != self._command_toggle):
                raise RuntimeError('原控制通道尚未空闲，不能接管连续轨迹')
            self._trajectory_control_locked(1)
            deadline = time.monotonic() + 0.05
            while not self._read32(self.TR_STATUS) & 1:
                if time.monotonic() >= deadline:
                    raise RuntimeError('FPGA did not grant trajectory ownership')
                time.sleep(0.0002)
            self._trajectory_final_queued = False
            self._trajectory_last_seq = 0
            self._trajectory_lease_valid = True
            self._trajectory_heartbeat_locked()
        return self.trajectory_status()
    def trajectory_enqueue(self, seq, targets, speeds, acceleration, final=False):
        seq, targets, speeds, acceleration, final = trajectory_batch(
            seq, targets, speeds, acceleration, final,axis_speed_limits=getattr(self,'trajectory_speed_limits',None))
        with self._lock:
            self._trajectory_require()
            state = self._read32(self.TR_STATUS)
            if not self._trajectory_lease_valid or not state & 1 or state & (16 | 64 | 128 | 8 | 4):
                raise RuntimeError('trajectory queue is not accepting frames')
            if self._trajectory_final_queued or seq != self._trajectory_last_seq + 1:
                raise ValueError('trajectory sequence must be contiguous from one, before final')
            if ((state >> 8) & 63) >= self._read32(self.TR_CAPACITY):
                raise BufferError('trajectory FIFO is full; no frame was written')
            commit_state = self._read32(self.TR_COMMIT_ACK)
            if (commit_state & 1) != ((commit_state >> 1) & 1):
                self._trajectory_lease_valid = False
                raise RuntimeError('previous trajectory commit still pending; lease revoked')
            ack = commit_state & 1
            for index, (target, speed, acc) in enumerate(zip(targets, speeds, acceleration)):
                self._write32(self.TR_STAGE_AXES + index * 8, target)
                self._write32(self.TR_STAGE_AXES + index * 8 + 4, (acc << 16) | speed)
            self._write32(self.TR_STAGE_SEQ, seq)
            self._write32(self.TR_STAGE_FINAL, int(final))
            self._write32(self.TR_COMMIT, 1)
            deadline = time.monotonic() + 0.05
            while time.monotonic() < deadline:
                state = self._read32(self.TR_STATUS)
                if state & 16:
                    raise RuntimeError('FPGA rejected trajectory batch: 0x%08X' % self._read32(self.TR_ERROR))
                if ((self._read32(self.TR_COMMIT_ACK) & 1) != ack
                        and self._read32(self.TR_ACCEPTED) == seq):
                    self._trajectory_last_seq = seq
                    self._trajectory_final_queued = final
                    self._trajectory_heartbeat_locked()
                    return seq
                time.sleep(0.0002)
            # Uncertain submissions are never blindly retried or kept alive.
            self._trajectory_lease_valid = False
            self._trajectory_control_locked(3)
            raise RuntimeError('trajectory batch acceptance uncertain; all-axis stop requested')
    def trajectory_start(self):
        with self._lock:
            self._trajectory_require()
            state = self._read32(self.TR_STATUS)
            count = (state >> 8) & 63
            if not state & 1 or state & (2 | 4 | 8 | 16 | 64 | 128):
                raise RuntimeError('trajectory is not in prefill state')
            if count < 4 and not (count and self._trajectory_final_queued):
                raise ValueError('prefill at least four frames, or a complete final batch')
            self._trajectory_heartbeat_at=None;self._trajectory_heartbeat_max_gap_ms=0.
            self._trajectory_heartbeat_locked()
            self._trajectory_control_locked(2)
        return self.trajectory_status()
    def trajectory_status(self):
        with self._lock:
            self._trajectory_require()
            flags = self._read32(self.TR_STATUS)
            heartbeat_gap=None
            if flags & 1 and self._trajectory_lease_valid:
                heartbeat_gap=self._trajectory_heartbeat_locked()
            feedback = {}
            raw = []
            for axis in range(6):
                base = self.TR_FEEDBACK + 32 * axis
                for attempt in range(4):
                    before = tuple(self._read32(base + 20 + 4 * j) for j in range(3))
                    values = [self._read32(base + 4 * j) for j in range(8)]
                    after = tuple(self._read32(base + 20 + 4 * j) for j in range(3))
                    if before == after == tuple(values[5:8]):
                        break
                else:
                    raise RuntimeError('trajectory feedback snapshot changed repeatedly')
                raw.append(values)
            now = self._read32(self.TR_NOW_MS)
            for axis, values in enumerate(raw, 1):
                packed, magnitude, ptime, mtime, htime, pseq, mseq, hseq = values
                def age(stamp, seq):
                    delta = (now - stamp) & 0xFFFFFFFF
                    return delta / 1000.0 if seq and delta < 0x80000000 else float('inf')
                feedback[axis] = {
                    'position_counts_signed': -magnitude if packed & 255 else magnitude,
                    'motor_flags': (packed >> 8) & 255, 'home_flags': (packed >> 16) & 255,
                    'position_age_s': age(ptime, pseq), 'motor_age_s': age(mtime, mseq),
                    'home_age_s': age(htime, hseq), 'position_seq': pseq,
                    'motor_seq': mseq, 'home_seq': hseq,
                }
            return dict(owned=bool(flags & 1), running=bool(flags & 2), draining=bool(flags & 4),
                stop_done=bool(flags & 8), fault=bool(flags & 16), full=bool(flags & 32),
                final_sent=bool(flags & 64), stopping=bool(flags & 128), error=self._read32(self.TR_ERROR),
                fifo_count=(flags >> 8) & 63, capacity=self._read32(self.TR_CAPACITY), tick_seconds=0.04,
                accepted_seq=self._read32(self.TR_ACCEPTED), fired_seq=self._read32(self.TR_FIRED),
                stop_mask=(flags >> 16) & 63, moving_mask=(flags >> 24) & 63,
                feedback=feedback, clock_ms=now,heartbeat_gap_ms=heartbeat_gap,
                heartbeat_max_gap_ms=getattr(self,'_trajectory_heartbeat_max_gap_ms',0.))
    def trajectory_cancel(self):
        with self._lock:
            self._trajectory_require()
            flags = self._read32(self.TR_STATUS)
            confirmed = bool(flags & 8) and ((flags >> 16) & 63) == 63
            if flags & 1 and not confirmed and not flags & 128:
                self._trajectory_control_locked(3)
        return self.trajectory_status()
    def trajectory_release(self):
        with self._lock:
            self._trajectory_require()
            flags = self._read32(self.TR_STATUS)
            if not flags & 1:
                return
            if not flags & 8 or ((flags >> 16) & 63) != 63:
                raise RuntimeError('全六轴停止尚未确认，不能释放轨迹通道')
            self._trajectory_control_locked(4)
            deadline = time.monotonic() + 0.05
            while self._read32(self.TR_STATUS) & 1:
                if time.monotonic() >= deadline:
                    raise RuntimeError('trajectory ownership release timed out')
                time.sleep(0.0002)
            self._trajectory_final_queued = False
            self._trajectory_last_seq = 0
            self._trajectory_lease_valid = False

