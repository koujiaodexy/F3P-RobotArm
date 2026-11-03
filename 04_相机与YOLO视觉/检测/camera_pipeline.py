"""Bounded capture/inference/publication overlap; each source ID is used once."""
import os,queue,threading,time

def read_bgr(source,item,cv,np):
    if item.get('cached_rgb_verified'):return source.raw_frame(item)
    words=np.empty((270,480),np.uint32)
    rc=source.lib.f3p_copy_rgb(item.get('physical_compact',item['compact']).ctypes.data,words.ctypes.data,
        480,270,780,240,item['frame_id'],item['trailer'][2])
    if rc:
        # The compact DMA ring has only six slots.  If inference falls behind,
        # the slot can be overwritten while RGB is being copied.  Verify the
        # header after the failed copy so the capture worker can discard only
        # that expired frame; retained-frame corruption remains fatal.
        source.verify_feature(item)
        raise RuntimeError('Camera preview failed its per-pixel frame/hash check: '+str(rc))
    # Preserve native per-pixel ID and whole-frame hash validation. Only the
    # final exact BGRA -> BGR packing changes; no strided NumPy pixel copy.
    return cv.cvtColor(words.view(np.uint8).reshape(270,480,4),cv.COLOR_BGRA2BGR)

class CapturePipeline:
    def __init__(self,source,cv,letterbox,size,byte_protocol,stop,expired,cpu=None,read_frame=None,demand=False):
        self.source,self.stop=source,stop;self.items=queue.Queue(maxsize=1);self.error=None;self.discarded=0
        self.request=threading.Event();self.request.set()
        def run():
            try:
                if cpu is not None:os.sched_setaffinity(0,{cpu})
                while not stop.is_set():
                    if demand and not self.request.wait(.05):continue
                    began=time.monotonic();source.recover_pending(limit=2)
                    try:
                        item=source.acquire_feature()
                        if item is None:stop.wait(.001);continue
                        bgr=read_frame(item) if read_frame else source.raw_frame(item);source.finish_feature(item)
                    except expired:continue
                    captured=time.monotonic();tensor,geometry=letterbox(bgr,cv,size=size,byte_tensor=byte_protocol)
                    packet=(item,bgr,tensor,geometry,began,captured,time.monotonic())
                    if demand:self.request.clear()
                    try:self.items.put_nowait(packet)
                    except queue.Full:
                        try:self.items.get_nowait();self.discarded+=1
                        except queue.Empty:pass
                        self.items.put_nowait(packet)
            except BaseException as error:self.error=error
        self.thread=threading.Thread(target=run,name='coco-capture',daemon=True);self.thread.start()

    def next(self):
        while not self.stop.is_set():
            if self.error:raise self.error
            try:
                item=self.items.get(timeout=.05);self.request.set();return item
            except queue.Empty:
                if not self.thread.is_alive():raise RuntimeError('Camera capture stopped')
        return None

    def close(self):
        self.thread.join(timeout=5)
        if self.thread.is_alive():raise RuntimeError('Camera capture did not stop; device kept mapped')
        if self.error:raise self.error

class ResultPipeline:
    def __init__(self,emit,cpu=None):
        self.items=queue.Queue(maxsize=2);self.error=None
        def run():
            try:
                if cpu is not None:os.sched_setaffinity(0,{cpu})
                while True:
                    item=self.items.get()
                    if item is None:return
                    emit(*item)
            except BaseException as error:self.error=error
        self.thread=threading.Thread(target=run,name='coco-publication',daemon=True);self.thread.start()

    def submit(self,*packet):
        while self.thread.is_alive():
            if self.error:raise self.error
            try:self.items.put(packet,timeout=.05);return
            except queue.Full:pass
        raise RuntimeError('Detection publication stopped: '+str(self.error))

    def close(self):
        if self.thread.is_alive():
            while self.thread.is_alive():
                try:self.items.put(None,timeout=.05);break
                except queue.Full:pass
            self.thread.join(timeout=5)
        if self.thread.is_alive():raise RuntimeError('Detection publication did not stop')
        if self.error:raise self.error
