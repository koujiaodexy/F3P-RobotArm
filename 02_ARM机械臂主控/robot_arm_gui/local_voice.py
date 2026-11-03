"""Fixed local NPU intents and the existing controller task owner. No network calls."""
import copy
import hashlib
import json
import math
import pathlib
import subprocess
import time

MODEL_SHA256 = 'd06017fb7c251d446e8ab26c08f48963254bfc3173b94d68669115716bfa4c0c'
RUNTIME = pathlib.Path('/opt/f3p-npu/commands-20261015-v1')
CATALOG = pathlib.Path(__file__).with_name('voice_command_catalog.json')
SPEEDS = {'LOW': (2, 5), 'NORMAL': (5, 10), 'HIGH': (10, 20)}


def classify_report(report):
    """Recompute the gate; never trust an action string from a subprocess."""
    if (report.get('backend') != 'Alnpu+CpuRef' or
            type(report.get('hard_workloads')) is not int or report['hard_workloads'] < 5 or
            type(report.get('irq_delta')) is not int or report['irq_delta'] <= 0 or
            report.get('model_sha256') != MODEL_SHA256):
        raise ValueError('本地硬 NPU 证据或模型版本不符，未执行')
    rows = json.loads(CATALOG.read_text(encoding='utf-8'))['classes']
    scores = report.get('scores')
    if (not isinstance(scores, list) or len(scores) != len(rows) or
            any(type(v) not in (float, int) or not math.isfinite(v) for v in scores)):
        raise ValueError('识别输出无效，未执行')
    order = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
    top = order[0]
    values = [math.exp(v - scores[top]) for v in scores]
    total = sum(values)
    confidence = values[top] / total
    margin = confidence - values[order[1]] / total
    accepted = top >= 2 and confidence >= .9 and margin >= .05
    return dict(intent=rows[top]['id'] if accepted else None, text=rows[top]['name'],
                accepted=accepted, score=confidence, margin=margin,
                source='local_npu', backend=report['backend'],
                hard_workloads=report['hard_workloads'], irq_delta=report['irq_delta'],
                model_compute_ms=report.get('model_compute_ms'))


