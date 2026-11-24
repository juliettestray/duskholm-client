"""Resizing pane areas by dragging their borders, behind a lock (no network)."""
import io, json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import layout
import tkinter as tk
from PIL import Image

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


def weights():
    return [r["weight"] for r in app.cfg["layout"]["regions"]]


def edge(side):
    return app._sash_frames[("edge", side)]


def top_child():
    return app._holder.tk.eval("lindex [winfo children %s] end" % app._holder)


pump(0.3)
assert app.panes_locked() and app.cfg["panes_locked"] is True, "locked by default"
build("Right column")
assert app._panes_active and not any(f.winfo_ismapped() for f in (app._sash_frames or {}).values()), "locked: no bars"
before = size_of("right")
app._sash_press("right", Ev(500, 300))
assert app._sash_drag is None, "a locked press does nothing"
app._sash_motion(Ev(400, 300))
assert size_of("right") == before, "and neither does a drag"

# unlock: a bar appears on the right side
app.set_panes_locked(False); pump(0.3)
assert not app.panes_locked() and ("edge", "right") in app._sash_frames
f = edge("right")
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
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert saved["panes_locked"] is False and saved["layout"]["regions"][0]["size"] == size_of("right"), "saved"

# lock again: the bar is gone
app.set_panes_locked(True); pump(0.2)
assert not f.winfo_ismapped()
app._sash_press("right", Ev(x0, 300)); assert app._sash_drag is None

# two areas stacked on the right: a divider between them moves their share of the height
build("Right column, two stacked")
app.set_panes_locked(False); pump(0.3)
splits = [k for k in app._sash_frames if k[0] == "split" and app._sash_frames[k].winfo_ismapped()]
assert len(splits) == 1, list(app._sash_frames)
sp = app._sash_frames[splits[0]]
assert sp.cget("cursor") == "sb_v_double_arrow" and sp.winfo_width() > 50
ra, rb = (app._pane_geom["regions"][r]["rect"] for r in splits[0][1:])
assert weights() == [1, 1] and abs(ra[3] - rb[3]) <= lh * 2, "equal to begin with"
y0 = sp.winfo_rooty()
app._sash_press(splits[0], Ev(900, y0))
app._sash_motion(Ev(900, y0 + 120))                          # drag down: the first area grows
ra2, rb2 = (app._pane_geom["regions"][r]["rect"] for r in splits[0][1:])
assert ra2[3] > ra[3] + 60 and rb2[3] < rb[3] - 60, (ra, ra2, rb, rb2)
assert weights()[0] > weights()[1] and sum(weights()) == 10, weights()
app._sash_motion(Ev(900, y0 - 100000))                       # as far up as it goes: both areas keep some height
assert min(weights()) >= 1
assert all(r in app._pane_geom["regions"] for r in splits[0][1:]), "neither area disappears"
app._sash_release(); pump(0.2)
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert [r["weight"] for r in saved["layout"]["regions"]] == weights(), "saved"
app.set_panes_locked(True)

# a strip along the bottom
build("Long strip on the bottom")
app.set_panes_locked(False); pump(0.3)
assert edge("bottom").cget("cursor") == "sb_v_double_arrow"
b = size_of("bottom")
y0 = edge("bottom").winfo_rooty()
app._sash_press("bottom", Ev(400, y0))
app._sash_motion(Ev(400, y0 - 2 * lh))
assert size_of("bottom") == b + 2, (b, size_of("bottom"))
app._sash_release()

# the DOS look: the bar is a whole cell on the frame line, and the scrollbars on those lines step aside
app.set_dos_mode(True); pump(0.5)
build("Right column, two stacked")
for i in range(80):
    app._on_data(("filler line %d\n\r" % i).encode())
for i in range(30):
    app._panes["tells"]["text"].configure(state="normal"); app._panes["tells"]["text"].insert("end", "x\n")
pump(0.4)
app.set_panes_locked(False); pump(0.4)
cw, lh = app._pane_cell()
assert not app.panes_locked() and app._resize_mode()
fr = edge("right")
assert fr.winfo_ismapped() and fr.winfo_width() >= cw - 1, "a whole cell wide, easy to grab"
assert not app._dosscroll.winfo_ismapped(), "the main scrollbar does not cover the bar"
assert not any(p["dsb"].winfo_ismapped() for p in app._panes.values()), "nor do the pane scrollbars"
assert top_child() == str(fr) or str(fr) in app._holder.tk.eval("winfo children %s" % app._holder)
sp = next(app._sash_frames[k] for k in app._sash_frames if k[0] == "split")
assert sp.winfo_ismapped() and sp.winfo_height() >= lh - 1
b = size_of("right")
x0 = fr.winfo_rootx()
app._sash_press("right", Ev(x0, 300))
app._sash_motion(Ev(x0 - 4 * cw, 300))
assert size_of("right") == b + 4, (b, size_of("right"))
app._sash_release()
app.set_panes_locked(True); pump(0.3)
assert not fr.winfo_ismapped() and not app._resize_mode()
assert app._dosscroll.winfo_ismapped(), "scrollbars come back when it is locked"
app.set_dos_mode(False); pump(0.3)

# a picture or the notepad covering the main area stays on top of the panes, headers and drag bars
build("Right column")
buf = io.BytesIO(); Image.new("RGB", (40, 30), (200, 40, 40)).save(buf, "PNG")
app.set_panes_locked(False); pump(0.3)
assert app.show_image("https://x.example/a.png", buf.getvalue()) is True; pump(0.3)
frame = app._image_view["frame"]
app.layout_panes(); pump(0.2)
assert top_child() == str(frame), "after a re-layout the picture is still the topmost thing: " + top_child()
app.set_panes_locked(True); app.set_panes_locked(False); pump(0.2)
assert top_child() == str(frame), "and after locking and unlocking"
app.pane_ensure("Late"); app.layout_panes(); pump(0.2)
assert top_child() == str(frame), "and when a new pane appears"
opened = []
sc.webbrowser.open = lambda u, *a, **k: opened.append(u)
app._image_view["cv"].event_generate("<Button-1>", x=20, y=20); pump(0.2)
assert not opened, "a click on the picture only takes the focus; it never opens the browser"
app.close_image_view(); pump(0.2)
app.toggle_notepad(); pump(0.3)
nf = app._notepad["frame"]
app.layout_panes(); pump(0.2)
assert top_child() == str(nf), "the notepad too"
app.toggle_notepad(); pump(0.2)
# a DOS dialog (the description editor is one) stays on top of the panes after a re-layout
app.set_dos_mode(True); pump(0.5)
ed = app.dos_edit_text("Description", "hello", lambda r: None); pump(0.3)
app.layout_panes(); pump(0.2)
assert app._panes_active and top_child() == str(ed), top_child()
ed.close(); app.set_dos_mode(False); pump(0.3)

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
