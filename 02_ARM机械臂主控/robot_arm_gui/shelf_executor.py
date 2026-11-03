"""Drive to each selected shelf, then run the existing full grasp batch."""
import copy
import json
import math
from pathlib import Path
import threading
import time

from . import grasp_motion
from .six_item_catalog import PICK_ITEMS, PICK_LABELS
from .zero_home import RATIOS,MOTOR_ZERO_TOLERANCE
from .shelf.shelf_mission import RETURN_EXTRA_MM
from .shelf.cargo_routes import validate_config
from .shelf.shelf_transport import ShelfLease


def validate_shelf_items(shelves):
    """Normalize old three-color drafts into six-item quotas without losing counts."""
    if not isinstance(shelves, list) or len(shelves) != 3:
        raise ValueError('必须配置 3 个货架')
    clean = []
    legacy_keys = {'red', 'yellow', 'green'}
    for row in shelves:
        if not isinstance(row, dict) or set(row) not in (legacy_keys, set(PICK_ITEMS)):
            raise ValueError('每个货架需要六种物品数量，或完整的旧红黄绿数量')
        normalized = {item: row.get(item, 0) for item in PICK_ITEMS}
        for item, count in normalized.items():
            if type(count) is not int or not 0 <= count <= 20:
                raise ValueError('%s数量须为 0 到 20 的整数' % PICK_LABELS[item])
        clean.append(normalized)
    if not any(sum(row.values()) for row in clean):
        raise ValueError('至少选择一个物品')
    return clean


def execute(task,params):
    from .backend import MemoryMappedBackend
    if not isinstance(task.controller.backend,MemoryMappedBackend):
        raise RuntimeError('货架任务只在板端运行，不会自动以仿真替代实物')
    return run_sequence(task,params)


