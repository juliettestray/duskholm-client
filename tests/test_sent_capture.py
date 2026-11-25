"""Capturing my own side of a conversation onto a pane, with a per-pane "show what I send" switch (no network)."""
import os, re, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import layout
import triggers as T
import tkinter as tk

# ---- the pieces ---------------------------------------------------------------------------------------------------------------------------
r = T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "when": "sent",
                        "actions": [{"type": "route", "pane": "P", "mine": True, "format": "You: %1 {time}"}]})
assert r["when"] == "sent" and r["actions"] == [{"type": "route", "pane": "P", "gag": False, "mine": True, "format": "You: %1 {time}"}], r
plain = T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "actions": [{"type": "route", "pane": "P"}]})
assert "when" not in plain and plain["actions"] == [{"type": "route", "pane": "P", "gag": False}], "nothing extra unless asked"
assert T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "when": "output", "actions": [{"type": "beep"}]}).get("when") is None
assert T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "actions": [{"type": "route", "pane": "P", "mine": 1}]}) is None
assert layout.validate_pane({"name": "P", "show_sent": False})["show_sent"] is False
assert "show_sent" not in layout.validate_pane({"name": "P", "show_sent": True}) and "show_sent" not in layout.validate_pane({"name": "P"})
presets = {p["name"]: p for p in sc.trigger_presets()}
mine_texts = presets["Capture my texts to a pane"]
assert mine_texts["when"] == "sent" and mine_texts["actions"][0]["mine"] is True and not mine_texts["enabled"]
assert presets["Capture your own tells to a pane"]["actions"][0]["mine"] is True
for line, who, msg in (("text 7108390 hello there", "7108390", "hello there"), ("text Mara yes after eight", "Mara", "yes after eight"),
                       ("text @bob hi", "@bob", "hi")):
    m = T.match_trigger(dict(mine_texts, enabled=True), line)
    assert m and m["captures"]["1"] == who and m["captures"]["2"] == msg, line
for line in ("text history Mara", "text clear", "text", "texting a b", "say text a b"):
    assert not T.match_trigger(dict(mine_texts, enabled=True), line), line
# the editors keep what they have no control over
v = sc.values_from_trigger(mine_texts)
assert v["sent"] is True and v["pane_mine"] is True and v["pane_format"] == "[{time}]You > %1: %2" and v["pane"] == "Phone"
back, why = sc.trigger_from_values(dict(v, name="mine2"))
assert back["when"] == "sent" and back["actions"][-1] == mine_texts["actions"][0], (back, why)
v.update(sent=False, pane_mine=False, pane_format="")
back = sc.trigger_from_values(dict(v, name="mine3"))[0]
assert "when" not in back and back["actions"][-1] == {"type": "route", "pane": "Phone", "gag": False}

# ---- in the app ------------------------------------------------------------------------------------------------------------------------------
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1250x720+20+20")
CR = chr(13) + chr(10)
sent = []
app.conn = type("C", (), {"gen": 0, "send": lambda self, b: sent.append(b) or True, "close": lambda *a: None})()
app.connected = True


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def pane_lines(key):
    p = app._panes.get(key)
    return [l for l in p["text"].get("1.0", "end").split(chr(10)) if l] if p else []


def type_main(text):
    app.input.focus_force()                            # (a key event only reaches the box that has the keyboard)
    app.input.delete(0, "end"); app.input.insert(0, text)
    app.input.event_generate("<Return>"); pump(0.3)


pump(0.5)
app.cfg["triggers"] = [dict(presets["Capture my texts to a pane"], enabled=True),
                       dict(presets["Capture your own tells to a pane"], enabled=True),
                       dict(presets["Capture phone texts (no repeats)"], enabled=True)]
STAMP = r"\[[A-Z][a-z]{2} [ 0-9]\d \d\d:\d\d\]"

# what I type in the main window is captured, with the game's kind of stamp, and still goes to the game
type_main("text 7108390 preferably someone useless")
assert sent[-1].decode().strip() == "text 7108390 preferably someone useless"
lines = pane_lines("phone")
assert len(lines) == 1 and re.fullmatch(STAMP + r"You > 7108390: preferably someone useless", lines[0]), lines
# incoming, from the other side, lands in the same pane
app._on_data(("[Nov 24 18:33]7108390: so who are we giving him?? charity?" + CR).encode()); pump(0.9)
assert len(pane_lines("phone")) == 2 and pane_lines("phone")[1].endswith("charity?")
# not everything I send: history, clear, and other commands
n = len(pane_lines("phone"))
type_main("text history 7108390"); type_main("text clear"); type_main("look"); type_main("say text 1 2")
assert len(pane_lines("phone")) == n
# a text from an alias, a button and a trigger's send is captured too: it is what goes out that counts
app._local("/alias tm text Mara %*"); type_main("tm on my way")
assert pane_lines("phone")[-1].endswith("You > Mara: on my way"), pane_lines("phone")[-1]
app._local("/button add Ping = text Bob ping"); pump(0.2)
app.run_button(app.cfg["buttons"][-1]); pump(0.3)
assert pane_lines("phone")[-1].endswith("You > Bob: ping")
# a game-text rule never fires on what I send, and a sent rule never fires on what the game shows
app.cfg["triggers"].append({"name": "g", "mode": "plain", "pattern": "text 7108390*", "enabled": True, "priority": 0,
                            "actions": [{"type": "route", "pane": "Seen"}]})
