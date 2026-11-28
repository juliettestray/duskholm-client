"""Triggers, aliases and the whole-line output engine, end to end (local fake server only)."""
import json, os, socket, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import dosui, triggers
import tkinter as tk

E = "\x1b["

# ============================== pure helpers ===================================================================
K = (None, None, False, False, False, False)
P = [("Bob says, ", K), ("hello", (1, None, True, False, False, False)), (" there", K)]
plain = "".join(t for t, _ in P)
h = sc.apply_highlight(P, 10, 15, fg="#ff0000")                    # exactly "hello"
assert "".join(t for t, _ in h) == plain
assert [(t, k[0]) for t, k in h] == [("Bob says, ", None), ("hello", "#ff0000"), (" there", None)]
assert h[1][1][2] is True, "other attributes (bold) are kept"
h = sc.apply_highlight(P, 4, 14, bg=3, bold=True)                  # spans two pieces
assert "".join(t for t, _ in h) == plain
assert [(t, k[1], k[2]) for t, k in h] == [("Bob ", None, False), ("says, ", 3, True), ("hell", 3, True), ("o", None, True), (" there", None, False)] or \
    "".join(t for t, k in h if k[1] == 3) == "says, hell"
assert sc.apply_highlight(P, 5, 5, fg=2) == P and sc.apply_highlight(P, 0, 99, fg=None) == P, "nothing to do"
assert "".join(t for t, _ in sc.apply_highlight(P, -5, 999, fg=1)) == plain, "out-of-range spans are clamped"

pc = sc.parse_colour_field
assert pc("") is None and pc(None) is None and pc("#FF8800") == "#ff8800" and pc("9") == 9 and pc(" 15 ") == 15
assert pc("red") == 1 and pc("Bright Cyan") == 14 and pc("bright white") == 15
for bad in ("16", "-1", "#fff", "purple", "bright", "٣", "1e1", "#gggggg"):
    try:
        pc(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("should reject %r" % bad)

v = sc.values_from_trigger(None)
v.update(name="T1", pattern="* tells you *", fg="red", hide=True, send="reply hi %1", beep=True, note="from %1", sample="Bob tells you 'x'")
trig, msg = sc.trigger_from_values(v)
assert trig and [a["type"] for a in trig["actions"]] == ["highlight", "gag", "send", "beep", "note"], msg
back = sc.values_from_trigger(trig)
assert back["fg"] == "1" and back["hide"] and back["send"] == "reply hi %1" and back["note"] == "from %1" and back["beep"]
assert sc.trigger_from_values(back)[0] == trig, "form -> trigger -> form is stable"
route = {"type": "route", "pane": "OOC", "gag": False}
tr2, _ = sc.trigger_from_values(dict(v, keep=[route])); assert any(a["type"] == "route" for a in tr2["actions"]), "unknown actions kept"
for bad_v, why in ((dict(v, name=""), "name"), (dict(v, pattern=""), "pattern"), (dict(v, fg="nope"), "colour"),
                   (dict(v, priority="x"), "priority"), (dict(v, regex=True, pattern="(a+)+$"), "unsafe regex"),
                   (dict(sc.values_from_trigger(None), name="n", pattern="x"), "no actions")):
    t, m = sc.trigger_from_values(bad_v)
    assert t is None and m, why

assert len(sc.trigger_presets()) == 14 and all(not p["enabled"] for p in sc.trigger_presets())

c = sc.clean_settings({"triggers": [trig, {"name": "bad"}, 5, None, dict(trig, pattern="(a+)+$", mode="regex")] * 300,
                       "alias_rules": "nope", "aliases": {"gg": "look;say hi $*", "x;y": "no", 5: "z"}, "hide_prompt": "yes"})
assert len(c["triggers"]) == 1 or len({t["name"] for t in c["triggers"]}) == 1
assert [a["name"] for a in c["alias_rules"]] == ["gg"] and c["alias_rules"][0]["body"] == "look;say hi %*", "legacy $* migrated"
assert c["hide_prompt"] is False
assert sc.clean_settings({"alias_rules": [{"name": "k", "body": "kill %1", "enabled": True}], "aliases": {"gg": "x"}})["alias_rules"][0]["name"] == "k"

# ============================== a fake game ====================================================================
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
PORT = srv.getsockname()[1]
conns, received = [], bytearray()
def accept():
    while True:
        try:
            c_, _ = srv.accept()
        except OSError:
            return
        conns.append(c_)
        def rd(c_=c_):
            try:
                while True:
                    d = c_.recv(4096)
                    if not d:
                        return
                    received.extend(d)
            except OSError:
                return
        threading.Thread(target=rd, daemon=True).start()
threading.Thread(target=accept, daemon=True).start()

tmp = tempfile.mkdtemp()
SETTINGS = os.path.join(tmp, "settings.json")
sc.SETTINGS_PATH = SETTINGS
sc.user_skin_dir = lambda: os.path.join(tmp, "skins")
json.dump({"aliases": {"gg": "look;say hi $*"}}, open(SETTINGS, "w"))      # an OLD settings file
root = tk.Tk()
root.geometry("1100x760+20+20")
app = sc.App(root)

def pump(secs=0.3):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)

