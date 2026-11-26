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

# holding the phone: a text shows up the moment it arrives, as a single line after "vibrates"; looking later does not double it
LIVE = "[Nov 24 18:31]7108390: so who are we giving him?? charity?"
feed("Your iPhone 15 vibrates.", LIVE); pump(0.9)
assert pane_lines() == [M1, M2, LIVE], pane_lines()
feed("text 7108390 preferably someone useless", "Sent."); pump(0.9)
assert pane_lines() == [M1, M2, LIVE], "what you type and the game's answer are not texts"
feed(*HEAD, M1, M2, LIVE, *LOOK_END); pump(0.9)
assert pane_lines() == [M1, M2, LIVE], pane_lines()

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
assert pane_lines() == [M1, M2, LIVE]

# a wide game: the game wraps at about 175 columns, so a 56-character text was NOT cut short, and the phone's description
# that follows the listing is not part of it (it was being captured as if it were)
app.pane_clear("phone"); pump(0.2)
WIDE = ("The corridor is long and the stone walls are wet with the damp of a thousand years, and torches gutter in iron rings. " * 2)[:172]
assert len(WIDE) == 172
feed(WIDE, WIDE.replace("stone", "brick"), WIDE.replace("torches", "lamps"), ""); pump(0.2)
W1 = "[Nov 24 18:53]7108390: its a euphemism for cunnilignus"
W2 = "[Nov 25 02:46]7108390: catherine says u are going australia???????"
DESC1 = "It has a symbol of a pair of red eyes in sinister mask."
DESC2 = "Out of date but still perfectly serviceable, this is a white titanium-coloured iPhone 15 Pro."
assert len(W2) >= 50 and len(DESC1) >= 50 and len(DESC2) >= 50, "long enough for the old rule to take them for a wrapped end"
feed(W1, W2, DESC1, DESC2, "[1/1DF M:0 K:0 ()] "); pump(0.9)
assert pane_lines() == [W1, W2], pane_lines()
feed(W1, W2, DESC1, DESC2); pump(0.9)
assert pane_lines() == [W1, W2], "and again: still just the texts"
# a text that really was wrapped at that width still comes in one piece
WL = ("[Nov 25 03:01]7108390: " + "this one really does run on and on until the game has to wrap it " * 3)[:172]
assert len(WL) == 172
WTAIL = "so the end of it is on a second line"
feed(WL, WTAIL, ""); pump(0.9)
assert pane_lines() == [W1, W2, WL, WTAIL], pane_lines()
# the width is judged per world, from the longest lines it has sent
narrow = app.open_new_world("Narrow"); pump(0.3)
app.session = narrow
cols = app.session.out.winfo_width() // max(1, app.f_norm.measure("0"))
assert app._wrap_floor() == max(50, min(80, cols - 30)), "nothing seen yet: by the window, never asking for more than 80"
for n in (80, 79, 78):
    app._wrap_note(n)
assert app._wrap_floor() == 50, "a game that wraps at about 80 keeps the old minimum"
for n in (172, 171, 172):
    app._wrap_note(n)
assert app._wrap_floor() == 141
short = app.open_new_world("Short"); pump(0.3)
app.session = short
for n in (55, 66, 55, 60):                                  # a few short lines say nothing about where the game wraps
    app._wrap_note(n)
assert app._wrap_floor() == max(50, min(80, app.session.out.winfo_width() // max(1, app.f_norm.measure("0")) - 30))
app.session = app._shown
app.close_world(short); pump(0.3)
app.session = narrow
app._wrap_note(900)
assert app._wrap_floor() == 142, "one over-long line does not skew it"
app._wrap_note(900)
assert app._wrap_floor() == 142, "nor do two"
app._wrap_note(30)
assert app._wrap_floor() == 142, "short lines are not counted"
app.session = app._shown
app.close_world(narrow); pump(0.3)

# a session that has only seen short lines so far (nothing learned about the game's wrap width yet): the window's width stands in
# for it, so a 66-character text is not taken for a wrapped one and the phone's description after it is left alone
app.pane_clear("phone"); app.session._wrap_lens.clear(); pump(0.2)
real_width = app.session.out.winfo_width
app.session.out.winfo_width = lambda: 1750                  # (a window about as wide as the screenshot's: the docked pane has squeezed this one)
assert app._wrap_floor() == 80, app._wrap_floor()
feed(W1, W2, DESC1, DESC2, ""); pump(0.9)
assert pane_lines() == [W1, W2], pane_lines()
feed(W1, W2, DESC1, DESC2, ""); pump(0.9)
assert pane_lines() == [W1, W2], "and again"
app.session.out.winfo_width = lambda: 600                   # a narrow window: a 66-character line could well have been wrapped, as before
assert app._wrap_floor() == 50
del app.session.out.winfo_width
root.update(); root.destroy()
print("capture-once tests OK")
