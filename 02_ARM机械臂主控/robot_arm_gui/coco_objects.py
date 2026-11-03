"""COCO vocabulary, checked detections and position profiles. No motor IO."""
import math
from .coco_policy import RETAINED_IDS,RETAINED_NAMES,RETAINED_SET

# Contiguous detector indices, not the non-contiguous COCO annotation category IDs.
ENGLISH = ('person','bicycle','car','motorcycle','airplane','bus','train','truck','boat','traffic light',
    'fire hydrant','stop sign','parking meter','bench','bird','cat','dog','horse','sheep','cow',
    'elephant','bear','zebra','giraffe','backpack','umbrella','handbag','tie','suitcase','frisbee',
    'skis','snowboard','sports ball','kite','baseball bat','baseball glove','skateboard','surfboard',
    'tennis racket','bottle','wine glass','cup','fork','knife','spoon','bowl','banana','apple','sandwich',
    'orange','broccoli','carrot','hot dog','pizza','donut','cake','chair','couch','potted plant','bed',
    'dining table','toilet','tv','laptop','mouse','remote','keyboard','cell phone','microwave','oven',
    'toaster','sink','refrigerator','book','clock','vase','scissors','teddy bear','hair drier','toothbrush')
CHINESE = ('人','自行车','汽车','摩托车','飞机','公交车','火车','卡车','船','交通灯',
    '消防栓','停车标志','停车计时器','长椅','鸟','猫','狗','马','羊','牛',
    '大象','熊','斑马','长颈鹿','背包','雨伞','手提包','领带','行李箱','飞盘',
    '滑雪板','单板滑雪板','球','风筝','棒球棒','棒球手套','滑板','冲浪板','网球拍',
    '瓶子','高脚杯','杯子','叉子','刀','勺子','碗','香蕉','苹果','三明治','橙子',
    '西兰花','胡萝卜','热狗','披萨','甜甜圈','蛋糕','椅子','沙发','盆栽','床',
    '餐桌','马桶','电视','笔记本电脑','鼠标','遥控器','键盘','手机','微波炉','烤箱',
    '烤面包机','水槽','冰箱','书','时钟','花瓶','剪刀','泰迪熊','吹风机','牙刷')
ENGLISH += ('red_cube','yellow_cube','green_cube')
CHINESE += ('红色积木','黄色积木','绿色积木')
assert len(ENGLISH)==len(CHINESE)==83
assert tuple(ENGLISH[i] for i in RETAINED_IDS)==RETAINED_NAMES

def finite(value):return type(value) in (int,float) and math.isfinite(value)

def detection(row, size):
    if not isinstance(row,dict):raise ValueError('物品识别结果无效')
    cid=row.get('class_id');score=row.get('confidence');box=row.get('bbox_xyxy')
    if type(cid) is not int or not 0<=cid<len(ENGLISH):raise ValueError('物品类别编号无效')
    if not finite(score) or not 0<=score<=1:raise ValueError('物品置信度无效')
    if (not isinstance(box,(list,tuple)) or len(box)!=4 or not all(finite(v) for v in box)
            or not 0<=box[0]<box[2]<=size[0] or not 0<=box[1]<box[3]<=size[1]):
        raise ValueError('物品识别框超出图像范围')
    return dict(class_id=cid,name=ENGLISH[cid],label=CHINESE[cid],confidence=float(score),
                bbox_xyxy=list(box),center=[(box[0]+box[2])/2,(box[1]+box[3])/2])

def checked_report(report, session_id, now, maximum_age=10.):
    if not isinstance(report,dict) or report.get('session_id')!=session_id or report.get('state')!='running':
        raise ValueError('等待本次物品识别结果')
    stamp=report.get('captured_at');size=report.get('source_size');rows=report.get('detections')
    completed=report.get('completed_at',stamp)
    # Configuration selects a fixed, labelled snapshot. Check publication age
    # separately from capture age so a valid 7-second NPU frame is selectable.
    # This snapshot never authorizes motion or supplies calibrated coordinates.
    if (not finite(stamp) or not finite(completed) or not finite(now)
            or not 0<=completed-stamp<=20. or not 0<=now-completed<=maximum_age):
        raise ValueError('识别画面已过期，请重新识别')
    if (not isinstance(size,(list,tuple)) or len(size)!=2 or
            any(type(v) is not int or not 1<=v<=4096 for v in size)):
        raise ValueError('物品图像尺寸无效')
    if not isinstance(rows,list) or len(rows)>64:raise ValueError('物品识别列表无效')
    if type(report.get('frame_id')) is not int or not 0<=report['frame_id']<=0xffffffff:
        raise ValueError('物品图像编号无效')
    normalized=[detection(row,size) for row in rows]
    result=[row for row in normalized if row['class_id'] in RETAINED_SET]
    return sorted(result,key=lambda r:(-r['confidence'],r['class_id'],r['bbox_xyxy']))

def selection(report, session_id, index, now):
    rows=checked_report(report,session_id,now)
    if type(index) is not int or not 0<=index<len(rows):raise ValueError('请先选中识别到的物品')
    return dict(rows[index],session_id=session_id,frame_id=report.get('frame_id'),
                captured_at=report['captured_at'],completed_at=report.get('completed_at',report['captured_at']),
                source_size=list(report['source_size']),
                coordinates_calibrated=False,motion_enabled=False)

def position_profile(selected,pick_xyz,drop_xyz):
    """Save deliberate coordinates; never turn a detection center into 3D implicitly."""
    if not isinstance(selected,dict) or selected.get('name') not in ENGLISH:
        raise ValueError('请先选择COCO物品')
    if ENGLISH.index(selected['name']) not in RETAINED_SET:
        raise ValueError('该类别已从本次识别范围移除')
    for xyz in (pick_xyz,drop_xyz):
        if (not isinstance(xyz,(list,tuple)) or len(xyz)!=3 or not all(finite(v) for v in xyz)
                or any(abs(v)>2000 for v in xyz)):
            raise ValueError('抓取点和投放点须填写完整XYZ，单位毫米')
    return dict(schema=1,class_id=ENGLISH.index(selected['name']),name=selected['name'],
        label=CHINESE[ENGLISH.index(selected['name'])],pick_xyz_mm=list(pick_xyz),drop_xyz_mm=list(drop_xyz),
        calibration_source='operator_entered',motion_enabled=False,
        note='Position configuration only; requires separate calibrated grasp-path validation')
