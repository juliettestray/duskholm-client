"""Hex -> xterm, gradients and saved patterns (pure, fuzzed)."""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import colortools as ct

assert len(ct.XTERM) == 256 and ct.XTERM[16] == "#000000" and ct.XTERM[21] == "#0000ff" and ct.XTERM[196] == "#ff0000"
assert ct.XTERM[231] == "#ffffff" and ct.XTERM[232] == "#080808" and ct.XTERM[255] == "#eeeeee" and ct.XTERM[208] == "#ff8700"
assert ct.parse_hex("#FF8800") == (255, 136, 0) and ct.parse_hex("f80") == (255, 136, 0) and ct.parse_hex("0xff8800") == (255, 136, 0)
for bad in ("", "#12", "gg0000", "#1234567", None, "12345", "ff 88 00", "١٢٣"):
    try:
        ct.parse_hex(bad); assert False, bad
    except ValueError:
        pass
assert ct.nearest_xterm((255, 0, 0))[0] == 196, "pure red is xterm 196 when the system colours are skipped"
assert ct.nearest_xterm((255, 0, 0), system=True)[0] in (9, 196)
assert ct.nearest_xterm((255, 136, 0))[0] == 208 and ct.nearest_xterm((0, 0, 0))[0] == 16
assert ct.nearest_xterm((255, 255, 255))[0] == 231 and ct.nearest_xterm((128, 128, 128))[0] == 244
assert ct.nearest_xterm((30, 30, 30))[0] == 234
idx, hx, d = ct.nearest_xterm((10, 200, 60)); assert ct.XTERM[idx] == hx and d >= 0
assert ct.code(45) == "`045" and ct.code(0) == "`000" and ct.code(255) == "`255"
assert ct.parse_colours("196 202, `208 #ffcc00") == [196, 202, 208, ct.nearest_xterm(ct.parse_hex("#ffcc00"))[0]]
for bad in ("", "256", "1234", "red", "a" * 5, ",,,"):
    try:
        ct.parse_colours(bad); assert False, bad
    except ValueError:
        pass
try:
    ct.parse_colours(" ".join(["1"] * 40)); assert False
except ValueError:
    pass

S = [196, 208, 226]
out = ct.apply("Hello world", S, "stretch", smooth=False)
assert out == "`196Hel`208lo w`226orld`x", out
assert ct.strip_codes(out) == "Hello world"
cyc = ct.apply("abcdef", [1, 2], "cycle")
assert ct.strip_codes(cyc) == "abcdef" and cyc.count("`001") == 3 and cyc.count("`002") == 3
mid = ct.apply("abcde", [10, 20, 30], "middle", smooth=False)
assert mid == "`030a`020b`010c`020d`030e`x", mid
bo = ct.apply("abcdefg", [1, 2, 3], "bounce")
assert bo == "`001a`002b`003c`002d`001e`002f`003g`x", bo
r1 = ct.apply("random text here", S, "random", seed=5); r2 = ct.apply("random text here", S, "random", seed=5)
assert r1 == r2 and ct.strip_codes(r1) == "random text here"
w = ct.apply("one two three", [1, 2, 3], "word", smooth=False)
assert w == "`001one `002two `003three`x", w
ln = ct.apply("top\nmid\nlow", [1, 2, 3], "line", smooth=False)
assert ln == "`001top\n`002mid\n`003low`x", ln
assert ct.apply("a`b", [5]) == "`005a``b`x" and ct.strip_codes("`005a``b`x") == "a``b"
assert ct.apply("   ", [5]) == "   " and ct.apply("", [5]) == ""
smooth = ct.apply("abcdefghij", [16, 231], "stretch", smooth=True)
cols = [int(x) for x in __import__("re").findall(r"`(\d{3})", smooth)]
assert cols[0] == 16 and cols[-1] == 231 and len(set(cols)) > 4, "a real ramp between the two ends"
for bad_mode in ("zigzag", None, 5):
    try:
        ct.apply("x", S, bad_mode); assert False
    except ValueError:
        pass
