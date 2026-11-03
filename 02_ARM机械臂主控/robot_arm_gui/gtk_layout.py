"""Presentation-only console organization; command handlers remain unchanged."""
from gi.repository import Gtk, GLib, Pango

CSS=b"""
.layout-clean .canvas-pane, .layout-clean .parameter-pane { background: #ffffff; border: 1px solid #e2e9f2; border-radius: 10px; }
.layout-clean .muted-info { font-size: 15px; color: #7285a0; }
.layout-clean .main-navigation button { border-radius: 6px; min-height: 42px; }
.layout-clean .canvas-pane button, .layout-clean .parameter-pane button { border-radius: 6px; }
.layout-clean .card { border: 0; background: transparent; }

.layout-clean { font-size: 17px; }
.layout-clean entry.connection-status { border: 0; box-shadow: none; background: transparent; min-height: 0; font-size: 16px; }
.layout-clean .title { font-size: 25px; }
.layout-clean .subtitle { font-size: 15px; }
.layout-clean button { min-height: 44px; min-width: 66px; padding: 6px 12px; font-size: 18px; border-radius: 8px; }
.layout-clean .operation-tabs button { min-height: 48px; font-size: 19px; padding: 6px 12px; }
.layout-clean button.stop { min-height: 52px; min-width: 120px; font-size: 22px; }
.layout-clean .motor-select { min-height: 56px; padding: 5px 8px; }
.layout-clean .motor-select entry { font-size: 17px; }
.layout-clean .joint-panel, .layout-clean .drawing-settings { font-size: 17px; }
.layout-clean .joint-panel button, .layout-clean .drawing-settings button { font-size: 18px; min-height: 44px; }
.layout-clean .joint-panel button.cart-jog { min-height: 54px; font-size: 26px; }
.layout-clean spinbutton { min-height: 44px; font-size: 20px; }
.layout-clean spinbutton button { min-width: 44px; min-height: 42px; padding: 0 5px; }
.layout-clean .card { padding: 8px 10px; border-radius: 10px; }
.layout-clean .diagnostic-values, .layout-clean .diagnostic-values label { font-size: 17px; }
.layout-clean .vision-stage { background: #ffffff; border: 1px solid #e2e9f2; border-radius: 10px; padding: 10px; }
.layout-clean { color: #516781; }
.layout-clean .title { color: #24364f; font-weight: 600; }
.layout-clean .subtitle { color: #7d8da3; }
.layout-clean button { font-weight: 500; }
.layout-clean .primary-navigation { background: #e9edf4; padding: 4px; border-radius: 10px; }
.layout-clean .primary-navigation button { background: transparent; border-color: transparent; color: #72839d; }
.layout-clean .primary-navigation button.active { background: #ffffff; color: #315f9f; border-color: #ffffff; }
.layout-clean .secondary-navigation { background: transparent; border-color: transparent; color: #7789a2; }
.layout-clean button.motor-select { background: #ffffff; border: 1px solid #e0e7f1; color: #607795; border-radius: 8px; }
.layout-clean button.motor-select.selected { border-color: #83a5dc; background: #ffffff; color: #3e67a5; }
.layout-clean button.stop { color: #b54f54; background: #fff2f2; border: 1px solid #e8bcbc; font-size: 20px; }
.layout-clean .canvas-pane, .layout-clean .parameter-pane { border-radius: 12px; }
.layout-clean .status-feedback { color: #7b8ca4; font-size: 15px; }
.layout-clean .primary-action { background: #416fc1; color: #ffffff; border-color: #416fc1; }
.layout-clean .primary-action:disabled { background: #eef2f7; color: #a5b0c0; border-color: #e5eaf2; }
.layout-clean spinbutton { background: #fafbfd; border-color: #dfe7f2; }
.layout-clean spinbutton entry { background: #fafbfd; color: #344e72; }
.layout-clean spinbutton button { background: #fafbfd; color: #7e94b5; border-color: #e7edf5; }

.layout-clean spinbutton entry { min-height: 42px; font-size: 20px; padding: 0 10px; }
.layout-clean scrollbar slider { min-width: 12px; min-height: 44px; background: #c7d3e3; }
.layout-clean scrollbar { background: #f4f6fa; }

.layout-clean.compact-layout button { min-height: 36px; padding: 3px 8px; font-size: 16px; }
.layout-clean.compact-layout .operation-tabs button { min-height: 36px; padding: 3px 8px; font-size: 17px; }
.layout-clean.compact-layout button.stop { min-height: 42px; font-size: 20px; }
.layout-clean.compact-layout .motor-select { min-height: 42px; padding: 3px 6px; }
.layout-clean.compact-layout .joint-panel button.cart-jog { min-height: 42px; font-size: 25px; }
.layout-clean.compact-layout spinbutton, .layout-clean.compact-layout spinbutton entry { min-height: 36px; }
.layout-clean.compact-layout spinbutton button { min-height: 36px; }
.layout-clean.compact-layout .card { padding: 2px 4px; }

"""

