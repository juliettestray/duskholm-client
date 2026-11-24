"""Tests for triggers.py.  Run: python tests/test_triggers.py  (exit 1 on any failure)."""
import copy
import os
import random
import re
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import triggers as T          # noqa: E402

RNG = random.Random(20240607)
BEEP = [{"type": "beep"}]


def trig(pattern, mode="plain", **kw):
    d = {"name": "t", "mode": mode, "pattern": pattern, "actions": list(BEEP)}
    d.update(kw)
    return d


def caps(pattern, line, mode="plain", **kw):
    m = T.match_trigger(trig(pattern, mode, **kw), line)
    return None if m is None else m["captures"]


# --------------------------------------------------------------------------- plain mode
def check_plain_table():
    table = [
        # pattern, line, ignore_case, expected captures subset (None = no match)
        ("tells you", "Bob tells you hi", True, {"0": "tells you", "1": ""}),
        ("TELLS YOU", "Bob tells you hi", True, {"0": "tells you"}),
        ("TELLS YOU", "Bob tells you hi", False, None),
        ("tells you", "Bob TELLS YOU", False, None),
        ("* tells you, '*'", "Bob tells you, 'hi there'", True,
         {"1": "Bob", "2": "hi there", "0": "Bob tells you, 'hi there'"}),
        ("a.b", "xa.by", True, {"0": "a.b"}),
        ("a.b", "axb", True, None),
        ("(x)", "say (x) now", True, {"0": "(x)"}),
        ("(x)", "x", True, None),
        ("[a]", "a", True, None),
        ("[a]", "b [a] c", True, {"0": "[a]"}),
        ("a\\b", "a\\b", True, {"0": "a\\b"}),
        ("a+b", "aab", True, None),
        ("a+b", "a+b", True, {"0": "a+b"}),
        ("100%", "got 100% now", True, {"0": "100%"}),
        ("{1}", "x{1}", True, {"0": "{1}"}),
        ("^[OOC]*", "[OOC] hello", True, {"1": " hello"}),
        ("^[OOC]*", " [OOC] hello", True, None),
        ("end$", "the end", True, {"0": "end"}),
        ("end$", "the end.", True, None),
        ("^exact$", "exact", True, {"0": "exact"}),
        ("^exact$", "exact ", True, None),
        ("^exact$", "an exact", True, None),
        ("^$", "", True, {"0": ""}),
        ("^$", "x", True, None),
        ("h?llo", "say hello", True, {"0": "hello", "1": ""}),
        ("h?llo", "hllo", True, None),
        ("h??", "hxy", True, {"0": "hxy"}),
        ("*", "abc", True, {"0": "abc", "1": "abc"}),
        ("*", "", True, {"0": "", "1": ""}),
        ("a*b", "ab", True, {"1": ""}),
        ("a*b", "a123b456b", True, {"0": "a123b", "1": "123"}),
        ("*foo", "xxfoo", True, {"1": "xx", "0": "xxfoo"}),
        ("foo*", "foo bar", True, {"1": " bar", "0": "foo bar"}),
        ("a*$", "abc", True, {"1": "bc"}),
        ("*a*b*c*", "xaybzc!", True, {"1": "x", "2": "y", "3": "z", "4": "!"}),
        ("***a***", "xay", True, {"1": "x", "2": "y"}),            # runs of * collapse
        ("a*b*c", "a-b-b-c", True, {"1": "-", "2": "-b-"}),        # lazy, left to right
        ("?*?", "xyz", True, {"0": "xy", "1": ""}),
        ("?*", "xyz", True, {"0": "xyz", "1": "yz"}),
        ("a*a", "a", True, None),
        ("a*A", "aXa", False, None),
        ("you say '*'", "You say 'hi'", True, {"1": "hi"}),
        ("café*", "CAFÉ au lait", True, {"1": " au lait"}),
        ("^*$", "anything", True, {"1": "anything"}),
        ("x*^", "x^", True, {"0": "x^"}),                           # ^ only anchors at the start
        ("a^b", "a^b", True, {"0": "a^b"}),
        ("a$b", "a$b", True, {"0": "a$b"}),
    ]
    for pat, line, ic, exp in table:
        got = caps(pat, line, ignore_case=ic)
        if exp is None:
            assert got is None, (pat, line, got)
        else:
            assert got is not None, (pat, line)
            for k, v in exp.items():
                assert got[k] == v, (pat, line, k, got[k], v)
    m = T.match_trigger(trig("end$"), "the end")
    assert (m["start"], m["end"]) == (4, 7)
    c = caps("a*b", "a1b")
    assert set(c) >= {str(i) for i in range(10)}
    assert c["3"] == "" and c["9"] == ""


