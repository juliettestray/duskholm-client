"""Emoji shortcodes for the client: ':smile:' <-> the emoji character (stdlib only).

Incoming text has :name: turned into the character; outgoing text has characters turned back into
:name: (the game only accepts plain ASCII). Names are the familiar chat shortcodes, plus any emoji's
official Unicode name with underscores (':rolling_on_the_floor_laughing:')."""
import re
import unicodedata

# shortcode -> official Unicode character name
_NAMES = {
    "grinning": "GRINNING FACE", "smile": "SMILING FACE WITH OPEN MOUTH AND SMILING EYES",
    "grin": "GRINNING FACE WITH SMILING EYES", "joy": "FACE WITH TEARS OF JOY",
    "rofl": "ROLLING ON THE FLOOR LAUGHING", "wink": "WINKING FACE",
    "blush": "SMILING FACE WITH SMILING EYES", "heart_eyes": "SMILING FACE WITH HEART-SHAPED EYES",
    "kissing_heart": "FACE THROWING A KISS", "sob": "LOUDLY CRYING FACE", "cry": "CRYING FACE",
    "angry": "ANGRY FACE", "rage": "POUTING FACE", "scream": "FACE SCREAMING IN FEAR",
    "thinking": "THINKING FACE", "neutral_face": "NEUTRAL FACE", "unamused": "UNAMUSED FACE",
    "sweat_smile": "SMILING FACE WITH OPEN MOUTH AND COLD SWEAT",
    "sunglasses": "SMILING FACE WITH SUNGLASSES", "smirk": "SMIRKING FACE",
    "innocent": "SMILING FACE WITH HALO", "skull": "SKULL", "ghost": "GHOST",
    "alien": "EXTRATERRESTRIAL ALIEN", "robot": "ROBOT FACE", "poop": "PILE OF POO",
    "+1": "THUMBS UP SIGN", "thumbsup": "THUMBS UP SIGN", "-1": "THUMBS DOWN SIGN",
    "thumbsdown": "THUMBS DOWN SIGN", "clap": "CLAPPING HANDS SIGN", "wave": "WAVING HAND SIGN",
    "pray": "PERSON WITH FOLDED HANDS", "muscle": "FLEXED BICEPS", "ok_hand": "OK HAND SIGN",
    "raised_hands": "PERSON RAISING BOTH HANDS IN CELEBRATION", "eyes": "EYES",
    "heart": "HEAVY BLACK HEART", "broken_heart": "BROKEN HEART", "sparkling_heart": "SPARKLING HEART",
    "fire": "FIRE", "star": "WHITE MEDIUM STAR", "sparkles": "SPARKLES", "zap": "HIGH VOLTAGE SIGN",
    "boom": "COLLISION SYMBOL", "snowflake": "SNOWFLAKE", "sunny": "BLACK SUN WITH RAYS",
    "cloud": "CLOUD", "umbrella": "UMBRELLA WITH RAIN DROPS", "moon": "CRESCENT MOON",
    "full_moon": "FULL MOON SYMBOL", "new_moon": "NEW MOON SYMBOL",
    "waxing_crescent_moon": "WAXING CRESCENT MOON SYMBOL", "first_quarter_moon": "FIRST QUARTER MOON SYMBOL",
    "waxing_gibbous_moon": "WAXING GIBBOUS MOON SYMBOL", "waning_gibbous_moon": "WANING GIBBOUS MOON SYMBOL",
    "last_quarter_moon": "LAST QUARTER MOON SYMBOL", "waning_crescent_moon": "WANING CRESCENT MOON SYMBOL",
    "dragon": "DRAGON", "wolf": "WOLF FACE", "cat": "CAT FACE", "dog": "DOG FACE", "bat": "BAT",
    "spider": "SPIDER", "rose": "ROSE", "tada": "PARTY POPPER", "gift": "WRAPPED PRESENT",
    "crown": "CROWN", "gem": "GEM STONE", "key": "KEY", "lock": "LOCK", "dagger": "DAGGER KNIFE",
    "crossed_swords": "CROSSED SWORDS", "shield": "SHIELD", "skull_and_crossbones": "SKULL AND CROSSBONES",
    "warning": "WARNING SIGN", "x": "CROSS MARK", "white_check_mark": "WHITE HEAVY CHECK MARK",
    "heavy_check_mark": "HEAVY CHECK MARK", "question": "BLACK QUESTION MARK ORNAMENT",
    "exclamation": "HEAVY EXCLAMATION MARK SYMBOL", "100": "HUNDRED POINTS SYMBOL",
    "beer": "BEER MUG", "wine_glass": "WINE GLASS", "coffee": "HOT BEVERAGE", "pizza": "SLICE OF PIZZA",
    "cake": "SHORTCAKE", "apple": "RED APPLE", "zzz": "SLEEPING SYMBOL", "bulb": "ELECTRIC LIGHT BULB",
    "bell": "BELL", "book": "OPEN BOOK", "scroll": "SCROLL", "moneybag": "MONEY BAG",
    "dollar": "BANKNOTE WITH DOLLAR SIGN", "crystal_ball": "CRYSTAL BALL", "candle": "CANDLE",
    "hourglass": "HOURGLASS", "rocket": "ROCKET",
}

