"""Time stamps: optional in the main text, optional for each capture pane (no network)."""
import os, re, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import stamps
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")
CR = chr(13) + chr(10)
HM = r"\[\d\d:\d\d\] "
HMS = r"\[\d\d:\d\d:\d\d\] "


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def feed(*lines):
    for l in lines:
        app._on_data((l + CR).encode()); pump(0.25)


def out():
    return app.out.get("1.0", "end-1c")


def pane(name):
    return app._panes[name.lower()]["text"].get("1.0", "end-1c")


pump(0.4)
app.connected = True
# ---- the pure helpers --------------------------------------------------------------------------
assert stamps.split_pane_name("OOC (time)") == ("OOC", True) and stamps.split_pane_name("OOC  (TS) ") == ("OOC", True)
assert stamps.split_pane_name("OOC") == ("OOC", False) and stamps.split_pane_name("Out of (time) bounds") == ("Out of (time) bounds", False)
assert sc.clean_settings({"host": "x", "timestamps": "hh:mm"})["timestamps"] == "hh:mm"
assert sc.clean_settings({"host": "x", "timestamps": "nonsense"})["timestamps"] == "off"
assert sc.clean_settings({"host": "x"})["timestamps"] == "off", "off by default"

# ---- the main text -------------------------------------------------------------------------------
feed("Hello there")
assert re.search(r"^Hello there$", out(), re.M) and not re.search(HM, out()), "no stamps unless asked"
app._set_extra("timestamps", "hh:mm")
feed("Second line", "", "Third line")
assert re.search("^" + HM + "Second line$", out(), re.M), out()[-120:]
assert re.search("^" + HM + "Third line$", out(), re.M)
assert not re.search(HM + "$", out(), re.M) and "\n\n" in out().replace("\n\n\n", "\n\n"), "a blank line stays blank"
assert re.search("^Hello there$", out(), re.M), "earlier lines are not changed"
app._set_extra("timestamps", "hh:mm:ss")
feed("With seconds")
assert re.search("^" + HMS + "With seconds$", out(), re.M)
# the stamp is dim, like the game's own dim text is not: it carries a colour tag of its own
pos = app.out.search("With seconds", "1.0")
stamp_pos = app.out.search("[", pos + "-12c", pos)
assert app.out.tag_names(stamp_pos), "the stamp has its own style"
# a line that arrives in two pieces is stamped once, at its start
app._on_data(b"first half "); pump(0.4)
app._on_data(b"second half" + CR.encode()); pump(0.3)
assert re.search("^" + HMS + "first half second half$", out(), re.M), out()[-100:]
assert len(re.findall("first half", out())) == 1 and not re.search("first half " + HMS, out())
# a bare prompt is not stamped; a line that follows it is
feed("[100/100DF 0ST 0WN 0LG M:0 K:0 ( )]")
assert re.search(r"^\[100/100DF 0ST 0WN 0LG M:0 K:0 \( \)\]$", out(), re.M), "prompts carry no stamp"
# triggers and the screen reader see the line as the game sent it, without a stamp
hits = []
app.cfg["triggers"] = [{"name": "t", "mode": "regex", "pattern": r"^Ping (?P<n>\d+)$", "enabled": True, "priority": 0,
                        "actions": [{"type": "note", "text": "got %{n}"}]}]
feed("Ping 7")
assert "got 7" in out() and re.search("^" + HMS + "Ping 7$", out(), re.M), "an anchored trigger still matches"
app.cfg["triggers"] = []
# echo and the client's own messages are not stamped
app.system("client message")
assert not re.search(HMS + r"\[client message\]", out()) and "[client message]" in out()
app._set_extra("timestamps", "off")
feed("after off")
assert re.search("^after off$", out(), re.M)

