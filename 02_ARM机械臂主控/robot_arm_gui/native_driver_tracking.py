"""Optional bounded native implementation of the Python response oracle."""
import ctypes as c
import math,os
from pathlib import Path
from . import native_math as nm
from . import fast_trajectory as f

LIBRARY=None
if os.environ.get('F3P_DISABLE_NATIVE')!='1':
    try:
        LIBRARY=c.CDLL(str(Path(__file__).parent/'native'/('driver_response.dll' if os.name=='nt' else 'driver_response.so')))
        LIBRARY.f3p_response_abi.restype=c.c_int
        if LIBRARY.f3p_response_abi()!=1:raise RuntimeError('native response ABI mismatch')
        LIBRARY.f3p_response_block.argtypes=[nm.POINTER]*4+[c.c_int]*3+[c.c_double,nm.POINTER,c.c_int,nm.POINTER]
        LIBRARY.f3p_response_block.restype=c.c_int
    except (OSError,AttributeError,RuntimeError):LIBRARY=None

def assess(model,start,rows,check,rate_factor,feedback_skew,kind):
    if LIBRARY is None or not getattr(model,'native_enabled',False):return None
    check()
    origin=model.forward(model.motor_to_joints(start))
    mapping=nm.array(model._motor_ref+model._joint_ref+model._directions+model._ratios)
    packed=nm.array([v for row in rows for v in (list(row['command_motor_deg'])+
        list(row['speed_rpm'])+list(row['acceleration'])+list(row['reference_xyz_mm'])+
        list(row['command_xyz_mm'])+[float(row.get('phase')=='wrist_preparation')])])
    if len(packed)!=25*len(rows) or not rows or not math.isfinite(rate_factor) or rate_factor<=0:
        raise f.TrajectoryError('驱动响应模型输入无效')
    state=nm.array(list(start)+[0.]*6+list(start)*9+[0.]*4)
    skew=nm.array([min(8,round(feedback_skew*i/5/.005)) for i in range(6)])
    origin=nm.array(nm.flatten(origin))
    for index in range(0,len(rows),50):
        check()
        result=LIBRARY.f3p_response_block(model._native_geometry,mapping,origin,packed,
            len(rows),index,min(50,len(rows)-index),rate_factor,skew,int(kind!='line'),state)
        if result:raise f.TrajectoryError('驱动响应位姿含非有限数值或输入无效')
    check()
    return dict(max_orientation_deg=state[66],max_skewed_orientation_deg=state[67],
        max_preparation_drift_mm=state[68],max_running_path_error_mm=state[69],
        rate_factor=rate_factor,feedback_skew_s=feedback_skew,model_only=True)
