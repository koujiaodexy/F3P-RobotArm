"""Offline target-lock boundary for current red/yellow/green grasp code.

Never issues hardware commands. Workspace gate must be bound to the current
arm calibration, limits, stowed pose and the existing grasp cycle planner.
"""
import copy
import math
import time
from .capture_bound import BASIS


def color_frame(telemetry, now, workspace_gate):
    from robot_arm_gui.grasp_preview import fresh_targets
    groups=fresh_targets(telemetry,now)
    captured=telemetry.get('captured_at')
    fid=telemetry.get('frame_id')
    bound_source=telemetry.get('capture_bound_source_id')
    delta=telemetry.get('capture_bound_delta')
    if (telemetry.get('capture_time_basis')!=BASIS or type(bound_source) is not int or
            not 0<=bound_source<=0xffffffff or type(fid) is not int or
            type(delta) is not int or not 2<=delta<=32 or ((fid-bound_source)&0xffffffff)!=delta):
        raise ValueError('Missing verified ISP frame-start bound; dequeue time is not sufficient')
    if type(captured) not in (int,float) or not math.isfinite(captured) or not 0<=now-captured<=.35:
        raise ValueError('Moving search needs capture time; legacy publication timestamp is insufficient')
    if type(fid) is not int or fid<0:
        raise ValueError('Moving search needs a distinct capture frame_id')
    sid=telemetry.get('session_id')
    if not isinstance(sid,str) or not sid: raise ValueError('Missing vision session')
    if not callable(workspace_gate) or not getattr(workspace_gate,'context_id',None):
        raise ValueError('Missing calibrated workspace evaluator')
    targets=[]
    for rows in groups.values():
        for row in rows:
            decision=workspace_gate(row)
            if type(decision.get('target_candidate')) is not bool or decision.get('workspace_context')!=workspace_gate.context_id:
                raise ValueError('Invalid workspace decision')
            targets.append(dict(row,uv=[row['source_pixel_uv'][0]/479.,row['source_pixel_uv'][1]/269.],**decision))
    return dict(running=True,fresh=True,session_id=sid,frame_id=fid,captured_at=captured,
                workspace_context=workspace_gate.context_id,targets=targets)


class LockedColorSession:
    def __init__(self, session, target, workspace_gate, clock=time.monotonic):
        if target.get('color') not in ('red','yellow','green'):
            raise ValueError('COCO/blue grasp not enabled in this offline version')
        if target.get('target_candidate') is not True or target.get('workspace_context')!=workspace_gate.context_id:
            raise ValueError('Target reference context mismatch')
        self.source=session; self.target=copy.deepcopy(target); self.gate=workspace_gate
        self.clock=clock; self.original_session=session.session_id

    @property
    def session_id(self): return self.source.session_id

    @property
    def running(self):
        return self.source.running and self.source.session_id==self.original_session

    @property
    def telemetry(self):
        if not self.running: raise RuntimeError('Locked vision session stopped/changed')
        raw=copy.deepcopy(self.source.telemetry)
        frame=color_frame(raw,self.clock(),self.gate)
        if frame['session_id']!=self.original_session or frame['workspace_context']!=self.target['workspace_context']:
            raise RuntimeError('Frame session or workspace changed')
        candidates=[t for t in frame['targets'] if t['color']==self.target['color']
            and t['target_candidate']
            and (self.target.get('track_id') is None or t['track_id']==self.target['track_id'])
            and math.dist(t['pixel_uv'],self.target['pixel_uv'])<=20]
        if not candidates: raise RuntimeError('Locked workspace target moved/disappeared; cancel grasp')
        chosen=min(candidates,key=lambda t:math.dist(t['pixel_uv'],self.target['pixel_uv']))
        raw['targets']=[dict(color=chosen['color'],center=chosen['pixel_uv'],track_id=chosen['track_id'])]
        return raw


def one_grasp_params(params,target,workspace_gate,clock=time.monotonic):
    """Return args for existing execute; a returned request is NOT execution."""
    if params.get('clearance_confirmed') is not True or params.get('use_gripper') is not True:
        raise ValueError('Original grasp preconditions must remain enabled')
    session=LockedColorSession(params['session'],target,workspace_gate,clock)
    session.telemetry
    return dict(params,session=session,requested={c:int(c==target['color']) for c in ('red','yellow','green')})
