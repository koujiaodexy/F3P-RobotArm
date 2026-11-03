"""Validated ctypes bridge; CDLL releases the GIL during C++ numerical calls."""
import ctypes as c
import os
import threading
from pathlib import Path
from .reference_endpoint.trajectory_math import PlanningModel as PythonPlanningModel
from .reference_endpoint.kinematics import (_vector,KinematicsError,_limits,_nearest_equivalent,
    _norm,rpy_to_matrix,UnreachableTarget)

LIBRARY=None;LOAD_ERROR='';POINTER=c.POINTER(c.c_double)
if os.environ.get('F3P_DISABLE_NATIVE')!='1':
    try:
        path=Path(os.environ.get('F3P_NATIVE_MATH_PATH') or str(Path(__file__).parent/'native'/('arm_math.dll' if os.name=='nt' else 'arm_math.so')))
        LIBRARY=c.CDLL(str(path));LIBRARY.f3p_math_abi.restype=c.c_int
        if LIBRARY.f3p_math_abi()!=1:raise RuntimeError('native math ABI mismatch')
        LIBRARY.f3p_fk.argtypes=[POINTER]*6;LIBRARY.f3p_fk.restype=None
        LIBRARY.f3p_residual.argtypes=[POINTER]*3;LIBRARY.f3p_residual.restype=None
        LIBRARY.f3p_pose_norms.argtypes=[POINTER]*3;LIBRARY.f3p_pose_norms.restype=None
        LIBRARY.f3p_iterate.argtypes=[POINTER]*6;LIBRARY.f3p_iterate.restype=c.c_int
        LIBRARY.f3p_fk_batch.argtypes=[POINTER,POINTER,c.c_int,POINTER];LIBRARY.f3p_fk_batch.restype=None
        if hasattr(LIBRARY,'f3p_q_pose_norms'):
            LIBRARY.f3p_q_pose_norms.argtypes=[POINTER]*5;LIBRARY.f3p_q_pose_norms.restype=None
            LIBRARY.f3p_path_tangent.argtypes=[POINTER]*4;LIBRARY.f3p_path_tangent.restype=c.c_int
        if hasattr(LIBRARY,'f3p_position_iterate'):
            LIBRARY.f3p_position_iterate.argtypes=[POINTER]*6;LIBRARY.f3p_position_iterate.restype=c.c_int
            LIBRARY.f3p_position_tangent.argtypes=[POINTER]*5;LIBRARY.f3p_position_tangent.restype=c.c_int
        if hasattr(LIBRARY,'f3p_timing_rates'):
            LIBRARY.f3p_derivative_bound.argtypes=[POINTER,c.c_int,c.c_double,c.c_double,c.c_int]
            LIBRARY.f3p_derivative_bound.restype=c.c_double
            LIBRARY.f3p_inverse_u.argtypes=[POINTER,c.c_double,c.c_double,c.c_double,c.c_int]
            LIBRARY.f3p_inverse_u.restype=c.c_double
            LIBRARY.f3p_timing_rates.argtypes=[POINTER]+[c.c_double]*5+[c.c_int,POINTER,POINTER]
            LIBRARY.f3p_timing_rates.restype=None
    except (OSError,RuntimeError) as exc:LIBRARY=None;LOAD_ERROR=str(exc)
if os.environ.get('F3P_REQUIRE_NATIVE')=='1' and LIBRARY is None:
    raise RuntimeError('required native math unavailable: '+LOAD_ERROR)

def array(values):
    # array('d') converts numeric sequences in C; ctypes retains its backing
    # buffer, avoiding per-element ctypes construction and an extra copy.
    from array import array as doubles
    storage=doubles('d',values)
    return (c.c_double*len(storage)).from_buffer(storage)
def flatten(matrix):return [x for row in matrix for x in row]

