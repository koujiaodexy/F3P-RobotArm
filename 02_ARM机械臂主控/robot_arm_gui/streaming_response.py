"""Carry a bounded response oracle across fixed-orientation drawing blocks.

The normal prefix and its alternative stopping reserve must both pass before
publication. A speculative stop never advances the continuing model state.
This is a model check, not a measurement of physical tracking accuracy.
"""
import math
from . import fast_trajectory as f
from .driver_tracking import orientation_error


class ResponseGuard:
    def __init__(self, model, motor, check):
        from .native_driver_tracking import LIBRARY
        from . import native_math as nm
        self.model=model;self.check=check;self.origin=model.forward(model.motor_to_joints(motor))
        self.library=LIBRARY if getattr(model,'native_enabled',False) else None
        self.mapping=nm.array(model._motor_ref+model._joint_ref+model._directions+model._ratios) if self.library else None
        self.native_origin=nm.array(nm.flatten(self.origin)) if self.library else None
        self.prefix=[];self.next_seq=1
        # Include different arm/wrist acceleration responses, not only uniform
        # scaling of all six axes, and both orders of asynchronous CAN samples.
        self.cases=[(rates,reverse) for rates in ((1.,)*6,(.5,)*6,
                    (.5,.5,.5,1.,1.,1.),(1.,1.,1.,.5,.5,.5))
                    for reverse in (False,True)]
        self.states=[list(motor)+[0.]*6+list(motor)*9+[0.]*4 for _ in self.cases]

    def _advance(self, state, rows, tail, rates, reverse):
        from . import native_math as nm
        points=self.prefix+rows+tail[:30];begin=len(self.prefix)
        # A shared native factor plus per-axis scratch ACC represents the
        # same rates exactly. Choose a feasible factor for low ACC too, so
        # mixed arm/wrist scenarios do not force slow Python FK on the board.
        upper=min(255*r/(256-a) for row in points for a,r in zip(row['acceleration'],rates))
        base=min(max(rates),upper*(1.-1e-9))
        native_ok=all(1<=256-(256-a)*base/r<=255
                      for row in points for a,r in zip(row['acceleration'],rates))
        if self.library and native_ok:
            packed=nm.array([v for row in points for v in (list(row['command_motor_deg'])+
                list(row['speed_rpm'])+[256-(256-a)*base/r for a,r in zip(row['acceleration'],rates)]+
                list(row['reference_xyz_mm'])+list(row['command_xyz_mm'])+
                [float(row.get('phase')=='wrist_preparation')])])
            skew=nm.array([round(.035*(5-i if reverse else i)/5/.005) for i in range(6)])
            native_state=nm.array(state)
            for offset in range(0,len(rows),50):
                self.check()
                result=self.library.f3p_response_block(self.model._native_geometry,self.mapping,
                    self.native_origin,packed,len(points),begin+offset,min(50,len(rows)-offset),
                    base,skew,1,native_state)
                if result:raise f.TrajectoryError('滚动驱动响应输入或位姿无效')
            return list(native_state)
        from .reference_endpoint.trajectory_service import _segment_distance
        state=list(state);motor=state[:6];velocity=state[6:12]
        history=[state[12+i*6:18+i*6] for i in range(9)];worst=state[66:]
        for index,row in enumerate(rows):
            self.check()
            acceleration=[6/((256-a)*50e-6)*r for a,r in zip(row['acceleration'],rates)]
            for _ in range(8):
                for i in range(6):
                    delta=row['command_motor_deg'][i]-motor[i]
                    desired=(1 if delta>=0 else -1)*min(6*row['speed_rpm'][i],math.sqrt(2*acceleration[i]*abs(delta)))
                    old=velocity[i];velocity[i]+=max(-acceleration[i]*.005,min(acceleration[i]*.005,desired-old))
                    step=(old+velocity[i])*.0025
                    if step*delta>=0 and abs(step)>=abs(delta):motor[i]=row['command_motor_deg'][i];velocity[i]=0.
                    else:motor[i]+=step
                history=history[1:]+[list(motor)]
            pose=self.model.forward(self.model.motor_to_joints(motor))
            sampled=[history[-1-round(.035*(5-i if reverse else i)/5/.005)][i] for i in range(6)]
            worst[0]=max(worst[0],orientation_error(pose,self.origin))
            worst[1]=max(worst[1],orientation_error(self.model.forward(self.model.motor_to_joints(sampled)),self.origin))
            xyz=[r[3] for r in pose[:3]]
            window=points[max(0,begin+index-30):begin+index+31]
            path=[r['reference_xyz_mm'] for r in window]+[window[-1]['command_xyz_mm']]
            worst[3]=max(worst[3],min(_segment_distance(xyz,a,b) for a,b in zip(path,path[1:])))
        return motor+velocity+[v for row in history for v in row]+worst

    @staticmethod
    def _validate(state):
        if any(not math.isfinite(v) for v in state):raise f.TrajectoryError('滚动驱动响应位姿含非有限数值')
        if max(state[66:68])>1.:raise f.TrajectoryError('滚动驱动响应朝向偏差超出1度预检预算')
        if max(state[68:70])>1.:raise f.TrajectoryError('滚动驱动响应路径偏差超出1mm预检预算')

    def accept(self, rows, reserve):
        if not rows or any(row['seq']!=self.next_seq+i for i,row in enumerate(rows)):
            raise f.TrajectoryError('滚动响应预检帧序号不连续')
        accepted=[]
        for state,(rates,reverse) in zip(self.states,self.cases):
            continuing=self._advance(state,rows,reserve,rates,reverse);self._validate(continuing)
            # Check the alternative brake from the same accepted normal state.
            prefix=self.prefix
            try:
                self.prefix=(prefix+rows)[-30:]
                stopping=self._advance(continuing,reserve,[],rates,reverse) if reserve else continuing
                self._validate(stopping)
            finally:self.prefix=prefix
            accepted.append(continuing)
        self.states=accepted;self.prefix=(self.prefix+rows)[-30:];self.next_seq+=len(rows)

    def report(self):
        return dict(model_only=True,scenarios=len(self.cases),frames_checked=self.next_seq-1,
            max_orientation_deg=max(max(s[66:68]) for s in self.states),
            max_path_error_mm=max(max(s[68:70]) for s in self.states),
            orientation_budget_deg=1.,position_budget_mm=1.,braking_reserve_checked=True)

    def preview(self, rows, reserve):
        saved=self.states,self.prefix,self.next_seq
        try:self.accept(rows,reserve)
        finally:self.states,self.prefix,self.next_seq=saved
