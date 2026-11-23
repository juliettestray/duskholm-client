"""The 'customize' form: turning filled-in fields into the game's commands, and the design book
(stdlib only, no GUI).

Every field is optional. A design is a saved set of field values so an item can be recreated."""
import re

TYPES = ("clothing", "jewelry", "weapon", "furniture", "food", "drink", "container", "phone", "game",
         "trash", "other")

# key, label, kind ('line' = one line of text, 'text' = several lines, 'choice'), width/help
# what you can name in a cover / zips list (the game's own keywords, one per body part)
COVER_PARTS = ("hands", "forearms", "upperarms", "feet", "lowerlegs", "forehead", "thighs", "groin", "buttocks",
               "lowerback", "upperback", "stomach", "chest", "upperchest", "neck", "lowerface", "hair", "eyes")
# what the game's item editor ("done" ends it) can make
ITEM_TYPES = ("Clothing", "Jewelry", "Food", "Drink", "Thing", "Bag", "Weapon", "Gun", "Phone", "Armor", "Furniture",
              "Drug", "Umbrella", "Perfume", "Flashlight", "Game", "Playback")
SIZES = ("", "small", "large")
LAYERS = ("", "0", "1", "2", "3", "4", "5")
MODES = ("cli", "interface")
MODE_TEXT = {"cli": "Command line (an item you have)", "interface": "Game item editor (a new shop item)"}

FIELDS = (
    ("item", "Item (a word it answers to)", "line", 24),
    ("names", "Keywords (names)", "line", 50),
    ("shortstring", "Short description", "line", 50),
    ("longstring", "Long description (on the ground)", "line", 60),
    ("wear", "Wear string", "line", 40),
    ("cost", "Price ($)", "line", 10),
    ("layer", "Layer (0-5)", "line", 4),
    ("size", "Size (large, small or blank)", "line", 8),
    ("cover", "Cover: body parts, e.g. neck, chest (or clear)", "line", 50),
    ("zips", "Zips: body parts, e.g. chest (or clear)", "line", 50),
    ("description", "Description", "text", 60),
    ("taste", "Taste (food and drink)", "text", 60),
    ("playlist", "Playlist (games)", "text", 60),
    ("extra", "Extra description: keyword", "line", 24),
    ("extra_text", "Extra description: text", "text", 60),
    ("itype", "Kind of item (game editor only), e.g. Clothing", "line", 12),
    ("count", "Bites / drinks / uses (game editor only)", "line", 5),
)
KEYS = tuple(f[0] for f in FIELDS) + ("mode",)          # 'mode' (cli / interface) rides along with a design
# the same fields, with names that fit a DOS dialog
SHORT = {"item": "Item word", "names": "Keywords", "shortstring": "Short desc", "longstring": "Long desc",
         "wear": "Wear string", "cost": "Price ($)", "layer": "Layer", "size": "Size", "cover": "Cover",
         "zips": "Zips", "description": "Description", "taste": "Taste", "playlist": "Playlist",
         "extra": "Extra keyword", "extra_text": "Extra text", "itype": "Item kind", "count": "Count"}
PAGE1 = ("item", "itype", "names", "shortstring", "longstring", "wear", "cost", "size", "count", "layer")
PAGE2 = ("cover", "zips", "description", "taste", "playlist", "extra", "extra_text")
MULTILINE = ("description", "taste", "playlist", "extra_text")
PICKED = ("itype", "size", "layer", "cover", "zips")
MAX_VALUE = 4000
MAX_DESIGNS = 300
MAX_COMMANDS = 120


def blank():
    out = {k: "" for k in KEYS}
    out["mode"] = "cli"
    return out


def clean_values(raw):
    """A dict of field texts reduced to known keys, strings, bounded and free of control characters."""
    out = blank()
    if not isinstance(raw, dict):
        return out
    for k in KEYS:
        v = raw.get(k)
        if isinstance(v, str):
            out[k] = "".join(c for c in v[:MAX_VALUE] if c == "\n" or c.isprintable())
    if out["mode"] not in MODES:
        out["mode"] = "cli"
    return out


