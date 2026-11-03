"""Compact zero/home dialog for the board's GTK control panel."""
from gi.repository import Gdk, GLib, Gtk
import threading

from .zero_home import RATIOS
from .protocol import HOME_MAX_SPEEDS_RPM


class ZeroHomeDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title='关节零位与回零', transient_for=parent, modal=True)
        self.parent = parent
        self.set_destroy_with_parent(True)
        self.get_style_context().add_class('zero-home-dialog')
        self.controller = parent.controller
        self.service = self.controller.zero_home
        self._values = {}
        self._config_saving = False
        self._destroyed = False
        self.node = self.controller.selected_node
        self.set_default_size(760, 530)
        box = self.get_content_area()
        box.set_border_width(16)
        box.set_spacing(10)
        self.angle = Gtk.Label(xalign=0)
        self.angle.set_line_wrap(True)
        self.angle.set_max_width_chars(70)
        box.pack_start(self.angle, False, False, 0)
        note = Gtk.Label(label='上电当前位置设为0。手动设零前，请对齐缺口并停止电机。', xalign=0)
        note.set_line_wrap(True)
        box.pack_start(note, False, False, 0)
        row = Gtk.Box(spacing=10)
        self.refresh = Gtk.Button(label='刷新角度')
        self.zero = Gtk.Button(label='当前位置设为0')
        self.home = Gtk.Button(label='当前关节回0')
        for button, op in ((self.refresh, 'refresh'), (self.zero, 'zero'), (self.home, 'home')):
            button.connect('clicked', self._start, op)
            row.pack_start(button, True, True, 0)
        box.pack_start(row, False, False, 0)
        self.safe = Gtk.CheckButton(label='我已确认缺口或回零路径、负载支撑和运动区域')
        self.safe.set_active(not parent.live_control)
        box.pack_start(self.safe, False, False, 0)
        config = Gtk.Grid(column_spacing=12, row_spacing=10)
        config.attach(Gtk.Label(label='回零基础转速（RPM）', xalign=0), 0, 0, 1, 1)
        self.speed = Gtk.SpinButton.new_with_range(1, HOME_MAX_SPEEDS_RPM[self.node], 1)
        self.speed.set_value(self.service.speeds[self.node])
        speed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        speed_box.pack_start(self.speed, False, False, 0)
        self.joint_speed = Gtk.Label(xalign=0)
        speed_box.pack_start(self.joint_speed, False, False, 0)
        config.attach(speed_box, 1, 0, 1, 1)
        config.attach(Gtk.Label(label='并行回零顺序（逗号分隔）', xalign=0), 0, 1, 1, 1)
        self.order = Gtk.Entry()
        self.order.set_placeholder_text('并行运动，按此顺序下发命令')
        self.order.set_text(','.join(map(str, self.service.order)))
        config.attach(self.order, 1, 1, 1, 1)
        self.verified = Gtk.CheckButton(label='我已确认各关节同时回0的路径，允许关机时并行回0')
        config.attach(self.verified, 0, 2, 2, 1)
        self.save = Gtk.Button(label='保存回零配置')
        self.save.connect('clicked', self._save)
        config.attach(self.save, 0, 3, 1, 1)
        self.ratio_speed = Gtk.Button(label='按减速比提速约20°/秒')
        self.ratio_speed.connect('clicked', self._apply_ratio_speed)
        config.attach(self.ratio_speed, 1, 3, 1, 1)
        details = Gtk.Expander(label='回零参数与反馈详情')
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.angle_details = Gtk.Label(xalign=0)
        self.angle_details.set_line_wrap(True)
        detail_box.pack_start(self.angle_details, False, False, 0)
        detail_box.pack_start(config, False, False, 0)
        timing_note = Gtk.Label(label='角度由电机反馈换算。回零按距离调整转速，到位后结束。', xalign=0)
        timing_note.set_line_wrap(True)
        detail_box.pack_start(timing_note, False, False, 0)
        details.add(detail_box)
        box.pack_start(details, False, False, 0)
        self.status = Gtk.Label(xalign=0)
        self.status.set_line_wrap(True)
        self.status.set_max_width_chars(70)
        self.status.set_ellipsize(3)
        self.status.set_lines(2)
        from .gtk_touch import reserve_label
        reserve_label(self.status,1,2);reserve_label(self.angle,1,1);reserve_label(self.joint_speed,1,1)
        box.pack_start(self.status, False, False, 0)
        self.stop = Gtk.Button(label='■ 停止 / 取消回零')
        self.stop.get_style_context().add_class('stop')
        self.stop.connect('clicked', lambda *_: self.controller.stop())
        box.pack_start(self.stop, False, False, 0)
        self.add_button('返回控制页', Gtk.ResponseType.CLOSE)
        self.connect('response', self._close)
        self.connect('delete-event', self._close_event)
        self.connect('focus-out-event', self._focus_out)
        self.connect('key-press-event', self._key)
        self._timer = GLib.timeout_add(200, self._refresh)
        self.connect('destroy', self._destroy)
        box.show_all()
        self._refresh()
        self.order._f3p_local_text = True
        from .gtk_touch import touch_window_header
        from .gtk_keyboard import NumericKeyboard
        touch_window_header(self)
        NumericKeyboard(self,desktop_osk=parent.live_control,track_dialogs=False)

    def _destroy(self, *_):
        self._destroyed = True
        GLib.source_remove(self._timer)
        self._values.clear()
        self.parent.zero_dialog = None

    def prepare_for_show(self):
        # A reused dialog must not carry a previous joint or confirmation.
        self.node=self.controller.selected_node
        self.speed.set_range(1,HOME_MAX_SPEEDS_RPM[self.node])
        self.speed.set_value(self.service.speeds[self.node])
        self.order.set_text(','.join(map(str,self.service.order)))
        self.safe.set_active(not self.parent.live_control)
        self.verified.set_active(False)
        self._values.clear();self._refresh()

    def _update(self, widget, method, value):
        key = (widget, method)
        if key not in self._values or self._values[key] != value:
            getattr(widget, method)(value)
            self._values[key] = value

    def _refresh(self):
        if self._destroyed:
            return False
        if not self.get_visible() and self._values:
            return True
        s = self.controller.nodes[self.node]
        value = '角度待读取' if s.motor_angle is None else f'{s.motor_angle / RATIOS[self.node]:.2f}°'
        self._update(self.angle, 'set_text', f'J{self.node} · {value} · 零位' + ('已确认' if s.zero_valid else '未确认'))
        motor = '未读取' if s.motor_angle is None else f'{s.motor_angle:.3f}°'
        self._update(self.angle_details, 'set_text', f'电机轴 {motor} · 减速比 {RATIOS[self.node]:.6g}∶1 · 固件 {s.firmware}')
        self._update(self.status, 'set_text', '正在保存配置…' if self._config_saving else self.service.message)
        self._update(self.status, 'set_tooltip_text', self.service.message)
        free = not self._config_saving and not self.service.busy and self.controller._pending is None and self.controller.active_node is None
        for widget in (self.refresh, self.zero, self.save, self.ratio_speed, self.speed, self.order):
            self._update(widget, 'set_sensitive', free)
        self._update(self.home, 'set_sensitive', free and s.zero_valid)
        self._update(self.stop, 'set_sensitive', not self._config_saving)
        self._update(self.joint_speed, 'set_text', f'约 {self.speed.get_value() * 6 / RATIOS[self.node]:.2f}°/秒')
        return True

    def _start(self, _button, operation):
        if operation in ('zero', 'home') and not self.safe.get_active():
            self.service.message = '请先确认缺口、负载和回零路径'
            self._update(self.status, 'set_text', self.service.message)
            return
        if operation == 'home':
            self.service.speeds[self.node] = self.speed.get_value_as_int()
        if operation == 'zero':
            dialog = Gtk.MessageDialog(transient_for=self, modal=True,
                buttons=Gtk.ButtonsType.OK_CANCEL, message_type=Gtk.MessageType.QUESTION,
                text=f'确认将关节 {self.node} 当前缺口对齐位置设为0°？')
            response = dialog.run()
            dialog.destroy()
            if response != Gtk.ResponseType.OK:
                return
        try:
            self.service.start(operation, self.node, lambda ok, error: GLib.idle_add(self._finished, ok, error))
        except Exception as exc:
            self.service.message = str(exc)
            self._update(self.status, 'set_text', self.service.message)

    def _finished(self, ok, error):
        if self._destroyed:
            return False
        self._update(self.status, 'set_text', self.service.message if ok else error)
        return False

    def _save_in_background(self, work, update_speed=False):
        if self._config_saving:
            return
        if self.service.busy or self.controller._pending or self.controller.active_node is not None:
            self.service.message = '请先完成当前操作并停止电机'
            self._refresh()
            return
        self._config_saving = True
        self._refresh()
        def run():
            error = ''
            try:
                work()
            except Exception as exc:
                error = str(exc)
            GLib.idle_add(self._config_saved, error, update_speed)
        threading.Thread(target=run, daemon=True, name='f3p-zero-config').start()

    def _config_saved(self, error, update_speed):
        self._config_saving = False
        if self._destroyed:
            return False
        if error:
            self.service.message = error
        elif update_speed:
            self.speed.set_value(self.service.speeds[self.node])
        self._refresh()
        return False

    def _apply_ratio_speed(self, *_):
        self._save_in_background(self.service.apply_ratio_speeds, update_speed=True)

    def _save(self, *_):
        try:
            if not self.verified.get_active():
                raise ValueError('请先确认并行回0路径并勾选确认')
            order = [int(n.strip()) for n in self.order.get_text().replace('，', ',').split(',')]
            speed = self.speed.get_value_as_int()
            self._save_in_background(lambda: self.service.configure(order, self.node, speed))
        except Exception as exc:
            self.service.message = str(exc)
            self._update(self.status, 'set_text', self.service.message)

    def _close(self, *_):
        if self._config_saving:
            self._update(self.status, 'set_text', '正在保存，请稍后返回')
            return
        if self.service.busy:
            self.controller.stop()
            self.status.set_text('正在取消，请等待停止确认后返回')
            return
        self.hide()

    def _close_event(self, *_):
        self._close()
        return True

    def _focus_out(self, *_):
        if self.service.busy and self.controller.active_node is not None:
            self.controller.stop()
        return False

    def _key(self, _widget, event):
        if event.keyval in (Gdk.KEY_space, Gdk.KEY_Escape):
            if self._config_saving:
                return True
            self.controller.stop()
            return True
        return False
