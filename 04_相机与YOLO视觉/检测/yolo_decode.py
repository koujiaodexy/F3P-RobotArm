"""YOLOv8 raw detection heads, with host-side DFL and class-aware NMS."""
import math
import numpy as np

INPUT_SIZE=320

def decode_candidates(candidates,geometry,model_class_ids=None,confidence=.30,iou=.45,limit=64):
    """Map compact native DFL results and apply the same clipped class NMS."""
    mapping=class_mapping(model_class_ids)
    if not isinstance(candidates,list) or len(candidates)>4096:raise ValueError('Invalid compact candidates')
    rows=[];scale=geometry['scale'];left,top=geometry['left'],geometry['top']
    for item in candidates:
        if not isinstance(item,list) or len(item)!=6 or type(item[0]) is not int or not 0<=item[0]<len(mapping):raise ValueError('Invalid compact class')
        if not all(type(v) in (int,float) and math.isfinite(v) for v in item[1:]) or not confidence<=item[1]<=1:raise ValueError('Invalid compact values')
        x0=max(0.,min(geometry['width'],(item[2]-left)/scale));y0=max(0.,min(geometry['height'],(item[3]-top)/scale))
        x1=max(0.,min(geometry['width'],(item[4]-left)/scale));y1=max(0.,min(geometry['height'],(item[5]-top)/scale))
        if x1>x0 and y1>y0:rows.append(dict(class_id=mapping[item[0]],confidence=item[1],bbox_xyxy=[x0,y0,x1,y1]))
    rows.sort(key=lambda v:-v['confidence']);kept=[]
    for row in rows:
        box=row['bbox_xyxy'];area=(box[2]-box[0])*(box[3]-box[1]);suppressed=False
        for previous in kept:
            if previous['class_id']!=row['class_id']:continue
            b=previous['bbox_xyxy'];common=max(0,min(box[2],b[2])-max(box[0],b[0]))*max(0,min(box[3],b[3])-max(box[1],b[1]))
            if common/max(1e-12,area+(b[2]-b[0])*(b[3]-b[1])-common)>iou:suppressed=True;break
        if not suppressed:kept.append(row)
        if len(kept)==limit:break
    return kept

def input_shape(size):
    shape=(size,size) if isinstance(size,int) else tuple(size)
    if shape not in ((192,192),(256,256),(320,320),(384,384),(320,384)):
        raise ValueError('Unsupported detector input shape')
    return shape

def class_mapping(ids=None):
    values=tuple(range(80)) if ids is None else tuple(ids)
    if (not 1<=len(values)<=83 or len(set(values))!=len(values)
            or any(type(v) is not int or not 0<=v<83 for v in values)):
        raise ValueError('Invalid COCO class mapping')
    return values

