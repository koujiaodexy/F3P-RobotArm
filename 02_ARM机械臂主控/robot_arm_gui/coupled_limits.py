"""J3/J4 constraint in displayed joint degrees, including swept boxes."""
import math


class PlanningBounds(dict):
    def __init__(self, values=(), rule=None):
        super().__init__(values)
        self.rule = rule


def one_based(bounds):
    return PlanningBounds({i+1:pair for i,pair in bounds.items()},getattr(bounds,'rule',None))


def nearest_legal_winding(model, angles, seed):
    """Unwrap continuous axes without undoing a conditional IK limit choice.

    The solver may return a J4 winding inside the old interval when J3 is
    above the threshold. Its unconstrained nearest equivalent can be outside
    that interval even though it represents the same mathematical pose.
    """
    result=list(angles)
    rule=model._profile.get('j3_j4_rule')
    for n in model.continuous_joints:
        i=n-1
        if n==4 and rule and (result[2]-rule['offsets'][2])*rule['signs'][2]>34:
            lo,hi=sorted(rule['signs'][3]*v+rule['offsets'][3] for v in rule['j4'])
            first=math.ceil((lo-result[i])/360)
            last=math.floor((hi-result[i])/360)
            if first>last:
                from .reference_endpoint.kinematics import KinematicsError
                raise KinematicsError('后续逆解的J4没有满足条件限位的等价角度')
            turns=min(last,max(first,round((seed[i]-result[i])/360)))
        else:turns=round((seed[i]-result[i])/360)
        result[i]+=360*turns
    return result


def check_box(rule, low, high):
    if not rule:
        return
    signs, offsets = rule['signs'], rule['offsets']
    pairs = [sorted(((a-o)*s, (b-o)*s))
             for a,b,s,o in zip(low, high, signs, offsets)]
    if any(not math.isfinite(v) for pair in pairs for v in pair):
        raise ValueError('J3/J4 条件限位角度无效')
    if pairs[2][1] > 34 and (pairs[3][0] < rule['j4'][0] or pairs[3][1] > rule['j4'][1]):
        raise ValueError('检查区间J3上界 %.6f° 超过34°，J4区间 [%.6f°, %.6f°] 超出 [%.0f°, %.0f°]；需要重新规划接续，不表示当前J3已超限'%
                         (pairs[2][1],pairs[3][0],pairs[3][1],*rule['j4']))


def check_model_box(model, start, end):
    rule=model._profile.get('j3_j4_rule')
    if not rule:return
    if any(not math.isfinite(v) for vector in (start,end) for v in vector):
        raise ValueError('J3/J4 条件限位角度无效')
    # An affine angle mapping preserves the endpoint extrema of the box.
    # Only J3/J4 enter this rule; every input still receives the finite check.
    pairs=[sorted(((start[i]-rule['offsets'][i])*rule['signs'][i],
                   (end[i]-rule['offsets'][i])*rule['signs'][i])) for i in (2,3)]
    if pairs[0][1]>34 and (pairs[1][0]<rule['j4'][0] or pairs[1][1]>rule['j4'][1]):
        raise ValueError('检查区间J3上界 %.6f° 超过34°，J4区间 [%.6f°, %.6f°] 超出 [%.0f°, %.0f°]；需要重新规划接续，不表示当前J3已超限'%
                         (pairs[0][1],pairs[1][0],pairs[1][1],*rule['j4']))


def check_cubic(model, coefficients):
    # Exact extrema of each cubic enclose every pose, not just sample points.
    low, high = [], []
    for a,b,c,d in coefficients:
        xs = [0., 1.]
        if abs(a)>1e-15:
            disc = 4*b*b-12*a*c
            if disc>=0:
                xs += [x for x in ((-2*b+math.sqrt(disc))/(6*a),
                                  (-2*b-math.sqrt(disc))/(6*a)) if 0<x<1]
        elif abs(b)>1e-15:
            x=-c/(2*b)
            if 0<x<1:xs.append(x)
        values=[((a*x+b)*x+c)*x+d for x in xs]
        low.append(min(values));high.append(max(values))
    check_box(model._profile.get('j3_j4_rule'), low, high)
