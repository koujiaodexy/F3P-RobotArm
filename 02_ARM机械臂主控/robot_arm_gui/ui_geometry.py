"""Pure placement helper for the touch editor; no control dependencies."""
def keyboard_position(target, size, workarea):
    x,y,w,h=target;dw,dh=size;ax,ay,aw,ah=workarea
    def clamp(px,py):return (max(ax,min(px,ax+max(0,aw-dw))),max(ay,min(py,ay+max(0,ah-dh))))
    candidates=[clamp(x-dw-20,y),clamp(x+w+20,y),clamp(x,y-dh-20),clamp(x,y+h+20)]
    def score(p):
        px,py=p
        overlap=max(0,min(px+dw,x+w)-max(px,x))*max(0,min(py+dh,y+h)-max(py,y))
        return overlap,abs(px-x)+abs(py-y)
    return min(candidates,key=score)