def out():
    return app.out.get("1.0", "end-1c")

def type_line(text, wait=0.3):
    app.input.delete(0, "end"); app.input.insert(0, text); app._on_enter(None); pump(wait)

def key(w, keysym):
    w = getattr(w, "_cv", w)
    w.focus_force(); root.update(); w.event_generate("<Key>", keysym=keysym); pump(0.2)

def overlay():
    return app._overlay if app._overlay_open() else None

def tag_fg(word):
    i = app.out.search(word, "1.0")
    assert i, "not on screen: " + word
    for name in app.out.tag_names(i):
        if name.startswith("s"):
            return app.out.tag_cget(name, "foreground").lower()
    raise AssertionError("no style tag at " + word)

def set_triggers(*specs):
    lst = []
    for spec in specs:
        t = triggers.validate_trigger(spec); assert t, spec; lst.append(t)
    app.cfg["triggers"] = lst

def feed(text):
    app._on_data(text.encode() if isinstance(text, str) else text)

app.toggle_connection() if False else None
app.v_host.set("127.0.0.1"); app.v_port.set(str(PORT)); app.v_tls.set(False)
app.toggle_connection(); pump(1.0)
assert app.connected and conns
assert app.cfg["alias_rules"] and app.cfg["alias_rules"][0]["body"] == "look;say hi %*", "old aliases carried over at load"

# ============================== the line engine, no triggers ===================================================
feed("first line\n\rsecond line\n\r"); pump(0.05)
assert "first line\nsecond line\n" in out(), repr(out()[-60:])
feed("[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] ")
assert "[350/350DF" not in out(), "an unfinished line is held for a moment..."
assert app.statbar.data and app.statbar.data["hp"] == (350, 350, "DF"), "...but the stat bar sees it at once"
pump(0.3)
assert out().endswith("( )] "), "...then it is shown (nothing waits forever for a newline)"
type_line("look", wait=0.3)
assert "( )] look\n" in out(), "typing echoes after the prompt, on its line"
# the newline arrives later: the line is not duplicated or lost
feed("\n\rtext after the prompt\n\r"); pump(0.1)
assert out().count("[350/350DF") == 1 and "text after the prompt\n" in out()
# order is preserved when the client itself speaks while a server line is pending
feed("pending text"); app.system("client note"); pump(0.1)
assert out().index("pending text") < out().index("[client note]"), "server text first, then the client's"
feed("\n\r"); pump(0.1)
# clear() drops a half-collected line
feed("half a line"); app.clear(); feed(" and the rest\n\r"); pump(0.1)
assert "half a line" not in out() and "and the rest" in out()
app.clear()

# ============================== highlight ======================================================================
set_triggers({"name": "ooc", "mode": "plain", "pattern": "^[OOC]*", "actions": [{"type": "highlight", "fg": "#00ff00", "scope": "line"}]})
feed("[OOC] Bob: 'hello'\n\rnot a channel\n\r"); pump(0.1)
assert tag_fg("[OOC]") == tag_fg("hello") == "#00ff00" and tag_fg("not a") != "#00ff00"
app.clear()
set_triggers({"name": "bob", "mode": "plain", "pattern": "B*b", "actions": [{"type": "highlight", "bg": 4, "bold": True}]})
feed("Hi Bob and Rob\n\r"); pump(0.1)
def tag_bg(word):
    i = app.out.search(word, "1.0")
    assert i, word
    for name in app.out.tag_names(i):
        if name.startswith("s"):
            return app.out.tag_cget(name, "background").lower()
