#!/usr/bin/env python3
"""
Sanctuary - a small tkinter telnet client for MUDs, built for Duskholm and other Haven-style games.

Run:   python sanctuary.py [host [port]]      (pythonw, or Sanctuary.pyw, hides the console)
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
import threading
import urllib.parse
import urllib.request
import webbrowser
import io
import shutil
import socket
import ssl
import sys
import time
import traceback
import unicodedata
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, messagebox, simpledialog

import dosui
import prompts
try:
    import triggers
except ImportError:                 # no trigger engine installed: output passes straight through
    triggers = None
try:
    import layout                   # geometry of the capture panes
except ImportError:
    layout = None
try:
    import emojis                   # :name: <-> emoji
except ImportError:
    emojis = None
try:
    import boxes                    # join ASCII boxes into solid lines
except ImportError:
    boxes = None
import extras                       # timers, clock, notepad, moon window, hotkeys
import toolsui                      # gradient maker, hex converter, customize form
import dosforms                     # the DOS-look versions of those: pick from lists, edit paragraphs
import colortools
import custom as customize_data
import worldfile
import speech
import access
import combatfilter
import updateui
import worldtabs                   # several worlds at once: tabs, Ctrl+F1..F12

DEFAULT_HOST = "duskholm.com"
PLAIN_PORT = 3000
TLS_PORT = 3001
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".sanctuary.json")
MAX_SCROLLBACK_LINES = 20000
KEEPALIVE_SECONDS = 120
APP_NAME = "Sanctuary"   # every user-visible mention of the client's name comes from here
MIN_FONT, MAX_FONT = 7, 40
RECONNECT_SECONDS = 30   # wait between automatic reconnect attempts
QUIT_GRACE = 15          # a close this soon after the user sent "quit" is intentional
PARTIAL_FLUSH_MS = 120   # an unfinished line (a prompt) is shown after this long without a newline

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


TAB_WIDTH = 8     # a TAB advances to the next multiple of this many columns, as in MUSHclient

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
# Extra colours used only by the DOS terminal look (see dosui.dos_colors). A skin may omit them;
# the DOS widgets then fall back to classic DOS blue/cyan.
DOS_KEYS = ("dos_bar_bg", "dos_bar_fg", "dos_bar2_bg", "dos_bar2_fg", "dos_key_fg", "dos_menu_bg",
            "dos_menu_fg", "dos_menu_border", "dos_menu_sel_bg", "dos_menu_sel_fg", "dos_menu_dim",
            "dos_shadow", "dos_screen_border")
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
DOS_LABELS = {
    "dos_bar_bg": "Hint bar background", "dos_bar_fg": "Hint bar text",
    "dos_bar2_bg": "Status bar background", "dos_bar2_fg": "Status bar text",
    "dos_key_fg": "Key highlight", "dos_menu_bg": "Menu background", "dos_menu_fg": "Menu text",
    "dos_menu_border": "Menu border", "dos_menu_sel_bg": "Menu selection background",
    "dos_menu_sel_fg": "Menu selection text", "dos_menu_dim": "Menu dimmed text",
    "dos_shadow": "Menu shadow", "dos_screen_border": "Screen border",
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
          fonts=["Perfect DOS VGA 437", "Perfect DOS VGA 437 Win", "More Perfect DOS VGA", "Nouveau IBM",
                "Px437 IBM VGA 8x16", "Fixedsys Excelsior 3.01", "Lucida Console", "Consolas"],
          ansi=["#0f4a1c", "#ff6b4a", "#33ff66", "#d4ff4a", "#3fb8a0", "#9be6b4", "#4de6d0",
                "#a8ffbd", "#2e8f48", "#ff9966", "#66ff99", "#eaff77", "#6fe0c8", "#b8f5c8",
                "#8ffff0", "#e6fff0"],
          blurb="Green-screen CRT. Reds stay warm so warnings still stand out."),
    _skin("Retro DOS", bg="#000000", fg="#aaaaaa", panel="#0000aa", panel_edge="#aaaaaa",
          input_bg="#0000aa", input_fg="#ffffff", echo="#55ffff", system="#ffff55",
          alert="#ffff55", dim="#9999dd", select="#aa00aa", button_bg="#aaaaaa",
          button_fg="#000000", relief="raised", min_contrast=3.0,
          fonts=["Perfect DOS VGA 437", "Perfect DOS VGA 437 Win", "More Perfect DOS VGA", "Nouveau IBM",
                "Px437 IBM VGA 8x16", "Fixedsys Excelsior 3.01", "Lucida Console", "Consolas"],
          ansi=["#000000", "#aa0000", "#00aa00", "#aa5500", "#0000aa", "#aa00aa", "#00aaaa",
                "#aaaaaa", "#555555", "#ff5555", "#55ff55", "#ffff55", "#5555ff", "#ff55ff",
                "#55ffff", "#ffffff"],
          blurb="Classic 16-colour VGA, blue panels, chunky buttons."),
    _skin("Retro Amber", bg="#0a0500", fg="#ffb000", panel="#1a0f00", panel_edge="#5a3a00",
          input_bg="#1a0f00", input_fg="#ffcc33", echo="#c27f00", system="#ffd24d",
          alert="#ffe08a", dim="#8a5a00", select="#5a3600", button_bg="#2a1800",
          button_fg="#ffb000", relief="ridge", min_contrast=3.5,
          fonts=["Perfect DOS VGA 437", "Perfect DOS VGA 437 Win", "More Perfect DOS VGA", "Nouveau IBM",
                "Px437 IBM VGA 8x16", "Fixedsys Excelsior 3.01", "Lucida Console", "Consolas"],
          ansi=["#2a1700", "#ff5a36", "#c9d93a", "#ffd24d", "#c27f00", "#ff8a4d", "#ffcc66",
                "#ffd9a0", "#7a4a00", "#ff7a59", "#e0f060", "#ffe680", "#e69a1a", "#ffa066",
                "#ffe0a0", "#fff0d0"],
          blurb="Amber monochrome CRT. Reds and greens stay distinct so warnings still show."),
)}
DEFAULT_SKIN = "Plain"
DEFAULT_DOS_SKIN = "Retro DOS"


def _dos(bar, bar_fg, bar2, bar2_fg, key, menu, menu_fg, border, sel, sel_fg, dim, shadow, screen):
    return dict(dos_bar_bg=bar, dos_bar_fg=bar_fg, dos_bar2_bg=bar2, dos_bar2_fg=bar2_fg,
                dos_key_fg=key, dos_menu_bg=menu, dos_menu_fg=menu_fg, dos_menu_border=border,
                dos_menu_sel_bg=sel, dos_menu_sel_fg=sel_fg, dos_menu_dim=dim, dos_shadow=shadow,
                dos_screen_border=screen)


_DOS_STYLE = {
    "Plain": _dos("#2a2d35", "#d8d8d8", "#1a1c21", "#c8c8c8", "#e5c07b", "#1a1c21", "#e8e8e8",
                  "#8a93a3", "#c8c8c8", "#101114", "#6f7a8a", "#05060a", "#0b0c0e"),
    "Plain Light": _dos("#d6d6ce", "#1f2328", "#ecece6", "#1f2328", "#8a4f00", "#ffffff", "#111111",
                        "#1f2328", "#1f2328", "#fafaf7", "#7b8088", "#b8b8b0", "#d0d0c8"),
    "Moody": _dos("#2a2438", "#d8d2e6", "#14121d", "#b9b4c8", "#d4a84e", "#14121d", "#d8d2e6",
                  "#c9a24b", "#c9a24b", "#0b0a10", "#6e6784", "#050408", "#07060b"),
    "Retro Phosphor": _dos("#0f4a1c", "#b8ffc8", "#061406", "#33ff66", "#e0ff6a", "#061406",
                           "#33ff66", "#33ff66", "#33ff66", "#020a02", "#1f7a35", "#010501", "#010601"),
    "Retro DOS": _dos("#007a7a", "#ffffff", "#0000aa", "#ffffff", "#ffff55", "#0000aa", "#ffffff",
                      "#ffffff", "#00aaaa", "#000000", "#9999dd", "#000044", "#0000aa"),
    "Retro Amber": _dos("#5a3600", "#ffe0a0", "#1a0f00", "#ffb000", "#ffe680", "#1a0f00", "#ffb000",
                        "#ffb000", "#ffb000", "#0a0500", "#8a5a00", "#050200", "#050300"),
}
for _n, _d in _DOS_STYLE.items():
    BUILTIN_SKINS[_n].update(_d)


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
    for k in COLOR_KEYS + DOS_KEYS:
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
    return os.path.join(os.path.expanduser("~"), ".sanctuary_skins")


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
    data = {k: theme[k] for k in ("name", "blurb", "relief", "min_contrast", "fonts", "ansi")
            + COLOR_KEYS + DOS_KEYS if k in theme}
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
        self._col = 0              # column within the current output line (for tab expansion)
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

    def _expand_tabs(self, s):
        """Replace TABs with spaces up to the next multiple of TAB_WIDTH columns. Done here, not
        by the text widget: Tk's default tab stops only advance one column once the text is past
        the first stop, which wrecks any table the game lays out with tabs."""
        if "\t" not in s and "\n" not in s:
            self._col += len(s)
            return s
        out = []
        for ch in s:
            if ch == "\n":
                self._col = 0
                out.append(ch)
            elif ch == "\t":
                n = TAB_WIDTH - self._col % TAB_WIDTH
                out.append(" " * n)
                self._col += n
            else:
                out.append(ch)
                self._col += 1
        return "".join(out)

    def _emit(self, s):
        if s:
            s = self._expand_tabs(s)
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

# Simple on/off options that appear in both Options menus: (key, default, menu label, DOS label, DOS hotkey)
EXTRA_BOOLS = [
    ("links", True, "Clickable links", "Clickable links", "L"),
    ("link_images", True, "Open image links in a pane", "Image links open in a pane", "I"),
    ("emoji", False, "Emoji: send and show :name: as emoji", "Emoji :name:", "E"),
    ("connect_boxes", False, "Join ASCII boxes into solid lines", "Join ASCII boxes", "J"),
    ("scroll_on_send", True, "Jump to the bottom when I send", "Jump to bottom on send", "S"),
    ("show_echo", True, "Show the commands I send", "Show my commands", "M"),
    ("custom_form", True, "Fill-in form when I type 'customize'", "Customize form", "F"),
    ("screen_reader", False, "Screen reader mode", "Screen reader mode", "Y"),
    ("sr_alerts", True, "Screen reader: announce stun, health and ready timers", "Reader alerts", "T"),
    ("update_check", False, "Check for updates when Sanctuary starts", "Check for updates at start", "G"),
    ("walk_preview", True, "Preview my walk on the status line when I set it", "Walk preview", "P"),
]
# Options with a few named values: (key, default, values, menu label, DOS hotkey)
EXTRA_CHOICES = [
    ("bell_new", "off", ("off", "unfocused", "scrolled", "always"), "Beep on new output", "N"),
    ("clock", "off", ("off", "real", "game"), "Clock", "C"),
    ("sr_voice", "auto", ("auto", "nvda", "jaws", "windows", "off"), "Screen reader voice", "U"),
]
CHOICE_WORDS = {"off": "off", "always": "always", "unfocused": "when the window is not in front",
                "scrolled": "when I am scrolled up or away", "real": "my local time",
                "game": "game time (US Eastern)", "auto": "automatic (NVDA, else Windows voice)",
                "nvda": "NVDA", "jaws": "JAWS", "windows": "Windows voice"}


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
    ds = cfg.get("dos_skin")
    cfg["dos_skin"] = ds.strip()[:60] if isinstance(ds, str) and ds.strip() else DEFAULT_DOS_SKIN
    cfg["ui_mode"] = "dos" if cfg.get("ui_mode") == "dos" else "normal"
    cfg["dos_cols"] = to_int(cfg.get("dos_cols"), 80, 40, 200)
    cfg["dos_font_size"] = to_int(cfg.get("dos_font_size"), 0, 0, MAX_FONT)   # 0 = not chosen
    cfg["line_spacing"] = to_int(cfg.get("line_spacing"), 0, 0, 12)
    cfg["worlds"] = clean_worlds(cfg.get("worlds"))
    pp = cfg.get("prompt_profile")
    cfg["prompt_profile"] = pp.strip()[:60] if isinstance(pp, str) and pp.strip() else prompts.DEFAULT_PRESET
    custom, names = [], set(n.lower() for n in prompts.PRESETS)
    for raw in (cfg.get("prompt_custom") if isinstance(cfg.get("prompt_custom"), list) else [])[:40]:
        prof = prompts.validate_profile(raw)
        if prof is not None and prof["kind"] == "regex" and prof["name"].lower() not in names:
            names.add(prof["name"].lower())
            custom.append(prof)
        if len(custom) >= 20:
            break
    cfg["prompt_custom"] = custom
    cfg["hide_prompt"] = cfg.get("hide_prompt") is True
    cfg["keys"] = extras.clean_keys(cfg.get("keys"))
    us = cfg.get("update_skip")
    cfg["update_skip"] = us if isinstance(us, str) and re.fullmatch(r"[vV]?[0-9.]{1,20}", us) else ""
    cfg["sr_combat"] = combatfilter.clean_settings(cfg.get("sr_combat"))
    si = cfg.get("sr_interval")
    cfg["sr_interval"] = 0 if not isinstance(si, int) or isinstance(si, bool) or si <= 0 else max(5, min(3600, si))
    sr = cfg.get("sr_rate")
    cfg["sr_rate"] = max(-10, min(10, sr)) if isinstance(sr, int) and not isinstance(sr, bool) else 0
    cfg["gradients"] = colortools.validate_saved(cfg.get("gradients"))
    go = cfg.get("game_offset")
    cfg["game_offset"] = go if isinstance(go, int) and not isinstance(go, bool) and abs(go) <= 14 * 3600 and go % 900 == 0 \
        else None
    cn = cfg.get("char_name")
    cfg["char_name"] = cn if isinstance(cn, str) and re.fullmatch(r"[A-Za-z][A-Za-z'-]{0,23}", cn) else ""
    cfg["designs"] = customize_data.validate_designs(cfg.get("designs"))
    ph = cfg.get("panes_hidden")
    cfg["panes_hidden"] = [x for x in ph[:8] if isinstance(x, str) and len(x) < 20] if isinstance(ph, list) else []
    if triggers is not None:
        raw = cfg.get("triggers") if isinstance(cfg.get("triggers"), list) else []
        cfg["triggers"] = [t for t in (triggers.validate_trigger(x) for x in raw[:1000]) if t is not None][:500]
        rules = cfg.get("alias_rules")
        if not isinstance(rules, list):
            legacy = cfg.get("aliases") if isinstance(cfg.get("aliases"), dict) else {}
            rules = triggers.migrate_legacy_aliases(
                {k: v.replace("$*", "%*") for k, v in legacy.items() if isinstance(k, str) and isinstance(v, str)})
        cfg["alias_rules"] = [a for a in (triggers.validate_alias(x) for x in rules[:400]) if a is not None][:200]
    else:
        cfg["triggers"], cfg["alias_rules"] = [], []
    if layout is not None:
        cfg["panes"] = layout.validate_panes(cfg.get("panes") if isinstance(cfg.get("panes"), list) else [])
        cfg["layout"] = layout.validate_layout(cfg.get("layout"), known_panes=[p["name"] for p in cfg["panes"]])
    else:
        cfg["panes"], cfg["layout"] = [], {"regions": [], "min_main_cols": 80}
    so = cfg.get("skin_overrides")
    cfg["skin_overrides"] = ({k: v for k, v in list(so.items())[:50]
                              if isinstance(k, str) and len(k) < 60 and isinstance(v, dict)}
                             if isinstance(so, dict) else {})
    for k, default in (("tls", True), ("verify", True), ("bell", True), ("keepalive", True),
                       ("auto_reconnect", False), ("statbar", True), ("fullscreen", False),
                       ("dos_autofit", True), ("dos_flourish", True), ("dos_fit", True)):
        if not isinstance(cfg.get(k), bool):
            cfg[k] = default
    for k, default, _l, _d, _h in EXTRA_BOOLS:
        if not isinstance(cfg.get(k), bool):
            cfg[k] = default
    for k, default, values, _l, _h in EXTRA_CHOICES:
        if cfg.get(k) not in values:
            cfg[k] = default
    al = cfg.get("aliases")
    cfg["aliases"] = {k: v for k, v in al.items() if isinstance(k, str) and isinstance(v, str)
                      and k and " " not in k} if isinstance(al, dict) else {}
    if not isinstance(cfg.get("geometry"), str) or not re.match(r"^\d+x\d+([+-]-?\d+){0,2}$",
                                                                cfg.get("geometry", "")):
        cfg.pop("geometry", None)
    return cfg

_COLOUR_NAMES = {"black": 0, "red": 1, "green": 2, "yellow": 3, "blue": 4, "magenta": 5, "cyan": 6, "white": 7}


def parse_colour_field(text):
    """A highlight colour typed by the user: '' -> None, '#rrggbb' -> that, 0-15 or a colour name
    (optionally 'bright red') -> a palette index. Raises ValueError on anything else."""
    t = str(text or "").strip().lower()
    if not t:
        return None
    if HEX_RE.match(t):
        return t
    if t.isascii() and t.isdigit() and int(t) < 16:
        return int(t)
    bright = t.startswith("bright ")
    name = t[7:] if bright else t
    if name in _COLOUR_NAMES:
        return _COLOUR_NAMES[name] + (8 if bright else 0)
    raise ValueError("a colour is #rrggbb, a number 0-15, or a name like 'red' / 'bright cyan'")


def colour_field_text(c):
    return "" if c is None else (c if isinstance(c, str) else str(c))


def trigger_from_values(v):
    """Build a trigger from the editors' simple values. Returns (trigger_or_None, message)."""
    if triggers is None:
        return None, "The trigger engine is not installed."
    try:
        fg, bg = parse_colour_field(v.get("fg")), parse_colour_field(v.get("bg"))
    except ValueError as e:
        return None, "Highlight colour: %s" % e
    try:
        prio = int(str(v.get("priority", "0")).strip() or "0")
    except ValueError:
        return None, "Priority must be a whole number (higher runs first)."
    actions = []
    if fg is not None or bg is not None or v.get("bold"):
        actions.append({"type": "highlight", "fg": fg, "bg": bg, "bold": bool(v.get("bold")),
                        "scope": "line" if v.get("whole") else "match"})
    if v.get("hide"):
        actions.append({"type": "gag"})
    if str(v.get("send", "")).strip():
        actions.append({"type": "send", "text": str(v["send"]).strip(), "echo": bool(v.get("echo", True))})
    if str(v.get("pane", "")).strip():
        actions.append({"type": "route", "pane": str(v["pane"]).strip(), "gag": bool(v.get("pane_gag"))})
    if v.get("beep"):
        actions.append({"type": "beep"})
    if str(v.get("note", "")).strip():
        actions.append({"type": "note", "text": str(v["note"]).strip()})
    if str(v.get("status", "")).strip():
        actions.append({"type": "status", "text": str(v["status"]).strip()})
    if str(v.get("speak", "")).strip():
        actions.append({"type": "speak", "text": str(v["speak"]).strip(), "interrupt": bool(v.get("speak_int"))})
    if v.get("silence"):
        actions.append({"type": "silence"})
    actions += [a for a in (v.get("keep") or []) if isinstance(a, dict)]     # actions the editor has no controls for
    if not actions:
        return None, "Choose at least one action (highlight, hide, send, beep or note)."
    trig = {"name": str(v.get("name", "")).strip(), "enabled": bool(v.get("enabled", True)),
            "mode": "regex" if v.get("regex") else "plain", "pattern": str(v.get("pattern", "")),
            "ignore_case": bool(v.get("ignore_case", True)), "priority": prio, "stop": bool(v.get("stop")),
            "actions": actions}
    ok_trig = triggers.validate_trigger(trig)
    if ok_trig is None:
        ok, msg, _m = triggers.check_trigger(trig, str(v.get("sample", "")) or "x")
        return None, msg if not ok else "That trigger cannot be used."
    return ok_trig, "OK"


# Ready-made triggers for Duskholm's actual wording (act_comm.c): channels print "[OOC] Name: 'text'"
# (or "[OOC] Name emote text"); tells print "Name tells you 'text'" and "Name tells you OOCly 'text'".
_PRESET_DEFS = [
    {"name": "Highlight OOC channel", "mode": "plain", "pattern": "^[OOC]*", "priority": 0,
     "actions": [{"type": "highlight", "fg": 14, "scope": "line"}]},
    {"name": "Highlight Guide channel", "mode": "plain", "pattern": "^[Guide]*", "priority": 0,
     "actions": [{"type": "highlight", "fg": 10, "scope": "line"}]},
    {"name": "Highlight Newbie channel", "mode": "plain", "pattern": "^[Newbie]*", "priority": 0,
     "actions": [{"type": "highlight", "fg": 10, "scope": "line"}]},
    {"name": "Highlight Legends channel", "mode": "plain", "pattern": "^[Legends]*", "priority": 0,
     "actions": [{"type": "highlight", "fg": 11, "scope": "line"}]},
    {"name": "Highlight tells", "mode": "plain", "pattern": "* tells you *", "priority": 0,
     "actions": [{"type": "highlight", "fg": 13, "bold": True, "scope": "line"}]},
    {"name": "Beep on tell", "mode": "plain", "pattern": "* tells you *", "priority": 0,
     "actions": [{"type": "beep"}, {"type": "note", "text": "%1 sent you a tell."}]},
    {"name": "Capture OOC to a pane", "mode": "plain", "pattern": "^[OOC]*", "priority": 0,
     "actions": [{"type": "route", "pane": "OOC"}]},
    {"name": "Capture tells to a pane", "mode": "plain", "pattern": "* tells you *", "priority": 0,
     "actions": [{"type": "route", "pane": "Tells"}]},
    {"name": "Capture your own tells to a pane", "mode": "plain", "pattern": "^You tell * '*", "priority": 0,
     "actions": [{"type": "route", "pane": "Tells"}]},
    {"name": "Capture Guide / Newbie to a pane", "mode": "plain", "pattern": "^[Guide]*", "priority": 0,
     "actions": [{"type": "route", "pane": "Guide"}]},
    {"name": "Capture Newbie to a pane", "mode": "plain", "pattern": "^[Newbie]*", "priority": 0,
     "actions": [{"type": "route", "pane": "Guide"}]},
]


def trigger_presets():
    """The built-in trigger presets as valid trigger dicts (empty if the engine is missing)."""
    if triggers is None:
        return []
    return [t for t in (triggers.validate_trigger(dict(d, enabled=False)) for d in _PRESET_DEFS) if t is not None]


def values_from_trigger(t):
    """The editors' simple values for an existing trigger (None for a new one)."""
    v = {"name": "", "enabled": True, "regex": False, "pattern": "", "ignore_case": True, "priority": "0",
         "stop": False, "fg": "", "bg": "", "bold": False, "whole": False, "hide": False, "send": "",
         "echo": True, "beep": False, "note": "", "sample": "", "keep": [], "pane": "", "pane_gag": False, "status": "",
         "speak": "", "speak_int": False, "silence": False}
    if not t:
        return v
    v.update(name=t["name"], enabled=t["enabled"], regex=t["mode"] == "regex", pattern=t["pattern"],
             ignore_case=t["ignore_case"], priority=str(t["priority"]), stop=t["stop"])
    for a in t["actions"]:
        k = a["type"]
        if k == "highlight":
            v.update(fg=colour_field_text(a.get("fg")), bg=colour_field_text(a.get("bg")),
                     bold=bool(a.get("bold")), whole=a.get("scope") == "line")
        elif k == "gag":
            v["hide"] = True
        elif k == "send":
            v.update(send=a["text"], echo=bool(a.get("echo", True)))
        elif k == "beep":
            v["beep"] = True
        elif k == "note":
            v["note"] = a["text"]
        elif k == "status":
            v["status"] = a["text"]
        elif k == "speak":
            v.update(speak=a["text"], speak_int=bool(a.get("interrupt")))
        elif k == "silence":
            v["silence"] = True
        elif k == "route":
            v.update(pane=a["pane"], pane_gag=bool(a.get("gag")))
        else:
            v["keep"].append(a)
    return v


def apply_highlight(pieces, start, end, fg=None, bg=None, bold=False):
    """pieces is [(text, style_key)] for one line; returns new pieces where the characters in
    [start, end) have the given colours (a '#rrggbb' string or a palette index 0-15) and/or bold."""
    if end <= start or not (fg is not None or bg is not None or bold):
        return list(pieces)
    out, pos = [], 0
    for text, key in pieces:
        a, b = pos, pos + len(text)
        pos = b
        lo, hi = max(start, a) - a, min(end, b) - a
        if hi <= lo:
            out.append((text, key))
            continue
        kfg, kbg, kbold, kital, kul, kinv = key
        hkey = (fg if fg is not None else kfg, bg if bg is not None else kbg, kbold or bool(bold), kital, kul, kinv)
        if lo > 0:
            out.append((text[:lo], key))
        out.append((text[lo:hi], hkey))
        if hi < len(text):
            out.append((text[hi:], key))
    return out


# ---- saved worlds (the "dialing directory") -------------------------------------------------
_HOST_RE = re.compile(r"^[A-Za-z0-9._\-]{1,253}$")
DEFAULT_WORLDS = [{"name": "Duskholm", "host": "duskholm.com", "port": TLS_PORT, "tls": True,
                   "note": "Haven-style MUD", "last": 0}]


def clean_world(w):
    """A sanitised world dict, or None if it is unusable. Never raises."""
    if not isinstance(w, dict):
        return None
    name = w.get("name")
    host = w.get("host")
    if not isinstance(name, str) or not isinstance(host, str):
        return None
    name = "".join(ch for ch in name if ch.isprintable()).strip()[:40]
    host = host.strip()
    if not name or not _HOST_RE.match(host) or host.startswith(("-", ".")):
        return None
    port = w.get("port")
    if isinstance(port, bool) or not isinstance(port, (int, str)):
        return None
    try:
        port = int(port)
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None
    note = w.get("note")
    note = "".join(ch for ch in note if ch.isprintable()).strip()[:80] if isinstance(note, str) else ""
    last = w.get("last")
    last = last if isinstance(last, int) and not isinstance(last, bool) and 0 <= last < 4102444800 else 0
    return {"name": name, "host": host, "port": port, "tls": bool(w.get("tls")), "note": note, "last": last}


