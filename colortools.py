"""Colour helpers for the game's xterm-256 colour codes (stdlib only, no GUI).

The game writes a colour as a backtick and three digits, `045, and `x puts it back to normal.
This module converts hex colours to the nearest xterm colour and builds gradients from a list of
xterm colours, applying them to text in several ways."""
import math
import random
import re

# ---------------------------------------------------------------- the xterm palette
_BASE16 = ["000000", "cd0000", "00cd00", "cdcd00", "0000ee", "cd00cd", "00cdcd", "e5e5e5",
           "7f7f7f", "ff0000", "00ff00", "ffff00", "5c5cff", "ff00ff", "00ffff", "ffffff"]
_LEVELS = (0, 95, 135, 175, 215, 255)


def _build_palette():
    out = ["#" + h for h in _BASE16]
    for r in _LEVELS:
        for g in _LEVELS:
            for b in _LEVELS:
                out.append("#%02x%02x%02x" % (r, g, b))
    for i in range(24):
        v = 8 + 10 * i
        out.append("#%02x%02x%02x" % (v, v, v))
    return out


XTERM = _build_palette()
assert len(XTERM) == 256


def parse_hex(text):
    """'#ff8800', 'ff8800', '0xff8800', '#f80' -> (r, g, b); raises ValueError."""
    t = str(text if text is not None else "").strip().lower()
    for pre in ("#", "0x"):
        if t.startswith(pre):
            t = t[len(pre):]
    if len(t) == 3 and re.fullmatch(r"[0-9a-f]{3}", t):
        t = "".join(c * 2 for c in t)
    if not re.fullmatch(r"[0-9a-f]{6}", t):
        raise ValueError("'%s' is not a hex colour (try ff8800 or #f80)." % str(text)[:20])
    return int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def _lab(rgb):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3.0) if t > 0.008856 else 7.787 * t + 16 / 116.0
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


_LABS = [_lab(tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))) for h in XTERM]


def nearest_xterm(rgb, system=False):
    """(index, hex, distance) of the xterm colour that looks closest (CIE Lab distance).
    The first 16 colours depend on the player's palette, so they are skipped unless system=True."""
    lab = _lab(tuple(max(0, min(255, int(v))) for v in rgb))
    best, bd = 16, 1e18
    for i in range(0 if system else 16, 256):
        d = math.dist(lab, _LABS[i])
        if d < bd:
            best, bd = i, d
    return best, XTERM[best], bd


def code(index):
    """The game's colour code for an xterm colour: 45 -> '`045'."""
    return "`%03d" % int(index)


RESET = "`x"


def parse_colours(text, limit=32):
    """'196 202, `208 #ffcc00' -> [196, 202, 208, 220]. Numbers are xterm codes (0-255); hex colours
    are converted to the nearest one. Raises ValueError on anything else."""
    out = []
    for tok in re.split(r"[\s,;]+", str(text or "").strip()):
        if not tok:
            continue
        t = tok.lstrip("`")
        if t.isdigit() and len(t) <= 3:
            n = int(t)
            if n > 255:
                raise ValueError("%d is not an xterm colour (0-255)." % n)
            out.append(n)
        else:
            out.append(nearest_xterm(parse_hex(tok))[0])
        if len(out) > limit:
            raise ValueError("At most %d colours in a pattern." % limit)
    if not out:
        raise ValueError("Give at least one colour (0-255 or a hex colour).")
    return out