assert tag_bg("Bob") == app.theme["ansi"][4], "the matched text is highlighted"
assert tag_bg("Rob") == app.theme["bg"] and tag_bg("Hi ") == app.theme["bg"], "and only the matched text"
app.clear()
# split across network packets: still one line
set_triggers({"name": "ooc", "mode": "plain", "pattern": "^[OOC]*", "actions": [{"type": "highlight", "fg": "#00ff00", "scope": "line"}]})
feed("[OO"); feed("C] Bob: 'sp"); feed("lit'\n\r"); pump(0.1)
assert tag_fg("split") == "#00ff00"
app.clear()

# ============================== hide (gag), logging, priority / stop ==============================================
logpath = os.path.join(tmp, "game.log")
app.toggle_log(logpath); pump(0.1)
set_triggers({"name": "spam", "mode": "plain", "pattern": "* is spamming *", "actions": [{"type": "gag"}]})
feed("Joe is spamming the channel\n\rhello\n\r"); pump(0.1)
assert "spamming" not in out() and "hello" in out(), "the line is hidden from the screen"
app.toggle_log(); pump(0.1)
assert "Joe is spamming the channel" in open(logpath, encoding="utf-8").read(), "...but still in the log"
app.clear()
# a line already on screen (flushed as a prompt) cannot be hidden retroactively, but commands still run
received.clear()
set_triggers({"name": "late", "mode": "plain", "pattern": "waiting*", "actions": [{"type": "gag"}, {"type": "send", "text": "ack"}]})
feed("waiting"); pump(0.3); feed(" for you\n\r"); pump(0.3)
assert "waiting" in out() and b"ack\r\n" in bytes(received)
app.clear()
set_triggers({"name": "low", "mode": "plain", "pattern": "alpha", "priority": -5, "actions": [{"type": "highlight", "fg": "#33ccff"}]},
             {"name": "high", "mode": "plain", "pattern": "alpha", "priority": 5, "stop": True,
              "actions": [{"type": "highlight", "fg": "#ffcc00"}]})
feed("alpha\n\r"); pump(0.1)
assert tag_fg("alpha") == "#ffcc00", "higher priority first, and it stops the rest"
app.clear()

# ============================== send / beep / note / loop guard ======================================================
received.clear()
set_triggers({"name": "tell", "mode": "plain", "pattern": "* tells you *", "actions": [
    {"type": "send", "text": "reply thanks %1; look", "echo": True}, {"type": "note", "text": "tell from %1"}]})
feed("Bob tells you 'hi'\n\r"); pump(0.4)
rb = bytes(received)
assert b"reply thanks Bob\r\n" in rb and b"look\r\n" in rb, rb
assert "[tell from Bob]" in out() and "reply thanks Bob" in out(), "note and echoed command appear"
# game text can never add commands: a ';' in a capture is data, not a separator
received.clear()
feed("Mal;rm tells you 'x'\n\r"); pump(0.4)
assert b"reply thanks Mal;rm\r\n" in bytes(received) and b"\r\nrm\r\n" not in bytes(received), bytes(received)
# the guard stops a runaway
received.clear(); app.clear()
for i in range(60):
    feed("Bob tells you 'spam %d'\n\r" % i)
pump(0.6)
assert bytes(received).count(b"reply thanks Bob") <= 22 and "stopped: too many commands" in out()
# beep respects the bell setting
beeps = []
app.root.bell = lambda *a, **k: beeps.append(1)
set_triggers({"name": "ding", "mode": "plain", "pattern": "ding", "actions": [{"type": "beep"}]})
app.cfg["bell"] = True; feed("ding\n\r"); pump(0.1); assert len(beeps) == 1
app.cfg["bell"] = False; feed("ding\n\r"); pump(0.1); assert len(beeps) == 1
app.cfg["bell"] = True
# a trigger only ever sees the game's lines, not the client's own messages or your own typing
set_triggers({"name": "self", "mode": "plain", "pattern": "zzz", "actions": [{"type": "beep"}]})
n = len(beeps); app.system("zzz"); type_line("zzz"); assert len(beeps) == n
# disabled triggers are ignored; regex mode with %0 / named groups
set_triggers({"name": "off", "mode": "plain", "pattern": "ding", "enabled": False, "actions": [{"type": "beep"}]})
n = len(beeps); feed("ding\n\r"); pump(0.1); assert len(beeps) == n
received.clear()
set_triggers({"name": "rx", "mode": "regex", "pattern": r"(?P<who>\w+) gives you (\d+) coins", "actions": [
    {"type": "send", "text": "say thanks %{who}, %2 coins (%0)"}]})
