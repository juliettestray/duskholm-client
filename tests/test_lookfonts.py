"""Each look (ordinary and DOS) keeps its own font family, size and line spacing (no network)."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk
import tkinter.font as tkfont

sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")

# ---- settings from a version with one font for both looks: the DOS look starts from it ---------
probe = tk.Tk()
fams = [f for f in ("Consolas", "Courier New", "Lucida Console") if f in set(tkfont.families())]
probe.destroy()
assert len(fams) >= 2, "this test needs two monospace fonts: " + str(fams)
A, B = fams[0], fams[1]
path = os.path.join(tempfile.mkdtemp(), "s.json")
sc.SETTINGS_PATH = path
json.dump({"font_family": A, "line_spacing": 4, "font_size": 12}, open(path, "w"))
c = sc.App.__new__(sc.App)
loaded = sc.App._load_settings(c)
assert loaded["dos_font_family"] == A and loaded["dos_line_spacing"] == 4, "the DOS look inherits it once"
json.dump({"font_family": A, "line_spacing": 4, "dos_font_family": None, "dos_line_spacing": 1}, open(path, "w"))
loaded = sc.App._load_settings(c)
assert loaded["dos_font_family"] is None and loaded["dos_line_spacing"] == 1, "but not again once it has its own"
assert sc.clean_settings({"host": "x", "dos_font_family": 5, "dos_line_spacing": 99})["dos_font_family"] is None
assert sc.clean_settings({"host": "x", "dos_line_spacing": 99})["dos_line_spacing"] == 12
assert sc.clean_settings({"host": "x", "dos_line_spacing": -3})["dos_line_spacing"] == 0
assert sc.clean_settings({"host": "x", "dos_font_family": "  Consolas "})["dos_font_family"] == "Consolas"

# ---- the app ---------------------------------------------------------------------------------
json.dump({"font_family": A, "line_spacing": 4, "font_size": 12, "dos_autofit": False, "dos_font_size": 13}, open(path, "w"))
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x760+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def family():
    return app.f_norm.cget("family")


pump(0.4)
assert not app.dos and family() == A and app._spacing() == 4 and int(app.out.cget("spacing3")) == 4
assert int(app.f_norm.cget("size")) == 12
# change the ordinary look's font, size and spacing
assert app.apply_font(B, 15) and family() == B and int(app.f_norm.cget("size")) == 15
app.apply_spacing(6); assert int(app.out.cget("spacing3")) == 6
assert app.cfg["font_family"] == B and app.cfg["font_size"] == 15 and app.cfg["line_spacing"] == 6
# the DOS look has not moved: it still has what it started with
assert app.cfg["dos_font_family"] == A and app.cfg["dos_line_spacing"] == 4 and app.cfg["dos_font_size"] == 13
app.set_dos_mode(True); pump(0.6)
assert family() == A, "DOS look keeps its own font: " + family()
assert int(app.f_norm.cget("size")) == 13, "and its own size"
assert app._spacing() == 4 and int(app.out.cget("spacing3")) == 4, "and its own line spacing"
# change the DOS look's font and spacing (choosing a font there must not apply the other look's size)
assert app.apply_font(B) and family() == B
assert int(app.f_norm.cget("size")) == 13, "a font chosen in DOS keeps DOS's size, not the ordinary look's 15"
app.apply_font(A); app.apply_spacing(1)
assert app.cfg["dos_font_family"] == A and app.cfg["dos_line_spacing"] == 1 and int(app.out.cget("spacing3")) == 1
assert app.cfg["font_family"] == B and app.cfg["line_spacing"] == 6 and app.cfg["font_size"] == 15, "ordinary look untouched"
# the DOS font menu's "skin font" resets only the DOS look
app.dos_font_skin(); pump(0.3)
assert app.cfg["dos_font_family"] is None and app.cfg["font_family"] == B
app.apply_font(A)
# and back: the ordinary look has what it had
app.set_dos_mode(False); pump(0.6)
assert family() == B and int(app.f_norm.cget("size")) == 15
assert app._spacing() == 6 and int(app.out.cget("spacing3")) == 6
for pane_text in [p["text"] for p in app._panes.values()]:
    assert int(pane_text.cget("spacing3")) == 6
# and in again
app.set_dos_mode(True); pump(0.6)
assert family() == A and int(app.f_norm.cget("size")) == 13 and int(app.out.cget("spacing3")) == 1
# zoom keys change only the look in use
app._zoom(+1); pump(0.2)
assert app.cfg["dos_font_size"] == 14 and app.cfg["font_size"] == 15
app.set_dos_mode(False); pump(0.5)
app._zoom(-1); pump(0.2)
assert app.cfg["font_size"] == 14 and app.cfg["dos_font_size"] == 14 and family() == B
# saved, and read back
saved = json.load(open(path, encoding="utf-8"))
assert saved["font_family"] == B and saved["dos_font_family"] == A and saved["line_spacing"] == 6 and saved["dos_line_spacing"] == 1

root.update(); root.destroy()
print("per-look font tests OK")
