"""Pure model geometry for a bounded singular-wrist preparation.

This only proposes J4/J6 equal-and-opposite joint motion. The trajectory
planner must check every timed/quantized pose against the original TCP pose;
no geometry proposal authorizes a hardware command or proves tracking.
"""
import math

from .kinematics import _solve_linear


def _cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def preparation_candidates(model, joints, tangent, limits, checkpoint):
    """Return nearest limit-valid wrist alignments for the starting tangent.

    At the aligned spherical wrist, J4 and J6 share a positive axis. The
    first three joints determine wrist-center velocity; their angular
    velocity determines the wrist bend plane needed to hold tool orientation.
    Reject other geometries/rank-deficient shoulder poses, not guess angles.
    """
    checkpoint()
    _pose, axes, origins, _points = model._chain(joints)
    if _dot(axes[3], axes[5]) < math.cos(math.radians(.001)):
        return []
    # A spherical wrist must have J5/J6 origins on the J4 axis. Independent
    # timed FK checks remain mandatory even when this geometric test passes.
    for origin in (origins[4], origins[5]):
        delta = [origin[i]-origins[3][i] for i in range(3)]
        if math.sqrt(_dot(_cross(delta, axes[3]), _cross(delta, axes[3]))) > 1e-6:
            return []
    wrist = origins[4]
    columns = [_cross(axis, [wrist[i]-origin[i] for i in range(3)])
               for axis, origin in zip(axes[:3], origins[:3])]
    jacobian = [[columns[j][i] for j in range(3)] for i in range(3)]
    try:
        rates = _solve_linear(jacobian, tangent)
    except ArithmeticError:
        return []
    if any(not math.isfinite(v) or abs(v) > 100 for v in rates):
        return []
    omega = [-sum(axes[j][i]*rates[j] for j in range(3)) for i in range(3)]
    normal = _cross(axes[3], axes[4])
    x, y = _dot(omega, axes[4]), _dot(omega, normal)
    if math.hypot(x, y) < 1e-10:
        return []
    delta = math.degrees(math.atan2(y, x))
    values = []
    for turn in range(-4, 5):
        change = delta+180*turn
        if not .01 < abs(change) <= 180+1e-9:
            continue
        q = list(joints)
        q[3] += change
        q[5] -= change
        if any(pair is not None and not pair[0]-1e-9 <= v <= pair[1]+1e-9
               for v, pair in zip(q, limits)):
            continue
        values.append(q)
    return sorted(values, key=lambda q: (abs(q[3]-joints[3]), q[3]))