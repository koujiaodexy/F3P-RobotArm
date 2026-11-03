"""Reconnect this PC's existing hotspot desktop without weakening host-key checks.

Run manually after a PC restart. A successful invocation leaves only the SSH
tunnel and bounded browser proxy running. It never installs a Windows startup
entry, changes a board service or sends an actuator command.
"""
import argparse
import datetime
import ipaddress
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
def desktop_state_directory():
    # MSIX redirects LocalAppData for the agent but not for Explorer launches.
    # Keep the enrolled identity in the account home, outside that redirection.
    if os.name == 'nt':
        import ctypes
        value = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x28, None, 0, value) == 0 and value.value:
            return Path(value.value) / '.f3p-display-mirror'
    return Path.home() / '.f3p-display-mirror'

STATE = desktop_state_directory()
PROXY = ROOT / 'scripts/desktop-mirror-proxy.py'
LEGACY_PROXY = ROOT / 'artifacts/display-mirror-20261030/start-pc-web-viewer.py'
URL = 'http://127.0.0.1:6080/control.html'
BOARD_MAC = '8c-7a-b3-f8-17-2d'
HOST_ALIAS = 'f3p-display-board'


def safe_address(value):
    address = ipaddress.IPv4Address(value)
    if address not in ipaddress.IPv4Network('192.168.137.0/24') or int(address) & 255 in (0, 1, 255):
        raise ValueError('Use the board address on the PC mobile hotspot')
    return str(address)


def pinned_alias(known_hosts):
    """Use the serial-verified public key across DHCP address changes."""
    identities = set()
    for line in known_hosts.splitlines():
        fields = line.split()
        if fields and not line.startswith('#'):
            if len(fields) < 3 or fields[1] != 'ssh-ed25519':
                raise ValueError('Unexpected host-key format; do not replace the existing trust record')
            identities.add(tuple(fields[1:3]))
    if len(identities) != 1:
        raise ValueError('Exactly one existing board host key is required')
    kind, key = identities.pop()
    if not re.fullmatch(r'[A-Za-z0-9+/=]+', key):
        raise ValueError('Malformed host key')
    return '%s %s %s\n' % (HOST_ALIAS, kind, key)


def discover_address():
    output = subprocess.check_output(['arp.exe', '-a'], timeout=5).decode(errors='replace')
    matches = []
    for line in output.splitlines():
        parts = line.lower().split()
        if len(parts) >= 2 and parts[1].replace(':', '-') == BOARD_MAC:
            try:
                matches.append(safe_address(parts[0]))
            except ValueError:
                pass
    if len(set(matches)) == 1:
        return matches[0]
    # The previous IP is only a connection hint. SSH still requires its pinned key.
    previous = STATE / 'tunnel.json'
    if previous.is_file():
        return safe_address(json.loads(previous.read_text(encoding='utf-8-sig'))['board'])
    return '192.168.137.5'


def process_identity(pid):
    process = psutil.Process(pid)
    return {'pid': pid, 'created': process.create_time(),
            'exe': os.path.normcase(process.exe()), 'argv': process.cmdline()}


def same_identity(record):
    try:
        current = process_identity(record['pid'])
        return current == record
    except (KeyError, psutil.Error):
        return False


def stop_owned(record):
    """Never terminate a reused PID or a process with changed identity."""
    if not same_identity(record):
        return
    process = psutil.Process(record['pid'])
    children = [(child, process_identity(child.pid)) for child in process.children(recursive=True)]
    for child, identity in reversed(children):
        if same_identity(identity):
            child.terminate()
    if same_identity(record):
        process.terminate()
    psutil.wait_procs([process] + [child for child, _ in children], timeout=3)


def expected_legacy_owner(record):
    return (Path(record['exe']).name.lower() in ('python.exe', 'pythonw.exe')
            and str(LEGACY_PROXY) in record['argv'])


def expected_legacy_child(record):
    argv = record['argv']
    return (Path(record['exe']).name.lower() in ('python.exe', 'pythonw.exe')
            and '-c' in argv and '--multiprocessing-fork' in argv
            and any('from multiprocessing.spawn import spawn_main' in value for value in argv))


def migrate_legacy_proxy():
    """Only remove the precisely identified old proxy tree, never a port owner by name."""
    owners = {row.pid for row in psutil.net_connections(kind='tcp')
              if row.status == psutil.CONN_LISTEN and row.laddr.port == 6080}
    if len(owners) != 1 or None in owners:
        raise RuntimeError('Cannot uniquely identify the old desktop listener')
    listener = psutil.Process(owners.pop())
    identity = process_identity(listener.pid)
    if not expected_legacy_owner(identity):
        raise RuntimeError('Port 6080 belongs to another application; it was not stopped')
    # The venv launcher may also own conhost.exe. Only the actual listening
    # interpreter and its verified worker descendants belong to this migration.
    # Do not climb to the launcher or touch its other children.
    snapshots = [identity]
    for child in listener.children(recursive=True):
        record = process_identity(child.pid)
        if not expected_legacy_child(record):
            raise RuntimeError('Unexpected child in old desktop tree; no process was stopped')
        snapshots.append(record)
    # Complete preflight before terminating even the first process.
    if not all(same_identity(record) for record in snapshots):
        raise RuntimeError('Old desktop process identity changed during inspection')
    processes = []
    for record in reversed(snapshots):
        if same_identity(record):
            process = psutil.Process(record['pid'])
            process.terminate()
            processes.append(process)
    psutil.wait_procs(processes, timeout=3)
    if listening(6080):
        raise RuntimeError('The old desktop listener has not released its port')
    return [record['pid'] for record in snapshots]


