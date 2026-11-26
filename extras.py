"""Small tools for Sanctuary: timers, clock, notepad, moon window, hotkeys (mixed into the App).

Everything that can be worked out without a window (reading a time like '10m' or 'game 21:30',
reading a key name like 'Ctrl-T') is a plain function with no GUI, so it can be tested on its own."""
import os
import re
import time
import datetime
import tkinter as tk

try:
    import moon
except ImportError:                     # the moon window and game clock need it
    moon = None
try:
    import dosui
except ImportError:
    dosui = None
import gametime

MAX_TIMERS = 20
MAX_TIMER_SECS = 7 * 86400
NOTES_MAX = 1_000_000


# ======================================================================================
# reading what the user typed
# ======================================================================================
_DUR = re.compile(r"^(?:(\d{1,3})d)?(?:(\d{1,4})h)?(?:(\d{1,5})m)?(?:(\d{1,6})s)?$", re.I)
_CLOCK = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", re.I)


def _clock_hm(text):
    m = _CLOCK.match(text.strip())
    if not m or (m.group(2) is None and m.group(3) is None):
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if ap == "pm" else 0)
    if h > 23 or mi > 59:
        return None
    return h, mi


def parse_when(text, now=None, game_offset=None, game=None):
    """What a timer is waiting for: '10m', '1h30m', '90s', '45' (minutes), '21:30' / '9:30pm'
    (your local clock) or 'game 21:30' / 'et 9pm' (the game's Eastern clock).
    Returns (due_timestamp, kind) with kind 'after', 'local' or 'game'; raises ValueError."""
    now = time.time() if now is None else float(now)
    t = " ".join(str(text or "").split()).lower()
    if not t:
        raise ValueError("Say when: for example 10m, 1h30m, 21:30 or game 21:30.")
    m = re.match(r"^(game|et|eastern)\s+(.+)$", t)
    if m:
        hm = _clock_hm(m.group(2))
        if hm is not None and game is not None:                  # this world's own clock (zone and speed)
            return _check(gametime.next_at(game, hm, now), now), "game"
        if hm is None or (moon is None and game_offset is None):
            raise ValueError("Game time looks like 'game 21:30' or 'game 9pm'.")
        loc = (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=now + game_offset)) \
            if game_offset is not None else moon.eastern_struct(now)
        target = loc.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if target <= loc:
            target += datetime.timedelta(days=1)
        wall = (target - datetime.datetime(1970, 1, 1)).total_seconds()
        due = wall - (game_offset if game_offset is not None else moon.eastern_offset(wall + 5 * 3600))
        return _check(due, now), "game"
    hm = _clock_hm(t[2:] if t.startswith("at ") else t)
    if hm is not None:
        loc = datetime.datetime.fromtimestamp(now)
        target = loc.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if target <= loc:
            target += datetime.timedelta(days=1)
        return _check(target.timestamp(), now), "local"
    m = _DUR.match(t)
    if m and any(m.groups()):
        d, h, mi, s = (int(x or 0) for x in m.groups())
        return _check(now + d * 86400 + h * 3600 + mi * 60 + s, now), "after"
    if t.isdigit() and len(t) <= 5:
        return _check(now + int(t) * 60, now), "after"
    raise ValueError("I couldn't read '%s'. Try 10m, 1h30m, 90s, 21:30 or game 21:30." % t[:30])


def _check(due, now):
    if due - now < 1:
        raise ValueError("That time has already passed.")
    if due - now > MAX_TIMER_SECS:
        raise ValueError("Timers can be at most 7 days away.")
    return due


def countdown(secs):
    """'4:12' or '1:02:30' for a number of seconds."""
    s = max(0, int(secs + 0.999))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


