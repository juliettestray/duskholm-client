"""Adversarial tests for the pure theme/colour functions in sanctuary.py.
Every check runs; PASS/FAIL printed per check; exit code 1 if any fail. Stdlib only."""
import colorsys, copy, json, math, os, random, shutil, sys, tempfile, time, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from sanctuary import (rel_luminance, contrast_ratio, ensure_contrast, validate_theme,
                             BUILTIN_SKINS, user_skin_dir, load_user_skins, save_user_skin,
                             HEX_RE, COLOR_KEYS, RELIEFS)

NOTES = []          # informational lines (robustness reports, tolerances)
CHECKS = []


def check(f):
    CHECKS.append(f)
    return f


class Fails:
    def __init__(self, cap=3):
        self.items, self.n, self.cap = [], 0, cap

    def add(self, msg):
        self.n += 1
        if len(self.items) < self.cap:
            self.items.append(msg)

    def __bool__(self):
        return self.n > 0


def rhex(rng):
    return "#%06x" % rng.randrange(0x1000000)


import re as _re
_STRICT = _re.compile(r"#[0-9a-fA-F]{6}")


def valid_hex(s):
    return isinstance(s, str) and bool(_STRICT.fullmatch(s))


def lhex(s):
    return valid_hex(s) and s == s.lower()


GREY_BGS = ["#%02x%02x%02x" % (v, v, v) for v in (0, 16, 40, 80, 119, 120, 128, 150, 180, 220, 255)]
EXTREME_BGS = ["#000000", "#ffffff", "#101114", "#0b0a10", "#fafaf7", "#ff0000", "#00ff00",
               "#0000ff", "#ffff00", "#00ffff", "#ff00ff", "#808000", "#008080"] + GREY_BGS


def hls(h):
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)


@check
def c1_contrast_ratio():
    f = Fails()
    r = contrast_ratio("#000000", "#ffffff")
    if abs(r - 21) > 0.01:
        f.add("black/white = %r" % r)
    rng = random.Random(1)
    for _ in range(5000):
        a, b = rhex(rng), rhex(rng)
        x, y = contrast_ratio(a, b), contrast_ratio(b, a)
        if x != y:
            f.add("asymmetric %s %s: %r vs %r" % (a, b, x, y))
        if not (1.0 <= x <= 21.0 + 1e-9):
            f.add("out of range %s %s: %r" % (a, b, x))
        if contrast_ratio(a, a) != 1:
            f.add("identity %s: %r" % (a, contrast_ratio(a, a)))
    return f


def meets_possible(bg, ratio):
    return max(contrast_ratio("#000000", bg), contrast_ratio("#ffffff", bg)) >= ratio


