"""Each world's own game clock: its time zone and how fast its time runs compared with yours.

Everything defaults to Duskholm: US Eastern time (EST/EDT) running 1:1 with real time. A world can instead use a
fixed UTC offset, an offset learned from the game's `time` command, and an IC:OOC ratio (3:1 means three in-character
hours pass for every real hour, and 1:24 means a game hour takes a whole real day).
A clock that does not simply follow the real one is kept as an anchor: "at this real moment the game clock read this".

The pure functions at the top take a settings dict (see `clean`); `GameTimeMixin` ties them to the app's worlds."""
import datetime
import math
import re
import time

try:
    import moon
except ImportError:
    moon = None

EASTERN, FIXED, LEARN = "eastern", "fixed", "learn"
DEFAULT_OFFSET = -5 * 3600
MIN_RATIO, MAX_RATIO = 1.0 / 1000, 1000.0
_EPOCH = datetime.datetime(1970, 1, 1)
_MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
_NAMES = {-5 * 3600: "EST", -4 * 3600: "EDT"}


# ---------------------------------------------------------------- settings
def default():
    return {"zone": EASTERN, "offset": DEFAULT_OFFSET, "ratio": 1.0, "anchor": None}


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clean(d):
    """Settings from anywhere (a saved file, say) reduced to valid ones; anything wrong falls back to Duskholm's."""
    out = default()
    if not isinstance(d, dict):
        return out
    if d.get("zone") in (EASTERN, FIXED, LEARN):
        out["zone"] = d["zone"]
    off = d.get("offset")
    if isinstance(off, int) and not isinstance(off, bool) and abs(off) <= 14 * 3600 and off % 900 == 0:
        out["offset"] = off
    r = d.get("ratio")
    if _finite(r) and MIN_RATIO <= r <= MAX_RATIO:
        out["ratio"] = float(r)
    a = d.get("anchor")
    if isinstance(a, (list, tuple)) and len(a) == 2 and _finite(a[0]) and _finite(a[1]) and abs(a[1]) < 1e11:
        out["anchor"] = [float(a[0]), float(a[1])]
    return out


def is_default(g):
    return clean(g) == default()


def clean_all(raw):
    """cfg["world_time"]: {world name (lower case): settings}, checked; entries equal to the default are dropped."""
    out = {}
    if isinstance(raw, dict):
        for name, d in list(raw.items())[:200]:
            if isinstance(name, str) and 0 < len(name) <= 40:
                c = clean(d)
                if not is_default(c):
                    out[name] = c
    return out


# ---------------------------------------------------------------- reading what the user types
def parse_zone(text):
    """'eastern', 'learn', 'utc', 'utc-5', '-5:30', '+9' -> (zone, offset seconds or None). ValueError otherwise."""
    t = " ".join(str(text or "").lower().split())
    if t in ("", "eastern", "et", "est", "edt", "est/edt", "default", "duskholm"):
        return EASTERN, DEFAULT_OFFSET
    if t in ("learn", "auto", "game", "from game"):
        return LEARN, None
    if t in ("utc", "gmt", "z"):
        return FIXED, 0
    m = re.fullmatch(r"(?:utc|gmt)?\s*([+-])?\s*(\d{1,2})(?::?(\d{2}))?", t)
    if m:
        off = (-1 if m.group(1) == "-" else 1) * (int(m.group(2)) * 3600 + int(m.group(3) or 0) * 60)
        if abs(off) <= 14 * 3600 and off % 900 == 0:
            return FIXED, off
    raise ValueError("Zone: eastern, utc, an offset like -5 or +5:30, or learn (from the game's `time` command).")


