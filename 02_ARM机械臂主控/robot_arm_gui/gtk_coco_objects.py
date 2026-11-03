"""On-demand COCO recognition, selection and explicit coordinate configuration."""
import copy,json,time
from pathlib import Path
from gi.repository import Gdk,GdkPixbuf,GLib,Gtk
from .coco_objects import CHINESE,position_profile,RETAINED_IDS
from .coco_session import CocoSession
from .gtk_touch import set_status_text

class CocoObjectsPanel:
    def __init__(self,owner,hardware,leave,stop,session=None,config=None):
        self.owner,self.hardware,self.leave,self.stop_motors=owner,hardware,leave,stop
        self.session=session or CocoSession();self.config=Path(config or Path.home()/'.config/f3p-control/coco-grasp-profiles.json')
        self.selected=None;self.closed=False;self._report=None;self._stamp=None;self._tick=0
        self._start_requested=False;self._configure_when_stopped=False;self.dialog=None
        self.hardware_mode=False;self._window_stamp=0.;self._result_signature=None;self._result_buttons=[]
        self.preview_target=None
        self._ui_stamp=None;self._image_key=None
        self._desktop_pixbuf=None;self._desktop_surface=None;self._desktop_image=None;self._desktop_stamp=0.
        self.widget=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin=16)
        header=Gtk.Box(spacing=12)
        header.pack_start(self.label('物品识别'),True,True,0)
        header.pack_end(self.button('返回主界面',lambda *_:self._leave()),False,False,0)
        header.pack_end(self.button('■ 停止电机',lambda *_:stop()),False,False,0)
        self.widget.pack_start(header,False,False,0)
        actions=Gtk.Box(spacing=12)
        self.start_button=self.button('开始识别',self.start)
        self.stop_button=self.button('结束识别',lambda *_:self.session.stop())
        self.configure_button=self.button('配置抓取 / 投放位置',lambda *_:self.configure())
        self.configure_button.set_sensitive(False)
        for button in (self.start_button,self.stop_button,self.configure_button):actions.pack_start(button,False,False,0)
        self.widget.pack_start(actions,False,False,0)
        body=Gtk.Box(spacing=16);self.widget.pack_start(body,True,True,0)
        left=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);body.pack_start(left,True,True,0)
        self.image=Gtk.Image()
        self.preview=Gtk.EventBox();self.preview.set_visible_window(True);self.preview.set_size_request(576,324)
        self.preview.override_background_color(Gtk.StateFlags.NORMAL,Gdk.RGBA(0,0,0,1))
        layer=Gtk.Overlay();layer.add(Gtk.Box());layer.add_overlay(self.image);self.preview.add(layer)
        self.preview._coco_desktop_image=self.image
        self.placeholder=self.label('尚未启动物品识别');left.pack_start(self.placeholder,False,False,0)
        left.pack_start(self.preview,True,True,0)
        self.status=self.label('点击开始识别')
        self.status.set_line_wrap(True);left.pack_end(self.status,False,False,0)
        right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);right.set_size_request(380,-1)
        body.pack_start(right,False,False,0)
        right.pack_start(self.label('识别到的物品 / 点击选择'),False,False,0)
        self.results=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False);scroll.add(self.results);right.pack_start(scroll,True,True,0)
        self.choice=self.label('尚未选择物品');self.choice.set_line_wrap(True);right.pack_end(self.choice,False,False,0)
        self.details_expander=Gtk.Expander(label='识别说明')
        self.details_expander.set_size_request(-1,48)
        detail=self.label('红、黄、绿积木，苹果、橘子、香蕉。\n单帧确认 · 置信度0.30 · 本地NPU\n选择物品可配置坐标；自动取货请在货架任务中设置。')
        detail.set_line_wrap(True);detail.set_max_width_chars(28)
        self.details_expander.add(detail);right.pack_end(self.details_expander,False,False,0)
        self.widget.connect('destroy',self.destroy)
        self._tick=GLib.timeout_add(33,self.poll)

    @staticmethod
    def label(text):return Gtk.Label(label=text,xalign=0)
    @staticmethod
    def button(text,callback):
        button=Gtk.Button(label=text);button.set_size_request(-1,64);button.connect('clicked',callback);return button

    def start(self,*_):
        if self.closed or self.session.running:return
        self.selected=None;self.configure_button.set_sensitive(False);set_status_text(self.choice, '尚未选择物品')
        self._stamp=None;self._report=None
        self._ui_stamp=None;self._image_key=None
        self._result_signature=None;self._result_buttons=[];self.hardware_mode=False
        for child in self.results.get_children():self.results.remove(child)
        try:
            if self.hardware.session.running:
                self._start_requested=True;set_status_text(self.status, '正在结束色块识别，准备物品检测…')
                self.hardware.stop(on_stopped=self._camera_stopped);return
            self._begin()
        except Exception as exc:set_status_text(self.status, str(exc))

    def _camera_stopped(self):
        if self._start_requested and not self.closed:
            self._start_requested=False;self._begin()

    def _begin(self):
        try:
            if self.session.start():set_status_text(self.status, '正在加载本地物品模型并打开摄像头…')
        except Exception as exc:set_status_text(self.status, str(exc))

    def poll(self):
        if self.closed:return False
        report=self.session.poll()
        if report:self.hardware_mode=report.get('preview_transport')=='fpga_hdmi'
        self._preview_geometry()
        self._desktop_preview(getattr(self.session,'desktop_telemetry',None) or report)
        for button,enabled in ((self.start_button,not self.session.running and not self._start_requested),
                               (self.stop_button,self.session.running)):
            if button.get_sensitive()!=enabled:button.set_sensitive(enabled)
        if not self.session.running:
            if self.session.error:set_status_text(self.status, self.session.error)
            elif self.selected:set_status_text(self.status, '已选中物品，识别已结束。可继续配置抓取与投放位置。')
            elif report and report.get('state')=='stopped':set_status_text(self.status, '本次识别已结束。')
            return True
        if report and report.get('state')=='failed':set_status_text(self.status, report.get('error','识别失败'));return True
        if self.session.stopping:
            set_status_text(self.status, '正在结束识别并释放NPU…');return True
        if not report or report.get('state')!='running':return True
        # The automatic grasp page shares this camera/NPU owner. Its own
        # status is refreshed from the same report; hidden result buttons
        # must not take time or republish a different preview rectangle.
        if self.preview_target is not None:return True
        if not self.widget.get_mapped():return True
        stamp=report.get('captured_at')
        self._stamp=stamp
        if self.placeholder.get_visible():self.placeholder.hide()
        # Keep session polling and image presentation at their existing rate.
        # Only text/list rendering is bounded; control uses session.telemetry.
        now=time.monotonic()
        if self._ui_stamp is not None and now-self._ui_stamp<.2:return True
        self._ui_stamp=now
        try:targets=self.session.targets()
        except Exception as exc:set_status_text(self.status, str(exc));return True
        self._report=copy.deepcopy(report)
        signature=tuple(row['class_id'] for row in targets)
        if signature!=self._result_signature:
            for child in self.results.get_children():self.results.remove(child)
            self._result_buttons=[]
            for index,row in enumerate(targets):
                button=self.button('',lambda _button,n=index:self.select(n,self._report))
                self.results.pack_start(button,False,False,0);self._result_buttons.append(button)
            if not targets:self.results.pack_start(self.label('尚未识别到物品，请调整摆放。'),False,False,0)
            self._result_signature=signature;self.results.show_all()
        for button,row in zip(self._result_buttons,targets):
            text='%s  %.0f%%'%(row['label'],100*row['confidence'])
            if button.get_label()!=text:button.set_label(text)
        fps=report.get('performance',{}).get('detection_fps',0.)
        display=report.get('preview_fps')
        rates='检测 %.0f 帧/秒'%fps
        if self.hardware_mode and isinstance(display,(int,float)):rates+=' · 画面 %.0f 帧/秒'%display
        set_status_text(self.status, '%d个物品 · %s'%(len(targets),rates))
        return True

    @staticmethod
    def _desktop_image_for(surface):
        image=getattr(surface,'_coco_desktop_image',None)
        if image is None:
            # Overlay children do not enlarge the preview's minimum size.
            layer=Gtk.Overlay();layer.add(Gtk.Box());image=Gtk.Image()
            layer.add_overlay(image);surface.add(layer);layer.show_all()
            surface._coco_desktop_image=image
        return image

    def _desktop_preview(self,report):
        """Paint into X11 as well as HDMI, so desktop sharing sees recognition."""
        surface=self.preview_target if self.preview_target is not None else self.preview
        if surface is not self._desktop_surface:
            if self._desktop_surface is not None:
                self._desktop_image.clear()
            self._desktop_surface=surface
            self._desktop_image=self._desktop_image_for(surface)
            self._image_key=None
            self._desktop_stamp=0.
        stamp=(report or {}).get('preview_captured_at',(report or {}).get('captured_at'))
        valid=(self.session.running and not self.session.stopping and report
               and report.get('state')=='running' and report.get('preview_name')
               and type(stamp) in (int,float) and 0<=time.monotonic()-stamp<=1.2)
        if not valid or report.get('desktop_stream_active',False):
            if self._desktop_pixbuf is not None:
                self._desktop_pixbuf=None;self._image_key=None;surface.queue_draw()
                self._desktop_image.clear()
            return
        if not surface.get_mapped():return
        # The independent PC stream carries all frames. Bound the redundant
        # X11 fallback to avoid spending board CPU scaling them a second time.
        now=time.monotonic()
        if self._image_key is not None and now-self._desktop_stamp<.2:return
        aw,ah=surface.get_allocated_width(),surface.get_allocated_height()
        zoom=max(2,min(8,aw//192,ah//108));width,height=192*zoom,108*zoom
        key=(str(self.session.preview_path),width,height)
        if key==self._image_key:return
        try:
            self._desktop_pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(key[0],width,height,True)
            self._image_key=key;self._desktop_image.set_from_pixbuf(self._desktop_pixbuf)
            self._desktop_stamp=now
            self._desktop_image.show()
        except (GLib.Error,OSError):
            self._desktop_pixbuf=None;self._image_key=None;self._desktop_image.clear()

    def _preview_geometry(self):
        if not self.session.running or time.monotonic()-self._window_stamp<.2:return
        self._window_stamp=time.monotonic();visible=False;x=y=0;width,height=576,324
        try:
            preview=self.preview_target if self.preview_target is not None else self.preview
            screen=Gdk.Screen.get_default();top=preview.get_toplevel()
            visible=(self.hardware_mode and preview.get_mapped() and top.has_toplevel_focus() and self.dialog is None
                and not self.session.stopping and screen.get_width()==1920 and screen.get_height()==1080)
            aw,ah=preview.get_allocated_width(),preview.get_allocated_height()
            zoom=max(2,min(8,aw//192,ah//108));width,height=192*zoom,108*zoom
            if visible:
                origin=preview.get_window().get_origin();x=int(origin[-2]+(aw-width)//2);y=int(origin[-1]+(ah-height)//2)
                visible=4<=x and x+width<=1920 and 0<=y and y+height<=1080
            self.session.set_window(x if visible else 0,y if visible else 0,visible,width,height)
        except (OSError,ValueError,AttributeError):self.session.stop()

    def select(self,index,displayed):
        try:self.selected=self.session.select(index,displayed)
        except Exception as exc:set_status_text(self.status, str(exc));return
        set_status_text(self.choice, '已选：%s\n配置前请核对实际物品。'%self.selected['label'])
        self.configure_button.set_sensitive(True)
        set_status_text(self.status, '已选中，正在结束本次识别…')
        for child in self.results.get_children():child.set_sensitive(False)

    def configure(self):
        if not self.selected:return
        if self.dialog is not None:self.dialog.present();return
        dialog=Gtk.Dialog(title=self.selected['label']+' / 抓取与投放位置',transient_for=self.owner,modal=True)
        self.dialog=dialog;dialog.set_default_size(750,430)
        dialog.add_button('取消',Gtk.ResponseType.CANCEL);dialog.add_button('保存配置',Gtk.ResponseType.OK)
        box=dialog.get_content_area();box.set_spacing(14);box.set_border_width(18)
        note=self.label('填写基座坐标，单位毫米。此处仅保存配置，不启动机械臂。');note.set_line_wrap(True);box.pack_start(note,False,False,0)
        grid=Gtk.Grid(column_spacing=16,row_spacing=12);box.pack_start(grid,True,True,0)
        previous={}
        try:
            existing=json.loads(self.config.read_text())
            if isinstance(existing,dict) and isinstance(existing.get(self.selected['name']),dict):
                previous=existing[self.selected['name']]
        except (OSError,ValueError):pass
        fields=[]
        for number,(caption,key) in enumerate((('抓取点','pick_xyz_mm'),('投放点','drop_xyz_mm'))):
            grid.attach(self.label(caption),0,number,1,1);row=[]
            old=previous.get(key,[])
            for axis in range(3):
                entry=Gtk.Entry();entry.set_width_chars(10);entry.set_size_request(170,60)
                entry.set_placeholder_text('XYZ'[axis]+' / mm')
                if isinstance(old,list) and len(old)==3:entry.set_text(str(old[axis]))
                grid.attach(entry,axis+1,number,1,1);row.append(entry)
            fields.append(row)
        error=self.label('');error.set_line_wrap(True);box.pack_start(error,False,False,0)
        keyboard=getattr(self.owner,'_f3p_numeric_keyboard',None)
        if keyboard is not None:keyboard.bind_tree(dialog)
        def response(_dialog,code):
            if code==Gtk.ResponseType.OK:
                try:
                    profile=position_profile(self.selected,*[[float(e.get_text().strip()) for e in row] for row in fields])
                    try:data=json.loads(self.config.read_text())
                    except (OSError,ValueError):data={}
                    if not isinstance(data,dict):raise ValueError('物品位置配置格式无效')
                    data[profile['name']]=profile
                    from .joint_motion import atomic_json
                    self.config.parent.mkdir(parents=True,exist_ok=True);atomic_json(self.config,data)
                except Exception as exc:set_status_text(error, str(exc));return
                set_status_text(self.status, '已保存%s的抓取和投放位置；尚未执行动作。'%self.selected['label'])
            self.dialog=None;dialog.destroy()
        dialog.connect('response',response);dialog.show_all()

    def suspend(self):
        self._start_requested=False;self.session.set_window(visible=False);self.session.stop()
    def _leave(self):self.suspend();self.leave()
    def destroy(self,*_):
        if self.closed:return
        self.closed=True;self.suspend()
        if self._desktop_surface is not None:
            self._desktop_image.clear()
            self._desktop_surface=None;self._desktop_pixbuf=None
        if self._tick:GLib.source_remove(self._tick);self._tick=0
        if self.dialog is not None:self.dialog.destroy();self.dialog=None
        if self.session.running:GLib.timeout_add(100,self._reap)

    def _reap(self):
        self.session.poll()
        return self.session.running