feed("Zed gives you 30 coins\n\r"); pump(0.4)
assert b"say thanks Zed, 30 coins (Zed gives you 30 coins)" in bytes(received)
app.cfg["triggers"] = []

# ============================== hide the prompt line ====================================================================
app.clear(); app.cfg["hide_prompt"] = True
feed("\n\rYou walk north.\n\r[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] "); pump(0.4)
assert "You walk north." in out() and "[350/350" not in out(), "the prompt is kept off the screen"
assert app.statbar.data["hp"] == (350, 350, "DF"), "but the stat bar still has it"
feed("You see a door.\n\r"); pump(0.2)
assert "You see a door." in out() and "[350/350" not in out(), "text after a hidden prompt is shown"
feed("[200/350DF 0ST 0WN 0LG M:0 K:0 ( )] "); pump(0.4); feed("\n\r"); pump(0.1)
assert "[200/350" not in out() and app.statbar.data["hp"][0] == 200 and "\n\n\n" not in out(), repr(out())
# prompts that arrive in the same burst as the text (combat, operations) are hidden too
app.clear()
feed("[480/480DF 0ST 0WN 0LG M:35 K:0 (S 40/50:39/50)]\n\r"
     "[480/480DF 0ST 0WN 0LG M:20 K:0 (S 40/50:39/50)] You can move again.\n\r"
     "[480/480DF 0ST 0WN 0LG M:9 K:0 (S 40/50:39/50)] [480/480DF 0ST 0WN 0LG M:3 K:0 (S 40/50:39/50)] a woman charges.\n\r"
     "[OOC] Bob: 'hi'\n\r"); pump(0.4)
assert "480/480" not in out(), "no prompt text in the output: " + repr(out())
assert "You can move again.\na woman charges.\n[OOC] Bob: 'hi'" in out().replace("\n\n", "\n"), repr(out())
assert "\n\n\n" not in out()
assert app.statbar.data["hp"][0] == 480, "the bar still has it"
app.cfg["hide_prompt"] = False
feed("[100/350DF 0ST 0WN 0LG M:0 K:0 ( )] "); pump(0.4)
assert "[100/350DF" in out(), "shown again when the option is off"
app.clear()

# ============================== aliases ===================================================================================
received.clear()
type_line("gg there", wait=0.4)
assert b"look\r\nsay hi there\r\n" in bytes(received)
received.clear(); type_line("GG", wait=0.3); assert b"look\r\nsay hi \r\n" in bytes(received) or b"say hi\r\n" in bytes(received)
app.cfg["alias_rules"][0]["enabled"] = False
received.clear(); type_line("gg x", wait=0.3); assert b"gg x\r\n" in bytes(received), "a disabled alias is ordinary text"
app.cfg["alias_rules"][0]["enabled"] = True
type_line("/alias k kill %1; flee"); assert any(a["name"] == "k" for a in app.cfg["alias_rules"])
received.clear(); type_line("k orc", wait=0.4); assert b"kill orc\r\nflee\r\n" in bytes(received)
type_line("/alias b@d x"); assert "Usage" in out() and all(a["name"] != "b@d" for a in app.cfg["alias_rules"])
type_line("/aliases"); assert "k = kill %1; flee" in out()
type_line("/unalias K"); assert all(a["name"] != "k" for a in app.cfg["alias_rules"])
assert json.load(open(SETTINGS))["alias_rules"][0]["name"] == "gg"

