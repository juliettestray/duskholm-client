"""Prompt-profile engine for the MUD client's stat bar (stdlib only, no GUI imports).

A *profile* describes how to turn the game's prompt line (the unfinished last line of
output) into a canonical result dict.  The built-in 'haven' kind reproduces the Duskholm
parser exactly; the 'regex' kind lets the user describe any other game with a Python
regular expression plus a list of named groups.

Canonical result (every key always present):
    {'gauges':    [(label, cur, max_or_None), ...],   # gauges[0] is the primary one (HP)
     'counters':  [(label, value), ...],
     'cooldowns': [(label, value), ...],
     'text':      [str, ...],
     'hp':        (cur, max, label) | None}           # legacy shape

Public API: PRESETS, DEFAULT_PRESET, get_preset, validate_profile, compile_profile,
parse_prompt, format_specs, parse_specs, describe_result, check_profile,
gauge_color_role.

Safety limits (user typed regexes run on every prompt, so they are policed):
  * only the last MAX_LINE (500) characters of a line are ever examined;
  * patterns are <= 400 chars, printable only, and must pass the static checker below
    (check_pattern_safety) BEFORE they are compiled;
  * numbers longer than 9 digits are rejected.
The static checker is a heuristic defence against catastrophic backtracking; see its
docstring for the rules and its known limits.  The module keeps no global mutable state
except the functools.lru_cache of compiled patterns.
"""
import copy
import functools
import re

__all__ = ["PRESETS", "DEFAULT_PRESET", "get_preset", "validate_profile", "compile_profile",
           "parse_prompt", "format_specs", "parse_specs", "describe_result", "check_profile",
           "gauge_color_role", "check_pattern_safety"]

MAX_LINE = 500          # characters of the line that are ever examined
MAX_PATTERN = 400
MAX_NAME = 40
MAX_LABEL = 8
MAX_SAMPLE = 300
MAX_ITEMS = 12
MAX_DEPTH = 10          # group nesting
MAX_QUANT_GROUPS = 6
MAX_UNBOUNDED = 12
MAX_BOUND = 99          # largest number allowed inside {m,n}

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,30}$")
_NUM_RE = re.compile(r"-?[0-9]{1,9}")
_LABEL_BAD = set(",=/;")          # would break the spec-string round trip


# ======================================================================================
# Duskholm ("haven") parser -- identical behaviour to duskholm_client.parse_prompt
# ======================================================================================
_HAVEN_RE = re.compile(
    r"\[(\d{1,9})/(\d{1,9})([A-Za-z]{1,4})"          # [350/350DF
    r"((?: -?\d{1,9}[A-Za-z]{1,4})*)"                 #  0ST 0WN 0LG
    r"((?: [A-Za-z]:-?\d{1,9})*)"                     #  M:0 K:0
    r"(?: ?\(([^()]{0,40})\))?\]"                     #  ( )]
    r"(.{0,200})$", re.S)
_HAVEN_START = re.compile(r"\[\d")
_HAVEN_TAG = re.compile(r"\(([^()]+)\)|\[([^\[\]]+)\]")
_HAVEN_CTR = re.compile(r"(-?\d+)([A-Za-z]+)")


def _parse_haven(tail):
    for start in reversed([m.start() for m in _HAVEN_START.finditer(tail)]):
        pm = _HAVEN_RE.match(tail, start)
        if not pm:
            continue
        cur, mx, label, counters, cds, facing, rest = pm.groups()
        facing = (facing or "").strip()
        tags = [(a or b).strip() for a, b in _HAVEN_TAG.findall(rest or "") if (a or b).strip()]
        return _canon([(label, int(cur), int(mx))],
                      [(g[1], int(g[0])) for g in _HAVEN_CTR.findall(counters)],
                      [(c[0], int(c[2:])) for c in cds.split()],
                      ([facing] if facing else []) + tags)
    return None


def _canon(gauges, counters, cooldowns, text):
    hp = None
    for lab, cur, mx in gauges:
        if mx is not None:
            hp = (cur, mx, lab)
            break
    if hp is None and gauges:
        lab, cur, _mx = gauges[0]
        hp = (cur, cur, lab)
    return {"gauges": gauges, "counters": counters, "cooldowns": cooldowns,
            "text": text, "hp": hp}


