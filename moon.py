"""The moon, worked out the way the game works it out (stdlib only).

Phases come from Meeus, Astronomical Algorithms ch. 49 (the true instant of each new/full moon,
accurate to minutes), the same method the game uses, so the client agrees with it: eight named
phases, and 'full' only on the real full-moon night (dusk to dawn, US Eastern calendar day).
Nothing here is slow: a phase takes a few dozen trig calls."""
import math
import time
import datetime

_E = datetime.datetime(1970, 1, 1)


def _utc(ts):
    return _E + datetime.timedelta(seconds=ts)

SYNODIC = 29.530588853
PHASES = ("new", "waxing crescent", "first quarter", "waxing gibbous",
          "full", "waning gibbous", "last quarter", "waning crescent")
_EPOCH_JD = 2440587.5
_K0 = 2451550.09766


def jd_from_ts(ts):
    return _EPOCH_JD + float(ts) / 86400.0


def ts_from_jd(jd):
    return (float(jd) - _EPOCH_JD) * 86400.0


def phase_jd(k, frac):
    """Julian day of a principal phase of lunation k (frac 0=new, .25=first quarter, .5=full, .75=last)."""
    d = math.pi / 180.0
    m = k + frac
    t = m / 1236.85
    jde = _K0 + 29.530588861 * m + 0.00015437 * t * t - 0.000000150 * t ** 3 + 0.00000000073 * t ** 4
    ms = (2.5534 + 29.10535670 * m - 0.0000014 * t * t - 0.00000011 * t ** 3) * d
    mm = (201.5643 + 385.81693528 * m + 0.0107582 * t * t + 0.00001238 * t ** 3 - 0.000000058 * t ** 4) * d
    mf = (160.7108 + 390.67050284 * m - 0.0016118 * t * t - 0.00000227 * t ** 3 + 0.000000011 * t ** 4) * d
    mo = (124.7746 - 1.56375588 * m + 0.0020672 * t * t + 0.00000215 * t ** 3) * d
    e = 1.0 - 0.002516 * t - 0.0000074 * t * t
    s = math.sin
    corr = (-0.40614 * s(mm) + 0.17302 * e * s(ms) + 0.01614 * s(2 * mm) + 0.01043 * s(2 * mf)
            + 0.00734 * e * s(mm - ms) - 0.00515 * e * s(mm + ms) + 0.00209 * e * e * s(2 * ms)
            - 0.00111 * s(mm - 2 * mf) - 0.00057 * s(mm + 2 * mf) + 0.00056 * e * s(2 * mm + ms)
            - 0.00042 * s(3 * mm) + 0.00042 * e * s(ms + 2 * mf) + 0.00038 * e * s(ms - 2 * mf)
            - 0.00024 * e * s(2 * mm - ms) - 0.00017 * s(mo) - 0.00007 * s(mm + 2 * ms)
            + 0.00004 * s(2 * mm - 2 * mf) + 0.00004 * s(3 * ms) + 0.00003 * s(mm + ms - 2 * mf)
            + 0.00003 * s(2 * mm + 2 * mf) - 0.00003 * s(mm + ms + 2 * mf) + 0.00003 * s(mm - ms + 2 * mf)
            - 0.00002 * s(mm - ms - 2 * mf) - 0.00002 * s(3 * mm + ms) + 0.00002 * s(4 * mm))
    return jde + corr


def _lunation(jd):
    return int(math.floor((jd - _K0) / SYNODIC))


def next_phase_ts(ts, frac):
    """UTC time of the next new (0) or full (0.5) moon strictly after `ts`."""
    jd = jd_from_ts(ts)
    k0 = _lunation(jd)
    best = 1e18
    for k in range(k0 - 1, k0 + 3):
        p = phase_jd(k, frac)
        if jd < p < best:
            best = p
    return ts_from_jd(best)


def age_days(ts):
    """The moon's age (0 .. 29.53) in days since the last new moon."""
    jd = jd_from_ts(ts)
    k0 = _lunation(jd)
    prev, nxt = -1e18, 1e18
    for k in range(k0 - 1, k0 + 3):
        n = phase_jd(k, 0.0)
        if n <= jd and n > prev:
            prev = n
        if n > jd and n < nxt:
            nxt = n
    span = nxt - prev
    if span <= 0:
        span = SYNODIC
    return (jd - prev) / span * SYNODIC


def phase_index_from_age(age):
    q, half = SYNODIC / 4.0, 0.5
    if age < half or age >= SYNODIC - half:
        return 0
    if age < q - half:
        return 1
    if age < q + half:
        return 2
    if age < 2 * q - half:
        return 3
    if age < 2 * q + half:
        return 4
    if age < 3 * q - half:
        return 5
    if age < 3 * q + half:
        return 6
    return 7


