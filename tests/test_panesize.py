"""Resizing pane areas by dragging a border, behind a lock (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import layout
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1300x800+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


class Ev:
    def __init__(self, x_root=0, y_root=0, x=0, y=0):
        self.x_root, self.y_root, self.x, self.y = x_root, y_root, x, y


def build(preset):
    app.cfg["panes"] = [{"name": "Tells", "title": "Tells", "max_lines": 100, "timestamps": False},
                        {"name": "OOC", "title": "OOC", "max_lines": 100, "timestamps": False}]
    app.cfg["layout"] = layout.preset_layout(preset, app.cfg["panes"])
    for d in app.cfg["panes"]:
        app.pane_ensure(d["name"])
    app.layout_panes(); pump(0.4)


def size_of(side):
    return max(r["size"] for r in app.cfg["layout"]["regions"] if r["side"] == side)


pump(0.3)
assert app.panes_locked() and app.cfg["panes_locked"] is True, "locked by default"
build("Right column")
assert app._panes_active and not app._sash_frames, "locked: no handles at all"
before = size_of("right")
app._sash_press("right", Ev(500, 300))
assert app._sash_drag is None, "a locked press does nothing"
app._sash_motion(Ev(400, 300))
assert size_of("right") == before, "and neither does a drag"

# unlock: a handle appears on the right side
app.set_panes_locked(False); pump(0.3)
assert not app.panes_locked() and "right" in app._sash_frames
f = app._sash_frames["right"]
assert f.winfo_ismapped() and f.cget("cursor") == "sb_h_double_arrow"
cw, lh = app._pane_cell()
x0 = f.winfo_rootx()
app._sash_press("right", Ev(x0, 300))
app._sash_motion(Ev(x0 - 5 * cw, 300))                      # drag left by five columns: the area grows
assert size_of("right") == before + 5, (before, size_of("right"))
app._sash_motion(Ev(x0 + 3 * cw, 300))
assert size_of("right") == before - 3, "and shrinks back past where it began"
app._sash_motion(Ev(x0 + 500 * cw, 300))
assert size_of("right") == 16, "never below the minimum width"
app._sash_motion(Ev(x0 - 900 * cw, 300))
mx, my, mw, mh = app._pane_geom["main"]
assert mw >= 80 * cw - 1, "the main text keeps its 80 columns however far it is dragged"
assert size_of("right") < 100, "the stored size is what really fits, not what the mouse asked for"
app._sash_release(); pump(0.2)
assert app._sash_drag is None
import json
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert saved["panes_locked"] is False and saved["layout"]["regions"][0]["size"] == size_of("right"), "saved"

# lock again: the handle is gone
app.set_panes_locked(True); pump(0.2)
assert not f.winfo_ismapped()
app._sash_press("right", Ev(x0, 300)); assert app._sash_drag is None

# a strip along the bottom
build("Long strip on the bottom")
app.set_panes_locked(False); pump(0.3)
assert "bottom" in app._sash_frames and app._sash_frames["bottom"].cget("cursor") == "sb_v_double_arrow"
b = size_of("bottom")
y0 = app._sash_frames["bottom"].winfo_rooty()
app._sash_press("bottom", Ev(400, y0))
app._sash_motion(Ev(400, y0 - 2 * lh))
assert size_of("bottom") == b + 2, (b, size_of("bottom"))
app._sash_release()

# the DOS look: the frame line is the handle, found by position
app.set_dos_mode(True); pump(0.5)
assert not app.panes_locked() and "bottom" in app._sash_hits
sx, sy, sw, sh = app._sash_hits["bottom"]
assert app._hit_side(sx + 3, sy + 1) == "bottom" and app._hit_side(5, 5) is None
assert not app._sash_frames["bottom"].winfo_ismapped(), "no bar in DOS look"
b = size_of("bottom")
app._canvas_press(Ev(x=sx + 10, y=sy + 2, x_root=400, y_root=600))
assert app._sash_drag is not None
app._sash_motion(Ev(x_root=400, y_root=600 - 3 * app._pane_cell()[1]))
assert size_of("bottom") == b + 3, (b, size_of("bottom"))
app._sash_release()
app.set_panes_locked(True); pump(0.2)
assert not app._sash_hits
app._canvas_press(Ev(x=sx + 10, y=sy + 2)); assert app._sash_drag is None
app.set_dos_mode(False); pump(0.3)

# /panelock and the menu variable
app._local("/panelock off"); assert not app.panes_locked() and not app.v_panelock.get()
app._local("/panelock on"); assert app.panes_locked() and app.v_panelock.get()
app._local("/panelock"); assert not app.panes_locked()
app._local("/panelock"); assert app.panes_locked()

# no areas at all: unlocking is harmless
app.cfg["layout"] = {"regions": [], "min_main_cols": 80}; app.layout_panes()
app.set_panes_locked(False); pump(0.2); app.set_panes_locked(True)

# a bad value in the settings file means locked
assert sc.clean_settings({"panes_locked": "no"})["panes_locked"] is True
assert sc.clean_settings({"panes_locked": False})["panes_locked"] is False
assert sc.clean_settings({})["panes_locked"] is True

root.update(); root.destroy()
print("pane size tests OK")
