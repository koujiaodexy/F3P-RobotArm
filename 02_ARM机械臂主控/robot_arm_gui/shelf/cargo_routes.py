"""Offline event-driven mission policy. No serial, MMIO, CAN, socket or GPIO IO.

Commands are intents for a simulator, NOT a hardware transport. A future board
executor must enforce freshness, lease expiry, physical start and output locks.
Distances use signed forward-positive cumulative encoder millimetres.
"""
import copy
import math

COLORS = ('red', 'yellow', 'green')
TERMINAL = ('IDLE', 'DONE', 'STOP', 'FAULT')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_config(cfg):
    if cfg.get('schema') != 1 or cfg.get('offline_only') is not True:
        raise ValueError('Only schema 1 offline configurations are supported')
    if type(cfg.get('program')) is not int or cfg['program'] not in (1, 2):
        raise ValueError('Unknown program')
    if cfg.get('provider') != 'color':
        raise ValueError('COCO grasp is reserved, not implemented')
    if cfg.get('enabled_colors') != list(COLORS) or cfg.get('station_quantity') != 1:
        raise ValueError('Exactly one red/yellow/green object per station')
    for key in ('station_wait_s','settle_s','stable_pixel_radius','vision_max_age_s',
                'vision_wait_s','seek_speed_mm_s','seek_max_mm','seek_timeout_s',
                'grasp_timeout_s','mission_timeout_s','status_max_age_s'):
        if not finite(cfg.get(key)) or cfg[key] <= 0:
            raise ValueError('Invalid positive parameter: '+key)
    if cfg['station_wait_s'] != 1 or cfg['seek_max_mm'] >= 520:
        raise ValueError('Wait must be 1s; seek limit must be below next 520mm leg')
    if not 0 < cfg['seek_speed_mm_s'] <= 50:
        raise ValueError('Offline creep limit is 50mm/s')
    if type(cfg.get('stable_frames')) is not int or cfg['stable_frames'] < 3:
        raise ValueError('At least three distinct frames required')
    if cfg.get('workspace_policy')!='current_calibration_full_pick_place_preflight':
        raise ValueError('Existing calibrated grasp workspace is required')
    expected=[{'forward_mm':700},{'station':1,'record':'X'},
              {'forward_mm':520,'subtract':'X'},{'station':2,'record':'Y'},
              {'forward_mm':520,'subtract':'Y'},{'station':3,'record':'Z'}]
    if cfg['program']==2:
        expected += [{'left_deg':-180},{'forward_mm':2000,'add':'Z'},
                     {'left_deg':45},{'forward_mm':500},{'left_deg':-45}]
    if cfg.get('travel') != expected:
        raise ValueError('Route differs from approved offline sequence')
    return copy.deepcopy(cfg)


def resolved_distance(leg, records):
    value=float(leg['forward_mm'])
    if 'subtract' in leg: value -= records[leg['subtract']]
    if 'add' in leg: value += records[leg['add']]
    if not finite(value) or value <= 0:
        raise ValueError('Compensation exhausted leg; reverse/clamp is forbidden')
    return value


