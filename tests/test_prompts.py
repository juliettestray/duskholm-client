"""Tests for prompts.py (prompt-profile engine).  Plain asserts; every check runs."""
import copy
import json
import os
import random
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import prompts as P

HAVEN = P.get_preset("Haven / Duskholm")
RNG_SEED = 20261123
HOSTILE = (["1" * 500, "a" * 500, " " * 500, "(" * 500, "1/" * 250, "-" * 500, "9" * 499 + "x",
            "x" * 499 + "1", "1 " * 250, "[1/1A" + " 1A" * 100, "<" + "1" * 498 + ">",
            "[" + "a" * 498 + "]", "1x" * 250, ":" * 500, "1/" * 100 + "hp" * 150,
            "HP: " + "1" * 400, "a1" * 250, "\t" * 500, "é" * 500, "1 " * 100 + "/" * 300]
           + ["".join(random.Random(i).choice("1a /:-<>[]()hpmMVx\t") for _ in range(500))
              for i in range(8)])


def ms(f):
    t = time.perf_counter()
    f()
    return (time.perf_counter() - t) * 1000.0


# ---------------------------------------------------------------- legacy parser (tests only)
def legacy():
    import sanctuary as dc
    return dc.parse_prompt


def canon_from_legacy(old):
    if old is None:
        return None
    return {"gauges": [(old["hp"][2], old["hp"][0], old["hp"][1])],
            "counters": list(old["counters"]), "cooldowns": list(old["cooldowns"]),
            "text": ([old["facing"]] if old["facing"] else []) + list(old["tags"]),
            "hp": (old["hp"][0], old["hp"][1], old["hp"][2])}


def gen_line(r):
    lab = lambda: "".join(r.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(r.randint(1, 4)))
    num = lambda: str(r.choice([0, 1, 7, 99, 350, 12345, 999999999, -3]))
    s = "[%d/%d%s" % (r.randint(0, 999), r.randint(0, 999), lab())
    for _ in range(r.randint(0, 4)):
        s += " %s%s" % (num(), lab())
    for _ in range(r.randint(0, 3)):
        s += " %s:%s" % (r.choice("MKXYZabc"), num())
    s += r.choice(["", " ( )", " (North 3/5:2/5)", "(East)", " (West)", " ()", " (a(b))"]) + "]"
    s += r.choice(["", " ", " (Sprawled)", " [Fatigued]", " (Carrier) [Tag two]", "(x)(y)", " ()"])
    pre = r.choice(["", "", "You are hit.\n\r", "(W1) (I2) ", "[Enter] ", "Players [3/4] ", "[1/9DF M:0] "])
    line = pre + s
    mode = r.random()
    if mode < 0.1:
        line += r.choice([" [5/9DF M:2]", "[2/2AB]"])
    elif mode < 0.2:
        line = "".join(r.choice("[]()/:0123456789 ABab-\n") for _ in range(r.randint(0, 80)))
    elif mode < 0.25:
        line = line[:r.randint(0, len(line))]
    return line


# ---------------------------------------------------------------- random user-style patterns
CAP_TOK = [r"(?P<g{i}>\d+)", r"(?P<g{i}>-?\d{{1,5}})", r"(?P<g{i}>\d*)", r"(?P<g{i}>[A-Za-z]+)",
           r"(?P<g{i}>.*?)", r"(?P<g{i}>\S+)", r"(?P<g{i}>\w+)", r"(?P<g{i}>[^\]]*)",
           r"(?P<g{i}>\d{{1,9}})", r"(?P<g{i}>[0-9]+)", r"(?P<g{i}>.+)"]
SEP_TOK = ["/", r"\s+", r"\s*", " ", ":", r"\|", ".*", r"[^\]]*", r"\[", r"\]", "<", ">", r"(?:/\d+)?",
           "(?:hp|mp)", r"(?:\s+\w+)*", r"\d+", "HP", r"\s?", r"(?:\d+,)*", r"[A-Z]+", r"\w*", ",",
           r"(?:ab)+", r"(a|b)+", r"(?:x\d+)?", r"\D+", r"[a-f]*", r"[a-z]+", r"(?i)", r"(?:a?)+",
           r"\d{2,}", r"(?=\d)", r"\W*", r"[\s\S]*"]


