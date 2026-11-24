"""Each world's game clock: zone, IC:OOC ratio, timers on it, and what is learned from `time` (no network)."""
import datetime, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gametime as gt
import extras
import sanctuary as sc
import tkinter as tk


def utc(y, mo, d, h=0, mi=0, s=0):
    return (datetime.datetime(y, mo, d, h, mi, s) - datetime.datetime(1970, 1, 1)).total_seconds()


# ---- the pure part ---------------------------------------------------------------------------
D = gt.default()
assert D == {"zone": "eastern", "offset": -18000, "ratio": 1.0, "anchor": None}, "Duskholm: Eastern, 1:1"
assert gt.clock_text(D, utc(2024, 1, 15, 17, 30)) == "12:30 EST"
assert gt.clock_text(D, utc(2024, 7, 15, 17, 30)) == "13:30 EDT", "daylight saving follows Eastern"
assert gt.parse_zone("") == ("eastern", -18000) and gt.parse_zone("EST")[0] == "eastern"
assert gt.parse_zone("utc") == ("fixed", 0) and gt.parse_zone("utc-5") == ("fixed", -18000)
assert gt.parse_zone("+5:30") == ("fixed", 19800) and gt.parse_zone("-0930") == ("fixed", -34200)
assert gt.parse_zone("learn")[0] == "learn" and gt.parse_zone("9")[1] == 9 * 3600
for bad in ("mars", "+15", "+5:10", "utc+", "1:2:3", "--5"):
    try:
        gt.parse_zone(bad); raise AssertionError(bad)
    except ValueError:
        pass
assert gt.parse_ratio("1:1") == 1.0 and gt.parse_ratio("3:1") == 3.0 and gt.parse_ratio("") == 1.0
assert gt.parse_ratio("3") == 3.0 and gt.parse_ratio("1:24") == 1 / 24 and gt.parse_ratio("5/2") == 2.5
for bad in ("0", "0:1", "1:0", "x", "-2", "1:2:3", "5000", "1:5000"):
    try:
        gt.parse_ratio(bad); raise AssertionError(bad)
    except ValueError:
        pass
assert gt.ratio_text(3.0) == "3:1" and gt.ratio_text(1 / 24) == "1:24" and gt.ratio_text(2.5) == "2.5:1"
assert gt.parse_hm("14:30") == (14, 30) and gt.parse_hm("9pm") == (21, 0) and gt.parse_hm("12am") == (0, 0)
assert gt.parse_hm("25:00") is None and gt.parse_hm("13pm") is None and gt.parse_hm("x") is None

# the same checks as the old timer test: game 21:30 from 08:00 EDT is 13h30 away; in winter 14h30 from 07:00 EST
now = utc(2024, 3, 20, 12)
assert abs(gt.next_at(D, (21, 30), now) - now - 13.5 * 3600) < 1
assert abs(gt.next_at(D, (21, 30), utc(2024, 1, 20, 12)) - utc(2024, 1, 20, 12) - 14.5 * 3600) < 1
assert abs(gt.next_at(D, (7, 0), utc(2024, 1, 20, 12)) - utc(2024, 1, 20, 12) - 24 * 3600) < 1, "already struck: tomorrow"
fixed = gt.clean({"zone": "fixed", "offset": 9 * 3600})
assert gt.clock_text(fixed, utc(2024, 1, 15, 0)) == "09:00 UTC+9"
assert gt.clock_text(gt.clean({"zone": "fixed", "offset": 19800}), utc(2024, 1, 15, 0)) == "05:30 UTC+5:30"
assert gt.clock_text(gt.clean({"zone": "fixed", "offset": -4 * 3600}), utc(2024, 1, 15, 12)) == "08:00 EDT"
assert abs(gt.next_at(fixed, (12, 0), utc(2024, 1, 15, 0)) - utc(2024, 1, 15, 3)) < 1, "noon in UTC+9 is 03:00 UTC"

# a world whose time runs faster: 3:1, started at 12:00 game time
n0 = utc(2024, 5, 1, 12)
fast = gt.with_ratio(gt.set_clock(D, (12, 0), n0), 3.0, n0)
assert gt.clock_text(fast, n0) == "12:00 IC", gt.clock_text(fast, n0)
assert gt.clock_text(fast, n0 + 3600) == "15:00 IC", "an hour later it is three game hours on"
assert gt.clock_text(fast, n0 + 8 * 3600) == "12:00 IC", "a game day passes in eight real hours"
assert abs(gt.next_at(fast, (18, 0), n0) - n0 - 2 * 3600) < 1, "18:00 is six game hours, two real hours, away"
slow = gt.with_ratio(gt.set_clock(D, (12, 0), n0), 1 / 24, n0)
assert gt.clock_text(slow, n0 + 24 * 3600) == "13:00 IC" and abs(gt.next_at(slow, (13, 0), n0) - n0 - 86400) < 1
# changing the speed never jumps the clock
before = gt.local_secs(fast, n0 + 1000)
assert abs(gt.local_secs(gt.with_ratio(fast, 10.0, n0 + 1000), n0 + 1000) - before) < 1e-6
back = gt.with_ratio(gt.set_clock(D, (9, 0), n0), 1.0, n0)
assert gt.clock_text(back, n0 + 3600) == "10:00 EDT" or gt.clock_text(back, n0 + 3600).startswith("10:00")

