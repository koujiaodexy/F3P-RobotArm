"""Nominal six-axis shaft-tip kinematics. mm/degree public units; no hardware IO.

The CAD reference is upper arm vertical, forearm horizontal. Controller zero
and signs MUST be mapped separately. TCP +Z points outward along the shaft.
"""
import math

DIMENSIONS = (170.0, 37.5, 160.0, 15.0, 142.3, 39.5)
GEOMETRY_VERSION = 'original-arm-cad-20261004-v1'


def finite_vector(v, count):
    if not isinstance(v, (list, tuple)) or len(v) != count or any(
            type(x) not in (int, float) or not math.isfinite(x) for x in v):
        raise ValueError('需要有限数值向量，长度 '+str(count))
    return list(v)


def add(a,b): return [x+y for x,y in zip(a,b)]
def sub(a,b): return [x-y for x,y in zip(a,b)]
def scale(a,k): return [x*k for x in a]
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def norm(a): return math.sqrt(dot(a,a))
def cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def transpose(a): return [list(v) for v in zip(*a)]
def mv(a,v): return [dot(row,v) for row in a]
def mm(a,b): return [[dot(row,col) for col in zip(*b)] for row in a]
def eye(): return [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]


def rotation(axis, radians):
    c,s=math.cos(radians),math.sin(radians)
    return ([[1,0,0],[0,c,-s],[0,s,c]] if axis==0 else
            [[c,0,s],[0,1,0],[-s,0,c]] if axis==1 else
            [[c,-s,0],[s,c,0],[0,0,1]])


def quaternion(r):
    """Stable rotation matrix to w,x,y,z, including rotations near pi."""
    t=sum(r[i][i] for i in range(3))
    if t>0:
        s=2*math.sqrt(t+1)
        q=[s/4,(r[2][1]-r[1][2])/s,(r[0][2]-r[2][0])/s,(r[1][0]-r[0][1])/s]
    else:
        i=max(range(3),key=lambda k:r[k][k]);j=(i+1)%3;k=(i+2)%3
        s=2*math.sqrt(max(0,1+r[i][i]-r[j][j]-r[k][k]))
        q=[0.,0.,0.,0.];q[0]=(r[k][j]-r[j][k])/s;q[i+1]=s/4
        q[j+1]=(r[i][j]+r[j][i])/s;q[k+1]=(r[i][k]+r[k][i])/s
    return scale(q,1/norm(q))


def rotation_log(r):
    q=quaternion(r)
    if q[0]<0:q=scale(q,-1)
    v=q[1:];s=norm(v)
    return scale(v,2) if s<1e-10 else scale(v,2*math.atan2(s,q[0])/s)


def validate_pose(pose):
    p=finite_vector(pose['position_mm'],3);r=pose['rotation']
    if not isinstance(r,(list,tuple)) or len(r)!=3:raise ValueError('方向矩阵须为3×3')
    r=[finite_vector(row,3) for row in r];check=mm(r,transpose(r))
    if max(abs(check[i][j]-(i==j)) for i in range(3) for j in range(3))>1e-6 or abs(dot(r[0],cross(r[1],r[2]))-1)>1e-6:
        raise ValueError('方向矩阵不是有效右手旋转')
    return dict(position_mm=p,rotation=r)


def pose_from_rpy(position, rpy_deg):
    roll,pitch,yaw=map(math.radians,finite_vector(rpy_deg,3))
    return dict(position_mm=finite_vector(position,3),rotation=mm(mm(rotation(2,yaw),rotation(1,pitch)),rotation(0,roll)))


def rpy_from_pose(pose):
    r=validate_pose(pose)['rotation'];pitch=math.asin(max(-1,min(1,-r[2][0])))
    if abs(math.cos(pitch))<1e-8:roll=0.;yaw=math.atan2(-r[0][1],r[1][1])
    else:roll=math.atan2(r[2][1],r[2][2]);yaw=math.atan2(r[1][0],r[0][0])
    return list(map(math.degrees,(roll,pitch,yaw)))


def _legacy_forward(angles_deg, jacobian=False):
    angles=finite_vector(angles_deg,6);r=eye();p=[0.,0.,0.];axes=[];origins=[]
    h,offset,upper,elbow,forearm,tip=DIMENSIONS
    def turn(axis,value):
        nonlocal r
        origins.append(list(p));axes.append([r[i][axis] for i in range(3)])
        r=mm(r,rotation(axis,math.radians(value)))
    def move(v):
        nonlocal p
        p=add(p,mv(r,v))
    turn(2,angles[0]);move([offset,0,h])
    turn(1,angles[1]);move([0,0,upper])
    turn(1,angles[2]);move([0,0,elbow])
    turn(0,angles[3]);move([forearm,0,0])
    turn(1,angles[4]);turn(0,angles[5]);move([tip,0,0])
    # Tool X = forearm Y, tool Y = forearm Z, tool Z = shaft X.
    result=dict(position_mm=p,rotation=mm(r,[[0,0,1],[1,0,0],[0,1,0]]))
    if jacobian:
        columns=[scale(cross(axis,sub(p,origin)),1/200)+axis for axis,origin in zip(axes,origins)]
        result['jacobian']=transpose(columns)  # scaled linear rows; per radian
        result['axes']=axes
        result['origins']=origins
    return result


def pose_error(goal,actual):
    return norm(sub(goal['position_mm'],actual['position_mm'])),math.degrees(norm(rotation_log(mm(goal['rotation'],transpose(actual['rotation'])))))


