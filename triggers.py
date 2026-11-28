"""Trigger and alias matching engine for the MUD client (stdlib only, no GUI imports).

TRIGGERS are plain JSON-serialisable dicts:
    {'name', 'enabled', 'mode': 'plain'|'regex', 'pattern', 'ignore_case', 'priority',
     'stop', 'actions': [...]}
Actions: highlight / gag / send / beep / note / route (see _clean_action).

PLAIN mode (case-insensitive unless ignore_case is False, matched ANYWHERE in the line):
    '*'  wildcard, any text (also empty); every '*' is a capture %1, %2, ...
    '?'  exactly one character, not captured
    '^'  as the FIRST character anchors to the line start; '$' as the LAST character
         anchors to the line end; everything else is literal.
    Consecutive '*' collapse into one.  At most MAX_STARS (8) wildcards per pattern.
    Wildcards are lazy (shortest text first, left to right) except a wildcard that ends
    the pattern, which takes the rest of the line.  A leading '*' captures from the
    line start.

Why plain mode does NOT run on `re` directly: a regex with k lazy wildcards can need
O(n^(k+1)) steps to FAIL (e.g. 'a*a*a*a*a*a*a*a*b' against 600 'a').  compile_trigger
therefore compiles a plain pattern into literal SEGMENTS (the text between wildcards,
'?' -> '.') and matches them left to right, each found at its earliest position after the
previous one (the last one pinned to the end of line when '$' is used).  Earliest
placement dominates, so this gives exactly the lazy-regex result in O(k * n * len)
time with no backtracking across wildcards.  plain_to_regex() returns the equivalent
regex string (used by the editor and by the tests, which cross-check both
implementations); it also guards against blow-up by treating '*' beyond the eighth as a
literal asterisk.

REGEX mode: Python `re` search; flags only via ignore_case (re.I); the pattern must pass
prompts.check_pattern_safety, compile, and have <= 9 capturing groups.  Only the first
MAX_LINE (600) characters of a line are ever searched.

Captures: %0 whole match, %1..%9, %{name}, %% literal percent; unknown tokens stay
literal.  Commands from a send action are split on ';' BEFORE captures are expanded
(see expand_commands) so text from the game can never inject extra commands.

Public API: validate_trigger, compile_trigger, match_trigger, match_line, expand,
split_commands, expand_commands, plain_to_regex, LoopGuard, validate_alias, find_alias,
expand_alias, migrate_legacy_aliases, check_trigger, describe_actions, PRESETS,
get_presets.
"""
import copy
import functools
import re
import time

import prompts

__all__ = ["validate_trigger", "compile_trigger", "match_trigger", "match_line", "expand",
           "split_commands", "expand_commands", "plain_to_regex", "LoopGuard",
           "validate_alias", "find_alias", "find_alias_line", "expand_alias", "migrate_legacy_aliases",
           "check_trigger", "describe_actions", "PRESETS", "get_presets"]

MAX_LINE = 600
MAX_NAME = 40
MAX_PATTERN = 300
MAX_STARS = 8
MAX_GROUPS = 9
MAX_ACTIONS = 8
MAX_TEXT = 200
MAX_PANE = 24
MAX_COMMANDS = 20
MAX_COMMAND = 200
MAX_ALIAS_NAME = 24
MAX_ALIAS_BODY = 400
MAX_ALIASES = 300
MAX_TRIGGERS = 1500

_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
_ALIAS_WORD = r"[A-Za-z0-9_!?.+\-]{1,24}"
_ALIAS_NAME_RE = re.compile(r"%s(?: %s){0,2}" % (_ALIAS_WORD, _ALIAS_WORD))     # one to three words: "text ywellia"
_CAP_NAME_RE = re.compile(r"[A-Za-z0-9_]{1,32}")
_STARS_RE = re.compile(r"\*+")
_ALIAS_TOKEN_RE = re.compile(r"%[0-9*%]")
_DIGITS = "0123456789"


# ======================================================================================
# Small helpers
# ======================================================================================
def _clean_text(s, maxlen):
    """Strip control characters (spaces are kept) and surrounding whitespace; None unless
    the result is 1..maxlen characters."""
    if not isinstance(s, str) or len(s) > maxlen * 4:
        return None
    t = "".join(ch for ch in s if ch.isprintable()).strip()
    return t if 1 <= len(t) <= maxlen else None


