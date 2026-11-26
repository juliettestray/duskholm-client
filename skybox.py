"""The sky box of the Duskholm GMCP layout: a little picture of the weather over the terrain, the temperature, the
neighbourhood and its coordinates, mist, the time and the moon. Pure text in, coloured lines out (no Tk).

A line is a list of (text, role); the roles are the ones gmcp.py maps to colours. The picture is plain ASCII in the normal
look and block characters in the DOS look. Weather, terrain, temperature and mist come from the game when it sends them
(Room.Environment); the time and the moon the client can work out itself. Nothing is drawn for what the game has not told us:
in particular mist only ever appears when the game sent it (the game leaves it out when you cannot see it)."""
import ctypes
import math
import sys

ART_W = 16                   # characters across the picture
ART_H = 5                    # rows: three of sky, two of ground
LEFT_W = ART_W + 6           # the picture, a gap, and room for the temperature in the corner
GAP = 1
FAHRENHEIT = frozenset("US BS BZ KY PW LR GU PR VI AS MH FM".split())    # the few places that use it
NIGHT_FROM, NIGHT_TO = 19, 6  # hours: dark from 19:00 until 06:00 when the game gave no better word

# ---- reading what the game sent ----------------------------------------------------------------------------------
_WEATHER = (("storm", "storm"), ("thunder", "storm"), ("lightning", "storm"), ("snow", "snow"), ("blizzard", "snow"), ("sleet", "snow"),
            ("hail", "snow"), ("rain", "rain"), ("drizzle", "rain"), ("shower", "rain"), ("downpour", "rain"), ("fog", "fog"),
            ("mist", "fog"), ("haze", "fog"), ("cloud", "cloudy"), ("overcast", "cloudy"), ("grey", "cloudy"), ("gray", "cloudy"),
            ("clear", "clear"), ("sun", "clear"), ("fair", "clear"), ("star", "clear"))
_TERRAIN = (("house", "indoors"), ("indoor", "indoors"), ("inside", "indoors"), ("room", "indoors"), ("shop", "indoors"),
            ("store", "indoors"), ("school", "indoors"), ("building", "indoors"), ("cave", "indoors"), ("water", "water"),
            ("river", "water"), ("lake", "water"), ("sea", "water"), ("ocean", "water"), ("beach", "water"), ("swamp", "water"),
            ("forest", "forest"), ("wood", "forest"), ("tree", "forest"), ("jungle", "forest"), ("field", "field"),
            ("grass", "field"), ("plain", "field"), ("farm", "field"), ("meadow", "field"), ("garden", "field"), ("park", "field"),
            ("road", "street"), ("street", "street"), ("city", "street"), ("urban", "street"), ("town", "street"),
            ("alley", "street"), ("sidewalk", "street"), ("mountain", "hills"), ("hill", "hills"), ("rock", "hills"),
            ("desert", "hills"))


def _word(v):
    return " ".join(str(v).split())[:40] if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""


def _kind(table, *texts):
    for t in texts:
        low = _word(t).lower()
        for key, kind in table:
            if key in low:
                return kind
    return None


def _list(v):
    return [str(x).lower() for x in v] if isinstance(v, (list, tuple)) else []


def weather_kind(env):
    """clear, few, partly, cloudy, rain, storm, snow, hail or fog from what the game sent (Room.Environment: clouds, cover,
    falling), or from a plain weather phrase; None when it told us nothing about the sky."""
    falling = _list(env.get("falling"))
    clouds = _word(env.get("clouds")).lower()
    if "snow" in falling:
        return "snow"
    if "hail" in falling:
        return "hail"
    if "rain" in falling:
        return "storm" if clouds == "storm" else "rain"
    if clouds:
        if clouds == "clear":
            return "clear"
        cover = _word(env.get("cover")).lower()
        return "few" if cover == "few" else "partly" if cover == "partly" else "cloudy"
    return _kind(_WEATHER, env.get("weather"), env.get("sky"))


