#!/usr/bin/env python3
"""
Duskholm telnet client - a small tkinter MUD client for Haven-Duskholm.

Run:   python duskholm_client.py [host [port]]
Needs: Python 3.8+ with tkinter (standard on Windows installers). No other deps.

Speaks what the server speaks (see src/comm.c):
  * plain telnet on 3000, TLS (stunnel) on 3001
  * WILL ECHO from the server = password prompt (input is masked, not echoed/saved)
  * MXP: replies DO to WILL MXP, then honours <color fore=#rrggbb>, </color>,
    <b>/<i>/<u> and the &lt; &gt; &amp; entities; other tags are swallowed
  * ANSI SGR incl. 16 colour, 38;5;N / 48;5;N (xterm-256) and 38;2;r;g;b

Local commands start with "/" (the game has no "/" commands). "//foo" sends "/foo".
Type /help in the client for the list.
"""

import codecs
import colorsys
import copy
import functools
import json
import os
import queue
import re
import socket
import ssl
import sys
import threading
import time
import traceback
import unicodedata
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, messagebox, simpledialog

DEFAULT_HOST = "duskholm.com"
PLAIN_PORT = 3000
TLS_PORT = 3001
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".duskholm_client.json")
MAX_SCROLLBACK_LINES = 20000
KEEPALIVE_SECONDS = 120
MIN_FONT, MAX_FONT = 7, 40
RECONNECT_SECONDS = 30   # wait between automatic reconnect attempts
QUIT_GRACE = 15          # a close this soon after the user sent "quit" is intentional

# telnet
IAC, DONT, DO, WONT, WILL, SB, SE, GA, NOP = 255, 254, 253, 252, 251, 250, 240, 249, 241
OPT_ECHO, OPT_SGA, OPT_MXP = 1, 3, 91

BG = "#101114"
FG = "#c8c8c8"
ECHO_FG = "#6f7a8a"
SYSTEM_FG = "#d7a84a"

ANSI16 = [
    "#000000", "#cd3131", "#0dbc79", "#e5e510", "#2472c8", "#bc3fbc", "#11a8cd", "#e5e5e5",
    "#666666", "#f14c4c", "#23d18b", "#f5f543", "#3b8eea", "#d670d6", "#29b8db", "#ffffff",
]


def xterm_color(n):
    if n < 16:
        return ANSI16[n]
    if n < 232:
        n -= 16
        steps = (0, 95, 135, 175, 215, 255)
        return "#%02x%02x%02x" % (steps[n // 36], steps[(n // 6) % 6], steps[n % 6])
    g = 8 + (n - 232) * 10
    return "#%02x%02x%02x" % (g, g, g)


MXP_NAMED = {
    "black": 0, "red": 1, "green": 2, "yellow": 3, "blue": 4, "magenta": 5, "cyan": 6,
    "white": 7, "gray": 8, "grey": 8,
}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}\Z")


def mxp_color(value):
    value = value.strip().lower()
    if HEX_RE.match(value):
        return value
    if value in MXP_NAMED:
        return MXP_NAMED[value]          # a palette reference, so skins can recolour it
    return None


# =========================================================================
# Themes / skins
# =========================================================================
# A theme is a flat dict of colours plus a few style hints. The game's colours reach us as
# palette *references* (ANSI colour 0-15), so changing the palette or skin recolours text that
# is already in the scrollback. Colours the game sends as raw RGB / xterm-256 stay as sent.
# `min_contrast` then lifts any text colour that would be too dark (or, on light skins, too
# light) against its background, keeping its hue: that is what rescues dark blues and
# "black" text on black, and it applies to every colour the game can send.

COLOR_KEYS = ("bg", "fg", "panel", "panel_edge", "input_bg", "input_fg", "echo", "system",
              "alert", "dim", "select", "button_bg", "button_fg")
RELIEFS = ("flat", "raised", "ridge", "groove", "sunken")
ANSI_NAMES = ("Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White",
              "Bright black", "Bright red", "Bright green", "Bright yellow", "Bright blue",
              "Bright magenta", "Bright cyan", "Bright white")
COLOR_LABELS = {
    "bg": "Background", "fg": "Default text", "panel": "Panels / toolbar",
    "panel_edge": "Panel edges", "input_bg": "Input background", "input_fg": "Input text",
    "echo": "Your typed commands", "system": "Client messages", "alert": "Highlight (stat chips)",
    "dim": "Dimmed text", "select": "Selection", "button_bg": "Button background",
    "button_fg": "Button text",
}


def _hex_ok(v):
    return isinstance(v, str) and bool(HEX_RE.match(v))


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _hex(r, g, b):
    return "#%02x%02x%02x" % (max(0, min(255, int(round(r)))), max(0, min(255, int(round(g)))),
                              max(0, min(255, int(round(b)))))


def rel_luminance(h):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(a, b):
    """WCAG contrast ratio between two #rrggbb colours (1.0 .. 21.0)."""
    la, lb = rel_luminance(a), rel_luminance(b)
    hi, lo = (la, lb) if la >= lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


@functools.lru_cache(maxsize=8192)
def ensure_contrast(fg, bg, ratio):
    """Return fg, or the nearest colour with the same hue/saturation that has at least
    `ratio` contrast against bg (lightening on dark backgrounds, darkening on light ones).
    ratio <= 1 disables the adjustment."""
    if ratio <= 1.0 or contrast_ratio(fg, bg) >= ratio:
        return fg
    r, g, b = _rgb(fg)
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)

    def at(level):
        rr, gg, bb = colorsys.hls_to_rgb(h, level, s)
        return _hex(rr * 255, gg * 255, bb * 255)

    order = (1.0, 0.0) if rel_luminance(bg) < 0.5 else (0.0, 1.0)
    for extreme in order:
        if contrast_ratio(at(extreme), bg) < ratio:
            continue
        near, far = l, extreme            # `near` fails, `far` passes; find the boundary
        for _ in range(24):
            mid = (near + far) / 2.0
            if contrast_ratio(at(mid), bg) >= ratio:
                far = mid
            else:
                near = mid
        return at(far)
    # the ratio is unreachable in either direction (mid-grey background): take the best extreme
    return max((at(0.0), at(1.0)), key=lambda c: contrast_ratio(c, bg))


def _skin(name, **kw):
    base = dict(
        name=name, bg="#101114", fg="#c8c8c8", panel="#1a1c21", panel_edge="#2a2d35",
        input_bg="#1a1c21", input_fg="#e8e8e8", echo="#6f7a8a", system="#d7a84a",
        alert="#e5c07b", dim="#6f7a8a", select="#33466b", button_bg="#2a2d35",
        button_fg="#e8e8e8", relief="flat", min_contrast=4.0, fonts=[], ansi=list(ANSI16),
        blurb="")
    base.update(kw)
    return base


BUILTIN_SKINS = {s["name"]: s for s in (
    _skin("Plain", blurb="Neutral dark. The default."),
    _skin("Plain Light", bg="#fafaf7", fg="#1f2328", panel="#ecece6", panel_edge="#d0d0c8",
          input_bg="#ffffff", input_fg="#111111", echo="#7a7f87", system="#8a5a00",
          alert="#9a5b00", dim="#7b8088", select="#cfe0ff", button_bg="#e2e2da",
          button_fg="#1f2328", min_contrast=4.5,
          ansi=["#000000", "#b3261e", "#1b7f3b", "#8a6100", "#1f4fbf", "#8e2a8e", "#0e6f80",
                "#3a3f46", "#6b7078", "#d32f2f", "#2e9e4f", "#a67c00", "#2f6fe0", "#b04fb0",
                "#1590a5", "#000000"],
          blurb="Light background; the game's white becomes dark text."),
    _skin("Moody", bg="#0b0a10", fg="#b9b4c8", panel="#14121d", panel_edge="#2a2438",
          input_bg="#14121d", input_fg="#d8d2e6", echo="#6e6784", system="#c9a24b",
          alert="#d4a84e", dim="#5f5876", select="#3a2f57", button_bg="#231d33",
          button_fg="#cfc7e6", fonts=["Cascadia Mono", "Consolas"],
          ansi=["#1b1826", "#b83a4b", "#5a9a78", "#c9a24b", "#6c7bd6", "#a45cc4", "#4fb0b8",
                "#c9c4d8", "#4a4560", "#e0566a", "#7fc79b", "#e8c46a", "#8c9cf0", "#c47ee6",
                "#78d3d9", "#f1edf9"],
          blurb="Violet-black, tarnished gold, candlelight and spectral teal."),
    _skin("Retro Phosphor", bg="#020a02", fg="#33ff66", panel="#061406", panel_edge="#124a1e",
          input_bg="#061406", input_fg="#66ff88", echo="#1f8f3a", system="#b6ff4d",
          alert="#e0ff6a", dim="#1f7a35", select="#0f5a24", button_bg="#0b2a10",
          button_fg="#33ff66", relief="ridge",
          fonts=["Perfect DOS VGA 437", "Fixedsys Excelsior 3.01", "Lucida Console", "Consolas"],
          ansi=["#0f4a1c", "#ff6b4a", "#33ff66", "#d4ff4a", "#3fb8a0", "#9be6b4", "#4de6d0",
                "#a8ffbd", "#2e8f48", "#ff9966", "#66ff99", "#eaff77", "#6fe0c8", "#b8f5c8",
                "#8ffff0", "#e6fff0"],
          blurb="Green-screen CRT. Reds stay warm so warnings still stand out."),
    _skin("Retro DOS", bg="#000000", fg="#aaaaaa", panel="#0000aa", panel_edge="#aaaaaa",
          input_bg="#0000aa", input_fg="#ffffff", echo="#55ffff", system="#ffff55",
          alert="#ffff55", dim="#9999dd", select="#aa00aa", button_bg="#aaaaaa",
          button_fg="#000000", relief="raised", min_contrast=3.0,
          fonts=["Perfect DOS VGA 437", "Fixedsys Excelsior 3.01", "Lucida Console", "Consolas"],
          ansi=["#000000", "#aa0000", "#00aa00", "#aa5500", "#0000aa", "#aa00aa", "#00aaaa",
                "#aaaaaa", "#555555", "#ff5555", "#55ff55", "#ffff55", "#5555ff", "#ff55ff",
                "#55ffff", "#ffffff"],
          blurb="Classic 16-colour VGA, blue panels, chunky buttons."),
)}
DEFAULT_SKIN = "Plain"