# ---------------------------------------------------------------- gradients
PRESETS = {
    "Fire": [196, 202, 208, 214, 220, 226],
    "Ocean": [17, 18, 19, 25, 31, 38, 45, 51],
    "Sunset": [53, 89, 125, 161, 197, 203, 209, 215, 221],
    "Forest": [22, 28, 34, 40, 46, 82, 118],
    "Rainbow": [196, 208, 226, 46, 51, 21, 93, 201],
    "Ice": [255, 195, 159, 123, 87, 51, 45],
    "Gold": [94, 136, 178, 220, 226, 229],
    "Blood": [52, 88, 124, 160, 196, 9],
    "Twilight": [54, 55, 56, 92, 128, 164, 200],
    "Ash": [232, 236, 240, 244, 248, 252, 255],
    "Bramble": [53, 89, 22, 28, 64, 100],
    "Moonlight": [17, 60, 103, 146, 189, 231],
}
MODES = ("stretch", "cycle", "middle", "edges", "bounce", "random", "word", "line")
MODE_HELP = {
    "stretch": "spread the whole pattern from the first letter to the last",
    "cycle": "repeat the pattern again and again",
    "middle": "start in the middle, end at the edges",
    "edges": "start at the edges, end in the middle",
    "bounce": "forward and back through the pattern",
    "random": "a random colour from the pattern for each letter",
    "word": "one colour per word, stretched across the line",
    "line": "one colour per line (use \\n between lines), stretched down",
}
MAX_TEXT = 1500
MAX_OUT = 6000


def _rgb(i):
    h = XTERM[i]
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def sample(stops, t, smooth=True):
    """Colour (xterm index) at position t in 0..1 along the pattern."""
    m = len(stops)
    if m == 1:
        return stops[0]
    t = max(0.0, min(1.0, t))
    if not smooth:
        return stops[min(m - 1, int(t * m))]
    pos = t * (m - 1)
    i = min(m - 2, int(pos))
    f = pos - i
    a, b = _rgb(stops[i]), _rgb(stops[i + 1])
    if f < 1e-9:
        return stops[i]
    return nearest_xterm(tuple(a[k] + (b[k] - a[k]) * f for k in range(3)))[0]


def _colour_for(stops, mode, j, n, smooth, rnd):
    if n <= 1:
        return stops[0] if mode != "middle" else stops[0]
    if mode == "stretch":
        return sample(stops, j / (n - 1.0), smooth)
    if mode == "cycle":
        return stops[j % len(stops)]
    if mode == "middle":
        c = (n - 1) / 2.0
        return sample(stops, abs(j - c) / c, smooth)
    if mode == "edges":
        c = (n - 1) / 2.0
        return sample(stops, 1.0 - abs(j - c) / c, smooth)
    if mode == "bounce":
        m = len(stops)
        if m == 1:
            return stops[0]
        p = j % (2 * (m - 1))
        return stops[p if p < m else 2 * (m - 1) - p]
    if mode == "random":
        return rnd.choice(stops)
    return stops[0]


def apply(text, stops, mode="stretch", smooth=True, seed=None, reset=True):
    """Colour `text` with the pattern. Returns the game text with `NNN codes in it.
    Spaces carry no code; a code is only written where the colour changes; a literal backtick is
    doubled so the game shows it. Raises ValueError for bad input or too-long results."""
    if mode not in MODES:
        raise ValueError("Unknown way to apply a pattern: %s" % str(mode)[:20])
    try:
        stops = [int(s) for s in stops]
    except (TypeError, ValueError):
        raise ValueError("The pattern must be a list of xterm colours.")
    if not stops or any(not 0 <= s <= 255 for s in stops) or len(stops) > 64:
        raise ValueError("The pattern needs 1 to 64 colours between 0 and 255.")
    text = str(text if text is not None else "")
    if len(text) > MAX_TEXT:
        raise ValueError("That is too long (at most %d characters)." % MAX_TEXT)
    rnd = random.Random(seed)
    lines = text.split("\n")
    out_lines = []
    if mode == "line":
        for i, ln in enumerate(lines):
            c = sample(stops, i / (len(lines) - 1.0), smooth) if len(lines) > 1 else stops[0]
            out_lines.append(_emit([(ch, c) for ch in ln]))
    else:
        for ln in lines:
            if mode == "word":
                words = re.findall(r"\S+", ln)
                cols, pieces = [], []
                for w_i in range(len(words)):
                    cols.append(sample(stops, w_i / (len(words) - 1.0), smooth) if len(words) > 1 else stops[0])
                w_i, k, cur = -1, 0, []
                inword = False
                for ch in ln:
                    if ch.isspace():
                        inword = False
                        cur.append((ch, None))
                    else:
                        if not inword:
                            w_i += 1
                            inword = True
                        cur.append((ch, cols[w_i]))
                out_lines.append(_emit(cur))
            else:
                chars = [ch for ch in ln if not ch.isspace()]
                n, j, cur = len(chars), 0, []
                for ch in ln:
                    if ch.isspace():
                        cur.append((ch, None))
                    else:
                        cur.append((ch, _colour_for(stops, mode, j, n, smooth, rnd)))
                        j += 1
                out_lines.append(_emit(cur))
    result = "\n".join(out_lines)
    if reset and "`" in result:
        result += RESET
    if len(result) > MAX_OUT:
        raise ValueError("The coloured text would be %d characters; the game takes about %d. Shorten it."
                         % (len(result), MAX_OUT))
    return result