def recognize_wav(path):
    path = pathlib.Path(path).resolve()
    if not path.is_file() or path.stat().st_size > 400000:
        raise ValueError('请选择 10 秒以内的 16kHz 单声道 PCM16 WAV 文件')
    # Fixed executable and argv, no shell, CPU fallback or cloud fallback.
    result = subprocess.run(['/usr/bin/python3', str(RUNTIME / 'command_npu.py'), '--wav', str(path)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError('本地 NPU 识别失败：' + result.stderr[-700:])
    report = json.loads(result.stdout)
    decision = classify_report(report)
    decision['run_directory'] = report.get('run_directory')
    return decision


class VoiceActions:
    """Called on GTK's main thread; worker callbacks return through schedule()."""
    def __init__(self, window, schedule, later, config=None):
        from .ai_ui_control import UIControl
        self.window = window
        self.ui = UIControl(window)
        self.task = window.controller.motion_task
        self.schedule = schedule
        self.later = later
        self.config = pathlib.Path(config or '/home/uisrc/.config/f3p-control/voice-routes.json')
        self.bindings = {}
        self.busy = False
        self.generation = 0
        self.finished = None
        try:
            self.bindings = json.loads(self.config.read_text())
        except (OSError, ValueError):
            pass

    def context(self):
        w = self.window
        return copy.deepcopy(dict(selected=w.controller.selected_node,
            direction=w.joint_pages.drawing_page.direction.get_active_id(),
            canvas=w.joint_pages.drawing_page.document(), points=self.task.points,
            speed=w.joint_pages.speed.get_value(),
            rpm=w.speed_adjustment.get_value(), acceleration=w.acceleration_adjustment.get_value(),
            calibration=self.task.cartesian.calibration))

    def bind(self, slot, path):
        if self.busy:
            raise RuntimeError('请等待当前语音动作结束')
        if slot not in range(1, 6):
            raise ValueError('线路编号无效')
        route = self.task.ai_actions.routes.add(path)
        entry = self.task.ai_actions.routes.items[route]
        value = dict(self.bindings)
        value[str(slot)] = dict(path=str(pathlib.Path(path).resolve()), sha256=entry['sha256'], name=entry['name'])
        from .joint_motion import atomic_json
        self.config.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self.config, value)
        self.bindings = value
        return entry['name']

    def cancel(self, stop=False):
        self.generation += 1
        self.task.ai_actions.invalidate()
        if stop:
            self.window._stop_all()

    def _done(self, generation, ok, result):
        if generation != self.generation:
            # A canceled operation must finish before another request can start.
            self.busy = False
            callback = self.finished
            self.finished = None
            if callback:
                callback(False, '本地任务已取消；停止状态以控制台反馈为准')
            return False
        self.busy = False
        callback = self.finished
        self.finished = None
        if callback:
            callback(ok, result)
        return False

    def execute(self, intent, finished):
        if intent in ('STOP', 'CANCEL', 'REJECT'):
            self.cancel(stop=True)
            finished(True, '停止请求已提交；请以控制台停止反馈为准')
            return
        if intent == 'STATUS':
            finished(True, self.ui.state())
            return
        if self.busy:
            raise RuntimeError('当前语音任务尚未结束；未排队执行')
        if intent == 'CONFIRM':
            finished(True, '当前为检查通过直接执行模式，没有待确认动作')
            return
        self.ui.idle()
        self.generation += 1
        generation = self.generation
        self.finished = finished
        self.busy = True
        def done(ok, error):
            self.schedule(self._done, generation, ok, error if not ok else self.task.message)
        try:
            if intent.startswith('RUN_ROUTE_'):
                slot = intent[len('RUN_ROUTE_'):]
                binding = self.bindings.get(slot)
                if not binding:
                    raise ValueError('线路 ' + slot + ' 尚未绑定，请先选择对应的已保存线路')
                path = pathlib.Path(binding['path'])
                if hashlib.sha256(path.read_bytes()).hexdigest() != binding['sha256']:
                    raise ValueError('已绑定线路文件改变，请重新绑定')
                route = self.task.ai_actions.routes.add(path)
                direction = self.window.joint_pages.drawing_page.direction.get_active_id() or 'hold'
                def prepared(ok, error):
                    self.schedule(self._prepared, generation, ok, error, direction, done)
                self.task.start('ai_prepare', prepared,
                                action=dict(name='run_saved_route', args=dict(route_id=route)), direction=direction)
                return
            asynchronous = {'HOME': 'home_all', 'REFRESH_ANGLES': 'refresh', 'CAPTURE_POSE': 'record',
                'PLAY_TEACHING': 'play', 'PREVIEW_TEACHING': 'cart_sequence_plan',
                'PREPARE_CANVAS': 'cart_drawing_prepare', 'EXECUTE_CANVAS': 'cart_drawing_execute'}
            if intent in asynchronous:
                command = asynchronous[intent]
                if intent == 'HOME':
                    self.task.ai_actions.invalidate()
                    def home_done(ok, error):
                        self.schedule(self._done, generation, ok,
                                      self.window.controller.zero_home.message if ok else error)
                    self.window.controller.zero_home.start('home_all', 1, home_done)
                else:
                    p = self.window.joint_pages
                    params = {}
                    if intent == 'REFRESH_ANGLES':
                        params = dict(nodes=list(range(1, 7)), fill_targets=False)
                    elif intent == 'CAPTURE_POSE':
                        params = dict(name=p.name.get_text().strip() or '语音姿态 ' + str(len(self.task.points) + 1),
                                      speed=p.teach_speed.get_value(), dwell=p.dwell.get_value())
                    elif intent in ('PREPARE_CANVAS', 'EXECUTE_CANVAS'):
                        params = dict(document=p.drawing_page.document())
                        if intent == 'EXECUTE_CANVAS':
                            params['clearance_confirmed'] = True
                    self.task.start(command, done, **params)
                return
            simple = {'ENABLE': 'enable_selected', 'DISABLE': 'disable_selected', 'OPEN_VISION': 'open_vision',
                      'VIEW_LOGS': 'view_logs', 'START_LOGGING': 'start_logging', 'END_LOGGING': 'end_logging',
                      'SAVE_CANVAS': 'save_canvas', 'LOAD_CANVAS': 'load_canvas'}
            if intent.startswith('JOINT_') and intent in {'JOINT_' + str(n) for n in range(1, 7)}:
                result = self._setting('selected_joint', int(intent[-1]))
            elif intent.startswith('SHOW_') and intent[5:].lower() in ('control', 'position', 'drawing', 'teaching'):
                result = self.ui.perform(dict(name='show_control_page', args=dict(page=intent[5:].lower())))
            elif intent.startswith('SPEED_') and intent[6:] in SPEEDS:
                joint, tcp = SPEEDS[intent[6:]]
                for setting, value in (('joint_speed', joint), ('drawing_joint_speed', joint), ('tcp_speed', tcp)):
                    self._setting(setting, value)
                result = dict(status='速度档位已设置', joint_deg_s=joint, tcp_mm_s=tcp)
            elif intent == 'OPEN_VISION' and callable(getattr(self.window,'_show_coco_objects',None)):
                self.window._show_coco_objects()
                result = dict(status='已进入物品识别流程，请在画面中选择物品；实际识别状态见界面')
            elif intent in simple:
                result = self.ui.perform(dict(name='activate_control', args=dict(command=simple[intent])),
                                         require_area_confirmation=False)
            else:
                raise ValueError('不支持该语音指令')
            if self.window.controller._pending is not None:
                self.later(50, self._pending, generation, intent, result, time.monotonic() + 10,
                           self.window.controller.selected_node)
            else:
                self._done(generation, True, result)
        except Exception as error:
            self._done(generation, False, str(error))

    def _setting(self, name, value):
        return self.ui.perform(dict(name='set_control_setting', args=dict(setting=name, value=value)))

    def _prepared(self, generation, ok, error, direction, done):
        if generation != self.generation:
            return self._done(generation, False, '已取消')
        try:
            if not ok:
                raise RuntimeError(error)
            if (self.window.joint_pages.drawing_page.direction.get_active_id() or 'hold') != direction:
                raise RuntimeError('检查期间朝向改变，请重试')
            receipt = self.task.ai_actions.pending
            if not receipt:
                raise RuntimeError('检查结果已失效，请重试')
            # The user's direct-execution instruction authorizes this handoff.
            # ArmActions.execute still verifies token, TTL, actual pose and references.
            self.task.start('ai_execute', done, token=receipt['token'], confirmed=True)
        except Exception as exc:
            self._done(generation, False, str(exc))
        return False

    def _pending(self, generation, intent, result, deadline, node):
        if generation != self.generation:
            return self._done(generation, False, '已取消')
        c = self.window.controller
        if c._pending is not None:
            if time.monotonic() < deadline:
                return True
            return self._done(generation, False, '控制反馈超时，不能视为完成')
        state = c.nodes[node if intent in ('ENABLE', 'DISABLE') else c.selected_node]
        error = state.error if state.error not in ('', '无') else ''
        if intent == 'ENABLE' and not state.enabled:
            error = error or '使能未确认'
        if intent == 'DISABLE' and state.enabled:
            error = error or '失能未确认'
        return self._done(generation, not bool(error),
                          error or dict(request=result, current_state=self.ui.state()))
