"""Picking the trigger highlight colours: the system chooser in the ordinary look, a list and the mixer in the DOS look."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import dosui
import tkinter as tk

for i in range(16):
    assert sc.parse_colour_field(sc.colour_words(str(i))) == i, i
assert sc.colour_words("#ABCDEF") == "#ABCDEF" and sc.colour_words("") == "" and sc.colour_words("junk") == "junk"


def start(mode):
    home = tempfile.mkdtemp()
    os.environ["USERPROFILE"] = os.environ["HOME"] = home
    sc.SETTINGS_PATH = os.path.join(home, "s.json")
    sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
    json.dump({"ui_mode": mode} if mode else {}, open(sc.SETTINGS_PATH, "w"))
    root = tk.Tk()
    app = sc.App(root)
    root.geometry("1200x720+10+10")
    return root, app


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


# ---- the ordinary look --------------------------------------------------------------------------------------------------------------
root, app = start(None)
pump(0.6)
assert not app.dos
form = app._trigger_form(None, None, root, lambda *_a: None)
pump(0.3)
sv = form._vars[0]
asked, answer = [], [((1, 2, 3), "#0A0B0C")]
real = sc.colorchooser.askcolor
sc.colorchooser.askcolor = lambda **kw: asked.append(kw) or answer[0]
form._picks["fg"].invoke(); pump(0.1)
assert sv["fg"].get() == "#0a0b0c" and sv["bg"].get() == "" and asked[-1]["parent"] is form
assert str(form._swatches["fg"].cget("bg")).lower() == "#0a0b0c" and form._swatches["fg"].cget("text") == ""
sv["bg"].set("bright yellow"); pump(0.1)
assert str(form._swatches["bg"].cget("bg")).lower() == app.theme["ansi"][11].lower(), "a typed name shows its colour"
form._picks["bg"].invoke(); pump(0.1)
assert asked[-1]["initialcolor" if "initialcolor" in asked[-1] else "color"].lower() == app.theme["ansi"][11].lower()
answer[0] = (None, None)                                       # the chooser cancelled: nothing changes
sv["bg"].set("red"); form._picks["bg"].invoke(); pump(0.1)
assert sv["bg"].get() == "red"
sv["bg"].set("nonsense"); pump(0.1)
assert form._swatches["bg"].cget("text") == "-"
assert form.winfo_reqwidth() < 900, form.winfo_reqwidth()
sc.colorchooser.askcolor = real
form.destroy()
root.destroy()

# ---- the DOS look -------------------------------------------------------------------------------------------------------------------
root, app = start("dos")
pump(0.8)
assert app.dos


def key(w, ks):
    w.focus_force(); pump(0.15)
    w.event_generate("<%s>" % ks); pump(0.35)


def overlay():
    return app._overlay if app._overlay_open() else None


def pick_item(label):
    m = overlay(); assert isinstance(m, dosui.DosMenu), type(m)
    names = [it["label"] if it else None for it in m._items]
    m.select(names.index(label)); pump(0.1)
    key(m._cv, "Return")


def shown(d, k):
    return next(f for f in d._fields if f["key"] == k)["shown"]


values = sc.values_from_trigger(None)
values.update(name="typo", pattern="teh", world="w", send="")
d = app._dos_trigger_form(None, values, 2); pump(0.4)
assert shown(d, "fg") == "" and d.values()["fg"] == ""
key(d._cv, "Return")                                           # Enter on the first field opens the list
m = overlay()
assert isinstance(m, dosui.DosMenu) and len([i for i in m._items if i]) == 18, (type(m), [i and i.get("label") for i in getattr(m, "_items", [])])
pick_item("Bright red"); pump(0.3)
d = overlay(); assert isinstance(d, dosui.DosDialog) and shown(d, "fg") == "bright red", values["fg"]
d._set_focus(1); key(d._cv, "Return")
pick_item("Mix any colour..."); pump(0.3)
p = overlay(); assert isinstance(p, dosui.DosColorPicker), type(p)
p.set_value("#123456"); p._finish("ok"); pump(0.5)
d = overlay(); assert isinstance(d, dosui.DosDialog) and shown(d, "bg") == "#123456" and shown(d, "fg") == "bright red"
assert d._cur() == ("field", 1), "the cursor stays on the colour just picked"
trig, why = sc.trigger_from_values(dict(values))
assert trig and trig["actions"][0]["fg"] == 9 and trig["actions"][0]["bg"] == "#123456", (trig, why)
# Esc in the list, and Cancel in the mixer, leave the colour as it was
key(d._cv, "Return")
key(overlay()._cv, "Escape"); pump(0.4)
d = overlay(); assert isinstance(d, dosui.DosDialog) and shown(d, "bg") == "#123456"
key(d._cv, "Return"); pick_item("Mix any colour..."); pump(0.3)
overlay().set_value("#ff0000"); overlay()._finish("cancel"); pump(0.5)
d = overlay(); assert isinstance(d, dosui.DosDialog) and shown(d, "bg") == "#123456"
d._set_focus(1); key(d._cv, "Return"); pick_item("No colour"); pump(0.3)
assert shown(overlay(), "bg") == "" and values["bg"] == ""
app.dos_close_overlay()
print("colour pick tests OK")
root.destroy()
