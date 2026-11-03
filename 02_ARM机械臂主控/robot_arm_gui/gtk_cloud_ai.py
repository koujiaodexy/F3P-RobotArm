"""Board-local network, chat and explicitly confirmed robot proposals."""
import json
import os
import pathlib
import tempfile
import threading
import time
import copy
import urllib.error

from gi.repository import Gtk, GLib
from .cloud_setup import Setup
from .ai_arm_control import tools, validate_action, route_document
from .joint_motion import atomic_json
from .ai_chat_client import DEFAULT_MODEL, conversation, compact_state, recent_history, ConversationFailure, error_text
from .ai_ui_control import UIControl


class HotspotWindow(Setup):
    def __init__(self, parent):
        super().__init__(wifi_only=True, standalone=False)
        self.set_title('热点连接')
        self.set_transient_for(parent)
        self.connect('delete-event', lambda window, event: (window.hide(), True)[1])
        self.get_child().get_children()[0].set_text('连接手机热点')
        self.ssid._f3p_local_text = self.password._f3p_local_text = True
        from .gtk_touch import touch_window_header
        from .gtk_keyboard import NumericKeyboard
        touch_window_header(self)
        NumericKeyboard(self,desktop_osk=getattr(parent,'live_control',False),track_dialogs=False)


def request_chat(key, model, messages):
    from .ai_chat_client import completion
    answer = completion(key, model, messages, with_tools=False).get('content') or ''
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError('Empty answer')
    return answer