# ======================================================================================
# Static pattern checker
# ======================================================================================
_ALL = frozenset("dulso")
_QUANT_BRACE = re.compile(r"\{(\d*)(,?)(\d*)\}")
_FLAGS_RE = re.compile(r"\(\?([aiLmsux]*)(?:-([imsx]*))?([:)])")


def _char_class(ch):
    o = ord(ch)
    if 48 <= o <= 57:
        return "d"
    if 65 <= o <= 90:
        return "u"
    if 97 <= o <= 122:
        return "l"
    if o in (9, 10, 11, 12, 13, 32):
        return "s"
    return "o"


def _esc_class(d):
    if d == "d":
        return frozenset("d")
    if d == "s":
        return frozenset("s")
    if d == "w":
        return frozenset("dulo")
    if d in "DSW":
        return _ALL
    if d in "nrtfv":
        return frozenset("s")
    if d.isalnum():
        return _ALL                      # \x41, é ... : be conservative
    return frozenset(_char_class(d))


def _range_class(lo, hi):
    cls = set()
    if hi < lo:
        return cls
    alnum = 0
    for a, b, c in ((48, 57, "d"), (65, 90, "u"), (97, 122, "l")):
        ov = min(hi, b) - max(lo, a) + 1
        if ov > 0:
            alnum += ov
            cls.add(c)
    if hi - lo + 1 > alnum:
        cls.add("o")
    if any(lo <= x <= hi for x in (9, 10, 11, 12, 13, 32)):
        cls.add("s")
    return cls


def _bracket_class(body, neg):
    if neg:
        return _ALL
    cls = set()
    k, n = 0, len(body)
    while k < n:
        ch = body[k]
        if ch == "\\" and k + 1 < n:
            cls |= _esc_class(body[k + 1])
            k += 2
            continue
        if k + 2 < n and body[k + 1] == "-":
            hi = body[k + 2]
            if hi == "\\":
                return _ALL
            cls |= _range_class(ord(ch), ord(hi))
            k += 3
            continue
        cls.add(_char_class(ch))
        k += 1
    return frozenset(cls)


def _narrow(run, cls):
    """A required single character `cls` sits after the repeats in `run`: a repeat can only
    still run into what follows if it could also have consumed that character, so keep just
    the overlap (the characters that could be ambiguous)."""
    return [x for x in (r & cls for r in run) if x]


class _Frame(object):
    __slots__ = ("init", "run", "acc", "alt", "quant", "multi")

    def __init__(self, init):
        self.init = list(init)   # 'run' on entry (what precedes the group)
        self.run = list(init)    # class sets of unbounded atoms that may be adjacent right now
        self.acc = []            # runs of finished alternation branches
        self.alt = False
        self.quant = False
        self.multi = False


def check_pattern_safety(pattern):
    """Static ReDoS heuristic for user-typed patterns.  Returns None when the pattern is
    acceptable, else a short human-readable reason.  Linear in the pattern length, never
    raises, does not need the pattern to be a valid regex.  Rules:
      1. length 1..400, printable characters only (use \\t, not a tab);
      2. no backreferences (\\1..\\9, (?P=name)), no conditionals (?(..)), no lookbehind of
         any kind (?<=, ?<!), no comments (?#), no verbose flag x; group depth <= 10;
      3. numbers inside {m,n} are <= 99;
      4. a group that is repeated with + * {n,} or {n,m>1} may not contain any quantifier or
         alternation (so (a+)+ (a*)* (.*)* (\\d+)+ ({2,})+ (a|aa)+ (a?b)* are all refused;
         (?:ab)+ is fine);
      5. at most 6 quantified groups (any quantifier, including ?) and at most 12
         unbounded quantifiers (+ * {n,}) in total;
      6. unbounded repeats that can run directly after each other (only optional atoms
         between them) may not be able to match the same kind of character: classes are
         approximated as digit / upper / lower / space / other, '.', \\w, \\S, \\D and
         negated classes count as everything.  So \\d+\\d+, \\s*\\d+\\s*\\d+ and .*.* are
         refused but \\d+ \\d+ , [A-Za-z]+\\d+ and \\s*\\d+ are fine.
    Known limits: character classes are approximated (two overlapping classes in the same
    coarse category are always treated as overlapping, which is merely conservative;
    classes that overlap only through unusual escapes such as \\x41 are treated as
    overlapping everything); bounded repeats like (\\d{1,9}){1,9} are not nested-checked
    cost wise beyond rule 4; the checker cannot see overlap between alternation branches
    that are not repeated.  It is a defence in depth: parse_prompt additionally only
    examines the last 500 characters, and the test-suite times every accepted pattern
    against hostile lines."""
    try:
        return _safety(pattern)
    except Exception as e:                       # never raise
        return "pattern could not be analysed (%s)" % type(e).__name__