@check
def c2_ensure_contrast_properties():
    f = Fails(6)
    rng = random.Random(2)
    HUE_TOL = 0.02          # in hue units (0..1) == 7.2 degrees
    hue_outliers = []
    triples = []
    for _ in range(6000):
        fg = rhex(rng)
        bg = rng.choice(EXTREME_BGS) if rng.random() < 0.6 else rhex(rng)
        triples.append((fg, bg, round(rng.uniform(1, 10), 2)))
    for fg in ("#000000", "#ffffff", "#808080", "#ff0000", "#0000ff", "#00008b"):
        for bg in EXTREME_BGS:
            for ratio in (1.0, 1.5, 3, 4.5, 7, 10):
                triples.append((fg, bg, ratio))
    for fg, bg, ratio in triples:
        tag = "ensure_contrast(%r,%r,%r)" % (fg, bg, ratio)
        try:
            out = ensure_contrast(fg, bg, ratio)
        except Exception as e:
            f.add("%s raised %r" % (tag, e))
            continue
        if not lhex(out):
            f.add("%s -> invalid %r" % (tag, out))
            continue
        cin, cout = contrast_ratio(fg, bg), contrast_ratio(out, bg)
        if ratio <= 1.0 and out != fg:
            f.add("%s ratio<=1 changed -> %s" % (tag, out))
        if cin >= ratio and out != fg:
            f.add("%s already meets (%.3f) but changed -> %s" % (tag, cin, out))
        if meets_possible(bg, ratio) and cout < ratio - 0.01:
            f.add("%s achievable but got %.3f (%s)" % (tag, cout, out))
        if cout < cin - 1e-9:
            f.add("%s LESS contrast: %.3f -> %.3f (%s)" % (tag, cin, cout, out))
        try:
            if ensure_contrast(out, bg, ratio) != out:
                f.add("%s not idempotent: %s -> %s" % (tag, out, ensure_contrast(out, bg, ratio)))
        except Exception as e:
            f.add("%s idempotence raised %r" % (tag, e))
        if cin < ratio and out != fg:
            lb = rel_luminance(bg)
            preferred_ok = (contrast_ratio("#ffffff" if lb < 0.5 else "#000000", bg) >= ratio)
            if preferred_ok:
                li, lo = rel_luminance(fg), rel_luminance(out)
                if lb < 0.5 and lo < li - 1e-9:
                    f.add("%s dark bg but darker: %s -> %s" % (tag, fg, out))
                if lb >= 0.5 and lo > li + 1e-9:
                    f.add("%s light bg but lighter: %s -> %s" % (tag, fg, out))
            # minimal change
            if meets_possible(bg, ratio) and out not in ("#000000", "#ffffff") and cout > ratio + 0.5:
                f.add("%s overshoot: %.3f (want < %.2f) -> %s" % (tag, cout, ratio + 0.5, out))
            # hue preservation
            h0, l0, s0 = hls(fg)
            h1, l1, s1 = hls(out)
            if s0 > 0.3 and 0.1 < l1 < 0.9 and abs(l1 - l0) < 0.3 and 0.1 < l0 < 0.9:
                dh = abs(h0 - h1)
                dh = min(dh, 1 - dh)
                if dh > HUE_TOL:
                    hue_outliers.append("%s -> %s dh=%.3f" % (tag, out, dh))
    for t in hue_outliers[:3]:
        f.add("hue drift (> %.2f): %s" % (HUE_TOL, t))
    f.n += max(0, len(hue_outliers) - 3)
    NOTES.append("c2: hue tolerance %.2f (7.2 deg) for s>0.3, |dL|<0.3, 0.1<L<0.9; outliers=%d"
                 % (HUE_TOL, len(hue_outliers)))
    return f


@check
def c2b_dark_blues_readable():
    f = Fails(6)
    for fg in ("#00008b", "#000080", "#0000aa", "#2472c8", "#0000ff", "#00003c"):
        for bg in ("#000000", "#101114", "#0b0a10"):
            for ratio in (3, 4.5, 7):
                out = ensure_contrast(fg, bg, ratio)
                c = contrast_ratio(out, bg)
                r, g, b = (int(out[i:i + 2], 16) for i in (1, 3, 5))
                if c < ratio - 0.01:
                    f.add("%s on %s @%s -> %s contrast %.2f" % (fg, bg, ratio, out, c))
                if b < max(r, g):
                    f.add("%s on %s @%s -> %s not blue-dominant" % (fg, bg, ratio, out))
                # "recognisably blue": blue must clearly exceed red
                if b < r + 20 and not (r == g == b):
                    f.add("%s on %s @%s -> %s barely blue (r=%d b=%d)" % (fg, bg, ratio, out, r, b))
    return f


@check
def c3_ensure_contrast_robustness():
    f = Fails()
    for bad in ("#fff", "red", "", None, "#GGGGGG", 123, "#12345", "#1234567", " #ffffff", "#FFFFFF"):
        for args in ((bad, "#000000", 4.5), ("#808080", bad, 4.5)):
            try:
                out = ensure_contrast(*args)
                NOTES.append("c3: ensure_contrast%r -> returned %r" % (args, out))
                # Only upper-case valid hex may legitimately return a valid colour.
            except Exception as e:
                NOTES.append("c3: ensure_contrast%r -> raises %s" % (args, type(e).__name__))
    # ratio edge cases (valid colours)
    for ratio in (0, -5, 1, 21, 25, 1000, float("inf")):
        try:
            out = ensure_contrast("#222222", "#000000", ratio)
            if not lhex(out):
                f.add("ratio=%r -> invalid %r" % (ratio, out))
        except Exception as e:
            f.add("ratio=%r raised %r" % (ratio, e))
    for ratio in (float("nan"),):
        try:
            out = ensure_contrast("#222222", "#000000", ratio)
            if not lhex(out):
                f.add("ratio=nan -> invalid %r" % (out,))
        except Exception as e:
            f.add("ratio=nan raised %r" % (e,))
    # upper-case input: contract says #rrggbb; result must at least be valid hex
    try:
        out = ensure_contrast("#0000AA", "#000000", 4.5)
        if not valid_hex(out):
            f.add("uppercase fg -> %r" % (out,))
        elif out != out.lower():
            NOTES.append("c3: uppercase fg #0000AA -> %r (mixed case output, informational)" % out)
    except Exception as e:
        f.add("uppercase fg raised %r" % (e,))
    return f


