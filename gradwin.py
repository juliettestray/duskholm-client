"""The gradient editor in the ordinary (Windows) look: clickable colour swatches, a picker with a
saturation/brightness square, a hue slider, a hex box and the palette grouped by hue, and a live blend bar."""
import colorsys
import tkinter as tk

import colortools as ct


def _ink(hexcol):
    try:
        r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "#ffffff"
    return "#000000" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 140 else "#ffffff"


# --------------------------------------------------------------------------------------------
class ColourPicker(tk.Toplevel):
    """Pick one xterm colour. on_change(index) as it changes (the swatch it belongs to follows live);
    on_close(index or None): the colour kept, or None when cancelled (the caller restores the old one)."""

    SQ = 180                                    # side of the square, in pixels
    CELL = 15                                   # side of a palette swatch

    def __init__(self, parent, title, current, theme, on_change, on_close):
        tk.Toplevel.__init__(self, parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.theme = theme
        self._on_change, self._on_close = on_change, on_close
        self._orig = int(current)
        self._index = int(current)
        self._done = False
        self._syncing = False
        h, s, v = ct.hsv_of(self._index)
        self._h, self._s, self._v = h, s, v
        self.configure(bg=theme["bg"])
        left = tk.Frame(self, bg=theme["bg"])
        left.grid(row=0, column=0, padx=10, pady=10, sticky="n")
        self._sq = tk.Canvas(left, width=self.SQ, height=self.SQ, highlightthickness=1, cursor="crosshair",
                             highlightbackground=theme.get("dim", "#888"), bg=theme["bg"])
        self._sq.pack()
        self._sq_img = tk.PhotoImage(width=self.SQ, height=self.SQ)
        self._sq.create_image(0, 0, image=self._sq_img, anchor="nw")
        self._sq_dot = self._sq.create_oval(0, 0, 0, 0, outline="#ffffff", width=2)
        self._hue = tk.Canvas(left, width=self.SQ, height=18, highlightthickness=1, cursor="sb_h_double_arrow",
                              highlightbackground=theme.get("dim", "#888"), bg=theme["bg"])
        self._hue.pack(pady=(6, 0))
        himg = tk.PhotoImage(width=self.SQ, height=1)
        himg.put("{" + " ".join(self._hex_of(i / float(self.SQ) * 360.0, 1, 1) for i in range(self.SQ)) + "}", to=(0, 0))
        self._hue_img = himg.zoom(1, 18)
        self._hue.create_image(0, 0, image=self._hue_img, anchor="nw")
        self._hue_mark = self._hue.create_rectangle(0, 0, 0, 0, outline="#ffffff", width=2)
        row = tk.Frame(left, bg=theme["bg"])
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text="Hex", bg=theme["bg"], fg=theme["fg"]).pack(side="left")
        self._var = tk.StringVar(value=ct.XTERM[self._index])
        self._entry = tk.Entry(row, textvariable=self._var, width=10, bg=theme.get("input_bg", theme["bg"]),
                               fg=theme.get("input_fg", theme["fg"]), insertbackground=theme.get("input_fg", theme["fg"]))
        self._entry.pack(side="left", padx=6)
        self._var.trace_add("write", self._typed)
        self._chip = tk.Canvas(left, width=self.SQ, height=26, highlightthickness=0, bg=theme["bg"])
        self._chip.pack(pady=(8, 0))
        self._info = tk.Label(left, text="", bg=theme["bg"], fg=theme["fg"], anchor="w", justify="left")
        self._info.pack(fill="x", pady=(4, 0))
        # the palette, grouped by hue
        fams = ct.hue_families()
        right = tk.Frame(self, bg=theme["bg"])
        right.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="n")
        tk.Label(right, text="Or pick from the palette", bg=theme["bg"], fg=theme["fg"], anchor="w").pack(fill="x")
        longest = max(len(i) for _n, i in fams)
        lab = 58
        self._pal = tk.Canvas(right, width=lab + longest * self.CELL + 2, height=len(fams) * self.CELL + 2,
                              highlightthickness=0, bg=theme["bg"], cursor="hand2")
        self._pal.pack(pady=(4, 0))
        self._cells = {}
        for r, (name, idxs) in enumerate(fams):
            y = r * self.CELL + 1
            self._pal.create_text(0, y + self.CELL // 2, text=name, anchor="w", fill=theme["fg"],
                                  font=("TkDefaultFont", 8))
            for k, idx in enumerate(idxs):
                x = lab + k * self.CELL
                self._pal.create_rectangle(x, y, x + self.CELL - 1, y + self.CELL - 1, fill=ct.XTERM[idx], outline="",
                                           tags=("c%d" % idx,))
                self._cells[idx] = (x, y)
        self._ring = self._pal.create_rectangle(0, 0, 0, 0, outline="#ffffff", width=2)
        self._pal.bind("<ButtonPress-1>", self._pal_click)
        self._pal.bind("<B1-Motion>", self._pal_click)
        btns = tk.Frame(self, bg=theme["bg"])
        btns.grid(row=1, column=0, columnspan=2, pady=(0, 10))
        tk.Button(btns, text="Use this colour", width=14, command=self._ok).pack(side="left", padx=4)
        tk.Button(btns, text="Cancel", width=10, command=self._cancel).pack(side="left", padx=4)
        for w in (self._sq,):
            w.bind("<ButtonPress-1>", self._sq_click)
            w.bind("<B1-Motion>", self._sq_click)
        self._hue.bind("<ButtonPress-1>", self._hue_click)
        self._hue.bind("<B1-Motion>", self._hue_click)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build_square()
        self._refresh()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self._entry.focus_set()

    @staticmethod
    def _hex_of(h, s, v):
        r, g, b = colorsys.hsv_to_rgb((h % 360.0) / 360.0, s, v)
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))

    # -- drawing ---------------------------------------------------------------------------------
    def _build_square(self):
        n = self.SQ
        rows = []
        for y in range(n):
            v = 1.0 - y / float(n - 1)
            rows.append("{" + " ".join(self._hex_of(self._h, x / float(n - 1), v) for x in range(n)) + "}")
        self._sq_img.put(" ".join(rows), to=(0, 0))

    def _refresh(self, from_hex=False):
        idx = self._index
        # the dot and the hue mark
        x, y = self._s * (self.SQ - 1), (1.0 - self._v) * (self.SQ - 1)
        self._sq.coords(self._sq_dot, x - 5, y - 5, x + 5, y + 5)
        hx = (self._h % 360.0) / 360.0 * (self.SQ - 1)
        self._hue.coords(self._hue_mark, hx - 2, 0, hx + 2, 18)
        # what is picked, and what the game will actually show
        self._chip.delete("all")
        picked = self._hex_of(self._h, self._s, self._v)
        self._chip.create_rectangle(0, 0, self.SQ // 2, 26, fill=picked, outline="")
        self._chip.create_rectangle(self.SQ // 2, 0, self.SQ, 26, fill=ct.XTERM[idx], outline="")
        self._chip.create_text(4, 13, text="picked", anchor="w", fill=_ink(picked), font=("TkDefaultFont", 8))
        self._chip.create_text(self.SQ // 2 + 4, 13, text="in the game", anchor="w", fill=_ink(ct.XTERM[idx]),
                               font=("TkDefaultFont", 8))
        self._info.configure(text="Colour %s" % ct.describe(idx))
        if idx in self._cells:
            x0, y0 = self._cells[idx]
            self._pal.coords(self._ring, x0 - 1, y0 - 1, x0 + self.CELL, y0 + self.CELL)
        if not from_hex:
            self._sync_entry(picked)

    def _sync_entry(self, hexv):
        if self._var.get().strip().lower() != hexv:
            self._syncing = True
            try:
                self._var.set(hexv)
            finally:
                self._syncing = False

    def _set(self, index, reshape=True):
        self._index = int(index)
        if reshape:
            self._h, self._s, self._v = ct.hsv_of(self._index)
            self._build_square()
        self._refresh()
        self._on_change(self._index)

    # -- input ---------------------------------------------------------------------------------------
    def _from_hsv(self):
        idx, _hexv = ct.from_hsv(self._h, self._s, self._v, system=False)
        self._index = idx
        self._refresh()
        self._on_change(idx)

    def _sq_click(self, e):
        self._s = max(0.0, min(1.0, e.x / float(self.SQ - 1)))
        self._v = max(0.0, min(1.0, 1.0 - e.y / float(self.SQ - 1)))
        self._from_hsv()

    def _hue_click(self, e):
        self._h = max(0.0, min(359.9, e.x / float(self.SQ - 1) * 360.0))
        self._build_square()
        self._from_hsv()

    def _pal_click(self, e):
        for idx, (x, y) in self._cells.items():
            if x <= e.x < x + self.CELL and y <= e.y < y + self.CELL:
                if idx != self._index:
                    self._set(idx)
                return

    def _typed(self, *_):
        if self._syncing:
            return
        try:
            idx, _hexv, _exact = ct.from_hex(self._var.get(), system=True)
            r, g, b = ct.parse_hex(self._var.get())
        except ValueError:
            return
        self._h, self._s, self._v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        self._h *= 360.0
        self._index = idx
        self._build_square()
        self._refresh(from_hex=True)
        self._on_change(idx)

    def _ok(self):
        if self._done:
            return
        self._done = True
        self._release()
        self._on_close(self._index)

    def _cancel(self):
        if self._done:
            return
        self._done = True
        self._release()
        self._on_close(None)

    def _release(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


# --------------------------------------------------------------------------------------------
class GradientPanel(tk.Frame):
    """Swatches for the colours, a live blend bar, the pattern list and how to apply it.
    `get()` gives {"stops", "mode", "smooth", "pattern"}; on_change() is called after every edit."""

    SW = 30

    def __init__(self, parent, app, state, on_change, theme):
        tk.Frame.__init__(self, parent, bg=theme["bg"])
        self.app = app
        self.theme = theme
        self._on_change = on_change
        self.stops = [int(s) for s in state.get("stops") or [196, 226]][:ct.MAX_STOPS] or [196]
        self.sel = 0
        self.pattern = tk.StringVar(value=state.get("pattern", "custom"))
        self.mode = tk.StringVar(value=state.get("mode", "stretch"))
        self.smooth = tk.BooleanVar(value=bool(state.get("smooth", True)))
        self._picker = None
        bg, fg = theme["bg"], theme["fg"]

        def row(label, w, r):
            tk.Label(self, text=label, bg=bg, fg=fg).grid(row=r, column=0, sticky="nw", padx=(0, 8), pady=3)
            w.grid(row=r, column=1, sticky="w", pady=3)
        # pattern list + saving
        pr = tk.Frame(self, bg=bg)
        self._pat_btn = tk.Menubutton(pr, textvariable=self.pattern, relief="raised", width=22, anchor="w")
        self._pat_menu = tk.Menu(self._pat_btn, tearoff=0)
        self._pat_btn.configure(menu=self._pat_menu)
        self._pat_btn.pack(side="left")
        self._fill_menu()
        row("Pattern", pr, 0)
        # swatches
        sw = tk.Frame(self, bg=bg)
        self._cv = tk.Canvas(sw, height=self.SW + 22, highlightthickness=1, bg=bg, takefocus=True,
                             highlightbackground=theme.get("dim", "#888"))
        self._cv.pack(side="left", fill="x", expand=True)
        row("Colours", sw, 1)
        self._cv.bind("<ButtonPress-1>", self._click)
        self._cv.bind("<Double-ButtonPress-1>", self._double)
        self._cv.bind("<Configure>", lambda e: self._draw())
        for seq, fn in (("<Left>", lambda e: self._select(self.sel - 1)), ("<Right>", lambda e: self._select(self.sel + 1)),
                        ("<Control-Left>", lambda e: self._move(-1)), ("<Control-Right>", lambda e: self._move(1)),
                        ("<Insert>", lambda e: self._add()), ("<Delete>", lambda e: self._remove()),
                        ("<plus>", lambda e: self._add()), ("<minus>", lambda e: self._remove()),
                        ("<Return>", lambda e: self._pick()), ("<space>", lambda e: self._pick())):
            self._cv.bind(seq, lambda e, fn=fn: (fn(e), "break")[1])
        self._info = tk.Label(self, text="", bg=bg, fg=theme.get("dim", fg), anchor="w")
        row("", self._info, 2)
        self._bar = tk.Canvas(self, height=18, highlightthickness=0, bg=bg)
        self._bar.bind("<Configure>", lambda e: self._draw_bar())
        row("Blend", self._bar, 3)
        self.columnconfigure(1, weight=1)
        self._bar.grid_configure(sticky="we")
        self._cv.master.grid_configure(sticky="we")
        # how it is applied
        mr = tk.Frame(self, bg=bg)
        tk.OptionMenu(mr, self.mode, *ct.MODES).pack(side="left")
        self._help = tk.Label(mr, text="", bg=bg, fg=theme.get("dim", fg), anchor="w")
        self._help.pack(side="left", padx=8)
        row("Apply", mr, 4)
        tk.Checkbutton(self, text="Blend between colours", variable=self.smooth, bg=bg, fg=fg, selectcolor=bg,
                       activebackground=bg, activeforeground=fg).grid(row=5, column=1, sticky="w")
        self.mode.trace_add("write", lambda *a: self._changed(keep_pattern=True))
        self.smooth.trace_add("write", lambda *a: self._changed(keep_pattern=True))
        self._draw()

    # -- state -------------------------------------------------------------------------------------
    def get(self):
        return {"stops": list(self.stops), "mode": self.mode.get(), "smooth": bool(self.smooth.get()),
                "pattern": self.pattern.get()}

    def set_stops(self, stops, pattern=None):
        self.stops = [int(s) for s in stops][:ct.MAX_STOPS] or [196]
        self.sel = min(self.sel, len(self.stops) - 1)
        self.pattern.set(pattern if pattern is not None else "custom")
        self._draw()
        self._on_change()

    def _changed(self, keep_pattern=False):
        if not keep_pattern:
            self.pattern.set("custom")
        self._draw()
        self._on_change()

    def _fill_menu(self):
        m = self._pat_menu
        m.delete(0, "end")
        saved = self.app.cfg.get("gradients", [])
        for n in ct.all_pattern_names(saved):
            m.add_command(label=n, command=lambda n=n: self._load(n))

    def refresh_patterns(self):
        self._fill_menu()

    def _load(self, name):
        cols = ct.find_pattern(name, self.app.cfg.get("gradients", []))
        if cols:
            self.set_stops(cols, name)

    # -- drawing -----------------------------------------------------------------------------------
    def _draw(self):
        cv = self._cv
        cv.delete("all")
        self._hits = []
        sw, pad = self.SW, 6
        x, y = pad, 6
        width = max(sw + 2 * pad, cv.winfo_width())
        fg = self.theme["fg"]
        n = len(self.stops)
        slots = n + 2
        per = max(1, (width - pad) // (sw + 6))
        rows = -(-slots // per)
        cv.configure(height=rows * (sw + 24) + 4)
        for slot in range(slots):
            r, k = divmod(slot, per)
            x0, y0 = pad + k * (sw + 6), 6 + r * (sw + 24)
            if slot < n:
                idx = self.stops[slot]
                cv.create_rectangle(x0, y0, x0 + sw, y0 + sw, fill=ct.XTERM[idx], outline=fg if slot == self.sel else "",
                                    width=3 if slot == self.sel else 1)
                if slot == self.sel:
                    cv.create_polygon(x0 + sw // 2 - 5, y0 + sw + 7, x0 + sw // 2 + 5, y0 + sw + 7, x0 + sw // 2, y0 + sw + 1,
                                      fill=fg, outline="")
                self._hits.append((x0, y0, x0 + sw, y0 + sw, "stop", slot))
            else:
                add = slot == n
                cv.create_rectangle(x0, y0, x0 + sw, y0 + sw, outline=self.theme.get("dim", fg), dash=(2, 2))
                cv.create_text(x0 + sw // 2, y0 + sw // 2, text="+" if add else "−", fill=fg,
                               font=("TkDefaultFont", 14))
                self._hits.append((x0, y0, x0 + sw, y0 + sw, "add" if add else "del", None))
        idx = self.stops[self.sel]
        self._info.configure(text="Colour %d of %d:  %s     click a swatch to select it, click it again to change it" %
                             (self.sel + 1, n, ct.describe(idx)))
        self._help.configure(text=ct.MODE_HELP.get(self.mode.get(), ""))
        self._draw_bar()

    def _draw_bar(self):
        bar = self._bar
        bar.delete("all")
        w = max(10, bar.winfo_width())
        n = max(2, min(w, 160))
        cols = ct.preview_bar(self.stops, n, self.smooth.get())
        step = w / float(n)
        for i, ci in enumerate(cols):
            bar.create_rectangle(i * step, 0, (i + 1) * step + 1, 18, fill=ct.XTERM[ci], outline="")

    # -- editing -------------------------------------------------------------------------------------
    def _select(self, i):
        self.sel = max(0, min(len(self.stops) - 1, i))
        self._draw()

    def _add(self):
        self.stops, self.sel = ct.add_stop(self.stops, self.sel)
        self._changed()

    def _remove(self):
        self.stops, self.sel = ct.remove_stop(self.stops, self.sel)
        self._changed()

    def _move(self, step):
        self.stops, self.sel = ct.move_stop(self.stops, self.sel, step)
        self._changed()

    def _hit(self, e):
        for x0, y0, x1, y1, kind, what in self._hits:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                return kind, what
        return None, None

    def _click(self, e):
        self._cv.focus_set()
        kind, what = self._hit(e)
        if kind == "stop":
            again = what == self.sel
            self._select(what)
            if again:
                self._pick()
        elif kind == "add":
            self._add()
        elif kind == "del":
            self._remove()

    def _double(self, e):
        kind, what = self._hit(e)
        if kind == "stop":
            self._select(what)
            self._pick()

    def _pick(self):
        if self._picker is not None:
            try:
                if self._picker.winfo_exists():
                    self._picker.lift()
                    return
            except tk.TclError:
                pass
        at = self.sel
        original = self.stops[at]

        def live(idx):
            if at < len(self.stops):
                self.stops[at] = idx
                self._changed()

        def closed(idx):
            self._picker = None
            if idx is None and at < len(self.stops):
                self.stops[at] = original
                self._changed()
            self._cv.focus_set()
        self._picker = ColourPicker(self.winfo_toplevel(), "Colour %d of %d" % (at + 1, len(self.stops)),
                                    original, self.theme, live, closed)