def _safety(p):
    if not isinstance(p, str):
        return "pattern is not text"
    if not 1 <= len(p) <= MAX_PATTERN:
        return "pattern must be 1-%d characters" % MAX_PATTERN
    if not p.isprintable():
        return "pattern contains control characters"
    ci = re.search(r"\(\?[a-zA-Z]*i", p) is not None

    def norm(cls):
        if ci and ("u" in cls or "l" in cls):
            return frozenset(cls | {"u", "l"})
        return frozenset(cls)

    stack = []
    top = _Frame([])
    pend = [None]            # pending atom: dict(kind, cls, frame, child_run)
    cnt = {"qg": 0, "unb": 0}
    i, n = 0, len(p)

    def flush():
        a = pend[0]
        if a is None:
            return
        pend[0] = None
        if a["kind"] == "char":
            top.run = _narrow(top.run, a["cls"])
        else:
            top.run = list(a["child_run"])

    def conflicts(cls):
        return any(r & cls for r in top.run)

    def apply_q(lo, hi):
        a = pend[0]
        if a is None:
            return None
        pend[0] = None
        multi = hi is None or hi > 1
        unb = hi is None
        top.quant = True
        if multi:
            top.multi = True
        if a["kind"] == "group":
            cnt["qg"] += 1
            if cnt["qg"] > MAX_QUANT_GROUPS:
                return "more than %d quantified groups" % MAX_QUANT_GROUPS
            g = a["frame"]
            if multi and (g.quant or g.alt):
                return "nested quantifier or repeated alternation (catastrophic backtracking risk)"
            if unb:
                cnt["unb"] += 1
                if top.run:
                    return "adjacent unbounded repeats that can match the same text"
                top.run = list(a["child_run"]) + [_ALL]
            elif lo == 0:
                top.run = top.run + list(a["child_run"])
            else:
                top.run = list(a["child_run"])
        else:
            cls = a["cls"]
            if unb:
                cnt["unb"] += 1
            if multi:
                if conflicts(cls):
                    return "adjacent repeats that can match the same text"
                if lo >= 1:
                    top.run = _narrow(top.run, cls)
                top.run.append(cls)
            elif lo >= 1:
                top.run = _narrow(top.run, cls)
        if cnt["unb"] > MAX_UNBOUNDED:
            return "more than %d unbounded quantifiers" % MAX_UNBOUNDED
        return None

    def suffix(j):
        if j < n and p[j] in "?+":
            return j + 1
        return j

    while i < n:
        c = p[i]
        if c == "\\":
            if i + 1 >= n:
                break
            d = p[i + 1]
            if d in "123456789":
                return "backreferences are not allowed"
            i += 2
            if d in "AbBZ":
                continue
            flush()
            pend[0] = {"kind": "char", "cls": norm(_esc_class(d))}
        elif c == "[":
            j = i + 1
            neg = False
            if j < n and p[j] == "^":
                neg = True
                j += 1
            start = j
            if j < n and p[j] == "]":
                j += 1
            while j < n and p[j] != "]":
                if p[j] == "\\":
                    j += 1
                j += 1
            body = p[start:j]
            i = j + 1
            flush()
            pend[0] = {"kind": "char", "cls": norm(_bracket_class(body, neg))}
        elif c == "(":
            flush()
            if p.startswith("(?", i):
                nxt = p[i + 2:i + 3]
                if nxt == "P":
                    if p.startswith("(?P<", i):
                        j = p.find(">", i)
                        if j < 0:
                            return "unterminated group name"
                        i = j + 1
                    elif p.startswith("(?P=", i):
                        return "backreferences are not allowed"
                    else:
                        return "unsupported group syntax"
                elif nxt in ("=", "!"):
                    i += 3
                elif nxt == "<":
                    return "lookbehind is not allowed"
                elif nxt == "(":
                    return "conditional groups are not allowed"
                elif nxt == "#":
                    return "regex comments are not allowed"
                else:
                    fm = _FLAGS_RE.match(p, i)
                    if not fm:
                        return "unsupported group syntax"
                    if "x" in (fm.group(1) or "") or "x" in (fm.group(2) or ""):
                        return "the verbose flag is not allowed"
                    i = fm.end()
                    if fm.group(3) == ")":
                        continue                       # global flags only, no group
            else:
                i += 1
            if len(stack) + 1 >= MAX_DEPTH:
                return "groups nested deeper than %d" % MAX_DEPTH
            stack.append(top)
            top = _Frame(top.run)
        elif c == ")":
            flush()
            if not stack:
                return "unbalanced parenthesis"
            child = top
            top = stack.pop()
            child_run = list(child.run)
            for r in child.acc:
                child_run += r
            top.quant = top.quant or child.quant
            top.multi = top.multi or child.multi
            top.alt = top.alt or child.alt
            pend[0] = {"kind": "group", "frame": child, "child_run": child_run}
            i += 1
        elif c == "|":
            flush()
            top.alt = True
            top.acc.append(top.run)
            top.run = list(top.init)
            i += 1
        elif c in "*+?":
            lo, hi = (1, None) if c == "+" else ((0, None) if c == "*" else (0, 1))
            i = suffix(i + 1)
            bad = apply_q(lo, hi)
            if bad:
                return bad
        elif c == "{":
            m = _QUANT_BRACE.match(p, i)
            if not m or (not m.group(1) and not m.group(2)):
                flush()
                pend[0] = {"kind": "char", "cls": norm(frozenset("o"))}
                i += 1
                continue
            a, comma, b = m.group(1), m.group(2), m.group(3)
            lo = int(a) if a else 0
            if not comma:
                hi = lo
            else:
                hi = int(b) if b else None
            if lo > MAX_BOUND or (hi is not None and hi > MAX_BOUND):
                return "repeat counts above %d are not allowed" % MAX_BOUND
            i = suffix(m.end())
            bad = apply_q(lo, hi)
            if bad:
                return bad
        elif c == ".":
            flush()
            pend[0] = {"kind": "char", "cls": _ALL}
            i += 1
        elif c in "^$":
            i += 1
        else:
            flush()
            pend[0] = {"kind": "char", "cls": norm(frozenset(_char_class(c)))}
            i += 1
    return None