def gen_pattern_profile(r):
    n = r.randint(2, 8)
    pat, groups = "", []
    for _ in range(n):
        if r.random() < 0.5:
            i = len(groups)
            groups.append("g%d" % i)
            pat += r.choice(CAP_TOK).format(i=i)
        else:
            pat += r.choice(SEP_TOK)
    if not groups:
        return None
    prof = {"name": "R", "kind": "regex", "pattern": pat, "sample": "x",
            "gauges": [{"label": "HP", "cur": groups[0], "max": groups[1] if len(groups) > 1 else None}],
            "counters": [{"label": "C%d" % k, "group": g} for k, g in enumerate(groups[2:4])],
            "cooldowns": [{"label": "K", "group": groups[-1]}],
            "text": groups[-2:]}
    return prof


def valid_random_profiles(count, seed):
    r = random.Random(seed)
    out, tries = [], 0
    while len(out) < count and tries < 200000:
        tries += 1
        p = P.validate_profile(gen_pattern_profile(r) or {})
        if p is not None:
            out.append(p)
    return out


# ---------------------------------------------------------------- the checks
CHECKS = []


def check(f):
    CHECKS.append(f)
    return f


@check
def parity_examples():
    old = legacy()
    ex = ["[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] ",
          "[120/350DF 2ST 1WN 3LG M:4 K:0 (North 3/5:2/5)] (Sprawled) [Fatigued] (Carrier)",
          "(W1) (I2) [10/20DF 0ST 0WN 0LG M:0 K:0 ( )]", "[1/9DF M:0] [5/9DF M:2]", "[7/7DF]",
          "[Enter] to continue", "[1] First option", "Players online [3/4]", "[x/y]",
          "[999999999999/1DF]", "", "[", "hello", "[3/4DF M:x]", "[1/1] Not a prompt "]
    for line in ex:
        assert P.parse_prompt(line, HAVEN) == canon_from_legacy(old(line)), line
    r = P.parse_prompt("[120/350DF 2ST 1WN 3LG M:4 K:0 (North 3/5:2/5)] (Sprawled) [Fatigued] (Carrier)", HAVEN)
    assert r["text"] == ["North 3/5:2/5", "Sprawled", "Fatigued", "Carrier"]
    assert r["hp"] == (120, 350, "DF") and r["gauges"] == [("DF", 120, 350)]
    assert P.parse_prompt("[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] ", HAVEN)["text"] == []


@check
def parity_generated():
    old = legacy()
    r = random.Random(RNG_SEED)
    hits = 0
    for _ in range(500):
        line = gen_line(r)
        got = P.parse_prompt(line, HAVEN)
        exp = canon_from_legacy(old(line[-500:]))
        assert got == exp, (line, got, exp)
        hits += got is not None
    assert hits > 250, hits
    long = "x" * 700 + "[5/9DF M:2] (Tag)"
    assert P.parse_prompt(long, HAVEN) == canon_from_legacy(old(long[-500:]))
    assert P.parse_prompt("[5/9DF]" + " " * 600, HAVEN) is None        # outside the last 500


@check
def parity_hostile():
    for bad in ("[1/1A" + " 1A" * 20000, "[1/1A" + " M:1" * 20000, "[1/1A" + " " * 50000,
                "[1" * 30000, "[1/1A (" + "(" * 50000, "[1/1A]" + "x" * 100000):
        assert ms(lambda: P.parse_prompt(bad, HAVEN)) < 50


@check
def presets_structure():
    assert list(P.PRESETS) == ["Haven / Duskholm", "ROM / Diku classic", "Simple brackets", "Custom"]
    assert P.DEFAULT_PRESET == "Haven / Duskholm"
    assert P.PRESETS["Haven / Duskholm"]["kind"] == "haven"
    for name, p in P.PRESETS.items():
        v = P.validate_profile(p)
        assert v == p, (name, v)
        assert json.loads(json.dumps(p)) == p
        assert len(p["sample"]) <= 300 and p["name"] == name
    g = P.get_preset("nope")
    assert g == P.PRESETS[P.DEFAULT_PRESET] and g is not P.PRESETS[P.DEFAULT_PRESET]
    g["gauges"].append(1)
    g["name"] = "zz"
    assert P.PRESETS[P.DEFAULT_PRESET]["name"] == "Haven / Duskholm"
    c = P.get_preset("ROM / Diku classic")
    c["gauges"][0]["label"] = "X"
    assert P.PRESETS["ROM / Diku classic"]["gauges"][0]["label"] == "HP"
    assert P.get_preset(None) == P.PRESETS[P.DEFAULT_PRESET] and P.get_preset(5) is not None


