"""F3P independent desktop mirror supervisor. Never calls controller interfaces."""
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path('/run/f3p-display-mirror')
GUI = '/opt/f3p-control/robot_arm_gui/gtk_app.py'
STOP = False


def proc_identity(pid):
    folder = Path('/proc') / str(pid)
    return {'pid': pid, 'start_ticks': (folder / 'stat').read_text().rsplit(')', 1)[1].split()[19],
            'argv': [part.decode() for part in (folder / 'cmdline').read_bytes().split(b'\0') if part]}


def listeners():
    result = []
    output = subprocess.check_output(['ss', '-H', '-ltn'], timeout=5).decode()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].rsplit(':', 1)[-1] == '5900':
            result.append(parts[3])
    return result


def loopback_only(values):
    return values == ['127.0.0.1:5900']


def find_gui():
    found = []
    for folder in Path('/proc').iterdir():
        if not folder.name.isdigit():
            continue
        try:
            item = proc_identity(int(folder.name))
            if not item['argv'] or not Path(item['argv'][0]).name.startswith('python') or GUI not in item['argv']:
                continue
            raw = dict(part.split(b'=', 1) for part in (folder / 'environ').read_bytes().split(b'\0') if b'=' in part)
            item['env'] = {name: raw[name.encode()].decode() for name in
                           ('DISPLAY', 'XAUTHORITY', 'HOME', 'LANG', 'PATH') if name.encode() in raw}
            authority = item['env'].get('XAUTHORITY')
            if not item['env'].get('DISPLAY') or not authority or not Path(authority).is_file():
                continue
            meta = Path(authority).stat()
            item['authority_signature'] = [meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns]
            found.append(item)
        except (OSError, UnicodeError):
            continue
    return found[0] if len(found) == 1 else None


def session_signature(gui):
    # GUI restart / Xauthority replacement recreates the share using fresh credentials.
    if gui is None:
        return None
    return (gui['pid'], gui['start_ticks'], gui['env']['DISPLAY'], gui['env']['XAUTHORITY'],
            tuple(gui['authority_signature']))


def build_command(server, help_text, display):
    mandatory = ('localhost', 'securitytypes', 'rfbport', 'framerate', 'maxprocessorusage', 'useipv6')
    if not all(name in help_text.lower() for name in mandatory):
        raise RuntimeError('TigerVNC lacks required loopback/performance options')
    command = [server, '-display', display, '-localhost=1', '-UseIPv6=0', '-rfbport', '5900',
               '-SecurityTypes=None', '-FrameRate=10', '-MaxProcessorUsage=15', '-AlwaysShared=1',
               '-AcceptKeyEvents=1', '-AcceptPointerEvents=1', '-AcceptCutText=0', '-SendCutText=0']
    if 'acceptsetdesktopsize' in help_text.lower():
        command.append('-AcceptSetDesktopSize=0')
    if 'interface' in help_text.lower():
        command.extend(['-interface', '127.0.0.1'])
    return command


def stop_child(child):
    # Only the Popen child owned by this supervisor can be signalled here.
    if child is None:
        return
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=2)
    else:
        child.wait()


def banner():
    with socket.create_connection(('127.0.0.1', 5900), timeout=2) as connection:
        raw = b''
        while len(raw) < 12:
            part = connection.recv(12 - len(raw))
            if not part:
                break
            raw += part
    if not re.fullmatch(rb'RFB \d{3}\.\d{3}\n', raw):
        raise RuntimeError('Desktop RFB handshake failed')
    return raw.decode().strip()


def write_state(value):
    temporary = ROOT / 'server.json.tmp'
    if temporary.is_symlink() or (ROOT / 'server.json').is_symlink():
        raise RuntimeError('Unexpected mirror state symlink')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    os.replace(str(temporary), str(ROOT / 'server.json'))


def main():
    global STOP
    if os.geteuid() != 0 or ROOT.is_symlink():
        raise RuntimeError('Invalid mirror supervisor ownership')
    ROOT.mkdir(mode=0o700, exist_ok=True)
    meta = ROOT.stat()
    if meta.st_uid != 0 or meta.st_mode & 0o077:
        raise RuntimeError('Private mirror runtime directory required')
    server = shutil.which('x0tigervncserver') or shutil.which('x0vncserver')
    if not server:
        raise RuntimeError('TigerVNC desktop scraping package is missing')
    server = str(Path(server).resolve())
    binary_sha = hashlib.sha256(Path(server).read_bytes()).hexdigest()
    help_text = subprocess.run([server, '-h'], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=8).stdout.decode(errors='replace')
    build_command(server, help_text, ':0')
    def request_stop(signum, frame):
        global STOP
        STOP = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    child = None
    current_signature = None
    previous_message = None
    try:
        while not STOP:
            gui = find_gui()
            signature = session_signature(gui)
            if child is not None and (child.poll() is not None or signature != current_signature):
                stop_child(child)
                child = None
                current_signature = None
            if child is None:
                if gui is None:
                    message = 'waiting for the existing GTK desktop'
                    write_state({'ready': False, 'state': 'waiting_for_gui', 'motion_requested': False})
                elif listeners():
                    # Never kill an unrelated service or take over another display listener.
                    message = 'waiting: port 5900 is owned by another process'
                    write_state({'ready': False, 'state': 'port_in_use', 'motion_requested': False})
                else:
                    command = build_command(server, help_text, gui['env']['DISPLAY'])
                    child = subprocess.Popen(command, env=dict(os.environ, **gui['env']),
                                             stdin=subprocess.DEVNULL, close_fds=True)
                    try:
                        deadline = time.monotonic() + 8
                        while not STOP and time.monotonic() < deadline:
                            if child.poll() is not None:
                                raise RuntimeError('Desktop scraper exited during startup')
                            addresses = listeners()
                            if addresses:
                                if not loopback_only(addresses):
                                    raise RuntimeError('Desktop scraper exposed a non-loopback listener')
                                break
                            time.sleep(.1)
                        else:
                            raise RuntimeError('Desktop scraper did not become ready')
                        rfb = banner()
                        if session_signature(find_gui()) != signature:
                            raise RuntimeError('Desktop session changed during startup')
                        current_signature = signature
                        write_state({'ready': True, 'server': proc_identity(child.pid),
                                     'supervisor': proc_identity(os.getpid()), 'gui_pid': gui['pid'],
                                     'gui_start_ticks': gui['start_ticks'], 'display': gui['env']['DISPLAY'],
                                     'listening': addresses, 'rfb_banner': rfb,
                                     'binary_sha256': binary_sha, 'max_desktop_fps': 10,
                                     'max_polling_cpu_percent': 15, 'ssh_tunnel_required': True,
                                     'camera_overlay_included': False, 'clipboard_shared': False,
                                     'input_enabled': True, 'motion_requested': False})
                        message = 'ready on 127.0.0.1:5900'
                    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                        stop_child(child)
                        child = None
                        current_signature = None
                        message = 'retrying desktop share: ' + str(error)
                        write_state({'ready': False, 'state': 'retrying', 'motion_requested': False})
                if message != previous_message:
                    print('F3P_DESKTOP ' + message, flush=True)
                    previous_message = message
            for _ in range(20):
                if STOP:
                    break
                time.sleep(.1)
    finally:
        stop_child(child)
        write_state({'ready': False, 'state': 'stopped', 'motion_requested': False})


if __name__ == '__main__':
    main()
