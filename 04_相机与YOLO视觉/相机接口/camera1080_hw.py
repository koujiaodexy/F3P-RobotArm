"""Camera-only 1080p hardware preview. DMA requires a verified DT reservation."""
import argparse
import ctypes
import fcntl
import json
import math
import mmap
import os
import pathlib
import re
import signal
import struct
import subprocess
import time

BASE=0x3c000000
END=0x3e000000
ROOT=pathlib.Path(__file__).resolve().parent

def checkpoint(phase,**values):
    record=dict(phase=phase,monotonic=time.monotonic(),boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),**values)
    with open(str(ROOT/'preflight-checkpoints.jsonl'),'a')as stream:
        stream.write(json.dumps(record)+'\n');stream.flush();os.fsync(stream.fileno())
    print('CAMERA_CHECKPOINT',json.dumps(record),flush=True)

def release_fdma_reset():
    # Vendor PL_GPIO54 = BANK2 bit0. This line only feeds the FDMA reset block.
    for path in pathlib.Path('/dev').glob('gpiochip*'):
        chip=os.open(str(path),os.O_RDONLY)
        try:
            info=bytearray(68);fcntl.ioctl(chip,0x8044b401,info,True)
            name,label,lines=struct.unpack('32s32sI',info)
            if label.rstrip(b'\0')!=b'f8411200.gpio':continue
            assert lines==32
            request=bytearray(struct.pack('64II64s32sIi',*([0]*64),2,b'\1'+bytes(63),b'f3p-camera-fdma',1,0))
            fcntl.ioctl(chip,0xc16cb403,request,True)
            handle=struct.unpack_from('i',request,360)[0]
            assert handle>=0
            return handle
        finally:os.close(chip)
    raise RuntimeError('专用FDMA复位GPIO未找到')

def ungray(value):
    value ^= value >> 1; value ^= value >> 2; value ^= value >> 4
    value ^= value >> 8; value ^= value >> 16
    return value

def reservation():
    node=pathlib.Path('/sys/firmware/devicetree/base/reserved-memory/camera@3c000000')
    assert (node/'no-map').exists(), '摄像头专用内存未预留，拒绝启动DMA'
    assert struct.unpack('>4I',(node/'reg').read_bytes())==(0,BASE,0,END-BASE)
    ranges=[]
    for line in pathlib.Path('/proc/iomem').read_text().splitlines():
        match=re.match(r'\s*([0-9a-f]+)-([0-9a-f]+) : (.*)',line)
        if match:ranges.append((int(match[1],16),int(match[2],16)+1,match[3]))
    reserved=any(a<=BASE and b>=END and name=='reserved' for a,b,name in ranges)
    outside_ram=not any(a<END and b>BASE and name=='System RAM' for a,b,name in ranges)
    assert reserved or outside_ram,'内核内存资源表未确认摄像头保留区'
    return dict(base=BASE,size=END-BASE,no_map=True,resource_reserved=reserved,outside_system_ram=outside_ram)

