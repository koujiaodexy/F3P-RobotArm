"""The console's colour parameters and lifecycle for FPGA camera preview."""
from dataclasses import replace
import time

from gi.repository import Gdk, GLib, Gtk

from .color_blocks import BlockParameters, COLORS, DEFAULT_BANDS, LABELS, config_path, load_profile, save_profile
from .hardware_preview_session import HardwarePreviewSession


class HardwareVisionPanel:
    def __init__(self, owner, leave, stop, session=None):
        self.owner, self.leave, self.stop_motors = owner, leave, stop
        self.session = session or HardwarePreviewSession()
        self.parameters, self.bands = BlockParameters(), dict(DEFAULT_BANDS)
        self._closed = self._updating = self._was_running = False
        self._callbacks = []
        self._last_valid = None
        self._last_timestamp = None
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.widget.set_border_width(8)
        self.widget.get_style_context().add_class('vision-root')
        self.widget.connect('realize',self._style_workspace)
        header = Gtk.Box(spacing=10)
        header.pack_start(Gtk.Label(label='彩色积木 / 实时识别', xalign=0), True, True, 0)
        self.exit_button = self.button('退出图像处理', lambda *_: leave())
        header.pack_end(self.exit_button, False, False, 0)
        emergency = self.button('■ 停止电机', lambda *_: stop())
        emergency.get_style_context().add_class('vision-stop')
        header.pack_end(emergency, False, False, 0)
        self.widget.pack_start(header, False, False, 0)
        actions = Gtk.Box(spacing=10)
        self.start_button = self.button('▶ 开始识别', self._start)
        self.stop_button = self.button('■ 停止识别', lambda *_: self.stop())
        actions.pack_start(self.start_button, False, False, 0)
        actions.pack_start(self.stop_button, False, False, 0)
        self.widget.pack_start(actions, False, False, 0)
        body = Gtk.Box(spacing=10)
        self.widget.pack_start(body, True, True, 0)
        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        controls.get_style_context().add_class('card')
        controls.get_style_context().add_class('vision-controls')
        compact_css=Gtk.CssProvider()
        compact_css.load_from_data(b'''
         .vision-root button { font-size: 17px; min-width: 56px; min-height: 56px; padding: 6px 10px; }
         .vision-root .card { padding: 4px 8px; border-radius: 12px; }
         .vision-controls spinbutton, .vision-controls spinbutton entry { font-size: 15px; min-height: 44px; padding: 0 2px; }
         .vision-controls spinbutton button { min-width: 64px; min-height: 64px; padding: 0; }
         .vision-preview { background-color: #060e16; background-image: none; border: 0; padding: 0; }
         .vision-root, .vision-pages, .vision-pages > stack { background-color: #f3f5f8; color: #52647e; font-size: 16px; }
         .vision-pages > header { background-color: #ffffff; color: #52647e; border-color: #e3e9f2; }
         .vision-pages tab { background-color: #f0f4fa; color: #52647e; }
         .vision-pages tab:checked { background-color: #edf3ff; color: #315f9f; }
         .vision-settings-scroll scrollbar slider { min-width: 28px; min-height: 64px; }
        ''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),compact_css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.controls = controls
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False)
        scroll.set_size_request(460, -1)
        self.settings_scroll = scroll
        scroll.get_style_context().add_class('vision-settings-scroll')
        scroll.add(controls)
        body.pack_start(scroll, False, False, 0)
        controls.pack_start(Gtk.Label(label='识别范围与过滤', xalign=0), False, False, 0)
        self.roi = Gtk.ComboBoxText()
        self.rois = [(0., 0., 1., 1.), (.1, .1, .8, .8), (.2, .2, .6, .6)]
        for name in ('完整画面', '中央 80%', '中央 60%'):
            self.roi.append_text(name)
        self.roi.set_active(0)
        self.roi.set_size_request(-1, 48)
        controls.pack_start(self.roi, False, False, 0)
        self.area = self.field(controls, '最小色块面积', 20, 100000, 20, 200)
        self.parameter_expander = Gtk.Expander(label='颜色参数')
        self.parameter_expander.set_size_request(-1, 48)
        advanced = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.parameter_expander.add(advanced)
        controls.pack_start(self.parameter_expander, False, False, 0)
        self.saturation = self.field(advanced, '红/蓝饱和度下限', 10, 240, 5, 70)
        self.green_saturation = self.field(advanced, '绿色饱和度下限', 10, 240, 5, 70)
        self.yellow_saturation = self.field(advanced, '黄色饱和度下限', 10, 240, 5, 70)
        self.brightness = self.field(advanced, '亮度下限', 5, 240, 5, 45)
        self.confirmations = self.field(advanced, '连续确认帧数', 1, 10, 1, 3)
        advanced.pack_start(Gtk.Label(label='颜色范围 / 色相 0～179', xalign=0), False, False, 0)
        self.band_fields = {}
        for color in COLORS:
            row = Gtk.Box(spacing=8)
            row.pack_start(Gtk.Label(label=LABELS[color] + '色', xalign=0), True, True, 0)
            center = Gtk.SpinButton.new_with_range(0, 179, 1)
            radius = Gtk.SpinButton.new_with_range(4, 30, 1)
            center.set_width_chars(3)
            radius.set_width_chars(2)
            center.set_size_request(76, 48)
            radius.set_size_request(72, 48)
            center.set_tooltip_text('色相中心，范围 0～179')
            radius.set_tooltip_text('色相半径，范围 4～30')
            row.pack_start(center, False, False, 0)
            row.pack_start(radius, False, False, 0)
            self.band_fields[color] = center, radius
            advanced.pack_start(row, False, False, 0)
        controls.pack_start(self.button('保存识别参数', self._save), False, False, 0)
        controls.pack_start(self.button('恢复默认参数', self._reset), False, False, 0)
        results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        results.get_style_context().add_class('card')
        body.pack_start(results, True, True, 0)
        hint = Gtk.Label(label='画面与识别框在右下角显示；空格键停止电机。', xalign=0)
        hint.set_line_wrap(True)
        # The action bar already identifies the preview; reserve height for it.
        self.result_title = Gtk.Label(label='最近识别结果', xalign=0)
        results.pack_start(self.result_title, False, False, 0)
        counts = Gtk.Box(spacing=10)
        counts.set_homogeneous(True)
        self.counters = {}
        for color in COLORS:
            label = Gtk.Label(label=LABELS[color] + '  0')
            label.set_size_request(80, 36)
            self.counters[color] = label
            counts.pack_start(label, True, True, 0)
        results.pack_start(counts, False, False, 0)
        self.details = Gtk.Label(label='尚无已确认目标', xalign=0, yalign=0)
        self.details.set_line_wrap(False)
        self.details.set_single_line_mode(True)
        self.details.set_selectable(True)
        self.details.set_max_width_chars(52)
        self.details.set_lines(1)
        self.details.set_ellipsize(3)
        self.details_expander = Gtk.Expander(label='识别详情')
        self.details_expander.set_size_request(-1, 48)
        diagnostics = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.details_expander.add(diagnostics)
        diagnostics.pack_start(self.details, False, False, 0)
        self.stream_metrics = Gtk.Label(label='图像坐标 / 像素', xalign=0)
        self.stream_metrics.set_ellipsize(3)
        diagnostics.pack_start(self.stream_metrics, False, False, 0)
        self.metrics = Gtk.Label(label='等待开始识别', xalign=0)
        self.metrics.set_ellipsize(3)
        results.pack_start(self.metrics, False, False, 0)
        self.preview_pixbuf = None
        self.preview_frames = self.preview_draws = 0
        self._metrics_stamp = 0.
        self.preview = Gtk.EventBox()
        self.preview_target = None
        self.preview.set_visible_window(True)
        self.preview.get_style_context().add_class('vision-preview')
        self.preview.set_size_request(384, 216)
        self.preview.set_hexpand(True)
        self.preview.set_vexpand(True)
        self.preview.connect('size-allocate', self._fit_preview)
        results.pack_start(self.preview, True, True, 0)
        results.pack_start(self.details_expander, False, False, 0)
        self.details_expander.connect('notify::expanded', lambda *_: self._render(self.session.telemetry or {}))
        note = Gtk.Label(label='本页仅识别，不自动夹取。', xalign=0)
        note.set_line_wrap(True)
        results.pack_start(note, False, False, 0)
        self.status = Gtk.Label(label='准备就绪', xalign=0)
        self.status.set_ellipsize(3)
        self.widget.pack_start(self.status, False, False, 0)
        for control, signal in ((self.roi, 'changed'), (self.area, 'value-changed'),
                (self.saturation, 'value-changed'), (self.green_saturation, 'value-changed'),
                (self.yellow_saturation, 'value-changed'), (self.brightness, 'value-changed'), (self.confirmations, 'value-changed')):
            control.connect(signal, self._settings)
        for fields in self.band_fields.values():
            for field in fields:
                field.connect('value-changed', self._settings)
        self._load()
        self._buttons()
        if hasattr(owner, '_numeric_keyboard'):
            owner._numeric_keyboard.bind_tree(self.widget)
        self.widget.connect('destroy', lambda *_: self.close())
        self._timer = GLib.timeout_add(100, self._tick)
        self._preview_timer = GLib.timeout_add(100, self._preview_tick)

    @staticmethod
    def _style_workspace(widget):
        parent=widget.get_parent()
        if parent is not None:
            parent.get_style_context().add_class('vision-pages')

    @staticmethod
    def button(label, callback):
        button = Gtk.Button(label=label)
        button.set_size_request(-1, 50)
        button.connect('clicked', callback)
        return button

    @staticmethod
    def field(box, caption, low, high, step, value):
        box.pack_start(Gtk.Label(label=caption, xalign=0), False, False, 0)
        field = Gtk.SpinButton.new_with_range(low, high, step)
        field.set_value(value)
        field.set_width_chars(6)
        field.set_size_request(-1, 48)
        box.pack_start(field, False, False, 0)
        return field

    def _sync(self):
        self._updating = True
        p = self.parameters
        for field, value in ((self.area, p.min_area), (self.saturation, p.min_saturation),
                (self.green_saturation,p.min_saturation if p.min_green_saturation is None else p.min_green_saturation),
                (self.yellow_saturation,p.min_saturation if p.min_yellow_saturation is None else p.min_yellow_saturation),
                (self.brightness, p.min_value), (self.confirmations, p.min_confirmations)):
            field.set_value(value)
        roi = tuple(p.roi)
        if roi not in self.rois:
            self.rois.append(roi)
            self.roi.append_text('自定义（已保存）')
        self.roi.set_active(self.rois.index(roi))
        for color, (center, radius) in self.band_fields.items():
            center.set_value(self.bands[color][0])
            radius.set_value(self.bands[color][1])
        self._updating = False

    def _load(self):
        try:
            path = config_path()
            if path.is_file():
                if path.stat().st_size > 65536:
                    raise ValueError('参数文件过大')
                self.parameters, self.bands = load_profile(path)
                self.status.set_text('已载入保存的识别参数')
        except Exception as exc:
            self.status.set_text('参数文件无效，已使用默认值：' + str(exc))
        self._sync()

    def _settings(self, *_):
        if self._updating:
            return
        self.parameters = replace(self.parameters, min_area=self.area.get_value_as_int(),
            min_saturation=self.saturation.get_value_as_int(), min_value=self.brightness.get_value_as_int(),
            min_green_saturation=self.green_saturation.get_value_as_int(),min_yellow_saturation=self.yellow_saturation.get_value_as_int(),
            min_confirmations=self.confirmations.get_value_as_int(), roi=self.rois[self.roi.get_active()]).validate()
        self.bands = {color: (center.get_value(), radius.get_value()) for color, (center, radius) in self.band_fields.items()}
        self.status.set_text('参数已修改，下次开始识别时使用。')

    def _save(self, *_):
        try:
            save_profile(config_path(), self.parameters, self.bands)
            from .recorder import user_owns
            user_owns(config_path())
            self.status.set_text('识别参数已保存。')
        except Exception as exc:
            self.status.set_text('保存失败：' + str(exc))

    def _reset(self, *_):
        self.parameters, self.bands = BlockParameters(), dict(DEFAULT_BANDS)
        self._sync()
        self.status.set_text('已恢复默认参数，点击保存可覆盖原配置。')

    def _start(self, *_):
        if self._closed or self.session.running:
            return
        try:
            if self.session.start(self.parameters, self.bands):
                self._was_running = True
                self._last_valid = None
                self._last_timestamp = None
                self.preview_pixbuf = None
                self.preview_frames = self.preview_draws = 0
                self.result_title.set_text('最近识别结果')
                self.status.set_text('正在打开相机…')
        except Exception as exc:
            self.status.set_text('无法开始识别：' + str(exc))
        self._buttons()

    def stop(self, on_stopped=None):
        if self.session.running:
            self.session.set_window(visible=False)
        if on_stopped is not None:
            if not self.session.running:
                on_stopped()
                return
            if on_stopped not in self._callbacks:
                self._callbacks.append(on_stopped)
        self.session.stop()
        if not self._closed:
            self._buttons()

    def _buttons(self):
        running = self.session.running
        for widget, enabled in ((self.start_button, not running),
                                (self.stop_button, running), (self.controls, not running)):
            if widget.get_sensitive() != enabled:
                widget.set_sensitive(enabled)

    def _render(self, value):
        if value.get('fresh'):
            self._last_valid = value
        recent = self._last_valid or {}
        for color, label in self.counters.items():
            self._label(label, LABELS[color] + '  ' + str(recent.get('counts', {}).get(color, 0)))
        if self.details_expander.get_expanded():
            self._label(self.details, '   |   '.join('%s #%s   X %.0f / Y %.0f   匹配 %.0f%%' % (
                LABELS.get(t.get('color'), '?'), t.get('track_id', '-'), *t.get('center', (0, 0)),
                t.get('confidence', 0.) * 100) for t in recent.get('targets', ())[:2]) or '尚无已确认目标')
        if time.monotonic() - self._metrics_stamp >= 1 or value.get('state') != 'running':
            self._metrics_stamp = time.monotonic()
            display = value.get('preview_fps', value.get('display_unique_fps_estimate'))
            self._label(self.metrics, '识别 %.0f 帧/秒' % value.get('recognition_fps', 0.))
            if self.details_expander.get_expanded():
                self._label(self.stream_metrics, '画面 %s · 输入 %.1f 帧/秒 · 像素坐标' % (
                    '%.1f' % display if display is not None else '待测', value.get('input_fps', 0.)))

    @staticmethod
    def _label(widget, text):
        if widget.get_text() != text:
            widget.set_text(text)

    def _tick(self):
        if self.session.poll():
            self.stop_motors()
        if self._closed:
            return self.session.running
        value = self.session.telemetry
        if value and value.get('timestamp') != self._last_timestamp:
            self._last_timestamp = value.get('timestamp')
            self._render(value)
            if value.get('state') == 'running' and not value.get('error'):
                self._label(self.status, '识别中')
        if value and (value.get('state') == 'failed' or value.get('error')):
            self._label(self.status, str(value.get('error') or '识别失败'))
        if self._was_running and not self.session.running:
            self._was_running = False
            if self.session.final:
                self._render(self.session.final)
            self.status.set_text(self.session.error or '识别已停止 · 可修改参数或再次开始。')
            self.result_title.set_text('最近识别结果（已停止）')
            self._buttons()
            callbacks, self._callbacks = self._callbacks, []
            for callback in callbacks:
                callback()
            self.owner.present()
        return True

    def _preview_tick(self):
        if self._closed:
            return False
        if self.session.running:
            try:
                preview = self.preview_target if self.preview_target is not None else self.preview
                top=preview.get_toplevel()
                screen=Gdk.Screen.get_default()
                visible=(preview.get_mapped() and top.has_toplevel_focus()
                    and preview.get_allocated_width()>=384 and preview.get_allocated_height()>=216
                    and screen.get_width()==1920 and screen.get_height()==1080)
                width, height = preview.get_allocated_width(), preview.get_allocated_height()
                rect=self.preview_bounds(width,height)
                if self.preview_target is not None:
                    zoom=min(5,rect[2]//192)
                    rect=(max(0,(width-192*zoom)//2),max(0,(height-108*zoom)//2),192*zoom,108*zoom)
                x=y=0
                if visible:
                    origin=preview.get_window().get_origin()
                    x=int(origin[-2]+rect[0])
                    y=int(origin[-1]+rect[1])
                    visible=4<=x and x+rect[2]<=1920 and 0<=y and y+rect[3]<=1080
                self.preview_rect=rect
                self.window_geometry=(x,y,visible)
                self.session.set_window(x if visible else 0,y if visible else 0,visible,
                                        self.preview_rect[2],self.preview_rect[3])
            except (OSError,ValueError,AttributeError):
                self.session.stop()
        return True

    def _preview_painted(self):
        if not self._closed:
            self.preview_draws += 1

    def _fit_preview(self, widget, allocation):
        self.preview_rect=self.preview_bounds(allocation.width,allocation.height)
        # The bottom-right screen position can stay fixed while labels change
        # the drawing area's height. Publish actual screen geometry on the
        # regular tick instead of blanking PL on each layout allocation.

    @staticmethod
    def preview_bounds(width, height):
        zoom=max(2,min(8,width//192,height//108))
        w,h=192*zoom,108*zoom
        return max(0,(width-w)//2),max(0,(height-h)//2),w,h

    def close(self):
        self._closed = True
        if self.session.running:
            self.session.set_window(visible=False)
        self._callbacks = []
        self.session.stop()
