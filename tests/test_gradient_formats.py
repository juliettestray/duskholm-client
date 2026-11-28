"""The gradient maker's other colour formats: what each writes, escaping, and switching in both looks (no network)."""
import json, os, re, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import colortools as ct
import sanctuary as sc
import dosgrad, dosui
import tkinter as tk

two = [196, 21]


def made(text, fmt, mode="word", stops=two, smooth=True):
    return ct.build(text, stops, mode, smooth, fmt, seed=1)[0]


# ---- what each one writes ---------------------------------------------------------------------------------------------------------------
assert made("ab cd", "duskholm") == ct.apply("ab cd", two, "word") == "`196ab `021cd`x"
assert made("ab cd", "mush") == "[ansi(<#FF0000>,ab)] [ansi(<#0000FF>,cd)]"
assert made("ab cd", "muxsub") == "%x<#FF0000>ab %x<#0000FF>cd%xn"
assert made("ab cd", "evennia") == "|#ff0000ab |#0000ffcd|n"
assert made("ab cd", "aardwolf") == "@x196ab @x021cd@w"
assert made("ab cd", "bbcode") == "[color=#FF0000]ab[/color] [color=#0000FF]cd[/color]"
assert made("ab cd", "html") == '<span style="color:#ff0000">ab</span> <span style="color:#0000ff">cd</span>'
assert made("one two", "mush", stops=[196]) == "[ansi(<#FF0000>,one two)]", "one colour across a space is one run"
# characters each game would read as its own
assert made("a,(b)[c]{d}%;\\", "mush", stops=[196]) == "[ansi(<#FF0000>,a\\,\\(b\\)\\[c\\]\\{d\\}\\%\;\\\\)]"
assert made("  a   b ", "mush", stops=[196]) == "%b%b[ansi(<#FF0000>,a %b%bb)]%b"
assert made("a\tb", "mush", stops=[196]) == "[ansi(<#FF0000>,a%tb)]"
assert made("a\nb", "mush", "line") == "[ansi(<#FF0000>,a)]%r[ansi(<#0000FF>,b)]"
assert made("a|b", "evennia", stops=[196]) == "|#ff0000a||b|n"
assert made("a@b", "aardwolf", stops=[196]) == "@x196a@@b@w"
assert made("<a&>", "html", stops=[196]) == '<span style="color:#ff0000">&lt;a&amp;&gt;</span>'
assert made("a\nb", "html", "line").count("<br>\n") == 1
for f in ct.FORMATS:
    assert made("", f) == "" and made("   ", f).strip("%b ") == "", f
# hex formats blend in true colour; the 256-colour ones round to the palette
hexes = re.findall(r"<#([0-9A-F]{6})>", made("abcdefghij", "mush", "stretch"))
assert len(set(hexes)) == 10 and any("#" + h.lower() not in ct.XTERM for h in hexes), hexes
assert all(int(n) < 256 for n in re.findall(r"@x(\d{3})", made("abcdefghij", "aardwolf", "stretch")))
assert re.findall(r"<#([0-9A-F]{6})>", made("abcd", "mush", "stretch", smooth=False)) == ["FF0000", "0000FF"]
# the look matches the codes, also when the colours are random
for f in ct.FORMATS:
    out, look = ct.build("abcdefgh", [196, 21, 46], "random", True, f)
    assert "".join(t for t, _c in look) == "abcdefgh", (f, look)
    cols = [c for _t, c in look]
    if f == "mush":
        assert [c.upper() for c in cols] == re.findall(r"<(#[0-9A-F]{6})>", out)
    if f in ("duskholm", "aardwolf"):
        assert cols == [ct.XTERM[int(n)] for n in re.findall(r"(?:`|@x)(\d{3})", out)], (f, out, cols)
# limits: games take about 6000 characters; web formats may be longer
try:
    made("x" * 600, "mush", "stretch", [196, 46, 21])
    raise AssertionError("too long was allowed")
except ValueError as e:
    assert "by word or line" in str(e)
assert len(made("x" * 600, "bbcode", "stretch", [196, 46, 21])) > ct.MAX_OUT
try:
    made("a", "nope")
    raise AssertionError("unknown format was allowed")
except ValueError:
    pass
assert ct.format_key("mux / pennmush ANSI()") == "mush" and ct.format_key("HTML") == "html" and ct.format_key("x") is None
assert sc.clean_settings({"gradient_format": 7})["gradient_format"] == "duskholm"
assert sc.clean_settings({"gradient_format": "evennia"})["gradient_format"] == "evennia"


