"""Hold-to-run Cartesian motion through the existing checked FIFO executor."""
import math
import threading
import time
from . import kinematics as k


class HoldLease:
    """A lost GTK heartbeat cannot leave a held command running indefinitely."""
    def __init__(self, clock=time.monotonic):
        self.clock=clock;self.lock=threading.Lock();self.deadline=clock()+.3
        self.released=False;self.pulses=0

    def pulse(self):
        with self.lock:
            if self.released or self.clock()>self.deadline:
                print('CART_JOG_HEARTBEAT_REJECTED',dict(released=self.released,pulses=self.pulses,overdue_seconds=self.clock()-self.deadline),flush=True)
                self.released=True;return False
            self.deadline=self.clock()+.3
            self.pulses+=1
            return True

    def release(self):
        with self.lock:self.released=True

    def check(self):
        with self.lock:
            if self.released or self.clock()>self.deadline:
                print('CART_JOG_LEASE_STOP',dict(released=self.released,pulses=self.pulses,overdue_seconds=self.clock()-self.deadline),flush=True)
                self.released=True
                raise RuntimeError('末端点动已松开或控制心跳中断')


def plane_direction(plane, flip, direction):
    axes={'xy':(0,1),'xz':(0,2),'yz':(1,2)}
    if plane not in axes or direction not in ('up','down','left','right'):
        raise ValueError('点动方向或绘图平面无效')
    i,j=axes[plane]
    return (i,-1 if direction=='left' else 1) if direction in ('left','right') else (j,(-1 if flip else 1)*(1 if direction=='up' else -1))


def stream_attempts(position,axis,sign,speed,adaptive):
    """A bounded ray, not repeated stop-to-stop steps.

    The endpoint is only a geometric horizon: the local producer must validate
    every published block and its braking reserve before the transport sees it.
    Short horizons are startup fallbacks near a boundary, never auto-restarted.
    """
    horizon=999.
    if axis==2 and sign<0:horizon=min(horizon,position[2]-.1)
    if horizon<=.01:raise ValueError('此方向已接近Z安全边界')
    distances=(horizon,100.,20.,5.,1.,.2,.05) if adaptive else (horizon,)
    seen=set()
    for distance in distances:
        distance=min(distance,horizon)
        if distance in seen or distance<=.01:continue
        seen.add(distance)
        # Smaller fallback horizons terminate smoothly; they are not followed
        # by another automatic acceleration cycle while the key stays held.
        feed=min(speed,5. if distance<=1. else speed)
        if distance<=.2:feed=min(feed,1.)
        if distance<=.05:feed=min(feed,.2)
        yield distance,feed


def preparation_key(cartesian,params):
    import copy
    bounds=cartesian.bounds()
    return copy.deepcopy(dict(context=cartesian.continuous._context(),
        bounds=dict(bounds),rule=getattr(bounds,'rule',None),speed=params['speed'],
        hardware=cartesian.planning_hardware(params.get('joint_speed',5),params.get('trajectory_acceleration'))))


def prepare_idle(cartesian,params,directions):
    """Use existing cached feedback, never query or command the hardware."""
    import copy
    from .zero_home import RATIOS
    from .reference_adapter import plan_jog_cartesian
    from .collision import check_target
    task=cartesian.task;controller=task.controller
    if task.busy or controller._moving or not cartesian.ready():return
    motor=[controller.nodes[n].motor_angle for n in range(1,7)]
    if any(v is None or not math.isfinite(v) for v in motor):return
    key=preparation_key(cartesian,params)
    start=cartesian.to_model([v/RATIOS[n] for n,v in enumerate(motor,1)])
    pose=k.forward(start);bounds=copy.deepcopy(cartesian.bounds())
    hardware=copy.deepcopy(key['hardware'])
    hardware.update(drawing_adaptive_orientation=False,drawing_orientation_released=False,
        drawing_position_tolerance_mm=.1,prefer_short_lookahead=True)
    def build(direction,cancel):
        def check():
            if cancel.is_set():raise RuntimeError('点动后台准备已取消')
        axis,sign=direction
        distance,feed=next(stream_attempts(pose['position_mm'],axis,sign,params['speed'],False))
        goal=copy.deepcopy(pose);goal['position_mm'][axis]+=sign*distance
        check_target(goal['position_mm'])
        report=plan_jog_cartesian(start,goal,bounds,feed,params.get('joint_speed',5),check,hardware)
        report['jog_preparation']=dict(distance=distance,feed=feed)
        return report
    cartesian.jog_prepared.ensure(key,motor,tuple(directions),build)