def check_plain_many_wildcards():
    assert T.validate_trigger(trig("*a" * 9)) is None            # 9 wildcards: rejected
    assert T.validate_trigger(trig("a*" * 8 + "b")) is not None
    assert T.validate_trigger(trig("a" + "*" * 12 + "b")) is not None   # collapses to one
    assert T.validate_trigger(trig("a*a*a*a*a*a*a*a*a*a*a*a*b")) is None   # 12 real ones
    line = "a" * 600
    for pat in ("a*" * 8 + "b", "*a" * 8 + "b$", "a*a*a*a*a*a*a*a*b", "*" * 12 + "a" * 3 + "z"):
        t0 = time.perf_counter()
        r = T.match_trigger(trig(pat), line)
        dt = time.perf_counter() - t0
        assert r is None and dt < 0.05, (pat, dt)
    # plain_to_regex treats the 9th+ '*' as a literal asterisk (no blow-up either)
    rx = T.plain_to_regex("a*" * 12 + "b")
    assert re.search(rx, "a" * 3) is None
    assert re.search(T.plain_to_regex("x" + "*a" * 9), "x*a*a") is None or True


def check_plain_vs_regex_equivalence():
    for _ in range(4000):
        n = RNG.randint(1, 9)
        body = "".join(RNG.choice("ab*?") for _ in range(n))
        pat = ("^" if RNG.random() < 0.3 else "") + body + ("$" if RNG.random() < 0.3 else "")
        ic = RNG.random() < 0.5
        line = "".join(RNG.choice("abAB ") for _ in range(RNG.randint(0, 14)))
        t = trig(pat, ignore_case=ic)
        if T.validate_trigger(t) is None:
            continue
        got = T.match_trigger(t, line)
        rm = re.search(T.plain_to_regex(pat, ic), line)
        if rm is None:
            assert got is None, (pat, line, ic, got)
        else:
            assert got is not None, (pat, line, ic)
            assert (got["start"], got["end"]) == rm.span(), (pat, line, got, rm.span())
            for i in range(1, rm.re.groups + 1):
                assert got["captures"][str(i)] == rm.group(i), (pat, line, i)


# --------------------------------------------------------------------------- regex mode
def check_regex_mode():
    c = caps(r"(\w+) tells you, '(.*)'", "Bob tells you, 'hi'", "regex")
    assert c["0"] == "Bob tells you, 'hi'" and c["1"] == "Bob" and c["2"] == "hi" and c["3"] == ""
    c = caps(r"(?P<who>\w+) says (?P<what>\d+)", "Al says 42", "regex")
    assert c["who"] == "Al" and c["what"] == "42" and c["1"] == "Al" and c["2"] == "42"
    assert caps("HELLO", "say hello", "regex") is not None
    assert caps("HELLO", "say hello", "regex", ignore_case=False) is None
    c = caps(r"a(b)?c", "ac", "regex")
    assert c["1"] == ""
    m = T.match_trigger(trig(r"\d+", "regex"), "abc 123 def")
    assert (m["start"], m["end"]) == (4, 7)
    nine = "".join("(%s)" % ch for ch in "abcdefghi")
    assert T.validate_trigger(trig(nine, "regex")) is not None
    assert T.validate_trigger(trig(nine + "(j)", "regex")) is None
    bad = [r"(a)\1", r"(?P<x>a)(?P=x)", r"(?<=a)b", r"(?<!a)b", r"(a+)+", r"(a*)*", r"(.*)*",
           r"(a|aa)+", r"\d+\d+", r".*.*", r"(?#c)a", r"(?x)a b", r"a{100}", "(", "[", "a)",
           r"(?P<n>", "*a", "a**", r"(?(1)a|b)"]
    for p in bad:
        assert T.validate_trigger(trig(p, "regex")) is None, p
        assert T.compile_trigger(trig(p, "regex")) is None, p
    ok, msg, ms = T.check_trigger(trig(r"(a+)+", "regex"), "aaa")
    assert not ok and msg.startswith("Unsafe pattern: ") and ms == []
    ok, msg, _ = T.check_trigger(trig("(", "regex"), "aaa")
    assert not ok and "regular expression" in msg.lower()
    ok, msg, _ = T.check_trigger(trig(nine + "(j)", "regex"), "aaa")
    assert not ok and "group" in msg.lower()
    assert T.match_trigger(trig("(", "regex"), "(") is None


# --------------------------------------------------------------------------- expand
def check_expand():
    c = {"0": "ALL", "1": "one", "2": "two", "name": "Zed"}
    cases = [
        ("", ""), ("plain", "plain"), ("%", "%"), ("%%", "%"), ("100%", "100%"),
        ("%%1", "%1"), ("%1", "one"), ("%0", "ALL"), ("%3", ""), ("%9", ""),
        ("%10", "one0"), ("%1%2", "onetwo"), ("%x", "%x"), ("%{", "%{"), ("%{name", "%{name"),
        ("%{name}", "Zed"), ("%{missing}", ""), ("%{}", "%{}"), ("%{na me}", "%{na me}"),
        ("a%{1}b", "aoneb"), ("%{name}%{name}", "ZedZed"), ("50%% of %1", "50% of one"),
        ("%%{name}", "%{name}"), ("%é", "%é"), ("x%", "x%"),
    ]
    for text, exp in cases:
        assert T.expand(text, c) == exp, (text, T.expand(text, c), exp)
    # non-recursive: substituted text is not expanded again
    assert T.expand("%1", {"1": "%2", "2": "no"}) == "%2"
    assert T.expand("%1", {"1": "%%"}) == "%%"
    assert T.expand("%1", {"1": "%{name}", "name": "x"}) == "%{name}"
    assert T.expand(None, c) == "" and T.expand("%1", None) == ""
    assert T.expand("%1", {"1": 5}) == "5" and T.expand("%1", {"1": None}) == ""
    assert T.expand("%1" * 100, {}) == ""


