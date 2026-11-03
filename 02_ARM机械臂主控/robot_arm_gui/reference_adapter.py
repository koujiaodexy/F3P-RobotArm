"""Unit/frame adapter for the unmodified handoff V2 FK/IK and LIN/CIRC."""
import copy
import json
import math
from pathlib import Path
from .reference_endpoint.kinematics import ArmModel, matrix_to_rpy
from .fast_trajectory import plan_path
from .native_math import PlanningModel
from .zero_home import RATIOS

SOURCE_PROFILE=json.loads((Path(__file__).parent/'reference_endpoint/actual_arm.json').read_text(encoding='utf-8'))
# Both conventions share physical tool +Z; reference tool X/Y are rotated -90°.
# This fixed right multiplication preserves the existing UI's RPY/calibration.
TOOL_ROTATION=[[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]]


def make_model(seed,bounds,calibration=None,check=lambda:None,multistart=True):
    profile=copy.deepcopy(SOURCE_PROFILE)
    profile['joint_limits_deg']=[list(bounds[i]) if i in bounds else
        (None if i==5 or i==3 and getattr(bounds,'rule',None) else [seed[i]-180,seed[i]+180]) for i in range(6)]
    if getattr(bounds,'rule',None):profile['continuous_joints']=sorted(set(profile.get('continuous_joints',[])) | {4})
    profile['j3_j4_rule']=copy.deepcopy(getattr(bounds,'rule',None))
    mapping=profile['motor_mapping'];mapping['ratios']=[RATIOS[i+1] for i in range(6)]
    mapping['directions']=list(calibration['signs']) if calibration else [1]*6
    mapping['joint_reference_deg']=list(calibration['offsets_deg']) if calibration else [0]*6
    mapping['motor_reference_deg']=[0]*6
    profile['solver']['position_tolerance_mm']=.03
    profile['solver']['orientation_tolerance_deg']=.02
    if not multistart:profile['solver']['max_seeds']=1
    class CancellableModel(PlanningModel):
        def _forward_chain(self,q,include_frames):
            check()
            return super()._forward_chain(q,include_frames)
        def _iterate(self,start,target,limits):
            check();result=super()._iterate(start,target,limits);check();return result
    return CancellableModel(profile)


def forward(q,jacobian=False):
    from . import kinematics as k
    model=make_model(q,{})
    transform,axes,origins,_=model._chain(q)
    pose=dict(position_mm=[row[3] for row in transform[:3]],
              rotation=k.mm([row[:3] for row in transform[:3]],TOOL_ROTATION))
    if jacobian:
        pose.update(axes=axes,origins=origins,jacobian=k.transpose([
            k.scale(k.cross(axis,k.sub(pose['position_mm'],origin)),1/200)+axis
            for axis,origin in zip(axes,origins)]))
    return pose


def inverse(goal,seed,bounds,check,multistart):
    from . import kinematics as k
    from .analytic_inverse import solve as analytic
    answer=analytic(goal,seed,bounds,check)
    if answer is not None:
        pe,ae=k.pose_error(goal,forward(answer['angles_deg']))
        sigma=k.singular_value(forward(answer['angles_deg'],True)['jacobian'])
        answer.update(position_error_mm=pe,orientation_error_deg=ae,singular_value=sigma,near_singularity=sigma<.01)
        return answer
    check();model=make_model(seed,bounds,check=check,multistart=multistart)
    r=k.mm(goal['rotation'],k.transpose(TOOL_ROTATION))
    solution=model.solve(goal['position_mm'],matrix_to_rpy(r),seed)
    pe,ae=k.pose_error(goal,forward(solution));sigma=k.singular_value(forward(solution,True)['jacobian'])
    from .coupled_limits import check_model_box
    check_model_box(model,solution,solution)
    if pe>.03 or ae>.03:raise ValueError('参考算法逆解回代误差超限')
    return dict(angles_deg=solution,position_error_mm=pe,orientation_error_deg=ae,
                singular_value=sigma,near_singularity=sigma<.01,algorithm='handoff-v2')