@check
def presets_parse_samples():
    for name, p in P.PRESETS.items():
        r = P.parse_prompt(p["sample"], p)
        assert r is not None, name
        ok, msg, res = P.check_profile(p, p["sample"])
        assert ok and msg.startswith("Matched: ") and res == r, (name, msg)
    r = P.parse_prompt(HAVEN["sample"], HAVEN)
    assert r["gauges"] == [("DF", 350, 350)] and r["text"] == ["Sprawled"]
    assert [c[0] for c in r["counters"]] == ["ST", "WN", "LG"] and r["cooldowns"] == [("M", 0), ("K", 0)]


@check
def preset_rom():
    p = P.PRESETS["ROM / Diku classic"]
    r = P.parse_prompt("<20hp 100m 100mv>", p)
    assert r["gauges"] == [("HP", 20, None), ("MN", 100, None), ("MV", 100, None)], r
    assert r["hp"] == (20, 20, "HP")
    r = P.parse_prompt("<20/100hp 5/50m 90/120mv> ", p)
    assert r["gauges"] == [("HP", 20, 100), ("MN", 5, 50), ("MV", 90, 120)] and r["hp"] == (20, 100, "HP")
    r = P.parse_prompt("You hit.\n<-3hp 0m 12mv>", p)
    assert r["gauges"][0] == ("HP", -3, None)
    assert P.parse_prompt("<20hp 100m>", p) is None
    r = P.parse_prompt("<1hp 1m 1mv> junk <2/3hp 4/5m 6/7mv>", p)
    assert r["gauges"][0] == ("HP", 2, 3)
    assert P.parse_prompt("<1234567890hp 1m 1mv>", p) is None          # > 9 digits


@check
def preset_simple():
    p = P.PRESETS["Simple brackets"]
    for line in ("[HP: 120/150  MP: 40/60  MV: 90/90]", "[hp:120/150 mp:40/60 mv:90/90]",
                 "[HP: 120 / 150 MANA: 40/60 MOVE: 90/90]", "x [Hp: 1/2  Mana: 3/4  Move: 5/6] "):
        r = P.parse_prompt(line, p)
        assert r and len(r["gauges"]) == 3, line
    r = P.parse_prompt("[HP: 120/150  MP: 40/60  MV: 90/90]", p)
    assert r["gauges"] == [("HP", 120, 150), ("MP", 40, 60), ("MV", 90, 90)]
    assert P.parse_prompt("[HP: 120/150  MP: 40/60]", p) is None


@check
def preset_custom():
    p = P.PRESETS["Custom"]
    r = P.parse_prompt("Health 12/40 now", p)
    assert r["gauges"] == [("HP", 12, 40)]
    assert P.parse_prompt("nothing", p) is None


@check
def optional_and_missing_groups():
    base = {"name": "T", "kind": "regex", "sample": "",
            "pattern": r"(?P<a>\d{1,3})(?:/(?P<b>\d{1,3}))?(?: x(?P<c>\d+))?(?: (?P<t>\w+))?",
            "gauges": [{"label": "A", "cur": "a", "max": "b"}, {"label": "Z", "cur": "zz", "max": None},
                       {"label": "C", "cur": "c", "max": None}],
            "counters": [{"label": "C", "group": "c"}],
            "cooldowns": [{"label": "T", "group": "t"}],
            "text": ["t", "nogroup"]}
    r = P.parse_prompt("5", base)
    assert r["gauges"] == [("A", 5, None)] and r["counters"] == [] and r["text"] == []
    r = P.parse_prompt("5/9 x2 hello", base)
    assert r["gauges"] == [("A", 5, 9), ("C", 2, None)] and r["counters"] == [("C", 2)]
    assert r["cooldowns"] == [] and r["text"] == ["hello"]      # 'hello' is not numeric
    # the profile is used unvalidated: bad items must never raise
    weird = {"kind": "regex", "pattern": r"(?P<a>\d+)", "gauges": [5, None, {"cur": 3}, {"cur": "a", "label": 4}],
             "counters": "no", "cooldowns": [[]], "text": [1, None, "a"]}
    r = P.parse_prompt("12", weird)
    assert r["gauges"] == [("", 12, None)] and r["text"] == ["12"]
    # -5 allowed, huge rejected
    neg = {"kind": "regex", "pattern": r"hp(?P<a>-?\d+)", "gauges": [{"label": "H", "cur": "a", "max": None}],
           "counters": [], "cooldowns": [], "text": []}
    assert P.parse_prompt("hp-5", neg)["gauges"] == [("H", -5, None)]
    assert P.parse_prompt("hp1234567890", neg) is None
    assert P.parse_prompt("hp123456789", neg)["gauges"] == [("H", 123456789, None)]
    # empty-matching pattern yields nothing
    allopt = dict(neg, pattern=r"(?P<a>\d+)?")
    assert P.parse_prompt("abc", allopt) is None
    assert P.parse_prompt("abc 7", allopt)["gauges"] == [("H", 7, None)]


