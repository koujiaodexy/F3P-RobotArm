"""Touch workspace for current axis-endpoint mapping and Y220/330 route preview."""
import time
import threading

from gi.repository import Gdk, GLib, Gtk

from .grasp_preview import COLORS, NAMES, preview_plan, quantities, fresh_targets, checked_pick_offset
from .grasp_motion import BOX_LAYOUT, RunControl
from .six_item_catalog import PICK_ITEMS, PICK_LABELS, DROP_BOX_FOR_ITEM
from .gtk_touch import set_status_text


class CaptionButton(Gtk.Button):
    """Keep the caption child when its text changes on an unmapped page."""
    def __init__(self, text, callback):
        super().__init__()
        self.caption = Gtk.Label(label=text)
        self.add(self.caption)
        self.get_accessible().set_name(text)
        self.connect('clicked', callback)

    def set_label(self, text):
        set_status_text(self.caption, text)
        self.get_accessible().set_name(text)

    def get_label(self):
        return self.caption.get_text()


class GraspOffsetDialog(Gtk.Dialog):
    """Edit a draft only; no movement and no persistent calibration writes."""
    def __init__(self, owner, values):
        super().__init__(title='临时夹取偏置', transient_for=owner, modal=True)
        self.add_buttons('取消', Gtk.ResponseType.CANCEL, '应用', Gtk.ResponseType.OK)
        self.set_default_size(460, 420)
        self.set_resizable(False)
        self.values = checked_pick_offset(values)
        area = self.get_content_area()
        area.set_border_width(16)
        area.set_spacing(12)
        note = Gtk.Label(label='以取料画面方向为准，叠加在当前标定上。\n只调整取料点；重启界面后清零。', xalign=0)
        note.set_line_wrap(True)
        area.pack_start(note, False, False, 0)
        row = Gtk.Box(spacing=12)
        row.pack_start(Gtk.Label(label='每次调整'), False, False, 0)
        self.step = Gtk.ComboBoxText()
        for value in (1, 5, 10):
            self.step.append(str(value), '%d mm' % value)
        self.step.set_active_id('1')
        self.step.set_size_request(140, 48)
        row.pack_start(self.step, True, True, 0)
        area.pack_start(row, False, False, 0)
        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_column_homogeneous(True)
        self.direction_buttons = {}
        for key, caption, column, row, dx, dz in (
                ('up', '↑ 上', 1, 0, 0, 1), ('left', '← 左', 0, 1, -1, 0),
                ('right', '右 →', 2, 1, 1, 0), ('down', '↓ 下', 1, 2, 0, -1)):
            button = Gtk.Button(label=caption)
            button.set_size_request(110, 56)
            button.connect('clicked', lambda _button, x=dx, z=dz: self.nudge(x, z))
            self.direction_buttons[key] = button
            grid.attach(button, column, row, 1, 1)
        self.reset = Gtk.Button(label='清零')
        self.reset.connect('clicked', self.clear_draft)
        grid.attach(self.reset, 1, 1, 1, 1)
        area.pack_start(grid, False, False, 0)
        self.readout = Gtk.Label(xalign=0)
        self.message = Gtk.Label(label='单位：mm（10 mm = 1 cm）；每方向最大100 mm。', xalign=0)
        self.message.set_line_wrap(True)
        area.pack_start(self.readout, False, False, 0)
        area.pack_start(self.message, False, False, 0)
        for response in (Gtk.ResponseType.OK, Gtk.ResponseType.CANCEL):
            self.get_widget_for_response(response).set_size_request(130, 48)
        self.refresh()
        self.show_all()

    @staticmethod
    def summary(values):
        right, up = checked_pick_offset(values)
        return '%s %g mm · %s %g mm' % ('右' if right >= 0 else '左', abs(right),
                                       '上' if up >= 0 else '下', abs(up))

    def refresh(self):
        set_status_text(self.readout, '当前草稿：' + self.summary(self.values))

    def nudge(self, right, up):
        step = int(self.step.get_active_id())
        try:
            values = checked_pick_offset((self.values[0]+right*step, self.values[1]+up*step))
        except ValueError as error:
            set_status_text(self.message, str(error))
            return
        self.values = values
        set_status_text(self.message, '点击“应用”后生效；此操作不移动机械臂。')
        self.refresh()

    def clear_draft(self, *_):
        self.values = (0.0, 0.0)
        set_status_text(self.message, '点击“应用”恢复当前标定的原位置。')
        self.refresh()