@check
def c4_performance():
    f = Fails()
    rng = random.Random(4)
    pool = [rhex(rng) for _ in range(5000)]
    t = time.time()
    for i in range(200000):
        ensure_contrast(pool[i % 5000], "#101114", 4.5)
    d = time.time() - t
    NOTES.append("c4: 200k calls / 5000 colours: %.2fs" % d)
    if d >= 10:
        f.add("200k warm calls took %.2fs" % d)
    t = time.time()
    seen = set()
    while len(seen) < 20000:
        seen.add(rhex(rng))
    for c in seen:
        ensure_contrast(c, "#000000", 7.0)
    d = time.time() - t
    NOTES.append("c4: cold 20k distinct: %.2fs" % d)
    if d >= 10:
        f.add("cold 20k run took %.2fs" % d)
    return f


# ---------------------------------------------------------------- validate_theme fuzz
def theme_problems(t):
    p = []
    if not isinstance(t, dict):
        return ["not a dict: %r" % type(t)]
    for k in COLOR_KEYS:
        if not lhex(t.get(k)):
            p.append("%s=%r" % (k, t.get(k)))
    a = t.get("ansi")
    if not (isinstance(a, list) and len(a) == 16 and all(lhex(c) for c in a)):
        p.append("ansi bad: %r" % (a if not isinstance(a, list) else [c for c in a if not lhex(c)] or len(a)))
    mc = t.get("min_contrast")
    if not (type(mc) is float and 1.0 <= mc <= 10.0):
        p.append("min_contrast=%r" % (mc,))
    fo = t.get("fonts")
    if not (isinstance(fo, list) and len(fo) <= 8 and all(isinstance(x, str) and len(x) < 60 for x in fo)):
        p.append("fonts bad")
    if t.get("relief") not in RELIEFS:
        p.append("relief=%r" % (t.get("relief"),))
    n = t.get("name")
    if not (isinstance(n, str) and 1 <= len(n) <= 40 and n.isprintable()):
        p.append("name=%r" % (n if not isinstance(n, str) else n[:50],))
    bl = t.get("blurb")
    if not (isinstance(bl, str) and bl.isprintable() and len(bl) <= 120):
        p.append("blurb bad: %r" % (bl if not isinstance(bl, str) else bl[:50],))
    return p


def junk_hex(rng):
    return rng.choice(["#12345g", "#abc", "red", 123, None, " #aabbcc", "#aabbcc ", "#aabbcc\n",
                       "#AABBCC", "#aAbBcC", "#1234567", "", "#12345", [], {}, 1.5, True,
                       "#\u0661\u0662\u0663\u0664\u0665\u0666", "#aabbcc\x00"])


def rand_value(rng, depth=0):
    r = rng.random()
    if depth > 3 or r < 0.5:
        return rng.choice([None, True, 0, -1, 1.5, "x", "", "#112233", "#ABCDEF", float("nan"),
                           float("inf"), "a" * 100, [], {}])
    if r < 0.75:
        return [rand_value(rng, depth + 1) for _ in range(rng.randrange(4))]
    return {rng.choice(["a", "16", "x", 3]): rand_value(rng, depth + 1) for _ in range(rng.randrange(4))}


