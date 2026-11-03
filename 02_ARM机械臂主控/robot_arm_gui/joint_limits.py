"""Configured joint bounds and conservative velocity-jog stopping reserve."""
import json
import math
from pathlib import Path
from .zero_home import RATIOS


class JointLimits:
    RESPONSE_TIMEOUT = 0.25
    # Two serial reads, monitor scheduling and CAN dispatch reserve.
    REACTION_SECONDS = 0.75
    EDGE_RESERVE_DEG = 0.5

    def __init__(self, zero_config):
        self.path = Path(zero_config).with_name('joint-limits.json')
        self.bounds = {}
        self.error = ''
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('enabled') is not True:
                    return
                bounds = {int(n): tuple(values) for n, values in data['bounds_deg'].items()}
                if not bounds or any(n not in RATIOS or len(v) != 2 or
                        any(type(x) is not int for x in v) or not v[0] < 0 < v[1]
                        for n, v in bounds.items()):
                    raise ValueError('限位必须为包含0的整数角度区间')
                self.bounds = bounds
        except Exception as exc:
            # Invalid enabled configuration must not silently disable protection.
            self.error = '限位配置无效：' + str(exc)

    @property
    def coupled(self):
        return 3 in self.bounds and 4 in self.bounds

    def effective_bounds(self, node, angles):
        if self.coupled and node == 4 and angles.get(3) is not None and angles[3] <= 34:
            return None
        return self.bounds.get(node)

    def target_bounds(self, node, angles):
        if self.coupled and node == 3 and angles.get(4) is not None:
            if not self.bounds[4][0] <= angles[4] <= self.bounds[4][1]:
                low,high=self.bounds[3]
                return low,min(high,34)
        return self.effective_bounds(node,angles)

    def planning_bounds(self, signs=None, offsets=None):
        from .coupled_limits import PlanningBounds
        signs = list(signs or [1]*6); offsets = list(offsets or [0]*6)
        values = dict(self.bounds)
        if self.coupled:
            # Search J4 as continuous; downstream pulse/feedback encoding
            # checks still enforce the driver's representation range.
            values.pop(4)
        transformed={n-1:tuple(sorted(signs[n-1]*v+offsets[n-1] for v in pair))
                     for n,pair in values.items()}
        rule=dict(j4=list(self.bounds[4]), signs=signs, offsets=offsets) if self.coupled else None
        return PlanningBounds(transformed, rule)

    def check_move(self, start, end):
        from .coupled_limits import check_box
        if self.coupled:
            # Missing coupled coordinates never grant an exemption.
            if any(n not in start or n not in end for n in (3,4)):
                raise ValueError('J3/J4 条件限位需要确认两轴角度')
            check_box(dict(j4=self.bounds[4], signs=[1]*6, offsets=[0]*6),
                      [min(start.get(n,0),end.get(n,0)) for n in range(1,7)],
                      [max(start.get(n,0),end.get(n,0)) for n in range(1,7)])

    def blend_bounds(self):
        from .coupled_limits import PlanningBounds
        values=self.planning_bounds()
        return PlanningBounds({n+1:pair for n,pair in values.items()},values.rule)

    def distance(self, node, motor_angle, reverse, angles=None):
        angles = angles or {}
        bounds = self.effective_bounds(node, angles)
        if bounds is None:
            return math.inf
        low, high = bounds
        if self.coupled and node == 3 and angles.get(4) is not None:
            if not self.bounds[4][0] <= angles[4] <= self.bounds[4][1]:
                high = min(high, 34)
        angle = motor_angle / RATIOS[node]
        return angle-low if reverse else high-angle

    def stopping_distance(self, node, rpm, acceleration):
        rpm_per_second = 1 / ((256-acceleration)*50e-6)
        reaction=self.REACTION_SECONDS+(2*self.RESPONSE_TIMEOUT if self.coupled and node in (3,4) else 0)
        return (self.EDGE_RESERVE_DEG + rpm*6/RATIOS[node]*reaction
                + rpm*rpm*3/(RATIOS[node]*rpm_per_second))

    def allowed_speed(self, node, distance, requested_rpm, acceleration):
        if distance == math.inf:
            return requested_rpm
        available = distance-self.EDGE_RESERVE_DEG
        if available <= 0:
            return 0
        a = 3*(256-acceleration)*50e-6/RATIOS[node]
        reaction=self.REACTION_SECONDS+(2*self.RESPONSE_TIMEOUT if self.coupled and node in (3,4) else 0)
        b = 6*reaction/RATIOS[node]
        maximum = math.floor(2*available/(b+math.sqrt(b*b+4*a*available)))
        return max(0, min(requested_rpm, maximum))
