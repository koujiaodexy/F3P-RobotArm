"""Closed-form branches for the existing actual-arm MDH, verified by FK."""
import math
from . import kinematics as k


def solve(goal,seed,bounds,check=lambda:None,model=None,all_solutions=False):
    from .reference_adapter import make_model,TOOL_ROTATION
    if model is None:model=make_model(seed,bounds)
    rule=model._profile.get('j3_j4_rule')
    xyz=goal['position_mm'];r=goal['rotation']
    wrist=[xyz[i]-39.5*r[i][2] for i in range(3)]
    radius=math.hypot(*wrist[:2])
    if radius<1e-8:return None
    length=math.hypot(142.3,15);beta=math.degrees(math.atan2(142.3,15))
    target=k.mm(r,k.transpose(TOOL_ROTATION));answers=[]
    def equivalents(value,axis):
        if axis==3 and rule and (q3-rule['offsets'][2])*rule['signs'][2]>34:
            lo,hi=sorted(rule['signs'][3]*v+rule['offsets'][3] for v in rule['j4'])
            return [value+360*n for n in range(math.ceil((lo-value-1e-8)/360),math.floor((hi-value+1e-8)/360)+1)]
        if axis not in bounds:
            nearest=value+360*round((seed[axis]-value)/360)
            if axis==3 and rule and all_solutions:
                # A nearest winding outside the original J4 interval is legal
                # now, but cannot cross into J3>34 later without a full turn.
                # Offer the original-interval winding for route lookahead too.
                lo,hi=sorted(rule['signs'][3]*v+rule['offsets'][3] for v in rule['j4'])
                return sorted(set([nearest]+[value+360*n for n in range(math.ceil((lo-value-1e-8)/360),math.floor((hi-value+1e-8)/360)+1)]))
            return [nearest]
        lo,hi=bounds[axis]
        return [value+360*n for n in range(math.ceil((lo-value-1e-8)/360),math.floor((hi-value+1e-8)/360)+1)]
    az=math.degrees(math.atan2(wrist[1],wrist[0]));z=wrist[2]-170
    for shoulder in (1,-1):
        radial=shoulder*radius-37.5
        cosine=(radial*radial+z*z-160**2-length**2)/(320*length)
        if abs(cosine)>1+1e-10:continue
        bend=math.degrees(math.acos(max(-1.,min(1.,cosine))))
        for q1 in equivalents(az+(180 if shoulder<0 else 0),0):
            for elbow in (1,-1):
                for q3 in equivalents(elbow*bend-beta,2):
                    theta=math.radians(beta+q3)
                    base=math.degrees(math.atan2(radial,z)-math.atan2(length*math.sin(theta),160+length*math.cos(theta)))
                    for q2 in equivalents(base,1):
                        check();a=[row[:3] for row in model.forward([q1,q2,q3,0,0,0])[:3]]
                        n=k.mv(k.transpose(a),[row[2] for row in r])
                        angle=math.degrees(math.acos(max(-1.,min(1.,n[2]))))
                        for sign in (1,-1):
                            for q5 in equivalents(sign*angle,4):
                                sn=math.sin(math.radians(q5))
                                # Native FK roundoff can make an aligned wrist
                                # appear to have a ~1e-6 degree bend. Preserve
                                # its seed roll, then verify the full pose below.
                                rolls=[seed[3],0,90,180] if abs(sn)<1e-6 else [math.degrees(math.atan2(-n[1]/sn,-n[0]/sn))]
                                for roll in rolls:
                                    for q4 in equivalents(roll,3):
                                        q=[q1,q2,q3,q4,q5,0]
                                        ref=[row[:3] for row in model.forward(q)[:3]]
                                        relative=k.mm(k.transpose(ref),target)
                                        yaw=math.degrees(math.atan2(relative[1][0],relative[0][0]))
                                        for q6 in equivalents(yaw,5):
                                            q[5]=q6;t=model.forward(q)
                                            pe=math.dist(xyz,[row[3] for row in t[:3]])
                                            if pe>.01 or max(abs(t[i][j]-target[i][j]) for i in range(3) for j in range(3))>1e-6:continue
                                            from .coupled_limits import check_model_box
                                            try:check_model_box(model,q,q)
                                            except ValueError:continue
                                            answers.append((sum((v-s)**2 for v,s in zip(q,seed)),list(q),pe))
    if all_solutions:
        return [dict(angles_deg=q,position_error_mm=pe,orientation_error_deg=0.,
                     singular_value=0.,near_singularity=False,algorithm='verified-analytic-mdh')
                for _,q,pe in sorted(answers,key=lambda item:item[0])]
    if not answers:return None
    _,q,pe=min(answers,key=lambda item:item[0])
    return dict(angles_deg=q,position_error_mm=pe,orientation_error_deg=0.,
                singular_value=0.,near_singularity=False,algorithm='verified-analytic-mdh')


def fixed_pose(model,xyz,rotation,seed,limits,check=lambda:None):
    """Reuse the exact MDH branches for guide points; validate on the caller FK."""
    from .reference_adapter import SOURCE_PROFILE,TOOL_ROTATION
    # Exact geometry only. Other profiles keep their original numerical solver.
    if not hasattr(model,'_analytic_geometry_compatible'):
        profile=model.profile
        model._analytic_geometry_compatible=all(profile.get(key)==SOURCE_PROFILE.get(key) for key in ('geometry','target_frame','model_endpoint_to_tcp'))
    if not model._analytic_geometry_compatible:return None
    from .native_analytic_inverse import solve as native_solve
    result=native_solve(model,xyz,rotation,seed,limits,check)
    if result is not None:return result
    bounds={i:tuple(pair) for i,pair in enumerate(limits) if pair is not None}
    result=solve(dict(position_mm=xyz,rotation=k.mm(rotation,TOOL_ROTATION)),seed,bounds,check,model=model)
    return None if result is None else result['angles_deg']
