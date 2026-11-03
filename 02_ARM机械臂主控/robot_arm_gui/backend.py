"""Transport backends for simulation, SocketCAN and the F3P PL register bridge."""

from __future__ import annotations

import socket
import struct
import threading
import ctypes
import mmap
import os
import time
from typing import Any, Callable, Dict

from .trajectory_transport import SimTrajectoryMixin, MMIOTrajectoryMixin
from .protocol import CAN_FRAME_FORMAT, HOME_MAX_SPEEDS_RPM, CanFrame, motor_can_id


FrameCallback = Callable[[CanFrame], None]
ErrorCallback = Callable[[str], None]
StatusCallback = Callable[[Dict[str, Any]], None]


class Backend:
    name = "backend"
    enable_delay = 0.5
    supports_zero_home = False
    supports_parallel_home = False
    supports_jog_deceleration = False
    supports_continuous_trajectory = False
    supports_position_targets = False
    position_target_nodes = (1, 2, 3, 4, 5)

    def __init__(self) -> None:
        self.on_frame: FrameCallback = lambda _frame: None
        self.on_error: ErrorCallback = lambda _message: None
        self.on_status: StatusCallback = lambda _status: None
        self.on_dispatched: FrameCallback = lambda _frame: None

    def connect(self) -> None:
        raise NotImplementedError

    def send(self, frame: CanFrame) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class SimulatedBackend(SimTrajectoryMixin, Backend):
    supports_continuous_trajectory = True
    name = "模拟 CAN"
    enable_delay = 0.0
    supports_zero_home = True
    supports_parallel_home = True
    supports_jog_deceleration = True
    supports_position_targets = True
    position_target_nodes = (1, 2, 3, 4, 5, 6)

    def __init__(self) -> None:
        super().__init__()
        self._trajectory_sim = None
        self._trajectory_sim_lock = threading.RLock()
        self.connected = False
        self.sent_frames: list[CanFrame] = []
        self.positions = {n: 0 for n in range(1, 7)}
        self.power_flags = {n: 0x80 for n in range(1, 7)}
        self.position_pulses_per_rev = {n: 3200 for n in range(1, 7)}

    def connect(self) -> None:
        self.connected = True

    def send(self, frame: CanFrame) -> None:
        if not self.connected:
            raise RuntimeError("simulation backend is not connected")
        if self._trajectory_sim and self._trajectory_sim['owned']:
            if frame.data and frame.data[0] == 0xFE:
                self.trajectory_cancel();return
            raise RuntimeError('连续轨迹独占通道；只允许停止')
        self.sent_frames.append(frame)
        function = frame.data[0] if frame.data else 0
        node = frame.can_id >> 8
        if function == 0x0A:
            self.positions[node] = 0
        if function == 0xFD:
            pulses = int.from_bytes(frame.data[5:9], 'big') * (-1 if frame.data[1] else 1)
            self.positions[node] = round(pulses * 65536 / self.position_pulses_per_rev[node])
        if function == 0x50:
            self.power_flags[node] = 0
        value = self.positions[node]
        replies = {
            0x1A: bytes.fromhex("1A 00 06 6B"),
            0xF3: bytes.fromhex("F3 02 6B"),
            0xF6: bytes.fromhex("F6 02 6B"),
            0xFE: bytes.fromhex("FE 02 6B"),
            0x0A: bytes.fromhex('0A 02 6B'),
            0x50: bytes.fromhex('50 02 6B'),
            0xFD: bytes.fromhex('FD 02 6B'),
            0x36: bytes([0x36, int(value < 0)]) + abs(value).to_bytes(4, 'big') + b'\x6b',
            0x3A: bytes([0x3A, self.power_flags[node] | 3, 0x6B]),
            0x3B: bytes.fromhex('3B 03 6B'),
        }
        if function in replies:
            self.on_frame(CanFrame(frame.can_id, replies[function], True))

    def close(self) -> None:
        self.connected = False


class SocketCanBackend(Backend):
    """Minimal raw SocketCAN backend for a future PS CAN or PS-to-PL bridge."""

    def __init__(self, interface: str) -> None:
        super().__init__()
        self.interface = interface
        self.name = f"SocketCAN {interface}"
        self._socket: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def connect(self) -> None:
        if not hasattr(socket, "AF_CAN"):
            raise RuntimeError("SocketCAN is available only on Linux")
        self._socket = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        self._socket.settimeout(0.2)
        self._socket.bind((self.interface,))
        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()

    def _receive_loop(self) -> None:
        assert self._socket is not None
        while self._running:
            try:
                raw = self._socket.recv(16)
            except TimeoutError:
                continue
            except OSError as exc:
                if self._running:
                    self.on_error(str(exc))
                return
            if len(raw) == 16:
                try:
                    self.on_frame(CanFrame.unpacked(raw))
                except (ValueError, struct.error) as exc:
                    self.on_error(f"invalid CAN frame: {exc}")

    def send(self, frame: CanFrame) -> None:
        if self._socket is None:
            raise RuntimeError("SocketCAN backend is not connected")
        raw = frame.packed()
        sent = self._socket.send(raw)
        if sent != 16:
            raise OSError(f"short CAN write: {sent} bytes")

    def close(self) -> None:
        self._running = False
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None


