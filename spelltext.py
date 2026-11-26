"""Which of the spell checker's complaints to show. Pure text in, ranges out (no Tk): the checker itself is passed in, so a
test can use a stand-in.

A flagged word is left alone when it is in the game's own words, in your dictionary, in the words you told it to ignore
(or, in the input box, words you have typed to the game before), when it is an acronym, has digits in it, sits in a link, or
follows `/`, `@`, `%` or `#`. In the input box a line is only checked when it reads like prose: three or more words, or it
starts with a talking command (say, emote, tell, text...), so `east` and `get sword` are not underlined."""
import re

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.U)
PROSE_STARTS = frozenset("say emote pose ooc tell reply whisper shout yell text sayto ' \" : ;".split())
PROSE_WORDS = 3
MAX_LINES = 400


def split_words(line):
    return [(m.start(), m.end(), m.group()) for m in WORD_RE.finditer(line)]


def reads_like_prose(line):
    """True when a typed line is worth checking: it starts with a talking command or quote, or has enough words."""
    s = line.lstrip()
    if not s or s.startswith("/"):
        return False
    first = s.split(None, 1)[0].lower()
    if first in PROSE_STARTS or s[0] in "'\":;":
        return True
    return len(split_words(s)) >= PROSE_WORDS


def history_words(lines):
    """The lower-case words in lines the player has already sent to the game."""
    out = set()
    for ln in lines:
        for _a, _b, w in split_words(ln):
            out.add(w.casefold())
    return out


def _skip(word, before, allowed):
    if word.casefold() in allowed or "'" in word and word.replace("’", "'").casefold() in allowed:
        return True
    if len(word) >= 2 and word.isupper():
        return True                                          # OOC, GMCP: an acronym
    return bool(before) and before in "/@%#"


def find_problems(engine, text, allowed=frozenset(), prose_only=False):
    """[(start, end, kind)] in `text` (str indices) that deserve an underline."""
    if engine is None or not text.strip():
        return []
    lines = text.split("\n")[:MAX_LINES]
    spans = []                                               # (offset of the line, line)
    pos = 0
    for ln in lines:
        spans.append((pos, ln))
        pos += len(ln) + 1
    checked, dead = [], []
    for off, ln in spans:
        ok = reads_like_prose(ln) if prose_only else bool(ln.strip())
        checked.append(ln if ok else " " * len(ln))
        for m in URL_RE.finditer(ln):
            dead.append((off + m.start(), off + m.end()))
    body = "\n".join(checked)
    out = []
    for a, b, kind in engine.check(body):
        word = text[a:b]
        if any(x <= a and b <= y for x, y in dead):
            continue
        if kind == "spelling" and _skip(word, text[a - 1:a] if a else "", allowed):
            continue
        if kind == "spelling" and not WORD_RE.fullmatch(word.replace("’", "'")):
            continue                                         # something with digits or symbols in it
        out.append((a, b, kind))
    return out
