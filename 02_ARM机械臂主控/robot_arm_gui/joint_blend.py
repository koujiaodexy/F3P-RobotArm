"""Offline joint-space look-ahead. No driver or hardware dependencies.

Quintic Bezier corners share velocity and zero acceleration with adjacent
segments. Convex-hull bounds certify limits and derivative caps continuously,
not just at preview samples. Units are joint degrees and seconds.
"""
import math


def norm(vector):
    return max(abs(x) for x in vector)


def subtract(a, b):
    return [x-y for x,y in zip(a,b)]


def lerp(a, b, fraction):
    return [x+(y-x)*fraction for x,y in zip(a,b)]


def evaluate(controls, fraction):
    values = controls
    while len(values)>1:
        values = [lerp(a,b,fraction) for a,b in zip(values,values[1:])]
    return values[0]


def derivatives(controls, duration):
    degree = len(controls)-1
    return [[degree*(y-x)/duration for x,y in zip(a,b)]
        for a,b in zip(controls,controls[1:])]


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def plan(start, points, bounds, radius=.5, acceleration=5.0, jerk=20.0):
    """Return a bounded preview; a positive dwell always disables corner blend.

    All points must use the same participating joints. Radius uses the maximum
    absolute joint component, not Cartesian millimetres or a Euclidean radius.
    Conservative global time scaling trades speed for certified smoothness.
    """
    if not points or len(points)>50 or not start or set(start)-set(range(1,7)):
        raise ValueError('融合需要1～50个姿态和有效参与关节')
    if not finite(radius) or not 0<=radius<=5:
        raise ValueError('融合偏差须为0～5°')
    if not finite(acceleration) or not 0<acceleration<=100 or not finite(jerk) or not 0<jerk<=1000:
        raise ValueError('加速度须为0～100°/s²，加速度变化率须为0～1000°/s³，均不含0')
    nodes = sorted(start)
    positions = [[start[n] for n in nodes]]
    speeds, dwells = [], [0.0]
    for point in points:
        angles = {int(n):v for n,v in point['angles_deg'].items()}
        speed, dwell = point['speed_deg_s'], point['dwell_seconds']
        if set(angles)!=set(nodes):
            raise ValueError('融合姿态的参与关节必须一致')
        if not finite(speed) or not 1<=speed<=20 or not finite(dwell) or not 0<=dwell<=30:
            raise ValueError('姿态速度或停留时间无效')
        positions.append([angles[n] for n in nodes])
        speeds.append(speed)
        dwells.append(dwell)
    for position in positions:
        for n,value in zip(nodes,position):
            if not finite(value) or (n!=6 and n not in bounds and not (n==4 and getattr(bounds,'rule',None))):
                raise ValueError('起点、姿态或关节限位无效')
            if n in bounds and not bounds[n][0]<=value<=bounds[n][1]:
                raise ValueError(f'J{n} 起点或姿态超过限位')
    # Full-program look-ahead: keep the most restrictive requested speed.
    speed = min(speeds)
    corners = {}
    reasons = {}
    for i in range(1,len(positions)-1):
        incoming = subtract(positions[i],positions[i-1])
        outgoing = subtract(positions[i+1],positions[i])
        a,b = norm(incoming), norm(outgoing)
        reason = '停留点' if dwells[i]>0 else '关闭融合' if radius==0 else ''
        if min(a,b)<1e-9:
            reason = reason or '重复姿态'
        if not reason:
            cosine = sum(x*y for x,y in zip(incoming,outgoing))/math.sqrt(
                sum(x*x for x in incoming)*sum(y*y for y in outgoing))
            if cosine<-.95:
                reason = '接近折返'
        if reason:
            reasons[i] = reason
            continue
        # Adjacent corners consume at most half the connecting edge together.
        r = min(radius,a*.25,b*.25)
        entry = lerp(positions[i],positions[i-1],r/a)
        exit = lerp(positions[i],positions[i+1],r/b)
        corners[i] = dict(entry=entry,exit=exit,radius=r,
            vin=[speed*x/a for x in incoming],vout=[speed*x/b for x in outgoing])
    segments = []
    zero = [0.0]*len(nodes)
    def add(a,b,vin,vout,duration,kind,point):
        if duration<=1e-12:
            return
        controls = [a,[x+v*duration/5 for x,v in zip(a,vin)],
            [x+2*v*duration/5 for x,v in zip(a,vin)],
            [x-2*v*duration/5 for x,v in zip(b,vout)],
            [x-v*duration/5 for x,v in zip(b,vout)],b]
        segments.append(dict(controls=controls,duration=duration,kind=kind,point=point))
    for i in range(1,len(positions)):
        prev, current = corners.get(i-1), corners.get(i)
        a = prev['exit'] if prev else positions[i-1]
        b = current['entry'] if current else positions[i]
        add(a,b,prev['vout'] if prev else zero,current['vin'] if current else zero,
            norm(subtract(b,a))/speed,'连接',i)
        if current:
            add(current['entry'],current['exit'],current['vin'],current['vout'],
                2*current['radius']/speed,'融合',i)
        elif dwells[i]>0:
            segments.append(dict(controls=[positions[i]]*6,duration=dwells[i],kind='停留',point=i))
    maxima = [0.0,0.0,0.0]
    for segment in segments:
        controls = segment['controls']
        rule=getattr(bounds,'rule',None)
        if rule:
            from .coupled_limits import check_box
            if any(n in nodes for n in (3,4)) and not all(n in nodes for n in (3,4)):
                raise ValueError('条件限位融合预览须同时包含J3和J4')
            low=[min(control[nodes.index(n)] for control in controls) if n in nodes else 0 for n in range(1,7)]
            high=[max(control[nodes.index(n)] for control in controls) if n in nodes else 0 for n in range(1,7)]
            check_box(rule,low,high)
        # Linear edges and corner control hulls stay inside legal joint boxes.
        for control in controls:
            for n,value in zip(nodes,control):
                if n in bounds and not bounds[n][0]-1e-9<=value<=bounds[n][1]+1e-9:
                    raise ValueError(f'J{n} 融合曲线控制包络超限')
        for order in range(3):
            controls = derivatives(controls,segment['duration'])
            maxima[order] = max(maxima[order],max(norm(v) for v in controls))
    scale = max(1.0,maxima[0]/speed,math.sqrt(maxima[1]/acceleration),
        (maxima[2]/jerk)**(1/3))
    duration = 0.0
    for segment in segments:
        # Keep explicitly requested dwell exact; only stretch motion intervals.
        if segment['kind']!='停留':
            segment['duration'] *= scale
        segment['start_seconds'] = duration
        duration += segment['duration']
    report = dict(nodes=nodes,segments=segments,total_seconds=duration,
        radius_deg=radius,time_scale=scale,speed_limit_deg_s=speed,
        acceleration_limit_deg_s2=acceleration,jerk_limit_deg_s3=jerk,
        derivative_bounds=[maxima[i]/scale**(i+1) for i in range(3)],
        blended_points={i:c['radius'] for i,c in corners.items()},
        stop_points={**reasons,len(positions)-1:'终点'},start=positions[0],end=positions[-1])
    return report


def sample(report, count=401):
    """Bounded display sampling, independent of any future execution period."""
    if type(count) is not int or not 2<=count<=2001:
        raise ValueError('预览采样数无效')
    segments = report['segments']
    if not segments:
        return [(0.0,list(report['end']))]
    result, index = [], 0
    for i in range(count):
        seconds = report['total_seconds']*i/(count-1)
        while index<len(segments)-1 and seconds>segments[index]['start_seconds']+segments[index]['duration']:
            index += 1
        segment = segments[index]
        fraction = max(0,min(1,(seconds-segment['start_seconds'])/segment['duration']))
        result.append((seconds,evaluate(segment['controls'],fraction)))
    return result
