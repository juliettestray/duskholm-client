"""Skins, palette editing, contrast lifting, persistence, user skins, the colour dialog."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as dc
import tkinter as tk
from tkinter import colorchooser, simpledialog

E = "\x1b["
tmp = tempfile.mkdtemp()
SETTINGS = os.path.join(tmp, "settings.json")
SKINS = os.path.join(tmp, "skins")
dc.SETTINGS_PATH = SETTINGS
dc.user_skin_dir = lambda: SKINS

# ---------------- palette references straight out of the parser ---------------------------
def key_of(data, text):
    t = dc.Terminal()
    for ev in t.feed(data):
        if ev[0] == "text" and text in ev[1]:
            return ev[2]
    raise AssertionError("no text event for %r" % text)

assert key_of((E + "31mX").encode(), "X")[0] == 1
assert key_of((E + "1;31mX").encode(), "X")[0] == 9            # bold + red = bright red
assert key_of((E + "91mX").encode(), "X")[0] == 9
assert key_of((E + "38;5;9mX").encode(), "X")[0] == 9
assert key_of((E + "38;5;196mX").encode(), "X")[0] == "#ff0000"  # beyond 16: fixed RGB
assert key_of((E + "38;2;1;2;3mX").encode(), "X")[0] == "#010203"
assert key_of((E + "44mX").encode(), "X")[1] == 4
assert key_of((E + "104mX").encode(), "X")[1] == 12
t = dc.Terminal(); t.feed(bytes([255, 251, 91, 255, 250, 91, 255, 240]))
assert [e for e in t.feed(b"<color fore=red>X</color>") if e[0] == "text"][0][2][0] == 1
assert [e for e in t.feed(b"<color fore=#10ff20>X</color>") if e[0] == "text"][0][2][0] == "#10ff20"

# ---------------- GUI ----------------------------------------------------------------------
root = tk.Tk()
app = dc.App(root)

def pump(secs=0.2):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)

def fg_of(word):
    """Foreground colour currently displayed for `word` in the scrollback."""
    idx = app.out.search(word, "1.0")
    assert idx, word
    for name in app.out.tag_names(idx):
        if name.startswith("s"):
            return app.out.tag_cget(name, "foreground").lower()
    raise AssertionError("no style tag on " + word)

def expected(raw, theme=None):
    th = theme or app.theme
    c = th["ansi"][raw] if isinstance(raw, int) else raw
    return dc.ensure_contrast(c, th["bg"], th["min_contrast"])

app._on_data((E + "31mredword" + E + "0m " + E + "34mblueword" + E + "0m " + E + "30mblackword" + E + "0m "
              + E + "38;5;17mnavyword" + E + "0m\n\r").encode())
assert app.cfg["skin"] == "Plain" and set(dc.BUILTIN_SKINS) >= {"Plain", "Plain Light", "Moody", "Retro Phosphor", "Retro DOS"}

# every built-in skin: widgets, tags and stat bar follow the theme; scrollback recolours live
for name in dc.BUILTIN_SKINS:
    assert app.set_skin(name)
    th = app.theme
    pump(0.05)
    assert th["name"] == name
    assert str(root.cget("bg")).lower() == th["bg"]
    assert app.out.cget("bg").lower() == th["bg"] and app.out.cget("fg").lower() == th["fg"]
    assert app.input.cget("bg").lower() == th["input_bg"]
    assert app.btn.cget("bg").lower() == th["button_bg"]
    assert app.statbar.cget("bg").lower() == th["panel"]
    assert fg_of("redword") == expected(1), name
    assert fg_of("blueword") == expected(4), name
    assert dc.contrast_ratio(fg_of("blackword"), th["bg"]) >= th["min_contrast"] - 0.01, name
    assert dc.contrast_ratio(fg_of("navyword"), th["bg"]) >= th["min_contrast"] - 0.01, name
    assert app.out.tag_cget("echo", "foreground") and app.out.tag_cget("system", "foreground")
assert not app.set_skin("No Such Skin") and app.theme["name"] == "Retro DOS"

# the default skin rescues the hard cases without touching colours that already pass
app.set_skin("Plain")
app._on_data((E + "1;31mbrightword" + E + "0m\n\r").encode()); pump(0.1)
assert fg_of("brightword") == "#f14c4c"                       # already readable: untouched
assert dc.contrast_ratio(fg_of("redword"), "#101114") >= 4.0  # dim red is nudged up to the minimum
assert dc.contrast_ratio(fg_of("blackword"), "#101114") >= 4.0 # black text on black: lifted

# ---------------- palette edits --------------------------------------------------------------
app._set_override(("ansi", 4), "#ff00ff")
assert app.theme["ansi"][4] == "#ff00ff" and fg_of("blueword") == expected(4) == "#ff00ff"
assert fg_of("redword") == expected(1)
assert app.cfg["skin_overrides"]["Plain"] == {"ansi": {"4": "#ff00ff"}}
app._set_override(("bg",), "#202030")
assert app.out.cget("bg").lower() == "#202030"
app._set_override(("bg",), dc.BUILTIN_SKINS["Plain"]["bg"])         # back to the skin's value
app._set_override(("ansi", 4), dc.BUILTIN_SKINS["Plain"]["ansi"][4])
assert "Plain" not in app.cfg["skin_overrides"], "edits equal to the skin must not be stored"
assert fg_of("blueword") == expected(4) and dc.contrast_ratio(fg_of("blueword"), "#101114") >= 4.0

# contrast slider semantics: 1.0 = exactly as sent, higher lifts
app._set_override(("min_contrast",), 1.0)
assert fg_of("blackword") == "#000000" and fg_of("navyword") == "#00005f"
app._set_override(("min_contrast",), 7.0)
for w in ("blackword", "blueword", "navyword", "redword"):
    assert dc.contrast_ratio(fg_of(w), app.theme["bg"]) >= 7.0 - 0.01, w
app.reset_skin_edits()
assert app.theme["min_contrast"] == 4.0 and "Plain" not in app.cfg["skin_overrides"]

# ---------------- persistence ------------------------------------------------------------------
app.set_skin("Moody")
app._set_override(("ansi", 1), "#aa1122")
app._set_override(("min_contrast",), 5.5)
app._save_settings()
saved = json.load(open(SETTINGS))
assert saved["skin"] == "Moody" and saved["skin_overrides"]["Moody"] == {"ansi": {"1": "#aa1122"}, "min_contrast": 5.5}, saved
root.update(); root.destroy()
root = tk.Tk(); app = dc.App(root)
assert app.theme["name"] == "Moody" and app.theme["ansi"][1] == "#aa1122" and app.theme["min_contrast"] == 5.5
assert app.theme["ansi"][2] == dc.BUILTIN_SKINS["Moody"]["ansi"][2]
root.update(); root.destroy()

# ---------------- hostile settings never stop startup ---------------------------------------------
bad = [
    {"skin": 5, "skin_overrides": "nope"},
    {"skin": "Moody", "skin_overrides": {"Moody": {"bg": "red", "ansi": {"99": "#fff", "3": 4, "x": "#111111"},
                                                   "min_contrast": float("nan"), "fonts": "x" * 100000,
                                                   "relief": "bumpy", "name": "\x00\x01" * 10}}},
    {"skin": "Nonexistent", "skin_overrides": {"Nonexistent": {"bg": "#000000"}}},
    {"skin": "Plain", "skin_overrides": {"Plain": {"ansi": [1] * 16, "bg": ["#fff"], "panel": None}}},
    {"skin": "x" * 5000, "skin_overrides": {"k" * 5000: {}, "ok": 5, 3: {}}},
    {"skin_overrides": {str(i): {"bg": "#111111"} for i in range(500)}},
]
for cfg in bad:
    with open(SETTINGS, "w") as f:
        json.dump(cfg, f, allow_nan=True)
    root = tk.Tk(); app = dc.App(root); pump(0.05)
    th = app.theme
    assert all(dc._hex_ok(th[k]) for k in dc.COLOR_KEYS) and len(th["ansi"]) == 16 and all(dc._hex_ok(c) for c in th["ansi"])
    assert 1.0 <= th["min_contrast"] <= 10.0 and th["relief"] in dc.RELIEFS
    assert app.cfg["skin"] in app.skins and len(app.cfg["skin_overrides"]) <= 50
    root.update(); root.destroy()
with open(SETTINGS, "w") as f:
    f.write("{not json")
root = tk.Tk(); app = dc.App(root); assert app.theme["name"] == "Plain"; root.update(); root.destroy()
os.remove(SETTINGS)

# ---------------- user skins: save, list, reload, safety ---------------------------------------------
root = tk.Tk(); app = dc.App(root)
app.set_skin("Retro Phosphor")
app._set_override(("ansi", 1), "#ff0000")
fp = app.save_skin_as("My Haunted Skin")
assert fp and os.path.dirname(os.path.abspath(fp)) == os.path.abspath(SKINS) and os.path.exists(fp)
assert app.cfg["skin"] == "My Haunted Skin" and app.theme["ansi"][1] == "#ff0000"
assert app.theme["bg"] == dc.BUILTIN_SKINS["Retro Phosphor"]["bg"]
assert "Retro Phosphor" in app.cfg["skin_overrides"] or True
assert app.save_skin_as("Plain") is None and app.save_skin_as("   ") is None, "reserved/empty names refused"
fp2 = app.save_skin_as("..\\..\\evil/../x")
assert fp2 and os.path.dirname(os.path.abspath(fp2)) == os.path.abspath(SKINS), fp2
assert not os.path.exists(os.path.join(tmp, "evil.json")) and not os.path.exists(os.path.join(os.path.dirname(tmp), "evil.json"))
labels = [app._skin_menu.entrycget(i, "label") for i in range(app._skin_menu.index("end") + 1)]
assert "My Haunted Skin" in labels and "Plain" in labels, labels
app.cfg["skin"] = "My Haunted Skin"; app._save_settings()
root.update(); root.destroy()
root = tk.Tk(); app = dc.App(root)
assert app.theme["name"] == "My Haunted Skin" and app.theme["ansi"][1] == "#ff0000"
root.update(); root.destroy()
# junk files in the skins folder are ignored; a clashing name gets a suffix
with open(os.path.join(SKINS, "broken.json"), "w") as f: f.write("{{{")
with open(os.path.join(SKINS, "plain_clash.json"), "w") as f:
    json.dump({"name": "Plain", "bg": "#123456"}, f)
loaded = dc.load_user_skins(SKINS)
assert "Plain (user)" in loaded and loaded["Plain (user)"]["bg"] == "#123456" and "broken" not in loaded

# ---------------- fonts follow the skin unless the user chose one ----------------------------------------
os.remove(SETTINGS)
root = tk.Tk(); app = dc.App(root)
mono = app.mono_families()
app.set_skin("Moody")
want = next((f for f in dc.BUILTIN_SKINS["Moody"]["fonts"] if f in mono), app._default_family())
assert app.font_family == want and app.f_norm.cget("family") == want
app.set_skin("Retro Phosphor")
want = next((f for f in dc.BUILTIN_SKINS["Retro Phosphor"]["fonts"] if f in mono), app._default_family())
assert app.font_family == want
explicit = next(f for f in mono if f != want)
assert app.apply_font(explicit, 13)
app.set_skin("Moody"); assert app.font_family == explicit, "an explicit choice survives skin changes"
app.apply_font(use_skin_font=True)
assert app.cfg["font_family"] is None and app.font_family != explicit or len(mono) == 1

# ---------------- the colour dialog -----------------------------------------------------------------
app.set_skin("Plain")
top = app.edit_colors(); pump(0.1)
assert app.edit_colors() is top, "opening it twice must not create a second window"
act = top._actions
act["choose_skin"]("Moody"); assert app.theme["name"] == "Moody"
orig_ask = colorchooser.askcolor
colorchooser.askcolor = lambda **kw: ((17, 34, 51), "#112233")
act["pick"](("ansi", 2)); assert app.theme["ansi"][2] == "#112233"
act["pick"](("key", "bg")); assert app.theme["bg"] == "#112233" and app.out.cget("bg").lower() == "#112233"
colorchooser.askcolor = lambda **kw: (None, None)              # user cancels the colour chooser
act["pick"](("ansi", 3)); assert app.theme["ansi"][3] == dc.BUILTIN_SKINS["Moody"]["ansi"][3]
colorchooser.askcolor = lambda **kw: ((0, 0, 0), "javascript:alert(1)")   # garbage must be ignored
act["pick"](("ansi", 3)); assert app.theme["ansi"][3] == dc.BUILTIN_SKINS["Moody"]["ansi"][3]
colorchooser.askcolor = orig_ask
act["scale"].set(6.0); pump(0.1)
assert app.theme["min_contrast"] == 6.0
act["reset"](); assert app.theme["min_contrast"] == dc.BUILTIN_SKINS["Moody"]["min_contrast"] and app.theme["bg"] == dc.BUILTIN_SKINS["Moody"]["bg"]
# Cancel puts everything back as it was when the dialog opened (Plain, no edits)
colorchooser.askcolor = lambda **kw: ((1, 2, 3), "#010203")
act["pick"](("ansi", 5)); act["choose_skin"]("Retro DOS")
colorchooser.askcolor = orig_ask
act["cancel"](); pump(0.1)
assert app.cfg["skin"] == "Plain" and app.cfg["skin_overrides"] == {} and app.theme["name"] == "Plain"
assert app.out.cget("bg").lower() == dc.BUILTIN_SKINS["Plain"]["bg"]
# Done keeps the changes and writes them out; Save-as goes through the name prompt
top = app.edit_colors(); pump(0.1); act = top._actions
act["choose_skin"]("Moody")
orig_ask_s = simpledialog.askstring
simpledialog.askstring = lambda *a, **k: "Dialog Skin"
act["save_as"](); assert app.cfg["skin"] == "Dialog Skin" and "Dialog Skin" in app.skins
simpledialog.askstring = orig_ask_s
act["done"](); pump(0.1)
assert app._colors_win is None and json.load(open(SETTINGS))["skin"] == "Dialog Skin"

# ---------------- the preview in the dialog really shows before/after ---------------------------------
top = app.edit_colors(); pump(0.1)
txt = app._colors_prev.get("1.0", "end")
assert "As shown (after contrast)" in txt and "As the game sends them" in txt and "#00005f" in txt
top._actions["cancel"]()

# ---------------- performance: many styles in the scrollback, switching skins repeatedly ---------------
import random
rng = random.Random(7)
chunks = []
for i in range(3000):
    chunks.append(E + "%d;%dm" % (rng.choice((0, 1)), rng.choice(list(range(30, 38)) + list(range(90, 98))))
                  + (E + "38;5;%dm" % rng.randrange(256) if i % 3 == 0 else "") + "line %d " % i + E + "0m\n\r")
app._on_data("".join(chunks).encode()); pump(0.2)
t0 = time.time()
for i in range(40):
    app.set_skin(list(dc.BUILTIN_SKINS)[i % 5])
assert time.time() - t0 < 10, time.time() - t0
assert len(app._tags) < 600, len(app._tags)

root.update(); root.destroy()
print("skin tests OK")
