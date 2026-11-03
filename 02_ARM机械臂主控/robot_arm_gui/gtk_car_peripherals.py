"""Touch status panel for the integrated physical key/OLED console."""
from gi.repository import GLib, Gtk
from .car_peripherals import read_status, request_stop
from pathlib import Path
from .gtk_touch import set_status_text


class CarPeripheralWindow(Gtk.Window):
    def __init__(self, owner):
        super().__init__(title='小车与夹爪')
        self.set_transient_for(owner)
        self.set_default_size(860, 620)
        self.simulation = owner._simulation_mode
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        body.set_border_width(24)
        self.add(body)
        self.status = Gtk.Label(xalign=0)
        self.status.set_line_wrap(True)
        body.pack_start(self.status, False, False, 0)
        details = Gtk.Expander(label='运行详情与按键说明')
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.details = Gtk.Label(xalign=0)
        self.details.set_line_wrap(True)
        detail_box.pack_start(self.details, False, False, 0)
        self.hints = []
        for text in (
            'KEY1：切换 PID / GRIP；切换时停止输出',
            'PID：KEY2 启动车轮；KEY3 切换目标10/20/30；KEY4 停止',
            'GRIP：KEY2 张开；KEY3 闭合并持续保持；KEY4停止',
            '自动夹取占用期间：小车停止、KEY1～3锁定；KEY4中止整项任务',
            '夹爪脉宽与等待时间以当前服务为准；OLED可选'):
            label = Gtk.Label(label=text, xalign=0)
            label.set_line_wrap(True)
            detail_box.pack_start(label, False, False, 0)
            self.hints.append(label)
        details.add(detail_box)
        body.pack_start(details, False, False, 0)
        note = Gtk.Label(label='启动与复位请到全自动夹取页。KEY4 或下方按钮停止全部。', xalign=0)
        note.set_line_wrap(True)
        body.pack_start(note, False, False, 0)
        stop = Gtk.Button(label='■ 停止小车和夹爪')
        stop.set_size_request(-1, 72)
        stop.get_style_context().add_class('stop')
        stop.connect('clicked', lambda *_: None if self.simulation else request_stop())
        body.pack_start(stop, False, False, 0)
        close = Gtk.Button(label='关闭窗口')
        close.set_size_request(-1, 64)
        close.connect('clicked', lambda *_: self.hide())
        body.pack_start(close, False, False, 0)
        self.connect('delete-event', lambda *_: self.hide() or True)
        self.timer = GLib.timeout_add(300, self.update_status)
        self.connect('destroy', self._destroy)
        self.connect('map', lambda *_: self.update_status())
        self.update_status()

    def update_status(self):
        if getattr(self, '_status_initialized', False) and not self.get_visible():
            return True
        self._status_initialized = True
        detail = ''
        if self.simulation:
            text = '仿真模式 · 外设未连接'
        else:
            value = read_status()
            if value.get('available') is False:
                text = '外设服务未就绪：'+value.get('error', '')
            elif value.get('version', '').startswith(('drive174-current','shelf-package-car')):
                for label, caption in zip(self.hints, (
                    '全自动夹取页：设置各货架物品数量，准备后点击启动',
                    'KEY1：空闲重置；KEY2：补偿+0.25%；KEY3：补偿-0.25%（停车后调整）；KEY4：停止全部',
                    '只在选中货架停稳后取货；任务复位只回到小车待机，不让机械臂回零',
                    '车轮与夹爪互锁；准备前检查识别、机械臂零点和通信',
                    '夹爪闭合1880μs并持续保持；OLED可选；未就绪时检查连接')):
                    set_status_text(label, caption)
                drive = read_status(Path('/run/f3p-drive174-grasp-status.json'))
                if drive.get('available') is False:
                    text = '行驶状态不可用：' + drive.get('error', '')
                else:
                    phase = dict(READY='已准备，等待启动' if drive.get('armed') else '待机',
                                 RUN='行驶', WAIT='等待停稳', DONE='夹取阶段', STOP='停止', FAULT='故障')
                    text = '任务完成' if drive.get('complete') else phase.get(drive.get('phase'), '状态未知')
                    faults = [('车轮', drive.get('fault')), ('夹爪', drive.get('grip_fault'))]
                    text += ''.join(' · %s故障 F%s' % (name, code) for name, code in faults if code != 0)
                    if not drive.get('imu_ready'):
                        text += '\nIMU未就绪'
                    detail = ('小车取货任务：%s · 车轮F=%s / 夹爪F=%s\n'
                            '左右距离mm：%s · PWM：%s\nOLED：%s · IMU：%s\n'
                            '距离标定：%s' % (
                        '任务完成' if drive.get('complete') else phase.get(drive.get('phase'), '未知'),
                        drive.get('fault'), drive.get('grip_fault'), drive.get('mm_lr'), drive.get('pwm_lr'),
                        '正常' if drive.get('oled_ready') else '未连接或不可用（可选）',
                        '正常' if drive.get('imu_ready') else '未就绪',
                        '已标定' if drive.get('distance_calibrated') else '待实车标定'))
                    if 'right_trim_percent' in drive:
                        text += ' · 右轮补偿 %+.2f%%' % drive['right_trim_percent']
                    if 'grip_open_wait_ms' in drive:
                        detail += '\n张开等待：%g秒' % (drive['grip_open_wait_ms']/1000.)
            else:
                text = ('车轮' if value.get('mode')==1 else '夹爪') + ('运行中' if value.get('running') else '待机')
                if value.get('fault') != 0:
                    text += ' · 故障 F%s' % value.get('fault')
                detail = ('模式：%s · %s · 故障F=%s\nOLED：%s · 自动任务占用：%s\n'
                        '左右速度（计数/10ms）：%s\n左右PWM：%s · 夹爪：%sμs · PWM：%s' % (
                    'PID' if value.get('mode')==1 else 'GRIP',
                    '运行' if value.get('running') else '停止', value.get('fault'),
                    '正常' if value.get('oled_ready') else '未连接或不可用（可选）',
                    '是' if value.get('remote_active') else '否',
                    value.get('speed'), value.get('pwm'), value.get('grip_command_us'),
                    '持续输出' if value.get('grip_output_enabled') else
                    '停止' if 'grip_output_enabled' in value else '待服务报告'))
        set_status_text(self.status, text)
        set_status_text(self.details, detail)
        return True

    def _destroy(self, *_):
        GLib.source_remove(self.timer)
