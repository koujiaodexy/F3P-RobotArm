"""Local planning math: identical MDH arithmetic with cached fixed geometry.

Public profiles and joints retain ArmModel validation. Pose errors below only
accept transforms constructed by this model or the validated path geometry;
external transform validation remains in the public kinematics API.
"""
import math
from .kinematics import (ArmModel, _vector, _multiply, _rotation, _transpose,
                         _rotation_log, KinematicsError)

class PlanningModel(ArmModel):
    def __init__(self, profile):
        super().__init__(profile)
        self._alpha_cs=tuple((math.cos(math.radians(a%360.)),
                              math.sin(math.radians(a%360.))) for a in self._alpha)
    def _forward_chain(self, joints_deg, include_frames):
        if include_frames:
            return super()._forward_chain(joints_deg, True)
        q=_vector(joints_deg,6,'joints_deg')
        r00,r01,r02,r10,r11,r12,r20,r21,r22=1.,0.,0.,0.,1.,0.,0.,0.,1.
        x,y,z=0.,0.,0.
        for i in range(6):
            ca,sa=self._alpha_cs[i]
            theta=math.radians((q[i]+self._offset_sign*self._offsets[i])%360.)
            ct,st=math.cos(theta),math.sin(theta)
            a,d=self._a[i],self._d[i]
            t0,t1,t2=ca*r01+sa*r02,ca*r11+sa*r12,ca*r21+sa*r22
            ax0,ax1,ax2=-sa*r01+ca*r02,-sa*r11+ca*r12,-sa*r21+ca*r22
            x,y,z=(x+a*r00)+d*ax0,(y+a*r10)+d*ax1,(z+a*r20)+d*ax2
            r00,r01,r02=ct*r00+st*t0,-st*r00+ct*t0,ax0
            r10,r11,r12=ct*r10+st*t1,-st*r10+ct*t1,ax1
            r20,r21,r22=ct*r20+st*t2,-st*r20+ct*t2,ax2
        t=[[r00,r01,r02,x],[r10,r11,r12,y],[r20,r21,r22,z],[0.,0.,0.,1.]]
        return _multiply(t,self._tcp) if self.target_frame=='physical_tcp' else t

def planning_pose_error(current,target):
    # FK plus the fixed start rotation construct rigid transforms. Retain
    # finiteness checks; rebuilding and validating SO(3) at every blend sample
    # repeated checks of the same already-validated geometry.
    if any(not math.isfinite(v) for matrix in (current,target) for row in matrix for v in row):
        raise KinematicsError('planning transform must contain finite numbers')
    return ([target[i][3]-current[i][3] for i in range(3)],
        _rotation_log(_multiply(_rotation(target),_transpose(_rotation(current)))))