def listening(port):
    with socket.socket() as stream:
        stream.settimeout(.3)
        return stream.connect_ex(('127.0.0.1', port)) == 0


def rfb_ready():
    def read(stream, count):
        data = b''
        while len(data) < count:
            part = stream.recv(count - len(data))
            if not part:
                raise EOFError('RFB closed')
            data += part
        return data
    try:
        with socket.create_connection(('127.0.0.1', 5901), timeout=2) as stream:
            stream.settimeout(3)
            version = read(stream, 12)
            if version not in (b'RFB 003.008\n', b'RFB 003.003\n'):
                return False
            stream.sendall(version)
            if version == b'RFB 003.003\n':
                if read(stream, 4) != b'\0\0\0\1':
                    return False
            else:
                count = read(stream, 1)[0]
                if not count or 1 not in read(stream, count):
                    return False
                stream.sendall(b'\1')
                if read(stream, 4) != b'\0'*4:
                    return False
            # Finish authentication and shared ClientInit before disconnecting.
            # A banner-only disconnect increments TigerVNC security failures.
            stream.sendall(b'\1')
            init = read(stream, 24)
            length = struct.unpack('!I', init[20:24])[0]
            if length > 4096:
                return False
            read(stream, length)
            return True
    except (OSError, EOFError):
        return False


def health():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:6080/f3p-health', timeout=2) as reply:
            data = json.loads(reply.read(4096))
        if data.get('service') == 'f3p-desktop-proxy-v2' and data.get('target') == '127.0.0.1:5901':
            return data
    except (OSError, ValueError):
        pass
    return None


def start_hidden(args, logfile):
    with logfile.open('ab') as output:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=output,
                                   stderr=subprocess.STDOUT, cwd=str(ROOT),
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    time.sleep(.3)
    if process.poll() is not None:
        raise RuntimeError('Background helper exited; inspect ' + str(logfile))
    return process_identity(process.pid)


def ssh_command(board, known_hosts, key):
    executable = shutil.which('ssh.exe')
    if not executable:
        raise RuntimeError('Windows OpenSSH client is missing')
    return [executable, '-N', '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=' + HOST_ALIAS,
            '-o', 'UserKnownHostsFile=' + str(known_hosts), '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            '-o', 'ConnectTimeout=8', '-o', 'LogLevel=ERROR', '-i', str(key),
            '-L', '127.0.0.1:5901:127.0.0.1:5900', 'root@' + safe_address(board)]


def save_state(value):
    path = STATE / 'reconnect-state.json'
    temporary = STATE / 'reconnect-state.tmp'
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', help='Current hotspot address; host key remains pinned')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--migrate-legacy-proxy', action='store_true',
                        help='Replace only the verified old project proxy process tree')
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('Use this reconnect entry on the Windows controller PC')
    key = STATE / 'desktop_ed25519'
    trust = STATE / 'known_hosts'
    for identity_file in (key, trust):
        try:
            with identity_file.open('rb'):
                pass
        except OSError as error:
            raise RuntimeError('Cannot read desktop identity: ' + str(identity_file) +
                               ' (' + type(error).__name__ + '); use the Windows account that created the connection') from None
    alias = STATE / 'known_hosts_desktop'
    alias_text = pinned_alias(trust.read_text(encoding='utf-8-sig'))
    if alias.exists() and alias.read_text(encoding='ascii') != alias_text:
        raise RuntimeError('Stored board key changed; refusing automatic replacement')
    if not alias.exists():
        alias.write_text(alias_text, encoding='ascii')
    board = safe_address(args.board) if args.board else discover_address()
    state_file = STATE / 'reconnect-state.json'
    state = json.loads(state_file.read_text()) if state_file.is_file() else {}
    command = ssh_command(board, alias, key)
    tunnel = state.get('ssh', {})
    if same_identity(tunnel) and tunnel['argv'] != command:
        stop_owned(tunnel)
        tunnel = {}
    if not same_identity(tunnel):
        # A banner alone cannot authenticate an unmanaged local tunnel.
        if listening(5901):
            raise RuntimeError('Port 5901 belongs to an unmanaged tunnel; it was not stopped')
        else:
            state['ssh'] = start_hidden(command, STATE / 'tunnel-reconnect.log')
            save_state(state)
    deadline = time.monotonic() + 12
    while not rfb_ready() and time.monotonic() < deadline:
        time.sleep(.5)
    if not rfb_ready():
        raise RuntimeError('The board desktop is not ready; check hotspot/IP and the board mirror service. No controller action was sent')
    current = health()
    if not current:
        if listening(6080):
            if args.migrate_legacy_proxy:
                state['replaced_legacy_proxy_pids'] = migrate_legacy_proxy()
            else:
                raise RuntimeError('Port 6080 is held by the old/unmanaged proxy; use --migrate-legacy-proxy only for the earlier project viewer')
        state['proxy'] = start_hidden([sys.executable, '-B', str(PROXY)], STATE / 'proxy-reconnect.log')
        save_state(state)
        deadline = time.monotonic() + 8
        while not current and time.monotonic() < deadline:
            time.sleep(.2)
            current = health()
        if not current:
            raise RuntimeError('The local browser proxy did not become ready')
    # Verify the claimed healthy endpoint is in fact this project proxy.
    owner = process_identity(current['pid'])
    if str(PROXY) not in owner['argv']:
        raise RuntimeError('Unexpected process behind the desktop proxy health endpoint')
    state.update(board=board, ready=True, url=URL, proxy_server=owner,
                 verified_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    save_state(state)
    print(json.dumps({'ready': True, 'board': board, 'url': URL, 'motion_requested': False}))
    if not args.no_browser:
        webbrowser.open(URL)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('DESKTOP_RECONNECT_ERROR: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
