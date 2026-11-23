"""The customize form's command builder and the design book (pure)."""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import custom as c

cmds, prob = c.build_commands({"item": "scarf", "shortstring": "a red scarf", "names": "red scarf silk",
                               "longstring": "A red scarf lies here.", "wear": "around the neck", "cost": "12.5",
                               "layer": "2", "size": "Large", "cover": "neck", "zips": "chest",
                               "description": "Soft silk.\nIt smells of rain.", "taste": "silk",
                               "extra": "tag", "extra_text": "Made in Haven."})
assert prob == []
assert cmds == ["customize scarf names red scarf silk", "customize scarf shortstring a red scarf",
                "customize scarf longstring A red scarf lies here.", "customize scarf wear around the neck",
                "customize scarf cost 12.5", "customize scarf layer 2", "customize scarf large",
                "customize scarf cover clear", "customize scarf cover neck", "customize scarf zips clear",
                "customize scarf zips chest",
                "customize scarf description", "Soft silk.", "It smells of rain.", "@",
                "customize scarf taste", "silk", "@", "customize scarf extra tag", "Made in Haven.", "@"], cmds
# typed \n works in one-line boxes; editor commands inside text are defanged
cm, _ = c.build_commands({"item": "x", "description": ".c\n@ now\n~ x\nfine"})
assert cm == ["customize x description", " .c", " @ now", " ~ x", "fine", "@"], cm
for bad, why in (({}, "item"), ({"item": "two words", "names": "a"}, "one word"), ({"item": "x"}, "at least one"),
                 ({"item": "x", "cost": "abc"}, "price"), ({"item": "x", "cost": "-5"}, "price"), ({"item": "x", "cost": "0"}, "price"),
                 ({"item": "x", "layer": "6"}, "layer"), ({"item": "x", "size": "huge"}, "Size"),
                 ({"item": "x", "extra_text": "t"}, "keyword"), ({"item": "x", "extra": "9", "extra_text": "t"}, "keyword"),
                 ({"item": "x", "extra": "k"}, "no text")):
    cm, pr = c.build_commands(bad)
    assert cm == [] and pr and why.lower() in " ".join(pr).lower(), (bad, pr)
# cover / zips: a list of the game's body parts, started clean because the game toggles each one
cm, pr = c.build_commands({"item": "x", "cover": "Neck, chest; neck"}); assert pr == [] and cm == [
    "customize x cover clear", "customize x cover neck", "customize x cover chest"], cm
assert c.build_commands({"item": "x", "zips": "clear"})[0] == ["customize x zips clear"]
cm, pr = c.build_commands({"item": "x", "cover": "neck, elbow"}); assert cm == [] and "elbow" in pr[0]
assert c.parse_parts("") == ([], "") and c.parse_parts("hair eyes") == (["hair", "eyes"], "") and c.parse_parts("tail")[1] == "tail"
assert len(c.COVER_PARTS) == 18 and len(set(c.COVER_PARTS)) == 18
# the game's own item editor (interface mode)
ic, ip = c.build_interface_commands({"itype": "clothing", "cost": "5.5", "size": "Large", "names": "red scarf",
                                     "shortstring": "a red scarf", "longstring": "A red scarf lies here.", "wear": "around the neck",
                                     "layer": "2", "cover": "neck", "zips": "clear", "description": "Soft.\nSilk.", "taste": "silk"})
assert ip == [] and ic == ["type Clothing", "cost 5.5", "size large", "names red scarf", "short a red scarf",
                           "long A red scarf lies here.", "wear around the neck", "layer 2", "cover clear", "cover neck", "zip clear",
                           "descedit", "Soft.", "Silk.", "@", "taste", "silk", "@"], ic
assert c.build_interface_commands({"itype": "food", "count": "3"})[0] == ["type Food", "bites 3"]
assert c.build_interface_commands({"itype": "drink", "count": "3"})[0] == ["type Drink", "drinks 3"]
assert c.build_interface_commands({"itype": "bag", "count": "3"})[0] == ["type Bag", "uses 3"]
for bad in ({}, {"itype": "spaceship"}, {"cost": "x"}, {"size": "big", "names": "a"}, {"count": "0", "names": "a"}, {"layer": "9", "names": "a"},
            {"cover": "tail", "names": "a"}):
    assert c.build_interface_commands(bad)[0] == [] and c.build_interface_commands(bad)[1], bad
