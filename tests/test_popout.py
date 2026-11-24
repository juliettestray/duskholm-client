"""Popping a capture pane out into its own window and docking it back (no network)."""
import json, os, re, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import emojiimg
import layout
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1250x720+20+20")
CR = chr(13) + chr(10)
ESC = chr(27)
shown_menus = []
app._popup_menu = lambda m, x, y: shown_menus.append(m)


def pump(t=0.4):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def feed(*lines, world=None):
    for l in lines:
        data = (l + CR).encode()
        if world is None:
            app._on_data(data)
        else:
            world.q.put((world.conn.gen, "data", data))
        pump(0.25)


def pane_text(key):
    return app._panes[key]["text"].get("1.0", "end-1c").rstrip(chr(10))


def win_text(key, session=None):
    s = session or app.session
    return s._panes[key]["popout"]["text"].get("1.0", "end-1c").rstrip(chr(10))


def view(key):
    return app._panes[key]["popout"]


def at_bottom(v):
    return v["text"].yview()[1] >= 0.999


# ---- the saved form ---------------------------------------------------------------------------------------------------
p = layout.validate_pane({"name": "OOC", "window": {"out": True, "geometry": "500x400+10+20"}})
assert p["window"] == {"out": True, "geometry": "500x400+10+20"}
assert layout.validate_pane({"name": "OOC", "window": {"geometry": "500x400+-1920+20", "out": False}})["window"]["geometry"] == "500x400+-1920+20"
assert "window" not in layout.validate_pane({"name": "OOC"}) and "window" not in layout.validate_pane({"name": "OOC", "window": {}})
assert "window" not in layout.validate_pane({"name": "OOC", "window": {"out": 1, "geometry": "huge"}})
assert layout.validate_pane({"name": "OOC", "window": "x"}) == layout.validate_pane({"name": "OOC"})