def _bool(v, default):
    return v if isinstance(v, bool) else default


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


# ======================================================================================
# Plain-mode parsing / regex generation
# ======================================================================================
def _parse_plain(pattern, strict):
    """(anchor_start, anchor_end, [segments]) with len(segments) == stars + 1.  In strict
    mode more than MAX_STARS wildcards -> None; otherwise extra '*' become literals."""
    body = pattern
    astart = body.startswith("^")
    if astart:
        body = body[1:]
    aend = body.endswith("$")
    if aend:
        body = body[:-1]
    segs = _STARS_RE.split(body)
    if len(segs) - 1 > MAX_STARS:
        if strict:
            return None
        tail = body
        segs = []
        for _i in range(MAX_STARS):
            m = _STARS_RE.search(tail)
            segs.append(tail[:m.start()])
            tail = tail[m.end():]
        segs.append(tail)                       # remaining '*' are literal text
    return astart, aend, segs


def _seg_regex(seg):
    return "".join("." if ch == "?" else re.escape(ch) for ch in seg)


def plain_to_regex(pattern, ignore_case=True):
    """Regex STRING equivalent to the plain-mode rules (see module docstring).  Group n is
    the n-th '*'.  Start with (?s) / (?is); use re.search.  Never raises (junk -> '(?!)')."""
    try:
        astart, aend, segs = _parse_plain(pattern, False)
    except Exception:
        return "(?!)"
    k = len(segs) - 1
    out = ["(?is)" if ignore_case else "(?s)"]
    if astart:
        out.append("^")
    for i, seg in enumerate(segs):
        if i:
            out.append("(.*)" if (i == k and not seg) else "(.*?)")
        out.append(_seg_regex(seg))
    if aend:
        out.append(r"\Z")
    return "".join(out)


# ======================================================================================
# Compilation (cached)
# ======================================================================================
class _Plain(object):
    __slots__ = ("kind", "astart", "aend", "rx", "lens", "ngroups", "names")

    def __init__(self, astart, aend, segs, ic):
        self.kind = "plain"
        self.astart = astart
        self.aend = aend
        flags = re.S | (re.I if ic else 0)
        self.rx = [re.compile(_seg_regex(s), flags) for s in segs]
        self.lens = [len(s) for s in segs]
        self.ngroups = len(segs) - 1
        self.names = {}


class _Rx(object):
    __slots__ = ("kind", "rx", "ngroups", "names")

    def __init__(self, rx):
        self.kind = "regex"
        self.rx = rx
        self.ngroups = rx.groups
        self.names = dict(rx.groupindex)


def _pattern_ok(p):
    return (isinstance(p, str) and 1 <= len(p) <= MAX_PATTERN and p.isprintable()
            and p.strip() != "")


@functools.lru_cache(maxsize=512)
def _build(mode, pattern, ic):
    """(compiled | None, problem)."""
    if mode == "plain":
        parsed = _parse_plain(pattern, True)
        if parsed is None:
            return None, "Too many wildcards (max %d)" % MAX_STARS
        try:
            return _Plain(parsed[0], parsed[1], parsed[2], ic), ""
        except Exception as e:
            return None, "Invalid pattern: %s" % type(e).__name__
    if mode == "regex":
        bad = prompts.check_pattern_safety(pattern)
        if bad:
            return None, "Unsafe pattern: %s" % bad
        try:
            rx = re.compile(pattern, re.I if ic else 0)
        except Exception as e:                   # re.error, RecursionError, OverflowError
            return None, "Invalid regular expression: %s" % str(e)[:80]
        if rx.groups > MAX_GROUPS:
            return None, "Too many capture groups (max %d)" % MAX_GROUPS
        return _Rx(rx), ""
    return None, "Unknown mode"


def compile_trigger(trigger):
    """Opaque compiled object (cached per (mode, pattern, ignore_case)) or None.  Never
    raises; does not look at 'enabled'."""
    try:
        if not isinstance(trigger, dict):
            return None
        mode = trigger.get("mode")
        pat = trigger.get("pattern")
        if not isinstance(mode, str) or not _pattern_ok(pat):
            return None
        return _build(mode, pat, trigger.get("ignore_case", True) is not False)[0]
    except Exception:
        return None