def _plan_cartesian_inline(start,goal,bounds,mode,via,speed,joint_speed,check,hardware=None):
    from . import kinematics as k
    hardware=hardware or {};model=make_model(start,bounds,hardware.get('calibration'),check)
    profile=model.profile;profile['trajectory_joint_speed_deg_s']=joint_speed;model=ArmModel(profile)
    limits=model.joint_limits_deg
    tolerance=hardware.get('drawing_position_tolerance_mm',.1)
    origin_error=0.
    if 'drawing_expected_origin_mm' in hardware:
        origin_error=math.dist([row[3] for row in model.forward(start)[:3]],hardware['drawing_expected_origin_mm'])
        tolerance-=origin_error
        if tolerance<.01:raise ValueError('绘图接续起点已用尽1mm路径误差预算，请重新定位')
    caps=hardware.get('speed_caps_rpm',[max(1,min(3000,int(joint_speed*RATIOS[n]/6))) for n in range(1,7)])
    acc=hardware.get('acceleration',[50]*6);ppr=hardware.get('pulses_per_rev',[3200]*6)
    native=plan_path(model,model.joints_to_motor(start),goal['position_mm'],kind='polyline' if mode=='D' else 'line' if mode=='L' else 'arc',
        via_mm=via if mode in ('C','D') else None,feed_mm_s=speed,speed_caps_rpm=dict(enumerate(caps,1)) if not isinstance(caps,dict) else caps,
        acceleration=dict(enumerate(acc,1)) if not isinstance(acc,dict) else acc,
        pulses_per_rev=dict(enumerate(ppr,1)) if not isinstance(ppr,dict) else ppr,
        limits_deg=limits,check_cancel=check,allow_stop_joint_transition=hardware.get('allow_stop_joint_transition',False),
        position_tolerance_mm=tolerance,allow_orientation_adjustment=hardware.get('drawing_adaptive_orientation',False))
    native['drawing_origin_error_mm']=origin_error
    if 'drawing_position_tolerance_mm' in hardware:native['drawing_position_budget_mm']=hardware['drawing_position_tolerance_mm']
    frames=native['frames']
    from .collision import check_joint_box
    previous=start
    for frame in frames:
        current=frame['reference_joints_deg']
        from .coupled_limits import check_model_box
        check_model_box(model,previous,current)
        check_model_box(model,current,model.motor_to_joints(frame['command_motor_deg']))
        check_joint_box(previous,current,check)
        check_joint_box(current,model.motor_to_joints(frame['command_motor_deg']),check)
        previous=current
    # The original packed frames stay intact for validation. Only plot samples
    # are reduced; preview reduction never creates executable commands.
    stride=max(1,math.ceil(len(frames)/800));indices=sorted(set(range(0,len(frames),stride))|{len(frames)-1})
    if native.get('preparation'):indices=sorted(set(indices)|{native['preparation']['frames']})
    start_rotation=forward(start)['rotation']
    rotations=native.get('reference_rotations')
    samples=[dict(time_s=frames[i]['t_s'],angles_deg=list(frames[i]['reference_joints_deg']),
        pose=dict(position_mm=list(frames[i]['reference_xyz_mm']),rotation=k.mm(rotations[i],TOOL_ROTATION) if rotations else start_rotation),phase=frames[i]['phase']) for i in indices]
    report=dict(mode='L' if mode=='D' else mode,samples=samples,target_angles_deg=list(frames[-1]['reference_joints_deg']),
        total_seconds=native['duration_s'],path_length_mm=native['path_length_mm'],algorithm='v16-rolling-cartesian',
        native_report=native,execution_supported=False,validation='discrete_preview_only',orientation='hold',
        warning='模型采样路径误差预算 %.3g mm，含脉冲量化与前视检查；实物精度及碰撞尚未验证。'%hardware.get('drawing_position_tolerance_mm',tolerance))
    if native.get('arc'):report['arc_radius_mm']=native['arc']['radius_mm']
    if rotations:report['orientation_adjusted']=True;report['orientation']='adaptive'
    if native.get('preparation'):
        prep=native['preparation'];report['preparation']=dict(prep,start_angles_deg=prep['start_joints_deg'],end_angles_deg=prep['end_joints_deg'],duration_s=prep['duration_s'])
    return report


