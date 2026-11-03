"""Untrusted AI proposals, checked by the existing single motion owner.

Preparing reads feedback but sends no motion frames. Only an explicit UI
authorization can consume a short-lived, reference-bound execution receipt.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import secrets
import threading
import time

from . import drawing, kinematics as k
from .collision import check_joint_box, check_target


def tools():
    specs = [
        ('move_tcp', '提出末端绝对定位方案，使用当前共享朝向；明确指令授权后检查通过执行。',
         dict(x_mm={'type':'number'}, y_mm={'type':'number'}, z_mm={'type':'number'},
              joint_speed_deg_s={'type':'number','minimum':1,'maximum':20})),
        ('jog_joint', '提出关节点动方案，一次相对移动，整段自动检查限位和扫过区域；明确指令授权后检查通过执行。',
         dict(joint={'type':'integer','minimum':1,'maximum':6},
              delta_deg={'type':'number','minimum':-360,'maximum':360},
              joint_speed_deg_s={'type':'number','minimum':1,'maximum':20})),
        ('move_joint', '关节绝对角度定位，一次规划到目标，不按10度拆分；目标受当前实际限位约束。',
         dict(joint={'type':'integer','minimum':1,'maximum':6},
              angle_deg={'type':'number','minimum':-3600,'maximum':3600},
              joint_speed_deg_s={'type':'number','minimum':1,'maximum':20})),
        ('draw_auto_route', '在当前工作面和切片高度自动选择可绘图中心；输入二维毫米偏移，保持尺寸和共享朝向，本地整条规划通过才执行。',
         dict(waypoints_uv_mm={'type':'array','minItems':2,'maxItems':256,
              'items':{'type':'array','minItems':2,'maxItems':2,'items':{'type':'number'}}},
              tcp_speed_mm_s={'type':'number','minimum':.1,'maximum':50},
              joint_speed_deg_s={'type':'number','minimum':1,'maximum':20})),
        ('run_saved_route', '提出运行用户已添加的线路方案；只能使用目录中的route_id，明确指令授权后检查通过执行。',
         dict(route_id={'type':'string'})),
        ('draw_route', '在工作区画布提出连续折线或采样曲线；绝对mm坐标，Z必须大于0，使用共享朝向和绘图加速度。明确指令授权后检查通过定位起点并运行。',
         dict(waypoints_mm={'type':'array','minItems':2,'maxItems':256,
              'items':{'type':'array','minItems':3,'maxItems':3,'items':{'type':'number'}}},
              tcp_speed_mm_s={'type':'number','minimum':.1,'maximum':50},
              joint_speed_deg_s={'type':'number','minimum':1,'maximum':20}))]
    return [dict(type='function',function=dict(name=name,description=desc,
        parameters=dict(type='object',properties=props,required=list(props),additionalProperties=False)))
        for name,desc,props in specs]


def validate_action(name, args):
    schema = next((t['function']['parameters'] for t in tools() if t['function']['name']==name), None)
    if schema is None or not isinstance(args,dict) or set(args)!=set(schema['required']):
        raise ValueError('AI动作类型或参数无效')
    for key,value in args.items():
        if key=='route_id':
            if not isinstance(value,str) or not value.startswith('route-') or len(value)!=22:
                raise ValueError('线路编号无效，请先添加已保存线路')
        elif key in ('waypoints_mm','waypoints_uv_mm'):
            dimension=3 if key=='waypoints_mm' else 2
            if not isinstance(value,list) or not 2<=len(value)<=256:
                raise ValueError('AI线路须有2～256个坐标点')
            for xyz in value:
                if (not isinstance(xyz,list) or len(xyz)!=dimension or
                    any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>2000 for v in xyz)):
                    raise ValueError('线路坐标必须是范围内的有限XYZ数值')
                if dimension==3:check_target(xyz)
        elif type(value) not in (int,float) or not math.isfinite(value):
            raise ValueError('动作参数必须是有限数值')
    if name in ('jog_joint','move_joint'):
        if type(args['joint']) is not int or not 1<=args['joint']<=6:
            raise ValueError('关节必须是J1～J6')
        if name=='jog_joint' and not 0<abs(args['delta_deg'])<=360:
            raise ValueError('相对移动角度须大于0且不超过360°')
        if name=='move_joint' and abs(args['angle_deg'])>3600:
            raise ValueError('绝对角度超过输入范围')
    if name=='move_tcp':
        xyz=[args[q+'_mm'] for q in ('x','y','z')]
        if any(abs(v)>2000 for v in xyz):raise ValueError('目标超出坐标输入范围')
        check_target(xyz)
    if name!='run_saved_route' and not 1<=args['joint_speed_deg_s']<=20:
        raise ValueError('关节速度须为1～20°/秒')
    if name in ('draw_route','draw_auto_route') and not .1<=args['tcp_speed_mm_s']<=50:
        raise ValueError('末端速度须为0.1～50mm/秒')
    return dict(name=name,args=copy.deepcopy(args))


def route_document(action,direction='hold',settings=None):
    action=validate_action(action['name'],action['args'])
    if action['name']!='draw_route':raise ValueError('不是绘图动作')
    settings=settings or {};a=action['args']
    document=drawing.validate(dict(schema=1,
        points=[dict(xyz=xyz,mode='L',stroke=0) for xyz in a['waypoints_mm']],
        direction=direction,speed=a['tcp_speed_mm_s'],joint_speed=a['joint_speed_deg_s'],
        trajectory_acceleration=settings.get('trajectory_acceleration'),
        allow_orientation_adjustment=settings.get('allow_orientation_adjustment',False)))
    drawing.segments(document)
    return document


class RouteCatalog:
    """Only the operator's file chooser can register paths; models see opaque IDs."""
    def __init__(self):
        self.items={}
        self.lock=threading.RLock()

    @staticmethod
    def _load(path):
        with Path(path).open('rb') as stream:raw=stream.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError('线路文件不能超过4MB')
        document=drawing.validate(json.loads(raw.decode('utf-8-sig')))
        drawing.segments(document)  # Arc/table validation, not just endpoints.
        return document,hashlib.sha256(raw).hexdigest()

    def add(self,path):
        path=Path(path).resolve();document,digest=self._load(path)
        ident='route-'+secrets.token_hex(8)
        with self.lock:
            self.items[ident]=dict(path=path,name=path.name,sha256=digest,points=len(document['points']))
        return ident

    def public(self):
        with self.lock:return [dict(route_id=i,name=v['name'],point_count=v['points']) for i,v in self.items.items()]

    def load(self,ident):
        with self.lock:item=copy.copy(self.items.get(ident))
        if item is None:raise ValueError('未添加该线路，请使用“添加已保存线路”')
        document,digest=self._load(item['path'])
        if digest!=item['sha256']:raise ValueError('线路文件已改变，请重新添加并检查方案')
        return document,item['name']