def clean_worlds(lst):
    """Saved worlds from settings: sanitised, de-duplicated by name (case-insensitive), capped.
    A missing or non-list value gives the default list; an empty list stays empty."""
    if not isinstance(lst, list):
        return copy.deepcopy(DEFAULT_WORLDS)
    out, seen = [], set()
    for w in lst[:400]:
        c = clean_world(w)
        if c is not None and c["name"].lower() not in seen:
            seen.add(c["name"].lower())
            out.append(c)
        if len(out) >= 200:
            break
    return out


def parse_dial_target(rest, worlds=(), default_port=None):
    """Parse what follows ATDT / ATD / ATT, or telnet's `open`: 'host port', 'host:port', or the
    name of a saved world, plus an optional tls / ssl / plain / notls flag. Returns
    (host, port, tls, world_name_or_None); raises ValueError with a readable message."""
    tokens = [t for t in str(rest).replace(",", " ").split() if t]
    flag = None
    rest_tokens = []
    for t in tokens:
        if t.lower() in ("tls", "ssl"):
            flag = True
        elif t.lower() in ("plain", "notls"):
            flag = False
        else:
            rest_tokens.append(t)
    if not rest_tokens:
        raise ValueError("usage: host [port] [tls|plain]  (or the name of a saved world)")
    wanted = " ".join(rest_tokens).lower()                 # a saved world's name may contain spaces
    for w in worlds:
        if isinstance(w, dict) and str(w.get("name", "")).lower() == wanted:
            return w["host"], int(w["port"]), bool(w["tls"]) if flag is None else flag, w["name"]
    if len(rest_tokens) > 2:
        raise ValueError("usage: host [port] [tls|plain]  (or the name of a saved world)")
    host = rest_tokens[0]
    port_text = rest_tokens[1] if len(rest_tokens) == 2 else None
    if port_text is None and host.count(":") == 1:
        host, port_text = host.split(":")
    if not _HOST_RE.match(host) or host.startswith(("-", ".")):
        raise ValueError("'%s' is not a valid host name" % host[:60])
    if port_text is None:
        port = default_port if default_port is not None else TLS_PORT
    else:
        if not (port_text.isascii() and port_text.isdigit() and 1 <= int(port_text) <= 65535):
            raise ValueError("the port must be a number from 1 to 65535")
        port = int(port_text)
    tls = flag if flag is not None else (port == TLS_PORT)
    return host, port, tls, None


AT_DIAL = ("ATDT", "ATDP", "ATD", "ATT")
AT_OK = ("AT", "ATZ", "ATH", "ATH0", "ATE0", "ATE1", "ATV1", "ATQ0")
TELNET_HELP = (
    "Commands may be abbreviated.  Commands are:",
    "",
    "open        connect to a site:  open host-name [port]",
    "close       close current connection",
    "status      print status information",
    "quit        exit telnet",
    "?           print help information",
)


# Plain-skin values, kept as module constants for callers/tests that want the defaults.
PANEL = BUILTIN_SKINS[DEFAULT_SKIN]["panel"]
DIM_FG = BUILTIN_SKINS[DEFAULT_SKIN]["dim"]
ALERT_FG = BUILTIN_SKINS[DEFAULT_SKIN]["alert"]


def stun_role(n):
    """How worrying a stun value is: 0 is quiet, 50 starts to show, 75 is bad, 100+ is critical."""
    if n <= 0:
        return "dim"
    if n < 50:
        return "normal"
    return "warn" if n < 75 else "bad"


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
            if label.upper() == "ST":                      # stun: the higher, the worse
                role = stun_role(n)
                out.append(("%s %d" % (label, n), {"dim": th["dim"], "normal": th["alert"], "warn": th["ansi"][11],
                                                   "bad": th["ansi"][9]}[role]))
            else:
                out.append(("%s %d" % (label, n), th["alert"] if n else th["dim"]))
        for letter, n in d["cooldowns"]:
            # the game colours these green when ready and red while cooling down
            out.append(("%s:%d" % (letter, n), th["ansi"][9] if n > 0 else th["ansi"][10]))
        for label, cur, mx in d["gauges"][1:]:              # further gauges (mana, move, ...)
            role = prompts.gauge_color_role(cur, mx)
            out.append(("%s %d/%d" % (label, cur, mx) if mx is not None else "%s %d" % (label, cur),
                        th["ansi"][{"good": 10, "warn": 11, "bad": 9}[role]]))
        for i, t in enumerate(d["text"]):
            out.append((t, th["fg"] if i == 0 else th["alert"]))
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
        hp = self.data.get("hp") if self.data else None
        txt = "%d/%d %s" % hp if hp else ""
        w = max(self.HP_W, self.bold.measure(txt) + 28)      # grows with the font
        c.configure(height=h, width=w)
        c.create_rectangle(0, 0, w - 1, h - 1, outline=th["panel_edge"], fill=th["bg"])
        if hp:
            cur, mx, _label = hp
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


class Session:
    """Everything that belongs to ONE world's connection: the socket, the byte parser, the unfinished
    line, reconnect state, command history. The App keeps one active Session and reads and writes
    these names through it (see SESSION_FIELDS), so a second world is a second Session."""

    def __init__(self, name="", host="", port=0, tls=True):
        self.name, self.host, self.port, self.tls = name, host, port, tls
        self.unread = False                    # text arrived while another world was on screen


# attributes the App forwards to its active Session
SESSION_FIELDS = (
    "q", "gen", "conn", "term", "connected", "connecting",
    "history", "hist_pos", "draft", "logfile", "last_send",
    "_retrying", "_reconnect_job", "_reconnect_at", "_quit_sent_at",
    "_line", "_last_prompt", "_pending", "_line_plain", "_line_flushed", "_line_hidden_len",
    "_flush_job", "_online_since", "_prompt_time", "_dial_mode", "_telnet_cli",
    "out", "_mid", "_sb",                      # this world's scrollback, its frame and scrollbar
)


def _session_property(name):
    def get(self):
        return getattr(self.session, name)

    def set_(self, value):
        setattr(self.session, name, value)
    return property(get, set_)