def unpack_heads(raw,input_size=INPUT_SIZE,model_class_ids=None):
    height,width=input_shape(input_size)
    channels=64+len(class_mapping(model_class_ids))
    value=np.asarray(raw,dtype=np.float32)
    grids=[(height//stride,width//stride) for stride in (8,16,32)]
    if value.shape!=(1,channels,sum(h*w for h,w in grids)):raise ValueError('Unexpected packed YOLOv8 COCO output: '+str(value.shape))
    heads=[];begin=0
    for h,w in grids:
        heads.append(value[:,:,begin:begin+h*w].reshape(1,channels,h,w));begin+=h*w
    return heads

def letterbox(bgr,cv,size=INPUT_SIZE,byte_tensor=False):
    if bgr.ndim!=3 or bgr.shape[2]!=3 or bgr.dtype!=np.uint8:raise ValueError('Expected uint8 BGR image')
    target_h,target_w=input_shape(size)
    h,w=bgr.shape[:2];scale=min(target_w/w,target_h/h)
    nw,nh=round(w*scale),round(h*scale);left=(target_w-nw)//2;top=(target_h-nh)//2
    canvas=np.full((target_h,target_w,3),114,np.uint8)
    canvas[top:top+nh,left:left+nw]=cv.resize(bgr,(nw,nh),interpolation=cv.INTER_LINEAR)
    tensor=canvas[:,:,::-1].transpose(2,0,1)[None]
    if not byte_tensor:tensor=tensor.astype(np.float32)/255.
    return np.ascontiguousarray(tensor),dict(scale=scale,left=left,top=top,width=w,height=h)

def decode_heads(heads,geometry,confidence=.30,iou=.45,limit=64,input_size=INPUT_SIZE,
                 allowed_class_ids=None,model_class_ids=None):
    if not .01<=confidence<=1 or not 0<iou<1 or not 1<=limit<=64:raise ValueError('Invalid detection limits')
    height,width=input_shape(input_size)
    mapping=np.asarray(class_mapping(model_class_ids),dtype=np.int64)
    allowed=None if allowed_class_ids is None else class_mapping(allowed_class_ids)
    channels=64+len(mapping)
    grids=[(height//stride,width//stride) for stride in (8,16,32)]
    if len(heads)!=3 or sorted(tuple(np.asarray(h).shape)[-2:] for h in heads)!=sorted(grids):
        raise ValueError('All three YOLOv8 detection scales are required')
    boxes=[];scores=[];classes=[]
    for head in heads:
        a=np.asarray(head,dtype=np.float32)
        if a.ndim!=4 or a.shape[0]!=1 or a.shape[1]!=channels or tuple(a.shape[-2:]) not in grids:
            raise ValueError('Unexpected YOLOv8 COCO head shape: '+str(a.shape))
        if not np.isfinite(a).all():raise ValueError('Non-finite inference output')
        gh,gw=a.shape[-2:];stride=width/gw
        raw=a[0].reshape(channels,-1);cls=raw[64:]
        # Sigmoid is monotonic: threshold and choose a class before expensive DFL.
        ids=np.argmax(cls,axis=0);logits=cls[ids,np.arange(gh*gw)]
        canonical=mapping[ids]
        accepted=logits>=math.log(confidence/(1-confidence)) if confidence<1 else np.zeros(logits.shape,dtype=bool)
        # Keep the winner across the original vocabulary, then drop excluded
        # categories. Never force a cat/bus into a retained class at this stage.
        if allowed is not None:accepted&=np.isin(canonical,allowed)
        keep=np.flatnonzero(accepted)
        if not len(keep):continue
        reg=raw[:64,keep].reshape(4,16,-1)
        prob=np.exp(reg-reg.max(axis=1,keepdims=True));prob/=prob.sum(axis=1,keepdims=True)
        distances=(prob*np.arange(16,dtype=np.float32)[None,:,None]).sum(axis=1)
        cx=keep%gw+.5;cy=keep//gw+.5
        box=np.stack((cx-distances[0],cy-distances[1],cx+distances[2],cy+distances[3]),axis=1)*stride
        box[:,[0,2]]=(box[:,[0,2]]-geometry['left'])/geometry['scale']
        box[:,[1,3]]=(box[:,[1,3]]-geometry['top'])/geometry['scale']
        box[:,[0,2]]=np.clip(box[:,[0,2]],0,geometry['width'])
        box[:,[1,3]]=np.clip(box[:,[1,3]],0,geometry['height'])
        valid=(box[:,2]>box[:,0])&(box[:,3]>box[:,1])
        boxes.extend(box[valid]);scores.extend((1/(1+np.exp(-np.clip(logits[keep],-80,80))))[valid]);classes.extend(canonical[keep][valid])
    if not boxes:return []
    boxes=np.asarray(boxes);scores=np.asarray(scores);classes=np.asarray(classes)
    order=np.argsort(-scores,kind='stable');kept=[]
    while len(order) and len(kept)<limit:
        first=order[0];kept.append(int(first));others=order[1:]
        if not len(others):break
        lo=np.maximum(boxes[first,:2],boxes[others,:2]);hi=np.minimum(boxes[first,2:],boxes[others,2:])
        intersect=np.maximum(hi-lo,0).prod(axis=1)
        area=(boxes[first,2:]-boxes[first,:2]).prod()+(boxes[others,2:]-boxes[others,:2]).prod(axis=1)-intersect
        overlap=intersect/np.maximum(area,1e-12)
        order=others[(classes[others]!=classes[first])|(overlap<=iou)]
    return [dict(class_id=int(classes[i]),confidence=float(scores[i]),bbox_xyxy=[float(v) for v in boxes[i]]) for i in kept]
