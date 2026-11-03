"""One physical KEY2 run, wheel settling, then the original full grasp task.

The local UI prepares a lease only. There is deliberately no remote wheel
start command. Wheel tests require the user to disconnect the PC first.
"""
import copy
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time

from . import grasp_motion
from .grasp_preview import COLORS, quantities

ENDPOINT = '/run/f3p-drive174-grasp.sock'


class DriveLease:
    def __init__(self, cancel, endpoint=ENDPOINT):
        self.token = secrets.token_hex(16)
        self.path = str(Path(endpoint).parent / ('f3p-mission-client-' + self.token + '.sock'))
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.settimeout(.25)
        self.lock = threading.Lock()
        self.ending = threading.Event()
        self.error = None
        self.worker = None
        self.cancel = cancel
        self.result = None
        self.updated = 0.0
        self.prepared_run_id = None
        try:
            self.socket.bind(self.path)
            os.chmod(self.path, 0o600)
            self.socket.connect(endpoint)
            self.result = self.command('prepare')
            if self.result['phase'] != 'READY' or not self.result.get('armed'):
                raise RuntimeError('行驶服务未进入准备状态')
            self.prepared_run_id = self.result['run_id']
            self.updated = time.monotonic()
            self.worker = threading.Thread(target=self._heartbeat, daemon=True)
            self.worker.start()
        except BaseException:
            # A timeout after prepare is stopped immediately if possible;
            # the board also expires its lease after 750 ms.
            self.close()
            raise

    def command(self, action):
        if action not in ('prepare', 'heartbeat', 'status', 'stop', 'finish'):
            raise ValueError('行走只允许板上KEY2启动')
        with self.lock:
            self.socket.send((self.token+' '+action).encode('ascii'))
            result = json.loads(self.socket.recv(1024).decode('ascii'))
        if not isinstance(result, dict) or not result.get('ok'):
            raise RuntimeError('174cm任务服务拒绝：'+str(result))
        if (result.get('phase') not in ('READY', 'RUN', 'WAIT', 'DONE', 'STOP', 'FAULT')
                or any(type(result.get(k)) is not int or result[k] < 0
                       for k in ('fault', 'grip_fault', 'run_id'))):
            raise RuntimeError('行驶服务返回了无效状态')
        return result

    def _heartbeat(self):
        while not self.ending.wait(.1):
            try:
                result = self.command('heartbeat')
                if result['fault'] or result['grip_fault'] or result['phase'] in ('FAULT', 'STOP'):
                    raise RuntimeError('行走或夹爪任务已停止：'+str(result))
                self.result = result
                self.updated = time.monotonic()
            except (OSError, RuntimeError, ValueError, KeyError) as error:
                self.error = error
                self.cancel()
                return

    def check(self):
        if self.error is not None:
            raise RuntimeError('组合任务已中断（KEY4/故障/通信）：'+str(self.error))
        if time.monotonic() - self.updated > .5:
            raise RuntimeError('行驶服务状态已过期')
        if self.result['phase'] in ('RUN', 'WAIT', 'DONE') and self.result['run_id'] != self.prepared_run_id + 1:
            raise RuntimeError('行走完成记录不属于本次任务')
        if self.result['fault'] or self.result['grip_fault'] or self.result['phase'] in ('STOP', 'FAULT'):
            raise RuntimeError('行走或夹爪任务已停止：'+str(self.result))
        return dict(self.result)

    def finish(self):
        self.check()
        self.ending.set()
        self.worker.join(timeout=.5)
        self.command('finish')

    def close(self, success=False):
        self.ending.set()
        if self.worker is not None:
            self.worker.join(timeout=.5)
        try:
            if not success:
                self.command('stop')
        except (OSError, RuntimeError, ValueError):
            pass
        finally:
            self.socket.close()
            try:
                Path(self.path).unlink()
            except FileNotFoundError:
                pass


def _preflight(task, params):
    if params.get('clearance_confirmed') is not True or params.get('use_gripper') is not True:
        raise RuntimeError('组合任务须确认区域安全并启用自动夹爪')
    requested = quantities(params['requested'])
    if not params['session'].running or getattr(params['session'], 'stopping', False):
        raise RuntimeError('先在板上开启识别，再准备174cm抓取任务')
    task.cartesian.require()
    if not task.controller.backend.supports_continuous_trajectory:
        raise RuntimeError('当前固件缺少原抓取任务需要的连续轨迹功能')
    reference = copy.deepcopy(task._reference(range(1,7)))
    # Query actual arm health/positions without moving, before arming wheels.
    task.cartesian.read_start()
    task._check()
    if not task.cartesian.ready():
        raise RuntimeError('机械臂零点和运动学参考尚未准备好')
    return requested, reference, params['session'].session_id


def run_sequence(task, params, lease_factory=DriveLease, clock=time.monotonic, sleep=time.sleep):
    requested, reference, session_id = _preflight(task, params)
    session, control = params['session'], params['control']
    publish = params.get('progress', lambda event: None)
    def check():
        task._check()
        if control.stopped.is_set():
            raise RuntimeError('组合任务已取消')
        if not session.running or getattr(session, 'stopping', False) or session.session_id != session_id:
            raise RuntimeError('识别会话改变，组合任务停止')
        if task._reference(range(1,7)) != reference or not task.cartesian.ready():
            raise RuntimeError('机械臂参考改变，组合任务停止')
    def event(label, stage):
        publish(dict(completed={c:0 for c in requested}, requested=requested, label=label, mission_stage=stage))
    lease = None
    success = False
    try:
        check()
        lease = lease_factory(task.cancel)
        event('已准备：断开电脑连接后，按板上KEY2开始174cm；KEY4停止', 'drive')
        deadline = clock()+600.0
        running = False
        while True:
            check()
            state = lease.check()
            if state.get('fault') or state.get('grip_fault') or state['phase'] in ('STOP','FAULT'):
                raise RuntimeError('行走停止，未启动抓取：'+str(state))
            if state['phase'] == 'DONE':
                if not state.get('run_id'):
                    raise RuntimeError('缺少有效的本轮行走完成记录')
                break
            if state['phase'] in ('RUN','WAIT') and not running:
                running = True
                event('小车正在前进174cm；到位停稳后自动开始原抓取任务', 'drive')
            if clock() >= deadline:
                raise RuntimeError('等待按键或行走超时，未启动抓取')
            sleep(.05)
        check()
        lease.check()
        event('174cm行走已停稳，开始原识别抓取与放盒任务', 'grasp')
        # This exact original function owns the single arm worker and gripper
        # lease, including close-hold, placing, and final return home.
        grasp_motion.execute(task, params)
        check()
        lease.check()
        lease.finish()
        success = True
    finally:
        if lease is not None:
            lease.close(success=success)


def execute(task, params):
    from .backend import MemoryMappedBackend
    if not isinstance(task.controller.backend, MemoryMappedBackend):
        raise RuntimeError('174cm后抓取须在板上MMIO模式运行，不会自动使用仿真代替')
    return run_sequence(task, params)