# ======================================================================================
# Compilation (cached)
# ======================================================================================
class _Compiled(object):
    __slots__ = ("kind", "rx")

    def __init__(self, kind, rx):
        self.kind = kind
        self.rx = rx


_HAVEN_COMPILED = _Compiled("haven", None)


def _compile_regex(pattern):
    """(re.Pattern | None, problem | None) -- static check first, then compile."""
    bad = check_pattern_safety(pattern)
    if bad:
        return None, bad
    try:
        rx = re.compile(pattern)
    except Exception as e:                       # re.error, RecursionError, OverflowError...
        return None, "invalid regular expression: %s" % str(e)[:80]
    if not rx.groupindex:
        return None, "pattern needs at least one named group like (?P<hp>\\d+)"
    return rx, None


@functools.lru_cache(maxsize=64)
def _compile_cached(kind, pattern):
    if kind == "haven":
        return _HAVEN_COMPILED
    rx, _bad = _compile_regex(pattern)
    return None if rx is None else _Compiled("regex", rx)


def compile_profile(profile):
    """Opaque compiled object for a profile (cached per (kind, pattern)), or None if the
    profile cannot be used.  Safe on unvalidated input."""
    try:
        if not isinstance(profile, dict):
            return None
        kind = profile.get("kind")
        if kind == "haven":
            return _compile_cached("haven", "")
        pat = profile.get("pattern")
        if kind != "regex" or not isinstance(pat, str):
            return None
        return _compile_cached("regex", pat)
    except Exception:
        return None


# ======================================================================================
# Parsing
# ======================================================================================
def _num(s):
    if not isinstance(s, str):
        return None
    s = s.strip()
    if _NUM_RE.fullmatch(s):
        return int(s)
    return None


def _label_of(v):
    return v.strip()[:MAX_LABEL] if isinstance(v, str) else ""


