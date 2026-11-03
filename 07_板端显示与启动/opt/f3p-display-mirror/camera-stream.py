"""Latest-frame MJPEG viewer, loopback only; never opens a camera or motor device."""
import argparse,json,os,re,socket,stat,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

ROOT=Path('/run/f3p-coco-preview')
ACTIVE=Path('/run/f3p-camera-stream/viewer-active')
SLOTS=threading.BoundedSemaphore(2)
VIEWERS=dict(connected=0,last_id=None,sent_frames=0)
VIEWER_LOCK=threading.Lock()
BRIDGE=b'''<!doctype html><html><meta charset="utf-8"><script src="/position.js"></script></html>'''
POSITION_JS=b'''let pending=false;window.addEventListener('message',async e=>{if(e.origin!=='http://127.0.0.1:6080'||e.source!==parent||e.data?.type!=='f3p-preview-poll'||pending)return;pending=true;try{const s=await(await fetch('/status',{cache:'no-store'})).json();parent.postMessage({type:'f3p-preview-position',window:s.running?s.window:null,preview_fps:s.preview_fps},e.origin);}catch(error){parent.postMessage({type:'f3p-preview-position',window:null},e.origin);}finally{pending=false;}});'''
HTML='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>实时识别画面</title><style>body{margin:0;background:#14202b;color:#edf4fa;font:18px sans-serif;text-align:center}main{max-width:1100px;margin:30px auto;padding:20px}h1{font-size:26px}img{width:100%;max-width:960px;aspect-ratio:16/9;object-fit:contain;background:#080c10}p{color:#becddd}a{color:#8ed0ff}</style><main><h1>实时识别画面</h1><p id="status">等待板卡开始识别…</p><img id="video" alt="识别画面"><p>480 × 270 原始分辨率 · 视频目标 35 帧/秒</p><a href="http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale&view_only=false&reconnect=true&reconnect_delay=2000" target="_blank" rel="noopener">打开板卡操作界面</a><p>在操作界面进入「全自动夹取 / COCO物品识别」并开始识别，视频会自动出现。</p></main><script src="/viewer.js"></script></html>'''.encode('utf8')
EMBED=b'''<!doctype html><html><meta charset="utf-8"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#000}img{display:block;width:100%;height:100%;object-fit:fill}</style><img id="video" alt=""><script src="/viewer.js"></script></html>'''
JS=b'''let active=false,loaded=false;const img=document.getElementById('video');img.onload=()=>{loaded=true;};img.onerror=()=>{active=false;loaded=false;};setInterval(async()=>{try{const s=await(await fetch('/status',{cache:'no-store'})).json();if(s.running&&!active){img.src='/stream.mjpg?view=embedded&t='+Date.now();active=true;}if(!s.running&&active){img.removeAttribute('src');active=false;loaded=false;}parent.postMessage({type:'f3p-preview-position',window:s.running&&active&&(loaded||img.naturalWidth>0)?s.window:null},'http://127.0.0.1:6080');}catch(e){img.removeAttribute('src');active=false;loaded=false;parent.postMessage({type:'f3p-preview-position',window:null},'http://127.0.0.1:6080');}},250);'''

