"""Bounded scheduling support for the existing single-owner motion worker.

No heartbeat thread, watchdog extension, or device access is introduced here.
The FPGA still stops if the actual checked execution loop stops progressing.
"""
from contextlib import contextmanager
import gc
import os
import sys
import threading


@contextmanager
def execution_runtime():
    enabled=gc.isenabled();tid=None;priority=None;changed=False
    if enabled:gc.disable()
    try:
        if sys.platform.startswith('linux') and hasattr(os,'setpriority'):
            tid=threading.get_native_id()
            try:
                priority=os.getpriority(os.PRIO_PROCESS,tid)
                if priority>-5:
                    os.setpriority(os.PRIO_PROCESS,tid,-5);changed=True
            except OSError:
                # Unprivileged simulation keeps normal scheduling; protection
                # and cancellation remain active regardless of priority.
                pass
        yield
    finally:
        try:
            if changed:os.setpriority(os.PRIO_PROCESS,tid,priority)
        finally:
            if enabled:gc.enable()


def fault_message(status):
    code=int(status.get('error') or status.get('fault') or 0)
    label='心跳超时' if code==0xFFFF3101 else '控制器故障'
    text='FPGA 连续轨迹故障：%s (0x%08X)'%(label,code)
    if status.get('heartbeat_gap_ms') is not None:
        text+='，本次心跳间隔%.1f毫秒'%status['heartbeat_gap_ms']
    text+='，已执行帧%s/已接收帧%s，队列%s'%(status.get('fired_seq','?'),status.get('accepted_seq','?'),status.get('fifo_count','?'))
    return text
