"""Which fighting lines are about you, and which are other people's (stdlib only, no GUI).

Screen reader mode can skip lines that are not about you while a fight is on, so the lines that
matter are not buried. The game does not say who is a player and who is an NPC, so this makes a
best guess from how the line is written, and the person can correct it:
  * a lone capitalised name ("Bob") is a player; "the goblin" / "a tall man" is an NPC; a name of
    several words ("Sir Bob the Bold") is an NPC unless the multi-word guess is switched off;
  * names the person lists are always players or always NPCs.
Anything that says you / your (or your character's name) is never skipped."""
import re

CATEGORIES = ("pn", "nn", "np", "pp")
CATEGORY_TEXT = {
    "pn": "Other players attacking NPCs",
    "nn": "NPCs fighting NPCs (and lone NPC actions)",
    "np": "NPCs attacking other players",
    "pp": "Players fighting players (and lone player actions)",
}
DEFAULTS = {"skip": {c: False for c in CATEGORIES}, "only_in_fight": True, "multiword_npc": True,
            "players": [], "npcs": [], "always": []}

_VERBS = (
    "hits?|hit|misses|miss|strikes?|struck|slash(?:es)?|slashed|punch(?:es)?|punched|kicks?|kicked|bites?|bit|claws?|clawed|"
    "stabs?|stabbed|shoots?|shot|fires?|fired|swings?|swung|parries|parried|dodges?|dodged|blocks?|blocked|staggers?|staggered|"
    "falls?|fell|collapses?|collapsed|knocks?|knocked|attacks?|attacked|defends?|defended|wounds?|wounded|bleeds?|dies|died|"
    "defeated|grazes?|grazed|pierces?|pierced|smashes|smashed|batters?|battered|slams?|slammed|lunges?|lunged|throws?|threw|"
    "whips?|whipped|cuts?|slices?|sliced|clubs?|clubbed|crushes|crushed|burns?|burned|freezes|froze|shocks?|shocked|"
    "tackles?|tackled|shoves?|shoved|grapples?|grappled|pins?|pinned|slaps?|slapped|rakes?|raked|gores?|gored|mauls?|mauled|"
    "hurls?|hurled|blasts?|blasted|casts?|conjures?|conjured|charges?|charged|retreats?|flees|fled|steps?|stepped"
)
_VERB_RE = re.compile(r"\b(?:%s)\b" % _VERBS, re.I)
_NPC_START = re.compile(r"^(?:the|an?|some|several|two|three|four|five)\s+", re.I)
_PLAYER_WORD = re.compile(r"^[A-Z][a-z'-]{1,23}$")
_CHANNEL = re.compile(r"^\s*(?:\[[^\]]{1,20}\]|\(?[A-Z][a-z'-]+ (?:says?|tells?|asks?|exclaims?|yells?|whispers?|shouts?)\b)", re.I)
_YOU = re.compile(r"\b(?:you|your|yours|yourself)\b", re.I)
_OBJECT = re.compile(r"^[\s,:;-]*((?:(?i:the|an?|some)\s+[^,.!;()\"]+?|[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)*)(?=[\s,.!;()]|$))")


def _names(seq):
    return {n.strip().lower() for n in (seq or []) if isinstance(n, str) and n.strip()}


def clean_settings(raw):
    """Saved settings reduced to what is valid."""
    out = {"skip": dict(DEFAULTS["skip"]), "only_in_fight": True, "multiword_npc": True,
           "players": [], "npcs": [], "always": []}
    if not isinstance(raw, dict):
        return out
    sk = raw.get("skip")
    if isinstance(sk, dict):
        for c in CATEGORIES:
            if isinstance(sk.get(c), bool):
                out["skip"][c] = sk[c]
    for k in ("only_in_fight", "multiword_npc"):
        if isinstance(raw.get(k), bool):
            out[k] = raw[k]
    for k in ("players", "npcs", "always"):
        v = raw.get(k)
        if isinstance(v, list):
            names = []
            for n in v[:60]:
                if isinstance(n, str):
                    n = " ".join("".join(c for c in n if c.isprintable()).split())[:40]
                    if n and n.lower() not in [x.lower() for x in names]:
                        names.append(n)
            out[k] = names
    return out


def parse_names(text):
    """'Bob, Sir Alan; the guard' -> ['Bob', 'Sir Alan', 'the guard']."""
    return clean_settings({"players": re.split(r"[,;\n]+", str(text or ""))})["players"]


def _kind(phrase, cfg, me):
    """'player' or 'npc' for a name as written in a line."""
    p = phrase.strip().strip(".,!;:'\"()")
    low = p.lower()
    if not p:
        return None
    if low in _names(cfg["players"]):
        return "player"
    if low in _names(cfg["npcs"]):
        return "npc"
    if _NPC_START.match(p):
        return "npc"
    if _PLAYER_WORD.match(p):
        return "player"
    if cfg["multiword_npc"] and len(p.split()) > 1:
        return "npc"
    return "player"


def classify(line, cfg=None, me="", in_fight=True):
    """The category of a fighting line that is NOT about you ('pn', 'nn', 'np', 'pp'), or None when it
    should be left alone (about you, not a fight line, chat, or not while fighting)."""
    cfg = cfg or DEFAULTS
    try:
        text = " ".join(str(line or "").split())
        if not text or len(text) > 400:
            return None
        if cfg.get("only_in_fight", True) and not in_fight:
            return None
        if _YOU.search(text) or _CHANNEL.match(text) or "'" in text and re.search(r"\b(?:says?|tells?|asks?)\b", text, re.I):
            return None
        if me and re.search(r"\b%s\b" % re.escape(me), text, re.I):
            return None
        low = text.lower()
        for n in cfg.get("always", []):
            if n.lower() in low:
                return None
        body = text.strip("()[] ")
        m = _VERB_RE.search(body)
        if not m or m.start() == 0:
            return None
        subj = body[:m.start()].strip()
        s_kind = _kind(subj, cfg, me)
        if s_kind is None or len(subj) > 60:
            return None
        o = _OBJECT.match(body[m.end():])
        o_kind = _kind(o.group(1), cfg, me) if o else None
        if o_kind is None:
            return "nn" if s_kind == "npc" else "pp"
        return {("player", "npc"): "pn", ("npc", "npc"): "nn", ("npc", "player"): "np",
                ("player", "player"): "pp"}[(s_kind, o_kind)]
    except Exception:
        return None


def should_skip(line, cfg=None, me="", in_fight=True):
    """True when this line should not be read aloud."""
    cfg = cfg or DEFAULTS
    if not any(cfg.get("skip", {}).values()):
        return False
    cat = classify(line, cfg, me, in_fight)
    return bool(cat and cfg["skip"].get(cat))
