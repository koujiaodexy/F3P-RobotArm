"""Independent 480x270 viewing only. Read-only DMA mapping, no camera/motor control."""
import argparse,ctypes,json,mmap,os,signal,struct,sys,time
from collections import deque
from pathlib import Path
from camera_worker import DesktopPreview,atomic_json,CAMERA

FPS=35

def coherent(head,tail,after,after_tail,count,completed,pixels_valid):
    return (bool(pixels_valid) and tuple(head)==tuple(after) and tuple(tail)==tuple(after_tail)
            and int(head[0])==0x43564d31 and int(head[2])==(270<<16|480)
            and int(head[1])==int(tail[3]) and ((completed-count)&0xffffffff)<6)

def current_report(path,session_id,now):
    try:
        if path.stat().st_size>65536:return None
        report=json.loads(path.read_text())
        age=now-report.get('completed_at',-1e30)
        if report.get('session_id')==session_id and report.get('state')=='running' and 0<=age<=1.2:
            return report
    except (OSError,ValueError,TypeError):pass
    return None

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--session-id',required=True);p.add_argument('--parent-pid',type=int,required=True)
    p.add_argument('--cpus',default='');args=p.parse_args()
    root=args.directory.resolve();assert root.name==args.session_id and len(args.session_id)==32
    assert root.stat().st_uid==os.geteuid() and not root.stat().st_mode&0o077
    if args.cpus:os.sched_setaffinity(0,{int(v) for v in args.cpus.split(',')})
    stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
    def alive():return not stopped and os.getppid()==args.parent_pid and not (root/'stop.request').exists()
    sys.path.insert(0,'/opt/f3p-control')
    from robot_arm_gui.vision import dependencies
    cv,np=dependencies();cv.setNumThreads(1)
    labels=json.loads(Path(__file__).with_name('manifest.json').read_text())['class_names']
    writer=DesktopPreview(root,cv,labels,fps_limit=FPS,retained=8,throttle=False)
    lib=ctypes.CDLL(str(CAMERA/'robot_arm_gui/feature_access_aarch64.so'))
    lib.f3p_copy_words.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];lib.f3p_copy_words.restype=ctypes.c_int
    status=root/'desktop.json';timeline=deque(maxlen=100);frames=invalid=0;last=None
    timing=deque(maxlen=100)
    fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
    try:
        with mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=0xa0000000) as ctl, \
             mmap.mmap(fd,0x600000,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=0x3d800000) as mem:
            view=np.ndarray((0x600000//4,),np.uint32,buffer=mem)
            head=np.empty(8,np.uint32);tail=np.empty(4,np.uint32)
            after=np.empty(8,np.uint32);after_tail=np.empty(4,np.uint32);words=np.empty((270,480),np.uint32)
            try:
                while alive():
                    began=time.monotonic();report=current_report(root/'status.json',args.session_id,began)
                    if report is None:time.sleep(.02);continue
                    count=struct.unpack_from('<I',ctl,0x38c)[0]
                    if not count or count==last:time.sleep(.001);continue
                    last=count;slot=(count-1)%6;ptr=view.ctypes.data+slot*0x100000
                    assert lib.f3p_copy_words(ptr,head.ctypes.data,8)==0
                    assert lib.f3p_copy_words(ptr+32+270*780*4,tail.ctypes.data,4)==0
                    fid=int(head[1])
                    compact=np.ndarray((270,780),np.uint32,buffer=mem,offset=slot*0x100000+32)
                    read_started=time.monotonic()
                    np.copyto(words,compact[:,240:720]);del compact
                    copied=time.monotonic()
                    pixels_valid=np.all((words>>24)==(fid&255))
                    assert lib.f3p_copy_words(ptr,after.ctypes.data,8)==0
                    assert lib.f3p_copy_words(ptr+32+270*780*4,after_tail.ctypes.data,4)==0
                    completed=struct.unpack_from('<I',ctl,0x38c)[0]
                    if not coherent(head,tail,after,after_tail,count,completed,pixels_valid):
                        invalid+=1;continue
                    bgr=cv.cvtColor(words.view(np.uint8).reshape(270,480,4),cv.COLOR_BGRA2BGR)
                    # The video is independent of detection. Never use this path for control.
                    detection_age=began-report.get('captured_at',-1e30)
                    delta=(fid-int(report.get('frame_id',fid)))&0xffffffff
                    boxes=report.get('detections',[]) if 0<=detection_age<=.25 and delta<=15 else []
                    encode_started=time.monotonic()
                    fields=writer.publish(dict(frame_id=fid,captured_at=began),bgr,boxes)
                    now=time.monotonic();timeline.append(now);frames+=1
                    timing.append((copied-read_started,encode_started-copied,now-encode_started,now-began))
                    try:stream_active=0<=time.time()-Path('/run/f3p-camera-stream/viewer-active').stat().st_mtime<2.
                    except OSError:stream_active=False
                    atomic_json(status,dict(fields,session_id=args.session_id,state='running',
                        frame_id=fid,source_size=[480,270],published_at=now,
                        preview_fps=(len(timeline)-1)/(timeline[-1]-timeline[0]) if len(timeline)>1 else 0.,
                        timing_ms=[1000*sum(row[i] for row in timing)/len(timing) for i in range(4)],
                        desktop_stream_active=stream_active,
                        independent_frames=frames,invalid_frames=invalid,read_only=True,motion_enabled=False))
                    time.sleep(max(0.,1./FPS-(time.monotonic()-began)))
            finally:del view
    except Exception as error:
        atomic_json(status,dict(session_id=args.session_id,state='failed',error=str(error)))
        raise
    finally:
        os.close(fd)
        if alive():stop()

if __name__=='__main__':main()