class Control:
    def __init__(self):
        self.lock=open('/run/f3p-camera-hd.lock','w')
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        self.mem=mmap.mmap(self.fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0xa0000000)
        self.address=ctypes.addressof(ctypes.c_uint32.from_buffer(self.mem))
        self.lib=ctypes.CDLL(str(ROOT/'camera1080_mmio.so'))
        self.lib.camera1080_read.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
        self.lib.camera1080_read.restype=ctypes.c_uint32
        self.lib.camera1080_write.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32]
        self.lib.camera1080_write.restype=ctypes.c_int
        assert self.read(0)==0x52414331 and self.read(4)==0x3000a and self.read(0x200)==0x41554431
        assert self.read(0x300)==0x43414d31 and self.read(0x3e0)==0x56494431,'1080p硬件固件尚未安装'
        self.region=reservation()
        assert self.read(0x30c)&1 and not self.read(0x30c)&2,'摄像头初始化失败'
        self.mode=0
        self.gpio=None

    def read(self,offset):
        return self.lib.camera1080_read(self.address,offset)

    def write(self,offset,value):
        assert self.lib.camera1080_write(self.address,offset,value)==0,'camera register write refused'

    def set_mode(self,mode):
        assert mode in (0,1,3)
        self.write(0x33c,0x56440000|mode); self.mode=mode

    def status(self):
        names=['written','read','underflows','guard_errors','overflows','displayed']
        result={name:ungray(self.read(0x3e4+4*i))for i,name in enumerate(names)}
        mode=self.read(0x33c)
        result.update(mode=mode&3,duplicates=ungray(mode>>16),source_frames=self.read(0x318),
                      camera_status=self.read(0x30c),linux_lines=ungray(self.read(0x3dc)>>15),
                      width=1920,height=1080,source='imx415_fpga_dma')
        if mode&1:
            result['dma_debug']=self.read(0x340)
            result['isp_frames']=ungray(self.read(0x344))
            result['isp_words']=ungray(self.read(0x348))
            result['isp_lines']=ungray(self.read(0x34c))
            result['write_beats']=ungray(self.read(0x350))
            result['read_beats']=ungray(self.read(0x354))
            result['ui_cycles']=ungray(self.read(0x358))
            result['write_address']=self.read(0x35c)
            result['read_address']=self.read(0x360)
            result['display_pixels']=ungray(self.read(0x364))
        return result

    def tables(self):
        self.set_mode(0);time.sleep(.05)
        if self.gpio is None:self.gpio=release_fdma_reset()
        time.sleep(.01)
        gains=[1.45,.71,1.12];black=12.;exposure=4.
        previous=pathlib.Path('/opt/f3p-npu/camera-live-20261016/live-status.json')
        if previous.exists():
            color=json.loads(previous.read_text()).get('color',{})
            if len(color.get('white_balance',[]))==3:
                gains=[min(3.,max(.5,float(v)))for v in color['white_balance']]
                black=min(16.,max(0.,float(color.get('black',12))))
                exposure=min(16.,max(.5,float(color.get('exposure',4))))
        profile=ROOT/'color-profile.json'
        if profile.exists():
            color=json.loads(profile.read_text())
            assert color.get('raw_cfa')=='RGGB'and len(color.get('white_balance',[]))==3
            gains=[min(3.,max(.5,float(v)))for v in color['white_balance']]
            black=min(16.,max(0.,float(color['black'])))
            exposure=min(16.,max(.5,float(color['exposure'])))
        for channel,gain in enumerate(reversed(gains)):
            for value in range(256):
                linear=min(1.,max(0.,(value-black)*gain*exposure/255.))
                tone=round(255*linear**(1/2.2))
                self.write(0x3e0,(channel<<16)|(value<<8)|tone)
        self.color=dict(black=black,exposure=exposure,white_balance=gains)

    def close(self):
        self.set_mode(0);time.sleep(.05)
        self.mem.close();os.close(self.fd);self.lock.close()
        if self.gpio is not None:os.close(self.gpio);self.gpio=None