# the blocks emoji live in (so that ':space:' or ':a:' never turn into ordinary characters)
_RANGES = ((0x1F300, 0x1FAFF), (0x2600, 0x27BF), (0x1F000, 0x1F2FF), (0x2B00, 0x2BFF), (0x2300, 0x23FF),
           (0x2190, 0x21FF), (0x2900, 0x297F), (0x3030, 0x3030), (0x303D, 0x303D), (0x00A9, 0x00AE))
_SKIP = {0x200D, 0xFE0F, 0xFE0E, 0x20E3}            # joiners and variation selectors: dropped on the way out
_MAX_NAME = 48
_CODE = re.compile(r":([A-Za-z0-9_+\-]{1,%d}):" % _MAX_NAME)


def _is_emoji(ch):
    o = ord(ch)
    return any(a <= o <= b for a, b in _RANGES)


def _build():
    fwd, rev = {}, {}
    for code, uname in _NAMES.items():
        try:
            ch = unicodedata.lookup(uname)
        except KeyError:
            continue
        fwd[code] = ch
        rev.setdefault(ch, code)                     # the first (primary) name wins
    return fwd, rev


_FWD, _REV = _build()


def lookup(name):
    """The emoji called `name` (without colons), or None."""
    try:
        name = str(name).strip().lower()
    except Exception:
        return None
    if not name or len(name) > _MAX_NAME:
        return None
    if name in _FWD:
        return _FWD[name]
    try:
        ch = unicodedata.lookup(name.replace("_", " "))
    except (KeyError, ValueError):
        return None
    return ch if len(ch) == 1 and _is_emoji(ch) else None


def name_of(ch):
    """':name:' style short name for one emoji character, or None."""
    if len(ch) != 1 or not _is_emoji(ch):
        return None
    if ch in _REV:
        return _REV[ch]
    try:
        return unicodedata.name(ch).lower().replace(" ", "_").replace("-", "_")
    except ValueError:
        return None


def expand(text):
    """':name:' -> emoji, for every name that is one."""
    if not isinstance(text, str) or ":" not in text:
        return text
    return _CODE.sub(lambda m: lookup(m.group(1)) or m.group(0), text)


def shorten(text):
    """emoji -> ':name:' (joiners and variation selectors are dropped); everything else is kept."""
    if not isinstance(text, str) or text.isascii():
        return text
    out = []
    for ch in text:
        if ord(ch) in _SKIP:
            continue
        n = name_of(ch) if ord(ch) > 0x7F else None
        out.append(":%s:" % n if n else ch)
    return "".join(out)
