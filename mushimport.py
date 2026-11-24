"""Import triggers and aliases from a MUSHclient world (.MCL), plugin or trigger-list XML file.

Nothing in the file is ever run: it is read as plain XML (a file that declares entities is refused), every trigger and
alias that comes out is re-checked by our own validators, and anything that could send commands to the game arrives
switched OFF for the person to look over. What cannot be carried over (scripts, notepad and variable targets,
multi-line matching, timers ...) is listed in the report instead of being dropped silently.

`parse(data)` returns a dict:
  world     {"name", "host", "port", "tls"} or None      the world the file describes
  triggers  [our trigger dicts]                          each tied to that world (global False)
  aliases   [our alias dicts]
  skipped   [(kind, label, reason)]                      what could not be imported, and why
  notes     [str]                                        things that came across approximately
  counts    {"triggers_seen", "aliases_seen", "timers", "macros", "keys", "plugins", ...}
"""
import re
import xml.etree.ElementTree as ET

import triggers as T

MAX_BYTES = 5_000_000
NAME_MAX = T.MAX_NAME

# MUSHclient's "send to" numbers
SEND_WORLD, SEND_COMMAND, SEND_OUTPUT, SEND_STATUS, SEND_EXECUTE = 0, 1, 2, 3, 10
_SEND_WHERE = {1: "the command window", 4: "a notepad", 5: "a notepad", 6: "a notepad", 7: "the log file",
               8: "a notepad", 9: "a variable", 11: "the speedwalk", 12: "a script", 13: "a script", 14: "a script"}

# the 16 custom colours a fresh MUSHclient world starts with: (text, background)
DEFAULT_CUSTOM = {
    1: ("#FF8080", "black"), 2: ("#FFFF80", "black"), 3: ("#80FF80", "black"), 4: ("#80FFFF", "black"),
    5: ("#0080FF", "black"), 6: ("#FF80C0", "black"), 7: ("red", "black"), 8: ("#0080C0", "black"),
    9: ("magenta", "black"), 10: ("#804040", "black"), 11: ("#FF8040", "black"), 12: ("teal", "black"),
    13: ("#004080", "black"), 14: ("#FF0080", "black"), 15: ("green", "black"), 16: ("blue", "black")}

_CSS = dict(
    aliceblue="f0f8ff", antiquewhite="faebd7", aqua="00ffff", aquamarine="7fffd4", azure="f0ffff", beige="f5f5dc",
    bisque="ffe4c4", black="000000", blanchedalmond="ffebcd", blue="0000ff", blueviolet="8a2be2", brown="a52a2a",
    burlywood="deb887", cadetblue="5f9ea0", chartreuse="7fff00", chocolate="d2691e", coral="ff7f50",
    cornflowerblue="6495ed", cornsilk="fff8dc", crimson="dc143c", cyan="00ffff", darkblue="00008b", darkcyan="008b8b",
    darkgoldenrod="b8860b", darkgray="a9a9a9", darkgreen="006400", darkgrey="a9a9a9", darkkhaki="bdb76b",
    darkmagenta="8b008b", darkolivegreen="556b2f", darkorange="ff8c00", darkorchid="9932cc", darkred="8b0000",
    darksalmon="e9967a", darkseagreen="8fbc8f", darkslateblue="483d8b", darkslategray="2f4f4f", darkslategrey="2f4f4f",
    darkturquoise="00ced1", darkviolet="9400d3", deeppink="ff1493", deepskyblue="00bfff", dimgray="696969",
    dimgrey="696969", dodgerblue="1e90ff", firebrick="b22222", floralwhite="fffaf0", forestgreen="228b22",
    fuchsia="ff00ff", gainsboro="dcdcdc", ghostwhite="f8f8ff", gold="ffd700", goldenrod="daa520", gray="808080",
    green="008000", greenyellow="adff2f", grey="808080", honeydew="f0fff0", hotpink="ff69b4", indianred="cd5c5c",
    indigo="4b0082", ivory="fffff0", khaki="f0e68c", lavender="e6e6fa", lavenderblush="fff0f5", lawngreen="7cfc00",
    lemonchiffon="fffacd", lightblue="add8e6", lightcoral="f08080", lightcyan="e0ffff", lightgoldenrodyellow="fafad2",
    lightgray="d3d3d3", lightgreen="90ee90", lightgrey="d3d3d3", lightpink="ffb6c1", lightsalmon="ffa07a",
    lightseagreen="20b2aa", lightskyblue="87cefa", lightslategray="778899", lightslategrey="778899",
    lightsteelblue="b0c4de", lightyellow="ffffe0", lime="00ff00", limegreen="32cd32", linen="faf0e6", magenta="ff00ff",
    maroon="800000", mediumaquamarine="66cdaa", mediumblue="0000cd", mediumorchid="ba55d3", mediumpurple="9370db",
    mediumseagreen="3cb371", mediumslateblue="7b68ee", mediumspringgreen="00fa9a", mediumturquoise="48d1cc",
    mediumvioletred="c71585", midnightblue="191970", mintcream="f5fffa", mistyrose="ffe4e1", moccasin="ffe4b5",
    navajowhite="ffdead", navy="000080", oldlace="fdf5e6", olive="808000", olivedrab="6b8e23", orange="ffa500",
    orangered="ff4500", orchid="da70d6", palegoldenrod="eee8aa", palegreen="98fb98", paleturquoise="afeeee",
    palevioletred="db7093", papayawhip="ffefd5", peachpuff="ffdab9", peru="cd853f", pink="ffc0cb", plum="dda0dd",
    powderblue="b0e0e6", purple="800080", red="ff0000", rosybrown="bc8f8f", royalblue="4169e1", saddlebrown="8b4513",
    salmon="fa8072", sandybrown="f4a460", seagreen="2e8b57", seashell="fff5ee", sienna="a0522d", silver="c0c0c0",
    skyblue="87ceeb", slateblue="6a5acd", slategray="708090", slategrey="708090", snow="fffafa", springgreen="00ff7f",
    steelblue="4682b4", tan="d2b48c", teal="008080", thistle="d8bfd8", tomato="ff6347", turquoise="40e0d0",
    violet="ee82ee", wheat="f5deb3", white="ffffff", whitesmoke="f5f5f5", yellow="ffff00", yellowgreen="9acd32")