def validate_theme(d, base=None):
    """Build a complete, safe theme from untrusted data (a skin file or saved overrides).
    Anything missing or malformed falls back to `base` (default: the Plain skin). Returns
    None if `d` is not a dict. `ansi` may be a full 16-list or a partial {"4": "#rrggbb"}."""
    if not isinstance(d, dict):
        return None
    base = base if isinstance(base, dict) else BUILTIN_SKINS[DEFAULT_SKIN]
    out = dict(base)
    out["ansi"] = list(base["ansi"])
    out["fonts"] = list(base.get("fonts", []))
    for k in COLOR_KEYS:
        v = d.get(k)
        if _hex_ok(v):
            out[k] = v.lower()
    ansi = d.get("ansi")
    if isinstance(ansi, list) and len(ansi) == 16 and all(_hex_ok(c) for c in ansi):
        out["ansi"] = [c.lower() for c in ansi]
    elif isinstance(ansi, dict):
        for k, v in ansi.items():
            if isinstance(k, str) and k.isascii() and k.isdigit() and len(k) < 3 and int(k) < 16 and _hex_ok(v):
                out["ansi"][int(k)] = v.lower()
    mc = d.get("min_contrast")
    if isinstance(mc, (int, float)) and not isinstance(mc, bool) and 1.0 <= mc <= 10.0:
        out["min_contrast"] = float(mc)
    fonts = d.get("fonts")
    if isinstance(fonts, list):
        out["fonts"] = [f.strip() for f in fonts if isinstance(f, str) and 0 < len(f.strip()) < 60][:8]
    if d.get("relief") in RELIEFS:
        out["relief"] = d["relief"]
    name = d.get("name")
    if isinstance(name, str):
        name = "".join(ch for ch in name if ch.isprintable()).strip()[:40]
        if name:
            out["name"] = name
    blurb = d.get("blurb")
    if isinstance(blurb, str):
        out["blurb"] = "".join(ch for ch in blurb if ch.isprintable())[:120]
    return out


