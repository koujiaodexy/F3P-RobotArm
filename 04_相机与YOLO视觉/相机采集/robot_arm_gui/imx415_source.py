"""Read verified build15 camera buffers while GTK scanout remains enabled."""
from __future__ import annotations
import ctypes
import mmap
import os
from pathlib import Path
import struct
import sys
import time
import threading
from .vision import dependencies

RUNTIME=Path('/opt/f3p-npu/camera-1080p60-20261016')

class Imx415Source:
    name='板载 IMX415'
    def __init__(self):self.control=None;self.mem=None;self.fd=None;self._views=[];self.last_id=None;self.source_size=(1920,1080);self._heartbeat=None;self._heartbeat_stop=threading.Event();self._heartbeat_error=None;self.sensor_reinitialized=False
    def open(self):
        if not (RUNTIME/'camera1080_hw.py').is_file():raise RuntimeError('板载摄像头运行时尚未安装，请先恢复 build15；原机械臂功能不受影响。')
        if str(RUNTIME)not in sys.path:sys.path.insert(0,str(RUNTIME))
        from camera1080_hw import reservation,Control
        reservation()
        # Verify hardware using a read-only map before creating a writable controller.
        fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
        try:
            with mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=0xa0000000)as mm:
                if struct.unpack_from('<I',mm,0x3e0)[0]!=0x56494431:raise RuntimeError('当前固件未启用 IMX415 图像通路，请核对 build15 启动版本。')
        finally:os.close(fd)
        try:self.control=Control()
        except BlockingIOError:raise RuntimeError('摄像头正被全屏预览占用，请退出全屏预览后重试。')
        self._ensure_sensor_clock()
        self.control.tables()
        _,np=dependencies()
        self.fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
        self.mem=mmap.mmap(self.fd,0x1800000,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=0x3c000000)
        self._views=[np.ndarray((1080,1920),np.uint32,buffer=self.mem,offset=i*0x800000)for i in range(3)]
        baseline=self.control.status()['written'];self.control.set_mode(1)
        self._heartbeat_stop.clear()
        self._heartbeat=threading.Thread(target=self._keep_alive,daemon=True,name='f3p-camera-lease');self._heartbeat.start()
        started=time.monotonic()
        while ((self.control.status()['written']-baseline)&0xffffffff)<3:
            if time.monotonic()-started>4:raise RuntimeError('摄像头未产生完整图像，请断电检查排线方向和连接。')
            time.sleep(.04)
        self.rate_stamp=time.monotonic();self.rate_frames=self.control.status()['source_frames'];self.source_fps=0.
    def _ensure_sensor_clock(self):
        from camera1080_hw import ungray
        first=ungray(self.control.read(0x3c0));time.sleep(.1)
        if ungray(self.control.read(0x3c0))!=first:return
        # Only reinitialize this camera sensor, with the DMA mode stopped and
        # the HD owner lock held. This does not reset the board or any motor.
        assert self.control.read(0x33c)&3==0
        before=self.control.read(0x304)
        if before not in (0,1):raise RuntimeError('摄像头正在由其他过程初始化，请稍后重试')
        sensor=ctypes.c_uint32.from_buffer(self.control.mem,0x304)
        try:
            sensor.value=before|2;self.control.read(0x304);time.sleep(.05)
            sensor.value=before;self.control.read(0x304)
        finally:del sensor
        previous=None;deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            time.sleep(.15);status=self.control.read(0x30c);cycles=ungray(self.control.read(0x3c0));frames=self.control.read(0x318)
            if status&2:raise RuntimeError('摄像头初始化未应答，请断电检查排线和相机连接')
            if status&1 and previous and cycles!=previous[0] and frames!=previous[1]:
                self.sensor_reinitialized=True;return
            previous=(cycles,frames)
        raise RuntimeError('摄像头像素时钟未恢复，请检查相机连接后重试')
    def _keep_alive(self):
        try:
            while not self._heartbeat_stop.wait(.15):self.control.set_mode(1)
        except Exception as exc:self._heartbeat_error=exc
    def read(self):
        _,np=dependencies()
        if self._heartbeat_error:raise RuntimeError('摄像头保活失败：'+str(self._heartbeat_error))
        # Device memory must be read as aligned words. Byte-wise strided copies
        # were measured at 120 ms and mixed several source frames on this board.
        # In writer-only mode the ring can keep rewriting its active slot.
        for step in (4,4,6,6):
            self.control.set_mode(1)
            address=self.control.read(0x35c);slot=(address-0x3c000000)//0x800000
            if not 0<=slot<3:raise RuntimeError('相机写缓冲地址超出保留区域')
            words=self._views[slot][::step,::step].copy()
            alpha=words>>24;frame_id=int(alpha[0,0])
            if not np.all(alpha==frame_id) or frame_id==self.last_id:
                time.sleep(.003);continue
            self.last_id=frame_id;now=time.monotonic()
            if now-self.rate_stamp>=1:
                current=self.control.status()['source_frames'];self.source_fps=((current-self.rate_frames)&0xffffffff)/(now-self.rate_stamp)
                self.rate_frames=current;self.rate_stamp=now
            h,w=words.shape;sample=words.view(np.uint8).reshape(h,w,4)
            bgr=sample[:,:,:3].copy()
            return bgr,{'source_size':self.source_size,'frame_id':frame_id,'slot':slot,'captured_at':now,
                        'source_fps':self.source_fps,'sampling_step':step,'backend':'imx415_build15_writer_only',
                        'coherent_frame_verified':True,'sensor_reinitialized':self.sensor_reinitialized}
        return None
    def close(self):
        self._heartbeat_stop.set()
        if self._heartbeat is not None:self._heartbeat.join();self._heartbeat=None
        self._views=[]
        if self.control is not None:
            self.control.close();self.control=None
        if self.mem is not None:self.mem.close();self.mem=None
        if self.fd is not None:os.close(self.fd);self.fd=None

class UsbSource:
    name='USB 摄像头'
    def __init__(self,index=0):self.index=index;self.cap=None;self.sequence=0
    def open(self):
        cv,_=dependencies();self.cap=cv.VideoCapture(self.index,cv.CAP_DSHOW if os.name=='nt'else cv.CAP_V4L2)
        if not self.cap.isOpened():raise RuntimeError('无法打开 USB 摄像头，请核对设备编号或是否被占用。板载 IMX415 请使用对应输入。')
        self.cap.set(cv.CAP_PROP_FRAME_WIDTH,640);self.cap.set(cv.CAP_PROP_FRAME_HEIGHT,480);self.cap.set(cv.CAP_PROP_FPS,15)
        self.cap.set(cv.CAP_PROP_BUFFERSIZE,1)
    def read(self):
        cv,_=dependencies();ok,frame=self.cap.read()
        if not ok or frame is None:raise RuntimeError('USB 摄像头读取失败，请重新连接后启动。')
        h,w=frame.shape[:2];scale=min(1.,640/w,480/h)
        if scale<1:frame=cv.resize(frame,(round(w*scale),round(h*scale)),interpolation=cv.INTER_AREA)
        self.sequence+=1
        return frame,{'source_size':(w,h),'frame_id':self.sequence,'captured_at':time.monotonic(),'backend':'usb','source_fps':None}
    def close(self):
        if self.cap is not None:self.cap.release();self.cap=None
