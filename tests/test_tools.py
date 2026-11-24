"""Hex tool, gradient maker and customize form, end to end in both looks (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import colortools as ct
import custom
import dosui
import tkinter as tk

home = tempfile.mkdtemp()
os.environ["USERPROFILE"] = os.environ["HOME"] = home
sc.SETTINGS_PATH = os.path.join(home, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x720+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


sent = []
app.conn = type("C", (), {"send": lambda self, b: sent.append(b.decode().rstrip("\r\n")) or True, "close": lambda self, *a: None})()
app.connected = True
txt = lambda: app.out.get("1.0", "end")

# ---- hex
app._local("/hex ff8800 zzz"); pump(0.2)
assert "closest to xterm 208" in txt() and "`208" in txt() and "not a hex colour" in txt()
app.hex_report("#00f", system=True); assert "xterm 21 " in txt() or "xterm 12 " in txt() or "xterm 4 " in txt()
app.open_hex().destroy()
app.set_dos_mode(True); pump(0.4)
app.open_hex(); pump(0.3); assert app._overlay_open(); app.dos_close_overlay()
app.set_dos_mode(False); pump(0.3)

# ---- gradient
coded, why = app.make_gradient({"pattern": "Fire", "mode": "stretch", "text": "Hello", "prefix": "say ", "smooth": False})
assert coded and coded.startswith("say `196H") and coded.endswith("`x"), coded
assert app.make_gradient({"pattern": "nope", "mode": "stretch", "text": "x"})[0] is None
assert app.make_gradient({"pattern": "Fire", "mode": "stretch", "text": "  "})[1] == "Type some text to colour."
assert app.make_gradient({"pattern": "196 21", "mode": "cycle", "text": "ab", "smooth": True})[0] == "`196a`021b`x"
assert app.make_gradient({"pattern": "Fire", "mode": "line", "text": "a\nb", "smooth": False})[0] == "`196a\n`226b`x"
ok, m = app.save_pattern("My Blues", "17 21 27"); assert ok, m
assert app.cfg["gradients"] == [{"name": "My Blues", "colours": [17, 21, 27]}]
assert app.make_gradient({"pattern": "my blues", "mode": "cycle", "text": "abcd"})[0] == "`017a`021b`027c`017d`x"
assert not app.save_pattern("Fire", "1 2")[0] and not app.save_pattern("", "1 2")[0] and not app.save_pattern("x", "nonsense")[0]
assert app.delete_pattern("MY BLUES") and app.cfg["gradients"] == [] and not app.delete_pattern("Fire")
app._local("/gradient Hello there"); pump(0.2)
assert app.input.get().startswith("`196H") and app.input.get().endswith("`x")
assert "Hello there" in txt(), "the coloured line is shown on screen"
win = app.open_gradient(); pump(0.4); assert win.winfo_exists()
import gradwin
panel = win._panel
assert isinstance(panel, gradwin.GradientPanel) and len(panel.stops) >= 2
n0 = len(panel.stops)


def click(widget, x, y):
    widget.event_generate("<ButtonPress-1>", x=x, y=y); pump(0.2)


def hit(kind, what=None):
    return next(h for h in panel._hits if h[4] == kind and (what is None or h[5] == what))


h = hit("stop", 1); click(panel._cv, h[0] + 3, h[1] + 3)
assert panel.sel == 1 and panel._picker is None, "one click selects"
h = hit("add"); click(panel._cv, h[0] + 3, h[1] + 3)
assert len(panel.stops) == n0 + 1 and panel.pattern.get() == "custom", "[+] adds a colour and it is now a custom pattern"
h = hit("del"); click(panel._cv, h[0] + 3, h[1] + 3)
assert len(panel.stops) == n0
panel._select(0); panel._move(1); assert panel.sel == 1
panel.set_stops([196, 226, 46], "Mine"); panel._select(1)
assert panel.get()["stops"] == [196, 226, 46] and panel.get()["pattern"] == "Mine"
# the picker: a click on a selected swatch opens it; changes show on the swatch straight away
h = hit("stop", 1); click(panel._cv, h[0] + 3, h[1] + 3)
pk = panel._picker; assert isinstance(pk, gradwin.ColourPicker) and pk.winfo_exists() and pk._index == 226
cell = pk._cells[46]
pk._pal_click(type("E", (), {"x": cell[0] + 2, "y": cell[1] + 2})()); pump(0.2)
assert panel.stops[1] == 46 and pk._index == 46, "a palette swatch is picked exactly"
pk._var.set("#ff8800"); pump(0.2); assert panel.stops[1] == 208, "typed hex snaps to the nearest colour"
pk._sq_click(type("E", (), {"x": pk.SQ - 1, "y": 0})()); pump(0.2)
assert panel.stops[1] == ct.from_hsv(pk._h, 1.0, 1.0)[0], "the square sets saturation and brightness"
old_sq = pk._h
pk._hue_click(type("E", (), {"x": 5, "y": 5})()); pump(0.2)
assert pk._h != old_sq and panel.stops[1] == ct.from_hsv(pk._h, pk._s, pk._v)[0]
pk._cancel(); pump(0.2)
assert panel.stops == [196, 226, 46] and panel._picker is None, "Cancel puts the colour back"
panel._pick(); pk = panel._picker; pk._pal_click(type("E", (), {"x": pk._cells[21][0] + 2, "y": pk._cells[21][1] + 2})()); pk._ok(); pump(0.2)
assert panel.stops == [196, 21, 46] and panel._picker is None, "OK keeps it"
# keys on the swatch row
panel._cv.focus_force(); pump(0.1)
panel._cv.event_generate("<Right>"); pump(0.1); assert panel.sel == 2
panel._cv.event_generate("<Insert>"); pump(0.1); assert len(panel.stops) == 4
panel._cv.event_generate("<Delete>"); pump(0.1); assert len(panel.stops) == 3
# the rest of the window follows
panel._load("Ocean"); pump(0.2)
assert panel.stops == ct.PRESETS["Ocean"] and panel.pattern.get() == "Ocean" and app._grad_state["pattern"] == "Ocean"
panel.set_stops([196, 21]); pump(0.2); assert app._grad_state["pattern"] == "196,21", app._grad_state["pattern"]
assert app.make_gradient(dict(app._grad_state, text="ab", mode="stretch", smooth=False))[0] == "`196a`021b`x"
win.destroy(); app._grad_win = None
# colour the selected text (paragraph box): the same panel
tw = tk.Text(root); tw.insert("1.0", "plain text here")
done_calls = []
tg = app._text_gradient_window(root, tw, lambda: done_calls.append(1)); pump(0.3)
tg._panel.set_stops([196, 226])
apply_btn = [b for w in tg.winfo_children() if isinstance(w, tk.Frame) and not isinstance(w, gradwin.GradientPanel)
             for b in w.winfo_children() if isinstance(b, tk.Button) and b.cget("text") == "Apply"][0]
apply_btn.invoke(); pump(0.3)
assert done_calls == [1] and ct.strip_codes(tw.get("1.0", "end-1c")) == "plain text here" and "`196" in tw.get("1.0", "end-1c")
app.set_dos_mode(True); pump(0.4)
box = app.open_gradient(); pump(0.3); assert type(box).__name__ == "DosGradientEditor"
app.dos_close_overlay(); pump(0.2)
app._grad_state = dict(app._grad_state, text="Shiny")
app.show_coloured(app.make_gradient(app._grad_state)[0]); pump(0.2)
tags = [t for t in app.out.tag_names(app.out.search("Shiny", "1.0")) if t.startswith("s")]
assert tags and app.out.tag_cget(tags[0], "foreground")
app.set_dos_mode(False); pump(0.3)

# ---- customize
sent.clear()
app.cfg["custom_form"] = True
app.input.delete(0, "end"); app.input.insert(0, "customize"); root.update()
app._on_enter(None); pump(0.4)
assert app._cust_win is not None and not sent, "typing 'customize' opens the form instead of sending it"
w = app._cust_win
w.destroy(); app._cust_win = None
ok, m = app.send_customize({"item": "scarf", "shortstring": "a red scarf", "description": "Soft.\nSilk."})
assert ok and sent == ["customize scarf shortstring a red scarf", "customize scarf description", "Soft.", "Silk.", "@"], sent
sent.clear()
assert not app.send_customize({"item": ""})[0] and sent == []
app.input.delete(0, "end"); app.input.insert(0, "customize scarf names x"); app._on_enter(None)
assert sent == ["customize scarf names x"], "with arguments it goes to the game untouched"
app.cfg["custom_form"] = False
sent.clear(); app.input.delete(0, "end"); app.input.insert(0, "customize"); app._on_enter(None)
assert sent == ["customize"], "the form can be turned off"
app.cfg["custom_form"] = True
app.set_dos_mode(True); pump(0.4)
d = app.open_customize(); pump(0.3); assert isinstance(d, dosui.DosDialog)
app.dos_close_overlay(); pump(0.2)
app._dos_customize(custom.blank(), 2); pump(0.3); assert app._overlay_open(); app.dos_close_overlay()
app.cfg["designs"] = custom.save_design([], "Silk scarf", "clothing", {"names": "red scarf", "item": "scarf"})
app._dos_design_book(lambda dd: None, lambda: None); pump(0.4); assert app._overlay_open(); app.dos_close_overlay()
app.set_dos_mode(False); pump(0.3)
top = app.open_customize({"item": "ring", "names": "gold ring"}); pump(0.3)
assert top.winfo_exists()
top.destroy(); app._cust_win = None
bk = app._design_book_window(app.root, lambda dd: None); pump(0.2); bk.destroy()

# review fixes: no alias expansion inside the editor text
app.cfg["alias_rules"] = [{"name": "n", "enabled": True, "body": "north"}]
sent.clear()
app.send_customize({"item": "hat", "description": "n is for nothing\nsecond"})
assert sent == ["customize hat description", "n is for nothing", "second", "@"], sent
app.cfg["alias_rules"] = []

# ---- settings are cleaned
c = sc.clean_settings({"host": "x", "gradients": [{"name": "A", "colours": [1]}, "junk"], "designs": [{"name": "B", "type": "game"}, 5]})
assert [g["name"] for g in c["gradients"]] == ["A"] and [d["name"] for d in c["designs"]] == ["B"]
c = sc.clean_settings({"host": "x", "gradients": 5, "designs": "x"}); assert c["gradients"] == [] and c["designs"] == []

root.update(); root.destroy()
print("tools tests OK")
