"""Workspace XY slice inside the existing lower-left Cartesian panel."""
from gi.repository import Gtk,GdkPixbuf
from . import kinematics as k


class WorkspacePanel(Gtk.Expander):
    def __init__(self,page):
        Gtk.Expander.__init__(self,label='非矩形工作区 · 当前高度截面')
        self.page=page;self.snapshot=None;self.rows=[];self.key=None
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        self.direction=Gtk.ComboBoxText()
        for key,label in (('auto','按目标朝向'),('plus_x','+X 前向'),('minus_x','−X 后向'),('plus_y','+Y'),('minus_y','−Y'),('plus_z','+Z 向上'),('minus_z','−Z 向下'),('union','六朝向合并 · 仅供参考')):self.direction.append(key,label)
        self.direction.set_active_id('auto');self.direction.connect('changed',lambda _w:self.update())
        box.pack_start(self.direction,False,False,0)
        self.notice=Gtk.Label(xalign=0);self.notice.set_line_wrap(True);self.notice.set_max_width_chars(70)
        box.pack_start(self.notice,False,False,0)
        self.canvas=Gtk.Image();self.canvas.set_size_request(300,220)
        box.pack_start(self.canvas,False,False,0)
        legend=Gtk.Label(label='蓝色：理论可达样本 · 绿点：最近反馈位置 · 红点：目标\n边缘使用精确逆解；工作区内仍须检查轨迹，未做碰撞检测。',xalign=0)
        legend.set_line_wrap(True);box.pack_start(legend,False,False,0);self.add(box)
        self.connect('notify::expanded',lambda *_:self.update())

    def update(self):
        if not self.get_expanded() or not self.get_mapped():return
        p=self.page;m=p.model;ws=m.workspace
        xyz=[v.get_value() for v in p.xyz]
        pose=m.cached_pose() if p.usage.get_active_id()=='live' else k.forward([v.get_value() for v in p.seeds])
        rotation=k.pose_from_rpy(xyz,[v.get_value() for v in p.rpy])['rotation'] if p.mode.get_active_id()=='J' else (pose or k.forward([0]*6))['rotation']
        goal=dict(position_mm=xyz,rotation=rotation)
        state,key=ws.classify(goal,p.task.controller.joint_limits.bounds,m.calibration)
        chosen=self.direction.get_active_id()
        key=(key or 'union') if chosen=='auto' else chosen
        z=round(xyz[2]/10)*10
        compatible=ws.compatible(p.task.controller.joint_limits.bounds,m.calibration)
        signature=(key,z,state,compatible,tuple(xyz),tuple((pose or {}).get('position_mm',[])))
        if signature==self.snapshot:return
        self.snapshot=signature;self.key=key;self.goal=xyz;self.pose=pose
        self.rows=ws.slice_rows(key,z) if compatible else []
        status={'sampled':'目标位于规整工作区','exact':'目标在规整边界外，需精确复核','arbitrary':'任意朝向：合并区仅供参考','unavailable':'限位、模型或标定未匹配，工作区预检查已停用'}[state]
        if chosen not in ('auto',ws.direction(goal)) and state!='unavailable':status+='；所选截面仅供参考'
        self.notice.set_text('Z=%d mm · %s'%(z,status));self.draw()

    def draw(self):
        w=500;h=220;scale=min(w-60,h-35)/800
        ox=w/2;oy=h/2
        svg=['<svg xmlns="http://www.w3.org/2000/svg" width="500" height="220"><rect width="100%" height="100%" fill="#171f2b"/>']
        for n in range(-300,401,100):
            svg.append('<path d="M %.2f %.2f V %.2f M %.2f %.2f H %.2f" stroke="#536376"/>'%(ox+n*scale,oy-380*scale,oy+380*scale,ox-380*scale,oy-n*scale,ox+380*scale))
            svg.append('<text x="%.2f" y="212" fill="#c9d7e2" font-size="10" text-anchor="middle">%d</text>'%(ox+n*scale,n))
        for y,runs in self.rows:
            for lo,hi in runs:svg.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="#3685b5"/>'%(ox+(lo-5)*scale,oy-(y+5)*scale,(hi-lo+10)*scale,10*scale))
        for xyz,color in ((getattr(self,'goal',None),'#ee695b'),((getattr(self,'pose',None) or {}).get('position_mm'),'#57c99a')):
            if xyz is None:continue
            svg.append('<circle cx="%.2f" cy="%.2f" r="4" fill="%s"/>'%(ox+xyz[0]*scale,oy-xyz[1]*scale,color))
        svg.append('<text x="455" y="212" fill="#c9d7e2" font-size="11">X mm</text><text x="8" y="15" fill="#c9d7e2" font-size="11">Y mm</text></svg>')
        loader=GdkPixbuf.PixbufLoader.new_with_type('svg');loader.write(''.join(svg).encode());loader.close();self.canvas.set_from_pixbuf(loader.get_pixbuf())