def rand_theme_dict(rng):
    d = {}
    for k in COLOR_KEYS:
        r = rng.random()
        if r < 0.4:
            d[k] = rhex(rng) if rng.random() < .5 else rhex(rng).upper().replace("X", "x")
        elif r < 0.7:
            d[k] = junk_hex(rng)
    r = rng.random()
    if r < 0.2:
        d["ansi"] = [rhex(rng) for _ in range(16)]
    elif r < 0.3:
        d["ansi"] = [rhex(rng) for _ in range(rng.choice([0, 1, 15, 17, 32]))]
    elif r < 0.4:
        d["ansi"] = {rng.choice(["0", "4", "15", "16", "-1", "x", "", "Ù£", "04", " 4", "4.0", 4, None]):
                     rng.choice([rhex(rng), junk_hex(rng)]) for _ in range(rng.randrange(6))}
    elif r < 0.5:
        d["ansi"] = [rhex(rng) if rng.random() < .9 else junk_hex(rng) for _ in range(16)]
    elif r < 0.6:
        d["ansi"] = rng.choice(["#112233", 5, None, "x" * 16, (1, 2), True])
    if rng.random() < .7:
        d["min_contrast"] = rng.choice([0, 0.99, 10.01, True, False, "x", float("nan"), float("inf"),
                                        float("-inf"), 5, 1, 10, 1.0, 4.5, None, [], -3, 1e308, "4.5"])
    r = rng.random()
    if r < .6:
        d["fonts"] = rng.choice([
            ["Consolas", 5, None, "x" * 10000, "  Cascadia Mono  ", "", "   ", ["a"], {"a": 1}],
            ["f%d" % i for i in range(100)], "Consolas", None, 5, [], ["a" * 59, "a" * 60],
            ["\n", "\t x \t", "x\x00y"], ["ok"] * 8, ["ok"] * 9])
    if rng.random() < .6:
        d["relief"] = rng.choice(RELIEFS + ("bogus", "", None, 5, ["flat"], "FLAT", {}))
    if rng.random() < .7:
        d["name"] = rng.choice(["Good", "a\nb", "\x00\x01", "x" * 10000, "", "   ", "  pad  ", 5, None,
                                "\u202eevil", "tab\tname", "Ã©" * 100, "\ud800", "\x1b[31mred", "a" * 40,
                                "a" * 41, "\u200b", ["x"]])
    if rng.random() < .6:
        d["blurb"] = rng.choice(["ok", "x" * 10000, "line1\nline2", None, 5, "\x00" * 200, "Ã©" * 500])
    for _ in range(rng.randrange(4)):
        d[rng.choice(["extra", "__proto__", "x", "bg2", "", 5, "Ansi", "BG"])] = rand_value(rng)
    if rng.random() < .1:   # huge nested
        v = []
        for _ in range(200):
            v = [v]
        d["extra"] = v
    return d


@check
def c5_validate_theme_fuzz():
    f = Fails(6)
    for bad in (None, [], [1], "str", 5, 1.5, True, (), b"x", {1, 2}):
        try:
            r = validate_theme(bad)
            if r is not None:
                f.add("validate_theme(%r) -> %r (expected None)" % (bad, r))
        except Exception as e:
            f.add("validate_theme(%r) raised %r" % (bad, e))
    snap_builtin = copy.deepcopy(BUILTIN_SKINS)
    rng = random.Random(5)
    bases = [None, dict(BUILTIN_SKINS["Moody"]), BUILTIN_SKINS["Retro DOS"], "x", [], 5]
    for i in range(2000):
        d = rand_theme_dict(rng)
        base = rng.choice(bases)
        dsnap = copy.deepcopy(d)
        bsnap = copy.deepcopy(base)
        try:
            t = validate_theme(d, base)
        except Exception as e:
            f.add("#%d raised %s: %s  input=%r" % (i, type(e).__name__, e, str(d)[:300]))
            continue
        # base={} or garbage-but-dict base is legitimately incomplete; only demand completeness
        # when base is None / a non-dict / a complete builtin.
        if isinstance(base, dict) and base is not BUILTIN_SKINS.get("Retro DOS") and base.get("bg") is None \
                and not base.get("name"):
            pass  # incomplete base: reported separately in c5d
        else:
            p = [x for x in theme_problems(t) if "\\n'" not in x]
            if len(p) != len(theme_problems(t)):
                NOTES.append("c5: trailing-newline hex accepted (see c5b)") if "c5: trailing-newline hex accepted (see c5b)" not in NOTES else None
            if p:
                f.add("#%d incomplete/invalid theme: %s  input=%r" % (i, p[:3], str(d)[:300]))
        try:
            if repr(d) != repr(dsnap) and not (d != d and dsnap != dsnap):
                f.add("#%d MUTATED input: %r" % (i, str(dsnap)[:200]))
            if base is not None and repr(base) != repr(bsnap):
                f.add("#%d MUTATED base" % i)
        except Exception:
            pass
        if t is not None:
            if isinstance(base, dict) and (t["ansi"] is base.get("ansi") or t["fonts"] is base.get("fonts")):
                f.add("#%d result aliases base lists" % i)
    if repr(snap_builtin) != repr(BUILTIN_SKINS):
        f.add("BUILTIN_SKINS mutated")
    return f


