"""Transport-free clearance checks in the locked CAD/model coordinate frame.

The table is the CAD mounting plane, model Z=0. Cartesian tracking budgets
are kept separate from clearance: an endpoint on that plane is not safe.
"""
import math

TABLE_CLEARANCE_MM = 0.0


class CollisionError(ValueError):
    pass


def _add(a, b):
    return a[0] + b[0], a[1] + b[1]


def _mul(a, b):
    values = [x*y for x in a for y in b]
    return min(values), max(values)


def _scale(a, value):
    return tuple(sorted((a[0]*value, a[1]*value)))


def _trig(pair, cosine=False):
    lo, hi = map(math.radians, pair)
    if cosine:
        lo += math.pi/2; hi += math.pi/2
    if hi-lo >= 2*math.pi:
        return -1., 1.
    values = [math.sin(lo), math.sin(hi)]
    first = math.ceil((lo-math.pi/2)/math.pi)
    last = math.floor((hi-math.pi/2)/math.pi)
    values.extend(1. if n % 2 == 0 else -1. for n in range(first, last+1))
    return min(values), max(values)


def endpoint_z_interval(box):
    """Enclose TCP Z for every combination of joint angles in a box.

    Exact MDH expression for actual_arm.json; J1/J6 do not affect TCP height.
    This covers unsynchronised J positioning, rather than assuming equal
    progress for six independent position drivers.
    """
    shoulder, elbow, wrist_roll, wrist_pitch = box[1:5]
    bend = _add(shoulder, elbow)
    c, s = _trig(bend, True), _trig(bend)
    z = _add((170., 170.), _scale(_trig(shoulder, True), 160.))
    z = _add(z, _add(_scale(c, 15.), _scale(s, -142.3)))
    tip = _add(_mul(s, _trig(wrist_pitch, True)),
               _mul(_mul(c, _trig(wrist_roll, True)), _trig(wrist_pitch)))
    return _add(z, _scale(tip, -39.5))


def check_target(position, clearance=TABLE_CLEARANCE_MM):
    if len(position) != 3 or any(not math.isfinite(v) for v in position):
        raise ValueError('目标坐标无效')
    if position[2] <= clearance:
        raise CollisionError('目标或路径Z必须大于0：Z=%.3f mm，必须大于 %.1f mm' %
                             (position[2], clearance))


def check_joint_box(start, end, check=lambda: None, clearance=None):
    """Validate a positioning box; optionally prove explicit table clearance.

    Interval subdivision fails closed if a box cannot be resolved. Endpoint
    checks alone, or a diagonal line between joint vectors, are insufficient.
    """
    box = [tuple(sorted((a, b))) for a, b in zip(start, end)]
    if len(box) != 6 or any(not math.isfinite(v) for pair in box for v in pair):
        raise ValueError('关节路径无效')
    check()
    # The CAD Z=0 plane is not an operator-calibrated physical obstacle.
    # Per operator request, ordinary positioning no longer stops on this
    # model-height criterion. Explicit clearance remains available offline.
    if clearance is None:
        return dict(table_clearance_mm=None,joint_boxes=0,table_check_enabled=False)
    from .native_driver_tracking import LIBRARY
    if LIBRARY is not None and hasattr(LIBRARY,'f3p_box_height'):
        from .native_curve_frames import array
        check();low=LIBRARY.f3p_box_height(array(start),array(end))
        if math.isfinite(low) and low>clearance+1e-8:
            return dict(table_clearance_mm=clearance,joint_boxes=1)
    pending = [box]; count = 0
    while pending:
        check(); current = pending.pop(); count += 1
        low, high = endpoint_z_interval(current)
        if low > clearance:
            continue
        midpoint = [(a+b)/2 for a,b in current]
        height = endpoint_z_interval([(v,v) for v in midpoint])[0]
        if height <= clearance:
            raise CollisionError('J定位途中可能碰桌面：模型Z=%.3f mm；请调整起点或分段定位' % height)
        axis = max(range(1,5), key=lambda i: current[i][1]-current[i][0])
        if count > 16384 or current[axis][1]-current[axis][0] < .001:
            raise CollisionError('无法证明J定位全过程高于桌面安全高度，请调整路径')
        a,b = current[axis]; mid = (a+b)/2
        left, right = list(current), list(current)
        left[axis] = (a,mid); right[axis] = (mid,b)
        pending.extend((left,right))
    return dict(table_clearance_mm=clearance, joint_boxes=count)