# ============================== the ordinary managers (normal look) =======================================================
errors, asked = [], []
sc.messagebox.showerror = lambda *a, **k: errors.append(a)
sc.messagebox.showinfo = lambda *a, **k: errors.append(a)
sc.messagebox.askyesno = lambda *a, **k: (asked.append(a) or True)
app.cfg["triggers"] = []
app.input.focus_force(); root.update()
app.input.delete(0, "end"); app.input.insert(0, "abc")
app.input.event_generate("<Control-t>"); pump(0.3)
win = app._trig_win; assert win is not None and win.winfo_exists(), "Ctrl+T opens the trigger manager"
assert app.input.get() == "abc", "and Ctrl+T does not transpose the typed text"
assert app.open_triggers() is win
A = win._actions
A["add_preset"](sc.trigger_presets()[0]); pump(0.1)
assert len(app.cfg["triggers"]) == 1 and app.cfg["triggers"][0]["enabled"] is True, "a preset is added switched on"
assert "[x]" in A["listbox"].get(0) and "Highlight OOC" in A["listbox"].get(0)
A["add_preset"](sc.trigger_presets()[0]); pump(0.1); assert len(app.cfg["triggers"]) == 1 and errors, "duplicate refused"
A["toggle"](); assert app.cfg["triggers"][0]["enabled"] is False and "[ ]" in A["listbox"].get(0)
A["edit"](None); pump(0.2)
form = [w for w in win.winfo_children() if isinstance(w, tk.Toplevel)][0]
sv, bv = form._vars
sv["name"].set("Gold"); sv["pattern"].set("You find * gold"); sv["fg"].set("bright yellow"); sv["sample"].set("You find 12 gold")
bv["beep"].set(True); sv["note"].set("got %1"); pump(0.2)
assert "Matched" in form._result.cget("text") and "%1=12" in form._result.cget("text"), form._result.cget("text")
sv["fg"].set("notacolour"); pump(0.1); assert "colour" in form._result.cget("text").lower()
sv["fg"].set("bright yellow"); bv["regex"].set(True); sv["pattern"].set("(a+)+$"); pump(0.1)
assert "Matched" not in form._result.cget("text"), "an unsafe regex is reported"
bv["regex"].set(False); sv["pattern"].set("You find * gold"); form._ok(); pump(0.2)
assert [t["name"] for t in app.cfg["triggers"]] == ["Highlight OOC channel", "Gold"]
A["listbox"].selection_clear(0, "end"); A["listbox"].selection_set(1); A["edit"](1); pump(0.2)
form = [w for w in win.winfo_children() if isinstance(w, tk.Toplevel)][0]
assert form._vars[0]["name"].get() == "Gold" and form._vars[0]["fg"].get() == "11"
form.destroy()
A["listbox"].selection_clear(0, "end"); A["listbox"].selection_set(1); A["delete"](); assert asked and len(app.cfg["triggers"]) == 1
win.destroy(); pump(0.1)
# aliases
app.input.event_generate("<Alt-a>"); pump(0.3)                  # (Ctrl+A selects the entry line; aliases are Alt+A)
aw = app._alias_win; assert aw is not None and aw.winfo_exists()
AA = aw._actions; assert "gg" in AA["listbox"].get(0)
AA["edit"](None); pump(0.2)
form = [w for w in aw.winfo_children() if isinstance(w, tk.Toplevel)][0]
form._vars[0]["name"].set("hh"); form._vars[0]["body"].set("heal %1"); form._vars[0]["sample"].set("bob"); pump(0.2)
assert "heal bob" in form._result.cget("text"); form._ok(); pump(0.2)
assert any(a["name"] == "hh" for a in app.cfg["alias_rules"])
aw.destroy()

# ============================== the DOS look ===========================================================================================
app.cfg["triggers"] = []
app.set_dos_mode(True); pump(0.6)
app.input.focus_force(); root.update(); app.input.event_generate("<Control-t>"); pump(0.3)
table = overlay(); assert isinstance(table, dosui.DosTable), "Ctrl+T opens the DOS trigger directory"
assert table.row_count == 0
key(table, "p"); pm = overlay(); assert isinstance(pm, dosui.DosMenu)
key(pm, "1"); pump(0.4)
assert len(app.cfg["triggers"]) == 1 and app.cfg["triggers"][0]["name"] == "Highlight OOC channel"
table = overlay(); assert isinstance(table, dosui.DosTable) and table.row_count == 1, "back in the directory"
key(table, "space"); assert app.cfg["triggers"][0]["enabled"] is False
key(table, "space"); assert app.cfg["triggers"][0]["enabled"] is True
# add (two pages)
key(table, "a"); d = overlay(); assert isinstance(d, dosui.DosDialog)
ents = {f["key"]: f for f in d._fields}
for k_, v_ in (("name", "Tell beep"), ("pattern", "* tells you *"), ("sample", "Al tells you 'x'")):
    e = ents[k_]["entry"]; e.delete(0, "end"); e.insert(0, v_)