class ArmActions:
    TTL_SECONDS=120
    START_TOLERANCE_DEG=.01

    def __init__(self,task):
        self.task=task
        self.routes=RouteCatalog()
        self.lock=threading.RLock()
        self.generation=0
        self.pending=None
        self.preview=None

    def invalidate(self):
        with self.lock:
            r=self.pending
            self.generation+=1;self.pending=None;self.preview=None
        if r and r.get('report') is not None:
            c=self.task.cartesian
            if hasattr(c,'drawing') and c.drawing.report is r['report']:c.drawing.invalidate()

    def _context(self):
        c=self.task.cartesian
        return copy.deepcopy(dict(reference=self.task._reference(range(1,7)),
                                  calibration=c.calibration,hardware=c.planning_hardware()))

    def _quantized_clearance(self,start,targets,speed):
        self.task._preflight(targets,speed)
        actual=self.task.cartesian.to_controller(start)
        for n,p in self.task.plans.items():actual[n-1]=p['target_deg']
        end=self.task.cartesian.to_model(actual)
        check_joint_box(start,end,self.task._check)
        return {n:p['target_deg'] for n,p in self.task.plans.items()}

    def prepare(self,action,direction='hold',drawing_settings=None):
        self.invalidate()
        with self.lock:generation=self.generation
        action=validate_action(action['name'],action['args'])
        t=self.task;c=t.cartesian
        actual,reference=c.read_start();start=c.to_model(actual)
        context=self._context();a=action['args'];name=action['name']
        receipt=dict(action=action,start=actual,context=context,generation=generation,
                     created=time.monotonic(),token=secrets.token_hex(16))
        if name=='move_tcp':
            if direction not in ('hold','plus_x','minus_x','plus_y','minus_y','plus_z','minus_z'):
                raise ValueError('请选择一个明确的共享朝向')
            goal=dict(position_mm=[a[q+'_mm'] for q in ('x','y','z')],
                      rotation=drawing.rotation(direction,k.forward(start)['rotation']))
            c.check_workspace(goal)
            result=k.inverse(goal,start,c.bounds(),check=t._check)
            check_joint_box(start,result['angles_deg'],t._check)
            targets=dict(enumerate(c.to_controller(result['angles_deg']),1))
            targets=self._quantized_clearance(start,targets,a['joint_speed_deg_s'])
            end=k.forward(c.to_model([targets[n] for n in range(1,7)]))
            pe,ae=k.pose_error(goal,end)
            if pe>1 or ae>.12:
                raise ValueError('量化后的末端位置或朝向误差超限')
            receipt.update(targets=targets,speed=a['joint_speed_deg_s'],target_reference=t._reference(targets))
            summary='末端定位（J方式）：X %.2f / Y %.2f / Z %.2f mm\n共享朝向：%s；关节速度 %.1f°/s\n已检查逆解、限位、量化目标和定位全程Z＞0。'%(*goal['position_mm'],direction,a['joint_speed_deg_s'])
        elif name in ('jog_joint','move_joint'):
            n=a['joint'];target=a['angle_deg'] if name=='move_joint' else actual[n-1]+a['delta_deg']
            targets={n:target}
            targets=self._quantized_clearance(start,targets,a['joint_speed_deg_s'])
            receipt.update(targets=targets,speed=a['joint_speed_deg_s'],target_reference=t._reference(targets))
            summary='关节点动：J%d 从 %.3f° 到 %.3f°（相对 %+.3f°）\n速度 %.1f°/s；已检查限位、量化目标和全程Z＞0。'%(n,actual[n-1],targets[n],target-actual[n-1],a['joint_speed_deg_s'])
        else:
            if name=='draw_auto_route':
                from .ai_auto_placement import prepare_auto_route
                document,center=prepare_auto_route(c,a,direction,drawing_settings or {})
                title='自动选位 AI线路（中心 '+', '.join('%.2f'%v for v in center)+' mm）'
            elif name=='draw_route':
                document=route_document(action,direction,drawing_settings);title='AI画布线路'
            else:document,title=self.routes.load(a['route_id'])
            if name!='draw_auto_route':c.operate('cart_drawing_prepare',dict(document=document))
            report=c.drawing.report
            receipt.update(document=document,report=report)
            if name=='draw_auto_route':
                receipt.update(placement_plane=drawing_settings['placement_plane'],placement_fixed_mm=drawing_settings['placement_fixed_mm'])
            summary=('整条线路已规划通过；' if name=='draw_auto_route' else '')+'线路：%s（%d点）\n末端 %.1fmm/s；关节 %.1f°/s；ACC %s\n朝向 %s；自动调整朝向：%s\n入口、首段及制动段已检查；后续按现有绘图流程后台校验。'%(title,len(document['points']),document['speed'],document['joint_speed'],document['trajectory_acceleration'] or '沿用当前',document['direction'],'允许' if document['allow_orientation_adjustment'] else '关闭')
        t._check()
        if context!=self._context() or reference!=t._reference(range(1,7)):
            raise RuntimeError('检查期间现场参数改变，请重新提出方案')
        with self.lock:
            if generation!=self.generation:raise RuntimeError('方案已取消')
            receipt['created']=time.monotonic()
            self.pending=receipt
            self.preview=dict(token=receipt['token'],summary=summary,created=receipt['created'])
        t.message='AI动作检查通过；尚未发送运动指令'

    def execute(self,token,confirmed=False):
        with self.lock:
            r=self.pending;self.pending=None;self.preview=None
            if confirmed is not True or r is None or not secrets.compare_digest(str(token),r['token']):
                raise RuntimeError('缺少有效的人工确认，请重新检查方案')
        t=self.task;c=t.cartesian;t._check()
        if time.monotonic()-r['created']>self.TTL_SECONDS:raise RuntimeError('方案已过期，请重新检查')
        actual,_=c.read_start()
        if r['context']!=self._context() or any(abs(a-b)>self.START_TOLERANCE_DEG for a,b in zip(actual,r['start'])):
            raise RuntimeError('起点、零点或现场参数已变化，请重新检查方案')
        if r['action']['name'] in ('run_saved_route','draw_route','draw_auto_route'):
            document=(self.routes.load(r['action']['args']['route_id'])[0]
                      if r['action']['name']=='run_saved_route' else r['document'])
            if document!=r['document'] or c.drawing.report is not r['report']:
                raise RuntimeError('线路或准备结果已改变，请重新检查')
            c.operate('cart_drawing_execute',dict(document=document,clearance_confirmed=True))
        else:
            start=c.to_model(actual)
            targets=self._quantized_clearance(start,r['targets'],r['speed'])
            t._check()
            t._move(targets,r['speed'],expected_reference=r['target_reference'])
            t.message='AI确认动作已完成并核验到位'