class GraspPreviewPanel:
    def __init__(self, owner, hardware, leave, stop):
        self.owner, self.hardware, self.leave, self.stop_motors = owner, hardware, leave, stop
        self.closed = self.syncing = self.paused = False
        self.run_active = False
        self.drive_stage = False
        self.start_ready = False
        self.start_sent = False
        self.reset_pending = False
        self.reset_epoch = 0
        self.shelf_tasks = None
        self.run_control = None
        self.run_epoch = 0
        self.plan = None
        self.offset_dialog = None
        owner._temporary_grasp_offset_mm = checked_pick_offset(getattr(owner, '_temporary_grasp_offset_mm', None))
        self.animation = None
        self.target_index = self.phase_index = self.completed = 0
        self._last_telemetry = None
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.widget.set_border_width(16)
        self.widget.get_style_context().add_class('grasp-preview-root')
        compact = Gdk.Screen.get_default().get_height() < 900
        if compact:
            self.widget.get_style_context().add_class('grasp-preview-compact')
        provider = Gtk.CssProvider()
        provider.load_from_data(b'''
          .grasp-preview-root {font-size:18px; color:#52647e; background:#f3f5f8;}
          .grasp-preview-root button {font-size:18px; min-height:56px; padding:6px 12px;}
          .grasp-preview-root checkbutton {min-height:56px; font-size:20px;}
          .grasp-preview-root spinbutton {font-size:20px; min-height:48px;}
          .grasp-preview-root spinbutton button {min-height:56px; min-width:56px; padding:0;}
          .grasp-preview-root .grasp-preview-card {background:#ffffff; border-radius:12px; padding:12px;}
          .grasp-preview-root .grasp-preview-main {min-height:72px;}
          .grasp-preview-root.grasp-preview-compact button {min-height:44px;}
          .grasp-preview-root.grasp-preview-compact .grasp-preview-main {min-height:48px;}
        ''')
        self.widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+2)
        # Descendant selectors need a screen provider to cover child widgets.
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+2)
        header = Gtk.Box(spacing=16)
        header.pack_start(self.label('货架取货'), True, True, 0)
        self.exit_button = self.button('返回主界面', self._leave)
        self.exit_button.set_size_request(180, 56 if compact else 64)
        header.pack_end(self.exit_button, False, False, 0)
        self.widget.pack_start(header, False, False, 0)
        intro = self.label('AI六类取放：Y220 → 伸入Y330 → 缩回Y220 → 对应投放箱；关节60°/秒，线速度200mm/秒；全部完成后回0。')
        intro.set_line_wrap(True)
        intro.set_max_width_chars(90)
        body = Gtk.Box(spacing=16)
        self.widget.pack_start(body, True, True, 0)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.pack_start(left, True, True, 0)
        camera_header = Gtk.Box(spacing=12)
        camera_header.pack_start(self.label('取料画面'), True, True, 0)
        self.camera_button = self.button('开始AI识别', lambda *_: self.hardware.start())
        camera_header.pack_end(self.camera_button, False, False, 0)
        left.pack_start(camera_header, False, False, 0)
        self.preview = Gtk.EventBox()
        self.preview.set_visible_window(True)
        self.preview.get_style_context().add_class('vision-preview')
        self.preview.set_size_request(384, 216)
        self.preview.set_hexpand(True)
        self.preview.set_vexpand(True)
        left.pack_start(self.preview, True, True, 0)
        self.live_status = self.label('等待AI识别')
        self.live_status.set_ellipsize(3)
        left.pack_start(self.live_status, False, False, 0)
        self.box_labels = []
        boxes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for number, color in enumerate(COLORS, 1):
            box = BOX_LAYOUT['boxes'][color]
            label = self.label('%d · %s盒（车体%s）\n盒口 X%.1f Y%.0f Z%.0f' % (number, NAMES[color][0], ('左','中','右')[number-1], *box['center_xy_mm'], box['rim_z_mm']))
            label.set_line_wrap(True)
            boxes.pack_start(label, True, True, 0)
            self.box_labels.append(label)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_size_request(420, -1)
        right.get_style_context().add_class('grasp-preview-card')
        self.task_scroll = Gtk.ScrolledWindow()
        self.task_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.task_scroll.set_overlay_scrolling(False)
        self.task_scroll.set_min_content_height(180)
        self.task_scroll.add(right)
        body.pack_start(self.task_scroll, False, False, 0)
        self.shelf_button = self.button('货架任务设置', self.configure_shelves)
        self.shelf_button.set_tooltip_text('只在这里设置各货架的物品与数量；0 表示不取')
        right.pack_start(self.shelf_button, False, False, 0)
        self.shelf_summary = self.label('请设置各货架物品与数量')
        self.shelf_summary.set_line_wrap(True)
        self.shelf_summary.set_max_width_chars(32)
        right.pack_start(self.shelf_summary, False, False, 0)
        self.offset_button = self.button('临时偏置', self.configure_offset)
        self.offset_button.set_tooltip_text('只调整取料位置；停止任务后可修改，重启界面清零')
        right.pack_start(self.offset_button, False, False, 0)
        self.offset_summary = self.label('临时偏置：' + GraspOffsetDialog.summary(self.pick_offset))
        self.offset_summary.set_line_wrap(True)
        right.pack_start(self.offset_summary, False, False, 0)
        right.pack_start(self.label('已完成 / 总数量'), False, False, 0)
        self.count_labels = {}
        totals = Gtk.Grid(column_spacing=12, row_spacing=6)
        for number, item in enumerate(PICK_ITEMS):
            row, column = number//2, (number%2)*2
            totals.attach(self.label(PICK_LABELS[item]), column, row, 1, 1)
            self.count_labels[item] = self.label('0 / 0')
            totals.attach(self.count_labels[item], column+1, row, 1, 1)
        right.pack_start(totals, False, False, 0)
        self.safety = Gtk.CheckButton(label='确认运动区域安全')
        self.safety.set_active(bool(getattr(owner, 'safety', None) and owner.safety.get_active()))
        self.safety.connect('toggled', self._safety_changed)
        self.safety_handler = owner.safety.connect('toggled', self._owner_safety_changed) if hasattr(owner, 'safety') else None
        right.pack_start(self.safety, False, False, 0)
        note = self.label('任务复位不移动机械臂、不修改零位。')
        note.set_line_wrap(True)
        note.set_max_width_chars(32)
        right.pack_start(note, False, False, 0)
        self.details_expander = Gtk.Expander(label='参数与路径')
        self.details_expander.set_size_request(-1, 48)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.details_expander.add(details)
        right.pack_start(self.details_expander, False, False, 0)
        details.pack_start(self.label('六类AI · 单帧确认 · 置信度0.30'), False, False, 0)
        intro.set_max_width_chars(32)
        details.pack_start(intro, False, False, 0)
        details.pack_start(boxes, False, False, 0)
        mapping = self.label('苹果→左箱 · 橘子→右箱 · 香蕉→中箱')
        mapping.set_line_wrap(True)
        details.pack_start(mapping, False, False, 0)
        self.current = self.label('等待生成定位路径')
        self.current.set_line_wrap(True)
        self.current.set_max_width_chars(32)
        details.pack_start(self.current, False, False, 0)
        self.route_labels = []
        for caption in ('预备点', '前伸定位点', '缩回点'):
            label = self.label(caption + ' / —')
            label.set_line_wrap(True)
            label.set_max_width_chars(34)
            details.pack_start(label, False, False, 0)
            self.route_labels.append(label)
        self.progress = self.label('取料向画面左侧偏置60mm；Z无额外偏置，终点确认到位')
        self.progress.set_line_wrap(True)
        self.progress.set_max_width_chars(34)
        details.pack_start(self.progress, False, False, 0)
        self.future_note = self.label('盒点来自小车模型；朝下放盒时按100mm前伸、下偏10mm换算轴端。夹爪末端停在盒口上方10mm。')
        self.future_note.set_line_wrap(True)
        self.future_note.set_max_width_chars(34)
        details.pack_start(self.future_note, False, False, 0)
        self.status = self.label('设置货架 → 开始识别 → 准备任务 → 启动')
        self.status.set_line_wrap(True)
        self.status.set_max_width_chars(100)
        self.widget.pack_start(self.status, False, False, 0)
        actions = Gtk.Box(spacing=14)
        self.plan_button = self.button('坐标路径预览', self.start_preview)
        self.run_button = self.button('准备任务', self.start_run)
        self.start_button = self.button('启动任务', self.start_task)
        self.reset_button = self.button('任务复位', self.reset_task)
        self.stop_button = self.button('■ 停止全部', self.stop)
        self.stop_button.get_style_context().add_class('vision-stop')
        for button in (self.plan_button, self.run_button, self.start_button, self.stop_button, self.reset_button):
            button.get_style_context().add_class('grasp-preview-main')
            actions.pack_start(button, True, True, 0)
            button.set_size_request(-1, 56)
        self.widget.pack_start(actions, False, False, 0)
        if hasattr(owner, '_numeric_keyboard'):
            owner._numeric_keyboard.bind_tree(self.widget)
        self.widget.connect('destroy', lambda *_: self.close())
        self.timer = GLib.timeout_add(200, self._tick)
        self._buttons()

    @staticmethod
    def label(text):
        return Gtk.Label(label=text, xalign=0)

    @staticmethod
    def button(text, callback):
        button = Gtk.Button(label=text)
        button.connect('clicked', callback)
        return button

    @property
    def busy(self):
        return self.run_active or self.animation is not None or self.paused or self.reset_pending

    def requested(self):
        return {item: sum(row.get(item, 0) for row in (self.shelf_tasks or [])) for item in PICK_ITEMS}

    @property
    def pick_offset(self):
        return checked_pick_offset(getattr(self.owner, '_temporary_grasp_offset_mm', None))

    def offset_editable(self):
        controller = getattr(self.owner, 'controller', None)
        task = getattr(controller, 'motion_task', None)
        return (not self.closed and not self.busy and task is not None and not task.busy
                and not getattr(controller, '_moving', None)
                and not getattr(self.owner, '_initializing_zero', False)
                and not getattr(self.owner, '_powering_off', False)
                and not getattr(getattr(self.owner, 'joint_pages', None), 'record_pending', False))

    def apply_pick_offset(self, values):
        values = checked_pick_offset(values)
        if not self.offset_editable():
            raise RuntimeError('请先停止任务，等待机械臂空闲后再调整偏置')
        self.owner._temporary_grasp_offset_mm = values
        self.plan = None
        set_status_text(self.offset_summary, '临时偏置：' + GraspOffsetDialog.summary(values))
        set_status_text(self.current, '偏置已更新，请重新生成定位路径')
        for caption, label in zip(('预备点', '前伸定位点', '缩回点'), self.route_labels):
            set_status_text(label, caption + ' / —')
        set_status_text(self.status, '临时偏置已应用：' + GraspOffsetDialog.summary(values))

    def configure_offset(self, *_):
        if not self.offset_editable() or self.offset_dialog is not None:
            return
        dialog = GraspOffsetDialog(self.owner, self.pick_offset)
        self.offset_dialog = dialog
        try:
            if dialog.run() == Gtk.ResponseType.OK:
                try:
                    self.apply_pick_offset(dialog.values)
                except (ValueError, RuntimeError) as error:
                    set_status_text(self.status, str(error))
        finally:
            self.offset_dialog = None
            dialog.destroy()
        self._buttons()

    def configure_shelves(self, *_):
        if self.busy:
            return
        from .gtk_shelf_config import ShelfConfigDialog
        dialog = ShelfConfigDialog(self.owner, self.shelf_tasks)
        try:
            if dialog.run() == Gtk.ResponseType.OK:
                try:
                    self.shelf_tasks = dialog.selected_shelves()
                    self._shelves_changed()
                    set_status_text(self.status, '货架已设置，可准备任务。')
                except ValueError as error:
                    set_status_text(self.status, str(error))
        finally:
            dialog.destroy()


    def _shelves_changed(self):
        self.plan = None
        lines = []
        for index, row in enumerate(self.shelf_tasks or []):
            items = '、'.join('%s%d' % (PICK_LABELS[item], row.get(item, 0))
                             for item in PICK_ITEMS if row.get(item, 0))
            lines.append('货架%d：%s' % (index+1, items or '跳过'))
        set_status_text(self.shelf_summary, '\n'.join(lines) or '请设置各货架物品与数量')
        for item, count in self.requested().items():
            set_status_text(self.count_labels[item], '0 / %d' % count)
        set_status_text(self.current, '货架任务已更新')
        self._buttons()

    def start_preview(self, *_):
        if self.busy:
            return
        try:
            if getattr(self.hardware.session, 'stopping', False):
                raise ValueError('识别正在结束，请等待后重新开始AI识别')
            if not self.hardware.session.running:
                raise ValueError('请先开始AI识别')
            from .shelf_executor import validate_shelf_items
            shelves = validate_shelf_items(self.shelf_tasks)
            station = next(i for i, row in enumerate(shelves) if any(row.values()))
            plan = preview_plan(self.hardware.session.telemetry, shelves[station], time.monotonic(),
                                expected_session_id=getattr(self.hardware.session, 'session_id', None),
                                pick_offset_mm=self.pick_offset)
        except (ValueError, TypeError) as error:
            set_status_text(self.status, str(error))
            return
        self.plan = plan
        self.target_index = self.phase_index = self.completed = 0
        self.paused = False
        for color in PICK_ITEMS:
            set_status_text(self.count_labels[color], '0 / %d' % plan['requested'][color])
        set_status_text(self.status, '仅预览当前画面中的货架%d目标坐标；不驱动电机。' % (station+1))
        self._show_route()
        self.animation = GLib.timeout_add(1000, self._advance)
        self._buttons()

    def _safety_changed(self, check):
        if hasattr(self.owner, 'safety') and self.owner.safety.get_active() != check.get_active():
            self.owner.safety.set_active(check.get_active())

    def _owner_safety_changed(self, check):
        if self.safety.get_active() != check.get_active():
            self.safety.set_active(check.get_active())
        if self.run_active and not check.get_active():
            self.stop()

    def start_run(self, *_):
        if self.busy:
            return
        try:
            if self.shelf_tasks is None:
                raise RuntimeError('请先设置货架物品及数量')
            if not self.safety.get_active():
                raise RuntimeError('请先勾选确认运动区域安全')
            if getattr(self.owner, '_initializing_zero', False) or getattr(self.owner, '_powering_off', False) or getattr(getattr(self.owner, 'joint_pages', None), 'record_pending', False):
                raise RuntimeError('请等待当前操作结束')
            task = self.owner.controller.motion_task
            if task.busy:
                raise RuntimeError('请等待当前运动任务结束')
            task.cartesian.require()
            if getattr(self.hardware.session, 'stopping', False):
                raise RuntimeError('识别正在结束，请等待后重新开始AI识别')
            if not self.hardware.session.running:
                raise RuntimeError('请先开始识别')
            from .shelf_executor import validate_shelf_items
            self.shelf_tasks = validate_shelf_items(self.shelf_tasks)
            requested = self.requested()
            plan = dict(requested=quantities(requested))
            self.plan = plan
            self.run_control = RunControl()
            self.run_epoch += 1
            epoch = self.run_epoch
            self.run_active = True
            self.start_ready = self.start_sent = False
            self.paused = False
            self.completed = 0
            for color in PICK_ITEMS:
                set_status_text(self.count_labels[color], '0 / %d' % plan['requested'][color])
            self.gripper_enabled = True
            self.drive_stage = True
            set_status_text(self.status, '正在准备货架任务；准备成功后点“启动任务”。')
            def progress(event):
                GLib.idle_add(self._apply_progress, epoch, event)
            def finished(ok, error):
                GLib.idle_add(self._run_finished, epoch, ok, error)
            task.start('shelf_grasp_execute', finished, session=self.hardware.session,
                       requested=plan['requested'], control=self.run_control, progress=progress,
                       clearance_confirmed=self.safety.get_active(), use_gripper=self.gripper_enabled,
                       shelves=self.shelf_tasks,touch_start_enabled=True,pick_offset_mm=self.pick_offset)
        except (ValueError, RuntimeError, AttributeError) as error:
            self.run_active = False
            set_status_text(self.status, str(error))
        self._buttons()

    def _can_start(self):
        session = self.hardware.session
        return (self.run_active and self.start_ready and not self.start_sent
                and self.run_control is not None and self.run_control.start_ready
                and not self.run_control.stopped.is_set() and not self.reset_pending
                and self.safety.get_active() and session.running
                and not getattr(session, 'stopping', False))

    def start_task(self, *_):
        if not self._can_start():
            set_status_text(self.status, '任务尚未准备好，或启动请求已发出；请检查任务状态。')
            return
        if self.run_control.request_start():
            self.start_sent = True
            self.start_ready = False
            set_status_text(self.status, '已请求启动当前货架任务，等待控制服务确认。')
        else:
            set_status_text(self.status, '当前任务状态已变化，启动请求未发送。')
        self._buttons()

    def reset_task(self, *_):
        if getattr(self.owner, '_simulation_mode', False):
            set_status_text(self.status, '仿真模式不连接小车控制服务。')
            return
        task = getattr(getattr(self.owner, 'controller', None), 'motion_task', None)
        if self.busy or task is None or task.busy:
            set_status_text(self.status, '请先停止任务，等待任务结束后再复位。')
            return
        if getattr(self.owner, '_initializing_zero', False) or getattr(self.owner, '_powering_off', False):
            set_status_text(self.status, '请等待当前操作结束后再复位。')
            return
        self.reset_pending = True
        self.reset_epoch += 1
        epoch = self.reset_epoch
        set_status_text(self.status, '正在复位小车任务状态；机械臂不移动。')
        self._buttons()
        def worker():
            result, error = None, ''
            try:
                from .shelf.task_controls import reset_task
                result = reset_task()
                if not isinstance(result, dict) or result.get('phase') != 'READY' or result.get('reset_done') is not True:
                    raise RuntimeError('缺少有效的任务复位回执')
            except Exception as exc:
                error = str(exc)
            GLib.idle_add(self._reset_finished, epoch, error)
        threading.Thread(target=worker, name='shelf-task-reset', daemon=True).start()

    def _reset_finished(self, epoch, error):
        self.reset_pending = False
        if self.closed or epoch != self.reset_epoch:
            if not self.closed:
                self._buttons()
            return False
        self.start_ready = self.start_sent = False
        self.plan = None
        self._shelves_changed()
        set_status_text(self.status, '任务复位失败：'+error if error else '任务已复位到待机；货架选择保留，请重新准备。')
        self._buttons()
        return False

    def _apply_progress(self, epoch, event):
        if self.closed or epoch != self.run_epoch or not self.run_active:
            return False
        if 'start_ready' in event:
            self.start_ready = event['start_ready'] is True
        if event.get('mission_stage') == 'grasp':
            self.drive_stage = False
            self._buttons()
        self.completed = sum(event['completed'].values())
        for color in PICK_ITEMS:
            set_status_text(self.count_labels[color], '%d / %d' % (event['completed'][color],event['requested'][color]))
        target = event.get('target')
        if target:
            set_status_text(self.current, '%s #%s / 实际取放定位' % (PICK_LABELS[target['color']],target['track_id']))
            from .grasp_preview import axis_route
            for label, step in zip(self.route_labels, axis_route(target['endpoint_xyz_mm'])):
                set_status_text(label, '%s / X%.1f Y%.1f Z%.1f' % (step['label'],*step['xyz_mm']))
        set_status_text(self.progress, event['label'])
        message = event['label']
        for detailed, simple in (
                ('准备四段高速路径；取料向画面左侧偏置60mm，Z无补偿', '正在准备夹取'),
                ('快速点到点 Y220', '前往取料区'), ('前伸定位 Y330', '伸入取料'),
                ('缩回 Y220', '收回机械臂'), ('取料前确认夹爪张开状态', '准备夹爪'),
                ('取料点闭合夹爪，稳定1秒后持续保持至投放', '夹爪闭合并保持'),
                ('盒口上方张开夹爪并等待1秒', '张开放料（1秒）')):
            message = message.replace(detailed, simple)
        set_status_text(self.status, '已完成%d件 · %s' % (self.completed, message))
        self._buttons()
        return False

    def _run_finished(self, epoch, ok, error):
        if self.closed or epoch != self.run_epoch:
            return False
        self.run_active = False
        self.start_ready = self.start_sent = False
        set_status_text(self.status, '取放命令完成并已回0；实际抓取结果请核对。' if ok else '实际取放已结束：'+error)
        self._buttons()
        return False

    def _show_route(self):
        target = self.plan['targets'][self.target_index]
        set_status_text(self.current, '%s #%s / 同类从左到右第%d个' % (PICK_LABELS[target['color']], target['track_id'] if target['track_id'] is not None else '—', target['same_color_order']))
        for index, (label, step) in enumerate(zip(self.route_labels, target['route'])):
            set_status_text(label, ('%s %s / X %.1f  Y %.1f  Z %.1f mm' % ('▶' if index == self.phase_index else ' ', step['label'], *step['xyz_mm'])))
        set_status_text(self.progress, '预览 %d / %d · 姿态保持，前伸110mm再缩回110mm' % (self.completed, len(self.plan['targets'])))

    def _advance(self):
        if self.closed or self.plan is None:
            self.animation = None
            return False
        if self.phase_index < 2:
            self.phase_index += 1
        else:
            self.completed += 1
            completed_targets = self.plan['targets'][:self.completed]
            for color in PICK_ITEMS:
                set_status_text(self.count_labels[color], '%d / %d' % (sum(t['color'] == color for t in completed_targets), self.plan['requested'][color]))
            if self.completed == len(self.plan['targets']):
                self.animation = None
                set_status_text(self.progress, '已预览 %d 个目标；电机与夹爪均未动作' % self.completed)
                missing = '；缺少' + '、'.join('%s%d个' % (PICK_LABELS[color], number) for color, number in self.plan['missing'].items()) if self.plan['missing'] else ''
                set_status_text(self.status, '轴端定位路径预览完成' + missing + '。需要执行时先准备任务，再点启动。')
                self._buttons()
                return False
            self.target_index += 1
            self.phase_index = 0
        self._show_route()
        return True

    def suspend(self):
        if self.run_active:
            self.run_control.cancel()
            self.owner.controller.motion_task.cancel()
            self.start_ready = False
            set_status_text(self.status, '离开取货页面已取消当前任务；返回后需重新准备。')
        if self.animation is not None:
            GLib.source_remove(self.animation)
            self.animation = None
        self.paused = False
        self._buttons()

    def stop(self, *_):
        self.reset_epoch += 1
        self.start_ready = False
        self.suspend()
        if self.run_active:
            self.run_control.cancel()
            self.owner.controller.motion_task.cancel()
        set_status_text(self.status, '已请求停止全部；等待运动控制器确认停止。')
        self.stop_motors()

    def _leave(self, *_):
        self.suspend()
        self.leave()

    def _buttons(self):
        if self.closed:
            return
        task = getattr(getattr(self.owner, 'controller', None), 'motion_task', None)
        idle = not self.busy and task is not None and not task.busy
        has_shelves = bool(self.shelf_tasks and any(any(row.values()) for row in self.shelf_tasks))
        for button, enabled in ((self.plan_button, idle and has_shelves),
                (self.run_button, idle and has_shelves), (self.start_button, self._can_start()),
                (self.reset_button, idle), (self.safety, not self.busy),
                (self.shelf_button, idle),
                (self.offset_button, self.offset_editable()),
                (self.camera_button, not self.busy and not self.hardware.session.running)):
            if button.get_sensitive() != enabled:
                button.set_sensitive(enabled)

    def _tick(self):
        if self.closed:
            return False
        if not self.widget.get_mapped():
            return True
        session = self.hardware.session
        self._buttons()
        value = session.telemetry
        if not session.running:
            text = '识别失败：'+session.error if getattr(session, 'error', '') else '识别已停止 · 点击开始识别'
        elif not isinstance(value, dict) or value.get('state') == 'loading':
            text = '等待本次AI识别结果'
        elif value.get('state') == 'failed':
            text = '识别失败：'+str(value.get('error', '请重新开始识别'))
        else:
            try:
                groups = fresh_targets(value, time.monotonic(), expected_session_id=session.session_id)
                text = 'AI目标：' + ' / '.join('%s%d' % (PICK_LABELS[item], len(groups[item])) for item in PICK_ITEMS)
            except (ValueError, TypeError) as error:
                text = str(error)
        if self.live_status.get_text() != text:
            set_status_text(self.live_status, text)
        return True

    def close(self):
        if self.closed:
            return
        if self.offset_dialog is not None:
            self.offset_dialog.response(Gtk.ResponseType.CANCEL)
        if self.run_active:
            self.stop()
        self.suspend()
        self.run_epoch += 1
        self.closed = True
        if self.safety_handler is not None:
            self.owner.safety.disconnect(self.safety_handler)
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
