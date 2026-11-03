"""Named GTK controls for the AI, without arbitrary code or credential access."""
import copy
import math
from dataclasses import asdict

PAGES = ('control', 'position', 'drawing', 'teaching')
SETTINGS = {
    'selected_joint': (1, 6, 'integer'),
    'motor_rpm': (1, 3000, 'integer'),
    'motor_acceleration': (0, 255, 'integer'),
    'joint_speed': (1, 20, 'number'),
    'tcp_speed': (.1, 50, 'number'),
    'drawing_joint_speed': (1, 20, 'number'),
    'drawing_acceleration': (1, 255, 'integer'),
    'slice_position': (-380, 510, 'number'),
    'auto_orientation': (False, True, 'boolean'),
    'independent_acceleration': (False, True, 'boolean'),
    'shared_direction': ('hold', 'plus_x', 'minus_x', 'plus_y', 'minus_y', 'plus_z', 'minus_z', 'union'),
    'slice_plane': ('xy', 'xz', 'yz'),
    'drawing_mode': ('J', 'L', 'C'),
}
COMMANDS = ('stop_all', 'enable_selected', 'disable_selected', 'home_all',
            'refresh_angles', 'capture_pose', 'open_zero_settings', 'open_wifi',
            'open_vision', 'view_logs', 'start_logging', 'end_logging',
            'open_position_settings', 'open_calibration', 'request_shutdown',
            'prepare_canvas', 'execute_canvas', 'play_teaching', 'preview_teaching',
            'save_canvas', 'load_canvas')


def ui_tools():
    def tool(name, description, properties):
        return dict(type='function', function=dict(name=name, description=description,
            parameters=dict(type='object', properties=properties, required=list(properties), additionalProperties=False)))
    return [
        tool('get_control_state', '读取完整控制状态、六轴反馈时间/错误、零点、标定、画布和姿态；不含密码密钥。', {}),
        tool('show_control_page', '切换控制页面，不启动运动。', {'page':dict(type='string', enum=list(PAGES))}),
        tool('set_control_setting', '按明确指令修改界面参数，绝不勾选安全确认或修改标定/零点/限位。',
             {'setting':dict(type='string', enum=list(SETTINGS)), 'value':dict(anyOf=[dict(type=t) for t in ('string','number','boolean')])}),
        tool('activate_control', '调用原界面功能。使能/失能/回零/回放/执行只在用户明确要求时调用；设置和关机保留原人工确认；保存/载入由文件选择器完成。',
             {'command':dict(type='string', enum=list(COMMANDS))}),
        tool('replace_canvas', '只画线/修改草稿，不执行运动；自动备份旧草稿，保留当前朝向/速度/ACC。',
             {'waypoints_mm':dict(type='array',minItems=2,maxItems=256,items=dict(type='array',minItems=3,maxItems=3,items=dict(type='number')))}),
        tool('set_pose_record_settings', '设置姿态记录名称、速度与停留时间，不启动记录或运动。',
             {'name':dict(type='string',maxLength=64), 'speed_deg_s':dict(type='number',minimum=1,maximum=20),
              'dwell_s':dict(type='number',minimum=0,maximum=30)}),
    ]


def validate_ui_action(name, args):
    expected = {'get_control_state':(), 'show_control_page':('page',),
                'set_control_setting':('setting','value'), 'activate_control':('command',),
                'replace_canvas':('waypoints_mm',), 'set_pose_record_settings':('name','speed_deg_s','dwell_s')}
    if name not in expected or not isinstance(args,dict) or set(args)!=set(expected[name]):
        raise ValueError('界面工具或参数无效')
    if name=='show_control_page' and args['page'] not in PAGES:raise ValueError('页面无效')
    if name=='activate_control' and args['command'] not in COMMANDS:raise ValueError('界面操作无效')
    if name=='replace_canvas':
        from .ai_arm_control import validate_action
        validate_action('draw_route',dict(waypoints_mm=args['waypoints_mm'],tcp_speed_mm_s=5,joint_speed_deg_s=5))
    if name=='set_pose_record_settings':
        if not isinstance(args['name'],str) or not 1<=len(args['name'].strip())<=64:raise ValueError('姿态名称无效')
        for key,minimum,maximum in [('speed_deg_s',1,20),('dwell_s',0,30)]:
            v=args[key]
            if type(v) not in (int,float) or not math.isfinite(v) or not minimum<=v<=maximum:raise ValueError('姿态参数超出范围')
    if name=='set_control_setting':
        spec=SETTINGS.get(args['setting']);v=args['value']
        if spec is None:raise ValueError('不能修改该设置')
        if len(spec)==3 and spec[2] in ('integer','number','boolean'):
            kind=spec[2]
            if kind=='boolean':
                if type(v) is not bool:raise ValueError('设置必须为布尔值')
            elif (type(v) not in (int,float) or not math.isfinite(v) or
                  not spec[0]<=v<=spec[1] or kind=='integer' and type(v) is not int):
                raise ValueError('设置数值超出范围或类型错误')
        elif not isinstance(v,str) or v not in spec:raise ValueError('设置选项无效')
    return dict(name=name,args=copy.deepcopy(args))


