"""Bounded position-only IK for explicitly opted-in drawing orientation changes."""
import math
from .reference_endpoint.kinematics import KinematicsError,_solve_linear


def solve_position(model,xyz,seed,limits,check=lambda:None,tolerance=.05):
    limits=[([v-180,v+180] if pair is None else pair) for v,pair in zip(seed,limits)]
    starts=[[max(lo,min(hi,v)) for v,(lo,hi) in zip(seed,limits)]]
    starts += [[max(lo,min(hi,v+d)) for v,d,(lo,hi) in zip(seed,delta,limits)]
               for delta in ((0,10,-15,0,15,0),(0,-10,15,0,-15,0),(0,25,-35,45,25,0))]
    best=float('inf')
    for start in starts:
        from .native_math import LIBRARY,array,flatten
        if (getattr(model,'native_enabled',False) and LIBRARY is not None
                and hasattr(LIBRARY,'f3p_position_iterate')):
            check();target=[[float(i==j) for j in range(4)] for i in range(4)]
            for i in range(3):target[i][3]=xyz[i]
            result=array([0.]*10)
            status=LIBRARY.f3p_position_iterate(model._native_geometry,array(start),array(flatten(target)),
                array(flatten(limits)),array([tolerance,1.,200.,math.radians(6),160]),result)
            check();best=min(best,result[7])
            if status<0:raise KinematicsError('自动朝向原生逆解产生非有限残差')
            if status:
                q=list(result[1:7]);t=model.forward(q)
                if (all(lo<=v<=hi for v,(lo,hi) in zip(q,limits))
                        and math.dist(xyz,[r[3] for r in t[:3]])<=tolerance):return q
            continue
        q=list(start);damping=.01
        for iteration in range(160):
            check();t,axes,origins,_=model._chain(q)
            p=[row[3] for row in t[:3]];error=[(a-b)/200 for a,b in zip(xyz,p)]
            norm=math.sqrt(sum(v*v for v in error));best=min(best,norm*200)
            if norm*200<=tolerance:return q
            columns=[]
            for axis,origin in zip(axes,origins):
                d=[a-b for a,b in zip(p,origin)]
                columns.append([(axis[1]*d[2]-axis[2]*d[1])/200,
                                (axis[2]*d[0]-axis[0]*d[2])/200,
                                (axis[0]*d[1]-axis[1]*d[0])/200])
            a=[[sum(c[i]*c[j] for c in columns)+(damping*damping if i==j else 0) for j in range(3)] for i in range(3)]
            try:dual=_solve_linear(a,error)
            except ArithmeticError:break
            step=[sum(c[i]*dual[i] for i in range(3)) for c in columns]
            scale=min(1.,math.radians(6)/max(max(abs(v) for v in step),1e-12))
            improved=False
            for fraction in (1.,.5,.25,.125,.0625):
                candidate=[max(lo,min(hi,v+math.degrees(s)*scale*fraction)) for v,s,(lo,hi) in zip(q,step,limits)]
                transform=model.forward(candidate)
                cost=sum((xyz[i]-transform[i][3])**2 for i in range(3))
                if cost<(norm*200)**2-1e-12:
                    q=candidate;damping=max(1e-5,damping*.7);improved=True;break
            if not improved:
                damping*=4
                if damping>10:break
    raise KinematicsError('自动朝向位置逆解未收敛，最小位置残差 %.4fmm；需核对可达性或关节限位'%best)
