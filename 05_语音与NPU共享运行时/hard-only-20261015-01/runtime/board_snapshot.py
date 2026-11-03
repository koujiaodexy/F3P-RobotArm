"""Snapshot the current deployment/config hashes without disclosing configuration values."""
import hashlib
import json
from pathlib import Path

def snapshot():
    root = Path('/opt/f3p-control')
    meta_path = root / 'six-motor-deployment.json'
    meta = json.loads(meta_path.read_text())
    sources = {n: hashlib.sha256((root/'robot_arm_gui'/n).read_bytes()).hexdigest()
               for n in meta['sources']}
    changed = [n for n, value in sources.items() if value != meta['sources'][n]]
    configs = {}
    control = Path('/home/uisrc/.config/f3p-control')
    for path in sorted(control.rglob('*')):
        if path.is_file():
            configs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    private = Path('/home/uisrc/.config/f3p-cloud-ai/deepseek.json')
    if private.is_file():
        configs[str(private)] = hashlib.sha256(private.read_bytes()).hexdigest()
    guis = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            args = (path/'cmdline').read_bytes().split(b'\0')
            if b'/opt/f3p-control/robot_arm_gui/gtk_app.py' in args and b'sudo' not in args[0]:
                guis.append(int(path.name))
        except (OSError, IndexError):
            pass
    return dict(version=meta['software_version'], sources=sources, changed=changed,
                deployment_sha256=hashlib.sha256(meta_path.read_bytes()).hexdigest(),
                config_sha256=configs, gui_pids=guis,
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())

if __name__ == '__main__':
    root = Path('/opt/f3p-npu/hard-only-20261015-01')
    root.mkdir(parents=True, exist_ok=True)
    target = root/'before.json'
    if target.exists():
        raise SystemExit('Existing baseline kept; inspect before continuing')
    state = snapshot()
    if state['changed'] or len(state['gui_pids']) != 1:
        raise SystemExit('Formal application baseline failed')
    target.write_text(json.dumps(state, indent=2)+'\n')
    print(json.dumps(dict(version=state['version'], files=len(state['sources']),
        changed=state['changed'], gui_pids=state['gui_pids'], boot_id=state['boot_id'],
        baseline_saved=True)))
