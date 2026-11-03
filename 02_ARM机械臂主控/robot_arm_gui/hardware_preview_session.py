"""Own one camera-only child; exchange bounded JSON and preserve motor ownership."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

from .color_blocks import BlockParameters, DEFAULT_BANDS, validate_bands

CAMERA_APP = Path('/opt/f3p-control-candidates/osd-engineering-trial-20261019/app/direct_preview.py')


def read_json(path, limit=262144):
    if not path.is_file() or path.stat().st_size > limit:
        return None
    try:
        return json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError):
        return None


class HardwarePreviewSession:
    def __init__(self, entrypoint=CAMERA_APP, runtime=None, popen=subprocess.Popen, clock=time.monotonic):
        self.entrypoint = Path(entrypoint)
        if runtime is None:
            runtime = Path('/run/f3p-console-preview') if os.name == 'posix' and os.geteuid() == 0 else Path(tempfile.gettempdir()) / 'f3p-console-preview'
        self.runtime = Path(runtime)
        self._popen, self.clock = popen, clock
        self.process = self.log = None
        self.telemetry = self.final = None
        self.error = ''
        self._stop_at = None
        self._stop_delivered = False
        self._returncode = None
        self._preview_signature = None
        self._preview_stamp = 0.

    @property
    def running(self):
        # Keep ownership until poll has consumed the final report and closed log.
        return self.process is not None

    def start(self, parameters=None, bands=None):
        if self.running:
            return False
        parameters = (parameters or BlockParameters()).validate()
        bands = validate_bands(bands or DEFAULT_BANDS)
        if not self.entrypoint.is_file():
            raise RuntimeError('硬件预览尚未安装，请检查相机程序。')
        self.runtime.mkdir(parents=True, mode=0o700, exist_ok=True)
        if os.name == 'posix':
            meta = self.runtime.stat()
            if meta.st_uid != os.geteuid() or meta.st_mode & 0o077:
                raise RuntimeError('相机会话目录权限无效')
        self.session_id = uuid.uuid4().hex
        self.directory = self.runtime / self.session_id
        self.directory.mkdir(mode=0o700)
        self.status_path, self.report_path = self.directory / 'status.json', self.directory / 'report.json'
        self.preview_path = self.directory / 'preview.jpg'
        self.window_path = self.directory / 'window.json'
        self._preview_signature = None
        self._preview_stamp = 0.
        profile_path = self.directory / 'profile.json'
        profile_path.write_text(json.dumps({'schema': 1, 'parameters': asdict(parameters), 'bands': bands}), encoding='utf8')
        self.log = (self.directory / 'preview.log').open('w', encoding='utf8')
        self.telemetry = self.final = None
        self.error = ''
        self._stop_at = None
        self._stop_delivered = False
        self._returncode = None
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        try:
            self.process = self._popen([sys.executable, str(self.entrypoint),
                '--profile', str(profile_path), '--status-file', str(self.status_path),
                '--report', str(self.report_path), '--session-id', self.session_id,
                '--window-file', str(self.window_path),
                '--parent-pid', str(os.getpid())], stdin=subprocess.DEVNULL,
                stdout=self.log, stderr=subprocess.STDOUT, close_fds=True, env=env)
        except BaseException:
            self.log.close()
            self.log = None
            raise
        return True

    def set_window(self, x=0, y=0, visible=False, width=384, height=216):
        """Refresh only geometry and visibility; FPGA supplies the image."""
        if not self.running:
            return
        if (type(width) is not int or type(height) is not int or width%192
                or not 2<=width//192<=8 or height!=108*(width//192)):
            raise ValueError('Invalid hardware preview size')
        if type(x) is not int or type(y) is not int or not 0 <= x <= 1920-width or not 0 <= y <= 1080-height:
            raise ValueError('Invalid hardware preview position')
        value={'session_id': self.session_id, 'timestamp': self.clock(),
               'x': x, 'y': y, 'width':width,'height':height,'visible': bool(visible)}
        temp=self.window_path.with_name('window.pending')
        temp.write_text(json.dumps(value),encoding='utf8')
        temp.replace(self.window_path)

    def read_preview(self):
        """Return only a new complete JPEG; the producer atomically replaces it."""
        if not self.running or not hasattr(self, 'preview_path'):
            return None
        try:
            meta = self.preview_path.stat()
            signature = (meta.st_mtime_ns, meta.st_size, meta.st_ino)
            if signature == self._preview_signature or not 4 <= meta.st_size <= 524288:
                return None
            data = self.preview_path.read_bytes()
            if not 4 <= len(data) <= 524288 or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
                return None
            self._preview_signature = signature
            self._preview_stamp = self.clock()
            return data
        except OSError:
            return None

    def preview_fresh(self):
        return self.running and self._preview_stamp > 0 and self.clock() - self._preview_stamp < 1.2

    def stop(self):
        if self.process is not None and self._stop_at is None:
            self._stop_at = self.clock()
            if self.process.poll() is None:
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    pass

    def poll(self):
        """Return a motor-stop request once; caller supplies the existing callback."""
        if self.process is None:
            return False
        value = read_json(self.status_path)
        request_stop = False
        if isinstance(value, dict) and value.get('session_id') == self.session_id:
            request_stop = bool(value.get('motor_stop_requested')) and not self._stop_delivered
            self._stop_delivered |= request_stop
            if self.clock() - value.get('timestamp', 0.) > 1.2:
                value = dict(value, fresh=False, targets=[], counts={c: 0 for c in DEFAULT_BANDS})
            self.telemetry = value
        code = self.process.poll()
        if code is None and self._stop_at is not None and self.clock() - self._stop_at > 7:
            self.process.kill()
            self.error = '相机退出超时，已结束预览进程；正在恢复桌面。'
        if code is not None:
            self.final = read_json(self.report_path)
            if not isinstance(self.final, dict) or self.final.get('session_id') != self.session_id:
                self.final = None
                if self._stop_at is None and not self.error:
                    self.error = '相机进程未返回有效结果，请查看预览日志。'
            elif self.final.get('state') == 'failed':
                self.error = self.final.get('error') or self.final.get('cleanup_error') or '相机预览失败'
            elif code != 0 and not self.error:
                self.error = '相机进程异常退出：%d' % code
            self._returncode = code
            self.process = None
            self.log.close()
            self.log = None
        return request_stop