def _items(profile, key):
    v = profile.get(key)
    if not isinstance(v, list):
        return []
    return [x for x in v[:MAX_ITEMS] if isinstance(x, dict)]


def _extract(m, profile):
    gd = m.groupdict()
    gauges, counters, cooldowns, text = [], [], [], []
    for it in _items(profile, "gauges"):
        g = it.get("cur")
        cur = _num(gd.get(g)) if isinstance(g, str) else None
        if cur is None:
            continue
        mg = it.get("max")
        mx = _num(gd.get(mg)) if isinstance(mg, str) else None
        gauges.append((_label_of(it.get("label")), cur, mx))
    for key, out in (("counters", counters), ("cooldowns", cooldowns)):
        for it in _items(profile, key):
            g = it.get("group")
            val = _num(gd.get(g)) if isinstance(g, str) else None
            if val is not None:
                out.append((_label_of(it.get("label")), val))
    names = profile.get("text")
    if isinstance(names, list):
        for g in names[:MAX_ITEMS]:
            v = gd.get(g) if isinstance(g, str) else None
            if isinstance(v, str) and v.strip():
                text.append(v.strip())
    if not (gauges or counters or cooldowns or text):
        return None
    return _canon(gauges, counters, cooldowns, text)


def parse_prompt(line, profile):
    """Parse the prompt out of `line` using `profile`.  Canonical dict or None.  Only the
    last 500 characters are examined; the last complete prompt wins.  Never raises."""
    try:
        if not isinstance(line, str):
            return None
        comp = compile_profile(profile)
        if comp is None:
            return None
        tail = line[-MAX_LINE:]
        if comp.kind == "haven":
            return _parse_haven(tail)
        for m in reversed(list(comp.rx.finditer(tail))):
            res = _extract(m, profile)
            if res is not None:
                return res
        return None
    except Exception:
        return None


# ======================================================================================
# Validation
# ======================================================================================
def _printable(s):
    return "".join(ch for ch in s if ch.isprintable())


def _label(v):
    if not isinstance(v, str):
        return None
    s = "".join(ch for ch in _printable(v) if ch not in _LABEL_BAD and not ch.isspace())
    return s if 1 <= len(s) <= MAX_LABEL else None


def _group_name(v, groups):
    if isinstance(v, str) and _NAME_RE.match(v) and v in groups:
        return v
    return None


def _validate(d):
    """(profile | None, problem)."""
    if not isinstance(d, dict):
        return None, "profile is not a dictionary"
    raw = d.get("name")
    name = _printable(raw).strip() if isinstance(raw, str) else ""
    if not 1 <= len(name) <= MAX_NAME:
        return None, "name must be 1-%d printable characters" % MAX_NAME
    kind = d.get("kind")
    if kind not in ("haven", "regex"):
        return None, "kind must be 'haven' or 'regex'"
    rs = d.get("sample")
    sample = _printable(rs)[:MAX_SAMPLE] if isinstance(rs, str) else ""
    out = {"name": name, "kind": kind, "pattern": "", "gauges": [], "counters": [],
           "cooldowns": [], "text": [], "sample": sample}
    if kind == "haven":
        return out, ""
    pat = d.get("pattern")
    if not isinstance(pat, str):
        return None, "pattern is missing"
    rx, bad = _compile_regex(pat)
    if rx is None:
        return None, bad
    groups = rx.groupindex
    out["pattern"] = pat
    lst = d.get("gauges")
    for it in (lst if isinstance(lst, list) else []):
        if len(out["gauges"]) >= MAX_ITEMS:
            break
        if not isinstance(it, dict):
            continue
        lab, cur = _label(it.get("label")), _group_name(it.get("cur"), groups)
        mx = it.get("max")
        if mx is None or mx == "":
            mxn = None
        else:
            mxn = _group_name(mx, groups)
            if mxn is None:
                continue
        if lab and cur:
            out["gauges"].append({"label": lab, "cur": cur, "max": mxn})
    for key in ("counters", "cooldowns"):
        lst = d.get(key)
        for it in (lst if isinstance(lst, list) else []):
            if len(out[key]) >= MAX_ITEMS:
                break
            if not isinstance(it, dict):
                continue
            lab, g = _label(it.get("label")), _group_name(it.get("group"), groups)
            if lab and g:
                out[key].append({"label": lab, "group": g})
    lst = d.get("text")
    for g in (lst if isinstance(lst, list) else []):
        if len(out["text"]) >= MAX_ITEMS:
            break
        gn = _group_name(g, groups)
        if gn:
            out["text"].append(gn)
    if not (out["gauges"] or out["counters"] or out["cooldowns"] or out["text"]):
        return None, "no gauge, counter, cooldown or text item refers to a named group of the pattern"
    return out, ""