# ======================================================================================
# Matching
# ======================================================================================
def _plain_match(c, line):
    """(start, end, [captures]) or None -- see the module docstring."""
    n = len(line)
    k = c.ngroups
    rx, lens = c.rx, c.lens
    if k == 0:
        size = lens[0]
        if c.astart and c.aend:
            m = rx[0].match(line, 0) if n == size else None
        elif c.astart:
            m = rx[0].match(line, 0)
        elif c.aend:
            m = rx[0].match(line, n - size) if n >= size else None
        else:
            m = rx[0].search(line)
        return (m.start(), m.end(), []) if m else None
    if c.astart:
        m = rx[0].match(line, 0)
    elif lens[0] == 0:
        m = rx[0].match(line, 0)
    else:
        m = rx[0].search(line)
    if not m:
        return None
    start, pos = m.start(), m.end()
    caps = []
    for i in range(1, k):
        m = rx[i].search(line, pos)
        if not m:
            return None
        caps.append(line[pos:m.start()])
        pos = m.end()
    size = lens[k]
    if size == 0:
        caps.append(line[pos:])
        end = n
    elif c.aend:
        s = n - size
        if s < pos:
            return None
        if not rx[k].match(line, s):
            return None
        caps.append(line[pos:s])
        end = n
    else:
        m = rx[k].search(line, pos)
        if not m:
            return None
        caps.append(line[pos:m.start()])
        end = m.end()
    return start, end, caps


def _result(c, line):
    if c.kind == "plain":
        r = _plain_match(c, line)
        if r is None:
            return None
        start, end, groups = r
        caps = {"0": line[start:end]}
        for i in range(1, 10):
            caps[str(i)] = groups[i - 1] if i <= len(groups) else ""
        return {"start": start, "end": end, "captures": caps}
    m = c.rx.search(line)
    if not m:
        return None
    caps = {"0": m.group(0)}
    for i in range(1, 10):
        caps[str(i)] = (m.group(i) or "") if i <= c.ngroups else ""
    for name in c.names:
        caps[name] = m.group(name) or ""
    return {"start": m.start(), "end": m.end(), "captures": caps}


def match_trigger(trigger, line):
    """None, or {'start', 'end', 'captures': {'0'..'9', named...}}.  Only the first 600
    characters of `line` are searched; disabled triggers never match; never raises."""
    try:
        if not isinstance(line, str) or not isinstance(trigger, dict):
            return None
        if not trigger.get("enabled", True):
            return None
        c = compile_trigger(trigger)
        if c is None:
            return None
        return _result(c, line[:MAX_LINE])
    except Exception:
        return None


def all_spans(trigger, line, limit=100):
    """[(start, end)] for every place the trigger's pattern matches in `line`: a regular expression or a plain text
    without wildcards can match more than once; a pattern with wildcards matches once. Never raises."""
    try:
        c = compile_trigger(trigger)
        if c is None or not isinstance(line, str):
            return []
        line = line[:MAX_LINE]
        if c.kind == "regex":
            return [(m.start(), m.end()) for m in c.rx.finditer(line) if m.end() > m.start()][:limit]
        if c.ngroups == 0 and not c.astart and not c.aend:
            return [(m.start(), m.end()) for m in c.rx[0].finditer(line) if m.end() > m.start()][:limit]
        r = _plain_match(c, line)
        return [(r[0], r[1])] if r else []
    except Exception:
        return []


