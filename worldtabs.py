"""Several worlds at once: tabs, switching, activity markers.

Each world is a Session (see sanctuary.Session). One is shown; the others keep running and fill
their own scrollback. Things that belong to the screen (the stat bar, the status row, the screen
reader) only follow the shown world; a world that gets new text while hidden is marked instead.
"""
import tkinter as tk
from tkinter import messagebox

import dosui

MAX_WORLDS = 12                     # Ctrl+F1 .. Ctrl+F12
EMPTY_LAYOUT = {"regions": [], "min_main_cols": 80}


def clean_world_panes(raw, layout):
    """cfg["world_panes"]: {world name (lower case): {"panes", "layout", "panes_hidden"}}, checked."""
    out = {}
    if not isinstance(raw, dict) or layout is None:
        return out
    for name, e in list(raw.items())[:24]:
        if not isinstance(name, str) or len(name) > 60 or not isinstance(e, dict):
            continue
        panes = layout.validate_panes(e.get("panes") if isinstance(e.get("panes"), list) else [])
        lay = layout.validate_layout(e.get("layout"), known_panes=[p["name"] for p in panes])
        ph = e.get("panes_hidden")
        out[name] = {"panes": panes, "layout": lay,
                     "panes_hidden": [x for x in ph[:8] if isinstance(x, str) and len(x) < 20] if isinstance(ph, list) else []}
    return out


