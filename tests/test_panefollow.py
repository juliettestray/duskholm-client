"""A capture pane keeps its newest line in view, including the first time a burst fills it, and stays where you
scrolled it (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")
CR = chr(13) + chr(10)


def pump(t=0.4):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def burst(a, b, world=None):
    data = "".join("Goose tells you 'line %d'%s" % (i, CR) for i in range(a, b)).encode()
    if world is None:
        app._on_data(data)
    else:
        world.q.put((world.conn.gen, "data", data))
    pump(0.6)


def tells():
    return app._panes["tells"]


def at_bottom(p=None):
    return (p or tells())["text"].yview()[1] >= 0.999


def last_line_visible(p=None):
    t = (p or tells())["text"]
    return bool(t.bbox("end-2c"))


pump(0.5)
app.connected = True
app.cfg["triggers"] = [{"name": "t", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "Tells"}]}]

# the first time: one burst, much more than the area holds, into an area that did not exist a moment ago
burst(0, 90)
assert at_bottom() and last_line_visible(), "the first fill follows: " + str(tells()["text"].yview())
assert tells()["follow"] is True
# more lines, in small bursts: still following
for a in range(90, 120, 3):
    burst(a, a + 3)
assert at_bottom() and last_line_visible()

# scrolled up: new lines do not drag it back
tells()["text"].yview_moveto(0.3); app._pane_user_scrolled(tells()); pump(0.3)   # as the wheel or scrollbar would
def top_line():
    return int(tells()["text"].index("@0,0").split(".")[0])


top_before = top_line()
burst(120, 130)
assert not at_bottom() and top_line() == top_before, "stays where you left it: %d -> %d" % (top_before, top_line())
assert tells()["follow"] is False
# a re-layout (window size) does not drag it either
root.geometry("1100x640+20+20"); pump(0.8)
assert not at_bottom(), "a resize does not yank a scrolled-up area to the bottom"
# back to the bottom: following resumes
tells()["text"].yview_moveto(1.0); app._pane_user_scrolled(tells()); pump(0.3)
burst(130, 140)
assert at_bottom() and last_line_visible() and tells()["follow"] is True

# a resize while following keeps the bottom
root.geometry("1200x700+20+20"); pump(0.8)
assert at_bottom() and last_line_visible(), "after a resize: " + str(tells()["text"].yview())
root.geometry("1000x560+20+20"); pump(0.8)
assert at_bottom() and last_line_visible()

# the DOS look, and back
app.set_dos_mode(True); pump(0.9)
assert at_bottom() and last_line_visible(), "after switching to the DOS look: " + str(tells()["text"].yview())
burst(140, 150)
assert at_bottom() and last_line_visible()
app.set_dos_mode(False); pump(0.9)
assert at_bottom() and last_line_visible(), "and back: " + str(tells()["text"].yview())
app._set_font_size(15); pump(0.8)
assert at_bottom() and last_line_visible(), "after a new font size"
app._set_font_size(11); pump(0.6)

# another world's area fills while it is off screen: it is at the bottom when you get there
first = app.session
second = app.open_new_world("Elsewhere"); pump(0.4)
app.switch_session(first); pump(0.4)
burst(0, 90, world=second)
app.switch_session(second); pump(0.9)
p2 = app._panes["tells"]
assert at_bottom(p2) and last_line_visible(p2), "a world's area filled in the background: " + str(p2["text"].yview())
app.switch_session(first); pump(0.5)
assert at_bottom() and last_line_visible()

root.update(); root.destroy()
print("pane follow tests OK")
