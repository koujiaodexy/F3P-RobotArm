"""GTK3 image workspace for the board's existing desktop runtime."""

from __future__ import annotations

from pathlib import Path
import threading

from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk

from .vision import VisionParameters, VisionSession, export_paths, preview_png


class VisionPages(Gtk.Stack):
    """Only the visible workspace contributes its minimum height."""
    __gsignals__={'switch-page':(GObject.SignalFlags.RUN_LAST,None,(Gtk.Widget,int))}

    def __init__(self):
        super().__init__();self.pages=[]
        self.set_hhomogeneous(False);self.set_vhomogeneous(False)
        self.set_transition_type(Gtk.StackTransitionType.NONE)
        self.connect('notify::visible-child',self._changed)

    def append_page(self,widget,_label):
        self.pages.append(widget);self.add_named(widget,str(len(self.pages)-1))

    def set_current_page(self,number):
        if 0<=number<len(self.pages):
            self.pages[number].show();self.set_visible_child(self.pages[number])

    def get_current_page(self):
        child=self.get_visible_child()
        return self.pages.index(child) if child in self.pages else -1

    def _changed(self,*_):
        child=self.get_visible_child()
        if child is not None:self.emit('switch-page',child,self.get_current_page())


class VisionWindow(Gtk.Window):
    def __init__(self, parent, stop):
        super().__init__(title="F3P 图像处理 · 轮廓提取")
        self.set_transient_for(parent)
        self.set_default_size(1280, 720)
        self.set_size_request(1050, 650)
        self.owner = parent
        self._fit_cache = None
        self.export_dialog = None
        self._export_busy = False
        self.stop = stop
        self.session = VisionSession(lambda completion: GLib.idle_add(self._complete, completion))
        self.checks = []
        self.connect("delete-event", self._hide)
        self.connect("key-press-event", self._key)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_border_width(16)
        self.add(outer)
        header = Gtk.Box(spacing=12)
        title = Gtk.Label(label="轮廓提取", xalign=0)
        title.get_style_context().add_class("title")
        header.pack_start(title, True, True, 0)
        self.exit_button = Gtk.Button(label="退出图像处理")
        self.exit_button.connect("clicked", self._hide)
        header.pack_end(self.exit_button, False, False, 0)
        button = Gtk.Button(label="■ 停止电机")
        button.get_style_context().add_class("vision-stop")
        button.connect("clicked", lambda *_: stop())
        header.pack_end(button, False, False, 0)
        outer.pack_start(header, False, False, 0)
        columns = Gtk.Box(spacing=12)
        outer.pack_start(columns, True, True, 0)

        left = self._card()
        left.set_size_request(235, -1)
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        left_scroll.set_overlay_scrolling(False)
        left_scroll.set_min_content_width(275)
        left_scroll.set_size_request(300, -1)
        left_scroll.add(left)
        columns.pack_start(left_scroll, False, False, 0)

        self._caption(left, "1 · 图片")
        self.import_button = Gtk.Button(label="＋ 导入物品图片")
        self.import_button.connect("clicked", self._import)
        left.pack_start(self.import_button, False, False, 0)
        self.file_label = Gtk.Label(label="尚未导入图片", xalign=0)
        self.file_label.set_line_wrap(True)
        self.file_label.set_max_width_chars(24)
        left.pack_start(self.file_label, False, False, 0)
        self.scope = Gtk.CheckButton(label="包含内部边界")
        left.pack_start(self.scope, False, False, 0)
        self.method = Gtk.ComboBoxText()
        for text in ["自动阈值", "手动阈值"]:
            self.method.append_text(text)
        self.method.set_active(0)
        self.threshold = Gtk.SpinButton.new_with_range(0, 255, 1)
        self.threshold.set_value(128)
        self.threshold.set_sensitive(False)
        self.blur = Gtk.ComboBoxText()
        for value in [0] + list(range(1, 22, 2)):
            self.blur.append_text(str(value))
        self.blur.set_active(2)
        self.blur.set_tooltip_text('0：不去噪；1～21：奇数高斯滤波窗口。')
        self.area = Gtk.SpinButton.new_with_range(1, 40000000, 1)
        self.area.set_value(200)
        self.epsilon = Gtk.SpinButton.new_with_range(0.5, 20, 0.5)
        self.epsilon.set_digits(1)
        self.epsilon.set_value(2)
        for caption, widget in [("分割方法", self.method), ("二值化阈值", self.threshold),
                                ("去噪强度", self.blur), ("最小面积 / 原图 px²", self.area),
                                ("路径简化 / 原图 px", self.epsilon)]:
            self._caption(left, caption)
            left.pack_start(widget, False, False, 0)
        for widget, chars in ((self.threshold, 3), (self.area, 8), (self.epsilon, 5)):
            widget.set_width_chars(chars)
            widget.set_hexpand(True)
        self.process_button = Gtk.Button(label="提取轮廓")
        self.process_button.connect("clicked", self._process)
        left.pack_end(self.process_button, False, False, 0)

        center = self._card()
        self._caption(center, "2 · 预览")
        columns.pack_start(center, True, True, 0)
        self.view = Gtk.ComboBoxText()
        for text in ["原图", "二值图", "轮廓", "叠加"]:
            self.view.append_text(text)
        self.view.set_active(0)
        self.view.connect("changed", self._render)
        center.pack_start(self.view, False, False, 0)
        self.image = Gtk.Image()
        self.placeholder = Gtk.Label(label="导入图片后提取轮廓")
        self.placeholder.set_line_wrap(True)
        self.placeholder.set_max_width_chars(30)
        center.pack_start(self.placeholder, False, False, 0)
        self.viewport = Gtk.ScrolledWindow()
        self.viewport.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.viewport.add(self.image)
        self.viewport.set_size_request(300, 200)
        self.viewport.connect("size-allocate", self._fit)
        self.pixbuf = None
        center.pack_start(self.viewport, True, True, 0)
        self.dimensions = Gtk.Label(label="像素坐标", xalign=0)
        center.pack_end(self.dimensions, False, False, 0)

        right = self._card()
        right.set_size_request(235, -1)
        columns.pack_start(right, False, False, 0)
        self._caption(right, "3 · 轮廓")
        self.stats = Gtk.Label(label="尚无处理结果", xalign=0)
        self.stats.set_line_wrap(True)
        self.stats.set_max_width_chars(24)
        right.pack_start(self.stats, False, False, 0)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.list_box)
        right.pack_start(scroll, True, True, 0)
        self._caption(right, "4 · 导出")
        self.svg = Gtk.Button(label="导出 SVG")
        self.json = Gtk.Button(label="导出路径 JSON")
        self.svg.connect("clicked", lambda *_: self._export("svg"))
        self.json.connect("clicked", lambda *_: self._export("json"))
        right.pack_start(self.svg, False, False, 0)
        right.pack_start(self.json, False, False, 0)
        note = Gtk.Label(label="原点在左上角，X向右、Y向下。\n仅导出像素路径，不启动机械臂。空格键可停止电机。", xalign=0)
        note.set_line_wrap(True)
        note.set_max_width_chars(22)
        note.get_style_context().add_class("subtitle")
        self.details_expander = Gtk.Expander(label='说明')
        self.details_expander.set_size_request(-1, 48)
        self.details_expander.add(note)
        right.pack_start(self.details_expander, False, False, 0)
        self.status = Gtk.Label(label="就绪 · 支持 PNG / JPEG / BMP / WebP", xalign=0)
        self.status.set_line_wrap(True)
        self.status.set_max_width_chars(100)
        outer.pack_end(self.status, False, False, 0)
        for widget, signal in [(self.method, "changed"), (self.scope, "toggled"),
                               (self.threshold, "value-changed"), (self.blur, "changed"),
                               (self.area, "value-changed"), (self.epsilon, "value-changed")]:
            widget.connect(signal, self._changed)
        self.get_style_context().add_class("vision-window")
        from .gtk_touch import reserve_label
        for label,chars,lines in ((self.file_label,24,2),(self.stats,24,4),
                                 (self.dimensions,1,1),(self.status,1,2)):
            reserve_label(label,chars,lines)
        self._buttons()
        if getattr(parent,'_simulation_mode',False):
            title.set_text('图像处理 / 仿真预览')
        if hasattr(parent,'_numeric_keyboard'):parent._numeric_keyboard.bind_tree(outer)
        def fit_vision_column(_window, allocation):
            scale = max(1.0, min(1.75, allocation.height / 800.0))
            scrollbar = left_scroll.get_vscrollbar().get_preferred_width()[0]
            required = max(round(300 * scale), left.get_preferred_width()[0] + scrollbar + 8)
            if left_scroll.get_size_request()[0] != required:
                left_scroll.set_size_request(required, -1)
        parent.connect('size-allocate', fit_vision_column)
        fit_vision_column(parent, parent.get_allocation())
        # Keep both image workflows inside the existing console workspace.
        from .gtk_hardware_vision import HardwareVisionPanel
        self.hardware_panel = HardwareVisionPanel(parent, self._hide, stop)
        from .gtk_coco_objects import CocoObjectsPanel
        self.coco_panel = CocoObjectsPanel(parent, self.hardware_panel, self._hide, stop)
        from .gtk_grasp_preview import GraspPreviewPanel
        self.grasp_panel = GraspPreviewPanel(parent, self.coco_panel, self._hide, stop)
        self.notebook = VisionPages()
        self.remove(outer)
        self.notebook.append_page(self.hardware_panel.widget, Gtk.Label(label='彩色积木识别'))
        self.notebook.append_page(outer, Gtk.Label(label='静态轮廓提取'))
        self.notebook.append_page(self.grasp_panel.widget, Gtk.Label(label='全自动夹取'))
        workspace = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        switcher = Gtk.Box(spacing=16)
        switcher.set_homogeneous(True)
        switcher.set_margin_top(24)
        switcher.set_margin_start(24)
        switcher.set_margin_end(24)
        self.page_buttons = []
        for number, caption in enumerate(('彩色积木识别', '静态轮廓提取', '全自动夹取')):
            button = Gtk.Button(label=caption)
            button.set_size_request(240, 72)
            button.set_can_focus(False)
            button.connect('clicked', lambda _button, page=number: self.notebook.set_current_page(page))
            switcher.pack_start(button, True, True, 0)
            self.page_buttons.append(button)
        workspace.pack_start(switcher, False, False, 0)
        workspace.pack_start(self.notebook, True, True, 0)
        self.add(workspace)
        self.notebook.show_all()
        self.notebook.set_current_page(2)
        self.notebook.connect('switch-page', self._page_switched)
        self._page_switched(self.notebook, None, 2)

    def _page_switched(self, _book, _page, number):
        for index, button in enumerate(self.page_buttons):
            context = button.get_style_context()
            (context.add_class if index == number else context.remove_class)('active')
        if number != 2:
            self.grasp_panel.suspend()
        self.coco_panel.preview_target = self.grasp_panel.preview if number == 2 else None
        if number != 2:
            self.coco_panel.suspend()
        self.hardware_panel.preview_target = None
        if number in (1,2):
            self.hardware_panel.stop()


    @staticmethod
    def _card():
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        box.get_style_context().add_class("card")
        return box

    @staticmethod
    def _caption(box, text):
        label = Gtk.Label(label=text, xalign=0)
        label.get_style_context().add_class("section")
        box.pack_start(label, False, False, 0)

    def _selected(self):
        return [path_id for path_id, button in self.checks if button.get_active()]

    def _clear(self):
        self.checks = []
        for child in self.list_box.get_children():
            self.list_box.remove(child)

    def _buttons(self):
        enabled = self.session.result is not None and bool(self._selected()) and not self.session.busy and not self._export_busy
        for button, active in ((self.import_button, not self.session.busy),
                (self.process_button, self.session.source is not None and not self.session.busy),
                (self.svg, enabled), (self.json, enabled)):
            if button.get_sensitive() != active:
                button.set_sensitive(active)

    def _changed(self, *_):
        self.threshold.set_sensitive(self.method.get_active() == 1)
        self.session.invalidate()
        self._clear()
        self.stats.set_text("参数已修改 · 请重新提取")
        self.status.set_text("处理结果已过期，导出已禁用。")
        self._render()
        self._buttons()

    def _import(self, *_):
        dialog = Gtk.FileChooserDialog(title="导入物品图片", transient_for=self.owner,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons("取消", Gtk.ResponseType.CANCEL, "导入", Gtk.ResponseType.OK)
        filter = Gtk.FileFilter()
        filter.set_name("图片 PNG / JPEG / BMP / WebP")
        for pattern in ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp", "*.PNG", "*.JPG", "*.JPEG", "*.BMP", "*.WEBP"]:
            filter.add_pattern(pattern)
        dialog.add_filter(filter)
        response = dialog.run()
        filename = dialog.get_filename()
        dialog.destroy()
        if response == Gtk.ResponseType.OK and filename:
            self._clear()
            self.stats.set_text("正在加载新图片…")
            self.session.start(filename=filename)
            self.status.set_text("正在读取图片…")
            self._buttons()

    def _process(self, *_):
        self._clear()
        parameters = VisionParameters(self.scope.get_active(), self.method.get_active() == 0,
                                      self.threshold.get_value_as_int(), int(self.blur.get_active_text()),
                                      self.area.get_value_as_int(), self.epsilon.get_value())
        self.session.start(parameters=parameters)
        self.status.set_text("正在提取轮廓…")
        self._buttons()

    def _complete(self, completion):
        outcome = self.session.accept(completion)
        if self.session.closed:
            return False
        if outcome == "stale":
            self.status.set_text("参数已变更，本次结果已丢弃；请重新提取。")
        elif outcome:
            self.status.set_text(outcome)
        else:
            self._updating_preview = True
            source = self.session.source
            self.file_label.set_text(Path(source["filename"]).name)
            self.dimensions.set_text(f'{source["width"]} × {source["height"]} px · 原图像素坐标')
            self.placeholder.hide()
            if self.session.result is not None:
                self._clear()
                for path in self.session.result["paths"]:
                    kind = "内部" if path["parent_id"] else "外部"
                    button = Gtk.CheckButton(label=f'{path["id"]:02d} {kind}边界 · {len(path["points"])} 点')
                    button.set_active(True)
                    self.checks.append((path["id"], button))
                    button.connect("toggled", self._selection_changed)
                    self.list_box.pack_start(button, False, False, 0)
                self.list_box.show_all()
                self.view.set_active(3)
                self.status.set_text("提取完成，请确认轮廓再导出。" if self.checks
                                     else "未找到符合条件的轮廓，请调整阈值或最小面积。")
            else:
                self.view.set_active(0)
                self.stats.set_text("图片已载入 · 等待提取")
                self.status.set_text("图片已载入，可调整参数后提取。")
            self._updating_preview = False
            self._show_preview_png(completion[3])
            self._preview_key = self._current_preview_key()
            self._selection_changed(render=False)
        self._buttons()
        return False

    def _current_preview_key(self):
        return (self.session.revision,self.view.get_active(),tuple(self._selected()))

    def _show_preview_png(self, data):
        loader=GdkPixbuf.PixbufLoader.new_with_type('png')
        loader.write(data);loader.close()
        self.pixbuf=loader.get_pixbuf();self._fit()

    def _render(self, *_):
        if self.session.source is None or getattr(self,'_updating_preview',False): return
        key=self._current_preview_key()
        if getattr(self,'_preview_key',None)==key:
            self._fit();return
        try:
            data=preview_png(self.session.source,self.session.result,
                ['original','binary','contour','overlay'][self.view.get_active()],self._selected())
            self._show_preview_png(data);self._preview_key=key
        except Exception as exc: self.status.set_text(str(exc))

    def _fit(self, *_):
        if self.pixbuf is None:
            return
        allocation = self.viewport.get_allocation()
        factor = min((max(1, allocation.width - 12)) / self.pixbuf.get_width(),
                     (max(1, allocation.height - 12)) / self.pixbuf.get_height(), 1.0)
        width=max(1,round(self.pixbuf.get_width()*factor))
        height=max(1,round(self.pixbuf.get_height()*factor))
        key=(id(self.pixbuf),width,height)
        if self._fit_cache == key: return
        self._fit_cache=key
        self.image.set_from_pixbuf(self.pixbuf if factor==1 else self.pixbuf.scale_simple(width,height,GdkPixbuf.InterpType.BILINEAR))

    def _selection_changed(self, *_, render=True):
        if self.session.result is not None:
            selected = self._selected()
            count = sum(len(p["points"]) for p in self.session.result["paths"] if p["id"] in selected)
            self.stats.set_text(f"选中 {len(selected)} 条轮廓 · {count} 个路径点")
            if render: self._render()
        self._buttons()

    def _export(self, format):
        if self.session.result is None or not self._selected() or self._export_busy:return
        self._export_format=format
        if self.export_dialog is None:
            self.export_dialog=Gtk.Dialog(title='保存轮廓路径',transient_for=self.owner,modal=True)
            self.export_dialog.add_buttons('取消',Gtk.ResponseType.CANCEL,'保存',Gtk.ResponseType.OK)
            self.export_dialog.set_default_size(660,160)
            box=self.export_dialog.get_content_area();box.set_border_width(12);box.set_spacing(8)
            box.pack_start(Gtk.Label(label='保存路径（可以修改）',xalign=0),False,False,0)
            self.export_entry=Gtk.Entry();box.pack_start(self.export_entry,False,False,0)
            box.show_all()
            self.export_dialog.connect('response',self._save_export)
            self.export_dialog.connect('delete-event',lambda dialog,event:(dialog.hide(),True)[1])
        from .recorder import default_directory
        self.export_entry.set_text(str(default_directory()/('contours.'+format)))
        self.export_dialog.show();self.export_dialog.present()

    def _save_export(self, dialog, response):
        dialog.hide()
        if response!=Gtk.ResponseType.OK:return
        filename=self.export_entry.get_text().strip();format=self._export_format
        if not filename:self.status.set_text('保存路径不能为空');return
        if not filename.lower().endswith('.'+format):filename+='.'+format
        if Path(filename).exists():
            confirm=Gtk.MessageDialog(transient_for=self.owner,modal=True,buttons=Gtk.ButtonsType.YES_NO,text='该文件已存在，是否覆盖？')
            accepted=confirm.run()==Gtk.ResponseType.YES;confirm.destroy()
            if not accepted:return
        result,selected=self.session.result,self._selected()
        if result is None or not selected:return
        self._export_busy=True;self._buttons();self.status.set_text('正在保存轮廓…')
        def work():
            error=''
            try:
                from .recorder import user_owns
                created=not Path(filename).parent.exists()
                Path(filename).parent.mkdir(parents=True,exist_ok=True)
                if created:user_owns(Path(filename).parent)
                export_paths(result,selected,filename,format);user_owns(Path(filename))
            except Exception as exc:error=str(exc)
            GLib.idle_add(self._exported,not error,error or filename)
        threading.Thread(target=work,daemon=True,name='f3p-path-export').start()

    def _exported(self, ok, message):
        self._export_busy=False
        if not self.session.closed:
            self.status.set_text(('已保存：' if ok else '导出失败：')+message);self._buttons()
        return False

    def _key(self, _widget, event):
        if event.keyval == Gdk.KEY_space:
            self.stop()
            return True
        if event.keyval == Gdk.KEY_Escape:
            self._hide()
            return True
        return False

    def _hide(self, *_):
        self.grasp_panel.suspend()
        self.coco_panel.suspend()
        if hasattr(self.owner,'_return_to_control'): self.owner._return_to_control()
        else:
            self.hide(); self.owner.present()
        return True