def _emit(pairs):
    out, last = [], None
    for ch, col in pairs:
        if col is not None and col != last:
            out.append(code(col))
            last = col
        out.append("``" if ch == "`" else ch)
    return "".join(out)


def strip_codes(text):
    """Remove `NNN, `#rrggbb and one-letter colour codes (keeps ``)."""
    return re.sub(r"``|`(?:\d{3}|#[0-9a-fA-F]{6}|[A-Za-z*/])",
                  lambda m: "``" if m.group() == "``" else "", str(text if text is not None else ""))


# ---------------------------------------------------------------- saved patterns
MAX_SAVED = 60


def validate_saved(raw):
    """Saved patterns from the settings file: [{'name', 'colours': [..]}], cleaned."""
    out, seen = [], set(k.lower() for k in PRESETS)
    if not isinstance(raw, list):
        return out
    for item in raw[:200]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        cols = item.get("colours")
        if not isinstance(name, str) or not isinstance(cols, list):
            continue
        name = " ".join("".join(c for c in name if c.isprintable()).split())[:30]
        if not name or name.lower() in seen:
            continue
        try:
            cols = [int(c) for c in cols[:32] if isinstance(c, int) and not isinstance(c, bool)]
        except (TypeError, ValueError):
            continue
        if not cols or any(not 0 <= c <= 255 for c in cols):
            continue
        seen.add(name.lower())
        out.append({"name": name, "colours": cols})
        if len(out) >= MAX_SAVED:
            break
    return out


def find_pattern(name, saved):
    """Colours for a preset or saved pattern name (case-insensitive), or None."""
    key = str(name or "").strip().lower()
    for k, v in PRESETS.items():
        if k.lower() == key:
            return list(v)
    for s in saved or []:
        if s["name"].lower() == key:
            return list(s["colours"])
    return None


def all_pattern_names(saved):
    return list(PRESETS) + [s["name"] for s in saved or []]


# ---------------------------------------------------------------- reading coded text back / converting lists
_RUN_TOKEN = re.compile(r"``|`(\d{3})|`x|`")


def runs(coded):
    """Game text with `NNN codes -> [(text, xterm index or None)] (None = normal colour). Anything that
    is not a colour code is kept as text."""
    out, cur, pos, text = [], None, 0, str(coded if coded is not None else "")
    buf = []

    def flush():
        if buf:
            out.append(("".join(buf), cur))
            buf.clear()
    for m in _RUN_TOKEN.finditer(text):
        buf.append(text[pos:m.start()])
        tok = m.group()
        pos = m.end()
        if tok == "``":
            buf.append("`")
        elif tok == "`x":
            flush()
            cur = None
        elif m.group(1) is not None and int(m.group(1)) <= 255:
            flush()
            cur = int(m.group(1))
        else:
            buf.append(tok)
    buf.append(text[pos:])
    flush()
    return [(t, c) for t, c in out if t]


