"""Drag the borders of the pane areas with the mouse to resize them, behind a lock so nothing moves by accident.

The lock is on by default. While it is on there is nothing to grab: no bar, no changed pointer. Unlocked:
  * the border between the main text and a side's pane areas moves that whole side (every area on it shares
    one width or height);
  * the divider between two areas stacked on the same side moves their share of the space.
In the DOS look the bars sit on the frame lines themselves, a whole cell thick, and the scrollbars that live on
those lines step aside while the lock is off (the wheel and PgUp/PgDn still scroll). Sizes are saved with the
layout (per world)."""
import tkinter as tk

import layout

GRIP = 8                     # thickness of a drag bar in the ordinary look, pixels
CURSOR = {"v": "sb_h_double_arrow", "h": "sb_v_double_arrow"}      # a vertical bar moves left/right
WEIGHT_STEPS = 10            # resolution of a divider between two areas
EDGE_SIDES = ("left", "right", "top", "bottom")


def _key(k):
    return ("edge", k) if isinstance(k, str) else tuple(k)


class PaneSizeMixin:
    _sash_frames = None            # key -> Frame; key is ("edge", side) or ("split", id_a, id_b)
    _sash_drag = None

    # ---- the lock ---------------------------------------------------------------------------
    def panes_locked(self):
        return self.cfg.get("panes_locked", True) is not False

    def _resize_mode(self):
        """Bars are showing (so the DOS scrollbars on the frame lines get out of their way)."""
        return bool(self.dos and not self.panes_locked() and getattr(self, "_panes_active", False))

    def set_panes_locked(self, locked, announce=True):
        self.cfg["panes_locked"] = bool(locked)
        try:
            self.v_panelock.set(bool(locked))
        except (AttributeError, tk.TclError):
            pass
        self._sash_drag = None
        self._save_settings()
        self._update_sashes()
        if self.dos:
            self._dos_scroll_visibility()
            for key in list(self._panes):
                self._pane_scroll_visibility(key)
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

    # ---- where the bars are -----------------------------------------------------------------
    def _sash_specs(self):
        """{key: (x, y, w, h, orientation)} in holder pixels; orientation "v" is a vertical bar."""
        geo = self._pane_geom
        cw, lh = self._pane_cell()
        by_side = {}
        for r in self._visible_layout()["regions"]:
            info = geo["regions"].get(r["id"]) if geo else None
            if info:
                by_side.setdefault(r["side"], []).append((r["id"], info["rect"]))
        dos = self.dos

        specs = {}
        for side, items in by_side.items():
            rs = [r for _i, r in items]
            x0, y0 = min(r[0] for r in rs), min(r[1] for r in rs)
            x1, y1 = max(r[0] + r[2] for r in rs), max(r[1] + r[3] for r in rs)
            if dos:                                     # the shared frame line, one cell thick
                geom = {"right": (x0, y0, cw, y1 - y0, "v"), "left": (x1 - cw, y0, cw, y1 - y0, "v"),
                        "top": (x0, y1 - lh, x1 - x0, lh, "h"), "bottom": (x0, y0, x1 - x0, lh, "h")}
            else:                                       # a bar across the gap between main text and the area
                geom = {"right": (x0 - GRIP + 2, y0, GRIP, y1 - y0, "v"), "left": (x1 - 2, y0, GRIP, y1 - y0, "v"),
                        "top": (x0, y1 - 2, x1 - x0, GRIP, "h"), "bottom": (x0, y0 - GRIP + 2, x1 - x0, GRIP, "h")}
            specs[("edge", side)] = geom[side]
            col = side in ("left", "right")
            order = sorted(items, key=lambda it: it[1][1] if col else it[1][0])
            for (ida, ra), (idb, rb) in zip(order, order[1:]):
                if col:                                 # stacked: a horizontal divider across the area's width
                    y = rb[1]
                    specs[("split", ida, idb)] = ((rb[0], y, rb[2], lh, "h") if dos
                                                  else (rb[0], y - GRIP + 2, rb[2], GRIP, "h"))
                else:                                   # side by side: a vertical divider
                    x = rb[0]
                    specs[("split", ida, idb)] = ((x, rb[1], cw, rb[3], "v") if dos
                                                  else (x - GRIP + 2, rb[1], GRIP, rb[3], "v"))
        return specs

    def _forget_sashes(self):
        for f in (self._sash_frames or {}).values():
            try:
                f.place_forget()
            except tk.TclError:
                pass

    def _sash_colour(self):
        th = self.theme
        if self.dos:
            try:
                return self._dc()["dos_menu_fg"]
            except Exception:
                pass
        return th.get("dim") or th.get("fg") or "#888888"

    def _update_sashes(self):
        """Called after every layout: show the bars (unlocked) or none at all (locked)."""
        if self._sash_frames is None:
            self._sash_frames = {}
        if (self.panes_locked() or not getattr(self, "_panes_active", False) or self._pane_geom is None
                or not self._visible_layout()["regions"]):
            self._forget_sashes()
            return
        specs = self._sash_specs()
        for key in list(self._sash_frames):
            if key not in specs:
                self._sash_frames.pop(key).destroy()
        colour = self._sash_colour()
        for key, (x, y, w, h, orient) in specs.items():
            f = self._sash_frames.get(key)
            if f is None:
                f = self._sash_frames[key] = tk.Frame(self._holder, cursor=CURSOR[orient], bd=0, highlightthickness=0)
                f.bind("<ButtonPress-1>", lambda e, k=key: self._sash_press(k, e))
                f.bind("<B1-Motion>", self._sash_motion)
                f.bind("<ButtonRelease-1>", self._sash_release)
            f.configure(bg=colour)
            f.place(x=x, y=y, width=max(2, w), height=max(2, h))
            f.lift()
        self._raise_overlays()                          # a picture or the notepad stays on top of the bars

    # ---- dragging --------------------------------------------------------------------------------
    def _regions_of(self, side):
        return [r for r in self._visible_layout()["regions"] if r["side"] == side]

    def _rect_of(self, rid):
        info = (self._pane_geom or {}).get("regions", {}).get(rid)
        return info["rect"] if info else None

    def _side_thickness(self, side):
        for r in self._regions_of(side):
            rect = self._rect_of(r["id"])
            if rect:
                return rect[2] if side in ("left", "right") else rect[3]
        return None

    def _sash_press(self, key, e):
        key = _key(key)
        if self.panes_locked():
            return
        if key[0] == "edge":
            side = key[1]
            th, regs = self._side_thickness(side), self._regions_of(side)
            if th is None or not regs:
                return
            size = max(r["size"] for r in regs)
            self._sash_drag = {"kind": "edge", "side": side, "x": e.x_root, "y": e.y_root, "th": th,
                               "size": size, "cur": size}
            return
        _k, ida, idb = key
        ra, rb = self._rect_of(ida), self._rect_of(idb)
        reg = {r["id"]: r for r in self._visible_layout()["regions"]}
        if not ra or not rb or ida not in reg or idb not in reg:
            return
        col = reg[ida]["side"] in ("left", "right")
        same = [r for r in self._regions_of(reg[ida]["side"])]
        # more resolution: scale the side's weights up (keeping their proportions) so the pair can be split finely
        pair = reg[ida]["weight"] + reg[idb]["weight"]
        m = max(1, min(WEIGHT_STEPS // max(1, pair), 9 // max(r["weight"] for r in same)))
        self._sash_drag = {"kind": "split", "a": ida, "b": idb, "col": col, "x": e.x_root, "y": e.y_root,
                           "la": ra[3] if col else ra[2], "lb": rb[3] if col else rb[2], "m": m,
                           "start": {r["id"]: r["weight"] for r in same}, "side": reg[ida]["side"],
                           "pair": pair * m, "cur": None}

    def _set_side_size(self, side, size):
        lay = self.cfg["layout"]
        regions = [dict(r, size=size if r["side"] == side else r["size"], panes=list(r["panes"]))
                   for r in lay["regions"]]
        self.cfg["layout"] = layout.validate_layout(
            dict(lay, regions=regions), known_panes=[d["name"] for d in self.cfg["panes"]])

    def _set_weights(self, weights):
        """weights: {region id: weight} for some regions."""
        lay = self.cfg["layout"]
        regions = [dict(r, weight=weights.get(r["id"], r["weight"]), panes=list(r["panes"]))
                   for r in lay["regions"]]
        self.cfg["layout"] = layout.validate_layout(
            dict(lay, regions=regions), known_panes=[d["name"] for d in self.cfg["panes"]])

    def _sash_motion(self, e):
        d = self._sash_drag
        if not d or self.panes_locked():
            return
        cw, lh = self._pane_cell()
        if d["kind"] == "split":
            return self._split_motion(d, e, cw, lh)
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

    def _split_motion(self, d, e, cw, lh):
        delta = (e.y_root - d["y"]) if d["col"] else (e.x_root - d["x"])
        total = d["la"] + d["lb"]
        frac = max(0.0, min(1.0, (d["la"] + delta) / float(max(1, total))))
        wa = max(1, min(d["pair"] - 1, int(round(frac * d["pair"]))))
        wb = d["pair"] - wa
        if (wa, wb) == d["cur"]:
            return
        old = {r["id"]: r["weight"] for r in self._regions_of(d["side"])}
        new = {rid: min(9, w * d["m"]) for rid, w in d["start"].items()}
        new[d["a"]], new[d["b"]] = wa, wb
        self._set_weights(new)
        self.layout_panes()
        shown = (self._pane_geom or {}).get("regions", {})
        if d["a"] not in shown or d["b"] not in shown:  # no room for that split: put it back
            self._set_weights(old)
            self.layout_panes()
            return
        d["cur"] = (wa, wb)

    def _sash_release(self, e=None):
        if self._sash_drag is not None:
            self._sash_drag = None
            self._save_settings()
