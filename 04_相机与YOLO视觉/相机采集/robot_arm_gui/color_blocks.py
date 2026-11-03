"""Bounded four-colour block detection in image coordinates; no motor imports."""
from __future__ import annotations
from functools import lru_cache
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import time
from .vision import dependencies

COLORS=('red','yellow','blue','green')
LABELS={'red':'红','yellow':'黄','blue':'蓝','green':'绿'}
BGR={'red':(55,65,245),'yellow':(30,220,245),'blue':(245,150,45),'green':(95,215,65)}
DEFAULT_BANDS={'red':(0.,10.),'yellow':(28.,10.),'blue':(114.,19.),'green':(63.,24.)}

@dataclass(frozen=True)
class BlockParameters:
    min_area: int=200
    min_saturation: int=70
    min_value: int=45
    min_rectangularity: float=.62
    min_solidity: float=.80
    max_aspect: float=3.5
    max_area_fraction: float=.45
    min_confirmations: int=3
    roi: tuple=(0.,0.,1.,1.)
    min_green_saturation: int | None=None
    min_yellow_saturation: int | None=None

    def validate(self):
        if not 20<=self.min_area<=100000:raise ValueError('最小面积应在20～100000分析像素之间')
        if not 10<=self.min_saturation<=240 or not 5<=self.min_value<=240:raise ValueError('颜色过滤参数超出范围')
        for value in (self.min_green_saturation,self.min_yellow_saturation):
            if value is not None and (type(value)is not int or not 10<=value<=240):raise ValueError('分颜色饱和度应在10～240之间')
        if not .3<=self.min_rectangularity<=.98 or not .5<=self.min_solidity<=1:raise ValueError('形状参数超出范围')
        if not 1<=self.max_aspect<=10 or not .01<=self.max_area_fraction<=.95:raise ValueError('尺寸参数超出范围')
        if not 1<=self.min_confirmations<=10:raise ValueError('稳定帧数应在1～10之间')
        if len(self.roi)!=4 or not all(math.isfinite(float(v)) for v in self.roi):raise ValueError('识别区域无效')
        x,y,w,h=self.roi
        if not (0<=x<1 and 0<=y<1 and .05<=w<=1 and .05<=h<=1 and x+w<=1.000001 and y+h<=1.000001):raise ValueError('识别区域超出画面')
        return self


def saturation_floors(parameters):
    """Per-colour floors, in COLORS order; old profiles retain one shared floor."""
    p=parameters
    return (p.min_saturation,p.min_saturation if p.min_yellow_saturation is None else p.min_yellow_saturation,
            p.min_saturation,p.min_saturation if p.min_green_saturation is None else p.min_green_saturation)

def validate_bands(bands):
    if set(bands)!=set(COLORS):raise ValueError('校色配置必须包含红黄蓝绿四种颜色')
    result={}
    for c,(center,radius) in bands.items():
        center,radius=float(center),float(radius)
        if not math.isfinite(center+radius) or not 0<=center<180 or not 4<=radius<=30:raise ValueError('色相校准范围无效')
        result[c]=(center,radius)
    return result

def config_path():
    if os.name=='nt':return Path(__file__).resolve().parents[2]/'Config'/'color-blocks.json'
    return Path('/home/uisrc/.config/f3p-vision/color-blocks.json')

def save_profile(filename,parameters,bands):
    parameters.validate();bands=validate_bands(bands)
    path=Path(filename);path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps({'schema':1,'parameters':asdict(parameters),'bands':bands},ensure_ascii=False,indent=2)
    temporary=path.with_suffix('.pending');temporary.write_text(data,encoding='utf-8');os.replace(str(temporary),str(path))

def load_profile(filename):
    v=json.loads(Path(filename).read_text(encoding='utf-8'))
    if v.get('schema')!=1:raise ValueError('不支持此校色文件版本')
    p=BlockParameters(**v['parameters']).validate()
    return p,validate_bands(v['bands'])

def hue_distance(h,center,np):
    difference=np.abs(h.astype(np.float32)-center)
    return np.minimum(difference,180.-difference)