class App(worldtabs.WorldTabsMixin, dosforms.DosFormsMixin, updateui.UpdateMixin, extras.ExtrasMixin,
          toolsui.ToolsMixin, access.AccessMixin):
    def __init__(self, root, host=None, port=None):
        self.root = root
        self.cfg = self._load_settings()
        if host:
            self.cfg["host"] = host
        if port:
            self.cfg["port"] = port
            self.cfg["tls"] = (port == TLS_PORT)
        self.session = Session(host=self.cfg["host"], port=self.cfg["port"], tls=self.cfg["tls"])
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
        self._last_new_bell = 0.0
        self._img_q = queue.Queue()
        self._img_pending, self._img_polling = 0, False
        self._image_view = None
        self._extras_init()
        self._tools_init()
        self._forms_init()
        self._worlds_init()
        self._access_init()
        self._update_init()
        self._prompt_time = 0.0                       # when the last prompt arrived (for self-ticking timers)
        self._cd_job = None
        self._mono = None
        self._themed = []             # (widget, role) pairs restyled by apply_theme()
        self._tag_keys = {}           # text-tag name -> raw style key (palette refs, not hex)
        self._colors_win = None
        self.skins = dict(BUILTIN_SKINS)
        self.skins.update(load_user_skins())
        self.dos = self.cfg["ui_mode"] == "dos"      # the DOS terminal look is active
        self.dosbar = None                            # DOS status bar (built with the widgets)
        self._dosscroll = None                        # the DOS-style scrollbar (built with the widgets)
        self._overlay = None                          # the open DOS menu/dialog, if any
        self._colors_snapshot = None                  # skin state when the DOS colour screens opened
        self._dial_mode = None                        # "modem" (ATDT) / "telnet" (fake CLI) / None
        self._telnet_cli = False                      # the fake telnet command line is active
        self._worlds_win = None                       # the ordinary Worlds dialog, if open
        self._pending = []                            # [(text, style_key)] of the unfinished output line
        self._line_plain = ""                         # plain text of the current logical line
        self._line_flushed = False                    # part of this line is already on screen
        self._line_hidden_len = 0                     # leading prompt text we chose not to show
        self._flush_job = None
        self._guard = triggers.LoopGuard() if triggers is not None else None
        self._panes = {}                              # pane key (lower-case name) -> runtime dict
        self._region_ui = {}                          # region id -> {"frame": Frame, "labels": {key: Label}}
        self._region_active = {}                      # region id -> active pane key
        self._panes_active = False                    # a pane layout is in force
        self._pane_geom = None                        # last compute_layout() result
        self._framecv = None                          # DOS look: the box-drawn frame behind the panes
        self._layout_job = None
        self._dos_job = None                          # 1-second status refresh while in the DOS look
        self._online_since = 0.0
        self._fit_job = None
        self._measure_font = None
        self.theme = self._effective_theme()

        root.title(APP_NAME)
        root.configure(bg=self.theme["bg"])
        root.geometry(self.cfg.get("geometry", "1000x700"))
        self._build_fonts()
        self._build_widgets()
        self._build_menu()
        self.apply_layout()
        self.apply_theme()
        self._bind_dos_keys()
        if self.dos:
            self._start_dos_tick()
            self.update_dosbar()
        if self.cfg["fullscreen"]:
            self.set_fullscreen(True, save=False)
        root.protocol("WM_DELETE_WINDOW", self.on_quit)
        self.input.focus_set()
        self._pump_job = root.after(25, self._pump)
        root.bind("<Destroy>", self._on_root_destroy, add="+")
        self.system("%s client. Type /help for local commands, or press Connect." % APP_NAME)
        if self.cfg.get("screen_reader"):
            self.root.after(400, lambda: self.set_screen_reader(True, announce=True))
        if self.cfg.get("update_check"):
            self.root.after(6000, lambda: self.check_for_updates(manual=False))

    # ---- settings ----------------------------------------------------
    def _load_settings(self):
        cfg = {"host": DEFAULT_HOST, "port": TLS_PORT, "tls": True, "verify": True,
               "font_size": 11, "aliases": {}, "bell": True, "keepalive": True,
               "auto_reconnect": False, "statbar": True, "font_family": None,
               "skin": DEFAULT_SKIN, "skin_overrides": {},
               "ui_mode": "normal", "dos_skin": DEFAULT_DOS_SKIN, "fullscreen": False,
               "dos_autofit": True, "dos_cols": 80, "dos_flourish": True, "dos_font_size": 0,
               "dos_fit": True, "line_spacing": 0, "worlds": None,
               "prompt_profile": prompts.DEFAULT_PRESET, "prompt_custom": [],
               "triggers": [], "alias_rules": None, "hide_prompt": False,
               "panes": [], "layout": {"regions": [], "min_main_cols": 80}}
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
        self._sync_variants()

    def _font_changed(self):
        """The cell size changed: in the DOS look the column count and font fit depend on it, so
        recompute now (waiting for a window event leaves the screen mis-sized until one arrives)."""
        if self.dos:
            self.root.update_idletasks()
            self._fit_font()

    def _sync_variants(self):
        """Keep bold/italic on the same character grid as normal text. If a styled variant has a
        different advance width, drop the offending attribute (colour still shows the emphasis)."""
        base = self.f_norm.measure("0")
        for f, want in ((self.f_bold, ("bold", "roman")), (self.f_ital, ("normal", "italic")),
                        (self.f_bi, ("bold", "italic"))):
            f.configure(weight=want[0], slant=want[1])
            if f.measure("0") != base:
                f.configure(weight="normal")
                if f.measure("0") != base:
                    f.configure(slant="roman")

    def _make_session_widgets(self, s):
        """The scrollback (with its frame and scrollbar) for one world."""
        mid = self._reg(tk.Frame(self._holder), "frame")
        # height=4: the pane must REQUEST little and expand into what is left, otherwise at large
        # font sizes its default 24-row request squeezes the stat bar and input line off-screen.
        out = self._reg(tk.Text(mid, font=self.f_norm, wrap="word", state="disabled",
                                height=4, width=40, borderwidth=0, highlightthickness=0,
                                padx=8, pady=4, cursor="arrow"), "text")
        sb = self._reg(tk.Scrollbar(mid, command=out.yview), "scroll")
        out.configure(yscrollcommand=sb.set)
        out.bind("<KeyPress>", self._out_key)
        self._bind_links(out)
        out.bind("<Control-MouseWheel>", self._zoom_wheel)
        s.out, s._mid, s._sb = out, mid, sb

    def _after_session(self, ms, fn):
        """root.after for a timer that belongs to the CURRENT world: it runs with that world active."""
        s = self.session

        def run():
            prev = self.session
            self.session = s
            try:
                fn()
            finally:
                self.session = prev
            if s is not self._shown and s in self.sessions:
                self._sync_session_ui()
        return self.root.after(ms, run)

    def add_session(self, name):
        """A new, empty world (not yet shown). Returns the Session."""
        s = Session(name, self.cfg["host"], self.cfg["port"], self.cfg["tls"])
        prev, self.session = self.session, s
        try:
            s.q = queue.Queue()
            s.gen = 0
            s.conn = Connection(s.q, s.gen)
            s.term = Terminal(want_mxp=True)
            s.connected = s.connecting = False
            s.history, s.hist_pos, s.draft = [], 0, ""
            s.logfile = None
            s.last_send = time.time()
            s._retrying, s._reconnect_job, s._reconnect_at, s._quit_sent_at = False, None, 0.0, 0.0
            s._line, s._last_prompt = "", None
            s._pending, s._line_plain, s._line_flushed, s._line_hidden_len = [], "", False, 0
            s._flush_job, s._online_since, s._prompt_time = None, 0.0, 0.0
            s._dial_mode, s._telnet_cli = None, False
            self._make_session_widgets(s)
            self.sessions.append(s)
            for w, role in ((s.out, "text"), (s._sb, "scroll"), (s._mid, "frame")):
                try:
                    w.configure(**self._role_options(role))
                except tk.TclError:
                    pass
            for tag in self._tags:
                self._style_tag(tag)
            self._restyle_tags()
            self._apply_spacing()
        finally:
            self.session = prev
        return s

    def switch_session(self, s):
        """Show world `s`. Its scrollback, line state and connection become the active ones."""
        if s is self.session or s not in self.sessions:
            return
        old = self.session
        try:                                           # what was typed in the host box belongs to the world we leave
            old.host, old.port, old.tls = (self.v_host.get().strip(), int(self.v_port.get()), bool(self.v_tls.get()))
        except ValueError:
            pass
        old.draft = self.input.get()
        for w in (old._mid, old._sb, old.out):
            w.pack_forget()
            w.place_forget()
        self.session = self._shown = s
        s.unread = False
        self._dosscroll._cmd = s.out.yview
        self.apply_layout()
        if self._panes_active or self.cfg["layout"]["regions"]:
            self.schedule_layout(5)
        self.input.delete(0, "end")
        self.input.insert(0, s.draft or "")
        s.out.see("end")
        self._sync_session_ui()

    def _reg(self, widget, role):
        """Register a widget so apply_theme() can restyle it."""
        self._themed.append((widget, role))
        return widget

    def _role_options(self, role, th=None):
        th = th or self.theme
        flat = th["relief"] == "flat"
        if role == "frame":
            return dict(bg=th["bg"])
        if role == "holder":
            return dict(bg=th.get("dos_screen_border", th["bg"]) if self.dos else th["bg"])
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
        top = self._top = self._reg(tk.Frame(self.root), "panel")
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
        self._notice_text, self._notice_job = "", None
        self.notice = self._reg(tk.Label(top, text="", anchor="e"), "label")
        self.notice.pack(side="right", padx=8)
        self.pane_badge = self._reg(tk.Label(top, text="", anchor="e"), "label")
        self.pane_badge.pack(side="right", padx=8)
        self.clock_label = self._reg(tk.Label(top, text="", anchor="e"), "label")
        self.clock_label.pack(side="right", padx=8)
        self._world_label = self._reg(tk.Label(top, text="", anchor="e", cursor="hand2"), "label")
        self._world_label.bind("<Button-1>", lambda e: self.goto_world(
            self.sessions.index(self._shown) % len(self.sessions) + 1))

        # holder = the coloured "overscan" border; in the DOS look the 80-column screen is
        # centred inside it, in the normal look the screen simply fills it
        self._holder = self._reg(tk.Frame(self.root), "holder")
        self._holder.bind("<Configure>", self._on_holder_configure, add="+")
        self.sessions = [self.session]
        self._make_session_widgets(self.session)
        # the DOS scrollbar replaces the right-hand border cell (placed over it) while there is
        # something to scroll; the parent is the holder so it can sit at the very edge
        self._dosscroll = dosui.DosScrollbar(self._holder, self.out.yview, dosui.dos_colors(self.theme),
                                             self.f_norm)
        self._apply_spacing()

        self.input = self._reg(tk.Entry(self.root, font=self.f_norm, highlightthickness=1), "input")
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
        self.dosbar = dosui.DosStatusBar(self.root, dosui.dos_colors(self.theme), self.f_norm, self.f_bold)
        for w in (self.root,):
            w.bind("<F11>", self.toggle_fullscreen)
            for n in range(1, 10):
                w.bind("<Control-Key-%d>" % n, lambda e, n=n: (self.select_pane_number(n), "break")[1])
            for n in range(0, 10):
                w.bind("<Alt-Key-%d>" % n, lambda e, n=n: (self.toggle_pane_area(n), "break")[1])
            w.bind("<Alt-Return>", self.toggle_fullscreen)
            w.bind("<FocusIn>", self._on_focus_in, add="+")
            w.bind("<KeyPress>", self._overlay_key_fallback, add="+")
            w.bind("<F12>", lambda e: (self.open_about(), "break")[1])
            w.bind("<F1>", lambda e: (self.open_help(), "break")[1] if not self.dos else None)
            for seq in ("<Control-KP_Multiply>", "<Control-asterisk>"):
                w.bind(seq, lambda e: (self.adjust_contrast(+0.5), "break")[1])
            for seq in ("<Control-KP_Divide>", "<Control-slash>"):
                w.bind(seq, lambda e: (self.adjust_contrast(-0.5), "break")[1])
            w.bind("<Configure>", self._on_configure, add="+")
            w.bind("<Control-plus>", lambda e: self._zoom(+1))
            w.bind("<Control-equal>", lambda e: self._zoom(+1))
            w.bind("<Control-minus>", lambda e: self._zoom(-1))
            w.bind("<Control-l>", lambda e: self.clear())
        self._bind_hotkeys()                                   # Ctrl-T, Alt-M ... (changeable: /hotkeys)
        self._bind_world_keys()                                # Ctrl-F1 .. Ctrl-F12 pick a world
        if self.cfg.get("clock", "off") != "off":
            self._start_xtick()

    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Connect / Disconnect", command=self.toggle_connection)
        f.add_command(label="Worlds...   Ctrl+W", command=self.open_worlds)
        f.add_command(label="Prompt bar format...", command=self.edit_prompt)
        f.add_command(label="Triggers...   Ctrl+T", command=self.open_triggers)
        f.add_command(label="Aliases...   Ctrl+A", command=self.open_aliases)
        f.add_command(label="Panes / layout...   Ctrl+P", command=self.open_panes)
        f.add_command(label="Timer...   Alt+T", command=self.open_timers)
        f.add_command(label="Notepad   Alt+N", command=self.toggle_notepad)
        f.add_command(label="Moon   Alt+M", command=self.open_moon)
        f.add_command(label="Gradient maker...   Alt+G", command=self.open_gradient)
        f.add_command(label="Hex to xterm...   Alt+H", command=self.open_hex)
        f.add_command(label="Customize form...   Alt+K", command=self.open_customize)
        f.add_command(label="Export world settings...", command=self.open_export)
        f.add_command(label="Import world settings...", command=self.open_import)
        f.add_command(label="Hotkeys...", command=self.open_hotkeys)
        f.add_command(label="Help   F1", command=self.open_help)
        f.add_command(label="Check for updates...", command=self.check_for_updates)
        f.add_command(label="About...   F12", command=self.open_about)
        f.add_command(label="Start/stop logging…", command=self.toggle_log)
        f.add_command(label="Clear screen   Ctrl+L", command=self.clear)
        f.add_separator()
        f.add_command(label="Quit", command=self.on_quit)
        m.add_cascade(label="File", menu=f)
        v = tk.Menu(m, tearoff=0)
        self._view_menu = v
        self.v_skin = tk.StringVar(value=self._skin_name())
        self._skin_menu = tk.Menu(v, tearoff=0)
        v.add_cascade(label="Skin", menu=self._skin_menu)
        self._rebuild_skin_menu()
        self.v_dos = tk.BooleanVar(value=self.dos)
        self.v_full = tk.BooleanVar(value=bool(self.cfg["fullscreen"]))
        v.add_checkbutton(label="DOS terminal look   Alt+D", variable=self.v_dos,
                          command=lambda: self.set_dos_mode(self.v_dos.get()))
        v.add_checkbutton(label="Full screen   F11", variable=self.v_full,
                          command=lambda: self.set_fullscreen(self.v_full.get()))
        v.add_separator()
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
        self.v_hideprompt = tk.BooleanVar(value=self.cfg["hide_prompt"])
        o.add_checkbutton(label="Hide the prompt line (show it in the bar only)", variable=self.v_hideprompt,
                          command=lambda: self.cfg.update(hide_prompt=self.v_hideprompt.get()))
        o.add_separator()
        self._xvars = {}
        for key, _d, label, _dl, _h in EXTRA_BOOLS:
            self._xvars[key] = tk.BooleanVar(value=self.cfg[key])
            o.add_checkbutton(label=label, variable=self._xvars[key],
                              command=lambda k=key: self._set_extra(k, self._xvars[k].get()))
        for key, _d, values, label, _h in EXTRA_CHOICES:
            sub = tk.Menu(o, tearoff=0)
            self._xvars[key] = tk.StringVar(value=self.cfg[key])
            for val in values:
                sub.add_radiobutton(label=CHOICE_WORDS.get(val, val), value=val, variable=self._xvars[key],
                                    command=lambda k=key: self._set_extra(k, self._xvars[k].get()))
            o.add_cascade(label=label, menu=sub)
            self._extra_menus = getattr(self, "_extra_menus", []) + [sub]
        sri = tk.Menu(o, tearoff=0)
        cur = self.cfg.get("sr_interval", 0)
        self._sr_interval_var = tk.IntVar(value=cur if cur in (0, 10, 15, 30, 60, 120, 300) else -1)
        for secs, label in ((0, "off"), (10, "every 10 seconds"), (15, "every 15 seconds"), (30, "every 30 seconds"),
                            (60, "every minute"), (120, "every 2 minutes"), (300, "every 5 minutes")):
            sri.add_radiobutton(label=label, value=secs, variable=self._sr_interval_var,
                                command=lambda: self.set_sr_interval(self._sr_interval_var.get()))
        o.add_cascade(label="Screen reader: read def and stun...", menu=sri)
        o.add_command(label="Screen reader: combat lines...", command=self.open_combat_filter)
        self._extra_menus = getattr(self, "_extra_menus", []) + [sri]
        m.add_cascade(label="Options", menu=o)
        self._menus = [m, f, v, o, self._skin_menu] + getattr(self, "_extra_menus", [])
        self._menubar = m
        self.root.config(menu=m)

    # ---- output ------------------------------------------------------
    # ---- theme ----------------------------------------------------------
    def _skin_cfg_key(self):
        """The DOS look keeps its own skin choice, so toggling the look never disturbs the
        skin you picked for the normal look (and vice versa)."""
        return "dos_skin" if self.dos else "skin"

    def _skin_name(self):
        return self.cfg[self._skin_cfg_key()]

    def _effective_theme(self):
        """The selected skin with the user's saved edits applied (validated)."""
        key = self._skin_cfg_key()
        name = self.cfg.get(key)
        if name not in self.skins:
            name = self.cfg[key] = DEFAULT_DOS_SKIN if self.dos and DEFAULT_DOS_SKIN in self.skins \
                else DEFAULT_SKIN
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

    # ---- links ---------------------------------------------------------------------------
    _URL_RE = re.compile(r"https?://[^\s<>\"'`]+")
    _IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

    @staticmethod
    def _trim_url(url):
        """A link without the punctuation that follows it in a sentence."""
        while url and (url[-1] in ".,;:!?'\"" or (url[-1] == ")" and url.count("(") < url.count(")"))
                       or (url[-1] == "]" and url.count("[") < url.count("]"))):
            url = url[:-1]
        return url

    @staticmethod
    def find_urls(text):
        """[(start, end)] of http(s) links in `text`, without trailing punctuation."""
        out = []
        for m in App._URL_RE.finditer(text):
            url = App._trim_url(m.group())
            if len(url) > len("https://") + 1:
                out.append((m.start(), m.start() + len(url)))
        return out

    def _linkify(self, w, start):
        """Tag every link in what was just added to a text widget (from index `start`). The widget's
        own search is used so positions stay right even when emoji (two units wide) precede a link."""
        try:
            n, idx = tk.IntVar(), start
            for _ in range(200):
                pos = w.search(r"https?://[^[:space:]<>\"'`]+", idx, stopindex="end-1c", regexp=True, count=n)
                if not pos or n.get() <= 0:
                    break
                end = "%s+%dc" % (pos, n.get())
                url = self._trim_url(w.get(pos, end))
                if len(url) > len("https://") + 1:
                    w.tag_add("link", pos, "%s+%dc" % (pos, len(url)))
                idx = end
        except tk.TclError:
            pass

    def _bind_links(self, w):
        w.tag_bind("link", "<Enter>", lambda e, w=w: w.configure(cursor="hand2"))
        w.tag_bind("link", "<Leave>", lambda e, w=w: w.configure(cursor="arrow"))
        w.bind("<ButtonPress-1>", lambda e: setattr(self, "_press_xy", (e.x, e.y)), add="+")
        w.tag_bind("link", "<ButtonRelease-1>", lambda e, w=w: self._link_click(w, e))

    def _link_click(self, w, e):
        if not self.cfg.get("links", True):
            return
        px, py = getattr(self, "_press_xy", (e.x, e.y))
        if abs(e.x - px) > 4 or abs(e.y - py) > 4:                 # dragged to select text, not a click
            return
        try:
            idx = w.index("@%d,%d" % (e.x, e.y))
            r = w.tag_prevrange("link", idx + "+1c")
            if not r or not (w.compare(r[0], "<=", idx) and w.compare(idx, "<", r[1])):
                return
            url = w.get(r[0], r[1])
        except tk.TclError:
            return
        self.open_link(url)
        return "break"

    def open_link(self, url):
        """A link was clicked: pictures open in the Images pane, everything else in the browser."""
        parts = urllib.parse.urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return
        if self.cfg.get("link_images", True) and parts.path.lower().endswith(self._IMAGE_EXT):
            self._fetch_image(url)
        else:
            webbrowser.open(url)

    MAX_IMAGE_BYTES = 8 * 1024 * 1024

    def _fetch_image(self, url):
        self.system("Fetching image...")
        q = self._img_q

        def work():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Sanctuary-MUD-client"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    data = r.read(self.MAX_IMAGE_BYTES + 1)
                if not ctype.startswith("image/") or len(data) > self.MAX_IMAGE_BYTES:
                    q.put((url, None, "not an image, or bigger than 8 MB"))
                else:
                    q.put((url, data, ""))
            except Exception as e:                       # network trouble of any kind
                q.put((url, None, type(e).__name__))

        self._img_pending += 1
        threading.Thread(target=work, daemon=True).start()
        self._poll_images()

    def _poll_images(self):
        try:
            url, data, why = self._img_q.get_nowait()
        except queue.Empty:
            if self._img_pending > 0 and not self._img_polling:
                self._img_polling = True
                try:
                    self.root.after(200, self._poll_images_tick)
                except tk.TclError:
                    self._img_polling = False
            return
        self._img_pending = max(0, self._img_pending - 1)
        if data is None:
            self.system("Could not open image (%s); opening it in the browser." % why)
            webbrowser.open(url)
        elif not self.show_image(url, data):
            self.system("This client cannot display that picture format; opening it in the browser.")
            webbrowser.open(url)
        self._poll_images()

    def _poll_images_tick(self):
        self._img_polling = False
        self._poll_images()

    def show_image(self, url, data):
        """Show a picture over the main text area, scaled to fit (a viewer, not a pane: a pane can be
        tiny). Esc closes it; O or a click opens the original in the browser. False when the picture
        cannot be decoded here."""
        self.close_image_view()
        try:
            try:
                from PIL import Image, ImageTk
                im = Image.open(io.BytesIO(data))
                if im.width * im.height > 40_000_000:
                    return False
                im.load()
                src = ("pil", im, ImageTk)
                size = im.size
            except ImportError:
                import base64
                ph = tk.PhotoImage(data=base64.b64encode(data))           # PNG / GIF only without Pillow
                src = ("tk", ph, None)
                size = (ph.width(), ph.height())
        except Exception:
            return False
        th = self.theme
        frame = tk.Frame(self._holder, bd=0, highlightthickness=0, bg=th["panel"])
        name = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1][:60] or "image"
        head = tk.Label(frame, anchor="w", padx=8, font=self.f_bold, bg=th["panel"], fg=th["fg"],
                        text="%s  (%d x %d)    Esc: close    O or click: open the original in your browser"
                        % (name, size[0], size[1]))
        head.pack(fill="x")
        cv = tk.Canvas(frame, bg=th["bg"], highlightthickness=0, bd=0, takefocus=1)
        cv.pack(fill="both", expand=True)
        view = {"frame": frame, "cv": cv, "url": url, "photo": None, "job": None}

        def render(_e=None):
            view["job"] = None
            w, h = max(50, cv.winfo_width()), max(50, cv.winfo_height())
            try:
                if src[0] == "pil":
                    im2 = src[1].copy()
                    im2.thumbnail((w - 8, h - 8))                           # shrinks, never enlarges
                    photo = src[2].PhotoImage(im2)
                else:
                    f = max(1, -(-src[1].width() // (w - 8)), -(-src[1].height() // (h - 8)))
                    photo = src[1].subsample(f) if f > 1 else src[1]
            except Exception:
                return
            view["photo"] = photo
            cv.delete("all")
            cv.create_image(w // 2, h // 2, image=photo)

        def later(_e=None):
            if view["job"] is not None:
                try:
                    self.root.after_cancel(view["job"])
                except tk.TclError:
                    pass
            try:
                view["job"] = self.root.after(80, render)
            except tk.TclError:
                view["job"] = None
        cv.bind("<Configure>", later)
        cv.bind("<Escape>", lambda e: (self.close_image_view(), "break")[1])
        cv.bind("<Key-o>", lambda e: (webbrowser.open(url), "break")[1])
        cv.bind("<Key-O>", lambda e: (webbrowser.open(url), "break")[1])
        cv.bind("<Button-1>", lambda e: (webbrowser.open(url), "break")[1])
        frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        frame.lift()
        self._image_view = view
        cv.focus_set()
        self.system("Image opened: %s, %d by %d pixels. Escape closes it, O opens the original in your browser."
                    % (name, size[0], size[1]))
        return True

    def close_image_view(self):
        v = getattr(self, "_image_view", None)
        if v is None:
            return
        self._image_view = None
        if v.get("job") is not None:
            try:
                self.root.after_cancel(v["job"])
            except tk.TclError:
                pass
        try:
            v["frame"].destroy()
        except tk.TclError:
            pass
        self.root.after_idle(self.input.focus_set)

    def _text_widgets(self):
        """The main text area and every pane's text area (they share one set of colour tags)."""
        return [s.out for s in self.sessions] + [p["text"] for p in self._panes.values()]

    def _style_tag(self, name):
        key = self._tag_keys[name]
        _fg, _bg, bold, ital, ul, _inv = key
        font = {(0, 0): self.f_norm, (1, 0): self.f_bold,
                (0, 1): self.f_ital, (1, 1): self.f_bi}[(int(bold), int(ital))]
        fg, bg = self._tag_colors(key)
        for w in self._text_widgets():
            w.tag_configure(name, foreground=fg, background=bg, underline=bool(ul), font=font)
            w.tag_raise("link")

    def _restyle_tags(self):
        th = self.theme
        for name in self._tags:
            self._style_tag(name)
        for w in self._text_widgets():
            w.tag_configure("echo", foreground=ensure_contrast(th["echo"], th["bg"], th["min_contrast"]))
            w.tag_configure("system", foreground=ensure_contrast(th["system"], th["bg"], th["min_contrast"]))
            w.tag_configure("link", underline=True,
                            foreground=ensure_contrast(th["ansi"][12], th["bg"], th["min_contrast"]))
            w.tag_raise("link")
        self._style_region_ui()

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
            self._sync_variants()
            self._font_changed()
        self.statbar.set_theme(th)
        self._restyle_dosbar()
        if self.dos and self._panes_active:
            self.schedule_layout(5)

    # ---- capture panes ---------------------------------------------------------------------
    def _find_pane_def(self, key):
        for d in self.cfg["panes"]:
            if d["name"].lower() == key:
                return d
        return None

    def pane_ensure(self, name):
        """The runtime pane called `name`, creating it (and, if nothing is docked yet, a sensible
        default place for it) the first time a trigger routes a line there."""
        key = str(name).strip().lower()
        if layout is None or not key:
            return None
        pane = self._panes.get(key)
        if pane is not None:
            return pane
        d = self._find_pane_def(key)
        if d is None:
            if len(self.cfg["panes"]) >= layout.MAX_PANES:
                return None
            d = layout.validate_pane({"name": str(name).strip()})
            if d is None:
                return None
            self.cfg["panes"] = self.cfg["panes"] + [d]
        text = tk.Text(self._holder, font=self.f_norm, wrap="word", state="disabled", height=2, width=8,
                       borderwidth=0, highlightthickness=0, padx=8, pady=4, cursor="arrow")
        self._reg(text, "text")
        sb = self._reg(tk.Scrollbar(self._holder, command=text.yview), "scroll")
        dsb = dosui.DosScrollbar(self._holder, text.yview, dosui.dos_colors(self.theme), self.f_norm)
        pane = {"key": key, "text": text, "sb": sb, "dsb": dsb, "history": [], "unread": 0}
        text.configure(yscrollcommand=lambda a, b, k=key: self._on_pane_scroll(k, a, b))
        text.bind("<Button-1>", lambda e: self.root.after_idle(self.input.focus_set), add="+")
        text.bind("<KeyPress>", self._out_key)
        self._bind_links(text)
        self._panes[key] = pane
        for w, role in ((text, "text"), (sb, "scroll")):
            try:
                w.configure(**self._role_options(role))
            except tk.TclError:
                pass
        for tag in self._tags:                         # the new area needs the colour tags too
            self._style_tag(tag)
        text.tag_configure("echo"), text.tag_configure("system")
        self._restyle_tags()
        self._apply_spacing()
        if layout.find_region(self.cfg["layout"], d["name"]) is None:
            self._auto_place(d["name"])
        self._save_settings()
        self.schedule_layout()
        return pane

    def _auto_place(self, name):
        lay = self.cfg["layout"]
        if not lay["regions"]:
            self.cfg["layout"] = layout.preset_layout("Right column", [p["name"] for p in self.cfg["panes"]])
            self.system("Captured lines get their own area on the right. Change it under File > Panes / layout (Ctrl+P).")
        else:
            regions = [dict(r, panes=list(r["panes"])) for r in lay["regions"]]
            regions[0]["panes"].append(name)
            self.cfg["layout"] = layout.validate_layout(dict(lay, regions=regions),
                                                        known_panes=[p["name"] for p in self.cfg["panes"]])

    def pane_append(self, name, pieces):
        """Add one line (styled pieces) to a pane; it keeps a history, trims to its limit and counts
        unread lines while its tab is not showing."""
        pane = self.pane_ensure(name)
        if pane is None:
            return
        d = self._find_pane_def(pane["key"])
        if d is None:
            return
        pieces = [(t, k) for t, k in pieces if t]
        if self.cfg.get("connect_boxes") and boxes is not None:
            pieces = boxes.connect_pieces(pieces)
        if d["timestamps"]:
            pieces = [(time.strftime("[%H:%M] "), (self.theme["dim"], None, False, False, False, False))] + pieces
        text = pane["text"]
        at_bottom = text.yview()[1] >= 0.999
        text.configure(state="normal")
        first = text.index("end-1c")
        for t, k in pieces:
            text.insert("end", t, self._tag_for(k))
        text.insert("end", "\n")
        if self.cfg.get("links", True):
            self._linkify(text, first)
        pane["history"].append(pieces)
        over = len(pane["history"]) - d["max_lines"]
        if over > 0:
            del pane["history"][:over]
            text.delete("1.0", "%d.0" % (over + 1))
        text.configure(state="disabled")
        if at_bottom:
            text.see("end")
        if not self._pane_visible(pane["key"]):
            pane["unread"] += 1
            self._style_region_ui()

    def pane_clear(self, key):
        pane = self._panes.get(str(key).lower())
        if pane:
            pane["text"].configure(state="normal")
            pane["text"].delete("1.0", "end")
            pane["text"].configure(state="disabled")
            pane["history"].clear()
            pane["unread"] = 0
            self._style_region_ui()

    def pane_delete(self, name):
        key = str(name).strip().lower()
        pane = self._panes.pop(key, None)
        if pane:
            for w in (pane["text"], pane["sb"], pane["dsb"]):
                self._themed = [(x, r) for x, r in self._themed if x is not w]
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        self.cfg["panes"] = [d for d in self.cfg["panes"] if d["name"].lower() != key]
        self.cfg["layout"] = layout.validate_layout(
            self.cfg["layout"], known_panes=[d["name"] for d in self.cfg["panes"]])
        self._region_active = {r: k for r, k in self._region_active.items() if k != key}
        self._save_settings()
        self.schedule_layout()

    def _pane_region(self, key):
        d = self._find_pane_def(key)
        return layout.find_region(self.cfg["layout"], d["name"]) if d else None

    def _pane_visible(self, key):
        reg = self._pane_region(key)
        if reg is None or not self._panes_active or self._pane_geom is None:
            return False
        if reg["id"] not in self._pane_geom["regions"]:
            return False
        return self._active_pane_key(reg) == key

    def _active_pane_key(self, reg):
        keys = [n.lower() for n in reg["panes"]]
        cur = self._region_active.get(reg["id"])
        return cur if cur in keys else (keys[0] if keys else None)

    def select_pane(self, key):
        key = str(key).lower()
        reg = self._pane_region(key)
        if reg is None:
            return False
        self._region_active[reg["id"]] = key
        if key in self._panes:
            self._panes[key]["unread"] = 0
        self.layout_panes()
        return True

    def select_pane_number(self, n):
        names = layout.region_pane_names(self.cfg["layout"]) if layout else []
        if 1 <= n <= len(names):
            self.select_pane(names[n - 1])

    def _on_pane_scroll(self, key, first, last):
        pane = self._panes.get(key)
        if pane is None:
            return
        pane["sb"].set(first, last)
        pane["dsb"].set(first, last)
        self._pane_scroll_visibility(key)

    def _pane_scroll_visibility(self, key):
        """In the DOS look a pane's scrollbar replaces its right-hand cell, only when needed."""
        pane = self._panes.get(key)
        if pane is None or not self.dos or not self._panes_active or self._pane_geom is None:
            return
        try:
            first, last = pane["text"].yview()
            reg = self._pane_region(key)
            info = self._pane_geom["regions"].get(reg["id"]) if reg else None
            show = info is not None and self._active_pane_key(reg) == key and (first > 0.0 or last < 1.0)
            if show:
                bx, by, bw, bh = info["body"]
                pane["dsb"].place(x=bx + bw, y=by, height=bh)
                pane["dsb"].lift()
            else:
                pane["dsb"].place_forget()
        except (tk.TclError, KeyError, TypeError):
            pass

    def schedule_layout(self, delay=30):
        if self._layout_job is not None:
            try:
                self.root.after_cancel(self._layout_job)
            except tk.TclError:
                pass
        try:
            self._layout_job = self.root.after(delay, self.layout_panes)
        except tk.TclError:
            self._layout_job = None

    def _on_holder_configure(self, e):
        if e.widget is self._holder and (self._panes_active or self.cfg["layout"]["regions"]):
            self.schedule_layout()

    def _pane_cell(self):
        return max(1, self.f_norm.measure("0")), max(1, self.f_norm.metrics("linespace") + int(self.cfg["line_spacing"]))

    def _panes_extra(self):
        """(extra columns, extra rows) the docked regions take beside/above the main text, so the
        DOS font fit leaves room for them."""
        if layout is None or not self._visible_layout()["regions"]:
            return 0, 0
        cols = {"left": 0, "right": 0}
        rows = {"top": 0, "bottom": 0}
        for r in self._visible_layout()["regions"]:
            if r["side"] in cols:
                cols[r["side"]] = max(cols[r["side"]], r["size"] + (3 if self.dos else 1))
            else:
                rows[r["side"]] = max(rows[r["side"]], r["size"] + (4 if self.dos else 2))
        return sum(cols.values()), sum(rows.values())

    def layout_panes(self):
        """Place the main text and the docked pane regions. With no regions the window keeps its
        ordinary arrangement (apply_layout)."""
        self._layout_job = None
        if layout is None:
            return
        lay = self._visible_layout()
        regions = lay["regions"]
        if not regions:
            if self._panes_active:
                self._panes_active, self._pane_geom = False, None
                self._hide_pane_widgets()
                self.apply_layout()
            return
        W, H = self._holder.winfo_width(), self._holder.winfo_height()
        if W < 100 or H < 60:
            return
        cw, lh = self._pane_cell()
        if self.dos:
            res = self._dos_geometry(W, H, cw, lh, lay)
        else:
            res = layout.compute_layout(lay, W, H, cw, lh, header_h=lh + 4, gap=4, pad_x=16)
        if len(regions) != len(self.cfg["layout"]["regions"]):       # folded areas: keep the real area ids
            ids = [r["id"] for r in regions]
            fix = lambda k: ids[int(k[1:]) - 1] if k[:1] == "r" and k[1:].isdigit() and 0 < int(k[1:]) <= len(ids) else k
            res = dict(res, regions={fix(k): v for k, v in res["regions"].items()},
                       hidden=[fix(k) for k in res.get("hidden", [])])
        first_time = not self._panes_active
        self._panes_active, self._pane_geom = True, res
        mx, my, mw, mh = res["main"]
        self._mid.pack_forget()
        self._mid.place_forget()
        self._mid.place(x=mx, y=my, width=mw, height=mh)
        if first_time:
            self.out.pack_forget()
            self._sb.pack_forget()
            if self.dos:
                self.out.configure(yscrollcommand=self._on_dos_yscroll)
                self.out.pack(fill="both", expand=True)
            else:
                self.out.configure(yscrollcommand=self._sb.set)
                self._sb.pack(side="right", fill="y")
                self.out.pack(side="left", fill="both", expand=True)
        self._dosscroll.place_forget()
        self._dos_scroll_visibility()
        shown = res["regions"]
        keep_frames = set()
        sbw = max(14, int(self._sb.winfo_reqwidth() or 17))
        if not self.dos and self._framecv is not None:
            self._framecv.place_forget()
        for reg in regions:
            info = shown.get(reg["id"])
            ui = self._region_ui.get(reg["id"])
            if info is None:
                if ui:
                    ui["frame"].place_forget()
                continue
            if ui is None:
                ui = self._region_ui[reg["id"]] = {"frame": tk.Frame(self._holder), "labels": {}}
            keep_frames.add(reg["id"])
            hx, hy, hw, hh = info["header"]
            ui["frame"].place(x=hx, y=hy, width=hw, height=hh)
            ui["frame"].lift()
            self._sync_region_labels(reg, ui)
        for rid, ui in self._region_ui.items():
            if rid not in keep_frames:
                ui["frame"].place_forget()
        # pane bodies
        placed = set()
        for reg in regions:
            info = shown.get(reg["id"])
            if info is None:
                continue
            active = self._active_pane_key(reg)
            pane = self._panes.get(active) if active else None
            if pane is None:
                continue
            bx, by, bw, bh = info["body"]
            if self.dos:
                pane["text"].place(x=bx, y=by, width=max(1, bw), height=bh)
                pane["sb"].place_forget()
            else:
                pane["text"].place(x=bx, y=by, width=max(1, bw - sbw), height=bh)
                pane["sb"].place(x=bx + bw - sbw, y=by, width=sbw, height=bh)
            pane["unread"] = 0
            placed.add(active)
        for key, pane in self._panes.items():
            if key not in placed:
                pane["text"].place_forget()
                pane["sb"].place_forget()
                pane["dsb"].place_forget()
        for key in placed:
            self._pane_scroll_visibility(key)
        self._style_region_ui()

    def _dos_geometry(self, W, H, cw, lh, lay=None):
        """DOS look: whole-cell geometry with a double-line frame drawn behind it. Neighbouring
        areas share one line, so the screen reads as a single boxed page. Returns a compute_layout
        style result whose rectangles are the inside (text) areas."""
        C, R = max(1, W // cw), max(1, H // lh)
        res = layout.compute_layout(lay or self.cfg["layout"], C * cw, R * lh, cw, lh, header_h=3 * lh, gap=0,
                                    pad_x=2 * cw)

        def cells(rect):
            x, y, w, h = rect
            return [int(round(x / cw)), int(round(y / lh)), int(round((x + w) / cw)), int(round((y + h) / lh))]

        def grow(c):                                       # overlap the neighbour's edge by one cell
            return [c[0] - 1 if c[0] > 0 else 0, c[1] - 1 if c[1] > 0 else 0, min(c[2], C), min(c[3], R)]

        main = grow(cells(res["main"]))
        regs = {rid: grow(cells(info["rect"])) for rid, info in res["regions"].items()}

        def inner(c, header=False):
            x0, y0, x1, y1 = c[0] + 1, c[1] + 1, c[2] - 1, c[3] - 1
            if header:
                return ((x0 * cw, y0 * lh, max(0, x1 - x0) * cw, lh),
                        (x0 * cw, (y0 + 1) * lh, max(0, x1 - x0) * cw, max(0, y1 - y0 - 1) * lh))
            return (x0 * cw, y0 * lh, max(0, x1 - x0) * cw, max(0, y1 - y0) * lh)

        out = {"main": inner(main), "regions": {}, "hidden": res["hidden"], "notes": res["notes"]}
        for rid, c in regs.items():
            hd, bd = inner(c, True)
            out["regions"][rid] = {"rect": (c[0] * cw, c[1] * lh, (c[2] - c[0]) * cw, (c[3] - c[1]) * lh),
                                   "header": hd, "body": bd}
        if self._framecv is None:
            self._framecv = tk.Canvas(self._holder, bd=0, highlightthickness=0)
        fc = self._framecv
        th = self.theme
        fc.configure(bg=th["bg"])
        fc.place(x=0, y=0, width=W, height=H)
        tk.Misc.lower(fc)
        fc.delete("all")
        colour = ensure_contrast(self._dc()["dos_menu_fg"], th["bg"], 4.5)
        for r, row in enumerate(dosui.box_cells(C, R, [main] + list(regs.values()))):
            for m in re.finditer(r"[^ ]+", row):
                fc.create_text(m.start() * cw, r * lh, text=m.group(), anchor="nw", fill=colour, font=self.f_norm)
        return out

    # ---- hiding panes ------------------------------------------------------------------------
    def _visible_layout(self):
        """The layout without the areas the user has folded away."""
        lay = self.cfg["layout"]
        hidden = set(self.cfg.get("panes_hidden", []))
        if not hidden:
            return lay
        return dict(lay, regions=[r for r in lay["regions"] if r["id"] not in hidden])

    def toggle_region(self, rid):
        hidden = list(self.cfg.get("panes_hidden", []))
        if rid in hidden:
            hidden.remove(rid)
        elif any(r["id"] == rid for r in self.cfg["layout"]["regions"]):
            hidden.append(rid)
        self.cfg["panes_hidden"] = hidden
        self._save_settings()
        self.layout_panes()
        self._update_badge()

    def toggle_pane_area(self, n):
        """Alt+1..9: fold away / bring back the area holding the nth pane. Alt+0: every area."""
        if layout is None:
            return
        if n == 0:
            ids = [r["id"] for r in self.cfg["layout"]["regions"]]
            hidden = set(self.cfg.get("panes_hidden", []))
            self.cfg["panes_hidden"] = [] if hidden >= set(ids) and ids else ids
            self._save_settings()
            self.layout_panes()
            self._update_badge()
            return
        names = layout.region_pane_names(self.cfg["layout"])
        if 1 <= n <= len(names):
            reg = layout.find_region(self.cfg["layout"], names[n - 1])
            if reg is not None:
                self.toggle_region(reg["id"])

    def unseen_summary(self):
        """'OOC*3 Tells*1': panes with unread lines that are not on screen right now."""
        out = []
        for key, pane in self._panes.items():
            if pane["unread"] > 0 and not self._pane_visible(key):
                d = self._find_pane_def(key)
                out.append("%s*%d" % (d["title"] if d else key, pane["unread"]))
        return " ".join(out)

    def _update_badge(self):
        text = self.unseen_summary()
        try:
            self.pane_badge.configure(text=("Unread: " + text) if text else "")
        except (tk.TclError, AttributeError):
            pass
        self.update_dosbar()

    def _update_badge_quiet(self):
        try:
            text = self.unseen_summary()
            self.pane_badge.configure(text=("Unread: " + text) if text else "")
        except (tk.TclError, AttributeError):
            pass

    def _hide_pane_widgets(self):
        if self._framecv is not None:
            self._framecv.place_forget()
        for pane in self._panes.values():
            for w in (pane["text"], pane["sb"], pane["dsb"]):
                w.place_forget()
        for ui in self._region_ui.values():
            ui["frame"].place_forget()

    def _sync_region_labels(self, reg, ui):
        want = [n.lower() for n in reg["panes"]]
        for key in list(ui["labels"]):
            if key not in want:
                ui["labels"].pop(key).destroy()
        for name in reg["panes"]:
            key = name.lower()
            if key not in ui["labels"]:
                lbl = tk.Label(ui["frame"], padx=6, cursor="hand2")
                lbl.bind("<Button-1>", lambda e, k=key: self.select_pane(k))
                ui["labels"][key] = lbl
        if "hide" not in ui:
            hb = tk.Label(ui["frame"], text=" \u25bc " if not self.dos else " - ", padx=2, cursor="hand2")
            hb.bind("<Button-1>", lambda e, r=reg["id"]: self.toggle_region(r))
            ui["hide"] = hb
        ui["hide"].pack_forget()
        ui["hide"].pack(side="right", fill="y")
        for lbl in ui["labels"].values():
            lbl.pack_forget()
        for key in want:
            ui["labels"][key].pack(side="left", fill="y")
        if not want:
            empty = ui["labels"].setdefault("", tk.Label(ui["frame"], text=" (no panes) ", padx=6))
            empty.pack(side="left")
        elif "" in ui["labels"]:
            ui["labels"].pop("").destroy()

    def _style_region_ui(self):
        """Tab headers: the active tab is highlighted, tabs with unread lines say how many."""
        self._update_badge_quiet()
        if not self._region_ui:
            return
        th = self.theme
        if self.dos:
            c = self._dc()
            base_bg, base_fg = c["dos_bar2_bg"], c["dos_bar2_fg"]
            act_bg, act_fg = c["dos_menu_sel_bg"], c["dos_menu_sel_fg"]
            alert = c["dos_key_fg"]
        else:
            base_bg, base_fg = th["panel"], th["fg"]
            act_bg, act_fg = th["select"], th["fg"]
            alert = th["alert"]
        for reg in (self.cfg["layout"]["regions"] if layout else []):
            ui = self._region_ui.get(reg["id"])
            if not ui:
                continue
            try:
                ui["frame"].configure(bg=base_bg)
                active = self._active_pane_key(reg)
                if "hide" in ui:
                    ui["hide"].configure(bg=base_bg, fg=base_fg, font=self.f_norm)
                for key, lbl in ui["labels"].items():
                    d = self._find_pane_def(key) if key else None
                    title = d["title"] if d else ""
                    unread = self._panes[key]["unread"] if key in self._panes else 0
                    text = " %s%s " % (title, "*%d" % unread if unread else "")
                    if not key:
                        continue
                    is_act = key == active
                    lbl.configure(text=text, font=self.f_bold if unread else self.f_norm,
                                  bg=act_bg if is_act else base_bg,
                                  fg=act_fg if is_act else (alert if unread else base_fg))
            except tk.TclError:
                pass

    # ---- look: layout, DOS mode, full screen, font fit ------------------------
    def apply_layout(self):
        """Arrange the window for the current look. Normal: toolbar, text, stat bar, input.
        DOS: no toolbar/menu bar/scrollbar; a centred N-column screen on a coloured border,
        the input line and the DOS status bar underneath."""
        for w in (self._top, self._holder, self.statbar, self.input, self.dosbar,
                  getattr(self.dosbar, "top", None)):
            if w is not None:
                w.pack_forget()
        self._mid.pack_forget()
        self._mid.place_forget()
        self._sb.pack_forget()
        self._dosscroll.place_forget()
        self.out.pack_forget()
        if self.dos:
            self.root.config(menu="")                              # no menu bar
            if self.dosbar is not None:
                self.dosbar.top.pack(fill="x")                     # the hotkey row sits on top, like a menu bar
            self._holder.pack(fill="both", expand=True)
            self._mid.place(relx=0.5, rely=0.0, anchor="n", relheight=1.0)
            self.out.configure(yscrollcommand=self._on_dos_yscroll)
            self.out.configure(width=self._dos_cols_now())
            self.out.pack(fill="both", expand=True)
            self.input.pack(fill="x", ipady=2)
            if self.dosbar is not None:
                self.dosbar.pack(fill="x")
            self._dos_scroll_visibility()
            self._panes_active = False
        else:
            self._panes_active = False
            self.root.config(menu=self._menubar)
            self._top.pack(fill="x")
            self._holder.pack(fill="both", expand=True)
            self._mid.pack(fill="both", expand=True)
            self.out.configure(yscrollcommand=self._sb.set)
            self._sb.pack(side="right", fill="y")
            self.out.configure(width=40)
            self.out.pack(side="left", fill="both", expand=True)
            self.input.pack(fill="x", ipady=5)
            self._statbar_show()

    # ---- DOS look: status bar, menus, dialogs, keys --------------------------------
    def _dc(self):
        """Colours for the DOS widgets. Text fields inside a dialog must stand out from the
        dialog itself, even when the skin's input colour equals the dialog colour."""
        c = dosui.dos_colors(self.theme)
        menu = c["dos_menu_bg"]
        if contrast_ratio(c["input_bg"], menu) < 1.6:
            c["input_bg"] = "#000000" if rel_luminance(menu) < 0.5 else "#ffffff"
            c["input_fg"] = ensure_contrast(c["input_fg"], c["input_bg"], 7.0)
        # every text colour must be readable on the background it is drawn on (user skins and
        # edited colours can break this); the key colour is used on three backgrounds at once
        for fg, bg, ratio in (("dos_bar_fg", "dos_bar_bg", 4.5), ("dos_bar2_fg", "dos_bar2_bg", 4.5),
                              ("dos_menu_fg", "dos_menu_bg", 4.5), ("dos_menu_sel_fg", "dos_menu_sel_bg", 4.5),
                              ("dos_menu_dim", "dos_menu_bg", 3.0)):
            c[fg] = ensure_contrast(c[fg], c[bg], ratio)
        bgs = (c["dos_bar_bg"], c["dos_bar2_bg"], c["dos_menu_bg"])
        cands = [c["dos_key_fg"]] + [ensure_contrast(c["dos_key_fg"], b, 4.5) for b in bgs] + ["#000000", "#ffffff"]
        c["dos_key_fg"] = max(cands, key=lambda k: (min(contrast_ratio(k, b) for b in bgs) >= 4.5,
                                                    cands[0] == k, min(contrast_ratio(k, b) for b in bgs)))
        return c

    def _restyle_dosbar(self):
        if self.dosbar is not None:
            try:
                self.dosbar.restyle(self._dc(), self.f_norm, self.f_bold)
            except tk.TclError:
                pass
        if self._dosscroll is not None:
            self._dosscroll.restyle(self._dc(), self.f_norm)
        for pane in self._panes.values():
            pane["dsb"].restyle(self._dc(), self.f_norm)
        if self._overlay_open():
            # an open menu/dialog caches the cell size: re-measure it when the font or theme changes
            try:
                self._overlay.restyle(self._dc(), self.f_norm)
            except (tk.TclError, AttributeError, TypeError):
                pass

    def _start_dos_tick(self):
        if self._dos_job is None:
            self._dos_tick()

    def _dos_tick(self):
        self._dos_job = None
        if not self.dos:
            return
        self.update_dosbar()
        try:
            self._dos_job = self.root.after(1000, self._dos_tick)
        except tk.TclError:
            pass

    def _dos_segments(self, avail):
        """Status-row content that fits in `avail` character cells. Items are ranked by
        importance (connection, HP, clock, cooldowns, counters, flags, extras, skin name) and
        added while they fit; they are then shown in a stable, readable order."""
        port = self.v_port.get().strip()
        host = self.v_host.get().strip()
        shown = host if port in ("3000", "3001") else "%s:%s" % (host, port)
        if self.connected:
            cands = [(1, 0, "ONLINE " + shown, "good")]
        elif self.connecting:
            cands = [(1, 0, "CONNECTING " + shown, "warn")]
        elif self._retrying:
            cands = [(1, 0, "REDIAL in %ds" % max(0, int(self._reconnect_at - time.time() + 0.999)), "warn")]
        else:
            cands = [(1, 0, "OFFLINE", "dim")]
        if self._notice_text:
            cands.append((1, 5.9, self._notice_text[:max(10, avail // 2)], "key"))      # just left of TLS / ANSI
        unseen = self.unseen_summary()
        if unseen:
            cands.append((2, 0.6, "Unread: " + unseen, "warn"))
        tseg = self.timer_segment()
        if tseg:
            cands.append((2, 0.7, "Timer " + tseg, "key"))
        pr = self._prompt_view() if self.connected else None
        if pr and pr.get("hp"):
            cur, mx, label = pr["hp"]
            gauge, role = dosui.gauge_text(cur, mx, 8)
            cands.append((2, 1, "%s %s %d/%d" % (label, gauge, cur, mx), role))
            # the combat readout is one group beside HP: stun and the other counters, then the timers
            for i, (lb, n) in enumerate(pr["counters"]):
                role = {"dim": "dim", "normal": "normal", "warn": "warn", "bad": "bad"}[stun_role(n)] \
                    if lb.upper() == "ST" else ("warn" if n else "dim")
                cands.append((3, 2.1 + 0.1 * i, "%s%d" % (lb, n), role, True))
            for i, (lb, n) in enumerate(pr["cooldowns"]):
                cands.append((4, 2.5 + 0.1 * i, "%s:%d" % (lb, n), "bad" if n > 0 else "good", True))
            for label, cur, mx in pr["gauges"][1:]:
                g, role = prompts.gauge_color_role(cur, mx), None
                cands.append((6, 6, "%s %d/%d" % (label, cur, mx) if mx is not None else "%s %d" % (label, cur),
                              g if g in ("good", "warn", "bad") else "normal"))
            if pr["text"]:
                cands.append((7, 5, " ".join(pr["text"]), "normal"))
        cands.append((6, 6, ("TLS " if self.v_tls.get() else "") + ("ANSI-MXP" if (self.connected and self.term.mxp) else "ANSI"),
                      "dim"))
        chosen, used = [], 0
        for c in sorted(cands, key=lambda c: (c[0], c[1])):
            prio, order, text, role = c[:4]
            join = len(c) > 4 and c[4]
            cost = len(text) + (1 if join else 3 if chosen else 0)    # 3 = the " | " separator
            if used + cost <= avail:
                chosen.append((order, text, role, join))
                used += cost
        chosen.sort(key=lambda c: c[0])
        tail = " ".join(x for x in (self.clock_text(),
                                    dosui.format_duration(time.time() - self._online_since) if self.connected else "") if x)
        return [(t, r, j) if j else (t, r) for _o, t, r, j in chosen], tail

    def update_dosbar(self):
        """Fill the two status rows from the live connection / prompt state."""
        bar = self.dosbar
        if bar is None or not self.dos or not self._here():
            return
        try:
            up = self.connected or self.connecting
            bar.set_hints(self.world_hints() +
                          [("F1", "Help", 8), ("F2", "Hangup" if up else "Dial", 7), ("F3", "Log", 3),
                           ("F5", "Skin", 4), ("F6", "Colours", 5), ("F7", "Font", 5), ("F10", "Menu", 9),
                           ("F11", "Full", 6), ("F12", "About", 2), ("^W", "Worlds", 1)],
                           right="Alt-D Normal  Alt-X Exit")
            cw = max(1, self.f_norm.measure("0"))
            cols = int(bar.winfo_width() / cw) if bar.winfo_width() > 100 else int(self.cfg["dos_cols"])
            segs, tail = self._dos_segments(max(20, cols - 2))
            bar.set_segments(segs, right=tail)
        except tk.TclError:
            pass

    def _overlay_open(self):
        o = self._overlay
        try:
            return o is not None and bool(o.is_open())
        except tk.TclError:
            return False

    def dos_close_overlay(self):
        if self._overlay_open():
            try:
                self._overlay.close()
            except tk.TclError:
                pass
        self._overlay = None

    def _cell(self):
        return self.f_norm.measure("0"), self.f_norm.metrics("linespace")

    def _dos_menu(self, title, items, corner=False, initial=None, back=None):
        kw = {} if initial is None else {"initial": initial}
        if back is not None:
            # a menu closes (and so goes `back`) before it runs the chosen entry; only go back if nothing was chosen
            chosen = [False]
            for it in items:
                if it is not None and it.get("action") is not None:
                    def mark(orig=it["action"]):
                        chosen[0] = True
                        return orig()
                    it["action"] = mark
            kw["on_close"] = lambda: self.root.after_idle(lambda: None if chosen[0] else self._reopen(back))
        m = dosui.DosMenu(self.root, title, items, self._dc(), self.f_norm, **kw)
        self._overlay = m
        if corner:
            cw, ch = self._cell()
            m.open(x=2 * cw, y=ch)
        else:
            m.open()
        return m

    def _dos_dialog(self, title, fields, buttons, on_result, **kw):
        d = dosui.DosDialog(self.root, title, fields, buttons, self._dc(), self.f_norm, on_result, **kw)
        self._overlay = d
        d.open()
        return d

    def dos_main_menu(self):
        up = self.connected or self.connecting or self._retrying
        items = [
            {"label": "Disconnect" if up else "Connect", "hotkey": "C", "shortcut": "F2",
             "action": self.toggle_connection},
            {"label": "Connection settings...", "hotkey": "S", "action": self.dos_connect_dialog},
            {"label": "Worlds...", "hotkey": "W", "shortcut": "Ctrl-W", "action": self.open_worlds},
            {"label": "Prompt bar format...", "hotkey": "B", "action": self.edit_prompt},
            {"label": "Triggers...", "hotkey": "T", "shortcut": "Ctrl-T", "action": self.open_triggers},
            {"label": "Aliases...", "hotkey": "A", "shortcut": "Ctrl-A", "action": self.open_aliases},
            {"label": "Panes / layout...", "hotkey": "V", "shortcut": "Ctrl-P", "action": self.open_panes},
            {"label": "Tools  >", "hotkey": "M", "action": self.dos_tools_menu},
            None,
            {"label": "Log to file", "hotkey": "L", "shortcut": "F3", "checked": bool(self.logfile),
             "action": self.toggle_log},
            {"label": "Clear screen", "hotkey": "E", "shortcut": "Ctrl-L", "action": self.clear},
            None,
            {"label": "Skin...", "hotkey": "K", "shortcut": "F5", "action": self.dos_skin_menu},
            {"label": "Colours...", "hotkey": "O", "shortcut": "F6", "action": self.edit_colors},
            {"label": "Font...", "hotkey": "F", "shortcut": "F7", "action": self.choose_font},
            None,
            {"label": "Options...", "hotkey": "P", "action": self.dos_options_menu},
            {"label": "Full screen", "hotkey": "U", "shortcut": "F11",
             "checked": bool(self.cfg["fullscreen"]), "action": self.toggle_fullscreen},
            {"label": "Normal look", "hotkey": "N", "shortcut": "Alt-D",
             "action": lambda: self.set_dos_mode(False)},
            None,
            {"label": "About", "shortcut": "F12", "action": self.open_about},
            {"label": "Help", "hotkey": "H", "shortcut": "F1", "action": self.dos_help},
            {"label": "Exit", "hotkey": "X", "shortcut": "Alt-X", "action": self.dos_confirm_quit},
        ]
        return self._dos_menu(APP_NAME, items, corner=True)

    def dos_tools_menu(self):
        items = [
            {"label": "Timer...", "hotkey": "T", "shortcut": "Alt-T", "action": self.open_timers},
            {"label": "Notepad", "hotkey": "N", "shortcut": "Alt-N", "action": self.toggle_notepad},
            {"label": "Moon", "hotkey": "M", "shortcut": "Alt-M", "action": self.open_moon},
            {"label": "Gradient maker...", "hotkey": "G", "shortcut": "Alt-G", "action": self.open_gradient},
            {"label": "Hex to xterm...", "hotkey": "H", "shortcut": "Alt-H", "action": self.open_hex},
            {"label": "Customize form...", "hotkey": "C", "shortcut": "Alt-K", "action": self.open_customize},
            None,
            {"label": "Export world settings...", "hotkey": "E", "action": self.open_export},
            {"label": "Import world settings...", "hotkey": "I", "action": self.open_import},
            {"label": "Hotkeys...", "hotkey": "K", "action": self.open_hotkeys},
            {"label": "Check for updates...", "hotkey": "U", "action": self.check_for_updates},
        ]
        return self._dos_menu("Tools", items, back=self.dos_main_menu)

    def dos_skin_menu(self, after=None):
        cur = self._skin_name()

        def pick(n):
            self.set_skin(n)
            if after is not None:
                self.root.after_idle(after)

        items = [{"label": name, "hotkey": str(i + 1) if i < 9 else None, "checked": name == cur,
                  "action": (lambda n=name: pick(n))} for i, name in enumerate(self.skins)]
        return self._dos_menu("Skin", items, back=after)

    def _toggle_option(self, key, index=0):
        if key in {k for k, *_ in EXTRA_BOOLS}:
            self._set_extra(key, not self.cfg[key])
            self.root.after_idle(lambda: self.dos_options_menu(initial=index))
            return
        new = not self.cfg[key]
        self.cfg[key] = new
        var = {"verify": "v_verify", "bell": "v_bell", "keepalive": "v_keep",
               "auto_reconnect": "v_auto", "hide_prompt": "v_hideprompt"}.get(key)
        if var:
            getattr(self, var).set(new)
        if key == "auto_reconnect":
            self._auto_toggled()
        elif key in ("dos_autofit", "dos_fit"):
            self._fit_font()
        self._save_settings()
        self.root.after_idle(lambda: self.dos_options_menu(initial=index))     # stay in the menu to flip several

    def dos_options_menu(self, initial=0):
        if not self.dos or self._overlay_open():
            return None
        rows = [("Verify TLS certificate", "V", "verify"), ("Beep on server bell", "B", "bell"),
                ("Send keep-alive", "K", "keepalive"), ("Auto-reconnect", "R", "auto_reconnect"),
                ("Auto-fit font to screen", "A", "dos_autofit"),
                ("Hide prompt line (bar only)", "H", "hide_prompt"),
                ("Screen width follows window", "W", "dos_fit"),
                ("Dial / connect messages", "D", "dos_flourish")]
        items = []
        for lbl, hk, k in rows:
            i = len(items)
            items.append({"label": lbl, "hotkey": hk, "checked": bool(self.cfg[k]),
                          "action": (lambda k=k, i=i: self._toggle_option(k, i))})
        for k, _d, _l, dl, hk in EXTRA_BOOLS:
            i = len(items)
            items.append({"label": dl, "hotkey": hk, "checked": bool(self.cfg[k]),
                          "action": (lambda k=k, i=i: self._toggle_option(k, i))})
        for k, _d, values, label, hk in EXTRA_CHOICES:
            i = len(items)
            items.append({"label": "%s: %s" % (label, CHOICE_WORDS.get(self.cfg[k], self.cfg[k])), "hotkey": hk,
                          "action": (lambda k=k, v=values, i=i: self._cycle_choice(k, v, i))})
        return self._dos_menu("Options", items, initial=initial)

    def _cycle_choice(self, key, values, index=0):
        cur = self.cfg[key]
        self._set_extra(key, values[(values.index(cur) + 1) % len(values)] if cur in values else values[0])
        self.root.after_idle(lambda: self.dos_options_menu(initial=index))

    def _set_extra(self, key, value):
        """One of the EXTRA options changed (from either menu)."""
        self.cfg[key] = value
        var = getattr(self, "_xvars", {}).get(key)
        if var is not None and var.get() != value:
            var.set(value)
        if key == "clock":
            self._start_xtick()
            self._update_clock()
        if key == "screen_reader":
            self.set_screen_reader(bool(value))
            return
        if key == "sr_voice" and self.sr_on():
            self.set_screen_reader(True, announce=True)
        if key == "links" and not value:
            for w in self._text_widgets():
                w.tag_remove("link", "1.0", "end")
        self._save_settings()

    def dos_connect_dialog(self):
        fields = [{"key": "host", "label": "Host", "type": "text", "value": self.v_host.get(), "width": 30},
                  {"key": "port", "label": "Port", "type": "text", "value": self.v_port.get(), "width": 6},
                  {"key": "tls", "label": "Use TLS", "type": "check", "value": bool(self.v_tls.get())}]
        buttons = [("Connect", "connect"), ("Save", "save"), ("Cancel", "cancel")]
        return self._dos_dialog("Connection", fields, buttons, self._dos_connect_result, width=52,
                                message="Where do you want to go?")

    def _dos_connect_result(self, result, values):
        if result not in ("connect", "save"):
            return
        host = str(values.get("host", "")).strip() or self.v_host.get().strip()
        try:
            port = int(str(values.get("port", "")).strip())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.system("Port must be a number from 1 to 65535.")
            return
        tls = bool(values.get("tls"))
        self.v_host.set(host)
        self.v_port.set(str(port))
        self.v_tls.set(tls)
        self.cfg.update(host=host, port=port, tls=tls)
        self._save_settings()
        if result == "connect":
            if self.connected or self.connecting:
                self._local("/reconnect")
            else:
                self._cancel_reconnect()
                self.toggle_connection()
        self.update_dosbar()

    def help_key_lines(self):
        """[(keys, what it does)] built from the real key table, so it can never go stale."""
        fixed = [("F1", "This help"), ("F2", "Connect / disconnect"), ("F3", "Log to file"), ("F5", "Skin"),
                 ("F6", "Colours"), ("F7", "Font"), ("F10", "Main menu"), ("F11", "Full screen"),
                 ("F12", "About"), ("Alt-X", "Exit"), ("PgUp / PgDn", "Scroll back"),
                 ("Up / Down", "Command history"), ("Ctrl-L", "Clear the screen"), ("Ctrl +/-", "Font size"),
                 ("Ctrl-1..9", "Show a pane's tab"), ("Alt-1..9", "Fold a pane area"), ("Alt-0", "Fold all areas"),
                 ("Ctrl-*", "More text contrast"), ("Ctrl-/", "Less text contrast"),
                 ("Alt-Left", "Back (menus, forms)"), ("Alt-Right", "Next / into a list"),
                 ("Ctrl-G", "Gradient in a text page"), ("Ctrl-K", "Strip colours there")]
        titles = {"worlds": "Worlds", "triggers": "Triggers", "aliases": "Aliases", "panes": "Panes",
                  "moon": "The moon", "notepad": "Notepad", "timers": "Timer", "dos_toggle": "DOS look",
                  "gradient": "Gradient maker", "hex": "Hex to xterm", "customize": "Customize form"}
        changeable = [(shown, titles[a]) for a, _t, shown in self.hotkey_table() if a in titles]
        out = fixed + changeable
        if self.sr_on():
            out += [(shown, t) for a, t, shown in self.hotkey_table() if a.startswith("sr_")]
        return out

    HELP_COMMANDS = (
        ("/connect [host [port]]", "connect;  /disconnect  /reconnect  /quit"),
        ("/world [n|name]", "switch world (Ctrl+F1..F12);  /newworld [name]  /closeworld"),
        ("/triggers  /alias", "triggers and aliases (/alias name body, /unalias, /aliases)"),
        ("/timer 10m [label]", "a timer; also 21:30, game 21:30, list, cancel [n]"),
        ("/moon  /notes", "the moon window; the notepad"),
        ("/hex ff8800", "nearest xterm colour;  /gradient [text]  /customize"),
        ("/export  /import", "world settings files (.snc)"),
        ("/update", "check for a newer Sanctuary"),
        ("/sr on|off|help", "screen reader mode;  /hotkeys changes keys"),
        ("/log [file]  /clear", "logging; clear the screen"),
        ("//text", "send '/text' to the game"),
    )

    def help_text(self):
        lines = ["Keys"]
        lines += ["  %-14s %s" % kv for kv in self.help_key_lines()]
        lines += ["", "Commands (type them in the input line)"]
        lines += ["  %-22s %s" % kv for kv in self.HELP_COMMANDS]
        return "\n".join(lines)

    def open_help(self):
        if self.dos:
            return self.dos_help()
        top = tk.Toplevel(self.root)
        top.title("Help")
        top.transient(self.root)
        txt = tk.Text(top, width=88, height=34, wrap="none", font=self.f_norm)
        sb = tk.Scrollbar(top, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", self.help_text())
        txt.configure(state="disabled")
        top.bind("<Escape>", lambda e: top.destroy())
        self._theme_tree(top)
        txt.focus_set()
        return top

    def dos_help(self, page=1):
        if self._overlay_open():
            return None
        if page == 1:
            keys = self.help_key_lines()
            half = (len(keys) + 1) // 2
            left, right = keys[:half], keys[half:]
            rows = []
            for i in range(half):
                a = "%-11s %-24s" % left[i] if i < len(left) else ""
                b = "%-11s %s" % right[i] if i < len(right) else ""
                rows.append(dosui.PRE + (a + " " + b).rstrip())
            text, buttons = "\n".join(rows), [("Commands", "more"), ("Close", "close")]
        else:
            text = "\n".join(dosui.PRE + "%-22s %s" % kv for kv in self.HELP_COMMANDS)
            buttons = [("Keys", "more"), ("Close", "close")]

        def result(res, _v):
            if res == "more":
                self._reopen(self.dos_help, 2 if page == 1 else 1)
        self._overlay = dosui.show_message(self.root, "Help: keys" if page == 1 else "Help: commands", text,
                                           self._dc(), self.f_norm, buttons=buttons, on_result=result)
        return self._overlay

    def dos_confirm_quit(self):
        self._overlay = dosui.confirm(self.root, "Exit", "Disconnect and exit %s?" % APP_NAME,
                                      self._dc(), self.f_norm,
                                      lambda r, v: self.on_quit() if r == "yes" else None)
        return self._overlay

    # ---- prompt profiles ---------------------------------------------------------------
    def all_profiles(self):
        d = {n: prompts.get_preset(n) for n in prompts.PRESETS}
        for p in self.cfg["prompt_custom"]:
            d[p["name"]] = p
        return d

    def current_profile(self):
        profiles = self.all_profiles()
        return profiles.get(self.cfg["prompt_profile"]) or profiles[prompts.DEFAULT_PRESET]

    def set_prompt_profile(self, name):
        if name not in self.all_profiles():
            return False
        self.cfg["prompt_profile"] = name
        self._last_prompt = None
        self._update_statbar()                      # re-read the line that is on screen right now
        self.update_dosbar()
        self._save_settings()
        return True

    def save_prompt_profile(self, profile):
        """Validate and store a custom profile, then select it. Returns (ok, message)."""
        prof = prompts.validate_profile(profile)
        if prof is None or prof["kind"] != "regex":
            ok, msg, _r = prompts.check_profile(profile, "x")
            return False, msg if not ok and "problem" in msg.lower() else "That profile cannot be used."
        if prof["name"].lower() in (n.lower() for n in prompts.PRESETS):
            return False, "'%s' is a built-in name; pick another." % prof["name"]
        custom = [c for c in self.cfg["prompt_custom"] if c["name"].lower() != prof["name"].lower()]
        if len(custom) >= 20:
            return False, "Too many custom prompt profiles (20 maximum)."
        custom.append(prof)
        self.cfg["prompt_custom"] = custom
        self.set_prompt_profile(prof["name"])
        return True, "Saved '%s'." % prof["name"]

    def delete_prompt_profile(self, name):
        before = len(self.cfg["prompt_custom"])
        self.cfg["prompt_custom"] = [c for c in self.cfg["prompt_custom"] if c["name"] != name]
        if self.cfg["prompt_profile"] == name:
            self.set_prompt_profile(prompts.DEFAULT_PRESET)
        else:
            self._save_settings()
        return len(self.cfg["prompt_custom"]) < before

    @staticmethod
    def profile_from_fields(name, pattern, gauges, counters, cooldowns, text, sample):
        """Build a regex profile from the editor's text fields. Returns (profile_or_None, message)."""
        lists, err = prompts.parse_specs(gauges, counters, cooldowns, text)
        if err:
            return None, err
        prof = {"name": name, "kind": "regex", "pattern": pattern, "sample": sample, **lists}
        ok, msg, _res = prompts.check_profile(prof, sample or "x")
        if prompts.validate_profile(prof) is None:
            return None, msg
        return prof, msg

    def edit_prompt(self):
        """Choose / edit the prompt-bar format (ordinary window)."""
        if self.dos:
            return self.dos_prompt_menu()
        top = tk.Toplevel(self.root)
        top.title("Prompt bar")
        top.transient(self.root)
        profiles = self.all_profiles()
        names = list(profiles) + ["New custom..."]
        cur = self.cfg["prompt_profile"] if self.cfg["prompt_profile"] in profiles else prompts.DEFAULT_PRESET
        var = tk.StringVar(value=cur)
        tk.Label(top, text="The prompt bar reads the game's prompt line. Pick a format, or design your own.",
                 wraplength=520, justify="left").grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 4))
        tk.Label(top, text="Format").grid(row=1, column=0, sticky="w", padx=(10, 6), pady=4)
        opt = tk.OptionMenu(top, var, *names, command=lambda n: load(n))
        opt.grid(row=1, column=1, sticky="w", pady=4)
        fields = {}
        rows = (("name", "Name", 30), ("pattern", "Pattern", 60), ("gauges", "Gauges", 60),
                ("counters", "Counters", 60), ("cooldowns", "Cooldowns", 60), ("text", "Text", 60),
                ("sample", "Sample line", 60))
        for r, (key, label, width) in enumerate(rows, start=2):
            tk.Label(top, text=label).grid(row=r, column=0, sticky="w", padx=(10, 6), pady=3)
            sv = tk.StringVar()
            e = tk.Entry(top, textvariable=sv, width=width)
            e.grid(row=r, column=1, sticky="w", pady=3, padx=(0, 10))
            fields[key] = (sv, e)
        tk.Label(top, justify="left", wraplength=520,
                 text="Pattern: a regular expression with named groups, e.g. (?P<hp>[0-9]+)/(?P<hpmax>[0-9]+)\n"
                      "Gauges: HP=hp/hpmax, MN=mana/manamax     Counters: ST=st     Cooldowns: M=m     Text: facing"
                 ).grid(row=9, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 2))
        result = tk.Label(top, text="", wraplength=520, justify="left", anchor="w")
        result.grid(row=10, column=0, columnspan=2, sticky="we", padx=10, pady=6)
        state = {"builtin": False}

        def values():
            return {k: fields[k][0].get() for k in fields}

        def build():
            v = values()
            return self.profile_from_fields(v["name"].strip(), v["pattern"], v["gauges"], v["counters"],
                                            v["cooldowns"], v["text"], v["sample"])

        def test(*_):
            if state["builtin"]:
                result.configure(text="Built-in format. Choose 'New custom...' to design your own.")
                return
            prof, msg = build()
            if prof is None:
                result.configure(text=msg)
            else:
                ok, msg2, _r = prompts.check_profile(prof, fields["sample"][0].get())
                result.configure(text=msg2)

        def load(name):
            if name == "New custom...":
                prof = prompts.get_preset("Custom")
                prof["name"] = "My prompt"
                state["builtin"] = False
            else:
                prof = profiles[name]
                state["builtin"] = name in prompts.PRESETS
            specs = prompts.format_specs(prof)
            for k, val in (("name", prof["name"]), ("pattern", prof.get("pattern", "")),
                           ("gauges", specs["gauges"]), ("counters", specs["counters"]),
                           ("cooldowns", specs["cooldowns"]), ("text", specs["text"]),
                           ("sample", prof.get("sample", ""))):
                fields[k][0].set(val)
            for k, (sv, e) in fields.items():
                e.configure(state="disabled" if state["builtin"] else "normal")
            test()

        def use():
            name = var.get()
            if name == "New custom...":
                return save()
            self.set_prompt_profile(name)
            result.configure(text="Now using '%s'." % name)

        def save():
            prof, msg = build()
            if prof is None:
                result.configure(text=msg)
                return
            ok, msg2 = self.save_prompt_profile(prof)
            result.configure(text=msg2)
            if ok:
                top.destroy()

        def delete():
            name = var.get()
            if name in self.cfg["prompt_custom"] and False:
                return
            if any(c["name"] == name for c in self.cfg["prompt_custom"]) and \
                    messagebox.askyesno("Prompt bar", "Delete '%s'?" % name, parent=top):
                self.delete_prompt_profile(name)
                top.destroy()

        for k, (sv, e) in fields.items():
            sv.trace_add("write", test)
        btn = tk.Frame(top)
        btn.grid(row=11, column=0, columnspan=2, sticky="e", padx=10, pady=(0, 10))
        tk.Button(btn, text="Use", width=9, command=use).pack(side="left")
        tk.Button(btn, text="Save custom", width=11, command=save).pack(side="left", padx=6)
        tk.Button(btn, text="Delete", width=9, command=delete).pack(side="left")
        tk.Button(btn, text="Close", width=9, command=top.destroy).pack(side="left", padx=6)
        top.bind("<Escape>", lambda e: top.destroy())
        top._actions = dict(load=load, use=use, save=save, delete=delete, test=test, fields=fields,
                            var=var, result=result, state=state)
        load(cur)
        self._theme_tree(top)
        return top

    def dos_prompt_menu(self):
        cur = self.cfg["prompt_profile"]
        profiles = self.all_profiles()
        items = [{"label": n, "checked": n == cur, "hotkey": str(i + 1) if i < 9 else None,
                  "action": (lambda n=n: self._dos_use_profile(n))} for i, n in enumerate(profiles)]
        custom_now = any(c["name"] == cur for c in self.cfg["prompt_custom"])
        items += [None,
                  {"label": "Edit this format...", "hotkey": "E", "action": lambda: self.dos_prompt_edit(cur)},
                  {"label": "New custom format...", "hotkey": "N", "action": lambda: self.dos_prompt_edit(None)},
                  {"label": "Delete this format", "hotkey": "D", "enabled": custom_now,
                   "action": lambda: self._dos_delete_profile(cur)}]
        return self._dos_menu("Prompt bar", items)

    def _dos_use_profile(self, name):
        self.set_prompt_profile(name)
        self._reopen(self.dos_prompt_menu)

    def _dos_delete_profile(self, name):
        self.delete_prompt_profile(name)
        self._reopen(self.dos_prompt_menu)

    def dos_prompt_edit(self, name, values=None):
        """Edit a profile (built-in ones are copied) or create a new one, as a DOS form."""
        if values is None:
            if name is None:
                prof = prompts.get_preset("Custom")
                prof["name"] = "My prompt"
            else:
                prof = self.all_profiles().get(name) or prompts.get_preset("Custom")
                if prof["kind"] == "haven":
                    self.system("The Haven / Duskholm format is built in. Use New custom format to design your own.")
                    self._reopen(self.dos_prompt_menu)
                    return None
                if name in prompts.PRESETS:
                    prof["name"] = name + " (custom)"
            specs = prompts.format_specs(prof)
            values = {"name": prof["name"], "pattern": prof.get("pattern", ""), "gauges": specs["gauges"],
                      "counters": specs["counters"], "cooldowns": specs["cooldowns"], "text": specs["text"],
                      "sample": prof.get("sample", "")}
        fields = [{"key": k, "label": lbl, "type": "text", "value": values.get(k, ""), "width": 46}
                  for k, lbl in (("name", "Name"), ("pattern", "Pattern"), ("gauges", "Gauges"),
                                 ("counters", "Counters"), ("cooldowns", "Cooldowns"), ("text", "Text"),
                                 ("sample", "Sample"))]

        def result(res, vals):
            if res == "cancel":
                self._reopen(self.dos_prompt_menu)
                return
            prof, msg = self.profile_from_fields(vals["name"].strip(), vals["pattern"], vals["gauges"],
                                                 vals["counters"], vals["cooldowns"], vals["text"], vals["sample"])
            if res == "test":
                if prof is None:
                    text = msg
                else:
                    text = prompts.check_profile(prof, vals["sample"])[1]
                self._overlay = dosui.show_message(
                    self.root, "Test", text, self._dc(), self.f_norm,
                    on_result=lambda r, v: self._reopen(lambda: self.dos_prompt_edit(name, vals)))
                return
            if prof is None:
                self.system(msg)
                self._reopen(lambda: self.dos_prompt_edit(name, vals))
                return
            ok, msg2 = self.save_prompt_profile(prof)
            self.system(msg2)
            if not ok:
                self._reopen(lambda: self.dos_prompt_edit(name, vals))
            else:
                self._reopen(self.dos_prompt_menu)

        return self._dos_dialog("Prompt format", fields,
                                [("Save", "save"), ("Test", "test"), ("Cancel", "cancel")], result, width=66,
                                message="Pattern groups, e.g. (?P<hp>[0-9]+)  -  Gauges: HP=hp/hpmax  "
                                        "Counters: ST=st  Cooldowns: M=m  Text: facing")

    # ---- triggers and aliases ---------------------------------------------------------------
    def _save_triggers(self, lst):
        self.cfg["triggers"] = [t for t in (triggers.validate_trigger(x) for x in lst) if t is not None][:500]
        self._save_settings()

    def _save_aliases(self, lst):
        self.cfg["alias_rules"] = [a for a in (triggers.validate_alias(x) for x in lst) if a is not None][:200]
        self._save_settings()

    def _store_trigger(self, index, trig):
        lst = list(self.cfg["triggers"])
        if any(t["name"].lower() == trig["name"].lower() and i != index for i, t in enumerate(lst)):
            return False, "There is already a trigger called '%s'." % trig["name"]
        if index is None:
            if len(lst) >= 500:
                return False, "Too many triggers (500 maximum)."
            lst.append(trig)
        else:
            lst[index] = trig
        self._save_triggers(lst)
        return True, "Saved '%s'." % trig["name"]

    def _store_alias(self, index, alias):
        lst = list(self.cfg["alias_rules"])
        if any(a["name"].lower() == alias["name"].lower() and i != index for i, a in enumerate(lst)):
            return False, "There is already an alias called '%s'." % alias["name"]
        if index is None:
            if len(lst) >= 200:
                return False, "Too many aliases (200 maximum)."
            lst.append(alias)
        else:
            lst[index] = alias
        self._save_aliases(lst)
        return True, "Saved '%s'." % alias["name"]

    def _toggle_rule(self, kind, index):
        key = "triggers" if kind == "trigger" else "alias_rules"
        lst = [dict(x) for x in self.cfg[key]]
        if 0 <= index < len(lst):
            lst[index]["enabled"] = not lst[index]["enabled"]
            (self._save_triggers if kind == "trigger" else self._save_aliases)(lst)

    def _delete_rule(self, kind, index):
        key = "triggers" if kind == "trigger" else "alias_rules"
        lst = list(self.cfg[key])
        if 0 <= index < len(lst):
            del lst[index]
            (self._save_triggers if kind == "trigger" else self._save_aliases)(lst)

    def _rules_list_window(self, kind):
        """The ordinary list window shared by the trigger and alias managers."""
        attr = "_trig_win" if kind == "trigger" else "_alias_win"
        cur = getattr(self, attr, None)
        if cur is not None:
            try:
                if cur.winfo_exists():
                    cur.lift()
                    return cur
            except tk.TclError:
                pass
        key = "triggers" if kind == "trigger" else "alias_rules"
        top = tk.Toplevel(self.root)
        setattr(self, attr, top)
        top.title("Triggers" if kind == "trigger" else "Aliases")
        top.transient(self.root)
        tk.Label(top, text=("Triggers run when a line from the game matches. Higher priority runs first."
                            if kind == "trigger" else
                            "An alias is a short word that expands to commands (separate with ;, use %1-%9 and %*).")
                 ).pack(anchor="w", padx=10, pady=(8, 0))
        box = tk.Frame(top)
        box.pack(fill="both", expand=True, padx=10, pady=4)
        lb = tk.Listbox(box, height=14, width=78, exportselection=False, font=self.f_norm,
                        highlightthickness=0, activestyle="none")
        sc = tk.Scrollbar(box, command=lb.yview)
        lb.configure(yscrollcommand=sc.set)
        lb.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

        def label(x):
            if kind == "trigger":
                return "%s %-22s %-5s %-28s %s" % ("[x]" if x["enabled"] else "[ ]", x["name"][:22], x["mode"],
                                                  x["pattern"][:28], triggers.describe_actions(x))
            return "%s %-16s %s" % ("[x]" if x["enabled"] else "[ ]", x["name"][:16], x["body"])

        def refresh(select=None):
            lb.delete(0, "end")
            for x in self.cfg[key]:
                lb.insert("end", label(x))
            if self.cfg[key]:
                i = max(0, min(len(self.cfg[key]) - 1, select or 0))
                lb.selection_set(i)
                lb.see(i)

        def current():
            sel = lb.curselection()
            return sel[0] if sel else None

        def edit(index):
            existing = self.cfg[key][index] if index is not None else None
            (self._trigger_form if kind == "trigger" else self._alias_form)(existing, index, top, refresh)

        def toggle(_e=None):
            i = current()
            if i is not None:
                self._toggle_rule(kind, i)
                refresh(i)
            return "break"

        def delete(_e=None):
            i = current()
            if i is not None and messagebox.askyesno("Delete", "Delete '%s'?" % self.cfg[key][i]["name"], parent=top):
                self._delete_rule(kind, i)
                refresh(i)
            return "break"

        def preset():
            menu = tk.Menu(top, tearoff=0)
            for pr in trigger_presets():
                menu.add_command(label=pr["name"], command=lambda pr=pr: add_preset(pr))
            try:
                menu.tk_popup(top.winfo_pointerx(), top.winfo_pointery())
            finally:
                menu.grab_release()

        def add_preset(pr):
            ok, msg = self._store_trigger(None, dict(pr, enabled=True))
            if not ok:
                messagebox.showinfo("Triggers", msg, parent=top)
            refresh(len(self.cfg[key]) - 1)

        btns = tk.Frame(top)
        btns.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(btns, text="Add...", width=8, command=lambda: edit(None)).pack(side="left")
        tk.Button(btns, text="Edit...", width=8,
                  command=lambda: edit(current()) if current() is not None else None).pack(side="left", padx=6)
        tk.Button(btns, text="On / Off", width=8, command=toggle).pack(side="left")
        tk.Button(btns, text="Delete", width=8, command=delete).pack(side="left", padx=6)
        if kind == "trigger":
            tk.Button(btns, text="Presets...", width=9, command=preset).pack(side="left")
        tk.Button(btns, text="Close", width=8, command=top.destroy).pack(side="right")
        lb.bind("<Double-Button-1>", lambda e: edit(current()) if current() is not None else None)
        lb.bind("<space>", toggle)
        lb.bind("<Delete>", delete)
        lb.bind("<Insert>", lambda e: edit(None))
        top.bind("<Escape>", lambda e: top.destroy())
        top._actions = dict(listbox=lb, refresh=refresh, edit=edit, toggle=toggle, delete=delete, kind=kind,
                            add_preset=add_preset)
        refresh()
        self._theme_tree(top)
        lb.focus_set()
        return top

    def open_triggers(self):
        if triggers is None:
            self.system("The trigger engine is not installed.")
            return None
        if self.dos:
            return self.dos_rules("trigger")
        return self._rules_list_window("trigger")

    def open_aliases(self):
        if triggers is None:
            self.system("The alias engine is not installed.")
            return None
        if self.dos:
            return self.dos_rules("alias")
        return self._rules_list_window("alias")

    def _trigger_form(self, existing, index, parent, refresh):
        """Add / edit a trigger (ordinary window) with a live test line."""
        win = tk.Toplevel(parent)
        win.title("Edit trigger" if existing else "Add trigger")
        win.transient(parent)
        v0 = values_from_trigger(existing)
        sv = {k: tk.StringVar(value=str(v0[k])) for k in ("name", "pattern", "priority", "fg", "bg", "send", "note", "sample", "pane", "status", "speak")}
        bv = {k: tk.BooleanVar(value=bool(v0[k])) for k in ("enabled", "regex", "ignore_case", "stop", "bold", "whole",
                                                           "hide", "echo", "beep", "pane_gag", "speak_int", "silence")}
        r = 0

        def row(label, widget):
            nonlocal r
            tk.Label(win, text=label).grid(row=r, column=0, sticky="w", padx=(10, 6), pady=3)
            widget.grid(row=r, column=1, sticky="w", pady=3, padx=(0, 10))
            r += 1

        row("Name", tk.Entry(win, textvariable=sv["name"], width=30))
        row("Pattern", tk.Entry(win, textvariable=sv["pattern"], width=64))
        mode = tk.Frame(win)
        tk.Checkbutton(mode, text="Regular expression  (plain: * is a wildcard)", variable=bv["regex"]).pack(side="left")
        tk.Checkbutton(mode, text="Ignore case", variable=bv["ignore_case"]).pack(side="left", padx=10)
        row("Match", mode)
        opts = tk.Frame(win)
        tk.Checkbutton(opts, text="Enabled", variable=bv["enabled"]).pack(side="left")
        tk.Checkbutton(opts, text="Stop other triggers", variable=bv["stop"]).pack(side="left", padx=10)
        tk.Label(opts, text="Priority").pack(side="left", padx=(10, 4))
        tk.Entry(opts, textvariable=sv["priority"], width=6).pack(side="left")
        row("", opts)
        hl = tk.Frame(win)
        tk.Label(hl, text="text").pack(side="left")
        tk.Entry(hl, textvariable=sv["fg"], width=10).pack(side="left", padx=(4, 10))
        tk.Label(hl, text="background").pack(side="left")
        tk.Entry(hl, textvariable=sv["bg"], width=10).pack(side="left", padx=(4, 10))
        tk.Checkbutton(hl, text="Bold", variable=bv["bold"]).pack(side="left")
        tk.Checkbutton(hl, text="Whole line", variable=bv["whole"]).pack(side="left", padx=6)
        row("Highlight", hl)
        row("Hide from screen", tk.Checkbutton(win, variable=bv["hide"]))
        snd = tk.Frame(win)
        tk.Entry(snd, textvariable=sv["send"], width=48).pack(side="left")
        tk.Checkbutton(snd, text="Show it", variable=bv["echo"]).pack(side="left", padx=8)
        row("Send command", snd)
        row("Beep", tk.Checkbutton(win, variable=bv["beep"]))
        cap = tk.Frame(win)
        tk.Entry(cap, textvariable=sv["pane"], width=24).pack(side="left")
        tk.Checkbutton(cap, text="Also hide from the main window", variable=bv["pane_gag"]).pack(side="left", padx=8)
        row("Send to pane", cap)
        row("Client note", tk.Entry(win, textvariable=sv["note"], width=64))
        row("Status line", tk.Entry(win, textvariable=sv["status"], width=64))
        spk = tk.Frame(win)
        tk.Entry(spk, textvariable=sv["speak"], width=40).pack(side="left")
        tk.Checkbutton(spk, text="Interrupt", variable=bv["speak_int"]).pack(side="left", padx=6)
        tk.Checkbutton(spk, text="Don't read this line aloud", variable=bv["silence"]).pack(side="left", padx=6)
        row("Speak (screen reader)", spk)
        tk.Label(win, justify="left", wraplength=560,
                 text="Colours: #rrggbb, 0-15 or a name like 'bright cyan'. In commands and notes: %0 is the match, "
                      "%1-%9 the wildcards/groups; ; separates commands."
                 ).grid(row=r, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 0)); r += 1
        row("Test line", tk.Entry(win, textvariable=sv["sample"], width=64))
        result = tk.Label(win, text="", wraplength=560, justify="left", anchor="w")
        result.grid(row=r, column=0, columnspan=2, sticky="we", padx=10, pady=4); r += 1

        def values():
            v = {k: x.get() for k, x in sv.items()}
            v.update({k: x.get() for k, x in bv.items()})
            v["keep"] = v0["keep"]
            return v

        def test(*_):
            trig, msg = trigger_from_values(values())
            if trig is None:
                result.configure(text=msg)
            else:
                result.configure(text=triggers.check_trigger(trig, sv["sample"].get())[1] if sv["sample"].get().strip()
                                 else "Looks fine. Type a sample line above to test it.")

        def ok():
            trig, msg = trigger_from_values(values())
            if trig is None:
                result.configure(text=msg)
                return
            good, msg2 = self._store_trigger(index, trig)
            if not good:
                result.configure(text=msg2)
                return
            refresh(len(self.cfg["triggers"]) - 1 if index is None else index)
            win.destroy()

        for x in list(sv.values()) + list(bv.values()):
            x.trace_add("write", test)
        row_b = tk.Frame(win)
        row_b.grid(row=r, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        tk.Button(row_b, text="OK", width=8, command=ok).pack(side="right")
        tk.Button(row_b, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        win.bind("<Escape>", lambda e: win.destroy())
        win._vars = (sv, bv)
        win._ok = ok
        win._result = result
        win._values = values
        test()
        self._theme_tree(win)
        return win

    def _alias_form(self, existing, index, parent, refresh):
        win = tk.Toplevel(parent)
        win.title("Edit alias" if existing else "Add alias")
        win.transient(parent)
        sv = {"name": tk.StringVar(value=existing["name"] if existing else ""),
              "body": tk.StringVar(value=existing["body"] if existing else ""),
              "sample": tk.StringVar(value="")}
        en = tk.BooleanVar(value=existing["enabled"] if existing else True)
        for r, (label, key, width) in enumerate((("Name", "name", 24), ("Expands to", "body", 70), ("Try arguments", "sample", 40))):
            tk.Label(win, text=label).grid(row=r, column=0, sticky="w", padx=(10, 6), pady=4)
            tk.Entry(win, textvariable=sv[key], width=width).grid(row=r, column=1, sticky="w", pady=4, padx=(0, 10))
        tk.Checkbutton(win, text="Enabled", variable=en).grid(row=3, column=1, sticky="w")
        tk.Label(win, justify="left", wraplength=560, text="Use ; between commands. %1-%9 are the words you type after the "
                 "alias, %* is all of them. With no % in the text, whatever you type is added to the last command."
                 ).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 0))
        result = tk.Label(win, text="", wraplength=560, justify="left", anchor="w")
        result.grid(row=5, column=0, columnspan=2, sticky="we", padx=10, pady=4)

        def build():
            return triggers.validate_alias({"name": sv["name"].get().strip(), "body": sv["body"].get().strip(),
                                            "enabled": en.get()})

        def test(*_):
            a = build()
            if a is None:
                result.configure(text="Give a name (letters, digits and _!?.+-, no spaces) and what it expands to.")
            else:
                result.configure(text="Sends: " + " | ".join(triggers.expand_alias(a, sv["sample"].get())))

        def ok():
            a = build()
            if a is None:
                test()
                return
            good, msg = self._store_alias(index, a)
            if not good:
                result.configure(text=msg)
                return
            refresh(len(self.cfg["alias_rules"]) - 1 if index is None else index)
            win.destroy()

        for x in sv.values():
            x.trace_add("write", test)
        en.trace_add("write", test)
        row_b = tk.Frame(win)
        row_b.grid(row=6, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        tk.Button(row_b, text="OK", width=8, command=ok).pack(side="right")
        tk.Button(row_b, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        win.bind("<Escape>", lambda e: win.destroy())
        win._vars = (sv, en)
        win._ok = ok
        win._result = result
        test()
        self._theme_tree(win)
        return win

    # -- DOS look ----------------------------------------------------------------------------
    def dos_rules(self, kind, selected=0):
        key = "triggers" if kind == "trigger" else "alias_rules"
        if kind == "trigger":
            cols = [{"title": "On", "width": 3}, {"title": "Name", "width": 18}, {"title": "Mode", "width": 5},
                    {"title": "Pattern", "width": 0}, {"title": "Actions", "width": 22}]
            hints = [("Enter", "Edit"), ("A", "Add"), ("Space", "On/Off"), ("Del", "Remove"), ("P", "Presets"),
                     ("Esc", "Close")]
        else:
            cols = [{"title": "On", "width": 3}, {"title": "Name", "width": 14}, {"title": "Expands to", "width": 0}]
            hints = [("Enter", "Edit"), ("A", "Add"), ("Space", "On/Off"), ("Del", "Remove"), ("Esc", "Close")]

        def rows():
            out = []
            for x in self.cfg[key]:
                on = "yes" if x["enabled"] else ""
                if kind == "trigger":
                    out.append({"cells": [on, x["name"], x["mode"], x["pattern"], triggers.describe_actions(x)],
                                "role": "normal" if x["enabled"] else "dim"})
                else:
                    out.append({"cells": [on, x["name"], x["body"]], "role": "normal" if x["enabled"] else "dim"})
            return out

        def act(name, idx, table):
            if name in ("select", "edit") and idx is not None:
                table.close()
                (self._dos_trigger_form if kind == "trigger" else self._dos_alias_form)(idx, None, 1)
            elif name == "add":
                table.close()
                (self._dos_trigger_form if kind == "trigger" else self._dos_alias_form)(None, None, 1)
            elif name == "toggle" and idx is not None:
                self._toggle_rule(kind, idx)
                table.set_rows(rows(), selected=idx)
            elif name == "remove" and idx is not None:
                table.close()
                victim = self.cfg[key][idx]["name"]
                self._overlay = dosui.confirm(
                    self.root, "Remove", "Remove '%s'?" % victim, self._dc(), self.f_norm,
                    lambda r, v: (self._delete_rule(kind, idx), self._reopen(self.dos_rules, kind, max(0, idx - 1)))
                    if r == "yes" else self._reopen(self.dos_rules, kind, idx))
            elif name == "presets" and kind == "trigger":
                table.close()
                self._dos_trigger_presets()

        keys = {"Return": "select", "KP_Enter": "select", "Escape": "close", "a": "add", "Insert": "add",
                "e": "edit", "Delete": "remove", "r": "remove", "space": "toggle"}
        if kind == "trigger":
            keys["p"] = "presets"
        table = dosui.DosTable(self.root, "Triggers" if kind == "trigger" else "Aliases", cols, rows(), self._dc(),
                               self.f_norm, act, keys=keys, hints=hints, min_width=70, selected=selected)
        self._overlay = table
        table.open()
        return table

    def _dos_trigger_presets(self):
        items = [{"label": pr["name"], "hotkey": str(i + 1) if i < 9 else None,
                  "action": (lambda pr=pr: self._dos_add_preset(pr))} for i, pr in enumerate(trigger_presets())]
        self._dos_menu("Trigger presets", items, back=lambda: self.dos_rules("trigger"))

    def _dos_add_preset(self, pr):
        ok, msg = self._store_trigger(None, dict(pr, enabled=True))
        self.system(msg)
        self._reopen(self.dos_rules, "trigger", max(0, len(self.cfg["triggers"]) - 1))

    def _dos_trigger_form(self, index, values, page):
        """Two pages: what to match, then what to do. `values` carries entries between pages."""
        if values is None:
            values = values_from_trigger(self.cfg["triggers"][index] if index is not None else None)
        t = lambda k, label, w=40: {"key": k, "label": label, "type": "text", "value": str(values[k]), "width": w}
        c = lambda k, label: {"key": k, "label": label, "type": "check", "value": bool(values[k])}
        if page == 1:
            fields = [t("name", "Name", 30), t("pattern", "Pattern", 46), c("regex", "Regular expression"),
                      c("ignore_case", "Ignore case"), c("enabled", "Enabled"), c("stop", "Stop other triggers"),
                      t("priority", "Priority", 6), t("sample", "Test line", 46)]
            buttons = [("Actions >", "next"), ("Test", "test"), ("Cancel", "cancel")]
            title = "Trigger: match"
            msg = "Plain: * is a wildcard. %1-%9 / %0 can be used in commands."
        else:
            fields = [t("fg", "Highlight text", 12), t("bg", "Highlight background", 12), c("bold", "Bold"),
                      c("whole", "Colour the whole line"), c("hide", "Hide line from screen"),
                      t("send", "Send command", 40), c("echo", "Show sent command"), c("beep", "Beep"),
                      t("pane", "Send to pane", 24), c("pane_gag", "...and hide from main window"),
                      t("note", "Client note", 40), t("status", "Status line text", 40)]
            buttons = [("Save", "save"), ("< Back", "back"), ("Cancel", "cancel")]
            title = "Trigger: actions"
            msg = "Colours: #rrggbb, 0-15, or a name like 'bright cyan'."

        def result(res, vals):
            values.update(vals)
            values["keep"] = values.get("keep", [])
            if res == "cancel":
                self._reopen(self.dos_rules, "trigger", index or 0)
                return
            if res == "next":
                self._reopen(lambda: self._dos_trigger_form(index, values, 2))
                return
            if res == "back":
                self._reopen(lambda: self._dos_trigger_form(index, values, 1))
                return
            trig, msg2 = trigger_from_values(values)
            if res == "test":
                text = msg2 if trig is None else (triggers.check_trigger(trig, str(values.get("sample", "")))[1]
                                                  if str(values.get("sample", "")).strip() else "Looks fine. Add a test line to try it.")
                self._overlay = dosui.show_message(self.root, "Test", text, self._dc(), self.f_norm,
                                                   on_result=lambda r, v: self._reopen(lambda: self._dos_trigger_form(index, values, 1)))
                return
            if trig is None:
                self.system(msg2)
                self._reopen(lambda: self._dos_trigger_form(index, values, 2 if page == 2 else 1))
                return
            good, msg3 = self._store_trigger(index, trig)
            self.system(msg3)
            if not good:
                self._reopen(lambda: self._dos_trigger_form(index, values, 1))
            else:
                self._reopen(self.dos_rules, "trigger", len(self.cfg["triggers"]) - 1 if index is None else index)

        return self._dos_dialog(title, fields, buttons, result, width=66, message=msg)

    def _dos_alias_form(self, index, values, page=1):
        if values is None:
            ex = self.cfg["alias_rules"][index] if index is not None else None
            values = {"name": ex["name"] if ex else "", "body": ex["body"] if ex else "",
                      "enabled": ex["enabled"] if ex else True, "sample": ""}
        fields = [{"key": "name", "label": "Name", "type": "text", "value": values["name"], "width": 22},
                  {"key": "body", "label": "Expands to", "type": "text", "value": values["body"], "width": 46},
                  {"key": "enabled", "label": "Enabled", "type": "check", "value": bool(values["enabled"])},
                  {"key": "sample", "label": "Try arguments", "type": "text", "value": values["sample"], "width": 30}]

        def result(res, vals):
            values.update(vals)
            if res == "cancel":
                self._reopen(self.dos_rules, "alias", index or 0)
                return
            a = triggers.validate_alias({"name": values["name"].strip(), "body": values["body"].strip(),
                                         "enabled": values["enabled"]})
            if res == "test":
                text = ("Sends: " + " | ".join(triggers.expand_alias(a, values["sample"]))) if a else \
                    "Give a name (letters, digits and _!?.+-, no spaces) and what it expands to."
                self._overlay = dosui.show_message(self.root, "Test", text, self._dc(), self.f_norm,
                                                   on_result=lambda r, v: self._reopen(lambda: self._dos_alias_form(index, values)))
                return
            if a is None:
                self.system("Give a name (no spaces) and what it expands to.")
                self._reopen(lambda: self._dos_alias_form(index, values))
                return
            good, msg = self._store_alias(index, a)
            self.system(msg)
            if not good:
                self._reopen(lambda: self._dos_alias_form(index, values))
            else:
                self._reopen(self.dos_rules, "alias", len(self.cfg["alias_rules"]) - 1 if index is None else index)

        return self._dos_dialog("Alias", fields, [("Save", "save"), ("Test", "test"), ("Cancel", "cancel")], result,
                                width=62, message="Use ; between commands. %1-%9 / %* are your arguments.")

    # ---- panes manager ---------------------------------------------------------------------
    PANE_SYNTAX = ("Lines reach a pane through a trigger (Ctrl+T) whose 'Send to pane' names it. "
                   "One line per area: side size panes. Side: top, bottom, left or right. Size is "
                   "rows (top/bottom) or columns (left/right). Panes are separated by commas, e.g. "
                   "'right 40 OOC, Tells'.")

    def _pane_lines(self):
        out = []
        for r in self.cfg["layout"]["regions"]:
            out.append("%s %d %s" % (r["side"], r["size"], ", ".join(r["panes"])))
        return (out + ["", "", ""])[:3] if len(out) <= 3 else out[:3]

    def _panes_parse(self, lines):
        """Text lines -> (layout, new pane definitions, message). Layout is None when nothing is wrong
        enough to refuse but nothing can be shown (empty lines mean no areas)."""
        if layout is None:
            return None, [], "The layout module is missing."
        regions, defs = [], {d["name"].lower(): d for d in self.cfg["panes"]}
        for n, line in enumerate(l.strip() for l in lines):
            if not line:
                continue
            parts = line.split(None, 2)
            side = parts[0].lower()
            if side not in layout.SIDES:
                return None, [], "Line %d: the side must be top, bottom, left or right." % (n + 1)
            if len(parts) < 2 or not (parts[1].isascii() and parts[1].isdigit()):
                return None, [], "Line %d: put a size (a number) after the side." % (n + 1)
            names = []
            for nm in (parts[2].split(",") if len(parts) > 2 else []):
                d = layout.validate_pane({"name": nm})
                if d is None:
                    continue
                if d["name"].lower() not in defs:
                    if len(defs) >= layout.MAX_PANES:
                        return None, [], "At most %d panes." % layout.MAX_PANES
                    defs[d["name"].lower()] = d
                if d["name"].lower() not in [x.lower() for x in names]:
                    names.append(defs[d["name"].lower()]["name"])
            regions.append({"id": "r%d" % (len(regions) + 1), "side": side, "size": int(parts[1]),
                            "weight": 1, "panes": names})
        lay = layout.validate_layout({"regions": regions, "min_main_cols": 80},
                                     known_panes=[d["name"] for d in defs.values()])
        return lay, list(defs.values()), "OK"

    def _panes_preview_text(self, lines):
        lay, _defs, msg = self._panes_parse(lines)
        if lay is None:
            return msg
        if not lay["regions"]:
            return "(no areas: the window is just the main text)"
        return "\n".join(layout.ascii_preview(lay, cols=60, rows=18))

    def _panes_save(self, lines):
        lay, defs, msg = self._panes_parse(lines)
        if lay is None:
            return False, msg
        self.cfg["panes"] = defs
        self.cfg["layout"] = lay
        self.cfg["panes_hidden"] = []                 # area ids are renumbered, so old folds no longer apply
        self._region_active = {}
        for d in defs:
            if d["name"].lower() in self._panes or layout.find_region(lay, d["name"]):
                self.pane_ensure(d["name"])
        self._save_settings()
        self.layout_panes()
        self.schedule_layout(5)
        return True, "Panes saved."

    def _preset_lines(self, name):
        lay = layout.preset_layout(name, [d["name"] for d in self.cfg["panes"]] or ["OOC", "Tells"])
        return [("%s %d %s" % (r["side"], r["size"], ", ".join(r["panes"]))).strip() for r in lay["regions"]][:3]

    def open_panes(self):
        if layout is None:
            self.system("The layout module is missing.")
            return
        if self.dos:
            return self._dos_panes_form(self._pane_lines())
        if getattr(self, "_panes_win", None) is not None:
            try:
                self._panes_win.lift()
                return
            except tk.TclError:
                self._panes_win = None
        win = self._panes_win = tk.Toplevel(self.root)
        win.title("Panes / layout")
        win.transient(self.root)
        vars_ = [tk.StringVar(value=l) for l in self._pane_lines()]
        tk.Label(win, justify="left", wraplength=520, text=self.PANE_SYNTAX + " The main text always keeps at "
                 "least 80 columns; areas that would squeeze it are narrowed, then hidden. "
                 "To send lines to a pane, add a trigger (Ctrl+T) with 'Send to pane' set to its name.").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 4))
        pr = tk.Frame(win)
        pr.grid(row=1, column=0, columnspan=2, sticky="w", padx=10)
        tk.Label(pr, text="Preset").pack(side="left")
        pv = tk.StringVar(value="(choose)")
        for i, v in enumerate(vars_):
            tk.Entry(win, textvariable=v, width=60).grid(row=2 + i, column=0, columnspan=2, sticky="w", padx=10, pady=2)
        prev = tk.Label(win, justify="left", anchor="nw", font=self.f_norm, relief="sunken", padx=4, pady=2)
        prev.grid(row=6, column=0, columnspan=2, sticky="w", padx=10, pady=6)
        msg = tk.Label(win, text="", anchor="w", justify="left", wraplength=520)
        msg.grid(row=7, column=0, columnspan=2, sticky="we", padx=10)

        def refresh(*_):
            lines = [v.get() for v in vars_]
            lay, _d, m = self._panes_parse(lines)
            prev.configure(text=self._panes_preview_text(lines))
            msg.configure(text="" if lay is not None else m)

        def preset(name):
            for v, l in zip(vars_, (self._preset_lines(name) + ["", "", ""])):
                v.set(l)
            refresh()

        om = tk.OptionMenu(pr, pv, *layout.PRESETS, command=preset)
        om.pack(side="left", padx=6)
        for v in vars_:
            v.trace_add("write", refresh)

        def save():
            ok, m = self._panes_save([v.get() for v in vars_])
            if ok:
                close()
            else:
                msg.configure(text=m)

        def close():
            self._panes_win = None
            win.destroy()

        bf = tk.Frame(win)
        bf.grid(row=8, column=0, columnspan=2, sticky="e", padx=10, pady=8)
        tk.Button(bf, text="Save", width=10, command=save).pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", width=10, command=close).pack(side="left")
        win.protocol("WM_DELETE_WINDOW", close)
        refresh()
        self._theme_tree(win)
        return win

    def _dos_panes_form(self, lines, note=None):
        names = ", ".join(layout.PRESETS)
        fields = [{"key": "l%d" % i, "label": "Area %d" % (i + 1), "type": "text", "value": l, "width": 44}
                  for i, l in enumerate((list(lines) + ["", "", ""])[:3])]
        buttons = [("Save", "save"), ("Preview", "preview"), ("Presets", "presets"), ("Cancel", "cancel")]

        def result(res, vals):
            cur = [vals.get("l%d" % i, "") for i in range(3)]
            if res == "cancel":
                return
            if res == "presets":
                items = [{"label": n, "action": (lambda n=n: self._reopen(self._dos_panes_form, self._preset_lines(n)))}
                         for n in layout.PRESETS]
                self._reopen(lambda: self._dos_menu("Layout presets", items))
                return
            if res == "preview":
                self._overlay = dosui.show_message(self.root, "Preview", self._panes_preview_text(cur), self._dc(),
                                                   self.f_norm, on_result=lambda r, v: self._reopen(self._dos_panes_form, cur))
                return
            ok, m = self._panes_save(cur)
            if not ok:
                self._reopen(self._dos_panes_form, cur, m)
            else:
                self.system(m)

        return self._dos_dialog("Panes / layout", fields, buttons, result, width=66, message=note or self.PANE_SYNTAX)

    def _reopen(self, fn, *args):
        """Re-open a menu once the one that just ran its action has fully closed."""
        self.root.after_idle(lambda: fn(*args) if self.dos and not self._overlay_open() else None)

    # -- colours ------------------------------------------------------------------
    def dos_colors_menu(self, fresh=True):
        if not self.dos:
            return None
        if fresh or self._colors_snapshot is None:
            self._colors_snapshot = (self._skin_cfg_key(), self._skin_name(),
                                     copy.deepcopy(self.cfg["skin_overrides"]))
        snap = self._colors_snapshot
        changed = (self._skin_name(), self.cfg["skin_overrides"]) != (snap[1], snap[2])
        items = [
            {"label": "Skin: %s..." % self._skin_name(), "hotkey": "S",
             "action": lambda: self.dos_skin_menu(after=lambda: self.dos_colors_menu(False))},
            None,
            {"label": "Game palette (16 colours)...", "hotkey": "P", "action": self.dos_palette_menu},
            {"label": "Interface colours...", "hotkey": "I", "action": lambda: self.dos_key_menu("ui")},
            {"label": "DOS screen colours...", "hotkey": "D", "action": lambda: self.dos_key_menu("dos")},
            {"label": "Minimum contrast: %.1f..." % self.theme["min_contrast"], "hotkey": "C",
             "action": self.dos_contrast_dialog},
            None,
            {"label": "Revert changes", "hotkey": "V", "enabled": changed, "action": self.dos_colors_revert},
            {"label": "Reset skin to defaults", "hotkey": "R", "action": self.dos_colors_reset},
            {"label": "Save as new skin...", "hotkey": "A", "action": self.dos_save_skin_dialog},
        ]
        return self._dos_menu("Colours", items)

    def dos_colors_revert(self):
        snap = self._colors_snapshot
        if snap:
            self.cfg[snap[0]] = snap[1]
            self.cfg["skin_overrides"] = copy.deepcopy(snap[2])
            self.v_skin.set(self._skin_name())
            self.theme = self._effective_theme()
            self.apply_theme()
            self._save_settings()
        self._reopen(self.dos_colors_menu, False)

    def dos_colors_reset(self):
        self.reset_skin_edits()
        self._save_settings()
        self._reopen(self.dos_colors_menu, False)

    def dos_palette_menu(self):
        th = self.theme
        items = [{"label": "%-2d %-14s %s" % (i, ANSI_NAMES[i], th["ansi"][i]), "swatch": th["ansi"][i],
                  "hotkey": format(i, "x"),
                  "action": (lambda i=i: self.dos_pick_color(
                      ANSI_NAMES[i], self.theme["ansi"][i],
                      lambda h, i=i: self._set_override(("ansi", i), h), self.dos_palette_menu))}
                 for i in range(16)]
        return self._dos_menu("Game palette", items, back=lambda: self.dos_colors_menu(False))

    def dos_key_menu(self, kind):
        if kind == "ui":
            keys, labels = COLOR_KEYS, COLOR_LABELS
        else:                           # the DOS screen also has its typed-command and message colours
            keys, labels = ("echo", "system") + DOS_KEYS, dict(COLOR_LABELS, **DOS_LABELS)
        cur = self.theme if kind == "ui" else dict(self._dc(), echo=self.theme["echo"], system=self.theme["system"])

        def cur_now(k, kind):
            return (self.theme if kind == "ui" or k in ("echo", "system") else self._dc())[k]
        items = [{"label": "%-26s %s" % (labels[k], cur[k]), "swatch": cur[k],
                  "hotkey": str(i + 1) if i < 9 else None,
                  "action": (lambda k=k: self.dos_pick_color(
                      labels[k], cur_now(k, kind),
                      lambda h, k=k: self._set_override((k,), h), lambda: self.dos_key_menu(kind)))}
                 for i, k in enumerate(keys)]
        return self._dos_menu("Interface colours" if kind == "ui" else "DOS screen colours", items,
                              back=lambda: self.dos_colors_menu(False))

    def dos_pick_color(self, title, current, apply, reopen):
        """Open the colour mixer; every change is applied live, Cancel restores the original."""
        box = []

        def on_change(h):
            apply(h)
            if box:
                try:
                    box[0].restyle(self._dc(), self.f_norm)
                except tk.TclError:
                    pass

        def on_result(name, value):
            if name != "ok":
                apply(current)
            self._save_settings()
            self._reopen(reopen)

        picker = dosui.DosColorPicker(self.root, title, current, self._dc(), self.f_norm, on_result,
                                      on_change=on_change)
        box.append(picker)
        self._overlay = picker
        picker.open()
        return picker

    def adjust_contrast(self, delta):
        """Ctrl-* raises and Ctrl-/ lowers the minimum text contrast by half a step (1.0 to 7.0)."""
        v = round(max(1.0, min(7.0, self.theme["min_contrast"] + delta)), 1)
        if v == round(self.theme["min_contrast"], 1):
            self.set_notice("Minimum contrast %.1f (the limit)" % v, 4)
            return v
        self._set_override(("min_contrast",), v)
        self._save_settings()
        self.set_notice("Minimum contrast %.1f" % v, 4)
        if self.sr_on():
            self.speech.say_now("Minimum contrast %.1f" % v)
        return v

    def dos_contrast_dialog(self):
        fields = [{"key": "v", "label": "Minimum contrast (1.0 - 7.0)", "type": "text",
                   "value": "%.1f" % self.theme["min_contrast"], "width": 6}]

        def result(name, values):
            if name == "ok":
                try:
                    v = float(str(values.get("v", "")).strip())
                    if v != v:
                        raise ValueError
                except ValueError:
                    self.system("Contrast must be a number from 1.0 to 7.0.")
                else:
                    v = round(max(1.0, min(7.0, v)), 1)
                    self._set_override(("min_contrast",), v)
                    self._save_settings()
            self._reopen(self.dos_colors_menu, False)

        return self._dos_dialog("Minimum contrast", fields, [("OK", "ok"), ("Cancel", "cancel")], result,
                                width=54, message="1.0 shows the game's colours exactly as sent.\n"
                                                  "Higher lifts dark colours so they stay readable.")

    def dos_save_skin_dialog(self):
        fields = [{"key": "name", "label": "Name", "type": "text", "value": "", "width": 30}]

        def result(name, values):
            if name == "ok":
                fp = self.save_skin_as(str(values.get("name", "")))
                self.system("Skin saved to %s" % fp if fp else "Could not save that skin (name empty or reserved).")
            self._reopen(self.dos_colors_menu, False)

        return self._dos_dialog("Save as new skin", fields, [("Save", "ok"), ("Cancel", "cancel")], result,
                                width=50)

    # -- font ----------------------------------------------------------------------
    def dos_font_menu(self):
        fams = self.mono_families()
        cur = self.font_family
        head = [{"label": "Size: %d..." % int(self.f_norm.cget("size")), "hotkey": "Z",
                 "action": self.dos_font_size_dialog},
                {"label": "Line spacing: %d..." % int(self.cfg["line_spacing"]), "hotkey": "L",
                 "action": self.dos_spacing_dialog},
                {"label": "Auto-fit size", "hotkey": "A", "checked": bool(self.cfg["dos_autofit"]),
                 "action": self.dos_toggle_autofit},
                {"label": "Use the skin's font", "hotkey": "K", "action": self.dos_font_skin},
                None]
        items = head + [{"label": f, "checked": f == cur, "action": (lambda f=f: self.apply_font(f))}
                        for f in fams]
        start = len(head) + (fams.index(cur) if cur in fams else 0)
        return self._dos_menu("Font", items, initial=start)

    def dos_spacing_dialog(self):
        fields = [{"key": "n", "label": "Extra pixels between lines (0 - 12)", "type": "text",
                   "value": str(int(self.cfg["line_spacing"])), "width": 4}]

        def result(name, values):
            if name == "ok":
                try:
                    self.apply_spacing(int(str(values.get("n", "")).strip()))
                except ValueError:
                    self.system("Line spacing must be a whole number from 0 to 12.")
            self._reopen(self.dos_font_menu)

        return self._dos_dialog("Line spacing", fields, [("OK", "ok"), ("Cancel", "cancel")], result, width=50)

    def dos_toggle_autofit(self):
        self.cfg["dos_autofit"] = not self.cfg["dos_autofit"]
        self._save_settings()
        self._fit_font()
        self._reopen(self.dos_font_menu)

    def dos_font_skin(self):
        self.apply_font(use_skin_font=True)

    def dos_font_size_dialog(self):
        fields = [{"key": "size", "label": "Size (%d - %d)" % (MIN_FONT, MAX_FONT), "type": "text",
                   "value": str(int(self.f_norm.cget("size"))), "width": 5}]

        def result(name, values):
            if name != "ok":
                return
            try:
                n = int(str(values.get("size", "")).strip())
            except ValueError:
                self.system("Font size must be a whole number from %d to %d." % (MIN_FONT, MAX_FONT))
                return
            n = max(MIN_FONT, min(MAX_FONT, n))
            if self.cfg["dos_autofit"]:
                self.cfg["dos_autofit"] = False
                self.system("Font auto-fit is off (you set a size). Turn it back on with F7 > Auto-fit size.")
            self.cfg["dos_font_size"] = n
            self._set_font_size(n)
            self._save_settings()

        return self._dos_dialog("Font size", fields, [("OK", "ok"), ("Cancel", "cancel")], result, width=46,
                                message="Setting a size turns font auto-fit off.")

    def _ctrl_handler(self, fn):
        def handler(_e=None):
            if not self._overlay_open():
                fn()
            return "break"
        return handler

    def _on_ctrl_w(self, _e=None):
        if not self._overlay_open():
            self.open_worlds()
        return "break"

    def _dos_only(self, fn):
        """Key handler that acts only in the DOS look and when no menu/dialog is already open."""
        def handler(_e=None):
            if not self.dos or self._overlay_open():
                return None
            fn()
            return "break"
        return handler

    def _bind_dos_keys(self):
        table = {"<F1>": self.dos_help, "<F2>": self.toggle_connection, "<F3>": self.toggle_log,
                 "<F5>": self.dos_skin_menu, "<F6>": self.edit_colors, "<F7>": self.choose_font,
                 "<F10>": self.dos_main_menu, "<Alt-m>": self.dos_main_menu, "<Alt-M>": self.dos_main_menu,
                 "<Alt-x>": self.dos_confirm_quit, "<Alt-X>": self.dos_confirm_quit}
        for seq, fn in table.items():
            self.root.bind(seq, self._dos_only(fn))

    def set_fullscreen(self, on, save=True):
        on = bool(on)
        self.cfg["fullscreen"] = on
        self.v_full.set(on)
        try:
            self.root.attributes("-fullscreen", on)
        except tk.TclError:
            pass
        if save:
            self._save_settings()
        self.root.after(150, self._fit_font)

    def toggle_fullscreen(self, _e=None):
        self.set_fullscreen(not bool(self.cfg["fullscreen"]))
        return "break"

    def set_dos_mode(self, on):
        on = bool(on)
        if on and self.sr_on():
            self.system("The DOS look is not available in screen reader mode.")
            self.v_dos.set(False)
            return
        if on == self.dos:
            self.v_dos.set(self.dos)
            return
        self.dos_close_overlay()
        if self._colors_win is not None:
            try:
                self._colors_win._actions["done"]()
            except Exception:  # noqa: BLE001
                self._colors_win = None
        self.dos = on
        self.cfg["ui_mode"] = "dos" if on else "normal"
        self.v_dos.set(on)
        self.theme = self._effective_theme()
        self.v_skin.set(self._skin_name())
        self.apply_layout()
        self.apply_theme()
        if on:
            self.root.update_idletasks()
            if self.cfg["dos_autofit"]:
                self._fit_font()
            elif self.cfg["dos_font_size"]:
                self._set_font_size(int(self.cfg["dos_font_size"]))
            if self.cfg["dos_flourish"]:
                self._dos_banner()
            self._start_dos_tick()
        else:
            self._set_font_size(int(self.cfg["font_size"]))
            if self._dos_job is not None:
                try:
                    self.root.after_cancel(self._dos_job)
                except tk.TclError:
                    pass
                self._dos_job = None
        self.update_dosbar()
        self._save_settings()

    def toggle_dos_mode(self, _e=None):
        self.set_dos_mode(not self.dos)
        return "break"

    def _dos_banner(self):
        return                                  # the hint bar already says all this

    def _set_font_size(self, size):
        """Apply a size to the display fonts without changing the saved preference."""
        for f in (self.f_norm, self.f_bold, self.f_ital, self.f_bi):
            f.configure(size=size)
        self._sync_variants()
        self._restyle_dosbar()
        self._update_dos_cols()

    def _on_dos_yscroll(self, first, last):
        self._dosscroll.set(first, last)
        self._dos_scroll_visibility(first, last)

    def _dos_scroll_visibility(self, first=None, last=None):
        """Show the scrollbar in the right border cell when the text is longer than the view."""
        try:
            if first is None:
                first, last = self.out.yview()
            scrollable = self.dos and (float(first) > 0.0 or float(last) < 1.0)
            if scrollable and not self._dosscroll.winfo_ismapped():
                if self._panes_active and self._pane_geom is not None:
                    mx, my, mw, mh = self._pane_geom["main"]
                    self._dosscroll.place(x=mx + mw, y=my, height=mh)
                else:
                    self._dosscroll.place(relx=1.0, rely=0.0, anchor="ne", relheight=1.0)
                self._dosscroll.lift()
            elif not scrollable and self._dosscroll.winfo_ismapped():
                self._dosscroll.place_forget()
        except (tk.TclError, ValueError):
            pass

    def _apply_spacing(self):
        n = int(self.cfg["line_spacing"])
        for w in self._text_widgets():
            w.configure(spacing2=n, spacing3=n)           # between wrapped lines / after each line

    def apply_spacing(self, n):
        self.cfg["line_spacing"] = max(0, min(12, int(n)))
        self._apply_spacing()
        self._save_settings()
        if self.dos:
            self.root.update_idletasks()
            self._fit_font()
        return self.cfg["line_spacing"]

    def _dos_cols_now(self):
        """Columns for the DOS screen: the window width in character cells, less a one-cell
        border on each side and the one-cell scrollbar (or the fixed width if fitting is off)."""
        fixed = int(self.cfg["dos_cols"])
        if not self.cfg["dos_fit"]:
            return fixed
        w = self._holder.winfo_width()
        if self._panes_active and self._pane_geom is not None:
            return max(40, int(self._pane_geom["main"][2] / max(1, self.f_norm.measure("0"))))
        if w < 100:
            return fixed
        cw = max(1, self.f_norm.measure("0"))
        return max(40, int((w - 2 * cw - 16) / cw))        # 2 cells = the borders (the right one doubles as the scrollbar)

    def _update_dos_cols(self):
        if not self.dos:
            return
        n = self._dos_cols_now()
        if int(self.out.cget("width")) != n:
            self.out.configure(width=n)

    def _fit_size(self, min_cols, avail_w, avail_h, extra_rows=0):
        """Largest font size at which at least `min_cols` columns (plus the two border cells)
        fit the width and 25 rows (as in 80x25 DOS) fit the height."""
        if self._measure_font is None:
            self._measure_font = tkfont.Font(family=self.font_family, size=10)
        f = self._measure_font
        for size in range(MAX_FONT, MIN_FONT - 1, -1):
            f.configure(family=self.font_family, size=size)
            if f.measure("0") * (min_cols + 2) + 16 <= avail_w and (f.metrics("linespace") + int(self.cfg["line_spacing"])) * (25 + extra_rows) <= avail_h:
                return size
        return MIN_FONT

    def _fit_font(self):
        """DOS look: pick the font size (if auto-fit is on), then set the column count so the
        screen fills the window width with a one-cell border."""
        self._fit_job = None
        if not self.dos:
            return
        if self.cfg["dos_autofit"]:
            w, h = self._holder.winfo_width(), self._holder.winfo_height()
            if w >= 100 and h >= 60:
                min_cols = 80 if self.cfg["dos_fit"] else int(self.cfg["dos_cols"])
                xc, xr = self._panes_extra()
                size = self._fit_size(min_cols + xc, w, h, xr)
                if size != self.f_norm.cget("size"):
                    self._set_font_size(size)
        self._update_dos_cols()
        self.schedule_layout(5)

    def _on_configure(self, e):
        if e.widget is self.root and self.dos:
            if self._fit_job is not None:
                try:
                    self.root.after_cancel(self._fit_job)
                except tk.TclError:
                    pass
            try:
                self._fit_job = self.root.after(120, self._fit_font)
            except tk.TclError:
                self._fit_job = None

    def _rebuild_skin_menu(self):
        m = self._skin_menu
        m.delete(0, "end")
        for name in self.skins:
            m.add_radiobutton(label=name, value=name, variable=self.v_skin,
                              command=lambda n=name: self.set_skin(n))

    def set_skin(self, name):
        if name not in self.skins:
            return False
        self.cfg[self._skin_cfg_key()] = name
        self.v_skin.set(name)
        self.theme = self._effective_theme()
        self.apply_theme()
        self._save_settings()
        return True

    def _set_override(self, path, value):
        """Record a user edit of the current skin (stored as a difference from the skin)."""
        name = self._skin_name()
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
            if value == base.get(path[0]):
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
        self.cfg["skin_overrides"].pop(self._skin_name(), None)
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

    def _append(self, pieces, _internal=False):
        """pieces: [(text, tagname_or_None)]. Anything written by the client itself first lets an
        unfinished server line (a prompt) appear, so the order on screen is always the true order."""
        if not _internal and self._pending and self._flush_job is None:
            self._flush_partial()           # (while the flush timer runs, the unfinished line is mid-arrival:
                                            # your echo goes above it rather than into the middle of it)
        if self.cfg.get("connect_boxes") and boxes is not None:
            pieces = boxes.connect_pieces(pieces, skip_tags=("echo", "system"))
        at_bottom = self.out.yview()[1] >= 0.999
        self.out.configure(state="normal")
        first = self.out.index("end-1c")
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
        if self.cfg.get("links", True):
            self._linkify(self.out, first)
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
        self._settle()
        # start on a fresh line if the server's prompt is sitting at the end of one
        prefix = "\n" if self.out.get("end-2c", "end-1c") not in ("\n", "") else ""
        self._append([(prefix + "[" + text + "]\n", "system")])
        self.sr_system(text)

    def clear(self):
        self._pending, self._line_plain, self._line_flushed, self._line_hidden_len = [], "", False, 0
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.configure(state="disabled")

    # ---- network pump ------------------------------------------------
    def _pump(self):
        # Always reschedules, whatever happens: an exception here must never silently
        # kill network handling for the rest of the session.
        try:
            deadline = time.time() + 0.02      # keep the window responsive during bursts
            shown = self.session
            for s in list(self.sessions):
                self.session = s               # this world is "the" world while its events are handled
                busy = not s.q.empty()
                try:
                    while time.time() < deadline:
                        try:
                            gen, kind, payload = self.q.get_nowait()
                        except queue.Empty:
                            break
                        if gen != self.conn.gen:
                            continue           # event from a connection we already dropped
                        try:
                            self._handle_event(kind, payload)
                        except Exception:  # noqa: BLE001
                            traceback.print_exc()
                            self.system("Internal error handling %s (see console); carrying on." % kind)
                    if (self.connected and self.cfg.get("keepalive") and
                            time.time() - self.last_send > KEEPALIVE_SECONDS):
                        self.conn.send(bytes([IAC, NOP]))
                        self.last_send = time.time()
                finally:
                    self.session = shown
                if s is not shown and busy:
                    self._sync_session_ui()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        finally:
            try:
                self._pump_job = self.root.after(25, self._pump)
            except tk.TclError:
                pass                       # window already destroyed

    def _on_root_destroy(self, e):
        if e.widget is self.root:
            for job in (self._pump_job, self._reconnect_job, self._fit_job, self._dos_job, self._flush_job,
                        self._layout_job, self._cd_job):
                if job is not None:
                    try:
                        self.root.after_cancel(job)
                    except tk.TclError:
                        pass
            try:
                self.save_notes()                      # notes typed in the last moments
                self.speech.set_backend(speech.NullBackend())
            except Exception:
                pass
            self.conn.close()

    def _set_disconnected(self):
        self.connecting = self.connected = False
        self._line, self._last_prompt = "", None     # stale stats must not outlive the session
        self._statbar_hide()
        self.update_dosbar()
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
            self._online_since = time.time()
            self._telnet_cli = False
            self._note_world_called()
            mode, self._dial_mode = self._dial_mode, None
            if mode == "modem":
                self._say("CONNECT%s" % (" (TLS)" if self.v_tls.get() else ""))
            elif mode == "telnet":
                self._say("Connected to %s.\nEscape character is '^]'." % self.v_host.get())
            elif self.dos and self.cfg["dos_flourish"]:
                self.system("CONNECT%s" % (" (TLS)" if self.v_tls.get() else ""))
            else:
                self.system("Connected to %s:%s%s." % (self.v_host.get(), self.v_port.get(),
                                                        " (TLS)" if self.v_tls.get() else ""))
            self.update_dosbar()
        elif kind == "failed":
            self._set_disconnected()
            mode, self._dial_mode = self._dial_mode, None
            if mode == "modem":
                self._say("NO CARRIER")
                self.system("Could not connect: %s" % payload)
            elif mode == "telnet":
                self._say("telnet: Unable to connect to remote host: %s" % payload)
                self._telnet_prompt()
            else:
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
        p = prompts.parse_prompt(self._line, self.current_profile())
        if p is None:
            return
        if self.term.echo_off:
            # A game prompt proves we are in play, not at a password prompt. The server never
            # sends WONT ECHO after new-account creation (comm.c state_confirm_new_account_password),
            # which would otherwise leave input masked for the whole session. Only this positive
            # evidence lifts the mask; guessing could leak a password into the log.
            self.term.echo_off = False
            if self._here():
                self.input.configure(show="")
        self._prompt_time = time.time()
        if p == self._last_prompt:
            self._start_cd_tick()
            return
        self._last_prompt = p
        if not self._here():
            return                                     # a hidden world keeps its stats; the screen shows the other
        self.statbar.set_data(self._prompt_view())
        self._statbar_show()
        self.update_dosbar()
        self._start_cd_tick()
        self.sr_alerts(self._prompt_view())

    def _prompt_view(self):
        """The last prompt with its cooldown timers counted down for the time since it arrived
        (the game lowers M and K by one every second)."""
        p = self._last_prompt
        if not p or not p.get("cooldowns"):
            return p
        gone = int(max(0.0, time.time() - self._prompt_time))
        if not gone:
            return p
        view = dict(p)
        view["cooldowns"] = [(lb, max(0, n - gone)) for lb, n in p["cooldowns"]]
        return view

    def _start_cd_tick(self):
        if self._cd_job is not None or not self._last_prompt:
            return
        if not any(n > 0 for _lb, n in self._prompt_view().get("cooldowns", [])):
            return
        try:
            self._cd_job = self.root.after(1000, self._cd_tick)
        except tk.TclError:
            self._cd_job = None

    def _cd_tick(self):
        self._cd_job = None
        if not self._last_prompt or not self.connected:
            return
        self.statbar.set_data(self._prompt_view())
        self.update_dosbar()
        self._start_cd_tick()
        self.sr_alerts(self._prompt_view())

    def _statbar_show(self):
        if (self.cfg.get("statbar") and self._last_prompt and not self.dos
                and not self.statbar.winfo_ismapped()):
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
        had_text = False
        for ev in self.term.feed(data):
            k = ev[0]
            if k == "text":
                had_text = True
                self._track_prompt(ev[1])
                self._feed_text(ev[1], ev[2])
            elif k == "send":
                self.conn.send(ev[1])
            elif k == "echo":
                if self._here():
                    self.input.configure(show="" if ev[1] else "*")
                if not ev[1]:
                    self.hist_pos = len(self.history)
            elif k == "bell" and self.cfg.get("bell"):
                self.root.bell()
        if self._pending and self._flush_job is None:
            self._flush_job = self._after_session(PARTIAL_FLUSH_MS, self._flush_partial)
        if had_text:
            self._update_statbar()
            self._new_output_bell()

    def _on_focus_in(self, e):
        """Coming back to the window (from another program, a dialog): keys must have somewhere to go."""
        if e.widget is self.root:
            try:
                self.root.after_idle(self._restore_focus)
            except tk.TclError:
                pass

    def _restore_focus(self):
        try:
            if self._overlay_open():
                self._overlay._cv.focus_set()
                return
            if getattr(self, "_notepad", None) or getattr(self, "_image_view", None):
                return
            fg = self.root.focus_get()
            if fg is None or fg is self.root or fg is self.out:
                self.input.focus_set()
        except (tk.TclError, AttributeError, KeyError):
            pass

    def _overlay_key_fallback(self, e):
        """A menu or dialog is open but the keyboard focus has strayed from it: put it back (Esc still closes)."""
        try:
            if not self._overlay_open():
                return
            fg = self.root.focus_get()
            if fg is not None and str(fg).startswith(str(self._overlay)):
                return
            if e.keysym == "Escape":
                self.dos_close_overlay()
                return "break"
            self._overlay._cv.focus_set()
        except (tk.TclError, AttributeError):
            pass

    def _window_active(self):
        """True while one of Sanctuary's windows is the one in front. (Tk keeps reporting a focused
        widget after you switch to another program, so on Windows ask the system instead.)"""
        if sys.platform.startswith("win"):
            try:
                import ctypes
                from ctypes import wintypes
                u = ctypes.windll.user32
                fg = u.GetForegroundWindow()
                pid = wintypes.DWORD(0)
                u.GetWindowThreadProcessId(fg, ctypes.byref(pid))
                return bool(fg) and pid.value == os.getpid()
            except Exception:
                pass
        return self.root.focus_displayof() is not None

    def _new_output_bell(self):
        if not self._here():
            self._mark_activity()
            return
        mode = self.cfg.get("bell_new", "off")
        if mode == "off" or time.time() - self._last_new_bell < 2.0:
            return
        try:
            front = self._window_active()
            scrolled = self.out.yview()[1] < 0.999
        except tk.TclError:
            return
        if mode == "always" or (mode == "unfocused" and not front) or (mode == "scrolled" and (scrolled or not front)):
            self._last_new_bell = time.time()
            self.root.bell()

    # ---- whole lines: triggers can act on a line before it is shown ----------------------
    def _feed_text(self, text, key):
        """Collect text into the current line; a complete line goes through the trigger engine."""
        if self.cfg.get("emoji") and emojis is not None:
            text = emojis.expand(text)
        while True:
            i = text.find("\n")
            if i < 0:
                if text:
                    self._pending.append((text, key))
                    self._line_plain += text
                return
            head = text[:i]
            if head:
                self._pending.append((head, key))
                self._line_plain += head
            self._finish_line(key)
            text = text[i + 1:]

    def _log_raw(self, text):
        if self.logfile:
            try:
                self.logfile.write(text)
                self.logfile.flush()
            except OSError:
                pass

    def _settle(self):
        """Show any unfinished line now (before something else is written after it)."""
        if self._pending or self._flush_job is not None:
            self._flush_partial()

    def _flush_partial(self):
        if self._flush_job is not None:
            try:
                self.root.after_cancel(self._flush_job)
            except tk.TclError:
                pass
            self._flush_job = None
        if not self._pending:
            return
        pieces, self._pending = self._pending, []
        if (self.cfg.get("hide_prompt") and not self._line_flushed and not self._line_hidden_len
                and prompts.parse_prompt(self._line_plain, self.current_profile()) is not None):
            self._line_hidden_len = len(self._line_plain)   # the bar shows it; keep it off the screen
            self._log_raw(self._line_plain)
            return
        self._append([(t, self._tag_for(k)) for t, k in pieces], _internal=True)
        self._line_flushed = True

    # the lines the game prints when your defence (DF) is back to full (regened_message in fight.c)
    DF_FULL_LINES = frozenset([
        "You fix up and readjust your ballistic armor.", "You fix up and readjust your armor.",
        "The punctures in your natural armor heal over.", "The pain from your injuries fades.",
        "Your energy shield flares strongly to life before fading to invisibility.",
        "Your fire shield flares strongly to life before fading to invisibility.",
        "Your ice shield flares strongly to life before fading to invisibility.",
        "Your lightning shield flares strongly to life before fading to invisibility.",
        "Your shield of stone forms strongly around you before fading to invisibility.",
        "Your shield of wood forms strongly around you before fading to invisibility.",
        "Your mental shield ripples strongly to life before fading to invisibility.",
        "Your shield of darkness flares strongly to life before fading to invisibility.",
        "Your shield pulses briefly with power before fading to invisibility.",
        "The discomfort from your injuries fades.", "You start to feel lucky again.",
        "You feel your mental fatigue lifting.", "You resettle your shield into place.",
        "You recover your defenses."])
    _WALK_RE = re.compile(r"^Your (.+?) walk(?: string)? is now: (.+?)\s*$")
    _TIME_RE = re.compile(r"^The time is [A-Z][a-z]{2} [A-Z][a-z]{2} +\d{1,2} (\d\d):(\d\d):(\d\d) (\d{4})\s*$")
    _NAME_RE = re.compile(r"^\[Name\s*\]\s+-\s+([A-Za-z][A-Za-z'-]{0,23})\s*$")

    def _df_full(self):
        """The game says your defence is back: top the DF gauge up now instead of waiting for the next prompt."""
        p = self._last_prompt
        hp = p.get("hp") if p else None
        if not hp or not hp[1] or hp[0] >= hp[1]:
            return
        new = dict(p)
        new["hp"] = (hp[1], hp[1], hp[2])
        g = list(p.get("gauges") or [])
        if g and g[0][0] == hp[2]:
            g[0] = (g[0][0], hp[1], hp[1])
            new["gauges"] = g
        self._last_prompt = new
        if not self._here():
            return
        view = self._prompt_view()
        self.statbar.set_data(view)
        self.update_dosbar()
        self.sr_alerts(view)

    def learn_from_line(self, plain):
        """Pick up facts the game states about itself: its clock (the `time` command's first line) and
        your character's name (the `display` command). Only the game's output is read, never your input."""
        try:
            rest = self._split_prompt(plain)[1]                  # a prompt may be stuck to the front of the line
        except Exception:
            rest = plain
        if rest.strip() in self.DF_FULL_LINES:
            self._df_full()
            return
        if rest.startswith("Your ") and " walk" in rest and self.cfg.get("walk_preview", True):
            m = self._WALK_RE.match(rest)
            if m:
                label, walk = m.group(1), m.group(2)
                who = self.cfg.get("char_name") or "Someone"
                form = "" if label.lower() in ("credit", "ego form", "ego") else " (%s)" % label
                self.set_notice("Preview%s: %s %s in from the north" % (form, who, walk), 90)
                return
        if plain.startswith("The time is "):
            m = self._TIME_RE.match(plain)
            if m:
                try:
                    # the game prints a date and time; compare its time of day with UTC now
                    h, mi, se = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    now = time.gmtime()
                    diff = (h * 3600 + mi * 60 + se) - (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec)
                    diff = ((diff + 43200) % 86400) - 43200            # nearest whole-day wrap
                    off = int(round(diff / 900.0)) * 900
                    if abs(off) <= 14 * 3600 and off != self.cfg.get("game_offset"):
                        self.cfg["game_offset"] = off
                        self._save_settings()
                except (ValueError, OverflowError):
                    pass
        elif plain.startswith("[Name"):
            m = self._NAME_RE.match(plain)
            if m and m.group(1) != self.cfg.get("char_name"):
                self.cfg["char_name"] = m.group(1)
                self._save_settings()

    def _finish_line(self, key):
        pieces, plain = self._pending, self._line_plain
        flushed, hidden = self._line_flushed, self._line_hidden_len
        self._pending, self._line_plain, self._line_flushed, self._line_hidden_len = [], "", False, 0
        if self._flush_job is not None:
            try:
                self.root.after_cancel(self._flush_job)
            except tk.TclError:
                pass
            self._flush_job = None
        self.learn_from_line(plain[hidden:] if hidden else plain)
        if hidden:
            plain = plain[hidden:]
            if not pieces:
                return                                    # nothing but the hidden prompt: drop it and its newline
        if self._iface is not None and self.iface_capture(pieces, plain):
            return                                        # the game's item editor talking: gathered, not scrolled
        shown, effects = self._run_triggers(pieces, plain, flushed)
        if shown is None:                                 # hidden by a trigger
            self._log_raw(plain + "\n")
        else:
            segs = [(t, self._tag_for(k)) for t, k in shown]
            segs.append(("\n", self._tag_for(key)))
            self._append(segs, _internal=True)
        self.sr_hear(plain, effects)
        for fx in effects:
            self._do_effect(fx)

    def _run_triggers(self, pieces, plain, flushed):
        """Returns (pieces_to_show_or_None, side_effects). Highlight and hide only apply to text
        that has not been drawn yet; commands, beeps and notes always run."""
        if triggers is None or not plain or not any(t.get("enabled", True) for t in self.cfg["triggers"]):
            return pieces, []
        self._guard.begin_line()
        gag, effects, routes = False, [], []
        for trig, m in triggers.match_line(plain, self.cfg["triggers"]):
            for act in trig["actions"]:
                kind = act["type"]
                if kind == "highlight" and not flushed:
                    lo, hi = (0, len(plain)) if act.get("scope") == "line" else (m["start"], m["end"])
                    pieces = apply_highlight(pieces, lo, hi, act.get("fg"), act.get("bg"), act.get("bold", False))
                elif kind == "gag":
                    gag = True
                elif kind == "route":
                    routes.append(act["pane"])
                    gag = gag or bool(act.get("gag"))        # copy by default; "hide from main" is per rule
                elif kind == "send":
                    effects.append(("send", trig["name"], act, m["captures"]))
                elif kind == "beep":
                    effects.append(("beep",))
                elif kind == "note":
                    effects.append(("note", triggers.expand(act["text"], m["captures"])))
                elif kind == "status":
                    effects.append(("status", triggers.expand(act["text"], m["captures"]).replace(
                        "{name}", self.cfg.get("char_name") or "Someone")))
                elif kind == "speak":
                    effects.append(("speak", triggers.expand(act["text"], m["captures"]), bool(act.get("interrupt"))))
                elif kind == "silence":
                    effects.append(("silence",))
        if routes:
            snapshot = list(pieces) if pieces else [(plain, (None, None, False, False, False, False))]
            for pane in routes:
                effects.insert(0, ("route", pane, snapshot))      # panes get the line before commands run
        if gag and not flushed:
            return None, effects
        return pieces, effects

    def set_notice(self, text, secs=60):
        """Show a short message on the status line (the toolbar, or the DOS bar) for a while."""
        text = " ".join(str(text).split())[:120]
        self._notice_text = text
        try:
            self.notice.configure(text=text)
            if self._notice_job is not None:
                self.root.after_cancel(self._notice_job)
            self._notice_job = self.root.after(secs * 1000, lambda: self.set_notice("", 0)) if text else None
        except tk.TclError:
            self._notice_job = None
        self.update_dosbar()

    def _do_effect(self, fx):
        if fx[0] == "route":
            self.pane_append(fx[1], fx[2])
        elif fx[0] == "beep":
            if self.cfg.get("bell"):
                self.root.bell()
        elif fx[0] == "note":
            self.system(fx[1])
        elif fx[0] == "status":
            self.set_notice(fx[1])
        elif fx[0] == "speak":
            if self.sr_on():
                self.speech.say(fx[1], interrupt=fx[2])
        elif fx[0] == "send":
            _kind, name, act, caps = fx
            for cmd in triggers.expand_commands(act["text"], caps):   # split first: game text can never add commands
                if not self.connected:
                    return
                if self._guard.allow(name):
                    self.send_line(cmd, echo=act.get("echo", True))
                else:
                    self.system("Trigger '%s' stopped: too many commands too fast." % name)
                    return

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
            if self._dial_command(line):
                return "break"
            if self.intercept_line(line):
                return "break"
            if line.startswith("//"):
                line = line[1:]
        self.send_line(line, echo=not secret, secret=secret)
        return "break"

    # ---- dialing by hand: ATDT <host> <port>, and a pretend telnet command line --------------
    def _offline(self):
        return not (self.connected or self.connecting)

    def _say(self, text):
        """Plain output line from the client itself (modem / telnet replies), no brackets."""
        self._settle()
        prefix = "\n" if self.out.get("end-2c", "end-1c") not in ("\n", "") else ""
        self._append([(prefix + text + "\n", None)])

    def _dial_command(self, line):
        """Handle modem-style and telnet-style commands, but only while NOT connected (online,
        everything typed belongs to the game). Returns True if the line was consumed."""
        if self._telnet_cli:
            if not self._offline():
                self._telnet_cli = False
            else:
                self._append([(line + "\n", "echo")])
                self._telnet_cli_line(line)
                return True
        if not self._offline():
            return False
        parts = line.strip().split(None, 1)
        if not parts:
            return False
        word, rest = parts[0].upper(), (parts[1] if len(parts) > 1 else "")
        if word in AT_DIAL:
            self._append([(line + "\n", "echo")])
            try:
                host, port, tls, _name = parse_dial_target(rest, self.cfg["worlds"])
            except ValueError as e:
                self._say("ERROR: %s" % e)
                return True
            self._begin_dial(host, port, tls, "modem")
            return True
        if word in AT_OK and not rest:
            self._append([(line + "\n", "echo")])
            self._say("OK")
            return True
        if word == "TELNET":
            self._append([(line + "\n", "echo")])
            self._telnet_start(rest)
            return True
        return False

    def _begin_dial(self, host, port, tls, mode):
        self.v_host.set(host)
        self.v_port.set(str(port))
        self.v_tls.set(bool(tls))
        self._cancel_reconnect()
        if mode == "modem":
            self._say("DIALING %s:%d%s" % (host, port, " (TLS)" if tls else ""))
        elif mode == "telnet":
            self._say("Trying %s..." % host)
        self._start_connect(quiet=mode is not None, mode=mode)

    def _telnet_prompt(self):
        self._append([("telnet> ", None)])                # no newline: the typed command follows

    def _telnet_start(self, rest):
        if rest.strip():
            try:
                host, port, tls, _n = parse_dial_target(rest, self.cfg["worlds"], default_port=23)
            except ValueError as e:
                self._say("telnet: %s" % e)
                return
            self._begin_dial(host, port, tls, "telnet")
            return
        self._telnet_cli = True
        self._say("Welcome to the telnet client.\nEscape character is '^]'.\n")
        self._telnet_prompt()

    def _telnet_cli_line(self, line):
        parts = line.strip().split(None, 1)
        if not parts:
            self._telnet_prompt()
            return
        cmd, rest = parts[0].lower(), (parts[1] if len(parts) > 1 else "")
        if cmd in ("o", "op", "ope", "open"):
            try:
                host, port, tls, _n = parse_dial_target(rest, self.cfg["worlds"], default_port=23)
            except ValueError as e:
                self._say("usage: open host-name [port]   (%s)" % e)
                self._telnet_prompt()
                return
            self._begin_dial(host, port, tls, "telnet")
            return                                         # the connection events print the rest
        if cmd in ("q", "qu", "qui", "quit", "exit"):
            self._telnet_cli = False
            self._say("")
            return
        if cmd in ("?", "h", "he", "hel", "help"):
            for t in TELNET_HELP:
                self._say(t)
        elif cmd in ("st", "sta", "stat", "statu", "status"):
            self._say("No connection.")
        elif cmd in ("c", "cl", "clo", "clos", "close"):
            self._say("?No connection.")
        else:
            self._say("?Invalid command")
        self._telnet_prompt()

    # ---- saved worlds ---------------------------------------------------------------------
    def dial_world(self, world, modem=None):
        """Connect to a saved world (disconnecting first if already online)."""
        w = clean_world(world)
        if w is None:
            return
        use_modem = (self.dos and self.cfg["dos_flourish"]) if modem is None else modem
        mode = "modem" if use_modem else None

        def go():
            self._begin_dial(w["host"], w["port"], w["tls"], mode)

        if self.connected or self.connecting:
            for s in self.sessions:                    # already open in a tab: go there
                if s.name == w["name"] and (s.connected or s.connecting):
                    self.switch_session(s)
                    return
            if self.open_new_world(w["name"]) is None:
                return
        else:
            self.session.name = w["name"]
            self._refresh_world_ui()
        go()

    def _save_worlds(self, worlds):
        self.cfg["worlds"] = clean_worlds(worlds)
        self._save_settings()

    def _note_world_called(self):
        """Remember when a saved world was last connected."""
        try:
            host, port = self.v_host.get().strip().lower(), int(self.v_port.get())
        except ValueError:
            return
        changed = False
        for w in self.cfg["worlds"]:
            if w["host"].lower() == host and w["port"] == port:
                w["last"] = int(time.time())
                changed = True
        if changed:
            self._save_settings()

    # ---- world settings files (.snc) -----------------------------------------------------
    def _world_tools(self):
        return {"clean_world": clean_world, "validate_trigger": triggers.validate_trigger,
                "validate_alias": triggers.validate_alias, "validate_prompt": prompts.validate_profile,
                "validate_panes": layout.validate_panes if layout else (lambda x: []),
                "validate_layout": (lambda d, k=None: layout.validate_layout(d, known_panes=k)) if layout
                else (lambda d, k=None: {"regions": [], "min_main_cols": 80}),
                "validate_gradients": colortools.validate_saved, "validate_designs": customize_data.validate_designs}

    def _current_world(self):
        host, port = self.v_host.get().strip(), self.v_port.get().strip()
        for w in self.cfg.get("worlds", []):
            if w["host"].lower() == host.lower() and str(w["port"]) == port:
                return dict(w)
        try:
            return clean_world({"name": host[:40] or "World", "host": host, "port": int(port), "tls": self.v_tls.get(),
                                "note": ""}) or {"name": "World", "host": DEFAULT_HOST, "port": TLS_PORT, "tls": True, "note": ""}
        except ValueError:
            return {"name": "World", "host": DEFAULT_HOST, "port": TLS_PORT, "tls": True, "note": ""}

    def default_export_path(self):
        w = self._current_world()
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", w["name"]).strip("._") or "world"
        return os.path.join(os.path.expanduser("~"), "Sanctuary-%s%s" % (safe, worldfile.EXT))

    def export_world_file(self, path, parts=worldfile.PARTS):
        path = os.path.expanduser(str(path or "").strip().strip('"'))
        if not path:
            return False, "Give a file name."
        if not path.lower().endswith(worldfile.EXT):
            path += worldfile.EXT
        if os.path.exists(path):
            return False, "%s already exists; choose another name (nothing was overwritten)." % path
        data = worldfile.dumps(worldfile.build(self.cfg, self._current_world(), parts))
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(data)
        except OSError as e:
            return False, "Could not write the file: %s" % (e.strerror or type(e).__name__)
        return True, "Saved %s (%d bytes)." % (path, len(data.encode("utf-8")))

    def import_world_file(self, path):
        path = os.path.expanduser(str(path or "").strip().strip('"'))
        try:
            if os.path.getsize(path) > worldfile.MAX_BYTES:
                return False, ["That file is too big to be a world file."]
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read(worldfile.MAX_BYTES + 1)
        except (OSError, UnicodeError) as e:
            return False, ["Could not read that file: %s" % (getattr(e, "strerror", None) or type(e).__name__)]
        bundle, why = worldfile.loads(text)
        if bundle is None:
            return False, [why]
        old_layout = self.cfg.get("layout")
        said = worldfile.merge(self.cfg, bundle, self._world_tools())
        if self.cfg.get("layout") != old_layout:
            self.cfg["panes_hidden"] = []
            self._region_active = {}
        self._save_settings()
        if layout is not None:
            self.layout_panes()
        return True, said or ["Nothing new in that file."]

    def open_export(self):
        labels = {"triggers": "Triggers", "aliases": "Aliases", "panes": "Pane layout", "prompts": "Prompt formats",
                  "gradients": "Gradient patterns", "designs": "Design book"}
        if self.dos:
            fields = [{"key": "path", "label": "File", "type": "text", "value": self.default_export_path(), "width": 50}]
            fields += [{"key": p, "label": labels[p], "type": "check", "value": True} for p in worldfile.PARTS]

            def result(res, vals):
                if res == "export":
                    ok, m = self.export_world_file(vals.get("path", ""), [p for p in worldfile.PARTS if vals.get(p)])
                    self.system(m)
                    if not ok:
                        self._reopen(self.open_export)
            return self._dos_dialog("Export world settings", fields, [("Export", "export"), ("Cancel", "cancel")],
                                    result, width=70, message="Saves the current world and what you tick, as one .snc file.")
        from tkinter import filedialog
        top = tk.Toplevel(self.root)
        top.title("Export world settings")
        top.transient(self.root)
        vs = {p: tk.BooleanVar(value=True) for p in worldfile.PARTS}
        tk.Label(top, text="Save the current world, and:", anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        for p in worldfile.PARTS:
            tk.Checkbutton(top, text=labels[p], variable=vs[p]).pack(anchor="w", padx=24)

        def go():
            path = filedialog.asksaveasfilename(parent=top, defaultextension=worldfile.EXT, initialdir=os.path.expanduser("~"),
                                                initialfile=os.path.basename(self.default_export_path()),
                                                filetypes=[("Sanctuary world", "*" + worldfile.EXT), ("All files", "*.*")])
            if not path:
                return
            if os.path.exists(path):                      # the file dialog already asked about replacing it
                try:
                    os.remove(path)
                except OSError:
                    pass
            ok, m = self.export_world_file(path, [p for p in worldfile.PARTS if vs[p].get()])
            self.system(m)
            if ok:
                top.destroy()
        bf = tk.Frame(top)
        bf.pack(pady=10)
        tk.Button(bf, text="Choose file...", command=go).pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", command=top.destroy).pack(side="left", padx=4)
        self._theme_tree(top)
        return top

    def open_import(self):
        if self.dos:
            def result(res, vals):
                if res == "import":
                    ok, lines = self.import_world_file(vals.get("path", ""))
                    for ln in lines:
                        self.system(ln)
                    if not ok:
                        self._reopen(self.open_import)
            return self._dos_dialog("Import world settings", [{"key": "path", "label": "File", "type": "text", "value": "",
                                                               "width": 52}],
                                    [("Import", "import"), ("Cancel", "cancel")], result, width=72,
                                    message="Triggers that send commands and all aliases arrive switched off.")
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.root, initialdir=os.path.expanduser("~"),
                                          filetypes=[("Sanctuary world", "*" + worldfile.EXT), ("All files", "*.*")])
        if path:
            ok, lines = self.import_world_file(path)
            for ln in lines:
                self.system(ln)

    def open_worlds(self):
        if self.dos:
            return self.dos_worlds()
        if self._worlds_win is not None:
            try:
                if self._worlds_win.winfo_exists():
                    self._worlds_win.lift()
                    return self._worlds_win
            except tk.TclError:
                pass
        top = tk.Toplevel(self.root)
        self._worlds_win = top
        top.title("Worlds")
        top.transient(self.root)
        tk.Label(top, text="Saved worlds").pack(anchor="w", padx=10, pady=(8, 0))
        box = tk.Frame(top)
        box.pack(fill="both", expand=True, padx=10, pady=4)
        lb = tk.Listbox(box, height=12, width=64, exportselection=False, font=self.f_norm,
                        highlightthickness=0, activestyle="none")
        sc = tk.Scrollbar(box, command=lb.yview)
        lb.configure(yscrollcommand=sc.set)
        lb.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

        def refresh(select=None):
            lb.delete(0, "end")
            for w in self.cfg["worlds"]:
                lb.insert("end", "%-22s %-32s %s" % (w["name"][:22], "%s:%d" % (w["host"], w["port"]),
                                                   "TLS" if w["tls"] else "plain"))
            if self.cfg["worlds"]:
                i = max(0, min(len(self.cfg["worlds"]) - 1, select or 0))
                lb.selection_set(i)
                lb.see(i)

        def current():
            sel = lb.curselection()
            return sel[0] if sel else None

        def connect(_e=None):
            i = current()
            if i is not None:
                w = self.cfg["worlds"][i]
                top.destroy()
                self.dial_world(w, modem=False)
            return "break"

        def edit_form(index):
            existing = self.cfg["worlds"][index] if index is not None else None
            self._world_form(existing, lambda w: save(index, w), top)

        def save(index, w):
            lst = list(self.cfg["worlds"])
            clash = [i for i, x in enumerate(lst) if x["name"].lower() == w["name"].lower() and i != index]
            if clash:
                messagebox.showerror("Worlds", "There is already a world called '%s'." % w["name"], parent=top)
                return False
            if index is None:
                lst.append(w)
            else:
                w["last"] = lst[index]["last"]
                lst[index] = w
            self._save_worlds(lst)
            refresh(len(lst) - 1 if index is None else index)
            return True

        def delete(_e=None):
            i = current()
            if i is None:
                return "break"
            name = self.cfg["worlds"][i]["name"]
            if messagebox.askyesno("Worlds", "Delete '%s'?" % name, parent=top):
                lst = list(self.cfg["worlds"])
                del lst[i]
                self._save_worlds(lst)
                refresh(i)
            return "break"

        btns = tk.Frame(top)
        btns.pack(fill="x", padx=10, pady=(4, 10))
        tk.Button(btns, text="Connect", width=10, command=connect).pack(side="left")
        tk.Button(btns, text="Add...", width=8, command=lambda: edit_form(None)).pack(side="left", padx=6)
        tk.Button(btns, text="Edit...", width=8,
                  command=lambda: edit_form(current()) if current() is not None else None).pack(side="left")
        tk.Button(btns, text="Delete", width=8, command=delete).pack(side="left", padx=6)
        tk.Button(btns, text="Close", width=8, command=top.destroy).pack(side="right")
        lb.bind("<Double-Button-1>", connect)
        lb.bind("<Return>", connect)
        lb.bind("<Delete>", delete)
        lb.bind("<Insert>", lambda e: edit_form(None))
        top.bind("<Escape>", lambda e: top.destroy())
        top._actions = dict(connect=connect, delete=delete, add=lambda: edit_form(None),
                            edit=lambda: edit_form(current()), refresh=refresh, listbox=lb, save=save)
        refresh()
        self._theme_tree(top)
        lb.focus_set()
        return top

    def _store_world(self, index, w):
        """Add (index None) or replace a saved world. Returns (ok, message)."""
        lst = list(self.cfg["worlds"])
        if any(x["name"].lower() == w["name"].lower() and i != index for i, x in enumerate(lst)):
            return False, "There is already a world called '%s'." % w["name"]
        if index is None:
            if len(lst) >= 200:
                return False, "Too many saved worlds (200 maximum)."
            lst.append(w)
        else:
            w["last"] = lst[index]["last"]
            lst[index] = w
        self._save_worlds(lst)
        return True, "Saved '%s'." % w["name"]

    # ---- DOS look: the dialing directory ---------------------------------------------------
    def _worlds_rows(self):
        rows = []
        for i, w in enumerate(self.cfg["worlds"]):
            last = time.strftime("%Y-%m-%d", time.localtime(w["last"])) if w["last"] else "-"
            rows.append({"cells": [str(i + 1), w["name"], w["host"], str(w["port"]),
                                   "yes" if w["tls"] else "", last],
                         "role": "normal" if w["last"] else "dim"})
        return rows

    def dos_worlds(self, selected=0):
        cols = [{"title": "#", "width": 3, "align": "r"}, {"title": "Name", "width": 18},
                {"title": "Host", "width": 0}, {"title": "Port", "width": 5, "align": "r"},
                {"title": "TLS", "width": 3}, {"title": "Last call", "width": 10}]
        hints = [("Enter", "Dial"), ("A", "Add"), ("E", "Edit"), ("Del", "Remove"), ("Esc", "Close")]

        def act(name, idx, table):
            worlds = self.cfg["worlds"]
            if name == "select" and idx is not None:
                w = worlds[idx]
                table.close()
                self.dial_world(w)
            elif name == "add":
                table.close()
                self._dos_world_form(None, None)
            elif name == "edit" and idx is not None:
                table.close()
                self._dos_world_form(idx, None)
            elif name == "remove" and idx is not None:
                table.close()
                victim = worlds[idx]["name"]
                self._overlay = dosui.confirm(
                    self.root, "Remove", "Remove '%s' from the directory?" % victim, self._dc(), self.f_norm,
                    lambda r, v: self._remove_world(idx) if r == "yes" else self._reopen(self.dos_worlds, idx))

        table = dosui.DosTable(self.root, "Dialing directory", cols, self._worlds_rows(), self._dc(),
                               self.f_norm, act, hints=hints, min_width=64, selected=selected)
        self._overlay = table
        table.open()
        return table

    def _remove_world(self, idx):
        lst = list(self.cfg["worlds"])
        if 0 <= idx < len(lst):
            del lst[idx]
            self._save_worlds(lst)
        self._reopen(self.dos_worlds, max(0, idx - 1))

    def _dos_world_form(self, index, values):
        existing = self.cfg["worlds"][index] if index is not None else None
        if values is None:
            values = {"name": existing["name"] if existing else "", "host": existing["host"] if existing else "",
                      "port": str(existing["port"]) if existing else str(TLS_PORT),
                      "tls": existing["tls"] if existing else True, "note": existing["note"] if existing else ""}
        fields = [{"key": "name", "label": "Name", "type": "text", "value": values["name"], "width": 30},
                  {"key": "host", "label": "Host", "type": "text", "value": values["host"], "width": 30},
                  {"key": "port", "label": "Port", "type": "text", "value": values["port"], "width": 6},
                  {"key": "tls", "label": "Use TLS", "type": "check", "value": bool(values["tls"])},
                  {"key": "note", "label": "Note", "type": "text", "value": values["note"], "width": 40}]

        def result(res, vals):
            back = lambda sel: self._reopen(self.dos_worlds, sel)
            if res != "save":
                back(index if index is not None else 0)
                return
            w = clean_world(vals)
            if w is None:
                self.system("Please give a name, a valid host and a port from 1 to 65535.")
                self._reopen(lambda: self._dos_world_form(index, vals))
                return
            ok, msg = self._store_world(index, w)
            if not ok:
                self.system(msg)
                self._reopen(lambda: self._dos_world_form(index, vals))
                return
            back(len(self.cfg["worlds"]) - 1 if index is None else index)

        return self._dos_dialog("Edit entry" if existing else "New entry", fields,
                                [("Save", "save"), ("Cancel", "cancel")], result, width=58)

    def _world_form(self, world, on_save, parent):
        """Add / edit one world in an ordinary dialog."""
        win = tk.Toplevel(parent)
        win.title("Edit world" if world else "Add world")
        win.transient(parent)
        v = {"name": tk.StringVar(value=world["name"] if world else ""),
             "host": tk.StringVar(value=world["host"] if world else ""),
             "port": tk.StringVar(value=str(world["port"]) if world else str(TLS_PORT)),
             "note": tk.StringVar(value=world["note"] if world else "")}
        tls = tk.BooleanVar(value=world["tls"] if world else True)
        for r, (label, key, width) in enumerate((("Name", "name", 30), ("Host", "host", 30),
                                                 ("Port", "port", 8), ("Note", "note", 40))):
            tk.Label(win, text=label).grid(row=r, column=0, sticky="w", padx=(10, 6), pady=4)
            tk.Entry(win, textvariable=v[key], width=width).grid(row=r, column=1, sticky="w", pady=4, padx=(0, 10))
        tk.Checkbutton(win, text="Use TLS", variable=tls).grid(row=4, column=1, sticky="w")

        def ok():
            w = clean_world({"name": v["name"].get(), "host": v["host"].get(), "port": v["port"].get(),
                             "tls": tls.get(), "note": v["note"].get()})
            if w is None:
                messagebox.showerror("World", "Please give a name, a valid host and a port from 1 to 65535.",
                                     parent=win)
                return
            if on_save(w) is not False:
                win.destroy()

        row = tk.Frame(win)
        row.grid(row=5, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        tk.Button(row, text="OK", width=8, command=ok).pack(side="right")
        tk.Button(row, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        win.bind("<Return>", lambda e: ok())
        win.bind("<Escape>", lambda e: win.destroy())
        win._set = v
        win._tls = tls
        win._ok = ok
        self._theme_tree(win)
        return win

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

    def send_line(self, line, echo=True, secret=False, expand=True):
        """secret=True (password prompt): no alias expansion, no local echo, and nothing
        about the content ever appears in a message."""
        if not self.connected:
            self.system("Not connected.")
            return
        parts = [line] if (secret or not expand) else self._expand(line)
        if self.cfg.get("emoji") and emojis is not None and not secret:
            parts = [emojis.shorten(p) for p in parts]
        for part in parts:
            if not secret and part.split(None, 1)[:1] == ["quit"]:
                self._quit_sent_at = time.time()   # the close that follows is intentional
            clean, dropped, truncated = sanitize_outgoing(part)
            if dropped:
                self.system("%d character%s the game can't accept %s removed from that line."
                            % (dropped, "" if dropped == 1 else "s", "was" if dropped == 1 else "were"))
            if truncated:
                self.system("Line cut to %d characters (the game's limit is about 6000)." % MAX_LINE)
            if echo and self.cfg.get("show_echo", True):
                self._append([(clean + "\n", "echo")])
            # clean is printable ASCII, so no IAC (0xFF) can occur and no escaping is needed
            if not self.conn.send(clean.encode("ascii") + b"\r\n"):
                self.system("Send failed.")
                return
        self.last_send = time.time()
        if self.cfg.get("scroll_on_send", True) and not secret:
            self.out.see("end")

    def _expand(self, line):
        """Alias expansion: an alias is a first word that expands to one or more commands
        (separated by ';', arguments as %1-%9 and %*; with no % in the body, the arguments are
        simply appended to the last command)."""
        if triggers is None:
            return [line]
        word, _, rest = line.partition(" ")
        alias = triggers.find_alias(word, self.cfg["alias_rules"])
        if alias is None:
            return [line]
        return triggers.expand_alias(alias, rest)

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
        if self._extras_command(cmd, arg) or self._tools_command(cmd, arg) or self._access_command(cmd, arg) \
                or self._update_command(cmd, arg) or self._worlds_command(cmd, arg):
            return
        if cmd == "export":
            if arg:
                self.system(self.export_world_file(arg)[1])
            else:
                self.open_export()
            return
        if cmd == "import":
            if arg:
                for ln in self.import_world_file(arg)[1]:
                    self.system(ln)
            else:
                self.open_import()
            return
        if cmd in ("help", "?"):
            self.system("Local commands:\n"
                        "  /connect [host [port]]   /disconnect   /reconnect   /quit\n"
                        "  /world [n|name]          /newworld [name]   /closeworld   (Ctrl+F1..F12)\n"
                        "  /alias name expansion    (use ; between commands, $* for arguments)\n"
                        "  /unalias name            /aliases\n"
                        "  /log [file]              start or stop logging\n"
                        "  /clear                   //text sends \"/text\" to the game\n"
                        "  /timer 10m [label]       /timer list | cancel [n]   (also 21:30, game 21:30)\n"
                        "  /moon   /notes   /hotkeys\n"
                        "  /hex ff8800              /gradient [text]   /customize\n"
                        "  /export [file]           /import file   (world settings, .snc)\n"
                        "  /sr on|off|status|help|test   screen reader mode\n"
                        "  /update                  check for a newer Sanctuary")
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
        elif cmd == "worlds":
            self.open_worlds()
        elif cmd == "prompt":
            self.edit_prompt()
        elif cmd == "triggers":
            self.open_triggers()
        elif cmd == "dial":
            self._dial_command("ATDT " + arg) if arg else self.system("Usage: /dial host [port] [tls|plain] or a saved world's name")
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
            a = triggers.validate_alias({"name": name, "body": exp.strip(), "enabled": True}) if triggers else None
            if a is None:
                self.system("Usage: /alias name expansion   (use ; between commands, %1-%9 / %* for arguments)")
            else:
                rules = [r for r in self.cfg["alias_rules"] if r["name"].lower() != a["name"].lower()]
                if len(rules) >= 200:
                    self.system("Too many aliases (200 maximum).")
                else:
                    rules.append(a)
                    self.cfg["alias_rules"] = rules
                    self._save_settings()
                    self.system("Alias %s = %s" % (a["name"], a["body"]))
        elif cmd == "unalias":
            rules = [r for r in self.cfg["alias_rules"] if r["name"].lower() != arg.strip().lower()]
            if len(rules) < len(self.cfg["alias_rules"]):
                self.cfg["alias_rules"] = rules
                self._save_settings()
                self.system("Removed alias %s." % arg.strip())
            else:
                self.system("No such alias.")
        elif cmd == "aliases":
            al = self.cfg["alias_rules"]
            self.system("\n".join("%s%s = %s" % (r["name"], "" if r["enabled"] else " (off)", r["body"])
                                  for r in sorted(al, key=lambda r: r["name"].lower())) if al else "No aliases.")
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

    def _start_connect(self, auto=False, quiet=False, mode=None):
        if self._here():
            host = self.v_host.get().strip()
            try:
                port = int(self.v_port.get())
            except ValueError:
                messagebox.showerror("Port", "Port must be a number.")
                self._cancel_reconnect()
                return
            tls = bool(self.v_tls.get())
            self.session.host, self.session.port, self.session.tls = host, port, tls
            self.cfg.update(host=host, port=port, tls=tls)
            self._save_settings()
        else:
            host, port, tls = self.session.host, self.session.port, self.session.tls
        self.connecting = True
        self.btn.configure(text="Cancel")
        self.status.configure(text="Connecting…")
        self._dial_mode = mode
        if quiet:
            pass                                      # the caller already printed its own wording
        elif self.dos and self.cfg["dos_flourish"]:
            self.system("%s%s:%d" % ("ATDT " if not auto else "ATDT (redial) ", host, port))
        else:
            self.system("%s %s:%d…" % ("Reconnecting to" if auto else "Connecting to", host, port))
        self.update_dosbar()
        self.gen += 1
        self.conn = Connection(self.q, self.gen)
        self.conn.open(host, port, tls, self.v_verify.get())

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
        self._reconnect_job = self._after_session(min(1000, left * 1000), self._reconnect_tick)

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
            path = time.strftime("sanctuary-%Y%m%d-%H%M%S.log")
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
        self._sync_variants()
        self._font_changed()
        self.statbar.refresh()
        self._restyle_dosbar()
        self._save_settings()
        return True

    def _zoom(self, d):
        if self.dos:
            if self.cfg["dos_autofit"]:
                self.cfg["dos_autofit"] = False  # the user is choosing a size now
                self.system("Font auto-fit is off (zoom keys set the size). Turn it back on with F7 > Auto-fit size.")
            n = max(MIN_FONT, min(MAX_FONT, int(self.f_norm.cget("size")) + d))
            self.cfg["dos_font_size"] = n        # the DOS look remembers its own size
            self._set_font_size(n)
            self._save_settings()
            return "break"
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
                    m = str(w.cget("menu"))
                    if m:
                        w.nametowidget(m).configure(bg=th["panel"], fg=th["fg"], activebackground=th["select"],
                                                    activeforeground=th["fg"])
            except tk.TclError:
                pass
        for c in w.winfo_children():
            self._theme_tree(c)

    def choose_font(self):
        """Dialog: monospace families only, size, live preview."""
        if self.dos:
            return self.dos_font_menu()
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
        tk.Label(row, text="Line spacing").pack(side="left", padx=(14, 0))
        v_gap = tk.IntVar(value=int(self.cfg["line_spacing"]))
        tk.Spinbox(row, from_=0, to=12, width=3, textvariable=v_gap).pack(side="left", padx=6)

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
            try:
                self.apply_spacing(int(v_gap.get()))
            except (tk.TclError, ValueError):
                pass
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
        if self.dos:
            return self.dos_colors_menu(fresh=True)
        if self._colors_win is not None:
            try:
                if self._colors_win.winfo_exists():
                    self._colors_win.lift()
                    return self._colors_win
            except tk.TclError:
                pass
        snapshot = (self._skin_name(), copy.deepcopy(self.cfg["skin_overrides"]), self._skin_cfg_key())
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
        var = tk.StringVar(value=self._skin_name())
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
            var.set(self._skin_name())
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
            self.cfg[snapshot[2]], self.cfg["skin_overrides"] = snapshot[0], snapshot[1]
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
        for s in self.sessions:
            try:
                s.conn.close()
            except Exception:  # noqa: BLE001
                pass
        self.conn.close()
        if self.logfile:
            self.logfile.close()
        self._save_settings()
        self.root.destroy()


def migrate_legacy_files(old_settings, new_settings, old_skins, new_skins):
    """After the rename from "Duskholm": copy (never move, never overwrite) the old settings file
    and skin folder to their new names so nothing is lost. Returns what was copied."""
    done = []
    try:
        if os.path.isfile(old_settings) and not os.path.exists(new_settings):
            shutil.copyfile(old_settings, new_settings)
            done.append("settings")
        if os.path.isdir(old_skins) and not os.path.exists(new_skins):
            os.makedirs(new_skins, exist_ok=True)
            for fn in os.listdir(old_skins):
                src = os.path.join(old_skins, fn)
                if fn.lower().endswith(".json") and os.path.isfile(src) and os.path.getsize(src) <= 65536:
                    shutil.copyfile(src, os.path.join(new_skins, fn))
            done.append("skins")
    except OSError:
        pass
    return done


for _n in SESSION_FIELDS:
    setattr(App, _n, _session_property(_n))
del _n


def main():
    home = os.path.expanduser("~")
    migrate_legacy_files(os.path.join(home, ".duskholm_client.json"), SETTINGS_PATH,
                         os.path.join(home, ".duskholm_skins"), user_skin_dir())
    args = [a for a in sys.argv[1:] if a != "--screen-reader"]
    want_sr = "--screen-reader" in sys.argv[1:]
    host = args[0] if args else None
    port = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    root = tk.Tk()
    app = App(root, host, port)
    if want_sr and not app.sr_on():
        root.after(400, lambda: app._set_extra("screen_reader", True))
    root.mainloop()


if __name__ == "__main__":
    main()
