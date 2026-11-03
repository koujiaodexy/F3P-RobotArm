"""Display calculated joint curves; never submits motion commands."""
from gi.repository import Gtk, GdkPixbuf


class BlendPreviewDialog(Gtk.Dialog):
    COLORS = ((.15,.65,1),(.95,.5,.15),(.25,.8,.45),(.85,.4,.8),(.9,.8,.25),(.6,.65,.75))

    def __init__(self, window, report):
        super().__init__(title='关节融合轨迹预览',transient_for=window,modal=True)
        self.report = report
        self.add_buttons('关闭',Gtk.ResponseType.CLOSE)
        self.set_default_size(920,600)
        box = self.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)
        v,a,j = report['derivative_bounds']
        summary = Gtk.Label(xalign=0,label=f'预计 {report["total_seconds"]:.2f} 秒 · 融合 {len(report["blended_points"])} 点 · 最大单关节偏差 {report["radius_deg"]:.2f}°\n'
            f'曲线包络上界：速度 {v:.2f}°/s，加速度 {a:.2f}°/s²，变化率 {j:.2f}°/s³')
        box.pack_start(summary,False,False,0)
        note = Gtk.Label(xalign=0,label='仅规划预览，不发送运动指令。加速度上限5°/s²、变化率20°/s³为规划默认值，尚未做实机标定。')
        note.set_line_wrap(True)
        box.pack_start(note,False,False,0)
        loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
        loader.write(self.chart_svg().encode('utf-8'))
        loader.close()
        self.chart = Gtk.Image.new_from_pixbuf(loader.get_pixbuf())
        chart = self.chart
        box.pack_start(chart,True,True,0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.set_size_request(-1,110)
        details = []
        for i,name in enumerate(report['point_names'],1):
            state = f'平滑通过，偏差≤{report["blended_points"][i]:.2f}°' if i in report['blended_points'] else '精确停车：'+report['stop_points'].get(i,'姿态点')
            details.append(f'{i}. {name} · {state}')
        text = Gtk.Label(xalign=0,yalign=0,label='\n'.join(details))
        text.set_selectable(True)
        scroll.add(text)
        box.pack_start(scroll,False,False,0)

    def chart_svg(self):
        report = self.report
        width,height = 860,300
        left,top,plot_w,plot_h = 60,30,width-80,height-60
        values = [value for _,pose in report['samples'] for value in pose]
        low,high = min(values)-1,max(values)+1
        total = max(report['total_seconds'],1e-9)
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            '<rect width="100%" height="100%" fill="#171f2b"/>']
        for k in range(5):
            y=top+plot_h*k/4
            parts += [f'<path d="M {left} {y} H {left+plot_w}" stroke="#657380" fill="none"/>',
                f'<text x="4" y="{y+4}" fill="#d0d8e0" font-size="12">{high-(high-low)*k/4:.1f}</text>']
        for col,node in enumerate(report['nodes']):
            color='#'+''.join(f'{round(c*255):02x}' for c in self.COLORS[node-1])
            coords=' '.join(f'{left+plot_w*seconds/total:.3f},{top+plot_h*(high-pose[col])/(high-low):.3f}'
                for seconds,pose in report['samples'])
            parts += [f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2"/>',
                f'<text x="{left+col*75}" y="17" fill="{color}" font-size="12">J{node}</text>']
        parts += [f'<text x="{left}" y="{height-8}" fill="#d0d8e0" font-size="12">0 s</text>',
            f'<text x="{width-115}" y="{height-8}" fill="#d0d8e0" font-size="12">{report["total_seconds"]:.2f} s</text>','</svg>']
        return ''.join(parts)