def _lines(text):
    """Text split into editor lines: real newlines, or a typed backslash-n for single-line boxes."""
    text = text.replace("\\n", "\n")
    return [l.rstrip() for l in text.split("\n")]


def _safe_line(line):
    """The game's text editor treats lines starting with . @ ~ as commands: keep pasted text from being one."""
    return " " + line if line[:1] in (".", "@", "~") else line


def _one(text):
    return " ".join(str(text).split())


def build_commands(values):
    """(commands, problems): the lines to send to the game, in order. problems is a list of
    messages; when it is not empty the commands should not be sent."""
    v = clean_values(values)
    problems, cmds = [], []
    item = _one(v["item"])
    if not item:
        return [], ["Say which item (the word it answers to)."]
    if " " in item:
        return [], ["The item must be one word (the game only reads the first)."]
    base = "customize %s " % item

    def line(key, sub):
        t = _one(v[key])
        if t:
            cmds.append(base + sub + " " + t)

    line("names", "names")
    line("shortstring", "shortstring")
    line("longstring", "longstring")
    line("wear", "wear")
    cost = _one(v["cost"])
    if cost:
        if re.fullmatch(r"\d{1,7}(\.\d{1,2})?", cost) and float(cost) > 0:
            cmds.append(base + "cost " + cost)
        else:
            problems.append("The price must be a number such as 12.50.")
    layer = _one(v["layer"])
    if layer:
        if layer in list("012345"):
            cmds.append(base + "layer " + layer)
        else:
            problems.append("The layer must be 0 to 5.")
    size = _one(v["size"]).lower()
    if size:
        if size in ("large", "small"):
            cmds.append(base + size)
        else:
            problems.append("Size is large, small or blank.")
    for key, sub in (("cover", "cover"), ("zips", "zips")):
        t = _one(v[key])
        if t:
            parts, bad = parse_parts(t)
            if bad:
                problems.append("%s: %s is not a body part (%s)." % (sub.capitalize(), bad, ", ".join(COVER_PARTS)))
            else:
                cmds.append(base + sub + " clear")                  # the game toggles each part, so start clean
                cmds.extend(base + sub + " " + p for p in parts)

    def block(sub, key):
        text = v[key].strip()
        if not text:
            return
        cmds.append(base + sub)
        cmds.extend(_safe_line(l) for l in _lines(text))
        cmds.append("@")

    block("description", "description")
    block("taste", "taste")
    block("playlist", "playlist")
    kw = _one(v["extra"])
    if v["extra_text"].strip():
        if not kw or not kw[0].isalpha():
            problems.append("An extra description needs a keyword that starts with a letter.")
        else:
            block("extra " + kw, "extra_text")
    elif kw:
        problems.append("The extra description has a keyword but no text.")
    if len(cmds) > MAX_COMMANDS:
        problems.append("That is more than %d lines to send." % MAX_COMMANDS)
    if not cmds and not problems:
        problems.append("Fill in at least one thing to change.")
    return (cmds if not problems else []), problems


# ---------------------------------------------------------------- the design book
def validate_designs(raw):
    """Saved designs from the settings file, cleaned: [{'name', 'type', 'values'}]."""
    out, seen = [], set()
    if not isinstance(raw, list):
        return out
    for d in raw[:MAX_DESIGNS * 2]:
        if not isinstance(d, dict):
            continue
        name = d.get("name")
        if not isinstance(name, str):
            continue
        name = " ".join("".join(c for c in name if c.isprintable()).split())[:40]
        typ = d.get("type") if d.get("type") in TYPES else "other"
        if not name or (typ, name.lower()) in seen:
            continue
        seen.add((typ, name.lower()))
        out.append({"name": name, "type": typ, "values": clean_values(d.get("values"))})
        if len(out) >= MAX_DESIGNS:
            break
    return out


def save_design(book, name, typ, values):
    """The book with this design added (or replacing the one with the same type and name)."""
    name = " ".join("".join(c for c in str(name) if c.isprintable()).split())[:40]
    if not name:
        raise ValueError("Give the design a name.")
    typ = typ if typ in TYPES else "other"
    v = clean_values(values)
    v["item"] = ""                    # the item word belongs to the moment, not to the design
    new = [d for d in book if not (d["type"] == typ and d["name"].lower() == name.lower())]
    if len(new) >= MAX_DESIGNS:
        raise ValueError("The design book is full (%d designs)." % MAX_DESIGNS)
    new.append({"name": name, "type": typ, "values": v})
    return new


