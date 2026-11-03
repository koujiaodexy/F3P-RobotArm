"""Bounded route lookahead for equivalent fixed-pose entry branches; no IO."""
import math
import time
from . import kinematics as k
from .analytic_inverse import solve
from .reference_adapter import make_model,SOURCE_PROFILE


def select_entry(start,goal,bounds,segments,check=lambda:None,budget=.35,reject_dead_end=False):
    if budget<=0:return None
    model=make_model(start,bounds)
    if not all(model.profile.get(key)==SOURCE_PROFILE.get(key) for key in ('geometry','target_frame','model_endpoint_to_tcp')):
        return None
    deadline=time.monotonic()+budget
    def bounded_check():
        check()
        if time.monotonic()>deadline:raise TimeoutError('branch lookahead budget')
    try:
        answers=solve(goal,start,bounds,bounded_check,model=model,all_solutions=True)
        if not answers:return None
        roots=[r['angles_deg'] for r in answers]
        # A single entry branch can still hit a hard stop later. Skipping it
        # granted motion before discovering a deterministic mid-stroke failure.
        if len(roots)<2 and not reject_dead_end:return None
        paths=[(i,list(q)) for i,q in enumerate(roots)]
        from .fast_trajectory import _path_geometry
        geometry=[];origin=goal['position_mm']
        for spec in segments:
            if spec['mode']=='J':break
            point,length,_=_path_geometry(origin,spec['goal'],{'D':'polyline','L':'line','C':'arc'}[spec['mode']],spec.get('via'))
            vertices=spec.get('via') or []
            corners=[]
            if spec['mode']=='D':
                distance=0.;previous=origin
                stride=max(1,math.ceil(len(vertices)/64))
                for index,vertex in enumerate(vertices):
                    distance+=math.dist(previous,vertex);previous=vertex
                    if index%stride==0 or index==len(vertices)-1:corners.append(distance/length)
            elif spec['mode']=='C':
                from .cartesian_planner import circle
                corners.append(circle(origin,spec['via'],spec['goal'])['via_fraction'])
            geometry.append((point,length,corners));origin=spec['goal']
        total=sum(length for _,length,_ in geometry)
        if not geometry:return None
        step=max(5.,total/64)
        for segment_index,(point,length,corners) in enumerate(geometry):
            count=max(1,math.ceil(length/step))
            fractions=sorted(set([j/count for j in range(1,count+1)]+[u for u in corners if 0<u<=1]))
            for fraction in fractions:
                bounded_check()
                candidates=solve(dict(position_mm=point(fraction),rotation=goal['rotation']),paths[0][1],bounds,bounded_check,model=model,all_solutions=True)
                next_paths=[]
                for root,previous in paths:
                    options=[]
                    for answer in candidates:
                        q=list(answer['angles_deg'])
                        for axis in model.continuous_joints:
                            i=axis-1;q[i]+=360*round((previous[i]-q[i])/360)
                        from .coupled_limits import check_model_box
                        try:check_model_box(model,previous,q)
                        except ValueError:continue
                        delta=max(abs(a-b) for a,b in zip(q,previous))
                        if delta<90:options.append((sum((a-b)**2 for a,b in zip(q,previous)),q))
                    if options:next_paths.append((root,min(options,key=lambda item:item[0])[1]))
                paths=next_paths
                if not paths:
                    if reject_dead_end:
                        error=ValueError('固定朝向线路抽查无法连续接续（第%d段，约%.1f%%），可能达到关节限位；请调整线路或显式允许自动调整朝向'%
                            (segment_index+1,fraction*100))
                        error.failure_kind='fixed_orientation_route_dead_end'
                        error.path_fraction=fraction
                        error.position_mm=point(fraction)
                        raise error
                    return None
        # This is a branch preference, not an execution certificate. The full
        # guide, frame, pulse, collision and braking checks remain mandatory.
        if any(root==0 for root,_ in paths):return None
        from .collision import check_joint_box
        for root,_ in paths:
            q=roots[root]
            try:check_joint_box(start,q,bounded_check)
            except ValueError:continue
            print('DRAWING_ENTRY_BRANCH',dict(reason='nearest_branch_loses_route_continuity',
                nearest=roots[0],selected=q,probe_step_mm=step),flush=True)
            return q
    except TimeoutError:
        # The optional probe cannot consume the two-second prepare deadline.
        return None
    return None