@check
def c5b_validate_theme_specifics():
    f = Fails(8)
    base = BUILTIN_SKINS["Plain"]
    t = validate_theme({"ansi": {"4": "#112233"}})
    exp = list(base["ansi"])
    exp[4] = "#112233"
    if t["ansi"] != exp:
        f.add("partial ansi override: %r" % (t["ansi"],))
    t = validate_theme({"ansi": {"4": "#AABBCC", "16": "#112233", "-1": "#112233", "x": "#112233",
                                 "5": "red", "Ù£": "#010203"}})
    exp = list(base["ansi"])
    exp[4] = "#aabbcc"
    if t["ansi"] != exp:
        f.add("partial ansi w/ bad keys: diff=%r" % ([(i, c) for i, c in enumerate(t["ansi"]) if c != exp[i]],))
    t = validate_theme({"bg": "#ABCDEF", "ansi": ["#ABCDEF"] * 16})
    if t["bg"] != "#abcdef" or t["ansi"] != ["#abcdef"] * 16:
        f.add("uppercase not normalised: %r" % t["bg"])
    for n in (15, 17, 0):
        t = validate_theme({"ansi": ["#112233"] * n})
        if t["ansi"] != base["ansi"]:
            f.add("ansi len %d accepted" % n)
    for bad in (float("nan"), float("inf"), float("-inf"), 0, 0.99, 10.01, True, "x", None):
        t = validate_theme({"min_contrast": bad})
        if t["min_contrast"] != base["min_contrast"]:
            f.add("min_contrast=%r accepted -> %r" % (bad, t["min_contrast"]))
    t = validate_theme({"min_contrast": 5})
    if not (t["min_contrast"] == 5.0 and type(t["min_contrast"]) is float):
        f.add("min_contrast=5 -> %r" % (t["min_contrast"],))
    for okv in (1, 10, 1.0, 10.0):
        if validate_theme({"min_contrast": okv})["min_contrast"] != float(okv):
            f.add("boundary min_contrast=%r rejected" % okv)
    # whitespace/newline around hex: '$' in HEX_RE allows trailing newline
    for v in ("#aabbcc\n", " #aabbcc", "#aabbcc "):
        out = validate_theme({"bg": v})["bg"]
        if out != base["bg"]:
            f.add("bg=%r accepted -> %r" % (v, out))
    # fonts
    t = validate_theme({"fonts": ["a"] * 20})
    if len(t["fonts"]) != 8:
        f.add("fonts not capped at 8: %d" % len(t["fonts"]))
    # name
    t = validate_theme({"name": "a\nb\x00c"})
    if "\n" in t["name"] or "\x00" in t["name"]:
        f.add("control chars in name: %r" % t["name"])
    t = validate_theme({"name": "x" * 10000})
    if len(t["name"]) != 40:
        f.add("name len %d" % len(t["name"]))
    # base is honoured
    t = validate_theme({}, BUILTIN_SKINS["Moody"])
    if t != BUILTIN_SKINS["Moody"]:
        f.add("empty overrides on Moody base differ from base")
    return f


@check
def c5c_validate_theme_incomplete_base():
    """Informational: base lacking keys yields incomplete theme (callers are expected to pass
    complete bases). Reported as FAIL only if it raises."""
    f = Fails()
    for base in ({}, {"name": "x"}, {"ansi": "bad"}, {"ansi": ["#000000"] * 3}):
        try:
            t = validate_theme({}, base)
            NOTES.append("c5c: base=%r -> theme missing keys: %s" % (
                base, [k for k in COLOR_KEYS + ("ansi", "name", "relief", "min_contrast") if k not in t]))
        except Exception as e:
            NOTES.append("c5c: validate_theme({}, %r) raises %s (incomplete base; informational)" % (base, type(e).__name__))
    return f


# ---------------------------------------------------------------- user skins
def snapshot(root):
    out = []
    for dp, dn, fn in os.walk(root):
        for x in dn + fn:
            out.append(os.path.relpath(os.path.join(dp, x), root))
    return sorted(out)


import subprocess as _sp
_CHILD = ("import sys,json;sys.path.insert(0,%r);import sanctuary as dc;"
          "r=dc.load_user_skins(sys.argv[1]);print(json.dumps(r))") % os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def safe_load(path, timeout=8):
    """load_user_skins in a child process so hangs/crashes/RecursionError become reportable.
    Returns (dict|None, problem_string|None)."""
    try:
        p = _sp.run([sys.executable, "-c", _CHILD, path], capture_output=True, timeout=timeout)
    except _sp.TimeoutExpired:
        return None, "HANG (> %ds, killed)" % timeout
    if p.returncode != 0:
        tail = p.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["?"]
        return None, "crashed: " + tail[0][:120]
    return json.loads(p.stdout.decode("utf-8")), None