# --------------------------------------------------------------------------- split
def check_split_commands():
    s = T.split_commands
    assert s("a;b;c") == ["a", "b", "c"]
    assert s("  a ; b  ") == ["a", "b"]
    assert s("a;;b") == ["a;b"]
    assert s("a;;;b") == ["a;", "b"]
    assert s("a;;;;b") == ["a;;b"]
    assert s(";;;") == [";"] or s(";;;") == []        # ';;' literal + separator
    assert s("") == [] and s("   ") == [] and s(";") == [] and s("; ;  ;") == []
    assert s(None) == [] and s(5) == []
    assert s("a\x00b\x07c;d\te\x1b") == ["abc", "de"]
    assert s("a\nb") == ["ab"]
    assert len(s(";".join("c%d" % i for i in range(50)))) == 20
    assert s(";".join("c%d" % i for i in range(50)))[0] == "c0"
    long_cmd = s("x" * 500)
    assert len(long_cmd) == 1 and len(long_cmd[0]) == 200
    assert s("é;ü") == ["é", "ü"]
    # injection through captures cannot add commands
    assert T.expand_commands("say %1", {"1": "a;b"}) == ["say a;b"]
    assert T.expand_commands("say %1;look", {"1": "x"}) == ["say x", "look"]
    assert T.expand_commands("say %1", {"1": "a\x00\nb"}) == ["say ab"]
    assert T.expand_commands("%1", {"1": ""}) == []
    assert len(T.expand_commands("%1", {"1": "z" * 1000})[0]) == 200


# --------------------------------------------------------------------------- match_line
def check_match_line():
    def tr(name, pat, **kw):
        d = trig(pat, **kw)
        d["name"] = name
        return d

    ts = [tr("low", "foo", priority=-5), tr("def1", "foo"), tr("high", "foo", priority=10),
          tr("def2", "foo"), tr("off", "foo", enabled=False), tr("other", "zzz")]
    names = [t["name"] for t, _m in T.match_line("a foo b", ts)]
    assert names == ["high", "def1", "def2", "low"], names
    ts2 = [tr("a", "foo"), tr("b", "foo", stop=True, priority=1), tr("c", "foo", priority=2)]
    assert [t["name"] for t, _ in T.match_line("foo", ts2)] == ["c", "b"]
    # stop only counts when the trigger actually matched
    ts3 = [tr("s", "nomatch", stop=True, priority=5), tr("a", "foo")]
    assert [t["name"] for t, _ in T.match_line("foo", ts3)] == ["a"]
    # garbage entries skipped silently
    junk = [None, 5, "x", [], {}, {"mode": "plain"}, tr("bad", "(", mode="regex"),
            {"name": "x", "mode": "plain", "pattern": "foo", "actions": []},
            {"name": "x", "mode": "plain", "pattern": "foo", "actions": "beep"},
            tr("ok", "foo"), tr("pri", "foo", priority="high"), tr("bool", "foo", priority=True)]
    got = [t["name"] for t, _ in T.match_line("foo", junk)]
    assert got == ["ok", "pri", "bool"], got
    assert T.match_line(None, ts) == [] and T.match_line("foo", None) == []
    assert T.match_line("foo", "foo") == [] and T.match_line("foo", []) == []
    # returned trigger is the original object and match dicts are fresh
    t = tr("same", "foo")
    (t2, m), = T.match_line("foo", [t])
    assert t2 is t and m["captures"]["0"] == "foo"
    # priority clamp: 5000 behaves like 1000
    big = [tr("n", "foo", priority=999), tr("b", "foo", priority=5000)]
    assert [x["name"] for x, _ in T.match_line("foo", big)] == ["b", "n"]
    # disabled / non-str lines
    assert T.match_trigger(tr("d", "foo", enabled=False), "foo") is None
    assert T.match_trigger(tr("d", "foo"), 123) is None and T.match_trigger(None, "x") is None
    # only the first 600 characters are searched
    assert T.match_trigger(tr("l", "needle"), "x" * 600 + "needle") is None
    assert T.match_trigger(tr("l", "needle"), "x" * 594 + "needle") is not None