@lru_cache(maxsize=16)
def _hue_tables(key):
    # Hue has only 180 possible 8-bit values. Classify those once, not every pixel.
    _,np=dependencies();hue=np.arange(256,dtype=np.uint8)
    costs=np.stack([hue_distance(hue,center,np)/radius for center,radius in key])
    ordered=np.sort(costs,axis=0);best=np.argmin(costs,axis=0)
    good=(hue<180)&(ordered[0]<=1.)&((ordered[1]-ordered[0])>=.08)
    classes=np.where(good,best+1,0).astype(np.uint8)
    return classes,costs

@lru_cache(maxsize=1)
def _hsv_tables():
    _,np=dependencies()
    return (np.asarray([0]+[round((255<<12)/i) for i in range(1,256)],np.int32),
            np.asarray([0]+[round((180<<12)/(6*i)) for i in range(1,256)],np.int32))

@lru_cache(maxsize=1)
def _native_hsv():
    if os.name=='nt':return None
    try:
        import ctypes
        lib=ctypes.CDLL(str(Path(__file__).with_name('feature_access_aarch64.so')))
        fn=lib.f3p_bgr_to_hsv
        fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_size_t,ctypes.c_size_t]
        fn.restype=ctypes.c_int
        return lib,fn
    except (OSError,AttributeError):return None

def canonical_hsv(frame):
    """One integer HSV definition for CPU, calibration and FPGA; no HAL rounding."""
    _,np=dependencies()
    if frame is None or frame.ndim!=3 or frame.shape[2]!=3 or frame.dtype!=np.uint8:raise ValueError('需要8位BGR彩色图像')
    image=np.ascontiguousarray(frame);h,w=image.shape[:2];native=_native_hsv()
    if native is not None:
        out=np.empty_like(image)
        if native[1](image.ctypes.data,out.ctypes.data,w,h,image.strides[0],out.strides[0]):raise ValueError('整数颜色转换参数无效')
        return out
    sdiv,hdiv=_hsv_tables();b,g,r=(image[:,:,i].astype(np.int32) for i in range(3))
    value=np.maximum(np.maximum(r,g),b);minimum=np.minimum(np.minimum(r,g),b);difference=value-minimum
    saturation=(difference*sdiv[value]+2048)>>12
    numerator=np.where(value==r,g-b,np.where(value==g,b-r+2*difference,r-g+4*difference))
    hue=(numerator*hdiv[difference]+2048)>>12;hue=np.where(hue<0,hue+180,hue)
    return np.stack((hue,saturation,value),axis=-1).astype(np.uint8)

