"""IPC to the sole wheel/OLED/gripper owner; never opens /dev/mem."""
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time

ENDPOINT = '/run/f3p-key-console.sock'
STATUS = Path('/run/f3p-key-console-status.json')


def read_status(path=STATUS):
    try:
        if time.time()-path.stat().st_mtime > 2:
            raise ValueError('小车控制服务状态已过期')
        return json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError) as error:
        return dict(available=False, error=str(error))


class ConsoleClient:
    def __init__(self, endpoint=ENDPOINT):
        self.token = secrets.token_hex(16)
        self.path = str(Path(endpoint).parent/('f3p-client-'+self.token+'.sock'))
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.settimeout(.2)
        try:
            self.socket.bind(self.path)
            os.chmod(self.path, 0o600)
            self.socket.connect(endpoint)
        except BaseException:
            self.close()
            raise
        self.lock = threading.Lock()

    def command(self, action):
        with self.lock:
            self.socket.send((self.token+' '+action).encode('ascii'))
            reply = self.socket.recv(128).decode('ascii').split()
            if len(reply) != 4 or reply[0] != 'OK':
                raise RuntimeError('小车/夹爪服务拒绝操作：'+' '.join(reply))
            return dict(fault=int(reply[1]), phase=int(reply[2]), settled=bool(int(reply[3])))

    def close(self):
        self.socket.close()
        try:
            Path(self.path).unlink()
        except FileNotFoundError:
            pass


def emergency_stop(endpoint=ENDPOINT):
    """One stopped command; no hardware probing, installation or activation."""
    client = None
    try:
        client = ConsoleClient(endpoint)
        client.command('stop')
        return True
    except (OSError, RuntimeError, ValueError):
        return False
    finally:
        if client is not None:
            client.close()


def request_stop():
    threading.Thread(target=emergency_stop, daemon=True).start()


class GripperLease:
    def __init__(self, cancel, endpoint=ENDPOINT):
        self.client = ConsoleClient(endpoint)
        self.error = None
        self.ending = threading.Event()
        self.cancel = cancel
        # Serialize command transitions with heartbeat validation so an open
        # cannot be mistaken for an unexpected loss of the preceding hold.
        self.state_lock = threading.RLock()
        self.holding = False
        # This records our acknowledged command in this exclusive lease,
        # not measured jaw position. A new lease must always open once.
        self._open_completed = False
        try:
            self.client.command('acquire')
        except BaseException:
            self.client.close()
            raise
        self.worker = threading.Thread(target=self._heartbeat, daemon=True)
        self.worker.start()

    def _heartbeat(self):
        while not self.ending.wait(.1):
            try:
                self._ping()
            except (OSError, ValueError, RuntimeError) as error:
                self.error = RuntimeError('夹爪占用已中断（KEY4/故障/服务断开）：'+str(error))
                self.cancel()
                return

    def check(self):
        if self.error is not None:
            with self.state_lock:
                self._open_completed = False
            raise self.error
        if self.ending.is_set():
            with self.state_lock:
                self._open_completed = False
            raise RuntimeError('夹爪占用已结束')

    @staticmethod
    def _validate(result, holding=False):
        if result['fault']:
            raise RuntimeError('夹爪控制故障 F%d' % result['fault'])
        if holding and (result['phase'] != 2 or not result['settled']):
            raise RuntimeError('夹爪闭合保持已丢失，停止搬运；请检查PWM输出与舵机供电')

    def _ping(self):
        with self.state_lock:
            try:
                result = self.client.command('ping')
                self._validate(result, self.holding)
            except BaseException:
                self._open_completed = False
                raise
            if result['phase'] != 0 or not result['settled']:
                self._open_completed = False
            return result

    def ensure_open(self, check):
        """Reuse this lease's completed open only after a live owner check.

        Explicit move('open') still starts a full opening dwell, including at
        every placement. Return whether the pre-pick opening was reused.
        """
        check()
        self.check()
        with self.state_lock:
            reusable = self._open_completed
            if reusable:
                self._ping()  # Invalidates the cache on changed state/errors.
                reusable = self._open_completed
        if not reusable:
            self.move('open', check)
        check()
        self.check()
        return reusable

    def move(self, action, check):
        self._move(action, check)

    def open_and_prepare(self, check, prepare):
        """Run pure next-item work during this placement's existing open dwell.

        The caller stays on its sole task thread, defers preparation errors,
        and must use the supplied deadline check during its bounded work.
        No completed-open state is shared with another lease.
        """
        return self._move('open', check, prepare)

    def _move(self, action, check, prepare=None):
        self.check()
        if action not in ('open', 'close'):
            raise ValueError('Unknown gripper command')
        with self.state_lock:
            self._open_completed = False
            result = self.client.command(action)
            self._validate(result)
            self.holding = False
        deadline = time.monotonic()+3.0
        overlap_seconds = 0.0
        if prepare is not None:
            check()
            confirmed = [False]
            def overlap_check():
                self.check()
                # Pure planning must not silently extend an unacknowledged
                # open command beyond the same original three-second limit.
                if not confirmed[0] and time.monotonic() >= deadline:
                    with self.state_lock:
                        state = self._ping()
                        if not state['settled']:
                            raise RuntimeError('夹爪命令未按时确认')
                        if state['phase'] != 0:
                            raise RuntimeError('夹爪张开完成状态无效')
                        confirmed[0] = True
            began = time.monotonic()
            prepare(overlap_check)
            overlap_seconds = time.monotonic()-began
        wait_began = time.monotonic() if prepare is not None else None
        while True:
            check()
            self.check()
            with self.state_lock:
                result = self._ping()
                if result['settled']:
                    self._validate(result, action == 'close')
                    if action == 'open' and result['phase'] != 0:
                        raise RuntimeError('夹爪张开完成状态无效')
                    self.holding = action == 'close'
                    self._open_completed = action == 'open'
                    if prepare is not None:
                        return dict(overlap_seconds=overlap_seconds,
                                    remaining_wait_seconds=time.monotonic()-wait_began)
                    return
            if time.monotonic() >= deadline:
                raise RuntimeError('夹爪命令未按时确认')
            self.ending.wait(.02)

    def close(self):
        self.ending.set()
        with self.state_lock:
            self._open_completed = False
        self.worker.join(timeout=.5)
        try:
            self.client.command('release')
        except (OSError, RuntimeError, ValueError):
            pass
        finally:
            self.client.close()


class SimulatedGripper:
    """Explicit simulation; no sockets or real outputs."""
    def __init__(self):
        self._open_completed = False
        self._closed = False

    def check(self):
        if self._closed:
            raise RuntimeError('夹爪占用已结束')

    def move(self, action, check):
        check()
        self.check()
        self._open_completed = action == 'open'

    def open_and_prepare(self, check, prepare):
        # Preserve subclasses' explicit command bookkeeping. There is no
        # real dwell or hardware activity in this simulation.
        self.move('open', check)
        began = time.monotonic()
        prepare(self.check)
        check()
        return dict(overlap_seconds=time.monotonic()-began, remaining_wait_seconds=0.0)

    def ensure_open(self, check):
        check()
        self.check()
        reusable = self._open_completed
        if not reusable:
            self.move('open', check)
        check()
        self.check()
        return reusable

    def close(self):
        self._closed = True
        self._open_completed = False
