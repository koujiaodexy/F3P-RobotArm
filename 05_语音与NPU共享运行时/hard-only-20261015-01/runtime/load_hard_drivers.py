"""Load only the isolated hard-NPU/CMA modules; never touch FPGA, GUI, or motion."""
import gzip
import hashlib
import json
from pathlib import Path
import platform
import stat
import subprocess
import sys

BASE = Path(__file__).resolve().parent
CONFIG_SHA = 'a26c6323501b39dd30fc8520cc3b76ca0c19414f66989b6dc1fed478682d7189'

def main():
    if platform.machine() != 'aarch64' or platform.release() != '6.1.111-rt42+':
        raise RuntimeError('Kernel/architecture does not match the isolated modules')
    if hashlib.sha256(gzip.decompress(Path('/proc/config.gz').read_bytes())).hexdigest() != CONFIG_SHA:
        raise RuntimeError('Kernel configuration hash mismatch')
    manifest = json.loads((BASE/'manifest.json').read_text())
    for name in ('modules/cma_mem.ko', 'modules/hard_npu.ko'):
        if hashlib.sha256((BASE/name).read_bytes()).hexdigest() != manifest['sha256'][name]:
            raise RuntimeError('Module hash mismatch: '+name)
    loaded = []
    try:
        for name in ('cma_mem', 'hard_npu'):
            if not (Path('/sys/module')/name).exists():
                subprocess.run(['/sbin/insmod', str(BASE/'modules'/(name+'.ko'))], check=True)
                loaded.append(name)
            node = Path('/dev')/name
            if not node.exists() or not stat.S_ISCHR(node.stat().st_mode):
                raise RuntimeError('Module did not create expected character device: '+name)
        print(json.dumps({'hard_npu_ready': True, 'newly_loaded': loaded,
                          'soft_npu_loaded': Path('/sys/module/soft_npu').exists(),
                          'fpga_changed': False, 'gui_restarted': False}))
    except Exception:
        for name in reversed(loaded):
            subprocess.run(['/sbin/rmmod', name], check=False)
        raise

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'hard_npu_ready': False, 'error': str(error)}))
        sys.exit(2)
