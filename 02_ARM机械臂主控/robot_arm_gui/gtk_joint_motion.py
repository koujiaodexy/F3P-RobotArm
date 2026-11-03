"""GTK joint positioning and teaching pages sharing the main controller."""
from gi.repository import Gtk
from .zero_home import RATIOS
from .joint_motion import motor_pulses_from_settings, parse_motor_pulses
from .gtk_joint_panels import JointPages
from .gtk_touch import set_status_text


def label(text):
    return Gtk.Label(label=text, xalign=0)


class PositionConfigDialog(Gtk.Dialog):
    """Explain and validate live positioning scale before a save is offered."""
    def __init__(self, window, scales):
        super().__init__(title='定位参数 · 电机每圈脉冲数', transient_for=window, modal=True)
        self.get_style_context().add_class('position-config-dialog')
        self.set_default_size(860, 560)
        self.add_buttons('取消', Gtk.ResponseType.CANCEL, '保存已核对参数', Gtk.ResponseType.OK)
        self.save_button = self.get_widget_for_response(Gtk.ResponseType.OK)
        box = self.get_content_area()
        box.set_spacing(10)
        box.set_border_width(16)
        explanation = label('填写各电机每圈脉冲数；减速比已由程序处理。保存前请核对驱动设置。')
        explanation.set_line_wrap(True)
        box.pack_start(explanation, False, False, 0)
        grid = Gtk.Grid(column_spacing=20, row_spacing=8)
        for column, text in enumerate(('关节', '电机脉冲 / 圈', '已配置减速比')):
            grid.attach(label(text), column, 0, 1, 1)
        self.entries = {}
        for n in range(1, 7):
            grid.attach(label(f'J{n}'), 0, n, 1, 1)
            entry = Gtk.Entry()
            entry.set_width_chars(16)
            entry.set_max_length(7)
            entry.set_placeholder_text('请核对驱动设置')
            entry.set_input_purpose(Gtk.InputPurpose.DIGITS)
            entry.set_text(str(scales.get(n, '')))
            grid.attach(entry, 1, n, 1, 1)
            grid.attach(label(f'{RATIOS[n]:.6g}（程序已处理）'), 2, n, 1, 1)
            self.entries[n] = entry
        box.pack_start(grid, False, False, 0)
        calculator = Gtk.Expander(label='脉冲数计算与参数说明')
        helper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        example = label('每圈脉冲数 = 360 ÷ 步距角 × 细分。例：1.8°、16细分为3200脉冲。\n定位按此换算脉冲；回零目标为0，角度反馈限位不使用此换算。')
        example.set_line_wrap(True)
        helper.pack_start(example, False, False, 0)
        row = Gtk.Box(spacing=8)
        self.calc_node = Gtk.ComboBoxText()
        for n in range(1, 7): self.calc_node.append_text(f'J{n}')
        self.calc_node.set_active(0)
        row.pack_start(self.calc_node, False, False, 0)
        row.pack_start(label('电机步距角'), False, False, 0)
        self.step_angle = Gtk.ComboBoxText()
        for text in ('请选择', '1.8°', '0.9°'): self.step_angle.append_text(text)
        self.step_angle.set_active(0)
        row.pack_start(self.step_angle, False, False, 0)
        row.pack_start(label('驱动细分'), False, False, 0)
        self.microsteps = Gtk.Entry()
        self.microsteps.set_width_chars(6)
        self.microsteps.set_max_length(3)
        self.microsteps.set_placeholder_text('例如16')
        self.microsteps.set_input_purpose(Gtk.InputPurpose.DIGITS)
        row.pack_start(self.microsteps, False, False, 0)
        self.apply_calculation = Gtk.Button(label='填入所选关节')
        self.apply_calculation.connect('clicked', self._apply_calculation)
        row.pack_start(self.apply_calculation, False, False, 0)
        helper.pack_start(row, False, False, 0)
        self.calculation_label = label('')
        helper.pack_start(self.calculation_label, False, False, 0)
        note = label('计算助手只适用于没有额外位置缩放的普通输入脉冲配置。\n'
            '请以实际驱动设置为准；计算结果只填入所选行，不自动复制到其他关节。')
        note.set_line_wrap(True)
        helper.pack_start(note, False, False, 0)
        calculator.add(helper)
        box.pack_start(calculator, False, False, 0)
        self.confirmed = Gtk.CheckButton(label='我已逐轴核对实际驱动设置、有效脉冲数与运动正方向')
        box.pack_start(self.confirmed, False, False, 0)
        self.validation = label('')
        self.validation.set_line_wrap(True)
        box.pack_start(self.validation, False, False, 0)
        for entry in self.entries.values(): entry.connect('changed', self._input_changed)
        self.confirmed.connect('toggled', self._validate)
        self.step_angle.connect('changed', self._calculate)
        self.microsteps.connect('changed', self._calculate)
        self._validate()
        self._calculate()

    def values(self):
        # Preserve existing five-axis configurations; never guess J6's scale.
        return {n: parse_motor_pulses(entry.get_text(), n) for n,entry in self.entries.items()
                if n != 6 or entry.get_text().strip()}

    def _input_changed(self, *_args):
        self.confirmed.set_active(False)
        self._validate()

    def _validate(self, *_args):
        try:
            self.values()
            valid = self.confirmed.get_active()
            suffix = ' · J6留空，仅J1～J5可定位' if 6 not in self.values() else ' · 六轴参数完整'
            message = ('可以保存' if valid else '请核对后勾选确认') + suffix
        except ValueError as exc:
            valid, message = False, str(exc)
        self.save_button.set_sensitive(valid)
        set_status_text(self.validation, message)

    def _calculated_value(self):
        selected = self.step_angle.get_active()
        if selected not in (1, 2):
            raise ValueError('请选择电机步距角，再填写实际驱动细分。')
        text = self.microsteps.get_text().strip()
        if not text.isdecimal():
            raise ValueError('请填写实际驱动细分，例如16。')
        step = (1.8, 0.9)[selected-1]
        return motor_pulses_from_settings(step, int(text))

    def _calculate(self, *_args):
        try:
            pulses = self._calculated_value()
            set_status_text(self.calculation_label, f'计算结果：{pulses} 脉冲/圈')
            self.apply_calculation.set_sensitive(True)
        except ValueError as exc:
            set_status_text(self.calculation_label, str(exc))
            self.apply_calculation.set_sensitive(False)

    def _apply_calculation(self, *_args):
        node = self.calc_node.get_active()+1
        self.entries[node].set_text(str(self._calculated_value()))
        self.confirmed.set_active(False)