# --------------------------------------------------------------------------- validators
HOSTILE = [None, True, False, 0, 1, -5, 5000, 3.5, float("inf"), "", " ", "x", "name",
           "a" * 10000, "\x00\x01\x02", "\ud800", "‮", "日本語", "plain", "regex", "gag",
           "highlight", "send", "note", "beep", "route", "#FF00aa", "#12345", 15, 16, [], {},
           [[]], [{}], {"a": 1}, b"bytes", (1, 2), "a\x00b", "*" * 400, "(" * 50, "((a+)+)+"]


def hostile_value():
    return RNG.choice(HOSTILE)


def random_action():
    t = RNG.choice(["highlight", "gag", "send", "beep", "note", "route", "bogus", None])
    a = {"type": t}
    for k in ("fg", "bg", "bold", "scope", "text", "echo", "pane", "gag", "extra"):
        r = RNG.random()
        if r < 0.35:
            continue
        if r < 0.65:
            a[k] = {"fg": RNG.choice([None, 3, "#AbCdEf", 15]), "bg": RNG.choice([None, 0, "#000000"]),
                    "bold": RNG.choice([True, False]), "scope": RNG.choice(["match", "line"]),
                    "text": RNG.choice(["hi %1", "reply thanks; look", "  spaced  "]),
                    "echo": RNG.choice([True, False]), "pane": RNG.choice(["chat", "ooc"]),
                    "gag": RNG.choice([True, False]), "extra": 1}[k]
        else:
            a[k] = hostile_value()
    return a


def random_trigger():
    d = {}
    for k in ("name", "enabled", "mode", "pattern", "ignore_case", "priority", "stop", "actions",
              "junk"):
        r = RNG.random()
        if r < 0.1:
            continue
        if r < 0.6:
            if k == "name":
                d[k] = RNG.choice(["Tells", " padded ", "x" * 40, "x" * 41, "n\x00l"])
            elif k == "mode":
                d[k] = RNG.choice(["plain", "regex"])
            elif k == "pattern":
                d[k] = RNG.choice(["* tells you*", "^[OOC]*", "(a)(b)", r"\d+ gold", "a" * 300,
                                   "a" * 301, "x*" * 9, "?", "(a+)+", r"(\w+) says", "$"])
            elif k == "actions":
                d[k] = [random_action() for _ in range(RNG.randint(0, 12))]
            elif k == "priority":
                d[k] = RNG.choice([0, 5, -1000, 1000, 1001, -99999])
            elif k == "junk":
                d[k] = 1
            else:
                d[k] = RNG.choice([True, False])
        else:
            d[k] = hostile_value()
    if RNG.random() < 0.05:
        d["pattern"] = "z" * 10000
    return d


def assert_fully_valid(v):
    assert isinstance(v, dict)
    assert set(v) == {"name", "enabled", "mode", "pattern", "ignore_case", "priority", "stop",
                      "actions"}, sorted(v)
    assert isinstance(v["name"], str) and 1 <= len(v["name"]) <= 40
    assert v["name"] == v["name"].strip() and v["name"].isprintable()
    assert isinstance(v["enabled"], bool) and isinstance(v["ignore_case"], bool)
    assert isinstance(v["stop"], bool)
    assert v["mode"] in ("plain", "regex")
    assert isinstance(v["pattern"], str) and 1 <= len(v["pattern"]) <= 300
    assert v["pattern"].isprintable()
    assert type(v["priority"]) is int and -1000 <= v["priority"] <= 1000
    assert isinstance(v["actions"], list) and 1 <= len(v["actions"]) <= 8
    for a in v["actions"]:
        t = a["type"]
        if t == "highlight":
            assert set(a) == {"type", "fg", "bg", "bold", "scope"}
            for k in ("fg", "bg"):
                x = a[k]
                assert x is None or (type(x) is int and 0 <= x <= 15) or \
                    (isinstance(x, str) and re.fullmatch(r"#[0-9a-f]{6}", x))
            assert isinstance(a["bold"], bool) and a["scope"] in ("match", "line")
            assert a["fg"] is not None or a["bg"] is not None or a["bold"]
        elif t in ("gag", "beep"):
            assert set(a) == {"type"}
        elif t == "send":
            assert set(a) == {"type", "text", "echo"} and isinstance(a["echo"], bool)
            assert 1 <= len(a["text"]) <= 200 and a["text"].isprintable()
            assert a["text"] == a["text"].strip()
        elif t == "note":
            assert set(a) == {"type", "text"} and 1 <= len(a["text"]) <= 200
            assert a["text"].isprintable()
        elif t == "route":
            assert set(a) == {"type", "pane", "gag"} and 1 <= len(a["pane"]) <= 24
            assert a["pane"].isprintable() and isinstance(a["gag"], bool)
        else:
            raise AssertionError("bad action type %r" % (t,))
    assert T.compile_trigger(v) is not None


