"""GTK shaft-tip controls, calibration and real computed trajectory preview."""
import time
from .gtk_touch import set_button_label,set_status_text
from gi.repository import Gtk,GdkPixbuf,GLib
from . import kinematics as k


def text(value):return Gtk.Label(label=value,xalign=0)


def spin(value,minimum=-2000,maximum=2000):
    w=Gtk.SpinButton.new_with_range(minimum,maximum,.1);w.set_digits(2);w.set_value(value);w.set_width_chars(8)
    return w


class CartesianPage:
    def __init__(self,pages):
        self.pages=pages;self.task=pages.task;self.window=pages.window
        self.model=self.task.cartesian;self.inputs=[]
        self.prepare_timer=None
        page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        page.get_style_context().add_class('joint-panel')
        self.notice=text('末端坐标 · 未标定');self.notice.set_ellipsize(3);self.notice.set_max_width_chars(78)
        page.pack_start(self.notice,False,False,0)
        chooser=Gtk.Grid(column_spacing=12,row_spacing=4)
        chooser.attach(text('使用方式'),0,0,1,1);chooser.attach(text('运动方式'),1,0,1,1)
        self.usage=Gtk.ComboBoxText();self.usage.append('model','模型预览 · 不运动');self.usage.append('live','实际定位');self.usage.set_active_id('model')
        self.usage.set_hexpand(True);chooser.attach(self.usage,0,1,1,1)
        page.pack_start(chooser,False,False,0);self.inputs.append(self.usage)
        row=Gtk.Box(spacing=6)
        self.mode=Gtk.ComboBoxText()
        for identifier,caption in (('J','PTP · 关节点到点'),('L','LIN · 直线'),('C','CIRC · 三点圆弧')):self.mode.append(identifier,caption)
        self.mode.set_active_id('J');self.inputs.append(self.mode)
        self.mode.set_hexpand(True);chooser.attach(self.mode,1,1,1,1)
        self.orientation=Gtk.ComboBoxText();self.orientation.append('hold','保持起点方向');self.orientation.append('interpolate','插值到目标方向');self.orientation.set_active_id('hold')
        self.inputs.append(self.orientation)
        basis=Gtk.Expander(label='坐标基准、模型尺寸与标定')
        basis_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        basis_box.pack_start(text('TCP为电机轴端；尺寸mm：170 / 37.5 / 160 / 15 / 142.3 / 39.5'),False,False,0)
        pages.button(row,'模型标定',self.calibrate);pages.button(row,'CAD离线计算',self.offline)
        pages.button(row,'计算目标逆解',lambda:self.run('cart_ik',**self.params()))
        basis_box.pack_start(row,False,False,0);basis.add(basis_box)
        page.pack_start(text('目标终点 · XYZ（mm）'),False,False,0)
        self.xyz=self.fields(page,('X','Y','Z'),(219.3,0,345))
        self.orientation_note=text('末端朝向 · Roll / Pitch / Yaw（°）')
        page.pack_start(self.orientation_note,False,False,0)
        self.rpy_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.rpy=self.fields(self.rpy_box,('Roll','Pitch','Yaw'),(90,0,90))
        page.pack_start(self.rpy_box,False,False,0)
        self.seed_box=Gtk.Expander(label='模型计算起点：J1～J6（°）')
        seed_container=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        self.seeds=self.fields(seed_container,('J1','J2','J3'),(0,0,0))+self.fields(seed_container,('J4','J5','J6'),(0,0,0))
        self.seed_box.add(seed_container)
        self.via_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        self.via=self.fields(self.via_box,('经过X mm','经过Y mm','经过Z mm'),(200,0,330))
        page.pack_start(self.via_box,False,False,0);self.via_box.set_no_show_all(True)
        row=Gtk.Box(spacing=6)
        self.speed=spin(5,.1,100);self.joint_speed=spin(5,1,100)
        row.pack_start(text('末端 mm/s'),False,False,0);row.pack_start(self.speed,False,False,0)
        row.pack_start(text('关节上限 °/s'),False,False,0);row.pack_start(self.joint_speed,False,False,0)
        self.inputs.extend((self.speed,self.joint_speed));page.pack_start(row,False,False,0)
        row=Gtk.Box(spacing=6)
        self.acc_override=Gtk.CheckButton(label='单独设置轨迹ACC（值越大，加速越快）')
        self.acc=spin(50,1,255);self.acc.set_digits(0)
        self.acc.get_adjustment().set_step_increment(1);self.acc.get_adjustment().set_page_increment(10)
        row.pack_start(self.acc_override,True,True,0);row.pack_start(self.acc,False,False,0)
        self.inputs.extend((self.acc_override,self.acc));page.pack_start(row,False,False,0)
        self.acc_override.connect('toggled',lambda _w:self.invalidate_preview())
        row=Gtk.Box(spacing=6)
        self.transition=Gtk.CheckButton(label='允许奇异区关节过渡（保持朝向）')
        self.deviation=spin(.1,.1,1);self.deviation.set_digits(2)
        row.pack_start(self.transition,True,True,0);row.pack_start(text('最大偏离 mm'),False,False,0)
        row.pack_start(self.deviation,False,False,0);page.pack_start(row,False,False,0)
        self.inputs.extend((self.transition,self.deviation))
        self.transition.connect('toggled',lambda _w:self.invalidate_preview())
        self.deviation.connect('value-changed',lambda _w:self.invalidate_preview())
        page.pack_start(self.seed_box,False,False,0);page.pack_start(basis,False,False,0)
        self.clearance=Gtk.CheckButton(label='已确认整段运动区域通畅、机械臂可安全运动')
        self.clearance.set_active(self.window.safety.get_active());self.clearance.connect('toggled',pages.safety_changed)
        pages.safety_checks.append(self.clearance);page.pack_start(self.clearance,False,False,0)
        row=Gtk.Box(spacing=6)
        self.preview_button=pages.button(row,'计算模型预览',lambda:self.run('cart_plan',**self.params()))
        pages.button(row,'读当前位置填入',self.copy_current)
        page.pack_start(row,False,False,0)
        self.result=text('模型预览不需要现场标定。')
        self.result.set_line_wrap(True);self.result.set_max_width_chars(75);page.pack_start(self.result,False,False,0)
        self.result_details=Gtk.Expander(label='计算与路径详情')
        self.result_detail=text('')
        self.result_detail.set_line_wrap(True);self.result_detail.set_max_width_chars(65)
        self.result_details.add(self.result_detail);page.pack_start(self.result_details,False,False,0)
        self.path_details=Gtk.Expander(label='模型路径投影（XY / XZ / YZ）')
        self.path_image=Gtk.Image();self.path_details.add(self.path_image);page.pack_start(self.path_details,False,False,0)
        from .gtk_workspace import WorkspacePanel
        self.workspace_panel=WorkspacePanel(self);page.pack_start(self.workspace_panel,False,False,0)
        row=Gtk.Box(spacing=6)
        self.move=pages.button(row,'仅执行终点定位',lambda:self.run('cart_move_endpoint',**self.params()),motion=True)
        self.stream=Gtk.Button(label='连续轨迹执行 · 未开放');self.stream.set_sensitive(False);row.pack_start(self.stream,False,False,0)
        self.stream.connect('clicked',lambda _w:self.window._command(lambda:self.run('cart_execute_path',**self.params())))
        pages.button(row,'取消计算 / 停止运动',self.task.cancel)
        action_row=row
        note=text('LIN/CIRC在启动前校验整段路径、朝向和前视指令，预览可选。ACC过低会限制速度，未勾选时沿用六轴当前ACC。')
        note.set_line_wrap(True);note.set_max_width_chars(75);page.pack_start(note,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(200);scroll.add(page)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        outer.pack_start(scroll,True,True,0);outer.pack_start(action_row,False,False,0)
        self.window.operation_stack.add_named(outer,'cartesian')
        self.mode.connect('changed',lambda _w:(self.invalidate_preview(),self.mode_changed()))
        self.orientation.connect('changed',lambda _w:self.mode_changed())
        self.usage.connect('changed',lambda _w:(self.invalidate_preview(),self.mode_changed()))
        for entry in self.xyz+self.rpy+self.via+self.seeds+[self.speed,self.joint_speed,self.acc]:
            entry.connect('value-changed',lambda _w:self.invalidate_preview())
        self.mode_changed()

    def invalidate_preview(self):
        self.model.clear_preview();self.path_details.set_expanded(False)
        self.model.prepared.invalidate()
        if self.prepare_timer:GLib.source_remove(self.prepare_timer)
        self.prepare_timer=GLib.timeout_add(120,self.prepare_idle)
        if hasattr(self,'workspace_panel'):self.workspace_panel.update()

    def prepare_idle(self):
        self.prepare_timer=None
        if self.task.busy or getattr(getattr(self,'combined',None),'jog_pending',False):
            self.prepare_timer=GLib.timeout_add(500,self.prepare_idle)
            return False
        if self.usage.get_active_id()=='live' and self.mode.get_active_id() in ('L','C'):
            try:self.model.prepare_idle(self.params())
            except (ValueError,RuntimeError):pass
            # Math preparation emits no transport events. Wake the coalesced
            # display so the ready/failed label also updates while CAN is idle.
            self.task.controller._publish()
        return False

    def fields(self,box,names,values):
        grid=Gtk.Grid(column_spacing=8,row_spacing=3);entries=[]
        for i,(name,value) in enumerate(zip(names,values)):
            entry=spin(value);entry.set_hexpand(True);grid.attach(text(name),i,0,1,1);grid.attach(entry,i,1,1,1)
            self.inputs.append(entry);entries.append(entry)
        box.pack_start(grid,False,False,0);return entries

    def mode_changed(self,ready=None):
        live=self.usage.get_active_id()=='live';joint=self.mode.get_active_id()=='J'
        self.transition.set_sensitive(live and self.mode.get_active_id()=='L' and not self.task.busy)
        self.deviation.set_sensitive(self.transition.get_sensitive() and self.transition.get_active())
        if not joint and self.orientation.get_active_id()!='hold':self.orientation.set_active_id('hold')
        if joint and self.orientation.get_active_id()!='interpolate':self.orientation.set_active_id('interpolate')
        supported=getattr(self.task.controller.backend,'supports_continuous_trajectory',False)
        if ready is None:ready=self.model.ready()
        key=(live,self.mode.get_active_id(),self.orientation.get_active_id(),supported)
        changed=key!=getattr(self,'_mode_layout_key',None)
        self._mode_layout_key=key
        self.orientation.set_sensitive(joint and not self.task.busy)
        if changed:
            self.orientation_note.set_text('末端朝向 · Roll / Pitch / Yaw（°）' if joint else '末端朝向 · 保持起点朝向')
            self.rpy_box.set_no_show_all(not joint);self.rpy_box.set_visible(joint)
            self.seed_box.set_visible(not live);self.seed_box.set_no_show_all(live)
            self.clearance.set_visible(live);self.clearance.set_no_show_all(not live)
            set_button_label(self.preview_button,'预览实际路径' if live else '模型预览')
            set_button_label(self.move,'执行终点定位')
            set_button_label(self.stream,('执行直线' if self.mode.get_active_id()=='L' else '执行圆弧')+('' if supported else ' · 固件不支持'))
        preview=self.model.preview
        valid=bool(preview and not preview.get('offline') and preview.get('native_report') and preview.get('mode')==self.mode.get_active_id())
        self.stream.set_sensitive(live and not joint and supported and ready and not self.task.busy and self.window.safety.get_active())
        if changed:
            self.stream.set_visible(not joint);self.stream.set_no_show_all(joint)
            self.move.set_visible(joint);self.move.set_no_show_all(not joint)
            visible=self.mode.get_active_id()=='C'
            self.via_box.set_no_show_all(not visible)
            (self.via_box.show_all if visible else self.via_box.hide)()
        for entry in self.rpy:entry.set_sensitive(self.orientation.get_active_id()=='interpolate' and not self.task.busy)
        self.move.set_sensitive(live and joint and ready and not self.task.busy and self.window.safety.get_active())

    def values(self,entries):
        import math
        for entry in entries:
            try:value=float(entry.get_text().strip())
            except ValueError:raise ValueError('请填写有效数值，不能留空或输入文字')
            adjustment=entry.get_adjustment()
            if not math.isfinite(value) or not adjustment.get_lower()<=value<=adjustment.get_upper():
                raise ValueError('输入数值超过当前字段允许范围')
            entry.update()
        return [entry.get_value() for entry in entries]

    def params(self):
        speed,joint_speed=self.values((self.speed,self.joint_speed))
        params=dict(goal=k.pose_from_rpy(self.values(self.xyz),self.values(self.rpy) if self.mode.get_active_id()=='J' else [0,0,0]),mode=self.mode.get_active_id(),
            orientation=self.orientation.get_active_id(),via=self.values(self.via),speed=speed,joint_speed=joint_speed)
        if hasattr(self,'combined'):params.update(self.combined.orientation_params(params['goal'],params['mode']))
        if self.acc_override.get_active():params['trajectory_acceleration']=int(self.values((self.acc,))[0])
        if not params.get('drawing_constraints') and self.transition.get_active() and self.usage.get_active_id()=='live' and self.mode.get_active_id()=='L':
            params.update(allow_singularity_transition=True,singularity_deviation_mm=self.values((self.deviation,))[0])
        return params

    def run(self,operation,**params):
        if self.usage.get_active_id()=='model':
            if operation in ('cart_plan','cart_ik'):
                params['seed_deg']=self.values(self.seeds)
                if operation=='cart_ik' and params.get('orientation')=='hold':params['goal']['rotation']=k.forward(params['seed_deg'])['rotation']
                operation='cart_offline_plan' if operation=='cart_plan' else 'cart_offline_ik'
            elif operation in ('cart_move_endpoint','cart_execute_path'):raise ValueError('模型预览方式不能执行现场定位')
        self.pages.run(operation,**params)

    def copy_current(self):
        def fill():
            p=self.model.solution['pose']
            for entry,value in zip(self.xyz,p['position_mm']):entry.set_value(value)
            for entry,value in zip(self.rpy,k.rpy_from_pose(p)):entry.set_value(value)
            for entry,value in zip(self.seeds,self.model.solution['model_angles_deg']):entry.set_value(value)
        self.after_refresh=fill;self.run('cart_refresh')

    def finished(self,operation):
        if operation=='cart_adjust_orientation' and self.model.solution and self.model.solution.get('pose'):
            for entry,value in zip(self.xyz,self.model.solution['pose']['position_mm']):entry.set_value(value)
        if operation=='cart_refresh' and getattr(self,'after_refresh',None):
            callback=self.after_refresh;self.after_refresh=None;callback()
        if operation in ('cart_plan','cart_offline_plan','cart_sequence_plan'):
            dialog=CartesianPreview(self.window,self.model.preview)
            try:
                if operation=='cart_sequence_plan':dialog.show_all();dialog.run()
                else:
                    self.path_image.set_from_pixbuf(dialog.chart.get_pixbuf())
                    self.path_details.set_expanded(True);self.path_details.show_all()
            finally:dialog.destroy()
        self.update(False)

    def update(self,busy):
        ready=self.model.ready();pose=self.model.cached_pose()
        # Visualization only; do not rasterize hidden pages or interfere with jog.
        if not getattr(getattr(self,'combined',None),'jog_pending',False):self.workspace_panel.update()
        notice=('XYZ mm：'+' / '.join(f'{v:.2f}' for v in pose['position_mm'])) if pose else '末端坐标未就绪'
        if pose:
            age=max(time.monotonic()-self.task.controller.nodes[n].position_time for n in range(1,7))
            tooltip=f'最近位置反馈 {age:.1f}s；由模型换算，非独立末端测量'
            if self.notice.get_tooltip_text()!=tooltip:self.notice.set_tooltip_text(tooltip)
        for entry in self.inputs:entry.set_sensitive(not busy)
        for entry in self.rpy:entry.set_sensitive(not busy and self.orientation.get_active_id()=='interpolate')
        self.mode_changed(ready)
        result=self.model.solution;detail=''
        if result and result.get('pose'):
            p=result['pose'];content='XYZ mm：'+' / '.join(f'{v:.2f}' for v in p['position_mm'])
            detail=content
            if 'angles_deg' in result:
                detail+='\n模型角 °：'+' / '.join(f'{v:.2f}' for v in result['angles_deg'])
                if result.get('position_preserved') is False:
                    content+=' · 换向允许位置变化'
                    detail+=f' · 腕部换向 · 方向误差 {result["orientation_error_deg"]:.3f}° · XYZ允许变化'
                else:detail+=f' · 回代误差 {result["position_error_mm"]:.3f}mm / {result["orientation_error_deg"]:.3f}°'
                if result['near_singularity']:content+=' · 接近奇异'
            if result.get('offline'):content+=' · 模型预览'
        elif self.model.preview:
            report=self.model.preview
            content=f'路径已计算 · {report["mode"]} · 约 {report["total_seconds"]:.2f} 秒'
            detail=('含保持末端位置的腕部预对齐。' if report.get('preparation') else '')+self.speed_note(report)
        elif self.usage.get_active_id()=='model':
            content='模型预览 · 不执行运动'
            detail='无需连接电机或建立现场标定。直线和圆弧保持起点朝向；可展开起点修改六轴角度。'
            notice='模型预览 · 坐标为电机轴端'
        elif not ready:content=self.model.error or '零点或标定未就绪，请先核对。'
        else:content='就绪 · 可预览或执行定位'
        if not busy and ready and self.usage.get_active_id()=='live' and self.mode.get_active_id() in ('L','C'):
            status=self.model.prepared.state
            if status=='ready':
                report=self.model.prepared.report or {}
                native=report.get('native_report',{})
                preparation=report.get('preparation') or native.get('preparation')
                content='轨迹已准备'
                detail=('含腕部预对齐。' if preparation else '局部起步与制动段已准备。' if native.get('local_planning') else '完整轨迹已准备。')+'执行前核对六轴实际起点。'
                if native.get('complete_before_start') and native.get('singularity_deviation_mm') is not None:
                    content+=' · 含奇异区过渡'
                    detail+=' 奇异区过渡 %d 段，最大允许偏离 %.2f mm；保持起点朝向。'%(
                        len(native.get('singularity_transitions',[])),native['singularity_deviation_mm'])
            elif status=='preparing':content='正在准备路径…'
            elif status=='failed':content='路径准备失败：'+self.model.prepared.error
            if not self.prepare_timer:self.prepare_timer=GLib.timeout_add(500,self.prepare_idle)
        # Publish the final state once: no transient "ready → preparing → ready"
        # label rewrites and size requests within one display snapshot.
        set_status_text(self.notice,notice)
        set_status_text(self.result,content)
        set_status_text(self.result_detail,detail)

    def speed_note(self,report):
        native=report.get('native_report') or {}
        peak=native.get('peak_feed_mm_s');wire=native.get('wire_speed_caps_rpm')
        content='模型采样检查，未做碰撞检测。'
        if peak is not None:content+=f' 规划峰值 {peak:.2f} mm/s。'
        if native.get('validated_joint_speed_deg_s') is not None:
            content+=' 关节请求 %.1f°/s，朝向预检采用 %.1f°/s。'%(native['requested_joint_speed_deg_s'],native['validated_joint_speed_deg_s'])
        retiming=native.get('retiming')
        if retiming and retiming['strategy']=='local_c2':
            content+=' 局部连续计时 %.1f→%.1f秒，%d执行帧。'%(retiming['old_duration_s'],retiming['duration_s'],native['total_frames'])
        if wire:
            from .zero_home import RATIOS
            content+=' 前视限速 °/s：'+' / '.join(f'{v*6/RATIOS[i+1]:.2f}' for i,v in enumerate(wire))
        reasons=native.get('slowdown_reasons') or []
        if reasons:content+='\n'+'；'.join(reasons)
        return content

    def calibrate(self):
        dialog=Gtk.Dialog(title='CAD参考姿态与控制角映射',transient_for=self.window,modal=True)
        dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'保存当前映射',Gtk.ResponseType.OK)
        box=dialog.get_content_area();box.set_border_width(12);box.set_spacing(8)
        description=text('填写当前实物姿态对应的CAD关节角，并逐轴核对控制正方向。\nCAD 0°参考：大臂竖直、前臂水平、腕部轴向与草图一致。\n仅记录角度映射，不移动电机；回零参考改变后必须重新核对。')
        description.set_line_wrap(True);box.pack_start(description,False,False,0)
        dims=text('尺寸 mm：170 / 37.5 / 160 / 肘偏置15 / 142.3 / 轴端39.5；无附加工具。')
        box.pack_start(dims,False,False,0)
        grid=Gtk.Grid(column_spacing=12,row_spacing=5);angles=[];signs=[]
        for i,name in enumerate(('关节','当前实物对应CAD角°','控制正方向→CAD正方向')):grid.attach(text(name),i,0,1,1)
        for i in range(6):
            a=spin(0,-100000,100000);s=Gtk.ComboBoxText();s.append('1','同向 +1');s.append('-1','反向 −1');s.set_active_id('1')
            grid.attach(text('J'+str(i+1)),0,i+1,1,1);grid.attach(a,1,i+1,1,1);grid.attach(s,2,i+1,1,1);angles.append(a);signs.append(s)
        box.pack_start(grid,False,False,0)
        confirm=Gtk.CheckButton(label='已对照实物核对CAD角和六轴正方向，以上数值不是默认假设')
        box.pack_start(confirm,False,False,0);save=dialog.get_widget_for_response(Gtk.ResponseType.OK);save.set_sensitive(False)
        confirm.connect('toggled',lambda _w:save.set_sensitive(confirm.get_active()))
        try:
            dialog.show_all()
            if dialog.run()==Gtk.ResponseType.OK:self.run('cart_calibrate',model_angles=self.values(angles),signs=[int(s.get_active_id()) for s in signs],confirmed=confirm.get_active())
        finally:dialog.destroy()

    def offline(self):
        dialog=Gtk.Dialog(title='CAD参考正逆解 · 不驱动电机',transient_for=self.window,modal=True)
        dialog.add_buttons('关闭',Gtk.ResponseType.CLOSE,'计算正解',1,'以这些角为初值求目标逆解',2)
        box=dialog.get_content_area();box.set_border_width(12);box.set_spacing(8)
        entries=self.fields(box,tuple('J'+str(i+1)+'°' for i in range(3)),(0,-20,35))+self.fields(box,tuple('J'+str(i+1)+'°' for i in range(3,6)),(0,25,0))
        self.inputs=[entry for entry in self.inputs if entry not in entries]
        note=text('名义CAD模型，不使用实机零位或限位。目标逆解使用末端定位中的XYZ与RPY。')
        note.set_line_wrap(True);box.pack_start(note,False,False,0)
        try:
            dialog.show_all();response=dialog.run();angles=self.values(entries)
            if response==1:self.run('cart_offline_fk',model_angles=angles)
            if response==2:self.run('cart_offline_ik',seed_deg=angles,goal=self.params()['goal'])
        finally:dialog.destroy()


