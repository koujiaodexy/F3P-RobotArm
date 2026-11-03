"""One optional RGB/COCO owner. No arm backend, no cloud, no model auto-download."""
import argparse,hashlib,json,os,signal,subprocess,sys,threading,time
from collections import deque
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CAMERA=Path('/opt/f3p-control-candidates/osd-engineering-trial-20261019/app')

def atomic_json(path,value):
    temporary=path.with_suffix('.pending');temporary.write_text(json.dumps(value,ensure_ascii=False)+'\n',encoding='utf8');temporary.replace(path)


class DesktopPreview:
    """Bounded desktop copy of the same detected frame, alongside FPGA HDMI."""
    def __init__(self,directory,cv,labels,clock=time.monotonic,fps_limit=5,retained=3,throttle=True):
        self.directory,self.cv,self.labels,self.clock=directory,cv,labels,clock
        self.fps_limit,self.retained,self.throttle=fps_limit,retained,throttle
        self.last=-float('inf');self.files=deque();self.frames=0;self.fields={}

    def publish(self,item,bgr,detections):
        now=self.clock()
        if self.throttle and now-self.last<1./self.fps_limit:return dict(self.fields)
        self.last=now
        cv=self.cv;annotated=bgr.copy()
        for row in detections:
            x0,y0,x1,y1=[round(v) for v in row['bbox_xyxy']]
            cv.rectangle(annotated,(x0,y0),(x1,y1),(40,220,255),2)
            label=self.labels[row['class_id']] if row['class_id']<len(self.labels) else str(row['class_id'])
            cv.putText(annotated,'%s %.0f%%'%(label,100*row['confidence']),
                (x0,max(12,y0-4)),cv.FONT_HERSHEY_SIMPLEX,.4,(40,220,255),1,cv.LINE_AA)
        ok,jpeg=cv.imencode('.jpg',annotated,[cv.IMWRITE_JPEG_QUALITY,75])
        if not ok:raise RuntimeError('Desktop preview encoding failed')
        name='frame-%08x.jpg'%item['frame_id']
        path=self.directory/name;temporary=self.directory/'preview.pending'
        temporary.write_bytes(jpeg.tobytes());temporary.replace(path)
        if path not in self.files:self.files.append(path)
        while len(self.files)>self.retained:self.files.popleft().unlink(missing_ok=True)
        self.frames+=1
        self.fields=dict(preview_name=name,preview_captured_at=item['captured_at'],
                         desktop_preview_fps_limit=self.fps_limit,jpeg_frames=self.frames)
        return dict(self.fields)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True,type=Path)
    parser.add_argument('--session-id',required=True);parser.add_argument('--parent-pid',required=True,type=int)
    parser.add_argument('--benchmark-seconds',type=float,default=0)
    args=parser.parse_args();directory=args.directory.resolve()
    if len(args.session_id)!=32 or any(c not in '0123456789abcdef' for c in args.session_id):raise ValueError('Invalid session')
    assert directory.is_dir() and directory.name==args.session_id and directory.stat().st_uid==os.geteuid()
    stop=threading.Event()
    for number in (signal.SIGINT,signal.SIGTERM):signal.signal(number,lambda *_:stop.set())
    def watch_parent():
        while not stop.wait(.1):
            if os.getppid()!=args.parent_pid or (directory/'stop.request').exists():stop.set()
    watcher=threading.Thread(target=watch_parent,daemon=True,name='coco-task-watch');watcher.start()
    report=dict(session_id=args.session_id,state='loading',detections=[],motion_enabled=False)
    status=directory/'status.json';atomic_json(status,report)
    source=window=detector=capture=publisher=osd=desktop_process=None;measurements=[];recent=deque(maxlen=180);benchmark_start=None;completed_count=0
    try:
        meta=json.loads((ROOT/'manifest.json').read_text())
        for name,digest in meta['sha256'].items():
            assert '/' not in name and '\\' not in name and name not in ('.','..')
            assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
        if meta['backend'] not in ('alnpu_hybrid','alnpu_full','alnpu_cpu_concat'):raise RuntimeError('视觉必须使用已验证硬NPU后端，未转为CPU')
        sys.path.insert(0,str(CAMERA))
        from robot_arm_gui.vision import dependencies
        cv,np=dependencies()
        from yolo_decode import letterbox,decode_heads
        from coco_policy import RETAINED_IDS,selection_spec
        from inference import AlnpuDetector
        from robot_arm_gui.accelerated_source import AcceleratedSource,ExpiredCameraFrame
        from hardware_window import HardwareWindow
        cv.setNumThreads(1 if meta.get('pipeline') else 2)
        labels=meta['class_names']
        desktop=DesktopPreview(directory,cv,labels)
        if meta.get('class_selection')!=selection_spec():raise RuntimeError('物品类别配置与本次物品和积木名单不一致')
        model_class_ids=meta.get('model_class_ids',list(range(80)))
        aux_cpu=None
        cpus=sorted(os.sched_getaffinity(0))
        if meta.get('pin_threads'):
            cpus=sorted(os.sched_getaffinity(0))
            if len(cpus)>=2:
                os.sched_setaffinity(0,{cpus[0]});aux_cpu=cpus[1]
                report['thread_cpus']=dict(inference=cpus[0],capture=aux_cpu,publication=aux_cpu)
        input_size=meta.get('input_size',320);model_name=meta.get('model_name','yolov8n-320-uint8.onnx')
        backend='Alnpu' if meta['backend']=='alnpu_full' else 'Alnpu+CpuRef'
        detector=AlnpuDetector(ROOT,directory,stop,model_class_ids=model_class_ids,input_size=input_size,model_name=model_name,backend=backend)
        if stop.is_set():return
        source=AcceleratedSource();source.open();source.allow_stream_gaps=True
        read_frame=source.raw_frame
        if meta.get('fast_rgb'):
            from camera_pipeline import read_bgr
            read_frame=lambda item:read_bgr(source,item,cv,np)
        window=HardwareWindow(directory/'window.json',args.session_id);window.attach(source)
        stop.wait(.02);source.configure_features()
        deadline=time.monotonic()+1.
        while source.control.read(0x38c)<3:
            if time.monotonic()>deadline:raise RuntimeError('Camera compact buffers did not settle')
            if stop.wait(.01):return
        if meta.get('hardware_preview'):
            from robot_arm_gui.direct_preview_mailbox import mapped_publisher
            osd=mapped_publisher(source.control)
            desktop_process=subprocess.Popen([sys.executable,'-B',str(ROOT/'desktop_preview_worker.py'),
                '--directory',str(directory),'--session-id',args.session_id,'--parent-pid',str(os.getpid()),
                '--cpus',','.join(map(str,cpus))],stdin=subprocess.DEVNULL,close_fds=True)
        def emit(item,bgr,detections,evidence,cycle_started,captured,prepared,started,elapsed):
            nonlocal completed_count
            if osd is not None:
                boxes=[dict(stable=True,color={80:'red',81:'yellow',82:'green'}.get(r['class_id'],'yellow'),bbox=[r['bbox_xyxy'][0],r['bbox_xyxy'][1],r['bbox_xyxy'][2]-r['bbox_xyxy'][0],r['bbox_xyxy'][3]-r['bbox_xyxy'][1]]) for r in detections]
                osd.publish(dict(source_size=[480,270],tracked=boxes),item['frame_id'],source.control.read(0x388))
                window.service(report)
                report.update(preview_transport='fpga_hdmi',osd_sent=osd.sent,osd_stale_drops=osd.stale_drops,
                    osd_busy_drops=osd.busy_drops,osd_truncated_boxes=osd.truncated)
            try:
                report.pop('desktop_preview_error',None)
                if desktop_process is None:report.update(desktop.publish(item,bgr,detections))
                elif desktop_process.poll() is not None:report['desktop_preview_error']='Independent preview exited'
            except Exception as error:
                # A viewing failure must not stop recognition or acquire camera IO again.
                report.update(preview_name='',desktop_preview_error=str(error))
            report.update(state='running',frame_id=int(item['frame_id']),captured_at=item['captured_at'],
                source_size=[480,270],detections=detections,inference_seconds=elapsed,
                backend=backend,model_sha256=meta['sha256'][model_name],npu=evidence,
                voice_npu_unchanged=True,coherent_rgb_verified=True,completed_at=time.monotonic())
            report['class_selection']=selection_spec()
            now=time.monotonic();recent.append(now);completed_count+=1
            report['performance']=dict(completed_frames=completed_count,
                detection_fps=(len(recent)-1)/(recent[-1]-recent[0]) if len(recent)>1 else 0.,
                capture_dropped=source.capture_dropped+(capture.discarded if capture else 0),duplicates=source.duplicates)
            atomic_json(status,report)
            completed=time.monotonic()
            sample=dict(frame_id=int(item['frame_id']),completed_at=completed,cycle_ms=1000*(completed-cycle_started),
                capture_ms=1000*(captured-cycle_started),preprocess_ms=1000*(prepared-captured),
                inference_and_decode_ms=1000*elapsed,model_ms=evidence['model_compute_ms'],
                postprocess_ms=1000*(completed-started-elapsed),hard_irq=evidence['hard_irq'],soft_irq=evidence.get('soft_irq',0))
            sample.update({key:evidence[key] for key in ('python_input_ms','python_wait_ms','python_total_ms','native_total_ms','encode_ms','read_ms') if key in evidence})
            if args.benchmark_seconds:
                measurements.append(sample)
        if meta.get('pipeline'):
            from camera_pipeline import CapturePipeline,ResultPipeline
            capture=CapturePipeline(source,cv,letterbox,input_size,meta.get('byte_protocol',False),stop,ExpiredCameraFrame,cpu=aux_cpu,read_frame=read_frame,demand=meta.get('demand_capture',False))
            publisher=ResultPipeline(emit,cpu=aux_cpu)
        while not stop.is_set():
            if os.getppid()!=args.parent_pid or (directory/'stop.request').exists():break
            if capture:
                packet=capture.next()
                if packet is None:break
                item,bgr,tensor,geometry,cycle_started,captured,prepared=packet
            else:
                cycle_started=time.monotonic();source.recover_pending(limit=2)
                try:
                    item=source.acquire_feature()
                    if item is None:stop.wait(.001);continue
                    bgr=read_frame(item);source.finish_feature(item)
                except ExpiredCameraFrame:continue
                captured=time.monotonic();tensor,geometry=letterbox(bgr,cv,size=input_size,byte_tensor=meta.get('byte_protocol',False));prepared=time.monotonic()
            if benchmark_start is None:benchmark_start=cycle_started
            started=time.monotonic()
            if meta.get('native_candidates'):detections,evidence=detector.infer(tensor,geometry=geometry)
            else:heads,evidence=detector.infer(tensor)
            if stop.is_set():break
            if not meta.get('native_candidates'):detections=decode_heads(heads,geometry,input_size=input_size,allowed_class_ids=RETAINED_IDS,model_class_ids=model_class_ids)
            elapsed=time.monotonic()-started
            result=(item,bgr,detections,evidence,cycle_started,captured,prepared,started,elapsed)
            if publisher:publisher.submit(*result)
            else:emit(*result)
            if args.benchmark_seconds and time.monotonic()-benchmark_start>=args.benchmark_seconds:break
    except Exception as exc:
        report.update(state='failed',error=str(exc),detections=[]);atomic_json(status,report);raise
    finally:
        stop.set()
        if desktop_process is not None:
            desktop_process.terminate()
            try:desktop_process.wait(timeout=3)
            except subprocess.TimeoutExpired:desktop_process.kill();desktop_process.wait(timeout=3)
        cleanup_errors=[]
        for task in (capture,publisher):
            try:
                if task is not None:task.close()
            except Exception as error:cleanup_errors.append(str(error))
        try:
            if osd is not None:osd.clear()
            if window is not None:window.close()
        finally:
            try:
                if source is not None:source.close()
            finally:
                if detector is not None:detector.close()
        watcher.join(timeout=.5)
        if cleanup_errors:report.update(state='failed',error='; '.join(cleanup_errors),detections=[])
        if args.benchmark_seconds:
            atomic_json(directory/'benchmark.json',dict(samples=measurements,backend=report.get('backend'),
                model_sha256=report.get('model_sha256'),capture_dropped=getattr(source,'capture_dropped',0)+(capture.discarded if capture else 0),
                duplicates=getattr(source,'duplicates',None),state=report['state'],error=report.get('error'),motion_requested=False,
                display={k:report[k] for k in ('preview_fps','preview_scanout_fps','preview_unique_frames','preview_health','display_fps_verified','preview_transport','jpeg_frames','osd_sent','osd_stale_drops') if k in report}))
        if report['state']!='failed':report.update(state='stopped',detections=[]);atomic_json(status,report)
        else:atomic_json(status,report)

if __name__=='__main__':main()
