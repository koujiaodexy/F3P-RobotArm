"""Joint controls inside the persistent main window, sharing its CAN owner."""
import copy
from .gtk_touch import set_button_label,set_status_text
from gi.repository import Gtk, GLib
from .zero_home import RATIOS


def label(text):
    return Gtk.Label(label=text, xalign=0)


class JointPages:
    def __init__(self, window):
        self.window, self.task = window, window.controller.motion_task
        self.entries, self.checks, self.actual, self.axis_status = {}, {}, {}, {}
        self.controls, self.motion_buttons, self.point_widgets = [], [], []
        self.point_key = None
        self.notices, self.safety_checks = [], [window.safety]
        self.record_pending = False
        self.record_generation = 0
        self.tabs = {}
        for caption, name in (('手动点动', 'control'), ('关节定位', 'position'), ('末端定位 / 绘图', 'drawing'), ('示教回放', 'teaching')):
            self.tabs[name] = self.button(window.operation_tabs, caption, lambda n=name: self.show(n), tracked=False)
        self.name = Gtk.Entry()
        self.name._f3p_local_text = True
        self.name.set_width_chars(12)
        self.name.set_max_width_chars(16)
        self.name.set_max_length(64)
        self.name.set_placeholder_text('姿态名称')
        window.pose_toolbar.pack_start(label('姿态记录'), False, False, 0)
        window.pose_toolbar.pack_start(self.name, False, False, 0)
        self.record_button = self.button(window.pose_toolbar, '记录当前姿态', self.record, tracked=False)
        self.count_label = label('')
        window.pose_toolbar.pack_start(self.count_label, True, True, 0)
        self.button(window.pose_toolbar, '姿态列表 / 回放', lambda: self.show('teaching'), tracked=False)
        for name in ('position', 'teaching'):
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            page.get_style_context().add_class('joint-panel')
            notice = label('')
            notice.set_line_wrap(False)
            notice.set_max_width_chars(78)
            notice.set_ellipsize(3)
            page.pack_start(notice, False, False, 0)
            self.notices.append(notice)
            (self.position if name == 'position' else self.teaching)(page)
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_overlay_scrolling(False)
            scroll.add(page)
            window.operation_stack.add_named(scroll, name)
        from .gtk_cartesian import CartesianPage
        self.cartesian_page=CartesianPage(self)
        from .gtk_drawing import DrawingPage
        self.drawing_page=DrawingPage(self)
        from .gtk_combined import CombinedPage
        self.combined_page=CombinedPage(self)
        window.safety.connect('toggled', self.safety_changed)
        self.show('drawing')

    def button(self, box, caption, action, tracked=True, motion=False):
        b=Gtk.Button(label=caption)
        b.get_style_context().add_class('record-action')
        b.connect('clicked', lambda _b: self.window._command(action))
        box.pack_start(b, False, False, 0)
        if tracked: self.controls.append(b)
        if motion: self.motion_buttons.append(b)
        return b

    def show(self, name):
        if name=='cartesian':name='drawing'
        if self.window._held_node is not None:
            self.window._stop()
        self.window.operation_stack.set_visible_child_name(name)
        for widget in (self.window.diagnostics,self.window.recording_row,self.window.pose_toolbar,self.window.motor_cards):
            widget.set_no_show_all(False);widget.set_visible(True)
        for key,b in self.tabs.items():
            context=b.get_style_context()
            (context.add_class if key==name else context.remove_class)('active')
        self.update()

    def position(self, page):
        grid=Gtk.Grid(column_spacing=12, row_spacing=6)
        for col,text in enumerate(('参与', '实际角度 / °', '目标角度 / °', '范围 / 条件')):
            grid.attach(label(text), col, 0, 1, 1)
        for n in range(1,7):
            check=Gtk.CheckButton(label=f'J{n}')
            check.set_active(n<=5 or n in self.task.controller.backend.position_target_nodes and n in self.task.pulses_per_rev)
            current=label('待读取')
            bounds=self.window.controller.joint_limits.bounds.get(n)
            # J6's input is bounded only by the protocol's representable pulses.
            maximum=0xFFFFFFFF*360/65536/RATIOS[n]
            spin=Gtk.SpinButton.new_with_range(*((bounds or (-maximum,maximum)) if n!=4 or not self.window.controller.joint_limits.coupled else (-maximum,maximum)), .1)
            spin.set_value(0)
            spin.set_digits(2)
            spin.set_width_chars(11)
            info=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            info.pack_start(label('J3≤34° 无限位；超过后 '+str(bounds[0])+' ～ '+str(bounds[1]) if n==4 and self.window.controller.joint_limits.coupled else f'{bounds[0]} ～ {bounds[1]}' if bounds else '无限位 · 可定位'),False,False,0)
            status=label('')
            status.set_max_width_chars(35)
            status.set_ellipsize(3)
            info.pack_start(status,False,False,0)
            for col,widget in enumerate((check,current,spin,info)): grid.attach(widget,col,n,1,1)
            self.checks[n],self.entries[n],self.actual[n],self.axis_status[n]=check,spin,current,status
            check.connect('toggled',lambda _c:self.update())
        page.pack_start(grid,False,False,0)
        row=Gtk.Box(spacing=8)
        row.pack_start(label('关节速度 °/秒'),False,False,0)
        self.speed=Gtk.SpinButton.new_with_range(1,20,1)
        self.speed.set_value(5)
        row.pack_start(self.speed,False,False,0)
        self.button(row,'定位参数',self.configure)
        self.button(row,'刷新角度',self.refresh)
        self.button(row,'当前→目标',lambda:self.refresh(fill_targets=True))
        self.button(row,'预检目标',lambda:self.run('preflight',targets=self.targets(),speed=self.speed.get_value()))
        self.button(row,'执行定位',lambda:self.run('move',targets=self.targets(),speed=self.speed.get_value()),motion=True)
        page.pack_start(row,False,False,0)
        self.plan_label=label('选择关节并填写目标角度。')
        self.plan_label.set_line_wrap(False)
        self.plan_label.set_ellipsize(3)
        self.plan_label.set_max_width_chars(80)
        page.pack_start(self.plan_label,False,False,0)
        plan_details=Gtk.Expander(label='定位速度详情')
        self.plan_detail=label('尚无预检结果')
        self.plan_detail.set_line_wrap(True)
        plan_details.add(self.plan_detail)
        page.pack_start(plan_details,False,False,0)
        safety=Gtk.CheckButton(label=self.window.safety.get_label())
        safety.set_active(self.window.safety.get_active())
        safety.connect('toggled',self.safety_changed)
        self.safety_checks.append(safety)
        page.pack_end(safety,False,False,0)

    def safety_changed(self, check):
        for other in self.safety_checks:
            if other is not check and other.get_active()!=check.get_active():other.set_active(check.get_active())
        self.update()

    def teaching(self,page):
        row=Gtk.Box(spacing=8)
        row.pack_start(label('新姿态速度 °/秒'),False,False,0)
        self.teach_speed=Gtk.SpinButton.new_with_range(1,20,1)
        self.teach_speed.set_value(5)
        row.pack_start(self.teach_speed,False,False,0)
        row.pack_start(label('停留 秒'),False,False,0)
        self.dwell=Gtk.SpinButton.new_with_range(0,30,.5)
        self.dwell.set_digits(1)
        row.pack_start(self.dwell,False,False,0)
        self.play_button=self.button(row,'顺序播放一次',lambda:self.run('play'),motion=True)
        page.pack_start(row,False,False,0)
        row=Gtk.Box(spacing=8)
        row.pack_start(label('融合偏差 °'),False,False,0)
        self.blend_radius=Gtk.SpinButton.new_with_range(0,5,.1)
        self.blend_radius.set_digits(1)
        self.blend_radius.set_value(.5)
        row.pack_start(self.blend_radius,False,False,0)
        self.blend_button=self.button(row,'融合轨迹预览',self.preview_blend)
        self.sequence_button=self.button(row,'J/L/C整段预览',lambda:self.run('cart_sequence_plan'))
        note=label('融合仅预览；停留点和终点停车')
        note.set_ellipsize(3)
        row.pack_start(note,True,True,0)
        page.pack_start(row,False,False,0)
        scroll=Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.list=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        scroll.add(self.list)
        page.pack_start(scroll,True,True,0)
        safety=Gtk.CheckButton(label=self.window.safety.get_label())
        safety.set_active(self.window.safety.get_active())
        safety.connect('toggled',self.safety_changed)
        self.safety_checks.append(safety)
        page.pack_end(safety,False,False,0)

    def targets(self):
        for e in self.entries.values():e.update()
        return {n:e.get_value() for n,e in self.entries.items() if self.checks[n].get_active()}

    def refresh(self,fill_targets=False):
        self.run('refresh',nodes=[n for n in self.entries if self.checks[n].get_active()],fill_targets=fill_targets)

    def record(self):
        c=self.window.controller
        if self.record_pending or self.task.busy:raise RuntimeError('正在记录或执行任务')
        if c.zero_home.busy or self.window._initializing_zero or self.window._powering_off:
            raise RuntimeError('请等待当前零点操作结束')
        params=dict(name=self.name.get_text().strip() or f'姿态 {len(self.task.points)+1}',
                    speed=self.teach_speed.get_value(),dwell=self.dwell.get_value())
        if c._moving or c._all_stopping:
            self.window._clear_hold()
            self.record_pending=True
            generation=self.record_generation
            self.update()
            def stopped(ok):
                def apply():
                    if generation!=self.record_generation:return False
                    self.record_pending=False
                    if self.window._display_mailbox.closed:return False
                    if ok and not c._moving and not c._all_stopping:
                        self.window._command(lambda:self.run('record',**params))
                    else:self.window._show_error('停止未确认，未保存姿态')
                    self.update()
                    return False
                GLib.idle_add(apply)
            c.stop_all(stopped)
        else:self.run('record',**params)

    def cancel_record(self):
        self.record_generation+=1
        self.record_pending=False
        self.update()

    def run(self,operation,**params):
        logged_params=dict(params)
        if 'document' in logged_params:
            d=logged_params['document'];logged_params['document']={key:d.get(key) for key in ('schema','direction','speed','joint_speed','trajectory_acceleration')}
            logged_params['document']['point_count']=len(d.get('points',[]))
        print('JOINT_UI_REQUEST',dict(operation=operation,params=logged_params,
              task_busy=self.task.busy,zero_busy=self.window.controller.zero_home.busy,
              moving=self.window.controller._moving),flush=True)
        if self.window._initializing_zero or self.window._powering_off or self.record_pending:
            raise RuntimeError('请等待当前操作结束')
        if operation in ('move','return','play','cart_move_endpoint','cart_execute_path','cart_drawing_execute','cart_adjust_orientation') and not self.window.safety.get_active():
            raise RuntimeError('请先确认运动区域安全')
        if operation in ('cart_execute_path','cart_drawing_execute','cart_adjust_orientation'):params['clearance_confirmed']=self.window.safety.get_active()
        def finished(ok,error):
            def apply():
                if self.window._display_mailbox.closed:return False
                if ok and (operation=='capture' or operation=='refresh' and params.get('fill_targets')):
                    for n,value in self.task.targets.items():self.entries[n].set_value(value)
                self.update()
                if ok and operation=='blend_preview':
                    self.show_blend_preview()
                if operation.startswith('cart_'):
                    if ok:self.cartesian_page.finished(operation)
                    else:self.cartesian_page.after_refresh=None
                if not ok and '取消' not in error:
                    self.window._show_error(error)
                return False
            GLib.idle_add(apply)
        self.task.start(operation,finished,**params)
        self.update()

    def preview_blend(self):
        self.blend_radius.update()
        self.run('blend_preview',radius=self.blend_radius.get_value())

    def make_blend_dialog(self):
        from .gtk_blend_preview import BlendPreviewDialog
        if self.task.blend_preview is None:
            raise RuntimeError('尚无融合规划结果')
        return BlendPreviewDialog(self.window,self.task.blend_preview)

    def show_blend_preview(self):
        dialog=self.make_blend_dialog()
        try:
            dialog.show_all()
            dialog.run()
        finally:
            dialog.destroy()

    def configure(self):
        from .gtk_joint_motion import PositionConfigDialog
        d=PositionConfigDialog(self.window,self.task.pulses_per_rev)
        try:
            d.show_all()
            if d.run()==Gtk.ResponseType.OK:self.run('configure',scales=d.values(),confirmed=d.confirmed.get_active())
        finally:d.destroy()

    def edit(self,index):
        p=copy.deepcopy(self.task.points[index])
        d=Gtk.Dialog(title='编辑姿态',transient_for=self.window,modal=True)
        d.add_buttons('取消',Gtk.ResponseType.CANCEL,'保存',Gtk.ResponseType.OK)
        box=d.get_content_area();box.set_border_width(12);box.set_spacing(8)
        name=Gtk.Entry();name._f3p_local_text=True;name.set_text(p['name']);name.set_max_length(64)
        speed=Gtk.SpinButton.new_with_range(1,20,1);speed.set_value(p['speed_deg_s'])
        dwell=Gtk.SpinButton.new_with_range(0,30,.5);dwell.set_value(p['dwell_seconds'])
        for caption,widget in (('名称',name),('速度 °/秒',speed),('停留 秒',dwell)):
            row=Gtk.Box(spacing=8);row.pack_start(label(caption),False,False,0);row.pack_start(widget,True,True,0);box.pack_start(row,False,False,0)
        motion=p.get('motion',dict(mode='J',orientation='interpolate',tcp_speed_mm_s=10))
        mode=Gtk.ComboBoxText()
        for key,caption in (('J','关节点到点 J'),('L','轴端直线 L'),('C','轴端圆弧 C')):mode.append(key,caption)
        mode.set_active_id(motion['mode'])
        orientation=Gtk.ComboBoxText();orientation.append('hold','保持起点方向');orientation.append('interpolate','插值至记录方向');orientation.set_active_id(motion['orientation'])
        tcp_speed=Gtk.SpinButton.new_with_range(.1,1000,.1);tcp_speed.set_digits(1);tcp_speed.set_value(motion['tcp_speed_mm_s'])
        for caption,widget in (('进入方式',mode),('方向策略',orientation),('末端速度 mm/s',tcp_speed)):
            row=Gtk.Box(spacing=8);row.pack_start(label(caption),False,False,0);row.pack_start(widget,True,True,0);box.pack_start(row,False,False,0)
        via=[];row=Gtk.Box(spacing=8)
        for caption,value in zip(('经过X mm','Y mm','Z mm'),motion.get('via_mm',[0,0,0])):
            widget=Gtk.SpinButton.new_with_range(-2000,2000,.1);widget.set_digits(2);widget.set_width_chars(8);widget.set_value(value)
            row.pack_start(label(caption),False,False,0);row.pack_start(widget,False,False,0);via.append(widget)
        box.pack_start(row,False,False,0)
        note=label('L/C可规划预览，连续实机执行尚未开放；已有精确到点仅执行J段。');note.set_line_wrap(True);box.pack_start(note,False,False,0)
        # Bind before mapping: the pose name initially receives focus, so the
        # periodic transient-window scan is too late to prevent GNOME's OSK.
        from .gtk_keyboard import NumericKeyboard
        NumericKeyboard(d,desktop_osk=self.window.live_control,track_dialogs=False)
        try:
            d.show_all()
            if d.run()==Gtk.ResponseType.OK:
                for e in via:e.update()
                self.run('edit',index=index,name=name.get_text(),speed=speed.get_value(),dwell=dwell.get_value(),
                    motion=dict(mode=mode.get_active_id(),orientation=orientation.get_active_id(),tcp_speed_mm_s=tcp_speed.get_value(),via_mm=[e.get_value() for e in via]))
        finally:d.destroy()

    def _playable(self,point):
        c=self.window.controller
        nodes=[int(n) for n in point['angles_deg']]
        return (point.get('motion',{}).get('mode','J')=='J' and c.backend.supports_position_targets and not self.task.config_error
                and all(n in c.backend.position_target_nodes and n in self.task.pulses_per_rev for n in nodes)
                and self.task.point_valid(point))

    def update(self):
        if not hasattr(self,'play_button'):return
        view=self.window.operation_stack.get_visible_child_name()
        workspace=getattr(self.window,'workspace',None)
        workspace_name=workspace.get_visible_child_name() if workspace is not None else 'control'
        if workspace_name=='drawing-fullscreen':view='drawing'
        elif workspace_name!='control':view=None
        c=self.window.controller
        busy=(self.task.busy or c.zero_home.busy or c._pending or c._switching or c._all_stopping
              or c._moving or self.window._initializing_zero or self.window._powering_off or self.record_pending)
        selected=[n for n,check in self.checks.items() if check.get_active()]
        ready=(c.backend.supports_position_targets and not self.task.config_error and bool(selected)
               and all(n in c.backend.position_target_nodes and n in self.task.pulses_per_rev for n in selected))
        for b in self.controls:b.set_sensitive(not busy)
        for b in self.motion_buttons:b.set_sensitive(not busy and ready and self.window.safety.get_active())
        if view=='teaching':
            self.play_button.set_sensitive(not busy and self.window.safety.get_active() and bool(self.task.points)
                                          and all(self._playable(p) for p in self.task.points))
            self.blend_button.set_sensitive(not busy and bool(self.task.points) and all(self.task.point_valid(p) for p in self.task.points))
            self.sequence_button.set_sensitive(not busy and self.task.cartesian.ready() and bool(self.task.points))
        set_button_label(self.record_button,'停止并记录姿态' if c._moving else '记录当前姿态')
        self.record_button.set_sensitive(not (self.task.busy or c.zero_home.busy or c._switching or self.window._initializing_zero or self.window._powering_off or self.record_pending)
                                         and (not c._pending or c._moving or c._all_stopping))
        set_status_text(self.count_label,f'{len(self.task.points)} 个姿态' + (' · 停止确认中' if self.record_pending else ''))
        for control in (self.name,self.speed,self.teach_speed,self.dwell,self.blend_radius):control.set_sensitive(not busy)
        text=self.task.phase+' · '+self.task.message
        if self.task.current_point:text=f'{self.task.current_point}/{self.task.total_points} · '+text
        if self.task.program_error:text+=' · 示教读取失败：'+self.task.program_error
        if view in ('position','teaching'):
            for notice in self.notices:
                set_status_text(notice,text)
                if notice.get_tooltip_text()!=text:notice.set_tooltip_text(text)
        if view=='position':
            for n,actual in self.actual.items():
                s=c.nodes[n]
                angle=s.motor_angle/RATIOS[n] if s.motor_angle is not None and s.zero_valid else None
                set_status_text(actual,f'{angle:.2f}°' if angle is not None else '零点未确认')
                problems=[]
                if s.online!='在线':problems.append('未在线')
                if not s.zero_valid:problems.append('零点未确认')
                if s.firmware!='Emm':problems.append('协议待确认')
                if not s.enabled or not s.motor_flags&1:problems.append('未使能')
                if n in c._f3_uncertain:problems.append('使能回复未确认')
                if n not in self.task.pulses_per_rev:problems.append('未设脉冲数')
                if s.motor_flags&0x8C or s.home_flags&0x3F!=3:problems.append('状态待核对')
                bounds=c.joint_limits.bounds.get(n)
                if c.joint_limits.error or not bounds and n!=6:problems.append('限位未确认')
                elif bounds and angle is not None and not self.task.feedback_within_bounds(n,angle):problems.append('当前角度越界')
                if not c.backend.supports_position_targets:problems.append('固件不支持定位')
                elif n not in c.backend.position_target_nodes:problems.append('固件不支持此关节定位')
                set_status_text(self.axis_status[n], ' / '.join(problems) if problems else '就绪')
                self.axis_status[n].set_tooltip_text('；'.join(problems)+f'；减速比 {RATIOS[n]:.6g}；脉冲/圈 {self.task.pulses_per_rev.get(n,"待核对")}；使能和保护为最近确认状态，定位仅读取位置')
                self.entries[n].set_sensitive(not busy and (bool(bounds) or n==6))
                self.checks[n].set_sensitive(not busy)
            set_status_text(self.plan_label,('已预检 %d 个关节' % len(self.task.plans)) if self.task.plans else '选择关节并填写目标角度。')
            set_status_text(self.plan_detail,'；'.join(f'J{n}: {p["target_deg"]:.2f}° / {p["actual_speed_deg_s"]:.2f}°每秒 / {p["rpm"]}RPM' for n,p in self.task.plans.items()) or '尚无预检结果')
        if view=='teaching':
            key=(self.task.revision,tuple(self.task.point_valid(p) for p in self.task.points))
            if key!=self.point_key:
                self.point_key=key
                for child in self.list.get_children():self.list.remove(child)
                self.point_widgets=[]
                for i,p in enumerate(self.task.points):
                    row=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3)
                    legacy=' · 不含 J6，回放保持 J6 不动' if '6' not in p['angles_deg'] else ''
                    text=f'{i+1}. {p["name"]} · {p["speed_deg_s"]}°/秒 · 停留 {p["dwell_seconds"]} 秒'+legacy
                    text+=' · '+p.get('motion',{}).get('mode','J')
                    info=label(text);info.set_ellipsize(3);info.set_max_width_chars(75);info.set_tooltip_text(text)
                    row.pack_start(info,False,False,0)
                    text=' / '.join(f'J{n} {v:.2f}°' for n,v in p['angles_deg'].items())
                    if not key[1][i]:text+=' · 参考已失效，需重新录点'
                    info=label(text);info.set_ellipsize(3);info.set_max_width_chars(75);info.set_tooltip_text(text)
                    row.pack_start(info,False,False,0)
                    actions=Gtk.Box(spacing=6)
                    go=self.button(actions,'返回姿态',lambda k=i:self.run('return',index=k),tracked=False)
                    delete=self.button(actions,'删除',lambda k=i:self.run('delete',index=k),tracked=False)
                    edit=self.button(actions,'编辑',lambda k=i:self.edit(k),tracked=False)
                    up=self.button(actions,'↑',lambda k=i:self.run('reorder',index=k,offset=-1),tracked=False)
                    down=self.button(actions,'↓',lambda k=i:self.run('reorder',index=k,offset=1),tracked=False)
                    row.pack_start(actions,False,False,0)
                    self.point_widgets.append((go,delete,key[1][i],edit,up,down))
                    self.list.pack_start(row,False,False,0)
                self.list.show_all()
        if view in ('cartesian','drawing') and hasattr(self,'cartesian_page'):self.cartesian_page.update(bool(busy))
        if view=='drawing' and hasattr(self,'drawing_page'):self.drawing_page.update(bool(busy))
        if view=='teaching':
            for i,(go,delete,valid,edit,up,down) in enumerate(self.point_widgets):
                go.set_sensitive(not busy and self._playable(self.task.points[i]) and self.window.safety.get_active())
                for b in (delete,edit):b.set_sensitive(not busy)
                up.set_sensitive(not busy and i>0);down.set_sensitive(not busy and i<len(self.task.points)-1)
