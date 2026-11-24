"""Capturing a repeating log (the phone's texts) onto a pane without doubling lines (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import triggers as T
import tkinter as tk

# ---- the action and the preset ---------------------------------------------------------------------------------------------------------
a = T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "actions": [{"type": "route", "pane": "P", "once": True}]})
assert a["actions"] == [{"type": "route", "pane": "P", "gag": False, "once": True}]
b = T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "actions": [{"type": "route", "pane": "P"}]})
assert b["actions"] == [{"type": "route", "pane": "P", "gag": False}], "off unless asked, and not written when off"
assert T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "actions": [{"type": "route", "pane": "P", "once": "yes"}]}) is None
preset = [p for p in sc.trigger_presets() if "phone" in p["name"].lower()]
assert len(preset) == 1 and not preset[0]["enabled"] and preset[0]["actions"][0]["once"] is True and preset[0]["actions"][0]["pane"] == "Phone"
for line in ("[Jun  9 12:34]5551234: hi there", "[Nov 24 09:05]Bob: ok", "[Dec 31 23:59]Unknown: x"):
    assert T.match_trigger(dict(preset[0], enabled=True), line), line
for line in ("[204/350DF 1ST 2WN]", "Phone Number: 5551234", "[OOC] Bob: hi", "[Jun 9 12:34 foo", " [Jun  9 12:34]x"):
    assert not T.match_trigger(dict(preset[0], enabled=True), line), line
# the editors round-trip the option, so editing the preset does not lose it
v = sc.values_from_trigger(preset[0])
assert v["pane_once"] is True and v["pane"] == "Phone"
back, why = sc.trigger_from_values(dict(v, name="mine"))
assert back["actions"][-1] == {"type": "route", "pane": "Phone", "gag": False, "once": True}, (back, why)
v["pane_once"] = False
assert "once" not in sc.trigger_from_values(dict(v, name="mine"))[0]["actions"][-1]

# ---- in the app ----------------------------------------------------------------------------------------------------------------------------
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
        app._on_data((l + CR).encode())
    pump(0.15)


def pane_lines(key="phone"):
    p = app._panes.get(key)
    return [l for l in p["text"].get("1.0", "end").split(chr(10)) if l] if p else []


pump(0.5)
app.connected = True
app.cfg["triggers"] = [dict(preset[0], enabled=True)]
M1 = "[Jun  9 12:34]5551234: hey, are you around later?"
M2 = "[Jun  9 12:40]Mara: yes, after eight"
M3 = "[Jun  9 12:41]Mara: that long text which the game wraps at eighty characters, so it comes in two"
M3b = "pieces on the screen"
HEAD = ["You look at the phone.", "Phone Number: 5551234"]
LOOK_END = ["Exits: north south"]

# the first look fills the pane with the messages, the wrapped one in one piece
feed(*HEAD, "", M1, M2, M3, M3b, "", *LOOK_END); pump(0.9)
assert pane_lines() == [M1, M2, M3, M3b], pane_lines()
assert M1 in app.out.get("1.0", "end") and "Phone Number" in app.out.get("1.0", "end"), "the main window still shows it all"
assert "Phone Number: 5551234" not in "\n".join(pane_lines()), "only the texts go to the pane"

# looking again, and again: nothing doubles
feed(*HEAD, M1, M2, M3, M3b, *LOOK_END); pump(0.9)
feed("[204/350DF 1ST 2WN]", *HEAD, "", M1, M2, M3, M3b, "", *LOOK_END); pump(0.9)
assert pane_lines() == [M1, M2, M3, M3b], pane_lines()

# a new text arrives: only it is added, in order, wherever it sits in the listing
M4 = "[Jun  9 13:02]Bob: dinner?"
feed(*HEAD, M1, M2, M3, M3b, M4, *LOOK_END); pump(0.9)
assert pane_lines() == [M1, M2, M3, M3b, M4], pane_lines()
feed(*HEAD, M1, M2, M3, M3b, M4, *LOOK_END); pump(0.9)
assert pane_lines() == [M1, M2, M3, M3b, M4]

# word-for-word identical texts inside one minute are both kept, and not doubled when looked at again
D = "[Jun  9 13:05]Mara: lol"
feed(*HEAD, M1, M2, M3, M3b, M4, D, D, *LOOK_END); pump(0.9)
assert pane_lines()[-2:] == [D, D], pane_lines()
feed(*HEAD, M1, M2, M3, M3b, M4, D, D, *LOOK_END); pump(0.9)
assert pane_lines().count(D) == 2 and len(pane_lines()) == 7, pane_lines()
feed(*HEAD, M1, M2, M3, M3b, M4, D, D, D, *LOOK_END); pump(0.9)
assert pane_lines().count(D) == 3, "a third identical one is new"
feed(*HEAD, M1, M2, M3, M3b, M4, D, D, D, *LOOK_END); pump(0.9)
assert pane_lines().count(D) == 3 and len(pane_lines()) == 8

# a line after a blank line or a prompt is not part of the text before it
before = len(pane_lines())
feed(M1.replace("12:34", "12:35"), "", "Something else entirely"); pump(0.9)
assert len(pane_lines()) == before + 1 and "Something else entirely" not in "\n".join(pane_lines())
feed("[Jun  9 12:36]Zed: last", "[204/350DF 1ST 2WN] "); pump(0.9)
assert pane_lines()[-1] == "[Jun  9 12:36]Zed: last" and len(pane_lines()) == before + 2
feed("[Jun  9 12:37]Zed: again", "Exits: north south"); pump(0.9)
assert "Exits: north south" not in "\n".join(pane_lines()), "a short line was not wrapped, so nothing continues it"
LONG = "[Jun  9 12:38]Zed: " + "a very long message " * 3
feed(LONG, "and its wrapped end", "", "Exits: up"); pump(0.9)
assert pane_lines()[-2:] == [LONG, "and its wrapped end"] and "Exits: up" not in "\n".join(pane_lines())
feed(LONG, "and its wrapped end", "Exits: up"); pump(0.9)
assert pane_lines().count(LONG) == 1, "a stray line carried along once never makes a text look new"

# clearing the pane forgets: the next look fills it again
app.pane_clear("phone"); pump(0.2)
assert pane_lines() == []
feed(*HEAD, M1, M2, *LOOK_END); pump(0.9)
assert pane_lines() == [M1, M2], pane_lines()

# a plain route (not once) is untouched, and another world has its own memory
app.cfg["triggers"].append({"name": "plain", "mode": "plain", "pattern": "Exits:*", "enabled": True, "priority": 0,
                            "actions": [{"type": "route", "pane": "Plain"}]})
feed("Exits: east"); feed("Exits: east"); pump(0.5)
assert pane_lines("plain") == ["Exits: east", "Exits: east"], "ordinary routes copy every time"
second = app.open_new_world("Elsewhere"); pump(0.4)
app.session = second
second_pane = None
app.cfg["triggers"] = [dict(preset[0], enabled=True)]
app._on_data((M1 + CR).encode()); pump(0.9)
app.session = app._shown
assert app._shown is second
assert pane_lines() == [M1], "the world on screen has its own pane and its own memory"
app.goto_world(1); pump(0.4)
assert pane_lines() == [M1, M2]

root.update(); root.destroy()
print("capture-once tests OK")