def sent_spans(trigger, line, limit=200):
    """Like all_spans, for a line I sent: the WHOLE line is searched however long it is (that is where a typo late in
    a long emote sits). A regular expression is run over pieces of at most MAX_LINE characters, cut at spaces."""
    try:
        c = compile_trigger(trigger)
        if c is None or not isinstance(line, str):
            return []
        if c.kind != "regex":
            if c.ngroups == 0 and not c.astart and not c.aend:
                return [(m.start(), m.end()) for m in c.rx[0].finditer(line) if m.end() > m.start()][:limit]
            r = _plain_match(c, line)
            return [(r[0], r[1])] if r and r[1] > r[0] else []
        out, lo, n = [], 0, len(line)
        while lo < n and len(out) < limit:
            hi = min(n, lo + MAX_LINE)
            if hi < n:
                cut = line.rfind(" ", lo + 1, hi)
                if cut > lo:
                    hi = cut
            for m in c.rx.finditer(line, lo, hi):
                if m.end() <= m.start():
                    continue
                if m.end() == hi < n:                   # '$' must mean the end of the line, not of this piece
                    real = c.rx.match(line, m.start())
                    if not real or real.end() != m.end():
                        continue
                out.append((m.start(), m.end()))
            lo = hi
        return out[:limit]
    except Exception:
        return []


def echo_highlights(line, rules):
    """[(start, end, action)]: the colours that rules on what I send put on my echoed line, highest priority first.
    A matching rule with 'stop' ends the run. Never raises."""
    try:
        cand = sorted(((-_priority(t), i, t) for i, t in enumerate(rules)
                       if isinstance(t, dict) and t.get("enabled", True) and isinstance(t.get("actions"), list)),
                      key=lambda x: (x[0], x[1]))
        out = []
        for _p, _i, t in cand:
            spans = sent_spans(t, line)
            if not spans:
                continue
            for a in t["actions"]:
                if a.get("type") != "highlight":
                    continue
                scope = a.get("scope")
                for lo, hi in ([(0, len(line))] if scope == "line" else spans if scope == "all" else spans[:1]):
                    out.append((lo, hi, a))
            if t.get("stop") is True:
                break
        return out
    except Exception:
        return []


def _priority(t):
    p = t.get("priority", 0)
    if not _is_int(p):
        return 0
    return max(-1000, min(1000, p))


def match_line(line, triggers):
    """[(trigger, match_dict), ...] in execution order (priority desc, then list order).
    Disabled/invalid entries are skipped; a matching trigger with stop=True ends the run
    (it is included).  Never raises."""
    try:
        if not isinstance(line, str) or not isinstance(triggers, (list, tuple)):
            return []
        cand = []
        for idx, t in enumerate(triggers):
            try:
                if (isinstance(t, dict) and t.get("enabled", True)
                        and isinstance(t.get("actions"), list) and t["actions"]
                        and compile_trigger(t) is not None):
                    cand.append((-_priority(t), idx, t))
            except Exception:
                continue
        cand.sort(key=lambda x: (x[0], x[1]))
        out = []
        for _p, _i, t in cand:
            m = match_trigger(t, line)
            if m is None:
                continue
            out.append((t, m))
            if t.get("stop") is True:
                break
        return out
    except Exception:
        return []


# ======================================================================================
# Text expansion / command splitting
# ======================================================================================
def _cap(caps, key):
    try:
        v = caps.get(key)
    except Exception:
        return ""
    if v is None:
        return ""
    return v if isinstance(v, str) else str(v)


def expand(text, captures):
    """%0..%9, %{name}, %% ; unknown tokens stay literal; substituted text is not
    re-expanded.  '%10' is %1 followed by '0'."""
    if not isinstance(text, str):
        return ""
    caps = captures if isinstance(captures, dict) else {}
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch != "%" or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        d = text[i + 1]
        if d == "%":
            out.append("%")
            i += 2
        elif d in _DIGITS:
            out.append(_cap(caps, d))
            i += 2
        elif d == "{":
            j = text.find("}", i + 2)
            name = text[i + 2:j] if j >= 0 else ""
            if j >= 0 and _CAP_NAME_RE.fullmatch(name):
                out.append(_cap(caps, name))
                i = j + 1
            else:
                out.append("%")
                i += 1
        else:
            out.append("%")
            i += 1
    return "".join(out)


def _printable(s):
    return "".join(ch for ch in s if ch.isprintable())