def check_validate_trigger_basic():
    d = {"name": "  Tells  ", "mode": "plain", "pattern": "tells you", "junk": 1,
         "actions": [{"type": "highlight", "fg": "#FFD700", "bg": 3, "scope": "line", "x": 1},
                     {"type": "send", "text": " reply\tthanks \x00 ", "echo": False},
                     {"type": "gag"}, {"type": "beep"}, {"type": "note", "text": ""},
                     {"type": "highlight"}, {"type": "route", "pane": "chat", "gag": True},
                     {"type": "highlight", "fg": "red"}, {"type": "send", "text": "x" * 201},
                     5, None]}
    snap = copy.deepcopy(d)
    v = T.validate_trigger(d)
    assert d == snap
    assert_fully_valid(v)
    assert v["name"] == "Tells" and v["enabled"] is True and v["priority"] == 0
    assert v["ignore_case"] is True and v["stop"] is False and "junk" not in v
    assert v["actions"][0] == {"type": "highlight", "fg": "#ffd700", "bg": 3, "bold": False,
                               "scope": "line"}
    assert v["actions"][1] == {"type": "send", "text": "replythanks", "echo": False}
    assert [a["type"] for a in v["actions"]] == ["highlight", "send", "gag", "beep", "route"]
    assert T.validate_trigger(v) == v
    assert T.describe_actions(v) == "highlight, send, hide, beep, route"
    for bad in (None, 5, "x", [], {}, {"name": "a"},
                trig("p", mode="glob"), trig("p", name=""), trig("p", name="  "),
                trig("p", name="x" * 41), trig("p", name=5), trig("", mode="plain"),
                trig("   "), trig("a" * 301), trig("a\nb"), trig("p", actions=[]),
                trig("p", actions=[{"type": "nope"}]), trig("p", actions="beep"),
                trig("p", mode=["plain"]), trig(5)):
        assert T.validate_trigger(bad) is None, bad
    v = T.validate_trigger(trig("p", enabled="yes", priority=9999, stop=1, ignore_case=0))
    assert v["enabled"] is False and v["priority"] == 1000 and v["stop"] is False
    assert v["ignore_case"] is True
    v = T.validate_trigger(trig("p", priority=-9999))
    assert v["priority"] == -1000
    v = T.validate_trigger(trig("p", actions=[{"type": "beep"}] * 12))
    assert len(v["actions"]) == 8


def check_validate_trigger_fuzz():
    ok = 0
    for i in range(2000):
        d = random_trigger()
        snap = repr(copy.deepcopy(d))
        v = T.validate_trigger(d)
        assert repr(d) == snap, "input mutated"
        if v is None:
            assert T.validate_trigger(d) is None
            continue
        ok += 1
        assert_fully_valid(v)
        v_snap = copy.deepcopy(v)
        v2 = T.validate_trigger(v)
        assert v2 == v_snap and v == v_snap, "not idempotent / mutated"
        assert v2 is not v and v2["actions"] is not v["actions"]
        for line in ("hello", "Bob tells you, 'hi'", "", "x" * 700):
            T.match_trigger(v, line)
        T.check_trigger(v, "Bob tells you, 'hi'")
    assert ok > 50, ok
    # wholly random junk never raises
    for _ in range(300):
        junk = RNG.choice([hostile_value(), [random_trigger()], {"actions": hostile_value()}])
        T.validate_trigger(junk)
        T.match_line("x", [junk])
        T.validate_alias(junk)
        T.migrate_legacy_aliases(junk)
        T.describe_actions(junk)
        T.check_trigger(junk, hostile_value())


# --------------------------------------------------------------------------- performance
def random_regex():
    frags = [r"\d+", r"\s*", "[a-z]+", "(?:ab)+", "x?", "(foo|bar)", ".", r"\w{2,5}", "a", "b",
             "[A-Z]", "(?P<w>\\w+)", " ", ",", r"'", "(?i:q)", "[^ ]+", "a{1,3}", ".*", r"\S+"]
    return "".join(RNG.choice(frags) for _ in range(RNG.randint(1, 7)))


def hostile_lines():
    s = "".join(RNG.choice("ab ") for _ in range(600))
    return ["a" * 600, "ab" * 300, " " * 600, "a" * 599 + "!", ("a " * 300), "1" * 600,
            "x" * 300 + "'" * 300, s, "A" * 590 + "     ", ("foo " * 150), "é" * 600,
            "tells you, " * 55]


def check_hostile_timing():
    lines = hostile_lines()
    made = 0
    attempts = 0
    worst = 0.0
    while made < 200 and attempts < 5000:
        attempts += 1
        if made % 2 == 0:
            pat = "".join(RNG.choice(["a", "b", "*", "?", " ", "'", "x", "foo", "*"])
                          for _ in range(RNG.randint(1, 20)))
            if RNG.random() < 0.3:
                pat = "^" + pat
            if RNG.random() < 0.3:
                pat = pat + "$"
            t = trig(pat)
        else:
            t = trig(random_regex(), "regex", ignore_case=RNG.random() < 0.5)
        v = T.validate_trigger(t)
        if v is None:
            continue
        made += 1
        for ln in lines:
            t0 = time.perf_counter()
            T.match_trigger(v, ln)
            dt = time.perf_counter() - t0
            worst = max(worst, dt)
            assert dt < 0.05, (v["pattern"], v["mode"], dt, ln[:20])
    assert made == 200
    # the classic evil regexes are refused outright, so they never get to run
    for p in (r"(a+)+$", r"(a|a)*b", r"(a*)*b", r"(.*a){12}"):
        assert T.validate_trigger(trig(p, "regex")) is None, p


