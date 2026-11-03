#!/usr/bin/env python3
"""GTK3 entry point for the factory ARM64 Ubuntu image."""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Callable

# The board GUI runs as root for MMIO. Use the desktop's XIM bridge so
# Chinese input does not require access to another user's private IBus bus.
if hasattr(os, "geteuid") and os.geteuid() == 0 and os.environ.get("XMODIFIERS") == "@im=ibus":
    os.environ["GTK_IM_MODULE"] = "xim"

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from robot_arm_gui.backend import MemoryMappedBackend, SimulatedBackend, SocketCanBackend
    from robot_arm_gui.controller import MotorController
    from robot_arm_gui.protocol import (
        DEFAULT_ACCELERATION,
        MAX_ACCELERATION,
        MAX_SPEED_RPM,
        MIN_ACCELERATION,
        MIN_SPEED_RPM,
    )
else:
    from .backend import MemoryMappedBackend, SimulatedBackend, SocketCanBackend
    from .controller import MotorController
    from .protocol import (
        DEFAULT_ACCELERATION,
        MAX_ACCELERATION,
        MAX_SPEED_RPM,
        MIN_ACCELERATION,
        MIN_SPEED_RPM,
    )

from robot_arm_gui.ui_updates import SnapshotMailbox

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


CSS = b"""
window { background: #f3f5f8; color: #52647e; font-family: sans-serif; font-size: 16px; }
.title { font-size: 25px; font-weight: 500; color: #22354f; }
.subtitle, .section { color: #7a8da8; }
.section { font-weight: 500; color: #5278b4; }
.card { background: #ffffff; border: 1px solid #e3e9f2; border-radius: 12px; padding: 4px 8px; }
button { min-height: 46px; min-width: 46px; padding: 5px 10px; border: 1px solid #dfe6f0;
 border-radius: 9px; background: #ffffff; color: #52647e; font-size: 17px; font-weight: 500; }
button:hover { background: #f0f4fa; border-color: #b6caea; }
button:active, button.active, .operation-tabs .active { background: #edf3ff; border-color: #a7c0e9; color: #315f9f; }
button:disabled { color: #9ba8ba; background: #f0f3f7; border-color: #e6ebf2; }
button:focus { border-color: #608bd0; }
button, button:hover, button:active, button:disabled, button:focus {
 background-image: none; box-shadow: none; text-shadow: none; outline-style: none; transition: none;
}
button label { text-shadow: none; }
.motor-select { min-height: 50px; font-size: 14px; padding: 4px 6px; }
.selected { background: #edf3ff; border-color: #a7c0e9; }
.record-action { min-height: 46px; font-size: 16px; padding: 5px 10px; }
.enable { background: #edf5f0; border-color: #9dbfab; }
.disable { background: #f9f0f0; border-color: #dcb6b6; }
.motion { min-height: 62px; font-size: 24px; }
.stop { min-height: 50px; background: #fff0f0; border: 2px solid #e8b3b3; font-size: 23px; }
.stop:hover, .vision-stop:hover { background: #fde3e3; }
.stop:disabled { background: #f5eded; color: #b7a3a3; }
.speed { color: #4475b9; font-size: 30px; font-weight: 600; }
.good { color: #4c8766; }
.bad { color: #b35c5c; font-weight: 500; }
entry, spinbutton, spinbutton entry { background: #fafbfd; color: #344e72; border-color: #dfe6f0; min-height: 52px; font-size: 17px; }
spinbutton button { min-width: 56px; min-height: 52px; padding: 0 2px; border-radius: 5px; }
checkbutton, radiobutton { min-height: 50px; padding: 2px 4px; }
checkbutton check, radiobutton radio { min-width: 28px; min-height: 28px; background: #ffffff; border: 1px solid #bac9dc; }
checkbutton check:checked { background: #4779c7; border-color: #4779c7; color: white; }
scale { padding: 4px; }
scale trough { background: #e4eaf2; min-height: 10px; border-radius: 5px; }
scale highlight { background: #789bd3; }
scale slider { background: #ffffff; min-width: 46px; min-height: 46px; }
scrollbar { background: #fafbfd; }
scrollbar slider { background: #b7c5d9; min-width: 26px; min-height: 54px; border-radius: 8px; }
expander title { min-height: 48px; color: #6d85a6; padding: 2px; }
menu, menuitem, popover { background-color: #315f9f; color: #52647e; }
menuitem { min-height: 50px; padding: 4px 12px; }
menuitem:hover { background-color: #f0f4fa; }
.diagnostic-values { font-size: 13px; }
.diagnostic-values label { font-size: 13px; }
.joint-panel, .drawing-settings { font-size: 15px; }
.joint-panel button, .operation-tabs button, .drawing-settings button { min-height: 46px; font-size: 16px; padding: 5px 8px; }
.joint-panel button.cart-jog { min-width: 66px; min-height: 52px; padding: 5px 8px; font-size: 27px; border-color: #d6e0ee; }
.operation-tabs button { min-height: 42px; }
.joint-panel spinbutton button { min-width: 56px; padding: 0 2px; }
.joint-panel spinbutton.slice-cut button { min-width: 56px; }
.joint-panel .combined-side button { min-height: 42px; }
.vision-window { font-size: 16px; }
.vision-window .vision-stop { background: #fff0f0; border-color: #e8b3b3; }
.zero-home-dialog, .zero-home-dialog box, .position-config-dialog, .position-config-dialog box { background: #f3f5f8; }
.zero-home-dialog label, .position-config-dialog label { color: #52647e; }
.numeric-keyboard, .numeric-keyboard box { background: #f3f5f8; color: #52647e; }
.numeric-keyboard button { min-height: 58px; font-size: 22px; }
.numeric-keyboard entry { font-size: 26px; min-height: 54px; }
.numeric-keyboard .suggested-action { background: #edf3ff; border-color: #a7c0e9; }
.text-keyboard button { min-width: 48px; min-height: 48px; padding: 4px; font-size: 20px; }
.text-keyboard entry { min-height: 54px; font-size: 24px; }
headerbar button { min-width: 100px; min-height: 48px; }
textview, textview text { background: #fafbfd; color: #52647e; caret-color: #5278b4; }
list row { min-height: 50px; padding: 2px 6px; }
treeview.view { font-size: 17px; background: #fafbfd; color: #52647e; }
treeview.view:selected, list row:selected { background: #edf3ff; color: #315f9f; }
list { background: #ffffff; color: #52647e; }
headerbar { background: #ffffff; color: #52647e; border-color: #e3e9f2; }
scrollbar.horizontal slider { min-height: 26px; min-width: 54px; }
.dialog-action-area button { min-width: 120px; }
button:active, button.touch-pressed { background: #e0eafe; border-color: #8baadc; color: #315f9f; box-shadow: none; }
button.stop:active, button.stop.touch-pressed, button.vision-stop:active, button.vision-stop.touch-pressed { background: #f9dada; border-color: #cf9292; box-shadow: none; }
button:disabled { color: #7d8e9e; opacity: 0.62; box-shadow: none; }
button:checked { background: #edf3ff; border-color: #a7c0e9; color: #315f9f; }
checkbutton.touch-pressed { background: #dce8fa; border-radius: 6px; }
.simulation-badge { color: #ffdc8a; background: #40321e; border: 1px solid #987a42; border-radius: 6px; padding: 2px 6px; font-size: 15px; font-weight: 500; }

button.stop, button.vision-stop { color: #b54f54; background: #fff2f2; border-color: #e8bcbc; }
button.active, .operation-tabs .active { color: #3264ad; }
button.enable { color: #48755d; }
button.disable { color: #a06165; }
.numeric-keyboard .suggested-action, button.suggested-action { background: #416fc1; color: #ffffff; border-color: #416fc1; }
.selection, selection { background: #dce8fa; color: #2b466f; }
"""


