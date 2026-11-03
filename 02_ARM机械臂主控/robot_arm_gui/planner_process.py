"""Math-only subprocess; validated frame blocks cross a bounded pipe.

The caller retains every CAN/MMIO operation and the existing RollingFrames
braking semantics. Complete grasp requests reuse one idle interpreter.
Reader threads perform IPC only, never trajectory math.
"""
import atexit,hashlib,os,pickle,queue,struct,subprocess,sys,threading,time
from pathlib import Path
from .rolling_trajectory import RollingFrames

MAX_MESSAGE=64*1024*1024
_warm_lock=threading.Lock();_warm=None;_shutdown=False

def source_identity():
    root=Path(__file__).resolve().parent
    names=('planner_process.py','planning_worker.py','reference_adapter.py','local_trajectory.py','streaming_response.py','grasp_transfer.py','grasp_motion.py')
    return dict(root=str(root),sha256={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names})

def stop_worker(process):
    """Reap a worker even when it exits between poll and signal delivery."""
    if process.poll() is None:
        try:process.terminate()
        except ProcessLookupError:pass
        try:process.wait(1)
        except subprocess.TimeoutExpired:
            try:process.kill()
            except ProcessLookupError:pass
            process.wait(1)

def launch_worker():
    env=dict(os.environ,F3P_PLANNER_CHILD='1',F3P_PLANNER_PARENT_PID=str(os.getpid()))
    env['PYTHONPATH']=str(Path(__file__).resolve().parent.parent)+os.pathsep+env.get('PYTHONPATH','')
    # With -m, cwd precedes PYTHONPATH. An inherited candidate directory used
    # to shadow the installed package even with the correct PYTHONPATH.
    options=dict(stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None,env=env,close_fds=True,bufsize=0,
                 cwd=str(Path(__file__).resolve().parent.parent))
    if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW
    return subprocess.Popen([sys.executable,'-u','-m','robot_arm_gui.planning_worker'],**options)

def prewarm():
    """One idle interpreter loads math ahead of the next target; no planning IO."""
    global _warm
    with _warm_lock:
        if _shutdown:return
        if _warm is None or _warm.poll() is not None:
            if _warm is not None:
                _warm.stdin.close();_warm.stdout.close()
            _warm=launch_worker()

def take_worker():
    global _warm
    with _warm_lock:
        worker=_warm;_warm=None
    if worker is not None and worker.poll() is None:return worker
    if worker is not None:
        worker.stdin.close();worker.stdout.close()
    return launch_worker()


def return_worker(worker):
    """Keep one idle math process after a complete grasp response."""
    global _warm
    with _warm_lock:
        if not _shutdown and _warm is None and worker.poll() is None:
            _warm=worker
            return
    stop_worker(worker)
    worker.stdin.close();worker.stdout.close()

def shutdown_warm():
    global _warm,_shutdown
    with _warm_lock:_shutdown=True;worker=_warm;_warm=None
    if worker is not None:
        stop_worker(worker)
        worker.stdin.close();worker.stdout.close()

atexit.register(shutdown_warm)

def send(stream,message):
    data=pickle.dumps(message,protocol=4)
    if len(data)>MAX_MESSAGE:raise ValueError('planner IPC message too large')
    for part in (struct.pack('!I',len(data)),data):
        view=memoryview(part)
        while view:
            written=stream.write(view)
            if written is None or written<=0:raise BrokenPipeError('planner pipe write failed')
            view=view[written:]
    stream.flush()

def read_exact(stream,count):
    data=bytearray()
    while len(data)<count:
        part=stream.read(count-len(data))
        if not part:raise EOFError('planner process disconnected')
        data.extend(part)
    return data

def receive(stream):
    size=struct.unpack('!I',read_exact(stream,4))[0]
    if not 0<size<=MAX_MESSAGE:raise ValueError('invalid planner IPC size')
    return pickle.loads(read_exact(stream,size))

class ProcessFrames(RollingFrames):
    def close(self):
        self.cancel.set()
        with self.lock:self.closed=True
        stop_worker(self.process)
        if self.producer and self.producer is not threading.current_thread():self.producer.join(1)
        for stream in (self.process.stdin,self.process.stdout):
            if stream:
                try:stream.close()
                except OSError:pass
        prewarm()