def validate_profile(d):
    """A fully sanitised NEW profile dict, or None when unusable.  Never raises, never
    mutates its input."""
    try:
        return _validate(d)[0]
    except Exception:
        return None


# ======================================================================================
# Presets
# ======================================================================================
def _mk(name, kind, pattern, gauges, counters, cooldowns, text, sample):
    return {"name": name, "kind": kind, "pattern": pattern, "gauges": gauges,
            "counters": counters, "cooldowns": cooldowns, "text": text, "sample": sample}


def _g(label, cur, mx=None):
    return {"label": label, "cur": cur, "max": mx}


_N = r"-?\d{1,9}"
_P = r"\d{1,9}"

PRESETS = {
    "Haven / Duskholm": _mk("Haven / Duskholm", "haven", "", [], [], [], [],
                            "[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] (Sprawled)"),
    "ROM / Diku classic": _mk(
        "ROM / Diku classic", "regex",
        r"<(?P<hp>%s)(?:/(?P<hpmax>%s))?hp\s{1,3}(?P<mn>%s)(?:/(?P<mnmax>%s))?m\s{1,3}"
        r"(?P<mv>%s)(?:/(?P<mvmax>%s))?mv>" % (_N, _P, _N, _P, _N, _P),
        [_g("HP", "hp", "hpmax"), _g("MN", "mn", "mnmax"), _g("MV", "mv", "mvmax")],
        [], [], [], "<20/100hp 5/50m 90/120mv>"),
    "Simple brackets": _mk(
        "Simple brackets", "regex",
        r"(?i)\[\s{0,3}(?:HP|HEALTH)\s{0,3}:\s{0,3}(?P<hp>%s)\s{0,3}/\s{0,3}(?P<hpmax>%s)"
        r"\s{1,4}(?:MP|MANA)\s{0,3}:\s{0,3}(?P<mp>%s)\s{0,3}/\s{0,3}(?P<mpmax>%s)"
        r"\s{1,4}(?:MV|MOVE)\s{0,3}:\s{0,3}(?P<mv>%s)\s{0,3}/\s{0,3}(?P<mvmax>%s)\s{0,3}\]"
        % (_N, _P, _N, _P, _N, _P),
        [_g("HP", "hp", "hpmax"), _g("MP", "mp", "mpmax"), _g("MV", "mv", "mvmax")],
        [], [], [], "[HP: 120/150  MP: 40/60  MV: 90/90]"),
    "Custom": _mk("Custom", "regex", r"(?P<hp>%s)/(?P<hpmax>%s)" % (_N, _P),
                  [_g("HP", "hp", "hpmax")], [], [], [], "120/150"),
}
DEFAULT_PRESET = "Haven / Duskholm"


def get_preset(name):
    """Deep copy of the named preset (unknown name -> the default)."""
    p = PRESETS.get(name) if isinstance(name, str) else None
    return copy.deepcopy(p if p is not None else PRESETS[DEFAULT_PRESET])


# ======================================================================================
# Editor helpers
# ======================================================================================
def format_specs(profile):
    """Four short strings describing the profile's lists (inverse of parse_specs)."""
    out = {"gauges": "", "counters": "", "cooldowns": "", "text": ""}
    try:
        g = []
        for it in _items(profile, "gauges"):
            s = "%s=%s" % (it.get("label", ""), it.get("cur", ""))
            if it.get("max"):
                s += "/%s" % it["max"]
            g.append(s)
        out["gauges"] = ", ".join(g)
        for key in ("counters", "cooldowns"):
            out[key] = ", ".join("%s=%s" % (it.get("label", ""), it.get("group", ""))
                                 for it in _items(profile, key))
        t = profile.get("text")
        if isinstance(t, list):
            out["text"] = ", ".join(x for x in t[:MAX_ITEMS] if isinstance(x, str))
    except Exception:
        pass
    return out