def cloud_tone(env):
    """'dark' for grey, dark and storm clouds; 'light' for wispy and thin ones."""
    clouds = _word(env.get("clouds")).lower()
    if clouds:
        return "light" if clouds in ("wispy", "thin") else "dark"
    low = (_word(env.get("weather")) + " " + _word(env.get("sky"))).lower()
    return "dark" if any(w in low for w in ("storm", "grey", "gray", "dark", "overcast")) else "light"


def weather_words(env):
    """The sky in words ('storm clouds, rain'), for when the picture is switched off."""
    text = _word(env.get("weather") or env.get("sky"))
    if text:
        return text
    clouds = _word(env.get("clouds")).lower()
    bits = []
    if clouds:
        bits.append("clear sky" if clouds == "clear" else clouds + " clouds")
    bits += _list(env.get("falling"))
    return ", ".join(bits)


MIST_LEVELS = {"ankle": 1, "waist": 2, "wreathed": 3}
MIST_WORDS = {1: "ankle-deep", 2: "waist-deep", 3: "wreathed"}


def mist_level(env):
    """0 when the game sent no mist; 1 ankle-deep, 2 waist-deep, 3 wreathed (any other word counts as 1)."""
    m = _word(env.get("mist")).lower()
    return MIST_LEVELS.get(m, 1) if m else 0


def terrain_kind(env):
    """indoors, water, forest, field, street, hills; 'plain' for anything else the game named; None when it named none."""
    if env.get("indoors") is True:
        return "indoors"
    k = _kind(_TERRAIN, env.get("terrain"), env.get("environment"))
    return k or ("plain" if _word(env.get("terrain")) or _word(env.get("environment")) else None)


def period_word(hour):
    """morning, afternoon, evening or night for an hour of the day."""
    return "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 17 else "evening" if 17 <= hour < 21 else "night"


def is_night(hour, period=None):
    """Dark or not: the game's word for the time of day when it is a clear one, else the hour."""
    p = _word(period).lower()
    if "night" in p:
        return True
    if any(w in p for w in ("morning", "noon", "afternoon", "midday", "day")):
        return False
    if not isinstance(hour, int):
        return False
    return hour >= NIGHT_FROM or hour < NIGHT_TO


# ---- Fahrenheit or Celsius -------------------------------------------------------------------------------------------
def region_code():
    """The two-letter region of the player's Windows setting ('US' from 'en-US'), '' when it cannot be told."""
    if sys.platform.startswith("win"):
        try:
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
                parts = buf.value.replace("_", "-").split("-")
                return parts[-1].upper() if len(parts) > 1 and len(parts[-1]) == 2 else ""
        except Exception:
            pass
    try:
        import locale
        loc = locale.getlocale()[0] or ""
        return loc.split("_")[-1][:2].upper() if "_" in loc else ""
    except Exception:
        return ""


def choose_unit(setting, region=None):
    """'f' or 'c' from the setting ('f', 'c', or anything else to guess from the region)."""
    if setting in ("f", "c"):
        return setting
    return "f" if (region_code() if region is None else region) in FAHRENHEIT else "c"


def temp_text(env, unit):
    """'29°F' / '-1°C' in the chosen unit, or '' when the game sent no temperature."""
    f, c = env.get("temp_f"), env.get("temp_c")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    if unit == "f":
        v = f if num(f) else (round(c * 9 / 5 + 32) if num(c) else None)
    else:
        v = c if num(c) else (round((f - 32) * 5 / 9) if num(f) else None)
    return "" if v is None else "%d°%s" % (round(v), "F" if unit == "f" else "C")


# ---- the picture -------------------------------------------------------------------------------------------------------
def _cells(rows):
    """[[(text, role), ...]] -> a grid of ART_W (char, role) cells per row."""
    grid = []
    for pieces in rows:
        cells = []
        for text, role in pieces:
            cells += [(ch, role) for ch in text]
        cells = (cells + [(" ", "normal")] * ART_W)[:ART_W]
        grid.append(cells)
    return grid