def solve(a,b):
    """Small pivoted linear solver for damped 6×6 normal equations."""
    rows=[list(row)+[v] for row,v in zip(a,b)];n=len(b)
    for i in range(n):
        k=max(range(i,n),key=lambda j:abs(rows[j][i]));rows[i],rows[k]=rows[k],rows[i]
        if abs(rows[i][i])<1e-15:raise ValueError('逆解数值矩阵退化')
        rows[i]=scale(rows[i],1/rows[i][i])
        for j in range(n):
            if j!=i:rows[j]=sub(rows[j],scale(rows[i],rows[j][i]))
    return [row[-1] for row in rows]


def singular_value(j):
    a=mm(transpose(j),j)
    for _ in range(100):
        p,q=max(((i,k) for i in range(6) for k in range(i+1,6)),key=lambda pair:abs(a[pair[0]][pair[1]]))
        if abs(a[p][q])<1e-13:break
        theta=.5*math.atan2(2*a[p][q],a[q][q]-a[p][p]);c,s=math.cos(theta),math.sin(theta)
        t=[[float(i==k) for k in range(6)] for i in range(6)]
        t[p][p]=t[q][q]=c;t[p][q]=s;t[q][p]=-s
        a=mm(mm(transpose(t),a),t)
    return math.sqrt(max(0,min(a[i][i] for i in range(6))))


def _legacy_inverse(goal, seed_deg, bounds=None, *, multistart=True, check=lambda:None):
    goal=validate_pose(goal);seed=finite_vector(seed_deg,6);bounds=bounds or {}
    for i,b in bounds.items():
        if type(i) is not int or not 0<=i<6 or len(b)!=2 or not all(type(x) in (int,float) and math.isfinite(x) for x in b) or b[0]>b[1]:raise ValueError('模型关节限位无效')
    def clamp(q):return [min(bounds[i][1],max(bounds[i][0],v)) if i in bounds else v for i,v in enumerate(q)]
    seeds=[clamp(seed)]
    if multistart:
        for axis,amount in ((1,35),(2,-60),(4,60),(4,-60),(0,90),(0,-90),(3,90),(3,-90)):
            trial=list(seed);trial[axis]+=amount;seeds.append(clamp(trial))
    candidates=[];best_error=float('inf')
    for initial in seeds:
        q=initial;damping=.03
        for _ in range(180):
            check();actual=forward(q,True);pe,ae=pose_error(goal,actual)
            residual=scale(sub(goal['position_mm'],actual['position_mm']),1/200)+rotation_log(mm(goal['rotation'],transpose(actual['rotation'])))
            cost=dot(residual,residual);best_error=min(best_error,pe+ae)
            if pe<=.03 and ae<=.03:
                # Choose equivalent whole turns nearest the supplied seed.
                nearest=[]
                for i,v in enumerate(q):
                    v+=360*round((seed[i]-v)/360)
                    if i in bounds:
                        legal=[v+360*k for k in range(-3,4) if bounds[i][0]-1e-8<=v+360*k<=bounds[i][1]+1e-8]
                        if not legal:break
                        v=min(legal,key=lambda x:abs(x-seed[i]))
                    nearest.append(v)
                if len(nearest)==6:
                    candidates.append((sum((v-w)**2 for v,w in zip(nearest,seed)),nearest,pe,ae))
                break
            j=actual['jacobian'];jt=transpose(j);a=mm(jt,j)
            for i in range(6):a[i][i]+=damping*damping
            step=solve(a,mv(jt,residual));largest=max(abs(v) for v in step)
            if largest>.25:step=scale(step,.25/largest)
            improved=False
            for fraction in (1.,.5,.25,.1):
                trial=clamp(add(q,scale(step,math.degrees(fraction))))
                pose=forward(trial);err=scale(sub(goal['position_mm'],pose['position_mm']),1/200)+rotation_log(mm(goal['rotation'],transpose(pose['rotation'])))
                if dot(err,err)<cost-1e-15:q=trial;improved=True;damping=max(.001,damping*.7);break
            if not improved:
                damping=min(2,damping*2)
                if damping>=2:break
        if candidates and not multistart:break
    if not candidates:raise ValueError('未找到收敛且满足限位的逆解；请调整位置、方向或初始姿态')
    _,q,pe,ae=min(candidates,key=lambda item:item[0]);sigma=singular_value(forward(q,True)['jacobian'])
    return dict(angles_deg=q,position_error_mm=pe,orientation_error_deg=ae,
                singular_value=sigma,near_singularity=sigma<.01)


def interpolate_rotation(a,b,t):
    qa,qb=quaternion(a),quaternion(b);cosine=dot(qa,qb)
    if cosine<0:qb=scale(qb,-1);cosine=-cosine
    if cosine>.9995:q=add(scale(qa,1-t),scale(qb,t));q=scale(q,1/norm(q))
    else:
        angle=math.acos(max(-1,min(1,cosine)));q=add(scale(qa,math.sin((1-t)*angle)/math.sin(angle)),scale(qb,math.sin(t*angle)/math.sin(angle)))
    w,x,y,z=q
    return [[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
            [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
            [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]


def forward(angles_deg,jacobian=False):
    from .reference_adapter import forward as reference_forward
    return reference_forward(finite_vector(angles_deg,6),jacobian)


def inverse(goal,seed_deg,bounds=None,*,multistart=True,check=lambda:None):
    from .reference_adapter import inverse as reference_inverse
    goal=validate_pose(goal);seed=finite_vector(seed_deg,6);bounds=bounds or {}
    for i,b in bounds.items():
        if type(i) is not int or not 0<=i<6 or len(b)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in b) or b[0]>b[1]:
            raise ValueError('模型关节限位无效')
    return reference_inverse(goal,seed,bounds,check,multistart)