class CartesianPreview(Gtk.Dialog):
    def __init__(self,window,report):
        super().__init__(title='轴端轨迹 · 计算预览',transient_for=window,modal=True)
        self.add_buttons('关闭',Gtk.ResponseType.CLOSE);self.set_default_size(920,520)
        box=self.get_content_area();box.set_border_width(12);box.set_spacing(8)
        label=text(f'{report["mode"]} · {len(report["samples"])} 点 · 约 {report["total_seconds"]:.2f} 秒 · 精确终点')
        box.pack_start(label,False,False,0)
        if report.get('preparation'):
            prep=report['preparation'];changes=[b-a for a,b in zip(prep['start_angles_deg'],prep['end_angles_deg'])]
            label=text(f'先保持TCP位置/朝向，腕部预对齐：J4 {changes[3]:+.1f}°，J6 {changes[5]:+.1f}°，约 {prep["duration_s"]:.2f} 秒。仅预览。')
            label.set_line_wrap(True);box.pack_start(label,False,False,0)
        points=report.get('requested_path_xyz_mm') or [v['pose']['position_mm'] for v in report['samples']]
        parts=['<svg xmlns="http://www.w3.org/2000/svg" width="860" height="300"><rect width="100%" height="100%" fill="#171f2b"/>']
        for panel,(a,b,title) in enumerate(((0,1,'X-Y / mm'),(0,2,'X-Z / mm'),(1,2,'Y-Z / mm'))):
            left=55+285*panel;top=32;w=215;h=225
            low=[min(p[i] for p in points)-2 for i in (a,b)];high=[max(p[i] for p in points)+2 for i in (a,b)]
            factor=max((high[0]-low[0])/w,(high[1]-low[1])/h)
            cx=(low[0]+high[0])/2;cy=(low[1]+high[1])/2
            lx=cx-factor*w/2;ly=cy-factor*h/2
            parts.append(f'<text x="{left}" y="19" fill="#d0d8e0" font-size="13">{title}</text>')
            for tick in range(3):
                x=left+w*tick/2;y=top+h*tick/2
                parts.append(f'<path d="M {x} {top} V {top+h} M {left} {y} H {left+w}" fill="none" stroke="#536376"/>')
                parts.append(f'<text x="{x}" y="{top+h+18}" fill="#d0d8e0" text-anchor="middle" font-size="12">{lx+factor*w*tick/2:.1f}</text>')
                parts.append(f'<text x="{left-6}" y="{y+4}" fill="#d0d8e0" text-anchor="end" font-size="12">{ly+factor*h*(1-tick/2):.1f}</text>')
            coords=' '.join(f'{left+(p[a]-lx)/factor:.2f},{top+h-(p[b]-ly)/factor:.2f}' for p in points)
            parts.append(f'<polyline points="{coords}" fill="none" stroke="#67baff" stroke-width="2"/>')
        parts.append('</svg>');loader=GdkPixbuf.PixbufLoader.new_with_type('svg');loader.write(''.join(parts).encode());loader.close()
        self.chart=Gtk.Image.new_from_pixbuf(loader.get_pixbuf());box.pack_start(self.chart,False,False,0)
        note=text(report.get('warning') or '由名义几何计算，非实机测量；请核对运动区域及路径。')
        note.set_line_wrap(True);box.pack_start(note,False,False,0)