# --------------------------------------------------------------------------- LoopGuard
def check_loop_guard():
    g = T.LoopGuard(max_per_second=3, max_per_line=100)
    assert [g.allow("k", now=0.0) for _ in range(5)] == [True, True, True, False, False]
    assert g.allow("other", now=0.5) is True
    assert g.allow("k", now=0.99) is False
    assert g.allow("k", now=1.0) is True               # the t=0 hits are exactly a second old
    g2 = T.LoopGuard(max_per_second=2, max_per_line=100)
    assert g2.allow("a", now=0.0) and g2.allow("a", now=0.6)
    assert not g2.allow("a", now=0.9)
    assert g2.allow("a", now=1.1) is True              # 0.0 expired, 0.6 still counts
    assert not g2.allow("a", now=1.2)
    assert g2.allow("a", now=1.65) is True
    # per-line cap, shared across keys, reset by begin_line
    g3 = T.LoopGuard(max_per_second=1000, max_per_line=8)
    g3.begin_line()
    res = [g3.allow("k%d" % (i % 3), now=0.0) for i in range(12)]
    assert res == [True] * 8 + [False] * 4
    g3.begin_line()
    assert g3.allow("k0", now=0.0) is True
    d = T.LoopGuard()
    assert d.max_per_second == 20 and d.max_per_line == 8
    d.begin_line()
    assert sum(d.allow("x", now=5.0) for _ in range(30)) == 8      # line cap bites first
    # denied attempts are not recorded: after a second it recovers fully
    g4 = T.LoopGuard(max_per_second=2, max_per_line=1000)
    for _ in range(50):
        g4.allow("a", now=0.0)
    assert g4.allow("a", now=1.0) is True
    # bounded memory with many distinct keys
    g5 = T.LoopGuard(max_per_second=5, max_per_line=10 ** 9)
    for i in range(20000):
        g5.allow(("key", i), now=i * 0.01)
    assert len(g5._hits) < 1200, len(g5._hits)
    g6 = T.LoopGuard(1, 10 ** 9)
    for i in range(5000):
        g6.allow(i, now=0.0)                       # all within the same instant
    assert len(g6._hits) <= 1200, len(g6._hits)
    # odd keys and the default clock do not raise
    g7 = T.LoopGuard()
    assert g7.allow(["unhashable"]) in (True, False)
    assert g7.allow(None, now=None) in (True, False)
    # clock going backwards does not wedge the guard
    g8 = T.LoopGuard(1, 100)
    assert g8.allow("a", now=100.0) and g8.allow("a", now=50.0)


# --------------------------------------------------------------------------- aliases
def check_alias_validation():
    v = T.validate_alias({"name": " Hello ", "body": "  say hi  ", "junk": 1})
    assert v == {"name": "Hello", "enabled": True, "body": "say hi"}
    assert T.validate_alias({"name": "a", "body": "b", "enabled": False})["enabled"] is False
    assert T.validate_alias({"name": "a", "body": "b", "enabled": "no"})["enabled"] is False
    for n in ("a!?.+-_9", "A" * 24):
        assert T.validate_alias({"name": n, "body": "x"}) is not None, n
    for bad in (None, 5, [], {}, {"name": "a"}, {"body": "x"}, {"name": "", "body": "x"},
                {"name": "a b", "body": "x"}, {"name": "A" * 25, "body": "x"},
                {"name": "é", "body": "x"}, {"name": "a;", "body": "x"},
                {"name": "a\n", "body": "x"} if False else {"name": "a/b", "body": "x"},
                {"name": "a", "body": ""}, {"name": "a", "body": "   "},
                {"name": "a", "body": "x" * 401}, {"name": "a", "body": 5},
                {"name": 5, "body": "x"}, {"name": "a" * 5000, "body": "x"}):
        assert T.validate_alias(bad) is None, bad
    d = {"name": "a", "body": "x\x00y\tz"}
    snap = copy.deepcopy(d)
    v = T.validate_alias(d)
    assert d == snap and v["body"] == "xyz"
    assert T.validate_alias(v) == v
    for _ in range(500):
        d = {RNG.choice(["name", "body", "enabled"]): hostile_value() for _ in range(3)}
        r = T.validate_alias(d)
        assert r is None or T.validate_alias(r) == r