class MemoryMappedBackend(MMIOTrajectoryMixin, Backend):
    """Linux /dev/mem backend for the PL control window at 0xA0000000."""

    name = "PL MMIO 0xA0000000"
    BASE_ADDRESS = 0xA0000000
    MAP_SIZE = 0x1000
    MAGIC = 0x52414331

    REG_ID = 0x00
    REG_VERSION = 0x04
    REG_SPEED = 0x08
    REG_COMMAND = 0x0C
    REG_HEARTBEAT = 0x10
    REG_STATUS = 0x14
    REG_ERROR = 0x18
    REG_TX_COUNT = 0x1C
    REG_RX_COUNT = 0x20
    REG_RX_ID = 0x24
    REG_RX_META = 0x28
    REG_RX_DATA_LO = 0x2C
    REG_RX_DATA_HI = 0x30
    REG_ACCELERATION = 0x40
    REG_NODE = 0x44
    REG_ACTIVE_NODE = 0x48
    REG_COMMAND_ACK = 0x4C
    REG_POSITION_PULSES = 0x50
    REG_CAN_FLAGS = 0x3C

    CMD_ENABLE = 1
    CMD_DISABLE = 2
    CMD_RUN = 3
    CMD_STOP = 4
    CMD_CLEAR_ERROR = 5
    CMD_QUERY = 6
    CMD_POSITION_TARGET = 13

    def __init__(self, device: str = "/dev/mem") -> None:
        super().__init__()
        self.device = device
        self._fd: int | None = None
        self._map: mmap.mmap | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_rx_count = 0
        self._last_error = 0
        self._lock = threading.Lock()
        self._command_toggle = 0
        self._queued_frame = None
        self._pending_rx = None
        self._home_pending = None
        self.supports_home_dispatch = False
        self.supports_continuous_trajectory = False
        self._trajectory_final_queued = False
        self._trajectory_last_seq = 0
        self._trajectory_control_toggle = None
        self._trajectory_lease_valid = False

    def _read32(self, offset: int) -> int:
        if self._map is None:
            raise RuntimeError("MMIO backend is not connected")
        if offset % 4:
            raise ValueError("MMIO register offset must be 32-bit aligned")
        return ctypes.c_uint32.from_buffer(self._map, offset).value

    def _write32(self, offset: int, value: int) -> None:
        if self._map is None:
            raise RuntimeError("MMIO backend is not connected")
        if offset % 4:
            raise ValueError("MMIO register offset must be 32-bit aligned")
        # This is a device register, not a byte buffer. On the board's Python
        # build pack_into can issue multiple stores for one command, leaving the
        # hardware toggle unchanged while software expects one acknowledgement.
        # A native uint32 assignment issues the aligned word access verified on
        # hardware. Do not retain a buffer view, so close() can unmap safely.
        ctypes.c_uint32.from_buffer(self._map, offset).value = value & 0xFFFFFFFF

    def connect(self) -> None:
        self._fd = os.open(self.device, os.O_RDWR | os.O_SYNC)
        try:
            self._map = mmap.mmap(
                self._fd,
                self.MAP_SIZE,
                flags=mmap.MAP_SHARED,
                prot=mmap.PROT_READ | mmap.PROT_WRITE,
                offset=self.BASE_ADDRESS,
            )
            magic = self._read32(self.REG_ID)
            if magic != self.MAGIC:
                raise RuntimeError(
                    f"PL register ID mismatch: expected 0x{self.MAGIC:08X}, "
                    f"read 0x{magic:08X}; check the loaded bitstream"
                )
            version = self._read32(self.REG_VERSION)
            if version not in (0x00020001, *range(0x00030001, 0x0003000B)):
                raise RuntimeError(f"unsupported PL register version 0x{version:08X}")
            self.supports_zero_home = version in range(0x00030001, 0x0003000B)
            self.supports_home_dispatch = version in range(0x00030002, 0x0003000B)
            self.supports_ratio_home_speed = version in range(0x00030004, 0x0003000B)
            self.supports_parallel_home = version in range(0x00030006, 0x0003000B)
            self.supports_jog_deceleration = version in (0x00030007, 0x00030008, 0x00030009,0x0003000A)
            self.supports_position_targets = version in (0x00030008, 0x00030009,0x0003000A)
            self.position_target_nodes = tuple(range(1, 7 if version >= 0x00030009 else 6))
            # Legacy V9 shares the version number but has no FIFO registers.
            self.supports_continuous_trajectory = version in (0x00030009,0x0003000A) and self._read32(self.TR_CAPACITY) == 32
            from .protocol import HOME_MAX_SPEEDS_RPM
            from .axis_speed import V10_TRAJECTORY_RPM
            self.trajectory_speed_limits=dict(V10_TRAJECTORY_RPM if version==0x0003000A else HOME_MAX_SPEEDS_RPM)
            self._trajectory_control_toggle = ((self._read32(self.TR_CONTROL_ACK)>>1)&1) if self.supports_continuous_trajectory else None
            self._command_toggle = self._read32(self.REG_COMMAND_ACK) & 1
            self._last_rx_count = self._read32(self.REG_RX_COUNT)
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
        except Exception:
            self.close()
            raise

    def send(self, frame: CanFrame) -> None:
        node = frame.can_id >> 8
        if not frame.extended or frame.can_id != motor_can_id(node):
            raise ValueError("invalid six-motor CAN address")
        if not frame.data:
            raise ValueError("empty CAN payload")
        with self._lock:
            if self.supports_continuous_trajectory and self._read32(self.TR_STATUS) & 1:
                if frame.data[0] == 0xFE:
                    self._trajectory_control_locked(3);return
                raise RuntimeError('连续轨迹独占通道；只允许停止')
            # Hold command parameters until the destination clock acknowledges
            # the toggle. STOP may replace a command not yet dispatched.
            if (self._read32(self.REG_COMMAND_ACK) & 1) != self._command_toggle:
                if self._queued_frame is not None and frame.data[0] != 0xFE:
                    raise RuntimeError("MMIO command mailbox is occupied")
                self._queued_frame = frame
                return
            self._dispatch(frame)

    def _dispatch(self, frame: CanFrame) -> None:
        function = frame.data[0]
        if self._read32(self.REG_STATUS) & 1 and function != 0xFE:
            raise RuntimeError("PL 引擎忙；只有停止可以抢占")
        if function == 0x1A and frame.data == bytes.fromhex("1A 6B"):
            command = self.CMD_QUERY
        elif function == 0xF3 and len(frame.data) == 5:
            command = self.CMD_ENABLE if frame.data[2] else self.CMD_DISABLE
        elif function == 0xF6 and len(frame.data) == 7:
            self._write32(self.REG_SPEED, (frame.data[2] << 8) | frame.data[3])
            self._write32(self.REG_ACCELERATION, frame.data[4])
            command = self.CMD_RUN | (int(bool(frame.data[1])) << 8)
        elif function == 0xFE and len(frame.data) == 4:
            command = self.CMD_STOP
        elif self.supports_zero_home and frame.data in (b'\x0a\x6d\x6b', b'\x36\x6b',
                b'\x3b\x6b', b'\x3a\x6b', b'\x50\x00\x6b'):
            command = {0x0A: 7, 0x36: 8, 0x3B: 9, 0x3A: 11, 0x50: 12}[function]
        elif self.supports_zero_home and function == 0xFD and len(frame.data) == 12:
            pulses = int.from_bytes(frame.data[5:9], 'big')
            nonzero = pulses != 0 or frame.data[1] != 0
            if frame.data[1] not in (0, 1) or frame.data[9:] != b'\x01\x00\x6b':
                raise ValueError('PL只支持立即执行的绝对位置命令')
            if nonzero and (not self.supports_position_targets or frame.can_id >> 8 not in self.position_target_nodes):
                raise ValueError('J1～J5 非零定位需要 MMIO v8；J6 定位需要 MMIO v9')
            speed = int.from_bytes(frame.data[2:4], 'big')
            limit = HOME_MAX_SPEEDS_RPM.get(frame.can_id >> 8, 0)
            if not getattr(self, "supports_ratio_home_speed", False):
                limit = min(limit, 30)
            if not 1 <= speed <= limit or not 1 <= frame.data[4] <= 255:
                raise ValueError('回零参数超出范围')
            self._write32(self.REG_SPEED, speed)
            self._write32(self.REG_ACCELERATION, frame.data[4])
            if nonzero:
                self._write32(self.REG_POSITION_PULSES, pulses)
                command = self.CMD_POSITION_TARGET | (frame.data[1] << 8)
            else:
                command = 10  # Preserve the original, hard-coded home path.
        else:
            raise ValueError(f"unsupported PL command function 0x{function:02X}")
        self._write32(self.REG_NODE, frame.can_id >> 8)
        self._home_pending = frame if command & 0xF in (10, self.CMD_POSITION_TARGET) else None
        self._write32(self.REG_COMMAND, command)
        self._command_toggle ^= 1
        # Read replies promptly during a transaction burst; retain low idle CPU.
        self._fast_poll_until = time.monotonic() + 0.2

    def _poll_loop(self) -> None:
        next_heartbeat = 0.0
        while self._running:
            try:
                now = time.monotonic()
                if now >= next_heartbeat:
                    with self._lock:
                        self._write32(self.REG_HEARTBEAT, 1)
                    next_heartbeat = now + 0.1

                if self.supports_continuous_trajectory and self._read32(self.TR_STATUS) & 1:
                    time.sleep(0.02)
                with self._lock:
                    if self.supports_continuous_trajectory and self._read32(self.TR_STATUS) & 1:
                        # The execution worker alone renews the independent FIFO lease.
                        continue
                    acknowledged = (self._read32(self.REG_COMMAND_ACK) & 1) == self._command_toggle
                    if acknowledged and self._queued_frame is not None:
                        queued, self._queued_frame = self._queued_frame, None
                        self._dispatch(queued)
                        acknowledged = False
                status = self._read32(self.REG_STATUS)
                error_code = self._read32(self.REG_ERROR)
                tx_count = self._read32(self.REG_TX_COUNT)
                rx_count = self._read32(self.REG_RX_COUNT)
                self.on_status(
                    {
                        "node": self._read32(self.REG_ACTIVE_NODE),
                        "busy": bool(status & 0x01) or not acknowledged,
                        "enabled": bool(status & 0x02),
                        "moving": bool(status & 0x04),
                        "error": bool(status & 0x08),
                        "watchdog_stop": bool(status & 0x10),
                        "state_code": (status >> 5) & 0x0F,
                        "error_code": error_code,
                        "tx_count": tx_count,
                        "rx_count": rx_count,
                        "command_ack": self._read32(self.REG_COMMAND_ACK) & 1,
                        "can_flags": self._read32(self.REG_CAN_FLAGS),
                    }
                )
                if rx_count != self._last_rx_count:
                    can_id = self._read32(self.REG_RX_ID) & 0x1FFFFFFF
                    meta = self._read32(self.REG_RX_META)
                    dlc = min(meta & 0x0F, 8)
                    raw = struct.pack(
                        "<II",
                        self._read32(self.REG_RX_DATA_LO),
                        self._read32(self.REG_RX_DATA_HI),
                    )
                    if self._read32(self.REG_RX_COUNT) == rx_count:
                        self._last_rx_count = rx_count
                        self._pending_rx = CanFrame(can_id, raw[:dlc], bool(meta & 0x10))
                # Replies are latched only by the runtime's matching transaction.
                # Wait for idle before allowing a callback to dispatch a successor.
                if self._pending_rx is not None and acknowledged and not (status & 1):
                    reply, self._pending_rx = self._pending_rx, None
                    if reply.data[0] == 0xFD:
                        self._home_pending = None
                    self.on_frame(reply)
                dispatched = None
                with self._lock:
                    current_status = self._read32(self.REG_STATUS)
                    if (self.supports_home_dispatch and self._home_pending is not None
                            and (self._read32(self.REG_COMMAND_ACK) & 1) == self._command_toggle
                            and self._read32(self.REG_COMMAND) & 0xF in (10, self.CMD_POSITION_TARGET)
                            and self._read32(self.REG_ACTIVE_NODE) == self._home_pending.can_id >> 8
                            and current_status & 4 and not current_status & 9):
                        dispatched, self._home_pending = self._home_pending, None
                if dispatched is not None:
                    self.on_dispatched(dispatched)
                if (status & 0x08) and error_code != self._last_error:
                    self._last_error = error_code
                    print('PL_TRANSACTION_FAILURE', dict(error=f'0x{error_code:08X}',
                        node=self._read32(self.REG_ACTIVE_NODE), command=self._read32(self.REG_COMMAND),
                        status=f'0x{status:08X}', tx_count=tx_count, rx_count=rx_count,
                        rx_id=f'0x{self._read32(self.REG_RX_ID):08X}',
                        rx_data=f'{self._read32(self.REG_RX_DATA_LO):08X} {self._read32(self.REG_RX_DATA_HI):08X}'), flush=True)
                    # The shared controller times out its own addressed transaction.
                    # A stale global PL error must not fail the next node command.
                    pass
                elif not (status & 0x08):
                    self._last_error = 0
            except Exception as exc:
                if self._running:
                    self.on_error(str(exc))
                return
            time.sleep(0.005 if time.monotonic() < getattr(self, '_fast_poll_until', 0) else 0.05)

    def close(self) -> None:
        self._running = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=0.5)
        self._thread = None
        if self._map is not None:
            self._map.close()
            self._map = None
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
