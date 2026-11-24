"""The entry box is a whole number of character cells wide, so a line that fills it never loses the end of its last
character (Tk lets text hang a few pixels past the edge before it scrolls) (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1000x500+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def cells():
    e = app.input
    cw = app.f_norm.measure("0")
    return e.winfo_width(), cw


def check(label):
    pump(0.5)
    w, cw = cells()
    assert w % cw == 0 and w >= 8 * cw, "%s: the typing area is %d px wide, a cell is %d px" % (label, w, cw)
    box = app._inbox
    inner = box.winfo_width() - 2 * (int(box.cget("highlightthickness")) + int(box.cget("borderwidth")))
    assert inner - w >= app._IN_LEFT + app._IN_RIGHT, "%s: room is kept at the sides (%d of %d)" % (label, inner - w, inner)
    assert app.input.master is box and str(app.input.cget("borderwidth")) == "0", "the box draws the border"


pump(0.5)
assert app.input.master is app._inbox
check("ordinary look")
# typing: it scrolls as soon as the text is wider than the area, and never before
e = app.input
e.focus_force(); pump(0.3)
w, cw = cells()
k = w // cw
for i in range(k + 6):
    e.event_generate("<KeyPress>", keysym=chr(97 + i % 26)); pump(0.01)
    n = i + 1
    pump(0.05)
    first, last = e.xview()
    if n <= k:
        assert first == 0.0, "n=%d of %d fits exactly: no scrolling (first=%s)" % (n, k, first)
    else:
        assert first > 0.0 and last >= 0.999, "n=%d is past the edge: it scrolled (first=%s last=%s)" % (n, first, last)
e.delete(0, "end")
# other window widths, fonts and looks keep it whole-cell
for geo in ("900x500+20+20", "1133x500+20+20", "777x500+20+20"):
    root.geometry(geo); check("window " + geo)
app._set_font_size(15); check("font size 15")
app._set_font_size(9); check("font size 9")
app._set_font_size(11)
app.set_dos_mode(True); check("DOS look")
root.geometry("1013x500+20+20"); check("DOS look, another width")
e.focus_force(); pump(0.3)
w, cw = cells(); k = w // cw
for i in range(k + 3):
    e.event_generate("<KeyPress>", keysym=chr(97 + i % 26)); pump(0.01)
    n = i + 1
    pump(0.05)
    first, last = e.xview()
    assert (first == 0.0) == (n <= k), "DOS n=%d k=%d first=%s" % (n, k, first)
e.delete(0, "end")
fams = [f for f in app.mono_families()][:2]
if len(fams) > 1:
    app.apply_font(fams[1]); check("another DOS font")
app.set_dos_mode(False); check("back to the ordinary look")
# the focus ring lights up while typing
e.event_generate("<FocusIn>"); pump(0.2)
assert app._inbox.cget("highlightbackground") == app.theme["select"]
e.event_generate("<FocusOut>"); pump(0.2)
assert app._inbox.cget("highlightbackground") == app.theme["panel_edge"]
# the statbar still goes above the box
app._last_prompt = {"hp": (10, 10, "DF")}
app._statbar_show(); pump(0.2)
packed = app.root.tk.call("pack", "slaves", app.root)
assert str(app._inbox) in str(packed)

root.update(); root.destroy()
print("entry fit tests OK")