def run(cartesian, params):
    lease=params.get('lease')
    if not isinstance(lease,HoldLease):raise ValueError('点动需要有效的按键保持状态')
    axis=params.get('axis');sign=params.get('sign');speed=params.get('speed')
    if type(axis) is not int or axis not in (0,1,2) or type(sign) is not int or sign not in (-1,1):
        raise ValueError('点动坐标轴无效')
    if type(speed) not in (int,float) or not math.isfinite(speed) or not 0<speed<=100:
        raise ValueError('点动末端速度须在0～100 mm/s之间')
    if params.get('clearance_confirmed') is not True:raise RuntimeError('请先确认运动区域安全')
    if params.get('allow_orientation_adjustment') is True:
        raise ValueError('方向点动必须保持末端朝向，已禁止自动调整朝向')
    cartesian.jog_lease=lease
    try:
        from .reference_adapter import plan_jog_cartesian
        from .collision import check_target
        reasons=cartesian.continuous._trajectory_reasons('line')
        if reasons:raise RuntimeError('；'.join(reasons))
        # Exactly one executor ownership per press. The producer carries its
        # C2 timing state across blocks instead of stopping between short runs.
        cartesian.task._check()
        task=cartesian.task;began=time.monotonic()
        task.phase='点动准备';task.message='正在读取六轴起点；请保持按住，松开可取消'
        task.controller._publish()
        actual,reference=cartesian.read_start();start=cartesian.to_model(actual)
        pose=k.forward(start)
        # A remote geometric horizon does not authorize unchecked motion.
        # Rolling blocks and their independent stop reserves are checked.
        goal=dict(position_mm=list(pose['position_mm']),rotation=pose['rotation'])
        adaptive=False
        request={key:value for key,value in params.items() if key not in ('lease','axis','sign')}
        request.update(goal=goal,mode='L',orientation='hold')
        cartesian.preview=None
        context=cartesian.continuous._context()
        hardware=cartesian.planning_hardware(params.get('joint_speed',5),params.get('trajectory_acceleration'))
        hardware['drawing_adaptive_orientation']=adaptive
        hardware['drawing_orientation_released']=hardware['drawing_adaptive_orientation']
        hardware['drawing_position_tolerance_mm']=.1
        hardware['prefer_short_lookahead']=True
        key=preparation_key(cartesian,params)
        # Fresh six-axis feedback above remains mandatory even on a cache hit.
        motor=[task.controller.nodes[n].motor_angle for n in range(1,7)]
        cache=getattr(cartesian,'jog_prepared',None)
        report=cache.take(key,motor,(axis,sign)) if cache else None
        cached=report is not None
        if cached:
            prepared=report['jog_preparation'];distance=prepared['distance'];feed=prepared['feed']
            goal['position_mm'][axis]+=sign*distance
        read_seconds=time.monotonic()-began
        task.phase='点动规划';task.message='正在核验起步与制动段；请保持按住，松开可取消'
        task.controller._publish()
        # The rolling solver validates IK, bounds, quantization and braking.
        # Avoid the general endpoint search, duplicate six-axis start read,
        # and implicit full-path/prealignment fallback of target positioning.
        attempts=stream_attempts(pose['position_mm'],axis,sign,speed,adaptive)
        failure=''
        for distance,feed in (() if cached else attempts):
            task._check()
            goal['position_mm']=list(pose['position_mm'])
            goal['position_mm'][axis]+=sign*distance
            task.message='核验连续点动起步；允许调整朝向，受限时降速' if adaptive else '核验连续点动起步与制动段'
            task.controller._publish()
            try:
                check_target(goal['position_mm'])
                report=plan_jog_cartesian(start,goal,cartesian.bounds(),feed,
                    params.get('joint_speed',5),task._check,hardware)
                break
            except ValueError as exc:failure=str(exc)
        if report is None:raise ValueError('此方向无法在保持末端朝向时安全起步（可能受奇异姿态、边界或关节约束限制）：'+failure)
        try:
            task._check()
            if context!=cartesian.continuous._context() or reference!=task._reference(range(1,7)):
                raise RuntimeError('点动准备期间零点、标定或参数改变')
            report['reference']=reference
            cartesian.continuous.bind_preview(report,context)
            print('CART_JOG_READY',dict(read_seconds=read_seconds,
                prepared_cache_hit=cached,
                distance_mm=distance,requested_feed_mm_s=speed,planning_feed_mm_s=feed,adaptive_orientation=adaptive,
                preparation_seconds=time.monotonic()-began,
                planning_seconds=report['native_report'].get('initial_planning_seconds')),flush=True)
            task.phase='点动执行';task.message='起步核验通过，正在核对现场反馈并启动；松开停止'
            task.controller._publish()
            cartesian.continuous.execute(report,request)
            task.message='方向点动已到达本次可行终点；重新按下才会再次起步'
            task.controller._publish()
        finally:report['native_report']['frames'].close()
    finally:
        lease.release();cartesian.jog_lease=None