def convert_many(text, system=False):
    """'ff8800 #00f' -> [{'input', 'index', 'hex', 'code', 'asked'}]; bad entries have 'error'."""
    rows = []
    for tok in [t for t in re.split(r"[\s,;]+", str(text if text is not None else "")) if t][:40]:
        try:
            rgb = parse_hex(tok)
        except ValueError as e:
            rows.append({"input": tok[:20], "error": str(e)})
            continue
        i, hx, d = nearest_xterm(rgb, system)
        rows.append({"input": tok[:20], "asked": rgb_to_hex(rgb), "index": i, "hex": hx, "code": code(i),
                     "distance": round(d, 1)})
    return rows


# ---------------------------------------------------------------- sharing a pattern as one line of text
SHARE_PREFIX = "sgrad1:"


def share_string(name, colours):
    """'sgrad1:Fire:196,202,208': one line that can be pasted into chat or a message."""
    name = " ".join("".join(c for c in str(name) if c.isprintable() and c not in ":,").split())[:30] or "Pattern"
    cols = [int(c) for c in colours][:32]
    if not cols or any(not 0 <= c <= 255 for c in cols):
        raise ValueError("A pattern needs 1 to 32 colours between 0 and 255.")
    return "%s%s:%s" % (SHARE_PREFIX, name, ",".join(str(c) for c in cols))


def parse_share(text):
    """(name, colours) from a shared line (found anywhere in the text); raises ValueError."""
    m = re.search(r"sgrad1:([^:\r\n]{1,30}):(\d{1,3}(?:,\d{1,3}){0,31})(?![\d,])", str(text or ""))
    if not m:
        raise ValueError("That is not a shared gradient (it should look like sgrad1:Fire:196,202,208).")
    cols = [int(x) for x in m.group(2).split(",")]
    if any(c > 255 for c in cols):
        raise ValueError("That gradient has a colour above 255.")
    name = " ".join("".join(c for c in m.group(1) if c.isprintable()).split())[:30]
    if not name:
        raise ValueError("That gradient has no name.")
    return name, cols


def spans(text):
    """[(start, end, xterm index or None, is_code)] covering `text`: the colour codes (`045, `x) and the
    runs of text each one colours. Offsets are characters."""
    text = str(text if text is not None else "")
    out, cur, pos = [], None, 0
    for m in _RUN_TOKEN.finditer(text):
        tok = m.group()
        if tok == "``" or (tok == "`" or (m.group(1) is not None and int(m.group(1)) > 255)):
            continue                                   # a literal backtick, or not a code: stays text
        if m.start() > pos:
            out.append((pos, m.start(), cur, False))
        out.append((m.start(), m.end(), None, True))
        cur = None if tok == "`x" else int(m.group(1))
        pos = m.end()
    if pos < len(text):
        out.append((pos, len(text), cur, False))
    return out


def colour_text(text, stops, mode="stretch", smooth=True, rng=None, seed=None):
    """Colour part (or all) of `text` with a gradient: the selected range (start, end) when given,
    otherwise everything. Colour codes already inside the range are removed first. Raises ValueError."""
    text = str(text if text is not None else "")
    a, b = (rng if rng and 0 <= rng[0] < rng[1] <= len(text) else (0, len(text)))
    seg = strip_codes(text[a:b]).replace("``", "`")
    return text[:a] + apply(seg, stops, mode, smooth, seed=seed, reset=True) + text[b:]


def strip_colour(text, rng=None):
    """The same text with the colour codes removed from the range (or from everything)."""
    text = str(text if text is not None else "")
    a, b = (rng if rng and 0 <= rng[0] < rng[1] <= len(text) else (0, len(text)))
    return text[:a] + strip_codes(text[a:b]) + text[b:]


# ---- the stop list as something you can edit with a picker -----------------------------------
MAX_STOPS = 32


def hsv_of(index):
    """(hue 0-360, saturation 0-1, value 0-1) of an xterm colour."""
    import colorsys
    r, g, b = (v / 255.0 for v in _rgb(int(index)))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s, v