def touch_css(screen_height=800):
    """Keep finger targets legible when the HDMI framebuffer is scaled."""
    import re
    scale = max(1.0, min(1.75, float(screen_height) / 800.0))
    if scale == 1.0:
        return CSS
    return re.sub(rb"([0-9]+)px", lambda m: str(round(int(m.group(1)) * scale)).encode() + b"px", CSS)


def _label(text: str, style: str | None = None) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0)
    if style:
        label.get_style_context().add_class(style)
    return label


def _entry_label(text):
    from robot_arm_gui.gtk_touch import StatusEntry
    return StatusEntry(label=text)

class ControlWindow(Gtk.Window):
    def __init__(self, controller: MotorController, live_control: bool, initialize_zero: bool = True) -> None:
        super().__init__(title="F3P 机械臂控制台")
        self.controller = controller
        self.live_control = live_control
        self.set_default_size(1280, 800)
        self.set_size_request(1100, 650)
        self.connect("destroy", self._destroy)
        self.connect("key-press-event", self._key_press)
        self.values: dict[str, Gtk.Label] = {}
        self.vision_window = None
        self.cloud_windows = {}
        self.record_dialog = None
        self.export_dialog = None
        self._export_notice = None
        self._display_mailbox = SnapshotMailbox()
        self._widget_values = {}
        self._selected_style_node = None
        self._syncing = False
        self._held = None
        self._held_node = None
        from robot_arm_gui.gtk_touch import TouchInput
        self._touch_input = TouchInput(self)
        self._powering_off = False
        self._recovering_state = False
        self._initializing_zero = initialize_zero
        self._zero_recovery_cursor = 0
        self._zero_recovery_retry_at = {}
        from robot_arm_gui.zero_home import ZeroHome
        ZeroHome(self.controller)
        from robot_arm_gui.joint_motion import JointMotion
        JointMotion(self.controller)
        self.zero_dialog = None
        self._hold_timer = GLib.timeout_add(50, self._check_hold)
        self.connect("focus-out-event", self._focus_out)
        self.add_events(Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.connect("button-release-event", self._window_mouse_release)
        self._build_ui()
        from robot_arm_gui.gtk_joint_motion import JointPages
        self.joint_pages = JointPages(self)
        from robot_arm_gui.gtk_touch import reserve_control_status
        reserve_control_status(self)
        self.utility_popover.get_child().show_all()
        from robot_arm_gui.gtk_keyboard import NumericKeyboard
        self._numeric_keyboard = NumericKeyboard(self, desktop_osk=live_control)
        from robot_arm_gui.gtk_layout import apply_layout
        apply_layout(self)
        self._display_timer = GLib.timeout_add(200, self._flush_snapshot)
        self.controller.on_snapshot = self._queue_snapshot
        # Create hidden vision pages on first use, not during startup.
        try:
            self.controller.connect()
            if initialize_zero:
                GLib.timeout_add(50, self._initialize_zero)
                GLib.timeout_add(200, self._retry_initial_zero)
            else:
                self._initializing_zero=True
                GLib.timeout_add(50,self._restore_existing_zero)
                GLib.timeout_add(500,self._retry_saved_zero)
        except Exception as exc:
            self._show_error(str(exc))

    def _build_ui(self) -> None:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_border_width(8)
        outer.set_spacing(6)
        self.workspace = Gtk.Stack()
        self.workspace.set_transition_type(Gtk.StackTransitionType.NONE)
        self.workspace.set_homogeneous(False)
        self.workspace.add_named(outer, "control")
        self.add(self.workspace)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._simulation_mode=isinstance(self.controller.backend,SimulatedBackend)
        heading=_label("F3P 控制台 · 仿真" if self._simulation_mode else "F3P 控制台", "title")
        titles.pack_start(heading, False, False, 0)
        titles.set_size_request(210, -1)
        self.mode_badge=_label("仿真 · 不驱动电机" if self._simulation_mode else "空格停止", "simulation-badge" if self._simulation_mode else "subtitle")
        self.mode_badge.set_tooltip_text("X42S · 500 kbit/s · 空格停止")
        titles.pack_start(self.mode_badge,False,False,0)
        header.pack_start(titles, False, False, 0)
        self.vision_button = Gtk.Button(label="图像处理")
        self.vision_button.connect("clicked", self._open_vision)
        header.pack_start(self.vision_button, False, False, 0)
        self.car_window = None
        self.car_button = Gtk.Button(label='小车 / 夹爪')
        self.car_button.connect('clicked', self._open_car)
        header.pack_start(self.car_button, False, False, 0)
        self.zero_button = Gtk.Button(label='零点设置')
        self.zero_button.connect('clicked', self._open_zero_home)
        header.pack_start(self.zero_button, False, False, 0)
        cloud_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.pack_start(cloud_actions, False, False, 0)
        for mode, label in [('wifi', '热点连接'), ('voice', '本地语音'), ('chat', '云端 AI')]:
            button = Gtk.Button(label=label)
            button.get_style_context().add_class('record-action')
            button.connect('clicked', lambda _button, page=mode: self._open_cloud(page))
            cloud_actions.pack_start(button, False, False, 0)
        self.shutdown_button = Gtk.Button(label='关机')
        self.shutdown_button.connect('clicked', self._confirm_shutdown)
        header.pack_end(self.shutdown_button, False, False, 0)
        self.connection = _entry_label("正在连接…")
        self.connection.set_xalign(1)
        header.pack_end(self.connection, True, True, 0)
        outer.pack_start(header, False, False, 0)
        motor_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        motor_cards = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        motor_cards.set_homogeneous(True)
        motor_row.pack_start(motor_cards, True, True, 0)
        self.motor_cards=motor_cards
        self.motor_buttons = {}
        for node in range(1, 7):
            from robot_arm_gui.gtk_touch import StatusButton
            button = StatusButton(label=f"电机 {node}\n未探测 · 未使能")
            button.get_style_context().add_class("motor-select")
            button.set_size_request(-1, 56)
            button.connect("clicked", lambda _button, n=node: self._command(lambda: self.controller.select_motor(n)))
            self.motor_buttons[node] = button
            motor_cards.pack_start(button, True, True, 0)
        all_stop = Gtk.Button(label="全部停止")
        all_stop.get_style_context().add_class("stop")
        all_stop.connect("clicked", lambda _button: self._command(self._stop_all))
        motor_row.pack_start(all_stop, False, False, 0)
        self.home_all_button = Gtk.Button(label='一键回0')
        self.home_all_button.get_style_context().add_class('enable')
        self.home_all_button.connect('clicked', self._home_all)
        motor_row.pack_start(self.home_all_button, False, False, 0)
        self.recover_state_button=Gtk.Button(label='恢复状态')
        self.recover_state_button.set_tooltip_text('检查 J1～J6 原零点、位置和保护状态，清理已结束任务的界面锁；不清零、不使能')
        self.recover_state_button.connect('clicked',self._recover_state)
        motor_row.pack_start(self.recover_state_button,False,False,0)
        outer.pack_start(motor_row, False, False, 0)
        self.recovery_notice=Gtk.Expander(label='六轴恢复结果')
        self.recovery_text=_label('')
        self.recovery_text.set_line_wrap(True)
        self.recovery_notice.add(self.recovery_text)
        self.recovery_notice.set_no_show_all(True)
        outer.pack_start(self.recovery_notice,False,False,0)
        recording_row = Gtk.Box(spacing=8)
        self.record_status = _label("未开始记录 · 电机 1–6", "subtitle")
        recording_row.pack_start(self.record_status, True, True, 0)
        self.record_start = Gtk.Button(label="开始日志")
        self.record_end = Gtk.Button(label="结束并导出")
        self.record_view = Gtk.Button(label="查看日志")
        for button, handler in ((self.record_start,self._record_start),(self.record_end,self._record_export),
                                (self.record_view,self._record_view)):
            button.get_style_context().add_class('record-action')
            button.connect('clicked',handler)
            recording_row.pack_start(button,False,False,0)
        utilities = Gtk.MenuButton(label="日志 / 姿态")
        utility_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        utility_box.set_border_width(12)
        utility_popover = Gtk.Popover.new(utilities)
        utility_popover.add(utility_box)
        utilities.set_popover(utility_popover)
        header.pack_start(utilities, False, False, 0)
        self.utility_button, self.utility_popover = utilities, utility_popover
        utility_box.pack_start(recording_row,False,False,0)
        self.recording_row=recording_row
        self.pose_toolbar = Gtk.Box(spacing=8)
        utility_box.pack_start(self.pose_toolbar, False, False, 0)
        utility_box.show_all()
        self._record_timer = GLib.timeout_add(1000,self._refresh_recording)
        self._refresh_recording()
        self.all_stop_label = _label("待机", "subtitle")
        self.all_stop_label.set_max_width_chars(105)
        self.all_stop_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        outer.pack_start(self.all_stop_label, False, False, 0)

        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        control = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left.get_style_context().add_class('card')
        self.operation_tabs = Gtk.Box(spacing=8)
        self.operation_tabs.set_homogeneous(True)
        self.operation_tabs.get_style_context().add_class('operation-tabs')
        left.pack_start(self.operation_tabs, False, False, 0)
        self.operation_stack = Gtk.Stack()
        self.operation_stack.set_homogeneous(False)
        self.operation_stack.set_transition_type(Gtk.StackTransitionType.NONE)
        control_scroll = Gtk.ScrolledWindow()
        control_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        control_scroll.set_overlay_scrolling(False)
        control_scroll.set_kinetic_scrolling(False)
        control_scroll.add(control)
        self.operation_stack.add_named(control_scroll, 'control')
        left.pack_start(self.operation_stack, True, True, 0)
        diagnostics = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        diagnostics.get_style_context().add_class("card")
        columns.pack_start(left, True, True, 0)
        diagnostic_scroll = Gtk.ScrolledWindow()
        diagnostic_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        diagnostic_scroll.set_overlay_scrolling(False)
        diagnostic_scroll.set_size_request(210, -1)
        diagnostic_scroll.add(diagnostics)
        columns.pack_start(diagnostic_scroll, False, False, 0)
        diagnostics.set_size_request(210, -1)
        self.diagnostics = diagnostics
        outer.pack_start(columns, True, True, 0)

        self.control_title = _label("电机 1 · 运动控制", "section")
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_row.pack_start(self.control_title, False, False, 0)
        self.limit_label = _label('软件限位未启用', 'subtitle')
        self.limit_label.set_width_chars(24)
        self.limit_label.set_max_width_chars(28)
        self.limit_label.set_ellipsize(3)
        title_row.pack_start(self.limit_label, True, True, 0)
        control.pack_start(title_row, False, False, 0)
        state_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        state_row.pack_start(_label("当前状态"), False, False, 0)
        self.state = _entry_label("空闲")
        self.state.set_xalign(1)
        state_row.pack_end(self.state, True, True, 0)
        control.pack_start(state_row, False, False, 0)

        enable_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.enable = enable = Gtk.Button(label="使能")
        self.disable = disable = Gtk.Button(label="失能")
        enable.get_style_context().add_class("enable")
        disable.get_style_context().add_class("disable")
        enable.connect("clicked", lambda _button: self._command(self.controller.enable))
        disable.connect("clicked", lambda _button: self._command(self.controller.disable))
        enable_row.pack_start(enable, True, True, 0)
        enable_row.pack_start(disable, True, True, 0)
        control.pack_start(enable_row, False, False, 0)
        self.unlock_button = Gtk.Button(label="手动解除 F3 锁定")
        self.unlock_button.connect("clicked", self._unlock_f3)
        self.unlock_button.set_label('解除 F3 锁定')
        self.unlock_button.get_style_context().add_class('record-action')
        enable_row.pack_start(self.unlock_button, False, False, 0)

        speed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        speed_row.pack_start(_label('目标转速', 'section'), False, False, 0)
        self.speed_text = _label("30", "speed")
        speed_row.pack_start(self.speed_text, False, False, 0)
        speed_row.pack_start(_label("RPM"), False, False, 0)
        self.speed_adjustment = adjustment = Gtk.Adjustment(
            30, MIN_SPEED_RPM, MAX_SPEED_RPM, 1, 100, 0
        )
        self.speed_spin = spin = Gtk.SpinButton(adjustment=adjustment, climb_rate=1, digits=0)
        spin.set_numeric(True)
        speed_row.pack_end(spin, False, False, 0)
        control.pack_start(speed_row, False, False, 0)
        self.speed_scale = scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        scale.set_draw_value(False)
        adjustment.connect("value-changed", self._speed_changed)
        control.pack_start(scale, False, False, 0)

        acceleration_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        acceleration_row.pack_start(_label("加速度档位", "section"), False, False, 0)
        acceleration_row.pack_start(_label("0 = 直接启动", "subtitle"), False, False, 0)
        self.acceleration_adjustment = acceleration = Gtk.Adjustment(
            DEFAULT_ACCELERATION,
            MIN_ACCELERATION,
            MAX_ACCELERATION,
            1,
            10,
            0,
        )
        self.acceleration_spin = acceleration_spin = Gtk.SpinButton(
            adjustment=acceleration, climb_rate=1, digits=0
        )
        acceleration_spin.set_numeric(True)
        acceleration_row.pack_end(acceleration_spin, False, False, 0)
        acceleration.connect("value-changed", self._acceleration_changed)
        control.pack_start(acceleration_row, False, False, 0)

        self.safety = Gtk.CheckButton(label="已确认急停、支撑及运动区域安全")
        self.safety.set_active(not self.live_control)
        self.safety.set_sensitive(self.live_control)
        self.safety.connect("toggled", lambda _check: self._update_motion_enabled())
        control.pack_start(self.safety, False, False, 0)

        motion_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.reverse = Gtk.Button(label="◀  按住反向")
        self.forward = Gtk.Button(label="按住正向  ▶")
        for button in (self.reverse, self.forward):
            button.get_style_context().add_class("motion")
        for button, command in ((self.reverse,self.controller.move_reverse),(self.forward,self.controller.move_forward)):
            button.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK)
            button.connect('button-press-event',self._motion_mouse_press,command)
            button.connect('button-release-event',self._motion_mouse_release)
            self._touch_input.bind(button,lambda b,e,command=command:self._motion_touch_press(b,e,command),
                lambda *_:self._released())
            button.connect('grab-broken-event',self._hold_cancelled)
            button.connect('unmap',self._hold_unmapped)
        motion_row.pack_start(self.reverse, True, True, 0)
        motion_row.pack_start(self.forward, True, True, 0)
        control.pack_start(motion_row, True, True, 0)

        self.stop_button = stop = Gtk.Button(label="■  停止")
        stop.get_style_context().add_class("stop")
        stop.connect("clicked", lambda _button: self._stop())
        control.pack_start(stop, False, False, 0)
        self._update_motion_enabled()

        diagnostics.pack_start(_label("状态", "section"), False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=5)
        grid.get_style_context().add_class('diagnostic-values')
        details = Gtk.Grid(column_spacing=10, row_spacing=5)
        details.get_style_context().add_class('diagnostic-values')
        self.communication_details = Gtk.Expander(label='通信详情')
        self.communication_details.add(details)
        fields = [
            ("motor", "电机"),
            ("direction", "方向"),
            ("last_command", "最后命令"),
            ("tx_count", "发送帧"),
            ("rx_count", "接收帧"),
            ("rx_id", "RX ID"),
            ("rx_dlc", "DLC"),
            ("rx_data", "DATA"),
            ("f3_reply", "F3RX"),
            ("f6_reply", "F6RX"),
            ("error", "错误"),
        ]
        for row, (key, caption) in enumerate(fields):
            target = grid if key in ('motor', 'direction', 'error') else details
            target.attach(_label(caption, "subtitle"), 0, row, 1, 1)
            value = _entry_label("-")
            self.values[key] = value
            target.attach(value, 1, row, 1, 1)
        diagnostics.pack_start(grid, False, False, 0)
        diagnostics.pack_start(self.communication_details, False, False, 0)

        warning = _label("软件停止不能替代硬件急停", "subtitle")
        warning.set_tooltip_text("软件停止依赖通信链路，不能替代断电急停、硬件失能、限位和过流保护。")
        warning.set_xalign(0.5)
        outer.pack_end(warning, False, False, 0)

    def _open_cloud(self, mode):
        if self._powering_off:
            return
        from robot_arm_gui.gtk_cloud_ai import ChatWindow, HotspotWindow
        if mode not in self.cloud_windows:
            if mode == 'voice':
                from robot_arm_gui.gtk_local_voice import LocalVoiceWindow
                self.cloud_windows[mode] = LocalVoiceWindow(self)
            else:
                self.cloud_windows[mode] = HotspotWindow(self) if mode == 'wifi' else ChatWindow(self)
        window = self.cloud_windows[mode]
        window.show_all()
        window.present()

    def _open_vision(self, *_args) -> None:
        if self._initializing_zero or self._powering_off or self.controller.zero_home.busy or self.controller.motion_task.busy:
            return
        if self.controller.active_node is None:
            self._show_vision()
            return
        self._command(lambda: self.controller.stop(
            lambda ok: GLib.idle_add(self._show_vision) if ok else None))

    def _open_zero_home(self, *_args):
        if self._powering_off or self._initializing_zero or self.controller.zero_home.busy or self.controller.motion_task.busy:
            return
        if self.controller.active_node is not None or self.controller._pending:
            self._show_error('请先停止电机并等待当前命令完成'); return
        if self.zero_dialog is None:
            from robot_arm_gui.gtk_zero_home import ZeroHomeDialog
            self.zero_dialog = ZeroHomeDialog(self)
        self.zero_dialog.prepare_for_show()
        self.zero_dialog.show(); self.zero_dialog.present()

    def _initialize_zero(self):
        if self._display_mailbox.closed or not self._initializing_zero:
            return False
        c = self.controller
        if c._pending or c._all_stopping or c._switching:
            return True
        try:
            c.zero_home.start('initialize', 1,
                lambda ok, error: GLib.idle_add(self._zero_initialized, ok, error))
        except Exception as exc:
            self._zero_initialized(False, str(exc))
        return False

    def _restore_existing_zero(self):
        if self._display_mailbox.closed:return False
        c=self.controller
        if c._pending or c._switching or c._all_stopping:return True
        try:
            c.zero_home.start('restore_session',1,
                lambda ok,error:GLib.idle_add(self._session_restored,ok,error))
        except Exception as exc:self._zero_initialized(False,str(exc))
        return False

    def _session_restored(self,ok,error):
        self._zero_initialized(ok,error)
        if not ok:return False
        print('ZERO_SESSION_RESTORED',self.controller.zero_home.message,flush=True)
        # An installer may supply a single-use receipt after the operator confirms
        # that this exact six-axis zero session is the locked CAD zero posture.
        from pathlib import Path
        import json,stat
        path=Path('/run/f3p-control-reference-confirmation.json')
        try:
            metadata=path.stat()
            if metadata.st_uid!=0 or stat.S_IMODE(metadata.st_mode)!=0o600:raise ValueError('参考确认文件权限无效')
            if metadata.st_size>10000:raise ValueError('参考确认文件无效')
            value=json.loads(path.read_text());path.unlink()
            reference=self.controller.motion_task._reference(range(1,7))
            if value!=dict(boot_id=reference['boot_id'],reference_ids=reference['reference_ids'],operator_confirmed=True):
                raise ValueError('本次参考确认与当前零点不匹配')
            self.controller.motion_task.start('cart_confirm_fixed_reference',
                lambda success,why:GLib.idle_add(self._reference_restored,success,why),confirmed=True)
        except FileNotFoundError:pass
        except Exception as exc:self.controller.zero_home.message=str(exc)
        return False

    def _reference_restored(self,ok,error):
        print('FIXED_REFERENCE_RESTORED',dict(ok=ok,error=error),flush=True)
        if not ok:self.controller.zero_home.message=error
        self.controller._publish()
        GLib.timeout_add(250,self._reference_diagnostic)
        return False

    def _zero_initialized(self, ok, error):
        self._initializing_zero = False
        if not ok:
            self.controller.zero_home.message = error
        self.controller._publish()
        GLib.timeout_add(250,self._reference_diagnostic)
        return False

    def _reference_diagnostic(self):
        if self._display_mailbox.closed:return False
        import json
        self._flush_snapshot()
        c=self.controller
        print('CONTROL_REFERENCE_STATE',json.dumps(dict(boot_id=c.zero_home.boot_id,
            calibration_ready=c.motion_task.cartesian.ready(),home_button_enabled=self.home_all_button.get_sensitive(),
            zero_error=c.zero_home.error,model_error=c.motion_task.cartesian.readiness_notice(),
            nodes={str(n):dict(online=s.online,zero_valid=s.zero_valid,motor_angle=s.motor_angle,enabled=s.enabled,error=s.error) for n,s in c.nodes.items()}),ensure_ascii=False),flush=True)
        return False

    def _retry_initial_zero(self):
        if self._display_mailbox.closed:
            return False
        c = self.controller
        if self.zero_dialog is not None and self.zero_dialog.get_visible():
            return True
        if (self._initializing_zero or self._powering_off or c.zero_home.busy or c.motion_task.busy
                or c._pending or c._switching or c._all_stopping
                or c.active_node is not None or any(s.moving for s in c.nodes.values())):
            return True
        now = time.monotonic()
        nodes = [n for n, s in c.nodes.items()
                 if (not s.zero_valid or n in c.zero_check_pending)
                 and now >= self._zero_recovery_retry_at.get(n, 0)]
        invalid = [n for n in nodes if c.nodes[n].online == '在线' and not c.nodes[n].zero_valid]
        if nodes:
            node = invalid[0] if invalid else nodes[self._zero_recovery_cursor % len(nodes)]
            self._zero_recovery_cursor += 1
            try:
                if c.nodes[node].online == '在线' and not c.nodes[node].zero_valid:
                    c.zero_home.start('recover_zero', node,
                        lambda ok, error, n=node: GLib.idle_add(self._recovery_finished, n, ok, error))
                else:
                    # Detect power changes without entering a zero operation or
                    # replacing its status message on every routine health check.
                    from robot_arm_gui.protocol import read_frame
                    with c._lock:
                        c._guard()
                        c._request('读取电机状态', read_frame(0x3A, node),
                            lambda ok, n=node: GLib.idle_add(self._recovery_finished, n, ok, None))
            except RuntimeError:
                pass  # Another user operation may have claimed the bus.
        return True

    def _retry_saved_zero(self):
        if self._display_mailbox.closed:return False
        c=self.controller
        if (self._recovering_state or self._initializing_zero or self._powering_off or c.zero_home.busy or c.motion_task.busy
                or c._pending or c._switching or c._all_stopping or c.active_node is not None
                or any(s.moving for s in c.nodes.values())):return True
        now=time.monotonic()
        nodes=[n for n in sorted(c.zero_home.session_nodes) if not c.nodes[n].zero_valid
            and n in c.zero_home.reference_ids and now>=self._zero_recovery_retry_at.get(n,0)]
        if nodes:
            node=nodes[0]
            self._zero_recovery_retry_at[node]=now+3.
            try:
                c.zero_home.start('verify_session_node',node,
                    lambda ok,error:GLib.idle_add(self._saved_zero_verified))
            except RuntimeError:pass
        return True

    def _recover_state(self,*_args):
        if self._recovering_state or self._initializing_zero or self._powering_off:return
        c=self.controller
        self._recovering_state=True
        self._initializing_zero=True
        self.recover_state_button.set_sensitive(False)
        self.recovery_notice.show();self.recovery_text.show();self.recovery_notice.set_expanded(True)
        self.recovery_text.set_text('正在取消后台规划，等待任务和停止确认…')
        self._recovery_deadline=time.monotonic()+12.
        c.zero_home.recovery_results={}
        combined=self.joint_pages.combined_page
        combined.release_jog()
        if c.motion_task.busy:c.motion_task.cancel()
        if c.zero_home.busy:c.zero_home.cancel()
        if c.active_node is not None or c._moving or any(s.moving for s in c.nodes.values()):
            self._command(c.stop_all,quiet=True)
        self.joint_pages.update()
        GLib.timeout_add(100,self._recover_when_idle)

    def _recover_when_idle(self):
        if self._display_mailbox.closed:return False
        c=self.controller
        if (c.motion_task.busy or c.zero_home.busy or c._pending or c._switching or c._all_stopping
                or c.active_node is not None or c._moving or any(s.moving for s in c.nodes.values())):
            if time.monotonic()<self._recovery_deadline:return True
            self._state_recovered(False,'任务或停止尚未确认，请全部停止后重试；未强行解除运动锁')
            return False
        try:
            c.zero_home.start('verify_sessions',1,
                lambda ok,error:GLib.idle_add(self._state_recovered,ok,error))
        except Exception as exc:self._state_recovered(False,str(exc))
        return False

    def _state_recovered(self,ok,error):
        if self._display_mailbox.closed:return False
        c=self.controller;model=c.motion_task.cartesian
        # Only invalidate settled tasks; never manufacture completion.
        if not c.motion_task.busy and not c.zero_home.busy:
            model.clear_preview();model.prepared.invalidate()
            if hasattr(model,'drawing'):model.drawing.invalidate()
            self.joint_pages.drawing_page.signature=None
        self._recovering_state=False;self._initializing_zero=False
        self.recover_state_button.set_sensitive(True)
        rows=[]
        for n,v in sorted(c.zero_home.recovery_results.items()):
            rows.append('J%d · '%n+('已恢复 · %.3f°'%v['angle_deg'] if v['ok'] else '未通过 · '+v['error']))
        rows.append('恢复完成：请重新预览后执行。' if ok else '恢复未完全通过：'+error)
        self.recovery_text.set_text('\n'.join(rows))
        self.recovery_text.set_tooltip_text('\n'.join(rows))
        c._publish();self.joint_pages.update()
        return False

    def _saved_zero_verified(self):
        if not self._display_mailbox.closed:
            self.controller._publish()
            self.joint_pages.update()
        return False

    def _recovery_finished(self, node, ok, error):
        if self._display_mailbox.closed:
            return False
        if ok:
            self._zero_recovery_retry_at.pop(node, None)
        else:
            self._zero_recovery_retry_at[node] = time.monotonic() + 2.0
        if error is not None:
            self._zero_initialized(ok, error)
        # Continue after a confirmed reply, without waiting for another timer tick.
        self._retry_initial_zero()
        return False

    def _home_all(self, *_args):
        if self._initializing_zero or self._powering_off:
            return
        try:
            self.controller.zero_home.start('home_all', 1,
                lambda ok, error: GLib.idle_add(self._home_all_finished, ok, error))
        except Exception as exc:
            self._show_error(str(exc))

    def _home_all_finished(self, ok, error):
        if not ok and not self._display_mailbox.closed:
            self.controller.zero_home.message = error
        return False

    def _prepare_vision(self):
        if self._display_mailbox.closed: return False
        if self.vision_window is None:
            from robot_arm_gui.gtk_vision import VisionWindow
            self.vision_window = VisionWindow(self, lambda: self._command(self.controller.stop))
            page = self.vision_window.get_child()
            self.vision_window.remove(page)
            page.get_style_context().add_class('vision-window')
            self.workspace.add_named(page, 'vision')
            page.show_all()
        return False

    def _show_vision(self) -> bool:
        self._prepare_vision()
        if self._display_mailbox.closed: return False
        if self.vision_window.session.source is not None:
            self.vision_window.placeholder.hide()
        self.workspace.set_visible_child_name('vision')
        surface = self.get_window()
        if surface is None or not (surface.get_state() & Gdk.WindowState.FULLSCREEN): self.fullscreen()
        return False

    def _return_to_control(self):
        coco = getattr(self.vision_window, 'coco_panel', None)
        if coco is not None:
            coco.suspend()
        panel = getattr(self.vision_window, 'hardware_panel', None)
        if panel is not None and panel.session.running:
            panel.stop(on_stopped=self._return_to_control)
            return
        self.workspace.get_child_by_name('control').show()
        self.workspace.set_visible_child_name('control')
        self._flush_snapshot()

    def _show_coco_objects(self):
        self._prepare_vision()
        if self._display_mailbox.closed:return False
        self.workspace.set_visible_child_name('vision')
        self.vision_window.notebook.set_current_page(2)
        self.vision_window.coco_panel.start()
        return False

    def _confirm_shutdown(self, *_args):
        if self._powering_off:return
        if not self.live_control or not sys.platform.startswith('linux'):
            self._show_error('模拟界面不执行系统关机。');return
        target=self.controller.active_node
        dialog=Gtk.MessageDialog(transient_for=self,modal=True,message_type=Gtk.MessageType.QUESTION,
                                 buttons=Gtk.ButtonsType.NONE,text='确认关闭开发板？')
        ready = [n for n, s in self.controller.nodes.items() if s.zero_valid and s.online == '在线']
        skipped = [n for n in self.controller.nodes if n not in ready]
        dialog.format_secondary_text('将停止当前动作，让在线且零点有效的关节回0，确认到位并保存记录后关闭系统。\n回0：' + '、'.join(map(str, ready)) + '号；跳过：' + ('、'.join(map(str, skipped)) + '号' if skipped else '无') + '\n回零期间可点击停止取消。关机完成后再断电。')
        dialog.add_button('取消',Gtk.ResponseType.CANCEL)
        dialog.add_button('确认关机',Gtk.ResponseType.YES)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        def response(widget,result):
            widget.destroy()
            if result==Gtk.ResponseType.YES:self._begin_shutdown(target)
        dialog.connect('response',response);dialog.show_all()

    def _begin_shutdown(self, target=None):
        if self._powering_off:return
        status=self.controller.recorder.status(include_recent=False)
        if status['starting'] or status['exporting']:
            self._show_error('记录正在开始或导出，请完成后再关机。');return
        if self.controller._switching or self.controller._all_stopping:
            self._show_error('正在切换或停止电机，请完成后再关机。');return
        home = self.controller.zero_home
        if home.busy or not home.order or not any(s.zero_valid and s.online == '在线' for s in self.controller.nodes.values()):
            self._show_error('没有在线且零点有效的关节，请检查通信或在“零点设置”修正零点。');return
        self._powering_off=True;self._clear_hold()
        self.connection.set_text('正在准备关机…')
        def stopped(ok):
            GLib.idle_add(self._shutdown_stopped,ok)
        if target is not None or self.controller.active_node is not None or self.controller._pending:
            try:
                if target is not None:
                    with self.controller._lock:self.controller._stop_node(target,stopped)
                else:self.controller.stop(stopped)
            except Exception as exc:self._shutdown_finished(False,str(exc))
        else:self._shutdown_stopped(True)

    def _shutdown_stopped(self, ok):
        if not self._powering_off:
            return False
        if not ok:
            self._shutdown_finished(False,'停止未确认，关机已取消。');return False
        try:
            self.controller.zero_home.start('shutdown', self.controller.selected_node,
                lambda ok,error: GLib.idle_add(self._shutdown_finished,ok,error))
        except Exception as exc:
            self._shutdown_finished(False,str(exc))
        return False

    def _shutdown_finished(self, ok, error):
        if ok:self.destroy()
        else:
            self._powering_off=False;self.set_sensitive(True);self._flush_snapshot()
            self._show_error('关机失败：'+error)
        return False

    def _motion_mouse_press(self, button, event, command):
        from robot_arm_gui.gtk_touch import emulated
        if emulated(event):return True
        if self._touch_input.contacts and not getattr(event,'touch_input',False):
            self._touch_input.cancel();return True
        if self._powering_off:return True
        if event.button != 1:
            if self._held_node is not None: self._released()
            return True
        if event.type != Gdk.EventType.BUTTON_PRESS: return True
        if self._held_node is not None: return True
        if not button.get_sensitive(): return True
        self._pressed(button,command)
        return True

    def _motion_touch_press(self,button,event,command):
        if self._held_node is not None:
            self._released();return False
        self._motion_mouse_press(button,event,command)
        return self._held is button

    def _motion_mouse_release(self, button, event):
        from robot_arm_gui.gtk_touch import emulated
        if emulated(event) or self._touch_input.active(button):return True
        if event.button == 1: self._released()
        return True

    def _window_mouse_release(self, widget, event):
        from robot_arm_gui.gtk_touch import emulated
        if emulated(event) or self._touch_input.active(self._held):return False
        if event.button == 1 and self._held_node is not None: self._released()
        return False

    def _hold_cancelled(self, button, event):
        if self._held is button: self._released()
        return False

    def _hold_unmapped(self, button):
        if self._held is button: self._released()

    def _pointer_buttons(self):
        display=self.get_display()
        pointer=display.get_default_seat().get_pointer()
        window=Gdk.get_default_root_window() or self.get_window()
        if window is None: raise RuntimeError('无法读取鼠标状态')
        # GI includes the returned window before the three out parameters.
        _window, _x, _y, mask = window.get_device_position(pointer)
        return mask

    def _check_hold(self):
        if self._display_mailbox.closed: return False
        if self._held_node is not None:
            try: pressed=self._touch_input.active(self._held) or bool(self._pointer_buttons() & Gdk.ModifierType.BUTTON1_MASK)
            except Exception: pressed=False
            if not pressed: self._released()
        return True

    def _pressed(self, button, command) -> None:
        self._held = button
        self._held_node = self.controller.selected_node
        button.set_state_flags(Gtk.StateFlags.ACTIVE,False)
        self._command(command)
        if self.controller.active_node != self._held_node: self._clear_hold()

    def _clear_hold(self):
        button,self._held = self._held,None
        node,self._held_node = self._held_node,None
        if button is not None:self._touch_input.cancel_for(button)
        if button is not None: button.unset_state_flags(Gtk.StateFlags.ACTIVE)
        return node

    def _released(self, *_args) -> None:
        node=self._clear_hold()
        if node is not None:
            self._command(lambda: self.controller.release_motion(node),quiet=True)
        self._update_motion_enabled()

    def _focus_out(self, *_args) -> bool:
        if self.controller.active_node is not None:
            self._stop()
        return False

    def _speed_changed(self, adjustment: Gtk.Adjustment) -> None:
        if self._syncing:
            return
        speed = int(adjustment.get_value())
        self.speed_text.set_text(str(speed))
        self._command(lambda: self.controller.set_speed(speed), quiet=True)

    def _acceleration_changed(self, adjustment: Gtk.Adjustment) -> None:
        if self._syncing:
            return
        value = int(adjustment.get_value())
        self._command(lambda: self.controller.set_acceleration(value), quiet=True)

    def _update_motion_enabled(self) -> None:
        s = self.controller.snapshot
        active = self.safety.get_active() and s.enabled and s.online == "在线"
        free = not self._initializing_zero and not self._powering_off and not self.controller.zero_home.busy and not self.controller.motion_task.busy and not self.controller._pending and not self.controller._switching and not self.controller._all_stopping and self.controller.active_node is None
        self._set_cached(self.reverse, 'set_sensitive', active and (free or self._held is self.reverse))
        self._set_cached(self.forward, 'set_sensitive', active and (free or self._held is self.forward))

    def _command(self, command: Callable[[], None], quiet: bool = False) -> None:
        try:
            command()
        except Exception as exc:
            if not quiet:
                self._show_error(str(exc))

    def _stop(self) -> None:
        self._stop_peripherals()
        voice = self.cloud_windows.get('voice')
        if voice is not None:
            voice.invalidate_from_stop()
        if hasattr(self,'joint_pages'):self.joint_pages.cancel_record()
        self._initializing_zero = False
        if self._powering_off and not self.controller.zero_home.busy:
            self._powering_off = False
            self.controller.zero_home.message = '关机准备已取消'
        self._clear_hold()
        self._command(self.controller.stop)

    def _open_car(self, *_):
        if self.car_window is None:
            from robot_arm_gui.gtk_car_peripherals import CarPeripheralWindow
            self.car_window = CarPeripheralWindow(self)
        self.car_window.show_all()
        self.car_window.present()

    def _stop_peripherals(self):
        if not self._simulation_mode:
            from robot_arm_gui.car_peripherals import request_stop
            request_stop()

    def _stop_all(self):
        coco=getattr(getattr(self,'vision_window',None),'coco_panel',None)
        if coco is not None:coco.suspend()
        self._stop_peripherals()
        voice = self.cloud_windows.get('voice')
        if voice is not None:
            voice.invalidate_from_stop()
        combined=getattr(getattr(self,'joint_pages',None),'combined_page',None)
        if combined is not None:combined.release_jog(False)
        if hasattr(self,'joint_pages'):self.joint_pages.cancel_record()
        self._clear_hold()
        self._initializing_zero = False
        if self._powering_off and not self.controller.zero_home.busy:
            self._powering_off = False
            self.controller.zero_home.message = '关机准备已取消'
        self.controller.stop_all()

    def _queue_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._display_mailbox.put(snapshot)

    def _flush_snapshot(self):
        snapshot = self._display_mailbox.take()
        if snapshot is not None: self._apply_snapshot(snapshot)
        return not self._display_mailbox.closed

    def _set_cached(self, widget, method, value):
        key = (widget, method)
        if self._widget_values.get(key) != value:
            self._widget_values[key] = value
            getattr(widget, method)(value)

    def _refresh_recording(self):
        s=self.controller.recorder.status(include_recent=False)
        state='正在开始' if s['starting'] else '记录失败' if s['error'] else '正在导出' if s['exporting'] else '正在记录' if s['active'] else '已结束' if s['path'] else '未开始记录'
        if self._export_notice and not s['error'] and not s['active'] and not s['exporting'] and not s['starting']:
            state = '已导出' if self._export_notice[0] else '导出失败，可重试'
        self._set_cached(self.record_status, 'set_text', f"{state} · {s['seconds']//60:02d}:{s['seconds']%60:02d} · {s['count']} 条")
        self._set_cached(self.record_status, 'set_tooltip_text', s['error'] or (self._export_notice[1] if self._export_notice else '') or s['path'] or f"覆盖电机1–6；系统时间未校准时日期可能不准确。未完成日志：{s['incomplete']}份")
        self._set_cached(self.record_start, 'set_sensitive', not s['starting'] and not s['active'] and not s['exporting'])
        self._set_cached(self.record_end, 'set_sensitive', bool(s['path']) and not s['starting'] and not s['exporting'])
        self._set_cached(self.record_end, 'set_label', '结束并导出' if s['active'] or not s['path'] else '再次导出')
        self._set_cached(self.record_view, 'set_sensitive', bool(s['path']) or bool(s['incomplete']))
        return True

    def _record_start(self,*_):
        self._export_notice = None
        self._command(lambda: self.controller.start_recording_async(lambda ok,error: GLib.idle_add(self._record_started,ok,error)))
        self._refresh_recording()

    def _record_started(self, ok, error):
        if self._display_mailbox.closed: return False
        self._refresh_recording()
        if not ok: self._show_error('开始记录失败：' + error)
        return False

    def _record_export(self,*_):
        from pathlib import Path
        state = self.controller.recorder.status(include_recent=False)
        if not state['path'] or state['exporting']: return
        if self.export_dialog is None:
            self.export_dialog = Gtk.Dialog(title='结束记录并导出 CSV', transient_for=self, modal=True)
            self.export_dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '保存', Gtk.ResponseType.OK)
            self.export_dialog.set_default_size(660,160)
            box = self.export_dialog.get_content_area()
            box.set_border_width(12); box.set_spacing(8)
            box.pack_start(_label('保存路径（可以修改）；取消后继续记录'),False,False,0)
            self.export_entry = Gtk.Entry()
            box.pack_start(self.export_entry,False,False,0)
            self.export_dialog.connect('response',self._save_record_export)
            self.export_dialog.connect('delete-event',lambda dialog,event:(dialog.hide(),True)[1])
            box.show_all()
        self.export_entry.set_text(str(Path(state['path']).with_suffix('.csv')))
        self.export_dialog.show(); self.export_dialog.present()

    def _save_record_export(self, dialog, response):
        dialog.hide()
        if response != Gtk.ResponseType.OK: return
        from pathlib import Path
        destination = self.export_entry.get_text().strip()
        if not destination:
            self._record_exported(False,'保存路径不能为空'); return
        if not destination.lower().endswith('.csv'): destination += '.csv'
        if Path(destination).exists():
            confirm=Gtk.MessageDialog(transient_for=self,modal=True,buttons=Gtk.ButtonsType.YES_NO,text='文件已存在，是否覆盖？')
            accepted=confirm.run()==Gtk.ResponseType.YES;confirm.destroy()
            if not accepted: return
        try:
            self._export_notice = None
            self.controller.recorder.export_async(destination,lambda ok,message:GLib.idle_add(self._record_exported,ok,message))
        except Exception as exc: self._record_exported(False,str(exc))
        self._refresh_recording()

    def _record_exported(self,ok,message):
        if self._display_mailbox.closed: return False
        self._export_notice=(ok,message)
        self._refresh_recording()
        if self.record_dialog is not None and self.record_dialog.get_visible(): self._record_view()
        return False

    def _record_view(self,*_):
        state=self.controller.recorder.status()
        if self.record_dialog is None:
            self.record_dialog=Gtk.Dialog(title='最近测试记录 · 全部电机',transient_for=self,modal=False)
            self.record_dialog.add_button('关闭',Gtk.ResponseType.CLOSE)
            self.record_dialog.set_default_size(720,420)
            self.record_text=Gtk.TextView();self.record_text.set_editable(False)
            self.record_text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            scroll=Gtk.ScrolledWindow();scroll.add(self.record_text)
            self.record_dialog.get_content_area().pack_start(scroll,True,True,0)
            self.record_dialog.connect('response',lambda dialog,*_:dialog.hide())
            self.record_dialog.connect('delete-event',lambda dialog,event:(dialog.hide(),True)[1])
            self.record_dialog.get_content_area().show_all()
        lines=[state['path'] or str(self.controller.recorder.directory),state['error'],f"历史未完成日志：{state['incomplete']}份；系统时间未经校准"]
        if self._export_notice: lines.append(('已导出：' if self._export_notice[0] else '导出失败：')+self._export_notice[1])
        lines += [f"{r['time']} M{r.get('node','-')} {r['event']} {r.get('operation','')} {r.get('result','')} {r.get('error','')}" for r in state['recent']]
        content='\n'.join(lines)
        if getattr(self,'_record_text_cache',None)!=content:
            self.record_text.get_buffer().set_text(content); self._record_text_cache=content
        self.record_dialog.show();self.record_dialog.present()

    def _unlock_f3(self, _button) -> None:
        node = self.controller.selected_node
        dialog = Gtk.MessageDialog(transient_for=self, modal=True,
            message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.NONE,
            text=f"解除电机 {node} 的 F3 锁定？")
        dialog.format_secondary_text("请确认电机已停止，接线和编号正确。此操作只清除软件锁定，不自动使能或运动；解除后需重新使能。")
        dialog.add_button("取消", Gtk.ResponseType.CANCEL)
        dialog.add_button("确认解除", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self._command(lambda: self.controller.clear_f3_lock(node))

    def _apply_snapshot(self, snapshot: dict[str, Any]) -> bool:
        combined=getattr(self.joint_pages,'combined_page',None)
        if combined is not None and getattr(combined,'jog_pending',False):
            # Hundreds of GTK property/style updates can stall an ARM frame
            # long enough to expire the 300 ms hold lease. Keep only the hold
            # controls and task text current; repaint diagnostics after release.
            combined.update_jog();combined.show_jog_status()
            return False
        exclusive = self._initializing_zero or self._powering_off or self.controller.zero_home.busy or self.controller.motion_task.busy
        self.joint_pages.update()
        # This is display-only work. Control events and the hold lease retain
        # their own callbacks; a hidden control page needs no GTK mutations.
        if self.workspace.get_visible_child_name() != 'control':
            return False
        free = not exclusive and not snapshot['busy'] and snapshot.get('active_node') is None
        ready = [n for n in self.controller.zero_home.order if snapshot['nodes'][n]['zero_valid'] and snapshot['nodes'][n]['online'] == '在线']
        skipped = [n for n in self.controller.zero_home.order if n not in ready]
        self._set_cached(self.home_all_button, 'set_sensitive', free and bool(ready))
        self._set_cached(self.home_all_button, 'set_tooltip_text',
            ('回0：' + '、'.join(map(str, ready)) + '号' if ready else '没有在线且零点有效的关节') +
            ('；跳过：' + '、'.join(map(str, skipped)) + '号' if skipped else ''))
        self._set_cached(self.zero_button, 'set_sensitive', not exclusive)
        self._set_cached(self.vision_button, 'set_sensitive', not exclusive)
        self._set_cached(self.shutdown_button, 'set_sensitive', not exclusive)
        self._set_cached(self.unlock_button, 'set_sensitive', snapshot.get('f3_locked', False) and
            not snapshot['busy'] and snapshot.get('active_node') is None)
        node = snapshot["selected_node"]
        self._set_cached(self.control_title, 'set_text', f"电机 {node}")
        bounds = snapshot.get('joint_limits', {}).get(node)
        limit_text = (f'软件限位：{bounds[0]}° ～ {bounds[1]}°（当前零点）'
                      if bounds else '此关节暂不限位')
        if bounds and snapshot.get('motor_angle') is not None and snapshot.get('zero_valid'):
            from robot_arm_gui.zero_home import RATIOS
            limit_text = f"限位{bounds[0]}～{bounds[1]}° · 当前{snapshot['motor_angle']/RATIOS[node]:.1f}°"
        if node==4 and self.controller.joint_limits.coupled:
            j3=snapshot['nodes'][3]
            from robot_arm_gui.zero_home import RATIOS
            confirmed=j3.get('zero_valid') and j3.get('motor_angle') is not None
            limit_text=('J3≤34°：J4无限位' if confirmed and j3['motor_angle']/RATIOS[3]<=34
                        else 'J3>34°或角度未确认：J4 '+str(bounds[0])+'～'+str(bounds[1])+'°')
        notice = snapshot.get('limit_notice') or self.controller.joint_limits.error
        self._set_cached(self.limit_label, 'set_text', notice or limit_text)
        self._set_cached(self.limit_label, 'set_tooltip_text', limit_text + ('；' + notice if notice else ''))
        self._set_cached(self.stop_button, 'set_label', "■  停止全部回0" if snapshot.get("parallel_home") else f"■  停止电机 {snapshot.get('active_node') or node}")
        for n, button in self.motor_buttons.items():
            self._set_cached(button, 'set_sensitive', not exclusive)
            state = snapshot["nodes"][n]
            from robot_arm_gui.zero_home import RATIOS
            angle = f"{state['motor_angle']/RATIOS[n]:.2f}°" if state.get('motor_angle') is not None and state['zero_valid'] else '角度待确认'
            self._set_cached(button, 'set_label', f"J{n} · {angle}\n{state['online']} · {state['state'].replace('已停止（保持使能）', '已停止')}")
            self._set_cached(button, 'set_tooltip_text', f"电机 {n}：{state['online']} · {state['state']}")
            context = button.get_style_context()
            if self._selected_style_node != node:
                context.remove_class("selected")
                if n == node: context.add_class("selected")
        self._selected_style_node = node
        self._syncing = True
        self._set_cached(self.speed_adjustment, 'set_value', snapshot['speed_rpm'])
        self._set_cached(self.acceleration_adjustment, 'set_value', snapshot['acceleration'])
        self._set_cached(self.speed_text, 'set_text', str(snapshot['speed_rpm']))
        self._syncing = False
        results = snapshot.get('all_stop_results', {})
        task=self.controller.motion_task
        progress=(f'姿态 {task.current_point}/{task.total_points} · ' if task.current_point else '')+task.phase+' · '+task.message
        status_text=progress if task.busy else ("全部停止：" + "  ".join(f"{n}号 {r}" for n, r in results.items()) if results and not exclusive else self.controller.zero_home.message)
        self._set_cached(self.all_stop_label, 'set_text', status_text)
        self._set_cached(self.all_stop_label, 'set_tooltip_text', status_text)
        for control in (self.speed_spin, self.speed_scale, self.acceleration_spin):
            self._set_cached(control, 'set_sensitive', not snapshot['busy'])
        self._set_cached(self.enable, 'set_sensitive', free)
        self._set_cached(self.disable, 'set_sensitive', not exclusive and not snapshot['busy'])
        self._update_motion_enabled()
        self._set_cached(self.connection, 'set_text', str(snapshot.get("connection", "-")))
        self._set_cached(self.state, 'set_text', str(snapshot.get("state", "-")))
        error = str(snapshot.get('error', '无'))
        self._set_cached(self.fault_summary, 'set_text', '' if error in ('无', '-', '') else error)
        self._set_cached(self.fault_summary, 'set_tooltip_text', error)
        for key, label in self.values.items():
            if not self.diagnostics.get_mapped():
                continue
            if key not in ('motor', 'direction', 'error') and not self.communication_details.get_expanded():
                continue
            self._set_cached(label, 'set_text', str(snapshot.get(key, "-")))
            self._set_cached(label, 'set_tooltip_text', str(snapshot.get(key, "-")))
        context = self.values["error"].get_style_context()
        error_style = 'good' if snapshot.get('error') == '无' else 'bad'
        if self._widget_values.get('error_style') != error_style:
            context.remove_class('good'); context.remove_class('bad'); context.add_class(error_style)
            self._widget_values['error_style'] = error_style
        return False

    def _show_error(self, message: str) -> None:
        if getattr(getattr(self, '_display_mailbox', None), 'closed', False):
            return
        # An error can arrive while a touch release is still waiting to open
        # the local keyboard. Withdraw those editors before taking modality.
        for top in Gtk.Window.list_toplevels():
            parent, visited = top, set()
            while parent is not None and parent is not self and parent not in visited:
                visited.add(parent)
                parent = parent.get_transient_for()
            if parent is self:
                keyboard = getattr(top, '_f3p_numeric_keyboard', None)
                if keyboard is not None:
                    keyboard.close()
        dialog = getattr(self, '_error_dialog', None)
        if dialog is None:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text="控制命令失败",
            )
            self._error_dialog = dialog
            self._error_message = None
            dialog.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
            # Keep the widgets and their styling warm between errors. Hiding
            # also releases the modal grab; parent teardown still destroys it.
            dialog.connect('response', lambda widget, _response: widget.hide())
            dialog.connect('delete-event', lambda widget, _event: widget.hide_on_delete())
            def destroyed(widget):
                if getattr(self, '_error_dialog', None) is widget:
                    self._error_dialog = None
                    self._error_message = None
            dialog.connect('destroy', destroyed)
        message = str(message)
        if self._error_message != message:
            dialog.format_secondary_text(message)
            self._error_message = message
        # Keep one visible error window. Repeated failures update its text
        # without nesting GTK main loops or repeatedly moving window focus.
        if not dialog.get_visible():
            dialog.show_all()
            dialog.present()

    def _key_press(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval in (Gdk.KEY_Escape,Gdk.KEY_space):
            combined=getattr(getattr(self,'joint_pages',None),'combined_page',None)
            if combined is not None:combined.release_jog()
        if event.keyval == Gdk.KEY_Escape:
            if combined is not None and getattr(combined,'canvas_fullscreen',False):
                combined.set_canvas_fullscreen(False); return True
            if self.workspace.get_visible_child_name() == 'vision':
                self._return_to_control(); return True
            self.unfullscreen()
            return True
        if event.keyval == Gdk.KEY_space:
            self._stop()
            return True
        return False

    def _destroy(self, _widget: Gtk.Widget) -> None:
        self._stop_peripherals()
        if self.car_window is not None:
            self.car_window.destroy()
        combined=getattr(getattr(self,'joint_pages',None),'combined_page',None)
        if combined is not None and hasattr(combined,'destroy_jog'):combined.destroy_jog()
        self._initializing_zero = False
        self.controller.zero_home.cancel()
        self._display_mailbox.close()
        GLib.source_remove(self._hold_timer)
        GLib.source_remove(self._display_timer)
        GLib.source_remove(self._record_timer)
        if self.vision_window is not None:
            self.vision_window.session.closed = True
            self.vision_window.destroy()
        for dialog in (self.record_dialog,self.export_dialog):
            if dialog is not None: dialog.destroy()
        for window in self.cloud_windows.values():
            window.destroy()
        self.controller.close()
        Gtk.main_quit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="F3P GTK3 HDMI control panel")
    parser.add_argument("--backend", choices=("simulation", "mmio", "socketcan"), default="simulation")
    parser.add_argument("--interface", default="vcan0")
    parser.add_argument("--allow-live-control", action="store_true")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--no-initialize-zero", action="store_true", help="Maintenance start: read existing reference only, never reset driver origin")
    return parser


def claim_live_control(path='/run/lock/f3p-arm-mmio.lock'):
    """Hold an OS lock before opening the live MMIO transport."""
    import fcntl
    handle=open(path,'a')
    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BaseException:handle.close();raise
    return handle


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.backend != "simulation" and not args.allow_live_control:
        print("ERROR: live backends require --allow-live-control", file=sys.stderr)
        return 2
    live_owner=None
    if args.backend=='mmio':
        try:live_owner=claim_live_control()
        except OSError:
            print('ERROR: another live controller already owns MMIO; open the existing window',file=sys.stderr)
            return 3
    provider = Gtk.CssProvider()
    provider.load_from_data(touch_css(Gdk.Screen.get_default().get_height() if not args.windowed else 800))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    if args.backend == "mmio":
        backend = MemoryMappedBackend()
    elif args.backend == "socketcan":
        backend = SocketCanBackend(args.interface)
    else:
        backend = SimulatedBackend()
    window = ControlWindow(MotorController(backend, snapshot_interval=.2), live_control=args.backend != "simulation",initialize_zero=not args.no_initialize_zero)
    window.show_all()
    window.joint_pages.show('drawing')
    if not args.windowed:
        window.fullscreen()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
