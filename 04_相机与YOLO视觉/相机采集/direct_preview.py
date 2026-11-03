"""Separate camera-only full-screen preview candidate. No arm-control backend.

Stage alongside the existing robot_arm_gui package and run with python3.
Requires the new OSD1 FPGA capability. Escape or the top-left touch target
stops capture and restores desktop scanout. No RGB readback/rendering loop.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import threading
import time

from robot_arm_gui.direct_preview_mailbox import mapped_publisher


def ungray(value):
    result = 0
    while value:
        result ^= value
        value >>= 1
    return result


def display_counters(control):
    mode = control.read(0x33C)
    return {'mode': mode & 3, 'duplicates': ungray(mode >> 16),
            'frames': ungray(control.read(0x3F8)),
            'underflows': ungray(control.read(0x3EC)),
            'guard_errors': ungray(control.read(0x3F0)),
            'overflows': ungray(control.read(0x3F4))}


def display_rates(before, after, seconds):
    frames = (after['frames'] - before['frames']) & 0xFFFFFFFF
    duplicates = (after['duplicates'] - before['duplicates']) & 0xFFFF
    faults = any(after[key] != before[key] for key in ('underflows', 'overflows', 'guard_errors'))
    valid = before['mode'] == after['mode'] == 3 and not faults and duplicates <= frames
    return {'display_scanout_fps': frames / seconds, 'display_duplicate_delta': duplicates,
            'display_unique_fps_estimate': (frames - duplicates) / seconds if valid else None,
            'display_error_counters': {key: after[key] for key in ('underflows', 'overflows', 'guard_errors')}}


def camera_source(stop, display_lease_factory=None):
    from robot_arm_gui.accelerated_source import AcceleratedSource

    class DirectSource(AcceleratedSource):
        def __init__(self):
            super().__init__()
            self._preview_mode = 1
            self._mode_lock = threading.Lock()
            self._display_lease = None

        def _desktop_locked(self):
            lease, self._display_lease = self._display_lease, None
            self._preview_mode = 1
            try:
                if lease is not None:
                    lease.close()
            finally:
                self.control.set_mode(1)

        def enable_direct_preview(self):
            factory = display_lease_factory
            if factory is None:
                from camera1080_display import DisplayLease
                factory = DisplayLease
            with self._mode_lock:
                self._preview_mode = 3
                self.control.set_mode(3)
                try:
                    self._display_lease = factory()
                    self._display_lease.stop()
                    # The existing display guardian requires camera mode 3
                    # before it halts desktop DMA. Then temporarily disarm the
                    # camera reader and refill three raw frames. Re-arm only
                    # after that handover has finished and old reads drained.
                    if self.control.read(0x368) & 0xFFFF0000 == 0x52530000:
                        self._preview_mode = 1
                        self.control.set_mode(1)
                        before = ungray(self.control.read(0x3E4))
                        deadline = time.monotonic() + .8
                        while (ungray(self.control.read(0x3E4)) - before) & 0xFFFFFFFF < 3:
                            if time.monotonic() >= deadline:
                                raise RuntimeError('Camera raw buffers did not settle after display handover')
                            time.sleep(.004)
                    self._preview_mode = 3
                    self.control.set_mode(3)
                except Exception:
                    self._desktop_locked()
                    raise

        def set_preview_mode(self, mode):
            if mode not in (1, 3):
                raise ValueError("Unsupported camera preview mode")
            with self._mode_lock:
                if mode == 1:
                    self._desktop_locked()
                    return
                self._preview_mode = mode
                self.control.set_mode(mode)

        def _keep_alive(self):
            try:
                while not self._heartbeat_stop.wait(.15):
                    with self._mode_lock:
                        # Return to desktop even if native analysis is stuck.
                        if stop.is_set():
                            self._desktop_locked()
                        elif self._display_lease is not None:
                            self._display_lease.beat()
                        self.control.set_mode(self._preview_mode)
            except Exception as exc:
                self._heartbeat_error = exc

    return DirectSource()


def run_capture(source, stop, report, parameters=None, bands=None, tracker_type=None, preview=None):
    """Single exclusive camera owner; report contains original result geometry."""
    if parameters is None or bands is None or tracker_type is None:
        from robot_arm_gui.color_blocks import BlockParameters, DEFAULT_BANDS, BlockTracker
        parameters = parameters or BlockParameters()
        bands = bands or DEFAULT_BANDS
        tracker_type = tracker_type or BlockTracker
    from robot_arm_gui.accelerated_source import ExpiredCameraFrame

    publisher = None
    processed = intentional_skips = recoveries = 0
    stamp = time.monotonic()
    frames_at_stamp = 0
    source_at_stamp = None
    last_frame = stamp
    report.update(state='opening', asynchronous_overlay=True, recognition_target_fps=45,
                  preview_target_fps=60 if preview is None or getattr(preview,'hardware',False) else 20, raw_rgb_copies=0,
                  display_mode='hardware_window' if getattr(preview,'hardware',False) else 'embedded' if preview else 'fullscreen', display_fps_verified=False)
    try:
        source.open()
        source.allow_stream_gaps = True
        if getattr(preview,'hardware',False):
            # Let the GTK startup repaint settle before adding compact DMA.
            # Linux scanout stays enabled throughout the hardware-window path.
            if stop.wait(.6):return
            preview.attach(source)
            if stop.wait(.01):return  # Drain accepted raw DMA before compact startup.
        if preview is None:
            publisher = mapped_publisher(source.control)  # Reject old firmware.
            source.enable_direct_preview()
            if source.control.read(0x33C) & 3 != 3:
                raise RuntimeError('Full-screen camera scanout did not enable')
        # Release desktop DDR scanout before enabling the compact writer.
        # Starting all three DMA clients during the display handover can
        # overflow the compact FIFO before the first result is acquired.
        source.configure_features(parameters, bands)
        if getattr(preview,'hardware',False):
            publisher=mapped_publisher(source.control)
            deadline=time.monotonic()+.8
            while source.control.read(0x38c)<3:
                if source.control.read(0x394):raise RuntimeError('Camera compact warmup failed: %#x'%source.control.read(0x394))
                if time.monotonic()>=deadline:raise RuntimeError('Camera compact buffers did not settle')
                if stop.wait(.005):return
        tracker = tracker_type(parameters.min_confirmations)
        display_at_stamp = display_counters(source.control)
        report['state'] = 'running'
        next_analysis = time.monotonic()
        stamp = next_analysis
        source_at_stamp = source.control.status()['source_frames']
        last_frame = next_analysis
        while not stop.is_set():
            if getattr(preview,'hardware',False):
                preview.service(report)
            delay = next_analysis - time.monotonic()
            if delay > 0 and stop.wait(delay):
                break
            next_analysis = time.monotonic() + 1 / 45
            pending = source.pending()
            if stop.is_set():
                break
            if pending >= 2:
                # Selecting the newest complete frame is normal when camera
                # capture is faster than analysis. Retain confirmations across
                # deliberate skips; BlockTracker still expires old observations
                # by elapsed time and emits only detections from the new frame.
                # Actual slot expiry/corruption is checked below before publish.
                intentional_skips += source.recover_pending(limit=2)
            try:
                item = source.acquire_feature()
                if item is None:
                    if time.monotonic() - last_frame > 1.2:
                        raise RuntimeError('Camera features stopped updating')
                    continue
                tick = time.monotonic()
                result = source.analyze(item)
                source.finish_feature(item)  # Verify retained slot/config first.
            except ExpiredCameraFrame:
                if publisher is not None:
                    publisher.clear()
                tracker = tracker_type(parameters.min_confirmations)
                report.pop('result', None); report.pop('capture_packet', None)
                recoveries += 1
                continue
            tracked = tracker.update(result['detections'], item['captured_at'])
            result['tracked'] = tracked
            result['counts'] = {color: sum(d['color'] == color and d['stable'] for d in tracked)
                                for color in ('red', 'green', 'blue', 'yellow')}
            latest_id = source.control.read(0x388)
            if publisher is not None:
                publisher.publish(result, item['frame_id'], latest_id)
            if preview is not None and preview.due():
                preview.submit(source, item, result, report)
            result_age = (latest_id - item['frame_id']) & 0xFFFFFFFF
            now = time.monotonic()
            last_frame = now
            processed += 1
            report.update(processed=processed, frame_id=item['frame_id'], config_epoch=source.epoch,
                          last_result_monotonic=now,
                          analysis_ms=(now - tick) * 1000, recoveries=recoveries,
                          intentional_skipped=intentional_skips, osd_sent=publisher.sent if publisher else 0,
                          osd_busy_drops=publisher.busy_drops if publisher else 0,
                          osd_stale_drops=publisher.stale_drops if publisher else 0,
                          osd_truncated_boxes=publisher.truncated if publisher else 0, result_age_frames=result_age)
            if result_age <= 6:
                report['result'] = {key: value for key, value in result.items() if key != 'masks'}
            else:
                report.pop('result', None); report.pop('capture_packet', None)
            # Publish frame identity, bound and detections as one immutable packet.
            report['capture_packet'] = dict(frame_id=item['frame_id'],config_epoch=source.epoch,
                result_at=now,result=report.get('result',{}),bound=item.get('capture_bound'))
            if now - stamp >= 1:
                count = source.control.status()['source_frames']
                current_display = display_counters(source.control)
                if preview is None:
                    report.update(display_rates(display_at_stamp, current_display, now - stamp))
                report['recognition_fps'] = (processed - frames_at_stamp) / (now - stamp)
                if source_at_stamp is not None:
                    report['input_fps'] = ((count - source_at_stamp) & 0xFFFFFFFF) / (now - stamp)
                stamp, frames_at_stamp, source_at_stamp = now, processed, count
                display_at_stamp = current_display
    except Exception as exc:
        report.update(state='failed', error=str(exc))
        raise
    finally:
        report.pop('result', None); report.pop('capture_packet', None)
        if preview is not None:
            preview.close()
        try:
            try:
                if publisher is not None:
                    publisher.clear()  # If busy, PL timeout still bounds old boxes.
            finally:
                try:
                    if source.control is not None:
                        source.set_preview_mode(1)
                finally:
                    source.close()  # Existing Control.close disables DMA/mode.
        except Exception as exc:
            report.update(state='failed', cleanup_error=str(exc))
            raise
        if report.get('state') != 'failed':
            report['state'] = 'stopped'


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.pending')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    temporary.replace(path)


def console_status(report, session_id, exit_reason='', motor_stop_requested=False):
    now = time.monotonic()
    fields = ('state', 'error', 'cleanup_error', 'processed', 'frame_id', 'analysis_ms',
              'recognition_fps', 'input_fps', 'display_scanout_fps', 'display_unique_fps_estimate',
              'display_duplicate_delta', 'display_error_counters', 'recoveries', 'osd_sent',
              'result_age_frames', 'configuration', 'preview_fps', 'preview_frames',
              'preview_frame_id', 'preview_size', 'preview_source_size', 'preview_transport', 'display_mode','preview_visible',
              'preview_unique_frames','preview_underflows','preview_health','preview_scanout_fps','raw_rgb_copies','raw_dma_paused')
    value = {key: report[key] for key in fields if key in report}
    packet = report.get('capture_packet') or {}
    fresh = report.get('state') == 'running' and 0 <= now - packet.get('result_at', 0.) < 1.2
    result = packet.get('result', {}) if fresh else {}
    value.pop('frame_id',None)
    value.pop('config_epoch',None)
    if packet:
        value.update(frame_id=packet['frame_id'],config_epoch=packet['config_epoch'])
        if packet.get('bound'):
            value.update(packet['bound'])
    fields = ('color', 'track_id', 'center', 'bbox', 'confidence')
    value.update(session_id=session_id, timestamp=now, fresh=fresh,
                 exit_reason=exit_reason, motor_stop_requested=motor_stop_requested,
                 counts={color: int(result.get('counts', {}).get(color, 0)) for color in ('red', 'yellow', 'blue', 'green')},
                 targets=[{key: detection[key] for key in fields if key in detection}
                          for detection in result.get('tracked', ()) if detection.get('stable')][:16])
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='Write final metadata JSON after stopping')
    parser.add_argument('--profile', type=Path, help='Validated colour profile supplied by the console')
    parser.add_argument('--status-file', type=Path, help='Atomic console telemetry; no RGB image transfer')
    parser.add_argument('--session-id', default='standalone')
    parser.add_argument('--parent-pid', type=int, help='Stop when the owning console exits')
    parser.add_argument('--preview-file', type=Path, help='Embedded JPEG preview; keep desktop and camera mode 1')
    parser.add_argument('--window-file',type=Path,help='FPGA window geometry; keep Linux desktop scanout active')
    args = parser.parse_args()
    parameters = bands = None
    if args.profile:
        from robot_arm_gui.color_blocks import load_profile
        if args.profile.stat().st_size > 65536:
            raise ValueError('Colour profile is too large')
        parameters, bands = load_profile(args.profile)
    stop = threading.Event()
    shutdown_at = [None]
    report = {}
    if parameters is not None:
        from dataclasses import asdict
        report['configuration'] = {'parameters': asdict(parameters), 'bands': bands}
    failures = []
    source = camera_source(stop)
    preview = None
    if args.window_file:
        if args.preview_file:raise ValueError('Select exactly one embedded preview path')
        from hardware_window import HardwareWindow
        preview=HardwareWindow(args.window_file,args.session_id)
    if args.preview_file:
        from embedded_preview import EmbeddedPreview
        preview = EmbeddedPreview(args.preview_file)
    exit_reason = ['']
    motor_stop_requested = [False]
    next_status = [0.]

    def write_status(force=False):
        now = time.monotonic()
        if args.status_file is None or (not force and now < next_status[0]):
            return
        next_status[0] = now + .2
        value = console_status(report, args.session_id, exit_reason[0], motor_stop_requested[0])
        try:
            atomic_json(args.status_file, value)
        except OSError as exc:
            failures.append('Console telemetry failed: ' + str(exc))
            shutdown(reason='telemetry_failed')

    def worker():
        try:
            run_capture(source, stop, report, parameters=parameters, bands=bands, preview=preview)
        except Exception as exc:
            failures.append(str(exc))
        finally:
            stop.set()

    def shutdown(*_, reason='stop'):
        if shutdown_at[0] is None:
            shutdown_at[0] = time.monotonic()
        stop.set()
        if not exit_reason[0]:
            exit_reason[0] = reason
        return True

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    thread = threading.Thread(target=worker, name='f3p-direct-preview', daemon=True)
    if preview is not None:
        thread.start()
        while thread.is_alive():
            if args.parent_pid is not None and os.getppid() != args.parent_pid:
                shutdown(reason='console_exited')
            write_status()
            if shutdown_at[0] is not None and time.monotonic() - shutdown_at[0] >= 5:
                break
            thread.join(.05)
        stop.set()
        if thread.is_alive():
            failures.append('Camera cleanup did not finish')
        if failures:
            report.update(state='failed', error=failures[-1])
        report.update(session_id=args.session_id, exit_reason=exit_reason[0] or 'capture_stopped',
                      motor_stop_requested=False)
        write_status(force=True)
        if args.report:
            atomic_json(args.report, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return int(bool(failures))
    # The mapped full-screen window receives input; PL supplies every video
    # pixel. Establish full coverage before changing scanout or halting VDMA.
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
    window = Gtk.Window(title='F3P hardware preview — Escape to return')
    window.set_decorated(False)
    window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
    window.connect('delete-event', shutdown)
    def key(_, event):
        if event.keyval == Gdk.KEY_Escape:
            return shutdown(reason='escape')
        if event.keyval == Gdk.KEY_space and args.status_file:
            # Only the owning console invokes its existing motor-stop callback.
            motor_stop_requested[0] = True
            shutdown(reason='motor_stop')
            write_status(force=True)
            return True
        return False
    window.connect('key-press-event', key)

    def touch(_, event):
        x = event.x * 1920 / max(1, window.get_allocated_width())
        y = event.y * 1080 / max(1, window.get_allocated_height())
        return shutdown(reason='touch') if 0 <= x < 80 and 0 <= y < 56 else False

    window.connect('button-press-event', touch)
    window.fullscreen()
    window.show_all()
    window.present()
    started = [False]
    mapped_deadline = time.monotonic() + 5

    def check():
        if args.parent_pid is not None and os.getppid() != args.parent_pid:
            shutdown(reason='console_exited')
        write_status()
        if not started[0]:
            if stop.is_set():
                Gtk.main_quit()
                return False
            if window.get_mapped():
                monitor = Gdk.Display.get_default().get_monitor_at_window(window.get_window())
                geometry = monitor.get_geometry()
                if window.get_allocated_width() >= geometry.width and window.get_allocated_height() >= geometry.height:
                    thread.start()
                    started[0] = True
                    return True
            if time.monotonic() < mapped_deadline:
                return True
            failures.append('Full-screen input window did not establish coverage')
            shutdown()
            Gtk.main_quit()
            return False
        timed_out = shutdown_at[0] is not None and time.monotonic() - shutdown_at[0] >= 5
        if thread.is_alive() and not timed_out:
            return True
        Gtk.main_quit()
        return False

    GLib.timeout_add(100, check)
    try:
        Gtk.main()
    finally:
        stop.set()
        if started[0]:
            thread.join(timeout=0 if thread.is_alive() and shutdown_at[0] is not None else 5)
        window.destroy()
    if thread.is_alive():
        failures.append('Camera cleanup did not finish; hardware lease will expire')
    if failures and report.get('state') != 'failed':
        report.update(state='failed', error=failures[-1])
    report.update(session_id=args.session_id, exit_reason=exit_reason[0] or 'capture_stopped',
                  motor_stop_requested=motor_stop_requested[0])
    write_status(force=True)
    if args.report:
        atomic_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for failure in failures:
        print(failure)
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
