"""Prototype of the unchanged contour stage consuming hardware-style planes."""
import ctypes,math,threading
from functools import lru_cache
from robot_arm_gui.color_blocks import COLORS,LABELS,BlockParameters,DEFAULT_BANDS,validate_bands,_hue_tables,canonical_hsv,saturation_floors
from robot_arm_gui.vision import dependencies

def bind(lib):
 lib.f3p_filter_saturation.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_void_p];lib.f3p_filter_saturation.restype=ctypes.c_int
 lib.f3p_copy_classified_features.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int];lib.f3p_copy_classified_features.restype=ctypes.c_int
 lib.f3p_copy_features.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int];lib.f3p_copy_features.restype=ctypes.c_int
 lib.f3p_contour_candidates.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_double,ctypes.c_void_p,ctypes.c_size_t];lib.f3p_contour_candidates.restype=ctypes.c_int
 lib.f3p_unpack_masks.argtypes=[ctypes.c_void_p,ctypes.c_void_p,*([ctypes.c_int]*4),ctypes.c_void_p];lib.f3p_unpack_masks.restype=ctypes.c_int
 lib.f3p_confidence_stats.argtypes=[ctypes.c_void_p,*([ctypes.c_int]*5),ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p];lib.f3p_confidence_stats.restype=ctypes.c_int

@lru_cache(maxsize=16)
def cost_orders(key):
 cv,np=dependencies();_,costs=_hue_tables(key)
 return [(np.ascontiguousarray(costs[i],dtype=np.float32),np.argsort(costs[i,:180],kind='stable').astype(np.uint8))for i in range(4)]

_scratch=threading.local()
def contour_scratch(height,width,np):
 size=height*width
 if getattr(_scratch,'size',0)<size:
  _scratch.size=480*270;_scratch.candidates=np.empty(_scratch.size,np.uint8);_scratch.workspace=np.empty(_scratch.size,np.uint32)
 return _scratch.candidates[:size].reshape(height,width),_scratch.workspace

