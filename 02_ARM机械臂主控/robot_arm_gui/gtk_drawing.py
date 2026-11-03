"""Slice drawing and document editing inside the persistent controller window."""
import json
import math
from gi.repository import Gtk,Gdk,GdkPixbuf,GLib
from . import drawing,vision_drawing
from .gtk_cartesian import spin,text
from .joint_motion import atomic_json
from .gtk_touch import StatusEntry,set_status_text


class SliceCanvas(Gtk.Image):
    """Render the slice without making its bitmap the window's minimum size."""
    def __init__(self):
        super().__init__()
        self.set_size_request(300,150);self.set_hexpand(True);self.set_vexpand(True)
        from .gtk_native_canvas import NativeCanvas,LIBRARY
        self.native=NativeCanvas(self) if LIBRARY is not None else None
    def get_pixbuf(self):
        if self.native and self.native.active:return self.native.pixbuf()
        return super().get_pixbuf()
    def set_from_pixbuf(self,pixbuf):
        if self.native:self.native.deactivate()
        super().set_from_pixbuf(pixbuf)
    def do_get_preferred_width(self):return (300,480)
    def do_get_preferred_height(self):return (150,460)
    def do_get_preferred_width_for_height(self,_height):return (300,480)
    def do_get_preferred_height_for_width(self,_width):return (150,460)


