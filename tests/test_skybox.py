"""The sky box: what the game sent decides what is drawn, nothing is invented, and the art always fits."""
import itertools, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gmcp, skybox

# every picture is the same size and uses only colours the client knows
n = 0
for w, t, night, mist, dos in itertools.product(["clear", "few", "partly", "cloudy", "rain", "storm", "snow", "hail", "fog", None],
                                                ["forest", "water", "field", "street", "hills", "plain", "indoors", None],
                                                [False, True], [0, 1, 2, 3], [False, True]):
    rows = skybox.art(w, t, night, mist, dos)
    assert len(rows) == skybox.ART_H, (w, t)
    assert all(sum(len(x) for x, _r in r) == skybox.ART_W for r in rows), (w, t, night, mist, dos)
    assert all(role in gmcp.ROLES for r in rows for _x, role in r)
    n += 1
assert n == 10 * 8 * 2 * 4 * 2
text = lambda rows: "".join(x for r in rows for x, _r in r)
assert "~" not in text(skybox.art("clear", "field", False, 0, False)) and "~" in text(skybox.art("clear", "field", False, 1, False)), "mist only when asked"
count = lambda lvl: text(skybox.art("clear", "field", False, lvl, False)).count("~")
assert count(1) < count(2) < count(3), "deeper mist, more of it"
assert "brown" in [role for r in skybox.art("clear", "forest", False, 0, True) for _x, role in r], "pines have brown trunks"

# the game's own fields (Room.Environment)
kind = lambda **e: skybox.weather_kind(e)
assert kind(clouds="clear") == "clear" and kind(clouds="wispy", cover="few") == "few" and kind(clouds="thin", cover="partly") == "partly"
assert kind(clouds="grey", cover="full") == "cloudy" and kind(clouds="dark", cover="full", falling=["rain"]) == "rain"
assert kind(clouds="storm", cover="full", falling=["rain"]) == "storm" and kind(clouds="grey", falling=["snow"]) == "snow"
assert kind(clouds="grey", falling=["hail"]) == "hail" and kind(falling=["rain", "hail"]) == "hail" and kind(falling=["snow", "hail"]) == "snow"
assert kind() is None
assert skybox.cloud_tone({"clouds": "wispy"}) == "light" and skybox.cloud_tone({"clouds": "dark"}) == "dark" and skybox.cloud_tone({"clouds": "storm"}) == "dark"
assert [skybox.mist_level({"mist": m}) for m in ("ankle", "waist", "wreathed", "thin")] == [1, 2, 3, 1] and skybox.mist_level({}) == 0
assert skybox.weather_words({"clouds": "storm", "falling": ["rain"]}) == "storm clouds, rain" and skybox.weather_words({"clouds": "clear"}) == "clear sky"
assert skybox.weather_words({}) == ""

# reading the game's words
assert skybox.weather_kind({"weather": "few dark grey stormclouds"}) == "storm"
assert skybox.weather_kind({"sky": "a light drizzle"}) == "rain" and skybox.weather_kind({"weather": "overcast"}) == "cloudy"
assert skybox.weather_kind({"weather": "heavy snow"}) == "snow" and skybox.weather_kind({"weather": "clear"}) == "clear"
assert skybox.weather_kind({}) is None and skybox.weather_kind({"weather": 5}) is None and skybox.weather_kind({"weather": ["x"]}) is None
assert [skybox.terrain_kind({"environment": e}) for e in ("inside", "city", "forest", "field", "water", "hills", "mystery")] == \
       ["indoors", "street", "forest", "field", "water", "hills", "plain"]
assert skybox.terrain_kind({}) is None and skybox.terrain_kind({"indoors": True}) == "indoors"
assert skybox.is_night(13, "afternoon") is False and skybox.is_night(13, "night") is True
assert skybox.is_night(22, "evening") is True and skybox.is_night(18, "evening") is False and skybox.is_night(3) is True and skybox.is_night(12) is False
assert [skybox.period_word(h) for h in (3, 8, 13, 18, 23)] == ["night", "morning", "afternoon", "evening", "night"]

