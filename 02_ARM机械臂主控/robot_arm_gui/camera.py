"""Background camera capture with a single latest frame, no GUI event backlog."""
import os
import threading
import time

from .vision import dependencies


class CameraFeed:
    def __init__(self, factory=None):
        self.factory = factory
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._latest = None
        self._sequence = 0
        self.message = ''

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, index=0):
        if self.running:
            return False
        self._stop.clear()
        with self._lock:
            self._latest = None
            self.message = '正在打开摄像头…'
        self._thread = threading.Thread(target=self._run, args=(index,), daemon=True,
                                        name='f3p-camera')
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()  # Never wait for a camera driver on the GUI thread.
        with self._lock:
            self._latest = None

    def latest(self):
        with self._lock:
            return self._sequence, self._latest, self.message

    def _run(self, index):
        cap = None
        try:
            cv, _ = dependencies()
            cap = (self.factory(index) if self.factory else
                   cv.VideoCapture(index, cv.CAP_DSHOW if os.name == 'nt' else cv.CAP_ANY))
            if not cap.isOpened():
                raise RuntimeError('无法打开摄像头，请检查设备编号、权限或是否被其他程序占用。')
            cap.set(cv.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv.CAP_PROP_FPS, 15)
            while not self._stop.is_set():
                start = time.monotonic()
                ok, frame = cap.read()
                if self._stop.is_set():
                    break
                if not ok or frame is None:
                    raise RuntimeError('摄像头画面读取失败，请关闭后重新打开。')
                # Bound preview and processing costs even if the driver ignores set().
                height, width = frame.shape[:2]
                scale = min(1.0, 640 / width, 480 / height)
                if scale < 1:
                    frame = cv.resize(frame, (round(width * scale), round(height * scale)))
                rgb = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
                with self._lock:
                    if not self._stop.is_set():
                        self._sequence += 1
                        self._latest = (frame, rgb)
                        self.message = f'摄像头 {index} · {frame.shape[1]}×{frame.shape[0]}'
                self._stop.wait(max(0, .1 - (time.monotonic() - start)))
        except Exception as exc:
            with self._lock:
                self._latest = None
                self.message = str(exc)
        finally:
            if cap is not None:
                cap.release()

