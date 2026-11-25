"""Clone worlds, aliases, triggers and buttons; leave my commands out of the log; copy without my commands;
no gap where a hidden message was (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import triggers as T
import tkinter as tk

# ---- names for copies -----------------------------------------------------------------------------------------------
assert T.copy_name("Tells", ["Tells"]) == "Tells copy"
assert T.copy_name("Tells", ["tells", "TELLS COPY"]) == "Tells copy 2"
assert T.copy_name("Tells", ["Tells", "Tells copy", "Tells copy 2"]) == "Tells copy 3"
assert T.copy_name("tm", ["tm"], words=False) == "tm2" and T.copy_name("tm", ["tm", "tm2"], words=False) == "tm3"
long = "x" * 40
c = T.copy_name(long, [long], 40)
assert len(c) <= 40 and c.endswith(" copy") and c != long
assert len(T.copy_name("y" * 24, ["y" * 24], 24)) <= 24

# ---- in the app ---------------------------------------------------------------------------------------------------------
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


def type_main(text):
    app.input.delete(0, "end"); app.input.insert(0, text)
    app.input.event_generate("<Return>"); pump(0.3)


def screen():
    return app.out.get("1.0", "end-1c")


pump(0.5)

# triggers: the copy sits right under the original, switched off, with its own name; the original is untouched
app.cfg["triggers"] = [
    {"name": "A", "mode": "plain", "pattern": "x", "enabled": True, "priority": 0, "actions": [{"type": "send", "text": "look", "echo": True}]},
    {"name": "B", "mode": "plain", "pattern": "y", "enabled": True, "priority": 0, "actions": [{"type": "beep"}]}]
ok, msg, j = app.clone_rule("trigger", 0)
assert ok and j == 1 and "A copy" in msg and "switched off" in msg, (ok, msg, j)
names = [t["name"] for t in app.cfg["triggers"]]
assert names == ["A", "A copy", "B"], names
assert app.cfg["triggers"][0]["enabled"] is True and app.cfg["triggers"][1]["enabled"] is False
assert app.cfg["triggers"][1]["actions"] == app.cfg["triggers"][0]["actions"]
app.cfg["triggers"][1]["actions"][0]["text"] = "changed"
assert app.cfg["triggers"][0]["actions"][0]["text"] == "look", "a copy, not the same object"
assert app.clone_rule("trigger", 0)[1].startswith("Cloned as 'A copy 2'")
assert app.clone_rule("trigger", 99)[0] is False and app.clone_rule("trigger", None)[0] is False

# aliases keep to one word and stay on
app.cfg["alias_rules"] = [{"name": "tm", "body": "text Mara %*", "enabled": True}]
ok, msg, j = app.clone_rule("alias", 0)
assert ok and j == 1 and app.cfg["alias_rules"][1]["name"] == "tm2" and app.cfg["alias_rules"][1]["body"] == "text Mara %*"
assert app.cfg["alias_rules"][1]["enabled"] is True
# multi-word alias names too
app.cfg["alias_rules"] = [{"name": "go home", "body": "recall", "enabled": True}]
ok, msg, j = app.clone_rule("alias", 0)
assert ok and app.cfg["alias_rules"][1]["name"] == "go home2", app.cfg["alias_rules"]
# what was saved is what is on disk
saved = __import__("json").load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert [a["name"] for a in saved["alias_rules"]] == ["go home", "go home2"]

# worlds
app.cfg["worlds"] = [{"name": "Duskholm", "host": "example.org", "port": 4000, "tls": True, "note": "main", "last": 1700000000},
                     {"name": "Other", "host": "other.example", "port": 23, "tls": False, "note": "", "last": 0}]
ok, msg, j = app.clone_world(0)
w = app.cfg["worlds"]
assert ok and j == 1 and [x["name"] for x in w] == ["Duskholm", "Duskholm copy", "Other"], w
assert w[1]["host"] == "example.org" and w[1]["port"] == 4000 and w[1]["tls"] is True and w[1]["note"] == "main"
assert w[1]["last"] == 0 and w[0]["last"] == 1700000000
assert app.clone_world(5)[0] is False

# buttons: the label changes, the hotkey is not copied
app.cfg["buttons"] = []
app._local("/button add Fly = shift fly"); app._local("/button key Fly Alt-F7"); pump(0.2)
assert app.cfg["buttons"][0]["key"], app.cfg["buttons"]
ok, msg, j = app.clone_button(0)
b = app.cfg["buttons"]
assert ok and j == 1 and [x["name"] for x in b] == ["Fly", "Fly copy"] and b[1]["key"] == "" and b[0]["key"]
assert b[1]["body"] == "shift fly" and "no hotkey" in msg
assert app.clone_button(0)[1].startswith("Cloned as 'Fly copy 2'")
assert app.clone_button(9)[0] is False

# the windows have a Clone button / key, in both looks
app.cfg["triggers"] = [dict(app.cfg["triggers"][0])]
win = app.open_triggers(); pump(0.3)
win._actions["listbox"].selection_clear(0, "end"); win._actions["listbox"].selection_set(0)
win._actions["clone"](); pump(0.2)
assert [t["name"] for t in app.cfg["triggers"]] == ["A", "A copy"]
assert [c.cget("text") for f in win.winfo_children() if isinstance(f, tk.Frame) for c in f.winfo_children()
        if isinstance(c, tk.Button)].count("Clone") == 1
win.destroy()
app.cfg["worlds"] = app.cfg["worlds"][:1]
win = app.open_worlds(); pump(0.3)
win._actions["listbox"].selection_clear(0, "end"); win._actions["listbox"].selection_set(0)
win._actions["clone"](); pump(0.2)
assert [x["name"] for x in app.cfg["worlds"]] == ["Duskholm", "Duskholm copy"]
win.destroy()
bw = app.open_buttons(); pump(0.3)
bw._list.selection_clear(0, "end"); bw._list.selection_set(0)
bw._clone(); pump(0.2)
n = len(app.cfg["buttons"])
bw._clone(); pump(0.2)
assert len(app.cfg["buttons"]) == n + 1 and app.cfg["buttons"][1]["name"].startswith("Fly copy")
bw.destroy()

app.set_dos_mode(True); pump(0.6)
for opener, hint_has in ((lambda: app.dos_rules("trigger"), "Clone"), (lambda: app.dos_rules("alias"), "Clone"),
                         (app.dos_worlds, "Clone"), (app.dos_buttons, "Clone")):
    app.cfg["alias_rules"] = [{"name": "tm", "body": "x", "enabled": True}]
    tbl = opener(); pump(0.3)
    assert any("Clone" in str(h) for h in tbl._hints), tbl._hints
    before = {"trigger": len(app.cfg["triggers"]), "worlds": len(app.cfg["worlds"]), "buttons": len(app.cfg["buttons"]),
              "alias": len(app.cfg["alias_rules"])}
    tbl._on_key(type("E", (), {"keysym": "c", "char": "c", "state": 0})()); pump(0.3)
    after = {"trigger": len(app.cfg["triggers"]), "worlds": len(app.cfg["worlds"]), "buttons": len(app.cfg["buttons"]),
             "alias": len(app.cfg["alias_rules"])}
    assert sum(after.values()) == sum(before.values()) + 1, (before, after)
    tbl.close(); pump(0.2)
app.set_dos_mode(False); pump(0.6)

# ---- my commands in the log --------------------------------------------------------------------------------------
path = os.path.join(tempfile.mkdtemp(), "log.txt")
app.logfile = open(path, "a", encoding="utf-8")
assert app.cfg["log_echo"] is True, "on by default: the log has always had them"
type_main("look")
app._on_data(("You see a room." + CR).encode()); pump(0.5)
app.logfile.flush(); text = open(path, encoding="utf-8").read()
assert "look" in text and "You see a room." in text, text
app._set_extra("log_echo", False)
type_main("north")
app._on_data(("You go north." + CR).encode()); pump(0.5)
app.system("a client note"); pump(0.2)
app.logfile.flush(); text = open(path, encoding="utf-8").read()
assert "north" not in text.replace("You go north.", ""), "my command is left out"
assert "You go north." in text and "a client note" in text, "the game's text and the client's notes stay"
assert "north" in screen(), "it is still on screen"
app._set_extra("log_echo", True)
type_main("south")
app.logfile.flush(); assert "south" in open(path, encoding="utf-8").read()
app.logfile.close(); app.logfile = None
assert sc.clean_settings({"host": "x", "log_echo": "no"})["log_echo"] is True
assert any(k == "log_echo" for k, *_ in sc.EXTRA_BOOLS)

# ---- copy without my commands -------------------------------------------------------------------------------------------
app.clear()
type_main("look")
app._on_data(("Kitchen" + CR + "A tidy room." + CR).encode()); pump(0.5)
type_main("get cup")
app._on_data(("You get a cup." + CR).encode()); pump(0.5)
app.out.tag_add("sel", "1.0", "end-1c")
assert "look" in app.out.get("sel.first", "sel.last")
got = app.copy_without_echo(app.out)
assert got == "Kitchen\nA tidy room.\nYou get a cup.\n", repr(got)
assert root.clipboard_get() == got
# part of it: a command at the start of the selection is left out too
app.out.tag_remove("sel", "1.0", "end")
app.out.tag_add("sel", "1.2", "3.4")
part = app.selection_without_echo(app.out)
assert part == "Kitchen\nA ti" and app.copy_without_echo(app.out) == part, repr(part)
# nothing selected
app.out.tag_remove("sel", "1.0", "end")
assert app.copy_without_echo(app.out) is None and app.selection_without_echo(app.out) == ""
app._local("/copyplain"); pump(0.2)
assert "Nothing is selected" in screen()
app.out.tag_add("sel", "1.0", "end-1c"); app._local("/copyplain"); pump(0.2)
assert "Copied, without the commands you sent." in screen() and root.clipboard_get().startswith("Kitchen")
# the menu offers it on the main text, only there
menus = []
app._popup_menu = lambda m, x, y: menus.append(m)
app.out.event_generate("<Button-3>", x=5, y=5); pump(0.2)
m = menus[-1]
labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) == "command"]
assert "Copy without my commands" in labels, labels
m.invoke(labels.index("Copy without my commands")); pump(0.2)
assert "get cup" not in root.clipboard_get()

# ---- no gap where a hidden message was ---------------------------------------------------------------------------------------
app.clear()
app.cfg["triggers"] = [{"name": "g", "mode": "plain", "pattern": "*spam*", "enabled": True, "priority": 0, "actions": [{"type": "gag"}]}]
app._on_data(("Before." + CR + CR + "some spam here" + CR + CR + "After." + CR).encode()); pump(0.6)
assert screen() == "Before.\n\nAfter.\n", repr(screen())
# a message with no blank line round it leaves nothing behind either
app.clear()
app._on_data(("One." + CR + "spam two" + CR + "Three." + CR).encode()); pump(0.5)
assert screen() == "One.\nThree.\n", repr(screen())
# the game's own blank line after a message that was NOT hidden stays, and so does one that comes first
app.clear()
app._on_data((CR + "spam" + CR + CR + "Next." + CR + CR + "Last." + CR).encode()); pump(0.6)
assert screen() == "\nNext.\n\nLast.\n", repr(screen())
# several hidden messages in a row: one blank line survives
app.clear()
app._on_data(("Top." + CR + CR + "spam a" + CR + CR + "spam b" + CR + CR + "Bottom." + CR).encode()); pump(0.6)
assert screen() == "Top.\n\nBottom.\n", repr(screen())
# only ONE blank line is dropped: a real blank run after the message keeps the rest
app.clear()
app._on_data(("Top." + CR + CR + "spam" + CR + CR + CR + "Bottom." + CR).encode()); pump(0.6)
assert screen() == "Top.\n\n\nBottom.\n", repr(screen())
# and the hidden text still reaches the log
path = os.path.join(tempfile.mkdtemp(), "log2.txt")
app.logfile = open(path, "a", encoding="utf-8")
app._on_data(("Top." + CR + CR + "spam" + CR + CR + "Bottom." + CR).encode()); pump(0.6)
app.logfile.close(); app.logfile = None
assert open(path, encoding="utf-8").read() == "Top.\n\nspam\n\nBottom.\n", repr(open(path, encoding="utf-8").read())

root.update(); root.destroy()
print("clone and echo tests OK")