_MODS = {"ctrl": "Control", "control": "Control", "alt": "Alt", "shift": "Shift"}
_NAMED = {"enter": "Return", "return": "Return", "tab": "Tab", "space": "space", "esc": "Escape",
          "escape": "Escape", "home": "Home", "end": "End", "pageup": "Prior", "pagedown": "Next",
          "insert": "Insert", "delete": "Delete", "backspace": "BackSpace", "up": "Up", "down": "Down",
          "left": "Left", "right": "Right", "next": "Next", "prior": "Prior"}
_LABELS = {"Next": "PageDown", "Prior": "PageUp"}          # how those keys are written (Tk calls them Next and Prior)
# Ctrl/Alt letters a normal text box or the client itself needs
RESERVED_KEYS = {"Control-c", "Control-v", "Control-x", "Control-z", "Control-y", "Control-l", "Control-plus",
                 "Control-minus", "Control-equal", "Alt-F4", "Alt-x", "Alt-Return"}


def parse_hotkey(text):
    """'Ctrl-T', 'alt+m', 'F9' -> (tk_sequence, display) such as ('<Control-t>', 'Ctrl-T'); raises ValueError.
    Needs Ctrl or Alt for letters/digits so that typing is never hijacked."""
    parts = [p for p in re.split(r"[-+ ]+", str(text or "").strip()) if p]
    if not parts:
        raise ValueError("Type a key such as Ctrl-T, Alt-M or F9.")
    *mods, key = parts
    tk_mods, shown = [], []
    for m in mods:
        mm = _MODS.get(m.lower())
        if mm is None or mm in tk_mods:
            raise ValueError("'%s' is not a modifier (Ctrl, Alt or Shift)." % m[:12])
        tk_mods.append(mm)
        shown.append({"Control": "Ctrl"}.get(mm, mm))
    k = key.lower()
    if re.fullmatch(r"f([1-9]|1[0-2])", k):
        name, label = k.upper(), k.upper()
    elif k in _NAMED:
        name = _NAMED[k]
        label = _LABELS.get(name, name)
    elif len(key) == 1 and key.isalnum() and key.isascii():
        if not ({"Control", "Alt"} & set(tk_mods)):
            raise ValueError("Letters and digits need Ctrl or Alt.")
        name, label = k, key.upper()
    else:
        raise ValueError("I don't know the key '%s'." % key[:12])
    seq = "-".join(tk_mods + [name])
    if seq in RESERVED_KEYS or (name.isdigit() and ("Control" in tk_mods or "Alt" in tk_mods)):
        raise ValueError("%s is used for something else." % "-".join(shown + [label]))
    order = {"Control": 0, "Alt": 1, "Shift": 2}
    tk_mods.sort(key=order.get)
    return "<%s>" % "-".join(tk_mods + [name]), "-".join([{"Control": "Ctrl"}.get(m, m) for m in tk_mods] + [label])