def _pieces(cells):
    out = []
    for ch, role in cells:
        if out and out[-1][1] == role:
            out[-1] = (out[-1][0] + ch, role)
        else:
            out.append((ch, role))
    return out


def _sun(night, dos):
    if night:
        if dos:
            return [[("  .    *      .   ", "dim")], [("     ", "dim"), ("\u2584\u2580\u2588\u2584", "normal"), ("      *  ", "dim")],
                    [("   *      .    *  ", "dim")]]
        return [[("  .    *      .   ", "dim")], [("     ", "dim"), (".-.", "normal"), ("     *     ", "dim")],
                [("   *  ", "dim"), ("`-'", "normal"), ("   .    *  ", "dim")]]
    if dos:
        return [[("     ", "normal"), ("\u2584" * 5, "warn")], [("    ", "normal"), ("\u2590" + "\u2588" * 5 + "\u258c", "warn")],
                [("     ", "normal"), ("\u2580" * 5, "warn")]]
    return [[(r"     \  |  /    ", "warn")], [(r"    - (   ) -   ", "warn")], [(r"     /  |  \    ", "warn")]]


def _overlay(rows, row, col, text, role):
    """Lay `text` over the cells of one row of pieces, from column `col` (the cells it covers are replaced)."""
    cells = _cells(rows)
    for k, ch in enumerate(text):
        if 0 <= col + k < ART_W:
            cells[row][col + k] = (ch, role)
    return [_pieces(r) for r in cells]


def _sky(kind, night, dos, tone="light"):
    cc = "normal" if tone == "light" else "grey"
    if kind == "clear":
        return _sun(night, dos)
    if kind == "few":                                     # the sun with one small cloud at its side
        return _overlay(_sun(night, dos), 2, 11, "\u2584\u2588\u2588\u2584" if dos else "(__)", cc)
    if kind == "partly":                                  # the sun above and behind a cloud
        if dos:
            return [[("   ", "normal"), ("\u2584\u2584\u2584", "warn")], [("  ", "normal"), ("\u2590\u2588\u2588\u2588\u258c", "warn"), ("\u2584\u2584\u2584", cc)],
                    [("  ", "normal"), ("\u2584" + "\u2588" * 9 + "\u2584", cc)]]
        return [[(r"    \ | /       ", "warn")], [("   - (", "warn"), (") .--.   ", cc)], [(" .-(    ).--.   ", cc)]]
    top = [[("      ", "normal"), ("\u2584\u2584\u2584\u2584", cc)] if dos else [("     .--.       ", cc)],
           [("   ", "normal"), ("\u2584\u2588\u2588\u2588\u2588\u2588\u2584\u2584\u2584", cc)] if dos else [("  .-(    ).--.  ", cc)]]
    if kind == "fog":
        return [[("  ~  ~  ~  ~  ~  ", "dim")], [(" ~  ~  ~  ~  ~  ~", "dim")], [("  ~  ~  ~  ~  ~  ", "dim")]]
    if kind == "cloudy":
        return top + [[("  " + "\u2580" * 10 + "  ", cc)] if dos else [(" (___.__)(____)  ", cc)]]
    if kind == "rain":
        return top + [[("   ' ' ' ' ' ' '  ", "blue")]]
    if kind == "storm":
        return top + [[("   ' ", "blue"), ("/", "warn"), (" ' ' ", "blue"), ("/", "warn"), (" ' '    ", "blue")]]
    if kind == "snow":
        return top + [[("   *  *  *  *  *  ", "normal")]]
    if kind == "hail":
        return top + [[("   o  o o  o  o o ", "cyan")]]
    return [[("", "normal")]] * 3


