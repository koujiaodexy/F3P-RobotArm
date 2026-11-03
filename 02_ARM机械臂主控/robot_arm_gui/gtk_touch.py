"""Single-contact input for custom controls; native GTK clicks stay native."""
from types import SimpleNamespace
from gi.repository import Gdk, Gtk

def touch_window_header(window):
    """Use a finger-sized close target and the existing delete-event handler."""
    header=Gtk.Box(spacing=12)
    header.pack_start(Gtk.Label(label=window.get_title(),xalign=0),True,True,0)
    button=Gtk.Button(label='关闭窗口');button.set_size_request(132,56)
    button.set_can_focus(False);button.connect('clicked',lambda *_:window.close())
    header.pack_end(button,False,False,0)
    content=window.get_content_area()if isinstance(window,Gtk.Dialog)else window.get_child()
    content.pack_start(header,False,False,0);content.reorder_child(header,0);header.show_all()
    window._f3p_close_button=button
    return button

class StatusEntry(Gtk.Entry):
    """Selectable live text with a requisition independent of its contents.

    Unlike GtkLabel.set_text(), GtkEntry updates its text without invalidating
    the surrounding layout. This is restricted to single-line live status and
    diagnostics; commands and editable controls keep their existing widgets.
    """
    def __init__(self,label='',xalign=0):
        super().__init__()
        self.set_editable(False);self.set_has_frame(False);self.set_alignment(xalign)
        provider=Gtk.CssProvider()
        provider.load_from_data(b'entry {min-height: 0; padding: 0; border: 0; background: transparent; font-size: inherit;}')
        self.get_style_context().add_provider(provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        self.set_text(label)
    def set_text(self,value):
        Gtk.Entry.set_text(self,' '.join(value.splitlines()))
        self.set_tooltip_text(value)
        self.set_position(0)
    def set_xalign(self,value):self.set_alignment(value)
    def reserve_text(self,chars,lines):
        from gi.repository import Pango
        import math
        self._status_reserved=True
        self.set_width_chars(chars);self.set_max_width_chars(chars)
        def measure(*_):
            context=self.get_pango_context()
            font=self.get_style_context().get_font(self.get_state_flags()).copy()
            font.set_weight(Pango.Weight.NORMAL)
            key=(font.to_string(),self.get_scale_factor())
            if key==getattr(self,'_status_font_key',None):return
            self._status_font_key=key
            layout=self.create_pango_layout('Ag国');layout.set_font_description(font)
            _,height=layout.get_pixel_size();metrics=context.get_metrics(font,None)
            bold=font.copy();bold.set_weight(Pango.Weight.BOLD)
            bold_metrics=context.get_metrics(bold,None)
            width=math.ceil(max(chars*max(metrics.get_approximate_char_width(),bold_metrics.get_approximate_char_width())/Pango.SCALE,12))
            self.set_size_request(width,max(1,height)*lines)
        measure();self.connect('style-updated',measure)
    def do_get_preferred_width(self):
        w,h=self.get_size_request();return max(1,w),max(1,w)
    def do_get_preferred_height(self):
        w,h=self.get_size_request();return max(1,h),max(1,h)
    def do_get_preferred_height_for_width(self,w):return self.do_get_preferred_height()
    def do_get_preferred_width_for_height(self,h):return self.do_get_preferred_width()


class StatusButton(Gtk.Button):
    """Motor selector whose two live rows keep their existing children."""
    def __init__(self,label=''):
        super().__init__()
        self._caption='';self._rows=[]
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for _ in range(2):
            row=StatusEntry('',.5)
            # Only the containing button receives input; these are display rows.
            row.set_sensitive(False);row.set_can_focus(False)
            provider=Gtk.CssProvider();provider.load_from_data(b'entry {color: inherit;}')
            row.get_style_context().add_provider(provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+2)
            self._rows.append(row);box.pack_start(row,False,False,0)
        self.add(box);self.set_label(label)

    def set_label(self,value):
        self._caption=value
        parts=value.split('\n',1)
        for i,row in enumerate(self._rows):
            text=parts[i] if i<len(parts) else ''
            if row.get_text()!=' '.join(text.splitlines()):row.set_text(text)
        self.get_accessible().set_name(value)

    def get_label(self):return self._caption

    def reserve_status(self,chars,lines):
        for row in self._rows:row.reserve_text(chars,1)

def emulated(event):
    getter=getattr(event,'get_pointer_emulated',None)
    return bool(getter and getter())


def set_button_label(button, value):
    """Keep the existing label/layout when a polling update has no new text."""
    if button.get_label() != value:
        button.set_label(value)


def set_status_text(label, value):
    # Reserved labels flatten paragraphs, retaining the full text as a tooltip.
    visible=' '.join(value.splitlines()) if getattr(label,'_status_reserved',False) else value
    if label.get_text() != visible:
        label.set_text(value)
    elif getattr(label,'_status_reserved',False) and label.get_tooltip_text()!=value:
        label.set_tooltip_text(value)

class TouchInput:
    def __init__(self,window):
        self.contacts=set();self.owner=None;self.sequence=None;self.finish=None
        window.add_events(Gdk.EventMask.TOUCH_MASK)
        window.connect('touch-event',self.window_event)
        for signal in ('focus-out-event','unmap','destroy'):
            window.connect(signal,lambda *_:self.reset())

    def bind(self,widget,begin,finish,update=None):
        widget.add_events(Gdk.EventMask.TOUCH_MASK)
        widget.connect('touch-event',self.event,begin,finish,update)
        widget.connect('unmap',lambda *_:self.cancel_for(widget,reset=True))
        widget.connect('grab-broken-event',lambda *_:self.cancel_for(widget,reset=True))

    def active(self,widget):return self.owner is not None and self.owner is widget

    def cancel_for(self,widget,reset=False):
        if self.active(widget):(self.reset if reset else self.cancel)()

    def reset(self):
        self.cancel();self.contacts.clear()
        return False

    def cancel(self,event=None):
        owner,finish=self.owner,self.finish
        self.owner=self.sequence=self.finish=None
        # Keep contacts until their END/CANCEL: a cancelled finger cannot rearm.
        if owner is not None:finish(owner,event,True)
        return False

    def pointer(self,event,kind):
        return SimpleNamespace(button=1,type=kind,x=event.x,y=event.y,
            state=Gdk.ModifierType.BUTTON1_MASK,touch_input=True,get_pointer_emulated=lambda:False)

    def event(self,widget,event,begin,finish,update):
        seq=event.get_event_sequence();kind=event.type
        if kind==Gdk.EventType.TOUCH_BEGIN:
            if seq in self.contacts:return True
            self.contacts.add(seq)
            if len(self.contacts)!=1:
                self.cancel(event);return True
            if not widget.get_sensitive():return True
            self.owner,self.sequence,self.finish=widget,seq,finish
            try:
                if begin(widget,self.pointer(event,Gdk.EventType.BUTTON_PRESS)) is False:self.cancel(event)
            except Exception:self.cancel(event);raise
        elif kind==Gdk.EventType.TOUCH_UPDATE and self.owner is widget and seq==self.sequence:
            a=widget.get_allocation()
            if not (0<=event.x<a.width and 0<=event.y<a.height):self.cancel(event)
            elif update:update(widget,self.pointer(event,Gdk.EventType.MOTION_NOTIFY))
        elif kind in (Gdk.EventType.TOUCH_END,Gdk.EventType.TOUCH_CANCEL):
            self.contacts.discard(seq)
            if self.owner is not None and seq==self.sequence:
                owner,done=self.owner,self.finish
                self.owner=self.sequence=self.finish=None
                a=widget.get_allocation()
                cancelled=kind==Gdk.EventType.TOUCH_CANCEL or not (0<=event.x<a.width and 0<=event.y<a.height)
                done(owner,self.pointer(event,Gdk.EventType.BUTTON_RELEASE),cancelled)
        return True

    def window_event(self,_window,event):
        if event.type in (Gdk.EventType.TOUCH_END,Gdk.EventType.TOUCH_CANCEL):
            seq=event.get_event_sequence();self.contacts.discard(seq)
            if seq==self.sequence:self.cancel(event)
        return False


def reserve_label(label, chars=1, lines=1):
    """Reserve status space independently of content, following the active font."""
    if hasattr(label,'reserve_text'):
        label.reserve_text(chars,lines);return label
    from gi.repository import Pango
    label._status_reserved=True
    label.set_width_chars(chars);label.set_max_width_chars(chars)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    label.set_line_wrap(lines>1);label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    label.set_lines(lines);label.set_yalign(0)
    def font_height(*_):
        key=(label.get_pango_context().get_font_description().to_string(),label.get_scale_factor())
        if key==getattr(label,'_status_font_key',None):return
        label._status_font_key=key
        layout=label.create_pango_layout('Ag国');_,height=layout.get_pixel_size()
        import math
        metrics=label.get_pango_context().get_metrics(None,None)
        layout.set_text('…',-1);ellipsis,_=layout.get_pixel_size()
        width=math.ceil(max(chars*metrics.get_approximate_char_width()/Pango.SCALE,ellipsis+6))
        label.set_size_request(width,max(1,height)*lines)
    font_height();label.connect('style-updated',font_height)
    def text_changed(*_):
        if getattr(label,'_reserving_text',False):return
        full=label.get_text();parts=full.splitlines()
        if len(parts)>1:
            # Pango limits lines per paragraph; use a single paragraph so
            # explicit newlines cannot create additional wrapped rows.
            visible=' '.join(parts)
            label._reserving_text=True
            try:label.set_text(visible)
            finally:label._reserving_text=False
        label.set_tooltip_text(full)
    label.connect('notify::label',text_changed);text_changed()
    return label


def reserve_button(button, chars=1, lines=1):
    if isinstance(button,StatusButton):
        button.reserve_status(chars,lines);return
    # GtkButton may reconstruct its child when set_label is called.
    def child_changed(*_):
        child=button.get_child()
        if child is not None and not getattr(child,'_reserved_status_space',False):
            reserve_label(child,chars,lines);child._reserved_status_space=True
    child_changed();button.connect('notify::label',child_changed)


def reserve_control_status(window):
    """Only live text gets bounded requisitions; intentional page changes remain."""
    for name,chars,lines in (('connection',1,1),('state',1,1),('speed_text',4,1),
        ('control_title',24,1),('limit_label',24,1),('all_stop_label',1,1),('record_status',28,1)):
        reserve_label(getattr(window,name),chars,lines)
    for label in window.values.values():reserve_label(label,12,2)
    for button in window.motor_buttons.values():reserve_button(button,12,2)
    reserve_button(window.stop_button,14);reserve_button(window.record_end,10)
    pages=window.joint_pages
    for label in pages.notices:reserve_label(label,1,2)
    for label in pages.actual.values():reserve_label(label,12)
    for label in pages.axis_status.values():reserve_label(label,1,2)
    reserve_label(pages.count_label,20);reserve_label(pages.plan_label,1,2)
    reserve_button(pages.record_button,16)
    c,d,p=pages.cartesian_page,pages.drawing_page,pages.combined_page
    for label,lines in ((c.notice,1),(c.result,2),(c.workspace_panel.notice,2),
        (d.notice,1),(d.summary,1),(d.point_info,1),(d.gate_notice,2),(d.calibration_notice,2),
        (p.fullscreen_summary,1),(p.fullscreen_notice,1)):
        reserve_label(label,1,lines)
    for button in (c.preview_button,c.move,c.stream,d.plan_button,d.execute):reserve_button(button)
    reserve_button(p.direction_button,14)
