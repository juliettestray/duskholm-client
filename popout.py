"""Pop a capture pane out into a window of its own (a second monitor, say), and dock it back.

Tk cannot move a widget into another window, so a popped-out pane is a second view: a window with its own text area that
is filled from the pane's history and then gets every new line as it arrives. The docked text area keeps filling too (it
is the pane's memory, so docking back is instant); while the pane is out its tab leaves the main window, and an area
whose panes are all out disappears, giving the room back to the main text. Colours, links, colour emoji, time stamps and
"follow the newest line" work as they do in the docked pane. A pane belongs to a world and keeps updating while that
world is not on screen, which is what a second monitor is for. Where the window was, and whether it was out, is
remembered with the pane (per world) and comes back next time.

Ways in: the arrow at the right of a pane area's header, `/popout <pane>`; back: the Dock button, closing the window, or
`/dock <pane>`."""
import re
import tkinter as tk

DEFAULT_SIZE = "520x420"
SAVE_AFTER_MS = 600
_GEOMETRY = re.compile(r"^\d+x\d+([+-]-?\d+){0,2}$")


class PopOutMixin:
    # ---- the pieces other code asks -------------------------------------------------------------------------------
    def _popped(self, name):
        p = self._panes.get(str(name).strip().lower())
        return bool(p and p.get("popout"))

    def _popout_texts(self):
        """The text areas of every pane window that is open, in any world."""
        out = []
        for s in self.sessions:
            for p in s._panes.values():
                v = p.get("popout")
                if v:
                    out.append(v["text"])
        return out

    # ---- commands ---------------------------------------------------------------------------------------------------
    def _popout_command(self, cmd, arg):
        """/popout <pane>   /dock <pane>   (with no name: which panes there are)"""
        if cmd not in ("popout", "dock"):
            return False
        name = (arg or "").strip()
        if not name:
            names = ["%s%s" % (d["name"], " (out)" if self._popped(d["name"]) else "") for d in self.cfg["panes"]]
            self.system("Panes: %s.   /popout <pane> puts one in its own window, /dock <pane> brings it back."
                        % (", ".join(names) if names else "none yet"))
            return True
        d = self._find_pane_def(name)
        if d is None:
            self.system("No pane called '%s'." % name)
        elif cmd == "popout":
            self.pop_out_pane(d["name"])
        elif not self.dock_pane(d["name"]):
            self.system("%s is not in its own window." % d["name"])
        return True

    def _popout_region_active(self, rid):
        reg = next((r for r in self.cfg["layout"]["regions"] if r["id"] == rid), None)
        key = self._active_pane_key(reg) if reg else None
        if key:
            self.pop_out_pane(key)

    # ---- opening ------------------------------------------------------------------------------------------------------
    def pop_out_pane(self, name):
        """Open the pane in its own window (or bring that window forward). Returns the window's view, or None."""
        key = str(name).strip().lower()
        pane = self._panes.get(key) or self.pane_ensure(name)
        if pane is None:
            return None
        if pane.get("popout"):
            self._popout_raise(pane["popout"])
            return pane["popout"]
        d = self._find_pane_def(key)
        if d is None:
            return None
        win = tk.Toplevel(self.root)
        win.title("%s - %s" % (d["title"], self._world_name(self.session)))
        geo = (d.get("window") or {}).get("geometry")
        if not (isinstance(geo, str) and _GEOMETRY.match(geo)):
            geo = "%s+%d+%d" % (DEFAULT_SIZE, self.root.winfo_rootx() + 80, self.root.winfo_rooty() + 80)
        try:
            win.geometry(geo)
        except tk.TclError:
            win.geometry(DEFAULT_SIZE)
        bar = tk.Frame(win)
        bar.pack(side="top", fill="x")
        tk.Button(bar, text="Dock", width=7, command=lambda: self.dock_pane(key)).pack(side="left", padx=(6, 3), pady=4)
        tk.Button(bar, text="Clear", width=7, command=lambda: self.pane_clear(key)).pack(side="left", padx=3, pady=4)
        box = tk.Frame(win)
        box.pack(side="top", fill="both", expand=True)
        sb = tk.Scrollbar(box)
        sb.pack(side="right", fill="y")
        text = tk.Text(box, font=self.f_norm, wrap="word", state="disabled", borderwidth=0, highlightthickness=0,
                       padx=8, pady=4, cursor="arrow")
        text.pack(side="left", fill="both", expand=True)
        sb.configure(command=text.yview)
        text.configure(yscrollcommand=sb.set)
        view = {"key": key, "session": self.session, "win": win, "text": text, "sb": sb, "follow": True,
                "settling": False, "unread": 0, "save_job": None}
        pane["popout"] = view                                # (from here the text counts among the text areas)
        for w, role in ((win, "panel"), (bar, "panel"), (box, "frame"), (text, "text"), (sb, "scroll")):
            self._reg(w, role)
        self._theme_tree(win)
        self._bind_links(text)                               # (this also makes the link style, which tags are raised over)
        self._bind_edit_menu(text)
        for tag in self._tags:                               # the new window needs the colour tags too
            self._style_tag(tag)
        text.tag_configure("echo"), text.tag_configure("system")
        self._restyle_tags()
        self._apply_spacing()
        text.configure(state="normal")
        for pieces in pane["history"]:
            for t, k in pieces:
                text.insert("end", t, self._tag_for(k))
            text.insert("end", "\n")
        if self.cfg.get("links", True):
            self._linkify(text, "1.0")
        if self._emoji_pics_on():
            self._emojify(text, "1.0")
        text.configure(state="disabled")
        text.see("end")
        for w in (text, sb):
            for seq in ("<MouseWheel>", "<ButtonRelease-1>", "<KeyRelease>", "<B1-Motion>"):
                try:
                    w.bind(seq, lambda e, v=view: self._pane_user_scrolled(v), add="+")
                except tk.TclError:
                    pass
        win.protocol("WM_DELETE_WINDOW", lambda: self.dock_pane(key))
        win.bind("<Configure>", lambda e, v=view: self._popout_moved(v) if e.widget is v["win"] else None)
        self._popout_clamp(win)
        pane["unread"] = 0
        d["window"] = {"out": True, "geometry": win.geometry()}
        self._save_settings()
        self.schedule_layout(5)
        self._style_region_ui()
        return view

    def _popout_raise(self, view):
        try:
            view["win"].deiconify()
            view["win"].lift()
        except tk.TclError:
            pass

    def _popout_clamp(self, win):
        """A window remembered on a monitor that is no longer there comes back onto the screen."""
        try:
            win.update_idletasks()
            m = re.match(r"^(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$", win.geometry())
            if not m:
                return
            w, h = int(m.group(1)), int(m.group(2))
            x, y = int(m.group(3).replace("+", "", 1)), int(m.group(4).replace("+", "", 1))
            vx, vy = win.winfo_vrootx(), win.winfo_vrooty()
            vw, vh = win.winfo_vrootwidth(), win.winfo_vrootheight()
            nx = max(vx - w + 120, min(x, vx + vw - 120))
            ny = max(vy, min(y, vy + vh - 80))
            if (nx, ny) != (x, y):
                win.geometry("%dx%d+%d+%d" % (w, h, nx, ny))
        except (tk.TclError, ValueError):
            pass

    # ---- closing ------------------------------------------------------------------------------------------------------
    def dock_pane(self, name):
        """Close the pane's window; the pane is back in its area. False if it was not out."""
        key = str(name).strip().lower()
        pane = self._panes.get(key)
        view = pane.get("popout") if pane else None
        if not view:
            return False
        d = self._find_pane_def(key)
        if d is not None:
            try:
                geo = view["win"].geometry()
            except tk.TclError:
                geo = (d.get("window") or {}).get("geometry")
            d["window"] = {"out": False, "geometry": geo} if geo else {"out": False}
        self._popout_destroy(pane)
        self._save_settings()
        self.schedule_layout(5)
        self._style_region_ui()
        return True

    def _popout_destroy(self, pane):
        view = pane.get("popout")
        if not view:
            return
        pane["popout"] = None
        if view.get("save_job") is not None:
            try:
                self.root.after_cancel(view["save_job"])
            except tk.TclError:
                pass
        win = view["win"]
        gone = str(win)
        self._themed = [(w, r) for (w, r) in self._themed if not str(w).startswith(gone)]
        try:
            win.destroy()
        except tk.TclError:
            pass

    # ---- the window moves and resizes: remember where it is ---------------------------------------------------------------
    def _popout_moved(self, view):
        if view.get("save_job") is not None:
            try:
                self.root.after_cancel(view["save_job"])
            except tk.TclError:
                pass
        try:
            view["save_job"] = self.root.after(SAVE_AFTER_MS, lambda: self._popout_save_geometry(view))
        except tk.TclError:
            view["save_job"] = None

    def _popout_save_geometry(self, view):
        view["save_job"] = None
        pane = view["session"]._panes.get(view["key"])
        if not pane or pane.get("popout") is not view:
            return
        try:
            geo = view["win"].geometry()
        except tk.TclError:
            return

        def store():
            d = self._find_pane_def(view["key"])
            if d is not None and (d.get("window") or {}).get("geometry") != geo:
                d["window"] = {"out": True, "geometry": geo}
                self._save_settings()
        prev, self.session = self.session, view["session"]
        try:
            self._in_world_cfg(store)
        finally:
            self.session = prev

    # ---- the lines ------------------------------------------------------------------------------------------------------------
    def _popout_append(self, pane, d, pieces):
        """One more line for the window (called as it goes into the docked pane)."""
        view = pane.get("popout")
        if not view:
            return
        text = view["text"]
        try:
            text.configure(state="normal")
            first = text.index("end-1c")
            for t, k in pieces:
                text.insert("end", t, self._tag_for(k))
            text.insert("end", "\n")
            if self.cfg.get("links", True):
                self._linkify(text, first)
            if self._emoji_pics_on():
                self._emojify(text, first)
            over = int(text.index("end-1c").split(".")[0]) - 1 - d["max_lines"]
            if over > 0:
                text.delete("1.0", "%d.0" % (over + 1))
            text.configure(state="disabled")
        except tk.TclError:
            return
        if view["follow"]:
            text.see("end")
            self._pane_follow_soon(view)

    def _popout_clear(self, pane):
        view = pane.get("popout")
        if view:
            try:
                view["text"].configure(state="normal")
                view["text"].delete("1.0", "end")
                view["text"].configure(state="disabled")
            except tk.TclError:
                pass
            view["follow"] = True

    # ---- coming back after a restart ------------------------------------------------------------------------------------------
    def _restore_popouts(self):
        """Open the windows that were out when the world on screen was last used (a pane that has no lines yet is
        made empty, so its window is there waiting)."""
        for d in list(self.cfg.get("panes", [])):
            if (d.get("window") or {}).get("out") and not self._popped(d["name"]):
                try:
                    self.pop_out_pane(d["name"])
                except tk.TclError:
                    pass