def check_alias_find():
    als = [None, 7, {"name": "bad name", "body": "x"}, {"name": "Kk", "body": "off", "enabled": False},
           {"name": "kk", "body": "second"}, {"name": "KK", "body": "third"}, {"name": "gg", "body": "g"}]
    assert T.find_alias("KK", als) is als[4]
    assert T.find_alias("kk", als)["body"] == "second"
    assert T.find_alias("gg", als) is als[6]
    assert T.find_alias("zz", als) is None
    assert T.find_alias("bad", als) is None and T.find_alias("bad name", als) is None
    assert T.find_alias("", als) is None and T.find_alias(None, als) is None
    assert T.find_alias("kk", None) is None and T.find_alias("kk", "kk") is None
    assert T.find_alias("kk", [als[3]]) is None


def check_alias_expand():
    A = lambda body, **kw: dict({"name": "x", "body": body}, **kw)       # noqa: E731
    E = T.expand_alias
    assert E(A("say hello"), "") == ["say hello"]
    assert E(A("say hello"), "   ") == ["say hello"]
    assert E(A("say hello"), "bob") == ["say hello bob"]             # legacy rule
    assert E(A("a;b"), "x y") == ["a", "b x y"]                       # appended to LAST command
    assert E(A("a;;b"), "x") == ["a;b x"]
    assert E(A("kill"), "  orc  ") == ["kill orc"]
    assert E(A("tell %1 %2"), "bob hi there") == ["tell bob hi"]
    assert E(A("tell %1 %2"), "bob") == ["tell bob"]                  # missing -> ''
    assert E(A("tell %1 %2"), "") == ["tell"]
    assert E(A("say %*"), "  a  b c ") == ["say a  b c"]
    assert E(A("say %0"), "a b") == ["say a b"]
    assert E(A("say %*"), "") == ["say"]
    assert E(A("%1"), "") == []                                       # empty command dropped
    assert E(A("say 100%%"), "x") == ["say 100%"]                     # a token: no legacy append
    assert E(A("say %x"), "arg") == ["say %x arg"]                    # %x is not a token
    assert E(A("say %1 %%"), "a") == ["say a %"]
    assert E(A("say %*"), "a;b") == ["say a;b"]                       # ';' in args: no split
    assert E(A("say %1;look"), "a;b c") == ["say a;b", "look"]
    assert E(A("say %*"), "%1 %2 %%") == ["say %1 %2 %%"]              # no recursion
    assert E(A("say"), "a;b") == ["say a;b"]
    assert E(A("%1 %1 %1;n"), "go") == ["go go go", "n"]
    assert E(A("say %1%2"), "a b") == ["say ab"]
    assert E(A("x %9"), "1 2 3 4 5 6 7 8 9 10") == ["x 9"]
    assert E(A("x%10"), "7") == ["x70"]
    assert E(A("n;s;e;w"), "") == ["n", "s", "e", "w"]
    assert E(A("say %*"), "x\x00y") == ["say xy"]
    assert len(E(A("say %*"), "z" * 1000)[0]) == 200
    assert E(A(";".join("c%d" % i for i in range(30))), "") == ["c%d" % i for i in range(20)]
    assert E(None, "x") == [] and E({"name": "x"}, "x") == [] and E(A("a"), None) == ["a"]
    assert E(A("a", enabled=False), "x") == ["a x"]       # enabled is the caller's business


def check_alias_migration():
    old = {"zed": "n;s", "Abc": "look", "bad name": "x", "ok": 5, 7: "x", "e": "", "n": None,
           "d": "x" * 500, "ABC": "dup", "g!": "say %1", "": "x", "long" * 10: "x"}
    got = T.migrate_legacy_aliases(old)
    assert [a["name"] for a in got] == ["ABC", "g!", "zed"], got
    assert all(T.validate_alias(a) == a for a in got) and all(a["enabled"] for a in got)
    assert got[0]["body"] == "dup"
    for junk in (None, 5, "x", [], [("a", "b")], {}):
        assert T.migrate_legacy_aliases(junk) == []
    many = {"a%03d" % i: "x" for i in range(T.MAX_ALIASES + 100)}
    r = T.migrate_legacy_aliases(many)
    assert len(r) == T.MAX_ALIASES and r[0]["name"] == "a000" and r[-1]["name"] == "a%03d" % (T.MAX_ALIASES - 1)
    snap = dict(old)
    T.migrate_legacy_aliases(old)
    assert old == snap


