"""Drag the border of a pane area with the mouse to resize it, behind a lock so nothing moves by accident.

The lock is on by default. While it is on there is nothing to grab: no bar, no changed pointer. Unlocked, the
border between the main text and a side's pane areas can be dragged; every area on that side follows (they
share one width or height). The new size is saved with the rest of the layout (per world)."""
import tkinter as tk

import layout

GRIP = 8                     # thickness of the grab bar in the ordinary look, pixels
CURSOR = {"left": "sb_h_double_arrow", "right": "sb_h_double_arrow",
          "top": "sb_v_double_arrow", "bottom": "sb_v_double_arrow"}


class PaneSizeMixin:
    _sash_frames = None            # side -> Frame (ordinary look)
    _sash_hits = None              # side -> (x, y, w, h), DOS look: the frame line is the handle
    _sash_drag = None

    # ---- the lock ---------------------------------------------------------------------------
    def panes_locked(self):
        return self.cfg.get("panes_locked", True) is not False

    def set_panes_locked(self, locked, announce=True):
        self.cfg["panes_locked"] = bool(locked)
        try:
            self.v_panelock.set(bool(locked))
        except (AttributeError, tk.TclError):
            pass
        self._sash_drag = None
        self._save_settings()
        self._update_sashes()
        if announce:
            has = bool(self.cfg["layout"]["regions"])
            self.set_notice("Pane sizes locked" if locked else
                            ("Pane sizes unlocked: drag the border of an area" if has else
                             "Pane sizes unlocked (no pane areas yet)"), 5)
        if self.dos:
            self.update_dosbar()

    def toggle_panes_locked(self):
        self.set_panes_locked(not self.panes_locked())

    def _panesize_command(self, cmd, arg):
        """/panelock [on|off]"""
        if cmd not in ("panelock", "panesize"):
            return False
        a = (arg or "").strip().lower()
        if a in ("on", "lock", "locked", "yes"):
            self.set_panes_locked(True)
        elif a in ("off", "unlock", "unlocked", "no"):
            self.set_panes_locked(False)
        else:
            self.toggle_panes_locked()
        return True

    # ---- where the handles are -----------------------------------------------------------------
    def _sash_specs(self):
        """side -> (x, y, w, h) of its handle, in holder pixels."""
        geo = self._pane_geom
        cw, lh = self._pane_cell()
        by_side = {}
        for r in self._visible_layout()["regions"]:
            info = geo["regions"].get(r["id"]) if geo else None
            if info:
                by_side.setdefault(r["side"], []).append(info["rect"])
        specs = {}
        for side, rs in by_side.items():
            x0, y0 = min(r[0] for r in rs), min(r[1] for r in rs)
            x1, y1 = max(r[0] + r[2] for r in rs), max(r[1] + r[3] for r in rs)
            if self.dos:                                # the shared frame line, one cell thick
                if side == "right":
                    specs[side] = (x0, y0, cw, y1 - y0)
                elif side == "left":
                    specs[side] = (x1 - cw, y0, cw, y1 - y0)
                elif side == "top":
                    specs[side] = (x0, y1 - lh, x1 - x0, lh)
                else:
                    specs[side] = (x0, y0, x1 - x0, lh)
            else:                                       # a bar across the gap between main text and the area
                if side == "right":
                    specs[side] = (x0 - GRIP + 2, y0, GRIP, y1 - y0)
                elif side == "left":
                    specs[side] = (x1 - 2, y0, GRIP, y1 - y0)
                elif side == "top":
                    specs[side] = (x0, y1 - 2, x1 - x0, GRIP)
                else:
                    specs[side] = (x0, y0 - GRIP + 2, x1 - x0, GRIP)
        return specs

    def _forget_sashes(self):
        for f in (self._sash_frames or {}).values():
            try:
                f.place_forget()
            except tk.TclError:
                pass
        self._sash_hits = {}

    def _update_sashes(self):
        """Called after every layout: show the handles (unlocked) or none at all (locked)."""
        if self._sash_frames is None:
            self._sash_frames = {}
        if (self.panes_locked() or not getattr(self, "_panes_active", False) or self._pane_geom is None
                or not self._visible_layout()["regions"]):
            self._forget_sashes()
            self._set_canvas_cursor("")
            return
        specs = self._sash_specs()
        if self.dos:
            for f in self._sash_frames.values():
                f.place_forget()
            self._sash_hits = specs
            self._bind_canvas()
            return
        self._sash_hits = {}
        for side in list(self._sash_frames):
            if side not in specs:
                self._sash_frames[side].place_forget()
        colour = self.theme.get("dim") or self.theme.get("fg") or "#888888"
        for side, (x, y, w, h) in specs.items():
            f = self._sash_frames.get(side)
            if f is None:
                f = self._sash_frames[side] = tk.Frame(self._holder, cursor=CURSOR[side], bd=0, highlightthickness=0)
                f.bind("<ButtonPress-1>", lambda e, s=side: self._sash_press(s, e))
                f.bind("<B1-Motion>", self._sash_motion)
                f.bind("<ButtonRelease-1>", self._sash_release)
            f.configure(bg=colour)
            f.place(x=x, y=y, width=max(2, w), height=max(2, h))
            f.lift()
        self._raise_overlays()                          # a picture or the notepad stays on top of the bars

    # ---- DOS look: the double-line frame behind the text is the handle ----------------------------
    def _bind_canvas(self):
        fc = self._framecv
        if fc is None or getattr(fc, "_sash_bound", False):
            return
        fc._sash_bound = True
        fc.bind("<Motion>", self._canvas_motion)
        fc.bind("<Leave>", lambda e: self._set_canvas_cursor(""))
        fc.bind("<ButtonPress-1>", self._canvas_press)
        fc.bind("<B1-Motion>", self._sash_motion)
        fc.bind("<ButtonRelease-1>", self._sash_release)

    def _set_canvas_cursor(self, cur):
        fc = getattr(self, "_framecv", None)
        if fc is not None:
            try:
                if fc.cget("cursor") != cur:
                    fc.configure(cursor=cur)
            except tk.TclError:
                pass

    def _hit_side(self, x, y):
        for side, (sx, sy, sw, sh) in (self._sash_hits or {}).items():
            if sx <= x < sx + sw and sy <= y < sy + sh:
                return side
        return None

    def _canvas_motion(self, e):
        if self._sash_drag:
            return
        side = self._hit_side(e.x, e.y) if not self.panes_locked() else None
        self._set_canvas_cursor(CURSOR[side] if side else "")

    def _canvas_press(self, e):
        side = self._hit_side(e.x, e.y) if not self.panes_locked() else None
        if side:
            self._sash_press(side, e)

    # ---- dragging --------------------------------------------------------------------------------
    def _side_regions(self, side):
        return [r for r in self._visible_layout()["regions"] if r["side"] == side]

    def _side_thickness(self, side):
        geo = self._pane_geom
        for r in self._side_regions(side):
            info = geo["regions"].get(r["id"]) if geo else None
            if info:
                return info["rect"][2] if side in ("left", "right") else info["rect"][3]
        return None

    def _sash_press(self, side, e):
        th = self._side_thickness(side)
        regs = self._side_regions(side)
        if th is None or not regs or self.panes_locked():
            return
        self._sash_drag = {"side": side, "x": e.x_root, "y": e.y_root, "th": th,
                           "size": max(r["size"] for r in regs), "cur": max(r["size"] for r in regs)}

    def _set_side_size(self, side, size):
        lay = self.cfg["layout"]
        regions = [dict(r, size=size if r["side"] == side else r["size"], panes=list(r["panes"]))
                   for r in lay["regions"]]
        self.cfg["layout"] = layout.validate_layout(
            dict(lay, regions=regions), known_panes=[d["name"] for d in self.cfg["panes"]])

    def _sash_motion(self, e):
        d = self._sash_drag
        if not d or self.panes_locked():
            return
        cw, lh = self._pane_cell()
        side = d["side"]
        move = {"right": -(e.x_root - d["x"]) / cw, "left": (e.x_root - d["x"]) / cw,
                "top": (e.y_root - d["y"]) / lh, "bottom": -(e.y_root - d["y"]) / lh}[side]
        want = d["size"] + int(round(move))
        if want == d["cur"]:
            return
        self._set_side_size(side, want)
        self.layout_panes()
        th = self._side_thickness(side)
        if th is not None:                              # the window may not have had room: keep what really fits
            unit = cw if side in ("left", "right") else lh
            actual = d["size"] + int(round((th - d["th"]) / float(unit)))
            if actual != want:
                self._set_side_size(side, actual)
                self.layout_panes()
            d["cur"] = actual
        else:
            d["cur"] = want

    def _sash_release(self, e=None):
        if self._sash_drag is not None:
            self._sash_drag = None
            self._save_settings()
