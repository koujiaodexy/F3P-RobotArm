"""One cancellable math-only prepared trajectory; no CAN or MMIO access."""
import threading
import time
import math


def valid_motor(values):
    return (isinstance(values,(list,tuple)) and len(values)==6
            and all(type(v) in (int,float) and math.isfinite(v) for v in values))


def close_report(report):
    if report and report.get('native_report',{}).get('rolling'):
        report['native_report']['frames'].close()


def retire_report(report):
    """Revoke a preview immediately; process shutdown must not block GTK."""
    frames=(report or {}).get('native_report',{}).get('frames')
    if not (report or {}).get('native_report',{}).get('rolling') or frames is None:return
    frames.cancel.set()
    with frames.lock:frames.closed=True
    threading.Thread(target=frames.close,name='preview-math-cleanup',daemon=True).start()


class PreparationCache:
    def __init__(self):
        self.lock=threading.RLock();self.generation=0;self.key=None
        self.cancel=None;self.report=None;self.error='';self.state='idle';self.thread=None
        self.origin=None

    def invalidate(self):
        with self.lock:
            self.generation+=1
            if self.cancel:self.cancel.set()
            retire_report(self.report)
            self.report=None;self.key=None;self.cancel=None;self.state='idle';self.error=''
            self.origin=None

    def invalidate_if_moved(self,motor):
        """Failed and in-flight jobs also belong to one actual starting pose."""
        with self.lock:
            origin=self.origin
            if origin is None and self.report:
                origin=self.report.get('native_report',{}).get('start_motor_deg')
            if self.key is not None and (not valid_motor(origin) or not valid_motor(motor)
                    or any(abs(a-b)>.25 for a,b in zip(origin,motor))):
                self.invalidate()

    def ensure(self,key,builder,motor=None):
        with self.lock:
            if self.key==key:return
            self.invalidate();self.key=key;generation=self.generation
            self.origin=list(motor) if motor is not None else None
            cancel=threading.Event();self.cancel=cancel;self.state='preparing'
        def work():
            report=None;began=time.monotonic()
            print('CART_PREPARATION_START',dict(generation=generation,request=key[0] if isinstance(key,tuple) else key),flush=True)
            try:report=builder(cancel)
            except Exception as exc:
                with self.lock:
                    if generation==self.generation:
                        self.state='failed';self.error=str(exc)
                        print('CART_PREPARATION_FAILED',dict(generation=generation,seconds=time.monotonic()-began,error=str(exc)),flush=True)
                return
            with self.lock:
                if cancel.is_set() or generation!=self.generation:close_report(report);return
                self.report=report;self.state='ready'
                native=report.get('native_report',{})
                print('CART_PREPARATION_READY',dict(generation=generation,seconds=time.monotonic()-began,
                    complete=native.get('complete_before_start',False),transitions=native.get('singularity_transitions',[])),flush=True)
        self.thread=threading.Thread(target=work,name='cartesian-preparation',daemon=True);self.thread.start()

    def take(self,key,motor,ppr):
        with self.lock:
            report=self.report
            if self.key!=key or self.state!='ready' or not report:return None
            native=report.get('native_report',{})
            origin=native.get('start_motor_deg')
            if (not valid_motor(origin) or not valid_motor(motor) or not valid_motor(ppr)
                    or any(v<=0 for v in ppr)):
                self.invalidate();return None
            frames=native.get('frames')
            if native.get('rolling') and (frames is None or frames.closed or frames.error or frames.cancel.is_set()):
                self.invalidate();return None
            if any(abs(a-b)>max(.25,360/ppr[i]+360/65536) for i,(a,b) in enumerate(zip(origin,motor))):
                self.invalidate();return None
            # Detach ownership: later UI edits must not cancel the executing producer.
            self.report=None;self.key=None;self.cancel=None;self.state='idle';self.generation+=1
            self.origin=None
            return report

    def wait_take(self,key,motor,ppr,check):
        """Join the matching math job instead of cancelling and replanning it."""
        with self.lock:
            generation=self.generation
        while True:
            check()
            with self.lock:
                if self.generation!=generation or self.key!=key:return None
                if self.state!='preparing':return self.take(key,motor,ppr)
            time.sleep(.02)