def split_commands(text):
    """Split on ';' (';;' is a literal ';'), strip, drop empties, control characters
    removed, <= 20 commands of <= 200 characters."""
    if not isinstance(text, str):
        return []
    text = _printable(text[:MAX_COMMANDS * MAX_COMMAND * 2])
    parts, cur = [], []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == ";":
            if i + 1 < n and text[i + 1] == ";":
                cur.append(";")
                i += 2
                continue
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur))
    out = []
    for p in parts:
        p = p.strip()[:MAX_COMMAND].strip()
        if p:
            out.append(p)
            if len(out) >= MAX_COMMANDS:
                break
    return out


def expand_commands(text, captures):
    """split_commands first, THEN expand each command (so a ';' inside a capture can never
    create a new command), then sanitise each result the same way."""
    out = []
    for cmd in split_commands(text):
        e = _printable(expand(cmd, captures)).strip()[:MAX_COMMAND].strip()
        if e:
            out.append(e)
    return out


# ======================================================================================
# Validation
# ======================================================================================
def _color(v):
    """(ok, value)."""
    if v is None:
        return True, None
    if _is_int(v):
        return (True, v) if 0 <= v <= 15 else (False, None)
    if isinstance(v, str) and _COLOR_RE.fullmatch(v):
        return True, v.lower()
    return False, None


def _clean_action(a):
    if not isinstance(a, dict):
        return None
    t = a.get("type")
    if t == "highlight":
        okf, fg = _color(a.get("fg"))
        okb, bg = _color(a.get("bg"))
        bold = a.get("bold", False)
        scope = a.get("scope", "match")
        if not (okf and okb) or not isinstance(bold, bool) or scope not in ("match", "line", "all"):
            return None
        if fg is None and bg is None and not bold:
            return None
        return {"type": "highlight", "fg": fg, "bg": bg, "bold": bold, "scope": scope}
    if t == "gag":
        return {"type": "gag"}
    if t == "beep":
        return {"type": "beep"}
    if t == "send":
        text = _clean_text(a.get("text"), MAX_TEXT)
        echo = a.get("echo", True)
        if text is None or not isinstance(echo, bool):
            return None
        return {"type": "send", "text": text, "echo": echo}
    if t == "note":
        text = _clean_text(a.get("text"), MAX_TEXT)
        return None if text is None else {"type": "note", "text": text}
    if t == "status":
        text = _clean_text(a.get("text"), MAX_TEXT)
        return None if text is None else {"type": "status", "text": text}
    if t == "speak":
        text = _clean_text(a.get("text"), MAX_TEXT)
        interrupt = a.get("interrupt", False)
        if text is None or not isinstance(interrupt, bool):
            return None
        return {"type": "speak", "text": text, "interrupt": interrupt}
    if t == "silence":
        return {"type": "silence"}
    if t == "route":
        pane = _clean_text(a.get("pane"), MAX_PANE)
        gag = a.get("gag", False)
        once = a.get("once", False)
        mine = a.get("mine", False)
        fmt = a.get("format")
        confirm = a.get("confirm")
        if pane is None or not isinstance(gag, bool) or not isinstance(once, bool) or not isinstance(mine, bool):
            return None
        out = {"type": "route", "pane": pane, "gag": gag}
        if once:
            out["once"] = True               # skip a line this pane was already given (a log the game shows again and again)
        if mine:
            out["mine"] = True               # my own side of a conversation: only while the pane's "show what I send" is on
        if fmt is not None:
            fmt = _clean_text(fmt, MAX_TEXT)  # what the pane gets instead of the line itself: %0-%9 captures, {time}, {name}
            if fmt is not None:
                out["format"] = fmt
        if confirm is not None:
            confirm = _clean_text(confirm, 80)  # for a rule on what I send: the pane gets the line only once the game says this ("Sent.")
            if confirm is not None:
                out["confirm"] = confirm
        return out
    return None


def _world_part(d):
    """{} for a rule that works in every world (the default, and how rules have always been stored);
    {"global": False, "world": name} for one tied to a single world."""
    if d.get("global", True) is not False:
        return {}
    world = _clean_text(d.get("world"), 60)
    if not world:
        return {}
    out = {"global": False, "world": world}
    wid = d.get("world_id")
    if isinstance(wid, str) and re.fullmatch(r"[0-9a-f]{8,32}", wid):       # the saved world's id (see worldids.py)
        out["world_id"] = wid
    return out