def request_arm_chat(key, model, messages):
    import urllib.request
    payload=dict(model=model,messages=messages,max_tokens=4096,stream=False,
                 thinking=dict(type='disabled'),tools=tools(),tool_choice='auto')
    request=urllib.request.Request('https://api.deepseek.com/chat/completions',
        data=json.dumps(payload,allow_nan=False).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    with urllib.request.urlopen(request,timeout=60) as response:
        value=json.loads(response.read(2*1024*1024).decode())
    message=value['choices'][0]['message'];calls=message.get('tool_calls') or []
    content=message.get('content') or ''
    if not isinstance(content,str):raise ValueError('Invalid answer')
    if not calls:
        if not content.strip():raise ValueError('Empty answer')
        return dict(text=content,action=None)
    if not isinstance(calls,list) or len(calls)!=1:raise ValueError('每轮只能提出一个动作，请拆开指令')
    call=calls[0]
    if call.get('type')!='function':raise ValueError('动作格式无效')
    fn=call['function']
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('重复动作参数')
            result[key]=value
        return result
    action=validate_action(fn['name'],json.loads(fn['arguments'],object_pairs_hook=unique))
    return dict(text=content or '已提出动作方案，等待本地检查。',action=action)


class ChatWindow(Gtk.Window):
    def __init__(self, parent, config_path=None):
        super().__init__(title='云端 AI · DeepSeek · 需要联网', transient_for=parent)
        self.set_default_size(780, 650)
        self.get_style_context().add_class('vision-window')
        self.connect('delete-event', lambda window, event: (window.hide(), True)[1])
        self.connect('destroy', self._destroyed)
        self.closed = False
        self.busy = False
        self.messages = []
        self.parent_control=parent
        self.task=getattr(getattr(parent,'controller',None),'motion_task',None)
        self.pending_action=None
        self.pending_document=None
        self.action_busy=False
        self.action_direction=None
        self.automatic_execution=True
        self.agent_active=False
        self.agent_cancel=threading.Event()
        self.tool_completion=None
        self.ui_control=UIControl(parent) if self.task else None
        self.config = pathlib.Path(config_path or '/home/uisrc/.config/f3p-cloud-ai/deepseek.json')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=16)
        self.add(box)
        header = Gtk.Box(spacing=12)
        source = Gtk.Label(label='云端 AI · 文字和控制状态发送至 DeepSeek', xalign=0)
        source.set_line_wrap(True)
        header.pack_start(source, True, True, 0)
        self.close_button = Gtk.Button(label='关闭窗口')
        self.close_button.set_size_request(132, 56)
        self.close_button.set_can_focus(False)
        self.close_button.connect('clicked', lambda _button: self.hide())
        header.pack_end(self.close_button, False, False, 0)
        box.pack_start(header, False, False, 0)
        self.key = Setup.entry(box, 'API 密钥', '')
        self.key.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.key.set_property('im-module', 'gtk-im-context-simple')
        toggle = Gtk.CheckButton(label='显示 API 密钥')
        toggle.set_active(True)
        toggle.connect('toggled', lambda button: self.key.set_visibility(button.get_active()))
        box.pack_start(toggle, False, False, 0)
        self.model = Setup.entry(box, '模型', DEFAULT_MODEL)
        self.model.set_input_purpose(Gtk.InputPurpose.URL)
        self.fast_reply=Gtk.CheckButton(label='快速回复（关闭深度思考）')
        self.fast_reply.set_active(True)
        box.pack_start(self.fast_reply,False,False,0)
        row = Gtk.Box(spacing=8)
        save = Gtk.Button(label='保存配置')
        save.connect('clicked', self.save_config)
        self.clear = Gtk.Button(label='新对话')
        self.clear.connect('clicked', self.clear_chat)
        row.pack_start(save, False, False, 0)
        row.pack_start(self.clear, False, False, 0)
        box.pack_start(row, False, False, 0)
        action_row=Gtk.Box(spacing=8)
        self.add_route=Gtk.Button(label='添加已保存线路')
        self.add_route.connect('clicked',self.choose_route)
        self.confirm_action=Gtk.Button(label='确认执行动作')
        self.confirm_action.set_sensitive(False)
        self.confirm_action.set_no_show_all(True)
        self.confirm_action.connect('clicked',self.execute_action)
        cancel=Gtk.Button(label='取消方案')
        cancel.connect('clicked',self.cancel_action)
        stop=Gtk.Button(label='停止全部')
        stop.connect('clicked',self.stop_arm)
        for button in (self.add_route,cancel,stop):action_row.pack_start(button,False,False,0)
        action_row.pack_start(Gtk.Label(label='明确指令 · 检查通过自动执行'),False,False,0)
        box.pack_start(action_row,False,False,0)
        self.action_note=Gtk.Label(label='输入问题或明确的控制指令',xalign=0)
        self.action_note.set_line_wrap(True)
        self.action_note.set_max_width_chars(80)
        action_scroll=Gtk.ScrolledWindow()
        action_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        action_scroll.set_min_content_height(95)
        action_scroll.set_max_content_height(150)
        action_scroll.add(self.action_note)
        box.pack_start(action_scroll,False,True,0)
        self.history = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.history.set_left_margin(10)
        self.history.set_right_margin(10)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.history)
        box.pack_start(scroll, True, True, 0)
        box.pack_start(Gtk.Label(label='Ctrl + 空格切换中文输入', xalign=0), False, False, 0)
        self.input = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        input_scroll = Gtk.ScrolledWindow()
        input_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        input_scroll.set_min_content_height(80)
        input_scroll.add(self.input)
        box.pack_start(input_scroll, False, True, 0)
        self.send = Gtk.Button(label='发送')
        self.send.connect('clicked', self.send_message)
        box.pack_start(self.send, False, False, 0)
        self.status = Gtk.Label(label='运动指令检查通过后自动执行；可随时停止全部', xalign=0)
        self.status.set_line_wrap(True)
        box.pack_start(self.status, False, False, 0)
        from .gtk_touch import reserve_label
        reserve_label(self.status,1,2);reserve_label(self.action_note,1,2)
        try:
            value = json.loads(self.config.read_text())
            self.key.set_text(value.get('api_key', ''))
            self.model.set_text(value.get('model', DEFAULT_MODEL))
            self.fast_reply.set_active(value.get('response_mode','fast')=='fast')
        except (ValueError, OSError):
            pass

    def _destroyed(self, *_args):
        self.closed = True
        self.agent_cancel.set()
        self._tool_done(False,'AI窗口已关闭')
        if self.task:self.task.ai_actions.invalidate()

    def cancel_action(self,*_args):
        if self.action_busy:
            self.status.set_text('正在检查或执行；需要中断请点击“停止全部”。')
            return
        self.pending_action=None
        self.pending_document=None
        self.confirm_action.set_sensitive(False)
        if self.task:self.task.ai_actions.invalidate()
        self.action_note.set_text('方案已取消；可以重新提出动作。')

    def stop_arm(self,*_args):
        self.agent_cancel.set()
        self.pending_action=None;self.confirm_action.set_sensitive(False)
        if self.task:self.task.ai_actions.invalidate()
        if hasattr(self.parent_control,'_stop_all'):self.parent_control._stop_all()

    def _dispatch_agent_tool(self,action):
        if self.agent_cancel.is_set():return dict(ok=False,error='本轮已被操作者停止，不再执行后续操作')
        event=threading.Event();holder={}
        def complete(result):holder['result']=result;event.set()
        GLib.idle_add(self._start_agent_tool,action,complete)
        deadline=time.monotonic()+600
        while not event.wait(.1):
            if self.closed or self.agent_cancel.is_set():
                return dict(ok=False,error='操作者取消本轮；已启动任务的停止结果以本地控制状态为准')
            if time.monotonic()>deadline:
                self.agent_cancel.set();GLib.idle_add(self.stop_arm)
                return dict(ok=False,error='执行等待超时，已请求停止；不能视为完成')
        return holder['result']

    def _tool_done(self,ok,message):
        done=self.tool_completion;self.tool_completion=None
        if done:done(dict(ok=ok,result=message))

    def _start_agent_tool(self,action,complete):
        if self.closed or self.agent_cancel.is_set():
            complete(dict(ok=False,error='本轮已取消'));return False
        self.tool_completion=complete
        self.append('控制请求',json.dumps(action,ensure_ascii=False))
        try:
            name=action['name'];args=action['args']
            if name in ('move_tcp','jog_joint','move_joint','run_saved_route','draw_route','draw_auto_route'):
                self.prepare_action(action);return False
            command=args.get('command') if name=='activate_control' else None
            asynchronous={'refresh_angles':'refresh','capture_pose':'record',
                'prepare_canvas':'cart_drawing_prepare','execute_canvas':'cart_drawing_execute',
                'play_teaching':'play','preview_teaching':'cart_sequence_plan'}
            if command=='home_all' or command in asynchronous:
                self.ui_control.idle()
                self.action_busy=True
                def completed(ok,error):
                    GLib.idle_add(self._ui_task_finished,ok,error)
                if command=='home_all':
                    self.parent_control.controller.zero_home.start('home_all',1,completed)
                else:
                    params={};p=self.parent_control.joint_pages
                    if command=='refresh_angles':params=dict(nodes=list(range(1,7)),fill_targets=False)
                    elif command=='capture_pose':
                        params=dict(name=p.name.get_text().strip() or 'AI姿态 '+str(len(self.task.points)+1),
                            speed=p.teach_speed.get_value(),dwell=p.dwell.get_value())
                    elif command in ('prepare_canvas','execute_canvas'):
                        params=dict(document=p.drawing_page.document())
                        if command=='execute_canvas':params['clearance_confirmed']=True
                    self.task.start(asynchronous[command],completed,**params)
                return False
            result=self.ui_control.perform(action,require_area_confirmation=False)
            # Enable/disable/select requests are acknowledged by existing CAN owner.
            if self.parent_control.controller._pending is not None:
                GLib.timeout_add(50,self._ui_request_finished,action,time.monotonic()+10,result)
            else:self._tool_done(True,result)
        except Exception as exc:
            self.action_busy=False;self._tool_done(False,str(exc))
        return False

    def _ui_request_finished(self,action,deadline,result):
        if self.closed or self.agent_cancel.is_set():self._tool_done(False,'本轮已取消');return False
        c=self.parent_control.controller
        if c._pending is not None:
            if time.monotonic()<deadline:return True
            self._tool_done(False,'控制反馈超时');return False
        state=c.nodes[c.selected_node]
        command=action['args'].get('command')
        error=state.error if state.error not in ('','无') else ''
        if command=='enable_selected' and not state.enabled:error=error or '电机使能未确认'
        if command=='disable_selected' and state.enabled:error=error or '电机失能未确认'
        self._tool_done(not bool(error),error or dict(result=result,state=self.ui_control.state()))
        return False

    def _ui_task_finished(self,ok,error):
        self.action_busy=False
        self.parent_control.joint_pages.update()
        message=error if not ok else dict(message=self.task.message,state=self.ui_control.state())
        self.append('控制结果',error if not ok else '任务完成，已回传控制状态。')
        self._tool_done(ok,message)
        return False

    def choose_route(self,*_args):
        if not self.task or self.busy or self.action_busy:return
        dialog=Gtk.FileChooserDialog(title='添加已保存线路',transient_for=self,action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'添加',Gtk.ResponseType.OK)
        try:
            if dialog.run()==Gtk.ResponseType.OK:
                self.cancel_action()
                ident=self.task.ai_actions.routes.add(dialog.get_filename())
                item=next(v for v in self.task.ai_actions.routes.public() if v['route_id']==ident)
                self.append('线路目录',item['name']+' · '+ident+' · '+str(item['point_count'])+'点')
                self.status.set_text('线路已添加，可以告诉AI运行该线路。当前画布草稿保留。')
        except Exception as exc:self.status.set_text(str(exc))
        finally:dialog.destroy()

    def _direction(self):
        return self.parent_control.joint_pages.drawing_page.direction.get_active_id()

    def _available(self):
        p=self.parent_control
        if (not self.task or self.task.busy or p._initializing_zero or p._powering_off
                or p.joint_pages.record_pending):raise RuntimeError('请等待当前机械臂操作结束')

    def _run_action(self,operation,**params):
        self._available()
        self.action_busy=True
        self.confirm_action.set_sensitive(False)
        self.send.set_sensitive(False);self.clear.set_sensitive(False);self.add_route.set_sensitive(False)
        def complete(ok,error):GLib.idle_add(self.action_finished,operation,ok,error)
        try:self.task.start(operation,complete,**params)
        except Exception:
            self.action_busy=False
            self.send.set_sensitive(True);self.clear.set_sensitive(True);self.add_route.set_sensitive(True)
            raise

    def prepare_action(self,action):
        self._available()
        self.action_direction=self._direction()
        self.pending_document=None
        settings=None
        if action['name'] in ('draw_route','draw_auto_route'):
            page=self.parent_control.joint_pages.drawing_page
            current=copy.deepcopy(page.document())
            settings={key:current[key] for key in ('trajectory_acceleration','allow_orientation_adjustment')}
            settings.update(placement_plane=page.plane.get_active_id(),placement_fixed_mm=page.cut.get_value())
            if action['name']=='draw_auto_route':
                self.auto_placement_draft=current
                self.action_note.set_text('正在当前工作面自动寻找整条可绘位置…')
                self._run_action('ai_prepare',action=action,direction=self.action_direction,drawing_settings=settings)
                return
            document=route_document(action,self.action_direction,settings)
            if current['points']:
                backup=self.config.parent.parent/'f3p-control'/'ai-draft-backups'/('ai-draft-'+str(time.time_ns())+'.json')
                backup.parent.mkdir(parents=True,exist_ok=True)
                atomic_json(backup,current)
                self.append('草稿备份',str(backup))
            page.apply_ai_document(document)
            if hasattr(self.parent_control,'operation_stack'):
                self.parent_control.operation_stack.set_visible_child_name('drawing')
            self.pending_document=copy.deepcopy(page.document())
            if self.pending_document!=document:raise RuntimeError('画布参数与AI线路不一致，请重新检查')
        self.action_note.set_text('正在检查动作，尚未执行…')
        self._run_action('ai_prepare',action=action,direction=self.action_direction,drawing_settings=settings)

    def execute_action(self,*_args):
        if not self.pending_action or (self.busy and not self.agent_active) or self.action_busy:return
        try:
            if self._direction()!=self.action_direction:raise RuntimeError('共享朝向已改变，请重新提出方案')
            if self.pending_document is not None and self.parent_control.joint_pages.drawing_page.document()!=self.pending_document:
                raise RuntimeError('画布线路或绘图参数已改变，请重新提出方案')
            receipt=self.task.ai_actions.pending
            if receipt and receipt['action']['name']=='draw_auto_route':
                page=self.parent_control.joint_pages.drawing_page
                if page.plane.get_active_id()!=receipt['placement_plane'] or page.cut.get_value()!=receipt['placement_fixed_mm']:
                    raise RuntimeError('工作面已改变，请重新自动选位')
            token=self.pending_action;self.pending_action=None
            self._run_action('ai_execute',token=token,confirmed=True)
            self.status.set_text('检查通过，机械臂正在执行；完成后会核验到位。')
        except Exception as exc:
            self.cancel_action();self.status.set_text(str(exc))
            self.action_note.set_text('未启动：'+str(exc));self.append('控制结果','未启动：'+str(exc))
            self.messages.append(dict(role='user',content='本地检查拒绝启动：'+str(exc)))
            self._tool_done(False,str(exc))

    def action_finished(self,operation,ok,error):
        if self.closed:return False
        self.action_busy=False
        self.send.set_sensitive(True);self.clear.set_sensitive(True);self.add_route.set_sensitive(True)
        preview=self.task.ai_actions.preview
        if not ok:
            self.cancel_action();self.action_note.set_text('动作检查/执行失败：'+error)
            self.status.set_text(error);self.append('控制结果',error)
            self.messages.append(dict(role='user',content='本地动作检查或执行失败，尚不能视为完成：'+error))
            self._tool_done(False,error)
        elif operation=='ai_prepare' and preview:
            receipt=self.task.ai_actions.pending
            if receipt and receipt['action']['name']=='draw_auto_route':
                page=self.parent_control.joint_pages.drawing_page
                current=copy.deepcopy(page.document())
                if (current!=self.auto_placement_draft or page.plane.get_active_id()!=receipt['placement_plane'] or
                        page.cut.get_value()!=receipt['placement_fixed_mm']):
                    self.cancel_action();self._tool_done(False,'自动选位期间工作面改变，请重试');return False
                if current['points']:
                    backup=self.config.parent.parent/'f3p-control'/'ai-draft-backups'/('ai-draft-'+str(time.time_ns())+'.json')
                    backup.parent.mkdir(parents=True,exist_ok=True);atomic_json(backup,current)
                page.apply_ai_document(receipt['document'])
                self.pending_document=copy.deepcopy(page.document())
                if self.pending_document!=receipt['document']:
                    self.cancel_action();self._tool_done(False,'画布参数与自动选位线路不一致');return False
                # Applying widgets invalidates the drawing preview; this is a
                # completed non-progressive report for the identical document.
                self.task.cartesian.drawing.report=receipt['report']
            self.pending_action=preview['token']
            self.action_note.set_text(preview['summary'])
            self.confirm_action.set_sensitive(not self.automatic_execution)
            self.append('动作方案',preview['summary'])
            self.status.set_text('检查通过，正在启动运动。')
            if self.automatic_execution:self.execute_action()
        else:
            self.pending_action=None;self.action_note.set_text(self.task.message)
            self.status.set_text(self.task.message);self.append('控制结果',self.task.message)
            self.messages.append(dict(role='user',content='本地控制执行结果：'+self.task.message))
            if self.tool_completion:self._tool_done(True,dict(message=self.task.message,state=self.ui_control.state()))
        return False

    def arm_context(self):
        if not self.task:return ''
        from .zero_home import RATIOS
        c=self.task.controller
        page=self.parent_control.joint_pages.drawing_page
        document=page.document() if hasattr(page,'document') else None
        canvas=(dict(point_count=len(document['points']),first_points=document['points'][:8],
                     trajectory_acceleration=document['trajectory_acceleration'],
                     allow_orientation_adjustment=document['allow_orientation_adjustment']) if document else None)
        with c._lock:
            values=dict(calibration_ready=self.task.cartesian.ready(),
                joint_angles_deg={str(n):s.motor_angle/RATIOS[n] if s.motor_angle is not None else None for n,s in c.nodes.items()},
                tcp_pose=self.task.cartesian.cached_pose(),shared_direction=self._direction(),
                  canvas=canvas,drawing_surface=dict(plane=page.plane.get_active_id(),fixed_mm=page.cut.get_value(),tcp_speed_mm_s=page.speed.get_value(),joint_speed_deg_s=page.joint_speed.get_value()),
                saved_routes=self.task.ai_actions.routes.public())
        values['control_interface']=compact_state(self.ui_control.state())
        return ('你是机械臂操作助手，可以读取控制界面和调用提供的界面工具。先理解用户目标，读取状态后逐步操作，依据真实工具结果回答。'
              '允许连续调用工具；每个工具等本地完成再执行下一个。使能、失能、回零、回放、运动和参数修改必须来自用户明确要求，不能为完成其他任务自行使能。'
              '只查看/解释/不运行时禁止改变界面参数或启动运动，可以读取状态。不要把打开对话框或提交请求声称为已完成。'
              '用户已选择运动检查通过直接执行，无需触屏确认；零点、标定、限位的变更保留原人工确认。'
              '工具方案通过本地检查后会自动执行，不能提前声称已执行；参数不明确必须先询问。'
            '用户要求自动选位置时，使用draw_auto_route由本地模型搜索，不要求用户给中心坐标；保持当前工作面、切片高度、尺寸和朝向。缺少图形或尺寸才询问。当前坐标执行前本地重新读取。'
            '末端定位使用绝对mm坐标、J方式和共享朝向；关节绝对定位用move_joint，相对移动用jog_joint，不按10度拆分。默认关节速度5度/秒。'
            '不允许自行修改标定、零点、限位或使能。所有目标和路径Z必须大于0。'
              '画线路使用draw_route：连续绝对XYZ点，直线用端点，常规曲线采样建议32～48点，复杂曲线最多128点；保留共享朝向、绘图加速度和自动朝向选项。'
              '用户明确指定位置用draw_route；用户要求自行寻找合适位置用draw_auto_route，输入二维毫米形状，当前工作面切片和共享朝向保持。未指定速度沿用当前画布速度。采样工作区只是模型提示，不代表识别到现场障碍物；本地整条规划通过后自动定位起点并运行。'
            '已保存线路必须由操作者添加，只能引用目录的route_id。当前状态：'+json.dumps(values,ensure_ascii=False,allow_nan=False))

    def save_config(self, *_args):
        key, model = self.key.get_text().strip(), self.model.get_text().strip()
        if not key or not model:
            self.status.set_text('请填写 API 密钥和模型。')
            return False
        try:
            self.config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, name = tempfile.mkstemp(prefix='.deepseek-', dir=str(self.config.parent))
            try:
                with os.fdopen(fd, 'w') as stream:
                    json.dump(dict(api_key=key, model=model,response_mode='fast' if self.fast_reply.get_active() else 'deep'), stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, str(self.config))
            finally:
                if os.path.exists(name): os.unlink(name)
        except OSError:
            self.status.set_text('配置保存失败，请检查文件权限。')
            return False
        self.status.set_text('配置已保存。')
        return True

    def append(self, speaker, text):
        buffer = self.history.get_buffer()
        buffer.insert(buffer.get_end_iter(), speaker + '\n' + text + '\n\n')
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.history.scroll_mark_onscreen(mark)
        buffer.delete_mark(mark)

    def clear_chat(self, *_args):
        if self.busy or self.action_busy or self.agent_active: return
        self.cancel_action()
        self.messages = []
        self.history.get_buffer().set_text('')
        self.status.set_text('已开始新对话。')

    def send_message(self, *_args):
        if self.busy or self.action_busy or self.agent_active: return
        buffer = self.input.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True).strip()
        if not text:
            self.status.set_text('请先输入消息。')
            return
        if not self.save_config(): return
        self.append('请求来源', '云端 AI · DeepSeek API · 模型 ' + self.model.get_text().strip())
        self.cancel_action()
        key, model = self.key.get_text().strip(), self.model.get_text().strip()
        # Keep complete recent pairs; failed turns are not added to the context.
        # Keep complete tool conversations; slicing individual messages can orphan tool results.
        messages = recent_history(self.messages + [dict(role='user', content=text)])
        reply_mode='fast' if self.fast_reply.get_active() else 'deep'
        api_messages=([dict(role='system',content=self.arm_context())] if self.task else [])+messages
        self.busy = True
        self.agent_active=True;self.agent_cancel.clear()
        self.send.set_sensitive(False)
        self.clear.set_sensitive(False)
        self.append('我', text)
        buffer.set_text('')
        self.status.set_text('正在等待 DeepSeek 回复…')
        def progress(message):
            def show():
                if not self.closed and self.agent_active:self.status.set_text(message)
                return False
            GLib.idle_add(show)
        def work():
            began=time.monotonic()
            try:
                answer = conversation(key,model,api_messages,self._dispatch_agent_tool,self.agent_cancel.is_set,mode=reply_mode,progress=progress) if self.task else request_chat(key, model, messages)
                error = None
            except Exception as exc:
                error=error_text(exc)
                answer=(dict(history=exc.history,completed_tools=exc.completed_tools) if isinstance(exc,ConversationFailure) else None)
                cause=exc.cause if isinstance(exc,ConversationFailure) else exc
                print('AI_REPLY_FAILED',json.dumps(dict(error_type=type(cause).__name__,http_status=getattr(cause,'code',None),seconds=round(time.monotonic()-began,3),completed_tools=getattr(exc,'completed_tools',0))),flush=True)
                if isinstance(cause,urllib.error.HTTPError):cause.close()
            GLib.idle_add(self.finish, messages, answer, error, text)
        threading.Thread(target=work, daemon=True).start()

    def finish(self, messages, answer, error, text):
        if self.closed: return False
        self.busy = False
        self.agent_active=False
        self.send.set_sensitive(True)
        self.clear.set_sensitive(True)
        if error:
            completed_tools=answer.get('completed_tools',0) if isinstance(answer,dict) else 0
            if completed_tools:
                self.messages=[m for m in answer['history'] if m['role']!='system']
                self.messages.append(dict(role='assistant',content=error))
            self.append('提示', error)
            buffer = self.input.get_buffer()
            # Preserve text typed while waiting; restore failed input only if empty.
            if not completed_tools and not buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True).strip():
                buffer.set_text(text)
            self.status.set_text(error)
        else:
            action=answer.get('action') if isinstance(answer,dict) else None
            answer_text=answer['text'] if isinstance(answer,dict) else answer
            # Tools are proposals: record a plain text summary, never a fake tool result.
            if action:answer_text+='\n提出方案：'+json.dumps(action,ensure_ascii=False,allow_nan=False)
            self.messages = ([m for m in answer['history'] if m['role']!='system']
                if isinstance(answer,dict) and 'history' in answer else messages + [dict(role='assistant', content=answer_text)])
            self.append('DeepSeek', answer_text)
            if action:
                try:self.prepare_action(action)
                except Exception as exc:self.cancel_action();self.status.set_text(str(exc));self.action_note.set_text(str(exc))
            else:self.status.set_text('已收到回复；可以继续提问。')
        return False
