"""Bounded, serial, math-only preparation of the visible hold directions."""
import copy
import threading
from .trajectory_preparation import retire_report, close_report


class JogPreparation:
    # Stay within encoder quantization, much stricter than executor arrival.
    MOTOR_TOLERANCE = .01

    def __init__(self):
        self.lock = threading.RLock()
        self.key = None
        self.motor = None
        self.cancel = None
        self.reports = {}
        self.thread = None

    def invalidate(self):
        with self.lock:
            if self.cancel:self.cancel.set()
            reports = list(self.reports.values())
            self.reports = {};self.key = None;self.motor = None;self.cancel = None
        for report in reports:retire_report(report)

    def matches(self, key, motor):
        return (self.key == key and self.motor is not None and len(motor) == 6
                and all(abs(a-b) <= self.MOTOR_TOLERANCE for a,b in zip(self.motor,motor)))

    def ensure(self, key, motor, directions, builder):
        with self.lock:
            if self.matches(key,motor):return
            self.invalidate()
            self.key = copy.deepcopy(key);self.motor = list(motor)
            cancel = threading.Event();self.cancel = cancel
        def work():
            for direction in directions:
                if cancel.is_set():return
                try:report = builder(direction,cancel)
                except Exception:
                    # An infeasible direction does not prevent preparing others.
                    continue
                with self.lock:
                    stale = cancel.is_set() or self.cancel is not cancel
                    if not stale:self.reports[direction] = report
                if stale:close_report(report);return
        self.thread = threading.Thread(target=work,name='jog-idle-preparation',daemon=True)
        self.thread.start()

    def take(self, key, motor, direction):
        with self.lock:
            report = self.reports.pop(direction,None) if self.matches(key,motor) else None
            if report:
                frames = report['native_report']['frames']
                # A later mathematical boundary can already be known while
                # idle. Its published prefix and braking reserve remain valid;
                # keep the error so the ordinary executor stops at that boundary.
                # Cancelled/consumed streams can never be reused.
                if frames.closed or frames.cancel.is_set():
                    retire_report(report);report = None
            # Only a detached ready report may survive a press. Never wait for
            # another direction, or retain background work during execution.
            self.invalidate()
            return report
