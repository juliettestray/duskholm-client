"""Regression tests for the polish batch: skin switch re-fit, readable DOS colours, scrollbar in the border."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import duskholm_client as dc
import tkinter as tk

tmp = tempfile.mkdtemp()
SETTINGS = os.path.join(tmp, "settings.json")
dc.SETTINGS_PATH = SETTINGS
dc.user_skin_dir = lambda: os.path.join(tmp, "skins")
with open(SETTINGS, "w") as f:
    json.dump({"ui_mode": "dos"}, f)

root = tk.Tk()
app = dc.App(root)
root.geometry("1200x760+20+20")


def pump(secs=0.3):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)


def border_cells():
    return (app._holder.winfo_width() - app._mid.winfo_width()) / 2.0 / app.f_norm.measure("0")


pump(0.8)
assert app.dos

# ---------------- switching skin (and so font) re-fits the DOS screen immediately ------------------------
for name in list(dc.BUILTIN_SKINS) * 2:
    app.set_skin(name)
    pump(0.06)                                   # NOT long enough for any debounced window event
    b = border_cells()
    assert 0.5 <= b <= 2.0, (name, "border straight after the switch", b, app.font_family)
    assert app.out.winfo_width() <= app._holder.winfo_width() + 1, (name, "text must never overflow the window")

# choosing a font by hand re-fits as well
mono = app.mono_families()
for fam in mono[:6]:
    app.apply_font(fam)
    pump(0.06)
    assert 0.5 <= border_cells() <= 2.0, (fam, border_cells())
app.apply_font(use_skin_font=True)
app.set_skin("Retro DOS"); pump(0.3)


# ---------------- DOS colours are readable on every skin, and for hostile user skins --------------------
def readable(c):
    bgs = (c["dos_bar_bg"], c["dos_bar2_bg"], c["dos_menu_bg"])
    worst_key = min(dc.contrast_ratio(c["dos_key_fg"], b) for b in bgs)
    return {
        "bar text": dc.contrast_ratio(c["dos_bar_fg"], c["dos_bar_bg"]),
        "status text": dc.contrast_ratio(c["dos_bar2_fg"], c["dos_bar2_bg"]),
        "menu text": dc.contrast_ratio(c["dos_menu_fg"], c["dos_menu_bg"]),
        "selection": dc.contrast_ratio(c["dos_menu_sel_fg"], c["dos_menu_sel_bg"]),
        "hotkeys (worst bg)": worst_key,
    }


for name in dc.BUILTIN_SKINS:
    app.set_skin(name)
    for what, ratio in readable(app._dc()).items():
        assert ratio >= 4.4, (name, what, round(ratio, 2))
# the skin data itself (before the safety net) already reads well on the two skins reported as bad
for name in ("Plain", "Plain Light", "Retro Phosphor"):
    th = dc.BUILTIN_SKINS[name]
    assert dc.contrast_ratio(th["dos_key_fg"], th["dos_bar_bg"]) >= 4.4, (name, "hotkeys on the hint bar")
# a skin whose key colour equals its bar colour is rescued by the guard
bad = dict(dc.BUILTIN_SKINS["Plain"], name="Bad Skin", dos_key_fg="#2a2d35", dos_bar_fg="#2b2e36",
           dos_menu_fg="#1a1c22")
app.skins["Bad Skin"] = dc.validate_theme(bad)
app.set_skin("Bad Skin")
for what, ratio in readable(app._dc()).items():
    assert ratio >= 4.4, ("hostile skin", what, round(ratio, 2))
app.set_skin("Retro DOS")

# ---------------- the scrollbar replaces the right border cell, only when there is something to scroll ---
app.clear()
app._append([("short\n", None)]); pump(0.3)
assert not app._dosscroll.winfo_ismapped(), "nothing to scroll: plain border"
for i in range(300):
    app._append([("line %d\n" % i, None)])
pump(0.4)
sb = app._dosscroll
assert sb.winfo_ismapped(), "long scrollback: the scrollbar appears"
right = app._holder.winfo_width()
assert sb.winfo_x() + sb.winfo_width() == right, "it sits at the very right edge (inside the border)"
assert sb.winfo_x() >= app._mid.winfo_x() + app._mid.winfo_width() - 1, "and does not overlap the text"
assert sb.winfo_height() == app._holder.winfo_height()
app.clear(); pump(0.3)
assert not sb.winfo_ismapped(), "back to a plain border when everything fits"
# the normal look uses the ordinary scrollbar and never shows the DOS one
for i in range(300):
    app._append([("line %d\n" % i, None)])
app.set_dos_mode(False); pump(0.4)
assert not sb.winfo_ismapped() and app._sb.winfo_ismapped()
app.set_dos_mode(True); pump(0.4)
assert sb.winfo_ismapped(), "and returns with the DOS look"

# an open menu / dialog / table follows font changes (resizing the window re-fits the font)
root.geometry("700x500+20+20"); pump(0.6)
for opener in (app.dos_worlds, app.dos_main_menu, app.dos_palette_menu):
    opener(); pump(0.25); o = app._overlay
    root.geometry("1500x900+20+20"); pump(0.8)
    assert o.lh == app.f_norm.metrics("linespace") and o.cw == app.f_norm.measure("0"), (opener.__name__, o.cw, o.lh)
    app.dos_close_overlay(); root.geometry("700x500+20+20"); pump(0.5)

root.update(); root.destroy()
print("polish tests OK")
