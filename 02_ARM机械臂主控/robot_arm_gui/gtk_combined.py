"""Shared Cartesian target and drawing controls inside the left operation area."""
from gi.repository import Gtk,Gdk,GLib
from .cartesian_jog import HoldLease,plane_direction
from .gtk_touch import emulated
from .gtk_cartesian import text
from . import drawing,kinematics as k


class CombinedPage:
    def __init__(self,pages):
        self.pages=pages;c=pages.cartesian_page;d=pages.drawing_page
        self.cartesian,self.drawing=c,d;self.syncing=False
        self.held_button=None;self.hold_lease=None;self.jog_buttons=[];self.jog_status='';self.jog_pending=False
        self.jog_prepare_at=0.
        outer=pages.window.operation_stack.get_child_by_name('drawing')
        old=outer.get_child()
        page=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=10)
        page.get_style_context().add_class('joint-panel')
        left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);page.pack_start(left,True,True,0)
        side=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);side.get_style_context().add_class('combined-side');side.set_size_request(330,-1);self.side=side;self.left=left;page.pack_start(side,False,False,0)
        def take(w,box,expand=False):
            parent=w.get_parent()
            if parent:parent.remove(w)
            box.pack_start(w,expand,expand,0)
        toolbar=Gtk.Box(spacing=4);left.pack_start(toolbar,False,False,0)
        cell=d.direction.get_cells()[0];cell.set_property('ellipsize',3);cell.set_property('width-chars',10)
        d.direction.set_tooltip_text('末端定位与绘图共用朝向；直线/圆弧保持起点朝向，换朝向请先用J定位')
        d.auto_orientation.set_label('允许改变末端朝向');d.auto_orientation.set_tooltip_text('默认关闭：同时保持线路高度与末端朝向，六轴自动联动；勾选后仅在固定朝向无法连续通过时允许改变末端朝向，紫色标明')
        take(d.plane,toolbar)
        d.direction.get_parent().remove(d.direction)
        self.direction_button=Gtk.MenuButton();toolbar.pack_start(self.direction_button,False,False,0)
        self.adjust_orientation_button=Gtk.Button(label='调整朝向')
        toolbar.pack_start(self.adjust_orientation_button,False,False,0)
        self.adjust_orientation_button.set_tooltip_text('仅转 J4/J5 改变工具主轴朝向；J1/J2/J3/J6 保持，末端位置允许变化，保留原限位')
        self.adjust_orientation_button.connect('clicked',lambda *_:pages.window._command(self.adjust_orientation))
        popover=Gtk.Popover.new(self.direction_button);self.direction_button.set_popover(popover)
        choices=Gtk.Grid(column_spacing=4,row_spacing=4);popover.add(choices)
        for n,(key,label) in enumerate([('plus_x','+X'),('minus_x','−X'),('plus_y','+Y'),('minus_y','−Y'),('plus_z','+Z'),('minus_z','−Z'),('hold','保持当前'),('union','合并查看')]):
            button=Gtk.Button(label=label);choices.attach(button,n%2,n//2,1,1)
            button.connect('clicked',lambda _w,key=key:(d.direction.set_active_id(key),popover.popdown()))
        choices.show_all()
        def direction_changed(*_):
            labels=dict(plus_x='+X',minus_x='−X',plus_y='+Y',minus_y='−Y',plus_z='+Z',minus_z='−Z',hold='保持',union='合并')
            self.direction_button.set_label('朝向 · '+labels.get(d.direction.get_active_id(),'保持'))
        d.direction.connect('changed',direction_changed);direction_changed()
        d.direction.connect('changed',lambda *_:self.update_jog())
        take(d.cut,toolbar)
        canvas_options=Gtk.MenuButton(label='自由' if d.free.get_active() else '点选');toolbar.pack_start(canvas_options,False,False,0)
        canvas_popover=Gtk.Popover.new(canvas_options);canvas_popover.set_modal(False);canvas_options.set_popover(canvas_popover)
        def close_canvas_options(*_):
            canvas_options.set_active(False);canvas_popover.hide()
        canvas_options.connect('toggled',lambda b:canvas_popover.hide() if not b.get_active() else None)
        canvas_options.connect('unmap',close_canvas_options)
        canvas_controls=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);canvas_controls.set_border_width(12);canvas_popover.add(canvas_controls)
        for widget in (d.flip,d.free):take(widget,canvas_controls)
        canvas_options.set_tooltip_text('画布选项：点选/自由绘线、翻转上下')
        d.free.connect('toggled',lambda *_:canvas_options.set_label('自由' if d.free.get_active() else '点选'))
        for widget in (d.flip,d.free):widget.connect('toggled',close_canvas_options)
        canvas_close=Gtk.Button(label='关闭选项');canvas_controls.pack_start(canvas_close,False,False,0);canvas_close.connect('clicked',close_canvas_options)
        canvas_controls.show_all();self.canvas_options_button=canvas_options
        self.fullscreen_button=Gtk.Button(label='全屏')
        self.fullscreen_button.set_tooltip_text('全屏绘图')
        self.fullscreen_button.connect('clicked',lambda *_:pages.window._command(lambda:self.set_canvas_fullscreen(True)))
        toolbar.pack_end(self.fullscreen_button,False,False,0)
        take(d.slice_box,left,True);take(d.summary,left);take(d.point_info,left)
        for label in (d.summary,d.point_info,d.notice):
            label.set_width_chars(45);label.set_max_width_chars(45)
            if isinstance(label,Gtk.Label):label.set_ellipsize(3)
        files=Gtk.Box(spacing=8);left.pack_start(files,False,False,0)
        for caption,action in [('撤销',d.remove_last),('清空',d.clear),('保存线路',lambda:d.file(False)),('载入',lambda:d.file(True))]:d.button(files,caption,action)
        # Both motion APIs use the same widgets, while their original guards remain.
        previous=(c.speed,c.joint_speed,c.acc,c.acc_override)
        c.speed,c.joint_speed,c.acc,c.acc_override=d.speed,d.joint_speed,d.acc,d.acc_override
        c.inputs=[w for w in c.inputs if w not in previous]+list((c.speed,c.joint_speed,c.acc,c.acc_override))
        for w in (c.speed,c.joint_speed,c.acc):w.connect('value-changed',lambda *_:c.invalidate_preview())
        c.acc_override.connect('toggled',lambda *_:c.invalidate_preview())
        d.xyz=c.xyz;d.combined=self;c.combined=self
        self.operation='position';self.operation_buttons={};self.operation_rows={}
        side_scroll=Gtk.ScrolledWindow();side_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        side_scroll.set_overlay_scrolling(False)
        side.pack_start(side_scroll,True,True,0)
        side_content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);side_scroll.add(side_content)
        self.side_content=side_content
        tabs=Gtk.Box(spacing=4);tabs.get_style_context().add_class('operation-tabs');side.pack_start(tabs,False,False,0);side.reorder_child(tabs,0)
        for key,caption in (('position','定位'),('drawing','绘图'),('orientation','朝向')):
            button=Gtk.Button(label=caption);tabs.pack_start(button,True,True,0)
            button.connect('clicked',lambda _b,key=key:self.show_operation(key))
            self.operation_buttons[key]=button
        self.parameter_button=Gtk.MenuButton(label='参数');tabs.pack_start(self.parameter_button,True,True,0)
        self.settings_popover=Gtk.Popover.new(self.parameter_button);self.settings_popover.set_position(Gtk.PositionType.LEFT);self.settings_popover.set_modal(False);self.parameter_button.set_popover(self.settings_popover)
        def close_parameters(*_):
            self.parameter_button.set_active(False);self.settings_popover.hide()
        self.parameter_button.connect('toggled',lambda b:self.settings_popover.hide() if not b.get_active() else None)
        self.parameter_button.connect('unmap',close_parameters)
        def close_hidden_popovers(*_):
            if pages.window.workspace.get_visible_child_name()!='control' or pages.window.operation_stack.get_visible_child_name()!='drawing':
                close_parameters();close_canvas_options()
        pages.window.workspace.connect('notify::visible-child',close_hidden_popovers)
        pages.window.operation_stack.connect('notify::visible-child',close_hidden_popovers)
        target_title=text('目标坐标');side_content.pack_start(target_title,False,False,0)
        grid=Gtk.Grid(column_spacing=10,row_spacing=4);side_content.pack_start(grid,False,False,0)
        for n,(name,w) in enumerate(zip('XYZ',c.xyz)):
            w.get_parent().remove(w);w.set_width_chars(5);w.set_max_width_chars(5);w.set_hexpand(True)
            grid.attach(text(name+' / mm'),0,n,1,1);grid.attach(w,1,n,1,1)
            w.connect('value-changed',self.target_changed)
        row=Gtk.Box(spacing=8);files.pack_start(row,False,False,0)
        d.button(row,'读当前位置',c.copy_current);d.button(row,'加入线路',lambda:(d.add(c.values(c.xyz)),d.changed()))
        jog_row=Gtk.Box(spacing=12);jog_row.set_homogeneous(True);left.pack_start(jog_row,False,False,0)
        for direction,label in [('up','↑'),('down','↓'),('left','←'),('right','→')]:
            button=Gtk.Button(label=label);jog_row.pack_start(button,True,True,0)
            button.get_style_context().add_class('cart-jog')
            button.set_tooltip_text('按住移动，松开停止（当前绘图平面）；保持按下时的末端朝向')
            button.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.LEAVE_NOTIFY_MASK)
            button.connect('button-press-event',self.jog_pressed,direction)
            button.connect('button-release-event',self.jog_mouse_release)
            button.connect('leave-notify-event',lambda b,e:False if pages.window._touch_input.active(b) else (self.release_jog(),False)[1])
            button.connect('grab-broken-event',lambda *_:(self.release_jog(),False)[1])
            pages.window._touch_input.bind(button,lambda b,e,direction=direction:self.jog_touch_pressed(b,e,direction),
                lambda *_:self.release_jog())
            button.connect('unmap',lambda *_:self.release_jog())
            self.jog_buttons.append(button)
        self.target_widgets=[target_title,grid,row,jog_row]
        orientation_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        side_content.pack_start(orientation_box,False,False,0)
        orientation_box.pack_start(text('腕部换向 · 仅 J4/J5'),False,False,0)
        direction_grid=Gtk.Grid(column_spacing=5,row_spacing=5)
        orientation_box.pack_start(direction_grid,False,False,0)
        self.wrist_buttons=[]
        for n,(key,caption) in enumerate((('plus_x','+X'),('minus_x','−X'),('plus_y','+Y'),('minus_y','−Y'),('plus_z','+Z'),('minus_z','−Z'))):
            button=Gtk.Button(label=caption);direction_grid.attach(button,n%3,n//3,1,1)
            button.set_hexpand(True);button.connect('clicked',lambda _b,key=key:d.direction.set_active_id(key))
            self.wrist_buttons.append(button)
        take(self.adjust_orientation_button,orientation_box,True)
        self.adjust_orientation_button.set_label('执行腕部换向')
        orientation_box.pack_start(text('末端位置允许变化 · 其余关节保持 · 换向≤20°/秒'),False,False,0)
        self.orientation_box=orientation_box
        window=pages.window
        window.connect('button-release-event',self.jog_mouse_release)
        window.connect('focus-out-event',lambda *_:(self.release_jog(reason='窗口失焦'),False)[1])
        window.connect('key-press-event',lambda _w,e:self.release_jog() if e.keyval in (Gdk.KEY_Escape,Gdk.KEY_space) else None)
        window.connect('destroy',self.destroy_jog)
        window.operation_stack.connect('notify::visible-child',lambda *_:self.release_jog())
        window.safety.connect('toggled',lambda *_:self.release_jog() if not window.safety.get_active() else None)
        self.jog_timer=GLib.timeout_add(50,self.check_jog,priority=GLib.PRIORITY_HIGH)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.NEVER)
        scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False);self.parameter_scroll=scroll
        parameter_shell=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);self.settings_popover.add(parameter_shell)
        parameter_header=Gtk.Box(spacing=8);parameter_header.set_border_width(8);parameter_shell.pack_start(parameter_header,False,False,0)
        parameter_header.pack_start(text('运动参数'),True,True,0)
        parameter_close=Gtk.Button(label='关闭');parameter_header.pack_end(parameter_close,False,False,0);parameter_close.connect('clicked',close_parameters)
        parameter_shell.pack_start(scroll,True,True,0);self.parameter_close_button=parameter_close
        settings=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);settings.set_border_width(12);settings.get_style_context().add_class('drawing-settings');scroll.add(settings)
        def field(name,w):
            row=Gtk.Box(spacing=4);settings.pack_start(row,False,False,0);row.pack_start(text(name),False,False,0);take(w,row,True)
            self.operation_rows[name]=row
        field('定位方式',c.usage);field('定位运动',c.mode);field('绘线方式',d.mode)
        field('末端 mm/s',d.speed);field('关节 °/s',d.joint_speed)
        advanced=Gtk.Expander(label='高级参数')
        advanced_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);advanced.add(advanced_box);settings.pack_start(advanced,False,False,0);self.advanced_expander=advanced
        acc_row=Gtk.Box(spacing=4);advanced_box.pack_start(acc_row,False,False,0)
        acc_row.pack_start(text('轨迹 ACC'),False,False,0);take(d.acc,acc_row,True);take(d.acc_override,advanced_box)
        take(d.auto_orientation,advanced_box)
        for w in (c.via_box,c.seed_box,c.transition):take(w,advanced_box)
        deviation_row=Gtk.Box(spacing=8);advanced_box.pack_start(deviation_row,False,False,0)
        deviation_row.pack_start(text('最大偏离 / mm'),False,False,0);take(c.deviation,deviation_row,True)
        def vertical_fields(entries,captions,container):
            fields=Gtk.Grid(column_spacing=10,row_spacing=8)
            for n,(entry,caption) in enumerate(zip(entries,captions)):
                parent=entry.get_parent()
                if parent:parent.remove(entry)
                entry.set_hexpand(True)
                fields.attach(text(caption),0,n,1,1);fields.attach(entry,1,n,1,1)
            for child in container.get_children():container.remove(child)
            if isinstance(container,Gtk.Box):container.pack_start(fields,False,False,0)
            else:container.add(fields)
        vertical_fields(c.via,('经过 X / mm','经过 Y / mm','经过 Z / mm'),c.via_box)
        vertical_fields(c.seeds,('J1 / °','J2 / °','J3 / °','J4 / °','J5 / °','J6 / °'),c.seed_box)
        for w in c.rpy+c.via+c.seeds:w.set_width_chars(4)
        row=Gtk.Box(spacing=4);advanced_box.pack_start(row,False,False,0)
        d.button(row,'目标逆解',lambda:c.run('cart_ik',**c.params()))
        take(d.calibration_notice,advanced_box)
        take(d.reference_box,settings)
        pointrow=Gtk.Box(spacing=4);settings.pack_start(pointrow,False,False,0)
        pointrow.pack_start(text('选中点'),False,False,0);take(d.index,pointrow)
        d.button(pointrow,'更新',d.apply);d.button(pointrow,'删除',d.delete)
        point_scroll=Gtk.ScrolledWindow();point_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.NEVER)
        point_scroll.set_min_content_width(1);point_scroll.set_min_content_height(44)
        parent=d.point_list.get_parent();parent.remove(d.point_list);point_scroll.add(d.point_list)
        settings.pack_start(point_scroll,False,False,0);self.point_scroll=point_scroll
        self.point_widgets=[pointrow,point_scroll]
        take(d.safety,side)
        row=Gtk.Box(spacing=4);side.pack_start(row,False,False,0)
        take(c.preview_button,row,True);c.preview_button.set_label('预览目标定位');take(d.plan_button,row,True)
        row=Gtk.Box(spacing=4);side.pack_start(row,False,False,0)
        take(c.move,row,True);take(c.stream,row,True);take(d.execute,row,True)
        self.execution_row=row
        take(d.gate_notice,side)
        d.point_info.set_max_width_chars(45)
        if isinstance(d.point_info,Gtk.Label):d.point_info.set_ellipsize(3)
        d.cut.get_style_context().add_class('slice-cut')
        d.cut.set_width_chars(6);d.cut.set_max_width_chars(6);d.cut.set_size_request(175,-1);d.index.set_max_width_chars(4)
        c.result.set_max_width_chars(32);c.result.set_lines(2);c.result.set_ellipsize(3);take(c.result,side)
        if hasattr(c,'result_details'):take(c.result_details,side_content)
        d.notice.set_max_width_chars(45);d.notice.set_ellipsize(3);take(d.notice,left)
        pages.controls=[w for w in pages.controls if not w.is_ancestor(old)]
        pages.motion_buttons=[w for w in pages.motion_buttons if not w.is_ancestor(old)]
        outer.remove(old);outer.add(page)
        side_content.show_all();parameter_shell.show_all()
        side.set_size_request(max(330,grid.get_preferred_width()[0]+32),-1)
        def fit_parameter_column(_window,allocation):
            scale=max(1.0,min(1.75,float(allocation.height)/800.0))
            scrollbar_width=side_scroll.get_vscrollbar().get_preferred_width()[0]
            required=max(round(330*scale),grid.get_preferred_width()[0]+scrollbar_width+8)
            if side.get_size_request()[0]!=required:side.set_size_request(required,-1)
            popup_width=max(round(410*scale),settings.get_preferred_width()[0]+scroll.get_vscrollbar().get_preferred_width()[0]+16)
            popup_height=min(round(400*scale),max(280,allocation.height-160))
            if scroll.get_size_request()!=(popup_width,popup_height):scroll.set_size_request(popup_width,popup_height)
        window.connect('size-allocate',fit_parameter_column)
        advanced.connect('notify::expanded',lambda *_:fit_parameter_column(window,window.get_allocation()))
        self.settings_popover.connect('map',lambda *_:fit_parameter_column(window,window.get_allocation()))
        def wrap_parameter_labels(widget):
            if isinstance(widget,(Gtk.Button,Gtk.CheckButton)):
                child=widget.get_child()
                if isinstance(child,Gtk.Label):child.set_line_wrap(True);child.set_max_width_chars(28)
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():wrap_parameter_labels(child)
        wrap_parameter_labels(side_content);wrap_parameter_labels(settings)
        fit_parameter_column(window,window.get_allocation())
        d.plane.connect('changed',self.target_changed)
        d.cut.connect('value-changed',self.slice_changed)
        d.direction.connect('changed',lambda *_:c.invalidate_preview())
        d.auto_orientation.connect('toggled',lambda *_:c.invalidate_preview())
        c.mode.connect('changed',lambda *_:self.update_operation())
        self.show_operation('position')
        d.view_key=None;self.target_changed()

        self.canvas_fullscreen=False;self.canvas_locations=[]
        self.fullscreen_page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        self.fullscreen_page.set_border_width(8)
        self.fullscreen_page.get_style_context().add_class('joint-panel')
        self.fullscreen_toolbar=Gtk.Box(spacing=6)
        self.fullscreen_page.pack_start(self.fullscreen_toolbar,False,False,0)
        self.fullscreen_return=Gtk.Button(label='返回 · Esc')
        self.fullscreen_return.connect('clicked',lambda *_:self.set_canvas_fullscreen(False))
        self.fullscreen_toolbar.pack_start(self.fullscreen_return,False,False,0)
        self.fullscreen_stop=Gtk.Button(label='全部停止')
        self.fullscreen_stop.get_style_context().add_class('stop')
        self.fullscreen_stop.connect('clicked',lambda *_:window._command(window._stop_all))
        self.fullscreen_toolbar.pack_end(self.fullscreen_stop,False,False,0)
        self.fullscreen_footer=Gtk.Box(spacing=6)
        self.fullscreen_page.pack_end(self.fullscreen_footer,False,False,0)
        self.fullscreen_undo=d.button(self.fullscreen_footer,'撤销末点',d.remove_last)
        self.fullscreen_save=d.button(self.fullscreen_footer,'保存线路',lambda:d.file(False))
        self.fullscreen_summary=text(d.summary.get_text());self.fullscreen_summary.set_ellipsize(3)
        self.fullscreen_footer.pack_start(self.fullscreen_summary,True,True,0)
        d.summary.connect('notify::label',lambda *_:self.fullscreen_summary.set_text(d.summary.get_text()))
        self.fullscreen_notice=text(d.notice.get_text());self.fullscreen_notice.set_ellipsize(3)
        self.fullscreen_notice.set_width_chars(1)
        self.fullscreen_page.pack_end(self.fullscreen_notice,False,False,0)
        d.notice.connect('notify::label',lambda *_:self.fullscreen_notice.set_text(d.notice.get_text()))
        window.workspace.add_named(self.fullscreen_page,'drawing-fullscreen')
        window.workspace.connect('notify::visible-child',self.canvas_page_changed)

    def set_canvas_fullscreen(self,active,restore_workspace=True):
        active=bool(active)
        if active==self.canvas_fullscreen:return
        window=self.pages.window;d=self.drawing
        if active and (self.pages.task.busy or d.busy or window.controller._moving):
            raise ValueError('请等待当前运动或计算结束，再放大全屏绘图')
        self.release_jog()
        window._touch_input.reset();d.stroke=None
        d.flush_point_info()
        if active:
            # Reuse the exact canvas and input widgets, including their bindings.
            widgets=(d.slice_box,d.plane,d.cut,d.flip,d.free)
            self.canvas_locations=[(w,w.get_parent(),w.get_parent().get_children().index(w),
                                    w.get_parent().query_child_packing(w)) for w in widgets]
            for w,parent,position,packing in self.canvas_locations:parent.remove(w)
            self.fullscreen_page.pack_start(d.slice_box,True,True,0)
            self.fullscreen_page.reorder_child(d.slice_box,1)
            for w in widgets[1:]:self.fullscreen_toolbar.pack_start(w,False,False,0)
            self.canvas_fullscreen=True
            self.fullscreen_page.show_all()
            window.workspace.set_visible_child_name('drawing-fullscreen')
        else:
            self.canvas_fullscreen=False
            if getattr(d.slice_image,'native',None):d.slice_image.native.deactivate()
            for w,parent,position,packing in self.canvas_locations:
                w.get_parent().remove(w)
                expand,fill,padding,pack_type=packing
                (parent.pack_start if pack_type==Gtk.PackType.START else parent.pack_end)(w,expand,fill,padding)
            for w,parent,position,packing in sorted(self.canvas_locations,key=lambda row:row[2]):
                parent.reorder_child(w,position);w.show()
            self.canvas_locations=[]
            if restore_workspace:window.workspace.set_visible_child_name('control')
        d.view_key=None
        if not active and getattr(d,'_fullscreen_editor_pending',False):d.refresh()
        d.draw()

    def canvas_page_changed(self,*_):
        if self.canvas_fullscreen and self.pages.window.workspace.get_visible_child_name()!='drawing-fullscreen':
            self.set_canvas_fullscreen(False,restore_workspace=False)

    def show_operation(self,name):
        if name not in self.operation_buttons:return
        self.release_jog()
        self.operation=name
        self.update_operation()

    def update_operation(self):
        key=(self.operation,self.cartesian.mode.get_active_id(),self.cartesian.usage.get_active_id())
        if key==getattr(self,'_operation_layout_key',None):return
        self._operation_layout_key=key
        position=self.operation=='position';draw=self.operation=='drawing';orient=self.operation=='orientation'
        def visible(w,value):
            w.set_no_show_all(not value)
            if value:w.show_all()
            else:w.hide()
        for w in self.target_widgets:visible(w,not orient)
        visible(self.orientation_box,orient)
        for key,b in self.operation_buttons.items():
            context=b.get_style_context();(context.add_class if key==self.operation else context.remove_class)('active')
        for key,value in (('定位方式',not draw),('定位运动',position),('绘线方式',draw),('末端 mm/s',not orient)):
            visible(self.operation_rows[key],value)
        for w in self.point_widgets:visible(w,draw)
        visible(self.cartesian.preview_button,position);visible(self.drawing.plan_button,draw)
        visible(self.cartesian.move,position and self.cartesian.mode.get_active_id()=='J')
        visible(self.cartesian.stream,position and self.cartesian.mode.get_active_id() in ('L','C'))
        visible(self.drawing.execute,draw)
        visible(self.execution_row,not orient)

    def jog_pressed(self,button,event,direction):
        if emulated(event):return True
        if self.pages.window._touch_input.contacts and not getattr(event,'touch_input',False):
            self.pages.window._touch_input.cancel();return True
        if event.button!=1 or event.type!=Gdk.EventType.BUTTON_PRESS:return True
        if self.hold_lease is not None or not button.get_sensitive():return True
        c=self.cartesian;window=self.pages.window
        def start():
            if c.usage.get_active_id()!='live':raise ValueError('请切换到现场定位方式')
            if not window.safety.get_active():raise ValueError('请先确认运动区域安全')
            speed,joint_speed=c.values((c.speed,c.joint_speed))
            axis,sign=plane_direction(self.drawing.plane.get_active_id(),self.drawing.flip.get_active(),direction)
            lease=HoldLease();self.hold_lease=lease;self.held_button=button
            params=dict(axis=axis,sign=sign,speed=speed,joint_speed=joint_speed,lease=lease,
                        required_direction='hold',clearance_confirmed=True,allow_orientation_adjustment=False)
            if c.acc_override.get_active():params['trajectory_acceleration']=int(c.values((c.acc,))[0])
            button.set_state_flags(Gtk.StateFlags.ACTIVE,False)
            self.jog_status='末端点动 · 准备中，请保持按住；松开可取消'
            self.jog_pending=True;self.drawing.notice.set_text(self.jog_status)
            print('CART_JOG_PRESS',dict(direction=direction,axis=axis,sign=sign,speed=speed),flush=True)
            try:c.task.start('cart_jog_hold',lambda ok,error:GLib.idle_add(self.jog_finished,lease,ok,error),**params)
            except Exception:
                self.jog_pending=False;self.release_jog(False);raise
        window._command(start)
        return True

    def jog_touch_pressed(self,button,event,direction):
        if self.hold_lease is not None:
            self.release_jog();return False
        self.jog_pressed(button,event,direction)
        return self.held_button is button

    def jog_mouse_release(self,_button,event):
        if not emulated(event) and event.button==1 and not self.pages.window._touch_input.active(self.held_button):self.release_jog()
        return False

    def release_jog(self,send_stop=True,reason='按键松开或界面切换'):
        lease,self.hold_lease=self.hold_lease,None
        button,self.held_button=self.held_button,None
        if button is not None:self.pages.window._touch_input.cancel_for(button)
        if lease is None:return
        print('CART_JOG_RELEASE',dict(reason=reason,send_stop=send_stop),flush=True)
        lease.release()
        self.jog_status='末端点动 · 已请求停止，等待确认'
        self.drawing.notice.set_text(self.jog_status)
        if button is not None:button.unset_state_flags(Gtk.StateFlags.ACTIVE)
        if send_stop:self.pages.window._command(self.cartesian.task.controller.stop_all,quiet=True)

    def jog_finished(self,lease,ok=True,error=''):
        if self.hold_lease is lease:self.release_jog(False)
        self.jog_pending=False
        self.jog_status='末端点动 · '+('完成' if ok else error or '未启动')
        self.update_jog()
        self.show_jog_status()
        if not ok and '取消' not in error and '松开' not in error:
            self.pages.window._show_error('末端点动未完成：'+error)
        return False

    def show_jog_status(self):
        if self.hold_lease is not None:
            task=self.cartesian.task
            # Streaming progress changes every transport cycle. Painting its
            # frame counter at 20 Hz can starve GTK's mouse heartbeat on ARM.
            self.jog_status=('末端点动 · 连续点动中 · 保持末端朝向；松开即停止'
                if task.phase=='连续轨迹执行' else '末端点动 · '+task.phase+' · '+task.message)
        elif self.cartesian.task.busy and not self.jog_pending:self.jog_status=''
        if self.jog_status and self.drawing.notice.get_text()!=self.jog_status:
            self.drawing.notice.set_text(self.jog_status)

    def check_jog(self):
        if self.hold_lease is not None:
            try:pressed=self.pages.window._touch_input.active(self.held_button) or bool(self.pages.window._pointer_buttons() & Gdk.ModifierType.BUTTON1_MASK)
            except Exception:pressed=False
            if not pressed or not self.hold_lease.pulse():self.release_jog(reason='鼠标按下状态消失或心跳超时')
            self.show_jog_status()
        elif not self.jog_pending:
            import time
            now=time.monotonic()
            if now>=self.jog_prepare_at:
                self.jog_prepare_at=now+.5
                self.prepare_jog_idle()
        return True

    def prepare_jog_idle(self):
        c=self.cartesian;window=self.pages.window
        busy=(c.task.busy or window._initializing_zero or window._powering_off
            or c.task.controller.zero_home.busy or c.task.controller._all_stopping
            or bool(c.task.controller._moving))
        if (busy or window.operation_stack.get_visible_child_name()!='drawing'
                or c.usage.get_active_id()!='live' or not window.safety.get_active() or not c.model.ready()):
            c.model.jog_prepared.invalidate();return
        try:
            from .cartesian_jog import prepare_idle
            speed,joint_speed=c.values((c.speed,c.joint_speed))
            params=dict(speed=speed,joint_speed=joint_speed)
            if c.acc_override.get_active():params['trajectory_acceleration']=int(c.values((c.acc,))[0])
            directions=[plane_direction(self.drawing.plane.get_active_id(),self.drawing.flip.get_active(),d)
                for d in ('up','down','left','right')]
            prepare_idle(c.model,params,directions)
        except Exception:
            c.model.jog_prepared.invalidate()

    def destroy_jog(self,*_):
        self.release_jog()
        self.cartesian.model.jog_prepared.invalidate()
        if self.jog_timer:GLib.source_remove(self.jog_timer);self.jog_timer=None
        if self.cartesian.prepare_timer:
            GLib.source_remove(self.cartesian.prepare_timer);self.cartesian.prepare_timer=None

    def update_jog(self):
        window=self.pages.window;task=self.cartesian.task
        busy=task.busy or window._initializing_zero or window._powering_off or task.controller.zero_home.busy or task.controller._all_stopping or bool(task.controller._moving)
        ready=self.cartesian.model.ready() and self.cartesian.usage.get_active_id()=='live' and window.safety.get_active()
        def sensitive(widget,value):
            if widget.get_sensitive()!=bool(value):widget.set_sensitive(bool(value))
        sensitive(self.direction_button,not busy)
        for button in list(self.operation_buttons.values())+self.wrist_buttons:sensitive(button,not busy)
        self.update_operation()
        sensitive(self.adjust_orientation_button,ready and not busy and not self.jog_pending
            and self.drawing.direction.get_active_id() in ('plus_x','minus_x','plus_y','minus_y','plus_z','minus_z'))
        for button in self.jog_buttons:sensitive(button,(ready and not busy) or button is self.held_button)

    def adjust_orientation(self):
        if self.cartesian.usage.get_active_id()!='live':raise ValueError('调整朝向需要现场定位方式')
        direction=self.drawing.direction.get_active_id()
        if direction not in ('plus_x','minus_x','plus_y','minus_y','plus_z','minus_z'):
            raise ValueError('请选择一个明确朝向后调整')
        self.cartesian.run('cart_adjust_orientation',direction=direction,
            joint_speed=self.cartesian.values((self.cartesian.joint_speed,))[0])

    def target_changed(self,*_args):
        if self.syncing:return
        d=self.drawing;self.syncing=True
        try:
            d.cut.set_value(d.xyz[d.axes()[2]].get_value());d.view_key=None;d.draw()
            d.point_info.set_text('目标 · X %.1f mm · Y %.1f mm · Z %.1f mm'%tuple(self.target()))
        finally:self.syncing=False

    def slice_changed(self,*_args):
        if self.syncing:return
        self.syncing=True
        try:self.drawing.xyz[self.drawing.axes()[2]].set_value(self.drawing.cut.get_value())
        finally:self.syncing=False
        self.target_changed()

    def orientation_params(self,goal,mode):
        direction=self.drawing.direction.get_active_id()
        if direction=='union':raise ValueError('六朝向合并区仅供查看，请选择一个定位/绘图朝向')
        c=self.cartesian
        pose=c.model.cached_pose() if c.usage.get_active_id()=='live' else None
        origin=pose or k.forward(c.values(c.seeds))
        goal['rotation']=drawing.rotation(direction,origin['rotation'])
        return dict(goal=goal,orientation='hold' if direction=='hold' or mode!='J' else 'interpolate',
                    required_direction=direction,drawing_constraints=mode in ('L','C'),
                    allow_orientation_adjustment=self.drawing.auto_orientation.get_active())

    def target(self):return [w.get_value() for w in self.cartesian.xyz]