def from_hsv(h, s, v, system=False):
    """The xterm colour (index, hex) nearest to a picked hue/saturation/value."""
    import colorsys
    r, g, b = colorsys.hsv_to_rgb((h % 360.0) / 360.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    i, hexv, _d = nearest_xterm((r * 255, g * 255, b * 255), system=system)
    return i, hexv


def from_hex(text, system=False):
    """The xterm colour (index, hex, exact) nearest to typed hex; `exact` when it needed no rounding.
    Raises ValueError for text that is not a hex colour."""
    rgb = parse_hex(text)
    i, hexv, d = nearest_xterm(rgb, system=system)
    return i, hexv, d < 0.5


def describe(index):
    """'45  #00d7ff' for showing next to a swatch."""
    return "%d  %s" % (int(index), XTERM[int(index)])


def palette_rows():
    """The 256 colours laid out for a picker: the 16 system colours (2 rows of 8), the 216-colour cube
    (12 rows of 18) and the 24 greys (2 rows of 12). Every index appears exactly once."""
    rows = [list(range(0, 8)), list(range(8, 16))]
    rows += [list(range(16 + 18 * r, 34 + 18 * r)) for r in range(12)]
    rows += [list(range(232, 244)), list(range(244, 256))]
    return rows


def preview_bar(stops, width, smooth=True):
    """`width` xterm colours showing how the pattern blends from end to end (for a gradient bar)."""
    stops = [int(s) for s in stops] or [7]
    width = max(1, int(width))
    return [sample(stops, (i / (width - 1.0)) if width > 1 else 0.0, smooth) for i in range(width)]


def add_stop(stops, at=None, colour=None):
    """New list with a stop added after position `at` (default: the end). Without a colour it takes the
    blend of its neighbours, so adding one does not change how the gradient looks."""
    stops = [int(s) for s in stops]
    if len(stops) >= MAX_STOPS:
        return stops, len(stops) - 1
    at = len(stops) - 1 if at is None else max(0, min(len(stops) - 1, int(at)))
    if colour is None:
        if not stops:
            colour = 196
        elif at + 1 < len(stops):
            colour = sample([stops[at], stops[at + 1]], 0.5)
        else:
            colour = stops[at]
    stops.insert(at + 1, int(colour))
    return stops, at + 1


def remove_stop(stops, at):
    """New list without stop `at` (the last one cannot be removed) and the position to select next."""
    stops = [int(s) for s in stops]
    if len(stops) <= 1 or not 0 <= at < len(stops):
        return stops, max(0, min(at, len(stops) - 1))
    del stops[at]
    return stops, min(at, len(stops) - 1)


def move_stop(stops, at, step):
    """New list with stop `at` moved one place left (-1) or right (+1), and its new position."""
    stops = [int(s) for s in stops]
    to = at + (1 if step > 0 else -1)
    if not (0 <= at < len(stops) and 0 <= to < len(stops)):
        return stops, at
    stops[at], stops[to] = stops[to], stops[at]
    return stops, to


def stops_text(stops):
    """The stop list as the text form patterns have always used ('196,202,208')."""
    return ",".join(str(int(s)) for s in stops)


_FAMILIES = ("Red", "Orange", "Yellow", "Lime", "Green", "Mint", "Cyan", "Sky", "Blue", "Violet", "Magenta", "Rose")


def hue_families():
    """The palette grouped for finding a colour by eye: [(name, [xterm indices light to dark])]. The 16 system
    colours (their look depends on the player's terminal) come first, then the greys, then twelve hue families.
    Every index appears exactly once."""
    fams = [("System", list(range(16))), ("Grey", [])]
    buckets = {n: [] for n in _FAMILIES}
    for i in range(16, 256):
        h, s, v = hsv_of(i)
        if s < 0.12:
            fams[1][1].append(i)
        else:
            buckets[_FAMILIES[int(((h + 15) % 360) // 30)]].append(i)
    key = lambda i: -(0.2126 * _rgb(i)[0] + 0.7152 * _rgb(i)[1] + 0.0722 * _rgb(i)[2])
    fams[1][1].sort(key=key)
    return fams + [(n, sorted(buckets[n], key=key)) for n in _FAMILIES]
