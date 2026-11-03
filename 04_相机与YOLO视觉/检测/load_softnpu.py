"""Load the pinned driver only for this board's real SoftNPU aperture."""
import fcntl,hashlib,json,mmap,re,struct,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parent
assert subprocess.check_output(['uname','-r'],universal_newlines=True).strip()=='6.1.111-rt42+'
node=Path('/proc/device-tree/soc/soft_npu@a0010000')
assert (node/'compatible').read_bytes().split(b'\0')[0]==b'anlogic,soft_npu'
assert struct.unpack('>4I',(node/'reg').read_bytes())==(0,0xa0010000,0,0x10000)
assert struct.unpack('>3I',(node/'interrupts').read_bytes())==(0,84,4)
module=root/'soft_npu.ko'
assert hashlib.sha256(module.read_bytes()).hexdigest()=='1a7570dd83319989b0553f96111c3329e80066d74999842f64a651e3e456a851'
with open('/dev/mem','rb',buffering=0) as f:
    words=[]
    for address in (0xa0000000,0xa0010000):
        with mmap.mmap(f.fileno(),4096,access=mmap.ACCESS_READ,offset=address) as m:
            words.append([struct.unpack('<I',m[i:i+4])[0] for i in (0,4,8,12)])
assert words[0][:2]==[0x52414331,0x3000a] and words[0]!=words[1]
with open('/opt/f3p-npu/hard-only-20261015-01/runtime/.inference.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if not Path('/sys/module/soft_npu').exists():subprocess.run(['insmod',str(module)],check=True,timeout=15)
    deadline=time.monotonic()+4
    while not Path('/dev/soft_npu').exists() and time.monotonic()<deadline:time.sleep(.1)
    assert Path('/dev/soft_npu').exists()
    irq=[s for s in Path('/proc/interrupts').read_text().splitlines() if 'SOFT_NPU_IRQ' in s]
    assert len(irq)==1 and re.search(r'GICv3\s+116\s+Level\s+SOFT_NPU_IRQ',irq[0])
print('COCO_SOFT_DRIVER_READY')