@check
def non_str_and_bad_profiles():
    for bad in (None, 5, 5.5, b"[1/1DF]", ["[1/1DF]"], {"a": 1}, object(), True):
        assert P.parse_prompt(bad, HAVEN) is None
    for prof in (None, 5, "x", [], {}, {"kind": "nope"}, {"kind": "regex"}, {"kind": "regex", "pattern": 5},
                 {"kind": "regex", "pattern": "("}, {"kind": "regex", "pattern": r"(a+)+(?P<x>b)"}):
        assert P.parse_prompt("[1/1DF]", prof) is None
        assert P.compile_profile(prof) is None
    assert P.compile_profile(HAVEN) is not None


@check
def last_prompt_wins():
    assert P.parse_prompt("[1/9DF M:0] [5/9DF M:2]", HAVEN)["hp"][0] == 5
    p = P.PRESETS["ROM / Diku classic"]
    r = P.parse_prompt("<9hp 9m 9mv>\n<7hp 8m 9mv>", p)
    assert r["gauges"][0][1] == 7
    r = P.parse_prompt("<9hp 9m 9mv> text <7hp 8m 9mv> trailing", p)
    assert r["gauges"][0][1] == 7
    s = P.PRESETS["Simple brackets"]
    r = P.parse_prompt("[HP: 1/2  MP: 1/2  MV: 1/2] [HP: 9/9  MP: 1/2  MV: 1/2]", s)
    assert r["gauges"][0][1] == 9


@check
def compile_cache_and_determinism():
    p = P.get_preset("ROM / Diku classic")
    a = P.compile_profile(p)
    assert a is P.compile_profile(copy.deepcopy(p))
    assert P.compile_profile(dict(p, name="other")) is a
    snap = copy.deepcopy(P.PRESETS)
    line = "x <20/100hp 5/50m 90/120mv>"
    first = P.parse_prompt(line, p)
    for _ in range(50):
        assert P.parse_prompt(line, p) == first
    p0 = copy.deepcopy(p)
    P.parse_prompt(line, p); P.validate_profile(p); P.format_specs(p); P.check_profile(p, line)
    assert p == p0 and P.PRESETS == snap
    r = P.parse_prompt(line, p)
    r["gauges"].append(("x", 1, 1))
    assert P.parse_prompt(line, p) == first                  # results are fresh objects


UNSAFE = [r"(a+)+(?P<x>b)", r"(a*)*(?P<x>b)", r"(.*)*(?P<x>b)", r"(\d+)+(?P<x>b)", r"(?:a{2,})+(?P<x>b)",
          r"(?P<x>(?:a+b?)+)", r"(?P<x>(?:\d+,)*)", r"(?P<x>(?:a|aa)+)", r"(?P<x>(?:a?b*)+)",
          r"(?P<x>a)\1", r"(?P<x>a)(?P=x)", r"(?<=a)(?P<x>b)", r"(?<!a)(?P<x>b)", r"(?P<x>a)(?(1)b|c)",
          r"(?P<x>a)(?#c)", r"(?x)(?P<x>a)", r"(?P<x>\d+)\d+", r"(?P<x>.*).*", r"(?P<x>\s*)\s*\d*",
          r"(?P<x>\d+)\s*\d+", r"(?P<x>\w+)[A-Z]+", r"(?P<x>[^a]*).+",
          r"(?P<x>a)(b)?(c)?(d)?(e)?(f)?(g)?(h)?", r"(?P<x>a{100})", r"(?P<x>a{1,100})",
          r"(?P<x>(?:(?:(?:(?:(?:(?:(?:(?:(?:(?:a)))))))))))", "(?P<x>a)\n", "(?P<x>a)\t", "",
          "x" * 401, r"(?P<x>(?:ab)+(?:cd)+)(?:\d+)+"]