def delete_design(book, typ, name):
    return [d for d in book if not (d["type"] == typ and d["name"].lower() == str(name).lower())]


def by_type(book):
    """[(type, [designs sorted by name])] for the types that have any, in the usual type order."""
    out = []
    for t in TYPES:
        ds = sorted((d for d in book if d["type"] == t), key=lambda d: d["name"].lower())
        if ds:
            out.append((t, ds))
    return out


def parse_parts(text):
    """'neck, chest' -> (['neck', 'chest'], '') ; 'clear' -> ([], '') ; an unknown word -> ([], word)."""
    words = [w for w in re.split(r"[\s,;]+", str(text or "").strip().lower()) if w]
    out = []
    for w in words:
        if w == "clear":
            continue
        if w not in COVER_PARTS:
            return [], w[:20]
        if w not in out:
            out.append(w)
    return out, ""


def build_interface_commands(values):
    """(commands, problems) for the game's own item editor (where you are already 'in the editor').
    Nothing is sent to finish: the person looks at the result and says done."""
    v = clean_values(values)
    problems, cmds = [], []
    it = _one(v["itype"])
    if it:
        match = [t for t in ITEM_TYPES if t.lower() == it.lower()]
        if match:
            cmds.append("type " + match[0])
        else:
            problems.append("The kind of item must be one of: %s." % ", ".join(ITEM_TYPES))
    cost = _one(v["cost"])
    if cost:
        if re.fullmatch(r"\d{1,7}(\.\d{1,2})?", cost) and float(cost) > 0:
            cmds.append("cost " + cost)
        else:
            problems.append("The price must be a number such as 12.50.")
    size = _one(v["size"]).lower()
    if size:
        if size in ("large", "small"):
            cmds.append("size " + size)
        else:
            problems.append("Size is large, small or blank.")
    count = _one(v["count"])
    if count:
        if count.isascii() and count.isdigit() and 0 < int(count) <= 99:
            word = {"food": "bites", "drink": "drinks"}.get(it.lower(), "uses")
            cmds.append("%s %s" % (word, count))
        else:
            problems.append("Bites / drinks / uses must be a number from 1 to 99.")
    for key, word in (("names", "names"), ("shortstring", "short"), ("longstring", "long"), ("wear", "wear")):
        t = _one(v[key])
        if t:
            cmds.append(word + " " + t)
    layer = _one(v["layer"])
    if layer:
        if layer in list("012345"):
            cmds.append("layer " + layer)
        else:
            problems.append("The layer must be 0 to 5.")
    for key, word in (("cover", "cover"), ("zips", "zip")):
        t = _one(v[key])
        if t:
            parts, bad = parse_parts(t)
            if bad:
                problems.append("%s: %s is not a body part." % (key.capitalize(), bad))
            else:
                cmds.append(word + " clear")
                cmds.extend("%s %s" % (word, p) for p in parts)

    def block(word, key):
        text = v[key].strip()
        if text:
            cmds.append(word)
            cmds.extend(_safe_line(l) for l in _lines(text))
            cmds.append("@")
    block("descedit", "description")
    block("taste", "taste")
    block("playlist", "playlist")
    if len(cmds) > MAX_COMMANDS:
        problems.append("That is more than %d lines to send." % MAX_COMMANDS)
    if not cmds and not problems:
        problems.append("Fill in at least one thing to change.")
    return (cmds if not problems else []), problems


def summary(text, width=40):
    """A one-line description of a longer text, for a list of fields: 'first words... (3 lines)'."""
    t = str(text or "").replace("\\n", "\n")
    lines = [l for l in t.split("\n") if l.strip()]
    if not lines:
        return "(empty)"
    first = " ".join(lines[0].split())
    more = " (+%d lines)" % (len(lines) - 1) if len(lines) > 1 else ""
    room = max(8, width - len(more))
    return (first if len(first) <= room else first[:room - 3] + "...") + more
