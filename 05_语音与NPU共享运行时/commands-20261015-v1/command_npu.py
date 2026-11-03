#!/usr/bin/python3
"""Experimental Chinese command classifier on the real hard NPU; suggestions only."""
import argparse
from array import array
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from command_policy import decide

BASE=Path(__file__).resolve().parent
SHARED=Path('/opt/f3p-npu/hard-only-20261015-01/runtime')

def irqs():
    lines=Path('/proc/interrupts').read_text().splitlines();n=len(lines[0].split())
    return sum(int(v) for line in lines if 'HARD_NPU_IRQ' in line for v in line.split()[1:1+n])

def check_files():
    manifest=json.loads((BASE/'manifest.json').read_text())
    for root,key in ((BASE,'sha256'),(SHARED,'shared_sha256')):
        for name,wanted in manifest[key].items():
            path=(root/name).resolve()
            if root not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest()!=wanted:
                raise RuntimeError('Pinned deployment integrity failed: '+name)
    return manifest

def infer(tensor,work,cpu=False):
    env=dict(os.environ,LD_LIBRARY_PATH=str(SHARED/'lib'));env.pop('LD_PRELOAD',None)
    if cpu: env['NPU_REFERENCE_CPU']='1'
    else: env.pop('NPU_REFERENCE_CPU',None)
    output=work/'output.bin';before=irqs()
    result=subprocess.run([str(SHARED/'hard_npu_hybrid_runner'),str(BASE/'commands-uint8.onnx'),str(tensor),str(output)],
                env=env,cwd=str(BASE),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=45)
    delta=irqs()-before;(work/'inference.log').write_text(result.stdout)
    if result.returncode: raise RuntimeError('Model inference failed: '+result.stdout[-1200:])
    count=re.search(r'hard_workloads=(\d+)',result.stdout);count=int(count.group(1)) if count else -1
    if (not cpu and (count<5 or delta<=0)) or (cpu and (count!=0 or delta!=0)):
        raise RuntimeError('Backend evidence does not match requested mode')
    values=array('f',output.read_bytes())
    if sys.byteorder!='little': values.byteswap()
    if not all(math.isfinite(x) for x in values): raise RuntimeError('Non-finite NPU output')
    timing=re.search(r'elapsed_ms=([0-9.]+)',result.stdout)
    return dict(scores=list(values),irq_delta=delta,hard_workloads=count,
                model_compute_ms=float(timing.group(1)) if timing else None,backend='CpuRef' if cpu else 'Alnpu+CpuRef')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--wav',type=Path);group.add_argument('--tensor',type=Path);group.add_argument('--self-test',action='store_true')
    parser.add_argument('--cpu-reference',action='store_true');args=parser.parse_args()
    if os.geteuid()!=0: raise RuntimeError('Run with sudo for NPU/CMA device access')
    with (SHARED/'.inference.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('NPU is busy')
        manifest=check_files()
        ready=subprocess.run([sys.executable,str(SHARED/'load_hard_drivers.py')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=20)
        if ready.returncode: raise RuntimeError(ready.stdout)
        work=BASE/'runs'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+str(os.getpid()))
        work.mkdir(parents=True)
        start=time.monotonic()
        if args.self_test or args.wav:
            source=BASE/'samples/stop.wav' if args.self_test else args.wav.resolve()
            tensor=work/'input.bin'
            result=subprocess.run([str(BASE/'command_wav_to_tensor'),str(source),str(tensor)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=20)
            if result.returncode: raise RuntimeError('WAV frontend failed: '+result.stdout)
        else: tensor=args.tensor.resolve()
        if tensor.stat().st_size!=48000: raise RuntimeError('Invalid input tensor size')
        values=array('f',tensor.read_bytes())
        if sys.byteorder!='little': values.byteswap()
        if not all(math.isfinite(v) and 0<=v<=1 for v in values): raise RuntimeError('Invalid feature range')
        report=infer(tensor,work,args.cpu_reference)
        catalog=json.loads((BASE/'commands.json').read_text());gate=json.loads((BASE/'rejection-policy.json').read_text())
        report.update(status='experimental_synthetic_trained_model',decision=decide(report['scores'],catalog,gate),
                      run_directory=str(work),pipeline_wall_ms=(time.monotonic()-start)*1000,
                      real_recording_validation=False,robot_commands_enabled=False,
                      model_sha256=manifest['sha256']['commands-uint8.onnx'])
        if args.self_test: report['self_test_recognized']=report['decision'].get('intent')=='STOP'
        (work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))

if __name__=='__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'status':'failed','error':str(error),'robot_commands_enabled':False}),file=sys.stderr);sys.exit(2)