SAFE = [r"(?P<x>\d+)", r"(?P<x>\d+) (?P<y>\d+)", r"(?P<x>-?\d{1,9})\s*/\s*(?P<y>\d{1,9})",
        r"\[(?P<x>[A-Za-z]+)\d+\]", r"(?P<x>\d+)(?:/(?P<y>\d+))?hp", r"(?:ab)+(?P<x>c)",
        r"(?P<x>\s*\d+)", r"(?P<x>[A-Z]+)\d+", r"<(?P<x>[^>]*)>", r"(?i)(?:HP|HEALTH):(?P<x>\d+)"]


@check
def unsafe_patterns_rejected():
    for pat in UNSAFE:
        prof = {"name": "U", "kind": "regex", "pattern": pat, "gauges": [{"label": "H", "cur": "x", "max": None}],
                "counters": [], "cooldowns": [], "text": []}
        assert P.validate_profile(prof) is None, pat
        assert P.compile_profile(prof) is None, pat
        ok, msg, res = P.check_profile(prof, "aaa")
        assert not ok and res is None and msg, pat
    for pat in SAFE:
        prof = {"name": "S", "kind": "regex", "pattern": pat, "gauges": [{"label": "H", "cur": "x", "max": None}]}
        assert P.validate_profile(prof) is not None, pat
        assert P.check_pattern_safety(pat) is None, pat
    assert P.check_pattern_safety(None) and P.check_pattern_safety(b"x") and P.check_pattern_safety("")


@check
def validate_rules():
    ok = {"name": "  Name \x00\x07  ", "kind": "regex", "pattern": r"(?P<hp>\d+)/(?P<hpmax>\d+)",
          "sample": "5/6\x01" + "x" * 400, "extra": 1,
          "gauges": [{"label": "H P", "cur": "hp", "max": "hpmax", "junk": 1},
                     {"label": "TooLongLabel", "cur": "hp"}, {"label": "X", "cur": "nope"},
                     {"label": "Y", "cur": "hp", "max": "nope"}, {"label": "a,b=c/d", "cur": "hp"}, "str"],
          "counters": [{"label": "C", "group": "hpmax"}, {"label": "", "group": "hp"}],
          "cooldowns": [{"label": "K", "group": "bad name"}],
          "text": ["hp", "hp!", 5, "x" * 50]}
    snap = copy.deepcopy(ok)
    v = P.validate_profile(ok)
    assert ok == snap
    assert v["name"] == "Name" and v["kind"] == "regex" and "extra" not in v
    assert v["gauges"] == [{"label": "HP", "cur": "hp", "max": "hpmax"}, {"label": "abcd", "cur": "hp", "max": None}]
    assert v["counters"] == [{"label": "C", "group": "hpmax"}] and v["cooldowns"] == []
    assert v["text"] == ["hp"] and len(v["sample"]) == 300 and "\x01" not in v["sample"]
    assert set(v) == {"name", "kind", "pattern", "gauges", "counters", "cooldowns", "text", "sample"}
    base = {"name": "n", "kind": "regex", "pattern": r"(?P<a>\d)", "gauges": [{"label": "A", "cur": "a"}]}
    assert P.validate_profile(base) is not None
    for bad in (dict(base, name=""), dict(base, name="\x01\x02"), dict(base, name="x" * 41), dict(base, name=5),
                dict(base, kind="x"), dict(base, kind=None), dict(base, pattern=r"\d"),
                dict(base, pattern=r"(\d)"), dict(base, pattern=r"(?P<a>\d"), dict(base, gauges=[]),
                dict(base, gauges=[{"label": "A", "cur": "q"}]), dict(base, gauges="x"),
                dict(base, pattern="x" * 401), dict(base, pattern=7), 5, None, [], "s"):
        assert P.validate_profile(bad) is None, bad
    assert P.validate_profile(dict(base, name="x" * 40)) is not None
    many = dict(base, gauges=[{"label": "L%d" % i, "cur": "a"} for i in range(30)])
    assert len(P.validate_profile(many)["gauges"]) == 12
    h = P.validate_profile({"name": "H", "kind": "haven", "pattern": "((", "gauges": [1], "sample": 7})
    assert h == {"name": "H", "kind": "haven", "pattern": "", "gauges": [], "counters": [],
                 "cooldowns": [], "text": [], "sample": ""}
    u = P.validate_profile({"name": "é中", "kind": "haven", "sample": "é"})
    assert u["name"] == "é中"


