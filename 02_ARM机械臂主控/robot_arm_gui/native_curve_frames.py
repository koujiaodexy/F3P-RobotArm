"""Batch the existing frame guards without changing reference sampling."""
import ctypes as c,math
from .native_driver_tracking import LIBRARY
from .native_math import POINTER,array,flatten

if LIBRARY is not None and hasattr(LIBRARY,'f3p_curve_frames'):
    LIBRARY.f3p_curve_frames.argtypes=[POINTER]*7+[c.c_int]*3+[c.c_double,c.c_int,POINTER]
    LIBRARY.f3p_curve_frames.restype=c.c_int
    LIBRARY.f3p_box_height.argtypes=[POINTER]*2;LIBRARY.f3p_box_height.restype=c.c_double
    if hasattr(LIBRARY,'f3p_rule_box'):
        LIBRARY.f3p_rule_box.argtypes=[POINTER]*3;LIBRARY.f3p_rule_box.restype=c.c_int
    if hasattr(LIBRARY,'f3p_restore_frames'):
        LIBRARY.f3p_restore_frames.argtypes=[POINTER]*5+[c.c_int,POINTER]
        LIBRARY.f3p_restore_frames.restype=c.c_int

def rule_values(model):
    rule=model._profile.get('j3_j4_rule')
    return [1.]+list(rule['signs'])+list(rule['offsets'])+list(rule['j4']) if rule else [0.]*15

def frames(curve,parameter,start_index,count,final):
    if (LIBRARY is None or not hasattr(LIBRARY,'f3p_curve_frames') or not getattr(curve,'native_frames',False)
            or not getattr(curve.model,'native_enabled',False) or getattr(curve,'adaptive',False)):
        return None
    ahead=round(curve.ahead/curve.tick);total=count+ahead
    if ahead<1 or count<1:return None
    curve.check();us=[parameter(k*curve.tick) for k in range(total)]
    qs=None
    if hasattr(curve,'guide_u') and curve.args.get('finite_complete') and not curve.adaptive:
        from .native_finite_timing import joints
        qs=joints(curve,us)
    if qs is None:qs=[curve.q(u) for u in us]
    xyz=[curve.point(u) for u in us]
    points=[];budgets=[curve.position_budget(u) for u in us]
    for k in range(count):
        for fraction in (.25,.5,.75):
            u=us[k]+fraction*(us[k+ahead]-us[k]);points.extend(curve.point(u));budgets.append(curve.position_budget(u))
    model=curve.model;mapping=array(model._motor_ref+model._joint_ref+model._directions+model._ratios)
    limits=[v for pair in curve.limits for v in (pair if pair else (-math.inf,math.inf))]
    cfg=array(list(curve.ppr)+list(curve.nominal)+list(curve.rates)+list(curve.wire)+limits+rule_values(model))
    rows=array([v for q,x,u in zip(qs,xyz,us) for v in q+x+[u]])
    out=array([0.]*(24*total));curve.check()
    ok=LIBRARY.f3p_curve_frames(model._native_geometry,mapping,array(flatten(curve.origin)),rows,
        array(points),array(budgets),cfg,total,count,ahead,curve.tick,int(getattr(curve,'strict_ideal',False)),out)
    curve.check()
    if not ok:return None
    result=[]
    for k in range(count):
        curve.check();command=k+ahead
        quantized=list(out[command*24+6:command*24+12])
        result.append(dict(seq=start_index+k+1,t_s=(start_index+k)*curve.tick,phase='cartesian',
            reference_u=us[k],reference_xyz_mm=xyz[k],reference_joints_deg=qs[k],reference_motor_deg=list(out[k*24:k*24+6]),
            command_t_s=(start_index+k+ahead)*curve.tick,command_reference_u=us[command],command_xyz_mm=xyz[command],command_joints_deg=qs[command],
            command_motor_deg=quantized,motor_target_pulses=[int(v) for v in out[command*24+12:command*24+18]],
            speed_rpm=[int(v) for v in out[k*24+18:k*24+24]],acceleration=list(curve.acc),final=bool(final and k==count-1)))
    return result

def restore(restorer,rows):
    if (LIBRARY is None or not hasattr(LIBRARY,'f3p_restore_frames') or not restorer.residual.native
            or not restorer.finite or not rows):return None
    model=restorer.model;samples=[];values=[]
    for row in rows:
        restorer.check();q=restorer.joints(row['reference_joints_deg']);cq=restorer.joints(row['command_joints_deg'])
        u=row['reference_u'];cu=row['command_reference_u'];xyz=restorer.point(u);cxyz=restorer.point(cu)
        samples.append((q,cq,xyz,cxyz));values.extend(q+cq+xyz+cxyz)
        for fraction in (.25,.5,.75):values.extend(restorer.point(u+fraction*(cu-u)))
    mapping=array(model._motor_ref+model._joint_ref+model._directions+model._ratios)
    cfg=array(list(restorer.ppr)+[v for pair in restorer.limits for v in (pair if pair else (-math.inf,math.inf))]+rule_values(model))
    packed=array(values);out=array([0.]*(20*len(rows)))
    for index in range(0,len(rows),200):
        restorer.check()
        ok=LIBRARY.f3p_restore_frames(model._native_geometry,mapping,restorer.residual.native_origin,
            c.cast(c.byref(packed,index*27*c.sizeof(c.c_double)),POINTER),cfg,min(200,len(rows)-index),
            c.cast(c.byref(out,index*20*c.sizeof(c.c_double)),POINTER))
        if not ok:return None
    restorer.check()
    from .coupled_limits import check_model_box
    result=[]
    for k,(row,(q,cq,xyz,cxyz)) in enumerate(zip(rows,samples)):
        restorer.check();quantized=list(out[k*20+6:k*20+12])
        restorer.max_ideal_position=max(restorer.max_ideal_position,out[k*20+18])
        restorer.max_ideal_orientation=max(restorer.max_ideal_orientation,out[k*20+19])
        result.append(dict(row,reference_xyz_mm=xyz,command_xyz_mm=cxyz,reference_joints_deg=q,
            command_joints_deg=cq,reference_motor_deg=list(out[k*20:k*20+6]),command_motor_deg=quantized,
            motor_target_pulses=[int(v) for v in out[k*20+12:k*20+18]]))
    # Adjacent frames inside each native block were checked there; retain the
    # same two checks across every block boundary.
    for index in range(200,len(result),200):
        previous,current=result[index-1:index+1]
        check_model_box(model,previous['reference_joints_deg'],current['reference_joints_deg'])
        check_model_box(model,model.motor_to_joints(previous['command_motor_deg']),model.motor_to_joints(current['command_motor_deg']))
    return result