for bad_stops in ([], [256], [-1], ["a"], None, [1] * 65):
    try:
        ct.apply("x", bad_stops); assert False, bad_stops
    except (ValueError, TypeError):
        pass
try:
    ct.apply("x" * 2000, S); assert False
except ValueError:
    pass
try:
    ct.apply("ab" * 700, S, "cycle"); assert False, "too many codes"
except ValueError:
    pass

# the presets are all sane
for name, cols in ct.PRESETS.items():
    assert 1 <= len(cols) <= 32 and all(0 <= c <= 255 for c in cols), name
    assert ct.strip_codes(ct.apply("The quick brown fox", cols, "stretch")) == "The quick brown fox"

# saved patterns
sv = ct.validate_saved([{"name": "  Mine  ", "colours": [1, 2]}, {"name": "fire", "colours": [1]}, {"name": "Bad", "colours": [999]},
                        {"name": "Two", "colours": []}, {"name": "mine", "colours": [3]}, "x", None, {"name": 5, "colours": [1]},
                        {"name": "Bool", "colours": [True]}, {"name": "Ok", "colours": [0, 255]}])
assert [s["name"] for s in sv] == ["Mine", "Ok"], sv
assert ct.find_pattern("FIRE", sv) == ct.PRESETS["Fire"] and ct.find_pattern("mine", sv) == [1, 2] and ct.find_pattern("nope", sv) is None
assert ct.all_pattern_names(sv)[-2:] == ["Mine", "Ok"] and ct.validate_saved("x") == []

# fuzz: never raises anything but ValueError; output always strips back to the input text
rnd = random.Random(3)
alpha = "ab c`\né☃x"
for _ in range(3000):
    t = "".join(rnd.choice(alpha) for _ in range(rnd.randint(0, 30)))
    st = [rnd.randint(0, 255) for _ in range(rnd.randint(1, 8))]
    mode = rnd.choice(ct.MODES)
    try:
        o = ct.apply(t, st, mode, smooth=rnd.random() < 0.5, seed=rnd.randint(0, 9))
    except ValueError:
        continue
    assert ct.strip_codes(o).replace("``", "`") == t, (t, o)

# ---- colour codes in a long text: where they are, colouring part of it, taking them off
text = "ab`196cd`xef"
assert ct.spans(text) == [(0, 2, None, False), (2, 6, None, True), (6, 8, 196, False), (8, 10, None, True), (10, 12, None, False)], ct.spans(text)
assert ct.spans("") == [] and ct.spans("plain") == [(0, 5, None, False)]
assert ct.spans("a``b") == [(0, 4, None, False)], "a doubled backtick is just text"
assert ct.spans("`999 `4 `") == [(0, 9, None, False)], "not a code: stays text"
assert [x for x in ct.spans("`045hi`123there`x!") if not x[3]] == [(4, 6, 45, False), (10, 15, 123, False), (17, 18, None, False)]
out = ct.colour_text("Hello world", [196, 226], "stretch", smooth=False)
assert out == ct.apply("Hello world", [196, 226], "stretch", smooth=False)
part = ct.colour_text("Hello big world", [196, 226], "cycle", rng=(6, 9))
assert part.startswith("Hello ") and part.endswith("`x world") and ct.strip_codes(part) == "Hello big world" and "`196b" in part
again = ct.colour_text(part, [21, 46], "cycle", rng=(0, len(part)))
assert ct.strip_codes(again) == "Hello big world" and "`196" not in again, "colours already there are replaced"
assert ct.colour_text("a``b", [5]) == "`005a``b`x" and ct.colour_text("`005a``b`x", [7]) == "`007a``b`x", "backticks survive a round trip"
assert ct.colour_text("a`bc", [5]) == "`005ac`x", "a lone backtick before a letter IS a game colour code (`b), so it is replaced"
assert ct.colour_text("abc", [1], rng=(2, 1)) == ct.apply("abc", [1]) and ct.colour_text("abc", [1], rng=(0, 99)) == ct.apply("abc", [1])
assert ct.colour_text("one\ntwo", [1, 2], "stretch", smooth=False) == "`001o`002ne\n`001t`002wo`x"[:0] + ct.apply("one\ntwo", [1, 2], "stretch", smooth=False)
assert ct.strip_colour("a`196b`xc", (0, 5)) == "ab`xc" and ct.strip_colour("a`196b`xc") == "abc" and ct.strip_colour(None) == ""
for bad in ([], [300]):
    try:
        ct.colour_text("x", bad); assert False
    except ValueError:
        pass

