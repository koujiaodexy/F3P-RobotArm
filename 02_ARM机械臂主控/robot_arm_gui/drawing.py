"""Drawing documents and arc-length polylines. No GTK or transport access."""
import bisect
import copy
import math
from . import kinematics as k

MAX_POINTS=10000
MAX_SEGMENTS=256


def copy_validated_document(document):
    """Copy the scalar/point schema returned by validate(), without aliasing."""
    return dict(document,points=[dict(p,xyz=list(p['xyz'])) for p in document['points']])


def validate(document):
    from .collision import check_target
    if not isinstance(document,dict) or document.get('schema')!=1:
        raise ValueError('绘图文件版本无效')
    points=document.get('points')
    if not isinstance(points,list) or not 1<=len(points)<=MAX_POINTS:
        raise ValueError('线路需要1～10000个点')
    out=[]
    for p in points:
        if not isinstance(p,dict) or p.get('mode') not in ('L','J','C'):
            raise ValueError('路径点方式无效')
        xyz=k.finite_vector(p.get('xyz'),3)
        if any(abs(v)>2000 for v in xyz):raise ValueError('坐标超出绘图范围')
        check_target(xyz)
        free=p.get('stroke')
        if free is not None and (type(free) is not int or free<0 or p['mode']!='L'):
            raise ValueError('自由曲线编号无效')
        out.append(dict(xyz=xyz,mode=p['mode'],stroke=free))
    direction=document.get('direction','hold')
    if direction not in ('hold','plus_x','minus_x','plus_y','minus_y','plus_z','minus_z'):
        raise ValueError('执行必须选择当前朝向或一个明确朝向，合并区仅供查看')
    speed=float(document.get('speed',5));joint=float(document.get('joint_speed',5))
    if not math.isfinite(speed) or not .1<=speed<=100 or not math.isfinite(joint) or not .1<=joint<=100:
        raise ValueError('末端速度须为0.1～100mm/s，关节速度须为0.1～100度/s；实际速度受各轴板端上限限制')
    acc=document.get('trajectory_acceleration')
    if acc is not None and (type(acc) is not int or not 1<=acc<=255):
        raise ValueError('轨迹ACC须为1～255整数')
    adjust=document.get('allow_orientation_adjustment',False)
    if type(adjust) is not bool:raise ValueError('自动调整朝向选项必须为布尔值')
    return dict(schema=1,points=out,direction=direction,speed=speed,joint_speed=joint,trajectory_acceleration=acc,allow_orientation_adjustment=adjust)


def visible_indices(points,selected):
    return [i for i,p in enumerate(points) if p.get('stroke') is None or i==selected
            or i==0 or i==len(points)-1 or points[i-1].get('stroke')!=p['stroke']
            or points[i+1].get('stroke')!=p['stroke']]


def polyline(start,end,via):
    if not isinstance(via,list) or len(via)>MAX_POINTS:raise ValueError('自由曲线数据无效')
    vertices=[k.finite_vector(start,3)]
    for xyz in [*via,end]:
        p=k.finite_vector(xyz,3)
        if math.dist(p,vertices[-1])>1e-9:vertices.append(p)
    lengths=[0.]
    for a,b in zip(vertices,vertices[1:]):lengths.append(lengths[-1]+math.dist(b,a))
    total=lengths[-1]
    if total<=.01:raise ValueError('线路长度不足0.01mm')
    def point(u):
        distance=max(0.,min(1.,u))*total
        i=min(len(vertices)-2,max(0,bisect.bisect_right(lengths,distance)-1))
        t=(distance-lengths[i])/(lengths[i+1]-lengths[i])
        return [a+(b-a)*t for a,b in zip(vertices[i],vertices[i+1])]
    return point,total,{}


def segment_interval(segment,start,lo,hi):
    """Trim geometry without removing any retained free-stroke vertices."""
    from .fast_trajectory import _path_geometry
    kind={'L':'line','C':'arc','D':'polyline'}[segment['mode']]
    point,length,_=_path_geometry(start,segment['goal'],kind,segment.get('via'))
    result=dict(mode=segment['mode'],goal=point(hi))
    if kind=='arc':result['via']=point((lo+hi)/2)
    if kind=='polyline':
        previous=start;distance=0.;vertices=[]
        for vertex in [*segment['via'],segment['goal']]:
            distance+=math.dist(previous,vertex);previous=vertex
            if lo+1e-10<distance/length<hi-1e-10:vertices.append(vertex)
        result['via']=vertices
    return result,point(lo),length*(hi-lo)


