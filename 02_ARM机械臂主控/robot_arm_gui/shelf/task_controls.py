"""Explicit idle task reset over the existing control service, never arm homing."""
import json
import os
from pathlib import Path
import secrets
import socket

from .shelf_transport import ENDPOINT


def _idle_reply(value):
    if (value.get('phase') not in ('READY','STOP','DONE') or value.get('owner') != ''
            or any(value.get(name) is not False for name in ('armed','motor_active','gripper_active'))
            or value.get('arm_idle') is not True):
        raise RuntimeError('请先停止任务，等待车轮、机械臂和夹爪空闲后再复位')
    if any(type(value.get(name)) is not int or value[name] != 0 for name in ('fault','grip_fault')):
        raise RuntimeError('故障未解除；任务复位不会自动清除硬件故障')


def reset_task(endpoint=ENDPOINT, timeout=.5):
    """Run on a worker thread. A status plus one guarded reset; no retries."""
    token=secrets.token_hex(16)
    path=str(Path(endpoint).parent/('shelf-reset-'+token+'.sock'))
    channel=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
    channel.settimeout(timeout)
    bound=False
    try:
        channel.bind(path);bound=True;os.chmod(path,0o600);channel.connect(endpoint)
        def exchange(text, ident, generation=None):
            channel.send((token+' '+text).encode('ascii'))
            value=json.loads(channel.recv(4096).decode('ascii'))
            if (not isinstance(value,dict) or value.get('ok') is not True or value.get('protocol')!=1
                    or value.get('request_owner')!=token or type(value.get('request_id')) is not int
                    or value['request_id']!=ident):
                raise RuntimeError('任务服务拒绝复位或回执不匹配')
            if generation is not None and value.get('generation')!=generation:
                raise RuntimeError('控制服务已重启，本次复位未确认')
            return value
        status=exchange('status',0)
        generation=status.get('generation')
        if (type(status.get('touch_control_version')) is not int or status['touch_control_version']<1
                or not isinstance(generation,str) or not generation.isdecimal()):
            raise RuntimeError('板端控制服务尚未升级触屏复位，请先安装匹配服务')
        _idle_reply(status)
        result=exchange('reset %s 1'%generation,1,generation)
        _idle_reply(result)
        if result['phase']!='READY':
            raise RuntimeError('服务尚未回到待机，复位未确认')
        return dict(result,reset_done=True)
    finally:
        channel.close()
        if bound:
            try:Path(path).unlink()
            except FileNotFoundError:pass
