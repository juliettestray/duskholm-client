"""Import triggers and aliases from a Mudlet package (.xml, or an .mpackage zip that holds one).

Like the MUSHclient importer, nothing in the file is ever run: it is read as plain XML (a file that declares entities is
refused), every rule that comes out is re-checked by our own validators, and anything that could send commands to the
game arrives switched OFF for the person to look over. Mudlet scripts are Lua and are never run; the one thing read from
them is the plain shape "send(text, matches[n], text)", which is how most small Mudlet aliases and triggers are written.
Everything else that cannot be carried over is listed in the report instead of being dropped silently.

`parse(data)` returns the same dict as mushimport.parse (world is always None: a Mudlet package has no world in it).
"""
import io
import re
import xml.etree.ElementTree as ET
import zipfile

import triggers as T
from mushimport import ImportProblem, MAX_BYTES, NAME_MAX, colour, _snippet, _yes

# Mudlet's pattern types (regexCodePropertyList)
P_SUBSTRING, P_REGEX, P_START, P_EXACT, P_LUA, P_SPACER, P_COLOUR, P_PROMPT = range(8)
_TYPE_NAME = {P_LUA: "a Lua function", P_SPACER: "a line spacer", P_COLOUR: "a colour pattern", P_PROMPT: "a prompt"}
_SPECIAL = set("*?^$")


def zip_xml(data):
    """The XML bytes inside an .mpackage (a zip), or None when `data` is not one."""
    if bytes(data[:4]) != b"PK\x03\x04":
        return None
    try:
        z = zipfile.ZipFile(io.BytesIO(bytes(data)))
    except (zipfile.BadZipFile, OSError):
        return None
    for info in z.infolist():
        if info.filename.lower().endswith(".xml") and 0 < info.file_size <= MAX_BYTES:
            with z.open(info) as f:
                return f.read(MAX_BYTES + 1)
    return None