def plan_remote(operation,args,check=lambda:None):
    began=time.monotonic();cancel=threading.Event();messages=queue.Queue(maxsize=2)
    reusable=operation=='grasp_prepare'
    process=take_worker()
    def reader():
        try:
            while not cancel.is_set():
                message=receive(process.stdout)
                while not cancel.is_set():
                    try:messages.put(message,timeout=.02);break
                    except queue.Full:pass
                if message['type'] in ('done','error') or reusable and message['type']=='ready':return
        except Exception as exc:
            while not cancel.is_set():
                try:messages.put(dict(type='error',error=str(exc)),timeout=.02);return
                except queue.Full:pass
    io=threading.Thread(target=reader,name='planner-ipc-reader',daemon=True);io.start()
    frames=None
    def get_message():
        while True:
            check()
            timeout=(args.get('hardware') or {}).get('initial_timeout_seconds',100)
            if time.monotonic()-began>timeout:raise ValueError('独立规划进程起步超时')
            try:return messages.get(timeout=.02)
            except queue.Empty:pass
    try:
        send(process.stdin,dict(operation=operation,args=args))
        if not reusable:process.stdin.close()
        first=get_message()
        if first['type']=='error':
            error=ValueError(first['error'])
            for key,value in first.get('details',{}).items():
                if key in ('joint_step_degrees','path_fraction','failure_kind'):setattr(error,key,value)
            raise error
        if first['type']!='ready':raise ValueError('独立规划进程协议错误')
        if first.get('source_identity')!=source_identity():
            raise ValueError('数学子进程代码来源不一致；未发布运动指令，请重启界面')
        report=first['report'];native=report['native_report']
        native.update(planning_process_pid=process.pid,math_backend=first['math_backend'],planner_source_identity=first['source_identity'])
        if not native.get('rolling'):
            from .reference_endpoint.trajectory_frames import PackedFrames
            native['frames']=PackedFrames(native['frames']['packed_bytes'])
            if reusable:
                cancel.set();io.join(1)
                if io.is_alive():raise RuntimeError('规划结果接收线程未结束')
                check()
                return_worker(process)
                return report
            process.wait(2);cancel.set();io.join(1)
            process.stdout.close()
            prewarm()
            return report
        frames=ProcessFrames(first['head'],first['reserve'],native['duration_s'],cancel)
        frames.process=process;native['frames']=frames
        def transfer():
            try:
                while not cancel.is_set():
                    status=process.poll()
                    if status is not None and status!=0:
                        with frames.lock:frames.error='独立规划进程异常退出，沿已校验制动段停车：'+str(status)
                        break
                    with frames.lock:
                        ahead=len(frames.head)-getattr(frames,'consumed',0)
                    if ahead>250 and not frames.complete:cancel.wait(.02);continue
                    try:message=messages.get(timeout=.02)
                    except queue.Empty:continue
                    if message['type']=='error':
                        print('CART_PROCESS_FAILED',dict(pid=process.pid,exit_code=process.poll(),error=message['error'],details=message.get('details',{}),received_frames=len(frames.head),consumed_frames=getattr(frames,'consumed',0)),flush=True)
                        with frames.lock:frames.error='独立后续规划失败，沿已校验制动段停车：'+message['error']
                        break
                    if message['type']=='done':break
                    if message['type']!='block':raise ValueError('unexpected planner message')
                    with frames.lock:
                        if not frames.publish(message['head'],message['reserve']):break
                        native.update(message['updates'])
            except Exception as exc:
                with frames.lock:frames.error='独立规划传输失败，沿已校验制动段停车：'+str(exc)
            finally:
                if frames.complete:
                    try:process.wait(2)
                    except subprocess.TimeoutExpired:stop_worker(process)
        frames.producer=threading.Thread(target=transfer,name='planner-frame-transfer',daemon=True)
        frames.producer.start()
        print('CART_PROCESS_READY',dict(pid=process.pid,math_backend=first['math_backend'],seconds=time.monotonic()-began,
            initial_frames=len(first['head']),complete=frames.complete,source_identity=first['source_identity']),flush=True)
        return report
    except BaseException:
        cancel.set()
        if frames:frames.close()
        else:stop_worker(process)
        io.join(1)
        for stream in (process.stdin,process.stdout):
            if stream:
                try:stream.close()
                except OSError:pass
        prewarm()
        raise