def read_file(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_size>limit:
            raise ValueError('Invalid preview file')
        with os.fdopen(fd,'rb',closefd=False) as f:return f.read(limit+1)
    finally:os.close(fd)

def read_report(directory):
    if not re.fullmatch('[0-9a-f]{32}',directory.name):return None
    try:
        info=directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077:return None
        if (directory/'stop.request').exists():return None
        report=json.loads(read_file(directory/'desktop.json',65536))
        age=time.monotonic()-report.get('published_at',-1e30)
        name=report.get('preview_name','')
        if (report.get('session_id')!=directory.name or report.get('state')!='running'
            or not 0<=age<=1.2 or report.get('source_size')!=[480,270]
            or not isinstance(name,str) or not re.fullmatch(r'frame-[0-9a-f]{8}\.jpg',name)):return None
        return directory,report
    except (OSError,ValueError,TypeError):return None

def preview_window(item):
    if not item:return None
    directory,report=item
    try:
        value=json.loads(read_file(directory/'window.json',4096))
        if value.get('session_id')!=directory.name or not 0<=time.monotonic()-value.get('timestamp',-1e30)<=.8:return None
        if not value.get('visible'):return None
        x,y,w,h=[value.get(k) for k in ('x','y','width','height')]
        if not all(type(v) is int for v in (x,y,w,h)) or not (0<=x<1920 and 0<=y<1080 and 0<w<=1920-x and 0<h<=1080-y):return None
        return dict(visible=True,x=x,y=y,width=w,height=h)
    except (OSError,ValueError,TypeError):return None

def latest(root=ROOT):
    try:items=[item for item in (read_report(d) for d in root.iterdir()) if item]
    except OSError:return None
    return max(items,key=lambda item:item[1]['published_at']) if items else None

class LatestFrame:
    def __init__(self,root):self.root=root;self.directory=None;self.scan_at=0.;self.lock=threading.Lock()
    def read(self):
        with self.lock:
            item=read_report(self.directory) if self.directory else None
            if item:return item
            if time.monotonic()-self.scan_at<1:return None
            self.scan_at=time.monotonic();item=latest(self.root)
            self.directory=item[0] if item else None
            return item

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def send_blob(self,data,kind):
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        ancestors='http://127.0.0.1:6080' if self.path.split('?',1)[0] in ('/embed','/bridge') else "'none'"
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'unsafe-inline'; frame-ancestors "+ancestors)
        self.end_headers();self.wfile.write(data)
    def do_GET(self):
        self.connection.settimeout(3)
        self.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        host=self.headers.get('Host','');origin=self.headers.get('Origin')
        if (host not in ('127.0.0.1:5902','127.0.0.1:5903')
            or self.headers.get('Sec-Fetch-Site')=='cross-site'
            or origin not in (None,'http://'+host)):
            self.send_error(403);return
        path=self.path.split('?',1)[0]
        if path=='/':
            self.send_response(302);self.send_header('Location','http://127.0.0.1:6080/control.html');self.send_header('Content-Length','0');self.end_headers();return
        if path=='/embed':return self.send_blob(EMBED,'text/html; charset=utf-8')
        if path=='/viewer.js':return self.send_blob(JS,'application/javascript')
        if path=='/bridge':return self.send_blob(BRIDGE,'text/html; charset=utf-8')
        if path=='/position.js':return self.send_blob(POSITION_JS,'application/javascript')
        if path=='/status':
            item=self.server.frames.read();r=item[1] if item else {}
            with VIEWER_LOCK:viewers=dict(VIEWERS)
            return self.send_blob(json.dumps(dict(service='f3p-camera-stream-v1',running=bool(item),source_size=[480,270],
                preview_fps=r.get('preview_fps',0),frame_id=r.get('frame_id'),window=preview_window(item),viewers=viewers,fps_limit=35,motion_enabled=False)).encode(),'application/json')
        if path!='/stream.mjpg':self.send_error(404);return
        query=parse_qs(urlsplit(self.path).query);viewer=query.get('viewer',[''])[0]
        if query.get('view')!=['embedded'] or not re.fullmatch(r'(native|probe)-[a-zA-Z0-9-]{1,64}',viewer):self.send_error(410,'Refresh the control page');return
        if not SLOTS.acquire(False):self.send_error(503);return
        with VIEWER_LOCK:VIEWERS['connected']+=1;VIEWERS['last_id']=viewer
        try:
            self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control','no-store');self.send_header('Connection','close');self.end_headers()
            previous=None;idle=time.monotonic();heartbeat=0.
            while time.monotonic()-idle<4:
                if time.monotonic()-heartbeat>.5:
                    ACTIVE.touch();heartbeat=time.monotonic()
                item=self.server.frames.read()
                if item:
                    directory,report=item;key=(directory.name,report['frame_id'])
                    if key!=previous:
                        try:data=read_file(directory/report['preview_name'],262144)
                        except (OSError,ValueError):time.sleep(.01);continue
                        if not data.startswith(b'\xff\xd8'):break
                        header=('\r\n--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\nX-Frame-Id: %d\r\n\r\n'%(len(data),key[1])).encode()
                        self.wfile.write(header+data);self.wfile.flush();previous=key;idle=time.monotonic()
                        with VIEWER_LOCK:VIEWERS['sent_frames']+=1
                time.sleep(.012)
        except (OSError,ValueError):pass
        finally:
            with VIEWER_LOCK:VIEWERS['connected']-=1
            SLOTS.release();self.close_connection=True

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args()
    ACTIVE.parent.mkdir(mode=0o700,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',5902),Handler);server.daemon_threads=True;server.frames=LatestFrame(a.root)
    server.serve_forever()
