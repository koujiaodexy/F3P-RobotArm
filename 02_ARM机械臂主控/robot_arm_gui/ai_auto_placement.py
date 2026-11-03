"""Bounded placement search on the operator's current drawing surface.

Sampled workspace cells are hints only. Every selected route must complete
the existing full planner, including its entry motion, before it is returned.
No transport or reference changes are made by this module.
"""
import math
from . import drawing, kinematics as k


def candidate_centers(cart, direction, axes, fixed, pose):
    i,j,f=axes
    preferred=list(pose);preferred[f]=fixed
    candidates=[preferred]
    # Prefer small displacements; this also works when sampled data is stale.
    for distance in (30.,60.,100.):
        for u,v in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            p=list(preferred);p[i]+=u*distance;p[j]+=v*distance;candidates.append(p)
    ws=cart.workspace
    if ws.data and direction in ws.index:
        step=ws.data['step_mm']
        cells=[]
        for (z,y),runs in ws.index[direction].items():
            for lo,hi in runs:
                for x in (lo,(lo+hi)/2,hi):
                    p=[x,y,z]
                    if abs(p[f]-fixed)<=step/2:
                        p[f]=fixed;cells.append(p)
        cells.sort(key=lambda p:math.dist(p,preferred))
        candidates.extend(cells[:128])
    unique={tuple(p):p for p in candidates}
    return sorted(unique.values(),key=lambda p:math.dist(p,preferred))


def prepare_auto_route(cart, args, direction, settings):
    plane=settings.get('placement_plane')
    if plane not in ('xy','xz','yz'):
        raise ValueError('自动选位需要当前绘图工作面')
    axes={'xy':(0,1,2),'xz':(0,2,1),'yz':(1,2,0)}[plane]
    fixed=settings.get('placement_fixed_mm')
    if type(fixed) not in (int,float) or not math.isfinite(fixed):
        raise ValueError('当前绘图切片坐标无效')
    actual,_=cart.read_start();start=cart.to_model(actual);pose=k.forward(start)
    rotation=drawing.rotation(direction,pose['rotation'])
    uv=args['waypoints_uv_mm']
    # Center by bounding box; never resize, rotate, or change the surface.
    origin=[(min(p[a] for p in uv)+max(p[a] for p in uv))/2 for a in (0,1)]
    failures=[];attempts=0
    for center in candidate_centers(cart,direction,axes,fixed,pose['position_mm']):
        cart.task._check()
        points=[]
        for p in uv:
            xyz=list(center)
            for a in (0,1):xyz[axes[a]]+=p[a]-origin[a]
            points.append(dict(xyz=xyz,mode='L',stroke=0))
        try:
            document=drawing.validate(dict(schema=1,points=points,direction=direction,
                speed=args['tcp_speed_mm_s'],joint_speed=args['joint_speed_deg_s'],
                trajectory_acceleration=settings.get('trajectory_acceleration'),
                allow_orientation_adjustment=False))
            for point in points:
                cart.task._check()
                cart.check_workspace(dict(position_mm=point['xyz'],rotation=rotation))
        except ValueError:
            continue
        attempts+=1
        try:
            cart.operate('cart_drawing_plan',dict(document=document))
            return document,center
        except ValueError as error:
            cart.drawing.invalidate();failures.append(str(error))
        # Cancellation, stale reference, and transport errors are never retried.
        if attempts>=12:break
    cart.drawing.invalidate()
    raise ValueError('当前工作面未找到整条规划通过的位置（尝试%d处）；未启动运动。%s'
                     %(attempts,failures[-1] if failures else '请检查尺寸、切片高度和朝向'))