class Mission:
    """Pure policy; advance by fresh snapshots and explicit command receipts.

    Snapshot: now, measured_at, odo_mm=[L,R], wheels_stopped, arm_stowed,
    gripper_released, fault (bool), optional done_id/success. GRASP receipt
    also needs placed_count=1. Vision uses capture timestamp, unique frame_id,
    session_id, running/fresh, and validated target objects from color_bridge.
    """
    def __init__(self, config):
        self.cfg=validate_config(config)
        self.state='IDLE'; self.records={}; self.log=[]; self.action=None
        self.counter=0; self.run_id=0; self.index=0; self.error=None
        self.quiet_at=None; self.quiet_odo=None; self.session=None; self.workspace_context=None
        self.last_time=None; self.last_frame=None; self.last_capture=None; self.observed_capture=None
        self.target=None; self.stable=0; self.search_origin=None

    def _command(self, kind, **args):
        self.counter+=1
        self.action=dict(id=self.counter, run_id=self.run_id, kind=kind, **args)
        self.log.append(dict(time=self.now, state=self.state, action=copy.deepcopy(self.action)))

    def _stop(self, reason, fault=True):
        self.error=reason; self.state='FAULT' if fault else 'STOP'
        self._command('stop', reason=reason, cancel_arm=True, release_gripper_pwm=True)

    def _fresh_status(self, s):
        if not finite(s.get('now')) or not finite(s.get('measured_at')):
            raise ValueError('Invalid status time')
        if not 0 <= s['now']-s['measured_at'] <= self.cfg['status_max_age_s']:
            raise ValueError('Status stale')
        odo=s.get('odo_mm')
        if not isinstance(odo,(list,tuple)) or len(odo)!=2 or not all(finite(x) for x in odo):
            raise ValueError('Invalid signed odometry')
        for key in ('wheels_stopped','arm_stowed','gripper_released','fault'):
            if type(s.get(key)) is not bool: raise ValueError('Missing status flag '+key)
        if s['fault']: raise ValueError('Executor fault')

    def _safe_wheels(self,s):
        if not s['arm_stowed'] or not s['gripper_released']:
            raise ValueError('Arm/gripper must be stowed/released before wheel motion')

    def _quiet(self,s):
        if not s['wheels_stopped']:
            self.quiet_at=None; self.quiet_odo=None; return False
        if self.quiet_at is None or max(abs(a-b) for a,b in zip(s['odo_mm'],self.quiet_odo)) > 1.0:
            self.quiet_at=self.now; self.quiet_odo=list(s['odo_mm']); return False
        return self.now-self.quiet_at >= self.cfg['settle_s']

    def _enter_leg(self,s):
        self.quiet_at=None
        if self.index >= len(self.cfg['travel']):
            self.state='DONE'; self._command('stop', reason='Route complete'); return
        leg=self.cfg['travel'][self.index]
        if 'station' in leg:
            self.state='WAIT'; self.wait_until=self.now+self.cfg['station_wait_s']
            self.search_origin=None; self.target=None; self.stable=0; self.hold_origin=list(s['odo_mm'])
            self.last_frame=None; self.last_capture=None; self.observed_capture=None
            self._command('hold', station=leg['station'], wait_s=self.cfg['station_wait_s'])
        else:
            self._safe_wheels(s); self.state='TRAVEL'
            if 'forward_mm' in leg:
                self._command('drive', distance_mm=resolved_distance(leg,self.records))
            else:
                self._command('turn', left_deg=leg['left_deg'], feedback='validated_imu_yaw')

    def _vision(self,s):
        frame=s.get('vision')
        if not isinstance(frame,dict): raise ValueError('No fresh vision frame')
        if frame.get('running') is not True or frame.get('fresh') is not True:
            raise ValueError('Vision not running/fresh')
        stamp=frame.get('captured_at')
        if not finite(stamp) or not 0<=self.now-stamp<=self.cfg['vision_max_age_s']:
            raise ValueError('Capture stale: publication time is not capture time')
        sid=frame.get('session_id'); fid=frame.get('frame_id')
        if not isinstance(sid,str) or not sid or type(fid) is not int or fid<0:
            raise ValueError('Invalid frame/session identity')
        if self.session is None: self.session=sid
        if sid!=self.session: raise ValueError('Vision session changed')
        context=frame.get('workspace_context')
        if not isinstance(context,str) or not context: raise ValueError('Missing workspace context')
        if self.workspace_context is None: self.workspace_context=context
        if context!=self.workspace_context: raise ValueError('Workspace calibration/reference changed')
        if self.last_capture is not None and stamp < self.last_capture:
            raise ValueError('Out-of-order vision capture')
        self.last_capture=stamp
        targets=frame.get('targets')
        if not isinstance(targets,list) or len(targets)>64: raise ValueError('Invalid targets')
        for t in targets:
            if not isinstance(t,dict) or t.get('color') not in COLORS: raise ValueError('Unsupported target')
            if type(t.get('target_candidate')) is not bool or t.get('workspace_context')!=context:
                raise ValueError('Target lacks matching reference identity')
            uv=t.get('uv'); pixel=t.get('pixel_uv')
            if (not isinstance(uv,(list,tuple)) or len(uv)!=2 or not all(finite(v) and 0<=v<=1 for v in uv)
                    or not isinstance(pixel,(list,tuple)) or len(pixel)!=2 or not all(finite(v) for v in pixel)):
                raise ValueError('Invalid target coordinates')
            if t.get('track_id') is not None and type(t['track_id']) not in (int,str):
                raise ValueError('Invalid track ID')
        return frame

    def _eligible(self,t):
        return t['target_candidate'] is True

    def _same_target(self,a,b):
        return (a['color']==b['color'] and
                (a.get('track_id') is None or b.get('track_id')==a['track_id']) and
                math.dist(a['pixel_uv'],b['pixel_uv'])<=self.cfg['stable_pixel_radius'])

    def _observe(self,frame):
        if frame['frame_id']==self.last_frame: return
        if self.last_frame is not None and frame['frame_id']<self.last_frame:
            raise ValueError('Frame ID moved backward')
        if self.observed_capture is not None and frame['captured_at']<=self.observed_capture:
            raise ValueError('New frame needs a newer capture timestamp')
        self.last_frame=frame['frame_id']; self.observed_capture=frame['captured_at']
        candidates=[t for t in frame['targets'] if self._eligible(t)]
        candidates.sort(key=lambda t:(COLORS.index(t['color']),tuple(t['pixel_uv'])))
        selected=next((t for t in candidates if self.target and self._same_target(self.target,t)),None)
        if selected is None:
            selected=candidates[0] if candidates else None; self.stable=0
        self.target=copy.deepcopy(selected)
        if selected is not None: self.stable+=1

    def _search_distance(self,s):
        if self.search_origin is None: return 0.0
        delta=[a-b for a,b in zip(s['odo_mm'],self.search_origin)]
        if min(delta)<-2: raise ValueError('Search encoder direction reversed')
        if abs(delta[0]-delta[1])>30: raise ValueError('Search wheel distances disagree')
        value=max(0.0,sum(delta)/2)
        if value>=self.cfg['seek_max_mm']: raise ValueError('Search distance limit exceeded')
        return value

    def tick(self,s, key=None):
        self.now=s.get('now',0.0)
        if key=='KEY4':
            self._stop('Physical KEY4 stop',fault=False); return copy.deepcopy(self.action)
        try:
            self._fresh_status(s)
            if self.last_time is not None and self.now < self.last_time: raise ValueError('Clock reversed')
            self.last_time=self.now
            if self.state in TERMINAL:
                if key=='KEY1':
                    if not s['wheels_stopped'] or not s['gripper_released'] or not s['arm_stowed']:
                        raise ValueError('Reset requires all actions stopped/stowed')
                    self.state='IDLE'; self.error=None; self._command('hold')
                if key=='KEY2' and self.state=='IDLE':
                    if s.get('pc_disconnected') is not True or not s['wheels_stopped']:
                        raise ValueError('Physical start requires PC disconnected and wheels stopped')
                    self._safe_wheels(s); self.run_id+=1; self.started=self.now
                    self.records={}; self.index=0; self.session=None; self.last_capture=None; self.workspace_context=None
                    self._enter_leg(s)
                return copy.deepcopy(self.action)
            if s.get('pc_disconnected') is not True: raise ValueError('PC reconnected; stop active mission')
            if self.now-self.started > self.cfg['mission_timeout_s']: raise ValueError('Mission timeout')
            if self.state!='GRASP': self._safe_wheels(s)
            if self.state in ('WAIT','OBSERVE','GRASP') and max(abs(a-b) for a,b in zip(s['odo_mm'],self.hold_origin))>2.:
                raise ValueError('Unexpected encoder motion during stationary phase')
            if self.state=='TRAVEL':
                if s.get('done_id')==self.action['id']:
                    if s.get('success') is not True: raise ValueError('Travel failed')
                    self.state='SETTLE'; self.quiet_at=None; self._command('stop',reason='Travel complete')
            elif self.state=='SETTLE':
                if self._quiet(s): self.index+=1; self._enter_leg(s)
            elif self.state=='WAIT':
                if not s['wheels_stopped']: raise ValueError('Motion during station wait')
                if self.now>=self.wait_until:
                    self.state='OBSERVE'; self.search_started=self.now
                    self.vision_deadline=self.now+self.cfg['vision_wait_s']
                    self._command('hold',reason='Start station recognition')
            elif self.state in ('OBSERVE','SEEK'):
                if self.now-self.search_started>self.cfg['seek_timeout_s']: raise ValueError('Search timeout')
                self._search_distance(s)
                try: frame=self._vision(s)
                except ValueError:
                    if self.state=='OBSERVE' and self.now<self.vision_deadline and self.session is None:
                        return copy.deepcopy(self.action)
                    raise
                self._observe(frame)
                if self.target is not None:
                    # Stop immediately on the first selected-color candidate. Confirm remaining
                    # distinct frames at rest so a short window is not overshot.
                    if self.state=='SEEK':
                        self.state='BRAKE'; self.quiet_at=None; self._command('stop',reason='Selected target became visible')
                    elif self.stable>=self.cfg['stable_frames']:
                        self.state='BRAKE'; self.quiet_at=None; self._command('stop',reason='Stable selected target')
                elif self.state=='OBSERVE':
                    self.search_origin=list(s['odo_mm']); self.state='SEEK'
                    self._command('creep',speed_mm_s=self.cfg['seek_speed_mm_s'],max_mm=self.cfg['seek_max_mm'])
            elif self.state=='BRAKE':
                if self.now-self.search_started>self.cfg['seek_timeout_s']: raise ValueError('Search/settle timeout')
                distance=self._search_distance(s)
                frame=self._vision(s)
                previous=self.target
                self._observe(frame)
                if self.target is None or previous is None or not self._same_target(previous,self.target):
                    raise ValueError('Target lost/changed while braking; no automatic restart')
                if self._quiet(s) and self.stable>=self.cfg['stable_frames']:
                    leg=self.cfg['travel'][self.index]; self.records[leg['record']]=distance
                    self.log.append(dict(time=self.now,station=leg['station'],record=leg['record'],distance_mm=distance,
                                         per_wheel_mm=[a-b for a,b in zip(s['odo_mm'],self.search_origin)] if self.search_origin else [0,0]))
                    self.state='GRASP'; self.grasp_started=self.now; self.hold_origin=list(s['odo_mm'])
                    self._command('grasp',station=leg['station'],quantity=1,target=self.target,
                                  require_place=True,require_home=True)
            elif self.state=='GRASP':
                if not s['wheels_stopped']: raise ValueError('Wheels moved during grasp')
                if self.now-self.grasp_started>self.cfg['grasp_timeout_s']: raise ValueError('Grasp timeout')
                if s.get('done_id')==self.action['id']:
                    if s.get('success') is not True or s.get('placed_count')!=1:
                        raise ValueError('Grasp/place did not complete exactly one command cycle')
                    self._safe_wheels(s)
                    self.state='SETTLE'; self.quiet_at=None; self._command('stop',reason='Placed and homed')
        except (ValueError,KeyError,TypeError,OverflowError) as exc:
            self._stop(str(exc))
        return copy.deepcopy(self.action)
