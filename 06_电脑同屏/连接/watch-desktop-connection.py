"""Keep the existing authenticated desktop connection alive while this PC runs."""
import contextlib
import importlib.util
import io
import json
import msvcrt
import os
import sys
import time
from pathlib import Path

spec=importlib.util.spec_from_file_location('desktop_reconnect',Path(__file__).with_name('reconnect-desktop-mirror.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
camera_spec=importlib.util.spec_from_file_location('camera_reconnect',Path(__file__).with_name('reconnect-camera-preview.py'))
camera=importlib.util.module_from_spec(camera_spec)
camera_spec.loader.exec_module(camera)

def ensure_connections():
    status={}
    for name,healthy,reconnect in (
        ('desktop',lambda:module.rfb_ready() and module.health(),module.main),
        ('camera',camera.health,camera.main),
    ):
        try:
            if not healthy():
                with contextlib.redirect_stdout(io.StringIO()):reconnect()
            status[name+'_ready']=True
        except Exception as exc:
            status[name+'_ready']=False;status[name+'_error']=str(exc)
    status['ready']=status['desktop_ready'] and status['camera_ready']
    return status

def main():
    folder=module.STATE
    if not (folder/'desktop_ed25519').is_file():
        raise RuntimeError('Desktop identity unavailable: '+str(folder))
    with (folder/'watchdog.lock').open('a+b') as lock:
        lock.seek(0)
        if lock.read(1)==b'':lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        sys.argv=[str(Path(__file__)),'--no-browser']
        previous=None
        while True:
            status=ensure_connections()
            if status!=previous:
                (folder/'watchdog-status.json').write_text(json.dumps(dict(status,pid=os.getpid(),time=time.time()),indent=2),encoding='utf-8')
                previous=status
            time.sleep(5)

if __name__=='__main__':main()