class PlanningModel(PythonPlanningModel):
    def __init__(self,profile):
        super().__init__(profile)
        self.native_enabled=LIBRARY is not None
        self._native_retry=threading.local()
        self._native_geometry=array(self._alpha+self._a+self._d+self._offsets+
            [self._offset_sign,int(self.target_frame=='physical_tcp')]+flatten(self._tcp or [[float(i==j) for j in range(4)] for i in range(4)]))

    def _forward_chain(self,q,include_frames):
        if not self.native_enabled:return super()._forward_chain(q,include_frames)
        q=array(_vector(q,6,'joints_deg'));t=array([0.]*16)
        axes=array([0.]*18) if include_frames else None
        origins=array([0.]*18) if include_frames else None
        points=array([0.]*21) if include_frames else None
        LIBRARY.f3p_fk(self._native_geometry,q,t,axes,origins,points)
        matrix=[list(t[i:i+4]) for i in range(0,16,4)]
        if include_frames:return matrix,[list(axes[i:i+3]) for i in range(0,18,3)],[list(origins[i:i+3]) for i in range(0,18,3)],[list(points[i:i+3]) for i in range(0,21,3)]
        return matrix

    def _iterate(self,start,target,limits):
        if not self.native_enabled:return super()._iterate(start,target,limits)
        retry=getattr(self._native_retry,'value',None)
        if retry is not None:
            self._native_retry.value=None
            if start==retry[0] and target==retry[1] and limits==retry[2]:return retry[3]
        result=array([0.]*10)
        status=LIBRARY.f3p_iterate(self._native_geometry,array(start),array(flatten(target)),array(flatten(limits)),
            array([self._position_tolerance,self._orientation_tolerance,self._scale,self._step,self._iterations]),result)
        if status<0:raise KinematicsError('native IK produced nonfinite residual')
        detail=(result[7],result[8],int(result[9]));q=list(result[1:7])
        return (q,detail) if status else (None,(result[0],q,detail))

    def _residual(self,t,target):
        if not self.native_enabled:return super()._residual(t,target)
        result=array([0.]*6);LIBRARY.f3p_residual(array(flatten(t)),array(flatten(target)),result)
        import math
        return [v/self._scale for v in result[:3]]+list(result[3:]),math.sqrt(sum(v*v for v in result[:3])),math.sqrt(sum(v*v for v in result[3:]))

    def solve(self,position_mm,rpy_deg,seed_deg,limits_deg=None):
        if not self.native_enabled:return super().solve(position_mm,rpy_deg,seed_deg,limits_deg)
        # Original first seed and normalization, without eagerly constructing
        # all other seeds when a nearby continuous solution already converges.
        position=_vector(position_mm,3,'position_mm');seed=_vector(seed_deg,6,'seed_deg')
        rotation=rpy_to_matrix(rpy_deg)
        physical=self.joint_limits_deg if limits_deg is None else _limits(limits_deg,self._continuous_joints)
        limits=[[reference-180.,reference+180.] if pair is None else pair for pair,reference in zip(physical,seed)]
        radius=sum(abs(v) for v in self._a+self._d)
        if self.target_frame=='physical_tcp':radius+=_norm([self._tcp[i][3] for i in range(3)])
        if _norm(position)>radius+self._position_tolerance:raise UnreachableTarget('target exceeds conservative model reach bound')
        target=[rotation[i]+[position[i]] for i in range(3)]+[[0,0,0,1]]
        start=[_nearest_equivalent(v,lo,hi,ref) for v,(lo,hi),ref in zip(seed,limits,seed)]
        solution,detail=self._iterate(start,target,limits)
        if solution is not None:
            solution=[_nearest_equivalent(v,lo,hi,ref) for v,(lo,hi),ref in zip(solution,limits,seed)]
            _,pe,oe=self._residual(self.forward(solution),target)
            if pe<=self._position_tolerance and oe<=self._orientation_tolerance:
                import math
                self.last_solve=dict(converged=True,seed_attempts=1,iterations=detail[2],position_error_mm=pe,
                    orientation_error_deg=math.degrees(oe),target_frame=self.target_frame)
                return solution
        # All original candidates, order and search bounds remain available.
        self._native_retry.value=(start,target,limits,(solution,detail))
        try:return super().solve(position_mm,rpy_deg,seed_deg,limits_deg)
        finally:self._native_retry.value=None
