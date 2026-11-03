"""Optional main-thread-only GTK/Cairo draw adapter; bitmap renderer is fallback."""
import ctypes as c
import os
import threading
from pathlib import Path
from gi.repository import GdkPixbuf,GLib
LIBRARY=None;LOAD_ERROR=''
try:
    if os.environ.get('F3P_DISABLE_NATIVE_CANVAS')=='1':raise OSError('disabled')
    lib=c.CDLL(os.environ.get('F3P_NATIVE_CANVAS_PATH') or str(Path(__file__).parent/'native/canvas.so'))
    lib.f3p_canvas_abi.restype=c.c_int
    if lib.f3p_canvas_abi()!=1:raise OSError('canvas ABI mismatch')
    P=c.c_void_p;D=c.c_double;I=c.c_int;DP=c.POINTER(D)
    lib.f3p_canvas_new.argtypes=[P];lib.f3p_canvas_new.restype=P
    lib.f3p_canvas_prepare.argtypes=[P,I,I,P,P,I,I,P,I,I,D,D,I];lib.f3p_canvas_prepare.restype=I
    lib.f3p_canvas_append.argtypes=[P,DP,I,DP,I,D,D];lib.f3p_canvas_append.restype=I
    lib.f3p_canvas_seed.argtypes=[P,DP,I,D,D];lib.f3p_canvas_seed.restype=None
    lib.f3p_canvas_deactivate.argtypes=[P];lib.f3p_canvas_deactivate.restype=None
    lib.f3p_canvas_snapshot.argtypes=[P];lib.f3p_canvas_snapshot.restype=P
    lib.f3p_canvas_painted.argtypes=[P];lib.f3p_canvas_painted.restype=c.c_uint
    lib.f3p_canvas_draw_ms.argtypes=[P];lib.f3p_canvas_draw_ms.restype=c.c_double
    lib.f3p_canvas_draw_area.argtypes=[P];lib.f3p_canvas_draw_area.restype=c.c_double
    capsule=c.pythonapi.PyCapsule_GetPointer;capsule.argtypes=[c.py_object,c.c_char_p];capsule.restype=P
    LIBRARY=lib
except (OSError,AttributeError) as exc:LOAD_ERROR=str(exc)
if os.environ.get('F3P_REQUIRE_NATIVE_CANVAS')=='1' and LIBRARY is None:raise RuntimeError(LOAD_ERROR)

def pointer(value):return capsule(value.__gpointer__,None) if value is not None else None
class NativeCanvas:
    def __init__(self,widget):
        self.thread=threading.get_ident()
        self.state=LIBRARY.f3p_canvas_new(pointer(widget));self.active=False;self.ready=False;self.revision=0
        widget.connect('destroy',self.destroyed)
    def destroyed(self,*_):
        # The C draw closure owns and frees its state with the widget.
        self.state=None;self.active=False;self.ready=False
    def check_thread(self):
        if threading.get_ident()!=self.thread:raise RuntimeError('GTK canvas is owned by its UI thread')
    def prepare(self,cache,regions,w,h,last,markers,target):
        self.check_thread()
        self.ready=bool(LIBRARY.f3p_canvas_prepare(self.state,w,h,pointer(cache[0][1]),pointer(cache[1][1]),*regions[1][:2],pointer(cache[4][1]),*regions[4][:2],*(last or (0,0)),bool(last)))
        self.active=self.ready;self.size=(w,h)
        if self.ready:self.revision+=1
        mk=(c.c_double*(4*len(markers)))(*(v for p in markers for v in p))
        LIBRARY.f3p_canvas_seed(self.state,mk,len(markers),*target)
    def append(self,coords,markers,target):
        self.check_thread()
        xy=(c.c_double*(2*len(coords)))(*(v for p in coords for v in p));mk=(c.c_double*(4*len(markers)))(*(v for p in markers for v in p))
        if not LIBRARY.f3p_canvas_append(self.state,xy,len(coords),mk,len(markers),*target):return False
        self.active=True;self.revision+=1;return True
    def deactivate(self):
        self.check_thread()
        LIBRARY.f3p_canvas_deactivate(self.state);self.active=False;self.ready=False
    def presented(self):return LIBRARY.f3p_canvas_painted(self.state)>=self.revision
    def draw_stats(self):return (LIBRARY.f3p_canvas_draw_ms(self.state),LIBRARY.f3p_canvas_draw_area(self.state))
    def pixbuf(self):
        self.check_thread()
        raw=LIBRARY.f3p_canvas_snapshot(self.state)
        if not raw:return None
        w,h=self.size;data=GLib.Bytes.new(c.string_at(raw,w*h*4))
        return GdkPixbuf.Pixbuf.new_from_bytes(data,GdkPixbuf.Colorspace.RGB,True,8,w,h,w*4)
