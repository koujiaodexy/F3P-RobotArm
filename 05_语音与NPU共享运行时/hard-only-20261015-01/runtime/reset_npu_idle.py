"""Bounded reset pulse from vendor DR1M90 anl_crp_rstbl[RST_NPU]."""
import ctypes,fcntl,json,mmap,os,stat,struct,time
from pathlib import Path
shared=Path('/opt/f3p-npu/hard-only-20261015-01/runtime')

def require_driver_ready():
 # The driver enables the NPU/SRAM in probe. Reading NPU MMIO before
 # probe on a cold boot can stall the bus and reset the entire board.
 if not Path('/sys/module/hard_npu').is_dir():
  raise RuntimeError('NPU reset refused: hard_npu driver must be loaded first')
 if not Path('/sys/bus/platform/drivers/hard_npu/63f00000.hard_npu').exists():
  raise RuntimeError('NPU reset refused: hard_npu device is not bound')
 for node in ('hard_npu','cma_mem'):
  p=Path('/dev')/node
  if not p.exists() or not stat.S_ISCHR(p.stat().st_mode):
   raise RuntimeError('NPU reset refused: missing driver device '+node)

require_driver_ready()
def rd(address):
 fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
 try:
  with mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=address&~4095) as m:return struct.unpack_from('<I',m,address&4095)[0]
 finally:os.close(fd)
def motion_state():return {hex(x):rd(0xa0000000+x) for x in [0,4,0x14,0x264,0x2c4]}
before=motion_state();assert before['0x14']&5==0 and before['0x264']==0 and before['0x2c4']==0,before
with (shared/'.inference.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 owners=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   for fd in (p/'fd').iterdir():
    try:
     if os.readlink(str(fd)) in ['/dev/hard_npu','/dev/cma_mem']:owners.append(p.name)
    except OSError:pass
  except OSError:pass
 assert not owners,owners
 report={'motion_before':before,'npu_before':{'status':rd(0x63f01014),'irq':rd(0x63f01018)},'register':'0xf8801074','mask':4096}
 fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
 try:
  with mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0xf8801000) as m:
   initial=struct.unpack_from('<I',m,0x74)[0];assert initial&4096,hex(initial)
   reg=ctypes.c_uint32.from_buffer(m,0x74)
   try:
    reg.value=initial&~4096;assert struct.unpack_from('<I',m,0x74)[0]==(initial&~4096)
    time.sleep(.001)
   finally:
    reg.value=reg.value|4096
    final=struct.unpack_from('<I',m,0x74)[0];del reg
   assert final==initial,(initial,final)
   report.update(reset_before=initial,reset_after=final)
 finally:os.close(fd)
 time.sleep(.05)
 report['npu_after']={'status':rd(0x63f01014),'irq':rd(0x63f01018)}
 report['motion_after']=motion_state();assert report['motion_after']==before
 report['passed']=True
print('NPU_RESET='+json.dumps(report,separators=(',',':')),flush=True)