# ---- panes: each on its own -------------------------------------------------------------------------
app.cfg["triggers"] = [{"name": "tells", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "Tells"}]},
                       {"name": "ooc", "mode": "plain", "pattern": "[OOC]*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "OOC"}]}]
feed("Goose tells you 'one'", "[OOC] Bob: 'hi'")
assert "one" in pane("tells") and "Bob" in pane("ooc")
assert not re.search(HM, pane("tells")) and not re.search(HM, pane("ooc")), "off for panes by default"
app._local("/stamps tells on"); pump(0.2)
feed("Goose tells you 'two'", "[OOC] Bob: 'again'")
assert re.search(HM + r"Goose tells you 'two'", pane("tells")), pane("tells")
assert not re.search(HM, pane("ooc").split("hi")[-1]), "the other pane is untouched"
app._set_extra("timestamps", "hh:mm:ss")
feed("Goose tells you 'three'")
assert re.search(HMS + r"Goose tells you 'three'", pane("tells")), "a stamping pane follows the main format"
app._local("/stamps tells off"); pump(0.2)
feed("Goose tells you 'four'")
assert not re.search(HMS + r"Goose tells you 'four'", pane("tells")) and "four" in pane("tells")
# the Panes / layout form: (time) after a name
app._set_extra("timestamps", "off")
lay, defs, msg = app._panes_parse(["right 40 OOC (time), Tells"])
assert msg == "OK" and {d["name"]: d["timestamps"] for d in defs} == {"OOC": True, "Tells": False}, (msg, defs)
assert lay["regions"][0]["panes"] == ["OOC", "Tells"], "the suffix is not part of the name"
ok, m = app._panes_save(["right 40 OOC (time), Tells"]); assert ok, m
assert app._find_pane_def("ooc")["timestamps"] is True and app._find_pane_def("tells")["timestamps"] is False
assert "OOC (time), Tells" in app._pane_lines()[0], app._pane_lines()
feed("[OOC] Bob: 'stamped'")
assert re.search(HM + r"\[OOC\] Bob: 'stamped'", pane("ooc")), "stamps with the main text off use HH:MM"
ok, m = app._panes_save(["right 40 OOC, Tells"]); assert ok
assert app._find_pane_def("ooc")["timestamps"] is False and "(time)" not in app._pane_lines()[0]
# saved and read back
import json
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert all(p["timestamps"] is False for p in saved["panes"])
app._local("/stamps ooc on")
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert [p["timestamps"] for p in saved["panes"] if p["name"] == "OOC"] == [True]

# ---- the command and the option ---------------------------------------------------------------------
app._local("/stamps"); pump(0.2)
assert "main text off" in out() and "OOC (time)" in out()
app._local("/stamps main seconds"); assert app.cfg["timestamps"] == "hh:mm:ss"
app._local("/stamps main on"); assert app.cfg["timestamps"] == "hh:mm"
app._local("/stamps main off"); assert app.cfg["timestamps"] == "off"
app._local("/stamps main sometimes"); pump(0.2)
assert "Say how" in out() and app.cfg["timestamps"] == "off"
app._local("/stamps nosuchpane on"); pump(0.2)
assert "No pane called 'nosuchpane'" in out()
app._local("/stamps ooc maybe"); pump(0.2)
assert "Say /stamps" in out()
# the DOS Options menu has it, and cycling it works
app.set_dos_mode(True); pump(0.5)
menu = app.dos_options_menu(); pump(0.3)
labels = [i["label"] for i in menu._items if i]
assert any(l.startswith("Time stamps (main text): off") for l in labels), labels
app.dos_close_overlay(); app._cycle_choice("timestamps", ("off", "hh:mm", "hh:mm:ss")); pump(0.4)
assert app.cfg["timestamps"] == "hh:mm"
app.dos_close_overlay()
feed("in dos")
assert re.search("^" + HM + "in dos$", out(), re.M)
app.set_dos_mode(False); pump(0.3)

root.update(); root.destroy()
print("time stamp tests OK")