def detect_blocks(frame,parameters=None,bands=None,source_size=None):
    cv,np=dependencies();parameters=(parameters or BlockParameters()).validate();bands=validate_bands(bands or DEFAULT_BANDS)
    if frame is None or frame.ndim!=3 or frame.shape[2]!=3 or frame.dtype!=np.uint8:raise ValueError('需要8位BGR彩色图像')
    height,width=frame.shape[:2]
    if min(height,width)<8:raise ValueError('图像尺寸过小')
    sw,sh=source_size or (width,height)
    if sw<=0 or sh<=0:raise ValueError('源图像尺寸无效')
    scale=min(1.,640./width,480./height)
    image=cv.resize(frame,(max(1,round(width*scale)),max(1,round(height*scale))),interpolation=cv.INTER_AREA) if scale<1 else frame
    ih,iw=image.shape[:2];sx,sy=sw/iw,sh/ih
    x,y,w,h=parameters.roi
    x0,y0=int(x*iw),int(y*ih);x1,y1=min(iw,round((x+w)*iw)),min(ih,round((y+h)*ih))
    crop=image[y0:y1,x0:x1];hsv=canonical_hsv(cv.GaussianBlur(crop,(3,3),0))
    hue,sat,value=cv.split(hsv)
    floors=saturation_floors(parameters)
    valid=cv.inRange(hsv,(0,min(floors),parameters.min_value),(179,255,255))
    table,costs=_hue_tables(tuple(bands[c]for c in COLORS))
    classes=cv.LUT(hue,table);classes=cv.bitwise_and(classes,classes,mask=valid)
    if len(set(floors))>1:
        required=np.asarray((0,)+floors,np.uint8)
        classes=np.where(sat>=required[classes],classes,0).astype(np.uint8)
    kernel=cv.getStructuringElement(cv.MORPH_ELLIPSE,(3,3));detections=[]
    masks={};rejected=0;roi_area=crop.shape[0]*crop.shape[1]
    for ci,color in enumerate(COLORS):
        mask=cv.compare(classes,ci+1,cv.CMP_EQ)
        mask=cv.morphologyEx(mask,cv.MORPH_OPEN,kernel)
        mask=cv.morphologyEx(mask,cv.MORPH_CLOSE,kernel,iterations=2)
        masks[color]=mask
        contours=cv.findContours(mask,cv.RETR_EXTERNAL,cv.CHAIN_APPROX_SIMPLE)[-2]
        for contour in contours:
            area=float(cv.contourArea(contour))
            if area<parameters.min_area*(iw/640.)**2:continue
            rect=cv.minAreaRect(contour);rw,rh=rect[1]
            box_area=rw*rh;hull_area=cv.contourArea(cv.convexHull(contour))
            aspect=max(rw,rh)/max(1.,min(rw,rh));fill=area/max(1.,box_area);solidity=area/max(1.,hull_area)
            if area>roi_area*parameters.max_area_fraction or aspect>parameters.max_aspect or fill<parameters.min_rectangularity or solidity<parameters.min_solidity:
                rejected+=1;continue
            points=cv.boxPoints(rect);points[:,0]+=x0;points[:,1]+=y0
            moments=cv.moments(contour)
            if moments['m00']<=0:continue
            cx=(moments['m10']/moments['m00']+x0)*sx;cy=(moments['m01']/moments['m00']+y0)*sy
            bx,by,bw,bh=cv.boundingRect(contour)
            object_mask=np.zeros_like(mask);cv.drawContours(object_mask,[contour],-1,255,-1)
            pixels=(object_mask>0)&(mask>0)
            hue_fit=1.-min(1.,float(np.median(costs[ci][hue[pixels]])))
            chroma=float(np.median(sat[pixels]))/255.
            confidence=min(.99,max(0.,.45*hue_fit+.25*chroma+.15*min(1.,fill)+.15*min(1.,solidity)))
            detections.append({'color':color,'label':LABELS[color],'center':[round(cx,2),round(cy,2)],
                'bbox':[round((bx+x0)*sx,2),round((by+y0)*sy,2),round(bw*sx,2),round(bh*sy,2)],
                'polygon':[[round(float(px)*sx,2),round(float(py)*sy,2)]for px,py in points],
                'area_px':round(area*sx*sy,2),'working_area_px':round(area,2),'confidence':round(confidence,3),
                'rectangularity':round(fill,3),'solidity':round(solidity,3)})
    detections.sort(key=lambda d:(-d['area_px'],d['color'],d['center'][0]))
    return {'detections':detections[:32],'source_size':[sw,sh],'analysis_size':[iw,ih],
            'roi':[round(x0*sx),round(y0*sy),round((x1-x0)*sx),round((y1-y0)*sy)],
            'counts':{c:sum(d['color']==c for d in detections[:32])for c in COLORS},'rejected_shapes':rejected,
            'masks':masks,'roi_origin':[x0,y0],
            'quality':{'mean_brightness':round(float(cv.mean(value)[0]),1),'low_light':float(cv.mean(value)[0])<45}}

class BlockTracker:
    """Only current-frame observations can be reported as confirmed targets."""
    def __init__(self,min_confirmations=3,max_gap_seconds=.45):
        self.min_confirmations=min_confirmations;self.max_gap=max_gap_seconds;self._tracks={};self._next_id=1;self._stamp=None
    def clear(self):self._tracks.clear();self._stamp=None
    def update(self,detections,now=None):
        now=time.monotonic()if now is None else float(now)
        if self._stamp is not None and now<=self._stamp:
            raise ValueError('跟踪时间必须递增，重复帧不能增加稳定帧数')
        self._stamp=now
        self._tracks={i:t for i,t in self._tracks.items()if now-t['last']<=self.max_gap}
        available=set(self._tracks);output=[]
        for d in detections:
            candidates=[]
            for i in available:
                old=self._tracks[i];dx=d['center'][0]-old['d']['center'][0];dy=d['center'][1]-old['d']['center'][1]
                gate=max(25.,math.hypot(d['bbox'][2],d['bbox'][3])*.7)
                if old['d']['color']==d['color'] and math.hypot(dx,dy)<=gate:candidates.append((math.hypot(dx,dy),i))
            if candidates:
                _,i=min(candidates);available.remove(i);old=self._tracks[i]
                streak=old['streak']+1 if old['seen'] else 1
            else:i=self._next_id;self._next_id+=1;streak=1
            current={'d':dict(d),'last':now,'streak':streak,'seen':True};self._tracks[i]=current
            item=dict(d,track_id=i,stable_frames=streak,stable=streak>=self.min_confirmations)
            output.append(item)
        for i in available:self._tracks[i]['seen']=False;self._tracks[i]['streak']=0
        return output

