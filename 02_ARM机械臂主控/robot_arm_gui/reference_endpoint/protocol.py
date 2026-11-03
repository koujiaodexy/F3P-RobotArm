"""ZDT X42S CAN frame definitions used by the Linux control panel."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


CAN_EFF_FLAG = 0x80000000
CAN_EFF_MASK = 0x1FFFFFFF
CAN_FRAME_FORMAT = "=IB3x8s"
MOTOR_CAN_ID = 0x00000100
MIN_SPEED_RPM = 1
MAX_SPEED_RPM = 3000
# Joint speed is capped at about 20 deg/s for the initial faster return profile.
HOME_MAX_SPEEDS_RPM = {1: 952, 2: 952, 3: 833, 4: 140, 5: 74, 6: 3}
MIN_ACCELERATION = 0
MAX_ACCELERATION = 255
DEFAULT_ACCELERATION = 50


@dataclass(frozen=True)
class CanFrame:
    can_id: int
    data: bytes
    extended: bool = True
    # Host intent only; never serialized. PPR must come from a calibrated profile.
    position_pulses_per_rev: int | None = field(default=None, compare=False)

    def packed(self) -> bytes:
        if not 0 <= self.can_id <= CAN_EFF_MASK:
            raise ValueError(f"CAN ID out of range: 0x{self.can_id:X}")
        if len(self.data) > 8:
            raise ValueError("Classic CAN payload cannot exceed 8 bytes")
        wire_id = self.can_id | (CAN_EFF_FLAG if self.extended else 0)
        return struct.pack(
            CAN_FRAME_FORMAT,
            wire_id,
            len(self.data),
            self.data.ljust(8, b"\x00"),
        )

    @classmethod
    def unpacked(cls, raw: bytes) -> "CanFrame":
        can_id, dlc, payload = struct.unpack(CAN_FRAME_FORMAT, raw)
        return cls(
            can_id=can_id & CAN_EFF_MASK,
            data=payload[:dlc],
            extended=bool(can_id & CAN_EFF_FLAG),
        )

    def payload_text(self) -> str:
        return self.data.hex(" ").upper()


def _validate_speed(speed_rpm: int) -> int:
    speed = int(speed_rpm)
    if not MIN_SPEED_RPM <= speed <= MAX_SPEED_RPM:
        raise ValueError(
            f"speed must be between {MIN_SPEED_RPM} and {MAX_SPEED_RPM} RPM"
        )
    return speed


def motor_can_id(node: int) -> int:
    if isinstance(node, bool) or not isinstance(node, int) or not 1 <= node <= 6:
        raise ValueError("电机编号必须为 1–6")
    return node << 8


def option_query_frame(node: int = 1) -> CanFrame:
    return CanFrame(motor_can_id(node), bytes.fromhex("1A 6B"))


def enable_frame(node: int = 1) -> CanFrame:
    return CanFrame(motor_can_id(node), bytes.fromhex("F3 AB 01 00 6B"))


def disable_frame(node: int = 1) -> CanFrame:
    return CanFrame(motor_can_id(node), bytes.fromhex("F3 AB 00 00 6B"))


def stop_frame(node: int = 1) -> CanFrame:
    return CanFrame(motor_can_id(node), bytes.fromhex("FE 98 00 6B"))


def zero_frame(node: int) -> CanFrame:
    return CanFrame(motor_can_id(node), bytes.fromhex('0A 6D 6B'))


def read_frame(function: int, node: int) -> CanFrame:
    if function not in (0x36, 0x3A, 0x3B):
        raise ValueError('unsupported read function')
    return CanFrame(motor_can_id(node), bytes([function, 0x6B]))


def mark_power_session_frame(node: int) -> CanFrame:
    return CanFrame(motor_can_id(node), bytes.fromhex('50 00 6B'))


def home_zero_frame(node: int, speed: int, acceleration: int = 50) -> CanFrame:
    limit = HOME_MAX_SPEEDS_RPM.get(node, 0)
    if type(speed) is not int or not 1 <= speed <= limit or not 1 <= acceleration <= 255:
        raise ValueError(f'{node}号回零电机转速须为1–{limit} RPM，加速度须为1–255')
    # Logical Emm FD command; transport sends two CAN packets (8 + 5 bytes).
    return CanFrame(motor_can_id(node), bytes([0xFD, 0, speed >> 8, speed & 255,
        acceleration, 0, 0, 0, 0, 1, 0, 0x6B]))


def position_frame(node: int, target_pulses: int, speed_rpm: int,
                   acceleration: int, *, pulses_per_rev: int) -> CanFrame:
    """Emm absolute-position command, with explicit calibrated pulse units.

    Positive uses direction 0, negative direction 1. This builder does not
    infer motor microsteps, input scaling, gear ratios or joint coordinates.
    The 3200 PPR convention is a simulation default, never a hardware default.
    """
    motor_can_id(node)
    if type(pulses_per_rev) is not int or not 1 <= pulses_per_rev <= 0xFFFFFFFF:
        raise ValueError('explicit positive integer pulses_per_rev is required')
    if type(target_pulses) is not int or abs(target_pulses) > 0xFFFFFFFF:
        raise ValueError('signed target pulse magnitude must fit uint32')
    limit = HOME_MAX_SPEEDS_RPM[node]
    if type(speed_rpm) is not int or not 1 <= speed_rpm <= limit:
        raise ValueError(f'position speed must be 1..{limit} RPM for node {node}')
    if type(acceleration) is not int or not 0 <= acceleration <= 255:
        raise ValueError('position acceleration must be 0..255; 0 means direct')
    data = bytes([0xFD, int(target_pulses < 0), speed_rpm >> 8,
                  speed_rpm & 255, acceleration])
    data += abs(target_pulses).to_bytes(4, 'big') + bytes([1, 0, 0x6B])
    return CanFrame(motor_can_id(node), data,
                    position_pulses_per_rev=pulses_per_rev)


def speed_frame(
    speed_rpm: int,
    reverse: bool,
    acceleration: int = DEFAULT_ACCELERATION,
    node: int = 1,
) -> CanFrame:
    """Build the verified seven-byte Emm-style F6 velocity command."""
    speed = _validate_speed(speed_rpm)
    if not MIN_ACCELERATION <= acceleration <= MAX_ACCELERATION:
        raise ValueError(
            f"acceleration must be between {MIN_ACCELERATION} and "
            f"{MAX_ACCELERATION}"
        )
    direction = 0x01 if reverse else 0x00
    payload = bytes(
        [
            0xF6,
            direction,
            (speed >> 8) & 0xFF,
            speed & 0xFF,
            acceleration,
            0x00,
            0x6B,
        ]
    )
    return CanFrame(motor_can_id(node), payload)


def is_valid_motor_reply(frame: CanFrame, node: int | None = None) -> bool:
    return (
        frame.extended
        and frame.can_id in ([motor_can_id(node)] if node is not None else [n << 8 for n in range(1, 7)])
        and len(frame.data) >= 3
        and frame.data[-1] == 0x6B
    )

def trajectory_batch(seq, targets, speeds, acceleration, final=False, *, axis_speed_limits=None):
    """Validate one V9 six-axis batch before any device register is written."""
    if type(seq) is not int or not 1 <= seq <= 0xFFFFFFFF:
        raise ValueError('trajectory sequence must be a positive uint32')
    if not isinstance(targets, (list, tuple)) or len(targets) != 6:
        raise ValueError('trajectory requires six signed pulse targets')
    if not isinstance(speeds, (list, tuple)) or len(speeds) != 6:
        raise ValueError('trajectory requires six integer motor speeds')
    acc = ([acceleration] * 6 if type(acceleration) is int else acceleration)
    if not isinstance(acc, (list, tuple)) or len(acc) != 6:
        raise ValueError('trajectory acceleration requires one or six integers')
    if type(final) is not bool:
        raise ValueError('trajectory final flag must be boolean')
    limits=HOME_MAX_SPEEDS_RPM if axis_speed_limits is None else axis_speed_limits
    if not isinstance(limits,dict) or set(limits)!=set(range(1,7)) or any(type(v) is not int or not 1<=v<=3000 for v in limits.values()):
        raise ValueError('trajectory axis speed limits must be six integers within motor rating')
    for axis, (target, speed, value) in enumerate(zip(targets, speeds, acc), 1):
        if type(target) is not int or not -0x80000000 <= target <= 0x7FFFFFFF:
            raise ValueError('trajectory pulse target must fit signed int32')
        if type(speed) is not int or not 1 <= speed <= limits[axis]:
            raise ValueError('trajectory speed exceeds axis %d limit' % axis)
        if type(value) is not int or not 0 <= value <= 255:
            raise ValueError('trajectory acceleration must be 0..255, unchanged')
    return (seq, tuple(targets), tuple(speeds), tuple(acc), final)
