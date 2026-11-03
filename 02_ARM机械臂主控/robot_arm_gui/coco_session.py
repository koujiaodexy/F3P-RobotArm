"""Own an on-demand camera/COCO child. Never instantiate a motor backend."""
import json,os,re,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from .coco_objects import checked_report,selection

RUNTIME=Path('/opt/f3p-npu/coco-yolov8n-20261025')

class CocoSession:
    vision_kind='coco_six'
    def __init__(self,entrypoint=None,runtime=None,popen=subprocess.Popen,clock=time.monotonic):
        self.entrypoint=Path(entrypoint or RUNTIME/'camera_worker.py')
        self.runtime=Path(runtime or (('/run/f3p-coco-preview') if os.name=='posix' and os.geteuid()==0 else Path(tempfile.gettempdir())/'f3p-coco-preview'))
        self._popen,self.clock=popen,clock
        self.process=self.log=None;self.telemetry=None;self.error='';self._stopping=None;self._terminated=False
        self.desktop_telemetry=None

    @property
    def running(self):return self.process is not None

    @property
    def stopping(self):return self.running and self._stopping is not None

    def start(self):
        if self.running:return False
        if not self.entrypoint.is_file():raise RuntimeError('COCO物品识别尚未安装')
        self.runtime.mkdir(parents=True,mode=0o700,exist_ok=True)
        if os.name=='posix':
            info=self.runtime.stat()
            if info.st_uid!=os.geteuid() or info.st_mode&0o077:raise RuntimeError('物品识别会话目录权限无效')
        self.session_id=uuid.uuid4().hex;self.directory=self.runtime/self.session_id;self.directory.mkdir(mode=0o700)
        self.status_path=self.directory/'status.json';self.preview_path=self.directory/'preview.jpg'
        self.desktop_path=self.directory/'desktop.json';self.desktop_telemetry=None
        self.window_path=self.directory/'window.json'
        self.log=(self.directory/'worker.log').open('w',encoding='utf8')
        self.telemetry=None;self.error='';self._stopping=None;self._terminated=False
        env=os.environ.copy();env.pop('PYTHONPATH',None);env['PYTHONUNBUFFERED']='1';env['PYTHONDONTWRITEBYTECODE']='1'
        try:
            self.process=self._popen([sys.executable,'-B',str(self.entrypoint),'--directory',str(self.directory),
                '--session-id',self.session_id,'--parent-pid',str(os.getpid())],stdin=subprocess.DEVNULL,
                stdout=self.log,stderr=subprocess.STDOUT,close_fds=True,env=env)
        except BaseException:
            self.log.close();self.log=None;raise
        return True

    def stop(self):
        if self.running and self._stopping is None:
            self.set_window(visible=False)
            self._stopping=self.clock();(self.directory/'stop.request').write_text(self.session_id,encoding='ascii')

    def set_window(self,x=0,y=0,visible=False,width=576,height=324):
        if not self.running:return
        if (type(width) is not int or type(height) is not int or width%192 or not 2<=width//192<=8 or height!=108*(width//192)
                or type(x) is not int or type(y) is not int or not 0<=x<=1920-width or not 0<=y<=1080-height):raise ValueError('Invalid preview geometry')
        value=dict(session_id=self.session_id,timestamp=self.clock(),x=x,y=y,width=width,height=height,visible=bool(visible))
        temporary=self.window_path.with_name('window.pending');temporary.write_text(json.dumps(value),encoding='utf8');temporary.replace(self.window_path)

    def poll(self):
        if not self.running:return None
        try:
            if self.status_path.is_file() and self.status_path.stat().st_size<=65536:
                value=json.loads(self.status_path.read_text(encoding='utf8'))
                if value.get('session_id')==self.session_id:
                    self.telemetry=value
                    name=value.get('preview_name','')
                    if isinstance(name,str) and re.fullmatch(r'frame-[0-9a-f]{8}\.jpg',name):
                        self.preview_path=self.directory/name
        except (OSError,ValueError):pass
        try:
            path=getattr(self,'desktop_path',None)
            if path is not None and path.is_file() and path.stat().st_size<=65536:
                value=json.loads(path.read_text(encoding='utf8'))
                if value.get('session_id')==self.session_id:
                    self.desktop_telemetry=value
                    name=value.get('preview_name','')
                    if value.get('state')=='running' and isinstance(name,str) and re.fullmatch(r'frame-[0-9a-f]{8}\.jpg',name):
                        self.preview_path=self.directory/name
        except (OSError,ValueError):pass
        code=self.process.poll()
        if code is None:
            if self._stopping is not None:
                age=self.clock()-self._stopping
                # Allow the bounded in-flight hard-NPU call to finish before
                # escalating; killing it mid-workload can strand device state.
                if age>25 and not self._terminated:self.process.terminate();self._terminated=True
                elif age>30:self.process.kill()
            return self.telemetry
        if code and self._stopping is None:self.error=(self.telemetry or {}).get('error','物品识别进程已退出，请重新识别')
        self.process=None
        if self.log:self.log.close();self.log=None
        return self.telemetry

    def targets(self):
        if not self.running or self._stopping is not None:raise ValueError('请先开始识别')
        return checked_report(self.telemetry,self.session_id,self.clock())

    def select(self,index,displayed_report=None):
        if not self.running or self._stopping is not None:raise ValueError('请先开始识别')
        target=selection(displayed_report or self.telemetry,self.session_id,index,self.clock());self.stop();return target

    def close(self):self.stop()