# ---- the stop list as a picker edits it
flat = [i for r in ct.palette_rows() for i in r]
assert sorted(flat) == list(range(256)) and max(len(r) for r in ct.palette_rows()) == 18
assert ct.from_hex("#ff0000") == (196, "#ff0000", True) and ct.from_hex("ff8800")[0] == 208 and not ct.from_hex("ff8800")[2]
try:
    ct.from_hex("nonsense"); assert False
except ValueError:
    pass
assert ct.from_hsv(120, 1, 1)[0] == 46 and ct.from_hsv(480, 1, 1)[0] == 46, "hue wraps"
assert ct.hsv_of(196) == (0.0, 1.0, 1.0) and ct.describe(196) == "196  #ff0000"
assert ct.add_stop([196, 226], 0) == ([196, 208, 226], 1), "a new stop sits between its neighbours"
assert ct.add_stop([196, 226]) == ([196, 226, 226], 2) and ct.add_stop([], None)[0] == [196]
full = list(range(ct.MAX_STOPS)); assert ct.add_stop(full, 3)[0] == full, "capped"
assert ct.remove_stop([1, 2, 3], 2) == ([1, 2], 1) and ct.remove_stop([5], 0) == ([5], 0), "the last one stays"
assert ct.move_stop([1, 2, 3], 0, 1) == ([2, 1, 3], 1) and ct.move_stop([1, 2, 3], 0, -1) == ([1, 2, 3], 0)
bar = ct.preview_bar([196, 226], 5)
assert len(bar) == 5 and bar[0] == 196 and bar[-1] == 226 and ct.preview_bar([21], 3) == [21, 21, 21] and ct.preview_bar([], 2) == [7, 7]
assert ct.stops_text([196, 202]) == "196,202" and ct.parse_colours(ct.stops_text([196, 202])) == [196, 202]

# ---- several gradients in one text, by highlighting each part
txt = "Hello brave new world"
one = ct.colour_text(txt, [196, 226], "stretch", rng=(0, 5))
two = ct.colour_text(one, [21, 51], "stretch", rng=(one.index("brave"), one.index("brave") + 5))
assert ct.strip_codes(two) == txt and "`196H" in two and "`021b" in two and two.endswith(" new world"), two
assert two.startswith(one[:one.index("`x") + 2]), "the first part is untouched by colouring the second"
# a highlight that starts or ends inside a code takes the whole code in (never a half code)
i = two.index("`") + 2
cut = ct.colour_text(two, [46, 82], "stretch", rng=(i, len(two)))
assert ct.strip_codes(cut) == txt and "`1`" not in cut and cut.count("`") == len([m for m in __import__("re").finditer("`(?:\d\d\d|x)", cut)]), cut
assert ct.snap_range("a`196bc", (3, 6)) == (1, 6) and ct.snap_range("a`196bc", (0, 3)) == (0, 5) and ct.snap_range("x", None) is None
assert ct.snap_range("a``b", (2, 4)) == (1, 4), "a doubled backtick is one character"
assert ct.strip_codes(ct.strip_colour(two, (i, len(two)))) == txt
print("colortools tests OK")
