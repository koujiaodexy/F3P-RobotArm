"""Bounded camera-window MMIO using the existing exclusive owner mapping."""
import ctypes
import json
import time


class HardwareWindow:
    hardware=True

    def __init__(self,path,session_id):
        self.path,self.session_id=path,session_id
        self.control=None
        self.attached=False
        self.position=None
        self.next=0.
        self.before=None
        self.source_size=[192,108]

    def read(self,offset):
        if offset not in range(0x1e0,0x200,4):raise ValueError('Outside hardware window aperture')
        self.control.read(0x33c)
        word=ctypes.c_uint32.from_buffer(self.control.mem,offset)
        try:return word.value
        finally:del word

    def write(self,offset,value):
        if offset not in (0x1e4,0x1e8,0x1ec):raise ValueError('Outside hardware window configuration')
        word=ctypes.c_uint32.from_buffer(self.control.mem,offset)
        try:word.value=value
        finally:del word
        self.control.read(0x33c)

    def attach(self,source):
        self.control=source.control
        capability=self.read(0x1e0)
        if capability not in (0x574e5033,0x574e5034):raise RuntimeError('Compatible FPGA HDMI window firmware is not installed')
        self.source_size=[480,270] if capability==0x574e5034 else [192,108]
        self.attached=True
        self.write(0x1e4,0x574e0002)
        if self.read(0x1e4)&2!=2:raise RuntimeError('Window firmware cannot pause redundant raw DMA')
        self.before=(time.monotonic(),self.read(0x1f0),self.read(0x1f4),self.read(0x1f8))

    def service(self,report):
        now=time.monotonic()
        if now<self.next:return
        self.next=now+.1
        visible=False
        try:
            if self.path.stat().st_size>4096:raise ValueError('Geometry file too large')
            value=json.loads(self.path.read_text())
            x,y=value['x'],value['y']
            width,height=value['width'],value['height']
            valid_size=(type(width)is int and type(height)is int and width%192==0
                and 2<=width//192<=8 and height==108*(width//192))
            # GTK may atomically publish a newer file after service began.
            # Sample its age after reading, so that fresh geometry is not
            # mistaken for a future timestamp and briefly hidden.
            geometry_now=time.monotonic()
            visible=(value['session_id']==self.session_id and 0<=geometry_now-value['timestamp']<1.2
                and valid_size and type(x)is int and type(y)is int
                and 4<=x and x+width<=1920 and 0<=y and y+height<=1080 and value['visible']is True)
        except (OSError,ValueError,KeyError,TypeError):pass
        if visible:
            if self.position!=(x,y,width,height):
                self.write(0x1e4,0x574e0002)
                self.write(0x1ec,width|(height<<16));self.write(0x1e8,x|(y<<16))
                if self.read(0x1ec)!=(width|height<<16):raise RuntimeError('Window size was not accepted')
                self.position=(x,y,width,height)
            self.write(0x1e4,0x574e0003)
        else:self.write(0x1e4,0x574e0002)
        report['preview_visible']=visible
        report['raw_dma_paused']=bool(self.read(0x1e4)&2)
        stamp,frames,unique,underflows=self.before
        if now-stamp>=1:
            f,u,e=self.read(0x1f0),self.read(0x1f4),self.read(0x1f8)
            health=self.read(0x1fc)
            if health&15:raise RuntimeError('Hardware window pixel integrity fault: %#x'%health)
            # Startup/visibility transitions may leave an incomplete first frame;
            # only count rates from a stable interval with no underflows.
            valid=visible and health&16 and e==underflows
            report.update(preview_fps=((u-unique)&0xffffffff)/(now-stamp) if valid else None,
                preview_scanout_fps=((f-frames)&0xffffffff)/(now-stamp),preview_frames=f,
                preview_unique_frames=u,preview_underflows=e,preview_health=health,
                preview_size=list(self.position[2:]) if self.position else [384,216],preview_source_size=self.source_size,
                preview_transport='fpga_hdmi',display_fps_verified=bool(valid))
            self.before=(now,f,u,e)

    def due(self):return False

    def close(self):
        if self.attached:
            self.write(0x1e4,0x574e0002)
