"""The phone look for a popped-out pane: reading the texts, the iPhone and Android skins, off by default, never in DOS or screen reader mode."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import layout
import phonelook as pl
import sanctuary as sc
import tkinter as tk

# ---- reading the texts (pure)
L = ["[Nov 24 18:31]Mara: are you around later?",
     "[Nov 24 18:33]You > Mara: yes, after eight",
     "[Nov 24 18:34]Mara: a long one that the game wrapped",
     "onto a second line",
     "[Jun  9 12:34]5551234: hello"]
m = pl.parse_messages(L)
assert [(x["who"], x["mine"]) for x in m] == [("Mara", False), ("Mara", True), ("Mara", False), ("5551234", False)]
assert m[2]["text"] == "a long one that the game wrapped onto a second line", m[2]
assert m[1]["text"] == "yes, after eight" and m[1]["when"] == "Nov 24 18:33"
assert pl.parse_messages(["[10:41] [Nov 24 18:31]Mara: with a pane time stamp"])[0]["who"] == "Mara"
n = pl.parse_messages(["It has a symbol of red eyes.", "Out of date but serviceable.", "[Nov 24 18:31]Mara: hi"])
assert [x["note"] for x in n] == [True, True, False], "lines before any text are notes, one each"
assert pl.parse_messages([]) == [] and pl.parse_messages(["", "  "]) == []
assert pl.heading_before(None, m[0]) == "Nov 24 18:31", "the first text gets a time heading"
assert pl.heading_before(m[0], m[1]) == "", "two minutes later: none"
assert pl.heading_before(m[0], {"when": "Nov 24 19:45", "who": "x", "mine": False, "text": "", "note": False}) == "Nov 24 19:45", "an hour of quiet"
assert pl.heading_before(m[0], {"when": "Nov 25 00:01", "who": "x", "mine": False, "text": "", "note": False}) == "Nov 25 00:01", "a new day"
assert pl.stamp_minutes("Nov 24 18:31") is not None and pl.stamp_minutes("junk") is None
for name, sk in pl.SKINS.items():
    for k in ("edge", "bezel", "screen", "head_bg", "head_fg", "sub", "line", "in_bg", "in_fg", "out_bg", "out_fg", "accent", "radius", "hint", "island", "label"):
        assert k in sk, (name, k)
assert pl.SKINS["iphone"]["out_bg"] == "#007aff" and pl.SKINS["iphone"]["island"] and not pl.SKINS["android"]["island"]
# the setting is checked when settings are loaded
assert layout.validate_pane({"name": "Phone", "window": {"phone": "iphone"}})["window"]["phone"] == "iphone"
assert layout.validate_pane({"name": "Phone", "window": {"phone": "android"}})["window"]["phone"] == "android"
for bad in ("windows", "", None, 5, ["iphone"]):
    assert "phone" not in (layout.validate_pane({"name": "Phone", "window": {"phone": bad, "out": True}}).get("window") or {}), bad

# ---- in the app
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x700+20+20")
CR = chr(13) + chr(10)


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def feed(*lines):
    for l in lines:
        app._on_data((l + CR).encode()); pump(0.1)


def bubbles(view):
    cv = view["ph"]["inner"]
    polys = [cv.itemcget(i, "fill") for i in cv.find_all() if cv.type(i) == "polygon"]
    return polys


pump(0.5)
app.connected = True
app.cfg["triggers"] = [{"name": "p", "mode": "regex", "ignore_case": False, "priority": 0, "enabled": True,
                        "pattern": "^\\[[A-Z][a-z]{2} [ 0-9][0-9] [0-9]{2}:[0-9]{2}\\]", "actions": [{"type": "route", "pane": "Phone"}]}]
feed(*L, "[Nov 25 09:02]Mara: booked for 8:30")
assert app.phone_look_of("phone") == "", "off by default"
app._local("/popout phone"); pump(0.8)
v = app._panes["phone"]["popout"]
assert v.get("ph") is None and v["text"].winfo_ismapped(), "a new window is an ordinary text window"
assert v["look_var"].get() == "Normal" and v["look_frame"].winfo_manager() == "pack", "with a Look box in its header"

# ---- iPhone
app._local("/phonelook phone iphone"); pump(0.9)
assert app.phone_look_of("phone") == "iphone" and v.get("ph") is not None
assert not v["text"].winfo_ismapped() and v["ph"]["chrome"].winfo_ismapped(), "the phone replaces the text area"
fills = bubbles(v)
assert len(fills) == 5 and fills.count("#007aff") == 1 and fills.count("#e9e9eb") == 4, fills       # 4 from Mara, 1 yours
assert v["win"].winfo_width() >= pl.MIN_WIDTH - 5 and v["win"].winfo_height() > v["win"].winfo_width(), "it turned upright"
assert v["look_var"].get() == "iPhone"
# the setting is remembered with the pane
assert app._find_pane_def("phone")["window"]["phone"] == "iphone"
# a new text arrives: it is drawn; a burst is one redraw
feed("[Nov 25 09:05]You > Mara: perfect", "[Nov 25 09:06]Mara: see you there"); pump(0.4)
fills = bubbles(v)
assert len(fills) == 7 and fills.count("#007aff") == 2, fills
assert any("see you there" in v["ph"]["inner"].itemcget(i, "text") for i in v["ph"]["inner"].find_all() if v["ph"]["inner"].type(i) == "text")
# resizing keeps the texts (the message area is put back each time the phone is drawn)
v["win"].geometry("640x900"); pump(0.8)
assert len(bubbles(v)) == 7 and v["ph"]["inner"].winfo_ismapped() and v["ph"]["inner"].winfo_width() > 150
cx0 = v["ph"]["inner"].winfo_width()
v["win"].geometry("560x700"); pump(0.8)
assert len(bubbles(v)) == 7 and v["ph"]["inner"].winfo_width() < cx0 + 400

# ---- Android
app._local("/phonelook phone android"); pump(0.9)
fills = bubbles(v)
assert len(fills) == 7 and fills.count("#d3e3fd") == 2 and fills.count("#f1f3f4") == 5, fills
assert v["ph"]["skin"] == "android" and v["look_var"].get() == "Android"
assert v["ph"]["inner"].winfo_ismapped(), "the message area is there after a change of skin"

# ---- clear, and back to normal
app.pane_clear("phone"); pump(0.5)
assert bubbles(v) == []
feed(*L); pump(0.4)
assert len(bubbles(v)) == 4
app._local("/phonelook phone normal"); pump(0.5)
assert v.get("ph") is None and v["text"].winfo_ismapped() and app.phone_look_of("phone") == ""
assert "phone" not in (app._find_pane_def("phone").get("window") or {})

# ---- a window that was a phone is one again after docking and popping out
app._local("/phonelook phone iphone"); pump(0.6)
app._local("/dock phone"); pump(0.5)
assert not app._popped("phone") and app.phone_look_of("phone") == "iphone"
app._local("/popout phone"); pump(0.8)
v = app._panes["phone"]["popout"]
assert v.get("ph") is not None and v["ph"]["skin"] == "iphone"

# ---- never in the DOS look, never in screen reader mode (the setting stays, the text area is shown)
app.set_dos_mode(True); pump(0.8)
assert v.get("ph") is None and v["text"].winfo_ismapped() and app.phone_look_of("phone") == "iphone"
assert v["look_frame"].winfo_manager() == "", "no Look box in the DOS look"
app._local("/phonelook phone android"); pump(0.2)
assert "not the DOS look" in app.out.get("1.0", "end") and app.phone_look_of("phone") == "iphone"
app.set_dos_mode(False); pump(0.8)
assert v.get("ph") is not None and v["look_frame"].winfo_manager() == "pack"
app.cfg["screen_reader"] = True; app._phone_apply_all(); pump(0.4)
assert v.get("ph") is None and v["text"].winfo_ismapped() and v["look_frame"].winfo_manager() == "", "a screen reader gets the text"
app.cfg["screen_reader"] = False; app._phone_apply_all(); pump(0.4)
assert v.get("ph") is not None

# ---- the command
app._local("/phonelook"); pump(0.1)
assert "Say which pane" in app.out.get("1.0", "end")
app._local("/phonelook nosuch iphone"); assert "No pane called 'nosuch'" in app.out.get("1.0", "end")
app._local("/phonelook phone bogus"); assert "iphone and android" in app.out.get("1.0", "end")
assert app.phone_look_of("phone") == "iphone"
app._local("/phonelook phone"); assert "window look: iPhone" in app.out.get("1.0", "end")

# ---- a lot of texts: drawn promptly, and only the newest ones
for i in range(260):
    app._pane_append("phone", [("[Nov 26 10:%02d]Bulk: text number %d" % (i % 60, i), (None, None, False, False, False, False))])
pump(0.6)
assert len(bubbles(v)) == pl.MAX_SHOWN, len(bubbles(v))
t1 = time.time()
v["ph"]["chrome"].event_generate("<Configure>")
app._phone_redraw_messages(v)
assert time.time() - t1 < 2.0, "a full redraw of the newest texts is quick"
root.update(); root.destroy()
print("phone look tests OK")
