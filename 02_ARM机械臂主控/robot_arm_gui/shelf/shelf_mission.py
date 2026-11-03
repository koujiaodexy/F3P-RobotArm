"""Offline multi-item shelf policy. Commands are simulation intents only."""
import copy
import math
from .cargo_routes import COLORS, Mission, finite

RETURN_EXTRA_MM = 260.0


def validate_shelves(shelves):
    if not isinstance(shelves, list) or len(shelves) != 3:
        raise ValueError('必须配置 3 个货架')
    clean = []
    for row in shelves:
        if not isinstance(row, dict) or set(row) != set(COLORS):
            raise ValueError('每个货架需要红、黄、绿数量')
        if any(type(row[c]) is not int or not 0 <= row[c] <= 20 for c in COLORS):
            raise ValueError('每种颜色数量须为 0 到 20 的整数')
        clean.append({c: row[c] for c in COLORS})
    if not any(sum(row.values()) for row in clean):
        raise ValueError('至少选择一个积木')
    return clean


class ShelfMission(Mission):
    """Original workspace and safety policy plus shelf quotas and measured return.

    The board executor reuses existing grasp_motion. A successful receipt indicates completion
    of a commanded pick/place cycle, not sensor-confirmed physical pickup.
    """
    def __init__(self, base_config, shelves):
        super().__init__(base_config)
        if self.cfg['program'] != 2:
            raise ValueError('多货架任务需要原程序 2 的基础配置')
        self.shelves = validate_shelves(shelves)
        last = max(i for i, row in enumerate(self.shelves, 1) if sum(row.values()))
        route = self.cfg['travel']
        last_index = next(i for i, leg in enumerate(route) if leg.get('station') == last)
        self.cfg['travel'] = route[:last_index + 1] + [
            {'left_deg': -180, 'capture_return': True}, {'return_actual': True},
            {'left_deg': 45}, {'forward_mm': 500}, {'left_deg': -45}]
        self.remaining = copy.deepcopy(self.shelves)
        self.origin = None
        self.return_mm = None
        self.repeat_station = False

    def _eligible(self, target):
        station = self.cfg['travel'][self.index]['station']
        return super()._eligible(target) and self.remaining[station - 1][target['color']] > 0

    def _search_distance(self, status):
        distance = super()._search_distance(status)
        leg = self.cfg['travel'][self.index]
        if self.records.get(leg['record'], 0.0) + distance >= self.cfg['seek_max_mm']:
            raise ValueError('Cumulative shelf search distance limit exceeded')
        return distance

    def _enter_leg(self, status):
        if self.repeat_station:
            self.index -= 1
            self.repeat_station = False
        while self.index < len(self.cfg['travel']):
            leg = self.cfg['travel'][self.index]
            if 'station' in leg and not sum(self.remaining[leg['station'] - 1].values()):
                self.records[leg['record']] = 0.0
                self.log.append(dict(time=self.now, station=leg['station'], skipped=True))
                self.index += 1
                continue
            break
        if self.index < len(self.cfg['travel']):
            leg = self.cfg['travel'][self.index]
            if leg.get('capture_return'):
                if self.origin is None or not status['wheels_stopped']:
                    raise ValueError('Return needs stopped wheels and a start odometry baseline')
                delta = [a-b for a,b in zip(status['odo_mm'],self.origin)]
                if not all(finite(v) and v >= 0 for v in delta) or abs(delta[0]-delta[1]) > 30:
                    raise ValueError('Invalid outbound odometry; cannot determine return distance')
                distance = sum(delta)/2
                if distance <= 0 or not math.isfinite(distance + RETURN_EXTRA_MM):
                    raise ValueError('Invalid outbound distance')
                self.return_mm = distance + RETURN_EXTRA_MM
                self.log.append(dict(time=self.now,outbound_per_wheel_mm=delta,
                                     outbound_mean_mm=distance,return_mm=self.return_mm))
            if leg.get('return_actual'):
                if self.return_mm is None:
                    raise ValueError('No frozen outbound distance')
                self._safe_wheels(status)
                self.quiet_at = None
                self.state = 'TRAVEL'
                self._command('drive',distance_mm=self.return_mm,basis='measured_outbound_plus_260mm')
                return
        super()._enter_leg(status)

    def tick(self, status, key=None):
        before = self.state
        before_action = copy.deepcopy(self.action)
        if key == 'KEY2' and before == 'IDLE':
            self.remaining = copy.deepcopy(self.shelves)
            self.origin = list(status['odo_mm']) if isinstance(status.get('odo_mm'),(list,tuple)) else None
            self.return_mm = None
            self.repeat_station = False
        previous_record = None
        if before == 'BRAKE':
            leg = self.cfg['travel'][self.index]
            previous_record = self.records.get(leg['record'], 0.0)
        result = super().tick(status, key)
        if before == 'BRAKE' and self.state == 'GRASP':
            leg = self.cfg['travel'][self.index]
            self.records[leg['record']] += previous_record
        if before == 'GRASP' and self.state == 'SETTLE':
            station = before_action['station']
            color = before_action['target']['color']
            if self.remaining[station - 1][color] <= 0:
                self._stop('Completed color exceeds shelf quota')
                return copy.deepcopy(self.action)
            self.remaining[station - 1][color] -= 1
            self.log.append(dict(time=self.now, station=station, completed_color=color,
                                 remaining=copy.deepcopy(self.remaining[station - 1])))
            self.repeat_station = sum(self.remaining[station - 1].values()) > 0
        return result