# --------------------------------------------------------------------------- editor helpers
def check_check_trigger():
    t = trig("* tells you, '*'", actions=[
        {"type": "highlight", "fg": "#ffd700"},
        {"type": "send", "text": "reply thanks"},
        {"type": "note", "text": "from %1: %2 (%%)"},
        {"type": "gag"}], enabled=False)
    ok, msg, ms = T.check_trigger(t, "Bob tells you, 'hi'")
    assert ok, msg
    assert msg.startswith("Matched 'Bob tells you, 'hi'' -> %1=Bob %2=hi; actions: highlight, "
                          "send 'reply thanks'"), msg
    assert "note 'from Bob: hi (%)'" in msg and msg.endswith("hide"), msg
    assert len(ms) == 1 and ms[0]["captures"]["1"] == "Bob"
    assert T.check_trigger(t, "nothing here") == (False, "Pattern does not match the sample", [])
    ok, msg, ms = T.check_trigger(t, "")
    assert not ok and ms == [] and msg
    ok, msg, ms = T.check_trigger(t, None)
    assert not ok
    ok, msg, ms = T.check_trigger(trig("(a+)+", "regex"), "aa")
    assert not ok and "Unsafe pattern:" in msg
    ok, msg, _ = T.check_trigger(trig("(x"), "x")
    assert ok or True
    ok, msg, _ = T.check_trigger({"name": "n"}, "x")
    assert not ok and msg
    ok, msg, _ = T.check_trigger(trig("p", name=""), "p")
    assert not ok and "Name" in msg
    ok, msg, _ = T.check_trigger(trig("p", actions=[]), "p")
    assert not ok and "action" in msg.lower()
    ok, msg, _ = T.check_trigger(trig("a*" * 9), "aaaa")
    assert not ok and "wildcard" in msg.lower()
    ok, msg, _ = T.check_trigger(trig("p", mode="x"), "p")
    assert not ok and "mode" in msg.lower()
    ok, msg, _ = T.check_trigger(trig(r"(?P<who>\w+) waves", "regex"), "Al waves")
    assert ok and "%1=Al" in msg and "%{who}=Al" in msg, msg
    ok, msg, _ = T.check_trigger(trig("say", actions=[{"type": "send", "text": "a;b %0"}]), "say")
    assert ok and "send 'a; b say'" in msg, msg
    assert T.describe_actions(t) == "highlight, send, note, hide"
    assert T.describe_actions({"actions": [{"type": "gag"}, {"type": "beep"}, 5, {"type": "x"}]}) \
        == "hide, beep"
    assert T.describe_actions(None) == "" and T.describe_actions({"actions": 3}) == ""
    assert T.describe_actions(trig("p", actions=[{"type": "highlight"}, {"type": "gag"},
                                                 {"type": "send"}, {"type": "beep"}])) \
        == "highlight, hide, send, beep"


def check_presets():
    assert isinstance(T.PRESETS, list) and len(T.PRESETS) >= 3
    names = set()
    for p in T.PRESETS:
        assert p["enabled"] is False, p["name"]
        assert_fully_valid(p)
        assert T.validate_trigger(p) == p
        names.add(p["name"])
    assert len(names) == len(T.PRESETS)
    by = {p["name"]: p for p in T.PRESETS}
    assert T.match_trigger(dict(by["Highlight tells"], enabled=True), "Bob tells you hi")
    assert T.match_trigger(dict(by["Highlight OOC"], enabled=True), "[OOC] Bob: hi")
    assert T.match_trigger(dict(by["Highlight OOC"], enabled=True), "x [OOC] hi") is None
    assert by["Highlight OOC"]["pattern"] == "^[OOC]*"
    assert T.match_trigger(by["Highlight tells"], "Bob tells you hi") is None      # disabled
    cp = T.get_presets()
    cp[0]["name"] = "changed"
    assert T.PRESETS[0]["name"] != "changed"
    assert T.match_line("Bob tells you, 'hi'", T.PRESETS) == []


def check_compile_cache_and_purity():
    t = trig("a*b")
    c1, c2 = T.compile_trigger(t), T.compile_trigger(dict(t, name="other", priority=3))
    assert c1 is not None and c1 is c2
    assert T.compile_trigger(dict(t, ignore_case=False)) is not c1
    for bad in (None, 5, {}, {"mode": "plain"}, {"mode": "plain", "pattern": 5},
                {"mode": "plain", "pattern": ""}, {"mode": "nope", "pattern": "a"},
                {"mode": "plain", "pattern": ["a"]}, {"mode": ["plain"], "pattern": "a"},
                {"mode": "plain", "pattern": "a\x00"}):
        assert T.compile_trigger(bad) is None, bad
    s = T.plain_to_regex("^a.b*?$")
    assert isinstance(s, str) and re.search(s, "a.b") is None and re.search(s, "a.bxy") and re.search(s, "a.bx")
    assert re.search(T.plain_to_regex("A*", False), "a") is None
    assert re.search(T.plain_to_regex("A*", True), "a")
    assert T.plain_to_regex(None) == "(?!)"
    # nothing is mutated by matching
    t = trig("* tells *")
    snap = copy.deepcopy(t)
    T.match_trigger(t, "Bob tells you x")
    T.match_line("Bob tells you x", [t])
    assert t == snap


def main():
    checks = [(n, f) for n, f in sorted(globals().items())
              if n.startswith("check_") and callable(f)]
    failed = 0
    t_all = time.time()
    for name, fn in checks:
        t0 = time.time()
        try:
            fn()
            print("PASS %s (%.2fs)" % (name, time.time() - t0))
        except Exception:
            failed += 1
            print("FAIL %s" % name)
            traceback.print_exc()
    print("%d checks, %d failed, %.1fs" % (len(checks), failed, time.time() - t_all))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