def _rand_value(r, depth=0):
    c = r.random()
    if c < 0.1:
        return None
    if c < 0.2:
        return r.choice([0, 1, -1, 2 ** 70, 1.5, float("nan"), True])
    if c < 0.55:
        return "".join(r.choice("ab()[]{}*+?|\\.^$<>=!#:P/ 12 \x00\n\té中\ud800-,") for _ in range(r.randint(0, 30)))
    if c < 0.7 and depth < 3:
        return [_rand_value(r, depth + 1) for _ in range(r.randint(0, 4))]
    if depth < 3:
        return {r.choice(["label", "cur", "max", "group", "x", 1]): _rand_value(r, depth + 1)
                for _ in range(r.randint(0, 3))}
    return "a"


@check
def validate_fuzz():
    r = random.Random(RNG_SEED + 1)
    pieces = [r"(?P<a>", r"(?P<b>", r"(?:", r"(", r")", r"+", r"*", r"?", r"{2,}", r"{3}", r"\d", r".", r"\w",
              r"\s", r"[a-z]", r"[^x]", r"|", r"\1", r"(?P=a)", r"(?<=", r"(?<!", r"(?=", r"x", r"/", r"\\",
              r"{", r"}", r"$", r"^", r"(?i)", "é", "\x00", " ", r"\b", r"*?", r"+?"]
    accepted = timing_ok = 0
    worst = 0.0
    for n in range(2000):
        k = r.random()
        if k < 0.1:
            d = _rand_value(r)
        else:
            if k < 0.5:
                pat = "".join(r.choice(pieces) for _ in range(r.randint(1, 14)))
            elif k < 0.55:
                pat = "(?P<a>a)" + "(a+)+" * 5000
            elif k < 0.6:
                pat = r.choice(["(?P<a>", "x", "(", r"\d+"]) * 10000
            elif k < 0.8:
                pat = (gen_pattern_profile(r) or {}).get("pattern", "(?P<a>\\d)")
            else:
                pat = _rand_value(r)
            d = {"name": r.choice(["n", "", "x" * 50, "\x00", _rand_value(r)]),
                 "kind": r.choice(["regex"] * 6 + ["haven", None, "x"]), "pattern": pat,
                 "sample": _rand_value(r),
                 "gauges": [{"label": r.choice(["HP", "", _rand_value(r)]), "cur": r.choice(["a", "b", "zz", _rand_value(r)]),
                             "max": r.choice([None, "a", "b", "", "q", 5])} for _ in range(r.randint(0, 3))],
                 "counters": r.choice([[{"label": "C", "group": "a"}], _rand_value(r), []]),
                 "cooldowns": r.choice([[{"label": "K", "group": "b"}], _rand_value(r), []]),
                 "text": r.choice([["a"], ["b", "a"], _rand_value(r), []])}
        before = copy.deepcopy(d) if isinstance(d, (dict, list)) else d
        v = P.validate_profile(d)
        if isinstance(before, (dict, list)):
            if isinstance(d, dict):
                assert repr(d) == repr(before)
        if v is None:
            continue
        accepted += 1
        assert P.validate_profile(v) == v, v                       # idempotent
        assert json.loads(json.dumps(v)) == v
        assert v["kind"] in ("haven", "regex") and 1 <= len(v["name"]) <= 40 and v["name"].isprintable()
        assert len(v["sample"]) <= 300 and v["sample"].isprintable() or v["sample"] == ""
        for key in ("gauges", "counters", "cooldowns", "text"):
            assert isinstance(v[key], list) and len(v[key]) <= 12
        if v["kind"] == "regex":
            rx = re.compile(v["pattern"])
            assert rx.groupindex and P.check_pattern_safety(v["pattern"]) is None
            assert v["gauges"] or v["counters"] or v["cooldowns"] or v["text"]
            for it in v["gauges"]:
                assert it["cur"] in rx.groupindex and (it["max"] is None or it["max"] in rx.groupindex)
                assert 1 <= len(it["label"]) <= 8 and it["label"].isprintable()
            for key in ("counters", "cooldowns"):
                for it in v[key]:
                    assert it["group"] in rx.groupindex and 1 <= len(it["label"]) <= 8
            for g in v["text"]:
                assert g in rx.groupindex
            for line in HOSTILE:
                t = ms(lambda: P.parse_prompt(line, v))
                worst = max(worst, t)
                assert t < 50, (v["pattern"], t)
            timing_ok += 1
    assert accepted > 30, accepted
    print("    fuzz: %d accepted, worst hostile match %.2f ms" % (accepted, worst))
    # non-dict inputs
    for bad in (None, 1, "x", [], (), b"b", object(), float("nan"), {1: 2}, {"name": object()}):
        assert P.validate_profile(bad) is None