def stop_software_preview():
    state=pathlib.Path('/opt/f3p-npu/camera-live-20261016/live-status.json')
    if not state.exists():return
    pid=json.loads(state.read_text()).get('pid');proc=pathlib.Path('/proc')/str(pid)
    if not proc.exists():return
    expected=b'/opt/f3p-npu/camera-live-20261016/camera_preview.py'
    if expected in(proc/'cmdline').read_bytes().split(b'\0'):
        os.kill(pid,signal.SIGTERM)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--audit',action='store_true')
    parser.add_argument('--dma-test',type=float,default=0)
    parser.add_argument('--linux-dma-lease',action='store_true')
    parser.add_argument('--seconds',type=float,default=0)
    parser.add_argument('--status-file',type=pathlib.Path,default=ROOT/'live-status.json')
    args=parser.parse_args()
    ctl=Control()
    if args.audit:
        print(json.dumps(dict(reservation=ctl.region,camera=ctl.status())),flush=True)
        ctl.close();return
    ctl.tables()
    if args.dma_test:
        stop_software_preview()
        # Camera video bypasses X11, so always cover the underlying robot UI
        # with an input-owning window before selecting the hardware picture.
        import gi
        gi.require_version('Gtk','3.0')
        from gi.repository import Gtk,Gdk
        cancelled=[False]
        lease=None
        shield=Gtk.Window(title='F3P 摄像头 · 帧率验证')
        shield.add(Gtk.Label(label='正在验证1080p视频通路…\n点击左上角或按 Esc 可结束测试'))
        shield.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        def cancel(*_):cancelled[0]=True
        def test_key(_window,event):
            if event.keyval==Gdk.KEY_Escape:cancel()
            return True
        def test_touch(_window,event):
            if event.x<80 and event.y<56:cancel()
            return True
        shield.connect('destroy',cancel);shield.connect('key-press-event',test_key);shield.connect('button-press-event',test_touch)
        signal.signal(signal.SIGTERM,cancel)
        shield.show_all();shield.fullscreen();shield.present()
        def pause(seconds):
            while Gtk.events_pending():Gtk.main_iteration_do(False)
            assert not cancelled[0],'Camera validation cancelled'
            if lease:lease.beat()
            time.sleep(seconds)
        try:
            covered=False
            for _ in range(40):
                pause(.05)
                if shield.get_mapped():
                    monitor=Gdk.Display.get_default().get_monitor_at_window(shield.get_window())
                    geometry=monitor.get_geometry();width,height=shield.get_size()
                    covered=width>=geometry.width and height>=geometry.height
                    if covered:break
            assert covered,'Full-screen input shield was not established'
            if args.linux_dma_lease:
                from camera1080_display import DisplayLease
                lease=DisplayLease()
            # Pre-fill complete camera buffers before starting display reads.
            checkpoint('before_write_warmup',camera=ctl.status())
            ctl.set_mode(1);warm=time.monotonic();base=ctl.status()['written']
            while ctl.status()['written']-base<3:
                assert time.monotonic()-warm<2,'Camera write warm-up failed'
                ctl.set_mode(1);pause(.05)
            checkpoint('before_display_enable',camera=ctl.status())
            settle=time.monotonic();ctl.set_mode(3)
            if lease:
                checkpoint('before_desktop_halt')
                checkpoint('desktop_halted',display=lease.stop())
            while time.monotonic()-settle<1.5:ctl.set_mode(3);pause(.1)
            start=time.monotonic();first=ctl.status();checkpoint('before_measure',camera=first)
            while time.monotonic()-start<args.dma_test:ctl.set_mode(3);pause(.2)
            last=ctl.status();elapsed=time.monotonic()-start
            checkpoint('measurement_complete',camera=last)
            print('CAMERA_DMA_TEST',json.dumps(dict(first=first,last=last,elapsed=elapsed)),flush=True)
            assert last['written']-first['written']>=args.dma_test*59 and last['read']-first['read']>=args.dma_test*59
            assert all(last[k]==first[k]for k in ['guard_errors','overflows','underflows','duplicates'])
            if lease:assert last['linux_lines']==first['linux_lines'],'Desktop VDMA did not remain halted'
            else:assert (last['linux_lines']-first['linux_lines'])&0x1ffff,'Linux scanout stopped unexpectedly'
        finally:
            checkpoint('before_display_exit')
            if lease:
                lease.close()
                checkpoint('desktop_restored')
            ctl.close();shield.destroy()
            checkpoint('display_exit_complete')
        return
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,Gdk,GLib
    stop_software_preview()
    window=Gtk.Window(title='F3P · 1080p 硬件摄像头')
    window.add(Gtk.Label(label='正在连接1080p硬件视频通路…\n点击左上角返回，或按 Esc 退出'))
    window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
    started=time.monotonic();initial=ctl.status();last_rate=initial.copy();rate_time=started;report={};closed=[False];lease=None
    def close(*_):
        if closed[0]:return
        closed[0]=True
        try:
            if lease:lease.close()
        finally:
            ctl.close();Gtk.main_quit()
    def key(_window,event):
        if event.keyval==Gdk.KEY_Escape:close()
        return False
    def touch(_window,event):
        if event.x<80 and event.y<56:close()
        return False
    def tick():
        if closed[0]:return False
        nonlocal last_rate,rate_time,report,lease
        now=time.monotonic();current=ctl.status()
        if now-started>5 and current['written']-initial['written']<10:
            print('CAMERA_HW_ERROR no complete DMA frames',flush=True);close();return False
        covered=False
        if window.get_mapped():
            geometry=Gdk.Display.get_default().get_monitor_at_window(window.get_window()).get_geometry()
            width,height=window.get_size();covered=width>=geometry.width and height>=geometry.height
        if now-started>5 and not covered:
            print('CAMERA_HW_ERROR full-screen input shield unavailable',flush=True);close();return False
        mode=3 if covered and current['written']-initial['written']>=3 else 1
        if mode==3 and lease is None:
            from camera1080_display import DisplayLease
            lease=DisplayLease()
            ctl.set_mode(3)
            checkpoint('live_desktop_halted',display=lease.stop())
        if lease:lease.beat()
        ctl.set_mode(mode)
        if now-rate_time>=1:
            elapsed=now-rate_time
            rates={name+'_fps':round((current[name]-last_rate[name])/elapsed,3)for name in ['source_frames','written','read','displayed']}
            report=dict(current,**rates,elapsed=round(now-started,3),pid=os.getpid(),mapped=window.get_mapped(),
                        color=ctl.color,robot_control=False,linux_dma_halted=lease is not None)
            temporary=args.status_file.with_suffix('.tmp');temporary.write_text(json.dumps(report));temporary.replace(args.status_file)
            last_rate=current;rate_time=now
        if args.seconds and now-started>=args.seconds:
            print('CAMERA_HW_RUN',json.dumps(dict(first=initial,last=current,elapsed=now-started,status=report)),flush=True)
            close();return False
        return True
    window.connect('destroy',close);window.connect('key-press-event',key);window.connect('button-press-event',touch)
    signal.signal(signal.SIGTERM,lambda *_:close())
    window.show_all();window.fullscreen();window.present()
    def safe_tick():
        try:return tick()
        except BaseException:
            import traceback
            traceback.print_exc();close();return False
    GLib.timeout_add(200,safe_tick)
    try:Gtk.main()
    finally:
        if not closed[0]:close()

if __name__=='__main__':main()