# action -> (title, default key) for the hotkeys that can be changed
HOTKEYS = {
    "worlds": ("Worlds", "Ctrl-W"), "triggers": ("Triggers", "Ctrl-T"), "aliases": ("Aliases", "Alt-A"),
    "panes": ("Panes / layout", "Ctrl-P"), "moon": ("Moon", "Alt-M"), "notepad": ("Notepad", "Alt-N"),
    "timers": ("Timers", "Alt-T"), "dos_toggle": ("DOS look on/off", "Alt-D"),
    "gradient": ("Gradient maker", "Alt-G"), "hex": ("Hex to xterm", "Alt-H"), "customize": ("Customize form", "Alt-K"),
    "emoji": ("Emoji picker", "Alt-E"), "buttons": ("Buttons", "Alt-B"),
    "select_input": ("Select the whole entry line", "Ctrl-A"), "settings": ("Settings", "Ctrl-Shift-O"),
    "find": ("Find in the text", "Ctrl-F"), "find_next": ("Find next", "Ctrl-Shift-F"),
    "world_next": ("Next world", "Ctrl-PageDown"), "world_prev": ("Previous world", "Ctrl-PageUp"),
    "world_swap": ("Swap with the last world", "Ctrl-Tab"),
    "close_world": ("Close this world", "Ctrl-Shift-W"),
    "world_1": ("Show world 1", "Ctrl-F1"),
    "world_2": ("Show world 2", "Ctrl-F2"),
    "world_3": ("Show world 3", "Ctrl-F3"),
    "world_4": ("Show world 4", "Ctrl-F4"),
    "world_5": ("Show world 5", "Ctrl-F5"),
    "world_6": ("Show world 6", "Ctrl-F6"),
    "world_7": ("Show world 7", "Ctrl-F7"),
    "world_8": ("Show world 8", "Ctrl-F8"),
    "world_9": ("Show world 9", "Ctrl-F9"),
    "world_10": ("Show world 10", "Ctrl-F10"),
    "world_11": ("Show world 11", "Ctrl-F11"),
    "world_12": ("Show world 12", "Ctrl-F12"),
    # screen reader mode
    "sr_prev": ("Review: older line", "Alt-Up"), "sr_next": ("Review: newer line", "Alt-Down"),
    "sr_last": ("Repeat last line", "Alt-R"), "sr_stats": ("Read my stats", "Alt-S"),
    "sr_pane": ("Read recent pane lines", "Alt-P"), "sr_time": ("Read time and moon", "Alt-C"),
    "sr_stop": ("Stop speech", "Alt-Q"), "sr_mute": ("Mute / unmute speech", "Alt-Z"),
}
FIXED_KEYS = {"F12": "About", "F1": "Help", "F2": "Dial / hang up", "F3": "Log", "F5": "Skin", "F6": "Colours", "F7": "Font",
              "F10": "Menu", "F11": "Full screen", "Alt-X": "Exit", "Ctrl-1..9": "Select pane tab",
              "Alt-1..9, Alt-0": "Fold pane areas"}