@check
def redos_timing_presets_and_random():
    worst = 0.0
    for name, p in P.PRESETS.items():
        for line in HOSTILE:
            worst = max(worst, ms(lambda: P.parse_prompt(line, p)))
    profs = valid_random_profiles(200, RNG_SEED + 2)
    assert len(profs) == 200, len(profs)
    for p in profs:
        for line in HOSTILE:
            t = ms(lambda: P.parse_prompt(line, p))
            worst = max(worst, t)
            assert t < 50, (p["pattern"], line[:20], t)
    print("    timing: worst %.2f ms over 200 random + %d presets x %d lines" % (worst, len(P.PRESETS), len(HOSTILE)))


@check
def specs_roundtrip_presets_and_random():
    profs = list(P.PRESETS.values()) + valid_random_profiles(150, RNG_SEED + 3)
    for p in profs:
        s = P.format_specs(p)
        assert set(s) == {"gauges", "counters", "cooldowns", "text"} and all(isinstance(x, str) for x in s.values())
        lists, err = P.parse_specs(s["gauges"], s["counters"], s["cooldowns"], s["text"])
        assert err is None, (s, err)
        for k in lists:
            assert lists[k] == p[k], (k, lists[k], p[k])
    rom = P.format_specs(P.PRESETS["ROM / Diku classic"])
    assert rom["gauges"] == "HP=hp/hpmax, MN=mn/mnmax, MV=mv/mvmax" and rom["counters"] == ""
    assert P.format_specs({"gauges": [{"label": "HP", "cur": "hp", "max": None}], "text": ["facing", "pos"],
                           "counters": [{"label": "ST", "group": "st"}],
                           "cooldowns": [{"label": "M", "group": "m"}]}) == \
        {"gauges": "HP=hp", "counters": "ST=st", "cooldowns": "M=m", "text": "facing, pos"}
    assert P.format_specs(None) == {"gauges": "", "counters": "", "cooldowns": "", "text": ""}


@check
def parse_specs_tolerance_and_errors():
    l, e = P.parse_specs(" HP = hp / hpmax ,, MN=mana/manamax, ", "ST=st , WN = wn,", " M=m,K=k ", " facing , pos,")
    assert e is None
    assert l["gauges"] == [{"label": "HP", "cur": "hp", "max": "hpmax"}, {"label": "MN", "cur": "mana", "max": "manamax"}]
    assert l["counters"] == [{"label": "ST", "group": "st"}, {"label": "WN", "group": "wn"}]
    assert l["cooldowns"] == [{"label": "M", "group": "m"}, {"label": "K", "group": "k"}] and l["text"] == ["facing", "pos"]
    l, e = P.parse_specs("hp=HP/HPMAX", "", "", "")
    assert e is None and l["gauges"][0]["cur"] == "HP"               # group names keep their case
    l, e = P.parse_specs("", "", "", "")
    assert e is None and all(v == [] for v in l.values())
    l, e = P.parse_specs("HP120", "ST=st", "", "")
    assert e and "HP120" in e and l["gauges"] == [] and l["counters"]
    l, e = P.parse_specs("HP=hp/hpmax/x", "", "", "")
    assert e and "HP=hp/hpmax/x" in e and l["gauges"] == []
    l, e = P.parse_specs("HP=hp", "ST=1bad", "M=m=n", "two words")
    assert e and "1bad" in e and "M=m=n" in e and "two words" in e
    assert l["gauges"] and l["counters"] == [] and l["cooldowns"] == [] and l["text"] == []
    l, e = P.parse_specs("TOOLONGLABEL=hp", "", "", "")
    assert e and "TOOLONGLABEL" in e and l["gauges"] == []
    l, e = P.parse_specs("=hp", "A B=x", "", "")
    assert e and l["gauges"] == [] and l["counters"] == []
    l, e = P.parse_specs(",".join("L%d=g%d" % (i, i) for i in range(13)), "", "", "")
    assert e and l["gauges"] == []
    l, e = P.parse_specs(None, 5, [], {})                              # never raises
    assert e is None and all(v == [] for v in l.values())


