"""Restore measured near-zero wrist offsets before publishing executable frames.

The exact-singular curve is a mathematical guide only. Every emitted ideal,
quantized and lookahead pose is checked in the original physical TCP frame.
"""
import math
from . import fast_trajectory as f
from .native_math import LIBRARY,array,flatten
from .planning_residual import planning_joint_error
from .collision import check_joint_box,check_target
from .coupled_limits import check_model_box

class Residual:
    def __init__(self,model,origin):
        self.model=model;self.origin=origin;self.cache={}
        if any(not math.isfinite(v) for row in origin for v in row):
            raise f.TrajectoryError('腕部原始位姿含非有限数值')
        self.native=LIBRARY is not None and getattr(model,'native_enabled',False) and hasattr(LIBRARY,'f3p_q_pose_norms')
        self.native_origin=array(flatten(origin)) if self.native else None
        self.xyz=tuple(row[3] for row in origin[:3]);self.native_xyz=array(self.xyz) if self.native else None
    def error(self,q,xyz):
        key=(tuple(q),tuple(xyz))
        if key in self.cache:return self.cache[key]
        if any(not math.isfinite(v) for v in q) or any(not math.isfinite(v) for v in xyz):
            raise f.TrajectoryError('腕部恢复轨迹含非有限数值')
        if self.native:
            out=array([0.,0.]);LIBRARY.f3p_q_pose_norms(self.model._native_geometry,array(q),self.native_origin,
                self.native_xyz if tuple(xyz)==self.xyz else array(xyz),out)
            # The fused native ABI already returns nonnegative mm/degree norms.
            pe,re=out[0],out[1]
        else:
            expected=[row[:3]+[xyz[i]] for i,row in enumerate(self.origin[:3])]+[[0.,0.,0.,1.]]
            pe,re=planning_joint_error(self.model,q,expected);pe=f._norm(pe);re=math.degrees(f._norm(re))
        if not math.isfinite(pe) or not math.isfinite(re):raise f.TrajectoryError('腕部恢复残差非有限')
        if len(self.cache)>=8192:self.cache.clear()
        self.cache[key]=(pe,re);return pe,re

class Restorer:
    def __init__(self,model,origin,point,offset,args,check):
        self.model=model;self.point=point;self.offset=offset;self.check=check;self.residual=Residual(model,origin)
        self.ppr=f._six(args['pulses_per_rev'],1,0xffffffff,'PPR');self.limits=model.joint_limits_deg
        self.max_ideal_position=0.;self.max_ideal_orientation=0.;self.cache={}
        self.finite=bool(args.get('finite_complete'))
    def joints(self,q):
        q=list(q);q[4]+=self.offset;return q
    def ideal(self,q,xyz):
        pe,re=self.residual.error(q,xyz)
        self.max_ideal_position=max(self.max_ideal_position,pe);self.max_ideal_orientation=max(self.max_ideal_orientation,re)
        if pe>.01 or re>.02:raise f.TrajectoryError('近零反馈导引恢复后的原路径残差超过0.01mm / 0.02度')
    def restore(self,rows):
        from .native_curve_frames import restore
        batch=restore(self,rows)
        if batch is not None:return batch
        result=[]
        for row in rows:
            self.check()
            key=(row['seq'],row['t_s'],row['command_t_s'],tuple(row['reference_joints_deg']),
                 tuple(row['command_joints_deg']),tuple(row['speed_rpm']),row['final'])
            if key in self.cache:result.append(self.cache[key]);continue
            q=self.joints(row['reference_joints_deg']);cq=self.joints(row['command_joints_deg'])
            u=row['reference_u'];cu=row['command_reference_u'];xyz=self.point(u);cxyz=self.point(cu)
            check_target(xyz);check_target(cxyz)
            motor=self.model.joints_to_motor(q);cmotor=self.model.joints_to_motor(cq)
            pulses=[round(m*p/360) for m,p in zip(cmotor,self.ppr)];quantized=[p*360/r for p,r in zip(pulses,self.ppr)]
            qq=self.model.motor_to_joints(quantized)
            if any(not -2147483648<=p<=2147483647 for p in pulses):raise f.TrajectoryError('恢复后的绝对脉冲超出signed32')
            if any(abs(m)*65536/360>0xffffffff for m in motor+cmotor+quantized):raise f.TrajectoryError('恢复后的角度超出反馈范围')
            for angles in (q,cq,qq):
                if any(pair and not pair[0]-1e-9<=v<=pair[1]+1e-9 for pair,v in zip(self.limits,angles)):
                    raise f.TrajectoryError('恢复后参考或量化关节超限')
            self.ideal(q,xyz);self.ideal(cq,cxyz)
            check_model_box(self.model,q,cq)
            check_model_box(self.model,q,qq)
            pe,re=self.residual.error(qq,cxyz)
            if pe>.1 or re>.12:raise f.TrajectoryError('恢复后量化误差超过0.1mm / 0.12度')
            check_joint_box(q,qq,self.check)
            for fraction in (.25,.5,.75):
                angles=[a+fraction*(b-a) for a,b in zip(q,cq)]
                pe,re=self.residual.error(angles,self.point(u+fraction*(cu-u)))
                if pe>.1 or re>.2:raise f.TrajectoryError('恢复后前视插值误差超过0.1mm / 0.2度')
            restored=dict(row,reference_xyz_mm=xyz,command_xyz_mm=cxyz,reference_joints_deg=q,
                command_joints_deg=cq,reference_motor_deg=motor,command_motor_deg=quantized,motor_target_pulses=pulses)
            if len(self.cache)>=8192:self.cache.clear()
            self.cache[key]=restored;result.append(restored)
        for previous,current in zip(result,result[1:]):
            check_model_box(self.model,previous['reference_joints_deg'],current['reference_joints_deg'])
            check_model_box(self.model,self.model.motor_to_joints(previous['command_motor_deg']),
                            self.model.motor_to_joints(current['command_motor_deg']))
        return result