# what the game says wins for a world with its own speed; a zone that learns takes the offset
learn = gt.clean({"zone": "learn"})
now = utc(2024, 7, 15, 12, 0, 5)
new = gt.learned_from_time_line(learn, "Jul", 15, 8, 0, 0, 2024, now)
assert new["offset"] == -4 * 3600 and new["anchor"] is None
assert gt.learned_from_time_line(D, "Jul", 15, 3, 0, 0, 2024, now) is None, "an Eastern world keeps Eastern"
got = gt.learned_from_time_line(fast, "Jul", 15, 3, 0, 0, 2030, now)
assert gt.clock_text(got, now) == "03:00 IC" and got["ratio"] == 3.0
assert gt.learned_from_time_line(learn, "Zzz", 15, 3, 0, 0, 2024, now) is None

# bad saved data falls back to the defaults
assert gt.clean({"zone": "mars", "offset": 7, "ratio": float("nan"), "anchor": [1, float("inf")]}) == D
assert gt.clean({"ratio": 0}) == D and gt.clean({"ratio": 99999}) == D and gt.clean("x") == D and gt.clean(None) == D
assert gt.clean_all({"a": {"ratio": 3}, "b": {}, "c": "x", "": {"ratio": 2}, 5: {"ratio": 2}}) == {"a": dict(D, ratio=3.0)}

# parse_when uses the world's clock; the old Eastern behaviour is unchanged
assert abs(extras.parse_when("game 21:30", utc(2024, 3, 20, 12), game=D)[0] - utc(2024, 3, 20, 12) - 13.5 * 3600) < 1
assert extras.parse_when("game 21:30", utc(2024, 3, 20, 12), game_offset=-4 * 3600)[1] == "game"
due, kind = extras.parse_when("game 18:00", n0, game=fast)
assert kind == "game" and abs(due - n0 - 2 * 3600) < 1

# ---- the app ---------------------------------------------------------------------------------
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x700+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def out():
    return app.out.get("1.0", "end")


pump(0.3)
first = app.session
app.cfg["clock"] = "game"
assert app.world_time() == D and app.clock_text().split()[-1] in ("EST", "EDT"), "Duskholm's by default"
app._local("/gametime"); pump(0.2)
assert "Ratio (game:real): 1:1" in out() and "Zone: eastern" in out()
app._local("/gametime zone utc-5"); pump(0.2)
assert app.world_time()["zone"] == "fixed" and app.clock_text().endswith("EST")
app._local("/gametime zone +9"); pump(0.2)
assert app.clock_text().endswith("UTC+9")
app._local("/gametime zone mars"); pump(0.2)
assert "Zone: eastern" in out() and app.world_time()["offset"] == 9 * 3600, "a bad zone changes nothing"
app._local("/gametime set 14:30"); pump(0.2)
assert app.clock_text().startswith("14:30")
app._local("/gametime ratio 3:1"); pump(0.2)
assert app.world_time()["ratio"] == 3.0 and app.clock_text().endswith("IC")
app._local("/gametime ratio nope"); pump(0.2)
assert app.world_time()["ratio"] == 3.0
# per world: a second world has its own, untouched
second = app.open_new_world("Elsewhere"); pump(0.3)
assert app.session is second and app.world_time() == D and app.clock_text().split()[-1] in ("EST", "EDT")
app._local("/gametime zone utc+1"); pump(0.2)
assert app.clock_text().endswith("UTC+1")
app.switch_session(first); pump(0.3)
assert app.world_time()["ratio"] == 3.0 and app.clock_text().endswith("IC"), "and the first keeps its own"
# a timer on a fast world: game time to real time
ok, msg = app.add_timer("game 23:00", "feast")
assert ok and app._timers[-1]["kind"] == "game"
due = app._timers[-1]["due"]
assert 0 < due - time.time() <= 24 / 3.0 * 3600 + 5, "never more than a game day (eight real hours) away"
app._timers.clear()
# saved and restored
import json
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert set(saved["world_time"]) >= {first.name.lower() or "world 1", "elsewhere"} or len(saved["world_time"]) == 2, saved["world_time"]
assert sc.clean_settings(saved)["world_time"] == saved["world_time"]
# reset puts a world back to Duskholm's
app._local("/gametime reset"); pump(0.2)
assert app.world_time() == D and len(app.cfg["world_time"]) == 1, "defaults are not stored"
# the forms open in both looks
app.open_game_time().destroy(); pump(0.2)
app.set_dos_mode(True); pump(0.4)
app.open_game_time(); pump(0.3); assert app._overlay_open(); app.dos_close_overlay()
app.set_dos_mode(False); pump(0.3)
# a time line from a hidden world belongs to that world
app.switch_session(second); pump(0.2)
app._local("/gametime zone learn"); app.switch_session(first); pump(0.2)
second.q.put((second.conn.gen, "data", ("The time is Mon Jul 15 08:00:00 %d\r\n" % 2024).encode()))
pump(0.5)
assert app.world_time(first) == D, "the world on screen is not touched"
assert app.world_time(second)["zone"] == "learn"

root.update(); root.destroy()
print("game time tests OK")