def _split(s):
    if not isinstance(s, str):
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def _spec_label(s):
    if not s or len(s) > MAX_LABEL or any(ch.isspace() or not ch.isprintable() for ch in s):
        return False
    return not any(ch in _LABEL_BAD for ch in s)


def parse_specs(gauges, counters, cooldowns, text):
    """Spec strings -> ({'gauges','counters','cooldowns','text'} lists, error | None).  A
    field with a bad item comes back empty and the message names the item."""
    res = {"gauges": [], "counters": [], "cooldowns": [], "text": []}
    errs = []

    def pair(item, what):
        if item.count("=") != 1:
            return None
        lab, grp = (x.strip() for x in item.split("="))
        return (lab, grp) if _spec_label(lab) else None

    def field(key, src, title, hint):
        items = _split(src)
        if len(items) > MAX_ITEMS:
            errs.append("%s: more than %d items" % (title, MAX_ITEMS))
            return
        out = []
        for it in items:
            if key == "text":
                if not _NAME_RE.match(it):
                    errs.append("%s: cannot read '%s' (use a group name like %s)" % (title, it, hint))
                    return
                out.append(it)
                continue
            pr = pair(it, key)
            if pr is None:
                errs.append("%s: cannot read '%s' (use %s)" % (title, it, hint))
                return
            lab, rest = pr
            if key == "gauges":
                if rest.count("/") > 1:
                    errs.append("%s: cannot read '%s' (use %s)" % (title, it, hint))
                    return
                cur, _s, mx = (x.strip() for x in rest.partition("/"))
                if not _NAME_RE.match(cur) or (_s and not _NAME_RE.match(mx)):
                    errs.append("%s: bad group name in '%s'" % (title, it))
                    return
                out.append({"label": lab, "cur": cur, "max": mx or None})
            else:
                if not _NAME_RE.match(rest):
                    errs.append("%s: bad group name in '%s'" % (title, it))
                    return
                out.append({"label": lab, "group": rest})
        res[key] = out

    field("gauges", gauges, "Gauges", "LABEL=cur/max, e.g. HP=hp/hpmax")
    field("counters", counters, "Counters", "LABEL=group, e.g. ST=st")
    field("cooldowns", cooldowns, "Cooldowns", "LABEL=group, e.g. M=m")
    field("text", text, "Text", "facing")
    return res, ("; ".join(errs) if errs else None)


def describe_result(result):
    """One-line summary, e.g. 'HP 350/350 | ST 0 WN 0 | M:0 K:0 | North'."""
    try:
        if not isinstance(result, dict):
            return "No prompt"
        parts = []
        g = []
        for lab, cur, mx in result.get("gauges", []):
            g.append("%s %d/%d" % (lab, cur, mx) if mx is not None else "%s %d" % (lab, cur))
        if g:
            parts.append(" ".join(g))
        c = ["%s %d" % (lab, v) for lab, v in result.get("counters", [])]
        if c:
            parts.append(" ".join(c))
        k = ["%s:%d" % (lab, v) for lab, v in result.get("cooldowns", [])]
        if k:
            parts.append(" ".join(k))
        t = [str(x) for x in result.get("text", [])]
        if t:
            parts.append(", ".join(t))
        return " | ".join(parts) if parts else "Empty prompt"
    except Exception:
        return "No prompt"


def check_profile(profile, sample):
    """(ok, message, result_or_None) for the editor's Test line."""
    try:
        prof, problem = _validate(profile)
        if prof is None:
            return False, "Profile problem: %s" % problem, None
        if not isinstance(sample, str) or not sample.strip():
            return False, "Type a sample prompt line to test", None
        res = parse_prompt(sample, prof)
        if res is None:
            return False, "Pattern does not match the sample", None
        return True, "Matched: %s" % describe_result(res), res
    except Exception as e:
        return False, "Profile problem: %s" % type(e).__name__, None


def gauge_color_role(cur, maximum):
    """'good' (>=60%), 'warn' (>=30%) or 'bad'; max None/<=0 -> 'good'."""
    try:
        if maximum is None or maximum <= 0:
            return "good"
        c = max(cur, 0)
        if c * 100 >= 60 * maximum:
            return "good"
        if c * 100 >= 30 * maximum:
            return "warn"
        return "bad"
    except Exception:
        return "good"