def move(widget,box,expand=False):
    parent=widget.get_parent()
    if parent is not None:parent.remove(widget)
    box.pack_start(widget,expand,expand,0)

def buttons(widget,seen=None):
    if seen is None:seen=set()
    if widget in seen:return set()
    seen.add(widget);result={widget} if isinstance(widget,Gtk.Button) else set()
    if isinstance(widget,Gtk.Container):
        for child in widget.get_children():result.update(buttons(child,seen))
    if isinstance(widget,Gtk.MenuButton) and widget.get_popover():result.update(buttons(widget.get_popover(),seen))
    return result

def apply_layout(window):
    original_buttons=buttons(window)
    window.get_style_context().add_class('layout-clean')
    if window.get_screen().get_height() <= 800:
        window.get_style_context().add_class('compact-layout')
    provider=Gtk.CssProvider();provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(window.get_screen(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+3)
    window._layout_provider=provider
    outer=window.workspace.get_child_by_name('control')
    outer.set_border_width(10);outer.set_spacing(6)
    header=outer.get_children()[0]
    children=list(header.get_children());titles=children[0]
    motor_row=window.motor_cards.get_parent()
    stop=next(w for w in motor_row.get_children() if isinstance(w,Gtk.Button) and w.get_label()=='全部停止')
    cloud=[]
    for child in children:
        if isinstance(child,Gtk.Box) and child is not titles:
            cloud.extend(w for w in child.get_children() if isinstance(w,Gtk.Button))
    for child in children:header.remove(child)
    header.set_spacing(12)
    header.get_style_context().add_class('console-header')
    header.pack_start(titles,False,False,0)
    # StatusEntry reserves one character on style updates; use a label here.
    window.connection=Gtk.Label(xalign=1)
    window.connection.set_ellipsize(Pango.EllipsizeMode.END)
    window.connection.set_width_chars(12)
    window.connection.set_max_width_chars(28)
    window.connection.connect('notify::label',lambda label,*_:label.set_tooltip_text(label.get_text()))
    header.pack_start(window.connection,True,True,0)
    window.fault_summary=Gtk.Label(xalign=0)
    window.fault_summary.set_max_width_chars(22)
    window.fault_summary.set_ellipsize(Pango.EllipsizeMode.END)
    window.fault_summary.get_style_context().add_class('bad')
    header.pack_start(window.fault_summary,False,False,0)
    move(stop,header)
    stop.set_size_request(140,52)
    stop.set_tooltip_text('停止所有关节任务；空格键同样可停止。不能代替硬件急停。')
    nav=Gtk.Box(spacing=10)
    nav.get_style_context().add_class('main-navigation')
    pages=window.joint_pages
    subnav=Gtk.Box(spacing=8)
    subnav.get_style_context().add_class('operation-tabs')
    subnav.set_homogeneous(True)
    subnav.set_no_show_all(True)
    for key in ('control','position'):
        move(pages.tabs[key],subnav,True)
    subnav_parent=window.operation_stack.get_parent()
    subnav_parent.pack_start(subnav,False,False,0)
    subnav_parent.reorder_child(subnav,0)
    joint=Gtk.Button(label='关节')
    last_joint=['control']
    joint.connect('clicked',lambda *_:window._command(lambda:pages.show(last_joint[0])))
    move(joint,window.operation_tabs,True)
    window.operation_tabs.reorder_child(joint,0)
    pages.tabs['drawing'].set_label('定位 / 绘图')
    teaching=pages.tabs['teaching']
    teaching.set_label('示教')
    move(teaching,nav)
    move(window.vision_button,window.operation_tabs,True)
    for button in window.operation_tabs.get_children():
        window.operation_tabs.set_child_packing(button,True,True,0,Gtk.PackType.START)
    window.operation_tabs.set_spacing(6)
    window.operation_tabs.get_style_context().add_class('primary-navigation')
    move(window.operation_tabs,nav,True)
    nav.reorder_child(window.operation_tabs,0)
    def sync_navigation(*_):
        name=window.operation_stack.get_visible_child_name()
        in_joint=name in ('control','position')
        if in_joint:last_joint[0]=name
        subnav.set_visible(in_joint)
        context=joint.get_style_context()
        (context.add_class if in_joint else context.remove_class)('active')
    window.operation_stack.connect('notify::visible-child',sync_navigation)
    window.joint_navigation=joint;window.joint_subnavigation=subnav
    window._sync_navigation=sync_navigation
    for button in subnav.get_children():button.show_all()
    sync_navigation()
    move(window.car_button,nav)
    details=Gtk.MenuButton(label='状态')
    nav.pack_start(details,False,False,0)
    tools=Gtk.MenuButton(label='更多')
    nav.pack_start(tools,False,False,0)
    outer.pack_start(nav,False,False,0);outer.reorder_child(nav,1)
    content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);content.set_border_width(12)
    popup=Gtk.Popover.new(tools);popup.add(content);tools.set_popover(popup)
    for widget in [window.zero_button,window.utility_button]+cloud+[window.shutdown_button]:
        move(widget,content);widget.set_size_request(240,48)
    window.zero_button.set_label('零点 / 标定')
    window.shutdown_button.set_label('安全关机')
    content.show_all()
    scroll=window.diagnostics
    while scroll is not None and not isinstance(scroll,Gtk.ScrolledWindow):scroll=scroll.get_parent()
    if scroll is None:raise RuntimeError('Diagnostics scroll not found')
    parent=scroll.get_parent();parent.remove(scroll)
    scroll.set_size_request(360, min(560, window.get_screen().get_height()-140));window.diagnostics.set_size_request(340,-1)
    diagnostic_popup=Gtk.Popover.new(details);diagnostic_popup.add(scroll);details.set_popover(diagnostic_popup)
    # A quiet controller may not publish another snapshot just for a popup.
    diagnostic_popup.connect('map', lambda *_: window._apply_snapshot(window.controller._snapshot_payload()))
    scroll.show_all()
    window.communication_button=details;window.tools_button=tools
    for w in (teaching,window.car_button,details,tools):w.get_style_context().add_class('secondary-navigation')
    window.home_all_button.set_tooltip_text('仅在关节在线、零点有效且任务空闲时可用。')
    d=window.joint_pages.drawing_page
    d.cut.set_width_chars(7);d.cut.set_max_width_chars(7);d.cut.set_size_request(224,-1)
    d.slice_box.set_hexpand(True);d.slice_box.set_vexpand(True)
    d.slice_box.set_halign(Gtk.Align.FILL);d.slice_box.set_valign(Gtk.Align.FILL)
    def fit_canvas():
        if d.slice_box.get_mapped():d.render(force=True)
        return False
    window.connect('map-event',lambda *_:(GLib.timeout_add(100,fit_canvas),False)[1])
    # Keep the existing controls and bindings; arrange them on a regular grid.
    combined=window.joint_pages.combined_page
    left,side=combined.left,combined.side
    left.get_parent().set_spacing(16)
    left.get_parent().set_child_packing(side,False,True,0,Gtk.PackType.START)
    left.get_style_context().add_class('canvas-pane')
    side.get_style_context().add_class('parameter-pane')
    left.set_border_width(8);side.set_border_width(8)
    left.set_spacing(4);side.set_spacing(4);combined.side_content.set_spacing(6)
    # Coordinate actions belong next to their coordinate inputs.
    coordinate_actions=combined.target_widgets[2]
    files=coordinate_actions.get_parent()
    move(coordinate_actions,combined.side_content)
    combined.side_content.reorder_child(coordinate_actions,2)
    coordinate_actions.set_homogeneous(True)
    for child in coordinate_actions.get_children():coordinate_actions.set_child_packing(child,True,True,0,Gtk.PackType.START)
    files.set_homogeneous(True);files.set_spacing(8)
    for child in files.get_children():files.set_child_packing(child,True,True,0,Gtk.PackType.START)
    for widget in (d.summary,d.point_info,d.notice):
        widget.get_style_context().add_class('muted-info')
    toolbar=left.get_children()[0];toolbar.set_spacing(8)
    # Consistent inputs and contextual numeric editor titles.
    for n,entry in window.joint_pages.entries.items():
        entry.set_width_chars(8);entry.set_hexpand(True)
        entry.set_tooltip_text('J%d 目标角度 / °'%n)
    for name,entry in zip('XYZ',d.xyz):entry.set_tooltip_text('目标 %s / mm'%name)
    d.cut.set_tooltip_text('当前绘图切片高度 / mm')
    grid=next(iter(window.joint_pages.entries.values())).get_parent()
    if isinstance(grid,Gtk.Grid):grid.set_column_spacing(16);grid.set_row_spacing(8)
    for box in (combined.side_content,combined.left):box.set_spacing(4)
    for w in (window.joint_pages.cartesian_page.preview_button,window.joint_pages.cartesian_page.move,d.plan_button,d.execute):w.get_style_context().add_class('primary-action')
    # All button instances, including nested popup actions, must remain reachable.
    remaining=buttons(window)
    missing=original_buttons-remaining
    if missing:raise RuntimeError('Layout lost controls: '+repr([w.get_label() for w in missing]))
    window._layout_function_inventory={'original_buttons':len(original_buttons),'retained_buttons':len(original_buttons & remaining),'missing':[]}
    nav.show_all();header.show_all();left.show_all()
    # Reapply the existing visibility rules after moving widgets.
    combined.show_operation(combined.operation)
    sync_navigation()
