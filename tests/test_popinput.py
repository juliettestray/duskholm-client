"""A popped-out window's own input bar: sends to its world, with a prefix, remembered per pane (no network)."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import layout
import tkinter as tk

# ---- what is remembered ----------------------------------------------------------------------------------------------------------------
v = layout.validate_pane({"name": "Phone", "window": {"out": True, "input": True, "prefix": "  text   Mara  ", "top": False}})
assert v["window"] == {"out": True, "top": False, "input": True, "prefix": "text Mara"}, v["window"]
assert "input" not in layout.validate_pane({"name": "P", "window": {"input": "yes"}}).get("window", {})
assert "prefix" not in layout.validate_pane({"name": "P", "window": {"input": True, "prefix": "   "}})["window"]
assert len(layout.validate_pane({"name": "P", "window": {"prefix": "x" * 90}})["window"]["prefix"]) == 40

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x700+20+20")
CR = chr(13) + chr(10)
sent = []
app.conn = type("C", (), {"gen": 0, "send": lambda self, b: sent.append(b) or True, "close": lambda *a: None})()
app.connected = True


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def lines():
    return [b.decode().rstrip() for b in sent]


def type_in(view, text):
    e = view["entry"]
    e.focus_force(); pump(0.1)
    e.delete(0, "end"); e.insert(0, text)
    e.event_generate("<Return>"); pump(0.3)


pump(0.5)
app.pane_ensure("Phone")
view = app.pop_out_pane("Phone"); pump(0.5)

# ---- off until asked for ----------------------------------------------------------------------------------------------------------------
assert not view["inbar"].winfo_ismapped() and view["inp_var"].get() is False
assert "input" not in (app._find_pane_def("phone").get("window") or {})
cb = [c for f in view["win"].winfo_children() if isinstance(f, tk.Frame) for c in f.winfo_children()
      if isinstance(c, tk.Checkbutton) and c.cget("text") == "Input"][0]
cb.invoke(); pump(0.4)
assert view["inbar"].winfo_ismapped() and app._find_pane_def("phone")["window"]["input"] is True
assert view["inbar"].winfo_y() > view["box"].winfo_y(), "under the text"
assert view["inbar"].winfo_y() + view["inbar"].winfo_height() <= view["win"].winfo_height() + 1, "and not cut off"
assert sc.json.load(open(sc.SETTINGS_PATH, encoding="utf-8")) if hasattr(sc, "json") else True

# ---- typing there sends to the game, with the prefix --------------------------------------------------------------------------------------
sent.clear()
type_in(view, "look")
assert lines() == ["look"], lines()
assert view["entry"].get() == "" and root.focus_get() is view["entry"], "it stays in the window's own box"
view["prefix_var"].set("text Mara")
type_in(view, "yes, after eight")
assert lines()[-1] == "text Mara yes, after eight", lines()
type_in(view, "/world"); assert lines()[-1] == "text Mara yes, after eight" and "Worlds:" in app.out.get("1.0", "end"), "a /command skips the prefix and stays local"
sent.clear(); type_in(view, "   "); assert sent == [], "nothing to send"
d = app._find_pane_def("phone")["window"]
assert d["prefix"] == "text Mara", d
assert "text Mara yes, after eight" in app.history, "it is in the command history like anything typed"

# ---- history in the window's box ----------------------------------------------------------------------------------------------------------
view["entry"].focus_force(); view["entry"].delete(0, "end")
view["entry"].event_generate("<Up>"); pump(0.1)
assert view["entry"].get() == "/world"
view["entry"].event_generate("<Up>"); view["entry"].event_generate("<Up>"); pump(0.1)
assert view["entry"].get() == "look"
view["entry"].event_generate("<Down>"); pump(0.1)
assert view["entry"].get() == "yes, after eight"
view["entry"].delete(0, "end")

# ---- /popinput ----------------------------------------------------------------------------------------------------------------------------------
app._local("/popinput phone prefix text Bob"); pump(0.2)
assert view["prefix_var"].get() == "text Bob" and app._find_pane_def("phone")["window"]["prefix"] == "text Bob"
app._local("/popinput phone prefix"); pump(0.2)
assert view["prefix_var"].get() == "" and "prefix" not in app._find_pane_def("phone")["window"]
app._local("/popinput phone off"); pump(0.3)
assert not view["inbar"].winfo_ismapped() and view["inp_var"].get() is False
app._local("/popinput phone"); pump(0.3)
assert view["inbar"].winfo_ismapped(), "no on/off: it flips"
n = len(app.out.get("1.0", "end")); app._local("/popinput nosuch"); app._local("/popinput"); pump(0.2)
msg = app.out.get("1.0", "end")[n:]
assert "No pane called 'nosuch'" in msg and "Say which pane" in msg

# ---- it comes back with the window, and the prefix typed last is kept when docking -------------------------------------------------------------
view["prefix_var"].set("text Zed")
app.dock_pane("phone"); pump(0.4)
w = app._find_pane_def("phone")["window"]
assert w["out"] is False and w["input"] is True and w["prefix"] == "text Zed", w
view = app.pop_out_pane("Phone"); pump(0.5)
assert view["inbar"].winfo_ismapped() and view["prefix_var"].get() == "text Zed", "the input bar and its prefix come back"
view["prefix_var"].set(""); app.dock_pane("phone"); pump(0.3)
assert "prefix" not in app._find_pane_def("phone")["window"], "an emptied prefix is forgotten"

# ---- it belongs to its world: a window for a hidden world sends there, not to the world on screen ------------------------------------------------
second = app.open_new_world("Elsewhere"); pump(0.5)
got = []
second.conn = type("C", (), {"gen": 0, "send": lambda self, b: got.append(b) or True, "close": lambda *a: None})()
second.connected = True
app.goto_world(1); pump(0.4)
app.session = second
app.pane_ensure("Phone")
v2 = app.pop_out_pane("Phone"); pump(0.5)
app.session = app._shown
assert v2["session"] is second and app._shown is not second
app.session = second; app.set_popout_input("phone", True); app.session = app._shown; pump(0.3)
sent.clear(); got.clear()
type_in(v2, "hello there")
assert [b.decode().rstrip() for b in got] == ["hello there"] and sent == [], (got, sent)
assert app.session is app._shown, "the window's world is only borrowed for the send"

# ---- a password prompt in that world: masked, sent without the prefix, and not remembered -------------------------------------------------------------
second.term.echo_off = True
v2["prefix_var"].set("text Mara")
v2["entry"].focus_force(); pump(0.1)
v2["entry"].event_generate("<KeyPress-a>"); pump(0.1)
assert v2["entry"].cget("show") == "*"
got.clear(); hist_before = list(v2["hist"])
type_in(v2, "hunter2")
assert [b.decode().rstrip() for b in got] == ["hunter2"], got
assert v2["hist"] == hist_before, "a password is not kept in the window's history"
second.term.echo_off = False
v2["entry"].event_generate("<KeyPress-a>"); pump(0.1)
assert v2["entry"].cget("show") == ""

# ---- closing the world closes its windows without trouble -----------------------------------------------------------------------------------------
app.close_world(second); pump(0.4)
root.update(); root.destroy()
print("pop-out input tests OK")
