"""Find can look in the capture panes too, but only when 'Search panes' is ticked (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1250x720+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def feed(*lines):
    for l in lines:
        app._on_data((l + "\n\r").encode()); pump(0.2)


def hits():
    """Where the highlight is: 'main', a pane name, or None."""
    for w in [("main", app.out)] + [(k, p["text"]) for k, p in app._panes.items()] + \
             [(k + "*", p["popout"]["text"]) for k, p in app._panes.items() if p.get("popout")]:
        if w[1].tag_ranges("findhit"):
            return w[0]
    return None


pump(0.5)
app.connected = True
app.cfg["triggers"] = [{"name": "ooc", "mode": "plain", "pattern": "[OOC]*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "OOC"}]},
                       {"name": "tells", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "Tells"}]}]
feed("You see a lantern.", "[OOC] Bob: 'lantern for sale'", "Goose tells you 'bring a lantern'", "Nothing else.")
assert app._panes["ooc"]["text"].search("lantern", "1.0") and app._panes["tells"]["text"].search("lantern", "1.0")

# off (the default): only the main window is searched, so nothing shows up twice
assert app.find_panes() is False and app.cfg["find_panes"] is False
assert sc.clean_settings({"host": "x", "find_panes": "yes"})["find_panes"] is False
app.find_set_from("bottom"); app.find_set_term("lantern")
seen = []
for _ in range(6):
    assert app.find_next(); seen.append(hits())
assert set(seen) == {"main"}, seen
app._find["pos"] = None
app.find_set_term("Nothing else"); assert app.find_next() and hits() == "main"
app.find_set_term("zzz-not-here"); assert app.find_next() is False and hits() is None

# on: main window first, then each pane, then round again; the notice says where
app.find_set_panes(True); assert app.cfg["find_panes"] is True and app._find["pos"] is None
app.find_set_term("lantern")
order = []
for _ in range(9):
    assert app.find_next(); order.append(hits())
assert order[:6] == ["main", "main", "main", "ooc", "tells", "main"], order
assert "ooc" in order and "tells" in order and order.count("main") >= 3, order
assert order.index("ooc") < order.index("tells"), "panes in the order they were made"
app.find_set_term("bring a"); assert app.find_next() and hits() == "main"
app.find_set_term("for sale"); app.find_next(); app.find_next()
assert hits() in ("ooc", "main")
app.find_set_term("bring a lantern"); n = 0
while hits() != "tells" and n < 5:
    app.find_next(); n += 1
assert hits() == "tells" and "in tells" in app.notice.cget("text"), (hits(), app.notice.cget("text"))
app.find_set_term("zzz-not-here"); assert app.find_next() is False and hits() is None
app.find_clear()
assert not any(p["text"].tag_ranges("findhit") for p in app._panes.values())

# a popped-out pane is searched in its own window
app._local("/popout tells"); pump(0.6)
assert app._popped("tells")
app.find_set_term("bring a lantern")
got = None
for _ in range(4):
    app.find_next()
    if hits() == "tells*":
        got = True; break
assert got, hits()
app._local("/dock tells"); pump(0.5)

# the Find window has the box, and ticking it changes the setting
app.find_set_panes(False)
win = app.open_find(); pump(0.3)
assert win._searchpanes.cget("text") == "Search panes" and win._panes_var.get() is False
win._searchpanes.invoke(); pump(0.1)
assert app.cfg["find_panes"] is True
win._close(); pump(0.2)
app.set_dos_mode(True); pump(0.6)
app.open_find(); pump(0.4)
d = app._overlay
assert [f.get("label") for f in d._fields][-1] == "Search panes"
d.close()
d._on_result("find", {"term": "lantern", "panes": False}); pump(0.4)
assert app.cfg["find_panes"] is False
app.set_dos_mode(False); pump(0.4)
root.destroy()
print("find panes tests OK")