def _plan_rolling_inline(start,goal,bounds,mode,via,speed,joint_speed,check,hardware):
    from .local_trajectory import plan_local as plan_rolling
    from . import kinematics as k
    model=make_model(start,bounds,hardware.get('calibration'),check)
    speed=k.finite_vector([speed],1)[0];joint_speed=k.finite_vector([joint_speed],1)[0]
    if not .01<=speed<=100 or not 0<joint_speed<=100:raise ValueError('轨迹速度参数超出范围')
    transition=hardware.get('allow_singularity_transition',False)
    if transition and mode!='L':raise ValueError('奇异区关节过渡目前仅支持直线')
    native=plan_rolling(model,model.joints_to_motor(start),goal['position_mm'],
        kind='polyline' if mode=='D' else 'line' if mode=='L' else 'arc',via_mm=via if mode in ('C','D') else None,
        feed_mm_s=speed,joint_speed_deg_s=joint_speed,
        speed_caps_rpm=dict(enumerate(hardware['speed_caps_rpm'],1)),
        acceleration=dict(enumerate(hardware['acceleration'],1)),pulses_per_rev=dict(enumerate(hardware['pulses_per_rev'],1)),
        check_cancel=check,allow_singularity_transition=transition,
        _wrist_prefix_disabled=hardware.get('disable_wrist_prefix',False),
        finite_complete=hardware.get('finite_complete',False),
        prefer_short_lookahead=hardware.get('prefer_short_lookahead',False),
        allow_orientation_adjustment=hardware.get('drawing_adaptive_orientation',False),
        orientation_released=hardware.get('drawing_orientation_released',False),
        position_tolerance_mm=hardware.get('drawing_position_tolerance_mm',.1),
        nominal_start_mm=hardware.get('drawing_nominal_start_mm'),
        singularity_deviation_mm=hardware.get('singularity_deviation_mm',.1))
    frames=native['frames'];first=frames[0]
    samples=[dict(time_s=0,angles_deg=list(first['reference_joints_deg']),
        pose=dict(position_mm=list(first['reference_xyz_mm']),rotation=k.forward(start)['rotation']),phase='cartesian')]
    if transition:
        stride=max(1,math.ceil(len(frames)/800))
        samples=[dict(time_s=frames[i]['t_s'],angles_deg=list(frames[i]['reference_joints_deg']),
                      pose=forward(frames[i]['reference_joints_deg']),phase='cartesian')
                 for i in sorted(set(range(0,len(frames),stride))|{len(frames)-1})]
    preparation=native.get('preparation')
    return dict(preparation=None if not preparation else dict(preparation,start_angles_deg=preparation['start_joints_deg'],end_angles_deg=preparation['end_joints_deg']),
        mode='L' if mode=='D' else mode,orientation_adjusted=bool(hardware.get('drawing_adaptive_orientation')),
        algorithm='v20-bounded-singularity-transition' if transition else 'v19-local-prepared-cartesian',native_report=native,
        total_seconds=native['duration_s'],path_length_mm=native['path_length_mm'],orientation='hold',
        samples=samples,
        target_angles_deg=model.motor_to_joints(native['final_motor_deg']),execution_supported=False,
        warning='滚动帧含独立制动备用段；模型采样检查，未做碰撞检测。')

def plan_cartesian(start,goal,bounds,mode,via,speed,joint_speed,check,hardware=None):
    from .planner_process import plan_remote
    return plan_remote('full',dict(start=start,goal=goal,bounds=bounds,mode=mode,via=via,
        speed=speed,joint_speed=joint_speed,hardware=hardware),check)

def plan_rolling_cartesian(start,goal,bounds,mode,via,speed,joint_speed,check,hardware):
    from .planner_process import plan_remote
    hardware=dict(hardware,finite_complete=True)
    return plan_remote('rolling',dict(start=start,goal=goal,bounds=bounds,mode=mode,via=via,
        speed=speed,joint_speed=joint_speed,hardware=hardware),check)

def plan_jog_cartesian(start,goal,bounds,speed,joint_speed,check,hardware):
    """Use checked local frames; reject failure without a full-plan fallback."""
    from .planner_process import plan_remote
    import time
    hardware=dict(hardware,disable_wrist_prefix=True)
    deadline=time.monotonic()+5.
    def guarded_check():
        check()
        if time.monotonic()>deadline:raise ValueError('点动起步计算超过5秒，改用更短步长')
    return plan_remote('progressive',dict(start=start,goal=goal,bounds=bounds,mode='L',via=None,
        speed=speed,joint_speed=joint_speed,hardware=hardware),guarded_check)
