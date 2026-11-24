"""Several worlds at once: tabs, switching, activity markers.

Each world is a Session (see sanctuary.Session). One is shown; the others keep running and fill
their own scrollback. Things that belong to the screen (the stat bar, the status row, the screen
reader) only follow the shown world; a world that gets new text while hidden is marked instead.
"""
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox

import dosui

MAX_WORLDS = 12                     # Ctrl+F1 .. Ctrl+F12
TAB_FONT_MAX = 13                   # the tab row never grows past this text size
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
        self._cfg_owner = self.session             # the world whose pane settings are in self.cfg right now
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

    def _in_world_cfg(self, fn):
        """Run fn() with the pane settings of the world being handled. For the world on screen that is a plain
        call; for a hidden world the settings in self.cfg are swapped to its own for the duration, so
        something it does (a trigger routing a line to a pane, say) never lands in the visible world's settings."""
        if self._here():
            return fn()
        owner, shown = self.session, self._shown
        self._stash_world_panes(self._cfg_owner)
        self._load_world_panes(owner)
        self._cfg_owner = owner
        try:
            return fn()
        finally:
            self._stash_world_panes(owner)
            self._load_world_panes(shown)
            self._cfg_owner = shown

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
            self._input_show("*" if echo_off else "")
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

    # ---- the row of world tabs (normal look) ---------------------------------------------
    def _build_tabbar(self):
        """A row of clickable tabs, one per world, centred under the toolbar."""
        self._tabbar = self._reg(tk.Frame(self.root), "panel")
        self._tabs_inner = tk.Frame(self._tabbar)
        self._tabs_inner.pack(pady=(6, 0))
        self._tabs_sig = None

    def tab_bar_wanted(self):
        mode = self.cfg.get("world_tabs", "always")
        return (not self.dos) and (mode == "always" or (mode == "two+" and len(self.sessions) > 1))

    def _tab_close(self, s):
        if s is not self._shown:
            self.switch_session(s)
        self.close_world_ask()

    def _tab_menu(self, e, s):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Switch to %s" % self._world_name(s), command=lambda: self.switch_session(s),
                      state="disabled" if s is self._shown else "normal")
        m.add_command(label="Close %s" % self._world_name(s), command=lambda: self._tab_close(s),
                      state="normal" if len(self.sessions) > 1 else "disabled")
        m.add_separator()
        m.add_command(label="Worlds...", command=self.open_worlds)
        self._popup_menu(m, e.x_root, e.y_root)

    def _refresh_tabbar(self, force=False):
        """Rebuild the tabs when something about them changed (a name, which one is shown, news in a hidden world)."""
        bar = getattr(self, "_tabbar", None)
        if bar is None:
            return
        try:
            if not self.tab_bar_wanted():
                if bar.winfo_manager():
                    bar.pack_forget()
                self._tabs_sig = None
                return
            th = self.theme
            size = max(8, min(TAB_FONT_MAX, int(self.cfg.get("font_size", 11))))      # a huge text font must not make a huge tab row
            fkey = (self.font_family, size)
            if fkey != getattr(self, "_tab_font_key", None):
                self._tab_font_key = fkey
                self._tab_fonts = (tkfont.Font(family=fkey[0], size=size), tkfont.Font(family=fkey[0], size=size, weight="bold"))
            f_plain, f_bold = self._tab_fonts
            sig = (tuple((self._world_name(s), s is self._shown, bool(s.unread) and s is not self._shown)
                         for s in self.sessions), th["bg"], th["panel"], th["select"], fkey)
            if not bar.winfo_manager():
                bar.pack(fill="x", after=self._top)
            if sig == self._tabs_sig and not force:
                return
            self._tabs_sig = sig
            for w in self._tabs_inner.winfo_children():
                w.destroy()
            self._tabs_inner.configure(bg=th["panel"])
            for i, s in enumerate(self.sessions, 1):
                shown = s is self._shown
                news = bool(s.unread) and not shown
                bg = th["bg"] if shown else th["button_bg"]
                fg = th["fg"] if shown else th["button_fg"]
                tab = tk.Frame(self._tabs_inner, bg=bg, cursor="hand2")
                tab.pack(side="left", padx=(0, 2))
                text = "%s%d  %s" % ("\u25cf " if news else "", i, self._world_name(s))
                lab = tk.Label(tab, text=text, bg=bg, fg=th["ansi"][11] if news else fg, padx=16, pady=5,
                               font=f_bold if (shown or news) else f_plain, cursor="hand2")
                lab.pack(side="top")
                tk.Frame(tab, height=3, bg=th["select"] if shown else bg).pack(side="top", fill="x")
                for w in (tab, lab):
                    w.bind("<Button-1>", lambda e, s=s: self.switch_session(s))
                    w.bind("<Button-3>", lambda e, s=s: self._tab_menu(e, s))
            if len(self.sessions) < MAX_WORLDS:
                plus = tk.Label(self._tabs_inner, text="+", bg=th["panel"], fg=th["fg"], padx=12, pady=5,
                                font=f_bold, cursor="hand2")
                plus.pack(side="left")
                plus.bind("<Button-1>", lambda e: self.open_worlds())
        except tk.TclError:
            pass

    def _dos_hint_click(self, hint):
        """A click on a key hint in the DOS top row does what pressing the key does."""
        import re
        key = str(hint[0])
        m = re.fullmatch(r"\^F(\d+)", key)
        if m:
            self.goto_world(int(m.group(1)))
        elif key == "^W":
            self.open_worlds()
        elif re.fullmatch(r"F\d+", key):
            self.root.event_generate("<%s>" % key)

    def _refresh_world_label(self):
        lab = self._world_label
        if lab is None:
            return
        self._refresh_tabbar()
        try:
            if self.tab_bar_wanted():
                if lab.winfo_ismapped():
                    lab.pack_forget()
            elif len(self.sessions) > 1:
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
            self._popout_destroy(pane)                     # a pane's own window goes with its world
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

    def cycle_world(self, step):
        """The next (+1) or previous (-1) world, wrapping round; False when there is only one."""
        if len(self.sessions) < 2:
            return False
        i = self.sessions.index(self._shown)
        self.switch_session(self.sessions[(i + step) % len(self.sessions)])
        return True

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