# ---------------------------------------------------------------- US Eastern time
def _nth_sunday(year, month, n):
    d = datetime.date(year, month, 1)
    first_sun = 1 + (6 - d.weekday()) % 7
    return datetime.date(year, month, first_sun + 7 * (n - 1))


def eastern_offset(ts):
    """Seconds to add to UTC for US Eastern time at that instant (-5h, or -4h in daylight time)."""
    try:
        y = _utc(ts).year
        start = datetime.datetime.combine(_nth_sunday(y, 3, 2), datetime.time(7, 0))     # 2:00 EST
        end = datetime.datetime.combine(_nth_sunday(y, 11, 1), datetime.time(6, 0))      # 2:00 EDT
        t = _utc(ts)
        return -4 * 3600 if start <= t < end else -5 * 3600
    except (OverflowError, OSError, ValueError, TypeError):
        return -5 * 3600


def eastern_struct(ts):
    return _utc(ts + eastern_offset(ts))


def eastern_day_start(ts):
    local = eastern_struct(ts).replace(hour=0, minute=0, second=0, microsecond=0)
    mid_ts = (local - datetime.datetime(1970, 1, 1)).total_seconds()
    return mid_ts - eastern_offset(mid_ts)


def is_full_moon_day(ts):
    start = eastern_day_start(ts)
    f = next_phase_ts(start - 1.0, 0.5)
    return start <= f < start + 86400


def is_full_moon_night(ts):
    """Dusk to dawn: a night belongs to the day it began on."""
    return is_full_moon_day(ts - 12 * 3600)


def phase_now(ts=None):
    """Index into PHASES, as the game names it ('full' only during the actual full-moon night)."""
    ts = time.time() if ts is None else ts
    if is_full_moon_night(ts):
        return 4
    loc = eastern_struct(ts)
    noon = (datetime.datetime(loc.year, loc.month, loc.day, 12) - datetime.datetime(1970, 1, 1)).total_seconds()
    idx = phase_index_from_age(age_days(noon))
    if idx == 4:
        return 3 if age_days(ts) < SYNODIC / 2.0 else 5
    return idx


def illumination(ts):
    """Fraction of the disc that is lit (0..1)."""
    return (1.0 - math.cos(2.0 * math.pi * age_days(ts) / SYNODIC)) / 2.0


def describe(ts=None):
    """Everything the pop-up shows, as a dict."""
    ts = time.time() if ts is None else ts
    idx = phase_now(ts)
    nf, nn = next_phase_ts(ts, 0.5), next_phase_ts(ts, 0.0)
    return {"index": idx, "name": PHASES[idx], "age": age_days(ts), "lit": illumination(ts),
            "next_full": nf, "next_new": nn, "full_night": is_full_moon_night(ts)}


def until(ts_from, ts_to):
    """'3 days 4 hours' style gap."""
    s = max(0, int(ts_to - ts_from))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    if d:
        return "%d day%s %d hour%s" % (d, "" if d == 1 else "s", h, "" if h == 1 else "s")
    if h:
        return "%d hour%s %d min" % (h, "" if h == 1 else "s", m)
    return "%d min" % m


def fmt_eastern(ts):
    t = eastern_struct(ts)
    return "%s %d %s, %d:%02d %s Eastern" % (t.strftime("%a"), t.day, t.strftime("%b"),
                                          (t.hour % 12) or 12, t.minute, "AM" if t.hour < 12 else "PM")


# ---------------------------------------------------------------- picture
def art(age, radius=6, solid=True):
    """The moon as text: a list of strings. Lit parts use shade blocks, the dark side a faint dot.
    Characters are drawn twice as wide as tall, so the disc looks round."""
    try:
        radius = max(2, min(int(radius), 20))
        theta = 2.0 * math.pi * (float(age) % SYNODIC) / SYNODIC
    except (TypeError, ValueError):
        return []
    lx, lz = math.sin(theta), -math.cos(theta)
    shades = ("░", "▒", "▓", "█") if solid else ("-", "=", "#", "@")
    rows = []
    for j in range(-radius, radius + 1):
        y = j / radius
        line = []
        for i in range(-2 * radius, 2 * radius + 1):
            x = i / (2.0 * radius)
            r2 = x * x + y * y
            if r2 > 1.0:
                line.append(" ")
                continue
            z = math.sqrt(1.0 - r2)
            b = x * lx + z * lz
            if b <= 0.02:
                line.append("·" if solid else ".")
            else:
                line.append(shades[min(3, int(b * 4))])
        rows.append("".join(line))
    return rows
