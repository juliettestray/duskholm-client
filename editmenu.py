"""Cut, copy and paste from a right-click menu: in the entry box (Cut, Copy, Paste, Select all, Clear) and in the main
text and the capture panes (Copy, Select all, and Open / Copy link on a link). In the DOS look the same choices come
up as a DOS menu. The keyboard works as it always did: Ctrl+X, Ctrl+C, Ctrl+V in the entry box, Ctrl+C on a selection
in the text. A multi-line paste is flattened to one line (never sent by itself), as before."""
import tkinter as tk


class EditMenuMixin:
    def _bind_edit_menu(self, w):
        """Right-click (and the Menu key / Shift+F10 in the entry box) on a text area or the entry box."""
        if w is getattr(self, "input", None):
            w.bind("<Button-3>", lambda e: self._edit_menu(w, e.x_root, e.y_root), add="+")
            for seq in ("<Shift-F10>", "<Key-Menu>"):
                try:
                    w.bind(seq, lambda e: (self._edit_menu(w, w.winfo_rootx() + 10, w.winfo_rooty() - 4), "break")[1], add="+")
                except tk.TclError:
                    pass
        else:
            w.bind("<Button-3>", lambda e, w=w: self._edit_menu(w, e.x_root, e.y_root, e.x, e.y), add="+")

    # ---- what the menu offers -------------------------------------------------------------------
    def _clipboard_has_text(self):
        try:
            return bool(self.root.clipboard_get())
        except tk.TclError:
            return False

    def _edit_items(self, w, local_x=None, local_y=None):
        """[(label, hotkey, enabled, action)] for the widget that was clicked."""
        out = []
        if w is self.input:
            try:
                has_sel = bool(w.selection_present())
            except tk.TclError:
                has_sel = False
            secret = str(w.cget("show")) != ""                  # a password being typed: nothing leaves the box
            out.append(("Cut", "T", has_sel and not secret, lambda: w.event_generate("<<Cut>>")))
            out.append(("Copy", "C", has_sel and not secret, lambda: w.event_generate("<<Copy>>")))
            out.append(("Paste", "P", self._clipboard_has_text(), lambda: self._on_paste(None)))
            out.append(("Select all", "A", bool(w.get()), lambda: w.select_range(0, "end")))
            out.append(("Clear", "L", bool(w.get()), lambda: w.delete(0, "end")))
            return out
        try:
            has_sel = bool(w.tag_ranges("sel"))
        except tk.TclError:
            has_sel = False
        url = self._link_at(w, local_x, local_y) if local_x is not None else None
        if url:
            out.append(("Open link", "O", True, lambda: self.open_link(url)))
            out.append(("Copy link", "K", True, lambda: self._to_clipboard(url)))
        out.append(("Copy", "C", has_sel, lambda: w.event_generate("<<Copy>>")))
        out.append(("Select all", "A", True, lambda: w.tag_add("sel", "1.0", "end-1c")))
        return out

    def _link_at(self, w, x, y):
        try:
            idx = w.index("@%d,%d" % (x, y))
            r = w.tag_prevrange("link", idx + "+1c")
            if r and w.compare(r[0], "<=", idx) and w.compare(idx, "<", r[1]):
                return w.get(r[0], r[1])
        except tk.TclError:
            pass
        return None

    def _to_clipboard(self, text):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except tk.TclError:
            pass

    # ---- showing it ---------------------------------------------------------------------------------
    def _edit_menu(self, w, x_root, y_root, local_x=None, local_y=None):
        items = self._edit_items(w, local_x, local_y)
        if w is self.input:
            w.focus_set()

        def back():
            try:
                self.root.after_idle(self.input.focus_set)
            except tk.TclError:
                pass
        if self.dos:
            if self._overlay_open():
                return
            dos_items = [{"label": label, "hotkey": hk, "enabled": enabled,
                          "action": (lambda a=action: (a(), back()))} for label, hk, enabled, action in items]
            return self._dos_menu("Edit", dos_items)
        th = self.theme
        m = tk.Menu(self.root, tearoff=0, bg=th["panel"], fg=th["fg"], activebackground=th["select"],
                    activeforeground=th["fg"], disabledforeground=th["dim"])
        for label, _hk, enabled, action in items:
            m.add_command(label=label, state="normal" if enabled else "disabled",
                          command=lambda a=action: (a(), back()))
        self._popup_menu(m, x_root, y_root)
        return m

    def _popup_menu(self, m, x_root, y_root):
        try:
            m.tk_popup(x_root, y_root)                        # (waits until the menu is dismissed)
        finally:
            m.grab_release()