def parse_ratio(text):
    """'1:1', '3:1' (IC:OOC), '3', '1:24', '2.5' -> game seconds per real second. ValueError otherwise."""
    t = str(text or "").strip().replace(" ", "")
    if not t:
        return 1.0
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:[:/](\d+(?:\.\d+)?))?", t)
    try:
        if not m:
            raise ValueError
        a, b = float(m.group(1)), float(m.group(2) or 1)
        r = a / b
        if not (MIN_RATIO <= r <= MAX_RATIO):
            raise ValueError
    except (ValueError, ZeroDivisionError):
        raise ValueError("Ratio is game time to real time, like 1:1 (the default), 3:1 or 1:24.")
    return r


def parse_hm(text):
    """'14:30', '9pm', '9:15 am' -> (hour, minute) or None."""
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", str(text or "").strip().lower())
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ap == "pm" else 0)
    return (h, mi) if h <= 23 and mi <= 59 else None


# ---------------------------------------------------------------- the clock
def _eastern_offset(ts):
    return moon.eastern_offset(ts) if moon is not None else DEFAULT_OFFSET


def offset_at(g, real_ts):
    return _eastern_offset(real_ts) if g["zone"] == EASTERN else g["offset"]


def local_secs(g, now):
    """The game's clock now, as seconds since 1970-01-01 00:00 of the game's own calendar."""
    a = g["anchor"]
    if a:
        return a[1] + (now - a[0]) * g["ratio"]
    return now + offset_at(g, now)


def local_dt(g, now):
    return _EPOCH + datetime.timedelta(seconds=local_secs(g, now))


def real_from_local(g, target_local, now):
    """The real time stamp at which the game's clock reads `target_local`."""
    if g["anchor"] or g["ratio"] != 1.0:
        return now + (target_local - local_secs(g, now)) / g["ratio"]
    if g["zone"] == EASTERN:
        return target_local - _eastern_offset(target_local + 5 * 3600)
    return target_local - g["offset"]


def next_at(g, hm, now):
    """Real time stamp of the next time the game's clock reads hour:minute."""
    loc = local_dt(g, now)
    target = loc.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    if target <= loc:
        target += datetime.timedelta(days=1)
    return real_from_local(g, (target - _EPOCH).total_seconds(), now)