@check
def c6_user_skins():
    f = Fails(40)
    top = tempfile.mkdtemp(prefix="skintest_")
    try:
        parent = os.path.join(top, "parent")
        os.makedirs(parent)
        sentinel = os.path.join(parent, "sentinel.txt")
        with open(sentinel, "w") as fh:
            fh.write("s")
        d = os.path.join(parent, "skins")
        os.makedirs(d)

        # nonexistent
        try:
            r = load_user_skins(os.path.join(top, "nope"))
            if r != {}:
                f.add("nonexistent dir -> %r" % (r,))
            r = load_user_skins(sentinel)
            if r != {}:
                f.add("path is a file -> %r" % (r,))
        except Exception as e:
            f.add("load_user_skins on nonexistent raised %r" % (e,))

        # round trip
        t = copy.deepcopy(BUILTIN_SKINS["Moody"])
        t["name"] = "My Custom Skin"
        t["bg"] = "#123456"
        t["ansi"][4] = "#abcdef"
        t["fonts"] = ["Consolas"]
        t["relief"] = "ridge"
        t["min_contrast"] = 5.5
        fp = save_user_skin(t, d)
        if os.path.dirname(os.path.abspath(fp)) != os.path.abspath(d):
            f.add("saved outside dir: %s" % fp)
        got = load_user_skins(d)
        if "My Custom Skin" not in got:
            f.add("roundtrip: name missing, got %r" % list(got))
        elif got["My Custom Skin"] != validate_theme(t, t):
            diff = [k for k in t if got["My Custom Skin"].get(k) != t[k]]
            f.add("roundtrip differs in %r" % diff)
        # clash with each builtin
        for n in BUILTIN_SKINS:
            tt = copy.deepcopy(BUILTIN_SKINS[n])
            tt["bg"] = "#010203"
            save_user_skin(tt, d)
        got = load_user_skins(d)
        for n in BUILTIN_SKINS:
            if n + " (user)" not in got:
                f.add("builtin clash %r: no '(user)' entry; keys=%r" % (n, list(got)))
            if n in got:
                f.add("user skin shadows builtin %r" % n)
        # clash with each builtin written under a different filename (case) too
        shutil.rmtree(d)
        os.makedirs(d)

        def w(name, content, mode="w"):
            kw = {} if "b" in mode else {"encoding": "utf-8"}
            with open(os.path.join(d, name), mode, **kw) as fh:
                fh.write(content)

        good = {"name": "Good", "bg": "#000001", "fg": "#fefefe"}
        w("good.json", json.dumps(good))
        w("malformed.json", "{not json")
        w("empty.json", "")
        w("list.json", "[1,2,3]")
        w("big.json", json.dumps(dict(good, name="Big", blurb="x" * 70000)))
        w("notjson.txt", json.dumps(dict(good, name="Txt")))
        w("noext", json.dumps(dict(good, name="Noext")))
        os.makedirs(os.path.join(d, "dir.json"))
        w("garbage.json", os.urandom(4096), "wb")
        w("onlyname.json", json.dumps({"name": "x"}))
        w("deep.json", "[" * 30000 + "]" * 30000)
        w("deepobj.json", '{"a":' * 20000 + "1" + "}" * 20000)
        w("nul.json", "\x00" * 100)
        w("bom.json", "\ufeff" + json.dumps(dict(good, name="Bom")))
        w("nan.json", '{"name":"NaN","bg":"#000000","min_contrast":NaN}')
        w("upper.JSON", json.dumps(dict(good, name="UpperExt")))
        w("noname.json", json.dumps({"bg": "#000002"}))
        w("nonstrname.json", json.dumps({"name": 5, "bg": "#000003"}))
        w("dup1.json", json.dumps(dict(good, name="Dup")))
        w("dup2.json", json.dumps(dict(good, name="Dup")))
        w("dup3.json", json.dumps(dict(good, name="Dup")))
        w("ansiint.json", json.dumps({"name": "AnsiInt", "ansi": 5}))
        got, prob = safe_load(d)
        if prob:
            f.add("load_user_skins on hostile folder: %s" % prob)
            got = {}
            # bisect: which single file is the culprit
            for fn in sorted(os.listdir(d)):
                if not os.path.isfile(os.path.join(d, fn)):
                    continue
                tmp = os.path.join(top, "one")
                shutil.rmtree(tmp, ignore_errors=True)
                os.makedirs(tmp)
                shutil.copy(os.path.join(d, fn), tmp)
                _, p1 = safe_load(tmp)
                if p1:
                    f.add("  culprit file %s (%d bytes): %s" % (fn, os.path.getsize(os.path.join(d, fn)), p1))
                    os.remove(os.path.join(d, fn))
            got, prob = safe_load(d)
            got = got or {}
        names = set(got)
        # duplicate names get a counter suffix: "Dup", "Dup (user)", "Dup (user 2)" (all distinct)
        for must in ("Good", "Bom", "UpperExt", "Dup", "Dup (user)", "Dup (user 2)", "noname", "nonstrname",
                     "AnsiInt"):
            if must not in names:
                f.add("expected skin %r missing; got %r" % (must, sorted(names)))
        for bad in ("Big", "Txt", "Noext", "x", "NaN"):
            if bad in names and bad != "NaN":
                f.add("file that should be skipped was loaded: %r" % bad)
        if "NaN" in names:
            mc = got["NaN"]["min_contrast"]
            if not (type(mc) is float and 1 <= mc <= 10):
                f.add("NaN json min_contrast -> %r" % mc)
        for n, t in got.items():
            p = theme_problems(t)
            if p:
                f.add("loaded skin %r invalid: %s" % (n, p[:2]))
            if t["name"] != n:
                f.add("key %r != name %r" % (n, t["name"]))
        if len(got) != len({t["name"] for t in got.values()}):
            f.add("duplicate names after load")

        # 500 files
        d2 = os.path.join(parent, "many")
        os.makedirs(d2)
        for i in range(500):
            with open(os.path.join(d2, "s%03d.json" % i), "w") as fh:
                json.dump({"name": "S%d" % (i % 50), "bg": "#%06x" % i}, fh)
        t0 = time.time()
        got, prob = safe_load(d2)
        dt = time.time() - t0
        NOTES.append("c6: 500 files (50 distinct names) loaded in %.2fs -> %s" % (
            dt, prob or "%d skins" % len(got)))
        if prob:
            f.add("500 files / 50 distinct names: %s" % prob)
            got = {}
        if dt > 5:
            f.add("500 files took %.2fs" % dt)
        # targeted duplicate-name reproducers
        for label, names_ in (("3 dups of 'Dup'", ["Dup"] * 3), ("10 dups of 'Dup'", ["Dup"] * 10),
                              ("3 dups of a 40-char name", ["n" * 40] * 3),
                              ("2 dups of 'Plain'", ["Plain"] * 2),
                              ("2 dups of 'Retro Phosphor'", ["Retro Phosphor"] * 2)):
            dd = os.path.join(top, "one_dup_%d" % len(os.listdir(top)))
            os.makedirs(dd)
            for i, nm in enumerate(names_):
                with open(os.path.join(dd, "f%d.json" % i), "w") as fh:
                    json.dump({"name": nm, "bg": "#000000"}, fh)
            g2, pr = safe_load(dd, timeout=4)
            if pr:
                f.add("duplicate names (%s): %s" % (label, pr))
            elif len(g2) != len(names_):
                f.add("duplicate names (%s): got %d skins %r" % (label, len(g2), sorted(g2)))
        if got and len(got) != 500:
            f.add("500 files (50 distinct names) gave %d skins, expected 500 via ' (user)' suffixing"
                  % len(got))
        for n in got:
            if len(n) > 48 + 0:
                f.add("name longer than 48 chars: %d" % len(n))
                break

        # save with hostile names
        d3 = os.path.join(parent, "save")
        before_parent = snapshot(parent)
        hostile = ["..\\..\\evil", "../../evil", "a/b", "a\\b", "CON", "con", "NUL", "COM1", "LPT1", "AUX", "x" * 500,
                   "", "....", "   ", "\x00\x01\x02", "\n\r", "..", ".", "evil.json", "C:\\evil", "C:evil",
                   "\\\\server\\share\\x", "name:stream", "a" * 40, "trailing.", "trailing ", " lead",
                   "Ã©", "\u202e", "*?<>|\"", "~", "PRN", "con.txt", "CLOCK$"]
        saved = {}
        for n in hostile:
            tt = copy.deepcopy(BUILTIN_SKINS["Plain"])
            tt["name"] = n
            try:
                p = save_user_skin(tt, d3)
            except Exception as e:
                f.add("save name=%r raised %s: %s" % (n[:30], type(e).__name__, str(e)[:60]))
                continue
            ap = os.path.abspath(p)
            if os.path.dirname(ap) != os.path.abspath(d3):
                f.add("save name=%r escaped: %s" % (n[:30], ap))
            base = os.path.basename(ap)
            if not os.path.isfile(ap):
                f.add("save name=%r returned %r but no such regular file exists (device name?)" % (n[:30], base))
            if len(base) > 120 or not base.lower().endswith(".json") or base.startswith("."):
                f.add("save name=%r -> unsane filename %r (len %d)" % (n[:30], base[:50], len(base)))
            saved[n] = p
        # nothing outside d3 changed
        after_parent = snapshot(parent)
        extra = [x for x in set(after_parent) - set(before_parent) if not x.startswith("save")]
        if extra:
            f.add("files created outside target dir: %r" % extra[:5])
        # top-level sentinel
        if open(sentinel).read() != "s":
            f.add("sentinel modified")
        top_listing = [x for x in snapshot(top) if not x.startswith(("parent", "one"))]
        if top_listing:
            f.add("files created above parent: %r" % top_listing[:5])
        # distinct hostile names should not silently overwrite each other (informational)
        files = {os.path.basename(p).lower() for p in saved.values()}
        NOTES.append("c6: %d hostile names -> %d distinct filenames" % (len(saved), len(files)))
        # loading what was saved must not raise
        _, pr = safe_load(d3)
        if pr:
            f.add("load after hostile saves: %s" % pr)
    finally:
        shutil.rmtree(top, ignore_errors=True)
    return f