def _ground(terrain, dos):
    """Two rows of ground. A third, listed first, is laid over the empty cells of the lowest row of sky (tall trees, peaks)."""
    if terrain == "forest":
        if dos:
            tip, body, trunk = "▄", "█", [("▄█", "good"), ("█", "brown"), ("█▄", "good")]
            return [[("  " + tip + "    " + tip + "    " + tip + "  ", "good")],                   # pines: a point, a wider row,
                    [(" " + tip + body + tip + "  " + tip + body + tip + "  " + tip + body + tip + " ", "good")],
                    trunk * 3 + [(tip, "good")]]                                                   # and a brown trunk at the foot
        return [[("  ^   ^^  ^   ^ ", "good")], [(r" /|\ /||\ /|\ /|\ ", "good")]]
    if terrain == "water":
        return [[("≈" * 16 if dos else "~" * 16, "blue")], [("▒" * 16 if dos else "~ ~~ ~~~ ~~ ~ ~~", "cyan")]]
    if terrain == "field":
        return [[("  ,  '  ,   '  ,  ", "good")], [("▓" * 16 if dos else ",.,'.,.,'.,.,'.,.", "good")]]
    if terrain == "street":
        return [[(" ▄█▄ ▄▄█▄ ▄█▄▄" if dos else " _[]_  _[]__[]_ ", "dim")],
                [("▓" * 16 if dos else "=====-=====-====", "dim")]]
    if terrain == "hills":
        if dos:
            return [[("      ▄       ▄    ", "normal")],
                    [("     ", "normal"), ("▄", "dim"), ("███", "dim"), ("▄", "dim"), ("   ", "normal"), ("▄", "dim"),
                     ("███", "dim"), ("▄", "dim"), (" ", "normal")],
                    [("▓", "good"), ("▄", "dim"), ("█" * 12, "dim"), ("▄", "dim"), ("▓", "good")]]
        return [[("   /\     /\     ".replace("\\\\", chr(92)), "dim")], [(" _/  \_ _/  \__ ".replace("\\\\", chr(92)), "good")]]
    return [[("", "normal")], [("▓" * 16 if dos else "_" * 16, "good")]]


def _room(night, dos):
    win = "dim" if night else "warn"
    if dos:
        return [[("┌" + "─" * 14 + "┐", "dim")],
                [("│ ", "dim"), ("██", win), ("   ", "dim"), ("██", win), ("   ", "dim"), ("██", win), (" │", "dim")],
                [("│" + " " * 14 + "│", "dim")], [("│  ", "dim"), ("▄▄▄▄▄▄", "normal"), ("      │", "dim")],
                [("└" + "─" * 14 + "┘", "dim")]]
    return [[(".--------------.", "dim")], [("| ", "dim"), ("[]", win), ("   ", "dim"), ("[]", win), ("   ", "dim"), ("[]", win), (" |", "dim")],
            [("|" + " " * 14 + "|", "dim")], [("|  ", "dim"), ("______", "normal"), ("      |", "dim")], [("'--------------'", "dim")]]


def art(weather, terrain, night, mist=0, dos=False, tone="light"):
    """ART_H rows of (text, role) pieces, each exactly ART_W characters across. `mist` is 0 for none, or 1 (ankle-deep), 2
    (waist-deep) or 3 (wreathed): wisps are laid over the top of the ground, then the lowest sky, then more of the sky."""
    if terrain == "indoors":
        return [_pieces(r) for r in _cells(_room(night, dos))]
    sky = _cells(_sky(weather or "clear", night, dos, tone)) if weather else _cells([[("", "normal")]] * 3)
    ground = _cells(_ground(terrain, dos))
    if len(ground) == 3:                                 # tall things (trees, peaks): over the empty part of the lowest sky
        over = ground.pop(0)
        sky[2] = [o if (c[0] == " " and o[0] != " ") else c for c, o in zip(sky[2], over)]
    level = int(mist or 0)

    def wisp(row, every):
        return [("~", "dim") if (ch == " " and i % every == 0) else (ch, role) for i, (ch, role) in enumerate(row)]
    if level >= 1:                                       # wisps in the empty places just above the ground
        ground[0] = wisp(ground[0], 2)
    if level >= 2:
        sky[2] = wisp(sky[2], 3)
    if level >= 3:
        sky[1] = wisp(sky[1], 2)
        sky[2] = wisp(sky[2], 2)
    return [_pieces(r) for r in sky + ground]


