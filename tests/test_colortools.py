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
print("colortools tests OK")
