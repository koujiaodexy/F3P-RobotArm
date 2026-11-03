"""Bridge the original V2 trajectory executor to the existing task owner."""
import copy
import threading
import uuid
from .reference_endpoint.trajectory_service import CartesianTrajectoryMixin
from .reference_adapter import make_model
from . import kinematics as k
from .streaming_executor import StreamingExecutorMixin


class ContinuousMotion(StreamingExecutorMixin,CartesianTrajectoryMixin):
    VERIFY_SAMPLES=3
    VERIFY_MOTOR_TOLERANCE_DEG=.1

    @staticmethod
    def _follow_tolerance_deg(index,ppr):
        # Running envelope margin, in motor degrees. Final arrival remains strict.
        from .zero_home import RATIOS
        return max(2.,min(30.,RATIOS[index+1]*.1),360/ppr)

    def __init__(self, cartesian):
        self.cartesian=cartesian
        self.task=cartesian.task
        self.controller=self.task.controller
        self._cancelled=self.task.cancelled
        self._trajectory_owned=False
        self._stop_started=False
        self._stop_done=threading.Event()
        self._stop_results={}
        self._stop_callbacks=[]
        self._participants=set()
        self._state={}
        self._plans={}

    def _context(self):
        return dict(reference=self.task._reference(range(1,7)),
                    hardware=self.cartesian.planning_hardware())

    def _trajectory_reasons(self, motion_kind, acceleration=None):
        if acceleration is None:
            acceleration=getattr(self,'_drawing_execution_acceleration',None)
        if acceleration is None:
            return super()._trajectory_reasons(motion_kind)
        if motion_kind not in ('line','arc'):
            return super()._trajectory_reasons(motion_kind)
        reasons=[]
        if not getattr(self.controller.backend,'supports_continuous_trajectory',False):
            reasons.append('连续直线/圆弧需要 V9 FPGA 轨迹接口；当前仍可离线预览或执行 PTP')
        if len(acceleration)!=6 or any(type(value) is not int or not 1<=value<=255 for value in acceleration):
            reasons.append('绘图轨迹需要六轴加速度为 1～255')
        return reasons

    def _execute_continuous(self, plan, callback):
        # Both rolling and complete executors recheck the prepared drawing ACC.
        from .rolling_trajectory import RollingFrames
        if not isinstance(plan['trajectory']['frames'],RollingFrames):
            model=self._get_model()
            for frame in plan['trajectory']['frames']:
                self._check_conditional_frame(frame,plan,model)
        previous=getattr(self,'_drawing_execution_acceleration',None)
        self._drawing_execution_acceleration=plan.get('drawing_acceleration')
        try:
            return super()._execute_continuous(plan,callback)
        finally:
            self._drawing_execution_acceleration=previous

    def bind_preview(self, report, context):
        report['execution_context']=copy.deepcopy(context)
        report['execution_id']=str(uuid.uuid4())
        self._plans={report['execution_id']:True}
        report['execution_supported']=bool(getattr(self.controller.backend,'supports_continuous_trajectory',False))

    def _get_model(self):
        context=self._context();bounds=self.cartesian.bounds()
        seed=self.cartesian.to_model([self.controller.nodes[n].motor_angle/float(context['reference']['ratios'][str(n)]) for n in range(1,7)])
        key=(context,bounds,None if all(i in bounds or i==3 and getattr(bounds,'rule',None) for i in range(5)) else seed)
        if getattr(self,'_model_key',None)!=key:
            self._feedback_model=make_model(seed,bounds,self.cartesian.calibration)
            self._model_key=copy.deepcopy(key)
        return self._feedback_model

    def _solver_limits(self):
        return self._get_model().joint_limits_deg

    def _check(self, **_kwargs):
        self.task._check()

    def _check_plan(self, plan):
        self._check()
        self.cartesian.require()
        if plan['id'] not in self._plans or plan['context']!=self._context():
            raise RuntimeError('轨迹预览已失效：零位、标定、限位或速度参数改变，请重新预览')

    def _read_axes(self,require_enabled=True):
        for n in range(1,7):
            self._check();self.task._read(n,require_enabled=require_enabled)
        return [self.controller.nodes[n].motor_angle for n in range(1,7)]

    def _start_tolerances(self,plan,current):
        normal={n:max(.25,360/plan['pulses_per_rev'][n]+360/65536) for n in range(1,7)}
        from .grasp_transfer import endpoint_tolerance
        normal[6]=endpoint_tolerance(plan,6,normal[6])
        if not plan.get('drawing_handoff'):return normal
        from .zero_home import MOTOR_ZERO_TOLERANCE
        tolerances={n:max(normal[n],MOTOR_ZERO_TOLERANCE+180/plan['pulses_per_rev'][n]+360/65536) for n in range(1,7)}
        errors=[abs(a-b) for a,b in zip(current,plan['motor_start_deg'])]
        pose=self._pose_accuracy(current,plan['trajectory']['start_xyz_mm'],plan['trajectory']['rpy_deg'])
        print('DRAWING_HANDOFF_CHECK',dict(motor_error_deg=errors,tolerances_deg=list(tolerances.values()),**pose),flush=True)
        if pose['position_error_mm']>.1 or pose['orientation_error_deg']>1.:
            raise RuntimeError('绘图接续起点偏差超限：%.3fmm / %.3f°，请重新定位起点'%(pose['position_error_mm'],pose['orientation_error_deg']))
        return tolerances

    def _start(self, _name, _callback, work):
        # Already on JointMotion's single worker. Do not create another CAN owner.
        self.task.phase='连续轨迹执行'
        from .trajectory_runtime import execution_runtime
        # Grasp uses complete PackedFrames and bypasses the rolling executor's
        # runtime guard. Protect both paths until their confirmed stop completes.
        with execution_runtime():
            try:
                return work()
            except Exception:
                if self._trajectory_owned:
                    self._start_trajectory_stop()
                    self._stop_done.wait(self.TRAJECTORY_STOP_SECONDS+1)
                raise

    @staticmethod
    def _callback(callback,ok):
        if callback:callback(ok)

    def _start_stop(self):
        self._start_trajectory_stop()

    def stop(self,callback=None):
        self._cancelled.set()
        with self.controller._lock:
            if callback:self._stop_callbacks.append(callback)
            self._start_trajectory_stop(retry_failed=True)

    def _verify(self,plan,require_arrived=False):
        motor=self._read_axes(require_enabled=True)
        from .grasp_transfer import endpoint_tolerance
        return all(abs(a-b)<=endpoint_tolerance(plan,i+1,max(self.VERIFY_MOTOR_TOLERANCE_DEG,180/plan['pulses_per_rev'][i+1]+360/65536))
                   for i,(a,b) in enumerate(zip(motor,plan['motor_target_deg'])))

    def _pose_accuracy(self,motor,position,rpy):
        from .reference_endpoint.kinematics import pose_error,rpy_to_matrix
        import math
        transform=self._get_model().forward(self._get_model().motor_to_joints(motor))
        expected=[row+[value] for row,value in zip(rpy_to_matrix(rpy),position)]+[[0,0,0,1]]
        p,r=pose_error(transform,expected)
        return dict(position_error_mm=math.sqrt(sum(v*v for v in p)),orientation_error_deg=math.degrees(math.sqrt(sum(v*v for v in r))))

    def _publish(self,**values):
        self._state.update(values)
        self.task.message=values.get('message',self.task.message)
        progress=self._state.get('trajectory_progress')
        if progress and 'message' not in values:
            self.task.message=f"连续轨迹 {progress['fired_seq']}/{progress['total_frames']} · 模型路径偏差 {progress['path_error_mm']:.3f} mm"
        self.controller._publish()

    def execute(self,report,params):
        from .grasp_transfer import PROFILE, feedback_limits
        fast = bool(report and report.get('algorithm')==PROFILE and report.get('native_report') and feedback_limits(report['native_report']))
        if not report or report.get('offline') or (report.get('mode') not in ('L','C') and not (fast and report.get('mode')=='J')) or not report.get('native_report'):
            raise RuntimeError('请先读取现场反馈并计算直线或圆弧预览')
        if params.get('clearance_confirmed') is not True:
            raise RuntimeError('请先确认运动区域安全')
        if params.get('mode')!=report['mode']:
            raise RuntimeError('运动模式改变，请重新预览')
        drawing_acceleration=report.get('drawing_acceleration')
        reasons=self._trajectory_reasons('line' if report['mode']=='L' else 'arc',drawing_acceleration)
        if reasons:raise RuntimeError('；'.join(reasons))
        native=report['native_report']
        if drawing_acceleration is not None and list(native['frames'][0]['acceleration'])!=list(drawing_acceleration):
            raise RuntimeError('绘图加速度与已准备轨迹不一致，请重新规划')
        if native.get('rolling'):
            print('CART_ROLLING_START',dict(initial_planning_seconds=native['initial_planning_seconds'],
                geometry_samples=native['geometry_samples'],duration_seconds=native['duration_s'],
                requested_feed=params.get('speed'),requested_joint_speed=params.get('joint_speed'),
                planned_peak_feed=native['peak_feed_mm_s'],wire_rpm=native['wire_speed_caps_rpm'],
                lookahead_seconds=native['lookahead_seconds'],lookahead_attempts=native.get('lookahead_attempts',[]),
                local_planning=native.get('local_planning',False),initial_geometry_fraction=native.get('initial_geometry_fraction'),
                acceleration=list(native['frames'][0]['acceleration'])),flush=True)
        context=report['execution_context']
        if self._context()!=context:raise RuntimeError('现场配置改变，请重新预览')
        self._stop_started=False;self._stop_done.clear();self._stop_results={};self._state={};self._participants=set()
        packed=dict(id=report['execution_id'],context=context,trajectory=native,
            motor_start_deg=native['start_motor_deg'],motor_target_deg=native['final_motor_deg'],
            pulses_per_rev=dict(enumerate(context['hardware']['pulses_per_rev'],1)),
            duration_seconds=native['duration_s'],target_position_mm=native['frames'][-1]['reference_xyz_mm'],
            target_rpy_deg=native.get('final_rpy_deg',native['rpy_deg']),path_kind='cartesian_line' if report['mode']=='L' else 'cartesian_arc')
        packed['drawing_handoff']=bool(report.get('drawing_handoff'))
        packed['drawing_acceleration']=drawing_acceleration
        return self._execute_continuous(packed,None)