_WIN_RESERVED = ({"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)}
                 | {"LPT%d" % i for i in range(1, 10)})


def user_skin_dir():
    return os.path.join(os.path.expanduser("~"), ".duskholm_skins")


def load_user_skins(path=None):
    """Skins from *.json files in the user skin folder. Bad or oversized files are skipped;
    a name that clashes with a built-in or earlier skin gets ' (user)' appended."""
    path = path or user_skin_dir()
    found = {}
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return found
    for fn in names:
        if not fn.lower().endswith(".json"):
            continue
        fp = os.path.join(path, fn)
        try:
            if os.path.getsize(fp) > 65536:
                continue
            with open(fp, "r", encoding="utf-8-sig") as f:      # -sig: Notepad adds a BOM
                raw = json.load(f)
        except (OSError, ValueError, RecursionError, MemoryError):
            continue
        t = validate_theme(raw)
        if t is None or not any(k in raw for k in ("ansi", "bg", "fg")):
            continue
        if not isinstance(raw.get("name"), str) or not t["name"].strip():
            t["name"] = os.path.splitext(fn)[0][:40]
        base_name, n, cand = t["name"][:40], 1, t["name"][:40]
        while cand in BUILTIN_SKINS or cand in found:       # counter suffix: always terminates
            n += 1
            suffix = " (user)" if n == 2 else " (user %d)" % (n - 1)
            cand = base_name[:48 - len(suffix)] + suffix
        t["name"] = cand
        found[cand] = t
    return found


def save_user_skin(theme, path=None):
    """Write a theme to the user skin folder; returns the file path."""
    path = path or user_skin_dir()
    os.makedirs(path, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in theme["name"])
    safe = safe.strip(" .")[:60] or "skin"
    if safe.split(".")[0].strip().upper() in _WIN_RESERVED:
        safe = "skin_" + safe                       # CON, NUL, COM1... are devices, not files
    fp = os.path.join(path, safe + ".json")
    data = {k: theme[k] for k in ("name", "blurb", "relief", "min_contrast", "fonts", "ansi") + COLOR_KEYS
            if k in theme}
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return fp


# The server keeps only printable ASCII from typed lines (comm.c read_from_buffer:
# isascii && isprint) and truncates lines at MAX_INPUT_LENGTH (6000), so anything else
# would vanish silently: pasted smart quotes, em-dashes, accents, tabs. Map them to ASCII.
MAX_LINE = 5990
_TRANSLIT = {
    "‘": "'", "’": "'", "‚": "'", "′": "'", "ʼ": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "–": "-", "−": "-", "—": "--", "―": "--",
    "…": "...", "•": "*", "·": "*",
    "\t": " ", "\r": " ", "\n": " ", " ": " ", " ": " ", " ": " ",
    " ": " ", " ": " ", " ": " ", "　": " ",
    "​": "", "‌": "", "‍": "", "﻿": "",
}


def sanitize_outgoing(line):
    """Returns (clean_line, dropped, truncated): printable ASCII only, tabs/newlines as
    spaces, typographic characters transliterated, accents stripped. `dropped` counts
    characters that could not be represented; `truncated` is True if the line was cut."""
    out, dropped = [], 0
    for ch in line:
        if " " <= ch <= "~":
            out.append(ch)
            continue
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
            continue
        base = "".join(c for c in unicodedata.normalize("NFKD", ch)
                       if not unicodedata.combining(c))
        if base and all(" " <= c <= "~" for c in base):
            out.append(base)
        else:
            dropped += 1
    clean = "".join(out)
    truncated = len(clean) > MAX_LINE
    if truncated:
        clean = clean[:MAX_LINE]
    return clean, dropped, truncated


ENTITIES = {"lt": "<", "gt": ">", "amp": "&", "quot": '"', "apos": "'", "nbsp": " "}
ENTITY_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#")
CSI_PARAM = frozenset("0123456789;:?")
CSI_MAX = 64       # longest CSI parameter list we parse; longer ones are discarded
MAX_TAG = 512      # longest MXP tag body; a '<' with no '>' inside this window is literal
MAX_SB = 4096      # longest telnet subnegotiation we buffer


def entity_text(name):
    """Text for an MXP entity name (without & and ;), or None if it isn't one we know.
    Numeric forms are ASCII-only, bounded, and never yield control characters or surrogates."""
    if name in ENTITIES:
        return ENTITIES[name]
    if name[:1] != "#":
        return None
    body = name[1:]
    try:
        if body[:1] in ("x", "X") and len(body) > 1 and len(body) <= 7 and all(
                ch in "0123456789abcdefABCDEF" for ch in body[1:]):
            cp = int(body[1:], 16)
        elif body and len(body) <= 7 and all(ch in "0123456789" for ch in body):
            cp = int(body)
        else:
            return None
    except ValueError:
        return None
    if cp in (9, 10):
        return chr(cp)
    if cp < 0x20 or 0x7F <= cp <= 0x9F:
        return ""                                  # control characters are never shown
    if cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
        return "�"
    return chr(cp)
ATTR_RE = re.compile(r'([A-Za-z]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))')


# ---- prompt / stat bar ---------------------------------------------------------------
# The game's default prompt template (src/act_info.c do_prompt) renders like
#   [350/350DF 0ST 0WN 0LG M:0 K:0 ( )] (Sprawled)
# i.e. current/max HP plus a label, "<n><LABEL>" counters, "<letter>:<n>" cooldowns
# (M = move timer, K = attack timer), the facing/position in parentheses while fighting
# (blank otherwise), then optional status tags. The labels are literal text in each
# player's template, so they are shown exactly as the game prints them.
_PROMPT_RE = re.compile(
    r"\[(\d{1,9})/(\d{1,9})([A-Za-z]{1,4})"          # [350/350DF
    r"((?: -?\d{1,9}[A-Za-z]{1,4})*)"                 #  0ST 0WN 0LG
    r"((?: [A-Za-z]:-?\d{1,9})*)"                     #  M:0 K:0
    r"(?: ?\(([^()]{0,40})\))?\]"                     #  ( )]
    r"(.{0,200})$", re.S)
_TAG_RE = re.compile(r"\(([^()]+)\)|\[([^\[\]]+)\]")


def parse_prompt(line):
    """Parse the last line of output as a game prompt. Returns None if it isn't one, else
    {'hp': (cur, max, label), 'counters': [(label, n)], 'cooldowns': [(letter, n)],
     'facing': str, 'tags': [str]}."""
    for m in reversed([m.start() for m in re.finditer(r"\[\d", line)]):
        pm = _PROMPT_RE.match(line, m)
        if not pm:
            continue
        cur, mx, label, counters, cds, facing, tail = pm.groups()
        return {
            "hp": (int(cur), int(mx), label),
            "counters": [(g[1], int(g[0])) for g in re.findall(r"(-?\d+)([A-Za-z]+)", counters)],
            "cooldowns": [(c[0], int(c[2:])) for c in cds.split()],
            "facing": (facing or "").strip(),
            "tags": [(a or b).strip() for a, b in _TAG_RE.findall(tail or "") if (a or b).strip()],
        }
    return None


def hp_color(cur, mx, ansi=ANSI16):
    """Same bands the game's own %d prompt code uses for health, in the given palette."""
    pct = 100 if mx <= 0 else (max(cur, 0) * 100) // mx
    if pct >= 80:
        return ansi[2]
    if pct >= 60:
        return ansi[3]
    if pct >= 40:
        return ansi[11]
    if pct >= 20:
        return ansi[1]
    return ansi[9]


class Style:
    """Current text attributes. Immutable-ish: use key() for tag naming."""
    __slots__ = ("fg", "bg", "bold", "italic", "underline", "inverse", "mfg", "mbg", "mb", "mi", "mu")

    def __init__(self):
        self.fg = self.bg = None          # '#rrggbb' or None  (from ANSI)
        self.bold = self.italic = self.underline = self.inverse = False
        self.mfg = self.mbg = None        # MXP <color> override
        self.mb = self.mi = self.mu = 0   # MXP <b>/<i>/<u> nesting depth

    def key(self):
        fg = self.mfg or self.fg
        bg = self.mbg or self.bg
        return (fg, bg, self.bold or self.mb > 0, self.italic or self.mi > 0,
                self.underline or self.mu > 0, self.inverse)


class Terminal:
    """Pure protocol logic: bytes in, events out. No GUI, so it can be tested."""

    def __init__(self, want_mxp=True):
        self.want_mxp = want_mxp
        self.mxp = False
        self.echo_off = False
        self.style = Style()
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._tstate = "data"
        self._cmd = 0
        self._sb = bytearray()
        self._text = bytearray()
        self._pending = ""
        self._us = {}              # options we have agreed to (SGA)
        self._refused = set()      # unknown WILLs we have already answered DONT
        self._refused_do = set()   # DOs we have already answered WONT
        self._mxp_replies = 0
        self._csi_skip = False     # discarding the tail of an over-long CSI sequence
        self._events = []

    # ---- public ------------------------------------------------------
    def feed(self, data):
        """Returns list of events:
        ('text', str, style_key) ('send', bytes) ('echo', bool) ('bell',) ('prompt',)"""
        self._events = []
        for b in data:
            self._telnet_byte(b)
        self._flush_text()
        out, self._events = self._events, []
        return out

    # ---- telnet layer ------------------------------------------------
    def _reply(self, verb, opt):
        self._events.append(("send", bytes([IAC, verb, opt])))

    def _telnet_byte(self, b):
        st = self._tstate
        if st == "data":
            if b == IAC:
                self._tstate = "iac"
            else:
                self._text.append(b)
        elif st == "iac":
            if b == IAC:
                self._text.append(255)
                self._tstate = "data"
            elif b in (WILL, WONT, DO, DONT):
                self._cmd = b
                self._tstate = "opt"
            elif b == SB:
                self._flush_text()      # text before the SB must be parsed in the old mode
                self._sb = bytearray()
                self._tstate = "sb"
            else:
                if b == GA:
                    self._flush_text()
                    self._drop_pending()   # a prompt is complete: nothing may stay withheld
                    self._events.append(("prompt",))
                self._tstate = "data"
        elif st == "opt":
            self._negotiate(self._cmd, b)
            self._tstate = "data"
        elif st == "sb":
            if b == IAC:
                self._tstate = "sb_iac"
            elif len(self._sb) < MAX_SB:
                self._sb.append(b)
            else:
                self._tstate = "data"   # runaway subnegotiation: give up, resume text
        elif st == "sb_iac":
            if b == SE:
                if self._sb[:1] == bytes([OPT_MXP]) and self.want_mxp:
                    self.mxp = True
                    self._mxp_replies = 0
                self._tstate = "data"
            elif b == IAC:
                if len(self._sb) < MAX_SB:
                    self._sb.append(255)
                    self._tstate = "sb"
                else:
                    self._tstate = "data"
            else:
                self._tstate = "data"

    def _negotiate(self, verb, opt):
        """Answer only on a state change (RFC 1143 style), so a server repeating or
        flooding negotiation can never make us reply in a loop."""
        self._flush_text()
        if verb == WILL:
            if opt == OPT_ECHO:
                if not self.echo_off:
                    self.echo_off = True
                    self._events.append(("echo", False))
                    self._reply(DO, opt)
            elif opt == OPT_MXP and self.want_mxp:
                # Re-answer if MXP is still off (e.g. the server re-offers after a restart),
                # but never more than a few times without it being switched on.
                if not self.mxp and self._mxp_replies < 3:
                    self._mxp_replies += 1
                    self._reply(DO, opt)
            elif opt == OPT_SGA:
                if not self._us.get(opt):
                    self._us[opt] = True
                    self._reply(DO, opt)
            elif opt not in self._refused:
                self._refused.add(opt)
                self._reply(DONT, opt)
        elif verb == WONT:
            if opt == OPT_ECHO:
                if self.echo_off:
                    self.echo_off = False
                    self._events.append(("echo", True))
                    self._reply(DONT, opt)
            elif opt == OPT_MXP:
                self.mxp = False
                self._mxp_replies = 0
            elif opt == OPT_SGA:
                self._us.pop(opt, None)
            self._refused.discard(opt)
        elif verb == DO:
            if opt not in self._refused_do:
                self._refused_do.add(opt)
                self._reply(WONT, opt)
        elif verb == DONT:
            self._refused_do.discard(opt)

    def _drop_pending(self):
        """Release whatever text is being withheld waiting for more bytes. A held escape
        sequence is discarded; a held '<' or '&' is shown as the literal text it was."""
        p, self._pending = self._pending, ""
        if p and p[0] != "\x1b":
            self._emit("".join(ch for ch in p if ch >= " " or ch in "\n\t"))

    # ---- text layer --------------------------------------------------
    def _flush_text(self):
        if not self._text:
            return
        chunk = self._decoder.decode(bytes(self._text))
        self._text = bytearray()
        if chunk:
            self._pending += chunk
            self._process()

    def _emit(self, s):
        if s:
            ev = self._events
            key = self.style.key()
            if ev and ev[-1][0] == "text" and ev[-1][2] == key:
                ev[-1] = ("text", ev[-1][1] + s, key)
            else:
                ev.append(("text", s, key))

    def _process(self):
        # Every decision below depends only on the bytes at and after the construct, never
        # on how the stream was chunked, so any split of the input gives identical output.
        # A construct that is still incomplete is left in self._pending; each one has a hard
        # size limit, after which it is treated as plain text (or discarded) instead.
        s = self._pending
        i, n = 0, len(s)
        buf = []
        while i < n:
            c = s[i]
            if self._csi_skip:                  # tail of an over-long CSI: drop up to the final byte
                i += 1
                if c not in CSI_PARAM:
                    self._csi_skip = False
                continue
            if c == "\x1b":
                self._emit("".join(buf)); buf = []
                if i + 1 >= n:
                    break
                nx = s[i + 1]
                if nx == "[":
                    j = i + 2
                    lim = min(n, i + 2 + CSI_MAX)
                    while j < lim and s[j] in CSI_PARAM:
                        j += 1
                    if j - (i + 2) >= CSI_MAX:   # absurdly long parameter list
                        self._csi_skip = True
                        i = j
                        continue
                    if j >= n:
                        break                    # incomplete CSI, wait for more
                    if s[j] == "m":
                        self._sgr(s[i + 2:j])
                    # every other CSI (incl. MXP line modes ESC[6z) is dropped
                    i = j + 1
                elif nx == "\x1b":
                    i += 1                       # first ESC is stray; re-examine the second
                elif "@" <= nx <= "_" or nx == "c":
                    i += 2                       # two-byte escape, ignored
                else:
                    i += 1                       # lone ESC: drop it, keep the next char
            elif c == "<" and self.mxp:
                if i + 1 >= n:
                    self._emit("".join(buf)); buf = []
                    break
                nx = s[i + 1]
                if not (("a" <= nx <= "z") or ("A" <= nx <= "Z") or nx in "/!?"):
                    buf.append(c); i += 1        # '<' not starting a tag ("a < b")
                    continue
                wend = min(n, i + 1 + MAX_TAG)
                end = s.find(">", i + 1, wend)
                nl = s.find("\n", i + 1, wend if end < 0 else end)
                if nl >= 0:
                    buf.append(c); i += 1        # tags never span lines
                elif end >= 0:
                    self._emit("".join(buf)); buf = []
                    self._mxp_tag(s[i + 1:end])
                    i = end + 1
                elif wend - (i + 1) >= MAX_TAG:
                    buf.append(c); i += 1        # over-long: not a tag
                else:
                    self._emit("".join(buf)); buf = []
                    break                        # tag split across packets
            elif c == "&" and self.mxp:
                j = i + 1
                while j < n and j - (i + 1) < 11 and (s[j] in ENTITY_CHARS):
                    j += 1
                nlen = j - (i + 1)
                if j >= n and nlen <= 10:
                    self._emit("".join(buf)); buf = []
                    break                        # entity split across packets
                rep = None
                if j < n and s[j] == ";" and 0 < nlen <= 10:
                    rep = entity_text(s[i + 1:j])
                if rep is None:
                    buf.append(c); i += 1        # not an entity: literal '&'
                else:
                    buf.append(rep)
                    i = j + 1
            elif c == "\a":
                self._emit("".join(buf)); buf = []
                self._events.append(("bell",))
                i += 1
            elif c in "\r\x00":
                i += 1
            elif c < " " and c not in "\n\t":
                i += 1
            else:
                buf.append(c)
                i += 1
        self._emit("".join(buf))
        self._pending = s[i:]

    def _sgr(self, params):
        st = self.style
        parts = re.split(r"[;:]", params) if params else ["0"]
        # ASCII digits only (str.isdigit() accepts things like '²' that int() rejects);
        # empty means 0, anything else unusable becomes -1 and matches no attribute.
        vals = [0 if not p else int(p) if len(p) <= 6 and p.isascii() and p.isdigit() else -1
                for p in parts]
        k = 0
        while k < len(vals):
            v = vals[k]
            if v == 0:
                st.fg = st.bg = None
                st.bold = st.italic = st.underline = st.inverse = False
            elif v == 1: st.bold = True
            elif v == 3: st.italic = True
            elif v == 4: st.underline = True
            elif v == 7: st.inverse = True
            elif v == 22: st.bold = False
            elif v == 23: st.italic = False
            elif v == 24: st.underline = False
            elif v == 27: st.inverse = False
            # colours 0-15 are kept as palette indices (ints); everything else as '#rrggbb'
            elif 30 <= v <= 37: st.fg = v - 30 + (8 if st.bold else 0)
            elif 90 <= v <= 97: st.fg = v - 90 + 8
            elif 40 <= v <= 47: st.bg = v - 40
            elif 100 <= v <= 107: st.bg = v - 100 + 8
            elif v == 39: st.fg = None
            elif v == 49: st.bg = None
            elif v in (38, 48):
                col = None
                if k + 2 < len(vals) and vals[k + 1] == 5:
                    n8 = max(0, min(255, vals[k + 2]))
                    col = n8 if n8 < 16 else xterm_color(n8)
                    k += 2
                elif k + 4 < len(vals) and vals[k + 1] == 2:
                    r, g, b = (max(0, min(255, x)) for x in vals[k + 2:k + 5])
                    col = "#%02x%02x%02x" % (r, g, b)
                    k += 4
                if col:
                    if v == 38: st.fg = col
                    else: st.bg = col
            k += 1

    def _mxp_tag(self, body):
        st = self.style
        body = body.strip()
        if not body:
            return
        closing = body.startswith("/")
        if closing:
            body = body[1:].strip()
        m = re.match(r"([A-Za-z0-9]+)(.*)", body, re.S)
        if not m:
            return
        name, rest = m.group(1).lower(), m.group(2)
        if name == "color" or name == "c":
            if closing:
                st.mfg = st.mbg = None
            else:
                for am in ATTR_RE.finditer(rest):
                    key = am.group(1).lower()
                    val = am.group(2) or am.group(3) or am.group(4) or ""
                    if key in ("fore", "f"): st.mfg = mxp_color(val)
                    elif key in ("back", "b"): st.mbg = mxp_color(val)
                if not ATTR_RE.search(rest):  # <color red>
                    first = rest.split()[0] if rest.split() else ""
                    st.mfg = mxp_color(first)
        elif name in ("b", "bold", "strong"):
            st.mb = max(0, st.mb + (-1 if closing else 1))
        elif name in ("i", "italic", "em"):
            st.mi = max(0, st.mi + (-1 if closing else 1))
        elif name in ("u", "underline"):
            st.mu = max(0, st.mu + (-1 if closing else 1))
        elif name == "br" and not closing:
            self._emit("\n")
        # everything else (send, a, h1.., p, !element, ...) is ignored; text still shows


# =========================================================================
# GUI
# =========================================================================

def clean_settings(cfg):
    """A hand-edited or corrupt settings file must never stop the client from starting."""
    def to_int(v, default, lo, hi):
        try:
            return max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            return default

    cfg["host"] = cfg["host"].strip() if isinstance(cfg.get("host"), str) and cfg["host"].strip() \
        else DEFAULT_HOST
    cfg["port"] = to_int(cfg.get("port"), TLS_PORT, 1, 65535)
    cfg["font_size"] = to_int(cfg.get("font_size"), 11, MIN_FONT, MAX_FONT)
    fam = cfg.get("font_family")
    cfg["font_family"] = fam.strip() if isinstance(fam, str) and fam.strip() and len(fam) < 100 else None
    sk = cfg.get("skin")
    cfg["skin"] = sk.strip()[:60] if isinstance(sk, str) and sk.strip() else DEFAULT_SKIN
    so = cfg.get("skin_overrides")
    cfg["skin_overrides"] = ({k: v for k, v in list(so.items())[:50]
                              if isinstance(k, str) and len(k) < 60 and isinstance(v, dict)}
                             if isinstance(so, dict) else {})
    for k, default in (("tls", True), ("verify", True), ("bell", True), ("keepalive", True),
                       ("auto_reconnect", False), ("statbar", True)):
        if not isinstance(cfg.get(k), bool):
            cfg[k] = default
    al = cfg.get("aliases")
    cfg["aliases"] = {k: v for k, v in al.items() if isinstance(k, str) and isinstance(v, str)
                      and k and " " not in k} if isinstance(al, dict) else {}
    if not isinstance(cfg.get("geometry"), str) or not re.match(r"^\d+x\d+([+-]-?\d+){0,2}$",
                                                                cfg.get("geometry", "")):
        cfg.pop("geometry", None)
    return cfg

# Plain-skin values, kept as module constants for callers/tests that want the defaults.
PANEL = BUILTIN_SKINS[DEFAULT_SKIN]["panel"]
DIM_FG = BUILTIN_SKINS[DEFAULT_SKIN]["dim"]
ALERT_FG = BUILTIN_SKINS[DEFAULT_SKIN]["alert"]


class StatBar(tk.Frame):
    """HP bar plus compact chips, drawn from parse_prompt() results and the current theme."""
    HP_W = 200

    def __init__(self, master, font, bold, theme=None):
        self.theme = theme or BUILTIN_SKINS[DEFAULT_SKIN]
        super().__init__(master, bg=self.theme["panel"])
        self.font, self.bold = font, bold
        self.data = None
        self._pool, self._shown = [], None
        self.canvas = tk.Canvas(self, width=self.HP_W, height=20, bg=self.theme["panel"],
                                highlightthickness=0)
        self.canvas.pack(side="left", padx=(8, 8), pady=3)
        self.chips = tk.Frame(self, bg=self.theme["panel"])
        self.chips.pack(side="left", fill="x")

    def set_theme(self, theme):
        self.theme = theme
        self.configure(bg=theme["panel"])
        self.canvas.configure(bg=theme["panel"])
        self.chips.configure(bg=theme["panel"])
        self._shown = None            # force the chips to be restyled
        self.refresh()

    def specs(self):
        """[(text, colour)] for the chips, in display order (before contrast adjustment)."""
        d, th = self.data, self.theme
        out = []
        if not d:
            return out
        for label, n in d["counters"]:
            out.append(("%s %d" % (label, n), th["alert"] if n else th["dim"]))
        for letter, n in d["cooldowns"]:
            # the game colours these green when ready and red while cooling down
            out.append(("%s:%d" % (letter, n), th["ansi"][9] if n > 0 else th["ansi"][10]))
        if d["facing"]:
            out.append((d["facing"], th["fg"]))
        for t in d["tags"]:
            out.append((t, th["alert"]))
        return out

    def set_data(self, data):
        self.data = data
        self.refresh()

    def refresh(self):
        th = self.theme
        # HP bar
        c = self.canvas
        c.delete("all")
        h = self.font.metrics("linespace") + 6
        txt = "%d/%d %s" % self.data["hp"] if self.data else ""
        w = max(self.HP_W, self.bold.measure(txt) + 28)      # grows with the font
        c.configure(height=h, width=w)
        c.create_rectangle(0, 0, w - 1, h - 1, outline=th["panel_edge"], fill=th["bg"])
        if self.data:
            cur, mx, _label = self.data["hp"]
            frac = 0.0 if mx <= 0 else max(0.0, min(1.0, cur / mx))
            c.create_rectangle(1, 1, 1 + int((w - 3) * frac), h - 2, outline="",
                               fill=hp_color(cur, mx, th["ansi"]))
            # white text with a black outline stays legible over both the fill and the track
            for dx, dy in ((-1, -1), (-1, 1), (1, -1), (1, 1), (0, 1), (0, -1), (1, 0), (-1, 0)):
                c.create_text(w // 2 + dx, h // 2 + dy, text=txt, fill="#000000", font=self.bold)
            c.create_text(w // 2, h // 2, text=txt, fill="#ffffff", font=self.bold)
        # chips (re-laid out only when something changed)
        specs = self.specs()
        key = (tuple(specs), id(self.font), self.font.actual("size"), self.font.actual("family"))
        if key == self._shown:
            return
        self._shown = key
        while len(self._pool) < len(specs):
            self._pool.append(tk.Label(self.chips, bg=th["panel"], font=self.font, padx=6))
        for lbl in self._pool:
            lbl.pack_forget()
        for lbl, (text, fg) in zip(self._pool, specs):
            lbl.configure(text=text, bg=th["panel"], font=self.font,
                          fg=ensure_contrast(fg, th["panel"], th["min_contrast"]))
            lbl.pack(side="left")


class Connection:
    """Socket owner. Reads on a thread, hands events to the GUI through a queue."""

    def __init__(self, q, gen=0):
        self.q = q
        self.gen = gen            # every event is tagged so the GUI can ignore stale ones
        self.sock = None
        self.closing = False
        self._lock = threading.Lock()
        self._out = queue.Queue()  # writes happen on their own thread, never the GUI's
        self._thread = None

    def _put(self, kind, payload=None):
        self.q.put((self.gen, kind, payload))

    def open(self, host, port, use_tls, verify):
        self._thread = threading.Thread(target=self._run, args=(host, port, use_tls, verify),
                                        daemon=True)
        self._thread.start()

    def _register(self, s):
        """Make `s` the live socket so close() can interrupt whatever it is doing. If we were
        cancelled in the meantime, drop it and report False."""
        with self._lock:
            if self.closing:
                try:
                    s.close()
                except OSError:
                    pass
                return False
            self.sock = s
            return True

    def _run(self, host, port, use_tls, verify):
        try:
            s = socket.create_connection((host, port), timeout=12)
            if not self._register(s):
                return
            if use_tls:
                ctx = ssl.create_default_context()
                if not verify:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                # handshake after registering, so Cancel can abort a stalled one
                s = ctx.wrap_socket(s, server_hostname=host, do_handshake_on_connect=False)
                if not self._register(s):
                    return
                s.do_handshake()
            s.settimeout(None)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception as e:  # noqa: BLE001
            if not self.closing:
                self._put("failed", str(e))
            return
        if self.closing:
            return
        threading.Thread(target=self._writer, args=(s,), daemon=True).start()
        self._put("connected")
        reason = "Connection closed by server."
        try:
            while True:
                data = s.recv(8192)
                if not data:
                    break
                self._put("data", data)
        except OSError as e:
            reason = "Connection lost: %s" % e
        if not self.closing:
            self._put("closed", reason)
        self._out.put(None)

    def _writer(self, s):
        while True:
            raw = self._out.get()
            if raw is None:
                return
            try:
                s.sendall(raw)
            except OSError as e:
                if not self.closing:
                    self._put("closed", "Send failed: %s" % e)
                self.close()
                return

    def send(self, raw):
        """Queue bytes for the writer thread. False if there is no live connection."""
        with self._lock:
            ok = self.sock is not None and not self.closing
        if ok:
            self._out.put(raw)
        return ok

    def close(self):
        with self._lock:
            self.closing = True
            s, self.sock = self.sock, None
        self._out.put(None)
        if s:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass


class App:
    def __init__(self, root, host=None, port=None):
        self.root = root
        self.cfg = self._load_settings()
        if host:
            self.cfg["host"] = host
        if port:
            self.cfg["port"] = port
            self.cfg["tls"] = (port == TLS_PORT)
        self.q = queue.Queue()
        self.gen = 0
        self.conn = Connection(self.q, self.gen)
        self.term = Terminal(want_mxp=True)
        self.connected = False
        self.connecting = False
        self.history, self.hist_pos, self.draft = [], 0, ""
        self.logfile = None
        self.last_send = time.time()
        self._tags = set()
        self._retrying = False        # auto-reconnect is active (waiting or mid-attempt)
        self._reconnect_job = None
        self._reconnect_at = 0.0
        self._quit_sent_at = 0.0      # when the user last sent "quit"
        self._line = ""               # unfinished last line of output (the prompt, usually)
        self._last_prompt = None
        self._mono = None
        self._themed = []             # (widget, role) pairs restyled by apply_theme()
        self._tag_keys = {}           # text-tag name -> raw style key (palette refs, not hex)
        self._colors_win = None
        self.skins = dict(BUILTIN_SKINS)
        self.skins.update(load_user_skins())
        self.theme = self._effective_theme()

        root.title("Duskholm")
        root.configure(bg=self.theme["bg"])
        root.geometry(self.cfg.get("geometry", "1000x700"))
        self._build_fonts()
        self._build_widgets()
        self._build_menu()
        self.apply_theme()
        root.protocol("WM_DELETE_WINDOW", self.on_quit)
        self.input.focus_set()
        self._pump_job = root.after(25, self._pump)
        root.bind("<Destroy>", self._on_root_destroy, add="+")
        self.system("Duskholm client. Type /help for local commands, or press Connect.")

    # ---- settings ----------------------------------------------------
    def _load_settings(self):
        cfg = {"host": DEFAULT_HOST, "port": TLS_PORT, "tls": True, "verify": True,
               "font_size": 11, "aliases": {}, "bell": True, "keepalive": True,
               "auto_reconnect": False, "statbar": True, "font_family": None,
               "skin": DEFAULT_SKIN, "skin_overrides": {}}
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except (OSError, ValueError):
            pass
        return clean_settings(cfg)

    def _save_settings(self):
        self.cfg["geometry"] = self.root.geometry()
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2)
        except OSError:
            pass

    # ---- ui ----------------------------------------------------------
    def _default_family(self):
        fams = set(tkfont.families())
        for f in ("Consolas", "Cascadia Mono", "Courier New"):
            if f in fams:
                return f
        return "Courier"

    def _is_mono(self, fam):
        try:
            return bool(tkfont.Font(root=self.root, family=fam, size=10).metrics("fixed"))
        except tk.TclError:
            return False

    def mono_families(self):
        """Installed monospace families only (cached; built on first use)."""
        if getattr(self, "_mono", None) is None:
            names = sorted({f for f in tkfont.families(self.root) if not f.startswith("@")},
                           key=str.lower)
            self._mono = [f for f in names if self._is_mono(f)]
        return self._mono

    def _pick_family(self):
        """The user's explicit font if valid, else the first installed monospace family the
        current skin prefers, else the platform default."""
        fams = set(tkfont.families())
        fam = self.cfg.get("font_family")
        if fam and fam in fams and self._is_mono(fam):
            return fam
        for f in self.theme.get("fonts", []):
            if f in fams and self._is_mono(f):
                return f
        return self._default_family()

    def _build_fonts(self):
        self.font_family = fam = self._pick_family()
        size = int(self.cfg.get("font_size", 11))
        self.f_norm = tkfont.Font(family=fam, size=size)
        self.f_bold = tkfont.Font(family=fam, size=size, weight="bold")
        self.f_ital = tkfont.Font(family=fam, size=size, slant="italic")
        self.f_bi = tkfont.Font(family=fam, size=size, weight="bold", slant="italic")

    def _reg(self, widget, role):
        """Register a widget so apply_theme() can restyle it."""
        self._themed.append((widget, role))
        return widget

    def _role_options(self, role, th=None):
        th = th or self.theme
        flat = th["relief"] == "flat"
        if role == "frame":
            return dict(bg=th["bg"])
        if role == "panel":
            return dict(bg=th["panel"])
        if role == "label":
            return dict(bg=th["panel"], fg=th["fg"])
        if role == "entry":
            return dict(bg=th["input_bg"], fg=th["input_fg"], insertbackground=th["input_fg"],
                        highlightbackground=th["panel_edge"], highlightcolor=th["select"],
                        selectbackground=th["select"], selectforeground=th["input_fg"])
        if role == "input":
            o = self._role_options("entry", th)
            o.update(relief="flat" if flat else "sunken", borderwidth=0 if flat else 2)
            return o
        if role == "check":
            return dict(bg=th["panel"], fg=th["fg"], selectcolor=th["input_bg"],
                        activebackground=th["panel"], activeforeground=th["fg"])
        if role == "button":
            return dict(bg=th["button_bg"], fg=th["button_fg"], activebackground=th["select"],
                        activeforeground=th["button_fg"], relief=th["relief"],
                        borderwidth=1 if flat else 2, highlightbackground=th["panel"])
        if role == "text":
            return dict(bg=th["bg"], fg=th["fg"], insertbackground=th["fg"],
                        selectbackground=th["select"], selectforeground=th["fg"])
        if role == "scroll":
            return dict(bg=th["button_bg"], troughcolor=th["bg"], activebackground=th["panel_edge"])
        if role == "list":
            return dict(bg=th["bg"], fg=th["fg"], selectbackground=th["select"],
                        selectforeground=th["fg"], highlightbackground=th["panel_edge"])
        return {}

    def _build_widgets(self):
        top = self._reg(tk.Frame(self.root), "panel")
        top.pack(fill="x")
        self._reg(tk.Label(top, text="Host"), "label").pack(side="left", padx=(8, 2), pady=4)
        self.v_host = tk.StringVar(value=self.cfg["host"])
        self._reg(tk.Entry(top, textvariable=self.v_host, width=22), "entry").pack(side="left")
        self._reg(tk.Label(top, text="Port"), "label").pack(side="left", padx=(8, 2))
        self.v_port = tk.StringVar(value=str(self.cfg["port"]))
        self._reg(tk.Entry(top, textvariable=self.v_port, width=6), "entry").pack(side="left")
        self.v_tls = tk.BooleanVar(value=self.cfg["tls"])
        self._reg(tk.Checkbutton(top, text="TLS", variable=self.v_tls, command=self._tls_toggled),
                  "check").pack(side="left", padx=6)
        self.btn = self._reg(tk.Button(top, text="Connect", width=10, command=self.toggle_connection),
                             "button")
        self.btn.pack(side="left", padx=4)
        self.status = self._reg(tk.Label(top, text="Disconnected", anchor="e"), "label")
        self.status.pack(side="right", padx=8)

        mid = self._reg(tk.Frame(self.root), "frame")
        mid.pack(fill="both", expand=True)
        # height=4: the pane must REQUEST little and expand into what is left, otherwise at large
        # font sizes its default 24-row request squeezes the stat bar and input line off-screen.
        self.out = self._reg(tk.Text(mid, font=self.f_norm, wrap="word", state="disabled",
                                     height=4, width=40, borderwidth=0, highlightthickness=0,
                                     padx=8, pady=4, cursor="arrow"), "text")
        sb = self._reg(tk.Scrollbar(mid, command=self.out.yview), "scroll")
        self.out.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.out.pack(side="left", fill="both", expand=True)
        self.out.bind("<KeyPress>", self._out_key)
        self.out.bind("<Control-MouseWheel>", self._zoom_wheel)

        self.input = self._reg(tk.Entry(self.root, font=self.f_norm, highlightthickness=1), "input")
        self.input.pack(fill="x", padx=0, pady=0, ipady=5)
        self.input.bind("<Return>", self._on_enter)
        self.input.bind("<KP_Enter>", self._on_enter)
        self.input.bind("<Up>", lambda e: self._hist(-1))
        self.input.bind("<Down>", lambda e: self._hist(+1))
        self.input.bind("<Prior>", lambda e: self.out.yview_scroll(-1, "pages"))
        self.input.bind("<Next>", lambda e: self.out.yview_scroll(1, "pages"))
        self.input.bind("<Escape>", lambda e: self.input.delete(0, "end"))
        self.input.bind("<<Paste>>", self._on_paste)
        self.input.bind("<Control-v>", self._on_paste)
        self.statbar = StatBar(self.root, self.f_norm, self.f_bold, self.theme)  # shown after 1st prompt
        for w in (self.root,):
            w.bind("<Control-plus>", lambda e: self._zoom(+1))
            w.bind("<Control-equal>", lambda e: self._zoom(+1))
            w.bind("<Control-minus>", lambda e: self._zoom(-1))
            w.bind("<Control-l>", lambda e: self.clear())

    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Connect / Disconnect", command=self.toggle_connection)
        f.add_command(label="Start/stop logging…", command=self.toggle_log)
        f.add_command(label="Clear screen   Ctrl+L", command=self.clear)
        f.add_separator()
        f.add_command(label="Quit", command=self.on_quit)
        m.add_cascade(label="File", menu=f)
        v = tk.Menu(m, tearoff=0)
        self._view_menu = v
        self.v_skin = tk.StringVar(value=self.cfg["skin"])
        self._skin_menu = tk.Menu(v, tearoff=0)
        v.add_cascade(label="Skin", menu=self._skin_menu)
        self._rebuild_skin_menu()
        v.add_command(label="Colours…", command=self.edit_colors)
        v.add_command(label="Font…", command=self.choose_font)
        self.v_statbar = tk.BooleanVar(value=self.cfg["statbar"])
        v.add_checkbutton(label="Stat bar", variable=self.v_statbar, command=self._statbar_toggled)
        v.add_separator()
        v.add_command(label="Bigger font   Ctrl +", command=lambda: self._zoom(+1))
        v.add_command(label="Smaller font   Ctrl -", command=lambda: self._zoom(-1))
        m.add_cascade(label="View", menu=v)
        o = tk.Menu(m, tearoff=0)
        self.v_verify = tk.BooleanVar(value=self.cfg["verify"])
        self.v_bell = tk.BooleanVar(value=self.cfg["bell"])
        self.v_keep = tk.BooleanVar(value=self.cfg["keepalive"])
        o.add_checkbutton(label="Verify TLS certificate", variable=self.v_verify,
                          command=lambda: self.cfg.update(verify=self.v_verify.get()))
        o.add_checkbutton(label="Beep on server bell", variable=self.v_bell,
                          command=lambda: self.cfg.update(bell=self.v_bell.get()))
        o.add_checkbutton(label="Send keep-alive", variable=self.v_keep,
                          command=lambda: self.cfg.update(keepalive=self.v_keep.get()))
        self.v_auto = tk.BooleanVar(value=self.cfg["auto_reconnect"])
        o.add_checkbutton(label="Auto-reconnect when disconnected", variable=self.v_auto,
                          command=self._auto_toggled)
        m.add_cascade(label="Options", menu=o)
        self._menus = [m, f, v, o, self._skin_menu]
        self.root.config(menu=m)

    # ---- output ------------------------------------------------------
    # ---- theme ----------------------------------------------------------
    def _effective_theme(self):
        """The selected skin with the user's saved edits applied (validated)."""
        name = self.cfg.get("skin")
        if name not in self.skins:
            name = self.cfg["skin"] = DEFAULT_SKIN
        base = self.skins[name]
        return validate_theme(self.cfg["skin_overrides"].get(name) or {}, base)

    def _color(self, c, default):
        """Resolve a style colour: None -> default, int -> palette entry, '#rrggbb' -> itself."""
        if c is None:
            return default
        if isinstance(c, int):
            return self.theme["ansi"][c] if 0 <= c < 16 else default
        return c

    def _tag_colors(self, key):
        fg_raw, bg_raw, _b, _i, _u, inv = key
        th = self.theme
        fg, bg = self._color(fg_raw, th["fg"]), self._color(bg_raw, th["bg"])
        if inv:
            fg, bg = bg, fg
        return ensure_contrast(fg, bg, th["min_contrast"]), bg

    def _tag_for(self, key):
        fg, bg, bold, ital, ul, inv = key
        name = "s%r|%r|%d%d%d%d" % (fg, bg, bold, ital, ul, inv)
        if name not in self._tags:
            self._tag_keys[name] = key
            self._tags.add(name)
            self._style_tag(name)
        return name

    def _style_tag(self, name):
        key = self._tag_keys[name]
        _fg, _bg, bold, ital, ul, _inv = key
        font = {(0, 0): self.f_norm, (1, 0): self.f_bold,
                (0, 1): self.f_ital, (1, 1): self.f_bi}[(int(bold), int(ital))]
        fg, bg = self._tag_colors(key)
        self.out.tag_configure(name, foreground=fg, background=bg, underline=bool(ul), font=font)

    def _restyle_tags(self):
        th = self.theme
        for name in self._tags:
            self._style_tag(name)
        self.out.tag_configure("echo", foreground=ensure_contrast(th["echo"], th["bg"], th["min_contrast"]))
        self.out.tag_configure("system", foreground=ensure_contrast(th["system"], th["bg"], th["min_contrast"]))

    def apply_theme(self):
        """Push self.theme into every widget, every text tag (so the scrollback recolours),
        the stat bar and the menus."""
        th = self.theme
        self.root.configure(bg=th["bg"])
        for w, role in self._themed:
            try:
                w.configure(**self._role_options(role))
            except tk.TclError:
                pass
        for m in getattr(self, "_menus", []):
            try:
                m.configure(bg=th["panel"], fg=th["fg"], activebackground=th["select"],
                            activeforeground=th["fg"])
            except tk.TclError:
                pass
        self._restyle_tags()
        # a skin may prefer a different font (unless the user has chosen one explicitly)
        fam = self._pick_family()
        if fam != self.font_family:
            self.font_family = fam
            for f in (self.f_norm, self.f_bold, self.f_ital, self.f_bi):
                f.configure(family=fam)
        self.statbar.set_theme(th)

    def _rebuild_skin_menu(self):
        m = self._skin_menu
        m.delete(0, "end")
        for name in self.skins:
            m.add_radiobutton(label=name, value=name, variable=self.v_skin,
                              command=lambda n=name: self.set_skin(n))

    def set_skin(self, name):
        if name not in self.skins:
            return False
        self.cfg["skin"] = name
        self.v_skin.set(name)
        self.theme = self._effective_theme()
        self.apply_theme()
        self._save_settings()
        return True

    def _set_override(self, path, value):
        """Record a user edit of the current skin (stored as a difference from the skin)."""
        name = self.cfg["skin"]
        base = self.skins[name]
        ov = copy.deepcopy(self.cfg["skin_overrides"].get(name) or {})
        if path[0] == "ansi":
            ansi = ov.get("ansi") if isinstance(ov.get("ansi"), dict) else {}
            if value == base["ansi"][path[1]]:
                ansi.pop(str(path[1]), None)
            else:
                ansi[str(path[1])] = value
            if ansi:
                ov["ansi"] = ansi
            else:
                ov.pop("ansi", None)
        else:
            if value == base[path[0]]:
                ov.pop(path[0], None)
            else:
                ov[path[0]] = value
        if ov:
            self.cfg["skin_overrides"][name] = ov
        else:
            self.cfg["skin_overrides"].pop(name, None)
        self.theme = self._effective_theme()
        self.apply_theme()

    def reset_skin_edits(self):
        self.cfg["skin_overrides"].pop(self.cfg["skin"], None)
        self.theme = self._effective_theme()
        self.apply_theme()

    def save_skin_as(self, name):
        """Save the current look (skin + edits) as a user skin file and switch to it."""
        name = "".join(ch for ch in (name or "") if ch.isprintable()).strip()[:40]
        if not name or name in BUILTIN_SKINS:
            return None
        t = dict(self.theme)
        t["name"] = name
        try:
            fp = save_user_skin(t)
        except OSError:
            return None
        self.skins[name] = validate_theme(t)
        self.cfg["skin_overrides"].pop(name, None)
        self._rebuild_skin_menu()
        self.set_skin(name)
        return fp

    def _append(self, pieces):
        """pieces: [(text, tagname_or_None)]"""
        at_bottom = self.out.yview()[1] >= 0.999
        self.out.configure(state="normal")
        for text, tag in pieces:
            if tag:
                self.out.insert("end", text, tag)
            else:
                self.out.insert("end", text)
            if self.logfile:
                try:
                    self.logfile.write(text)
                except OSError:
                    pass
        lines = int(self.out.index("end-1c").split(".")[0])
        if lines > MAX_SCROLLBACK_LINES:
            self.out.delete("1.0", "%d.0" % (lines - MAX_SCROLLBACK_LINES))
        self.out.configure(state="disabled")
        if at_bottom:
            self.out.see("end")
        if self.logfile:
            try:
                self.logfile.flush()
            except OSError:
                pass

    def system(self, text):
        # start on a fresh line if the server's prompt is sitting at the end of one
        prefix = "\n" if self.out.get("end-2c", "end-1c") not in ("\n", "") else ""
        self._append([(prefix + "[" + text + "]\n", "system")])

    def clear(self):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.configure(state="disabled")

    # ---- network pump ------------------------------------------------
    def _pump(self):
        # Always reschedules, whatever happens: an exception here must never silently
        # kill network handling for the rest of the session.
        try:
            deadline = time.time() + 0.02      # keep the window responsive during bursts
            while time.time() < deadline:
                try:
                    gen, kind, payload = self.q.get_nowait()
                except queue.Empty:
                    break
                if gen != self.conn.gen:
                    continue                   # event from a connection we already dropped
                try:
                    self._handle_event(kind, payload)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
                    self.system("Internal error handling %s (see console); carrying on." % kind)
            if (self.connected and self.cfg.get("keepalive") and
                    time.time() - self.last_send > KEEPALIVE_SECONDS):
                self.conn.send(bytes([IAC, NOP]))
                self.last_send = time.time()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        finally:
            try:
                self._pump_job = self.root.after(25, self._pump)
            except tk.TclError:
                pass                       # window already destroyed

    def _on_root_destroy(self, e):
        if e.widget is self.root:
            for job in (self._pump_job, self._reconnect_job):
                if job is not None:
                    try:
                        self.root.after_cancel(job)
                    except tk.TclError:
                        pass
            self.conn.close()

    def _set_disconnected(self):
        self.connecting = self.connected = False
        self._line, self._last_prompt = "", None     # stale stats must not outlive the session
        self._statbar_hide()
        self.input.configure(show="")
        self.btn.configure(text="Connect")
        self.status.configure(text="Disconnected")

    def _handle_event(self, kind, payload):
        if kind == "data":
            self._on_data(payload)
        elif kind == "connected":
            self._retrying = False
            self._quit_sent_at = 0.0      # a "quit" from an earlier session means nothing now
            self.connecting, self.connected = False, True
            self.term = Terminal(want_mxp=True)
            self.input.configure(show="")
            self.btn.configure(text="Disconnect")
            self.status.configure(text="Connected")
            self.system("Connected to %s:%s%s." % (self.v_host.get(), self.v_port.get(),
                                                    " (TLS)" if self.v_tls.get() else ""))
        elif kind == "failed":
            self._set_disconnected()
            self.system("Could not connect: %s" % payload)
            if "CERTIFICATE" in payload.upper():
                self._cancel_reconnect()      # retrying cannot fix a certificate problem
                self.system("TLS certificate was not accepted. Options > Verify TLS certificate "
                            "turns checking off, or use the plain port 3000.")
            elif self._retrying:              # this was an automatic attempt: keep trying
                self._schedule_reconnect("Reconnect failed.")
        elif kind == "closed":
            if self.connected:
                self._set_disconnected()
                self.system(payload)
                if time.time() - self._quit_sent_at < QUIT_GRACE:
                    self.system("You quit, so the client will not reconnect.")
                else:
                    self._schedule_reconnect("Disconnected unexpectedly.")

    # ---- stat bar ----------------------------------------------------
    def _track_prompt(self, text):
        """Keep the unfinished last line; if it is a game prompt, update the stat bar."""
        self._line += text
        if "\n" in self._line:
            self._line = self._line.rsplit("\n", 1)[1]
        if len(self._line) > 2000:
            self._line = self._line[-2000:]

    def _update_statbar(self):
        p = parse_prompt(self._line)
        if p is None:
            return
        if self.term.echo_off:
            # A game prompt proves we are in play, not at a password prompt. The server never
            # sends WONT ECHO after new-account creation (comm.c state_confirm_new_account_password),
            # which would otherwise leave input masked for the whole session. Only this positive
            # evidence lifts the mask; guessing could leak a password into the log.
            self.term.echo_off = False
            self.input.configure(show="")
        if p == self._last_prompt:
            return
        self._last_prompt = p
        self.statbar.set_data(p)
        self._statbar_show()

    def _statbar_show(self):
        if self.cfg.get("statbar") and self._last_prompt and not self.statbar.winfo_ismapped():
            self.statbar.pack(fill="x", before=self.input)

    def _statbar_hide(self):
        self.statbar.pack_forget()

    def _statbar_toggled(self):
        self.cfg["statbar"] = self.v_statbar.get()
        if self.cfg["statbar"]:
            self._statbar_show()
        else:
            self._statbar_hide()

    def _on_data(self, data):
        pieces = []
        for ev in self.term.feed(data):
            k = ev[0]
            if k == "text":
                pieces.append((ev[1], self._tag_for(ev[2])))
                self._track_prompt(ev[1])
            elif k == "send":
                self.conn.send(ev[1])
            elif k == "echo":
                self.input.configure(show="" if ev[1] else "*")
                if not ev[1]:
                    self.hist_pos = len(self.history)
            elif k == "bell" and self.cfg.get("bell"):
                self.root.bell()
        if pieces:
            self._append(pieces)
            self._update_statbar()

    # ---- input -------------------------------------------------------
    def _on_enter(self, _e):
        line = self.input.get()
        self.input.delete(0, "end")
        secret = self.term.echo_off
        if not secret and line.strip() and (not self.history or self.history[-1] != line):
            self.history.append(line)
            del self.history[:-500]
        self.hist_pos, self.draft = len(self.history), ""
        if not secret:
            if line.startswith("/") and not line.startswith("//"):
                self._local(line)
                return "break"
            if line.startswith("//"):
                line = line[1:]
        self.send_line(line, echo=not secret, secret=secret)
        return "break"

    def _on_paste(self, _e):
        # Entry would insert newlines as odd glyphs; flatten them (never auto-send a paste).
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return "break"
        clean, _dropped, _trunc = sanitize_outgoing(text)
        try:
            if self.input.selection_present():
                self.input.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.input.insert("insert", clean)
        return "break"

    def send_line(self, line, echo=True, secret=False):
        """secret=True (password prompt): no alias expansion, no local echo, and nothing
        about the content ever appears in a message."""
        if not self.connected:
            self.system("Not connected.")
            return
        parts = [line] if secret else self._expand(line)
        for part in parts:
            if not secret and part.split(None, 1)[:1] == ["quit"]:
                self._quit_sent_at = time.time()   # the close that follows is intentional
            clean, dropped, truncated = sanitize_outgoing(part)
            if dropped:
                self.system("%d character%s the game can't accept %s removed from that line."
                            % (dropped, "" if dropped == 1 else "s", "was" if dropped == 1 else "were"))
            if truncated:
                self.system("Line cut to %d characters (the game's limit is about 6000)." % MAX_LINE)
            if echo:
                self._append([(clean + "\n", "echo")])
            # clean is printable ASCII, so no IAC (0xFF) can occur and no escaping is needed
            if not self.conn.send(clean.encode("ascii") + b"\r\n"):
                self.system("Send failed.")
                return
        self.last_send = time.time()

    def _expand(self, line):
        """Alias expansion. Alias templates may hold several commands separated by ';'
        and use $* for the arguments (otherwise arguments are appended)."""
        word, _, rest = line.partition(" ")
        tmpl = self.cfg["aliases"].get(word)
        if tmpl is None:
            return [line]
        rest = rest.strip()
        parts = [p.strip() for p in tmpl.split(";") if p.strip()]
        if "$*" in tmpl:
            return [p.replace("$*", rest) for p in parts]
        if rest and parts:
            parts[-1] = parts[-1] + " " + rest
        return parts

    def _hist(self, d):
        if not self.history or self.term.echo_off:
            return "break"
        if self.hist_pos == len(self.history):
            self.draft = self.input.get()
        self.hist_pos = max(0, min(len(self.history), self.hist_pos + d))
        self.input.delete(0, "end")
        self.input.insert(0, self.draft if self.hist_pos == len(self.history)
                          else self.history[self.hist_pos])
        return "break"

    def _out_key(self, e):
        # typing while the output pane has focus goes to the input line
        if e.char and e.char.isprintable() and not (e.state & 0x4):
            self.input.focus_set()
            self.input.insert("end", e.char)
            return "break"

    # ---- local commands ----------------------------------------------
    def _local(self, line):
        cmd, _, arg = line[1:].partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        if cmd in ("help", "?"):
            self.system("Local commands:\n"
                        "  /connect [host [port]]   /disconnect   /reconnect   /quit\n"
                        "  /alias name expansion    (use ; between commands, $* for arguments)\n"
                        "  /unalias name            /aliases\n"
                        "  /log [file]              start or stop logging\n"
                        "  /clear                   //text sends \"/text\" to the game")
        elif cmd == "connect":
            bits = arg.split()
            if bits:
                self.v_host.set(bits[0])
            if len(bits) > 1:
                self.v_port.set(bits[1])
                self.v_tls.set(bits[1] == str(TLS_PORT))
            if not self.connected:
                self._cancel_reconnect()
                self.toggle_connection()
        elif cmd == "reconnect":
            self._cancel_reconnect()
            if self.connected or self.connecting:
                self.toggle_connection()
            self.root.after(300, self.toggle_connection)
        elif cmd == "disconnect":
            if self.connected or self.connecting or self._retrying:
                self.toggle_connection()
        elif cmd == "quit":
            self.on_quit()
        elif cmd == "clear":
            self.clear()
        elif cmd == "alias":
            name, _, exp = arg.partition(" ")
            if not name or not exp.strip():
                self.system("Usage: /alias name expansion")
            else:
                self.cfg["aliases"][name] = exp.strip()
                self._save_settings()
                self.system("Alias %s = %s" % (name, exp.strip()))
        elif cmd == "unalias":
            if self.cfg["aliases"].pop(arg, None) is not None:
                self._save_settings()
                self.system("Removed alias %s." % arg)
            else:
                self.system("No such alias.")
        elif cmd == "aliases":
            al = self.cfg["aliases"]
            self.system("\n".join("%s = %s" % kv for kv in sorted(al.items())) if al else "No aliases.")
        elif cmd == "log":
            self.toggle_log(arg or None)
        else:
            self.system("Unknown local command. /help lists them; //text sends a literal \"/text\".")

    # ---- actions -----------------------------------------------------
    def _tls_toggled(self):
        # swap between the two stock ports when the user flips TLS
        if self.v_port.get() in (str(PLAIN_PORT), str(TLS_PORT)):
            self.v_port.set(str(TLS_PORT if self.v_tls.get() else PLAIN_PORT))

    def toggle_connection(self):
        if self.connected or self.connecting:
            self._cancel_reconnect()
            self.conn.close()
            self._set_disconnected()
            self.system("Disconnected.")
            return
        if self._retrying:                  # waiting to retry: this click cancels
            self._cancel_reconnect(announce=True)
            return
        self._start_connect()

    def _start_connect(self, auto=False):
        host = self.v_host.get().strip()
        try:
            port = int(self.v_port.get())
        except ValueError:
            messagebox.showerror("Port", "Port must be a number.")
            self._cancel_reconnect()
            return
        self.cfg.update(host=host, port=port, tls=self.v_tls.get())
        self._save_settings()
        self.connecting = True
        self.btn.configure(text="Cancel")
        self.status.configure(text="Connecting…")
        self.system("%s %s:%d…" % ("Reconnecting to" if auto else "Connecting to", host, port))
        self.gen += 1
        self.conn = Connection(self.q, self.gen)
        self.conn.open(host, port, self.v_tls.get(), self.v_verify.get())

    # ---- auto-reconnect ----------------------------------------------
    def _auto_toggled(self):
        self.cfg["auto_reconnect"] = self.v_auto.get()
        if not self.v_auto.get():
            self._cancel_reconnect(announce=self._retrying and not self.connecting)

    def _schedule_reconnect(self, reason):
        """Called after an unexpected drop or a failed attempt. No-op unless enabled."""
        if not self.cfg.get("auto_reconnect"):
            return
        self._retrying = True
        self._reconnect_at = time.time() + RECONNECT_SECONDS
        self.btn.configure(text="Cancel retry")
        self.system("%s Retrying every %d seconds (Options > Auto-reconnect; Cancel retry to stop)."
                    % (reason, RECONNECT_SECONDS))
        self._reconnect_tick()

    def _reconnect_tick(self):
        self._reconnect_job = None
        if not self._retrying or self.connected or self.connecting:
            return
        left = int(self._reconnect_at - time.time() + 0.999)
        if left <= 0:
            self._start_connect(auto=True)
            return
        self.status.configure(text="Reconnecting in %ds" % left)
        self._reconnect_job = self.root.after(min(1000, left * 1000), self._reconnect_tick)

    def _cancel_reconnect(self, announce=False):
        was = self._retrying
        self._retrying = False
        if self._reconnect_job is not None:
            self.root.after_cancel(self._reconnect_job)
            self._reconnect_job = None
        if was and not self.connected and not self.connecting:
            self.btn.configure(text="Connect")
            self.status.configure(text="Disconnected")
        if announce and was:
            self.system("Auto-reconnect cancelled.")

    def toggle_log(self, path=None):
        if self.logfile:
            self.logfile.close()
            self.logfile = None
            self.system("Logging stopped.")
            return
        if not path:
            path = time.strftime("duskholm-%Y%m%d-%H%M%S.log")
        try:
            self.logfile = open(path, "a", encoding="utf-8")
        except OSError as e:
            self.system("Cannot open log: %s" % e)
            return
        self.system("Logging to %s" % os.path.abspath(path))

    def apply_font(self, family=None, size=None, use_skin_font=False):
        """Change the display font. Only installed monospace families are accepted.
        use_skin_font=True drops the explicit choice so the skin's preferred font applies."""
        if use_skin_font:
            self.cfg["font_family"] = None
        elif family is not None:
            if family not in self.mono_families():
                return False
            self.cfg["font_family"] = family
        if size is not None:
            self.cfg["font_size"] = max(MIN_FONT, min(MAX_FONT, int(size)))
        self.font_family = self._pick_family()
        for f in (self.f_norm, self.f_bold, self.f_ital, self.f_bi):
            f.configure(family=self.font_family, size=self.cfg["font_size"])
        self.statbar.refresh()
        self._save_settings()
        return True

    def _zoom(self, d):
        self.apply_font(size=int(self.cfg["font_size"]) + d)
        return "break"

    def _theme_tree(self, w):
        """Style a dialog (and everything in it) from the current theme. Widgets that carry
        `_noskin` (colour swatches, previews) are left for their owner to colour."""
        th = self.theme
        cls = w.winfo_class()
        if not getattr(w, "_noskin", False):
            role = {"Frame": "panel", "Toplevel": "panel", "Labelframe": "panel", "Label": "label",
                    "Button": "button", "Entry": "entry", "Spinbox": "entry", "Listbox": "list",
                    "Text": "text", "Checkbutton": "check", "Menubutton": "button",
                    "Scrollbar": "scroll"}.get(cls)
            try:
                if role:
                    w.configure(**self._role_options(role))
                if cls == "Scale":
                    w.configure(bg=th["panel"], fg=th["fg"], troughcolor=th["input_bg"],
                                highlightbackground=th["panel"], activebackground=th["select"])
                elif cls == "Labelframe":
                    w.configure(fg=th["fg"])
                elif cls == "Spinbox":
                    w.configure(buttonbackground=th["button_bg"])
                elif cls == "Menubutton":
                    w["menu"].configure(bg=th["panel"], fg=th["fg"], activebackground=th["select"],
                                        activeforeground=th["fg"])
            except tk.TclError:
                pass
        for c in w.winfo_children():
            self._theme_tree(c)

    def choose_font(self):
        """Dialog: monospace families only, size, live preview."""
        top = tk.Toplevel(self.root)
        top.title("Font")
        top.transient(self.root)
        fams = self.mono_families()
        cur_fam, cur_size = self.font_family, int(self.cfg["font_size"])
        pad = dict(padx=10, pady=(8, 0))

        tk.Label(top, text="Monospace fonts installed on this computer").pack(anchor="w", **pad)
        box = tk.Frame(top)
        box.pack(fill="both", expand=True, padx=10, pady=4)
        lb = tk.Listbox(box, height=12, width=34, exportselection=False, highlightthickness=0)
        sc = tk.Scrollbar(box, command=lb.yview)
        lb.configure(yscrollcommand=sc.set)
        lb.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")
        for f in fams:
            lb.insert("end", f)
        if cur_fam in fams:
            i = fams.index(cur_fam)
            lb.selection_set(i)
            lb.see(i)

        row = tk.Frame(top)
        row.pack(fill="x", padx=10, pady=4)
        tk.Label(row, text="Size").pack(side="left")
        v_size = tk.IntVar(value=cur_size)
        sp = tk.Spinbox(row, from_=MIN_FONT, to=MAX_FONT, width=4, textvariable=v_size)
        sp.pack(side="left", padx=6)

        prev_font = tkfont.Font(family=cur_fam, size=cur_size)
        preview = tk.Label(top, text='The quick brown fox: "Hello," she said. 0O 1lI\n'
                                     '[350/350DF 0ST 0WN 0LG M:0 K:0 ( )]',
                           font=prev_font, justify="left", anchor="w", padx=8, pady=8)
        preview._noskin = True
        preview.pack(fill="x", padx=10, pady=4)

        def chosen():
            sel = lb.curselection()
            fam = fams[sel[0]] if sel else cur_fam
            try:
                size = max(MIN_FONT, min(MAX_FONT, int(v_size.get())))
            except (tk.TclError, ValueError):
                size = cur_size
            return fam, size

        def update_preview(*_):
            fam, size = chosen()
            prev_font.configure(family=fam, size=size)

        lb.bind("<<ListboxSelect>>", update_preview)
        v_size.trace_add("write", update_preview)

        def ok():
            fam, size = chosen()
            self.apply_font(fam, size)
            top.destroy()

        def skin_font():
            self.apply_font(size=chosen()[1], use_skin_font=True)
            top.destroy()

        btns = tk.Frame(top)
        btns.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(btns, text="OK", width=8, command=ok).pack(side="right")
        tk.Button(btns, text="Cancel", width=8, command=top.destroy).pack(side="right", padx=6)
        tk.Button(btns, text="Use skin's font", command=skin_font).pack(side="left")
        top.bind("<Return>", lambda e: ok())
        top.bind("<Escape>", lambda e: top.destroy())
        self._theme_tree(top)
        preview.configure(bg=self.theme["bg"], fg=self.theme["fg"])
        top.focus_set()
        return top

    def edit_colors(self):
        """Skin picker + palette / interface colour editor + contrast slider, applied live.
        Cancel restores everything as it was when the dialog opened."""
        if self._colors_win is not None:
            try:
                if self._colors_win.winfo_exists():
                    self._colors_win.lift()
                    return self._colors_win
            except tk.TclError:
                pass
        snapshot = (self.cfg["skin"], copy.deepcopy(self.cfg["skin_overrides"]))
        top = tk.Toplevel(self.root)
        self._colors_win = top
        top.title("Skin and colours")
        top.transient(self.root)
        swatches = {}
        state = {"busy": False}

        def readable(h):
            return "#000000" if rel_luminance(h) > 0.35 else "#ffffff"

        head = tk.Frame(top)
        head.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(head, text="Skin").pack(side="left")
        var = tk.StringVar(value=self.cfg["skin"])
        opt = tk.OptionMenu(head, var, *self.skins.keys(), command=lambda n: choose_skin(n))
        opt.pack(side="left", padx=8)
        blurb = tk.Label(head, anchor="w", justify="left")
        blurb.pack(side="left", fill="x", expand=True)

        body = tk.Frame(top)
        body.pack(fill="both", expand=True, padx=10)
        left = tk.LabelFrame(body, text=" Game palette (the 16 ANSI colours) ")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        for i in range(16):
            b = tk.Button(left, text=ANSI_NAMES[i], width=14, command=lambda i=i: pick(("ansi", i)))
            b._noskin = True
            b.grid(row=i % 8, column=i // 8, padx=3, pady=2, sticky="ew")
            swatches[("ansi", i)] = b
        right = tk.LabelFrame(body, text=" Interface colours ")
        right.grid(row=0, column=1, sticky="nsew")
        for r, k in enumerate(COLOR_KEYS):
            tk.Label(right, text=COLOR_LABELS[k], anchor="w", width=22).grid(
                row=r, column=0, sticky="w", padx=4)
            b = tk.Button(right, width=10, command=lambda k=k: pick(("key", k)))
            b._noskin = True
            b.grid(row=r, column=1, padx=3, pady=1)
            swatches[("key", k)] = b

        crow = tk.Frame(top)
        crow.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(crow, text="Minimum text contrast").pack(side="left")
        scale = tk.Scale(crow, from_=1.0, to=7.0, resolution=0.1, orient="horizontal", length=240,
                         command=lambda v: on_scale(v))
        scale.pack(side="left", padx=8)
        tk.Label(crow, justify="left", wraplength=360,
                 text="1.0 shows the game's colours exactly as sent. Higher lifts any colour that "
                      "is too dark (dark blues, black) until it is readable, keeping its hue."
                 ).pack(side="left")

        prev = tk.Text(top, height=9, width=84, borderwidth=0, state="disabled", wrap="word",
                       highlightthickness=0, cursor="arrow")
        prev._noskin = True
        prev.pack(fill="x", padx=10, pady=8)
        self._colors_prev = prev

        def render_preview():
            th = self.theme
            prev.configure(state="normal", bg=th["bg"], fg=th["fg"])
            prev.delete("1.0", "end")
            n = [0]

            def put(text, color):
                tag = "t%d" % n[0]
                n[0] += 1
                prev.tag_configure(tag, foreground=color)
                prev.insert("end", text, tag)

            put("As shown (after contrast):  ", th["fg"])
            for i in range(16):
                put(" %s" % ANSI_NAMES[i].replace("Bright ", "+"),
                    ensure_contrast(th["ansi"][i], th["bg"], th["min_contrast"]))
            put("\nAs the game sends them:    ", th["fg"])
            for i in range(16):
                put(" %s" % ANSI_NAMES[i].replace("Bright ", "+"), th["ansi"][i])
            put("\n\nHard cases, shown / as sent:  ", th["fg"])
            for raw in ("#00005f", "#000087", "#000000", "#2472c8", "#303030", "#5f005f"):
                put("  %s " % raw, ensure_contrast(raw, th["bg"], th["min_contrast"]))
                put("(%s)" % raw, raw)
            put("\n\nYou walk north.  ", th["fg"])
            put("A cold wind carries a whisper.  ", ensure_contrast(th["system"], th["bg"], th["min_contrast"]))
            put("> look", ensure_contrast(th["echo"], th["bg"], th["min_contrast"]))
            prev.configure(state="disabled")

        def refresh():
            th = self.theme
            self._theme_tree(top)
            blurb.configure(text=th.get("blurb", ""))
            for i in range(16):
                c = th["ansi"][i]
                swatches[("ansi", i)].configure(bg=c, fg=readable(c), activebackground=c,
                                                activeforeground=readable(c))
            for k in COLOR_KEYS:
                c = th[k]
                swatches[("key", k)].configure(bg=c, fg=readable(c), text=c, activebackground=c,
                                               activeforeground=readable(c))
            state["busy"] = True
            if abs(float(scale.get()) - th["min_contrast"]) > 0.001:
                scale.set(th["min_contrast"])
            state["busy"] = False
            var.set(self.cfg["skin"])
            menu = opt["menu"]
            menu.delete(0, "end")
            for nm in self.skins:
                menu.add_command(label=nm, command=lambda nm=nm: (var.set(nm), choose_skin(nm)))
            render_preview()

        def choose_skin(name):
            self.set_skin(name)
            refresh()

        def pick(which):
            cur = self.theme["ansi"][which[1]] if which[0] == "ansi" else self.theme[which[1]]
            title = ANSI_NAMES[which[1]] if which[0] == "ansi" else COLOR_LABELS[which[1]]
            res = colorchooser.askcolor(color=cur, parent=top, title=title)
            col = res[1] if res else None
            if isinstance(col, str) and _hex_ok(col.lower()):
                self._set_override(("ansi", which[1]) if which[0] == "ansi" else (which[1],), col.lower())
                refresh()

        def on_scale(v):
            if state["busy"]:
                return
            self._set_override(("min_contrast",), round(float(v), 1))
            render_preview()
            self._restyle_tags()
            self.statbar.set_theme(self.theme)

        def reset():
            self.reset_skin_edits()
            refresh()

        def save_as():
            name = simpledialog.askstring("Save skin", "Name for the new skin:", parent=top)
            if name:
                fp = self.save_skin_as(name)
                if fp:
                    self.system("Skin saved to %s" % fp)
                else:
                    self.system("Could not save that skin (name empty or reserved).")
                refresh()

        def done():
            self._save_settings()
            self._colors_win = None
            top.destroy()

        def cancel():
            self.cfg["skin"], self.cfg["skin_overrides"] = snapshot[0], snapshot[1]
            self.v_skin.set(snapshot[0])
            self.theme = self._effective_theme()
            self.apply_theme()
            self._colors_win = None
            top.destroy()

        btns = tk.Frame(top)
        btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btns, text="Done", width=10, command=done).pack(side="right")
        tk.Button(btns, text="Cancel changes", command=cancel).pack(side="right", padx=6)
        tk.Button(btns, text="Save as new skin…", command=save_as).pack(side="left")
        tk.Button(btns, text="Reset this skin", command=reset).pack(side="left", padx=6)
        top.protocol("WM_DELETE_WINDOW", done)
        top.bind("<Escape>", lambda e: cancel())
        top._actions = dict(pick=pick, choose_skin=choose_skin, reset=reset, done=done,
                            cancel=cancel, save_as=save_as, refresh=refresh, scale=scale)
        refresh()
        return top

    def _zoom_wheel(self, e):
        return self._zoom(+1 if e.delta > 0 else -1)

    def on_quit(self):
        self._cancel_reconnect()
        self.conn.close()
        if self.logfile:
            self.logfile.close()
        self._save_settings()
        self.root.destroy()


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else None
    port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None
    root = tk.Tk()
    App(root, host, port)
    root.mainloop()


if __name__ == "__main__":
    main()
