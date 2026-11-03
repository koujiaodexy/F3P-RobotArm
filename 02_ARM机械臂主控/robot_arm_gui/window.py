"""PyQt6 full-screen operator interface."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent
from PyQt6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog, QDialog, QDialogButtonBox, QTextEdit, QLineEdit, QStackedWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .controller import MotorController
from .ui_updates import SnapshotMailbox
from .protocol import (
    DEFAULT_ACCELERATION,
    MAX_ACCELERATION,
    MAX_SPEED_RPM,
    MIN_ACCELERATION,
    MIN_SPEED_RPM,
)


STYLE = """
QWidget { background: #0b1220; color: #e7eefc; }
QLabel { background: transparent; }
QFrame#card { background: #111c2f; border: 1px solid #263652; border-radius: 14px; }
QLabel#title { font-size: 26px; font-weight: 700; }
QLabel#subtitle { color: #91a4c4; font-size: 13px; }
QLabel#section { color: #8fa5c9; font-size: 13px; font-weight: 700; }
QLabel#value { font-size: 18px; font-weight: 650; }
QLabel#speed { color: #59d3ff; font-size: 44px; font-weight: 800; }
QPushButton { min-height: 36px; border: 1px solid transparent; border-radius: 12px;
              background: #1a2a43; font-size: 18px; font-weight: 700; padding: 6px 18px; }
QPushButton:hover { background: #223957; }
QPushButton:pressed { background: #2c4a70; }
QPushButton:disabled { color: #62718b; background: #141d2b; border-color: transparent; }
QPushButton#enable { background: #146c52; border-color: transparent; }
QPushButton#disable { background: #61394a; border-color: transparent; }
QPushButton#stop { min-height: 38px; background: #b52f3a; border: 2px solid transparent; font-size: 26px; }
QPushButton#motion { min-height: 40px; font-size: 22px; }
QPushButton#motion:disabled { background: #1a2a43; color: #e7eefc; border-color: transparent; }
QPushButton#enable:disabled { background: #146c52; color: #e7eefc; border-color: transparent; }
QPushButton#disable:disabled { background: #61394a; color: #e7eefc; border-color: transparent; }
QSpinBox { background: #0b1424; border: 1px solid #365075; border-radius: 8px;
           padding: 6px; font-size: 18px; min-width: 100px; }
QSlider::groove:horizontal { height: 8px; background: #273a59; border-radius: 4px; }
QSlider::handle:horizontal { width: 24px; margin: -8px 0; background: #59d3ff; border-radius: 12px; }
QCheckBox { color: #aebbd0; spacing: 10px; }
"""


class SnapshotBridge(QWidget):
    updated = pyqtSignal(dict)
    vision_ready = pyqtSignal()
    export_done = pyqtSignal(bool, str)
    record_started = pyqtSignal(bool, str)


class MainWindow(QMainWindow):
    def __init__(self, controller: MotorController, live_control: bool) -> None:
        super().__init__()
        self.controller = controller
        self.live_control = live_control
        self.setWindowTitle("F3P 机械臂控制台")
        self.setMinimumSize(1100, 650)
        self.resize(1280, 720)
        self.setStyleSheet(STYLE)

        self.bridge = SnapshotBridge()
        self._display_mailbox = SnapshotMailbox()
        self._widget_values = {}
        self.bridge.record_started.connect(self._record_started)
        self.bridge.vision_ready.connect(self._show_vision)
        self.bridge.export_done.connect(self._record_exported)
        self.controller.on_snapshot = self._display_mailbox.put

        self.values: dict[str, QLabel] = {}
        self.vision_window = None
        self.record_dialog = None
        self.export_dialog = None
        self._export_notice = None
        self._held_node = None
        self._held_button = None
        self._build_ui()
        QApplication.instance().installEventFilter(self)
        self.hold_timer = QTimer(self)
        self.hold_timer.timeout.connect(self._check_hold)
        self.hold_timer.start(50)
        QTimer.singleShot(0, self._prepare_vision)
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self._refresh_recording)
        self.record_timer.start(1000)
        self.display_timer = QTimer(self)
        self.display_timer.timeout.connect(self._flush_snapshot)
        self.display_timer.start(200)
        self._refresh_recording()
        QShortcut(QKeySequence("Esc"), self, activated=self._escape)
        QShortcut(QKeySequence("Space"), self, activated=self._stop)

        try:
            self.controller.connect()
        except Exception as exc:
            self._show_error(str(exc))

    def _card(self) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)
        return frame, layout

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 10, 18, 10)
        outer.setSpacing(4)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("F3P 机械臂控制台")
        title.setObjectName("title")
        subtitle = QLabel("六电机 X42S · 500 kbit/s · 29 位扩展帧 · 空格键停止")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.vision_button = QPushButton("图像处理")
        self.vision_button.setStyleSheet("min-height: 30px; font-size: 15px;")
        self.vision_button.clicked.connect(self._open_vision)
        header.addWidget(self.vision_button)
        self.connection_badge = QLabel("正在连接…")
        self.connection_badge.setObjectName("value")
        header.addWidget(self.connection_badge)
        outer.addLayout(header)
        motors = QHBoxLayout()
        self.motor_buttons = {}
        for node in range(1, 7):
            button = QPushButton(f"电机 {node}\n未探测 · 未使能")
            button.setStyleSheet("min-height: 36px; font-size: 14px; padding: 4px;")
            button.clicked.connect(lambda _checked=False, n=node: self._command(lambda: self.controller.select_motor(n)))
            motors.addWidget(button)
            self.motor_buttons[node] = button
        self.all_stop_button = QPushButton("全部停止")
        self.all_stop_button.setStyleSheet("background: #b52f3a; min-height: 36px; font-size: 15px;")
        self.all_stop_button.clicked.connect(lambda: self._command(self.controller.stop_all))
        motors.addWidget(self.all_stop_button)
        outer.addLayout(motors)
        recording = QHBoxLayout()
        self.record_status = QLabel('未记录')
        self.record_status.setObjectName('subtitle')
        recording.addWidget(self.record_status, 1)
        self.record_start = QPushButton('开始记录')
        self.record_end = QPushButton('结束并导出')
        self.record_view = QPushButton('查看记录')
        for button, handler in ((self.record_start,self._record_start),(self.record_end,self._record_export),
                                (self.record_view,self._record_view)):
            button.setStyleSheet('min-height: 24px; font-size: 14px; padding: 4px 12px;')
            button.clicked.connect(handler)
            recording.addWidget(button)
        outer.addLayout(recording)
        self.all_stop_label = QLabel("单次只允许一台运动；切换前等待停止确认")
        self.all_stop_label.setObjectName("subtitle")
        outer.addWidget(self.all_stop_label)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        control_card, control = self._card()
        diag_card, diag = self._card()
        columns.addWidget(control_card, 7)
        columns.addWidget(diag_card, 3)
        outer.addLayout(columns, 1)

        self.control_title = section = QLabel("电机 1 · 运动控制")
        section.setObjectName("section")
        control.addWidget(section)
        state_row = QHBoxLayout()
        state_row.addWidget(QLabel("当前状态"))
        self.state_value = QLabel("空闲")
        self.state_value.setObjectName("value")
        state_row.addStretch()
        state_row.addWidget(self.state_value)
        control.addLayout(state_row)

        enable_row = QHBoxLayout()
        self.enable_button = QPushButton("使能")
        self.enable_button.setObjectName("enable")
        self.enable_button.clicked.connect(lambda: self._command(self.controller.enable))
        self.disable_button = QPushButton("失能")
        self.disable_button.setObjectName("disable")
        self.disable_button.clicked.connect(lambda: self._command(self.controller.disable))
        enable_row.addWidget(self.enable_button)
        enable_row.addWidget(self.disable_button)
        control.addLayout(enable_row)
        self.unlock_button = QPushButton("手动解除 F3 锁定")
        self.unlock_button.clicked.connect(self._unlock_f3)
        control.addWidget(self.unlock_button)

        speed_caption = QLabel("目标转速")
        speed_caption.setObjectName("section")
        control.addWidget(speed_caption)
        speed_row = QHBoxLayout()
        self.speed_label = QLabel("30")
        self.speed_label.setObjectName("speed")
        speed_row.addWidget(self.speed_label)
        speed_row.addWidget(QLabel("RPM"))
        speed_row.addStretch()
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(MIN_SPEED_RPM, MAX_SPEED_RPM)
        self.speed_spin.setValue(30)
        self.speed_spin.setSuffix(" RPM")
        speed_row.addWidget(self.speed_spin)
        control.addLayout(speed_row)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(MIN_SPEED_RPM, MAX_SPEED_RPM)
        self.speed_slider.setValue(30)
        self.speed_slider.valueChanged.connect(self.speed_spin.setValue)
        self.speed_spin.valueChanged.connect(self.speed_slider.setValue)
        self.speed_spin.valueChanged.connect(self._speed_changed)
        control.addWidget(self.speed_slider)

        acceleration_row = QHBoxLayout()
        acceleration_row.addWidget(QLabel("加速度档位"))
        acceleration_row.addWidget(QLabel("0 = 直接启动"))
        acceleration_row.addStretch()
        self.acceleration_spin = QSpinBox()
        self.acceleration_spin.setRange(MIN_ACCELERATION, MAX_ACCELERATION)
        self.acceleration_spin.setValue(DEFAULT_ACCELERATION)
        self.acceleration_spin.valueChanged.connect(self._acceleration_changed)
        acceleration_row.addWidget(self.acceleration_spin)
        control.addLayout(acceleration_row)

        live_text = "我已确认急停、负载支撑和扫掠区域安全"
        self.safety_check = QCheckBox(live_text)
        self.safety_check.setChecked(not self.live_control)
        self.safety_check.setEnabled(self.live_control)
        self.safety_check.toggled.connect(self._update_motion_enabled)
        control.addWidget(self.safety_check)

        motion_row = QHBoxLayout()
        self.reverse_button = QPushButton("按住反向")
        self.forward_button = QPushButton("按住正向")
        for button in (self.reverse_button, self.forward_button):
            button.setObjectName("motion")
        motion_row.addWidget(self.reverse_button)
        motion_row.addWidget(self.forward_button)
        control.addLayout(motion_row)

        self.stop_button = QPushButton("■  停止")
        self.stop_button.setObjectName("stop")
        self.stop_button.clicked.connect(self._stop)
        control.addWidget(self.stop_button)
        self._update_motion_enabled()

        diag_title = QLabel("通信诊断")
        diag_title.setObjectName("section")
        diag.addWidget(diag_title)
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
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for row, (key, label_text) in enumerate(fields):
            label = QLabel(label_text)
            label.setObjectName("subtitle")
            value = QLabel("-")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.values[key] = value
            grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        diag.addLayout(grid)
        diag.addStretch()

        warning = QLabel("软件停止依赖通信链路，不能替代断电急停、硬件失能、限位和过流保护。")
        warning.setObjectName("subtitle")
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(warning)
        self.workspace = QStackedWidget()
        self.workspace.addWidget(root)
        self.setCentralWidget(self.workspace)

    def _open_vision(self) -> None:
        if self.controller.active_node is None:
            self._show_vision()
            return
        self._command(lambda: self.controller.stop(
            lambda ok: self.bridge.vision_ready.emit() if ok else None))

    def eventFilter(self, watched, event):
        kind=event.type()
        buttons=(getattr(self,'forward_button',None),getattr(self,'reverse_button',None))
        if kind==QEvent.Type.MouseButtonPress:
            if event.button()!=Qt.MouseButton.LeftButton:
                if self._held_node is not None:self._released()
                if watched in buttons:return True
            elif watched in buttons:
                if self._held_node is None and watched.isEnabled():
                    self._held_button=watched;watched.setDown(True)
                    self._pressed(self.controller.move_forward if watched is self.forward_button else self.controller.move_reverse)
                    if self._held_button is watched:watched.grabMouse()
                return True
        if kind==QEvent.Type.MouseButtonRelease:
            if event.button()==Qt.MouseButton.LeftButton and self._held_node is not None:self._released()
            if watched in buttons:return True
        if kind in (QEvent.Type.UngrabMouse,QEvent.Type.Hide) and watched is self._held_button:self._released()
        if kind==QEvent.Type.ApplicationDeactivate and self._held_node is not None:self._released()
        return super().eventFilter(watched,event)

    def _check_hold(self):
        if self._held_node is not None and not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):self._released()

    def _pressed(self, command) -> None:
        self._held_node = self.controller.selected_node
        self._command(command)
        if self.controller.active_node != self._held_node:self._clear_hold()

    def _clear_hold(self):
        node,self._held_node=self._held_node,None
        button,self._held_button=self._held_button,None
        if button is not None:
            button.setDown(False);button.releaseMouse()
        return node

    def _released(self) -> None:
        node=self._clear_hold()
        if node is not None:self._command(lambda:self.controller.release_motion(node),quiet=True)
        self._update_motion_enabled()

    def _prepare_vision(self):
        if self._display_mailbox.closed: return
        if self.vision_window is None:
            from .vision_window import VisionWindow
            self.vision_window = VisionWindow(self, self._stop)
            self.vision_window.setWindowFlags(Qt.WindowType.Widget)
            self.workspace.addWidget(self.vision_window)

    def _show_vision(self) -> None:
        self._prepare_vision()
        self.workspace.setCurrentWidget(self.vision_window)
        if not self.isFullScreen(): self.showFullScreen()

    def _return_to_control(self):
        if self.vision_window is not None:self.vision_window._close_camera()
        self.workspace.setCurrentIndex(0)
        self._flush_snapshot()

    def _escape(self):
        if self.workspace.currentIndex() == 1: self._return_to_control()
        else: self.showNormal()

    def _speed_changed(self, value: int) -> None:
        self.speed_label.setText(str(value))
        self._command(lambda: self.controller.set_speed(value), quiet=True)

    def _acceleration_changed(self, value: int) -> None:
        self._command(lambda: self.controller.set_acceleration(value), quiet=True)

    def _update_motion_enabled(self) -> None:
        s = self.controller.snapshot
        allowed = self.safety_check.isChecked() and s.enabled and s.online == "在线"
        free = not self.controller._pending and not self.controller._switching and not self.controller._all_stopping and self.controller.active_node is None
        self.forward_button.setEnabled(allowed and (free or self.forward_button.isDown()))
        self.reverse_button.setEnabled(allowed and (free or self.reverse_button.isDown()))

    def _command(self, command: Any, quiet: bool = False) -> None:
        try:
            command()
        except Exception as exc:
            if not quiet:
                self._show_error(str(exc))

    def _stop(self) -> None:
        self._clear_hold()
        self._command(self.controller.stop)

    def _refresh_recording(self):
        s = self.controller.recorder.status(include_recent=False)
        state = '正在开始' if s['starting'] else '记录异常' if s['error'] else '导出中' if s['exporting'] else '记录中' if s['active'] else '已结束' if s['path'] else '未记录'
        if self._export_notice and not s['error'] and not s['active'] and not s['exporting'] and not s['starting']:
            state = '已导出' if self._export_notice[0] else '导出失败，可重试'
        self._set_cached(self.record_status, 'setText', f"{state} · {s['seconds']//60:02d}:{s['seconds']%60:02d} · {s['count']} 条")
        self._set_cached(self.record_status, 'setToolTip', s['error'] or (self._export_notice[1] if self._export_notice else '') or s['path'] or '系统时间未经校准')
        self._set_cached(self.record_start, 'setEnabled', not s['starting'] and not s['active'] and not s['exporting'])
        self._set_cached(self.record_end, 'setEnabled', bool(s['path']) and not s['starting'] and not s['exporting'])
        self._set_cached(self.record_end, 'setText', '结束并导出' if s['active'] or not s['path'] else '再次导出')
        self._set_cached(self.record_view, 'setEnabled', bool(s['path']) or bool(s['incomplete']))

    def _record_start(self):
        self._export_notice = None
        self._command(lambda: self.controller.start_recording_async(self.bridge.record_started.emit))
        self._refresh_recording()

    def _record_started(self, ok, error):
        if self._display_mailbox.closed: return
        self._refresh_recording()
        if not ok: self._show_error('开始记录失败：' + error)

    def _record_export(self):
        from pathlib import Path
        state = self.controller.recorder.status(include_recent=False)
        if not state['path'] or state['exporting']: return
        if self.export_dialog is None:
            self.export_dialog = QDialog(self)
            self.export_dialog.setWindowTitle('结束记录并导出 CSV')
            self.export_dialog.setModal(True); self.export_dialog.resize(660,160)
            layout=QVBoxLayout(self.export_dialog)
            layout.addWidget(QLabel('保存路径（可以修改）；取消后继续记录'))
            self.export_entry=QLineEdit(); layout.addWidget(self.export_entry)
            buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self._save_record_export)
            buttons.rejected.connect(self.export_dialog.hide);layout.addWidget(buttons)
        self.export_entry.setText(str(Path(state['path']).with_suffix('.csv')))
        self.export_dialog.show(); self.export_dialog.raise_()

    def _save_record_export(self):
        from pathlib import Path
        self.export_dialog.hide()
        destination=self.export_entry.text().strip()
        if not destination:
            self._record_exported(False,'保存路径不能为空');return
        if not destination.lower().endswith('.csv'):destination += '.csv'
        if Path(destination).exists() and QMessageBox.question(self,'覆盖文件','文件已存在，是否覆盖？') != QMessageBox.StandardButton.Yes:return
        try:
            self._export_notice=None
            self.controller.recorder.export_async(destination,self.bridge.export_done.emit)
        except Exception as exc:self._record_exported(False,str(exc))
        self._refresh_recording()

    def _record_exported(self, ok, message):
        if self._display_mailbox.closed:return
        self._export_notice=(ok,message)
        self._refresh_recording()
        if self.record_dialog is not None and self.record_dialog.isVisible(): self._record_view()

    def _record_view(self):
        state=self.controller.recorder.status()
        if self.record_dialog is None:
            self.record_dialog=QDialog(self);self.record_dialog.setWindowTitle('最近测试记录');self.record_dialog.resize(720,420)
            layout=QVBoxLayout(self.record_dialog)
            self.record_text=QTextEdit();self.record_text.setReadOnly(True);layout.addWidget(self.record_text)
            buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(self.record_dialog.hide);layout.addWidget(buttons)
        lines=[state['path'],state['error'],f"历史未完成日志：{state['incomplete']}份；系统时间未经校准"]
        if self._export_notice:lines.append(('已导出：' if self._export_notice[0] else '导出失败：')+self._export_notice[1])
        lines += [f"{r['time']} 电机{r.get('node','-')} {r['event']} {r.get('operation','')} {r.get('result','')} {r.get('error','')}" for r in state['recent']]
        content='\n'.join(lines)
        if getattr(self,'_record_text_cache',None)!=content:
            self.record_text.setPlainText(content);self._record_text_cache=content
        self.record_dialog.show();self.record_dialog.raise_()

    def _unlock_f3(self) -> None:
        node = self.controller.selected_node
        answer = QMessageBox.question(self, f"解除电机 {node} 的 F3 锁定？",
            "请确认电机已停止，接线和编号正确。此操作只清除软件锁定，不自动使能或运动；解除后需重新使能。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._command(lambda: self.controller.clear_f3_lock(node))

    def _flush_snapshot(self):
        snapshot = self._display_mailbox.take()
        if snapshot is not None: self._apply_snapshot(snapshot)

    def _set_cached(self, widget, method, value):
        key = (widget, method)
        if self._widget_values.get(key) != value:
            self._widget_values[key] = value
            getattr(widget, method)(value)

    def _apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._set_cached(self.unlock_button, 'setEnabled', snapshot.get('f3_locked', False) and
            not snapshot['busy'] and snapshot.get('active_node') is None)
        node = snapshot["selected_node"]
        self._set_cached(self.control_title, 'setText', f"电机 {node} · 运动控制 · CAN 0x{node << 8:03X}")
        self._set_cached(self.stop_button, 'setText', f"■  停止电机 {snapshot.get('active_node') or node}")
        for n, button in self.motor_buttons.items():
            state = snapshot["nodes"][n]
            self._set_cached(button, 'setText', f"电机 {n}\n{state['online']} · {state['state'].replace('已停止（保持使能）', '已停止')}")
            self._set_cached(button, 'setStyleSheet', "min-height: 36px; font-size: 13px; padding: 4px;" +
                ("background: #146c52; border: 2px solid transparent;" if n == node else ""))
        for widget, value in ((self.speed_spin, snapshot['speed_rpm']), (self.speed_slider, snapshot['speed_rpm']), (self.acceleration_spin, snapshot['acceleration'])):
            widget.blockSignals(True)
            self._set_cached(widget, 'setValue', value)
            widget.blockSignals(False)
        self._set_cached(self.speed_label, 'setText', str(snapshot['speed_rpm']))
        results = snapshot.get('all_stop_results', {})
        self._set_cached(self.all_stop_label, 'setText', "全部停止：" + "  ".join(f"{n}号 {r}" for n, r in results.items()) if results else "单次只允许一台运动；切换前等待停止确认")
        self._set_cached(self.speed_spin, 'setEnabled', not snapshot['busy'])
        self._set_cached(self.speed_slider, 'setEnabled', not snapshot['busy'])
        self._set_cached(self.acceleration_spin, 'setEnabled', not snapshot['busy'])
        self._set_cached(self.enable_button, 'setEnabled', not snapshot['busy'] and snapshot.get('active_node') is None)
        self._set_cached(self.disable_button, 'setEnabled', not snapshot['busy'])
        self._update_motion_enabled()
        self._set_cached(self.connection_badge, 'setText', str(snapshot.get("connection", "-")))
        self._set_cached(self.state_value, 'setText', str(snapshot.get("state", "-")))
        for key, label in self.values.items():
            self._set_cached(label, 'setText', str(snapshot.get(key, "-")))
        error = str(snapshot.get("error", "无"))
        self._set_cached(self.values["error"], 'setStyleSheet', 
            "color: #ff7b86; font-weight: 700;" if error != "无" else "color: #70e1a1;"
        )

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "控制命令失败", message)

    def changeEvent(self, event) -> None:
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow() and self.controller.active_node is not None:
            self._stop()
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self.vision_window is not None:
            self.vision_window.shutdown_camera()
            self.vision_window.session.closed = True
            self.vision_window.hide()
        self._display_mailbox.close()
        QApplication.instance().removeEventFilter(self)
        self.hold_timer.stop()
        self.display_timer.stop(); self.record_timer.stop()
        self.controller.close()
        event.accept()
