"""Reference-bound kinematics on JointMotion's existing worker/CAN owner."""
import copy
import json
from . import kinematics as k
from .cartesian_planner import plan
from .joint_motion import atomic_json
from .zero_home import RATIOS
from .coupled_limits import one_based


class CartesianMotion:
    def __init__(self, task):
        self.task=task
        self.path=task.path.with_name('kinematics.json')
        self.calibration=None
        self.error=''
        self.solution=None
        self.preview=None
        from .workspace import Workspace
        self.workspace=Workspace()
        self.workspace_note=''
        from .trajectory_preparation import PreparationCache
        self.prepared=PreparationCache()
        from .jog_preparation import JogPreparation
        self.jog_prepared=JogPreparation()
        from .planner_process import prewarm
        prewarm()
        from .continuous_motion import ContinuousMotion
        self.continuous=ContinuousMotion(self)
        try:
            if self.path.exists():
                data=json.loads(self.path.read_text(encoding='utf-8'))
                self.validate_calibration(data);self.calibration=data
        except Exception as exc:self.error='运动学参数未加载：'+str(exc)

    @staticmethod
    def validate_calibration(data):
        if data.get('schema_version')!=1 or data.get('geometry_version')!=k.GEOMETRY_VERSION or data.get('operator_confirmed') is not True:
            raise ValueError('运动学标定版本或确认信息无效')
        k.finite_vector(data['offsets_deg'],6)
        if not isinstance(data['signs'],list) or len(data['signs'])!=6 or any(type(x) is not int or x not in (-1,1) for x in data['signs']):
            raise ValueError('六轴正方向必须为+1或-1')
        if not isinstance(data.get('reference'),dict):raise ValueError('缺少关节零点参考')

    def ready(self):
        try:
            if self.calibration is None:return False
            self.validate_calibration(self.calibration)
            return self.calibration['reference']==self.task._reference(range(1,7))
        except Exception:return False

    def require(self):
        if not self.ready():raise RuntimeError('请先核对CAD参考姿态、六轴正方向并完成当前零点的运动学标定')
        if any(n not in self.task.pulses_per_rev for n in range(1,7)):
            raise RuntimeError('运动学需要六轴定位当量，包括J6')

    def fixed_reference_candidate(self):
        data=self.calibration
        if not data or data.get('configuration_locked') is not True:
            raise ValueError('尚无已锁定的机械臂标定')
        self.validate_calibration(data)
        current=self.task._reference(range(1,7))
        for key in ('backend','ratios','bounds','pulses_per_rev'):
            if current[key]!=data['reference'].get(key):
                raise ValueError('定位当量、减速比或限位已变化，请先核对原配置')
        return current

    def readiness_notice(self):
        if self.ready():return ''
        try:
            self.fixed_reference_candidate()
            return '零点会话已变化；确认当前六轴零位是原标定姿态后，沿用固定标定'
        except (ValueError,RuntimeError) as exc:return str(exc)

    def confirm_fixed_reference(self,params):
        if params.get('confirmed') is not True:
            raise ValueError('请确认当前六轴零位对应原标定机械姿态')
        reference=self.fixed_reference_candidate()
        actual=self.task._capture()
        if any(abs(actual[str(n)])>.05 for n in range(1,7)):
            raise ValueError('当前六轴未在零位，请先回到已确认的标定零姿态')
        if reference!=self.fixed_reference_candidate():
            raise RuntimeError('核对期间零点参考发生变化，请重试')
        data=copy.deepcopy(self.calibration);data['reference']=reference
        atomic_json(self.path,data);self.calibration=data;self.error=''
        self.clear_preview();self.solution=None;self.prepared.invalidate()
        if hasattr(self,'drawing'):self.drawing.invalidate()
        self.continuous._plans.clear()
        self.task.message='已沿用固定标定并确认本次零点；方向、偏置和模型未改动'

    def check_cad_reference_configuration(self):
        """Check locked mapping without requiring an already-valid zero session."""
        data=self.calibration
        if not data or data.get('configuration_locked') is not True:
            raise ValueError('尚无已锁定的原 CAD 标定')
        self.validate_calibration(data)
        old=data['reference'];c=self.task.controller
        current=dict(backend=c.backend.name,ratios={str(n):RATIOS[n] for n in range(1,7)},
            bounds={str(n):list(c.joint_limits.bounds.get(n,())) for n in range(1,7)},
            pulses_per_rev={str(n):self.task.pulses_per_rev.get(n) for n in range(1,7)})
        if (c.joint_limits.error or any(n not in c.joint_limits.bounds for n in range(1,6))
                or self.task.config_error or any(v is None for v in current['pulses_per_rev'].values())):
            raise ValueError('限位或定位当量未确认')
        if any(current[key]!=old.get(key) for key in current):
            raise ValueError('定位当量、减速比或限位已变化，不能直接沿用原 CAD 标定')
        return True

    def clear_preview(self):
        from .trajectory_preparation import retire_report
        retire_report(self.preview)
        self.preview=None

    def to_model(self,angles):
        return [self.calibration['signs'][i]*v+self.calibration['offsets_deg'][i] for i,v in enumerate(angles)]

    def to_controller(self,angles):
        return [(v-self.calibration['offsets_deg'][i])*self.calibration['signs'][i] for i,v in enumerate(angles)]

    def bounds(self):
        return self.task.controller.joint_limits.planning_bounds(
            self.calibration['signs'], self.calibration['offsets_deg'])

    def check_workspace(self,goal):
        from .collision import check_target
        check_target(goal['position_mm'])
        from .workspace import endpoint_reachable
        state,key=('unavailable',None) if self.task.controller.joint_limits.coupled else self.workspace.classify(goal,self.task.controller.joint_limits.bounds,self.calibration)
        self.workspace_note={'sampled':'目标位于规整工作区；继续核验逆解与路径',
            'exact':'目标在规整边界外；使用精确可达性复核',
            'arbitrary':'任意末端朝向；使用精确逆解',
            'unavailable':'工作区参数未匹配；使用现有逆解与规划'}[state]
        if state=='exact' and endpoint_reachable(goal,self.bounds()) is False:
            raise ValueError('目标超出当前限位下的末端可达范围（工作区边缘已精确复核）')
        return state

    def read_start(self):
        self.require();reference=self.task._reference(range(1,7));values=[]
        for n in range(1,7):
            self.task._check();self.task._read(n,require_enabled=False,position_only=True)
            value=self.task.controller.nodes[n].motor_angle/RATIOS[n]
            if not self.task.feedback_within_bounds(n,value):raise RuntimeError('J'+str(n)+' 当前角度超过限位')
            b=self.task.effective_bounds(n)
            values.append(min(b[1],max(b[0],value)) if b else value)
        if reference!=self.task._reference(range(1,7)) or not self.ready():raise RuntimeError('读取期间零点或运动学标定改变')
        return values,reference

    def cached_pose(self):
        if not self.ready():return None
        values=[]
        for n in range(1,7):
            state=self.task.controller.nodes[n]
            if state.motor_angle is None or not state.zero_valid:return None
            values.append(state.motor_angle/RATIOS[n])
        return k.forward(self.to_model(values))

    def planning_hardware(self,joint_speed=None,acceleration=None):
        result=dict(calibration=copy.deepcopy(self.calibration),
            speed_caps_rpm=[int(self.task.controller.nodes[n].speed_rpm) for n in range(1,7)],
            acceleration=[int(self.task.controller.nodes[n].acceleration) for n in range(1,7)],
            pulses_per_rev=[self.task.pulses_per_rev[n] for n in range(1,7)])
        if joint_speed is not None:
            from .protocol import HOME_MAX_SPEEDS_RPM
            if type(joint_speed) not in (int,float) or not 0<joint_speed<=100:raise ValueError('关节速度上限须为0～100度/秒')
            limits=getattr(self.task.controller.backend,'trajectory_speed_limits',HOME_MAX_SPEEDS_RPM)
            result['speed_caps_rpm']=[min(limits[n],max(1,int(joint_speed*RATIOS[n]/6))) for n in range(1,7)]
        if acceleration is not None:
            if type(acceleration) is not int or not 1<=acceleration<=255:raise ValueError('轨迹ACC须为1～255整数')
            result['acceleration']=[acceleration]*6
        return result

    @staticmethod
    def transition_hardware(hardware,params):
        if params.get('allow_singularity_transition',False):
            value=float(params.get('singularity_deviation_mm',.1))
            if not __import__('math').isfinite(value) or not .1<=value<=1:raise ValueError('奇异区偏离须为0.1～1mm')
            if params.get('mode')!='L':raise ValueError('奇异区关节过渡目前仅支持直线')
            hardware.update(allow_singularity_transition=True,singularity_deviation_mm=value)
        return hardware

    def drawing_hardware(self,joint_speed,acceleration=None,allow_orientation_adjustment=False):
        """One motion envelope for drawing and Cartesian positioning."""
        hardware=self.planning_hardware(joint_speed,acceleration)
        hardware.update(prefer_short_lookahead=True,drawing_position_tolerance_mm=1.,
                        drawing_adaptive_orientation=bool(allow_orientation_adjustment))
        return hardware

    def positioning_hardware(self,params):
        if params.get('drawing_constraints'):
            return self.drawing_hardware(params.get('joint_speed',5),params.get('trajectory_acceleration'),
                                         params.get('allow_orientation_adjustment',False))
        return self.transition_hardware(self.planning_hardware(params.get('joint_speed',5),
                                       params.get('trajectory_acceleration')),params)

    @staticmethod
    def request_signature(params):
        mode=params.get('mode','L')
        return dict(mode=mode,position_mm=k.validate_pose(params['goal'])['position_mm'],
            via=params.get('via') if mode=='C' else None,speed=params.get('speed',10),
            orientation=params.get('orientation','hold'),required_direction=params.get('required_direction','hold'),joint_speed=params.get('joint_speed',5),
            trajectory_acceleration=params.get('trajectory_acceleration'),
            drawing_constraints=bool(params.get('drawing_constraints',False)),
            allow_orientation_adjustment=bool(params.get('allow_orientation_adjustment',False)),
            allow_singularity_transition=bool(params.get('allow_singularity_transition',False)),
            singularity_deviation_mm=params.get('singularity_deviation_mm',.1) if params.get('allow_singularity_transition') else None)

    @staticmethod
    def check_shared_direction(params,start):
        if params.get('drawing_constraints') and params.get('allow_orientation_adjustment'):return
        direction=params.get('required_direction','hold')
        if params.get('mode') not in ('L','C') or direction=='hold':return
        from .workspace import Workspace
        if direction not in Workspace.AXES:raise ValueError('所选末端朝向无效')
        import math
        rotation=k.forward(start)['rotation'];axis=[r[2] for r in rotation]
        if k.dot(axis,Workspace.AXES[direction])<math.cos(math.radians(.12)):
            raise ValueError('直线/圆弧保持起点朝向；当前与左上所选朝向不一致，请先用J定位调整朝向')

    def operate(self,operation,params):
        if operation=='cart_adjust_orientation':
            if params.get('direction') not in ('plus_x','minus_x','plus_y','minus_y','plus_z','minus_z'):
                raise ValueError('请选择一个明确朝向后调整')
            if params.get('clearance_confirmed') is not True:raise RuntimeError('请先确认运动区域安全')
        if operation=='cart_jog_hold':
            from .cartesian_jog import run
            return run(self,params)
        if operation=='cart_confirm_fixed_reference':
            return self.confirm_fixed_reference(params)
        if operation in ('cart_drawing_plan','cart_drawing_prepare','cart_drawing_execute'):
            from .drawing_motion import DrawingMotion
            if not hasattr(self,'drawing'):self.drawing=DrawingMotion(self)
            return self.drawing.operate(operation,params)
        if operation=='cart_execute_path':
            if params.get('clearance_confirmed') is not True:raise RuntimeError('请先确认运动区域安全')
            reasons=self.continuous._trajectory_reasons('line' if params.get('mode')=='L' else 'arc')
            if reasons:raise RuntimeError('；'.join(reasons))
            if 'goal' in params:
                self.require()
                if params.get('mode') not in ('L','C') or params.get('orientation','hold')!='hold':
                    raise ValueError('连续执行仅支持保持起点朝向的LIN/CIRC')
                signature=self.request_signature(params)
                self.task.phase='自动规划与预检'
                actual,reference=self.read_start()
                self.check_shared_direction(params,self.to_model(actual))
                checked_goal=k.validate_pose(params['goal'])
                checked_goal['rotation']=k.forward(self.to_model(actual))['rotation']
                self.check_workspace(checked_goal)
                report=self.preview
                prepared_key=(self.request_signature(params),self.continuous._context())
                prepared=self.prepared.wait_take(prepared_key,
                    [self.task.controller.nodes[n].motor_angle for n in range(1,7)],
                    [self.task.pulses_per_rev[n] for n in range(1,7)],self.task._check)
                if prepared is None:self.prepared.invalidate()
                if prepared is not None:
                    report=prepared;self.continuous.bind_preview(report,prepared_key[1]);self.preview=report
                    print('CART_PREPARED_REUSED',dict(algorithm=report.get('algorithm')),flush=True)
                reusable=bool(report and not report.get('offline') and report.get('native_report')
                    and report['native_report'].get('complete_before_start',False)
                    and (not report['native_report'].get('rolling') or
                         (not report['native_report']['frames'].closed and not report['native_report']['frames'].error))
                    and report.get('request_signature')==signature
                    and report.get('execution_context')==self.continuous._context())
                if reusable:
                    motor=report['native_report']['start_motor_deg']
                    reusable=all(abs(self.task.controller.nodes[n].motor_angle-motor[n-1])<=
                        max(.25,360/self.task.pulses_per_rev[n]+360/65536) for n in range(1,7))
                if not reusable:
                    from .reference_adapter import plan_rolling_cartesian
                    context=self.continuous._context()
                    hardware=self.positioning_hardware(params)
                    start=self.to_model(actual)
                    try:
                        report=plan_rolling_cartesian(start,params['goal'],self.bounds(),params['mode'],params.get('via'),
                            params.get('speed',10),params.get('joint_speed',5),self.task._check,hardware)
                    except ValueError as exc:
                        self.task._check()
                        print('CART_ROLLING_FALLBACK',dict(error=str(exc),start_angles_deg=start,
                            target_xyz_mm=params['goal']['position_mm']),flush=True)
                        self.task.message='滚动起步未通过，转完整预对齐/路径规划：'+str(exc)
                        try:self.operate('cart_plan',dict(params,full_preview=True));report=self.preview
                        except ValueError as fallback:
                            raise ValueError('连续接续失败：%s；完整规划也未通过：%s'%(exc,fallback)) from fallback
                    else:
                        if context!=self.continuous._context() or reference!=self.task._reference(range(1,7)):
                            report['native_report']['frames'].close();raise RuntimeError('规划期间现场参考或参数改变')
                        report.update(reference=reference,request_signature=signature)
                        self.continuous.bind_preview(report,context);self.preview=report
            executing=self.preview
            if executing and executing.get('native_report',{}).get('rolling'):
                finite=executing['native_report'];frames=finite['frames']
                with frames.lock:
                    if not finite.get('complete_before_start') or not frames.complete or frames.error or frames.closed:
                        raise RuntimeError('整段直线/圆弧尚未通过预检；未启动运动，请重新计算')
            try:self.continuous.execute(executing,params)
            finally:
                if executing and executing.get('native_report',{}).get('rolling'):
                    executing['native_report']['frames'].close()
            self.preview=None
            return
        from .trajectory_preparation import close_report
        close_report(self.preview)
        self.preview=None;self.solution=None
        if operation=='cart_calibrate':
            if (self.calibration or {}).get('configuration_locked') is True:
                raise ValueError('当前机械臂标定已固定，不允许重新写入')
            if params.get('confirmed') is not True:raise ValueError('请确认实物对应的CAD角与六轴正方向')
            model=k.finite_vector(params['model_angles'],6);signs=params['signs']
            if not isinstance(signs,list) or len(signs)!=6 or any(type(x) is not int or x not in (-1,1) for x in signs):raise ValueError('正方向无效')
            if any(n not in self.task.pulses_per_rev for n in range(1,7)):raise RuntimeError('请先配置六轴电机脉冲当量')
            actual=self.task._capture()
            data=dict(schema_version=1,geometry_version=k.GEOMETRY_VERSION,operator_confirmed=True,
                      signs=signs,offsets_deg=[model[i]-signs[i]*actual[str(i+1)] for i in range(6)],
                      reference=self.task._reference(range(1,7)))
            self.validate_calibration(data);atomic_json(self.path,data);self.calibration=data;self.error=''
            self.task.message='当前零点的CAD角度映射已保存；未发送运动命令'
            return
        if operation=='cart_offline_fk':
            self.solution=dict(pose=k.forward(params['model_angles']),model_angles_deg=params['model_angles'],offline=True)
            self.task.message='CAD名义正解已计算；不是实机零位'
            return
        if operation=='cart_offline_ik':
            seed=k.finite_vector(params['seed_deg'],6)
            self.check_shared_direction(params,seed)
            self.solution=k.inverse(params['goal'],seed,check=self.task._check)
            self.solution.update(offline=True,pose=k.forward(self.solution['angles_deg']))
            self.task.message='CAD参考逆解完成；未发送运动命令'
            return
        if operation=='cart_offline_plan':
            seed=k.finite_vector(params['seed_deg'],6)
            self.check_shared_direction(params,seed)
            self.preview=plan(seed,params['goal'],{i:(-180.,180.) for i in range(5)},
                mode=params.get('mode','L'),via=params.get('via'),speed=params.get('speed',5),
                orientation=params.get('orientation','hold'),joint_speed=params.get('joint_speed',5),check=self.task._check)
            self.preview['offline']=True
            self.task.message='交接包V2模型路径预览完成；离线参数不是现场执行参数'
            return
        # Fail before any bus IO: no streamed executor exists on current MMIO.
        if operation=='cart_execute_blend':
            raise RuntimeError('当前FPGA/驱动同步接续尚未验证；连续轨迹执行入口未开放')
        if operation=='cart_move_endpoint' and params.get('mode','J')!='J':
            raise RuntimeError('终点定位只适用于J方式，不能替代直线或圆弧执行')
        actual,reference=self.read_start();start=self.to_model(actual)
        adjusting_orientation=operation=='cart_adjust_orientation'
        if adjusting_orientation:
            from .wrist_orientation import solve
            for n in range(1,7):
                self.task._healthy(n)
                if not self.task.controller.nodes[n].enabled:
                    raise RuntimeError('J%d 请先使能以保持关节姿态'%n)
            self.prepared.invalidate()
            if hasattr(self,'drawing'):self.drawing.invalidate()
            result=solve(start,params['direction'],self.bounds(),self.task._check)
            if not self.ready() or reference!=self.task._reference(range(1,7)):
                raise RuntimeError('腕部换向规划期间六轴参考改变')
            converted=self.to_controller(result['angles_deg'])
            targets={n:converted[n-1] for n in (4,5)}
            wrist_speed=min(20.,float(params.get('joint_speed',5)))
            self.task._move(targets,wrist_speed,self.task._reference((4,5)))
            if reference!=self.task._reference(range(1,7)):
                raise RuntimeError('腕部换向期间六轴参考改变，请重新检查')
            final_actual,reference=self.read_start()
            if any(abs(final_actual[n-1]-actual[n-1])>.05 for n in (1,2,3,6)):
                raise RuntimeError('腕部换向后保持关节的位置偏离，请检查反馈和驱动状态')
            pose=k.forward(self.to_model(final_actual))
            self.solution=dict(result,controller_targets=targets,reference=reference,pose=pose,offline=False)
            self.task.message='腕部换向完成：只转 J4/J5；已刷新实际 XYZ，草稿保留'
            return
        self.check_shared_direction(params,start)
        self.task.phase='运动学计算'
        if operation=='cart_sequence_plan':
            if not self.task.points:raise ValueError('请先记录姿态')
            if any(not self.task.point_valid(p) or set(p['angles_deg'])!={str(n) for n in range(1,7)} for p in self.task.points):
                raise RuntimeError('整段运动学规划需要当前参考下的六轴姿态')
            previews=[];seconds=0.
            for point in copy.deepcopy(self.task.points):
                self.task._check()
                motion=point.get('motion',dict(mode='J',orientation='interpolate',tcp_speed_mm_s=10))
                target=self.to_model([point['angles_deg'][str(n)] for n in range(1,7)])
                goal=k.forward(target)
                if motion['mode']=='J':
                    # A taught joint pose retains explicit multi-turn goals and branch.
                    from .joint_blend import plan as jp,sample as js
                    r=jp(dict(enumerate(start,1)),[dict(angles_deg=dict(enumerate(target,1)),speed_deg_s=point['speed_deg_s'],dwell_seconds=0)],one_based(self.bounds()),radius=0)
                    report=dict(mode='J',samples=[dict(time_s=t,angles_deg=a,pose=k.forward(a)) for t,a in js(r)],
                                target_angles_deg=target,total_seconds=r['total_seconds'],validation='joint_convex_hull',execution_supported=False)
                else:
                    report=plan(start,goal,self.bounds(),mode=motion['mode'],via=motion.get('via_mm'),
                        speed=motion['tcp_speed_mm_s'],joint_speed=point['speed_deg_s'],
                        orientation=motion['orientation'],check=self.task._check,hardware=self.planning_hardware())
                report['name']=point['name'];report['start_seconds']=seconds
                report['dwell_seconds']=point['dwell_seconds'];seconds+=report['total_seconds']+point['dwell_seconds']
                previews.append(report);start=report['target_angles_deg']
            if reference!=self.task._reference(range(1,7)) or not self.ready():raise RuntimeError('整段规划期间参考改变')
            samples=[dict(p,time_s=p['time_s']+r['start_seconds']) for r in previews for p in r['samples']]
            self.preview=dict(mode='sequence',segments=previews,samples=samples,total_seconds=seconds,
                              reference=reference,execution_supported=False,validation='discrete_preview_only')
            self.task.message=f'已规划{len(previews)}段J/L/C轨迹，约{seconds:.2f}秒；各段精确停车，连续执行未开放'
            return
        if operation=='cart_refresh':
            self.solution=dict(pose=k.forward(start),model_angles_deg=start,controller_angles_deg=actual,offline=False)
            self.task.message='已读取六轴位置并计算轴端正解'
            return
        goal=k.validate_pose(params['goal'])
        if params.get('orientation','hold')=='hold':goal['rotation']=k.forward(start)['rotation']
        self.check_workspace(goal)
        if operation in ('cart_ik','cart_move_endpoint'):
            result=k.inverse(goal,start,self.bounds(),check=self.task._check)
            targets=dict(enumerate(self.to_controller(result['angles_deg']),1))
            self.solution=dict(result,controller_targets=targets,reference=reference,pose=k.forward(result['angles_deg']),offline=False)
            if not self.ready() or reference!=self.task._reference(range(1,7)):raise RuntimeError('逆解期间参考改变')
            if operation=='cart_move_endpoint':
                from .collision import check_joint_box
                check_joint_box(start,result['angles_deg'],self.task._check)
                # Existing precise endpoint controller, not execution of MoveJ/L/C samples.
                self.task._check();self.task._move(targets,min(20.,float(params.get('joint_speed',5))),reference)
                self.task.message=('所选朝向调整完成；终点XYZ保持调整前位置' if adjusting_orientation else
                    '轴端目标的六轴终点定位完成；未执行连续轨迹')
            else:self.task.message='逆解完成，六轴目标可用于现有终点定位'
        elif operation=='cart_plan':
            context=self.continuous._context()
            if params.get('allow_singularity_transition') or (params.get('mode','L') in ('L','C') and params.get('orientation','hold')=='hold' and not params.get('full_preview')):
                from .reference_adapter import plan_rolling_cartesian
                hardware=self.positioning_hardware(params)
                self.preview=plan_rolling_cartesian(start,goal,self.bounds(),params.get('mode','L'),params.get('via'),
                    params.get('speed',10),params.get('joint_speed',5),self.task._check,hardware)
            else:self.preview=plan(start,goal,self.bounds(),mode=params.get('mode','L'),via=params.get('via'),
                speed=params.get('speed',10),orientation=params.get('orientation','hold'),
                joint_speed=(min(20.,params.get('joint_speed',5)) if params.get('mode','L')=='J' else params.get('joint_speed',5)),check=self.task._check,
                hardware=self.positioning_hardware(params))
            if not self.ready() or reference!=self.task._reference(range(1,7)):close_report(self.preview);self.preview=None;raise RuntimeError('规划期间参考改变')
            self.preview.update(reference=reference,calibration=copy.deepcopy(self.calibration),
                controller_samples=[dict(time_s=p['time_s'],angles_deg=self.to_controller(p['angles_deg'])) for p in self.preview['samples']])
            if context!=self.continuous._context():close_report(self.preview);self.preview=None;raise RuntimeError('规划期间现场参数改变，请重新预览')
            if self.preview.get('native_report'):self.continuous.bind_preview(self.preview,context)
            self.preview['request_signature']=self.request_signature(params)
            if self.preview.get('native_report',{}).get('rolling'):
                from .fast_preview import attach_geometry
                try:attach_geometry(self.preview,start,goal,params.get('via'))
                except Exception:
                    close_report(self.preview);self.preview=None;raise
            self.task.message=f'{self.preview["mode"]} 轨迹规划完成，{len(self.preview["samples"])}点，约{self.preview["total_seconds"]:.2f}秒；执行前会再次核对现场起点'
        else:raise ValueError('未知末端操作')

    def prepare_idle(self,params):
        if self.task.busy or self.task.controller._moving or not self.ready():return
        signature=self.request_signature(params);context=self.continuous._context()
        report=self.preview
        if (report and report.get('request_signature')==signature and report.get('execution_context')==context
                and report.get('native_report',{}).get('rolling')
                and not report['native_report']['frames'].closed and not report['native_report']['frames'].error
                and all(self.task.controller.nodes[n].motor_angle is not None and
                    abs(self.task.controller.nodes[n].motor_angle-report['native_report']['start_motor_deg'][n-1])<=.25 for n in range(1,7))):return
        motor=[self.task.controller.nodes[n].motor_angle for n in range(1,7)]
        from .trajectory_preparation import valid_motor
        if not valid_motor(motor):
            self.prepared.invalidate();return
        self.prepared.invalidate_if_moved(motor)
        start=self.to_model([v/RATIOS[n] for n,v in enumerate(motor,1)])
        self.check_shared_direction(params,start)
        goal=k.validate_pose(params['goal']);goal['rotation']=k.forward(start)['rotation']
        bounds=copy.deepcopy(self.bounds());hardware=self.positioning_hardware(params)
        request=copy.deepcopy(params);reference=copy.deepcopy(self.task._reference(range(1,7)))
        def build(cancel):
            def check():
                if cancel.is_set():raise RuntimeError('后台准备已取消')
            from .reference_adapter import plan_rolling_cartesian
            check()
            self.check_workspace(goal)
            check()
            try:
                report=plan_rolling_cartesian(start,request['goal'],bounds,request['mode'],request.get('via'),
                    request.get('speed',5),request.get('joint_speed',5),check,hardware)
            except ValueError as exc:
                check()
                try:
                    report=plan(start,request['goal'],bounds,mode=request['mode'],via=request.get('via'),
                        speed=request.get('speed',5),joint_speed=request.get('joint_speed',5),
                        orientation='hold',check=check,hardware=hardware)
                except ValueError as fallback:
                    raise ValueError('连续接续失败：%s；完整规划也未通过：%s'%(exc,fallback)) from fallback
                report['rolling_fallback_reason']=str(exc)
            report.update(reference=reference,request_signature=signature,execution_context=context)
            return report
        self.prepared.ensure((signature,context),build,motor=motor)