def rule_applies(rule, world, world_id=""):
    """True if a trigger/alias is global, or tied to this world. A rule tied by id applies to the world with that id
    (whatever either is called now); otherwise the name is compared, without regard to case."""
    try:
        if rule.get("global", True) is not False:
            return True
        rid = rule.get("world_id")
        if rid and world_id:
            return rid == world_id
        return str(rule.get("world", "")).strip().lower() == str(world or "").strip().lower()
    except Exception:
        return True


def for_world(rules, world, world_id=""):
    """The rules that apply in a world (the same dict objects, in the same order)."""
    return [r for r in rules if isinstance(r, dict) and rule_applies(r, world, world_id)]


def _validate_trigger(d):
    """(clean | None, problem)."""
    if not isinstance(d, dict):
        return None, "Trigger is not a dictionary"
    name = _clean_text(d.get("name"), MAX_NAME)
    if name is None:
        return None, "Name must be 1-%d printable characters" % MAX_NAME
    mode = d.get("mode")
    if not isinstance(mode, str) or mode not in ("plain", "regex"):
        return None, "Unknown mode (use 'plain' or 'regex')"
    pat = d.get("pattern")
    if not _pattern_ok(pat):
        return None, "Pattern must be 1-%d printable characters" % MAX_PATTERN
    ic = _bool(d.get("ignore_case", True), True)
    comp, problem = _build(mode, pat, ic)
    if comp is None:
        return None, problem
    prio = d.get("priority", 0)
    prio = max(-1000, min(1000, prio)) if _is_int(prio) else 0
    raw = d.get("actions")
    acts = []
    if isinstance(raw, list):
        for a in raw[:64]:
            ca = _clean_action(a)
            if ca is not None:
                acts.append(ca)
                if len(acts) >= MAX_ACTIONS:
                    break
    if not acts:
        return None, "No valid actions"
    out = {"name": name, "enabled": _bool(d.get("enabled", True), False), "mode": mode,
           "pattern": pat, "ignore_case": ic, "priority": prio,
           "stop": _bool(d.get("stop", False), False), "actions": acts}
    if d.get("when") == "sent":
        out["when"] = "sent"                 # matched against the commands I send, not against what the game shows
    out.update(_world_part(d))
    return out, ""


def validate_trigger(d):
    """Sanitised NEW trigger dict or None.  Never raises, never mutates `d`."""
    try:
        return _validate_trigger(d)[0]
    except Exception:
        return None


# ======================================================================================
# Loop guard
# ======================================================================================
class LoopGuard(object):
    """Rate limiter for trigger sends.  begin_line() at the start of every received line;
    allow(key) before every send.  Denied attempts are not counted."""
    _MAX_KEYS = 256

    def __init__(self, max_per_second=20, max_per_line=8):
        self.max_per_second = max_per_second
        self.max_per_line = max_per_line
        self._hits = {}
        self._line = 0

    def begin_line(self):
        self._line = 0

    def allow(self, key, now=None):
        if now is None:
            now = time.monotonic()
        try:
            hash(key)
        except TypeError:
            key = repr(key)[:80]
        if self._line >= self.max_per_line:
            return False
        if len(self._hits) > self._MAX_KEYS:
            self._purge(now)
        hits = [t for t in self._hits.get(key, ()) if 0 <= now - t < 1.0]
        if len(hits) >= self.max_per_second:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        self._line += 1
        return True

    def _purge(self, now):
        for k in [k for k, v in self._hits.items() if not v or not (0 <= now - v[-1] < 1.0)]:
            del self._hits[k]
        if len(self._hits) > 4 * self._MAX_KEYS:        # pathological: keep the newest
            keep = sorted(self._hits.items(), key=lambda kv: kv[1][-1])[-self._MAX_KEYS:]
            self._hits = dict(keep)


# ======================================================================================
# Aliases
# ======================================================================================
def _validate_alias(d):
    if not isinstance(d, dict):
        return None
    name = d.get("name")
    if not isinstance(name, str) or len(name) > 64:
        return None
    name = " ".join(name.split())
    if not _ALIAS_NAME_RE.fullmatch(name):
        return None
    body = _clean_text(d.get("body"), MAX_ALIAS_BODY)
    if body is None:
        return None
    out = {"name": name, "enabled": _bool(d.get("enabled", True), False), "body": body}
    out.update(_world_part(d))
    return out


