"""WAV testing and direct fixed-command control using the board's hard NPU."""
import json
import pathlib
import threading
import time
import tempfile
import wave
import shutil
from gi.repository import Gtk, GLib
from .local_voice import VoiceActions, recognize_wav
from .microphone import MicrophoneSession
from .gtk_touch import set_status_text


class LocalVoiceWindow(Gtk.Window):
    def __init__(self, parent):
        super().__init__(title='本地语音', transient_for=parent)
        self.set_default_size(780, 650)
        self.parent_control = parent
        self.closed = False
        self.recognizing = False
        self.generation = 0
        self.mic = None
        self.mic_token = 0
        self.mic_epoch = 0
        self.mic_contexts = {}
        self.mic_execute = False
        self.recordings = tempfile.TemporaryDirectory(prefix='f3p-mic-')
        self.last_recording = None
        self.mic_factory = MicrophoneSession
        self.actions = VoiceActions(parent, GLib.idle_add, GLib.timeout_add)
        self.connect('delete-event', self._hide)
        self.connect('destroy', self._destroy)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=16)
        self.add(box)
        self.source = Gtk.Label(label='本地语音 · 离线运行', xalign=0)
        self.source.get_style_context().add_class('good')
        self.source.set_line_wrap(True)
        box.pack_start(self.source, False, False, 0)
        note = Gtk.Label(label='“识别并执行”会直接启动动作。请保持运动区域安全。', xalign=0)
        note.set_line_wrap(True)
        box.pack_start(note, False, False, 0)
        row = Gtk.Box(spacing=8)
        self.test = Gtk.Button(label='选择 WAV · 仅识别')
        self.test.connect('clicked', lambda *_: self.choose_wav(False))
        self.run = Gtk.Button(label='选择 WAV · 识别并执行')
        self.run.connect('clicked', lambda *_: self.choose_wav(True))
        cancel = Gtk.Button(label='取消识别')
        cancel.connect('clicked', self.cancel)
        for b in (self.test, self.run, cancel):
            row.pack_start(b, False, False, 0)
        box.pack_start(row, False, False, 0)
        mic_row = Gtk.Box(spacing=8)
        self.mic_test = Gtk.Button(label='麦克风 · 仅识别')
        self.mic_run = Gtk.Button(label='麦克风 · 识别并执行')
        self.mic_stop = Gtk.Button(label='停止语音')
        self.mic_test.connect('clicked', lambda *_: self.start_microphone(False))
        self.mic_run.connect('clicked', lambda *_: self.start_microphone(True))
        self.mic_stop.connect('clicked', self.stop_listening)
        for b in (self.mic_test, self.mic_run, self.mic_stop):
            mic_row.pack_start(b, False, False, 0)
        box.pack_start(mic_row, False, False, 0)
        meter = Gtk.Box(spacing=8)
        self.mic_state = Gtk.Label(label='板载 MIC · 未启动', xalign=0)
        self.mic_state.set_width_chars(36)
        self.mic_state.set_ellipsize(3)
        self.mic_level = Gtk.LevelBar.new_for_interval(0, 80)
        self.mic_level.set_value(0)
        meter.pack_start(self.mic_state, False, False, 0)
        meter.pack_start(self.mic_level, True, True, 0)
        box.pack_start(meter, False, False, 0)
        bindings = Gtk.Expander(label='线路绑定 / 麦克风设置 / 指令表')
        self.bindings = bindings
        routes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        settings = Gtk.Box(spacing=8)
        settings.pack_start(Gtk.Label(label='MIC 增益（dB）'), False, False, 0)
        self.mic_gain = Gtk.SpinButton.new_with_range(0, 24, 3)
        self.mic_gain.set_value(18)
        settings.pack_start(self.mic_gain, False, False, 0)
        settings.pack_start(Gtk.Label(label='触发阈值（dBFS）'), False, False, 0)
        self.mic_threshold = Gtk.SpinButton.new_with_range(-65, -20, 1)
        self.mic_threshold.set_value(-45)
        settings.pack_start(self.mic_threshold, False, False, 0)
        routes.pack_start(settings, False, False, 0)
        actions = Gtk.Box(spacing=8)
        self.save_recording = Gtk.Button(label='保存最近录音')
        self.save_recording.connect('clicked', self.save_last_recording)
        commands = Gtk.Button(label='查看全部指令')
        commands.connect('clicked', self.show_commands)
        actions.pack_start(self.save_recording, False, False, 0)
        actions.pack_start(commands, False, False, 0)
        routes.pack_start(actions, False, False, 0)
        self.commands_details = Gtk.Expander(label='语音指令表')
        self.command_text = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        command_scroll = Gtk.ScrolledWindow()
        command_scroll.set_min_content_height(150)
        command_scroll.set_max_content_height(180)
        command_scroll.add(self.command_text)
        self.commands_details.add(command_scroll)
        routes.pack_start(self.commands_details, False, False, 0)
        self._commands_loaded = False
        self.route_labels = {}
        for slot in range(1, 6):
            line = Gtk.Box(spacing=8)
            b = Gtk.Button(label='绑定线路 ' + str(slot))
            b.connect('clicked', lambda _b, n=slot: self.choose_route(n))
            label = Gtk.Label(label=self.actions.bindings.get(str(slot), {}).get('name', '尚未绑定'), xalign=0)
            label.set_ellipsize(3)
            line.pack_start(b, False, False, 0)
            line.pack_start(label, True, True, 0)
            self.route_labels[slot] = label
            routes.pack_start(line, False, False, 0)
        label = Gtk.Label(label='低 / 中 / 高：关节 2 / 5 / 10 °/s，TCP 5 / 10 / 20 mm/s', xalign=0)
        label.set_line_wrap(True)
        routes.pack_start(label, False, False, 0)
        route_scroll = Gtk.ScrolledWindow()
        route_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        route_scroll.set_min_content_height(130)
        route_scroll.set_max_content_height(180)
        route_scroll.add(routes)
        bindings.add(route_scroll)
        box.pack_start(bindings, False, False, 0)
        self.history = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.history)
        scroll.set_min_content_height(130)
        self.history_details = Gtk.Expander(label='识别记录与技术详情')
        self.history_details.add(scroll)
        box.pack_start(self.history_details, True, True, 0)
        self.status = Gtk.Label(label='就绪', xalign=0)
        self.status.set_line_wrap(True)
        self.status.set_lines(2)
        self.status.set_ellipsize(3)
        box.pack_start(self.status, False, False, 0)
        stop = Gtk.Button(label='停止全部')
        stop.get_style_context().add_class('stop')
        stop.connect('clicked', self.stop)
        box.pack_start(stop, False, False, 0)
        from .gtk_touch import touch_window_header
        touch_window_header(self)
        self.refresh_inputs()

    def _hide(self, *_):
        self.stop_listening()
        self.hide()
        return True

    def _destroy(self, *_):
        self.closed = True
        self.stop_listening()

    def cancel(self, *_):
        self.generation += 1
        self.reset_microphone_epoch()
        self.actions.cancel(stop=self.actions.busy)
        set_status_text(self.status, '已取消待处理识别；正在运行的语音动作已请求停止' if self.actions.busy else '已取消待处理识别')

    def stop(self, *_):
        self.generation += 1
        self.reset_microphone_epoch()
        self.actions.cancel(stop=True)
        self.append('停止请求已提交；请以控制台停止反馈为准')

    def invalidate_from_stop(self):
        self.generation += 1
        self.reset_microphone_epoch()
        self.actions.cancel(stop=False)

    def reset_microphone_epoch(self):
        self.mic_epoch += 1
        self.mic_contexts.clear()
        if self.mic is not None:
            self.mic.reset_utterance()

    def refresh_inputs(self):
        ready = not self.recognizing and self.mic is None
        for b in (self.test, self.run, self.mic_test, self.mic_run):
            b.set_sensitive(ready)
        self.mic_stop.set_sensitive(self.mic is not None)
        self.mic_gain.set_sensitive(self.mic is None)
        self.mic_threshold.set_sensitive(self.mic is None)
        self.save_recording.set_sensitive(self.last_recording is not None)

    def start_microphone(self, execute=False):
        if self.mic is not None or self.recognizing or self.closed:
            return
        self.mic_token += 1
        token = self.mic_token
        self.mic_execute = execute
        self.reset_microphone_epoch()
        self.mic = self.mic_factory(lambda kind, value: GLib.idle_add(self.mic_event, token, kind, value),
            gain=self.mic_gain.get_value_as_int() // 3, floor_db=self.mic_threshold.get_value())
        set_status_text(self.mic_state, '正在打开板载 MIC…')
        self.refresh_inputs()
        self.append('麦克风监听启动 · ' + ('检查通过直接执行' if execute else '仅识别，不执行动作'))
        self.mic.start()

    def stop_listening(self, *_):
        mic = self.mic
        self.mic = None
        self.mic_token += 1
        if mic is not None:
            mic.stop()
        self.cancel()
        if not self.closed:
            set_status_text(self.mic_state, '板载 MIC · 已停止')
            self.refresh_inputs()

    def _vision_npu_busy(self):
        panel=getattr(getattr(self.parent_control,'vision_window',None),'coco_panel',None)
        return panel is not None and panel.session.running

    def mic_event(self, token, kind, value):
        if token != self.mic_token or self.closed or self.mic is None:
            return False
        if kind == 'level':
            now = time.monotonic()
            if not self.get_visible() or now-getattr(self, '_last_level_draw', 0.) < .2:
                return False
            self._last_level_draw = now
            db = value['db']
            level = round(max(0, min(80, db + 80)))
            if self.mic_level.get_value() != level:
                self.mic_level.set_value(level)
            message = ('削波，请降低增益' if value['clipped'] else
                       '电平很低，请检查麦克风连接' if db < -75 else '正在监听')
            if self._vision_npu_busy():message='物品检测使用NPU中，结束后继续语音'
            set_status_text(self.mic_state, '麦克风 · %s' % message)
            tooltip = '输入电平：%.0f dBFS' % db
            if self.mic_state.get_tooltip_text() != tooltip:
                self.mic_state.set_tooltip_text(tooltip)
        elif kind == 'onset':
            if self._vision_npu_busy():return False
            try:
                context = self.actions.context()
            except Exception as exc:
                self.append('当前控制状态无法核对，本句已丢弃：' + str(exc))
                return False
            self.mic_contexts[value['id']] = (self.mic_epoch, context, value['started'])
            set_status_text(self.status, '正在收听，请说一条完整指令…')
        elif kind == 'discard':
            self.mic_contexts.pop(value['id'], None)
            self.append(value['reason'])
        elif kind == 'utterance':
            capture = self.mic_contexts.pop(value['id'], None)
            if capture is None or capture[0] != self.mic_epoch:
                return False
            if self.recognizing:
                self.append('上一句仍在识别，本句已丢弃；未排队执行')
                return False
            try:
                path = pathlib.Path(self.recordings.name) / ('mic-%s-%s.wav' % (token, value['id']))
                with wave.open(str(path), 'wb') as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(16000)
                    stream.writeframes(value['pcm'])
                self.last_recording = path
                for old in sorted(path.parent.glob('mic-*.wav'), key=lambda p: p.stat().st_mtime)[:-20]:
                    old.unlink()
            except OSError as exc:
                self.append('录音保存失败，本句未识别：' + str(exc))
                return False
            self.start_wav(path, self.mic_execute, context=capture[1], started=capture[2],
                           deadline=value['ended'] + 3, source='microphone')
        elif kind == 'closed':
            self.mic = None
            self.cancel()
            self.refresh_inputs()
            error = value.get('error')
            if error:
                known = {'capture firmware is not installed': '板载麦克风采集固件尚未安装',
                    'I2C NACK': '音频芯片没有应答，请检查板卡音频连接',
                    'already in use': '麦克风正被其他程序使用',
                    'FIFO overflow': '录音缓存溢出，本次语音已取消'}
                message = next((v for k, v in known.items() if k in error), error)
                set_status_text(self.mic_state, 'MIC · 录音已停止')
                self.append('录音失败：' + message)
            else:
                set_status_text(self.mic_state, 'MIC · 录音已停止')
        return False

    def save_last_recording(self, *_):
        if self.last_recording is None:
            return
        dialog = Gtk.FileChooserDialog(title='保存最近的麦克风录音', transient_for=self, action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '保存', Gtk.ResponseType.OK)
        dialog.set_current_name('voice-command.wav')
        dialog.set_do_overwrite_confirmation(True)
        try:
            if dialog.run() == Gtk.ResponseType.OK:
                shutil.copyfile(str(self.last_recording), dialog.get_filename())
                self.append('麦克风录音已保存')
        except OSError as exc:
            self.append('录音保存失败：' + str(exc))
        finally:
            dialog.destroy()

    def show_commands(self, *_):
        from .local_voice import CATALOG
        if not self._commands_loaded:
            rows = json.loads(CATALOG.read_text(encoding='utf-8'))['classes'][2:]
            self.command_text.get_buffer().set_text('\n\n'.join(row['name'] + '：' + ' / '.join(row['phrases']) for row in rows))
            self._commands_loaded = True
        self.bindings.set_expanded(True)
        self.commands_details.set_expanded(True)

    def append(self, text):
        text = text[:10000]
        headline = text.split('；', 1)[0]
        set_status_text(self.status, headline[:140] + ('…' if len(headline)>140 else ''))
        if any(word in text for word in ('失败', '故障', '超时', '未启动', '未完成')):
            self.history_details.set_expanded(True)
        buffer = self.history.get_buffer()
        buffer.insert(buffer.get_end_iter(), time.strftime('%H:%M:%S') + ' [本地 NPU] ' + text + '\n\n')
        # Keep the dialog's text and journal bounded on the 1GB board.
        if buffer.get_char_count() > 20000:
            buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_offset(8000))
        self.history.scroll_to_iter(buffer.get_end_iter(), 0, False, 0, 0)
        try:
            path = pathlib.Path('/home/uisrc/.config/f3p-control/voice-events.jsonl')
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size > 2 * 1024 * 1024:
                path.replace(path.with_suffix('.previous.jsonl'))
            with path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(dict(time=time.time(), source='local_npu', message=text), ensure_ascii=False) + '\n')
        except OSError:
            pass

    def choose_route(self, slot):
        if self.mic is not None:
            self.append('请先停止语音，再更改线路绑定')
            return
        if self.recognizing or self.actions.busy:
            self.append('请等待当前识别或动作结束')
            return
        dialog = Gtk.FileChooserDialog(title='绑定已保存线路 ' + str(slot), transient_for=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '绑定', Gtk.ResponseType.OK)
        filter_ = Gtk.FileFilter()
        filter_.set_name('机械臂线路 JSON')
        filter_.add_pattern('*.json')
        dialog.add_filter(filter_)
        try:
            if dialog.run() == Gtk.ResponseType.OK:
                name = self.actions.bind(slot, dialog.get_filename())
                set_status_text(self.route_labels[slot], name)
                self.append('线路 ' + str(slot) + ' 已绑定：' + name)
        except Exception as exc:
            self.append('线路未绑定：' + str(exc))
        finally:
            dialog.destroy()

    def choose_wav(self, execute):
        if self.recognizing:
            return
        dialog = Gtk.FileChooserDialog(title='选择语音 WAV' + (' · 识别通过后直接执行' if execute else ' · 仅识别'),
                                      transient_for=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('取消', Gtk.ResponseType.CANCEL, '识别并执行' if execute else '仅识别', Gtk.ResponseType.OK)
        filter_ = Gtk.FileFilter()
        filter_.set_name('16kHz 单声道 PCM16 WAV')
        filter_.add_pattern('*.wav')
        dialog.add_filter(filter_)
        try:
            if dialog.run() == Gtk.ResponseType.OK:
                self.start_wav(dialog.get_filename(), execute)
        finally:
            dialog.destroy()

    def start_wav(self, path, execute=False, *, context=None, started=None, deadline=None, source='wav'):
        if self._vision_npu_busy():
            set_status_text(self.status, '物品检测正在使用NPU，请先结束识别；本句未排队。')
            return False
        if self.recognizing:
            raise RuntimeError('识别进行中；未排队')
        context = self.actions.context() if context is None else context
        self.generation += 1
        generation = self.generation
        started = time.monotonic() if started is None else started
        self.recognizing = True
        self.refresh_inputs()
        self.append('正在本地硬 NPU 识别：' + ('麦克风录音' if source == 'microphone' else pathlib.Path(path).name) + ('；通过后直接执行' if execute else '；仅识别'))
        def work():
            try:
                result, error = recognize_wav(path), None
            except Exception as exc:
                result, error = None, str(exc)
            GLib.idle_add(self.recognized, generation, started, context, execute, result, error, deadline)
        threading.Thread(target=work, name='f3p-local-npu', daemon=True).start()

    def recognized(self, generation, started, context, execute, result, error, deadline=None):
        self.recognizing = False
        if self.closed:
            return False
        self.refresh_inputs()
        if generation != self.generation:
            return False
        if error:
            self.append(error + '；未调用云端，未执行动作')
            return False
        evidence = '硬 NPU %s 工作负载 / IRQ +%s / 模型 %.2f ms' % (
            result['hard_workloads'], result['irq_delta'], result['model_compute_ms'] or 0)
        set_status_text(self.source, '本地语音 · 识别完成')
        self.append('识别：%s；得分 %.3f；%s' % (result['text'], result['score'], evidence))
        if not result['accepted']:
            self.append('未通过拒识阈值；未执行')
        elif not execute:
            self.append('仅识别模式；未执行：' + result['intent'])
        else:
            try:
                if result['intent'] not in ('STOP', 'CANCEL', 'REJECT'):
                    if time.monotonic() - started > 15 or deadline is not None and time.monotonic() > deadline:
                        raise RuntimeError('识别结果已过期，请重试')
                    if self.actions.context() != context:
                        raise RuntimeError('识别期间控制上下文改变，请重试')
                self.actions.execute(result['intent'], self.action_finished)
            except Exception as exc:
                self.append('未启动：' + str(exc))
        return False

    def action_finished(self, ok, result):
        if self.closed:
            return
        from .ai_chat_client import compact_state
        text = json.dumps(compact_state(result), ensure_ascii=False) if not isinstance(result, str) else result
        self.append(('控制结果：' if ok else '控制未完成：') + text)
