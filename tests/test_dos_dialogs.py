"""DOS-style Colours and Font screens, wired into the client (needs dosui's swatch menus + colour picker)."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import duskholm_client as dc
import dosui
import tkinter as tk

tmp = tempfile.mkdtemp()
SETTINGS = os.path.join(tmp, "settings.json")
SKINS = os.path.join(tmp, "skins")
dc.SETTINGS_PATH = SETTINGS
dc.user_skin_dir = lambda: SKINS
with open(SETTINGS, "w") as f:
    json.dump({"ui_mode": "dos", "skin": "Plain Light", "dos_skin": "Moody", "font_size": 13}, f)

root = tk.Tk()
root.geometry("1000x700+30+30")
app = dc.App(root)


def pump(secs=0.25):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)


def key(w, keysym, **kw):
    w = getattr(w, "_cv", w)
    w.focus_force(); root.update()
    w.event_generate("<Key>", keysym=keysym, **kw); pump(0.15)


def overlay():
    return app._overlay if app._overlay_open() else None


def settle():
    pump(0.35)       # lets a "reopen" run after the previous overlay closed


pump(0.5)
assert app.dos and app.theme["name"] == "Moody" and app.cfg["skin"] == "Plain Light"
base_moody = dc.BUILTIN_SKINS["Moody"]

# ---------------- colours: menu tree ---------------------------------------------------------------------
key(app.input, "F6")
m = overlay(); assert isinstance(m, dosui.DosMenu), "F6 opens the DOS colours menu"
key(m, "F6"); assert overlay() is m, "no stacking"
assert app._colors_snapshot is not None
key(m, "v"); assert overlay() is m, "Revert is disabled until something changed"

# game palette -> pick Red -> change live -> Escape restores
key(m, "p"); pal = overlay(); assert isinstance(pal, dosui.DosMenu) and pal is not m
before = app.theme["ansi"][1]
key(pal, "1"); pk = overlay()
assert isinstance(pk, dosui.DosColorPicker) and pk.value() == before
pk.set_value("#123456"); pump(0.2)
assert app.theme["ansi"][1] == "#123456", "colour applies live while the picker is open"
key(pk, "Escape"); settle()
assert app.theme["ansi"][1] == before, "Cancel restores the original colour"
assert isinstance(overlay(), dosui.DosMenu), "palette menu reopens after the picker"
# again, this time keep it with Enter
pal = overlay(); key(pal, "1"); pk = overlay()
pk.set_value("#abcdef"); key(pk, "Return"); settle()
assert app.theme["ansi"][1] == "#abcdef"
assert app.cfg["skin_overrides"]["Moody"]["ansi"]["1"] == "#abcdef"
assert json.load(open(SETTINGS))["skin_overrides"]["Moody"]["ansi"]["1"] == "#abcdef", "saved immediately"
pal = overlay(); assert isinstance(pal, dosui.DosMenu)
# keyboard nudges in the picker change the colour by 1 (Right on the focused R channel)
key(pal, "1"); pk = overlay(); r0 = int(pk.value()[1:3], 16)
key(pk, "Right"); assert int(pk.value()[1:3], 16) == min(255, r0 + 1) and app.theme["ansi"][1] == pk.value()
key(pk, "Escape"); settle()
assert app.theme["ansi"][1] == "#abcdef"
key(overlay(), "Escape"); settle()                  # Esc steps back to the colours menu
back = overlay(); assert isinstance(back, dosui.DosMenu) and back is not pal, "Esc steps back one level"
m = back

# revert, then interface colours and DOS screen colours
key(m, "v")                                       # enabled now: there are changes
settle()
m = overlay(); assert isinstance(m, dosui.DosMenu) and app.theme["ansi"][1] == base_moody["ansi"][1], "Revert undoes edits"
key(m, "i"); ui = overlay(); key(ui, "1"); pk = overlay()
assert isinstance(pk, dosui.DosColorPicker) and pk.value() == app.theme["bg"]
pk.set_value("#202040"); key(pk, "Return"); settle()
assert app.theme["bg"] == "#202040" and app.out.cget("bg").lower() == "#202040"
key(overlay(), "Escape"); settle(); m = overlay()                 # back to the colours menu
assert isinstance(m, dosui.DosMenu)
key(m, "d"); dm = overlay(); key(dm, "1"); pk = overlay()
assert isinstance(pk, dosui.DosColorPicker)
pk.set_value("#ff00ff"); key(pk, "Return"); settle()
assert app.theme["dos_bar_bg"] == "#ff00ff"
key(overlay(), "Escape"); settle(); m = overlay()                 # back to the colours menu
assert isinstance(m, dosui.DosMenu)

# minimum contrast
key(m, "c"); d = overlay(); assert isinstance(d, dosui.DosDialog)
ent = {f["key"]: f for f in d._fields}["v"]["entry"]
ent.delete(0, "end"); ent.insert(0, "6.5"); key(ent, "Return"); settle()
assert app.theme["min_contrast"] == 6.5
assert isinstance(overlay(), dosui.DosMenu), "back to the colours menu"
key(overlay(), "c"); d = overlay(); ent = {f["key"]: f for f in d._fields}["v"]["entry"]
ent.delete(0, "end"); ent.insert(0, "abc"); key(ent, "Return"); settle()
assert app.theme["min_contrast"] == 6.5 and "from 1.0 to 7.0" in app.out.get("1.0", "end-1c")
key(overlay(), "c"); d = overlay(); ent = {f["key"]: f for f in d._fields}["v"]["entry"]
ent.delete(0, "end"); ent.insert(0, "99"); key(ent, "Return"); settle()
assert app.theme["min_contrast"] == 7.0, "clamped to the slider range"
key(overlay(), "c"); d = overlay(); ent = {f["key"]: f for f in d._fields}["v"]["entry"]
ent.delete(0, "end"); ent.insert(0, "0"); key(ent, "Return"); settle()
assert app.theme["min_contrast"] == 1.0
key(overlay(), "c"); key(overlay(), "Escape"); settle()          # Cancel leaves it unchanged
assert app.theme["min_contrast"] == 1.0

# reset, save as, skin switch chain
key(overlay(), "r"); settle()
assert app.cfg["skin_overrides"].get("Moody") is None and app.theme["bg"] == base_moody["bg"]
key(overlay(), "a"); d = overlay(); assert isinstance(d, dosui.DosDialog)
ent = {f["key"]: f for f in d._fields}["name"]["entry"]
ent.delete(0, "end"); ent.insert(0, "DOS Test Skin"); key(ent, "Return"); settle()
assert app.cfg["dos_skin"] == "DOS Test Skin" and os.path.exists(os.path.join(SKINS, "DOS Test Skin.json"))
assert app.cfg["skin"] == "Plain Light", "the normal look's skin is untouched"
key(overlay(), "s"); sk = overlay(); assert isinstance(sk, dosui.DosMenu)
key(sk, "1"); settle()
assert app.cfg["dos_skin"] == list(app.skins)[0]
assert isinstance(overlay(), dosui.DosMenu), "colours menu reopens after choosing a skin"
key(overlay(), "Escape"); assert overlay() is None

# ---------------- font ----------------------------------------------------------------------------------------
mono = app.mono_families()
key(app.input, "F7"); fm = overlay(); assert isinstance(fm, dosui.DosMenu), "F7 opens the DOS font menu"
selected = fm.selected
assert selected >= 3, "opens with the current font pre-selected, below the 3 header rows"
key(fm, "z"); d = overlay(); assert isinstance(d, dosui.DosDialog)
ent = {f["key"]: f for f in d._fields}["size"]["entry"]
ent.delete(0, "end"); ent.insert(0, "20"); key(ent, "Return"); pump(0.3)
assert int(app.f_norm.cget("size")) == 20 and app.cfg["dos_autofit"] is False and app.cfg["dos_font_size"] == 20
assert app.cfg["font_size"] == 13, "the normal look's size is untouched"
key(app.input, "F7"); key(overlay(), "z"); d = overlay(); ent = {f["key"]: f for f in d._fields}["size"]["entry"]
ent.delete(0, "end"); ent.insert(0, "x"); key(ent, "Return"); pump(0.3)
assert int(app.f_norm.cget("size")) == 20 and "whole number" in app.out.get("1.0", "end-1c")
key(app.input, "F7"); key(overlay(), "z"); d = overlay(); ent = {f["key"]: f for f in d._fields}["size"]["entry"]
ent.delete(0, "end"); ent.insert(0, "999"); key(ent, "Return"); pump(0.3)
assert int(app.f_norm.cget("size")) == dc.MAX_FONT
key(app.input, "F7"); key(overlay(), "z"); d = overlay(); ent = {f["key"]: f for f in d._fields}["size"]["entry"]
ent.delete(0, "end"); ent.insert(0, "2"); key(ent, "Return"); pump(0.3)
assert int(app.f_norm.cget("size")) == dc.MIN_FONT
app.cfg["dos_font_size"] = 17; app._set_font_size(17)
# the normal look keeps its own size; the DOS size comes back with the DOS look
app.set_dos_mode(False); pump(0.3)
assert int(app.f_norm.cget("size")) == 13
app.set_dos_mode(True); pump(0.4)
assert int(app.f_norm.cget("size")) == 17 and app.cfg["dos_autofit"] is False
# zoom keys in the DOS look change the DOS size only
app._zoom(+1); assert int(app.f_norm.cget("size")) == 18 and app.cfg["dos_font_size"] == 18 and app.cfg["font_size"] == 13

# choosing a family from the list (Down + Enter), and "use the skin's font"
if len(mono) > 1:
    key(app.input, "F7"); fm = overlay()
    key(fm, "Down"); key(fm, "Return"); pump(0.3)
    assert app.cfg["font_family"] in mono and app.font_family == app.cfg["font_family"]
key(app.input, "F7"); key(overlay(), "k"); pump(0.3)
assert app.cfg["font_family"] is None
key(app.input, "F7"); assert overlay() is not None; key(overlay(), "Escape"); assert overlay() is None

# ---------------- the normal look still gets the ordinary dialogs ------------------------------------------------
app.set_dos_mode(False); pump(0.3)
top = app.edit_colors(); assert isinstance(top, tk.Toplevel); top._actions["cancel"](); pump(0.1)
f = app.choose_font(); assert isinstance(f, tk.Toplevel); f.destroy(); pump(0.1)
# an ordinary colours dialog left open is closed when switching to the DOS look
top = app.edit_colors(); pump(0.2)
app.set_dos_mode(True); pump(0.4)
assert app._colors_win is None and not top.winfo_exists()

root.update(); root.destroy()
print("dos dialogs tests OK")