assert c.build_interface_commands({"description": ".c\n@ x"})[0] == ["descedit", " .c", " @ x", "@"], "editor commands are defanged"
assert len(c.ITEM_TYPES) == 17 and c.MODES == ("cli", "interface")
# the mode travels with a design, and junk becomes the default
assert c.clean_values({"mode": "interface"})["mode"] == "interface" and c.clean_values({"mode": "rm -rf"})["mode"] == "cli" and c.blank()["mode"] == "cli"
bk = c.save_design([], "Shop scarf", "clothing", {"mode": "interface", "names": "x"}); assert bk[0]["values"]["mode"] == "interface"
assert c.summary("") == "(empty)" and c.summary("one") == "one" and c.summary("a\nb\nc") == "a (+2 lines)"
assert len(c.summary("x" * 200, 30)) <= 30 and c.summary("x" * 200, 30).endswith("...") and c.summary("a\\nb") == "a (+1 lines)"
# one bad field refuses everything (nothing half-sent)
cm, pr = c.build_commands({"item": "x", "names": "ok", "layer": "9"}); assert cm == [] and pr
cm, pr = c.build_commands({"item": "x", "description": "\n".join("l%d" % i for i in range(130))}); assert cm == [] and "more than" in pr[0]
# junk values are cleaned, never trusted
cm, pr = c.build_commands({"item": "x", "names": "a\x07b\x1b[31m", "shortstring": 5, "bogus": "y"})
assert cm == ["customize x names ab[31m"], cm
assert c.clean_values(None) == c.blank() and c.clean_values({"names": "x" * 9000})["names"] == "x" * c.MAX_VALUE

# design book
book = []
book = c.save_design(book, " Silk  scarf ", "clothing", {"item": "scarf", "names": "red scarf"})
assert book == [{"name": "Silk scarf", "type": "clothing", "values": dict(c.blank(), names="red scarf")}], book
book = c.save_design(book, "silk SCARF", "clothing", {"names": "blue scarf"})
assert len(book) == 1 and book[0]["values"]["names"] == "blue scarf", "same type and name replaces"
book = c.save_design(book, "silk scarf", "jewelry", {"names": "x"}); assert len(book) == 2
book = c.save_design(book, "Bin", "garbage-type", {}); assert book[-1]["type"] == "other"
for bad in ("", "   ", "\x00"):
    try:
        c.save_design(book, bad, "clothing", {}); assert False
    except ValueError:
        pass
assert [t for t, _ in c.by_type(book)] == ["clothing", "jewelry", "other"]
book = c.delete_design(book, "jewelry", "SILK scarf"); assert len(book) == 2
assert c.delete_design(book, "weapon", "nope") == book
full = [{"name": "d%d" % i, "type": "other", "values": {}} for i in range(c.MAX_DESIGNS)]
try:
    c.save_design(full, "one more", "other", {}); assert False
except ValueError:
    pass
v = c.validate_designs([{"name": "A", "type": "clothing", "values": {"names": "x"}}, {"name": "a", "type": "clothing"}, "x", None,
                        {"name": 5}, {"name": "B", "type": "nonsense", "values": "junk"}, {"name": "", "type": "game"}])
assert [(d["name"], d["type"]) for d in v] == [("A", "clothing"), ("B", "other")] and v[1]["values"] == c.blank()
assert c.validate_designs("x") == [] and len(c.validate_designs([{"name": "n%d" % i} for i in range(1000)])) == c.MAX_DESIGNS
# fuzz
rnd = random.Random(11)
for _ in range(3000):
    vals = {k: "".join(rnd.choice("ab .@~\n\n1.5x`") for _ in range(rnd.randint(0, 20))) for k in c.KEYS if rnd.random() < 0.5}
    vals["item"] = rnd.choice(["x", "y z", "", "scarf"])
    cm, pr = c.build_commands(vals)
    assert (cm == []) == bool(pr)
    for line in cm:
        assert "\n" not in line and line == line.rstrip() or line == "@"
print("custom tests OK")