# ---- putting the box together ----------------------------------------------------------------------------------------------
def _fit(text, width):
    text = str(text)
    return text if len(text) <= width else text[:max(0, width - 1)] + "…"


def _pad(pieces, width):
    n = sum(len(t) for t, _r in pieces)
    return list(pieces) + ([(" " * (width - n), "normal")] if n < width else [])


def sky_lines(info):
    """The box's lines for one moment. `info` (all optional): area, coords, hour, clock, moon {name, lit, full}, unit ('f'/'c'),
    art_on, dos, width, and the game's own environment: temp_f, temp_c, weather, sky, terrain, mist, period."""
    env = info if isinstance(info, dict) else {}
    w = env.get("width")
    width = max(LEFT_W + GAP + 12, w if isinstance(w, int) and not isinstance(w, bool) else 44)
    right_w = width - LEFT_W - GAP
    night = is_night(env.get("hour"), env.get("daytime") or env.get("period"))
    weather, terrain = weather_kind(env), terrain_kind(env)
    mist = mist_level(env)
    art_on = env.get("art_on", True)
    temp = temp_text(env, env.get("unit") or "c")
    known = bool(weather or terrain or temp)

    left = []                                                    # LEFT_W characters per row
    if art_on and known:
        rows = art(weather, terrain, night, mist, bool(env.get("dos")), cloud_tone(env))
        for i, r in enumerate(rows):
            tail = [(" ", "normal"), (temp.rjust(LEFT_W - ART_W - 1), "head")] if (i == 0 and temp) else []
            left.append(_pad(r + tail, LEFT_W))
    elif known:
        words = [w for w in (temp, weather_words(env)) if w]
        left = [_pad([(_fit(w, LEFT_W), "head" if i == 0 else "normal")], LEFT_W) for i, w in enumerate(words)]
    right = []
    name = _fit(env.get("area") or env.get("neighborhood") or env.get("neighbourhood") or "", right_w)
    coords = _word(env.get("coords"))
    if name or coords:
        gap = max(1, right_w - len(name) - len(coords))
        right.append([(name, "head"), (" " * gap, "normal"), (coords, "dim")] if coords and len(name) + 1 + len(coords) <= right_w
                     else [(name, "head")])
    right.append([])
    right.append([("Mist: ", "dim"), (_fit(MIST_WORDS[mist], right_w - 6), "cyan")] if mist else [])
    right.append([])
    clock = _word(env.get("clock"))
    if clock:
        period = _word(env.get("daytime") or env.get("period"))
        both = clock + "  " + period
        right.append([(_fit(both if period and len(both) <= right_w else clock, right_w), "normal")])    # (the word only when it fits)
    moon = env.get("moon")
    if isinstance(moon, str) and moon.strip():                       # the game sends just the phase ("full" only on the full-moon night)
        moon = {"name": moon.strip(), "full": moon.strip().lower() == "full"}
    moon = moon if isinstance(moon, dict) else None
    if moon and _word(moon.get("name")):
        lit = moon.get("lit")
        pct = " %d%%" % round(lit * 100) if isinstance(lit, (int, float)) and not isinstance(lit, bool) and 0 <= lit <= 1 else ""
        text = ("Full moon" if _word(moon["name"]).lower() == "full" else _word(moon["name"]).capitalize()) + pct
        right.append([(_fit(text, right_w), "magenta" if moon.get("full") else "normal")])
        if moon.get("full"):
            right.append([(_fit("A full-moon night", right_w), "magenta")])
    out = []
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else [(" " * LEFT_W, "normal")]
        r = right[i] if i < len(right) else []
        out.append(l + [(" " * GAP, "normal")] + r)
    return out