class DrawingPage:
    def __init__(self,pages):
        self.pages=pages;self.task=pages.task;self.window=pages.window;self.model=self.task.cartesian
        self.points=[];self.selected=0;self.stroke=None;self.stroke_id=0;self.busy=False
        self.signature=None;self.render_timer=None;self.slice_cache=None
        self.window.connect('destroy',self.cancel_render)
        page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        page.get_style_context().add_class('joint-panel')
        self.notice=text('先准备线路，再执行 · 未做碰撞检测')
        self.notice.set_line_wrap(True);page.pack_start(self.notice,False,False,0)
        row=Gtk.Box(spacing=6);page.pack_start(row,False,False,0)
        self.direction=Gtk.ComboBoxText()
        for key,name in [('hold','保持当前末端朝向'),('plus_x','+X 前向'),('minus_x','−X 后向'),('plus_y','+Y'),('minus_y','−Y'),('plus_z','+Z 向上'),('minus_z','−Z 向下'),('union','六朝向合并 · 仅查看')]:self.direction.append(key,name)
        self.direction.set_active_id('hold');row.pack_start(self.direction,False,False,0)
        self.plane=Gtk.ComboBoxText()
        for key,name in [('xy','XY / 高度Z'),('xz','XZ / 横向Y'),('yz','YZ / 前后X')]:self.plane.append(key,name)
        self.plane.set_active_id('xy');row.pack_start(self.plane,False,False,0)
        self.flip=Gtk.CheckButton(label='翻转上下');self.flip.set_active(True);row.pack_start(self.flip,False,False,0)
        self.cut=spin(200,-380,510);row.pack_start(self.cut,False,False,0);row.pack_start(text('mm'),False,False,0)
        row=Gtk.Box(spacing=6);page.pack_start(row,False,False,0)
        self.free=Gtk.CheckButton(label='自由绘线');row.pack_start(self.free,False,False,0)
        self.mode=Gtk.ComboBoxText()
        for key,name in [('L','直线'),('J','关节点到点'),('C','圆弧经过点')]:self.mode.append(key,name)
        self.mode.set_active_id('L');row.pack_start(self.mode,False,False,0)
        self.speed=spin(100,.1,100);self.joint_speed=spin(60,.1,100)
        self.speed.set_tooltip_text('连续绘图请求速度，可调0.1～100mm/s；实际进给由各轴和路径预检确定')
        self.joint_speed.set_tooltip_text('连续绘图可调0.1～100°/s；各轴独立限速。入口和J点到点运动采用最高20°/s')
        for name,w in [('末端mm/s',self.speed),('关节°/s',self.joint_speed)]:row.pack_start(text(name),False,False,0);row.pack_start(w,False,False,0)
        row=Gtk.Box(spacing=6);page.pack_start(row,False,False,0)
        self.acc_override=Gtk.CheckButton(label='自定义加速度')
        self.acc_override.set_tooltip_text('轨迹ACC越大，加速越快')
        self.acc=spin(255,1,255);self.acc.set_digits(0);self.acc_override.set_active(True)
        self.acc.get_adjustment().set_step_increment(1)
        row.pack_start(self.acc_override,False,False,0);row.pack_start(self.acc,False,False,0)
        self.auto_orientation=Gtk.CheckButton(label='允许调整末端朝向')
        self.auto_orientation.set_tooltip_text('模型路径误差≤1mm；调整段以紫色显示')
        self.auto_orientation.set_active(False);page.pack_start(self.auto_orientation,False,False,0)
        self.slice_box,self.slice_image=self.canvas('截面选点或拖动绘线',page)
        self.slice_box.connect('button-press-event',self.press)
        self.slice_box.connect('motion-notify-event',self.move)
        self.slice_box.connect('button-release-event',self.release)
        self.window._touch_input.bind(self.slice_box,self.press,self.touch_finished,self.move)
        self.slice_box.connect('size-allocate',self.resized)
        self.summary=text('0点 · 0.0mm');page.pack_start(self.summary,False,False,0)
        self.summary.set_tooltip_text('最多10000点；密集曲线仅显示起终点与选中点。长度为折线长度。')
        self.point_list=Gtk.Box(spacing=4);page.pack_start(self.point_list,False,False,0)
        row=Gtk.Box(spacing=4);page.pack_start(row,False,False,0)
        self.index=Gtk.SpinButton.new_with_range(1,10000,1);self.index.set_digits(0)
        row.pack_start(text('选中点'),False,False,0);row.pack_start(self.index,False,False,0)
        self.xyz=[spin(0) for _ in range(3)]
        for name,w in zip('XYZ',self.xyz):row.pack_start(text(name),False,False,0);row.pack_start(w,False,False,0)
        self.button(row,'更新点',self.apply);self.button(row,'删除',self.delete)
        row=Gtk.Box(spacing=5);page.pack_start(row,False,False,0)
        self.button(row,'前移',lambda:self.reorder(-1));self.button(row,'后移',lambda:self.reorder(1))
        self.button(row,'撤销末点',lambda:self.remove_last());self.button(row,'清空',self.clear)
        self.button(row,'保存线路',lambda:self.file(False));self.button(row,'载入线路',lambda:self.file(True))
        row=Gtk.Box(spacing=5);page.pack_start(row,False,False,0)
        self.plan_button=self.button(row,'准备线路',lambda:self.run(False))
        self.execute=self.button(row,'定位起点并绘图',lambda:self.run(True))
        self.safety=Gtk.CheckButton(label=self.window.safety.get_label())
        self.safety.set_active(self.window.safety.get_active())
        self.safety.connect('toggled',pages.safety_changed)
        pages.safety_checks.append(self.safety);page.pack_start(self.safety,False,False,0)
        self.gate_notice=text('');self.gate_notice.set_line_wrap(True);page.pack_start(self.gate_notice,False,False,0)
        self.calibration_notice=text('');self.calibration_notice.set_line_wrap(True);page.pack_start(self.calibration_notice,False,False,0)
        page.pack_start(text('自由曲线隐藏密集编号；输入点号可编辑任意采样点。C点是经过点，下一点是圆弧终点。\n绘图模型路径误差上限1mm；拐点插值失败会自动分段停车，超过300mm也分段。无法核验1mm的J过渡不执行。合并工作区仅供参考。'),False,False,0)
        for w in (self.direction,self.plane,self.cut,self.speed,self.joint_speed,self.acc):
            w.connect('changed' if isinstance(w,Gtk.ComboBoxText) else 'value-changed',lambda *_:self.changed())
        self.flip.connect('toggled',lambda *_:self.refresh())
        self.plane.connect('changed',lambda *_:self.flip.set_active(self.plane.get_active_id()=='xy'))
        self.acc_override.connect('toggled',lambda *_:self.changed())
        self.auto_orientation.connect('toggled',lambda *_:self.changed())
        self.index.connect('value-changed',self.select_number)
        self.arrange(page)
        outer=Gtk.ScrolledWindow();outer.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.NEVER);outer.add(page)
        self.window.operation_stack.add_named(outer,'drawing');self.changed()

    def confirm_cad_reference(self):
        if not self.reference_confirm.get_active():
            raise ValueError('请先确认驱动器已供电且机械臂处于原 CAD 零位')
        self.model.check_cad_reference_configuration()
        dialog=Gtk.MessageDialog(transient_for=self.window,modal=True,
            buttons=Gtk.ButtonsType.OK_CANCEL,message_type=Gtk.MessageType.QUESTION,
            text='确认实物当前在原 CAD 零位？')
        dialog.format_secondary_text('将六轴当前位置设为本次零位，并沿用原固定标定。不会使能或运动。实物不在原 CAD 零位时请取消。')
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        response=dialog.run();dialog.destroy()
        if response!=Gtk.ResponseType.OK:return
        self.window._initializing_zero=True
        try:
            self.task.controller.zero_home.start('confirm_cad_zero',1,
                lambda ok,error:GLib.idle_add(self._cad_zero_confirmed,ok,error),cad_reference_confirmed=True)
        except Exception:
            self.window._initializing_zero=False;raise
        self.pages.update()

    def _cad_zero_confirmed(self,ok,error):
        self.window._initializing_zero=False
        if not ok:
            self.notice.set_text('零位确认未完成：'+error);self.pages.update();self.window._show_error(error)
            return False
        try:
            self.task.start('cart_confirm_fixed_reference',
                lambda success,why:GLib.idle_add(self._cad_reference_linked,success,why),confirmed=True)
        except Exception as exc:self._cad_reference_linked(False,str(exc))
        return False

    def _cad_reference_linked(self,ok,error):
        self.reference_confirm.set_active(False)
        self.notice.set_text('本次 CAD 零位与原固定标定已确认，可以定位和绘图；未使能或运动' if ok else '标定关联未通过：'+error)
        self.task.controller._publish();self.pages.update()
        if not ok:self.window._show_error(error)
        return False

    def arrange(self,page):
        children=page.get_children();editor=self.index.get_parent()
        edits=editor.get_children()[-2:];files=children[10].get_children()
        instructions=children[-1]
        for child in children:page.remove(child)
        body=Gtk.Box(spacing=12);body.set_halign(Gtk.Align.CENTER);body.set_valign(Gtk.Align.START)
        page.pack_start(body,True,True,0)
        left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);body.pack_start(left,True,True,0)
        self.notice.set_line_wrap(False);self.notice.set_max_width_chars(65);self.notice.set_ellipsize(3)
        left.pack_start(self.notice,False,False,0)
        def take(widget,box,expand=False):
            parent=widget.get_parent()
            if parent:parent.remove(widget)
            box.pack_start(widget,expand,expand,0)
        toolbar=Gtk.Box(spacing=6);left.pack_start(toolbar,False,False,0)
        for widget in (self.plane,self.cut,self.flip,self.free):take(widget,toolbar)
        self.cut.set_width_chars(5)
        left.pack_start(self.slice_box,False,False,0)
        self.summary.set_max_width_chars(65);self.summary.set_ellipsize(3)
        left.pack_start(self.summary,False,False,0)
        self.point_info=StatusEntry('未选中点');left.pack_start(self.point_info,False,False,0)
        edit_row=Gtk.Box(spacing=5);left.pack_start(edit_row,False,False,0)
        edit_row.pack_start(text('点号'),False,False,0);take(self.index,edit_row);self.index.set_width_chars(4)
        for name,widget in zip('XYZ',self.xyz):
            edit_row.pack_start(text(name),False,False,0);take(widget,edit_row);widget.set_width_chars(5)
        edit_buttons=Gtk.Box(spacing=5);left.pack_start(edit_buttons,False,False,0)
        for widget in edits:take(widget,edit_buttons)
        side=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);side.set_size_request(340,-1);body.pack_start(side,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False)
        settings=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);settings.get_style_context().add_class('drawing-settings')
        scroll.add(settings);side.pack_start(scroll,True,True,0)
        def field(name,widget):
            row=Gtk.Box(spacing=6);settings.pack_start(row,False,False,0)
            label=text(name);label.set_size_request(78,-1);row.pack_start(label,False,False,0)
            take(widget,row,True)
            if isinstance(widget,Gtk.SpinButton):widget.set_width_chars(5)
        field('首选朝向',self.direction);field('绘线方式',self.mode)
        field('末端mm/s',self.speed);field('关节°/s',self.joint_speed)
        self.acc_override.set_label('独立轨迹ACC');field('加速度',self.acc)
        take(self.acc_override,settings)
        self.auto_orientation.set_label('自动调整朝向（紫色预览）');take(self.auto_orientation,settings)
        flow=Gtk.FlowBox();flow.set_selection_mode(Gtk.SelectionMode.NONE);flow.set_min_children_per_line(2);flow.set_max_children_per_line(2)
        settings.pack_start(flow,False,False,0)
        for widget in files:
            widget.get_parent().remove(widget);flow.add(widget)
        point_scroll=Gtk.ScrolledWindow();point_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.NEVER)
        point_scroll.set_min_content_height(42)
        point_scroll.add(self.point_list);settings.pack_start(point_scroll,False,False,0)
        for widget in (self.gate_notice,self.calibration_notice,instructions):
            widget.set_line_wrap(True);widget.set_max_width_chars(26);settings.pack_start(widget,False,False,0)
        self.reference_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        self.reference_confirm=Gtk.CheckButton(label='驱动器已供电，实物当前在原 CAD 零位')
        self.reference_confirm.get_child().set_line_wrap(True)
        self.reference_confirm.get_child().set_max_width_chars(26)
        self.reference_box.pack_start(self.reference_confirm,False,False,0)
        self.reference_button=self.button(self.reference_box,'确认 CAD 零位并沿用原标定',self.confirm_cad_reference)
        self.reference_confirm.connect('toggled',lambda *_:self.update(self.busy))
        settings.pack_start(self.reference_box,False,False,0)
        self.safety.get_child().set_line_wrap(True);self.safety.get_child().set_max_width_chars(26)
        take(self.safety,side)
        for widget in (self.plan_button,self.execute):take(widget,side)

    def button(self,row,name,callback):
        return self.pages.button(row,name,callback)

    def resized(self,_widget,allocation):
        size=(max(300,allocation.width),max(150,allocation.height))
        if size!=getattr(self,'last_size',None):
            self.last_size=size;self.draw()

    def canvas(self,name,page):
        page.pack_start(text(name),False,False,0)
        box=Gtk.EventBox();box.set_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.POINTER_MOTION_MASK)
        image=SliceCanvas();box.add(image);page.pack_start(box,True,True,0);return box,image

    def document(self):
        return dict(schema=1,points=self.points,direction=self.direction.get_active_id(),speed=self.speed.get_value(),joint_speed=self.joint_speed.get_value(),trajectory_acceleration=self.acc.get_value_as_int() if self.acc_override.get_active() else None,allow_orientation_adjustment=self.auto_orientation.get_active())

    def apply_ai_document(self,document):
        import copy
        d=drawing.validate(copy.deepcopy(document))
        self.view_key=None;self.points=d['points'];self.selected=0;self.stroke_id=0
        self.direction.set_active_id(d['direction'])
        self.speed.set_value(d['speed']);self.joint_speed.set_value(d['joint_speed'])
        self.acc_override.set_active(d['trajectory_acceleration'] is not None)
        if d['trajectory_acceleration'] is not None:self.acc.set_value(d['trajectory_acceleration'])
        self.auto_orientation.set_active(d['allow_orientation_adjustment'])
        self.changed()

    def invalidate(self):
        if hasattr(self.model,'drawing'):self.model.drawing.invalidate()

    def changed(self):
        self.invalidate();self.signature=None;self.refresh()

    def touch_points(self,append=False):
        previous=getattr(self,'points_revision',0)
        if append:
            if getattr(self,'_append_pending',None) is None:
                self._append_pending=(id(self.points),len(self.points)-1,previous)
        else:self._append_pending=None
        self.points_revision=getattr(self,'points_revision',0)+1
        # Keep the coordinate frame under the pointer stable throughout a stroke.
        if not append or self.stroke is None:self.view_key=None

    def axes(self):
        return {'xy':(0,1,2),'xz':(0,2,1),'yz':(1,2,0)}[self.plane.get_active_id()]

    def select_number(self,_w):
        if self.busy:return
        self.selected=min(len(self.points)-1,max(0,self.index.get_value_as_int()-1));self.refresh()

    def add(self,xyz,stroke=None):
        if xyz[2]<=0:
            self.notice.set_text('线路Z必须大于0，该点未加入；请提高高度。');return False
        if len(self.points)>=drawing.MAX_POINTS:
            self.notice.set_text('已达到10000个点，未丢弃已有线路。');return False
        length_current=getattr(self,'length_key',None)==(id(self.points),len(self.points),getattr(self,'points_revision',0))
        segment=math.dist(self.points[-1]['xyz'],xyz) if self.points else 0
        self.points.append(dict(xyz=xyz,mode='L' if stroke is not None else self.mode.get_active_id(),stroke=stroke));self.selected=len(self.points)-1;self.touch_points(append=True)
        if length_current:
            self.path_length+=segment;self.length_key=(id(self.points),len(self.points),self.points_revision)
        caption='选中第%d点 · X %.1f mm · Y %.1f mm · Z %.1f mm'%(self.selected+1,*xyz)
        if self.stroke is not None and getattr(getattr(self,'combined',None),'canvas_fullscreen',False):self._pending_point_info=caption
        else:self.point_info.set_text(caption)
        return True

    def flush_point_info(self):
        caption=getattr(self,'_pending_point_info',None)
        if caption is not None:self.point_info.set_text(caption);self._pending_point_info=None

    def coords(self,e):
        a=self.slice_box.get_allocation();w,h=self.size
        if getattr(self,'render_allocation',None)!=(max(300,a.width),max(150,a.height)):
            self.render();w,h=self.size
        x=e.x-(a.width-w)/2;y=e.y-(a.height-h)/2
        i,j,fixed=self.axes();p=[0.,0.,0.];p[fixed]=self.cut.get_value()
        p[i]=(x-self.ox)/self.scale;p[j]=(y-self.oy)/(self.scale*(1 if self.flip.get_active() else -1))+self.vertical_offset
        return [round(v,1) for v in p]

    def press(self,_w,e):
        from .gtk_touch import emulated
        if emulated(e):return True
        if self.window._touch_input.contacts and not getattr(e,'touch_input',False):
            self.window._touch_input.cancel();return True
        if self.busy or e.button!=1:return False
        if self.free.get_active():
            self.stroke_id+=1;self.stroke=self.stroke_id
        self.add(self.coords(e),self.stroke);self.changed();return True

    def move(self,_w,e):
        from .gtk_touch import emulated
        if emulated(e):return True
        if self.busy or self.stroke is None or not e.state&Gdk.ModifierType.BUTTON1_MASK:return False
        xyz=self.coords(e)
        if not self.points or math.dist(xyz,self.points[-1]['xyz'])>=.5:
            self.add(xyz,self.stroke);self.invalidate();self.draw()
        return True

    def release(self,_w,e):
        from .gtk_touch import emulated
        if emulated(e):return True
        if self.stroke is not None and not self.busy:
            xyz=self.coords(e)
            if not self.points or math.dist(xyz,self.points[-1]['xyz'])>.01:self.add(xyz,self.stroke)
            self.native_append()
        self.stroke=None
        if not self.native_unchanged():self.view_key=None
        self.refresh();return True

    def touch_finished(self,widget,event,cancelled):
        if cancelled:self.stroke=None;self.view_key=None;self.refresh()
        else:self.release(widget,event)

    def apply(self):
        if self.points:
            xyz=[w.get_value() for w in self.xyz]
            from .collision import check_target
            check_target(xyz)
            p=self.points[self.selected];p['xyz']=xyz;p['mode']=self.mode.get_active_id()
            if p['mode']!='L':p['stroke']=None
            self.touch_points()
            self.changed()

    def delete(self):
        if self.points:self.points.pop(self.selected);self.selected=max(0,min(self.selected,len(self.points)-1));self.touch_points();self.changed()

    def remove_last(self):
        if self.points:self.points.pop();self.selected=max(0,min(self.selected,len(self.points)-1));self.touch_points();self.changed()

    def clear(self):self.points=[];self.selected=0;self.touch_points();self.changed()

    def reorder(self,delta):
        j=self.selected+delta
        if 0<=j<len(self.points):
            p=self.points[self.selected];q=self.points[j]
            # Individual reordering explicitly converts affected curve points to manual points.
            p['stroke']=q['stroke']=None
            self.points[j],self.points[self.selected]=p,q;self.selected=j;self.touch_points();self.changed()

    def import_pixel_document(self,document):
        paths=vision_drawing.contours(document)
        axes=self.axes();anchor=[w.get_value() for w in self.xyz];anchor[axes[2]]=self.cut.get_value()
        dialog=Gtk.Dialog(title='载入图像轮廓',transient_for=self.window,modal=True)
        dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'载入绘图',Gtk.ResponseType.OK)
        box=dialog.get_content_area();box.set_spacing(12);box.set_border_width(16)
        label=text('共%d条轮廓；保持宽高比例。工作面：%s\n请确认整条图形的中心和高度；以下初值取自当前目标。\n轮廓间使用关节移动；载入后请先预览整条线路。'%(len(paths),self.plane.get_active_id().upper()))
        label.set_line_wrap(True);box.pack_start(label,False,False,0)
        row=Gtk.Box(spacing=12);row.pack_start(text('图形最长边 / mm'),False,False,0)
        size=spin(50,.1,1000);row.pack_start(size,False,False,0);box.pack_start(row,False,False,0)
        centers=[]
        for axis,value in zip('XYZ',anchor):
            row=Gtk.Box(spacing=12);row.pack_start(text('图形中心 %s / mm'%axis),False,False,0)
            value_input=spin(value);centers.append(value_input);row.pack_start(value_input,False,False,0);box.pack_start(row,False,False,0)
        keyboard=getattr(self.window,'_numeric_keyboard',None)
        if keyboard:keyboard.bind_tree(dialog)
        dialog.show_all()
        try:
            if dialog.run()!=Gtk.ResponseType.OK:return None
            size.update()
            for value_input in centers:value_input.update()
            anchor=[value_input.get_value() for value_input in centers]
            return vision_drawing.convert(document,size=size.get_value(),anchor=anchor,axes=axes,flip=self.flip.get_active(),settings=self.document())
        finally:dialog.destroy()

    def file(self,load):
        action=Gtk.FileChooserAction.OPEN if load else Gtk.FileChooserAction.SAVE
        dialog=Gtk.FileChooserDialog(title='载入线路' if load else '保存线路',transient_for=self.window,action=action)
        dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'载入' if load else '保存',Gtk.ResponseType.OK)
        if not load:dialog.set_current_name('arm-path.json');dialog.set_do_overwrite_confirmation(True)
        from .gtk_keyboard import NumericKeyboard
        NumericKeyboard(dialog,desktop_osk=self.window.live_control,track_dialogs=False)
        try:
            if dialog.run()!=Gtk.ResponseType.OK:return
            from pathlib import Path
            path=Path(dialog.get_filename())
            if load:
                if path.stat().st_size>4*1024*1024:raise ValueError('线路文件超过4MB')
                raw=json.loads(path.read_text(encoding='utf-8'))
                if vision_drawing.is_pixel_document(raw):
                    dialog.hide()
                    d=self.import_pixel_document(raw)
                    if d is None:return
                else:d=drawing.validate(raw)
                self.view_key=None
                self.points=d['points'];self.direction.set_active_id(d['direction']);self.speed.set_value(d['speed']);self.joint_speed.set_value(d['joint_speed'])
                self.auto_orientation.set_active(False)  # Loaded routes also start with fixed TCP orientation.
                self.acc_override.set_active(d['trajectory_acceleration'] is not None)
                if d['trajectory_acceleration'] is not None:self.acc.set_value(d['trajectory_acceleration'])
                self.stroke_id=max((p.get('stroke') or 0 for p in self.points),default=0);self.selected=0;self.changed()
            else:atomic_json(path,drawing.validate(self.document()))
            self.notice.set_text('线路已载入，需重新规划' if load else '完整线路已保存')
        finally:dialog.destroy()

    def run(self,execute):
        if self.stroke is not None:raise ValueError('请先结束当前笔画')
        self.pages.run('cart_drawing_execute' if execute else 'cart_drawing_prepare',document=drawing.validate(self.document()))

    def refresh(self):
        if not hasattr(self,'index'):return
        # Editors and point buttons are hidden while drawing fullscreen. Updating
        # them on press or polling ticks needlessly invalidates the whole window.
        # Release and leaving fullscreen still perform the complete refresh.
        if self.stroke is not None and getattr(getattr(self,'combined',None),'canvas_fullscreen',False):
            self.draw();return
        if self.native_unchanged():
            # Only the canvas and footer are visible. Editors are synchronized
            # when leaving fullscreen; the original document is already current.
            self._fullscreen_editor_pending=True
            if not getattr(self,'fullscreen_footer_timer',None):
                self.fullscreen_footer_timer=GLib.timeout_add(50,self.refresh_fullscreen_footer)
            self.signature=None;self.update(self.busy);return
        self._fullscreen_editor_pending=False
        self.index.handler_block_by_func(self.select_number)
        self.index.set_value(self.selected+1);self.index.handler_unblock_by_func(self.select_number)
        p=self.points[self.selected] if self.points else None
        point_key=(id(self.points),self.selected,tuple(p['xyz'])) if p else None
        if p and point_key!=getattr(self,'editor_point',None):
            combined=getattr(self,'combined',None)
            if combined:combined.syncing=True
            try:
                for i,w in enumerate(self.xyz):w.set_value(p['xyz'][i])
            finally:
                if combined:combined.syncing=False
        self.editor_point=point_key
        if hasattr(self,'point_info'):
            self._pending_point_info=None
            set_status_text(self.point_info,'选中第%d点 · X %.1f mm · Y %.1f mm · Z %.1f mm'%(self.selected+1,*p['xyz']) if p else '点击画布添加点')
        indices=self.visible_indices()
        if len(indices)>20:indices=sorted(set(indices[:8]+indices[-8:]+[self.selected]))
        list_key=tuple(indices)
        if list_key!=getattr(self,'point_list_key',None):
            self.point_list_key=list_key
            for child in self.point_list.get_children():self.point_list.remove(child)
            for i in indices:
                b=Gtk.Button(label=str(i+1));b.connect('clicked',lambda _w,n=i:self.index.set_value(n+1));self.point_list.pack_start(b,False,False,0)
            self.point_list.show_all()
        length_key=(id(self.points),len(self.points),getattr(self,'points_revision',0))
        if length_key!=getattr(self,'length_key',None):
            self.length_key=length_key
            self.path_length=sum(math.dist(a['xyz'],b['xyz']) for a,b in zip(self.points,self.points[1:]))
        length=self.path_length
        set_status_text(self.summary,'%d点 · %.1fmm'%(len(self.points),length))
        self.signature=None
        self.update(self.busy)

    def image(self,target,parts,w,h):
        svg='<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">%s</svg>'%(w,h,''.join(parts))
        key=(id(target),w,h,svg)
        if key==getattr(self,'_image_key',None):
            native=getattr(target,'native',None)
            if native and native.ready and target is self.slice_image:
                self._native_scene=(self._coords_key,self.native_scene_key())
            elif native and target is self.slice_image:self.prepare_native()
            return
        layers=getattr(self,'_image_layers',None) if target is self.slice_image else None
        layers=layers or [parts]
        regions=getattr(self,'_image_regions',None) if target is self.slice_image else None
        if regions is None or len(regions)!=len(layers):regions=[(0,0,w,h)]*len(layers)
        cache=getattr(self,'_layer_cache',None)
        if cache is None or len(cache)!=len(layers):cache=[None]*len(layers)
        pixbuf=None
        for index,(layer,region) in enumerate(zip(layers,regions)):
            body=''.join(layer);x,y,rw,rh=region;layer_key=(w,h,body,region)
            cached=cache[index]
            if cached is None or cached[0]!=layer_key:
                bitmap=None
                if body and rw>0 and rh>0:
                    data='<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="%d %d %d %d">%s</svg>'%(rw,rh,x,y,rw,rh,body)
                    loader=GdkPixbuf.PixbufLoader.new_with_type('svg');loader.write(data.encode());loader.close();bitmap=loader.get_pixbuf()
                cached=(layer_key,bitmap);cache[index]=cached
            if pixbuf is None:pixbuf=cached[1].copy()
            elif cached[1] is not None:cached[1].composite(pixbuf,x,y,rw,rh,x,y,1,1,GdkPixbuf.InterpType.NEAREST,255)
        self._layer_cache=cache
        # Gtk.Image caches a Cairo surface for the supplied pixbuf. Replacing
        # the image invalidates that surface; mutating its bytes does not.
        target.set_from_pixbuf(pixbuf)
        self._image_key=key
        if target is self.slice_image:self.prepare_native()

    def prepare_native(self):
        native=getattr(self.slice_image,'native',None);cache=getattr(self,'_layer_cache',[])
        if native and len(cache)==5 and getattr(getattr(self,'combined',None),'canvas_fullscreen',False):
            w,h=self.size;regions=self._image_regions
            coords=self._point_coords;i,j,_=self.axes();sign=1 if self.flip.get_active() else -1
            point=self.combined.target();target_xy=(self.ox+point[i]*self.scale,self.oy+sign*(point[j]-self.vertical_offset)*self.scale)
            markers=[(*coords[n],5 if n==self.selected else 3,n+1) for n in self.visible_indices()]
            native.prepare(cache,regions,w,h,coords[-1] if coords else None,markers,target_xy)
            self._native_scene=(self._coords_key,self.native_scene_key())
            self._native_target=tuple(point);self._native_selected=self.selected

    def native_scene_key(self):
        return (self.render_allocation,self.plane.get_active_id(),self.cut.get_value(),self.direction.get_active_id(),self.flip.get_active(),
            self.auto_orientation.get_active(),id(self.model.preview),id(getattr(getattr(self.model,'drawing',None),'report',None)),
            id(self.model.workspace.data),self.model.workspace.compatible(self.task.controller.joint_limits.bounds,self.model.calibration),
            self.view_key,self.scale,self.ox,self.oy,self.vertical_offset)

    def native_append(self):
        native=getattr(self.slice_image,'native',None);scene=getattr(self,'_native_scene',None);pending=getattr(self,'_append_pending',None)
        if not native or not native.ready or not scene or not pending or self.stroke is None or not self.combined.canvas_fullscreen:return False
        a=self.slice_box.get_allocation()
        if (max(300,a.width),max(150,a.height))!=self.render_allocation or pending!=scene[0][:3] or scene[1]!=self.native_scene_key():return False
        start=scene[0][1];i,j,_=self.axes();sign=1 if self.flip.get_active() else -1
        added=[(self.ox+p['xyz'][i]*self.scale,self.oy+sign*(p['xyz'][j]-self.vertical_offset)*self.scale) for p in self.points[start:]]
        if not added:return False
        coords=self._point_coords;coords.extend(added)
        markers=[(*coords[n],5 if n==self.selected else 3,n+1) for n in self.visible_indices()]
        target=self.combined.target();target_xy=(self.ox+target[i]*self.scale,self.oy+sign*(target[j]-self.vertical_offset)*self.scale)
        if not native.append(added,markers,target_xy):
            del coords[start:];return False
        self._coords_key=(id(self.points),len(self.points),getattr(self,'points_revision',0),*scene[0][3:])
        self._native_scene=(self._coords_key,scene[1]);self._route_polyline=None;self._append_pending=None
        self._native_target=tuple(target);self._native_selected=self.selected
        return True

    def native_unchanged(self):
        native=getattr(self.slice_image,'native',None);scene=getattr(self,'_native_scene',None)
        if not native or not native.active or not native.ready or not scene or self._append_pending is not None:return False
        a=self.slice_box.get_allocation()
        return ((max(300,a.width),max(150,a.height))==self.render_allocation and scene[0][:3]==(id(self.points),len(self.points),getattr(self,'points_revision',0))
            and scene[1]==self.native_scene_key() and self._native_target==tuple(self.combined.target()) and self._native_selected==self.selected)

    def draw(self):
        if not hasattr(self,'scale'):
            return self.render()
        if self.native_append():
            self.cancel_render();return
        if self.render_timer is None:
            native=getattr(self.slice_image,'native',None)
            if self.stroke is not None and native and native.ready:self.render_timer=GLib.idle_add(self.flush_render,priority=GLib.PRIORITY_HIGH_IDLE)
            else:self.render_timer=GLib.timeout_add(16 if self.stroke is not None else 33,self.flush_render)

    def cancel_render(self,*_args):
        if self.render_timer is not None:
            GLib.source_remove(self.render_timer);self.render_timer=None
        timer=getattr(self,'fullscreen_footer_timer',None)
        if timer:GLib.source_remove(timer);self.fullscreen_footer_timer=None

    def refresh_fullscreen_footer(self):
        self.fullscreen_footer_timer=None
        if self.combined.canvas_fullscreen and getattr(self,'_fullscreen_editor_pending',False):
            set_status_text(self.summary,'%d点 · %.1fmm'%(len(self.points),self.path_length))
        return False

    def flush_render(self):
        self.render_timer=None;self.render();return False

    def render(self,force=False):
        if not hasattr(self,'index'):return
        if getattr(getattr(self,'combined',None),'jog_pending',False):
            self.signature=None
            return
        if not force and self.native_append():return
        if not force and self.native_unchanged():return
        w=max(300,self.slice_box.get_allocated_width());h=max(150,self.slice_box.get_allocated_height());self.size=(w,h)
        self.render_allocation=(w,h)
        i,j,fixed=self.axes();ws=self.model.workspace;key=self.direction.get_active_id()
        pose=self.model.cached_pose()
        if key=='hold':key=ws.direction(pose) if pose else None
        if self.auto_orientation.get_active():key='union'
        compatible=ws.compatible(self.task.controller.joint_limits.bounds,self.model.calibration)
        rows=ws.data['rows'].get(key or 'union',[]) if ws.data else []
        cut=round(self.cut.get_value()/10)*10
        slice_key=(id(ws.data),key,fixed,cut,compatible)
        cached=self.slice_cache
        rectangles=[] if cached is None or cached[0]!=slice_key else cached[1]
        if compatible and (cached is None or cached[0]!=slice_key):
            for z,y,runs in rows:
                for lo,hi in runs:
                    if fixed==2 and z==cut:rectangles.append((lo-5,y-5,hi-lo+10,10))
                    elif fixed==1 and y==cut:rectangles.append((lo-5,z-5,hi-lo+10,10))
                    elif fixed==0 and lo<=cut<=hi:rectangles.append((y-5,z-5,10,10))
        self.slice_cache=(slice_key,rectangles)
        preview=self.model.preview if hasattr(self,'combined') else None
        preview_xyz=(preview or {}).get('requested_path_xyz_mm') or [v['pose']['position_mm'] for v in (preview or {}).get('samples',[])]
        view_key=(w,h,i,j,cut,key,compatible,id(ws.data),id(preview))
        if view_key!=getattr(self,'view_key',None):
            self.view_key=view_key
            bounds=[(a,b) for a,b,dx,dy in rectangles]+[(a+dx,b+dy) for a,b,dx,dy in rectangles]
            route_key=(id(self.points),len(self.points),getattr(self,'points_revision',0),i,j)
            if route_key!=getattr(self,'_route_bounds_key',None):
                self._route_bounds_key=route_key
                self._route_bounds=([(min(p['xyz'][i] for p in self.points),min(p['xyz'][j] for p in self.points)),
                    (max(p['xyz'][i] for p in self.points),max(p['xyz'][j] for p in self.points))] if self.points else [])
            bounds += self._route_bounds
            bounds += [(p[i],p[j]) for p in preview_xyz]
            if hasattr(self,'combined'):
                target=self.combined.target();bounds.append((target[i],target[j]))
            if bounds:
                low=[min(p[n] for p in bounds) for n in (0,1)];high=[max(p[n] for p in bounds) for n in (0,1)]
            else:low=[-400,-400 if j==1 else -140];high=[400,400 if j==1 else 660]
            self.view_bounds=(low,high)
        low,high=self.view_bounds
        # Fill the allocated canvas, including the enlarged ordinary view.
        self.size=(w,h)
        self.scale=min((w-70)/max(80,(high[0]-low[0])*1.1),(h-60)/max(80,(high[1]-low[1])*1.1))
        self.ox=w/2-(low[0]+high[0])/2*self.scale;self.oy=h/2
        self.vertical_offset=(low[1]+high[1])/2
        sign=1 if self.flip.get_active() else -1
        px=lambda p:self.ox+p[i]*self.scale;py=lambda p:self.oy+sign*(p[j]-self.vertical_offset)*self.scale
        parts=['<rect width="100%" height="100%" fill="#f7f9fc"/>']
        if compatible and (key is None or key=='union'):parts.append('<text x="10" y="14" fill="#8a7655">合并工作区仅供参考，执行前须核验路径</text>')
        for n in range(-400,701,100):
            parts.append('<path d="M %.1f 16 V %d M 20 %.1f H %d" stroke="#dce5f1"/>'%(self.ox+n*self.scale,h-22,self.oy+sign*(n-self.vertical_offset)*self.scale,w-10))
        mask=[]
        if compatible:
            for a,b,dx,dy in rectangles:
                mask.append('M%.2f,%.2fh%.2fv%.2fh%.2fz'%(self.ox+a*self.scale,self.oy+sign*(b-self.vertical_offset)*self.scale,dx*self.scale,sign*dy*self.scale,-dx*self.scale))
            parts.append('<path d="%s" fill="#c9d9ef"/>'%''.join(mask))
        else:parts.append('<text x="10" y="22" fill="#8a7655">工作区数据与当前参数未匹配，仅显示线路</text>')
        if compatible and not mask:
            parts.append('<text x="10" y="32" fill="#8a7655">当前截面无工作区，请调整高度或朝向</text>')
        coords_key=(id(self.points),len(self.points),getattr(self,'points_revision',0),i,j,self.scale,self.ox,self.oy,self.vertical_offset,sign)
        if coords_key!=getattr(self,'_coords_key',None) or self._route_polyline is None:
            old_key=getattr(self,'_coords_key',None);pending=getattr(self,'_append_pending',None)
            incremental=bool(old_key and pending==old_key[:3] and old_key[0]==coords_key[0] and old_key[3:]==coords_key[3:])
            start=old_key[1] if incremental else 0
            ox,oy,scale,offset=self.ox,self.oy,self.scale,self.vertical_offset
            added=[(ox+v[i]*scale,oy+sign*(v[j]-offset)*scale) for v in (p['xyz'] for p in self.points[start:])]
            if incremental:self._point_coords.extend(added)
            else:self._point_coords=added
            if added:
                bounds=[min(p[0] for p in added),min(p[1] for p in added),max(p[0] for p in added),max(p[1] for p in added)]
                if incremental:
                    old=self._projected_bounds;bounds=[min(old[0],bounds[0]),min(old[1],bounds[1]),max(old[2],bounds[2]),max(old[3],bounds[3])]
                self._projected_bounds=bounds
            elif not incremental:self._projected_bounds=[0,0,0,0]
            self._coords_key=coords_key
            display_coords=self.display_route(self._point_coords)
            self._route_polyline=('<polyline points="%s" fill="none" stroke="#c08640" stroke-width="2"/>'%
                ' '.join('%.2f,%.2f'%p for p in display_coords)) if display_coords else ''
        coords=self._point_coords
        if preview_xyz:
            parts.append('<polyline points="%s" fill="none" stroke="#498f85" stroke-width="2"/>'%' '.join('%.2f,%.2f'%(px(p),py(p)) for p in preview_xyz))
            if (preview or {}).get('preview_scope'):
                parts.append('<text x="10" y="38" fill="#8a7655">请求路径；起步及制动已校验，后续由后台继续规划</text>')
        route=[self._route_polyline] if self._route_polyline else []
        markers=self.marker_svg(coords)
        target_parts=[]
        if hasattr(self,'combined'):
            target=self.combined.target();x,y=px(target),py(target)
            target_parts.append('<circle cx="%.2f" cy="%.2f" r="6" fill="#4a7ac2"/><text x="%.2f" y="%.2f" fill="#4a7ac2" font-size="11">目标</text>'%(x,y,x+8,y-5))
        ending=self.planned_svg(lambda p:(px(p),py(p)))
        ending.append('<text x="10" y="%d" fill="#7186a3">%s mm / %s mm · %s=%.1fmm</text>'%(h-5,'XYZ'[i],'XYZ'[j],'XYZ'[fixed],self.cut.get_value()))
        self._image_layers=(parts,route,markers,target_parts,ending)
        def region(boxes):
            if not boxes:return (0,0,0,0)
            left=max(0,min(w,math.floor(min(b[0] for b in boxes))));top=max(0,min(h,math.floor(min(b[1] for b in boxes))))
            right=max(left,min(w,math.ceil(max(b[2] for b in boxes))));bottom=max(top,min(h,math.ceil(max(b[3] for b in boxes))))
            return (left,top,right-left,bottom-top)
        a,b,c,d=self._projected_bounds
        marker_boxes=[(coords[n][0]-8,coords[n][1]-22,coords[n][0]+8+12*len(str(n+1)),coords[n][1]+9) for n in self.visible_indices()]
        self._image_regions=((0,0,w,h),region([(a-3,b-3,c+3,d+3)]) if route else (0,0,0,0),region(marker_boxes),
            region([(x-8,y-22,x+48,y+10)]) if target_parts else (0,0,0,0),
            (0,0,w,h) if getattr(getattr(self.model,'drawing',None),'report',None) else (0,max(0,h-26),w,min(26,h)))
        self.image(self.slice_image,parts+route+markers+target_parts+ending,w,h)
        self._append_pending=None
    def planned_svg(self,project):
        report=getattr(getattr(self.model,'drawing',None),'report',None)
        if not report:return []
        parts=[]
        for segment in report['segments']:
            samples=segment['samples'];stride=max(1,len(samples)//500)
            xyz=[p['pose']['position_mm'] for p in samples[::stride]]
            if samples:xyz.append(samples[-1]['pose']['position_mm'])
            color='#9273bd' if segment.get('orientation_adjusted') else '#b96f91' if segment.get('drawing_transition') else '#4f9680'
            parts.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.5"/>'%(' '.join('%.2f,%.2f'%project(p) for p in xyz),color))
            if segment.get('orientation_adjusted'):
                for sample in samples[::max(1,len(samples)//12)]:
                    p=sample['pose'];end=[v+15*row[2] for v,row in zip(p['position_mm'],p['rotation'])]
                    a=project(p['position_mm']);b=project(end)
                    parts.append('<path d="M %.2f %.2f L %.2f %.2f" stroke="#9273bd" stroke-width="1"/>'%(*a,*b))
        return parts

    def path_svg(self,coords):
        parts=[]
        if coords:parts.append('<polyline points="%s" fill="none" stroke="#c08640" stroke-width="2"/>'%' '.join('%.2f,%.2f'%p for p in coords))
        return parts+self.marker_svg(coords)

    @staticmethod
    def simplify_display(coords,tolerance=.2):
        """Bound only screen-space drawing error; never change route data."""
        if len(coords)<3:return coords
        keep={0,len(coords)-1};pending=[(0,len(coords)-1)];limit=tolerance*tolerance
        while pending:
            start,end=pending.pop();ax,ay=coords[start];bx,by=coords[end]
            dx,dy=bx-ax,by-ay;length=dx*dx+dy*dy;furthest=-1;maximum=limit
            for index in range(start+1,end):
                x,y=coords[index];px,py=x-ax,y-ay;dot=px*dx+py*dy
                if dot<=0 or length==0:distance=px*px+py*py
                elif dot>=length:distance=(x-bx)**2+(y-by)**2
                else:distance=(px*dy-py*dx)**2/length
                if distance>maximum:maximum=distance;furthest=index
            if furthest>=0:
                keep.add(furthest);pending.append((start,furthest));pending.append((furthest,end))
        return [coords[index] for index in sorted(keep)]

    def display_route(self,coords):
        # Short blocks keep work bounded. Immutable keys detect edits anywhere;
        # appending to a stable view only rebuilds the final block.
        cache=getattr(self,'_display_blocks',[]);blocks=[];result=[]
        for index,start in enumerate(range(0,max(1,len(coords)-1),128)):
            key=tuple(coords[start:start+129])
            cached=cache[index] if index<len(cache) else None
            if cached is None or cached[0]!=key:cached=(key,self.simplify_display(key))
            blocks.append(cached);result.extend(cached[1][bool(result):])
        self._display_blocks=blocks
        return result

    def visible_indices(self):
        key=(id(self.points),len(self.points),getattr(self,'points_revision',0),self.selected)
        if key!=getattr(self,'_visible_key',None):
            self._visible_key=key
            data_key=key[:3]
            if data_key!=getattr(self,'_marker_key',None):
                pending=getattr(self,'_append_pending',None);old=getattr(self,'_marker_key',None)
                if old and pending==old and old[0]==data_key[0]:
                    indices=self._marker_indices;start=max(0,old[1]-1)
                    while indices and indices[-1]>=start:indices.pop()
                    last=len(self.points)-1
                    for n in range(start,len(self.points)):
                        stroke=self.points[n].get('stroke')
                        if (stroke is None or n==0 or n==last or self.points[n-1].get('stroke')!=stroke or self.points[n+1].get('stroke')!=stroke):indices.append(n)
                else:indices=drawing.visible_indices(self.points,None)
                self._marker_key=data_key;self._marker_indices=indices
            base=self._marker_indices
            indices=sorted(set((base[:9]+base[-9:] if len(base)>20 else base)+([self.selected] if 0<=self.selected<len(self.points) else [])))
            if len(base)>20 or len(indices)>20:indices=sorted(set(indices[:8]+indices[-8:]+[self.selected]))
            self._visible_indices=indices
        return self._visible_indices

    def marker_svg(self,coords):
        parts=[]
        for i in self.visible_indices():
            x,y=coords[i];parts.append('<circle cx="%.2f" cy="%.2f" r="%d" fill="#c08640"/><text x="%.2f" y="%.2f" fill="#536c90" font-size="11">%d</text>'%(x,y,5 if i==self.selected else 3,x+6,y-4,i+1))
        return parts

    def update(self,busy):
        if hasattr(self,'combined'):self.combined.update_jog()
        self.busy=busy
        def sensitive(widget,value):
            if widget.get_sensitive()!=bool(value):widget.set_sensitive(bool(value))
        for w in (self.direction,self.plane,self.cut,self.flip,self.free,self.mode,self.speed,self.joint_speed,self.acc_override,self.auto_orientation,self.index,*self.xyz):sensitive(w,not busy)
        sensitive(self.acc,not busy and self.acc_override.get_active())
        ready=self.model.ready();sensitive(self.plan_button,not busy and ready and bool(self.points) and self.direction.get_active_id()!='union')
        reference_needed=not ready and bool((self.model.calibration or {}).get('configuration_locked'))
        if self.reference_box.get_no_show_all()==reference_needed:self.reference_box.set_no_show_all(not reference_needed)
        if self.reference_box.get_visible()!=reference_needed:
            if reference_needed:self.reference_box.show_all()
            else:self.reference_box.hide()
        sensitive(self.reference_confirm,not busy)
        try:self.model.check_cad_reference_configuration();can_confirm=True
        except (ValueError,RuntimeError):can_confirm=False
        sensitive(self.reference_button,not busy and can_confirm and self.reference_confirm.get_active())
        report=getattr(getattr(self.model,'drawing',None),'report',None)
        progressive=report.get('progressive') if report else None
        if progressive:progressive.refresh_preview()
        matching=bool(report and report['document']==self.document() and report['context']==self.model.continuous._context())
        if progressive and progressive.error:matching=False
        sensitive(self.execute,not busy and ready and matching and self.window.safety.get_active())
        reason=('任务进行中' if busy else
                self.model.readiness_notice() if not ready else
                '请先绘制路径' if not self.points else
                '合并区仅供查看，请选择朝向' if self.direction.get_active_id()=='union' else
                '请准备线路' if not matching else
                '已准备，请确认运动区域安全' if not self.window.safety.get_active() else
                '已准备，可以执行')
        if progressive and ready and not busy:
            reason=('后台核验失败：'+progressive.error if progressive.error else
                '全线路已核验，可以执行' if progressive.done else
                '首段已核验，后续核验中')
        set_status_text(self.gate_notice,reason)
        cal=self.model.calibration or {}
        cal_signature=(tuple(cal.get('signs',[])),tuple(cal.get('offsets_deg',[])),repr(self.task.controller.joint_limits.bounds))
        set_status_text(self.calibration_notice,'模型标定：固定参数 · '+(' / '.join('J%d %s'%(i+1,'同向' if s==1 else '反向') for i,s in enumerate(cal.get('signs',[]))) if cal else '尚未加载'))
        signature=(self.plane.get_active_id(),self.direction.get_active_id(),self.cut.get_value(),self.flip.get_active(),self.auto_orientation.get_active(),ready,id(report),getattr(progressive,'revision',0),id(self.model.preview),cal_signature)
        if signature!=self.signature and not getattr(getattr(self,'combined',None),'jog_pending',False):
            self.signature=signature;self.draw()
        if self.task.phase.startswith('绘图') or self.task.busy or '绘图' in self.task.message or '绘制线路' in self.task.message:
            set_status_text(self.notice,self.task.phase+' · '+self.task.message)
        if hasattr(self,'combined') and hasattr(self.combined,'show_jog_status'):self.combined.show_jog_status()