def _load(data):
    if isinstance(data, str):
        data = re.sub(r"^<\?xml[^>]*\?>", "", data.lstrip("﻿")).encode("utf-8")
    if not isinstance(data, (bytes, bytearray)):
        raise ImportProblem("That is not a file I can read.")
    inner = zip_xml(data)
    if inner is not None:
        data = inner
    if len(data) > MAX_BYTES:
        raise ImportProblem("That file is too big (over %d MB)." % (MAX_BYTES // 1_000_000))
    low = bytes(data).lower()
    if b"<!entity" in low or b"<!doctype" in low and b"[" in low.split(b"<!doctype", 1)[1][:200].split(b">", 1)[0]:
        raise ImportProblem("That file declares XML entities, which I do not read.")
    try:
        root = ET.fromstring(bytes(data))
    except ET.ParseError as e:
        raise ImportProblem("That does not read as XML (%s)." % str(e)[:60])
    if root.tag != "MudletPackage":
        raise ImportProblem("That is not a Mudlet package (it should start with <MudletPackage>).")
    return root


# ---- the little Lua we understand: send("text" .. matches[2] .. "more") ---------------------------------------------
_TERM = re.compile(r"""\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|matches\[(\d+)\])\s*""")
_SEND = re.compile(r"^send\((.*?)(?:\s*,\s*(?:true|false))?\)\s*;?$")
_BOILER = re.compile(r"^local\s+\w+\s*=\s*matches\[\d+\](?:\s+or\s+\"\")?\s*;?$")


def _unlua(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            if i + 1 >= len(s) or s[i + 1] not in "\\\"'":
                return None
            out.append(s[i + 1])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _lua_sends(script, ref):
    """The commands a script sends when it is nothing but send() lines, as text in our syntax; None when it is anything else.
    `ref(n)` says what matches[n] becomes (or None when it cannot be said)."""
    cmds = []
    for line in (script or "").replace("\r", "").split("\n"):
        line = line.strip()
        if not line or line.startswith("--") or _BOILER.match(line):
            continue
        m = _SEND.match(line)
        if not m:
            return None
        arg, pos, parts = m.group(1), 0, []
        while pos < len(arg):
            t = _TERM.match(arg, pos)
            if not t:
                return None
            if t.group(3) is not None:
                r = ref(int(t.group(3)))
                if r is None:
                    return None
                parts.append(r)
            else:
                text = _unlua(t.group(1) if t.group(1) is not None else t.group(2))
                if text is None:
                    return None
                parts.append(text.replace("%", "%%"))
            pos = t.end()
            if pos < len(arg):
                if not arg.startswith("..", pos):
                    return None
                pos += 2
        if not parts:
            return None
        cmds.append("".join(parts))
    return cmds or None


def _command_text(text):
    """A Mudlet command box in our syntax: lines and ';;' become ';' separated commands, '%' stays literal."""
    t = (text or "").replace("\r", "")
    lines = []
    for l in t.split("\n"):
        lines.extend(x.strip() for x in l.split(";;"))
    return ";".join(x for x in lines if x).replace("%", "%%")


def _chunks(text, limit):
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


def _text(el, tag):
    c = el.find(tag)
    return (c.text or "") if c is not None and c.text else ""


# ---- triggers -------------------------------------------------------------------------------------------------------
def _pattern(text, kind):
    """(mode, pattern) for one Mudlet pattern, or None."""
    if not text.strip():
        return None
    special = any(ch in _SPECIAL for ch in text)
    if kind == P_REGEX:
        return "regex", text
    if kind == P_SUBSTRING:
        return ("regex", re.escape(text)) if special else ("plain", text)
    if kind == P_START:
        return ("regex", "^" + re.escape(text)) if special else ("plain", "^" + text)
    if kind == P_EXACT:
        return ("regex", "^" + re.escape(text) + "$") if special else ("plain", "^" + text + "$")
    return None


def _convert_trigger(el, world_name, used_names, active):
    """([trigger dicts], reason | None, [warnings])."""
    warns = []
    name = (_text(el, "name")).strip()
    texts = [(s.text or "") for s in el.findall("./regexCodeList/string")]
    kinds = []
    for i in el.findall("./regexCodePropertyList/integer"):
        try:
            kinds.append(int((i.text or "0").strip()))
        except ValueError:
            kinds.append(0)
    kinds += [P_SUBSTRING] * (len(texts) - len(kinds))
    shown = name if name and name != "New trigger" else (_snippet(texts[0], False)[:30] if texts else "trigger")
    if _yes(el.get("isMultiline")):
        return [], "it matches over several lines, which the trigger engine cannot", warns
    if _yes(el.get("isFilterTrigger")):
        warns.append("%s: a filter trigger works as an ordinary one here" % shown)
    pats, left = [], []
    for text, kind in zip(texts, kinds):
        p = _pattern(text, kind)
        if p is None:
            if text.strip() or kind in _TYPE_NAME:
                left.append(_TYPE_NAME.get(kind, "an empty pattern"))
            continue
        pats.append(p)
    if left:
        warns.append("%s: %s pattern%s left out" % (shown, ", ".join(sorted(set(left))), "" if len(left) == 1 else "s"))
    if not pats:
        return [], "it only has %s" % (", ".join(sorted(set(left))) or "no patterns"), warns
    actions = []
    if _yes(el.get("isColorizerTrigger")):
        fg, bg = colour(_text(el, "mFgColor")), colour(_text(el, "mBgColor"))
        if bg == "#000000":
            bg = None
        if fg or bg:
            actions.append({"type": "highlight", "fg": fg, "bg": bg, "bold": False, "scope": "match"})
    cmd = _command_text(_text(el, "mCommand"))
    if cmd:
        parts = _chunks(cmd, T.MAX_TEXT)
        if parts is None:
            warns.append("%s: a command longer than %d characters was left out" % (shown, T.MAX_TEXT))
        else:
            actions.extend({"type": "send", "text": p, "echo": True} for p in parts)
    script = _text(el, "script").strip()
    if script:
        sent = _lua_sends(script, lambda n: "%0" if n == 1 else ("%%%d" % (n - 1) if 2 <= n <= 10 else None))
        if sent is None:
            warns.append("%s: its Lua script is not run" % shown)
        else:
            for c in sent:
                for p in (_chunks(c, T.MAX_TEXT) or []):
                    actions.append({"type": "send", "text": p, "echo": True})
    if _yes(el.get("isSoundTrigger")) and _text(el, "mSoundFile").strip():
        actions.append({"type": "beep"})
        warns.append("%s: a sound file became a beep" % shown)
    if not actions:
        if script:
            return [], "it only runs a Lua script", warns
        return [], "it sends and colours nothing", warns
    out = []
    for mode, pattern in pats:
        base = name if name and name != "New trigger" else _snippet(pattern, mode == "regex") or shown
        label, n = base[:NAME_MAX].strip() or "trigger", 2
        stem = label
        while label.lower() in used_names:
            suffix = " (%d)" % n
            label = stem[:NAME_MAX - len(suffix)] + suffix
            n += 1
        used_names.add(label.lower())
        acts = [dict(a) for a in actions]
        if mode == "regex" and _yes(el.get("isPerlSlashGOption")):
            for a in acts:
                if a["type"] == "highlight":
                    a["scope"] = "all"
        t = {"name": label, "enabled": active and _yes(el.get("isActive")), "mode": mode, "pattern": pattern,
             "ignore_case": False, "priority": 0, "stop": False, "actions": acts[:T.MAX_ACTIONS]}
        if world_name:
            t.update({"global": False, "world": world_name})
        out.append(t)
    return out, None, warns


# ---- aliases --------------------------------------------------------------------------------------------------------
_W = r"[A-Za-z0-9_!?.+\-]{1,24}"
_TEXT_CAP = r"\((?:\.\*|\.\+|\.\*\?|\.\+\?)\)"
_WORD_CAP = r"\((?:\\S\+|\\w\+|\\d\+|\[\^ \]\+)\)"
_SEP = r"(?:\\s\+|\\s| )"
_ALIAS_RX = re.compile(r"^\^?(?P<w>%s(?:%s%s){0,2})(?:(?:\\s\+|\\s\*|\\s| )(?P<c>%s|%s))?\$?$"
                       % (_W, _SEP, _W, _TEXT_CAP, _WORD_CAP))


def _alias_shape(rx):
    """(word, takes_text, capture_is_one_word) when the pattern is one word and perhaps one capture, else None."""
    m = _ALIAS_RX.match(rx.strip())
    if not m:
        return None
    cap = m.group("c")
    return " ".join(re.split(_SEP, m.group("w"))), bool(cap), bool(cap and re.fullmatch(_WORD_CAP, cap))


def _convert_alias(el, world_name, used, active):
    """(alias dict | None, reason | None, warnings)."""
    warns = []
    rx = _text(el, "regex").strip()
    shape = _alias_shape(rx)
    if shape is None:
        return None, "its pattern is more than a word and what follows it", warns
    word, takes, one_word = shape
    if not rx.rstrip().endswith("$") and not takes:
        warns.append("%s: Mudlet matches anything that starts with the word; here it is the word on its own" % word)

    def ref(n):
        if n == 1:
            return (word + " %*") if takes else word
        if n == 2 and takes:
            return "%1" if one_word else "%*"
        return None
    parts = []
    cmd = _command_text(_text(el, "command"))
    if cmd:
        parts.append(cmd)
    script = _text(el, "script").strip()
    if script:
        sent = _lua_sends(script, ref)
        if sent is None:
            warns.append("%s: its Lua script is not run" % word)
        else:
            parts.extend(sent)
    if not parts:
        return None, ("it only runs a Lua script" if script else "it sends nothing"), warns
    body = ";".join(parts)
    if len(body) > T.MAX_ALIAS_BODY:
        return None, "its text is longer than %d characters" % T.MAX_ALIAS_BODY, warns
    key = word.lower()
    if key in used:
        return None, "another alias with the same name came first", warns
    used.add(key)
    out = {"name": word, "enabled": active and _yes(el.get("isActive")), "body": body}
    if world_name:
        out.update({"global": False, "world": world_name})
    return out, None, warns


# ---- the whole file -------------------------------------------------------------------------------------------------
def _walk(parent, leaf, group):
    """(element, active) for every non-folder `leaf` under parent, descending through folders (a switched-off folder switches
    off what is in it)."""
    def go(node, active, depth):
        for ch in list(node):
            if ch.tag not in (leaf, group):
                continue
            if _yes(ch.get("isFolder")) or ch.tag == group:
                if depth < 20:
                    yield from go(ch, active and _yes(ch.get("isActive")), depth + 1)
            else:
                yield ch, active
    yield from go(parent, True, 0)


def parse(data, world_name=None):
    root = _load(data)
    result = {"world": None, "triggers": [], "aliases": [], "skipped": [], "notes": [], "counts": {}, "plugin": False}
    scope = (world_name or "").strip()
    seen_t = seen_a = 0
    used_t, used_a = set(), set()
    for pkg in root.findall("TriggerPackage"):
        for el, active in _walk(pkg, "Trigger", "TriggerGroup"):
            seen_t += 1
            made, reason, warns = _convert_trigger(el, scope, used_t, active)
            result["notes"].extend(warns)
            shown = (_text(el, "name").strip() or (el.findtext("regexCodeList/string") or "?"))[:40]
            if not made:
                result["skipped"].append(("trigger", shown, reason))
                continue
            for raw in made:
                clean, problem = T._validate_trigger(raw)
                if clean is None:
                    result["skipped"].append(("trigger", raw["name"], problem.lower() if problem else "it did not pass the checks"))
                else:
                    result["triggers"].append(clean)
    for pkg in root.findall("AliasPackage"):
        for el, active in _walk(pkg, "Alias", "AliasGroup"):
            seen_a += 1
            raw, reason, warns = _convert_alias(el, scope, used_a, active)
            result["notes"].extend(warns)
            if raw is None:
                result["skipped"].append(("alias", (_text(el, "regex").strip() or _text(el, "name").strip() or "?")[:40], reason))
                continue
            clean = T.validate_alias(raw)
            if clean is None:
                result["skipped"].append(("alias", raw["name"], "it did not pass the checks"))
                continue
            result["aliases"].append(clean)
    other = []
    for pkg_tag, leaf, group, label in (("TimerPackage", "Timer", "TimerGroup", "timer"), ("KeyPackage", "Key", "KeyGroup", "key"),
                                        ("ScriptPackage", "Script", "ScriptGroup", "script"),
                                        ("ActionPackage", "Action", "ActionGroup", "button")):
        n = sum(1 for pkg in root.findall(pkg_tag) for _ in _walk(pkg, leaf, group))
        if n:
            other.append("%d %s%s" % (n, label, "" if n == 1 else "s"))
    if other:
        result["notes"].append("Not imported: %s (only triggers and aliases are read)." % ", ".join(other))
    result["counts"] = {"triggers_seen": seen_t, "aliases_seen": seen_a, "timers": 0, "macros": 0, "keys": 0, "plugins": 0}
    return result
