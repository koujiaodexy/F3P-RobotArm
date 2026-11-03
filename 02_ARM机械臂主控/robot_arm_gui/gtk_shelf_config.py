"""GTK shelf quantity settings. Saving settings never starts motion."""
from gi.repository import Gtk
from .six_item_catalog import PICK_ITEMS, PICK_LABELS, DROP_BOX_FOR_ITEM


class ShelfConfigDialog(Gtk.Dialog):
    def __init__(self, parent, shelves=None):
        super().__init__(title='货架取货任务设置', transient_for=parent, modal=True)
        self.set_default_size(740, 620)
        self.add_button('取消', Gtk.ResponseType.CANCEL)
        self.add_button('保存选择', Gtk.ResponseType.OK)
        body = self.get_content_area()
        body.set_spacing(16)
        body.set_border_width(20)
        note = Gtk.Label(label='设置各货架数量；0 表示不取。上下滑动查看。', xalign=0)
        body.pack_start(note, False, False, 0)
        grid = Gtk.Grid(column_spacing=20, row_spacing=12)
        for col, label in enumerate(('物品 / 投放箱', '货架 1', '货架 2', '货架 3')):
            grid.attach(Gtk.Label(label=label), col, 0, 1, 1)
        self.fields = [{} for _ in range(3)]
        initial = shelves or [{item: 0 for item in PICK_ITEMS} for _ in range(3)]
        box_labels = {'red': '左侧红箱', 'yellow': '中间黄箱', 'green': '右侧绿箱'}
        for row, item in enumerate(PICK_ITEMS, 1):
            label = Gtk.Label(label='%s\n→ %s' % (PICK_LABELS[item], box_labels[DROP_BOX_FOR_ITEM[item]]), xalign=0)
            grid.attach(label, 0, row, 1, 1)
            for station in range(3):
                field = Gtk.SpinButton.new_with_range(0, 20, 1)
                field.set_numeric(True)
                field.set_width_chars(2)
                field.set_size_request(110, 56)
                field.set_value(initial[station].get(item, 0))
                grid.attach(field, station+1, row, 1, 1)
                self.fields[station][item] = field
        self.table_scroll = Gtk.ScrolledWindow()
        self.table_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.table_scroll.set_overlay_scrolling(False)
        self.table_scroll.set_min_content_height(220)
        self.table_scroll.add(grid)
        body.pack_start(self.table_scroll, True, True, 0)
        route_note = Gtk.Label(label='取货完成后右转180°，按实际前进距离加26cm返回；\n完整走完3个货架时为200cm＋额外行程。然后左45°、前进50cm、右45°后停止。', xalign=0)
        route_note.set_line_wrap(True)
        self.route_expander = Gtk.Expander(label='返回路线')
        self.route_expander.set_size_request(-1, 48)
        self.route_expander.add(route_note)
        body.pack_start(self.route_expander, False, False, 0)
        warning = Gtk.Label(label='启动前：机械臂回0收回，IMU和AI识别就绪。\n保存不启动；准备后点“启动任务”，停止按钮或KEY4可停止。', xalign=0)
        warning.set_line_wrap(True)
        body.pack_start(warning, False, False, 0)
        self.show_all()

    def selected_shelves(self):
        from .shelf_executor import validate_shelf_items
        return validate_shelf_items([{item: fields[item].get_value_as_int() for item in PICK_ITEMS} for fields in self.fields])
