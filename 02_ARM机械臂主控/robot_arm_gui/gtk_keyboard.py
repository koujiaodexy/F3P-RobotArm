"""Local numeric editing without the desktop's fullscreen keyboard overlay."""
import math
import os
import subprocess
import string
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib


class _DesktopOskGuard:
    """One bounded, coalesced shell update for all windows in this process."""
    def __init__(self):
        self.applied = None
        self.desired = None
        self.source = None
        self.worker = None

    def request(self, active, script):
        self.desired = (active, script)
        if self.worker is None and self.source is None and active != self.applied:
            self.source = GLib.timeout_add(40, self._dispatch)

    def _dispatch(self):
        self.source = None
        active, script = self.desired
        if active == self.applied:
            return False
        def work():
            ok = False
            try:
                result = subprocess.run(['runuser', '-u', 'uisrc', '--', 'gdbus', 'call',
                    '--session', '--dest', 'org.gnome.Shell', '--object-path', '/org/gnome/Shell',
                    '--timeout', '2', '--method', 'org.gnome.Shell.Eval', script],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, timeout=3)
                ok = result.returncode == 0 and result.stdout.lstrip().startswith(b'(true,')
            except (OSError, subprocess.TimeoutExpired):
                pass
            GLib.idle_add(self._finished, active, ok)
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        return False

    def _finished(self, active, ok):
        self.worker = None
        self.applied = active if ok else None
        if self.desired[0] != active:
            self.request(*self.desired)
        return False


_DESKTOP_OSK = _DesktopOskGuard()


