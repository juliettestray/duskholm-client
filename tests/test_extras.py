"""Timers, clock, notepad, moon window and hotkeys (pure parts first, then the window)."""
import calendar, datetime, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import extras
import moon


def utc(*a):
    return calendar.timegm(datetime.datetime(*a).timetuple())


# ---- reading times
now = 1_700_000_000.0
pw = extras.parse_when
assert pw("10m", now) == (now + 600, "after") and pw("1h30m", now)[0] == now + 5400 and pw("90s", now)[0] == now + 90
assert pw("45", now)[0] == now + 2700 and pw("2d", now)[0] == now + 172800 and pw("1d2h3m4s", now)[0] == now + 93784
for bad in ("", "abc", "0s", "-5m", "99d", "25:00", "12:99", "13pm", "10 minutes", None, "game", "game 25:00", "1e3"):
    try:
        pw(bad, now)
        assert False, bad
    except ValueError:
        pass
# local clock: next occurrence of that wall time
loc = datetime.datetime.fromtimestamp(now)
tgt = loc.replace(hour=(loc.hour + 2) % 24, minute=0, second=0, microsecond=0)
due, kind = pw("%02d:00" % tgt.hour, now)
assert kind == "local" and 0 < due - now <= 86400 and datetime.datetime.fromtimestamp(due).minute == 0
assert pw("at 9:30pm", now)[1] == "local" and pw("9pm", now)[1] == "local"
# game clock: Eastern. 2024-03-20 12:00 UTC is 08:00 EDT, so game 21:30 is 13h30 away
t0 = utc(2024, 3, 20, 12)
due, kind = pw("game 21:30", t0)
assert kind == "game" and abs((due - t0) - 13.5 * 3600) < 1, (due - t0)
due, _ = pw("et 7am", t0)                                    # already past today: tomorrow 07:00 EDT
assert abs((due - t0) - 23 * 3600) < 1
due, _ = pw("game 21:30", utc(2024, 1, 20, 12))             # winter: 07:00 EST now -> 14h30
assert abs((due - utc(2024, 1, 20, 12)) - 14.5 * 3600) < 1
assert extras.countdown(0) == "0:00" and extras.countdown(61) == "1:01" and extras.countdown(3725) == "1:02:05"
assert extras.countdown(0.2) == "0:01"

# ---- hotkeys
ph = extras.parse_hotkey
assert ph("Ctrl-T") == ("<Control-t>", "Ctrl-T") and ph("alt+m") == ("<Alt-m>", "Alt-M") and ph("F9") == ("<F9>", "F9")
assert ph("ctrl alt x") == ("<Control-Alt-x>", "Ctrl-Alt-X") and ph("Shift-F2")[0] == "<Shift-F2>"
for bad in ("", "t", "Shift-T", "Ctrl-", "Ctrl-C", "Ctrl-V", "Alt-F4", "Ctrl-5", "Alt-0", "Hyper-T", "Ctrl-ab",
            "Ctrl-Ctrl-T", "Ctrl-é", None, "F13"):
    try:
        ph(bad)
        assert False, bad
    except ValueError:
        pass
assert extras.clean_keys({"moon": "Ctrl-M", "triggers": "Ctrl-T", "bogus": "Ctrl-Q"}) == {"moon": "Ctrl-M"}
assert extras.clean_keys({"moon": "Ctrl-T"}) == {}, "a clash with another action's key drops the lot"
assert extras.clean_keys({"moon": "Ctrl-M", "notepad": "Ctrl-M"}) == {}
assert extras.clean_keys("x") == {} and extras.clean_keys({"moon": 5}) == {}
eff = extras.effective_keys({"moon": "Ctrl-M"})
assert eff["moon"] == ("<Control-m>", "Ctrl-M") and eff["triggers"][1] == "Ctrl-T"

# ---- the window
import sanctuary as sc
import dosui
import tkinter as tk

