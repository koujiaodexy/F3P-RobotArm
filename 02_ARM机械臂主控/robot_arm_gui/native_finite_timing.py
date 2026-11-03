"""Optional batch equivalents of the local timing guards, with Python fallback."""
import ctypes as c
import os,math
from pathlib import Path
from .native_math import POINTER,array

LIBRARY=None
if os.environ.get('F3P_DISABLE_NATIVE')!='1':
    try:
        lib=c.CDLL(str(Path(__file__).parent/'native'/('finite_timing.dll' if os.name=='nt' else 'finite_timing.so')))
        lib.f3p_finite_timing_abi.restype=c.c_int
        if lib.f3p_finite_timing_abi()!=1:raise RuntimeError('finite timing ABI mismatch')
        lib.f3p_timing_samples.argtypes=[POINTER]+[c.c_double]*4;lib.f3p_timing_samples.restype=c.c_int
        lib.f3p_timing_envelope.argtypes=[POINTER]+[c.c_double]*3+[POINTER,c.c_int]+[POINTER]*3+[c.c_int]
        lib.f3p_timing_envelope.restype=c.c_int
        lib.f3p_timing_chords.argtypes=[POINTER]*3+[c.c_int,POINTER,c.c_int,c.c_double]
        lib.f3p_timing_chords.restype=c.c_int
        lib.f3p_timing_peak.argtypes=[POINTER,c.c_int];lib.f3p_timing_peak.restype=c.c_double
        lib.f3p_timing_q_batch.argtypes=[POINTER,c.c_int,POINTER,c.c_int,POINTER];lib.f3p_timing_q_batch.restype=c.c_int
        lib.f3p_guide_max_rates.argtypes=[POINTER,c.c_int,POINTER,POINTER];lib.f3p_guide_max_rates.restype=None
        lib.f3p_guide_samples.argtypes=[POINTER]*6;lib.f3p_guide_samples.restype=c.c_int
        LIBRARY=lib
    except (OSError,AttributeError,RuntimeError):pass

def enabled(curve):
    return LIBRARY is not None and curve.args.get('finite_complete') and not curve.adaptive and curve.native_fused

def packed_guides(curve):
    cached=getattr(curve,'_timing_guides',None)
    if cached is None or cached[0]!=len(curve.segments):
        cached=(len(curve.segments),array([v for left,right,guide in curve.segments
                                         for v in [left,right]+[v for q in guide for v in q]]))
        curve._timing_guides=cached
    return cached

def guide_max_rates(curve):
    if not enabled(curve):return None
    count,guides=packed_guides(curve);out=array([0.]*12);curve.check()
    LIBRARY.f3p_guide_max_rates(guides,count,array(curve.ratios),out);curve.check()
    return list(out[:6]),list(out[6:])

def guide_samples(curve,coeff,left,span):
    if not enabled(curve):return None
    curve.check();out=array([0.,0.])
    points=array([v for x in (.25,.5,.75,1.) for v in curve.point(left+span*x)])
    limits=array([v for pair in curve.limits for v in (pair or (-math.inf,math.inf))])
    result=LIBRARY.f3p_guide_samples(curve.model._native_geometry,curve.native_origin,
                                    array([v for q in coeff for v in q]),points,limits,out)
    curve.check();return result,list(out)

def samples(coeff,u,end,duration,cap):
    if LIBRARY is None:return None
    return LIBRARY.f3p_timing_samples(array(coeff),u,end,duration,cap)

def peak(curve):
    if not enabled(curve):return None
    result=LIBRARY.f3p_timing_peak(array([v for _,duration,coeff in curve.schedule for v in [duration]+coeff]),len(curve.schedule))*curve.length
    if not math.isfinite(result):raise ValueError('原生进给峰值无效')
    return result

def joints(curve,values):
    if not enabled(curve) or not curve.segments or max(values)>curve.guide_u+1e-12:return None
    curve.check();count,guides=packed_guides(curve);out=array([0.]*(6*len(values)))
    if not LIBRARY.f3p_timing_q_batch(guides,count,array(values),len(values),out):return None
    curve.check();return [list(out[k*6:k*6+6]) for k in range(len(values))]

def envelope(curve,coeff,duration,u,end,preview=False):
    if not enabled(curve):return None
    count,guides=packed_guides(curve);curve.check()
    result=LIBRARY.f3p_timing_envelope(array(coeff),duration,u,end,guides,count,
                                     array(curve.ratios),array(curve.nominal),array(curve.rates),int(preview))
    curve.check();return result

def chords(curve,values,rates):
    if not enabled(curve):return None
    bounds=[]
    for lo,rate in zip(values,rates):
        if not math.isfinite(rate) or rate<0:raise ValueError('原生前瞻速度无效')
        bounds.append((lo,min(1.,lo+rate*curve.ahead)))
    curve.q(max(hi for _,hi in bounds));count,guides=packed_guides(curve)
    packed=[]
    for lo,hi in bounds:
        curve.check();packed.extend((lo,hi))
        for fraction in (.25,.5,.75):packed.extend(curve.point(lo+fraction*(hi-lo)))
    result=LIBRARY.f3p_timing_chords(curve.model._native_geometry,curve.native_origin,
                                   guides,count,array(packed),len(bounds),curve.path_budget)
    curve.check();return None if result<0 else bool(result)