# ---- in the app ---------------------------------------------------------------------------------------------------------------------------
def start(mode):
    home = tempfile.mkdtemp()
    os.environ["USERPROFILE"] = os.environ["HOME"] = home
    sc.SETTINGS_PATH = os.path.join(home, "s.json")
    sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
    json.dump({"ui_mode": mode} if mode else {}, open(sc.SETTINGS_PATH, "w"))
    root = tk.Tk()
    app = sc.App(root)
    root.geometry("1200x800+10+10")
    return root, app


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def screen():
    return app.term.text.get("1.0", "end") if hasattr(app.term, "text") else app.text.get("1.0", "end")


def saved():
    return json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))


root, app = start(None)
pump(0.6)
state = {"pattern": "196 21", "mode": "word", "text": "ab cd", "prefix": "say ", "smooth": True}
assert app.make_gradient(state)[0] == "say `196ab `021cd`x"
app._local("/gradient format"); pump(0.2)
app._local("/gradient format nonsense"); pump(0.2)
assert app.gradient_format() == "duskholm"
app._local("/gradient format mush"); pump(0.2)
assert app.gradient_format() == "mush" and saved()["gradient_format"] == "mush"
assert app.make_gradient(state)[0] == "say [ansi(<#FF0000>,ab)] [ansi(<#0000FF>,cd)]"
app._grad_state = dict(state, text="", prefix="")
app._local("/gradient Hello there"); pump(0.3)
assert app.input.get().startswith("[ansi(<#FF0000>,"), app.input.get()
# the window: the Format box switches, the Code box shows what will be sent
app._grad_state = dict(state)
win = app.open_gradient(); pump(0.4)
assert win._format.get() == ct.FORMATS["mush"][0]
assert win._code.get("1.0", "end-1c") == "say [ansi(<#FF0000>,ab)] [ansi(<#0000FF>,cd)]"
for key_, (name, _example, _true, _limit) in ct.FORMATS.items():
    win._format.set(name); pump(0.15)
    assert app.gradient_format() == key_ and saved()["gradient_format"] == key_
    assert win._code.get("1.0", "end-1c") == app.make_gradient(state)[0], key_
win._panel.set_stops([46]); pump(0.2)
assert app.gradient_format() == "html", "editing the colours keeps the format"
win.destroy(); app._grad_win = None
# colouring a paragraph for the game stays in the game's own codes
assert ct.colour_text("ab", two).startswith("`196")
root.destroy()

# ---- the DOS look -------------------------------------------------------------------------------------------------------------------------
root, app = start("dos")
pump(0.8)
assert app.dos


def key(w, ks):
    w.focus_force(); pump(0.15)
    w.event_generate("<%s>" % ks); pump(0.35)


def overlay():
    return app._overlay if app._overlay_open() else None


app._grad_state = dict(state, prefix="")
d = app.open_gradient(); pump(0.4)
assert isinstance(d, dosgrad.DosGradientEditor) and d._format == "duskholm"
d._set_focus(d._order.index(("pick", "format")))
key(d._cv, "Right")
assert d._format == "mush" and d._preview_coded()[1] == "[ansi(<#FF0000>,ab)] [ansi(<#0000FF>,cd)]"
key(d._cv, "Left"); key(d._cv, "Left")
assert d._format == list(ct.FORMATS)[-1], "it goes round"
key(d._cv, "Return")                                           # Enter opens the list
m = overlay()
assert isinstance(m, dosui.DosMenu) and len([i for i in m._items if i]) == len(ct.FORMATS)
names = [i["label"] if i else "" for i in m._items]
m.select(next(i for i, n in enumerate(names) if n.startswith("Evennia"))); pump(0.1)
key(m._cv, "Return"); pump(0.3)
d = overlay()
assert isinstance(d, dosgrad.DosGradientEditor) and d._format == "evennia" and app.gradient_format() == "evennia"
assert saved()["gradient_format"] == "evennia"
# every button is on the screen and inside the box
spots = [h for h in d._hits if h[0] == "button"]
assert len(spots) == len(d._buttons) and max(h[3] for h in spots) <= d._total - 1, (spots, d._total)
assert d._hpx <= app._holder.winfo_height() and d._wpx <= app._holder.winfo_width()
d._press([b["result"] for b in d._buttons].index("copy")); pump(0.5)
assert app.root.clipboard_get() == "|#ff0000ab |#0000ffcd|n", app.root.clipboard_get()
d = overlay()
d._press([b["result"] for b in d._buttons].index("send")); pump(0.4)
assert app.input.get() == "|#ff0000ab |#0000ffcd|n" and overlay() is None
# the text colouring page has no Format line
tg = app._dos_text_gradient(dict(app._grad_state), "Description", "text", None, lambda r: None); pump(0.4)
assert tg._format is None and ("pick", "format") not in tg._order
app.dos_close_overlay()
print("gradient format tests OK")
root.destroy()