class UIControl:
    def __init__(self, window):self.window=window

    def state(self):
        w=self.window;c=w.controller;t=c.motion_task;p=w.joint_pages
        with c._lock:
            nodes={str(n):asdict(s) for n,s in c.nodes.items()}
        return dict(selected_joint=c.selected_node, nodes=nodes,
            page=w.operation_stack.get_visible_child_name(), safety_confirmed=w.safety.get_active(),
            task_busy=t.busy, task_message=t.message, zero_busy=c.zero_home.busy,
            calibration_ready=t.cartesian.ready(), tcp_pose=t.cartesian.cached_pose(),
            canvas=copy.deepcopy(p.drawing_page.document()),
            joint_targets={str(n):v.get_value() for n,v in p.entries.items()},
            teaching_poses=copy.deepcopy(t.points),
            saved_routes=t.ai_actions.routes.public(),
            available_pages=list(PAGES), available_settings=copy.deepcopy(SETTINGS),
            available_commands=list(COMMANDS),
            observation='界面缓存快照，position_time为反馈时间；运动前原流程重新读取，不能假设缓存实时有效。')

    def idle(self):
        w=self.window;c=w.controller
        if (c.motion_task.busy or c.zero_home.busy or c._moving or c._pending is not None or
            w._initializing_zero or w._powering_off or w.joint_pages.record_pending):
            raise RuntimeError('请等待当前控制操作结束；停止全部仍可用')

    def perform(self, action, *, require_area_confirmation=True):
        a=validate_ui_action(action['name'],action['args']);name=a['name'];args=a['args']
        w=self.window;p=w.joint_pages;d=p.drawing_page;c=w.controller
        if name=='get_control_state':return self.state()
        if name=='activate_control' and args['command']=='stop_all':
            w._stop_all();return dict(status='停止请求已提交；须等待反馈确认停止')
        self.idle();c.motion_task.ai_actions.invalidate()
        if name=='show_control_page':p.show(args['page'])
        elif name=='replace_canvas':
            import pathlib,time
            from . import drawing
            from .joint_motion import atomic_json
            old=copy.deepcopy(d.document());new=copy.deepcopy(old)
            new['points']=[dict(xyz=xyz,mode='L',stroke=0) for xyz in args['waypoints_mm']]
            new=drawing.validate(new);drawing.segments(new)
            if old['points']:
                path=pathlib.Path('/home/uisrc/.config/f3p-control/ai-draft-backups')/('ai-draft-'+str(time.time_ns())+'.json')
                path.parent.mkdir(parents=True,exist_ok=True);atomic_json(path,old)
            else:path=None
            d.apply_ai_document(new);p.show('drawing')
            return dict(status='画布已更新，未启动运动',backup=str(path) if path else None,state=self.state())
        elif name=='set_pose_record_settings':
            p.name.set_text(args['name']);p.teach_speed.set_value(args['speed_deg_s']);p.dwell.set_value(args['dwell_s'])
        elif name=='set_control_setting':
            key=args['setting'];v=args['value']
            if key=='selected_joint':c.select_motor(v)
            else:
                widgets={'motor_rpm':w.speed_adjustment, 'motor_acceleration':w.acceleration_adjustment,
                    'joint_speed':p.speed, 'tcp_speed':d.speed, 'drawing_joint_speed':d.joint_speed,
                    'drawing_acceleration':d.acc, 'slice_position':d.cut,
                    'auto_orientation':d.auto_orientation, 'independent_acceleration':d.acc_override,
                    'shared_direction':d.direction, 'slice_plane':d.plane, 'drawing_mode':d.mode}
                widget=widgets[key]
                if not widget.get_sensitive():raise RuntimeError('该界面设置目前不可操作')
                if type(v) is bool:widget.set_active(v)
                elif isinstance(v,str):widget.set_active_id(v)
                else:widget.set_value(v)
        else:
            cmd=args['command']
            if require_area_confirmation and cmd in ('enable_selected','home_all','execute_canvas','play_teaching') and not w.safety.get_active():
                raise RuntimeError('请操作者先确认实际运动区域安全；AI不能代为勾选')
            functions={
                'enable_selected':c.enable, 'disable_selected':c.disable,
                'open_zero_settings':w._open_zero_home, 'open_wifi':lambda:w._open_cloud('wifi'),
                'open_vision':w._open_vision, 'view_logs':w._record_view,
                'start_logging':w._record_start, 'end_logging':w._record_export,
                'open_position_settings':p.configure, 'open_calibration':p.cartesian_page.calibrate,
                'request_shutdown':w._confirm_shutdown,
                'save_canvas':lambda:d.file(False), 'load_canvas':lambda:d.file(True),
            }
            if cmd not in functions:raise ValueError('异步动作须经任务完成回调执行')
            functions[cmd]()
        return dict(status='界面操作已提交', state=self.state())