def run_sequence(task,params,lease_factory=ShelfLease,clock=time.monotonic,sleep=time.sleep,
                 grasp=grasp_motion.execute):
    # One snapshot for every shelf, even if the caller later edits its draft.
    from .grasp_preview import checked_pick_offset
    params=dict(params,pick_offset_mm=checked_pick_offset(params.get('pick_offset_mm')))
    shelves=validate_shelf_items(params['shelves'])
    if params.get('clearance_confirmed') is not True or params.get('use_gripper') is not True:
        raise RuntimeError('货架任务须确认运动区域安全并开启自动夹爪')
    touch_start = params.get('touch_start_enabled') is True
    if not touch_start and params.get('physical_key_start_confirmed') is not True:
        raise RuntimeError('请确认断开电脑数据连接后，仅在板上按KEY2启动')
    session=params['session']
    if not session.running or getattr(session,'stopping',False):
        raise RuntimeError('请先开启AI识别，识别正在结束时不能准备货架任务')
    session_id=session.session_id
    control=params['control'];cart=task.cartesian;cart.require()
    if not task.controller.backend.supports_continuous_trajectory:
        raise RuntimeError('当前固件缺少连续轨迹功能')
    config=validate_config(json.loads((Path(__file__).parent/'shelf/program2.json').read_text(encoding='utf-8')))
    reference=copy.deepcopy(task._reference(range(1,7)))
    requested={c:sum(row[c] for row in shelves) for c in PICK_ITEMS}
    completed={c:0 for c in PICK_ITEMS};remaining=copy.deepcopy(shelves)
    # Each drive command ends with a full stop. Combine outbound legs across
    # empty shelves so that only shelves with requested items become stops.
    visits=[];distance=0
    for station,row in enumerate(shelves):
        distance+=config['travel'][2*station]['forward_mm']
        if sum(row.values()):
            visits.append((station,distance))
            distance=0
    publish=params.get('progress',lambda e:None)
    lease=None;success=False;in_grasp=False;started=None;return_mm=None;sequence=0;events=[]
    old_guard=getattr(task,'_shelf_guard',None)
    planning_scope=threading.local()

    def guard():
        if not session.running or getattr(session,'stopping',False) or session.session_id!=session_id:
            raise RuntimeError('识别会话已停止或变化，货架任务取消')
        if control.stopped.is_set() or control.paused.is_set():
            raise RuntimeError('货架任务已停止；不支持暂停续跑')
        if (not getattr(planning_scope,'math_only',False) and
                (task._reference(range(1,7))!=reference or not cart.ready())):
            raise RuntimeError('机械臂零点或标定改变')
        if started is not None and clock()-started>config['mission_timeout_s']:
            raise RuntimeError('货架任务超过总时限')
        if lease is not None and lease.prepared:
            state=lease.check()
            if in_grasp and (not state['shelf_arm_lock'] or state['phase']!='DONE' or state['motor_active']):
                raise RuntimeError('取放期间车轮互锁失效')
        if old_guard is not None:old_guard()

    def planning_check():
        """Skip only duplicate context building within this math callback.

        The original task checker still checks cancellation and jog ownership;
        this guard still checks session, owner freshness and wheel interlock.
        All ordinary callbacks, including other threads, retain the full guard.
        The grasp planner separately calls its full check at least every 20 ms
        and again before any gripper or arm command.
        """
        previous=getattr(planning_scope,'math_only',False)
        planning_scope.math_only=True
        try:
            task._check()
        finally:
            planning_scope.math_only=previous

    guard.planning_check=planning_check

    def event(label):
        publish(dict(completed=dict(completed),requested=requested,label=label,mission_stage='shelf',
                     shelves_remaining=copy.deepcopy(remaining),return_mm=return_mm,start_ready=control.start_ready))

    def stowed():
        task._check();actual,current=cart.read_start()
        if current!=reference:raise RuntimeError('读取期间机械臂参考改变')
        if any(abs(actual[n-1])*RATIOS[n]>MOTOR_ZERO_TOLERANCE for n in range(1,7)):
            raise RuntimeError('小车行驶前机械臂必须先回0收回')

    def stopped(state):
        return state['phase']=='DONE' and state['quiet_ms']>=250 and not state['motor_active']

    def action(kind,**values):
        nonlocal sequence
        sequence+=1
        return dict(id=sequence,kind=kind,**values)

    def wait_drive(command):
        nonlocal started
        physical_deadline=clock()+600
        last_ready = None
        while True:
            task._check();state=lease.check()
            if not state['shelf_started']:
                if touch_start:
                    ready = (state['phase']=='READY' and state['quiet_ms']>=250 and state['imu_ready']
                             and state['arm_idle'] and not state['motor_active'] and not state['gripper_active'])
                    control.set_start_ready(ready)
                    if control.start_ready != last_ready:
                        last_ready = control.start_ready
                        event('任务已准备：请点击启动任务' if last_ready else '等待车轮停稳及启动条件就绪')
                    if control.take_start_request():
                        guard();stowed();guard()
                        state = lease.start()
                        control.disarm_start()
                        event('启动请求已处理，等待本次任务行驶回执')
                if clock()>=physical_deadline:raise RuntimeError('等待启动超时，请重新准备任务')
            else:
                control.disarm_start()
                if started is None:started=clock()
                if state['shelf_command_id']!=command['id']:
                    raise RuntimeError('行驶回执不属于当前分段')
                if stopped(state):
                    events.append(dict(command=command,odo_mm_lr=list(state['odo_mm_lr'])))
                    return state
            sleep(.02)

    def move(command):
        stowed()
        if not stopped(lease.check()):raise RuntimeError('下一段开始前车轮未停稳')
        lease.move(command)
        return wait_drive(command)

    try:
        task._shelf_guard=guard;stowed()
        # Neither preparing nor driving reads camera frames or checks frame age.
        lease=lease_factory(task.cancel)
        if touch_start and not getattr(lease,'touch_supported',False):
            raise RuntimeError('板端控制服务尚未升级触屏启动/复位，请先安装匹配服务')
        command=action('drive',distance_mm=visits[0][1])
        lease.prepare(command)
        event('任务已准备：直达货架%d；点击启动任务开始，停止按钮或KEY4停止'%(visits[0][0]+1))
        wait_drive(command)
        for visit_index,(station,distance) in enumerate(visits):
            if visit_index:
                event('前往货架%d'%(station+1))
                move(action('drive',distance_mm=distance))
            batch=dict(shelves[station])
            event('已到货架%d，停稳后按原全自动夹取流程取货'%(station+1))
            until=clock()+config['station_wait_s']
            while clock()<until:
                task._check()
                if not stopped(lease.check()):raise RuntimeError('货架停留期间车轮未停稳')
                sleep(.02)
            stowed();lease.arm_lock(True);in_grasp=True
            receipt=[False];base=dict(completed)
            def progress(e):
                counts=e.get('completed')
                if counts is not None:
                    # Old cube-only executors omit fruit zeros. Preserve that
                    # receipt shape without ever treating a fruit as completed.
                    if isinstance(counts,dict) and set(counts)=={'red','yellow','green'}:
                        counts={item:counts.get(item,0) for item in PICK_ITEMS}
                    if (not isinstance(counts,dict) or set(counts)!=set(PICK_ITEMS) or
                            any(type(counts[c]) is not int or not 0<=counts[c]<=batch[c] for c in PICK_ITEMS)):
                        raise RuntimeError('原夹取数量回执无效')
                    for c in PICK_ITEMS:completed[c]=base[c]+counts[c]
                if e.get('state')=='complete':receipt[0]=counts==batch
                event('货架%d：%s'%(station+1,e.get('label','取放中')))
            # Pass the ORIGINAL session and complete item quantities unchanged.
            # Original execute owns recognition, target refresh, preflight, grasp,
            # consumed-target tracking, placement and final return to zero.
            grasp(task,dict(params,requested=batch,progress=progress,clock=clock))
            task._check()
            if not receipt[0]:raise RuntimeError('缺少取放数量及回0完成回执')
            stowed();in_grasp=False;lease.arm_lock(False)
            remaining[station]={c:0 for c in PICK_ITEMS}
            events.append(dict(station=station+1,completed=dict(batch)))
        state=lease.check()
        if not stopped(state):raise RuntimeError('返回前车轮未停稳')
        # The C owner resets cumulative signed odometry at prepare, and includes
        # stopping coast. Freeze it before turning, never after a return leg.
        outbound=state['odo_mm_lr']
        if (len(outbound)!=2 or any(not math.isfinite(v) or v<0 for v in outbound)
                or abs(outbound[0]-outbound[1])>30 or sum(outbound)<=0):
            raise RuntimeError('累计前进里程无效，不能计算返回距离')
        return_mm=sum(outbound)/2+RETURN_EXTRA_MM
        event('取货完成，按实际前进距离加30cm返回')
        for kind,values in [('turn',dict(left_deg=-180)),('drive',dict(distance_mm=return_mm)),
                            ('turn',dict(left_deg=45)),('drive',dict(distance_mm=500)),
                            ('turn',dict(left_deg=-45))]:
            move(action(kind,**values))
        lease.finish();success=True
        event('货架取放和返回命令全部完成；实物夹取结果请核对')
        return dict(remaining=remaining,return_mm=return_mm,events=events)
    finally:
        control.disarm_start()
        task._shelf_guard=old_guard
        if lease is not None:lease.close(success=success)
