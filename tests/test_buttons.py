"""Buttons: a bar of clickable buttons that send commands, with hotkeys, per-world scope, both looks (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import buttons as B
import tkinter as tk

# ---- the pure part ------------------------------------------------------------------------------------------------------------------
v = B.validate_button({"name": "  Sneak ", "body": " sneak;hide ", "key": "alt-f5", "junk": 1})
assert v == {"name": "Sneak", "body": "sneak;hide", "key": "Alt-F5", "enabled": True}, v
assert B.validate_button({"name": "Hi", "body": "x", "key": "not a key"})["key"] == "", "a bad hotkey is dropped, the button stays"
assert B.validate_button({"name": "Hi", "body": "x", "key": "a"})["key"] == "", "letters need Ctrl or Alt"
for bad in (None, 5, {}, {"name": "", "body": "x"}, {"name": "x", "body": ""}, {"name": "A" * 25, "body": "x"},
            {"name": "x", "body": "y" * 5000}, {"body": "x"}):
    assert B.validate_button(bad) is None, bad
w = B.validate_button({"name": "Hi", "body": "x", "global": False, "world": "Duskholm", "enabled": False})
assert w["global"] is False and w["world"] == "Duskholm" and w["enabled"] is False
lst = B.clean_buttons([{"name": "A", "body": "x"}, {"name": "a", "body": "y"}, {"name": "A", "body": "z", "global": False, "world": "W"},
                       "junk", None, {"name": "B", "body": "x"}])
assert [x["name"] for x in lst] == ["A", "A", "B"], "same label twice in one scope is dropped"
assert len(B.clean_buttons([{"name": "n%d" % i, "body": "x"} for i in range(200)])) == B.MAX_BUTTONS
assert B.clean_buttons("nope") == [] and sc.clean_settings({"buttons": [{"name": "A", "body": "x"}, 5]})["buttons"][0]["name"] == "A"
assert sc.clean_settings({"button_dock": "sideways"})["button_dock"] == "top"

# ---- in the app --------------------------------------------------------------------------------------------------------------------
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x700+20+20")
sent = []
app.conn = type("C", (), {"gen": 0, "send": lambda self, b: sent.append(b) or True, "close": lambda *a: None})()
app.connected = True


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def lines():
    return [b.decode().rstrip() for b in sent]


def widgets():
    return list(app._btn_widgets)


def out_text():
    return app.out.get("1.0", "end")


pump(0.5)
assert not app._btnbar.winfo_ismapped(), "no buttons, no bar"
app._local("/button list"); assert "No buttons" in out_text()

# ---- /button add: the bar appears under the tabs, and a click sends the commands, without touching the history ----------------------
app._local("/button add Sneak = sneak;hide"); pump(0.4)
assert app._btnbar.winfo_ismapped() and len(widgets()) == 1 and widgets()[0].cget("text") == "Sneak"
assert app._btnbar.winfo_y() > app._tabbar.winfo_y() and app._holder.winfo_y() > app._btnbar.winfo_y(), "under the tabs, over the text"
hist = list(app.history)
sent.clear()
widgets()[0].invoke(); pump(0.3)
assert lines() == ["sneak", "hide"], lines()
assert app.history == hist, "buttons do not fill the command history"
assert sc.json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))["buttons"][0]["name"] == "Sneak" if hasattr(sc, "json") else True

# ---- aliases and /commands inside a button -----------------------------------------------------------------------------------------
app._local("/alias zz say zapped")
app._local("/button add Zap = zz"); pump(0.3)
sent.clear(); [w for w in widgets() if w.cget("text") == "Zap"][0].invoke(); pump(0.3)
assert lines() == ["say zapped"], lines()
app._local("/button add Peek = /world"); pump(0.3)
n = len(out_text()); sent.clear()
[w for w in widgets() if w.cget("text") == "Peek"][0].invoke(); pump(0.3)
assert sent == [] and "Worlds:" in out_text()[n:], "a /command runs locally and sends nothing"
app._local("/button del Peek"); app._local("/button del Zap"); pump(0.3)
assert [w.cget("text") for w in widgets()] == ["Sneak"]

# ---- hotkeys -----------------------------------------------------------------------------------------------------------------------
app._local("/button key Sneak Alt-F5"); pump(0.3)
assert app.cfg["buttons"][0]["key"] == "Alt-F5" and widgets()[0].cget("text") == "Sneak  Alt-F5"
sent.clear()
app.input.focus_force(); pump(0.1)
app.input.event_generate("<Alt-F5>"); pump(0.3)
assert lines() == ["sneak", "hide"], "the hotkey runs it from the entry box"
sent.clear(); root.event_generate("<Alt-F5>"); pump(0.2)
assert lines() == ["sneak", "hide"], "and from the window"
n = len(out_text())
app._local("/button key Sneak Ctrl-T"); assert "Triggers" in out_text()[n:] and app.cfg["buttons"][0]["key"] == "Alt-F5", "a built-in key is refused"
app._local("/button add Hide = hide"); app._local("/button key Hide Alt-F5")
assert [b["key"] for b in app.cfg["buttons"]] == ["Alt-F5", ""], "two buttons cannot share a key"
n = len(out_text()); app._local("/button key Hide banana"); assert out_text()[n:].strip()
app._local("/button key Hide Alt-H"); app._local("/button key Hide Alt-F9"); pump(0.3)
assert app.cfg["buttons"][1]["key"] == "Alt-F9"
app._local("/button key Sneak none"); pump(0.3)
sent.clear(); app.input.event_generate("<Alt-F5>"); pump(0.3)
assert sent == [] and app.cfg["buttons"][0]["key"] == "", "clearing the key unbinds it"

# ---- per world ---------------------------------------------------------------------------------------------------------------------
b, why = app.make_button(None, "Local", "look", "Alt-F7", True, False)
assert b["global"] is False and b["world"] == app._world_name(app._shown), (b, why)
assert app.store_button(None, b)[0]
second = app.open_new_world("Elsewhere"); pump(0.5)
assert "Local" not in [w.cget("text").split("  ")[0] for w in widgets()], "a button tied to another world is not shown here"
sent.clear(); app.input.event_generate("<Alt-F7>"); pump(0.2)
assert sent == [], "and its hotkey does nothing here"
app.goto_world(1); pump(0.5)
assert "Local" in [w.cget("text").split("  ")[0] for w in widgets()]
app.close_world(second); pump(0.3)

# ---- where it docks ------------------------------------------------------------------------------------------------------------------
app._local("/button dock bottom"); pump(0.5)
assert app._btnbar.winfo_ismapped() and app._btnbar.winfo_y() > app._holder.winfo_y(), "bottom: under the text"
assert app._btnbar.winfo_y() < app._inbox.winfo_y(), "above the entry box"
app._local("/button dock off"); pump(0.3)
assert not app._btnbar.winfo_ismapped() and app.cfg["button_dock"] == "off"
sent.clear(); app.input.event_generate("<Alt-F9>"); pump(0.2)
assert sent == [], "no bar, no hotkeys"
app._local("/button dock top"); pump(0.4)
assert app._btnbar.winfo_ismapped() and app.cfg["button_dock"] == "top"
app._set_extra("world_tabs", "off"); pump(0.4)
assert app._btnbar.winfo_y() < app._holder.winfo_y() and app._btnbar.winfo_y() >= app._top.winfo_y() + app._top.winfo_height() - 1
app._set_extra("world_tabs", "always"); pump(0.4)
assert app._btnbar.winfo_y() > app._tabbar.winfo_y(), "stays under the tabs when they come back"

# ---- wraps onto more rows in a narrow window ---------------------------------------------------------------------------------------------
for i in range(8):
    app._local("/button add Long button number %d = look" % i)
root.geometry("520x600+20+20"); pump(0.8)
rows = {int(w.grid_info()["row"]) for w in widgets()}
assert len(rows) >= 2, rows
root.geometry("1100x700+20+20"); pump(0.6)
for i in range(8):
    app._local("/button del Long button number %d" % i)
pump(0.3)

# ---- the manager window -------------------------------------------------------------------------------------------------------------------
win = app.open_buttons(); pump(0.4)
lb = win._list
assert lb.size() == len(app.cfg["buttons"]) and "Sneak" in lb.get(0)
lb.selection_clear(0, "end"); lb.selection_set(0)
kids = [w for f in win.winfo_children() if isinstance(f, tk.Frame) for w in f.winfo_children() if isinstance(w, tk.Button)]
byname = {b.cget("text"): b for b in kids}
byname["On/off"].invoke(); pump(0.2)
assert app.cfg["buttons"][0]["enabled"] is False and "Sneak" not in [w.cget("text").split("  ")[0] for w in widgets()]
byname["On/off"].invoke(); pump(0.2)
assert app.cfg["buttons"][0]["enabled"] is True
names0 = [b["name"] for b in app.cfg["buttons"]]
byname["Down"].invoke(); pump(0.2)
assert [b["name"] for b in app.cfg["buttons"]][:2] == [names0[1], names0[0]]
byname["Up"].invoke(); pump(0.2)
assert [b["name"] for b in app.cfg["buttons"]] == names0
byname["Add"].invoke(); pump(0.4)
form = [w for w in win.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Add button"][0]
sv, en, allw = form._vars
sv["name"].set("From form"); sv["body"].set("emote waves"); sv["key"].set("Ctrl-T")
form._ok(); pump(0.2)
assert "Triggers" in form._msg.cget("text") and form.winfo_exists(), "the form says why a key is refused"
sv["key"].set("Alt-F8"); form._ok(); pump(0.3)
assert app.cfg["buttons"][-1]["name"] == "From form" and app.cfg["buttons"][-1]["key"] == "Alt-F8"
assert lb.size() == len(app.cfg["buttons"])
sv_name = "From form"
byname["Edit"].invoke() if False else None
win.destroy()

# ---- the DOS look: the bar and its list --------------------------------------------------------------------------------------------------------
app.set_dos_mode(True); pump(0.8)
assert app._btnbar.winfo_ismapped() and all(isinstance(w, tk.Label) for w in widgets()), "labels in the DOS look"
assert app._btnbar.winfo_y() > app.dosbar.top.winfo_y(), "under the DOS hint row"
sent.clear()
[w for w in widgets() if w.cget("text").strip().startswith("Sneak")][0].event_generate("<Button-1>", x=3, y=3); pump(0.3)
assert lines() == ["sneak", "hide"], lines()
t = app.open_buttons(); pump(0.4)
assert t is not None and app._overlay_open()
t.close(); pump(0.3)
app._dos_button_form(None, None); pump(0.3)
assert app._overlay_open()
app._overlay.close(); pump(0.2)
app.set_dos_mode(False); pump(0.8)
assert app._btnbar.winfo_ismapped() and all(isinstance(w, tk.Button) for w in widgets())

# ---- a button from a bad file never breaks start-up ------------------------------------------------------------------------------------------
assert sc.clean_settings({"buttons": [{"name": "ok", "body": "x"}, {"name": 5}, "x", None]})["buttons"] == \
    [{"name": "ok", "body": "x", "key": "", "enabled": True}]

root.update(); root.destroy()
print("button tests OK")