def zone_name(g, now=None):
    if g["ratio"] != 1.0:
        return "IC"
    off = offset_at(g, time.time() if now is None else now)
    if g["zone"] == EASTERN or off in _NAMES:
        return _NAMES.get(off, "")
    sign = "-" if off < 0 else "+"
    h, m = divmod(abs(off) // 60, 60)
    return "UTC%s%d%s" % (sign, h, ":%02d" % m if m else "")


def clock_text(g, now=None):
    now = time.time() if now is None else now
    t = local_dt(g, now)
    return ("%02d:%02d %s" % (t.hour, t.minute, zone_name(g, now))).strip()


def ratio_text(r):
    if abs(r - round(r)) < 1e-9:
        return "%d:1" % round(r)
    if r < 1 and abs(1 / r - round(1 / r)) < 1e-9:
        return "1:%d" % round(1 / r)
    return "%g:1" % r


def zone_label(g):
    if g["zone"] == EASTERN:
        return "eastern"
    if g["zone"] == LEARN:
        return "learn (now %s)" % (zone_name(dict(g, ratio=1.0)) or "UTC%+d" % (g["offset"] // 3600))
    return zone_name(dict(g, ratio=1.0), 0)


def summary(g):
    now = time.time()
    return "Game clock %s.  Zone: %s.  Ratio (game:real): %s.%s" % (
        clock_text(g, now), zone_label(g), ratio_text(g["ratio"]),
        "  The clock was set by hand or from the game's `time` command." if g["anchor"] else "")


def set_clock(g, hm, now):
    """Settings whose game clock reads hour:minute right now (today's date on the game's calendar)."""
    loc = local_dt(g, now)
    target = loc.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    return dict(g, anchor=[now, (target - _EPOCH).total_seconds()])


def with_ratio(g, ratio, now):
    """New ratio; the game clock keeps its reading at this moment (so changing the speed never jumps the clock)."""
    out = dict(g, ratio=ratio)
    if ratio != 1.0 or g["anchor"]:
        out["anchor"] = [now, local_secs(g, now)]
    return out


def learned_from_time_line(g, month, day, h, mi, se, year, now):
    """The game said what time it is: new settings, or None when nothing needs to change."""
    try:
        game = datetime.datetime(year, _MONTHS[month], day, h, mi, se)
    except (KeyError, ValueError):
        return None
    secs = (game - _EPOCH).total_seconds()
    if g["ratio"] != 1.0 or g["anchor"]:
        return dict(g, anchor=[now, secs])                 # its own clock is the truth for a world that keeps one
    if g["zone"] != LEARN:
        return None
    diff = ((secs - now + 43200) % 86400) - 43200          # game local minus UTC, whole days wrapped away
    off = int(round(diff / 900.0)) * 900
    if abs(off) <= 14 * 3600 and off != g["offset"]:
        return dict(g, offset=off)
    return None


# ---------------------------------------------------------------- the app side
class GameTimeMixin:
    def _gt_key(self, s=None):
        s = s or self._shown
        return (self._world_key(s) or self._world_name(s).lower())[:40]        # the world's id when it is a saved one

    def world_time(self, s=None):
        """The game-clock settings of a world (the one on screen by default), Duskholm's unless changed."""
        return clean(self.cfg.get("world_time", {}).get(self._gt_key(s)))

    def set_world_time(self, g, s=None):
        table = dict(self.cfg.get("world_time") or {})
        g = clean(g)
        if is_default(g):
            table.pop(self._gt_key(s), None)
        else:
            table[self._gt_key(s)] = g
        self.cfg["world_time"] = table
        self._save_settings()
        try:
            self._update_clock()
        except Exception:
            pass

    def game_clock_text(self):
        return clock_text(self.world_time())

    def learn_game_time(self, month, day, h, mi, se, year):
        """The game printed its `time`: keep the world's clock in step when it is one that follows the game."""
        new = learned_from_time_line(self.world_time(self.session), month, day, h, mi, se, year, time.time())
        if new is not None:
            self.set_world_time(new, self.session)

    # ---- /gametime ----------------------------------------------------------------------------
    HELP_GAMETIME = ("/gametime               show this world's game clock settings;  /gametime reset\n"
                     "/gametime zone <eastern|utc|-5|+5:30|learn>   /gametime ratio <3:1>   /gametime set <14:30>")

    def _gametime_command(self, cmd, arg):
        if cmd not in ("gametime", "gametz", "gameclock"):
            return False
        words = (arg or "").split(None, 1)
        sub, rest = (words[0].lower() if words else ""), (words[1] if len(words) > 1 else "")
        g, now = self.world_time(), time.time()
        name = self._world_name(self._shown)
        try:
            if not sub:
                self.system("%s: %s\n%s" % (name, summary(g), self.HELP_GAMETIME))
                return True
            if sub == "reset":
                self.set_world_time(default())
                self.system("%s: back to Duskholm's clock (Eastern, 1:1). %s" % (name, summary(self.world_time())))
            elif sub == "zone":
                zone, off = parse_zone(rest)
                g = dict(g, zone=zone, offset=g["offset"] if off is None else off)
                if g["anchor"] and g["ratio"] == 1.0:
                    g["anchor"] = None                       # a zone change means "follow the real clock" again
                self.set_world_time(g)
                self.system("%s: %s" % (name, summary(self.world_time())))
            elif sub == "ratio":
                self.set_world_time(with_ratio(g, parse_ratio(rest), now))
                self.system("%s: %s" % (name, summary(self.world_time())))
            elif sub in ("set", "clock"):
                hm = parse_hm(rest)
                if hm is None:
                    raise ValueError("Say what the game clock reads now, like /gametime set 14:30 or 9pm.")
                self.set_world_time(set_clock(g, hm, now))
                self.system("%s: %s" % (name, summary(self.world_time())))
            else:
                self.system(self.HELP_GAMETIME)
        except ValueError as e:
            self.system(str(e))
        return True

    # ---- the settings form (both looks) -------------------------------------------------------
    def open_game_time(self):
        g = self.world_time()
        name = self._world_name(self._shown)
        fields = [("zone", "Time zone", {EASTERN: "eastern", FIXED: "%+d" % (g["offset"] // 3600), LEARN: "learn"}[g["zone"]],
                   "eastern, utc, -5, +5:30, or learn (from the game's `time` command)"),
                  ("ratio", "IC : OOC", ratio_text(g["ratio"]), "game time to real time: 1:1, 3:1, 1:24"),
                  ("clock", "Clock now", "", "what the game clock reads right now (optional), like 14:30 or 9pm")]

        def apply(values):
            g2 = self.world_time()
            zone, off = parse_zone(values.get("zone", ""))
            g2 = dict(g2, zone=zone, offset=g2["offset"] if off is None else off)
            ratio = parse_ratio(values.get("ratio", ""))
            if ratio != g2["ratio"]:
                g2 = with_ratio(g2, ratio, time.time())
            elif g2["anchor"] and ratio == 1.0 and zone != g["zone"]:
                g2["anchor"] = None
            hm = str(values.get("clock", "")).strip()
            if hm:
                parsed = parse_hm(hm)
                if parsed is None:
                    raise ValueError("Clock now: like 14:30 or 9pm.")
                g2 = set_clock(g2, parsed, time.time())
            self.set_world_time(g2)
            self.system("%s: %s" % (name, summary(self.world_time())))

        if self.dos:
            dfields = [{"key": k, "label": label, "type": "text", "value": v, "width": 14} for k, label, v, _h in fields]

            def result(res, vals):
                if res == "ok":
                    try:
                        apply(vals)
                    except ValueError as e:
                        self.system(str(e))
                elif res == "reset":
                    self._gametime_command("gametime", "reset")
            return self._dos_dialog("Game time: %s" % name, dfields, [("OK", "ok"), ("Reset", "reset"), ("Cancel", "cancel")],
                                    result, width=64,
                                    message="Duskholm: eastern, 1:1. Zone: eastern / utc / -5 / learn. IC:OOC e.g. 3:1.")
        import tkinter as tk
        top = tk.Toplevel(self.root)
        top.title("Game time: %s" % name)
        top.transient(self.root)
        tk.Label(top, justify="left", anchor="w",
                 text="The game clock for %s. Defaults are Duskholm's: Eastern time, 1:1." % name).grid(
            row=0, column=0, columnspan=2, padx=10, pady=(8, 4), sticky="w")
        vars_ = {}
        for i, (k, label, v, hint) in enumerate(fields, 1):
            tk.Label(top, text=label).grid(row=2 * i - 1, column=0, padx=10, sticky="w")
            vars_[k] = tk.StringVar(value=v)
            tk.Entry(top, textvariable=vars_[k], width=18).grid(row=2 * i - 1, column=1, sticky="w", pady=(4, 0))
            tk.Label(top, text=hint, justify="left", anchor="w").grid(row=2 * i, column=0, columnspan=2, padx=10, sticky="w")
        msg = tk.Label(top, text=summary(g), justify="left", anchor="w")
        msg.grid(row=8, column=0, columnspan=2, padx=10, pady=6, sticky="w")

        def ok():
            try:
                apply({k: v.get() for k, v in vars_.items()})
            except ValueError as e:
                msg.configure(text=str(e))
                return
            top.destroy()

        def reset():
            self._gametime_command("gametime", "reset")
            top.destroy()
        bf = tk.Frame(top)
        bf.grid(row=9, column=0, columnspan=2, pady=8)
        tk.Button(bf, text="OK", width=8, command=ok).pack(side="left", padx=4)
        tk.Button(bf, text="Reset", width=8, command=reset).pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", width=8, command=top.destroy).pack(side="left", padx=4)
        top.bind("<Return>", lambda e: ok())
        top.bind("<Escape>", lambda e: top.destroy())
        self._theme_tree(top)
        return top