key(ents["sample"]["entry"], "Return"); pump(0.4)                    # first button: "Actions >"
d2 = overlay(); assert isinstance(d2, dosui.DosDialog) and "send" in {f["key"] for f in d2._fields}
ents2 = {f["key"]: f for f in d2._fields}
e = ents2["note"]["entry"]; e.delete(0, "end"); e.insert(0, "from %1")
e = ents2["send"]["entry"]; e.delete(0, "end"); e.insert(0, "reply hi %1")
key(ents2["note"]["entry"], "Return"); pump(0.5)                      # first button: "Save"
assert [t["name"] for t in app.cfg["triggers"]] == ["Highlight OOC channel", "Tell beep"], app.cfg["triggers"]
assert [a["type"] for a in app.cfg["triggers"][1]["actions"]] == ["send", "note"]
table = overlay(); assert isinstance(table, dosui.DosTable) and table.row_count == 2 and table.selected == 1
# a bad trigger keeps you in the form, with your entries
key(table, "a"); d = overlay(); ents = {f["key"]: f for f in d._fields}
for k_, v_ in (("name", "Broken"), ("pattern", "x")):
    e = ents[k_]["entry"]; e.delete(0, "end"); e.insert(0, v_)
key(ents["name"]["entry"], "Return"); pump(0.4)                       # to page 2 ...
d2 = overlay(); key({f["key"]: f for f in d2._fields}["note"]["entry"], "Return"); pump(0.4)   # ... save with no action
assert len(app.cfg["triggers"]) == 2 and "action" in out().lower(), "needs at least one action"
d3 = overlay(); assert isinstance(d3, dosui.DosDialog)
key(d3, "Escape"); pump(0.4)
# edit, remove with a confirmation
table = overlay(); table.select(1); key(table, "Return"); d = overlay()
assert {f["key"]: f for f in d._fields}["name"]["entry"].get() == "Tell beep"
key(d, "Escape"); pump(0.4)
table = overlay(); table.select(1); key(table, "Delete"); key(overlay(), "n"); pump(0.4); assert len(app.cfg["triggers"]) == 2
table = overlay(); table.select(1); key(table, "Delete"); key(overlay(), "y"); pump(0.5); assert len(app.cfg["triggers"]) == 1
key(overlay(), "Escape")
# the live line engine works in the DOS look as well
feed("[OOC] Bob: 'dos'\n\r"); pump(0.1)
assert tag_fg("dos") == app.theme["ansi"][14], "the OOC highlight trigger works in the DOS look too"
# aliases
app.input.focus_force(); root.update(); app.input.event_generate("<Alt-a>"); pump(0.3)
table = overlay(); assert isinstance(table, dosui.DosTable) and table.row_count >= 1
key(table, "a"); d = overlay(); ents = {f["key"]: f for f in d._fields}
for k_, v_ in (("name", "zz"), ("body", "say z %*")):
    e = ents[k_]["entry"]; e.delete(0, "end"); e.insert(0, v_)
key(ents["body"]["entry"], "Return"); pump(0.5)
assert any(a["name"] == "zz" for a in app.cfg["alias_rules"])
key(overlay(), "Escape")
# the main menu lists both
app.dos_main_menu(); pump(0.2); m = overlay()
key(m, "t"); assert isinstance(overlay(), dosui.DosTable), "the main menu opens the trigger directory"
key(overlay(), "Escape")
# hide-the-prompt is a menu option in both looks
app.cfg["hide_prompt"] = False
app.dos_options_menu(); o = overlay(); assert isinstance(o, dosui.DosMenu)
key(o, "h"); pump(0.3)
assert app.cfg["hide_prompt"] is True and app.v_hideprompt.get() is True
key(overlay(), "h"); pump(0.3)
assert app.cfg["hide_prompt"] is False and app.v_hideprompt.get() is False
key(overlay(), "Escape")
app.set_dos_mode(False); pump(0.3)
app.v_hideprompt.set(True); app.cfg.update(hide_prompt=app.v_hideprompt.get()); assert app.cfg["hide_prompt"] is True
app.cfg["hide_prompt"] = False

root.update(); root.destroy()
print("rules tests OK")
