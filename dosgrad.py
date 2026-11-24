"""The gradient editor in the DOS look: a row of colour swatches you can see and click, a live blend bar,
and a palette that groups the 256 colours by hue so one can be found by eye.

Everything works with the keyboard alone (arrows, Tab, Enter, Ins/Del) and with the mouse.
"""
import tkinter as tk

import colortools as ct
import dosui
from dosui import _DosBox, _trunc, _alt_down, dos_colors

SAMPLE = "The quick brown fox jumps over the lazy dog"


def _ink(hexcol):
    """Black or white, whichever reads on `hexcol`."""
    try:
        r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "#ffffff"
    return "#000000" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 140 else "#ffffff"


# --------------------------------------------------------------------------------------------
class DosPalette(_DosBox):
    """Choose one of the 256 xterm colours: rows are hue families (light to dark), or type a hex colour and
    it snaps to the nearest. on_result(index) with the colour chosen, or on_result(None) when cancelled."""

    CELL = 2                                    # cells wide per colour

    def __init__(self, parent, title, current, colors, font, on_result):
        _DosBox.__init__(self, parent, colors, font)
        self._title = str(title)
        self._on_result = on_result
        self._fams = ct.hue_families()
        self._current = int(current)
        self._done = False
        self._hits = []
        self._pos = (0, 0)
        for r, (_n, idxs) in enumerate(self._fams):
            if self._current in idxs:
                self._pos = (r, idxs.index(self._current))
        self._hover = None
        self._zone = 0                          # 0 grid, 1 hex entry, 2 Use, 3 Cancel
        self._note = ""
        self._var = tk.StringVar(self, ct.XTERM[self._current])
        self._entry = tk.Entry(self._cv, bd=0, highlightthickness=0, relief="flat", textvariable=self._var)
        for seq in ("<Tab>", "<ISO_Left_Tab>", "<Up>", "<Down>", "<Return>", "<KP_Enter>", "<Escape>"):
            try:
                self._entry.bind(seq, self._on_entry_key)
            except tk.TclError:
                pass
        self._entry.bind("<KeyRelease>", self._hex_typed)
        self._entry.bind("<FocusIn>", lambda e: self._zone_to(1, focus=False))
        cv = self._cv
        cv.bind("<Key>", self._on_key)
        cv.bind("<ButtonPress-1>", self._on_click)
        cv.bind("<Motion>", self._on_motion)
        self._layout()
        self._render()

    # -- geometry ---------------------------------------------------------------------------
    def _layout(self):
        longest = max(len(i) for _n, i in self._fams)
        self._lab = max(len(n) for n, _i in self._fams) + 1
        self._gx = 2 + self._lab                # first grid column
        total = self._gx + longest * self.CELL + 3
        total = max(total, 44)
        pw, _ph = self._parent_size()
        self._total = min(total, max(20, pw // self.cw - 1))
        self._r_grid = 2
        self._r_info = self._r_grid + len(self._fams) + 1
        self._r_hex = self._r_info + 1
        self._r_btn = self._r_hex + 2
        self._size_canvas(self._total, self._r_btn + 2)
        self._cv.delete("all")
        self._cv.create_window((self._gx + 4) * self.cw, self._r_hex * self.lh, anchor="nw", window=self._entry,
                               width=9 * self.cw, height=self.lh, tags="win")
        self._style_entry()

    def _style_entry(self):
        c = self.colors
        on = self._zone == 1
        try:
            self._entry.configure(bg=c["dos_menu_sel_bg"] if on else c["input_bg"],
                                  fg=c["dos_menu_sel_fg"] if on else c["input_fg"], font=self._font,
                                  insertwidth=self.cw, insertbackground=c["dos_key_fg"],
                                  selectbackground=c["dos_menu_fg"], selectforeground=c["dos_menu_bg"])
        except tk.TclError:
            pass

    def _index(self, pos=None):
        r, k = pos or self._pos
        return self._fams[r][1][k]

    # -- drawing ------------------------------------------------------------------------------
    def _render(self):
        c = self.colors
        self._cv.delete("deco")
        self._hits = []
        self._draw_frame(self._title)
        bg, fg = c["dos_menu_bg"], c["dos_menu_fg"]
        self._text(2, 1, _trunc("Arrows move, Enter chooses, Tab for a hex colour", self._total - 4), c["dos_menu_dim"], bg)
        cur_idx = self._index()
        for r, (name, idxs) in enumerate(self._fams):
            row = self._r_grid + r
            self._text(2, row, name.ljust(self._lab - 1), fg, bg)
            for k, idx in enumerate(idxs):
                col = self._gx + k * self.CELL
                self._rect(col, row, self.CELL, ct.XTERM[idx])
                if idx == self._current:                                  # the colour it has now: a small dot
                    x, y = col * self.cw + self.cw - 2, row * self.lh + self.lh // 2 - 2
                    self._cv.create_rectangle(x, y, x + 4, y + 4, fill=_ink(ct.XTERM[idx]), outline="", tags="deco")
                if (r, k) == self._pos and self._zone == 0:               # the cursor: a frame round the cell
                    x0, y0 = col * self.cw + 1, row * self.lh + 1
                    self._cv.create_rectangle(x0, y0, x0 + self.CELL * self.cw - 3, y0 + self.lh - 3,
                                              outline=_ink(ct.XTERM[idx]), width=2, tags="deco")
                self._hits.append(("cell", (r, k), col, col + self.CELL, row))
        shown = self._hover if self._hover is not None else cur_idx
        self._text(2, self._r_info, _trunc(ct.describe(shown), self._total - 14).ljust(18), fg, bg)
        self._rect(self._total - 10, self._r_info, 8, ct.XTERM[shown])
        self._text(2, self._r_hex, "Hex", fg, bg)
        if self._note:
            self._text(self._gx + 14, self._r_hex, _trunc(self._note, self._total - self._gx - 16), c["dos_menu_dim"], bg)
        labels = ["[ Use ]", "[ Cancel ]"]
        col = max(2, (self._total - sum(map(len, labels)) - 2) // 2)
        for i, s in enumerate(labels):
            on = self._zone == 2 + i
            self._text(col, self._r_btn, s, c["dos_menu_sel_fg"] if on else fg, c["dos_menu_sel_bg"] if on else bg)
            self._hits.append(("button", i, col, col + len(s), self._r_btn))
            col += len(s) + 2

    # -- input ----------------------------------------------------------------------------------
    def _zone_to(self, z, focus=True):
        self._zone = z % 4
        self._style_entry()
        self._render()
        if focus:
            try:
                if self._zone == 1:
                    self._entry.focus_set()
                    self._entry.selection_range(0, "end")
                else:
                    self._cv.focus_set()
            except tk.TclError:
                pass

    def _move(self, dr, dk):
        r, k = self._pos
        r = max(0, min(len(self._fams) - 1, r + dr))
        k = max(0, min(len(self._fams[r][1]) - 1, k + dk))
        if dr:                                                            # keep roughly the same column when changing row
            k = min(k, len(self._fams[r][1]) - 1)
        self._pos = (r, k)
        self._hover = None
        self._render()

    def _choose(self, index=None):
        if self._done:
            return
        self._done = True
        self.close()
        cb = self._on_result
        if callable(cb):
            cb(self._index() if index is None else index)

    def _cancel(self):
        if self._done:
            return
        self._done = True
        self.close()
        cb = self._on_result
        if callable(cb):
            cb(None)

    def _enter(self):
        if self._zone == 3:
            self._cancel()
        elif self._zone == 1:
            self._hex_typed(apply=True)
        else:
            self._choose()

    def _on_key(self, e):
        ks = e.keysym
        if ks in ("Tab", "ISO_Left_Tab"):
            self._zone_to(self._zone + (-1 if ks == "ISO_Left_Tab" or e.state & 1 else 1))
        elif ks == "Escape":
            self._cancel()
        elif ks in ("Return", "KP_Enter"):
            self._enter()
        elif self._zone == 0:
            if ks == "Left":
                self._move(0, -1)
            elif ks == "Right":
                self._move(0, 1)
            elif ks == "Up":
                self._move(-1, 0)
            elif ks == "Down":
                self._move(1, 0)
            elif ks == "Home":
                self._pos = (self._pos[0], 0)
                self._render()
            elif ks == "End":
                self._pos = (self._pos[0], len(self._fams[self._pos[0]][1]) - 1)
                self._render()
            elif ks == "space":
                self._choose()
        elif ks in ("Left", "Right") and self._zone in (2, 3):
            self._zone_to(5 - self._zone)
        elif ks == "space" and self._zone in (2, 3):
            self._enter()
        return "break"

    def _on_entry_key(self, e):
        ks = e.keysym
        if ks in ("Tab", "ISO_Left_Tab"):
            self._zone_to(self._zone + (-1 if ks == "ISO_Left_Tab" or e.state & 1 else 1))
        elif ks == "Escape":
            self._cancel()
        elif ks in ("Return", "KP_Enter"):
            self._hex_typed(apply=True)
        elif ks == "Up":
            self._zone_to(0)
        elif ks == "Down":
            self._zone_to(2)
        return "break"

    def _hex_typed(self, _e=None, apply=False):
        try:
            idx, hexv, exact = ct.from_hex(self._var.get(), system=True)
        except ValueError:
            self._note = "not a hex colour"
            self._render()
            return
        for r, (_n, idxs) in enumerate(self._fams):
            if idx in idxs:
                self._pos = (r, idxs.index(idx))
        self._note = ("exactly %d" if exact else "nearest is %d") % idx
        self._render()
        if apply:
            self._choose(idx)

    def _hit(self, e):
        col, row = int(e.x) // self.cw, int(e.y) // self.lh
        for kind, what, c0, c1, r in self._hits:
            if r == row and c0 <= col < c1:
                return kind, what
        return None, None

    def _on_motion(self, e):
        kind, what = self._hit(e)
        new = self._index(what) if kind == "cell" else None
        if new != self._hover:
            self._hover = new
            self._render()

    def _on_click(self, e):
        kind, what = self._hit(e)
        if kind == "cell":
            self._pos = what
            self._choose()
        elif kind == "button":
            self._zone = 2 + what
            self._enter()
        else:
            try:
                self._cv.focus_set()
            except tk.TclError:
                pass

    # -- lifecycle ---------------------------------------------------------------------------------
    def open(self, x=None, y=None):
        if self._is_open:
            self.close()
        self._done = False
        self._begin_open()
        self._layout()
        self._render()
        self._place_box(x, y)
        try:
            self.update_idletasks()
            self._cv.focus_set()
        except tk.TclError:
            pass

    def close(self):
        self._finish_close()

    def restyle(self, colors, font=None):
        self.colors = dos_colors(colors)
        if font is not None:
            self._font = font
        self._measure()
        self.configure(bg=self.colors["dos_menu_bg"])
        self._layout()
        self._render()


# --------------------------------------------------------------------------------------------
class DosGradientEditor(_DosBox):
    """The gradient as you see it: colour swatches, a blend bar, a preview in the real colours.

    `state`: {"stops": [xterm...], "mode", "smooth", "text", "prefix", "pattern": label shown for the pattern}.
    on_result(result, state): a button's result, ('pick', 'pattern' | 'mode') when one of those was chosen (the
    caller shows its list and comes back), or 'cancel'. `text=False` hides the text fields (used when the
    gradient is applied to text that is being edited elsewhere)."""

    LAB = 11

    def __init__(self, parent, title, state, buttons, colors, font, on_result, text=True, message=None):
        _DosBox.__init__(self, parent, colors, font)
        self._title = str(title)
        self._on_result = on_result
        self._with_text = bool(text)
        self._message = message or ""
        self._stops_list = [int(s) for s in state.get("stops") or [196, 226]][:ct.MAX_STOPS] or [196]
        self._sel = 0
        self._mode = state.get("mode") or "stretch"
        self._smooth = bool(state.get("smooth", True))
        self._pattern = str(state.get("pattern") or "custom")
        self._buttons = []
        for b in buttons:
            label, res = str(b[0]), b[1]
            self._buttons.append({"label": label, "result": res,
                                  "hotkey": (str(b[2])[:1].lower() if len(b) > 2 and b[2] else label[:1].lower())})
        self._done = False
        self._hits = []
        self._entries = {}
        self._entry_keys = ("text", "prefix") if self._with_text else ()
        init = {"text": state.get("text", ""), "prefix": state.get("prefix", "")}
        for key in self._entry_keys:
            e = tk.Entry(self._cv, bd=0, highlightthickness=0, relief="flat")
            e.insert(0, str(init[key]))
            for seq in ("<Tab>", "<ISO_Left_Tab>", "<Up>", "<Down>", "<Return>", "<KP_Enter>", "<Escape>", "<Alt-Key>"):
                try:
                    e.bind(seq, self._on_entry_key)
                except tk.TclError:
                    pass
            e.bind("<KeyRelease>", lambda ev: self._render())
            e.bind("<FocusIn>", lambda ev, k=key: self._entry_focus(k))
            self._entries[key] = e
        # focus order
        self._order = [("stops", None), ("pick", "pattern"), ("pick", "mode"), ("check", "smooth")]
        self._order += [("entry", k) for k in self._entry_keys]
        self._order += [("button", i) for i in range(len(self._buttons))]
        self._fi = 0
        cv = self._cv
        cv.bind("<Key>", self._on_key)
        cv.bind("<Alt-Key>", self._on_alt)
        cv.bind("<ButtonPress-1>", self._on_click)
        self._layout()
        self._render()

    # -- state ----------------------------------------------------------------------------------
    def state(self):
        out = {"stops": list(self._stops_list), "mode": self._mode, "smooth": self._smooth,
               "pattern": self._pattern}
        for k, e in self._entries.items():
            try:
                out[k] = e.get()
            except tk.TclError:
                out[k] = ""
        return out

    def _changed(self):
        """The colours were edited by hand: it is no longer the named pattern."""
        self._pattern = "custom"
        self._render()

    # -- layout -----------------------------------------------------------------------------------
    def _layout(self):
        pw, _ph = self._parent_size()
        self._total = max(40, min(78, pw // self.cw - 1))
        slots = len(self._stops_list) + 2
        self._per = max(1, (self._total - 2 - self.LAB - 1) // 4)
        self._swatch_rows = -(-slots // self._per)
        row = 1
        self._r_msg = row
        row += 2 if self._message else 1
        self._r_sw = row
        row += self._swatch_rows * 2
        self._r_info = row
        row += 1
        self._r_bar = row
        row += 2
        self._r_pat = row
        self._r_mode = row + 1
        self._r_smooth = row + 2
        row += 3
        self._r_entry = {}
        for k in self._entry_keys:
            self._r_entry[k] = row
            row += 1
        row += 1
        self._r_prev = row
        self._prev_rows = 3 if self._with_text else 1
        row += self._prev_rows + 1
        self._r_btn = row
        row += 2
        self._size_canvas(self._total, row)
        self._cv.delete("all")
        self._ecol = 2 + self.LAB
        self._ew = self._total - self._ecol - 2
        for k, e in self._entries.items():
            self._cv.create_window(self._ecol * self.cw, self._r_entry[k] * self.lh, anchor="nw", window=e,
                                   width=self._ew * self.cw, height=self.lh, tags="win")
        self._style_entries()

    def _style_entries(self):
        c = self.colors
        for k, e in self._entries.items():
            on = self._order[self._fi] == ("entry", k)
            try:
                e.configure(bg=c["dos_menu_sel_bg"] if on else c["input_bg"],
                            fg=c["dos_menu_sel_fg"] if on else c["input_fg"], font=self._font, insertwidth=self.cw,
                            insertbackground=c["dos_key_fg"] if not on else "#aa0000",
                            selectbackground=c["dos_menu_fg"], selectforeground=c["dos_menu_bg"])
            except tk.TclError:
                pass

    def _focus_is(self, kind, what=None):
        return self._order[self._fi] == (kind, what)

    # -- drawing ------------------------------------------------------------------------------------
    def _preview_coded(self):
        raw = self._entries["text"].get() if self._with_text else SAMPLE
        raw = (raw or SAMPLE).replace("\\n", "\n")
        pre = self._entries["prefix"].get() if self._with_text else ""
        try:
            return pre, ct.apply(raw, self._stops_list, self._mode, self._smooth, seed=1)
        except ValueError:
            return pre, None

    def _render(self):
        c = self.colors
        self._cv.delete("deco")
        self._hits = []
        self._draw_frame(self._title)
        bg, fg, dim = c["dos_menu_bg"], c["dos_menu_fg"], c["dos_menu_dim"]
        screen = c["bg"]
        if self._message:
            self._text(2, self._r_msg, _trunc(self._message, self._total - 4), dim, bg)
        # swatches
        self._text(2, self._r_sw, "Colours".ljust(self.LAB), fg, bg)
        n = len(self._stops_list)
        on_stops = self._focus_is("stops")
        for slot in range(n + 2):
            r, k = divmod(slot, self._per)
            col, row = 2 + self.LAB + k * 4, self._r_sw + r * 2
            if slot < n:
                idx = self._stops_list[slot]
                self._rect(col, row, 3, ct.XTERM[idx])
                if slot == self._sel:
                    self._text(col, row + 1, "▲▲▲", c["dos_key_fg"] if on_stops else fg, bg)
                self._hits.append(("stop", slot, col, col + 3, row))
                self._hits.append(("stop", slot, col, col + 3, row + 1))
            else:
                add = slot == n
                label = "[+]" if add else "[-]"
                self._text(col, row, label, fg, bg)
                self._hits.append(("add" if add else "del", None, col, col + 3, row))
        idx = self._stops_list[self._sel]
        head = "Colour %d of %d  %s" % (self._sel + 1, n, ct.describe(idx))
        self._text(2, self._r_info, head, fg, bg)
        self._text(2 + len(head) + 3, self._r_info,
                   _trunc("Enter palette  Ins add  Del remove", max(0, self._total - 7 - len(head))), dim, bg)
        # the blend bar and the preview sit on the game's own background
        bw = self._total - self._ecol - 2
        self._text(2, self._r_bar, "Blend".ljust(self.LAB), fg, bg)
        for i, ci in enumerate(ct.preview_bar(self._stops_list, bw, self._smooth)):
            self._rect(self._ecol + i, self._r_bar, 1, ct.XTERM[ci])
        # pick fields and the check
        for key, label, row, shown in (("pattern", "Pattern", self._r_pat, self._pattern),
                                       ("mode", "Apply", self._r_mode, self._mode)):
            on = self._focus_is("pick", key)
            self._text(2, row, label.ljust(self.LAB), fg, bg)
            fw = 34 if key == "pattern" else 12
            cell = _trunc(shown, fw - 2).ljust(fw - 2) + " ▼"
            self._text(self._ecol, row, cell, c["dos_menu_sel_fg"] if on else c["input_fg"],
                       c["dos_menu_sel_bg"] if on else c["input_bg"])
            self._hits.append(("pick", key, self._ecol, self._ecol + fw, row))
        on = self._focus_is("check", "smooth")
        s = "[%s] Blend between colours" % ("x" if self._smooth else " ")
        self._text(2, self._r_smooth, s, c["dos_menu_sel_fg"] if on else fg, c["dos_menu_sel_bg"] if on else bg)
        self._hits.append(("check", "smooth", 2, 2 + len(s), self._r_smooth))
        for k in self._entry_keys:
            self._text(2, self._r_entry[k], ("Text" if k == "text" else "Start with").ljust(self.LAB), fg, bg)
            self._hits.append(("entry", k, self._ecol, self._ecol + self._ew, self._r_entry[k]))
        # preview
        self._text(2, self._r_prev, "Preview".ljust(self.LAB), fg, bg)
        self._rect(self._ecol, self._r_prev, bw, screen, nrows=self._prev_rows)
        pre, coded = self._preview_coded()
        if coded is None:
            self._text(self._ecol, self._r_prev, _trunc("(nothing to show)", bw), dim, screen)
        else:
            col, row = 0, 0
            for text, ci in ct.runs(coded):
                colr = ct.XTERM[ci] if ci is not None else c["fg"]
                for ch in text:
                    if ch == "\n":
                        col, row = 0, row + 1
                        continue
                    if row >= self._prev_rows:
                        break
                    if col < bw:
                        self._text(self._ecol + col, self._r_prev + row, ch, colr, screen)
                    col += 1
        # buttons
        labels = ["[ %s ]" % b["label"] for b in self._buttons]
        total = sum(map(len, labels)) + 2 * max(0, len(labels) - 1)
        col = max(1, (self._total - total) // 2)
        for i, (s, b) in enumerate(zip(labels, self._buttons)):
            on = self._focus_is("button", i)
            bfg = c["dos_menu_sel_fg"] if on else fg
            bbg = c["dos_menu_sel_bg"] if on else bg
            self._text(col, self._r_btn, s[:max(0, self._total - 1 - col)], bfg, bbg)
            p = b["label"].lower().find(b["hotkey"])
            if p >= 0 and 2 + p < len(s):
                self._text(col + 2 + p, self._r_btn, b["label"][p], "#aa0000" if on else c["dos_key_fg"], bbg)
            self._hits.append(("button", i, col, col + len(s), self._r_btn))
            col += len(labels[i]) + 2

    # -- focus ---------------------------------------------------------------------------------------
    def _set_focus(self, i):
        self._fi = i % len(self._order)
        self._style_entries()
        self._render()
        kind, what = self._order[self._fi]
        try:
            if kind == "entry":
                e = self._entries[what]
                e.focus_set()
                e.selection_range(0, "end")
                e.icursor("end")
            else:
                self._cv.focus_set()
        except tk.TclError:
            pass

    def _entry_focus(self, key):
        try:
            j = self._order.index(("entry", key))
        except ValueError:
            return
        if j != self._fi:
            self._fi = j
            self._style_entries()
            self._render()

    # -- editing the stops -----------------------------------------------------------------------------
    def _select(self, i):
        self._sel = max(0, min(len(self._stops_list) - 1, i))
        self._render()

    def _add(self):
        self._stops_list, self._sel = ct.add_stop(self._stops_list, self._sel)
        self._layout()
        self._changed()

    def _remove(self):
        self._stops_list, self._sel = ct.remove_stop(self._stops_list, self._sel)
        self._layout()
        self._changed()

    def _move_stop(self, step):
        self._stops_list, self._sel = ct.move_stop(self._stops_list, self._sel, step)
        self._changed()

    def _open_palette(self):
        pal = DosPalette(self._parent, "Colour %d of %d" % (self._sel + 1, len(self._stops_list)),
                         self._stops_list[self._sel], self.colors, self._font, self._palette_done)
        self._palette = pal
        pal.open()

    def _palette_done(self, index):
        self._palette = None
        if index is not None and index != self._stops_list[self._sel]:
            self._stops_list[self._sel] = int(index)
            self._changed()
        try:
            self._cv.focus_set()
        except tk.TclError:
            pass

    # -- results ----------------------------------------------------------------------------------------
    def _finish(self, result):
        if self._done:
            return
        self._done = True
        st = self.state()
        self.close()
        cb = self._on_result
        if callable(cb):
            cb(result, st)

    def _press(self, i):
        if 0 <= i < len(self._buttons):
            self._finish(self._buttons[i]["result"])

    def _hotkey(self, ch):
        for i, b in enumerate(self._buttons):
            if b["hotkey"] == ch.lower():
                self._press(i)
                return True
        return False

    def _escape(self):
        names = [b["result"] for b in self._buttons]
        if "cancel" in names:
            self._finish("cancel")
        else:
            self.close()

    def _enter(self):
        kind, what = self._order[self._fi]
        if kind == "stops":
            self._open_palette()
        elif kind == "pick":
            self._finish(("pick", what))
        elif kind == "check":
            self._smooth = not self._smooth
            self._render()
        elif kind == "button":
            self._press(what)
        elif self._buttons:
            self._press(0)

    # -- events ------------------------------------------------------------------------------------------
    def _common(self, e):
        ks = e.keysym
        if ks in ("Tab", "ISO_Left_Tab"):
            self._set_focus(self._fi + (-1 if ks == "ISO_Left_Tab" or e.state & 1 else 1))
        elif ks == "Down" and self._order[self._fi][0] != "stops":
            self._set_focus(self._fi + 1)
        elif ks == "Up" and self._order[self._fi][0] != "stops":
            self._set_focus(self._fi - 1)
        elif ks in ("Return", "KP_Enter"):
            self._enter()
        elif ks == "Escape":
            self._escape()
        else:
            return False
        return True

    def _on_entry_key(self, e):
        if e.keysym.startswith("Alt") or (e.state & 0x20000 and len(e.keysym) == 1):
            if len(e.keysym) == 1:
                self._hotkey(e.keysym)
            return "break"
        self._common(e)
        return "break"

    def _on_alt(self, e):
        if e.keysym == "Left":
            self._escape()
        elif len(e.keysym) == 1:
            self._hotkey(e.keysym)
        return "break"

    def _on_key(self, e):
        if self._common(e):
            return "break"
        ks = e.keysym
        kind, what = self._order[self._fi]
        ctrl = bool(e.state & 0x4)
        if kind == "stops":
            if ks == "Left":
                self._move_stop(-1) if ctrl else self._select(self._sel - 1)
            elif ks == "Right":
                self._move_stop(1) if ctrl else self._select(self._sel + 1)
            elif ks == "Home":
                self._select(0)
            elif ks == "End":
                self._select(len(self._stops_list) - 1)
            elif ks in ("Insert", "plus", "KP_Add"):
                self._add()
            elif ks in ("Delete", "minus", "KP_Subtract"):
                self._remove()
            elif ks == "space":
                self._open_palette()
            elif ks in ("Up", "Down"):
                self._set_focus(self._fi + (1 if ks == "Down" else -1))
        elif kind == "button" and ks in ("Left", "Right"):
            self._set_focus(self._fi + (1 if ks == "Right" else -1) if 0 <= what + (1 if ks == "Right" else -1) < len(self._buttons)
                            else self._fi)
        elif ks == "space":
            self._enter()
        elif e.char and len(e.char) == 1 and e.char.isprintable():
            self._hotkey(e.char)
        return "break"

    def _on_click(self, e):
        col, row = int(e.x) // self.cw, int(e.y) // self.lh
        for kind, what, c0, c1, r in self._hits:
            if r != row or not c0 <= col < c1:
                continue
            if kind == "stop":
                again = self._sel == what and self._focus_is("stops")
                self._sel = what
                self._fi = 0
                self._style_entries()
                self._render()
                self._cv.focus_set()
                if again:
                    self._open_palette()
            elif kind == "add":
                self._fi = 0
                self._add()
            elif kind == "del":
                self._fi = 0
                self._remove()
            elif kind == "pick":
                self._finish(("pick", what))
            elif kind == "check":
                self._set_focus(self._order.index(("check", "smooth")))
                self._enter()
            elif kind == "entry":
                self._set_focus(self._order.index(("entry", what)))
            elif kind == "button":
                self._press(what)
            return
        try:
            self._cv.focus_set()
        except tk.TclError:
            pass

    # -- lifecycle ------------------------------------------------------------------------------------------
    def open(self, x=None, y=None):
        if self._is_open:
            self.close()
        self._done = False
        self._begin_open()
        self._layout()
        self._fi = 0
        self._render()
        self._place_box(x, y)
        try:
            self.update_idletasks()
            self._cv.focus_set()
        except tk.TclError:
            pass

    def close(self):
        self._finish_close()

    def restyle(self, colors, font=None):
        self.colors = dos_colors(colors)
        if font is not None:
            self._font = font
        self._measure()
        self.configure(bg=self.colors["dos_menu_bg"])
        self._layout()
        self._render()