home = tempfile.mkdtemp()
os.environ["USERPROFILE"] = os.environ["HOME"] = home
sc.SETTINGS_PATH = os.path.join(home, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


app.connected = True; app._online_since = time.time()
bells = []
app.root.bell = lambda *a, **k: bells.append(1)

# timers
ok, msg = app.add_timer("2s", "tea")
assert ok and app.timer_segment().startswith("tea 0:0"), app.timer_segment()
assert not app.add_timer("nonsense", "x")[0]
app.cfg["clock"] = "off"
pump(2.8)
assert not app._timers and bells and "Time's up: tea" in app.out.get("1.0", "end")
assert app._notice_text == "Time's up: tea"
app.add_timer("1h", "a"); app.add_timer("2h", "b")
assert "1." in app.list_timers() and app.cancel_timer(1).startswith("Cancelled a") and len(app._timers) == 1
assert app.cancel_timer(9) == "There is no timer 9." and app.cancel_timer() == "All timers cancelled." and app.cancel_timer() == "There are no timers."
for i in range(extras.MAX_TIMERS):
    app.add_timer("1h", "t%d" % i)
assert not app.add_timer("1h", "over")[0]
app._timers.clear()
app._local("/timer 5m stretch your legs"); assert app._timers[0]["label"] == "stretch your legs"
app._local("/timer game 21:30 dinner"); assert app._timers[1]["kind"] == "game" and app._timers[1]["label"] == "dinner"
app._local("/timer cancel 2"); assert len(app._timers) == 1
app._local("/timer list"); app._local("/timer bogus")
app.open_timers().destroy()

# clock
app._set_extra("clock", "real"); pump(1.2)
assert app.clock_label.cget("text") == time.strftime("%H:%M")
app._set_extra("clock", "game"); pump(1.2)
assert app.clock_label.cget("text").endswith(("EDT", "EST")), app.clock_label.cget("text")
app.set_dos_mode(True); pump(0.5)
assert app.clock_text().split()[0] in app._dos_segments(200)[1] and "Timer" in " ".join(x[0] for x in app._dos_segments(200)[0])
app._set_extra("clock", "off"); pump(0.3)
assert app.clock_text() == "" and app.clock_label.cget("text") == ""

# notepad (in both looks)
assert app._notepad is None
app.toggle_notepad(); pump(0.3)
assert app._notepad and app._notepad["frame"].winfo_ismapped()
app._notepad["text"].insert("end", "remember the milk\n")
assert app.save_notes() and open(app.notes_path(), encoding="utf-8").read() == "remember the milk\n"
app.toggle_notepad(); pump(0.2)
assert app._notepad is None
app.set_dos_mode(False); pump(0.3)
app.toggle_notepad(); pump(0.3)
assert "remember the milk" in app._notepad["text"].get("1.0", "end"), "notes come back"
app._notepad["text"].event_generate("<Escape>"); pump(0.2)
assert app._notepad is None
assert app.input.focus_get() is not None

# moon window
lines = app.moon_lines(utc(2024, 3, 20, 12))
assert lines[0] == "The moon is waxing gibbous." and any("lit" in l for l in lines) and any("Next full moon" in l for l in lines)
assert any("░" not in l for l in lines)
top = app.open_moon(); pump(0.2); assert top.winfo_exists(); top.destroy()
app.set_dos_mode(True); pump(0.4)
box = app.open_moon(); pump(0.3)
assert isinstance(box, dosui.DosDialog) and app._overlay_open()
app.dos_close_overlay(); pump(0.2)
app._local("/moon"); pump(0.3); assert app._overlay_open(); app.dos_close_overlay()
app.set_dos_mode(False); pump(0.3)

# about (F12)
t = app.open_about(); pump(0.2); assert t.winfo_exists(); t.destroy()
app.set_dos_mode(True); pump(0.4)
a = app.open_about(); pump(0.3); assert isinstance(a, dosui.DosDialog) and app._overlay_open()
app.dos_close_overlay(); pump(0.2)
assert any(tuple(h[:2]) == ("F12", "About") for h in app.dosbar._hints[0]), "the hint bar lists F12"
app.set_dos_mode(False); pump(0.3)
app.root.focus_force(); pump(0.2)
shown = []
app.open_about = lambda: shown.append(1)
app.root.event_generate("<F12>"); pump(0.2)
assert shown == [1], "F12 opens About"
del app.open_about

# hotkeys: defaults work, a change moves the key, a clash is refused
opened = []
app.open_moon = lambda: opened.append("moon")
app._bind_hotkeys()
app.root.focus_force(); pump(0.2)
app.root.event_generate("<Alt-m>"); pump(0.2)
assert opened == ["moon"], opened
ok, m = app.set_hotkeys({"moon": "Ctrl-M"}); assert ok, m
assert app.cfg["keys"] == {"moon": "Ctrl-M"}
app.root.event_generate("<Alt-m>"); pump(0.2); assert opened == ["moon"], "the old key no longer works"
app.root.event_generate("<Control-m>"); pump(0.2); assert opened == ["moon", "moon"]
ok, m = app.set_hotkeys({"moon": "Ctrl-T"}); assert not ok and "same key" in m
ok, m = app.set_hotkeys({"moon": "Ctrl-C"}); assert not ok
ok, m = app.set_hotkeys({"moon": "garbage"}); assert not ok
assert app.cfg["keys"] == {"moon": "Ctrl-M"}, "a refused change leaves the saved keys alone"
ok, m = app.set_hotkeys({}); assert ok and app.cfg["keys"] == {}
app.open_hotkeys().destroy()
app.set_dos_mode(True); pump(0.4); app.open_hotkeys(); pump(0.3); assert app._overlay_open(); app.dos_close_overlay()
app.set_dos_mode(False); pump(0.3)
c = sc.clean_settings({"host": "x", "keys": {"moon": "Ctrl-T"}, "clock": "nonsense"})
assert c["keys"] == {} and c["clock"] == "off"

# the game's own clock and your name are learned from what the game prints
import time as _t
def game_line(offset):
    t = _t.gmtime(_t.time() + offset)
    return "The time is %s %s %2d %02d:%02d:%02d %d" % (_t.strftime("%a", t), _t.strftime("%b", t), t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, t.tm_year)
app._on_data((game_line(-4 * 3600) + "\n\r").encode()); pump(0.2)
assert app.world_time()["zone"] == "eastern" and app.world_time()["offset"] == -5 * 3600, "an Eastern world ignores it"
app._local("/gametime zone learn")
app._on_data((game_line(-4 * 3600) + "\n\r").encode()); pump(0.2)
assert app.world_time()["offset"] == -4 * 3600, app.world_time()
app._on_data((game_line(5 * 3600 + 1800) + "\n\r").encode()); pump(0.2)
assert app.world_time()["offset"] == 5 * 3600 + 1800
app._on_data(b"The time is nonsense\n\r"); pump(0.1)
assert app.world_time()["offset"] == 5 * 3600 + 1800, "junk does not change it"
app._on_data((game_line(-5 * 3600) + "\n\r").encode()); pump(0.2)
app.cfg["clock"] = "game"
assert app.clock_text().endswith("EST"), app.clock_text()
app._local("/gametime reset")
due, kind = extras.parse_when("game 21:30", utc(2024, 3, 20, 12), game_offset=-4 * 3600)
assert abs((due - utc(2024, 3, 20, 12)) - 13.5 * 3600) < 1
app.cfg["char_name"] = ""
app._on_data(b"[Name        ] - Ywellia\n\r"); pump(0.2)
assert app.cfg["char_name"] == "Ywellia"
app._on_data(b"[Name        ] - <script>\n\r"); pump(0.1)
assert app.cfg["char_name"] == "Ywellia"
app._on_data(b"Your credit walk string is now: strides\n\r"); pump(0.2)
assert app._notice_text == "Preview: Ywellia strides in from the north", app._notice_text
c = sc.clean_settings({"host": "x", "char_name": "bad name!"})
assert c["char_name"] == ""

root.update(); root.destroy()
print("extras tests OK")
