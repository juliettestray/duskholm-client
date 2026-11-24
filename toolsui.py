"""Windows for the colour tools and the customize form (mixed into the App).

The logic lives in colortools.py and custom.py; this file only shows it. Each tool works in both
looks: an ordinary window in the normal look, and DOS dialogs and menus in the DOS look."""
import tkinter as tk

import colortools as ct
import custom
import gradwin

try:
    import dosui
except ImportError:
    dosui = None


class ToolsMixin:
    def _tools_init(self):
        self._grad_win = None
        self._grad_state = {"pattern": "Fire", "mode": "stretch", "text": "", "prefix": "", "smooth": True}
        self._cust_win = None
        self._cust_values = custom.blank()
        self._cust_type = "clothing"

    # ---- showing coloured text on the screen ---------------------------------------------
    def show_coloured(self, coded, lead=""):
        """Put game-coded text (with `NNN codes) on the main screen as it will look in the game."""
        self._settle()
        pieces = []
        if lead:
            pieces.append((lead, "system"))
        for text, idx in ct.runs(coded):
            key = (ct.XTERM[idx] if idx is not None else None, None, False, False, False, False)
            pieces.append((text, self._tag_for(key)))
        pieces.append(("\n", None))
        self._append(pieces)

    def put_in_input(self, text):
        self.input.delete(0, "end")
        self.input.insert(0, text)
        self.input.icursor("end")
        self.input.focus_set()

    # ---- hex -> xterm --------------------------------------------------------------------
    def hex_report(self, text, system=False):
        rows = ct.convert_many(text, system)
        if not rows:
            self.system("Give a hex colour, for example /hex ff8800 or /hex #f80 3366cc")
            return
        for r in rows:
            if "error" in r:
                self.system(r["error"])
                continue
            self._settle()
            sw = (r["hex"], None, False, False, False, False)
            asked = (r["asked"], None, False, False, False, False)
            self._append([("  %s " % r["input"], "system"), ("██", self._tag_for(asked)),
                          ("  is closest to xterm %d " % r["index"], "system"),
                          ("██", self._tag_for(sw)),
                          (" %s   code: %s\n" % (r["hex"], r["code"]), "system")])

    def open_hex(self):
        if self.dos:
            fields = [{"key": "hex", "label": "Hex colour(s)", "type": "text", "value": "", "width": 40},
                      {"key": "sys", "label": "May use the first 16 colours", "type": "check", "value": False}]

            def result(res, vals):
                if res == "convert":
                    self.hex_report(vals.get("hex", ""), bool(vals.get("sys")))
            return self._dos_dialog("Hex to xterm", fields, [("Convert", "convert"), ("Close", "cancel")], result,
                                    width=62, message="e.g. ff8800  #f80  3366cc. The code (like `208) goes in game text.")
        top = tk.Toplevel(self.root)
        top.title("Hex to xterm")
        top.transient(self.root)
        v, s = tk.StringVar(), tk.BooleanVar(value=False)
        tk.Label(top, text="Hex colour(s), e.g. ff8800  #f80  3366cc").grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")
        e = tk.Entry(top, textvariable=v, width=46)
        e.grid(row=1, column=0, padx=10, sticky="w")
        tk.Checkbutton(top, text="May use the first 16 (system) colours, which depend on your palette",
                       variable=s).grid(row=2, column=0, padx=10, sticky="w")
        out = tk.Text(top, width=60, height=8, font=self.f_norm, state="disabled", wrap="none")
        out.grid(row=3, column=0, padx=10, pady=6)

        def convert(*_):
            out.configure(state="normal")
            out.delete("1.0", "end")
            for r in ct.convert_many(v.get(), s.get()):
                if "error" in r:
                    out.insert("end", r["error"] + "\n")
                    continue
                a, b = "a%s" % r["asked"], "b%s" % r["hex"]
                out.tag_configure(a, foreground=r["asked"])
                out.tag_configure(b, foreground=r["hex"])
                out.insert("end", "%s " % r["input"])
                out.insert("end", "██", a)
                out.insert("end", " -> xterm %d " % r["index"])
                out.insert("end", "██", b)
                out.insert("end", " %s   %s\n" % (r["hex"], r["code"]))
            out.configure(state="disabled")
        bf = tk.Frame(top)
        bf.grid(row=4, column=0, pady=8)
        tk.Button(bf, text="Convert", width=9, command=convert).pack(side="left", padx=4)
        tk.Button(bf, text="Close", width=9, command=top.destroy).pack(side="left", padx=4)
        top.bind("<Return>", convert)
        top.bind("<Escape>", lambda ev: top.destroy())
        self._theme_tree(top)
        e.focus_set()
        return top

    # ---- gradients -----------------------------------------------------------------------
    def _pattern_colours(self, text):
        """A pattern named by the user (a preset, a saved one) or typed as colours."""
        named = ct.find_pattern(text, self.cfg.get("gradients", []))
        return named if named is not None else ct.parse_colours(text)

    def make_gradient(self, state):
        """(coded text or None, message)."""
        try:
            stops = self._pattern_colours(state.get("pattern", ""))
            body = ct.apply(state.get("text", "").replace("\\n", "\n"), stops, state.get("mode", "stretch") or "stretch",
                            bool(state.get("smooth", True)))
        except ValueError as e:
            return None, str(e)
        if not state.get("text", "").strip():
            return None, "Type some text to colour."
        return (state.get("prefix", "") or "") + body, ""

    def save_pattern(self, name, pattern_text):
        try:
            cols = self._pattern_colours(pattern_text)
        except ValueError as e:
            return False, str(e)
        name = " ".join(str(name).split())[:30]
        if not name:
            return False, "Give the pattern a name."
        if name.lower() in (k.lower() for k in ct.PRESETS):
            return False, "'%s' is one of the built-in patterns; pick another name." % name
        saved = [s for s in self.cfg.get("gradients", []) if s["name"].lower() != name.lower()]
        if len(saved) >= ct.MAX_SAVED:
            return False, "Too many saved patterns (at most %d)." % ct.MAX_SAVED
        saved.append({"name": name, "colours": cols[:32]})
        self.cfg["gradients"] = ct.validate_saved(saved)
        self._save_settings()
        return True, "Saved the pattern '%s'." % name

    def delete_pattern(self, name):
        before = len(self.cfg.get("gradients", []))
        self.cfg["gradients"] = [s for s in self.cfg.get("gradients", []) if s["name"].lower() != str(name).lower()]
        self._save_settings()
        return len(self.cfg["gradients"]) < before

    def open_gradient(self, state=None):
        st = dict(self._grad_state if state is None else state)
        if self.dos:
            return self._dos_gradient(st)
        if self._grad_win is not None:
            try:
                self._grad_win.lift()
                return self._grad_win
            except tk.TclError:
                self._grad_win = None
        top = self._grad_win = tk.Toplevel(self.root)
        top.title("Gradient")
        top.transient(self.root)
        stops0 = self._grad_stops(st)
        panel = gradwin.GradientPanel(top, self, {"stops": stops0, "mode": st["mode"], "smooth": st["smooth"],
                                                  "pattern": self._grad_label(st, stops0)},
                                      lambda: refresh(), self.theme)
        panel.grid(row=0, column=0, columnspan=2, sticky="we", padx=10, pady=(8, 2))
        top.columnconfigure(1, weight=1)
        prefix = tk.StringVar(value=st["prefix"])
        r = 1

        def row(label, w, sticky="w"):
            nonlocal r
            tk.Label(top, text=label).grid(row=r, column=0, sticky="nw", padx=(10, 6), pady=3)
            w.grid(row=r, column=1, sticky=sticky, pady=3, padx=(0, 10))
            r += 1
        text = tk.Text(top, width=56, height=4, wrap="word", font=self.f_norm)
        text.insert("1.0", st["text"].replace("\\n", "\n"))
        row("Text", text, "we")
        row("Start with", tk.Entry(top, textvariable=prefix, width=24))
        pv = tk.Text(top, width=56, height=5, wrap="word", font=self.f_norm, state="disabled")
        row("Preview", pv, "we")
        msg = tk.Label(top, text="", anchor="w", justify="left", wraplength=420, fg="#c04040")
        msg.grid(row=r, column=0, columnspan=2, sticky="we", padx=10)
        r += 1

        def state_now():
            g = panel.get()
            pat = g["pattern"] if g["pattern"] != "custom" else ct.stops_text(g["stops"])
            return {"pattern": pat, "mode": g["mode"], "prefix": prefix.get(), "smooth": g["smooth"],
                    "text": text.get("1.0", "end-1c")}

        def refresh(*_):
            self._grad_state = state_now()
            coded, why = self.make_gradient(self._grad_state)
            pv.configure(state="normal")
            pv.delete("1.0", "end")
            if coded is not None:
                for i, (t, idx) in enumerate(ct.runs(coded)):
                    tag = "c%d" % i
                    pv.tag_configure(tag, foreground=ct.XTERM[idx] if idx is not None else self.theme["fg"])
                    pv.insert("end", t, tag)
                msg.configure(text="%d characters" % len(coded), fg=self.theme["dim"])
            else:
                msg.configure(text=why, fg="#c04040")
            pv.configure(state="disabled")
        prefix.trace_add("write", refresh)
        text.bind("<KeyRelease>", refresh)

        def to_input():
            coded, why = self.make_gradient(state_now())
            if coded is None:
                msg.configure(text=why)
                return
            if "\n" in coded:
                self.root.clipboard_clear()
                self.root.clipboard_append(coded)
                msg.configure(text="Several lines: copied to the clipboard (paste into the game's editor).")
                return
            self.put_in_input(coded)
            close()

        def copy():
            coded, why = self.make_gradient(state_now())
            if coded is None:
                msg.configure(text=why)
                return
            self.root.clipboard_clear()
            self.root.clipboard_append(coded)
            msg.configure(text="Copied to the clipboard.")

        def save():
            from tkinter import simpledialog
            name = simpledialog.askstring("Save pattern", "Name for this pattern:", parent=top)
            if name:
                ok, m = self.save_pattern(name, ct.stops_text(panel.stops))
                msg.configure(text=m)
                panel.refresh_patterns()
                if ok:
                    panel.pattern.set(" ".join(name.split())[:30])

        def share():
            try:
                label = panel.pattern.get()
                name = label if label != "custom" else "Pattern"
                line = ct.share_string(name, panel.stops)
            except ValueError as e:
                msg.configure(text=str(e))
                return
            self.root.clipboard_clear()
            self.root.clipboard_append(line)
            msg.configure(text="Copied: " + line)

        def import_shared():
            from tkinter import simpledialog
            line = simpledialog.askstring("Import a pattern", "Paste a shared line (sgrad1:Fire:196,202,208):", parent=top)
            if not line:
                return
            try:
                name, cols = ct.parse_share(line)
            except ValueError as e:
                msg.configure(text=str(e))
                return
            ok, m = self.save_pattern(name, ",".join(str(c) for c in cols))
            msg.configure(text=m)
            if ok:
                panel.refresh_patterns()
                panel.set_stops(cols, name)

        def delete():
            if self.delete_pattern(panel.pattern.get()):
                msg.configure(text="Deleted.")
                panel.refresh_patterns()
                panel.pattern.set("custom")
            else:
                msg.configure(text="Only your own saved patterns can be deleted.")

        def close():
            self._grad_state = state_now()
            self._grad_win = None
            top.destroy()
        bf = tk.Frame(top)
        bf.grid(row=r, column=0, columnspan=2, pady=8)
        for label, fn in (("To input", to_input), ("Copy", copy), ("Reverse", lambda: panel.set_stops(panel.stops[::-1])),
                          ("Save pattern...", save), ("Share", share), ("Import...", import_shared),
                          ("Delete pattern", delete), ("Close", close)):
            tk.Button(bf, text=label, command=fn).pack(side="left", padx=3)
        top.protocol("WM_DELETE_WINDOW", close)
        top.bind("<Escape>", lambda e: close())
        top._panel = panel
        refresh()
        self._theme_tree(top)
        panel._cv.focus_set()
        return top

    # ---- customize -----------------------------------------------------------------------
    def intercept_line(self, line):
        """A typed line the client handles itself. True when it was consumed."""
        if self.cfg.get("custom_form", True) and line.strip().lower() == "customize" and self.connected:
            self.open_customize()
            return True
        return False

    def open_customize(self, values=None):
        vals = custom.clean_values(values if values is not None else self._cust_values)
        if self.dos:
            return self._dos_customize(vals, 1)
        if self._cust_win is not None:
            try:
                self._cust_win.lift()
                return self._cust_win
            except tk.TclError:
                self._cust_win = None
        top = self._cust_win = tk.Toplevel(self.root)
        top.title("Customize an item")
        top.transient(self.root)
        widgets, order = {}, []
        typ = tk.StringVar(value=self._cust_type)
        r = 0
        tk.Label(top, text="Type (for your design book)").grid(row=r, column=0, sticky="w", padx=10, pady=3)
        tk.OptionMenu(top, typ, *custom.TYPES).grid(row=r, column=1, sticky="w")
        r += 1
        modevar = tk.StringVar(value=vals.get("mode") or self._cust_mode)
        tk.Label(top, text="Send it").grid(row=r, column=0, sticky="w", padx=10, pady=3)
        mf = tk.Frame(top)
        mf.grid(row=r, column=1, sticky="w")
        for m in custom.MODES:
            tk.Radiobutton(mf, text=custom.MODE_TEXT[m], value=m, variable=modevar).pack(side="left", padx=(0, 10))
        r += 1
        for key, label, kind, width in custom.FIELDS:
            tk.Label(top, text=label).grid(row=r, column=0, sticky="nw", padx=10, pady=2)
            if kind == "text":
                w = tk.Text(top, width=min(width, 70), height=3, wrap="word", font=self.f_norm)
                w.insert("1.0", vals[key])
            else:
                w = tk.Entry(top, width=min(width, 70))
                w.insert(0, vals[key])
            w.grid(row=r, column=1, sticky="w", padx=(0, 10), pady=2)
            widgets[key] = w
            order.append(key)
            r += 1
        def tint(w):
            try:
                dosui.apply_code_tags(w, self.theme["dim"], self.theme["bg"])
            except tk.TclError:
                pass
        for k, w in widgets.items():
            if isinstance(w, tk.Text):
                w.bind("<KeyRelease>", lambda e, w=w: tint(w), add="+")
                tint(w)
        msg = tk.Label(top, text="Ctrl+S sends. Up/Down move between boxes. Leave a box empty to leave it alone.",
                       anchor="w", justify="left", wraplength=520)
        msg.grid(row=r, column=0, columnspan=2, sticky="we", padx=10, pady=4)

        def read():
            out = {}
            for k, w in widgets.items():
                out[k] = w.get("1.0", "end-1c") if isinstance(w, tk.Text) else w.get()
            out["mode"] = modevar.get()
            return custom.clean_values(out)

        def move(key, d):
            i = order.index(key) + d
            if 0 <= i < len(order):
                widgets[order[i]].focus_set()
            return "break"
        for k, w in widgets.items():
            if isinstance(w, tk.Entry):
                w.bind("<Down>", lambda e, k=k: move(k, 1))
                w.bind("<Up>", lambda e, k=k: move(k, -1))

        def put(values):
            modevar.set(values.get("mode") if values.get("mode") in custom.MODES else "cli")
            for k, w in widgets.items():
                if isinstance(w, tk.Text):
                    w.delete("1.0", "end")
                    w.insert("1.0", values.get(k, ""))
                else:
                    w.delete(0, "end")
                    w.insert(0, values.get(k, ""))

        def send(_e=None):
            self._cust_values, self._cust_type, self._cust_mode = read(), typ.get(), modevar.get()
            ok, m = self.send_customize(self._cust_values)
            msg.configure(text=m, fg="#c04040" if not ok else self.theme["fg"])
            return "break"

        def close():
            self._cust_values, self._cust_type = read(), typ.get()
            self._cust_win = None
            top.destroy()

        def save_design():
            from tkinter import simpledialog
            name = simpledialog.askstring("Save design", "Name for this design:", parent=top)
            if not name:
                return
            try:
                self.cfg["designs"] = custom.save_design(self.cfg.get("designs", []), name, typ.get(), read())
                self._save_settings()
                msg.configure(text="Saved '%s' in the design book." % name.strip())
            except ValueError as e:
                msg.configure(text=str(e))

        def colour_text():
            w = top.focus_get()
            if not isinstance(w, tk.Text):
                msg.configure(text="Click in a paragraph box (description, taste ...) first.")
                return
            self._text_gradient_window(top, w, lambda: tint(w))

        def strip_text():
            w = top.focus_get()
            if not isinstance(w, tk.Text):
                msg.configure(text="Click in a paragraph box first.")
                return
            try:
                a, b = w.index("sel.first"), w.index("sel.last")
            except tk.TclError:
                a, b = "1.0", "end-1c"
            seg = w.get(a, b)
            w.delete(a, b)
            w.insert(a, ct.strip_codes(seg))
            tint(w)

        def book():
            self._design_book_window(top, lambda d: (put(d["values"]), typ.set(d["type"])))
        bf = tk.Frame(top)
        bf.grid(row=r + 1, column=0, columnspan=2, pady=8)
        for label, fn in (("Send  (Ctrl+S)", send), ("Save design...", save_design), ("Design book...", book),
                          ("Colour text...", colour_text), ("Strip colours", strip_text), ("Clear", lambda: put(custom.blank())), ("Close", close)):
            tk.Button(bf, text=label, command=fn).pack(side="left", padx=3)
        top.bind("<Control-s>", send)
        top.bind("<Control-S>", send)
        top.bind("<Escape>", lambda e: close())
        top.protocol("WM_DELETE_WINDOW", close)
        self._theme_tree(top)
        widgets["item"].focus_set()
        return top

    def _text_gradient_window(self, parent, widget, done=None):
        """Colour the selected text (or all of it) in a paragraph box with a gradient."""
        top = tk.Toplevel(parent)
        top.title("Colour the text")
        top.transient(parent)
        st = {k: self._grad_state[k] for k in ("pattern", "mode", "smooth")}
        stops0 = self._grad_stops(st)
        panel = gradwin.GradientPanel(top, self, {"stops": stops0, "mode": st["mode"], "smooth": st["smooth"],
                                                  "pattern": self._grad_label(st, stops0)}, lambda: None, self.theme)
        panel.grid(row=0, column=0, sticky="we", padx=10, pady=(8, 2))
        note = tk.Label(top, text="", fg="#c04040", anchor="w", wraplength=420, justify="left")
        note.grid(row=1, column=0, sticky="we", padx=10)

        def apply():
            text = widget.get("1.0", "end-1c")
            try:
                a = widget.count("1.0", widget.index("sel.first"), "chars")[0]
                b = widget.count("1.0", widget.index("sel.last"), "chars")[0]
                rng = (a, b) if b > a else None
            except (tk.TclError, TypeError, IndexError):
                rng = None
            g = panel.get()
            try:
                out = ct.colour_text(text, g["stops"], g["mode"], g["smooth"], rng)
            except ValueError as e:
                note.configure(text=str(e))
                return
            widget.delete("1.0", "end")
            widget.insert("1.0", out)
            pat = g["pattern"] if g["pattern"] != "custom" else ct.stops_text(g["stops"])
            self._grad_state = dict(self._grad_state, pattern=pat, mode=g["mode"], smooth=g["smooth"])
            if done:
                done()
            top.destroy()
        bf = tk.Frame(top)
        bf.grid(row=2, column=0, pady=8)
        tk.Button(bf, text="Apply", width=9, command=apply).pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", width=9, command=top.destroy).pack(side="left", padx=4)
        top.bind("<Escape>", lambda e: top.destroy())
        top._panel = panel
        self._theme_tree(top)
        return top

    def _design_book_window(self, parent, on_load):
        book = self.cfg.get("designs", [])
        win = tk.Toplevel(parent)
        win.title("Design book")
        win.transient(parent)
        lb = tk.Listbox(win, width=50, height=14, exportselection=False)
        lb.pack(padx=10, pady=8, fill="both", expand=True)
        entries = []

        def fill():
            lb.delete(0, "end")
            entries.clear()
            for t, ds in custom.by_type(self.cfg.get("designs", [])):
                for d in ds:
                    entries.append(d)
                    lb.insert("end", "%-10s %s" % (t, d["name"]))
            if not entries:
                lb.insert("end", "(empty: save a design from the form)")
        fill()

        def load(_e=None):
            sel = lb.curselection()
            if sel and sel[0] < len(entries):
                on_load(entries[sel[0]])
                win.destroy()

        def delete():
            sel = lb.curselection()
            if sel and sel[0] < len(entries):
                d = entries[sel[0]]
                self.cfg["designs"] = custom.delete_design(self.cfg.get("designs", []), d["type"], d["name"])
                self._save_settings()
                fill()
        bf = tk.Frame(win)
        bf.pack(pady=6)
        tk.Button(bf, text="Load", width=9, command=load).pack(side="left", padx=4)
        tk.Button(bf, text="Delete", width=9, command=delete).pack(side="left", padx=4)
        tk.Button(bf, text="Close", width=9, command=win.destroy).pack(side="left", padx=4)
        lb.bind("<Double-Button-1>", load)
        win.bind("<Escape>", lambda e: win.destroy())
        self._theme_tree(win)
        return win

    def _dos_save_design(self, values, back):
        def got(res, v):
            if res == "ok":
                try:
                    self.cfg["designs"] = custom.save_design(self.cfg.get("designs", []), v.get("name", ""),
                                                             self._cust_type, values)
                    self._save_settings()
                    self.system("Saved '%s' in the design book." % v.get("name", "").strip())
                except ValueError as e:
                    self.system(str(e))
            self._reopen(back)
        self._reopen(lambda: self._dos_dialog(
            "Save design", [{"key": "name", "label": "Name", "type": "text", "value": "", "width": 30}],
            [("OK", "ok"), ("Cancel", "cancel")], got, width=52,
            message="Saved under the type: %s" % self._cust_type))

    def _dos_design_book(self, on_load, back):
        groups = custom.by_type(self.cfg.get("designs", []))
        if not groups:
            self.system("The design book is empty: save a design from the form.")
            self._reopen(back)
            return
        items = []
        for t, ds in groups:
            items.append({"label": "%s (%d)" % (t, len(ds)), "action": (lambda t=t, ds=ds: self._reopen(
                self._dos_design_type, t, ds, on_load, back))})
        self._reopen(lambda: self._dos_menu("Design book", items, back=back))

    def _dos_design_type(self, t, ds, on_load, back):
        items = []
        for d in ds:
            items.append({"label": d["name"], "action": (lambda d=d: self._reopen(self._dos_design_pick, d, on_load, back))})
        self._dos_menu(t, items, back=lambda: self._dos_design_book(on_load, back))

    def _dos_design_pick(self, d, on_load, back):
        def delete():
            self.cfg["designs"] = custom.delete_design(self.cfg.get("designs", []), d["type"], d["name"])
            self._save_settings()
            self.system("Deleted '%s'." % d["name"])
            self._reopen(self._dos_design_book, on_load, back)
        items = [{"label": "Load it", "hotkey": "L", "action": lambda: on_load(d)},
                 {"label": "Delete it", "hotkey": "D", "action": delete}]
        self._dos_menu(d["name"], items, back=lambda: self._dos_design_book(on_load, back))

    # ---- typed commands ------------------------------------------------------------------
    def _tools_command(self, cmd, arg):
        if cmd == "hex":
            if arg:
                self.hex_report(arg)
            else:
                self.open_hex()
            return True
        if cmd in ("gradient", "grad"):
            word, _, rest = arg.partition(" ")
            if word.lower() == "share":
                try:
                    cols = self._pattern_colours(rest or self._grad_state["pattern"])
                    line = ct.share_string(rest or self._grad_state["pattern"], cols)
                except ValueError as e:
                    self.system(str(e))
                else:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(line)
                    self.system("Copied to the clipboard: " + line)
                return True
            if word.lower() == "import":
                try:
                    name, cols = ct.parse_share(rest)
                except ValueError as e:
                    self.system(str(e))
                else:
                    self.system(self.save_pattern(name, ",".join(str(c) for c in cols))[1])
                return True
            if arg:
                state = dict(self._grad_state, text=arg)
                coded, why = self.make_gradient(state)
                if coded is None:
                    self.system(why)
                else:
                    self._grad_state = state
                    self.show_coloured(coded)
                    self.put_in_input(coded)
            else:
                self.open_gradient()
            return True
        if cmd in ("customize", "custom"):
            self.open_customize()
            return True
        return False
