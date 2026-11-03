"""Generation-bound UNIX datagram lease for the single wheel/gripper owner.

Preparing never starts wheels. A prepared owner can explicitly start by touch,
or physical KEY2 can start the same prepared mission.
On uncertainty cancel the arm worker and let the independent 750ms owner lease
expire. No command is retried: duplicate replies cannot acknowledge new work.
"""
import json
import math
import os
from pathlib import Path
import secrets
import socket
import threading
import time

ENDPOINT = '/run/f3p-drive174-grasp.sock'


class ShelfLease:
    def __init__(self, cancel, endpoint=ENDPOINT, clock=time.monotonic):
        self.cancel, self.clock = cancel, clock
        self.token = secrets.token_hex(16)
        self.path = str(Path(endpoint).parent / ('shelf-client-'+self.token+'.sock'))
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        # Initial status is read-only and owns no actuator lease; allow startup
        # scheduling. All prepared commands still use the short .2 s deadline.
        self.socket.settimeout(1.)
        self.lock = threading.RLock()
        self.ending = threading.Event()
        self.worker = None
        self.error = None
        self.sequence = 0
        self.generation = None
        self.result = None
        self.closed = False
        self.prepared = False
        self.touch_supported = False
        try:
            self.socket.bind(self.path)
            os.chmod(self.path, 0o600)
            self.socket.connect(endpoint)
            result = self._exchange('status', 0)
            if result.get('protocol') != 1 or not isinstance(result.get('generation'), str):
                raise RuntimeError('多货架控制服务未安装')
            self.generation = result['generation']
            self.touch_supported = type(result.get('touch_control_version')) is int and result['touch_control_version'] >= 1
            if (not self.generation.isdecimal() or result.get('armed') is not False
                    or result.get('owner') != '' or result.get('phase') not in ('READY','STOP','DONE')):
                raise RuntimeError('请先停止当前任务，再准备货架任务')
            if any(type(result.get(name)) is not int or result[name] != 0 for name in ('fault','grip_fault')):
                raise RuntimeError('车轮或夹爪故障未解除，不能准备任务')
            if any(result.get(name) is not False for name in ('motor_active','gripper_active')):
                raise RuntimeError('车轮或夹爪输出未停止，不能准备任务')
            if (type(result.get('motor_max_pwm')) is not int or type(result.get('turn_pwm')) is not int
                    or result['motor_max_pwm']<result['turn_pwm']):
                raise RuntimeError('当前FPGA不支持包内转弯PWM，请先安装匹配固件')
            self.socket.settimeout(.2)
        except BaseException:
            self.close()
            raise

    def _exchange(self, text, request_id):
        self.socket.send((self.token+' '+text).encode('ascii'))
        raw = self.socket.recv(4096)
        value = json.loads(raw.decode('ascii'))
        if (not isinstance(value, dict) or value.get('ok') is not True or value.get('protocol') != 1
                or value.get('request_owner') != self.token or type(value.get('request_id')) is not int
                or value['request_id'] != request_id):
            raise RuntimeError('任务服务拒绝指令或回执不匹配')
        if self.generation is not None and value.get('generation') != self.generation:
            raise RuntimeError('控制服务已重启，取消本次任务')
        return value

    def command(self, verb, *args):
        if verb not in ('prepare','start','next','brake','lock','heartbeat','finish'):
            raise ValueError('Unsupported shelf command')
        with self.lock:
            self.sequence += 1
            if self.sequence > 0xffffffff:
                raise RuntimeError('任务序号耗尽')
            text = 'shelf %s %d %s' % (self.generation,self.sequence,verb)
            if args:
                text += ' '+' '.join(str(a) for a in args)
            result = self._exchange(text, self.sequence)
            if verb != 'finish':
                self._validate(result)
            self.result = result
            return dict(result)

    def _validate(self, s):
        if (s.get('owner') != self.token or s.get('armed') is not True or s.get('shelf_mode') is not True
                or s.get('phase') not in ('READY','RUN','WAIT','DONE')):
            raise RuntimeError('多货架任务控制权失效或已经停止')
        for name in ('fault','grip_fault','shelf_command_id','measured_ms','quiet_ms','run_id'):
            if type(s.get(name)) is not int or s[name]<0:
                raise RuntimeError('无效的控制状态：'+name)
        for name in ('shelf_started','shelf_arm_lock','imu_ready','arm_idle','gripper_active','motor_active'):
            if type(s.get(name)) is not bool:
                raise RuntimeError('缺少控制状态：'+name)
        if s['fault'] or s['grip_fault']:
            raise RuntimeError('车轮或夹爪故障')
        if not 0 <= self.clock()-s['measured_ms']/1000. <= .2:
            raise RuntimeError('板端采样已过期')
        odometry=s.get('odo_mm_lr')
        if (not isinstance(odometry,list) or len(odometry)!=2 or
                any(type(v) not in (int,float) or not math.isfinite(v) for v in odometry)):
            raise RuntimeError('无效的累计编码器里程')

    def prepare(self, action):
        if self.prepared or action.get('kind') != 'drive':
            raise RuntimeError('初始准备必须是第一段直行')
        self.prepared = True  # An ambiguous prepare timeout must send stop.
        self.command('prepare',action['id'],0,action['distance_mm'],0)
        self.worker = threading.Thread(target=self._heartbeat,daemon=True,name='shelf-lease')
        self.worker.start()

    def _heartbeat(self):
        while not self.ending.wait(.08):
            try:
                self.command('heartbeat')
            except Exception as error:
                self.error = error
                self.cancel()
                return

    def check(self):
        if self.error is not None:
            raise RuntimeError('多货架任务失联或停止：'+str(self.error))
        with self.lock:
            if self.result is None:
                raise RuntimeError('任务尚未准备')
            self._validate(self.result)
            return dict(self.result)

    def move(self, action):
        self.check()
        kind=action['kind']
        if kind=='drive':args=(0,action['distance_mm'],0)
        elif kind=='turn':args=(1,action['left_deg'],0)
        elif kind=='creep':args=(2,action['max_mm'],action['speed_mm_s'])
        else:raise ValueError('Unsupported wheel intent')
        return self.command('next',action['id'],*args)

    def start(self):
        """One explicit start, serialized with heartbeats; never retry motion."""
        with self.lock:
            if not self.prepared or self.closed or self.ending.is_set() or not self.touch_supported:
                raise RuntimeError('任务未准备或当前服务不支持触屏启动')
            self.check()
            state = self.command('heartbeat')
            if state['shelf_started']:
                return state  # KEY2 won the race; do not send another start.
            if (state['phase'] != 'READY' or state['quiet_ms'] < 250 or not state['imu_ready']
                    or not state['arm_idle'] or state['motor_active'] or state['gripper_active']
                    or state['shelf_arm_lock']):
                raise RuntimeError('启动条件未满足：检查任务、机械臂收回、IMU和车轮停稳状态')
            try:
                return self.command('start')
            except RuntimeError:
                # KEY2 can win between the fresh heartbeat and start packet.
                # A read-only status can recognize that same owned mission;
                # no motion command is retried after an uncertain result.
                state = self._exchange('status', 0)
                self._validate(state)
                if not state['shelf_started']:
                    raise
                self.result = state
                return dict(state)

    def brake(self, action_id):
        return self.command('brake',action_id)

    def arm_lock(self, locked):
        return self.command('lock',int(locked))

    def finish(self):
        self.check()
        self.ending.set()
        if self.worker is not None:self.worker.join(timeout=.5)
        self.command('finish')

    def close(self, success=False):
        if self.closed:return
        self.closed = True
        self.ending.set()
        if self.worker is not None and self.worker is not threading.current_thread():
            self.worker.join(timeout=.5)
        try:
            if self.prepared and not success:
                with self.lock:self.socket.send((self.token+' stop').encode('ascii'))
        except OSError:
            pass
        finally:
            self.socket.close()
            try:Path(self.path).unlink()
            except FileNotFoundError:pass