def annotate(frame,result,show_mask=False):
    cv,np=dependencies();out=frame.copy();ih,iw=out.shape[:2];sw,sh=result['source_size'];sx,sy=iw/sw,ih/sh
    if show_mask:
        tint=np.zeros_like(out)
        for c,mask in result.get('masks',{}).items():
            ox,oy=result['roi_origin'];canvas=np.zeros((result['analysis_size'][1],result['analysis_size'][0]),np.uint8)
            canvas[oy:oy+mask.shape[0],ox:ox+mask.shape[1]]=mask
            resized=cv.resize(canvas,(iw,ih),interpolation=cv.INTER_NEAREST)
            tint[resized>0]=BGR[c]
        out=cv.addWeighted(out,.35,tint,.65,0)
    rx,ry,rw,rh=result['roi'];cv.rectangle(out,(round(rx*sx),round(ry*sy)),(round((rx+rw)*sx)-1,round((ry+rh)*sy)-1),(165,180,195),1)
    for d in result.get('tracked',result['detections']):
        color=BGR[d['color']];stable=d.get('stable',True)
        pts=np.asarray([[round(x*sx),round(y*sy)]for x,y in d['polygon']],np.int32)
        cv.polylines(out,[pts],True,(12,18,25),5 if stable else 3,cv.LINE_AA)
        cv.polylines(out,[pts],True,color,2 if stable else 1,cv.LINE_AA)
        cx,cy=round(d['center'][0]*sx),round(d['center'][1]*sy)
        cv.drawMarker(out,(cx,cy),(12,18,25),cv.MARKER_CROSS,14,4)
        cv.drawMarker(out,(cx,cy),(245,250,255),cv.MARKER_CROSS,12,1)
        label=d['color'].upper()+(' #'+str(d.get('track_id',0))if stable else ' ...')
        tx,ty=max(0,int(pts[:,0].min())),max(19,int(pts[:,1].min())-6)
        (tw,th),baseline=cv.getTextSize(label,cv.FONT_HERSHEY_SIMPLEX,.5,1)
        cv.rectangle(out,(tx,ty-th-4),(min(iw-1,tx+tw+6),ty+baseline+2),(12,18,25),-1)
        cv.putText(out,label,(tx+3,ty),cv.FONT_HERSHEY_SIMPLEX,.5,color,1,cv.LINE_AA)
    return out

def sample_band(frame,x,y,color,bands=None):
    cv,np=dependencies()
    if color not in COLORS:raise ValueError('请选择红黄蓝绿中的一种颜色')
    h,w=frame.shape[:2]
    if not math.isfinite(float(x)+float(y)) or not 0<=x<w or not 0<=y<h:raise ValueError('取样位置超出画面')
    x,y=int(x),int(y)
    roi=frame[max(0,y-6):min(h,y+7),max(0,x-6):min(w,x+7)]
    hsv=canonical_hsv(roi).reshape(-1,3);hsv=hsv[(hsv[:,1]>65)&(hsv[:,2]>30)]
    if len(hsv)<25:raise ValueError('取样区域太暗或接近白灰色，请点积木中央')
    angle=hsv[:,0].astype(float)*math.pi/90;center=(math.atan2(float(np.sin(angle).mean()),float(np.cos(angle).mean()))*90/math.pi)%180
    default_center,default_radius=DEFAULT_BANDS[color]
    if abs((center-default_center+90)%180-90)>default_radius+8:raise ValueError('取样颜色与所选颜色差距较大，请检查颜色和位置')
    spread=float(np.percentile(hue_distance(hsv[:,0],center,np),95))
    if spread>12:raise ValueError('取样区颜色混杂，请点积木中央的均匀区域')
    result=dict(bands or DEFAULT_BANDS);result[color]=(round(center,2),round(min(24.,max(6.,spread+5.)),2))
    return validate_bands(result)
