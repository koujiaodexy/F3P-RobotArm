"""Strict persistent hard-NPU inference with the existing voice ownership lock."""
import fcntl,json,math,mmap,os,select,subprocess,time
from pathlib import Path
import numpy as np
from yolo_decode import unpack_heads,class_mapping,decode_candidates

SHARED=Path('/opt/f3p-npu/hard-only-20261015-01/runtime')

def irqs():
    lines=Path('/proc/interrupts').read_text().splitlines();cpus=len(lines[0].split())
    return sum(int(v) for line in lines if 'HARD_NPU_IRQ' in line for v in line.split()[1:1+cpus])

class AlnpuDetector:
    def __init__(self,root,directory,stop,model_class_ids=None,input_size=320,model_name='yolov8n-320-uint8.onnx',backend='Alnpu+CpuRef'):
        self.root,self.directory,self.stop=Path(root),Path(directory),stop
        if input_size not in (192,256,320,384) or Path(model_name).name!=model_name:raise ValueError('Invalid model configuration')
        self.input_size,self.backend=input_size,backend
        self.cells=sum((input_size//s)**2 for s in (8,16,32))
        self.model_class_ids=class_mapping(model_class_ids)
        self.output_channels=64+len(self.model_class_ids)
        self.lock=self.log=self.errors=self.process=None;self.buffer=b'';self.sequence=0
        self.image_file=self.image_map=self.shared_image=None
        try:
            self.lock=(SHARED/'.inference.lock').open('a')
            deadline=time.monotonic()+20
            while True:
                try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if self.stop.wait(.05) or time.monotonic()>deadline:raise RuntimeError('等待语音释放NPU超时，请结束识别后重试')
            self.log=(self.directory/'npu-stdout.log').open('ab')
            self.errors=(self.directory/'npu-stderr.log').open('ab')
            env=dict(os.environ,LD_LIBRARY_PATH=str(SHARED/'lib'))
            env['F3P_NPU_LOCK_FD']=str(self.lock.fileno())
            env.pop('LD_PRELOAD',None);env.pop('NPU_REFERENCE_CPU',None)
            self.process=subprocess.Popen([str(self.root/'coco_npu_server'),str(self.root/model_name),str(self.directory)],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.errors,cwd=str(self.directory),env=env,
                close_fds=True,pass_fds=(self.lock.fileno(),))
            os.set_blocking(self.process.stdout.fileno(),False)
            self.ready=self._wait('COCO_NPU_READY ',45)
            if self.ready.get('backend')!=backend or type(self.ready.get('hard_workloads')) is not int or self.ready['hard_workloads']<=0:
                raise RuntimeError('没有实际硬NPU工作负载，已拒绝纯CPU结果')
            if self.ready.get('class_count',80)!=len(self.model_class_ids):raise RuntimeError('模型输出类别数与类别映射不符')
            if self.ready.get('input_size',320)!=input_size:raise RuntimeError('模型图像尺寸与配置不符')
            if self.ready.get('shared_input'):
                self.image_file=(self.directory/'input.u8').open('r+b')
                self.image_map=mmap.mmap(self.image_file.fileno(),3*input_size*input_size,access=mmap.ACCESS_WRITE)
                self.shared_image=np.ndarray((1,3,input_size,input_size),dtype=np.uint8,buffer=self.image_map)
        except BaseException:self.close();raise

    def _wait(self,prefix,timeout,cancellable=True):
        began=time.monotonic()
        while time.monotonic()-began<timeout:
            while b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                text=line.decode('utf8','replace')
                if text.startswith(prefix):return json.loads(text[len(prefix):])
            if cancellable and self.stop.is_set():raise RuntimeError('物品识别已取消')
            if self.process.poll() is not None:
                self.errors.flush();detail=(self.directory/'npu-stderr.log').read_text(errors='replace')[-1800:]
                raise RuntimeError('硬NPU模型未能运行：'+detail)
            available,_,_=select.select([self.process.stdout],[],[],.05)
            if available:
                data=os.read(self.process.stdout.fileno(),65536)
                # Keep a bounded recent diagnostic window in /run tmpfs.
                if self.log.tell()+len(data)>1048576:
                    self.log.seek(0);self.log.truncate()
                self.log.write(data);self.log.flush();self.buffer+=data
                if len(self.buffer)>262144:raise RuntimeError('NPU输出协议超出限制')
        raise RuntimeError('硬NPU推理回复超时')

    def infer(self,tensor,geometry=None):
        python_started=time.monotonic()
        byte_protocol=tensor.dtype==np.uint8
        if tensor.shape!=(1,3,self.input_size,self.input_size) or (not byte_protocol and (not np.isfinite(tensor).all() or tensor.min()<0 or tensor.max()>1)):
            raise ValueError('物品图像输入无效')
        if byte_protocol and not self.ready.get('uint8_protocol'):raise RuntimeError('NPU服务不支持字节输入')
        compact=geometry is not None
        if compact and (not byte_protocol or not self.ready.get('native_candidates')):raise RuntimeError('NPU服务不支持紧凑检测输出')
        if byte_protocol and self.shared_image is not None:np.copyto(self.shared_image,tensor)
        else:
            temporary=self.directory/'input.pending'
            (tensor if byte_protocol else tensor.astype('<f4',copy=False)).tofile(temporary);temporary.replace(self.directory/'input.bin')
        self.sequence+=1;before=irqs() if not byte_protocol else None
        write_done=time.monotonic()
        self.process.stdin.write(('%s %d\n'%('DETECT' if compact else ('RUNU8' if byte_protocol else 'RUN'),self.sequence)).encode());self.process.stdin.flush()
        result=self._wait('COCO_NPU_FRAME ',20,cancellable=False)
        # The pinned native server also samples real /proc IRQ counters while
        # holding the same ownership lease. Byte mode avoids two duplicate
        # Python /proc parses; it still requires its actual per-frame IRQ proof.
        delta=irqs()-before if before is not None else result.get('hard_irq',0)
        if (result.get('seq')!=self.sequence or result.get('hard_workloads')!=self.ready['hard_workloads'] or delta<=0
                or type(result.get('model_compute_ms')) not in (int,float) or not math.isfinite(result['model_compute_ms']) or result['model_compute_ms']<0):
            raise RuntimeError('本帧硬NPU执行证据不符，已丢弃结果')
        result['python_input_ms']=1000*(write_done-python_started)
        result['python_wait_ms']=1000*(time.monotonic()-write_done)
        if compact:
            rows=decode_candidates(result.pop('candidates',None),geometry,model_class_ids=self.model_class_ids)
            result.update(backend=self.backend,irq_delta=delta,python_total_ms=1000*(time.monotonic()-python_started))
            return rows,result
        path=self.directory/'output.bin'
        if byte_protocol:
            if result.get('quantized_output') is not True or path.stat().st_size!=self.output_channels*self.cells:raise RuntimeError('NPU字节输出格式不符')
            raw=np.fromfile(path,dtype=np.uint8);heads=[];begin=0
            for level in range(3):
                grid=self.input_size//(8<<level);parts=[]
                for part,channels in enumerate((64,len(self.model_class_ids))):
                    info=self.ready['quantized_heads'][2*level+part];count=channels*grid*grid
                    if info['elements']!=count or not math.isfinite(info['scale']) or info['scale']<=0:raise RuntimeError('无效输出量化参数')
                    values=raw[begin:begin+count];begin+=count
                    if info['signed']:values=values.view(np.int8)
                    parts.append((values.astype(np.float32)-info['offset'])*np.float32(info['scale']))
                heads.append(np.concatenate(parts).reshape(1,self.output_channels,grid,grid))
            result.update(backend=self.backend,irq_delta=delta);return heads,result
        if path.stat().st_size!=self.output_channels*self.cells*4:raise RuntimeError('NPU输出张量长度不符')
        raw=np.fromfile(path,dtype='<f4').reshape(1,self.output_channels,self.cells)
        if not np.isfinite(raw).all():raise RuntimeError('NPU输出包含非有限数值')
        if self.backend=='Alnpu' and result.get('soft_irq',0)<=0:raise RuntimeError('本帧缺少真实SoftNPU执行证据')
        result.update(backend=self.backend,irq_delta=delta)
        return unpack_heads(raw,input_size=self.input_size,model_class_ids=self.model_class_ids),result

    def close(self):
        if self.process is not None:
            try:
                if self.process.poll() is None:
                    try:self.process.stdin.write(b'QUIT\n');self.process.stdin.flush()
                    except (OSError,BrokenPipeError):pass
                    # QUIT is handled after the hardware request returns. Do not
                    # kill a driver call and strand the shared NPU state.
                    self.process.wait(timeout=30)
            finally:
                for stream in (self.process.stdin,self.process.stdout):
                    if stream:stream.close()
                self.process=None
        self.shared_image=None
        if self.image_map:self.image_map.close();self.image_map=None
        for name in ('image_file','log','errors','lock'):
            stream=getattr(self,name,None)
            if stream:stream.close();setattr(self,name,None)