class ImportProblem(Exception):
    """The file cannot be read as a MUSHclient file; the message says why, for the person."""


def colour(text):
    """'saddlebrown', '#D13000' or 'D13000' -> '#d13000'; None when it is not a colour we know."""
    t = (text or "").strip().lower()
    if not t:
        return None
    if re.fullmatch(r"#[0-9a-f]{6}", t):
        return t
    if t in _CSS:
        return "#" + _CSS[t]
    return None


def _yes(v):
    return str(v or "").strip().lower() in ("y", "yes", "1", "true")


def _int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _load(data):
    if isinstance(data, str):
        data = re.sub(r"^<\?xml[^>]*\?>", "", data.lstrip("﻿")).encode("utf-8")
    if not isinstance(data, (bytes, bytearray)):
        raise ImportProblem("That is not a file I can read.")
    if len(data) > MAX_BYTES:
        raise ImportProblem("That file is too big (over %d MB)." % (MAX_BYTES // 1_000_000))
    low = bytes(data).lower()
    if b"<!entity" in low or b"<!doctype" in low and b"[" in low.split(b"<!doctype", 1)[1][:200].split(b">", 1)[0]:
        raise ImportProblem("That file declares XML entities, which I do not read.")
    try:
        root = ET.fromstring(bytes(data))
    except ET.ParseError as e:
        raise ImportProblem("That does not read as XML (%s)." % str(e)[:60])
    if root.tag != "muclient":
        raise ImportProblem("That is not a MUSHclient file (it should start with <muclient>).")
    return root


def _custom_palette(root):
    pal = dict(DEFAULT_CUSTOM)
    for c in root.findall("./colours/custom/colour"):
        n = _int(c.get("seq"), 0)
        if 1 <= n <= 16:
            pal[n] = (c.get("text") or pal[n][0], c.get("back") or pal[n][1])
    return pal


def _snippet(match, regexp):
    s = match
    if regexp:
        s = re.sub(r"\\(.)", r"\1", s)
        s = re.sub(r"[\^\$\(\)\[\]\{\}\|\*\+\?\.]|\\", "", s)
    s = " ".join(s.split())
    return s


def _send_text(text, warns, where):
    """The <send> text in our syntax: %<name> becomes %{name}, lines become ; separated commands."""
    t = (text or "").replace("\r", "")
    lines = [l.strip() for l in t.split("\n") if l.strip()]
    t = ";".join(lines)
    t = re.sub(r"%<([A-Za-z0-9_]{1,32})>", r"%{\1}", t)
    if "@" in t and re.search(r"@!?[A-Za-z_]", t):
        warns.append("%s uses @variables, which stay as typed" % where)
    return t


def _chunks(text, limit):
    """Cut ;-separated commands into pieces of at most `limit` characters (never inside a command)."""
    out, cur = [], ""
    for part in text.split(";"):
        if len(part) > limit:
            return None
        cand = part if not cur else cur + ";" + part
        if len(cand) > limit:
            out.append(cur)
            cur = part
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out


def _convert_trigger(el, pal, world_name, used_names):
    """(trigger dict | None, reason | None, warnings [str])."""
    warns = []
    match = el.get("match") or ""
    regexp = _yes(el.get("regexp"))
    label = (el.get("name") or el.get("label") or "").strip()
    group = (el.get("group") or "").strip()
    snippet = _snippet(match, regexp)
    shown = label or snippet or match[:30] or "trigger"
    if not match.strip():
        return None, "it has no text to match", warns
    if _int(el.get("lines_to_match"), 1) > 1 or _yes(el.get("multi_line")):
        warns.append("%s: matches over several lines in MUSHclient, one line at a time here" % shown)
    repeat = _yes(el.get("repeat"))
    if repeat and not regexp:
        warns.append("%s: repeat applies to regular expressions only" % shown)
    actions = []
    # the colour change
    cc = _int(el.get("custom_colour"), 0)
    fg = bg = None
    if cc == 17:
        fg, bg = colour(el.get("other_text_colour")), colour(el.get("other_back_colour"))
    elif 1 <= cc <= 16:
        fg, bg = colour(pal[cc][0]), colour(pal[cc][1])
    if bg == "#000000":
        bg = None                                         # MUSHclient's "black" background is no change at all
    bold = _yes(el.get("make_bold"))
    if _yes(el.get("make_italic")) or _yes(el.get("make_underline")):
        warns.append("%s: italic and underline are not carried over" % shown)
    if fg or bg or bold:
        actions.append({"type": "highlight", "fg": fg, "bg": bg, "bold": bold,
                        "scope": "all" if (repeat and regexp) else "match"})       # repeat: colour every match on the line
    if _yes(el.get("omit_from_output")):
        actions.append({"type": "gag"})
    # what it sends
    send = el.find("send")
    text = send.text if send is not None and send.text else ""
    send_to = _int(el.get("send_to"), 0)
    if text.strip():
        if send_to in (SEND_WORLD, SEND_EXECUTE):
            body = _send_text(text, warns, shown)
            parts = _chunks(body, T.MAX_TEXT)
            if parts is None:
                warns.append("%s: a command longer than %d characters was left out" % (shown, T.MAX_TEXT))
            else:
                for p in parts:
                    actions.append({"type": "send", "text": p, "echo": True})
        elif send_to == SEND_OUTPUT:
            actions.append({"type": "note", "text": _send_text(text, warns, shown)[:T.MAX_TEXT]})
        elif send_to == SEND_STATUS:
            actions.append({"type": "status", "text": _send_text(text, warns, shown)[:T.MAX_TEXT]})
        else:
            warns.append("%s: its text goes to %s in MUSHclient, which is not carried over"
                         % (shown, _SEND_WHERE.get(send_to, "somewhere else")))
    sound = (el.get("sound") or "").strip()
    if sound and sound.lower() != "(no sound)":
        actions.append({"type": "beep"})
        warns.append("%s: a sound file became a beep" % shown)
    script = (el.get("script") or "").strip()
    if script:
        warns.append("%s: it calls the script function %s, which is not run" % (shown, script[:30]))
    if not actions:
        if script:
            return None, "it only calls the script function %s" % script[:30], warns
        return None, "it does nothing here (MUSHclient would not colour or send anything either)", warns
    # the pattern: MUSHclient's own wildcards match the whole line
    if regexp:
        mode, pattern = "regex", match
    elif any(ch in match for ch in "^$?"):
        mode = "regex"
        pattern = "^" + "(.*?)".join(re.escape(p) for p in match.split("*")) + "$"
        pattern = re.sub(r"\(\.\*\?\)\$$", "(.*)$", pattern)
    else:
        mode, pattern = "plain", "^" + match + "$"
    name = (label or ("%s: %s" % (group, snippet) if group and snippet else snippet or shown))[:NAME_MAX].strip()
    n, base = 2, name
    while name.lower() in used_names:
        suffix = " (%d)" % n
        name = base[:NAME_MAX - len(suffix)] + suffix
        n += 1
    used_names.add(name.lower())
    out = {"name": name, "enabled": _yes(el.get("enabled")), "mode": mode, "pattern": pattern,
           "ignore_case": _yes(el.get("ignore_case")), "priority": max(-1000, min(1000, 100 - _int(el.get("sequence"), 100))),
           "stop": not _yes(el.get("keep_evaluating")), "actions": actions[:T.MAX_ACTIONS]}
    if world_name:
        out.update({"global": False, "world": world_name})
    return out, None, warns


_WORD = re.compile(r"[A-Za-z0-9_!?.+\-]{1,24}")
_RX_ALIAS = [re.compile(p) for p in (r"^\^?(?P<w>[A-Za-z0-9_!?.+\-]{1,24})\$$",
                                     r"^\^?(?P<w>[A-Za-z0-9_!?.+\-]{1,24})(?:\\s\+|\\s\*| )\((?:\.\*|\.\+|\.\*\?)\)\$?$")]


def _alias_shape(match, regexp):
    """('word', takes_text) when the alias is one word (optionally followed by anything), else None."""
    m = match.strip()
    if regexp:
        for k, rx in enumerate(_RX_ALIAS):
            r = rx.match(m)
            if r:
                return r.group("w"), k == 1
        return None
    if _WORD.fullmatch(m):
        return m, False
    if m.endswith(" *") and _WORD.fullmatch(m[:-2]):
        return m[:-2], True
    return None


def _convert_alias(el, world_name, used):
    warns = []
    match = el.get("match") or ""
    regexp = _yes(el.get("regexp"))
    shape = _alias_shape(match, regexp)
    if shape is None:
        return None, "its pattern is more than a word and what follows it", warns
    word, takes = shape
    send = el.find("send")
    text = send.text if send is not None and send.text else ""
    send_to = _int(el.get("send_to"), 0)
    if send_to not in (SEND_WORLD, SEND_EXECUTE):
        return None, "it sends to %s" % _SEND_WHERE.get(send_to, "somewhere other than the game"), warns
    if (el.get("script") or "").strip():
        warns.append("%s: it calls a script function, which is not run" % word)
    body = _send_text(text, warns, word)
    if not body:
        return None, "it sends nothing", warns
    # MUSHclient: %0 is everything typed (the word too), %1 what the * matched; ours: %* is what follows the word
    whole = (word + " %*") if takes else word
    changed = []

    def sub(m):
        d = m.group(1)
        if d == "0":
            changed.append(d)
            return whole
        if d == "1" and takes:
            return "%*"
        return "" if d.isdigit() and takes is False else m.group(0)
    body2 = re.sub(r"%([0-9])", sub, body)
    if "0" in changed:
        warns.append("%s: MUSHclient's %%0 is everything you type, the word too, so it became '%s'" % (word, whole))
    if len(body2) > T.MAX_ALIAS_BODY:
        return None, "its text is longer than %d characters" % T.MAX_ALIAS_BODY, warns
    key = word.lower()
    if key in used:
        return None, "another alias with the same name came first", warns
    used.add(key)
    out = {"name": word, "enabled": _yes(el.get("enabled")), "body": body2}
    if world_name:
        out.update({"global": False, "world": world_name})
    return out, None, warns


def parse(data, world_name=None):
    """Read a MUSHclient file. `world_name` ties the rules to that world (the file's own world name otherwise)."""
    root = _load(data)
    result = {"world": None, "triggers": [], "aliases": [], "skipped": [], "notes": [], "counts": {}, "plugin": False}
    w = root.find("world")
    if w is not None and w.get("name"):
        host, port = (w.get("site") or "").strip(), _int(w.get("port"), 0)
        result["world"] = {"name": w.get("name").strip(), "host": host, "port": port,
                           "tls": _yes(w.get("use_ssl")), "note": "imported from MUSHclient"}
        if w.get("script_filename"):
            result["notes"].append("The world used the script file %s, which is not run." % w.get("script_filename"))
    scope = (world_name or (result["world"] or {}).get("name") or "").strip()
    pal = _custom_palette(root)
    plug = root.find("plugin")
    if plug is not None:
        result["plugin"] = True
        result["notes"].append("This is a plugin (%s); its script is not run, only its triggers and aliases are read."
                               % (plug.get("name") or "unnamed"))
    seen_t = seen_a = 0
    used_t, used_a = set(), set()
    for el in root.iterfind(".//triggers/trigger"):
        seen_t += 1
        raw, reason, warns = _convert_trigger(el, pal, scope, used_t)
        result["notes"].extend(warns)
        if raw is None:
            result["skipped"].append(("trigger", (el.get("name") or el.get("match") or "?")[:40], reason))
            continue
        clean, problem = T._validate_trigger(raw)
        if clean is None:
            result["skipped"].append(("trigger", raw["name"], problem.lower() if problem else "it did not pass the checks"))
            continue
        result["triggers"].append(clean)
    for el in root.iterfind(".//aliases/alias"):
        seen_a += 1
        raw, reason, warns = _convert_alias(el, scope, used_a)
        result["notes"].extend(warns)
        if raw is None:
            result["skipped"].append(("alias", (el.get("match") or "?")[:40], reason))
            continue
        clean = T.validate_alias(raw)
        if clean is None:
            result["skipped"].append(("alias", raw["name"], "it did not pass the checks"))
            continue
        result["aliases"].append(clean)
    timers = len(root.findall(".//timers/timer"))
    macros = len(root.findall(".//macros/macro"))
    keys = len([k for k in root.findall(".//keypad/key") if k.find("send") is not None and (k.find("send").text or "").strip()])
    includes = [i.get("name") or "" for i in root.findall("include") if _yes(i.get("plugin"))]
    result["counts"] = {"triggers_seen": seen_t, "aliases_seen": seen_a, "timers": timers, "macros": macros,
                        "keys": keys, "plugins": len(includes)}
    if timers:
        result["notes"].append("%d timer%s not imported (use /timer)." % (timers, "" if timers == 1 else "s"))
    if includes:
        result["notes"].append("The world loads %d plugin%s (%s); import each plugin file on its own to read its triggers."
                               % (len(includes), "" if len(includes) == 1 else "s",
                                  ", ".join(x.replace("\\", "/").rsplit("/", 1)[-1] for x in includes)[:120]))
    return result


def sends(trigger):
    return any(isinstance(a, dict) and a.get("type") == "send" for a in trigger.get("actions", []))


def describe(result, limit=8):
    """The report, as lines of text."""
    c = result["counts"]
    lines = []
    w = result["world"]
    if w:
        lines.append("World: %s%s" % (w["name"], " (%s:%s)" % (w["host"], w["port"]) if w["host"] and w["port"] else ""))
    t, a = result["triggers"], result["aliases"]
    hl = sum(1 for x in t if any(y["type"] == "highlight" for y in x["actions"]))
    gag = sum(1 for x in t if any(y["type"] == "gag" for y in x["actions"]))
    snd = sum(1 for x in t if sends(x))
    lines.append("Triggers: %d of %d can be imported (%d colour%s, %d hide%s, %d send%s)."
                 % (len(t), c["triggers_seen"], hl, "" if hl == 1 else "s", gag, "" if gag == 1 else "s", snd,
                    "" if snd == 1 else "s"))
    lines.append("Aliases: %d of %d can be imported." % (len(a), c["aliases_seen"]))
    if c["macros"] or c["keys"]:
        lines.append("Macros and keypad keys (%d, %d with text) are not imported yet." % (c["macros"], c["keys"]))
    skipped = result["skipped"]
    if skipped:
        lines.append("Left out (%d):" % len(skipped))
        for kind, label, why in skipped[:limit]:
            lines.append("  %s '%s': %s" % (kind, label, why))
        if len(skipped) > limit:
            lines.append("  ... and %d more" % (len(skipped) - limit))
    notes = list(dict.fromkeys(result["notes"]))
    for n in notes[:limit]:
        lines.append("Note: " + n)
    if len(notes) > limit:
        lines.append("Note: ... and %d more" % (len(notes) - limit))
    return lines
