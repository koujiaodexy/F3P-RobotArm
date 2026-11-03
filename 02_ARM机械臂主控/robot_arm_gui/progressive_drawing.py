"""Bounded drawing preparation; math workers never own the motor channel."""
import copy
import math
import threading
import time
from . import kinematics as k
from .cartesian_planner import plan
from .planner_process import plan_remote
from .reference_adapter import make_model,TOOL_ROTATION


class ProgressiveDrawing:
    def __init__(self,owner,document,segments):
        self.owner=owner;self.cart=owner.cart;self.document=document;self.specs=copy.deepcopy(segments)
        origin=document['points'][0]['xyz']
        for spec in self.specs:
            spec['nominal_start']=list(origin);origin=spec['goal']
        self.cancel=threading.Event();self.condition=threading.Condition()
        self.reports=[];self.error='';self.done=False;self.revision=0;self.thread=None
        self.preview_at=0.

    def check(self):
        if self.cancel.is_set():raise RuntimeError('绘图后台规划已取消')
        self.cart.task._check()

    def close(self):
        self.cancel.set()
        with self.condition:self.condition.notify_all();reports=list(self.reports)
        for report in reports:
            frames=report.get('native_report',{}).get('frames')
            if frames is not None and hasattr(frames,'close'):frames.close()

    def invalidate(self):
        self.cancel.set()
        threading.Thread(target=self.close,name='drawing-math-cleanup',daemon=True).start()

    def build(self,start,spec):
        self.check();d=self.document
        check=self.check
        goal=dict(position_mm=spec['goal'],rotation=self.rotation)
        if spec['mode']=='J':
            return plan(start,goal,self.bounds,mode='J',orientation='interpolate',
                        joint_speed=min(20.,d['joint_speed']),check=check)
        hardware=dict(self.hardware)
        hardware['drawing_nominal_start_mm']=spec['nominal_start']
        # Complete short, fixed-heading strokes before publishing a start.
        # This enables a checked cruise interval without late producer timing.
        if (spec['mode'] in ('L','D') and d['speed']>=15
                and not d['allow_orientation_adjustment']
                and not hardware.get('drawing_orientation_released')):
            vertices=[spec['nominal_start'],*(spec.get('via') or []),spec['goal']]
            length=sum(math.dist(a,b) for a,b in zip(vertices,vertices[1:]))
            if length<=60:hardware['finite_complete']=True
        report=plan_remote('progressive',dict(start=start,goal=goal,bounds=self.bounds,
            mode=spec['mode'],via=spec.get('via'),speed=d['speed'],joint_speed=d['joint_speed'],
            hardware=hardware),check)
        return report

    def final_angles(self,report):
        native=report.get('native_report')
        if not native:return list(report['target_angles_deg'])
        frames=native['frames']
        while True:
            self.check()
            with frames.lock:
                if frames.error or frames.failed:raise RuntimeError(frames.error or frames.failed)
                if frames.complete:
                    motor=list(frames.head[-1]['command_motor_deg']);break
            self.cancel.wait(.01)
        return self.model.motor_to_joints(motor)

    def prepare(self,start,entry,context,reference,entry_motor):
        self.bounds=self.cart.bounds();self.rotation=k.forward(entry['target_angles_deg'])['rotation']
        d=self.document;self.hardware=self.cart.drawing_hardware(d['joint_speed'],d['trajectory_acceleration'],
                                                               d['allow_orientation_adjustment'])
        self.model=make_model(start,self.bounds,self.hardware['calibration'])
        if d['allow_orientation_adjustment']:
            # Decide a document-wide policy before publishing its first frames.
            # Switching only after a wrist branch/limit is reached changes the
            # derivatives underneath already committed timing boundaries.
            from .analytic_inverse import fixed_pose
            seed=list(entry['target_angles_deg']);rotation=[r[:3] for r in self.model.forward(seed)[:3]]
            points=d['points'];stride=max(1,math.ceil((len(points)-1)/64))
            indices=sorted(set(range(0,len(points),stride))|{len(points)-1})
            for i in indices:
                self.check()
                q=fixed_pose(self.model,points[i]['xyz'],rotation,seed,self.model.joint_limits_deg,self.check)
                if q is None:
                    if not getattr(self.model,'_analytic_geometry_compatible',False):break
                    self.hardware['drawing_orientation_released']=True;break
                if max(abs(a-b) for a,b in zip(seed,q))>60:
                    self.hardware['drawing_orientation_released']=True;break
                seed=q
            if self.hardware.get('drawing_orientation_released'):
                print('DRAWING_ORIENTATION_POLICY',dict(policy='authorized_position',reason='fixed_pose_branch_precheck',point_index=i),flush=True)
        self.reports=[entry]
        try:
            if self.specs:self.reports.append(self.build(entry['target_angles_deg'],self.specs[0]))
        except Exception:self.close();raise
        from .drawing import copy_validated_document
        self.report=dict(document=copy_validated_document(d),context=context,reference=reference,
            entry_motor=entry_motor,segments=self.reports,progressive=self,expected_segments=len(self.specs)+1)
        def produce():
            spec=None;angles=None;phase='waiting_previous'
            try:
                for spec in self.specs[1:]:
                    angles=None;phase='waiting_previous'
                    angles=self.final_angles(self.reports[-1]);self.check();phase='building_next'
                    report=self.build(angles,spec)
                    if self.cancel.is_set():
                        frames=report.get('native_report',{}).get('frames')
                        if frames is not None:frames.close()
                        self.check()
                    with self.condition:self.reports.append(report);self.revision+=1;self.condition.notify_all()
                if self.specs:
                    phase='waiting_final';angles=None;self.final_angles(self.reports[-1])
                with self.condition:self.done=True;self.revision+=1;self.condition.notify_all()
            except Exception as exc:
                failed_index=max(0,len(self.reports)-2) if phase!='building_next' else len(self.reports)-1
                failed_spec=self.specs[failed_index] if failed_index<len(self.specs) else spec
                details=dict(segment=failed_index+1,expected_segments=len(self.specs)+1,error=str(exc),
                    phase=phase,start_angles_deg=angles,spec=failed_spec,next_spec=spec,
                    direction=self.document['direction'],allow_orientation_adjustment=self.document['allow_orientation_adjustment'])
                if not self.cancel.is_set():
                    try:
                        import json,os
                        from pathlib import Path
                        directory=Path(os.environ.get('XDG_STATE_HOME') or str(Path.home()/'.local/state'))/'f3p-control'
                        directory.mkdir(parents=True,exist_ok=True)
                        path=directory/'last-planning-failure.json';temporary=path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(dict(details=details,document=self.document),ensure_ascii=False,indent=2),encoding='utf-8')
                        temporary.replace(path);details['diagnostic_file']=str(path)
                    except OSError as diagnostic_error:details['diagnostic_error']=str(diagnostic_error)
                print('DRAWING_BACKGROUND_FAILED',details,flush=True)
                with self.condition:self.error=str(exc);self.revision+=1;self.condition.notify_all()
        self.thread=threading.Thread(target=produce,name='drawing-math-sequence',daemon=True)
        self.thread.start();self.refresh_preview()
        return self.report

    def get(self,index):
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            self.cart.task._check();self.check()
            with self.condition:
                if self.error:raise RuntimeError('后续绘图规划失败：'+self.error)
                if index<len(self.reports):return self.reports[index]
                self.condition.wait(.02)
        raise RuntimeError('下一段绘图规划超时，保持停车')

    def refresh_preview(self):
        if time.monotonic()-self.preview_at<.25:return
        self.preview_at=time.monotonic();changed=False
        with self.condition:reports=list(self.reports)
        for report in reports:
            native=report.get('native_report')
            if not native:continue
            frames=native['frames']
            with frames.lock:
                key=(len(frames.head),frames.complete)
                if report.get('_preview_key')==key:continue
                visible=[row for row in frames.head if row is not None]
                stride=max(1,math.ceil(len(visible)/200));rows=visible[::stride]
                if visible and (not rows or rows[-1] is not visible[-1]):rows.append(visible[-1])
            report['samples']=[dict(time_s=row['t_s'],angles_deg=row['reference_joints_deg'],
                pose=dict(position_mm=row['reference_xyz_mm'],rotation=
                    k.mm(row['reference_rotation'],TOOL_ROTATION) if 'reference_rotation' in row else self.rotation))
                for row in rows]
            report['_preview_key']=key;changed=True
        if changed:self.revision+=1

    def execute(self):
        c=self.cart;t=c.task;r=self.report;d=self.document
        if r['context']!=c.continuous._context() or not c.ready():raise RuntimeError('现场参考改变，请重新规划')
        for spec in self.specs:
            if spec['mode']!='J':
                reasons=c.continuous._trajectory_reasons('arc' if spec['mode']=='C' else 'line',
                    None if d['trajectory_acceleration'] is None else [d['trajectory_acceleration']]*6)
                if reasons:raise RuntimeError('；'.join(reasons))
        c.read_start()
        if any(abs(t.controller.nodes[n].motor_angle-r['entry_motor'][n-1])>
               max(.25,360/t.pulses_per_rev[n]+360/65536) for n in range(1,7)):
            raise RuntimeError('机械臂已离开绘图预览起点，请重新规划')
        self.owner.report=None;t.total_points=r['expected_segments']
        previous=None
        try:
            for index in range(r['expected_segments']):
                t.phase='绘图执行 %d/%d：等待已核验段'%(index+1,r['expected_segments'])
                report=self.get(index);t.current_point=index+1
                if r['context']!=c.continuous._context():raise RuntimeError('绘图执行期间现场参数改变')
                if report['mode']=='J':
                    actual,_=c.read_start()
                    from .collision import check_joint_box
                    check_joint_box(c.to_model(actual),report['target_angles_deg'],t._check)
                    t._move(dict(enumerate(c.to_controller(report['target_angles_deg']),1)),min(20.,d['joint_speed']),r['reference'],acceleration=d['trajectory_acceleration'])
                else:
                    report['drawing_handoff']=previous is not None and previous['mode']=='J'
                    report['drawing_acceleration']=None if d['trajectory_acceleration'] is None else [d['trajectory_acceleration']]*6
                    c.continuous.bind_preview(report,r['context'])
                    c.continuous.execute(report,dict(mode=report['mode'],clearance_confirmed=True,
                        speed=d['speed'],joint_speed=d['joint_speed']))
                previous=report
            if self.error:raise RuntimeError(self.error)
            t.message='绘制线路全部执行完成，终点与六轴停止已核验'
        finally:self.close();t.current_point=0;t.total_points=0
