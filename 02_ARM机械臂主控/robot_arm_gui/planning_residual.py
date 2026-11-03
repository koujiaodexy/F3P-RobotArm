"""Norm-only residual for internally constructed rigid planning transforms.

The planner only uses the norm of rotation error, never its axis. The IK
Jacobian/refinement continues using the original full rotation logarithm.
"""
import math
from .native_math import LIBRARY,array,flatten
from .reference_endpoint.kinematics import KinematicsError


def planning_pose_error(current,target):
    if any(not math.isfinite(v) for matrix in (current,target) for row in matrix for v in row):
        raise KinematicsError('planning transform must contain finite numbers')
    if LIBRARY is not None:
        result=array([0.]*6);LIBRARY.f3p_pose_norms(array(flatten(current)),array(flatten(target)),result)
        return list(result[:3]),list(result[3:])
    # trace(target.R * current.R.T) is their nine-element dot product.
    trace=sum(current[i][j]*target[i][j] for i in range(3) for j in range(3))
    cosine=max(-1.,min(1.,(trace-1.)/2))
    # Round-off at an identical rotation must not invent a near-zero wrist
    # deviation. This band is far below the 0.0001-degree IK threshold.
    angle=0. if cosine>=1.-1e-15 else math.acos(cosine)
    return [target[i][3]-current[i][3] for i in range(3)],[angle,0.,0.]


def planning_joint_error(model,joints,target):
    """Same norm-only rigid residual, with FK and norm evaluation fused.

    The numerical solver still uses its full rotation logarithm. No geometry,
    sampling density, or error threshold is changed by this fast path.
    """
    if LIBRARY is not None and getattr(model,'native_enabled',False) and hasattr(LIBRARY,'f3p_q_pose_norms'):
        if any(not math.isfinite(v) for v in joints) or any(not math.isfinite(v) for row in target for v in row):
            raise KinematicsError('planning transform must contain finite numbers')
        result=array([0.,0.])
        LIBRARY.f3p_q_pose_norms(model._native_geometry,array(joints),array(flatten(target)),array([target[i][3] for i in range(3)]),result)
        return [result[0],0.,0.],[math.radians(result[1]),0.,0.]
    return planning_pose_error(model.forward(joints),target)
