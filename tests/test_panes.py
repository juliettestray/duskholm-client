"""Capture panes: routing, tabs, unread counts, geometry in both looks (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import layout
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x760+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def feed(*lines):
    for l in lines:
        app._on_data((l + "\n\r").encode())
    pump(0.2)


def main_text():
    return app.out.get("1.0", "end")


app.connected = True
pump(0.3)
app.cfg["triggers"] = [
    {"name": "ooc", "enabled": True, "mode": "plain", "pattern": "^[OOC]*", "priority": 0,
     "actions": [{"type": "route", "pane": "OOC"}]},
    {"name": "tell", "enabled": True, "mode": "plain", "pattern": "* tells you *", "priority": 0,
     "actions": [{"type": "route", "pane": "Tells", "gag": True}]},
]
assert not app.cfg["layout"]["regions"] and not app._panes_active

feed("[OOC] Bob: 'hi all'")
assert "[OOC] Bob" in main_text(), "copy by default: the line stays in the main window"
assert "ooc" in app._panes and app._panes_active, "first routed line creates the pane and a default layout"
assert app.cfg["layout"]["regions"], "a default layout was applied"
assert "[OOC] Bob" in app._panes["ooc"]["text"].get("1.0", "end")

feed("Ann tells you 'psst'")
assert "Ann tells you" not in main_text(), "gag hides it from the main window"
assert "Ann tells you" in app._panes["tells"]["text"].get("1.0", "end")
assert layout.find_region(app.cfg["layout"], "Tells") is not None

# geometry: main keeps >= 80 columns, panes sit inside the holder
pump(0.4)
g = app._pane_geom
assert g and g["main"][2] >= 80 * app.f_norm.measure("0"), g
for rid, info in g["regions"].items():
    bx, by, bw, bh = info["body"]
    assert bx >= 0 and by >= 0 and bx + bw <= app._holder.winfo_width() + 1 and by + bh <= app._holder.winfo_height() + 1

# unread counts on the tab that is not showing
reg = app._pane_region("ooc")
shown = app._active_pane_key(reg)
other = [k for k in ("ooc", "tells") if k != shown]
if other and app._pane_region(other[0]) is reg:
    feed("[OOC] Bob: 'again'" if other[0] == "ooc" else "Ann tells you 'x'")
    assert app._panes[other[0]]["unread"] == 1
    app.select_pane(other[0]); pump(0.2)
    assert app._panes[other[0]]["unread"] == 0 and app._active_pane_key(reg) == other[0]

# history trimming
d = app._find_pane_def("ooc")
d["max_lines"] = 50
for i in range(80):
    app.pane_append("OOC", [("line %d" % i, (None, None, False, False, False, False))])
assert len(app._panes["ooc"]["history"]) == 50
assert int(app._panes["ooc"]["text"].index("end-1c").split(".")[0]) <= 51

# unknown route target cap
for i in range(20):
    app.pane_ensure("extra%d" % i)
assert len(app.cfg["panes"]) <= layout.MAX_PANES

# presets and a narrow window never push main under 80 columns
app.cfg["layout"] = layout.preset_layout("Top strip + right column", [p["name"] for p in app.cfg["panes"]])
app.layout_panes(); pump(0.3)
assert app._pane_geom["main"][2] >= 80 * app.f_norm.measure("0") or app._pane_geom["hidden"]

# DOS look
app.set_dos_mode(True); pump(0.6)
assert app._panes_active and app._pane_geom
app.feed_check = None
feed("[OOC] Bob: 'dos'")
assert "[OOC] Bob: 'dos'" in app._panes["ooc"]["text"].get("1.0", "end")
app.set_dos_mode(False); pump(0.4)


# ---- manager: parse, preview, save (both looks), trigger editor round trip
app.cfg["panes"], app.cfg["layout"] = [], {"regions": [], "min_main_cols": 80}
lay, defs, msg = app._panes_parse(["top 4 OOC", "right 40 Tells, Guide", ""])
assert lay and len(lay["regions"]) == 2 and {d["name"] for d in defs} == {"OOC", "Tells", "Guide"}, msg
assert app._panes_parse(["middle 3 X"])[0] is None and app._panes_parse(["top x"])[0] is None
txt = app._panes_preview_text(["top 4 OOC", "right 40 Tells"])
assert "OOC" in txt and "Tells" in txt
ok, m = app._panes_save(["top 4 OOC", "right 40 Tells, Guide"]); pump(0.4)
assert ok and app._panes_active and len(app.cfg["layout"]["regions"]) == 2
assert app._pane_lines()[0].startswith("top 4")
for n in layout.PRESETS:
    assert app._preset_lines(n), n
app.open_panes(); pump(0.3); assert app._panes_win is not None
app._panes_win.destroy(); app._panes_win = None
app.set_dos_mode(True); pump(0.5)
app.open_panes(); pump(0.3); assert app._overlay_open()
app.dos_close_overlay(); pump(0.2)
app._dos_trigger_form(None, None, 2); pump(0.3); assert app._overlay_open(); app.dos_close_overlay()
app.set_dos_mode(False); pump(0.4)
import triggers
raw = triggers.validate_trigger({"name": "t", "enabled": True, "mode": "plain", "pattern": "x*", "priority": 0,
                                 "actions": [{"type": "route", "pane": "OOC", "gag": True}]})
raw = raw[0] if isinstance(raw, tuple) else raw
v = sc.values_from_trigger(raw)
assert v["pane"] == "OOC" and v["pane_gag"] is True
t, _ = sc.trigger_from_values(v)
assert t["actions"] == [{"type": "route", "pane": "OOC", "gag": True}]

# the DOS frame: neighbouring areas share a line, with proper joins
import dosui
g = dosui.box_cells(10, 5, [(0, 0, 10, 5), (5, 0, 10, 5)])
assert g[0] == "╔" + "═" * 4 + "╦" + "═" * 3 + "╗", g[0]
assert g[4] == "╚" + "═" * 4 + "╩" + "═" * 3 + "╝" and g[2][5] == "║"
assert dosui.box_cells(5, 5, [(0, 0, 1, 1), "junk", (3, 3, 99, 99)])[0] == " " * 5
assert dosui.box_cells(-3, "x", None) == []
app.set_dos_mode(True); pump(0.5)
app._panes_save(["top 4 OOC", "right 36 Tells"]); pump(0.5)
assert app._framecv is not None and app._framecv.winfo_ismapped()
mx, my, mw, mh = app._pane_geom["main"]
cwid = app.f_norm.measure("0")
assert mw // cwid >= 80, (mw, cwid)
assert app.dosbar.top.winfo_ismapped() and app.dosbar.top.winfo_y() < app._holder.winfo_y()
app.set_dos_mode(False); pump(0.4)

# removing every pane restores the plain arrangement
for d in list(app.cfg["panes"]):
    app.pane_delete(d["name"])
app.cfg["layout"] = {"regions": [], "min_main_cols": 80}
app.layout_panes(); pump(0.2)
assert not app._panes_active

root.update(); root.destroy()
print("pane tests OK")
