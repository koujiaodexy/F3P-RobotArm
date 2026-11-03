"""Bounded PCM capture and speech endpointing; no robot or network access."""
from array import array
from collections import deque
import math
import pathlib
import subprocess
import sys
import threading
import time

RATE = 16000
FRAME_SAMPLES = 320
FRAME_BYTES = FRAME_SAMPLES * 2
NATIVE = pathlib.Path(__file__).with_name('native') / 'microphone_capture'


class Segmenter:
    """20ms frames, 200ms pre-roll, 400ms endpoint; discard overlong speech."""
    def __init__(self, floor_db=-45):
        if type(floor_db) not in (float, int) or not -65 <= floor_db <= -20:
            raise ValueError('录音触发阈值应在 -65 至 -20 dBFS')
        self.floor = 32768 * 10 ** (floor_db / 20)
        self.noise = self.floor / 4
        self.next_id = 0
        self.reset(False)

    def reset(self, require_silence=True):
        self.pre = deque(maxlen=10)
        self.frames = None
        self.run = self.speech = self.silence = 0
        self.cooldown = require_silence
        self.started = None

    def feed(self, pcm, now=None):
        if len(pcm) != FRAME_BYTES:
            raise ValueError('Incomplete microphone PCM frame')
        now = time.monotonic() if now is None else now
        values = array('h', pcm)
        if sys.byteorder != 'little':
            values.byteswap()
        rms = math.sqrt(sum(v * v for v in values) / FRAME_SAMPLES)
        peak = max(abs(v) for v in values)
        threshold = max(self.floor, self.noise * 2.5)
        voiced = rms >= threshold
        events = [('level', dict(db=20 * math.log10(max(rms, 1) / 32768),
            peak=peak / 32768, clipped=sum(abs(v) >= 32760 for v in values) >= 4,
            threshold_db=20 * math.log10(threshold / 32768)))]
        if self.cooldown:
            self.silence = 0 if voiced else self.silence + 1
            if self.silence >= 20:
                self.reset(False)
            return events
        if self.frames is None:
            self.pre.append(pcm)
            self.run = self.run + 1 if voiced else 0
            if not voiced:
                self.noise = .98 * self.noise + .02 * rms
            if self.run >= 3:
                self.next_id += 1
                self.frames = list(self.pre)
                self.started = now - .02 * (len(self.frames) - 1)
                self.speech = self.run
                self.silence = 0
                events.append(('onset', dict(id=self.next_id, started=self.started)))
            return events
        self.frames.append(pcm)
        self.speech += int(voiced)
        self.silence = 0 if voiced else self.silence + 1
        if len(self.frames) >= 175:
            events.append(('discard', dict(id=self.next_id, reason='声音持续过长，本句已丢弃，请分开说指令')))
            self.reset(True)
        elif self.silence >= 20:
            if self.speech >= 9:
                # Keep 120ms of trailing silence, without truncating speech.
                frames = self.frames[:len(self.frames) - self.silence + 6]
                events.append(('utterance', dict(id=self.next_id, pcm=b''.join(frames),
                    started=self.started, ended=now, sample_rate=RATE)))
            else:
                events.append(('discard', dict(id=self.next_id, reason='声音过短，本句未识别')))
            self.reset(False)
        return events


class MicrophoneSession:
    def __init__(self, event, gain=6, floor_db=-45, native=NATIVE, process_factory=subprocess.Popen):
        if type(gain) is not int or not 0 <= gain <= 8:
            raise ValueError('麦克风增益无效')
        self.event = event
        self.gain = gain
        self.native = pathlib.Path(native)
        self.process_factory = process_factory
        self.segmenter = Segmenter(floor_db)
        self.stopping = threading.Event()
        self.reset_requested = threading.Event()
        self.process = None
        self.lock = threading.Lock()
        self.thread = None

    def start(self):
        if self.thread is not None:
            raise RuntimeError('Microphone session cannot be restarted')
        self.thread = threading.Thread(target=self._work, name='f3p-microphone', daemon=True)
        self.thread.start()

    def reset_utterance(self):
        self.reset_requested.set()

    def stop(self):
        self.stopping.set()
        with self.lock:
            process = self.process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass

    def _work(self):
        error = None
        process = None
        last_level = 0
        try:
            process = self.process_factory([str(self.native), '--stream', '--gain', str(self.gain)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            with self.lock:
                self.process = process
            if self.stopping.is_set():
                process.terminate()
            pending = b''
            while not self.stopping.is_set():
                chunk = process.stdout.read(FRAME_BYTES - len(pending))
                if not chunk:
                    if not self.stopping.is_set():
                        raise RuntimeError('录音服务已退出')
                    break
                pending += chunk
                if len(pending) != FRAME_BYTES:
                    continue
                if self.reset_requested.is_set():
                    self.reset_requested.clear()
                    self.segmenter.reset(True)
                now = time.monotonic()
                for kind, value in self.segmenter.feed(pending, now):
                    if kind == 'level':
                        if now - last_level < .15:
                            continue
                        last_level = now
                    self.event(kind, value)
                pending = b''
        except Exception as exc:
            if not self.stopping.is_set():
                error = str(exc)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                diagnostic = process.stderr.read(4096).decode('utf-8', errors='replace').strip()
                process.stdout.close()
                process.stderr.close()
                if not self.stopping.is_set() and (error or process.returncode):
                    error = diagnostic or error or '录音服务异常退出'
            self.event('closed', dict(error=error))
