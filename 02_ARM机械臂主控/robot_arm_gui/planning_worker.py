"""Math worker entry point. No controller, CAN, GTK, or MMIO is imported."""
import contextlib,os,sys,time,threading
from .planner_process import send,receive,source_identity

def main():
    # PR_SET_PDEATHSIG follows the creating thread on Linux. Preparation
    # threads finish while the GUI is alive, so watch the process instead.
    if sys.platform.startswith('linux'):
        parent=int(os.environ.get('F3P_PLANNER_PARENT_PID') or os.getppid())
        if os.getppid()!=parent:return
        def watch_parent():
            while os.getppid()==parent:time.sleep(.1)
            os._exit(0)
        threading.Thread(target=watch_parent,name='planner-parent-watch',daemon=True).start()
        # Inherit the caller's allowed CPUs. Pinning to the final core makes
        # preparation compete with desktop rendering even when another core
        # is idle; the math process remains separate from GUI and hardware IO.
    output=sys.stdout.buffer;frames=None
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from .reference_adapter import _plan_rolling_inline,_plan_cartesian_inline
            from .native_math import LIBRARY
            # Load the grasp math while this process is still idle. Importing
            # it after the target arrives defeats prewarming on the ARM CPU.
            from . import grasp_motion, grasp_transfer, analytic_inverse, native_analytic_inverse, driver_tracking
            while True:
                request=receive(sys.stdin.buffer)
                operation=request['operation'];args=request['args']
                if operation=='rolling':
                    try:report=_plan_rolling_inline(**args,check=lambda:None)
                    except ValueError as exc:
                        report=_plan_cartesian_inline(**args,check=lambda:None)
                        report['rolling_fallback_reason']=str(exc)
                elif operation=='progressive':report=_plan_rolling_inline(**args,check=lambda:None)
                elif operation=='full':report=_plan_cartesian_inline(**args,check=lambda:None)
                elif operation=='grasp_transfer':
                    from .grasp_transfer import plan_inline
                    report=plan_inline(**args,check=lambda:None)
                elif operation=='grasp_cycle':
                    from .grasp_transfer import plan_cycle_inline
                    report=plan_cycle_inline(**args,check=lambda:None)
                elif operation=='grasp_prepare':
                    from .grasp_transfer import prepare_cycle_inline
                    report=prepare_cycle_inline(**args,check=lambda:None)
                else:raise ValueError('unknown planner operation')
                native=report['native_report'];backend='cpp-double-gil-released' if LIBRARY is not None else 'python'
                if operation=='rolling' and args['hardware'].get('finite_complete'):
                    if native.get('rolling') and (not native.get('complete_before_start') or not native['frames'].complete):
                        raise ValueError('有限路径整段预检未完成；未发布运动指令')
                    if not native.get('driver_response_checks'):
                        from .reference_adapter import make_model
                        from .driver_tracking import validate
                        model=make_model(args['start'],args['bounds'],args['hardware'].get('calibration'))
                        native['driver_response_checks']=validate(model,native['start_motor_deg'],native['frames'],lambda:None,
                            'line' if args['mode']=='L' else 'arc')
                    native['complete_before_start']=True
                if not native.get('rolling'):
                    packed=native['frames']
                    encoded=dict(report,native_report=dict(native,frames=dict(packed_bytes=packed._data)))
                    send(output,dict(type='ready',report=encoded,math_backend=backend,source_identity=source_identity()))
                    if operation=='grasp_prepare':continue
                    return
                frames=native['frames']
                with frames.lock:
                    head=list(frames.head);reserve=list(frames.reserve);index=len(head)
                    snapshot=dict(native);snapshot.pop('frames')
                plain=dict(report,native_report=snapshot,total_seconds=snapshot['duration_s'])
                send(output,dict(type='ready',report=plain,head=head,reserve=reserve,math_backend=backend,source_identity=source_identity()))
                gate=getattr(frames,'background_ready',None)
                if gate is not None:gate.set()
                while True:
                    with frames.lock:
                        ready=len(frames.head);complete=frames.complete;error=frames.error
                        head=list(frames.head[index:ready]);reserve=list(frames.reserve)
                        updates={k:v for k,v in native.items() if k!='frames'}
                    if head:
                        send(output,dict(type='block',head=head,reserve=reserve,updates=updates))
                        with frames.lock:
                            frames.consumed=ready
                            for i in range(frames.discarded,index):frames.head[i]=None
                            frames.discarded=index
                        index=ready
                    if error:raise ValueError(error)
                    if complete and index==ready:send(output,dict(type='done'));return
                    time.sleep(.005)
    except Exception as exc:
        try:send(output,dict(type='error',error=str(exc),details={key:getattr(exc,key) for key in ('joint_step_degrees','path_fraction','failure_kind') if hasattr(exc,key)}))
        except (BrokenPipeError,OSError):pass
    finally:
        if frames:frames.close()

if __name__=='__main__':main()