def process(compact,lib,parameters=None,bands=None,pool=None,details=False,mean_value=0.):
 cv,np=dependencies();p=(parameters or BlockParameters()).validate();bands=validate_bands(bands or DEFAULT_BANDS);iw,ih=480,270;sw,sh=1920,1080;sx,sy=sw/iw,sh/ih
 planes=np.empty((4,ih,iw),np.uint8);bounds=np.empty((4,4),np.int32);stride=compact.strides[0]//4
 assert lib.f3p_unpack_masks(compact.ctypes.data,planes.ctypes.data,iw,ih,stride,iw*3//2,bounds.ctypes.data)==0
 floors=saturation_floors(p)
 if len(set(floors))>1:
  # PL captures the least restrictive floor. Native filtering reads only
  # HS16 groups needed by stricter colours; RGB stays with FPGA HDMI.
  native_floors=np.asarray(floors,dtype=np.uint8)
  if lib.f3p_filter_saturation(compact.ctypes.data,planes.ctypes.data,iw,ih,stride,native_floors.ctypes.data):raise RuntimeError('Invalid saturation feature data')
  kernel=cv.getStructuringElement(cv.MORPH_ELLIPSE,(3,3))
  for ci,floor in enumerate(floors):
   if floor>min(floors):
    bx,by,bw,bh=cv.boundingRect(planes[ci])
    if not bw or not bh:
     bounds[ci]=(0,0,0,0);continue
    # Six pixels cover the complete open/close neighbourhood. This keeps
    # identical edge handling while avoiding work on empty image regions.
    lx,ly=max(0,bx-6),max(0,by-6);rx,ry=min(iw,bx+bw+6),min(ih,by+bh+6)
    crop=planes[ci,ly:ry,lx:rx]
    clean=cv.morphologyEx(crop,cv.MORPH_OPEN,kernel)
    crop[:]=cv.morphologyEx(clean,cv.MORPH_CLOSE,kernel,iterations=2)
    bx,by,bw,bh=cv.boundingRect(planes[ci]);bounds[ci]=(bx,by,bx+bw,by+bh)
 x,y,w,h=p.roi;x0,y0=int(x*iw),int(y*ih);x1,y1=min(iw,round((x+w)*iw)),min(ih,round((y+h)*ih));roi_area=(x1-x0)*(y1-y0);detections=[];rejected=[0]*4
 cached=cost_orders(tuple(bands[c]for c in COLORS))
 def one_color(ci,color):
  local_detections=[]
  mask=planes[ci,y0:y1,x0:x1];hue_cost,order=cached[ci]
  lx,ly,rx,ry=map(int,bounds[ci]);lx=max(lx,x0);ly=max(ly,y0);rx=min(rx,x1);ry=min(ry,y1)
  if lx>=rx or ly>=ry:return []
  # Preserve the original mask for confidence and preview. Only discard an
  # entire 8-connected component when its pixel-center bounding rectangle
  # proves its external contour cannot reach the existing area threshold.
  selected=planes[ci,ly:ry,lx:rx];candidates,workspace=contour_scratch(*selected.shape,np)
  rc=lib.f3p_contour_candidates(selected.ctypes.data,selected.strides[0],candidates.ctypes.data,selected.shape[1],selected.shape[0],p.min_area*(iw/640.)**2,workspace.ctypes.data,workspace.size)
  if rc<0:raise RuntimeError('Invalid contour candidate data: '+str(rc))
  bx0,by0,bw0,bh0=cv.boundingRect(candidates)
  if not bw0 or not bh0:return []
  contours=cv.findContours(candidates[by0:by0+bh0,bx0:bx0+bw0],cv.RETR_EXTERNAL,cv.CHAIN_APPROX_SIMPLE,offset=(lx+bx0-x0,ly+by0-y0))[-2]
  for contour in contours:
   area=float(cv.contourArea(contour))
   if area<p.min_area*(iw/640.)**2:continue
   # The same rejection predicates, evaluated before calculations whose
   # result cannot affect an already rejected contour.
   if area>roi_area*p.max_area_fraction:rejected[ci]+=1;continue
   rect=cv.minAreaRect(contour);rw,rh=rect[1];box_area=rw*rh;aspect=max(rw,rh)/max(1.,min(rw,rh));fill=area/max(1.,box_area)
   if aspect>p.max_aspect or fill<p.min_rectangularity:rejected[ci]+=1;continue
   hull_area=cv.contourArea(cv.convexHull(contour));solidity=area/max(1.,hull_area)
   if solidity<p.min_solidity:rejected[ci]+=1;continue
   points=cv.boxPoints(rect);points[:,0]+=x0;points[:,1]+=y0;moments=cv.moments(contour)
   if moments['m00']<=0:continue
   cx=(moments['m10']/moments['m00']+x0)*sx;cy=(moments['m01']/moments['m00']+y0)*sy;bx,by,bw,bh=cv.boundingRect(contour)
   object_mask=np.zeros((bh,bw),np.uint8);cv.drawContours(object_mask,[contour],-1,255,-1,offset=(-bx,-by));selected=mask[by:by+bh,bx:bx+bw];stats=np.empty(3,np.float64)
   rc=lib.f3p_confidence_stats(compact.ctypes.data,stride,bx+x0,by+y0,bw,bh,object_mask.ctypes.data,object_mask.strides[0],selected.ctypes.data,selected.strides[0],hue_cost.ctypes.data,order.ctypes.data,stats.ctypes.data)
   if rc:raise RuntimeError('Invalid feature data: '+str(rc))
   hue_fit=1.-min(1.,float(stats[0]));chroma=float(stats[1])/255.;confidence=min(.99,max(0.,.45*hue_fit+.25*chroma+.15*min(1.,fill)+.15*min(1.,solidity)))
   local_detections.append({'color':color,'label':LABELS[color],'center':[round(cx,2),round(cy,2)],'bbox':[round((bx+x0)*sx,2),round((by+y0)*sy,2),round(bw*sx,2),round(bh*sy,2)],'polygon':[[round(float(px)*sx,2),round(float(py)*sy,2)]for px,py in points],'area_px':round(area*sx*sy,2),'working_area_px':round(area,2),'confidence':round(confidence,3),'rectangularity':round(fill,3),'solidity':round(solidity,3)})
  return local_detections
 if pool is None:
  for ci,c in enumerate(COLORS):detections.extend(one_color(ci,c))
 else:
  # Start the largest masks first so a long colour does not wait behind
  # two short colours on the same CPU. Collect in original colour order.
  order=sorted(range(4),key=lambda i:cv.countNonZero(planes[i]),reverse=True)
  tasks={ci:pool.submit(one_color,ci,COLORS[ci])for ci in order}
  for ci in range(4):detections.extend(tasks[ci].result())
 detections.sort(key=lambda d:(-d['area_px'],d['color'],d['center'][0]));detections=detections[:32]
 if not details:return detections
 return {'detections':detections,'source_size':[sw,sh],'analysis_size':[iw,ih],'roi':[round(x0*sx),round(y0*sy),round((x1-x0)*sx),round((y1-y0)*sy)],'counts':{c:sum(d['color']==c for d in detections)for c in COLORS},'rejected_shapes':sum(rejected),'masks':{c:planes[ci,y0:y1,x0:x1]for ci,c in enumerate(COLORS)},'roi_origin':[x0,y0],'quality':{'mean_brightness':round(mean_value,1),'low_light':mean_value<45}}

def model(frame,parameters=None,bands=None):
 from robot_arm_gui.color_blocks import detect_blocks
 cv,np=dependencies();p=parameters or BlockParameters();iw,ih=480,270;ref=detect_blocks(frame,p,bands,source_size=(1920,1080));x0,y0=ref['roi_origin'];cw,ch=next(iter(ref['masks'].values())).shape[::-1]
 crop=frame[y0:y0+ch,x0:x0+cw];hsv=canonical_hsv(cv.GaussianBlur(crop,(3,3),0));out=np.zeros((ih,iw*3//2+iw//8),np.uint32)
 hs=np.zeros((ih,iw),np.uint16);hs[y0:y0+ch,x0:x0+cw]=hsv[:,:,0].astype(np.uint16)|(hsv[:,:,1].astype(np.uint16)<<8)
 out[:,:iw//2]=hs[:,0::2].astype(np.uint32)|(hs[:,1::2].astype(np.uint32)<<16)
 out[:,iw//2:iw*3//2]=frame[:,:,0].astype(np.uint32)|(frame[:,:,1].astype(np.uint32)<<8)|(frame[:,:,2].astype(np.uint32)<<16)
 labels=np.zeros((ih,iw),np.uint8)
 for ci,c in enumerate(COLORS):labels[y0:y0+ch,x0:x0+cw]|=(ref['masks'][c]>0).astype(np.uint8)<<ci
 for i in range(8):out[:,iw*3//2:]|=labels[:,i::8].astype(np.uint32)<<(4*i)
 return out,ref