def clean_keys(raw):
    """Saved overrides {action: 'Ctrl-T'} reduced to valid ones; if they clash with each other or with
    another action's key, none are kept."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for action, (_t, default) in HOTKEYS.items():
        want = raw.get(action)
        if not isinstance(want, str):
            continue
        try:
            shown = parse_hotkey(want)[1]
        except ValueError:
            continue
        if shown != default:
            out[action] = shown
    seqs = [seq for seq, _s in effective_keys(out).values()]
    return out if len(set(seqs)) == len(seqs) and all(
        effective_keys(out)[a][1] == out[a] for a in out) else {}


def effective_keys(overrides):
    """{action: (sequence, display)}, defaults filled in; a clash falls back to the default."""
    out, seen = {}, set()
    for action, (_t, default) in HOTKEYS.items():
        shown = (overrides or {}).get(action, default)
        try:
            pair = parse_hotkey(shown)
        except ValueError:
            pair = parse_hotkey(default)
        if pair[0] in seen:
            pair = parse_hotkey(default)
        seen.add(pair[0])
        out[action] = pair
    return out


# ======================================================================================
# the mixin
# ======================================================================================
class ExtrasMixin:
    """Timers, clock, notepad, moon window and hotkeys. Needs the App's own helpers."""

    def _extras_init(self):
        self._timers = []                       # [{"due", "label", "kind"}]
        self._xtick_job = None
        self._notepad = None
        self._notes_job = None
        self._hotkey_bound = []

    # ---- the once-a-second beat --------------------------------------------------------
    def _start_xtick(self):
        if self._xtick_job is None:
            self._xtick()

    def _xtick(self):
        self._xtick_job = None
        try:
            self._fire_timers()
            self._update_clock()
            if self._timers or self.cfg.get("clock", "off") != "off":
                self._xtick_job = self.root.after(1000, self._xtick)
        except tk.TclError:
            self._xtick_job = None

    # ---- clock -------------------------------------------------------------------------
    def clock_text(self):
        mode = self.cfg.get("clock", "off")
        now = time.time()
        if mode == "real":
            return time.strftime("%H:%M", time.localtime(now))
        if mode == "game":                                   # this world's clock: its zone and speed
            return self.game_clock_text()
        return ""

    def _update_clock(self):
        try:
            self.clock_label.configure(text=self.clock_text())
        except (tk.TclError, AttributeError):
            pass
        self.update_dosbar()

    # ---- timers ------------------------------------------------------------------------
    def add_timer(self, when, label=""):
        """Start a timer. Returns a message for the user."""
        try:
            due, kind = parse_when(when, game=self.world_time())
        except ValueError as e:
            return False, str(e)
        if len(self._timers) >= MAX_TIMERS:
            return False, "That is too many timers (at most %d)." % MAX_TIMERS
        label = " ".join(str(label or "").split())[:60] or "Timer"
        self._timers.append({"due": due, "label": label, "kind": kind})
        self._timers.sort(key=lambda t: t["due"])
        self._start_xtick()
        self._update_clock()
        return True, "%s set for %s (%s)." % (label, time.strftime("%H:%M:%S", time.localtime(due)), countdown(due - time.time()))

    def _fire_timers(self):
        now = time.time()
        due = [t for t in self._timers if t["due"] <= now]
        if not due:
            return
        self._timers = [t for t in self._timers if t["due"] > now]
        for t in due:
            self.system("Time's up: %s" % t["label"])
            self.set_notice("Time's up: %s" % t["label"], 30)
            try:
                self.root.bell()
            except tk.TclError:
                pass

    def timer_segment(self):
        """Text for the status bars: the next timer and how long is left."""
        if not self._timers:
            return ""
        t = self._timers[0]
        more = " +%d" % (len(self._timers) - 1) if len(self._timers) > 1 else ""
        return "%s %s%s" % (t["label"][:14], countdown(t["due"] - time.time()), more)

    def cancel_timer(self, n=None):
        if not self._timers:
            return "There are no timers."
        if n is None:
            self._timers.clear()
            return "All timers cancelled."
        if 1 <= n <= len(self._timers):
            t = self._timers.pop(n - 1)
            return "Cancelled %s." % t["label"]
        return "There is no timer %d." % n

    def list_timers(self):
        if not self._timers:
            return "No timers running. /timer 10m [label] starts one."
        now = time.time()
        return "Timers:\n" + "\n".join("  %d. %s  %s" % (i + 1, countdown(t["due"] - now), t["label"])
                                       for i, t in enumerate(self._timers))

    def open_timers(self):
        """Dialog: when + label."""
        if self.dos:
            fields = [{"key": "when", "label": "When", "type": "text", "value": "", "width": 20},
                      {"key": "label", "label": "Label", "type": "text", "value": "", "width": 30}]

            def result(res, vals):
                if res == "start":
                    ok, msg = self.add_timer(vals.get("when", ""), vals.get("label", ""))
                    self.system(msg)
                elif res == "list":
                    self.system(self.list_timers())
                elif res == "clear":
                    self.system(self.cancel_timer())
            return self._dos_dialog("Timer", fields, [("Start", "start"), ("List", "list"), ("Clear all", "clear"),
                                                      ("Cancel", "cancel")], result, width=60,
                                    message="Examples: 10m   1h30m   21:30   game 21:30 (this world's game clock)")
        top = tk.Toplevel(self.root)
        top.title("Timer")
        top.transient(self.root)
        w, l = tk.StringVar(), tk.StringVar()
        tk.Label(top, justify="left", text="When: 10m, 1h30m, 90s, 21:30, or game 21:30 (this world's game clock)"
                 ).grid(row=0, column=0, columnspan=2, padx=10, pady=(8, 2), sticky="w")
        tk.Label(top, text="When").grid(row=1, column=0, padx=10, sticky="w")
        e = tk.Entry(top, textvariable=w, width=20)
        e.grid(row=1, column=1, sticky="w", pady=2)
        tk.Label(top, text="Label").grid(row=2, column=0, padx=10, sticky="w")
        tk.Entry(top, textvariable=l, width=34).grid(row=2, column=1, sticky="w", pady=2)
        msg = tk.Label(top, text=self.list_timers(), justify="left", anchor="w")
        msg.grid(row=3, column=0, columnspan=2, padx=10, pady=6, sticky="w")

        def start():
            ok, m = self.add_timer(w.get(), l.get())
            msg.configure(text=m if not ok else self.list_timers())
            if ok:
                w.set(""), l.set("")
        bf = tk.Frame(top)
        bf.grid(row=4, column=0, columnspan=2, pady=8)
        tk.Button(bf, text="Start", width=8, command=start).pack(side="left", padx=4)
        tk.Button(bf, text="Clear all", width=8, command=lambda: msg.configure(text=self.cancel_timer())).pack(side="left", padx=4)
        tk.Button(bf, text="Close", width=8, command=top.destroy).pack(side="left", padx=4)
        top.bind("<Return>", lambda ev: start())
        top.bind("<Escape>", lambda ev: top.destroy())
        self._theme_tree(top)
        e.focus_set()
        return top

    # ---- notepad -----------------------------------------------------------------------
    def notes_path(self):
        return os.path.join(os.path.expanduser("~"), ".sanctuary_notes.txt")

    def toggle_notepad(self):
        if self._notepad is not None:
            self.close_notepad()
        else:
            self.open_notepad()

    def open_notepad(self):
        if self._notepad is not None:
            return
        c = self._dc() if self.dos else None
        bg = c["input_bg"] if c else self.theme["bg"]
        fg = c["input_fg"] if c else self.theme["fg"]
        frame = tk.Frame(self._holder, bd=0, highlightthickness=0, bg=self.theme["panel"])
        head = tk.Label(frame, anchor="w", padx=8, text="Notepad   Esc: close   Ctrl-S: save",
                        bg=(c["dos_bar_bg"] if c else self.theme["panel"]),
                        fg=(c["dos_bar_fg"] if c else self.theme["fg"]), font=self.f_bold)
        head.pack(fill="x")
        text = tk.Text(frame, wrap="word", undo=True, font=self.f_norm, bd=0, highlightthickness=0, padx=8, pady=4,
                       bg=bg, fg=fg, insertbackground=fg, selectbackground=self.theme["select"])
        sb = tk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        if not self.dos:
            sb.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        try:
            with open(self.notes_path(), "r", encoding="utf-8", errors="replace") as f:
                text.insert("1.0", f.read(NOTES_MAX))
            text.edit_reset()
        except OSError:
            pass
        text.bind("<Escape>", lambda e: (self.close_notepad(), "break")[1])
        text.bind("<Control-s>", lambda e: (self.save_notes(), "break")[1])
        self.spell_attach(text, "notepad")
        text.bind("<<Modified>>", self._notes_modified)
        text.edit_modified(False)
        frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        frame.lift()
        self._notepad = {"frame": frame, "text": text}
        text.focus_set()
        text.mark_set("insert", "end")

    def _notes_modified(self, _e=None):
        np_ = self._notepad
        if np_ is None or not np_["text"].edit_modified():
            return
        np_["text"].edit_modified(False)
        if self._notes_job is not None:
            try:
                self.root.after_cancel(self._notes_job)
            except tk.TclError:
                pass
        try:
            self._notes_job = self.root.after(2500, self.save_notes)
        except tk.TclError:
            self._notes_job = None

    def save_notes(self):
        np_ = self._notepad
        if np_ is None:
            return False
        try:
            data = np_["text"].get("1.0", "end-1c")[:NOTES_MAX]
            tmp = self.notes_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(data)
            os.replace(tmp, self.notes_path())
            return True
        except (OSError, tk.TclError):
            return False

    def close_notepad(self):
        np_ = self._notepad
        if np_ is None:
            return
        self.save_notes()
        if self._notes_job is not None:
            try:
                self.root.after_cancel(self._notes_job)
            except tk.TclError:
                pass
            self._notes_job = None
        self._notepad = None
        try:
            np_["frame"].destroy()
        except tk.TclError:
            pass
        self.root.after_idle(self.input.focus_set)

    # ---- moon --------------------------------------------------------------------------
    def moon_lines(self, ts=None, pre=False):
        if moon is None:
            return ["The moon module is missing."]
        ts = time.time() if ts is None else ts
        d = moon.describe(ts)
        lines = ["The moon is %s." % d["name"], ""]
        lines += [(dosui.PRE + r) if pre else r for r in moon.art(d["age"], radius=5, solid=bool(self.dos))]
        lines += ["", "%d%% lit, %.1f days old" % (round(d["lit"] * 100), d["age"])]
        if d["full_night"]:
            lines.append("Tonight is the full-moon night.")
        lines.append("Next full moon: %s (in %s)" % (moon.fmt_eastern(d["next_full"]), moon.until(ts, d["next_full"])))
        lines.append("Next new moon:  %s (in %s)" % (moon.fmt_eastern(d["next_new"]), moon.until(ts, d["next_new"])))
        return lines

    def open_moon(self):
        text = "\n".join(self.moon_lines(pre=self.dos))
        if self.dos:
            if self._overlay_open():
                return None
            self._overlay = dosui.show_message(self.root, "Moon", text, self._dc(), self.f_norm)
            return self._overlay
        top = tk.Toplevel(self.root)
        top.title("Moon")
        top.transient(self.root)
        lbl = tk.Label(top, text=text, justify="left", font=self.f_norm, padx=16, pady=10)
        lbl.pack()
        tk.Button(top, text="Close", width=10, command=top.destroy).pack(pady=(0, 10))
        top.bind("<Escape>", lambda e: top.destroy())
        self._theme_tree(top)
        top.focus_set()
        return top

    # ---- about -------------------------------------------------------------------------
    def about_text(self):
        return "Sanctuary"

    def open_about(self):
        if self.dos:
            if self._overlay_open():
                return None
            self._overlay = dosui.show_message(self.root, "About", self.about_text(), self._dc(), self.f_norm)
            return self._overlay
        top = tk.Toplevel(self.root)
        top.title("About Sanctuary")
        top.transient(self.root)
        tk.Label(top, text=self.about_text(), justify="left", padx=20, pady=14).pack()
        tk.Button(top, text="Close", width=10, command=top.destroy).pack(pady=(0, 12))
        top.bind("<Escape>", lambda e: top.destroy())
        self._theme_tree(top)
        top.focus_set()
        return top

    # ---- hotkeys -----------------------------------------------------------------------
    def _bind_hotkeys(self):
        """(Re)bind the command hotkeys from the saved choices."""
        for w, seq in self._hotkey_bound:
            try:
                w.unbind(seq)
            except tk.TclError:
                pass
        self._hotkey_bound = []
        actions = {"worlds": self.open_worlds, "triggers": self.open_triggers, "aliases": self.open_aliases,
                   "panes": self.open_panes, "moon": self.open_moon, "notepad": self.toggle_notepad,
                   "timers": self.open_timers, "dos_toggle": self.toggle_dos_mode,
                   "gradient": self.open_gradient, "hex": self.open_hex, "customize": self.open_customize,
                   "emoji": self.open_emoji_picker, "buttons": self.open_buttons, "select_input": self._select_input_line, "settings": self.open_settings,
                   "find": self.open_find, "find_next": self.find_next_key,
                   "world_next": lambda: self.cycle_world(+1), "world_prev": lambda: self.cycle_world(-1),
                   "world_swap": self.swap_world,
                   "close_world": self.close_world_ask}
        for n in range(1, 13):
            actions["world_%d" % n] = (lambda n=n: self.goto_world(n))
        actions.update(self.access_actions())
        for action, (seq, _shown) in effective_keys(self.cfg.get("keys")).items():
            fn = actions.get(action)
            if fn is None:
                continue
            handler = self._ctrl_handler(fn) if action != "dos_toggle" else (lambda e=None: self.toggle_dos_mode())
            variants = {seq}
            m = re.match(r"^<(.*-)?([a-z])>$", seq)
            if m:                                           # caps lock must not change what a key does
                variants.add("<%s%s>" % (m.group(1) or "", m.group(2).upper()))
            for s in variants:
                for w in (self.root,) + self._inputs():
                    w.bind(s, handler)
                    self._hotkey_bound.append((w, s))

    def _select_input_line(self):
        """Ctrl-A (as in MUSHclient): the whole entry line is selected, ready to be replaced or cut."""
        self.input.focus_set()
        self.input.select_range(0, "end")
        self.input.icursor("end")

    def world_key_prefix(self):
        """'Ctrl-F' when worlds 1..12 are all that prefix plus 1..12; '' when they have been set one by one."""
        keys = {a: s for a, _t, s in self.hotkey_table()}
        first = keys.get("world_1", "")
        if not first.endswith("1"):
            return ""
        pre = first[:-1]
        return pre if all(keys.get("world_%d" % n) == "%s%d" % (pre, n) for n in range(1, 13)) else ""

    def _hotkey_rows(self):
        """The rows of the Hotkeys form: the twelve world keys are one row (their prefix, e.g. Ctrl-F)."""
        rows = [r for r in self.hotkey_table() if not re.fullmatch(r"world_\d+", r[0])]
        at = next((k for k, r in enumerate(rows) if r[0] == "worlds"), -1) + 1
        rows.insert(at, ("world_keys", "Show world 1-12: key prefix", self.world_key_prefix() or "(custom)"))
        return rows

    def _wanted_from_form(self, vals):
        """What the Hotkeys form holds -> {action: key text}; a new prefix is spread over world 1..12."""
        wanted = {a: v for a, v in vals.items() if a != "world_keys"}
        pre = str(vals.get("world_keys", "") or "").strip()
        now = {a: s for a, _t, s in self.hotkey_table()}
        changed = bool(pre) and pre != "(custom)" and pre != (self.world_key_prefix() or "(custom)")
        for n in range(1, 13):
            wanted["world_%d" % n] = ("%s%d" % (pre, n)) if changed else now["world_%d" % n]
        return wanted

    def _hotkey_current(self, action):
        return effective_keys(self.cfg.get("keys"))[action][1]

    def hotkey_table(self):
        return [(a, HOTKEYS[a][0], shown) for a, (_s, shown) in effective_keys(self.cfg.get("keys")).items()]

    def set_hotkeys(self, wanted):
        """wanted {action: text}. Returns (ok, message); nothing changes unless every key is fine."""
        clean, used = {}, {}
        for action in HOTKEYS:                              # anything not mentioned goes back to its default
            text = (wanted.get(action) or "").strip() or HOTKEYS[action][1]
            try:
                seq, shown = parse_hotkey(text)
            except ValueError as e:
                return False, "%s: %s" % (HOTKEYS[action][0], e)
            if seq in used:
                return False, "%s and %s would use the same key." % (HOTKEYS[used[seq]][0], HOTKEYS[action][0])
            used[seq] = action
            clean[action] = shown
        keys = {a: s for a, s in clean.items() if s != HOTKEYS[a][1]}
        self.cfg["keys"] = keys
        self._bind_hotkeys()
        self._save_settings()
        return True, "Hotkeys saved."

    def open_hotkeys(self):
        rows = self._hotkey_rows()
        if self.dos:
            rows = [r for r in rows if not r[0].startswith("sr_")]      # screen reader keys: normal look only
            fields = [{"key": a, "label": title, "type": "text", "value": shown, "width": 12} for a, title, shown in rows]

            def result(res, vals):
                if res == "save":
                    ok, msg = self.set_hotkeys(self._wanted_from_form(
                        {a: vals.get(a, shown) for a, _t, shown in self._hotkey_rows()}))
                    self.system(msg)
                    if not ok:
                        self._reopen(self.open_hotkeys)
                elif res == "reset":
                    self.set_hotkeys({})
                    self.system("Hotkeys reset to the defaults.")
            return self._dos_dialog("Hotkeys", fields, [("Save", "save"), ("Defaults", "reset"), ("Cancel", "cancel")],
                                    result, width=56,
                                    message="Type keys like Ctrl-T or Alt-M. Fixed: " +
                                            ", ".join(sorted(FIXED_KEYS)[:6]) + "...")
        top = tk.Toplevel(self.root)
        top.title("Hotkeys")
        top.transient(self.root)
        vars_ = {}
        half = (len(rows) + 1) // 2                         # two columns, so the form is not taller than the screen
        for i, (a, title, shown) in enumerate(rows):
            col = (i // half) * 2
            tk.Label(top, text=title).grid(row=i % half, column=col, sticky="w", padx=10, pady=2)
            vars_[a] = tk.StringVar(value=shown)
            tk.Entry(top, textvariable=vars_[a], width=14).grid(row=i % half, column=col + 1, padx=10, pady=2)
        tk.Label(top, justify="left", wraplength=620, text="Type keys like Ctrl-T or Alt-M. The world prefix is "
                 "the key part before the number: Ctrl-F gives Ctrl-F1 .. Ctrl-F12. Fixed keys: " +
                 ", ".join("%s %s" % (k, v) for k, v in FIXED_KEYS.items())).grid(
            row=half, column=0, columnspan=4, padx=10, pady=6, sticky="w")
        msg = tk.Label(top, text="", fg="#c03030")
        msg.grid(row=half + 1, column=0, columnspan=4)

        def save():
            ok, m = self.set_hotkeys(self._wanted_from_form({a: v.get() for a, v in vars_.items()}))
            if ok:
                top.destroy()
            else:
                msg.configure(text=m)

        def reset():
            for a, v in vars_.items():
                v.set("Ctrl-F" if a == "world_keys" else HOTKEYS[a][1])
        bf = tk.Frame(top)
        bf.grid(row=half + 2, column=0, columnspan=4, pady=8)
        tk.Button(bf, text="Save", width=8, command=save).pack(side="left", padx=4)
        tk.Button(bf, text="Defaults", width=8, command=reset).pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", width=8, command=top.destroy).pack(side="left", padx=4)
        self._theme_tree(top)
        return top

    # ---- typed commands ----------------------------------------------------------------
    def _extras_command(self, cmd, arg):
        """/timer, /moon, /notes, /hotkeys. True when the command was one of ours."""
        if cmd == "timer":
            bits = arg.split(None, 1)
            if not bits:
                self.open_timers()
            elif bits[0].lower() == "list":
                self.system(self.list_timers())
            elif bits[0].lower() in ("cancel", "clear", "stop"):
                n = bits[1].strip() if len(bits) > 1 else ""
                self.system(self.cancel_timer(int(n) if n.isascii() and n.isdigit() else None))
            else:
                # '/timer game 21:30 label' / '/timer 10m label' : the label is whatever follows the time
                m = re.match(r"^((?:game|et|eastern)\s+\S+(?:\s*[ap]m)?|at\s+\S+(?:\s*[ap]m)?|\S+)\s*(.*)$", arg, re.I)
                ok, msg = self.add_timer(m.group(1), m.group(2)) if m else (False, "Usage: /timer 10m [label]")
                self.system(msg)
            return True
        if cmd in ("changes", "whatsnew"):
            self._whatsnew_command(arg)
            return True
        if cmd == "crt":
            self._crt_command(arg)
            return True
        if cmd == "spell":
            self._spell_command(arg)
            return True
        if cmd == "gmcp":
            self._gmcp_command(arg)
            return True
        if cmd == "keep":
            self._keep_command(arg)
            return True
        if cmd == "moon":
            self.open_moon()
            return True
        if cmd in ("notes", "notepad"):
            self.toggle_notepad()
            return True
        if cmd == "hotkeys":
            self.open_hotkeys()
            return True
        return False