def validate_alias(d):
    """Sanitised NEW alias dict {'name', 'enabled', 'body'} or None.  Never raises."""
    try:
        return _validate_alias(d)
    except Exception:
        return None


def find_alias(word, aliases):
    """First ENABLED one-word alias whose name equals `word` case-insensitively (the
    original list entry), else None.  Invalid entries are skipped."""
    try:
        if not isinstance(word, str) or not isinstance(aliases, (list, tuple)):
            return None
        w = word.strip().lower()
        if not w or " " in w:
            return None
        for a in aliases:
            v = validate_alias(a)
            if v is not None and v["enabled"] and v["name"].lower() == w:
                return a
        return None
    except Exception:
        return None


def find_alias_line(line, aliases):
    """(alias, rest of the line) for the ENABLED alias whose name is the first word(s) of
    `line` (case-insensitive, whole words); the alias with the most words wins, then the
    first in the list.  (None, line) when there is none.  Names of up to three words work:
    'text ywellia' beats 'text'."""
    try:
        if not isinstance(line, str) or not isinstance(aliases, (list, tuple)):
            return None, line
        words = [m for m in re.finditer(r"\S+", line[:MAX_LINE])][:3]
        if not words:
            return None, line
        low = [m.group().lower() for m in words]
        best, best_n = None, 0
        for a in aliases:
            v = validate_alias(a)
            if v is None or not v["enabled"]:
                continue
            parts = v["name"].lower().split(" ")
            n = len(parts)
            if n > best_n and n <= len(low) and low[:n] == parts:
                best, best_n = a, n
        if best is None:
            return None, line
        return best, line[words[best_n - 1].end():]
    except Exception:
        return None, line


def _alias_sub(piece, words, args):
    out = []
    i, n = 0, len(piece)
    while i < n:
        ch = piece[i]
        if ch == "%" and i + 1 < n:
            d = piece[i + 1]
            if d == "%":
                out.append("%")
                i += 2
                continue
            if d == "*" or d == "0":
                out.append(args)
                i += 2
                continue
            if d in _DIGITS:
                k = int(d)
                out.append(words[k - 1] if k <= len(words) else "")
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def expand_alias(alias, args_text):
    """List of commands for a typed alias.  %1..%9 words, %* / %0 all arguments, %% a
    percent.  The body is split BEFORE substituting, so ';' inside arguments never creates
    commands.  Legacy: a body with no % token gets ' ' + args appended to its last
    command."""
    try:
        v = validate_alias(alias)
        if v is None:
            return []
        args = _printable(args_text).strip() if isinstance(args_text, str) else ""
        args = args[:MAX_ALIAS_BODY * 2]
        words = args.split()
        pieces = split_commands(v["body"])
        if not pieces:
            return []
        if not _ALIAS_TOKEN_RE.search(v["body"]):
            if args:
                pieces[-1] = pieces[-1] + " " + args
            subbed = pieces
        else:
            subbed = [_alias_sub(p, words, args) for p in pieces]
        out = []
        for p in subbed:
            p = _printable(p).strip()[:MAX_COMMAND].strip()
            if p:
                out.append(p)
        return out[:MAX_COMMANDS]
    except Exception:
        return []


def migrate_legacy_aliases(d):
    """Old {name: body} dict -> sorted list of valid alias dicts (max 200; names that differ
    only by case keep the first)."""
    try:
        if not isinstance(d, dict):
            return []
        found = []
        for k, v in list(d.items()):
            if isinstance(k, str) and isinstance(v, str):
                a = validate_alias({"name": k, "body": v})
                if a is not None:
                    found.append(a)
        found.sort(key=lambda a: (a["name"].lower(), a["name"]))
        out, seen = [], set()
        for a in found:
            low = a["name"].lower()
            if low in seen:
                continue
            seen.add(low)
            out.append(a)
            if len(out) >= MAX_ALIASES:
                break
        return out
    except Exception:
        return []


