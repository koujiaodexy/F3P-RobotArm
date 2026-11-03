"""Change the tool axis with J4/J5 only; TCP translation is unconstrained."""
import math
from . import kinematics as k
from .reference_adapter import make_model
from .coupled_limits import check_model_box
from .collision import check_joint_box
from .workspace import Workspace


def solve(start, direction, bounds, check=lambda: None):
    if direction not in Workspace.AXES:
        raise ValueError('请选择一个明确朝向')
    start=k.finite_vector(start,6)
    model=make_model(start,bounds,check=check)
    base=list(start);base[3]=base[4]=base[5]=0.
    # In this MDH convention tool Z is independent of J6.
    r=[row[:3] for row in model.forward(base)[:3]]
    n=k.mv(k.transpose(r),Workspace.AXES[direction])
    bend=math.degrees(math.acos(max(-1.,min(1.,n[2]))))
    limits=dict(bounds)
    rule=getattr(bounds,'rule',None)
    if rule and (start[2]-rule['offsets'][2])*rule['signs'][2]>34:
        limits[3]=tuple(sorted(rule['offsets'][3]+rule['signs'][3]*v for v in rule['j4']))
    def equivalents(value,axis):
        if axis not in limits:
            return [value+360*round((start[axis]-value)/360)]
        lo,hi=limits[axis]
        return [value+360*j for j in range(math.ceil((lo-value-1e-8)/360),math.floor((hi-value+1e-8)/360)+1)]
    candidates=[];rejections=[]
    for sign in (1.,-1.):
        for q5 in equivalents(sign*bend,4):
            sn=math.sin(math.radians(q5))
            rolls=[start[3]] if abs(sn)<1e-7 else [math.degrees(math.atan2(-n[1]/sn,-n[0]/sn))]
            for roll in rolls:
                for q4 in equivalents(roll,3):
                    check();q=list(start);q[3]=q4;q[4]=q5
                    axis=[row[2] for row in k.forward(q)['rotation']]
                    error=math.degrees(math.acos(max(-1.,min(1.,k.dot(axis,Workspace.AXES[direction])))))
                    if error>.02:continue
                    try:
                        check_model_box(model,start,q)
                        check_joint_box(start,q,check)
                    except ValueError as exc:
                        rejections.append(str(exc));continue
                    candidates.append((sum((q[i]-start[i])**2 for i in (3,4)),q,error))
    if not candidates:
        detail=rejections[0] if rejections else 'J4/J5 原限位内没有解；所需 J5 弯角约 %.2f°'%bend
        raise ValueError('仅转 J4/J5 无法到达所选朝向：'+detail)
    _,q,error=min(candidates,key=lambda item:item[0])
    return dict(angles_deg=q,orientation_error_deg=error,position_error_mm=0.,
                near_singularity=False,algorithm='wrist-axis-only',position_preserved=False)
