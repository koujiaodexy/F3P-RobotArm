"""Optional grasp-only batching. No hardware, worker or process ownership."""
import ctypes as c
import math
import os
from pathlib import Path
from . import native_math as nm

LIBRARY = None
if os.environ.get('F3P_DISABLE_NATIVE') != '1' and os.environ.get('F3P_DISABLE_GRASP_NATIVE') != '1':
    try:
        path = Path(__file__).parent / 'native' / ('grasp_prepare.dll' if os.name == 'nt' else 'grasp_prepare.so')
        library = c.CDLL(str(path))
        library.f3p_grasp_prepare_abi.restype = c.c_int
        if library.f3p_grasp_prepare_abi() != 1:
            raise RuntimeError('grasp preparation ABI mismatch')
        library.f3p_grasp_grid.argtypes = [nm.POINTER]*3 + [c.c_int, nm.POINTER] + [c.c_int]*4 + [nm.POINTER]*4
        library.f3p_grasp_grid.restype = c.c_int
        library.f3p_grasp_samples.argtypes = [nm.POINTER]*3 + [c.c_int] + [nm.POINTER]*4 + [c.c_int, nm.POINTER]
        library.f3p_grasp_samples.restype = c.c_int
        LIBRARY = library
    except (OSError, AttributeError, RuntimeError):
        pass


class PreparedCurve:
    def __init__(self, model, guide, slopes, ppr):
        if (not guide or len(guide) != len(slopes) or any(len(q) != 6 or any(not math.isfinite(v) for v in q)
                for q in guide + slopes)):
            raise ValueError('快速取放导引含无效关节角度')
        rule = model._profile.get('j3_j4_rule')
        self.rule = nm.array([1.] + list(rule['signs']) + list(rule['offsets']) + list(rule['j4']) if rule else [0.]*15)
        self.model = model
        self.guide = nm.array(nm.flatten(guide))
        self.slopes = nm.array(nm.flatten(slopes))
        self.count = len(guide)-1
        self.mapping = nm.array(model._motor_ref + model._joint_ref + model._directions + model._ratios)
        self.ppr = nm.array(ppr)

    @staticmethod
    def _require(status):
        if status:
            raise ValueError({-3: '快速取放导引或量化关节路径违反J3/J4条件限位',
                              -4: '伸缩导引偏离目标直线或朝向；本轮未启动',
                              -5: '快速取放轨迹脉冲超出signed32范围',
                              -6: '快速取放轨迹超出位置反馈范围'}.get(status, '快速取放本地批量数学输入或结果无效'))

    def derivatives(self, grid, mode, origin, goal, check):
        state = nm.array([0.]*24)
        a, b, rotation = nm.array(origin['position_mm']), nm.array(goal['position_mm']), nm.array(nm.flatten(goal['rotation']))
        for begin in range(0, grid+1, 64):
            check()
            self._require(LIBRARY.f3p_grasp_grid(self.model._native_geometry, self.guide, self.slopes, self.count,
                self.rule, grid, begin, min(64, grid+1-begin), int(mode == 'L'), a, b, rotation, state))
        check()
        return list(state[12:18]), list(state[18:24])

    def samples(self, us, check):
        results = []
        for begin in range(0, len(us), 64):
            check()
            group = us[begin:begin+64]
            output = nm.array([0.]*(34*len(group)))
            self._require(LIBRARY.f3p_grasp_samples(self.model._native_geometry, self.guide, self.slopes, self.count,
                self.rule, self.mapping, self.ppr, nm.array(group), len(group), output))
            for offset in range(0, len(output), 34):
                row = output[offset:offset+34]
                transform = [row[i:i+4] for i in (18,22,26,30)]
                native_rotation = [r[:3] for r in transform[:3]]
                pose = dict(position_mm=[r[3] for r in transform[:3]], native_rotation=native_rotation,
                            rotation=[[-r[1], r[0], r[2]] for r in native_rotation])
                results.append((list(row[:6]), list(row[6:12]), [int(p) for p in row[12:18]], pose))
            check()
        return results


def prepare(model, guide, slopes, ppr):
    if LIBRARY is None or not getattr(model, 'native_enabled', False):
        return None
    return PreparedCurve(model, guide, slopes, ppr)