type_main("text 7108390 again"); pump(0.3)
assert pane_lines("seen") == []
n = len(pane_lines("phone")); app._on_data(("text 7108390 from the game" + CR).encode()); pump(0.4)
assert len(pane_lines("phone")) == n
app.cfg["triggers"].pop()
# a password is never captured
app.term.echo_off = True; sent.clear()
type_main("text 7108390 hunter2"); pump(0.2)
assert not any("hunter2" in l for l in pane_lines("phone")), pane_lines("phone")
app.term.echo_off = False

# my own tells, as the game echoes them, follow the same switch
app._on_data(("You tell Bob 'hi there'" + CR).encode()); pump(0.4)
assert pane_lines("tells") == ["You tell Bob 'hi there'"], pane_lines("tells")

# ---- the switch: per pane, from a command, the pop-out window and the tab menu ------------------------------------------------------------------
n = len(pane_lines("phone"))
app._local("/panesent phone off"); pump(0.2)
assert app._find_pane_def("phone")["show_sent"] is False
type_main("text Mara not shown"); pump(0.2)
assert len(pane_lines("phone")) == n and sent[-1].decode().strip() == "text Mara not shown", "still sent, just not shown"
app._on_data(("[Nov 24 18:40]Mara: incoming still comes" + CR).encode()); pump(0.9)
assert pane_lines("phone")[-1].endswith("incoming still comes"), "the other side is unaffected"
app._on_data(("You tell Bob 'quiet'" + CR).encode()); pump(0.4)
assert pane_lines("tells") == ["You tell Bob 'hi there'", "You tell Bob 'quiet'"], "the tells pane has its own switch, still on"
app._local("/panesent phone"); pump(0.2)
assert "show_sent" not in app._find_pane_def("phone"), "no on/off: it flips"
type_main("text Mara shown again")
assert pane_lines("phone")[-1].endswith("You > Mara: shown again")
view = app.pop_out_pane("Phone"); pump(0.5)
cb = [c for f in view["win"].winfo_children() if isinstance(f, tk.Frame) for c in f.winfo_children()
      if isinstance(c, tk.Checkbutton) and c.cget("text") == "Show mine"][0]
assert view["mine_var"].get() is True
cb.invoke(); pump(0.2)
assert app._find_pane_def("phone")["show_sent"] is False and view["mine_var"].get() is False
app._local("/panesent phone on"); pump(0.2)
assert view["mine_var"].get() is True, "the window follows the command"
saved = __import__("json").load(open(sc.SETTINGS_PATH, encoding="utf-8"))
# typing in the window's own input bar is captured the same way
app.set_popout_input("phone", True); app.set_popout_prefix("phone", "text Mara"); pump(0.3)
n = len(pane_lines("phone")); sent.clear()
view["entry"].focus_force(); view["entry"].insert(0, "from the window"); view["entry"].event_generate("<Return>"); pump(0.4)
assert sent[-1].decode().strip() == "text Mara from the window"
assert pane_lines("phone")[-1].endswith("You > Mara: from the window") and len(pane_lines("phone")) == n + 1
# the right-click menu on a pane's tab
menus = []
app._popup_menu = lambda m, x, y: menus.append(m)
app.dock_pane("phone"); pump(0.4)
reg = app._pane_region("phone")
lbl = app._region_ui[reg["id"]]["labels"]["phone"]
lbl.event_generate("<Button-3>", x=3, y=3, rootx=60, rooty=60); pump(0.2)
m = menus[-1]
labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) in ("command", "checkbutton")]
assert labels == ["Show what I send", "Pop out", "Clear"], labels
m.invoke(0); pump(0.2)
assert app._find_pane_def("phone")["show_sent"] is False, "the menu flips the switch"
m.invoke(0) if False else None
app.set_pane_sent("phone", True)

# ---- worlds are separate -------------------------------------------------------------------------------------------------------------------------
got = []
second = app.open_new_world("Elsewhere"); pump(0.5)
second.conn = type("C", (), {"gen": 0, "send": lambda self, b: got.append(b) or True, "close": lambda *a: None})()
second.connected = True
app.cfg["triggers"] = [dict(presets["Capture my texts to a pane"], enabled=True)]
app.pane_ensure("Phone"); pump(0.2)
assert app._find_pane_def("phone") is not None
app._local("/panesent phone off"); pump(0.2)
assert app._find_pane_def("phone")["show_sent"] is False
type_main("text Zed in the other world"); pump(0.3)
assert [b.decode().strip() for b in got] == ["text Zed in the other world"], "it was sent to this world"
assert pane_lines("phone") == [], "this world's switch is off"
app.goto_world(1); pump(0.5)
assert app._find_pane_def("phone") and app._find_pane_def("phone").get("show_sent") is None
app.close_world(second); pump(0.3)

root.update(); root.destroy()
print("sent capture tests OK")
