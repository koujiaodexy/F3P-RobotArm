"""Bounded, asynchronous event recording; never sends motor commands."""
from __future__ import annotations
import csv
import json
import os
import queue
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path


def default_directory():
    user = os.environ.get('SUDO_USER', '')
    home = Path('/home') / user if os.name == 'posix' and user and user != 'root' else Path.home()
    return home / 'Documents' / 'F3P-TestRecords'


def user_owns(path):
    if os.name == 'posix' and os.geteuid() == 0 and os.environ.get('SUDO_USER') not in (None, '', 'root'):
        import pwd
        owner = pwd.getpwnam(os.environ['SUDO_USER'])
        os.chown(str(path), owner.pw_uid, owner.pw_gid)


class TestRecorder:
    def __init__(self, directory=None, capacity=4096):
        self.directory = Path(directory) if directory is not None else default_directory()
        self.capacity = capacity
        self.lock = threading.RLock()
        self.starting = False
        self.active = False
        self.exporting = False
        self.path = None
        self.error = ''
        self.count = 0
        self.started = 0.0
        self.ended = 0.0
        self.recent = deque(maxlen=50)
        self.done = threading.Event()
        self.stopping = threading.Event()
        self.incomplete = 0
        try:
            for path in self.directory.glob('*.jsonl'):
                with path.open('rb') as stream:
                    stream.seek(max(0, path.stat().st_size - 4096))
                    if b'"event": "session_end"' not in stream.read():
                        self.incomplete += 1
        except OSError:
            pass

    def start(self, metadata=None, _reserved=False):
        with self.lock:
            if (self.starting and not _reserved) or self.active or self.exporting or (self.path and not self.done.is_set()):
                raise RuntimeError('上一轮记录尚未结束')
            self.starting = True
            if not _reserved: self._start_cancelled = False
        stream = None
        try:
            created = not self.directory.exists()
            self.directory.mkdir(parents=True, exist_ok=True)
            if created: user_owns(self.directory)
            name = 'motor-test-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
            path = self.directory / (name + '.jsonl')
            stream = path.open('x', encoding='utf-8')
            user_owns(path)
            with self.lock:
                if self._start_cancelled: raise RuntimeError('开始记录已取消')
                self.path = path
                self.events = queue.Queue(maxsize=self.capacity)
                self.done.clear(); self.stopping.clear()
                self.error = ''; self.count = 0; self.recent.clear()
                self.started = time.monotonic(); self.ended = 0
                self.active = True
                self.record('session_start', metadata=metadata or {}, clock='system_time_unverified', scope=[1,2,3,4,5,6])
                threading.Thread(target=self._write, args=(stream,), daemon=True, name='f3p-record-writer').start()
            return str(path)
        except Exception:
            if stream is not None: stream.close()
            raise
        finally:
            with self.lock: self.starting = False

    def start_async(self, metadata, callback):
        with self.lock:
            if self.starting or self.active or self.exporting or (self.path and not self.done.is_set()):
                raise RuntimeError('上一轮记录尚未结束，或正在开始记录')
            self.starting = True
            self._start_cancelled = False
        def work():
            error = ''
            try: self.start(metadata, _reserved=True)
            except Exception as exc: error = str(exc)
            with self.lock:
                self.starting = False
                if error: self.error = '开始记录失败：' + error
            callback(not error, error)
        threading.Thread(target=work, daemon=True, name='f3p-record-start').start()

    def record(self, event, **fields):
        with self.lock:
            if not self.active:
                return
            row = dict(time=datetime.now().astimezone().isoformat(timespec='milliseconds'),
                       elapsed_ms=round((time.monotonic()-self.started)*1000, 3), event=event, **fields)
            try:
                self.events.put_nowait(row)
            except queue.Full:
                self.error = '记录队列已满；记录不完整，原始文件已保留'
                self.active = False
                self.ended = time.monotonic()
                self.stopping.set()
                return
            self.count += 1
            self.recent.append(row)

    def _write(self, stream):
        synced = time.monotonic()
        try:
            while not self.stopping.is_set() or not self.events.empty():
                try:
                    row = self.events.get(timeout=.2)
                except queue.Empty:
                    row = None
                if row is not None:
                    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                if time.monotonic()-synced >= 1:
                    stream.flush()
                    os.fsync(stream.fileno())
                    synced = time.monotonic()
            stream.flush()
            os.fsync(stream.fileno())
        except Exception as exc:
            with self.lock:
                self.error = '记录写入失败：' + str(exc)
                self.active = False
                self.ended = time.monotonic()
                self.stopping.set()
        finally:
            try:
                stream.close()
            except Exception:
                pass
            self.done.set()

    def stop(self, reason='operator'):
        with self.lock:
            if self.starting: self._start_cancelled = True
            if self.active:
                self.record('session_end', reason=reason)
                self.active = False
                self.ended = time.monotonic()
                self.stopping.set()

    def status(self, include_recent=True):
        with self.lock:
            seconds = int((time.monotonic() if self.active else self.ended or self.started)-self.started) if self.started else 0
            return dict(starting=self.starting, active=self.active, exporting=self.exporting, count=self.count,
                seconds=max(0, seconds), error=self.error, path=str(self.path or ''),
                recent=list(self.recent) if include_recent else [], incomplete=self.incomplete)

    def export_async(self, destination, callback):
        with self.lock:
            if not self.path or self.exporting:
                raise RuntimeError('没有可导出的记录，或正在导出')
            self.stop()
            self.exporting = True
            source = self.path
        def work():
            error = ''
            temp = None
            try:
                if not self.done.wait(15):
                    raise RuntimeError('原始日志仍在写入，请稍后重试')
                destination_path = Path(destination)
                if destination_path.resolve() == source.resolve():
                    raise RuntimeError('不能覆盖原始日志')
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                temp = destination_path.with_name(destination_path.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
                keys = ['time','elapsed_ms','event','node','can_id','operation','result','response_ms','data','reply','speed_rpm','acceleration','item','observation','note','error','reason']
                with source.open(encoding='utf-8') as raw, temp.open('x', encoding='utf-8-sig', newline='') as out:
                    writer = csv.writer(out)
                    writer.writerow(['时间','经过毫秒','事件','电机编号','CAN ID','操作','命令结果','回复耗时毫秒','发送数据','回复数据','目标转速RPM','加速度','观察项目','实际观察','备注','错误','结束原因','完整数据JSON'])
                    for line in raw:
                        try:
                            row = json.loads(line)
                        except ValueError:
                            writer.writerow(['']*len(keys) + ['原始日志尾部不完整'])
                            continue
                        def cell(value):
                            text = str(value)
                            return "'" + text if text.startswith(('=','+','-','@')) else text
                        writer.writerow([cell(row.get(key,'')) for key in keys] + [json.dumps(row,ensure_ascii=False)])
                    if self.error:
                        writer.writerow(['']*len(keys) + [self.error])
                user_owns(temp)
                os.replace(str(temp), str(destination_path))
            except Exception as exc:
                error = str(exc)
                if temp is not None:
                    try: temp.unlink()
                    except OSError: pass
            with self.lock:
                self.exporting = False
            callback(not error, error or str(destination))
        threading.Thread(target=work, daemon=True).start()
