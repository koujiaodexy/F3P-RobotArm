"""Version-bound sampled workspace hints and analytic endpoint reach checks.

No transport calls. A sampled membership is never an execution permission.
"""
import gzip
import hashlib
import json
import math
from pathlib import Path
from . import kinematics as k

CONDITIONAL_J4_POLICY=dict(j3_threshold_deg=34,j4_unlimited_at_or_below=True)


class Workspace:
    AXES={'plus_x':(1,0,0),'minus_x':(-1,0,0),'plus_y':(0,1,0),
          'minus_y':(0,-1,0),'plus_z':(0,0,1),'minus_z':(0,0,-1)}
    def __init__(self,path=None):
        self.error='';self.data=None;self.index={}
        try:
            with gzip.open(path or Path(__file__).parent/'workspace-data.json.gz','rt',encoding='utf-8') as f:self.data=json.load(f)
            if self.data['geometry_version']!=k.GEOMETRY_VERSION or tuple(self.data['dimensions_mm'])!=k.DIMENSIONS:
                raise ValueError('模型尺寸或版本不匹配')
            profile=Path(__file__).parent/'reference_endpoint/actual_arm.json'
            if self.data['profile_sha256']!=hashlib.sha256(profile.read_bytes()).hexdigest():raise ValueError('运动学模型文件不匹配')
            for key,rows in self.data['rows'].items():
                self.index[key]={(z,y):runs for z,y,runs in rows}
        except Exception as exc:self.error='工作区不可用：'+str(exc);self.data=None

    def compatible(self,bounds,calibration):
        if not self.data:return False
        actual={str(n):list(v) for n,v in bounds.items()}
        expected=self.data['controller_limits_deg']
        if 3 in bounds and 4 in bounds and self.data.get('conditional_j4')!=CONDITIONAL_J4_POLICY:
            return False
        return actual==expected and calibration is not None and calibration.get('geometry_version')==k.GEOMETRY_VERSION and calibration.get('signs')==self.data['signs'] and all(abs(a-b)<1e-6 for a,b in zip(calibration.get('offsets_deg',[]),self.data['offsets_deg'])) and len(calibration.get('offsets_deg',[]))==6

    @classmethod
    def direction(cls,goal):
        axis=[row[2] for row in goal['rotation']]
        return next((key for key,v in cls.AXES.items() if max(abs(a-b) for a,b in zip(axis,v))<1e-6),None)

    def classify(self,goal,bounds,calibration):
        if not self.compatible(bounds,calibration):return 'unavailable',None
        key=self.direction(goal)
        if key is None:return 'arbitrary',None
        x,y,z=goal['position_mm'];step=self.data['step_mm']
        x0,y0,z0=(int(math.floor(v/step+.5))*step for v in (x,y,z))
        inside=any(lo<=x0<=hi for lo,hi in self.index[key].get((z0,y0),[]))
        return ('sampled' if inside else 'exact'),key

    def slice_rows(self,key,z):
        if key not in self.index:return []
        z=int(math.floor(z/self.data['step_mm']+.5))*self.data['step_mm']
        return [(y,runs) for (z0,y),runs in self.index[key].items() if z0==z]


def endpoint_reachable(goal,bounds):
    """Analytic shaft-axis IK existence for this model, with unlimited J6.

    Arbitrary rotation around the shaft is supplied by continuous J6. Return
    None rather than claiming rejection when J6 has configured bounds.
    """
    if 5 in bounds:return None
    r=goal['rotation'];xyz=goal['position_mm'];w=[xyz[i]-39.5*r[i][2] for i in range(3)]
    radius=math.hypot(w[0],w[1]);z=w[2]-170
    if radius<1e-9:return None  # q1 is indeterminate: defer to normal solver.
    length=math.hypot(142.3,15);beta=math.degrees(math.atan2(142.3,15))
    from .reference_adapter import make_model
    model=make_model([0]*6,bounds)
    def equiv(a,i,interval=None):
        lo,hi=interval if interval is not None else bounds.get(i,(-180,180))
        return [a+360*n for n in range(math.ceil((lo-a-1e-8)/360),math.floor((hi-a+1e-8)/360)+1)]
    az=math.degrees(math.atan2(w[1],w[0]))
    for shoulder in (0,1):
        for q1 in equiv(az+shoulder*180,0):
            radial=radius*(-1 if shoulder else 1)-37.5
            c=(radial*radial+z*z-160**2-length**2)/(320*length)
            if abs(c)>1+1e-10:continue
            bend=math.degrees(math.acos(max(-1,min(1,c))))
            for sign in (1,-1):
                for q3 in equiv(sign*bend-beta,2):
                    t=math.radians(beta+q3)
                    q2base=math.degrees(math.atan2(radial,z)-math.atan2(length*math.sin(t),160+length*math.cos(t)))
                    for q2 in equiv(q2base,1):
                        rule=getattr(bounds,'rule',None)
                        j4_unlimited=bool(rule and (q3-rule['offsets'][2])*rule['signs'][2]<=34)
                        j4_interval=(sorted(rule['signs'][3]*v+rule['offsets'][3] for v in rule['j4'])
                                     if rule else bounds.get(3,(-180,180)))
                        # UI tool basis differs from reference by TOOL_ROTATION.
                        a=[row[:3] for row in model.forward([q1,q2,q3,0,0,0])[:3]]
                        n=[sum(a[j][i]*r[j][2] for j in range(3)) for i in range(3)]
                        angle=math.degrees(math.acos(max(-1,min(1,n[2]))))
                        for wrist in (1,-1):
                            base=wrist*angle;sn=math.sin(math.radians(base))
                            if not equiv(base,4):continue
                            q4bases=[0,90,180,*j4_interval] if abs(sn)<1e-9 else [math.degrees(math.atan2(-n[1]/sn,-n[0]/sn))]
                            if j4_unlimited or any(equiv(v,3,j4_interval) for v in q4bases):return True
    return False