@check
def c6b_user_skin_dir():
    f = Fails()
    p = user_skin_dir()
    if not isinstance(p, str) or not p:
        f.add("user_skin_dir() -> %r" % (p,))
    return f


@check
def c7_builtin_skins():
    f = Fails(10)
    unreachable = []
    names = [s["name"] for s in BUILTIN_SKINS.values()]
    if len(set(names)) != len(names):
        f.add("duplicate names")
    for k, s in BUILTIN_SKINS.items():
        if k != s["name"]:
            f.add("key %r != name %r" % (k, s["name"]))
        snap = copy.deepcopy(s)
        v = validate_theme(s, s)
        if v != s:
            f.add("%s: validate_theme(skin, skin) changed: %r" % (k, [x for x in s if v.get(x) != s[x]]))
        if repr(s) != repr(snap):
            f.add("%s mutated by validate" % k)
        p = theme_problems(s)
        if p:
            f.add("%s invalid: %s" % (k, p[:3]))
            continue
        mc, bg = s["min_contrast"], s["bg"]
        for i, c in enumerate(s["ansi"]):
            out = ensure_contrast(c, bg, mc)
            cr = contrast_ratio(out, bg)
            if cr < mc - 0.01:
                if meets_possible(bg, mc):
                    f.add("%s ansi[%d]=%s -> %s only %.2f < %.2f" % (k, i, c, out, cr, mc))
                else:
                    unreachable.append((k, i))
        for a, b, lab in (("fg", "bg", "fg/bg"), ("input_fg", "input_bg", "input"),
                          ("button_fg", "button_bg", "button")):
            cr = contrast_ratio(s[a], s[b])
            if cr < 4.5:
                f.add("%s: %s contrast %.2f (%s on %s) < 4.5" % (k, lab, cr, s[a], s[b]))
    if unreachable:
        NOTES.append("c7: unreachable ansi contrast: %r" % unreachable)
    return f


def main():
    t_all = time.time()
    failed = 0
    for fn in CHECKS:
        t0 = time.time()
        try:
            res = fn()
        except BaseException as e:
            res = Fails()
            res.add("check crashed: %s\n%s" % (e, traceback.format_exc(limit=3)))
        dt = time.time() - t0
        if res:
            failed += 1
            print("FAIL  %s  (%.1fs, %d problems)" % (fn.__name__, dt, res.n))
            for m in res.items:
                print("        - " + m.replace("\n", "\n          ")[:600])
            if res.n > len(res.items):
                print("        ... and %d more" % (res.n - len(res.items)))
        else:
            print("PASS  %s  (%.1fs)" % (fn.__name__, dt))
    print("\n-- notes --")
    for n in NOTES:
        print("  " + n)
    print("\n%d/%d checks failed, total %.1fs" % (failed, len(CHECKS), time.time() - t_all))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()





