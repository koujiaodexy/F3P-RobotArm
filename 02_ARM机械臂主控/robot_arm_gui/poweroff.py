"""Flush recordings before requesting Linux poweroff; caller confirms motor stop."""
import subprocess


def finish_poweroff(controller, command=None, preflight=None):
    recorder = controller.recorder
    status = recorder.status(include_recent=False)
    if status['starting'] or status['exporting']:
        raise RuntimeError('记录正在开始或导出，请完成后再关机。')
    recorder.stop('system_shutdown')
    if recorder.path and not recorder.done.wait(15):
        raise RuntimeError('记录尚未写入完成，关机已取消。')
    if recorder.status(include_recent=False)['error']:
        raise RuntimeError('记录写入存在错误，关机已取消，请检查记录。')
    if controller.active_node is not None:
        raise RuntimeError('电机尚未确认停止，关机已取消。')
    if preflight is not None:
        preflight()
    if command is not None:
        command()
    else:
        subprocess.run(['/sbin/shutdown', '-h', 'now'], check=True,
                       capture_output=True, text=True, timeout=10)
