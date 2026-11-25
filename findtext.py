"""Find in the main text: Ctrl+F opens a small Find box, Ctrl+Shift+F finds the next match without it.

The search is plain text, ignores case, and looks in the main window of the world on screen (and, only when the
*Search panes* box is ticked, in that world's capture panes and pop-out windows too, main window first, then each pane). *From the bottom* (the
default) starts at the newest line and works up, so the first match is the most recent one and each further match is
older; *From the top* starts at the oldest line and works down. When there is nothing more in that direction it says so
and starts again from the far end. The match is shown in reverse colours and scrolled into view. The choice is
remembered (Options file); the word searched for is not."""
import tkinter as tk

FROM_CHOICES = ("bottom", "top")
HIT_TAG = "findhit"


class FindMixin:
    def _find_state(self):
        st = getattr(self, "_find", None)
        if st is None:
            st = self._find = {"term": "", "pos": None, "out": None, "win": None, "ti": 0}
        return st

    def find_from(self):
        return "top" if self.cfg.get("find_from") == "top" else "bottom"

    def find_set_from(self, frm):
        frm = "top" if frm == "top" else "bottom"
        if frm != self.find_from():                    # (only a change of direction starts the search over)
            self.cfg["find_from"] = frm
            self._save_settings()
            self._find_reset()

    def _find_reset(self):
        st = self._find_state()
        st["pos"], st["ti"] = None, 0

    def find_panes(self):
        return self.cfg.get("find_panes") is True

    def find_set_panes(self, on):
        on = bool(on)
        if on != self.find_panes():                    # (a different place to look starts the search over)
            self.cfg["find_panes"] = on
            self._save_settings()
            self._find_reset()

    def find_case(self):
        return self.cfg.get("find_case") is True

    def find_set_case(self, on):
        on = bool(on)
        if on != self.find_case():                     # (a different kind of match starts the search over)
            self.cfg["find_case"] = on
            self._save_settings()
            self._find_reset()

    def find_set_term(self, term):
        term = str(term or "").replace("\r", " ").replace("\n", " ")[:200]
        st = self._find_state()
        if term != st["term"]:
            st["term"], st["pos"], st["ti"] = term, None, 0

    def find_clear(self):
        st = self._find_state()
        for w in self._text_widgets():
            try:
                w.tag_remove(HIT_TAG, "1.0", "end")
            except tk.TclError:
                pass
        st["pos"], st["ti"] = None, 0

    def _find_targets(self):
        """[(pane name or '', text area, pane)]: the main window, then (with Search panes on) each pane of this world,
        looking in its own window when it has been popped out."""
        out = [("", self._shown.out, None)]
        if self.find_panes():
            for key, p in list(self._panes.items()):
                v = p.get("popout")
                out.append((key, v["text"] if v else p["text"], p))
        return out

    def _find_show_pane(self, key, pane, w, idx):
        """Bring the pane the match is in to the front (its tab, or its window) and keep the match in view."""
        try:
            self.select_pane(key)                      # (a popped-out pane: its window comes forward)
            w.see(idx)
            pane["follow"] = False                     # new lines must not scroll the match away
        except (tk.TclError, KeyError):
            pass

    def find_next(self):
        """Go to the next match in the chosen direction. Returns True when one was found."""
        st = self._find_state()
        term = st["term"]
        if not term:
            self.open_find()
            return False
        targets = self._find_targets()
        if st["out"] is not self._shown.out:           # another world came on screen: start over there
            st["pos"], st["ti"], st["out"] = None, 0, self._shown.out
        ti = st["ti"] if 0 <= st["ti"] < len(targets) else 0
        back = self.find_from() == "bottom"
        wrapped = False
        idx = None
        for attempt in range(len(targets) + 1):
            label, out, pane = targets[ti]
            start = ("end-1c" if back else "1.0") if st["pos"] is None else st["pos"]
            try:
                idx = out.search(term, start, stopindex="1.0" if back else "end-1c", backwards=back, nocase=not self.find_case())
            except tk.TclError:
                idx = None
            if idx:
                break
            st["pos"] = None                           # ran out in this one: on to the next, and round to the first
            ti += 1
            if ti >= len(targets):
                ti, wrapped = 0, True
        if not idx:
            for w in self._text_widgets():
                try:
                    w.tag_remove(HIT_TAG, "1.0", "end")
                except tk.TclError:
                    pass
            st["ti"] = 0
            self.set_notice("Not found: %s" % term[:60], 8)
            return False
        end = "%s+%dc" % (idx, len(term))
        for w in self._text_widgets():
            try:
                w.tag_remove(HIT_TAG, "1.0", "end")
            except tk.TclError:
                pass
        try:                                           # reverse video of the window's own colours: readable in every skin
            out.tag_configure(HIT_TAG, background=out.cget("foreground"), foreground=out.cget("background"))
        except tk.TclError:
            pass
        out.tag_add(HIT_TAG, idx, end)
        out.tag_raise(HIT_TAG)
        st["pos"], st["ti"] = (idx if back else end), ti
        out.see(idx)
        if pane is not None:
            self._find_show_pane(label, pane, out, idx)
        self.set_notice(("Wrapped round: " if wrapped else "") + "Found '%s'%s (searching from the %s). Ctrl+Shift+F for the next."
                        % (term[:40], " in %s" % label if label else "", "bottom" if back else "top"), 8)
        return True

    def find_next_key(self):
        """Ctrl+Shift+F: the next match, or the Find box when there is nothing to look for yet."""
        if not self._find_state()["term"]:
            return self.open_find()
        return self.find_next()

    # ---- the box ----------------------------------------------------------------------------------------------
    def _find_prefill(self):
        st = self._find_state()
        try:
            out = self._shown.out
            if out.tag_ranges("sel"):
                text = out.get("sel.first", "sel.last")
                if text.strip() and "\n" not in text.strip() and len(text) <= 100:
                    return text.strip()
        except tk.TclError:
            pass
        return st["term"]

    def open_find(self):
        if self._overlay_open():
            return None
        if self.dos:
            return self._dos_find_dialog()
        st = self._find_state()
        win = st.get("win")
        if win is not None:
            try:
                if win.winfo_exists():
                    win.deiconify(); win.lift()
                    win._entry.focus_set(); win._entry.select_range(0, "end")
                    return win
            except tk.TclError:
                pass
        win = tk.Toplevel(self.root)
        st["win"] = win
        win.title("Find")
        win.transient(self.root)
        try:
            win.geometry("+%d+%d" % (self.root.winfo_rootx() + 80, self.root.winfo_rooty() + 80))
        except tk.TclError:
            pass
        term = tk.StringVar(value=self._find_prefill())
        frm = tk.StringVar(value=self.find_from())
        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="Find:").pack(side="left")
        ent = tk.Entry(top, textvariable=term, width=34)
        ent.pack(side="left", padx=6, fill="x", expand=True)
        rf = tk.Frame(win)
        rf.pack(fill="x", padx=10)
        tk.Label(rf, text="Start:").pack(side="left")
        radios = [tk.Radiobutton(rf, text=t, value=v, variable=frm, command=lambda: changed())
                  for v, t in (("bottom", "from the bottom (newest first)"), ("top", "from the top (oldest first)"))]
        for r in radios:
            r.pack(side="left", padx=(6, 0))
        case = tk.BooleanVar(value=self.find_case())
        cf = tk.Frame(win)
        cf.pack(fill="x", padx=10, pady=(2, 0))
        mc = tk.Checkbutton(cf, text="Match case", variable=case, command=lambda: changed())
        mc.pack(side="left")
        panes = tk.BooleanVar(value=self.find_panes())
        sp = tk.Checkbutton(cf, text="Search panes", variable=panes, command=lambda: changed())
        sp.pack(side="left", padx=(12, 0))
        msg = tk.Label(win, anchor="w", text="Enter finds the next one. Ctrl+Shift+F does too, with this box closed.")
        msg.pack(fill="x", padx=10, pady=(6, 0))

        def changed(*_a):
            self.find_set_from(frm.get())
            self.find_set_case(case.get())
            self.find_set_panes(panes.get())
            self.find_set_term(term.get())

        def go(_e=None):
            self.find_set_term(term.get())
            self.find_set_from(frm.get())
            self.find_set_case(case.get())
            self.find_set_panes(panes.get())
            if not term.get().strip():
                msg.configure(text="Type what to look for.")
                return "break"
            ok = self.find_next()
            msg.configure(text="Found it." if ok else "Not found: %s" % term.get()[:50])
            return "break"

        def close(_e=None):
            self.find_clear()
            st["win"] = None
            win.destroy()
            try:
                self.input.focus_set()
            except tk.TclError:
                pass
            return "break"

        row = tk.Frame(win)
        row.pack(fill="x", padx=10, pady=10)
        tk.Button(row, text="Find next", width=10, command=go).pack(side="left")
        tk.Button(row, text="Close", width=8, command=close).pack(side="right")
        for w in (win, ent):
            w.bind("<Return>", go)
            w.bind("<KP_Enter>", go)
            w.bind("<Escape>", close)
        for seq in ("<Control-Shift-f>", "<Control-Shift-F>"):
            win.bind(seq, go)
        for seq in ("<Control-f>", "<Control-F>"):
            ent.bind(seq, lambda e: (ent.select_range(0, "end"), "break")[1] if not (e.state & 1) else go())
        win.protocol("WM_DELETE_WINDOW", close)
        win._entry, win._term, win._from, win._msg, win._go, win._close = ent, term, frm, msg, go, close
        win._radios, win._case, win._matchcase = radios, case, mc
        win._panes_var, win._searchpanes = panes, sp
        self._theme_tree(win)
        ent.focus_set()
        ent.select_range(0, "end")
        return win

    def _dos_find_dialog(self):
        fields = [{"key": "term", "label": "Find", "type": "text", "value": self._find_prefill(), "width": 40},
                  {"key": "top", "label": "Start from the top (off: from the bottom)", "type": "check",
                   "value": self.find_from() == "top"},
                  {"key": "case", "label": "Match case", "type": "check", "value": self.find_case()},
                  {"key": "panes", "label": "Search panes", "type": "check", "value": self.find_panes()}]

        def result(res, vals):
            if res != "find":
                return
            self.find_set_term(str(vals.get("term", "")))
            self.find_set_from("top" if vals.get("top") else "bottom")
            self.find_set_case(bool(vals.get("case")))
            self.find_set_panes(bool(vals.get("panes")))
            self.root.after_idle(lambda: self.find_next() if self._find_state()["term"].strip() else None)
        return self._dos_dialog("Find", fields, [("Find", "find"), ("Cancel", "cancel")], result, width=62,
                                message="Ctrl+Shift+F finds the next match afterwards.")

    # ---- /find ----------------------------------------------------------------------------------------------
    def _find_command(self, cmd, arg):
        """/find [words]  /findnext"""
        if cmd == "find":
            if arg.strip():
                self.find_set_term(arg.strip())
                self.find_next()
            else:
                self.open_find()
            return True
        if cmd in ("findnext", "findn"):
            self.find_next_key()
            return True
        return False