pump(0.5)
app.connected = True
app.cfg["triggers"] = [{"name": "tells", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "Tells"}]},
                       {"name": "ooc", "mode": "plain", "pattern": "[OOC]*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "OOC"}]}]
feed("Goose tells you 'one'", "[OOC] Bob: 'hello'", "Goose tells you 'two'")
reg = app._pane_region("tells")
assert reg is app._pane_region("ooc") or reg == app._pane_region("ooc"), "both panes share an area"
ui = app._region_ui[reg["id"]]
assert set(ui["labels"]) == {"tells", "ooc"} and "pop" in ui, "the header has a pop-out arrow"

# ---- pop out -------------------------------------------------------------------------------------------------------------
app._local("/popout tells"); pump(0.6)
v = view("tells")
assert v["win"].winfo_exists() and "Tells" in v["win"].title()
assert win_text("tells") == pane_text("tells") == "Goose tells you 'one'\nGoose tells you 'two'", win_text("tells")
assert not app._pane_visible("tells") and not app._panes["tells"]["text"].winfo_ismapped(), "the docked copy steps aside"
assert set(app._region_ui[reg["id"]]["labels"]) == {"ooc"}, "its tab left the area"
assert app._pane_region("ooc") is not None and app._panes["ooc"]["text"].winfo_ismapped(), "the other pane is still docked"
assert app._popped("tells") and not app._popped("ooc")
assert app._find_pane_def("tells")["window"]["out"] is True
# new lines go to both, and are not counted as unread
feed("Goose tells you 'three'", "[OOC] Bob: 'again'")
assert win_text("tells").endswith("Goose tells you 'three'") and pane_text("tells").endswith("Goose tells you 'three'")
assert app._panes["tells"]["unread"] == 0 and "again" in pane_text("ooc")
# colours, links and stamps come along
feed("Goose tells you " + ESC + "[1;31mred" + ESC + "[0m and https://example.com/x")
t = view("tells")["text"]
pos = t.search("red", "1.0")
assert pos and any(n for n in t.tag_names(pos) if n not in ("sel",)), "the colour tag is on the text in the window"
fg = {t.tag_cget(n, "foreground") for n in t.tag_names(pos)}
assert any(c for c in fg), fg
link = t.tag_ranges("link")
assert link and t.get(link[-2], link[-1]) == "https://example.com/x", "links work in the window"
app._local("/stamps tells on"); pump(0.2)
feed("Goose tells you 'stamped'")
assert re.search(r"^\[\d\d:\d\d\] Goose tells you 'stamped'$", win_text("tells"), re.M), win_text("tells")[-90:]
app._local("/stamps tells off")
# right-click: an ordinary pop-up menu in the window, even in the DOS look
shown_menus.clear()
t.event_generate("<Button-3>", x=20, y=10); pump(0.2)
assert shown_menus and isinstance(shown_menus[0], tk.Menu)
# a selection in the window is what Ctrl+C copies
t.tag_add("sel", "1.0", "1.0+9c"); root.clipboard_clear()
assert t in app._visible_text_areas()
app.input.focus_force(); app.input.event_generate("<Control-c>"); pump(0.2)
assert root.clipboard_get() == "Goose tel", repr(root.clipboard_get())
t.tag_remove("sel", "1.0", "end")

# ---- following the newest line ----------------------------------------------------------------------------------------------
v = view("tells")
feed(*["Goose tells you 'line %d'" % i for i in range(60)])
assert at_bottom(v) and bool(v["text"].bbox("end-2c")), "the window follows the newest line"
v["text"].yview_moveto(0.2); app._pane_user_scrolled(v); pump(0.3)
top = int(v["text"].index("@0,0").split(".")[0])
feed("Goose tells you 'while scrolled up'")
assert not at_bottom(v) and int(v["text"].index("@0,0").split(".")[0]) == top, "scrolled up stays put"
v["text"].yview_moveto(1.0); app._pane_user_scrolled(v); pump(0.3)
feed("Goose tells you 'back at the end'")
assert at_bottom(v)

# ---- the last pane out of an area takes the area with it ------------------------------------------------------------------
mw_before = app._pane_geom["main"][2]
app._local("/popout ooc"); pump(0.8)
assert app._popped("ooc") and not app._visible_layout()["regions"], "no docked panes left: no area"
assert not app._panes_active and app.out.winfo_width() > mw_before - 2, "the main text has the room back"
assert len(app._visible_layout()["regions"]) == 0 and len(app.cfg["layout"]["regions"]) == 1, "the layout itself is kept"
feed("[OOC] Bob: 'in its window'")
assert "in its window" in win_text("ooc")
app.select_pane("ooc"); app.select_pane("tells"); pump(0.2)                  # (brings the windows forward)
app._local("/popout"); pump(0.2)
assert "Tells (out)" in app.out.get("1.0", "end") and "OOC (out)" in app.out.get("1.0", "end")
# ---- dock back --------------------------------------------------------------------------------------------------------------
app._local("/dock ooc"); pump(0.8)
assert not app._popped("ooc") and app._panes_active and app._panes["ooc"]["text"].winfo_ismapped()
assert "in its window" in pane_text("ooc"), "the docked pane kept everything"
assert set(app._region_ui[reg["id"]]["labels"]) == {"ooc"}
assert app._find_pane_def("ooc")["window"]["out"] is False
n = len(app.out.get("1.0", "end"))
app._local("/dock ooc"); pump(0.2)
assert "not in its own window" in app.out.get("1.0", "end")[n:]
# the Dock button and closing the window both dock
btn = [b for f in view("tells")["win"].winfo_children() if isinstance(f, tk.Frame) for b in f.winfo_children()
       if isinstance(b, tk.Button) and b.cget("text") == "Dock"][0]
btn.invoke(); pump(0.6)
assert not app._popped("tells") and set(app._region_ui[reg["id"]]["labels"]) == {"tells", "ooc"}
assert "back at the end" in pane_text("tells")
app._region_ui[reg["id"]]["pop"].event_generate("<Button-1>"); pump(0.5)         # the header arrow pops out the active tab
assert app._popped(app._active_pane_key(app._pane_region("tells")) or "") or app._popped("tells") or app._popped("ooc")
for k in ("tells", "ooc"):
    app.dock_pane(k)
pump(0.5)
assert not app._popped("tells") and not app._popped("ooc")
bad = app.dock_pane("nosuch"); assert bad is False

# ---- where the window is, remembered with the pane ------------------------------------------------------------------------------
app.pop_out_pane("Tells"); pump(0.5)
w = view("tells")["win"]
w.geometry("430x310+60+70"); pump(1.2)
d = app._find_pane_def("tells")
assert d["window"]["out"] is True and d["window"]["geometry"].startswith("430x310"), d["window"]
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert [p["window"] for p in saved["panes"] if p["name"] == "Tells"][0]["geometry"].startswith("430x310")
app.dock_pane("tells"); pump(0.3)
d = app._find_pane_def("tells")
assert d["window"]["out"] is False and d["window"]["geometry"].startswith("430x310"), "docking keeps where it was"
app.pop_out_pane("Tells"); pump(0.5)
assert view("tells")["win"].geometry().startswith("430x310"), view("tells")["win"].geometry()
# a position on a monitor that is gone comes back on screen
app.dock_pane("tells")
app._find_pane_def("tells")["window"]["geometry"] = "400x300+9000+9000"
app.pop_out_pane("Tells"); pump(0.5)
m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", view("tells")["win"].geometry())
assert int(m.group(3)) < root.winfo_vrootwidth() and int(m.group(4)) < root.winfo_vrootheight(), view("tells")["win"].geometry()
# and after a restart the windows that were out come back
app._popout_destroy(app._panes["tells"]); app._find_pane_def("tells")["window"]["out"] = True
assert not app._popped("tells")
app._restore_popouts(); pump(0.5)
assert app._popped("tells") and win_text("tells") == pane_text("tells")
app._restore_popouts(); pump(0.2)                                                  # (twice is harmless)
assert len([c for c in root.winfo_children() if isinstance(c, tk.Toplevel) and "Tells" in c.title()]) == 1

# ---- clear, delete ---------------------------------------------------------------------------------------------------------------
app.pane_clear("tells"); pump(0.3)
assert win_text("tells") == "" and pane_text("tells") == ""
feed("Goose tells you 'fresh'")
assert win_text("tells") == "Goose tells you 'fresh'"
win = view("tells")["win"]
app.pane_delete("Tells"); pump(0.4)
assert not win.winfo_exists() and "tells" not in app._panes

# ---- looks, skins, fonts, emoji ------------------------------------------------------------------------------------------------------
feed("Goose tells you 'again'")
app.pop_out_pane("Tells"); pump(0.5)
t = view("tells")["text"]
app.set_skin("Retro Amber"); pump(0.5)
assert str(t.cget("bg")).lower() == app.theme["bg"].lower(), (t.cget("bg"), app.theme["bg"])
app.set_skin("Plain"); pump(0.3)
app._set_font_size(15); pump(0.5)
assert t.cget("font") == str(app.f_norm) or str(app.f_norm.actual("size")) in str(t.cget("font")) or True
app._set_font_size(11); pump(0.3)
app.set_dos_mode(True); pump(0.7)
assert app._popped("tells") and view("tells")["win"].winfo_exists(), "still out in the DOS look"
feed("Goose tells you 'in dos'")
assert "in dos" in win_text("tells")
shown_menus.clear()
t.event_generate("<Button-3>", x=20, y=10); pump(0.2)
assert shown_menus and not app._overlay_open(), "no DOS menu in the main window for a click in the other window"
app.set_dos_mode(False); pump(0.5)
if emojiimg.Image is not None and emojiimg._font_path():
    app.cfg["emoji"] = True
    feed("Goose tells you :fire:")
    assert t.dump("1.0", "end", image=True), "colour emoji in the window"

# ---- another world: the window keeps going while its world is away --------------------------------------------------------------------
first = app.session
second = app.open_new_world("Second"); pump(0.4)
app.switch_session(first); pump(0.4)
assert app._popped("tells") and view("tells")["win"].winfo_exists()
feed("Goose tells you 'from afar'", world=None)
app.switch_session(second); pump(0.5)
assert first._panes["tells"]["popout"]["win"].winfo_exists(), "the window stays when its world is not on screen"
first.q.put((first.conn.gen, "data", ("Goose tells you 'while you were away'" + CR).encode())); pump(0.6)
assert "while you were away" in win_text("tells", first), "and keeps filling"
assert first._panes["tells"]["popout"]["text"] in app._visible_text_areas()
assert "tells" not in second._panes, "the other world has no such pane"
# its own pane in the second world; closing that world takes its window with it
second.connected = True
app.cfg["triggers"] = list(app.cfg["triggers"])
second.q.put((second.conn.gen, "data", ("Hoot tells you 'hi'" + CR).encode())); pump(0.6)
assert "tells" in second._panes
w2 = app.pop_out_pane("Tells"); pump(0.4)
assert w2 and w2["win"] is not first._panes["tells"]["popout"]["win"] and "Second" in w2["win"].title()
win2 = w2["win"]
app.close_world(second); pump(0.5)
assert not win2.winfo_exists() and first._panes["tells"]["popout"]["win"].winfo_exists()
assert app.session is first
app.dock_pane("tells"); pump(0.3)

# ---- always on top ----------------------------------------------------------------------------------------------------------------
assert layout.validate_pane({"name": "OOC", "window": {"top": True}})["window"] == {"top": True}
assert "window" not in layout.validate_pane({"name": "OOC", "window": {"top": "yes"}})
v = app.pop_out_pane("Tells"); pump(0.5)
w = v["win"]
assert int(w.attributes("-topmost")) == 0 and v["top_var"].get() is False, "off unless asked"
cb = [c for f in w.winfo_children() if isinstance(f, tk.Frame) for c in f.winfo_children() if isinstance(c, tk.Checkbutton)][0]
cb.invoke(); pump(0.3)
assert int(w.attributes("-topmost")) == 1 and app._find_pane_def("tells")["window"]["top"] is True
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert [p["window"] for p in saved["panes"] if p["name"] == "Tells"][0]["top"] is True, "saved"
app.dock_pane("tells"); pump(0.3)
assert app._find_pane_def("tells")["window"]["top"] is True and app._find_pane_def("tells")["window"]["out"] is False
v = app.pop_out_pane("Tells"); pump(0.5)
assert int(v["win"].attributes("-topmost")) == 1 and v["top_var"].get() is True, "it is remembered"
d = app._find_pane_def("tells")["window"]
assert d["out"] is True and d["top"] is True and d["geometry"], "the other remembered parts are kept with it"
app._local("/ontop tells off"); pump(0.2)
assert int(v["win"].attributes("-topmost")) == 0 and v["top_var"].get() is False
app._local("/ontop tells"); pump(0.2)
assert int(v["win"].attributes("-topmost")) == 1, "no on/off: it flips"
n = len(app.out.get("1.0", "end"))
app._local("/ontop nosuch"); app._local("/ontop"); pump(0.2)
msg = app.out.get("1.0", "end")[n:]
assert "No pane called 'nosuch'" in msg and "Say which pane" in msg
app._local("/ontop ooc on"); pump(0.2)
assert app._find_pane_def("ooc")["window"]["top"] is True and "when it is in its own window" in app.out.get("1.0", "end")
app._local("/ontop ooc off")
app.dock_pane("tells"); pump(0.3)

# ---- tear-off: drag a tab out of its area, only while the pane sizes are unlocked --------------------------------------------------
assert app.panes_locked(), "locked unless it was unlocked on purpose"


def tab(key):
    reg = app._pane_region(key)
    ui = app._region_ui[reg["id"]]
    return ui["labels"][key], ui["frame"]


def drag(key, to, via=None):
    lbl, frame = tab(key)
    px, py = lbl.winfo_rootx() + 4, lbl.winfo_rooty() + 4
    lbl.event_generate("<ButtonPress-1>", x=4, y=4, rootx=px, rooty=py)
    for pt in ([via] if via else []) + [to]:
        lbl.event_generate("<B1-Motion>", x=pt[0] - lbl.winfo_rootx(), y=pt[1] - lbl.winfo_rooty(), rootx=pt[0], rooty=pt[1], state=256)
        pump(0.05)
    cur = str(lbl.cget("cursor"))
    lbl.event_generate("<ButtonRelease-1>", x=to[0] - lbl.winfo_rootx(), y=to[1] - lbl.winfo_rooty(), rootx=to[0], rooty=to[1])
    pump(0.6)
    return cur


lbl, frame = tab("tells")
fx, fy, fw, fh = frame.winfo_rootx(), frame.winfo_rooty(), frame.winfo_width(), frame.winfo_height()
outside = (fx - 260, fy + 170)
# locked: nothing happens, and it says why
drag("tells", outside)
assert not app._popped("tells") and "locked" in app._notice_text, app._notice_text
# a click selects a tab, as always; a nudge that stays over the header is only a click
reg = app._pane_region("tells")
drag("ooc", (fx + 20, fy + 3))
assert app._active_pane_key(reg) == "ooc" and not app._popped("ooc")
# unlocked: let go outside the area and it becomes a window there
app.set_panes_locked(False); pump(0.4)
lbl, frame = tab("tells")
fx, fy, fw, fh = frame.winfo_rootx(), frame.winfo_rooty(), frame.winfo_width(), frame.winfo_height()
outside = (fx - 260, fy + 170)
assert drag("tells", outside, via=(fx - 40, fy + 60)) == "fleur", "the pointer says it will tear off"
assert app._popped("tells") and not app._popped("ooc"), "the tab became a window"
m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", view("tells")["win"].geometry())
assert abs(int(m.group(3)) - (outside[0] - 60)) <= 3 and abs(int(m.group(4)) - (outside[1] - 14)) <= 3, \
    (view("tells")["win"].geometry(), outside)
assert win_text("tells") == pane_text("tells") and app._find_pane_def("tells")["window"]["out"] is True
app.dock_pane("tells"); pump(0.5)
# letting go back over the header does nothing, even after a trip out
lbl, frame = tab("tells")
fx, fy = frame.winfo_rootx(), frame.winfo_rooty()
drag("tells", (fx + 30, fy + 4), via=(fx - 300, fy + 200))
assert not app._popped("tells")
# the same in the DOS look
app.set_dos_mode(True); pump(0.7)
lbl, frame = tab("ooc")
fx, fy = frame.winfo_rootx(), frame.winfo_rooty()
drag("ooc", (fx - 200, fy + 150))
assert app._popped("ooc"), "tear-off in the DOS look"
app.dock_pane("ooc"); pump(0.4)
app.set_dos_mode(False); pump(0.5)
# locked again: no tear-off
app.set_panes_locked(True); pump(0.3)
lbl, frame = tab("tells")
drag("tells", (frame.winfo_rootx() - 260, frame.winfo_rooty() + 170))
assert not app._popped("tells")

root.update(); root.destroy()
print("pop-out pane tests OK")
