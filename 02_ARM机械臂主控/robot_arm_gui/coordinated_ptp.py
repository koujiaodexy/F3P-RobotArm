"""Bounded Emm rest-to-rest timing; no I/O and no changes to target positions."""
import math

PTP_CAPABILITY_WORD = 0xB9
PTP_CAPABILITY = 0x5054503C
PTP_MAX_DEG_S = 60.0
PTP_SPEEDS_RPM = {1:2857, 2:2857, 3:2500, 4:420, 5:224, 6:10}


def position_speed_limits(backend):
    from .protocol import HOME_MAX_SPEEDS_RPM
    return dict(getattr(backend, 'position_speed_limits', HOME_MAX_SPEEDS_RPM))


def motion_seconds(distance, rpm, acceleration):
    """Motor degrees, integer RPM and Emm acceleration code; start/end at rest."""
    distance = abs(distance) / 6.0
    rate = 1.0 / ((256 - acceleration) * 50e-6)
    if distance <= rpm * rpm / rate:
        return 2 * math.sqrt(distance / rate)
    return distance / rpm + rpm / rate


def match_arrival(distances, speed_caps, accelerations, *, adjust_acceleration=True):
    """Choose bounded integer parameters closest to the slowest axis duration.

    Acceleration may only decrease. Integer RPM (notably J6), sequential CAN
    dispatch and mechanical lag prevent an exact simultaneous-arrival promise.
    Already-at-target axes must be excluded by the caller's position tolerance.
    """
    nodes = set(distances)
    if not nodes <= set(speed_caps) or not nodes <= set(accelerations):
        raise ValueError('同步定位参数不完整')
    for n in nodes:
        if (not math.isfinite(distances[n]) or abs(distances[n]) <= 0 or
                type(speed_caps[n]) is not int or not 1 <= speed_caps[n] <= 3000 or
                type(accelerations[n]) is not int or not 1 <= accelerations[n] <= 255):
            raise ValueError('同步定位行程、速度或加速度无效')
    target = max((motion_seconds(distances[n], speed_caps[n], accelerations[n])
                  for n in nodes), default=0.0)
    result = {}
    for n in sorted(nodes):
        distance, cap = abs(distances[n]), speed_caps[n]
        best = None
        for acc in (range(1, accelerations[n] + 1) if adjust_acceleration else (accelerations[n],)):
            rate = 1.0 / ((256 - acc) * 50e-6)
            disc = target * target - 4 * distance / (6 * rate)
            # Stable form of the lower quadratic root (avoid cancellation).
            required = (2 * distance / 6 / (target + math.sqrt(disc))) if disc >= 0 else cap
            for rpm in {1, cap, max(1,min(cap,math.floor(required))),
                        max(1,min(cap,math.ceil(required)))}:
                seconds = motion_seconds(distance, rpm, acc)
                score = (abs(seconds-target), -acc, -rpm)
                if best is None or score < best[0]:
                    best = (score, dict(rpm=rpm, acceleration=acc,
                                       predicted_motion_seconds=seconds,
                                       synchronized_duration_seconds=target))
        result[n] = best[1]
    return result
