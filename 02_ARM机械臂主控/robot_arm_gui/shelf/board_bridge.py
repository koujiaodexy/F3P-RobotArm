"""Fail-closed board-integration primitives; no hardware or IPC access.

The trusted board adapter is not implemented. In particular, its capture
timestamp must be tied to acquisition by a validated producer, not fabricated
from a status write or frame dequeue time. This module does not start motion.
"""
import math


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


class BridgeError(ValueError):
    pass


class SnapshotGate:
    def __init__(self, max_status_age=.2, max_frame_age=.35):
        self.max_status_age = max_status_age
        self.max_frame_age = max_frame_age
        self.vision_session = None
        self.frame_id = None
        self.capture_time = None

    def status(self, now, status):
        if not isinstance(status, dict) or not _number(now) or not _number(status.get('measured_at')):
            raise BridgeError('Missing trusted board status time')
        if not 0 <= now - status['measured_at'] <= self.max_status_age:
            raise BridgeError('Board status stale or from the future')
        for field in ('wheels_stopped', 'arm_stowed', 'gripper_released', 'fault', 'pc_disconnected'):
            if type(status.get(field)) is not bool:
                raise BridgeError('Missing board status: ' + field)
        if status['fault'] or not status['pc_disconnected']:
            raise BridgeError('Fault or PC data link present')
        odo = status.get('odo_mm')
        if not isinstance(odo, (tuple, list)) or len(odo) != 2 or not all(_number(x) for x in odo):
            raise BridgeError('Missing signed cumulative encoder distances')
        return status

    def vision(self, now, frame, *, trusted_capture_clock=False):
        # Caller can set this flag only after the capture timestamp source has
        # been verified in the board adapter; status publication time, polling
        # time and dequeue time cannot prove acquisition freshness.
        if trusted_capture_clock is not True:
            raise BridgeError('Camera capture timestamp source not verified')
        if not isinstance(frame, dict) or frame.get('running') is not True or frame.get('fresh') is not True:
            raise BridgeError('Camera is not running with a fresh frame')
        stamp = frame.get('captured_at')
        if not _number(now) or not _number(stamp) or not 0 <= now-stamp <= self.max_frame_age:
            raise BridgeError('Camera capture is stale or from the future')
        session = frame.get('session_id')
        ident = frame.get('frame_id')
        if not isinstance(session, str) or not session or type(ident) is not int or ident < 0:
            raise BridgeError('Missing frame/session identity')
        if self.vision_session is None:
            self.vision_session = session
        if session != self.vision_session:
            raise BridgeError('Camera session changed')
        if self.frame_id is not None:
            if ident < self.frame_id or stamp < self.capture_time:
                raise BridgeError('Out-of-order camera frame')
            if ident == self.frame_id and stamp != self.capture_time:
                raise BridgeError('Repeated frame has changed capture time')
            if ident > self.frame_id and stamp <= self.capture_time:
                raise BridgeError('New frame has no newer capture time')
        self.frame_id, self.capture_time = ident, stamp
        return frame

    def authorize_intent(self, now, action, status, frame=None, *, trusted_capture_clock=False):
        """Preflight only: the hardware owner must enforce its own interlocks."""
        if not isinstance(action, dict):
            raise BridgeError('Invalid action')
        kind = action.get('kind')
        # Always allow a stop request even if the data that prompted it is stale.
        if kind == 'stop':
            return True
        if kind not in ('hold', 'drive', 'turn', 'creep', 'grasp'):
            raise BridgeError('Unsupported action')
        self.status(now, status)
        if kind in ('drive', 'turn', 'creep'):
            if not status['arm_stowed'] or not status['gripper_released']:
                raise BridgeError('Wheels locked until arm is stowed and gripper released')
        if kind == 'grasp' and not status['wheels_stopped']:
            raise BridgeError('Grasp locked until wheels are stopped')
        if kind in ('creep', 'grasp'):
            self.vision(now, frame, trusted_capture_clock=trusted_capture_clock)
        return True


class ReceiptGate:
    """Reject stale or duplicate action receipts across service generations."""
    def __init__(self, owner, generation):
        if not isinstance(owner, str) or not owner or not isinstance(generation, str) or not generation:
            raise BridgeError('A unique owner and service generation are required')
        self.owner, self.generation = owner, generation
        self.last_id = 0
        self.pending = None

    def issue(self, action):
        if self.pending is not None:
            raise BridgeError('Previous command is still pending')
        ident = action.get('id') if isinstance(action, dict) else None
        if type(ident) is not int or ident <= self.last_id:
            raise BridgeError('Command ID was replayed or invalid')
        self.last_id = ident
        self.pending = ident
        return dict(owner=self.owner, generation=self.generation, command_id=ident)

    def accept(self, receipt):
        if not isinstance(receipt, dict) or self.pending is None:
            raise BridgeError('No pending command')
        if (receipt.get('owner') != self.owner or receipt.get('generation') != self.generation
                or type(receipt.get('command_id')) is not int or receipt['command_id'] != self.pending):
            raise BridgeError('Receipt does not match the current command and generation')
        if type(receipt.get('success')) is not bool:
            raise BridgeError('Missing success flag')
        self.pending = None
        return receipt