class NumericKeyboard:
    def __init__(self, window, desktop_osk=False, track_dialogs=True):
        self.window = window
        self.dialog = None
        self._cached_dialog = None
        self._cached_text_dialog = None
        self._text_mode = False
        self.target = None
        self.pending = None
        self.target_handler = None
        self.bound = set()
        self.touch_feedback = {}
        self.tracker = None
        self.chooser_fit_source = None
        self._contacts = {}
        self._last_touch = (None, 0.)
        self._disposed = False
        window._f3p_numeric_keyboard = self
        self.desktop_osk = desktop_osk
        self.osk_blocked = None
        settings=Gtk.Settings.get_default()
        if settings.get_property('gtk-enable-animations'):
            settings.set_property('gtk-enable-animations',False)
        self.bind_tree(window)
        window.connect('set-focus', self.focus_changed)
        window.connect('focus-in-event', self.window_focused)
        window.connect('destroy', self.dispose)
        window.connect('focus-out-event', self.clear_touch_feedback)
        window.connect('unmap', self.clear_touch_feedback)
        window.connect('unmap', lambda *_: self.close())
        window.connect('destroy', self.stop_file_chooser_fit)
        if isinstance(window,Gtk.FileChooserDialog):
            window.connect('configure-event',lambda *_:(GLib.idle_add(self.file_chooser_configured),False)[1])
            window.connect('map',lambda *_:self.fit_file_chooser())
            window.connect('unmap',self.stop_file_chooser_fit)
        if track_dialogs:
            self.tracker=GLib.timeout_add(200,self.bind_owned_windows)
            window.connect('destroy',self.stop_tracking)
        self.focus_changed(window, window.get_focus())

    def bind_tree(self, widget):
        if self.is_keyboard_widget(widget):
            return
        # GtkButton already provides :active feedback for touch and mouse.
        # An extra CAPTURE gesture competes with its native input controller
        # and invalidates CSS on every contact. Custom hold controls keep
        # their existing TouchInput handling in gtk_touch.py.
        if isinstance(widget,Gtk.MenuButton) and widget.get_popover() is not None:
            self.bind_tree(widget.get_popover())
        # Filenames, pose names and other single-line fields use the same
        # local text pad. Requiring each caller to opt in left native save
        # dialogs able to raise GNOME's blocking touchscreen keyboard.
        if isinstance(widget,Gtk.Entry) and widget.get_editable() and not isinstance(widget,Gtk.SpinButton):
            widget._f3p_local_text=True
        if isinstance(widget,Gtk.Entry) and widget.get_editable() and widget not in self.bound:
            self.bound.add(widget)
            widget.set_input_hints(widget.get_input_hints() | Gtk.InputHints.INHIBIT_OSK)
            widget.add_events(Gdk.EventMask.TOUCH_MASK)
            # GtkEntry may consume the event in its default class handler;
            # an after-handler is then skipped entirely.
            widget.connect('touch-event', self.touch)
            widget.connect('button-release-event', self.mouse_release)
            widget.connect('unmap', self.entry_unmapped)
            widget.connect('destroy', lambda w, bound=self.bound: bound.discard(w))
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                self.bind_tree(child)

    def focus_changed(self, _window, widget):
        if isinstance(widget, Gtk.Entry):
            self.bind_tree(widget)
        self.suppress_desktop_osk(self.block_desktop_osk(widget))

    def block_desktop_osk(self, widget):
        # Read-only status entries and buttons are not text input. GNOME 3.36
        # auto-enables its OSK in touch mode even when the a11y setting is off.
        # Single-line editing uses the local numeric/text pad, even when an
        # internal file-chooser entry receives focus before the next scan.
        if self.dialog is not None or isinstance(widget, Gtk.Entry):
            return True
        return not (isinstance(widget, (Gtk.Entry, Gtk.TextView)) and
                    widget.get_editable() and widget.is_sensitive())

    def window_focused(self, *_):
        self.focus_changed(self.window, self.window.get_focus())
        return False

    def suppress_desktop_osk(self, active):
        if not self.desktop_osk or self._disposed:
            return
        self.osk_blocked = active
        # The board uses X11/XIM, where GNOME's automatic keyboard does not
        # consistently honor GTK INHIBIT_OSK. Scope its open guard to this
        # process and local-editor focus only; other apps keep their OSK.
        script = '''
        (() => {
          let proto = imports.ui.keyboard.Keyboard.prototype;
          if (!proto._f3pOriginalOpen) {
            proto._f3pOriginalOpen = proto.open;
          }
          proto.open = function(...args) {
              let f = global._f3pNumericInput;
              let w = global.display.focus_window;
              if (f && f.active && w && w.get_pid() === f.pid) return;
              return proto._f3pOriginalOpen.apply(this, args);
          };
          let old = global._f3pNumericInput;
          if (old && old.pid === PID && old.sequence > SEQUENCE) return;
          global._f3pNumericInput = {pid: PID, active: ACTIVE, sequence: SEQUENCE};
          let wm = Main.wm;
          if (!wm._f3pOriginalShouldAnimateActor)
            wm._f3pOriginalShouldAnimateActor = wm._shouldAnimateActor;
          wm._shouldAnimateActor = function(actor, ...args) {
            let owner = global._f3pNumericInput;
            if (owner && actor.meta_window && actor.meta_window.get_pid() === owner.pid)
              return false;
            return this._f3pOriginalShouldAnimateActor.call(this, actor, ...args);
          };
          let focused = global.display.focus_window;
          if (ACTIVE && focused && focused.get_pid() === PID) {
            Main.keyboard.close();
            let keyboard = Main.keyboard._keyboard;
            if (keyboard) {
              keyboard._clearShowIdle();
              keyboard._clearKeyboardRestTimer();
              keyboard._keyboardRequested = false;
            }
            Main.layoutManager.hideKeyboard(true);
          }
        })();'''.replace('PID', str(os.getpid())).replace('ACTIVE', 'true' if active else 'false').replace('SEQUENCE', str(time.monotonic() * 1000))
        _DESKTOP_OSK.request(active, script)

    @staticmethod
    def is_keyboard_widget(widget):
        top = widget.get_toplevel()
        return bool(getattr(top, '_f3p_keyboard_window', False))

    @staticmethod
    def event_position(widget, event):
        # Spin arrows and the entry text each have their own input-only GDK
        # window. event.x/y are local to that window, not the Gtk allocation.
        window = getattr(event, 'window', None)
        if window is None:
            return event.x, event.y
        owner = widget.get_window()
        if owner is None:
            return None
        ex, ey = window.get_origin()[-2:]
        wx, wy = owner.get_origin()[-2:]
        x, y = event.x + ex - wx, event.y + ey - wy
        if not widget.get_has_window():
            allocation = widget.get_allocation()
            x, y = x - allocation.x, y - allocation.y
        return x, y

    def text_hit(self, widget, event):
        point = self.event_position(widget, event)
        if point is None:
            return False
        text = widget.get_text_area() if isinstance(widget, Gtk.SpinButton) else widget.get_allocation()
        x, y = (text.x, text.y) if isinstance(widget, Gtk.SpinButton) else (0, 0)
        return x <= point[0] < x + text.width and y <= point[1] < y + text.height

    def touch(self, widget, event):
        sequence = event.get_event_sequence()
        if event.type == Gdk.EventType.TOUCH_BEGIN:
            self._contacts[sequence] = (widget, self.text_hit(widget, event), self.event_position(widget, event))
        elif event.type in (Gdk.EventType.TOUCH_END, Gdk.EventType.TOUCH_CANCEL):
            contact = self._contacts.pop(sequence, None)
            self._last_touch = (widget, time.monotonic())
            point = self.event_position(widget, event)
            if (event.type == Gdk.EventType.TOUCH_END and contact is not None and
                contact[0] is widget and contact[1] and point is not None and
                math.dist(contact[2], point) < 16):
                self.queue(widget, event)
        return False

    def mouse_release(self, widget, event):
        source = getattr(event, 'get_source_device', lambda: None)()
        if source and source.get_source() == Gdk.InputSource.TOUCHSCREEN:
            if self._last_touch[0] is widget and time.monotonic() - self._last_touch[1] < .35:
                return False
            self.queue(widget, event)
        return False

    def queue(self, widget, event):
        # Tapping a spin arrow should retain its ordinary one-step behavior.
        if self.is_keyboard_widget(widget) or not self.text_hit(widget, event):
            return
        if self._disposed or not widget.get_mapped() or not widget.is_sensitive() or not widget.get_editable():
            return
        if self.pending is None:
            # Finish the source contact and emulated release before mapping
            # another window. Idle callbacks can run before that release.
            self._pending_started = time.monotonic()
            self._pending_target = widget
            self.pending = GLib.timeout_add(60, self.open_pending, widget)

    def entry_unmapped(self, widget):
        if widget is getattr(self, '_pending_target', None) or widget is self.target:
            self.close()

    def open_pending(self, widget):
        if self._disposed or not widget.get_mapped():
            self.pending = None
            self._pending_target = None
            return False
        display = self.window.get_display()
        pointer = display.get_default_seat().get_pointer()
        root = Gdk.get_default_root_window()
        if root is not None and root.get_device_position(pointer)[-1] & Gdk.ModifierType.BUTTON1_MASK:
            if time.monotonic() - self._pending_started < 1.5:
                return True
            self.pending = None
            self._pending_target = None
            return False
        self.pending = None
        self._pending_target = None
        self.open(widget)
        return False

    def open(self, target):
        if self._disposed or self.is_keyboard_widget(target):
            return
        self.close()
        if not target.get_mapped() or not target.is_sensitive() or not target.get_editable():
            return
        self.target = target
        self.suppress_desktop_osk(True)
        self._text_mode = not isinstance(target, Gtk.SpinButton)
        dialog = self._cached_text_dialog if self._text_mode else self._cached_dialog
        if dialog is None:
            dialog = self.build_text_dialog(target.get_toplevel()) if self._text_mode else self.build_dialog(target.get_toplevel())
            dialog._f3p_editor, dialog._f3p_notice = self.editor, self.notice
            if self._text_mode:self._cached_text_dialog = dialog
            else:self._cached_dialog = dialog
        self.editor, self.notice = dialog._f3p_editor, dialog._f3p_notice
        dialog.set_transient_for(target.get_toplevel())
        self.dialog = dialog
        self.editor.set_visibility(target.get_visibility())
        self.editor.set_max_length(target.get_max_length() if self._text_mode else 0)
        self.editor.set_text(target.get_text())
        self.notice.set_text('')
        self.target_handler = target.connect('unmap', self.target_unmapped, dialog)
        caption=target.get_tooltip_text()
        dialog.set_title(('输入文字' if self._text_mode else '输入数值')+(' · '+caption.splitlines()[0][:40] if caption else ''))
        dialog.show_all()
        GLib.timeout_add(100,self.position_editor,dialog,target)
        GLib.timeout_add(300,self.position_editor,dialog,target)
        dialog.present()
        self.editor.grab_focus()
        self.editor.select_region(0, -1)

    def position_editor(self, dialog, target):
        if self.dialog is not dialog or self.target is not target or not target.get_mapped():return False
        top=target.get_toplevel();surface=top.get_window()
        if surface is None:return False
        offset=target.translate_coordinates(top,0,0)
        if offset is None:return False
        origin=surface.get_origin();ox,oy=origin[-2:]
        a=target.get_allocation();rect=(ox+offset[0],oy+offset[1],a.width,a.height)
        monitor=top.get_display().get_monitor_at_window(surface);area=monitor.get_workarea()
        from .ui_geometry import keyboard_position
        dialog.set_position(Gtk.WindowPosition.NONE)
        dialog.move(*keyboard_position(rect,dialog.get_size(),(area.x,area.y,area.width,area.height)))
        return False

    def build_dialog(self, parent):
        # Keep the parent command controls blocked while editing. The queued
        # path above waits for the original pointer release before mapping.
        dialog = Gtk.Dialog(title='输入数值', transient_for=parent, modal=True)
        # Utility hint keeps this modal editor movable under GNOME Mutter.
        dialog.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        dialog._f3p_keyboard_window = True
        dialog.get_style_context().add_class('numeric-keyboard')
        dialog.set_default_size(440, 530)
        dialog.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        dialog.set_resizable(False)
        box = dialog.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)
        self.editor = Gtk.Entry()
        self.editor.set_input_hints(Gtk.InputHints.INHIBIT_OSK)
        box.pack_start(self.editor, False, False, 0)
        self.notice = Gtk.Label()
        box.pack_start(self.notice, False, False, 0)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        box.pack_start(grid, True, True, 0)
        for i, key in enumerate(('7','8','9','4','5','6','1','2','3','±','0','.','清空','⌫')):
            button = Gtk.Button(label=key)
            button.set_size_request(128, 64)
            button.set_can_focus(False)
            button.connect('clicked', lambda _b, k=key: self.key(k))
            grid.attach(button, i % 3, i // 3, 1, 1)
        dialog.add_button('关闭（不保存）', Gtk.ResponseType.CANCEL)
        dialog.add_button('完成', Gtk.ResponseType.OK).get_style_context().add_class('suggested-action')
        dialog.connect('response', self.response)
        dialog.connect('delete-event', lambda *_: (self.close(), True)[1])
        dialog.connect('key-press-event', self.key_press)
        self.editor.connect('activate', lambda *_: self.response(dialog, Gtk.ResponseType.OK))
        return dialog

    def build_text_dialog(self, parent):
        dialog = Gtk.Dialog(title='输入文字 / 密码', transient_for=parent, modal=True)
        # Utility hint keeps this modal editor movable under GNOME Mutter.
        dialog.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        dialog._f3p_keyboard_window = True
        dialog.get_style_context().add_class('text-keyboard')
        dialog.set_default_size(850, 570)
        dialog.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        box = dialog.get_content_area();box.set_border_width(12);box.set_spacing(8)
        self.editor = Gtk.Entry();self.editor.set_input_hints(Gtk.InputHints.INHIBIT_OSK)
        box.pack_start(self.editor,False,False,0)
        self.notice = Gtk.Label();box.pack_start(self.notice,False,False,0)
        grid = Gtk.Grid(column_spacing=6,row_spacing=6,column_homogeneous=True)
        self._text_keys=[];self._text_upper=False;self._text_symbols=False
        for i in range(40):
            button=Gtk.Button();button.set_can_focus(False)
            button.connect('clicked',lambda b:self.key(b.get_label()))
            grid.attach(button,i%10,i//10,1,1);self._text_keys.append(button)
        self._refresh_text_keys();box.pack_start(grid,True,True,0)
        tools=Gtk.Box(spacing=8)
        for label,action in (('大小写',lambda:self._toggle_text_keys('upper')),('字母 / 符号',lambda:self._toggle_text_keys('symbols')),('空格',lambda:self.key(' ')),('清空',lambda:self.key('清空')),('退格',lambda:self.key('⌫'))):
            button=Gtk.Button(label=label);button.set_can_focus(False);button.connect('clicked',lambda _b,f=action:f());tools.pack_start(button,True,True,0)
        box.pack_start(tools,False,False,0)
        dialog.add_button('关闭（不保存）',Gtk.ResponseType.CANCEL)
        dialog.add_button('完成',Gtk.ResponseType.OK)
        dialog.connect('response',self.response)
        dialog.connect('delete-event',lambda *_:(self.close(),True)[1])
        dialog.connect('key-press-event',self.key_press)
        self.editor.connect('activate',lambda *_:self.response(dialog,Gtk.ResponseType.OK))
        return dialog

    def _toggle_text_keys(self, kind):
        if kind=='upper':self._text_upper=not self._text_upper
        else:self._text_symbols=not self._text_symbols
        self._refresh_text_keys()

    def _refresh_text_keys(self):
        keys=(string.punctuation+' '*40)[:40] if self._text_symbols else '1234567890qwertyuiopasdfghjkl@zxcvbnm.-_'
        if self._text_upper:keys=keys.upper()
        for button,key in zip(self._text_keys,keys):
            button.set_label(key);button.set_sensitive(key!=' ')

    def target_unmapped(self, _target, dialog):
        if self.dialog is dialog:
            self.close()

    def key(self, key):
        entry = self.editor
        text = entry.get_text()
        selected = entry.get_selection_bounds()
        a, b = selected if selected else (entry.get_position(), entry.get_position())
        if key == '清空':
            value, position = '', 0
        elif key == '±' and not self._text_mode:
            value = text[1:] if text.startswith('-') else '-' + text
            position = len(value)
        elif key == '⌫':
            if a == b:
                a = max(0, a - 1)
            value, position = text[:a] + text[b:], a
        else:
            value, position = text[:a] + key + text[b:], a + len(key)
            if not self._text_mode and value.count('.') > 1:
                return
        entry.set_text(value)
        entry.set_position(position)
        self.notice.set_text('')

    def response(self, _dialog, response):
        if response == Gtk.ResponseType.OK:
            if self._text_mode:
                target,value=self.target,self.editor.get_text()
                self.close();target.set_text(value);target.set_position(-1)
                return
            try:
                value = float(self.editor.get_text())
                adjustment = self.target.get_adjustment()
                if not math.isfinite(value) or not adjustment.get_lower() <= value <= adjustment.get_upper():
                    raise ValueError()
            except ValueError:
                self.notice.set_text('请输入允许范围内的有效数字')
                return
            target = self.target
            self.close()
            target.set_value(value)
        else:
            self.close()

    def key_press(self, _dialog, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def close(self):
        if self.pending is not None:
            GLib.source_remove(self.pending)
            self.pending = None
        self._pending_target = None
        self._contacts.clear()
        dialog, self.dialog = self.dialog, None
        if self.target_handler is not None and self.target is not None:
            self.target.disconnect(self.target_handler)
            self.target_handler = None
        self.target = None
        if dialog is not None:
            dialog.hide()
        self.suppress_desktop_osk(self.block_desktop_osk(self.window.get_focus()))

    def dispose(self, *_):
        self._disposed = True
        self.close()
        dialog, self._cached_dialog = self._cached_dialog, None
        if dialog is not None:
            dialog.destroy()
        dialog, self._cached_text_dialog = self._cached_text_dialog, None
        if dialog is not None:
            dialog.destroy()

    def clear_touch_feedback(self, *_):
        self._contacts.clear()
        for widget in tuple(self.touch_feedback):
            widget.get_style_context().remove_class('touch-pressed')
        return False


    def stop_tracking(self, *_):
        if self.tracker is not None:
            GLib.source_remove(self.tracker)
            self.tracker = None


    def bind_owned_windows(self):
        # Only our transient dialogs; unrelated applications keep their keyboard.
        for top in Gtk.Window.list_toplevels():
            if top is self.window or hasattr(top, '_f3p_numeric_keyboard') or top.get_style_context().has_class('numeric-keyboard') or top.get_style_context().has_class('text-keyboard'):
                continue
            parent = top.get_transient_for()
            visited = set()
            while parent is not None and parent is not self.window and parent not in visited:
                visited.add(parent)
                parent = parent.get_transient_for()
            if parent is self.window:
                manager = NumericKeyboard(top, desktop_osk=self.desktop_osk, track_dialogs=False)
                if isinstance(top, Gtk.FileChooserDialog):manager.fit_file_chooser()
                manager.focus_changed(top, top.get_focus())
        return True


    def stop_file_chooser_fit(self, *_):
        if self.chooser_fit_source is not None:
            GLib.source_remove(self.chooser_fit_source)
            self.chooser_fit_source = None


    def file_chooser_configured(self, *_):
        # GTK may apply saved geometry or CSD after the initial fit has ended.
        top = self.window
        parent = top.get_transient_for()
        if self.chooser_fit_source is None and top.get_realized() and parent is not None and parent.get_window() is not None:
            scale = max(1.0, min(1.75, parent.get_allocated_height() / 800.0))
            width = min(parent.get_allocated_width() - 60, round(1100 * scale))
            height = min(parent.get_allocated_height() - 80, round(780 * scale))
            frame = top.get_window().get_frame_extents()
            if frame.width > width or frame.height > height:
                GLib.idle_add(self.fit_file_chooser)
        return False


    def fit_file_chooser(self):
        if self.chooser_fit_source is not None:
            return
        attempts = [0]
        stable = [0]
        def fit():
            top = self.window
            if not top.get_realized() or not top.get_visible():
                self.chooser_fit_source = None
                return False
            parent = top.get_transient_for()
            if parent is None or parent.get_window() is None:
                self.chooser_fit_source = None
                return False
            attempts[0] += 1
            scale = max(1.0, min(1.75, parent.get_allocated_height() / 800.0))
            width = min(parent.get_allocated_width() - 60, round(1100 * scale))
            height = min(parent.get_allocated_height() - 80, round(780 * scale))
            frame = top.get_window().get_frame_extents()
            content = top.get_size()
            # GtkWindow.resize accepts content size. Account for the current
            # titlebar, borders and shadows before fitting the outer frame.
            chrome_width = max(0, frame.width - content.width)
            chrome_height = max(0, frame.height - content.height)
            requested = (max(1, width - chrome_width), max(1, height - chrome_height))
            if attempts[0] == 1:
                top.set_geometry_hints(None, Gdk.Geometry(), Gdk.WindowHints(0))
            if (content.width, content.height) != requested:
                top.resize(*requested)
            parent_frame = parent.get_window().get_frame_extents()
            top.move(parent_frame.x + max(0, (parent_frame.width - width) // 2),
                     parent_frame.y + max(0, (parent_frame.height - height) // 2))
            stable[0] = stable[0] + 1 if (frame.width, frame.height) == (width, height) else 0
            if stable[0] >= 2 or attempts[0] >= 20:
                self.chooser_fit_source = None
                return False
            return True
        # Send the first resize immediately; GTK commits it asynchronously.
        if fit():
            self.chooser_fit_source = GLib.timeout_add(200, fit)

