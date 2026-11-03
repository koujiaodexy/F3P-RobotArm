"""ZDT X42S CAN frame definitions used by the Linux control panel."""

from __future__ import annotations

import struct
from dataclasses import dataclass


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


def absolute_position_frame(node: int, signed_pulses: int, speed: int,
                            acceleration: int = 50) -> CanFrame:
    """Emm FD: signed input pulses, absolute to the established motor zero.

    Input pulses depend on motor step/subdivision settings; they are NOT the
    65536-per-revolution units returned by the 36 position query.
    """
    motor_can_id(node)
    if node not in range(1, 7):
        raise ValueError('定位仅支持1～6号关节')
    if type(signed_pulses) is not int or abs(signed_pulses) > 0xFFFFFFFF:
        raise ValueError('目标脉冲数超出32位范围')
    if type(speed) is not int or not 1 <= speed <= HOME_MAX_SPEEDS_RPM[node]:
        raise ValueError('定位RPM超出已配置上限')
    if type(acceleration) is not int or not 1 <= acceleration <= 255:
        raise ValueError('定位加速度须为1～255')
    return CanFrame(motor_can_id(node), bytes([0xFD, int(signed_pulses < 0),
        speed >> 8, speed & 255, acceleration]) +
        abs(signed_pulses).to_bytes(4, 'big') + b'\x01\x00\x6b')


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