class WorldTabsMixin:
    def _worlds_init(self):
        self._shown = self.session
        self.session.unread = False
        self._world_label = None

    # ---- pane settings are kept per world ----------------------------------------------
    @staticmethod
    def _world_key(s):
        return (s.name or "").strip().lower()

    def _stash_world_panes(self, s):
        """The current pane settings belong to world `s`: remember them under its name."""
        import copy
        store = self.cfg.setdefault("world_panes", {})
        key = self._world_key(s)
        store[key] = {"panes": copy.deepcopy(self.cfg.get("panes", [])),
                      "layout": copy.deepcopy(self.cfg.get("layout", EMPTY_LAYOUT)),
                      "panes_hidden": list(self.cfg.get("panes_hidden", []))}
        while len(store) > 24:                         # keep the newest; never drop the world on screen
            for k in list(store):
                if k != key:
                    del store[k]
                    break

    def _load_world_panes(self, s):
        """Make world `s`'s saved pane settings the current ones (an empty layout for a new world)."""
        import copy
        e = self.cfg.get("world_panes", {}).get(self._world_key(s))
        if e is None:
            e = {"panes": [], "layout": EMPTY_LAYOUT, "panes_hidden": []}
        self.cfg["panes"] = copy.deepcopy(e["panes"])
        self.cfg["layout"] = copy.deepcopy(e["layout"])
        self.cfg["panes_hidden"] = list(e["panes_hidden"])

    def _rename_world(self, s, name):
        """A world that dials a saved one takes its name (and that name's remembered panes, if any)."""
        name = (name or "").strip()
        if not name or name == s.name:
            return
        old_key = self._world_key(s)
        had = self.cfg.get("world_panes", {}).get(name.lower())
        if s is self._shown:
            if had is not None:
                s.name = name
                self._load_world_panes(s)
                self._region_active = {}
                self.schedule_layout(5)
            else:
                s.name = name
                self._stash_world_panes(s)
        else:
            s.name = name
        if old_key != self._world_key(s) and old_key.startswith("world "):
            self.cfg.get("world_panes", {}).pop(old_key, None)     # a placeholder name is not worth remembering

    # ---- which world is on screen --------------------------------------------------
    def _here(self):
        """True when the world being handled right now is the one on screen."""
        return self.session is getattr(self, "_shown", self.session)

    def _world_number(self, s):
        return self.sessions.index(s) + 1

    def _world_name(self, s):
        return (s.name or "World %d" % self._world_number(s)).strip()

    def world_tabs_text(self):
        """'[1 Duskholm]  2 Other*' — the shown world in brackets, '*' on a world with news."""
        parts = []
        for i, s in enumerate(self.sessions, 1):
            mark = "*" if getattr(s, "unread", False) and s is not self._shown else ""
            if s is self._shown:
                parts.append("[%d %s]" % (i, self._world_name(s)))
            else:
                parts.append("%d %s%s" % (i, self._world_name(s), mark))
        return "  ".join(parts)

    def world_hints(self):
        """Top-bar hints, one per world beyond the first: (key, label, priority)."""
        if len(self.sessions) < 2:
            return []
        out = []
        for i, s in enumerate(self.sessions, 1):
            if i > MAX_WORLDS:
                break
            name = self._world_name(s)
            label = "[%s]" % name if s is self._shown else name + ("*" if s.unread else "")
            out.append(("^F%d" % i, label, 9.5 if (s is self._shown or s.unread) else 6))
        return out

    # ---- keeping the shared screen in step with the shown world -----------------------
    def _sync_session_ui(self):
        """Toolbar, status and bars show the shown world's connection."""
        s = self._shown
        prev, self.session = self.session, s
        try:
            if s.connected:
                self.btn.configure(text="Disconnect")
                self.status.configure(text="Connected")
            elif s.connecting:
                self.btn.configure(text="Cancel")
                self.status.configure(text="Connecting…")
            elif s._retrying:
                self.btn.configure(text="Cancel retry")
                self.status.configure(text="Reconnecting")
            else:
                self.btn.configure(text="Connect")
                self.status.configure(text="Disconnected")
            self.v_host.set(s.host)
            self.v_port.set(str(s.port))
            self.v_tls.set(bool(s.tls))
            echo_off = bool(getattr(s.term, "echo_off", False))
            self.input.configure(show="*" if echo_off else "")
            if s._last_prompt:
                self.statbar.set_data(self._prompt_view())
                self._statbar_show()
            else:
                self._statbar_hide()
            self._start_cd_tick()
            self.update_dosbar()
            self._refresh_world_label()
        finally:
            self.session = prev

    def _refresh_world_label(self):
        lab = self._world_label
        if lab is None:
            return
        try:
            if len(self.sessions) > 1:
                lab.configure(text=self.world_tabs_text())
                if not lab.winfo_ismapped():
                    lab.pack(side="right", padx=8)
            elif lab.winfo_ismapped():
                lab.pack_forget()
        except tk.TclError:
            pass

    def _refresh_world_ui(self):
        """Redraw tabs and bars from whichever world is being handled."""
        prev, self.session = self.session, self._shown
        try:
            self.update_dosbar()
            self._refresh_world_label()
        finally:
            self.session = prev

    def _mark_activity(self):
        """The world being handled got text while another one is on screen."""
        s = self.session
        if s.unread:
            return
        s.unread = True
        if self.cfg.get("bell"):
            try:
                self.root.bell()
            except tk.TclError:
                pass
        self._refresh_world_ui()

    # ---- opening, switching, closing --------------------------------------------------
    def goto_world(self, n):
        """Show world number n (1-based). Returns False if there is none."""
        if not 1 <= n <= len(self.sessions):
            return False
        self.switch_session(self.sessions[n - 1])
        return True

    def open_new_world(self, name=""):
        if len(self.sessions) >= MAX_WORLDS:
            self.system("No more than %d worlds at once." % MAX_WORLDS)
            return None
        s = self.add_session(name or "World %d" % (len(self.sessions) + 1))
        self.switch_session(s)
        return s

    def close_world(self, s=None):
        """Hang up and remove a world (the last one cannot be closed)."""
        s = s or self.session
        if len(self.sessions) < 2 or s not in self.sessions:
            return False
        if s is self._shown:
            nxt = self.sessions[max(0, self.sessions.index(s) - 1)]
            if nxt is s:
                nxt = self.sessions[1]
            self.switch_session(nxt)
        prev, self.session = self.session, s
        try:
            self._cancel_reconnect()
            s.conn.close()
            if s.logfile:
                try:
                    s.logfile.close()
                except OSError:
                    pass
                s.logfile = None
            if s._flush_job is not None:
                try:
                    self.root.after_cancel(s._flush_job)
                except tk.TclError:
                    pass
        finally:
            self.session = prev
        for pane in list(s._panes.values()):
            for w in (pane["text"], pane["sb"], pane["dsb"]):
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        for ui in list(s._region_ui.values()):
            try:
                ui["frame"].destroy()
            except tk.TclError:
                pass
        self._themed = [(w, r) for (w, r) in self._themed
                        if not any(w is p[k] for p in s._panes.values() for k in ("text", "sb"))]
        self.sessions.remove(s)
        if self._world_key(s).startswith("world "):
            self.cfg.get("world_panes", {}).pop(self._world_key(s), None)
        self._themed = [(w, r) for (w, r) in self._themed if w not in (s.out, s._sb, s._mid)]
        try:
            s._mid.destroy()
        except tk.TclError:
            pass
        self._refresh_world_ui()
        return True

    def close_world_ask(self):
        """Close the world on screen (menu entry / Ctrl+Shift+W): asks first if it is still connected."""
        s = self._shown
        if len(self.sessions) < 2:
            self.system("That is the only world; use Exit to leave.")
            return
        name = self._world_name(s)
        live = s.connected or s.connecting or s._retrying
        if not live:
            self.close_world(s)
            return
        text = "Hang up and close %s?" % name
        if self.dos:
            self._overlay = dosui.confirm(self.root, "Close world", text, self._dc(), self.f_norm,
                                          lambda r, v: self.close_world(s) if r == "yes" else None)
        elif messagebox.askyesno("Close world", text, parent=self.root):
            self.close_world(s)

    def _bind_world_keys(self):
        for seq in ("<Control-Shift-W>", "<Control-Shift-w>"):
            self.root.bind(seq, lambda e: (self.close_world_ask(), "break")[1])
        for n in range(1, MAX_WORLDS + 1):
            self.root.bind("<Control-F%d>" % n, lambda e, n=n: (self.goto_world(n), "break")[1])

    def _worlds_command(self, cmd, arg):
        """/world [n|name]  /newworld [name]  /closeworld"""
        if cmd == "world":
            if not arg:
                self.system("Worlds: " + self.world_tabs_text() + "   (Ctrl+F1..F12 switches; /newworld, /closeworld)")
            elif arg.isdigit() and self.goto_world(int(arg)):
                pass
            else:
                hit = [s for s in self.sessions if self._world_name(s).lower().startswith(arg.lower())]
                if hit:
                    self.switch_session(hit[0])
                else:
                    self.system("No world called '%s'." % arg)
            return True
        if cmd == "newworld":
            self.open_new_world(arg)
            return True
        if cmd == "closeworld":
            if not self.close_world():
                self.system("That is the only world; use /quit to leave.")
            return True
        return False
