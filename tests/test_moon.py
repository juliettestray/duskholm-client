"""The moon: agrees with published new/full moon times, the game's phase naming, and art."""
import calendar, math, os, sys, time, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import moon


def utc(*a):
    return calendar.timegm(datetime.datetime(*a).timetuple())


# published times (UTC): tolerance 15 minutes
for (y, mo, d, h, mi), frac in (((2024, 1, 25, 17, 54), 0.5), ((2024, 2, 24, 12, 30), 0.5), ((2024, 3, 25, 7, 0), 0.5),
                                ((2024, 1, 11, 11, 57), 0.0), ((2024, 4, 8, 18, 21), 0.0), ((2025, 1, 13, 22, 27), 0.5)):
    ts = utc(y, mo, d, h, mi)
    got = moon.next_phase_ts(ts - 5 * 86400, frac)
    assert abs(got - ts) < 15 * 60, (y, mo, d, got - ts)

assert moon.phase_index_from_age(0.1) == 0 and moon.phase_index_from_age(29.4) == 0
assert [moon.PHASES[moon.phase_index_from_age(a)] for a in (3, 7.4, 11, 14.8, 18, 22.1, 26)] == [
    "waxing crescent", "first quarter", "waxing gibbous", "full", "waning gibbous", "last quarter", "waning crescent"]

# Eastern time: daylight saving 2024 began March 10 and ended November 3
assert moon.eastern_offset(utc(2024, 1, 15, 12)) == -5 * 3600
assert moon.eastern_offset(utc(2024, 7, 15, 12)) == -4 * 3600
assert moon.eastern_offset(utc(2024, 3, 10, 6, 59)) == -5 * 3600 and moon.eastern_offset(utc(2024, 3, 10, 7, 0)) == -4 * 3600
assert moon.eastern_offset(utc(2024, 11, 3, 5, 59)) == -4 * 3600 and moon.eastern_offset(utc(2024, 11, 3, 6, 0)) == -5 * 3600
assert moon.eastern_offset(10 ** 15) == -5 * 3600 and moon.eastern_offset(None) == -5 * 3600

# the full-moon night: the instant is 2024-03-25 03:00 EDT, so the night runs dusk 03-25 to dawn 03-26
assert moon.is_full_moon_night(utc(2024, 3, 26, 2, 0)) is True                      # 22:00 EDT on the 25th
assert moon.is_full_moon_night(utc(2024, 3, 26, 9, 0)) is True                      # 05:00 EDT: still that night
assert moon.is_full_moon_night(utc(2024, 3, 25, 2, 0)) is False                     # the night before
assert moon.is_full_moon_night(utc(2024, 3, 22, 2, 0)) is False
assert moon.phase_now(utc(2024, 3, 26, 2, 0)) == 4
assert moon.phase_now(utc(2024, 3, 22, 2, 0)) in (3,)
assert moon.phase_now(utc(2024, 4, 8, 12, 0)) == 0
assert moon.phase_now(utc(2024, 4, 16, 20, 0)) == 2
d = moon.describe(utc(2024, 3, 20, 12))
assert d["name"] == "waxing gibbous" and 0.7 < d["lit"] < 0.95 and d["next_full"] > utc(2024, 3, 20, 12)
assert moon.until(0, 90000) == "1 day 1 hour" and moon.until(0, 100) == "1 min"
assert moon.fmt_eastern(utc(2024, 3, 25, 7, 0)) == "Mon 25 Mar, 3:00 AM Eastern"

# the picture
full = moon.art(14.77, 6)
assert len(full) == 13 and all(len(r) == len(full[0]) for r in full)
new = moon.art(0.0, 6)
assert "█" in "".join(full) and "█" not in "".join(new) and "▓" not in "".join(new)
fq = moon.art(7.4, 6)
mid = fq[6]
assert mid.rstrip().endswith(("█", "▓")) and mid.lstrip()[0] == "·", "first quarter: lit on the right"
lq = moon.art(22.1, 6)[6]
assert lq.lstrip()[0] in "█▓" and lq.rstrip().endswith("·"), "last quarter: lit on the left"
assert moon.art("x") == [] and moon.art(None) == [] and len(moon.art(5, 99)) == 41 and len(moon.art(5, 0)) == 5
assert set("".join(moon.art(12, 5, solid=False))) <= set(" -=#@.")
# any time at all, quickly
t0 = time.time()
for ts in range(0, 4_000_000_000, 91_000_000):
    d = moon.describe(ts)
    assert 0 <= d["age"] <= moon.SYNODIC + 0.01 and 0 <= d["lit"] <= 1
assert time.time() - t0 < 2.0
print("moon tests OK")