# ======================================================================================
# Editor helpers
# ======================================================================================
_ACTION_WORDS = {"highlight": "highlight", "gag": "hide", "send": "send", "beep": "beep",
                 "note": "note", "route": "route", "status": "status line",
                 "speak": "speak", "silence": "silence"}


def describe_actions(trigger):
    """'highlight, hide, send, beep' style summary for list views (never raises)."""
    try:
        acts = trigger.get("actions") if isinstance(trigger, dict) else None
        words = []
        for a in (acts if isinstance(acts, list) else [])[:64]:
            w = _ACTION_WORDS.get(a.get("type")) if isinstance(a, dict) else None
            if w:
                words.append(w)
        return ", ".join(words)
    except Exception:
        return ""


def _short(s, n):
    return s if len(s) <= n else s[:n - 3] + "..."


def check_trigger(trigger, sample_line):
    """(ok, message, matches) for the editor's Test line.  `matches` is a list with the
    match dict on success.  The 'enabled' flag is ignored (you may test a disabled one)."""
    try:
        clean, problem = _validate_trigger(trigger)
        if clean is None:
            return False, problem, []
        if not isinstance(sample_line, str) or not sample_line.strip():
            return False, "Type a sample line to test", []
        probe = dict(clean)
        probe["enabled"] = True
        comp = compile_trigger(probe)
        m = match_trigger(probe, sample_line)
        if comp is None or m is None:
            return False, "Pattern does not match the sample", []
        caps = m["captures"]
        shown = ["%%%d=%s" % (i, _short(caps.get(str(i), ""), 40))
                 for i in range(1, comp.ngroups + 1)]
        shown += ["%%{%s}=%s" % (n, _short(caps.get(n, ""), 40)) for n in sorted(comp.names)]
        acts = []
        for a in clean["actions"]:
            t = a["type"]
            if t in ("send", "note", "status", "speak"):
                txt = "; ".join(expand_commands(a["text"], caps)) if t == "send" \
                    else expand(a["text"], caps)
                acts.append("%s '%s'" % (_ACTION_WORDS[t], _short(txt, 80)))
            else:
                acts.append(_ACTION_WORDS[t])
        msg = "Matched '%s'" % _short(caps["0"], 60)
        if shown:
            msg += " -> " + " ".join(shown)
        msg += "; actions: " + ", ".join(acts)
        return True, msg, [m]
    except Exception as e:
        return False, "Trigger problem: %s" % type(e).__name__, []


# ======================================================================================
# Presets (all disabled)
# ======================================================================================
def _preset(name, pattern, actions, **kw):
    d = {"name": name, "enabled": False, "mode": "plain", "pattern": pattern,
         "ignore_case": True, "priority": 0, "stop": False, "actions": actions}
    d.update(kw)
    return validate_trigger(d)


PRESETS = [p for p in (
    _preset("Highlight tells", "tells you",
            [{"type": "highlight", "fg": "#ffd700", "bg": None, "bold": True,
              "scope": "line"}]),
    _preset("Highlight OOC", "^[OOC]*",
            [{"type": "highlight", "fg": "#9aa0a6", "bg": None, "bold": False,
              "scope": "line"}]),
    _preset("Beep on tell", "* tells you, '*'",
            [{"type": "beep"},
             {"type": "note", "text": "Tell from %1: %2"}]),
    _preset("Auto-reply to tell", "^* tells you, '*'$",
            [{"type": "send", "text": "reply thanks, I will answer soon", "echo": True}],
            priority=-10),
) if p is not None]


def get_presets():
    """Deep copy of PRESETS (safe to edit)."""
    return copy.deepcopy(PRESETS)


def copy_name(name, taken, limit=MAX_NAME, words=True):
    """A name for a clone of `name` that none of `taken` (compared ignoring case) already uses, at most `limit`
    characters: 'Name copy', 'Name copy 2', ... With words=False (an alias, whose name is what you type) it is
    'name2', 'name3', ... instead, so it stays one word."""
    taken = set(str(t).lower() for t in taken)
    n = 1 if words else 2
    while True:
        suffix = ((" copy" if n == 1 else " copy %d" % n) if words else str(n))
        cand = str(name)[:max(1, limit - len(suffix))].rstrip() + suffix
        if cand.lower() not in taken:
            return cand
        n += 1