def segments(document):
    """First point is an explicit entry MoveJ; C consumes via + next end.

    Consecutive LIN vertices within one stroke are one path, split at 300mm to respect the existing
    planner's 1600 reconnaissance samples. Splits have exact stops.
    """
    d=validate(document);pts=d['points'];result=[];i=1
    while i<len(pts):
        p=pts[i]
        if p['mode']=='C':
            if i+1>=len(pts) or pts[i+1]['mode']=='C':raise ValueError('圆弧经过点后需要一个终点')
            result.append(dict(mode='C',via=p['xyz'],goal=pts[i+1]['xyz']));i+=2
        elif p['mode']=='L' and pts[i-1].get('stroke')==p.get('stroke'):
            group=[pts[i-1]['xyz']];length=0.
            while i<len(pts) and pts[i]['mode']=='L' and pts[i].get('stroke')==p.get('stroke'):
                xyz=pts[i]['xyz'];distance=math.dist(xyz,group[-1])
                if length+distance>300 and len(group)>1:
                    result.append(dict(mode='D',via=group[1:-1],goal=group[-1]));group=[group[-1]];length=0.
                # Large single edges use ordinary LIN splitting too.
                origin=list(group[-1]);n=max(1,math.ceil(distance/300))
                for j in range(1,n+1):
                    q=list(xyz) if j==n and p.get('stroke') is None else [a+(b-a)*j/n for a,b in zip(origin,xyz)]
                    delta=math.dist(q,group[-1])
                    if length+delta>300 and len(group)>1:
                        result.append(dict(mode='D',via=group[1:-1],goal=group[-1]));group=[group[-1]];length=0.
                    group.append(q);length+=delta
                i+=1
            if length>.01:
                if len(group)==2 and p.get('stroke') is None:result.append(dict(mode='L',goal=group[-1]))
                else:result.append(dict(mode='D',via=group[1:-1],goal=group[-1]))
        else:
            if math.dist(p['xyz'],pts[i-1]['xyz'])>.01:result.append(dict(mode=p['mode'],goal=p['xyz']))
            i+=1
        if len(result)>MAX_SEGMENTS:raise ValueError('线路超过256个独立运动段，请拆分保存')
    start=pts[0]['xyz']
    from .cartesian_planner import circle
    for segment in result:
        if segment['mode']=='C' and circle(start,segment['via'],segment['goal'])['minimum_z_mm']<=0:
            raise ValueError('圆弧途中Z小于或等于0，请提高圆弧高度')
        start=segment['goal']
    # validate() has already produced a fresh, fixed-schema document. Copy its
    # point vectors directly instead of recursively copying 1200+ dictionaries.
    # Keep the document and segment vectors independent as before.
    return copy_validated_document(d),result


def rotation(direction,current):
    if direction=='hold':return copy.deepcopy(current)
    from .workspace import Workspace
    z=list(Workspace.AXES[direction]);old_z=[row[2] for row in current]
    axis=k.cross(old_z,z);s=k.norm(axis);c=max(-1.,min(1.,k.dot(old_z,z)))
    if s>1e-10:
        axis=k.scale(axis,1/s)
        # Transport the entire frame with the shortest shaft-axis rotation.
        # Projecting the old tool X alone becomes singular at +/-Y and can
        # turn a tiny J6 feedback offset into a quarter-turn of the jaws.
        x=[row[0] for row in current]
        x=k.add(k.add(k.scale(x,c),k.scale(k.cross(axis,x),s)),
                k.scale(axis,k.dot(axis,x)*(1-c)))
    elif c<0:
        # A half-turn has no unique shortest axis. Keep the current tool Y
        # (vertical for horizontal jaws) instead of choosing a world axis.
        axis=[row[1] for row in current];x=[row[0] for row in current]
        x=k.sub(k.scale(axis,2*k.dot(axis,x)),x)
    else:x=[row[0] for row in current]
    # Remove rounding error and keep the requested shaft direction exact.
    x=k.sub(x,k.scale(z,k.dot(x,z)))
    x=k.scale(x,1/k.norm(x));y=k.cross(z,x)
    return k.transpose([x,y,z])