# Fahrenheit or Celsius
assert skybox.choose_unit("f", "GB") == "f" and skybox.choose_unit("c", "US") == "c"
assert skybox.choose_unit("guess", "US") == "f" and skybox.choose_unit("guess", "LR") == "f" and skybox.choose_unit("guess", "GB") == "c"
assert skybox.choose_unit("guess", "") == "c" and skybox.choose_unit("nonsense", "US") == "f"
assert skybox.temp_text({"temp_f": 29, "temp_c": -1}, "f") == "29\u00b0F" and skybox.temp_text({"temp_f": 29, "temp_c": -1}, "c") == "-1\u00b0C"
assert skybox.temp_text({"temp_f": 32}, "c") == "0\u00b0C" and skybox.temp_text({"temp_c": 100}, "f") == "212\u00b0F", "either one is enough"
assert skybox.temp_text({}, "f") == "" and skybox.temp_text({"temp_f": "hot"}, "f") == "" and skybox.temp_text({"temp_f": True}, "f") == ""
assert skybox.region_code() == "" or len(skybox.region_code()) == 2

# the box
info = {"neighborhood": "Whitney", "coords": "10,18,0", "temp_f": 29, "temp_c": -1, "clouds": "storm", "cover": "few", "falling": ["rain"],
        "terrain": "forest", "hour": 13, "minute": 10, "clock": "13:10", "daytime": "afternoon", "moon": {"name": "waning gibbous", "lit": 0.92}, "unit": "f", "width": 46}
box = lambda **kw: skybox.sky_lines(dict(info, **kw))
full = lambda lines: [("".join(t for t, _r in ln)) for ln in lines]
lines = full(box())
assert "29\u00b0F" in lines[0] and "Whitney" in lines[0] and "10,18,0" in lines[0] and lines[0].index("Whitney") > skybox.LEFT_W
assert any("13:10  afternoon" in l for l in lines) and any("Waning gibbous 92%" in l for l in lines)
assert not any("Mist" in l for l in lines), "no mist unless it was sent"
assert any("Mist: waist-deep" in l for l in full(box(mist="waist"))) and any("Mist: wreathed" in l for l in full(box(mist="wreathed")))
assert not any("Mist" in l for l in full(box(mist=""))) and "Waning gibbous" in "".join(full(box(moon="waning gibbous")))
assert not any("Mist" in l for l in full(box(mist=None)))
assert "-1\u00b0C" in full(box(unit="c"))[0]
# a narrow column: shorter mist words, and the coordinates on a line of their own when they do not fit beside the name
narrow = full(box(width=34, mist="waist"))
assert any("Mist: waist" in l and "deep" not in l for l in narrow), narrow
assert any(l.strip().endswith("10,18,0") for l in narrow) and "10,18,0" not in narrow[0], narrow
assert not any("Mist" in l and "\u2026" in l for l in narrow), "the mist word is not cut short"
assert any("Waning gibb" in l for l in narrow) and not any("92%" in l for l in narrow), "the moon drops its percentage first"
assert any("Mist: waist-deep" in l for l in full(box(mist="waist"))), "a wide column keeps the full word"
# a property whose time is frozen
fz = full(box(frozen=True, hour=13, minute=0, clock="13:00"))
assert any("eternally 13:00" in l for l in fz), fz
assert not any("eternally" in l for l in full(box())) and not any("eternally" in l for l in full(box(frozen=False))) and not any("eternally" in l for l in full(box(frozen="yes")))
assert any("full-moon night" in l for l in full(box(moon={"name": "full", "lit": 1.0, "full": True}))) and any("full-moon night" in l for l in full(box(moon="full")))
assert not any("full-moon night" in l for l in full(box(moon="waxing gibbous")))
# the picture off: words only; nothing known: no left side at all, and no invented sky
off = full(box(art_on=False))
assert "29\u00b0F" in off[0] and "storm clouds, rain" in off[1] and "/|\\" not in "".join(off)
none = full(skybox.sky_lines({"coords": "1,2,3", "clock": "09:00 EST", "hour": 9, "unit": "c", "width": 44}))
assert none[0].strip() == "1,2,3" and "\u00b0" not in "".join(none) and "/" not in "".join(none).replace("1,2,3", "")
# a very long name is shortened, never overflowing its column
assert all(len(l) <= 46 for l in full(box(area="A" * 80)))
# junk in, no crash
for junk in (None, 5, [], {"width": "wide"}, {"moon": "full"}, {"coords": ["x"]}, {"temp_f": float("nan")}):
    try:
        skybox.sky_lines(junk)
    except (ValueError, OverflowError):
        raise AssertionError(junk)
print("skybox tests OK")