@check
def describe_result_cases():
    r = P.parse_prompt("[350/350DF 0ST 0WN 0LG M:0 K:0 (North)]", HAVEN)
    assert P.describe_result(r) == "DF 350/350 | ST 0 WN 0 LG 0 | M:0 K:0 | North"
    r = {"gauges": [("HP", 350, 350)], "counters": [("ST", 0), ("WN", 0)], "cooldowns": [("M", 0), ("K", 0)],
         "text": ["North"], "hp": (350, 350, "HP")}
    assert P.describe_result(r) == "HP 350/350 | ST 0 WN 0 | M:0 K:0 | North"
    assert P.describe_result({"gauges": [("HP", 5, None), ("MN", 1, 2)], "counters": [], "cooldowns": [],
                              "text": ["a", "b"], "hp": None}) == "HP 5 MN 1/2 | a, b"
    assert P.describe_result(None) == "No prompt" and P.describe_result("x") == "No prompt"
    assert "|" not in P.describe_result({"gauges": [], "counters": [], "cooldowns": [], "text": [], "hp": None})
    assert P.describe_result({"gauges": "bad"}) == "No prompt"


@check
def check_profile_messages():
    ok, msg, res = P.check_profile(P.PRESETS["Custom"], "HP 12/30")
    assert ok and msg == "Matched: HP 12/30" and res["hp"] == (12, 30, "HP")
    ok, msg, res = P.check_profile(P.PRESETS["Custom"], "no numbers")
    assert not ok and msg == "Pattern does not match the sample" and res is None
    ok, msg, res = P.check_profile(dict(P.PRESETS["Custom"], pattern="(?P<hp>"), "1/2")
    assert not ok and "Profile problem" in msg and "regular expression" in msg and res is None
    ok, msg, res = P.check_profile(dict(P.PRESETS["Custom"], pattern=r"(?P<hp>a+)+"), "aa")
    assert not ok and "nested" in msg.lower()
    ok, msg, res = P.check_profile(dict(P.PRESETS["Custom"], pattern=r"(?P<hp>\d)\1"), "11")
    assert not ok and "backreference" in msg
    ok, msg, res = P.check_profile(dict(P.PRESETS["Custom"], pattern=r"\d+"), "11")
    assert not ok and "named group" in msg
    ok, msg, res = P.check_profile(dict(P.PRESETS["Custom"], gauges=[]), "1/2")
    assert not ok and "named group" in msg
    ok, msg, res = P.check_profile(P.PRESETS["Custom"], "")
    assert not ok and "sample" in msg.lower()
    ok, msg, res = P.check_profile(5, "x")
    assert not ok and res is None
    ok, msg, res = P.check_profile(P.PRESETS["Custom"], None)
    assert not ok
    ok, msg, res = P.check_profile(HAVEN, HAVEN["sample"])
    assert ok and "DF 350/350" in msg


@check
def gauge_color_boundaries():
    f = P.gauge_color_role
    assert f(100, 100) == "good" and f(60, 100) == "good" and f(59, 100) == "warn"
    assert f(30, 100) == "warn" and f(29, 100) == "bad" and f(0, 100) == "bad" and f(-5, 100) == "bad"
    assert f(6, 10) == "good" and f(3, 10) == "warn" and f(2, 10) == "bad"
    assert f(599, 1000) == "warn" and f(600, 1000) == "good" and f(299, 1000) == "bad" and f(300, 1000) == "warn"
    assert f(5, None) == "good" and f(5, 0) == "good" and f(5, -3) == "good" and f(0, 0) == "good"
    assert f(200, 100) == "good"
    assert f("x", 5) == "good" and f(None, 5) == "good"


@check
def static_checker_never_raises():
    r = random.Random(RNG_SEED + 4)
    alphabet = "()[]{}*+?|\\.^$<>=!#:P/ 1234,-abc\x00é\ud800"
    t0 = time.perf_counter()
    for _ in range(3000):
        s = "".join(r.choice(alphabet) for _ in range(r.randint(0, 450)))
        res = P.check_pattern_safety(s)
        assert res is None or isinstance(res, str)
    assert time.perf_counter() - t0 < 5
    for s in ("(" * 400, ")" * 400, "[" * 400, "{" * 399, "\\", "(?", "(?P", "(?P<", "[a-", "a{1,", "a{,}"):
        P.check_pattern_safety(s)


def main():
    t0 = time.time()
    failed = 0
    for f in CHECKS:
        t = time.time()
        try:
            f()
            print("PASS %s (%.2fs)" % (f.__name__, time.time() - t))
        except Exception:
            failed += 1
            print("FAIL %s" % f.__name__)
            traceback.print_exc()
    print("%d checks, %d failed, %.1fs" % (len(CHECKS), failed, time.time() - t0))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
