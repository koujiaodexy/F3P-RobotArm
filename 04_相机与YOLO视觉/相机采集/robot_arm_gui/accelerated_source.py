"""Camera-only compact-frame reader. Count each completed source ID once."""
import ctypes,mmap,os,time
from pathlib import Path
from robot_arm_gui.imx415_source import Imx415Source
from robot_arm_gui.color_blocks import BlockParameters,DEFAULT_BANDS,COLORS,validate_bands,_hue_tables,saturation_floors
from robot_arm_gui.vision import dependencies
from .feature_regions import bind,process

class ExpiredCameraFrame(RuntimeError):
 pass

class AcceleratedSource(Imx415Source):
 def __init__(self,library=None):
  super().__init__();self.library=library or str(Path(__file__).with_name('feature_access_aarch64.so'));self.feature_mem=None;self.feature_views=[];self.lib=None;self.next_count=1;self.processed=0;self.last_source_id=None;self.skipped=0;self.duplicates=0;self.epoch=0;self.accelerated=False;self.pattern=False;self.captured=0;self._last_processed_count=0;self._last_processed_source_id=None;self.allow_stream_gaps=False;self._capture_gap=0;self.capture_dropped=0
 def open(self):
  super().open()
  if self.control.read(0x380)!=0x434c5231:return
  self.lib=ctypes.CDLL(str(self.library));bind(self.lib)
  self.lib.f3p_color_write.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint32];self.lib.f3p_color_write.restype=ctypes.c_int
  self.lib.f3p_copy_words.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];self.lib.f3p_copy_words.restype=ctypes.c_int
  self.lib.f3p_copy_rgb.argtypes=[ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_int]*4),ctypes.c_uint32,ctypes.c_uint32];self.lib.f3p_copy_rgb.restype=ctypes.c_int
  if self.control.read(0x3b4)!=0x48533136 or self.control.read(0x3b8)!=105306 or self.control.read(0x3bc)!=(270<<16|480):raise RuntimeError('Unsupported compact camera geometry')
  cv,np=dependencies();fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
  try:self.feature_mem=mmap.mmap(fd,0x600000,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=0x3d800000)
  finally:os.close(fd)
  self.feature_views=[np.ndarray((270,780),np.uint32,buffer=self.feature_mem,offset=i*0x100000+32)for i in range(6)]
  # Camera registers are mapped by the existing exclusive owner controller.
  self._register=ctypes.c_uint32.from_buffer(self.control.mem);self._register_ptr=ctypes.addressof(self._register)
  self.accelerated=True
 def write_config(self,offset,value):
  rc=self.lib.f3p_color_write(self._register_ptr,offset,value)
  if rc:raise RuntimeError('Camera configuration refused: offset=%#x code=%d'%(offset,rc))
 def configure_features(self,parameters=None,bands=None,pattern=False):
  if not self.accelerated:raise RuntimeError('Compact camera firmware is not installed')
  p=(parameters or BlockParameters()).validate();bands=validate_bands(bands or DEFAULT_BANDS)
  self.write_config(0x384,0x434c0000);deadline=time.monotonic()+2
  while self.control.read(0x390)&8:
   if time.monotonic()>deadline:raise RuntimeError('Compact camera failed to drain')
   time.sleep(.002)
  time.sleep(.003);x,y,w,h=p.roi;x0,y0=int(x*480),int(y*270);x1,y1=min(480,round((x+w)*480)),min(270,round((y+h)*270))
  self.write_config(0x39c,(x1<<16)|x0);self.write_config(0x3a0,(y1<<16)|y0);self.write_config(0x3a4,(p.min_value<<8)|min(saturation_floors(p)))
  table,_=_hue_tables(tuple(bands[c]for c in COLORS))
  for i in range(180):self.write_config(0x3a8,0x4c550000|(i<<8)|((1<<(int(table[i])-1))if table[i]else 0))
  self.epoch=(self.epoch+1)&0xffffffff;self.write_config(0x3ac,self.epoch);self.pattern=bool(pattern)
  self.write_config(0x384,0x434c0001|(int(self.pattern)<<1));self.next_count=1;self.last_source_id=None;self.captured=0;self._last_processed_count=0;self._last_processed_source_id=None;self._capture_gap=0;self.parameters=p;self.bands=bands
  self.rate_stamp=time.monotonic();self.rate_frames=self.control.status()['source_frames']
 def header(self,slot):
  cv,np=dependencies();view=self.feature_views[slot];h=np.empty(8,np.uint32);t=np.empty(4,np.uint32)
  if self.lib.f3p_copy_words(view.ctypes.data-32,h.ctypes.data,8)or self.lib.f3p_copy_words(view.ctypes.data+270*780*4,t.ctypes.data,4):raise RuntimeError('Unaligned compact header')
  return tuple(map(int,h)),tuple(map(int,t))
 def pending(self):
  if self._heartbeat_error:raise RuntimeError('Camera heartbeat failed: '+str(self._heartbeat_error))
  errors=self.control.read(0x394)
  if errors:raise RuntimeError('Camera accelerator error: %#x'%errors)
  return (self.control.read(0x38c)-self.next_count+1)&0xffffffff
 def acquire_feature(self):
  lag=self.pending()
  if not lag:return None
  if lag>=6:
   if not self.allow_stream_gaps:self.skipped+=lag-5
   raise ExpiredCameraFrame('Analysis backlog exceeded retained camera frames: '+str(lag))
  slot=(self.next_count-1)%6;header,trailer=self.header(slot);fid=header[1]
  if self.allow_stream_gaps and((self.control.read(0x38c)-self.next_count+1)&0xffffffff)>=6:raise ExpiredCameraFrame('Camera slot expired during header acquisition')
  x,y,w,h=self.parameters.roi;x0,y0=int(x*480),int(y*270);x1,y1=min(480,round((x+w)*480)),min(270,round((y+h)*270))
  if header[0]!=0x43564d31 or header[2]!=(270<<16|480)or header[3]!=(y0<<16|x0)or header[4]!=(y1<<16|x1)or header[5]!=self.epoch or header[6]!=0x48533136 or header[7]!=int(self.pattern)or trailer[3]!=fid or trailer[1]!=(x1-x0)*(y1-y0):raise RuntimeError('Incoherent camera feature/header/config')
  if self.last_source_id is not None:
   delta=(fid-self.last_source_id)&0xffffffff
   if delta!=1+self._capture_gap:
    if delta==0:self.duplicates+=1
    else:self.skipped+=delta-1
    raise RuntimeError('Camera source frame discontinuity: '+str(delta))
  now=time.monotonic()
  return {'slot':slot,'count':self.next_count,'frame_id':fid,'header':header,'trailer':trailer,'compact':self.feature_views[slot],'captured_at':now,'backlog':lag}
 def recover_pending(self,limit=6):
  if not self.allow_stream_gaps:return 0
  lag=self.pending()
  if lag<limit:return 0
  lost=lag-1;self.next_count+=lost;self._capture_gap+=lost;self.capture_dropped+=lost
  return lost
 def verify_feature(self,item):
  completed=self.control.read(0x38c);age=(completed-item['count']+1)&0xffffffff;actual=self.header(item['slot'])
  detail='age=%d count=%d completed=%d expected_source=%d actual_source=%d trailer_source=%d'%(age,item['count'],completed,item['frame_id'],actual[0][1],actual[1][3])
  if age>=6:raise ExpiredCameraFrame('Camera buffer overwritten during analysis: '+detail)
  if actual!=(item['header'],item['trailer']):
   # Counter may have advanced while the header was being read. Only expired
   # slots are recoverable; corrupt metadata in a retained slot remains fatal.
   if((self.control.read(0x38c)-item['count']+1)&0xffffffff)>=6:raise ExpiredCameraFrame('Camera buffer expired during verification: '+detail)
   raise RuntimeError('Camera buffer overwritten or invalid within retained frame: '+detail)
 def finish_feature(self,item):
  self.verify_feature(item)
  self.next_count+=1;self.processed+=1;self.last_source_id=item['frame_id'];self.skipped+=self._capture_gap;self._capture_gap=0
 def copy_feature_snapshot(self,item):
  # This copy is validated while its physical slot is still retained. Analysis
  # thereafter owns a cached immutable array and never races DMA overwrites.
  cv,np=dependencies();snapshot=np.empty((270,780),np.uint32)
  rc=self.lib.f3p_copy_classified_features(item['compact'].ctypes.data,snapshot.ctypes.data,480,270,780)
  if rc:raise RuntimeError('Invalid camera feature snapshot: '+str(rc))
  self.verify_feature(item);snapshot.setflags(write=False)
  cached=dict(item,physical_compact=item['compact'],compact=snapshot,verified_snapshot=True)
  self.next_count+=1;self.last_source_id=item['frame_id'];self._capture_gap=0;self.captured+=1
  return cached
 def finish_snapshot(self,item,allow_gaps=False):
  if not item.get('verified_snapshot')or item['header'][5]!=self.epoch:raise RuntimeError('Invalid analysis snapshot or configuration epoch')
  delta=item['count']-self._last_processed_count
  if delta<1 or(not allow_gaps and delta!=1):raise RuntimeError('Cached analysis frame count discontinuity')
  if self._last_processed_source_id is not None and((item['frame_id']-self._last_processed_source_id)&0xffffffff)!=delta:raise RuntimeError('Cached analysis source ID discontinuity')
  self.skipped+=delta-1;self._last_processed_count=item['count'];self._last_processed_source_id=item['frame_id'];self.processed+=1
 def verify_preview(self,item):
  if item.get('cached_rgb_verified'):
   if item.get('cached_rgb_frame_id')!=item['frame_id']or not item.get('verified_snapshot'):raise RuntimeError('Incoherent cached preview identity')
   return
  self.verify_feature(item)
 def raw_frame(self,item):
  if item.get('cached_rgb_verified'):
   self.verify_preview(item);return item['cached_rgb']
  cv,np=dependencies();words=np.empty((270,480),np.uint32)
  rc=self.lib.f3p_copy_rgb(item.get('physical_compact',item['compact']).ctypes.data,words.ctypes.data,480,270,780,240,item['frame_id'],item['trailer'][2])
  if rc:raise RuntimeError('Camera preview failed its per-pixel frame/hash check: '+str(rc))
  return words.view(np.uint8).reshape(270,480,4)[:,:,:3].copy()
 def analyze(self,item,pool=None):
  return process(item['compact'],self.lib,self.parameters,self.bands,pool=pool,details=True,mean_value=item['trailer'][0]/item['trailer'][1])
 def close(self):
  failure=None
  try:
   if self.accelerated and self.control is not None:
    self.write_config(0x384,0x434c0000);deadline=time.monotonic()+2
    while self.control.read(0x390)&8:
     if time.monotonic()>=deadline:raise RuntimeError('Camera accelerator did not finish its accepted transfer')
     time.sleep(.002)
  except Exception as exc:failure=exc
  finally:
   self.accelerated=False;self.feature_views=[]
   try:
    if self.feature_mem is not None:self.feature_mem.close();self.feature_mem=None
   finally:
    if hasattr(self,'_register'):del self._register
    super().close()
  if failure is not None:raise failure
