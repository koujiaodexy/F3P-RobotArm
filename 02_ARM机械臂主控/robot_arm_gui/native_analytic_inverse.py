"""Optional same-branch analytic solver for the locked actual-arm geometry."""
import ctypes as c,math
from .native_driver_tracking import LIBRARY
from .native_math import POINTER,array,flatten
if LIBRARY is not None and hasattr(LIBRARY,'f3p_fixed_pose'):
    LIBRARY.f3p_fixed_pose.argtypes=[POINTER]*7
    LIBRARY.f3p_fixed_pose.restype=c.c_int

def solve(model,xyz,rotation,seed,limits,check):
    if LIBRARY is None or not hasattr(LIBRARY,'f3p_fixed_pose') or not getattr(model,'native_enabled',False):return None
    check();rule=model._profile.get('j3_j4_rule')
    rule_data=[1.]+list(rule['signs'])+list(rule['offsets'])+list(rule['j4']) if rule else [0.]*15
    out=array([0.]*6)
    ok=LIBRARY.f3p_fixed_pose(model._native_geometry,array(xyz),array(flatten(rotation)),array(seed),
        array([v for pair in limits for v in (pair if pair else (-math.inf,math.inf))]),array(rule_data),out)
    check()
    if not ok:return None
    q=list(out)
    if any(not math.isfinite(v) for v in q):return None
    from .coupled_limits import check_model_box
    # Native search has small bound tolerances. A candidate rejected by the
    # exact downstream rule must fall through to the original branch search.
    try:check_model_box(model,q,q)
    except ValueError:return None
    return q
