"""Preflight the entire drawing before granting the existing motion owner IO."""
import copy
import time
import math
from . import drawing,kinematics as k
from .cartesian_planner import plan
from .reference_adapter import plan_cartesian


class DrawingMotion:
    def __init__(self,cartesian):
        self.cart=cartesian;self.report=None

    def invalidate(self):
        old=self.report;self.report=None
        if old and old.get('progressive'):old['progressive'].invalidate()

    def entry_failure(self,error,goal,document,start):
        """Retain the exact failing route, rather than just a seed-search error."""
        import json,os
        from pathlib import Path
        details=dict(stage='entry',error=str(error),goal=goal,start_angles_deg=start,
                     direction=document['direction'],point_count=len(document['points']))
        try:
            from .joint_motion import atomic_json
            directory=Path(os.environ.get('XDG_STATE_HOME') or str(Path.home()/'.local/state'))/'f3p-control'
            directory.mkdir(parents=True,exist_ok=True)
            path=directory/'last-planning-failure.json'
            atomic_json(path,dict(details=details,document=document))
            details['diagnostic_file']=str(path)
        except OSError as diagnostic_error:details['diagnostic_error']=str(diagnostic_error)
        print('DRAWING_ENTRY_FAILED',json.dumps(details,ensure_ascii=True),flush=True)
        reason=str(error)
        if reason.startswith('no limit-valid IK solution found'):
            reason='有限次数逆解搜索未找到满足限位的姿态；尚不能据此判定目标不可达'
        xyz=goal['position_mm']
        result=ValueError('绘图入口规划失败（X %.2f / Y %.2f / Z %.2f mm，朝向 %s）：%s。请核对线路入口坐标；修改目标框不会自动平移已载入的整条线路。'%
                          (*xyz,document['direction'],reason))
        for name in ('failure_kind','path_fraction','joint_step_degrees'):
            if hasattr(error,name):setattr(result,name,getattr(error,name))
        return result

    def plan_segment(self,start,segment,rotation,document,hardware,depth=0,origin=None):
        c=self.cart;t=c.task
        origin=k.forward(start)['position_mm'] if origin is None else origin
        hardware=dict(hardware,drawing_expected_origin_mm=origin)
        goal=dict(position_mm=segment['goal'],rotation=rotation)
        if not document['allow_orientation_adjustment']:c.check_workspace(goal)
        try:
            if segment['mode']=='D':
                r=plan_cartesian(start,goal,c.bounds(),'D',segment['via'],document['speed'],document['joint_speed'],t._check,hardware)
            else:
                r=plan(start,goal,c.bounds(),mode=segment['mode'],via=segment.get('via'),orientation='hold',
                       speed=document['speed'],joint_speed=(min(20.,document['joint_speed']) if segment['mode']=='J' else document['joint_speed']),check=t._check,hardware=hardware)
            return [r]
        except ValueError as error:
            step=getattr(error,'joint_step_degrees',0);u=getattr(error,'path_fraction',None)
            if document['allow_orientation_adjustment'] and not hardware.get('drawing_adaptive_orientation') and (step>10 or getattr(error,'failure_kind',None) in ('ik_nonconvergence','interpolation_error','joint_limit')):
                print('DRAWING_ORIENTATION_FALLBACK',dict(reason=str(error)),flush=True)
                return self.plan_segment(start,segment,rotation,document,dict(hardware,drawing_adaptive_orientation=True),depth+1,origin)
            if getattr(error,'failure_kind',None)=='interpolation_error' and depth<12 and self.split_count<128:
                from .fast_trajectory import _path_geometry
                point,length,_=_path_geometry(origin,segment['goal'],{'L':'line','C':'arc','D':'polyline'}[segment['mode']],segment.get('via'))
                if length>.5:
                    split=.5
                    if segment['mode']=='D':
                        distance=0.;previous=origin;fractions=[]
                        for vertex in segment['via']:
                            distance+=math.dist(previous,vertex);previous=vertex
                            if .001<distance/length<.999:fractions.append(distance/length)
                        if fractions:split=min(fractions,key=lambda value:abs(value-.5))
                    self.split_count+=1
                    prefix,_,_=drawing.segment_interval(segment,origin,0.,split)
                    suffix,_,_=drawing.segment_interval(segment,origin,split,1.)
                    before=self.plan_segment(start,prefix,rotation,document,hardware,depth+1,origin)
                    after=self.plan_segment(before[-1]['target_angles_deg'],suffix,rotation,document,hardware,depth+1,point(split))
                    print('DRAWING_ERROR_SPLIT',dict(fraction=split,reason=str(error)),flush=True)
                    return before+after
            if segment['mode']=='J' or step<=10 or u is None or not math.isfinite(u) or not 0<u<=1:raise
            if depth>=6 or self.transition_count>=8:raise ValueError('停车关节过渡超过8处或连续接续失败，请分开线路') from error
            from .fast_trajectory import _path_geometry
            point,length,_=_path_geometry(origin,segment['goal'],{'L':'line','C':'arc','D':'polyline'}[segment['mode']],segment.get('via'))
            # Stop one millimetre before the discontinuity; reconnect one
            # millimetre beyond it. The intervening MoveJ is visibly off-path.
            lo=max(0.,u-1./length);hi=min(1.,u+1./length)
            reports=[];before=start
            if lo*length>.01:
                prefix,_,_=drawing.segment_interval(segment,origin,0.,lo)
                reports=self.plan_segment(start,prefix,rotation,document,hardware,depth+1,origin)
                before=reports[-1]['target_angles_deg']
            t._check();t.phase='绘图规划：停车关节过渡'
            exit_goal=dict(position_mm=point(hi),rotation=rotation);c.check_workspace(exit_goal)
            bridge=plan(before,exit_goal,c.bounds(),mode='J',orientation='interpolate',joint_speed=min(20.,document['joint_speed']),check=t._check)
            if hardware.get('drawing_position_tolerance_mm') is not None:
                # The new 1 mm request excludes the old unbounded off-line J bridge.
                # Refuse it rather than claim a sparse MoveJ preview bounds its sweep.
                raise ValueError('该关节分支需要偏离线路的J过渡，尚不能证明满足1mm路径误差，请调整朝向或线路') from error
            bridge['drawing_transition']=dict(reason=str(error),joint_step_degrees=step,bypassed_length_mm=(hi-lo)*length)
            self.transition_count+=1
            print('DRAWING_STOP_J_TRANSITION',bridge['drawing_transition'],flush=True)
            reports.append(bridge)
            if (1-hi)*length>.01:
                suffix,_,_=drawing.segment_interval(segment,origin,hi,1.)
                reports+=self.plan_segment(bridge['target_angles_deg'],suffix,rotation,document,hardware,depth+1)
            return reports

    def operate(self,operation,params):
        c=self.cart;t=c.task;began=time.monotonic()
        if operation=='cart_drawing_prepare':
            from .planner_process import prewarm
            prewarm()
        document,segments=drawing.segments(params['document'])
        if operation=='cart_drawing_prepare':
            from .progressive_drawing import ProgressiveDrawing
            self.invalidate();c.prepared.invalidate();check=t._check
            t.phase='绘图准备：入口与首段';actual,reference=c.read_start();check()
            print('DRAWING_PREPARE_PHASE',dict(phase='read_start',seconds=time.monotonic()-began),flush=True)
            start=c.to_model(actual);context=c.continuous._context()
            goal=dict(position_mm=document['points'][0]['xyz'],
                rotation=drawing.rotation(document['direction'],k.forward(start)['rotation']))
            try:
                c.check_workspace(goal)
                from .drawing_branches import select_entry
                selected=None
                if not document['allow_orientation_adjustment']:
                    selected=select_entry(start,goal,c.bounds(),segments,check,budget=.35,reject_dead_end=True)
                entry=plan(start,goal,c.bounds(),mode='J',orientation='interpolate',joint_speed=min(20.,document['joint_speed']),check=check,joint_target=selected)
            except ValueError as error:
                check()
                if not document['allow_orientation_adjustment']:raise self.entry_failure(error,goal,document,start) from error
                from .reference_adapter import make_model
                from .position_inverse import solve_position
                model=make_model(start,c.bounds())
                q=solve_position(model,goal['position_mm'],start,model.joint_limits_deg,check,tolerance=.01)
                entry=plan(start,k.forward(q),c.bounds(),mode='J',orientation='interpolate',joint_speed=min(20.,document['joint_speed']),check=check)
                entry['orientation_adjusted']=True
            print('DRAWING_PREPARE_PHASE',dict(phase='entry',seconds=time.monotonic()-began),flush=True)
            helper=ProgressiveDrawing(self,document,segments)
            report=helper.prepare(start,entry,context,reference,
                [t.controller.nodes[n].motor_angle for n in range(1,7)])
            if context!=c.continuous._context() or not c.ready():helper.close();raise RuntimeError('规划期间现场参考改变')
            self.report=report
            elapsed=time.monotonic()-began
            report.update(preparation_seconds=elapsed,preparation_target_seconds=1.5,preparation_target_met=elapsed<=1.5)
            print('DRAWING_PREPARED',dict(seconds=elapsed,segments=len(segments),first_ready=True),flush=True)
            t.message='入口和首段及制动段已核验，可执行；其余线路后台核验，紫色表示自动朝向，模型位置预算1mm。准备%.2f秒'%elapsed
            return
        if operation=='cart_drawing_plan':
            self.transition_count=0
            self.split_count=0
            began=time.monotonic();t.phase='绘图规划：读取起点'
            self.invalidate();c.prepared.invalidate();actual,reference=c.read_start()
            start=c.to_model(actual);context=c.continuous._context()
            rotation=drawing.rotation(document['direction'],k.forward(start)['rotation'])
            goal=dict(position_mm=document['points'][0]['xyz'],rotation=rotation)
            t.phase='绘图规划：入口逆解';entry_began=time.monotonic()
            try:
                c.check_workspace(goal)
                entry=plan(start,goal,c.bounds(),mode='J',orientation='interpolate',joint_speed=min(20.,document['joint_speed']),check=t._check)
            except ValueError as error:
                if not document['allow_orientation_adjustment']:raise self.entry_failure(error,goal,document,start) from error
                from .reference_adapter import make_model
                from .position_inverse import solve_position
                model=make_model(start,c.bounds())
                q=solve_position(model,goal['position_mm'],start,model.joint_limits_deg,t._check,tolerance=.25)
                adaptive_goal=k.forward(q)
                entry=plan(start,adaptive_goal,c.bounds(),mode='J',orientation='interpolate',joint_speed=min(20.,document['joint_speed']),check=t._check)
                entry['orientation_adjusted']=True
            print('DRAWING_PLAN_ENTRY',dict(seconds=round(time.monotonic()-entry_began,3)),flush=True)
            start=entry['target_angles_deg'];reports=[entry]
            frames=0
            hardware=c.drawing_hardware(document['joint_speed'],document['trajectory_acceleration'])
            hardware['allow_stop_joint_transition']=True
            hardware['drawing_position_tolerance_mm']=1.
            origin=document['points'][0]['xyz']
            for i,s in enumerate(segments):
                t._check();t.phase='绘图规划 %d/%d'%(i+1,len(segments))
                segment_began=time.monotonic()
                planned=self.plan_segment(start,s,rotation,document,hardware,origin=origin)
                native=planned[-1].get('native_report',{})
                print('DRAWING_PLAN_SEGMENT',dict(index=i+1,mode=s['mode'],seconds=round(time.monotonic()-segment_began,3),frames=len(native.get('frames',[])),duration_s=native.get('duration_s'),acceleration=hardware['acceleration']),flush=True)
                frames+=sum(len(r.get('native_report',{}).get('frames',[])) for r in planned)
                if frames>200000:raise ValueError('整条线路超过20万执行帧，请分开保存执行')
                reports.extend(planned);start=planned[-1]['target_angles_deg']
                origin=s['goal']
            if context!=c.continuous._context() or not c.ready():raise RuntimeError('规划期间参考改变，请重新规划')
            self.report=dict(document=copy.deepcopy(document),context=context,reference=reference,
                entry_motor=[t.controller.nodes[n].motor_angle for n in range(1,7)],segments=reports)
            elapsed=time.monotonic()-began
            print('DRAWING_PLAN_COMPLETE',dict(seconds=round(elapsed,3),segments=len(segments),frames=frames),flush=True)
            adjusted=sum(bool(r.get('orientation_adjusted')) for r in reports)
            t.message='整条绘图规划完成：入口J定位 + %d段，自动拆分%d次，%d段调整朝向，模型路径误差上限1mm，耗时%.1f秒；实物精度及碰撞尚未验证'%(len(reports)-1,self.split_count,adjusted,elapsed)
            return
        if operation!='cart_drawing_execute':raise ValueError('未知绘图操作')
        if params.get('clearance_confirmed') is not True:raise RuntimeError('请先确认运动区域安全')
        r=self.report
        if not r or r['document']!=document or r['context']!=c.continuous._context() or not c.ready():
            raise RuntimeError('线路或现场参数改变，请先重新规划整条线路')
        if r.get('progressive'):return r['progressive'].execute()
        # Fail capability checks before the first entry MoveJ.
        for s in r['segments'][1:]:
            if s['mode'] in ('L','C'):
                if not s.get('native_report'):raise RuntimeError('该段没有可执行轨迹')
                reasons=c.continuous._trajectory_reasons('line' if s['mode']=='L' else 'arc',
                    None if document['trajectory_acceleration'] is None else [document['trajectory_acceleration']]*6)
                if reasons:raise RuntimeError('；'.join(reasons))
        c.read_start()
        if any(abs(t.controller.nodes[n].motor_angle-r['entry_motor'][n-1])>
               max(.25,360/t.pulses_per_rev[n]+360/65536) for n in range(1,7)):
            raise RuntimeError('机械臂已离开绘图预览起点，请重新规划')
        self.report=None # never reuse an executed or partially failed drawing
        t.total_points=len(r['segments'])
        try:
            for i,s in enumerate(r['segments']):
                t._check();t.current_point=i+1;t.phase='绘图执行 %d/%d'%(i+1,len(r['segments']))
                if r['context']!=c.continuous._context():raise RuntimeError('绘图执行期间现场参数改变')
                if s['mode']=='J':
                    actual,_=c.read_start()
                    from .collision import check_joint_box
                    check_joint_box(c.to_model(actual),s['target_angles_deg'],t._check)
                    t._move(dict(enumerate(c.to_controller(s['target_angles_deg']),1)),min(20.,document['joint_speed']),r['reference'],acceleration=document['trajectory_acceleration'])
                else:
                    # Only the internally owned MoveJ-to-curve transition gets
                    # its verified arrival envelope; standalone previews stay strict.
                    s['drawing_handoff']=i>0 and r['segments'][i-1]['mode']=='J'
                    s['drawing_acceleration']=None if document['trajectory_acceleration'] is None else [document['trajectory_acceleration']]*6
                    c.continuous.bind_preview(s,r['context'])
                    c.continuous.execute(s,dict(mode=s['mode'],clearance_confirmed=True,speed=document['speed'],joint_speed=document['joint_speed']))
            t.message='绘制线路执行完成'
        finally:t.current_point=0;t.total_points=0
