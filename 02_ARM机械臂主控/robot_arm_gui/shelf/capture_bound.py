"""Bound ISP frame start using observed hardware SOF counts, never dequeue time.

0x344 exposes the Gray-synchronized ISP SOF count. A compact frame latches this
count at the same frame's streamed first pixel. Require a two-frame separation
from an earlier observation (the synchronizer delay is much less than one
1920x1080 frame). This is a conservative ISP-input bound, not a sensor exposure
timestamp. Frames without a bound remain unsuitable for moving search.
"""
from collections import deque
import math

BASIS = 'isp_sof_lower_bound_v1'


def ungray(value):
    result=0
    while value:
        result ^= value
        value >>= 1
    return result


class FrameStartBound:
    def __init__(self):
        self.samples=deque(maxlen=256)

    def observe(self, stamp, source_id):
        if (type(stamp) not in (int,float) or not math.isfinite(stamp) or
                type(source_id) is not int or not 0<=source_id<=0xffffffff):
            raise ValueError('Invalid ISP clock observation')
        if self.samples:
            old_stamp,old_id=self.samples[-1]
            if stamp<old_stamp or ((source_id-old_id)&0xffffffff)>=0x80000000:
                raise ValueError('Camera source reset or clock reversal')
            if source_id==old_id:return
        self.samples.append((stamp,source_id))

    def bound(self, frame_id, now):
        if type(frame_id) is not int or not 0<=frame_id<=0xffffffff:
            raise ValueError('Invalid compact frame identity')
        for stamp,ident in reversed(self.samples):
            delta=(frame_id-ident)&0xffffffff
            if 2<=delta<0x80000000:
                if not 0<=now-stamp<=.35:return None
                return dict(captured_at=stamp,capture_time_basis=BASIS,
                            capture_bound_source_id=ident,capture_bound_delta=delta)
        return None
