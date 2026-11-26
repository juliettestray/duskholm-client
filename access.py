"""Screen reader mode for Sanctuary (mixed into the App).

In this mode the client keeps to its plain, ordinary window (no DOS look) and talks: it reads new
game lines (not the prompt, not art), pane lines with the pane's name, client messages, and
announces stun, health and timer changes. Keys let you repeat a line and step back through
recent ones. Triggers can add *speak* and *silence* actions. Nothing here needs a screen reader to
be installed: if none is running the Windows voice is used."""
import re
import time

import speech
import combatfilter
import tkinter as tk

try:
    import prompts
except ImportError:
    prompts = None

STUN_STEPS = (50, 75, 100)
HEALTH_STEPS = (50, 25, 10)

HELP_TEXT = (
    "Screen reader mode. Alt Up and Alt Down step back and forward through recent lines. "
    "Alt R repeats the last line. Alt S reads your stats. Alt P reads recent lines from your panes. "
    "Alt C reads the time and the moon. Alt Q stops speech. Alt Z mutes or unmutes. "
    "You can change these keys with slash hotkeys. Slash S R help says this again.")


class AccessMixin:
    def _access_init(self):
        self.speech = speech.Speech()
        self._sr_alert = {}
        self._sr_pane_lines = {}             # pane title -> last lines (for the pane key)
        self._sr_interval_job = None

    # ---- state -------------------------------------------------------------------------
    def sr_on(self):
        # a world that is not on screen stays silent
        return bool(self.cfg.get("screen_reader")) and self._here()

    def set_screen_reader(self, on, announce=True):
        on = bool(on)
        self.cfg["screen_reader"] = on
        var = getattr(self, "_xvars", {}).get("screen_reader")
        if var is not None and var.get() != on:
            var.set(on)
        if on:
            if self.dos:
                self.set_dos_mode(False)
            backend, msg = speech.make_backend(self.cfg.get("sr_voice", "auto"), self.cfg.get("sr_rate", 0))
            self.speech.set_backend(backend)
            self.speech.muted = False
            self._sr_alert = {}
            self.root.title("Sanctuary (screen reader mode)")
            self._sr_schedule_interval()
            if announce:
                self.system("Screen reader mode on. " + msg)
                self.speech.say_now("Screen reader mode on. " + msg + " " + HELP_TEXT)
        else:
            self.speech.stop()
            self.speech.set_backend(speech.NullBackend())
            self._sr_cancel_interval()
            self.root.title("Sanctuary")
            if announce:
                self.system("Screen reader mode off.")
        self._phone_apply_all()                              # (a picture of a phone cannot be read aloud: the text area is shown)
        self._save_settings()

    # ---- hearing the game --------------------------------------------------------------
    def _split_prompt(self, plain):
        """(is_prompt_only, rest): the line with any prompts at its start removed (several can run
        together when output arrives in a burst)."""
        if prompts is None:
            return False, plain
        stripped = False
        for _ in range(10):
            if not plain.startswith("["):
                break
            end = plain.find("] ")
            head = plain[:end + 2] if end >= 0 else plain + " "
            try:
                ok = prompts.parse_prompt(head, self.current_profile()) is not None
            except Exception:
                ok = False
            if not ok:
                break
            stripped = True
            plain = plain[end + 2:].strip() if end >= 0 else ""
        return (stripped and not plain), plain

    def sr_hear(self, plain, effects):
        """A complete line of game output. `effects` are the trigger side effects for it."""
        if not self.sr_on():
            return
        silenced = any(fx[0] == "silence" for fx in effects)
        routes = [fx[1] for fx in effects if fx[0] == "route"]
        only_prompt, plain = self._split_prompt(plain)
        if only_prompt:
            return
        if not silenced and self._combat_gag(plain):
            silenced = True                                  # other people's fighting: kept for review, not read
        prefix = ""
        if routes:
            d = self._find_pane_def(routes[0].strip().lower()) if hasattr(self, "_find_pane_def") else None
            prefix = d["title"] if d else routes[0]
        if silenced:
            self.speech.note(plain, prefix)
        else:
            self.speech.say(plain, prefix=prefix)
        for r in routes:
            d = self._find_pane_def(r.strip().lower())
            title = d["title"] if d else r
            lines = self._sr_pane_lines.setdefault(title, [])
            t = speech.clean_for_speech(plain)
            if t:
                lines.append(t)
                del lines[:-20]

    def _combat_gag(self, plain):
        cfg = self.cfg.get("sr_combat")
        if not cfg:
            return False
        p = self._last_prompt
        return combatfilter.should_skip(plain, cfg, self._char_name(), bool(p and p.get("text")))

    def open_combat_filter(self):
        """Which fighting lines not about you are skipped by the voice."""
        if self.dos:
            self.system("Open this in the normal look (Alt+D); screen reader mode uses it anyway.")
            return None
        cfg = combatfilter.clean_settings(self.cfg.get("sr_combat"))
        top = tk.Toplevel(self.root)
        top.title("Combat lines (screen reader)")
        top.transient(self.root)
        tk.Label(top, justify="left", wraplength=480, text="While a fight is on, lines that are not about you can be "
                 "left unread (they stay on screen and in the review keys). Tick what to skip.").pack(anchor="w", padx=12, pady=(10, 4))
        skip = {}
        for c in combatfilter.CATEGORIES:
            skip[c] = tk.BooleanVar(value=cfg["skip"][c])
            tk.Checkbutton(top, text="Skip: " + combatfilter.CATEGORY_TEXT[c], variable=skip[c]).pack(anchor="w", padx=24)
        fight = tk.BooleanVar(value=cfg["only_in_fight"])
        multi = tk.BooleanVar(value=cfg["multiword_npc"])
        tk.Checkbutton(top, text="Only while I am in a fight", variable=fight).pack(anchor="w", padx=12, pady=(8, 0))
        tk.Checkbutton(top, text="Treat a name of several words as an NPC", variable=multi).pack(anchor="w", padx=12)
        ents = {}
        for key, label in (("players", "Always players (comma separated)"), ("npcs", "Always NPCs"),
                           ("always", "Always read lines that mention")):
            tk.Label(top, text=label).pack(anchor="w", padx=12, pady=(6, 0))
            v = tk.StringVar(value=", ".join(cfg[key]))
            tk.Entry(top, textvariable=v, width=56).pack(anchor="w", padx=12)
            ents[key] = v

        def save():
            self.cfg["sr_combat"] = combatfilter.clean_settings({
                "skip": {c: v.get() for c, v in skip.items()}, "only_in_fight": fight.get(), "multiword_npc": multi.get(),
                "players": combatfilter.parse_names(ents["players"].get()), "npcs": combatfilter.parse_names(ents["npcs"].get()),
                "always": combatfilter.parse_names(ents["always"].get())})
            self._save_settings()
            top.destroy()
            self.system("Combat line settings saved.")
        bf = tk.Frame(top)
        bf.pack(pady=10)
        tk.Button(bf, text="Save", width=9, command=save).pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", width=9, command=top.destroy).pack(side="left", padx=4)
        top.bind("<Escape>", lambda e: top.destroy())
        self._theme_tree(top)
        return top

    def sr_system(self, text):
        """A client message (connected, timer, error...)."""
        if self.sr_on():
            self.speech.say(text, prefix="")

    # ---- alerts: stun, health, timers --------------------------------------------------
    def sr_alerts(self, view):
        """Called with the current prompt view. Announces when stun or health cross a threshold and when
        the move or attack timer becomes ready."""
        if not self.sr_on() or not self.cfg.get("sr_alerts", True) or not view:
            return
        st, said = self._sr_alert, []
        hp = view.get("hp")
        if hp and hp[1] and not self._gmcp_speaks("Char.Vitals"):
            frac = 100.0 * hp[0] / hp[1]
            band = sum(1 for s in HEALTH_STEPS if frac < s)
            old = st.get("health")
            st["health"] = band
            if old is not None and band > old:
                said.append("%s %d percent" % (speech.LABEL_WORDS.get(hp[2], hp[2]), round(frac)))
        for label, n in view.get("counters") or []:
            if label.upper() == "ST":
                band = sum(1 for s in STUN_STEPS if n >= s)
                old = st.get("stun")
                st["stun"] = band
                if old is not None and band != old:
                    said.append("Stun %d" % n)
        for label, n in view.get("cooldowns") or []:
            key = "cd" + label
            was = st.get(key)
            st[key] = n
            if was is not None and was > 0 and n <= 0:
                said.append("%s ready" % speech.LABEL_WORDS.get(label, label).split()[0].capitalize())
        for s in said:
            self.speech.say_now(s)

    # ---- reading stats at intervals ----------------------------------------------------
    def _sr_cancel_interval(self):
        if self._sr_interval_job is not None:
            try:
                self.root.after_cancel(self._sr_interval_job)
            except Exception:
                pass
            self._sr_interval_job = None

    def _sr_schedule_interval(self):
        self._sr_cancel_interval()
        secs = int(self.cfg.get("sr_interval", 0) or 0)
        if self.sr_on() and secs > 0:
            try:
                self._sr_interval_job = self.root.after(secs * 1000, self._sr_interval_tick)
            except Exception:
                self._sr_interval_job = None

    def _sr_interval_tick(self):
        self._sr_interval_job = None
        if self.sr_on() and self.connected and self._last_prompt:
            text = speech.describe_interval(self._prompt_view())
            if text:
                self.speech.say(text, record=False)
        self._sr_schedule_interval()

    def set_sr_interval(self, secs):
        secs = int(secs)
        secs = 0 if secs <= 0 else max(5, min(3600, secs))
        if self.cfg.get("sr_interval") != secs:
            self._opt_touch("@sr_interval")
        self.cfg["sr_interval"] = secs
        var = getattr(self, "_sr_interval_var", None)
        if var is not None:
            try:
                var.set(secs if secs in (0, 10, 15, 30, 60, 120, 300) else -1)
            except Exception:
                pass
        self._save_settings()
        self._sr_schedule_interval()
        return secs

    # ---- review keys -------------------------------------------------------------------
    def _sr_off_message(self):
        if not self.sr_on():
            self.system("Screen reader mode is off. Turn it on under Options, or type /sr on.")
            return True
        return False

    def sr_prev(self):
        if self._sr_off_message():
            return
        t, note = self.speech.review_step(-1)
        self.speech.say_now((t + (". Top." if note == "top" else "")) if t else "Nothing to review.")

    def sr_next(self):
        if self._sr_off_message():
            return
        t, note = self.speech.review_step(+1)
        self.speech.say_now((t + (". Bottom." if note == "bottom" else "")) if t else "Nothing to review.")

    def sr_last(self):
        if self._sr_off_message():
            return
        h = self.speech.last()
        self.speech.review = None
        self.speech.say_now(h[0] if h else "Nothing to repeat.")

    def sr_stats(self):
        if self._sr_off_message():
            return
        self.speech.say_now(speech.describe_prompt(self._prompt_view()))

    def sr_pane(self):
        if self._sr_off_message():
            return
        if not self._sr_pane_lines:
            self.speech.say_now("No pane lines yet.")
            return
        out = []
        for title, lines in self._sr_pane_lines.items():
            out.append("%s: %s" % (title, " . ".join(lines[-3:])))
        self.speech.say_now(" ".join(out))

    def sr_time(self):
        if self._sr_off_message():
            return
        bits = []
        clock = self.clock_text() or time.strftime("%H:%M")
        bits.append("The time is %s." % clock)
        try:
            bits.append(" ".join(self.moon_lines()[:1]))
        except Exception:
            pass
        self.speech.say_now(" ".join(bits))

    def sr_stop(self):
        self.speech.stop()

    def sr_mute(self):
        if self._sr_off_message():
            return
        self.speech.muted = not self.speech.muted
        if self.speech.muted:
            self.speech.stop()
            self.system("Speech muted.")
        else:
            self.speech.say_now("Speech on.")

    def access_actions(self):
        return {"sr_prev": self.sr_prev, "sr_next": self.sr_next, "sr_last": self.sr_last,
                "sr_stats": self.sr_stats, "sr_pane": self.sr_pane, "sr_time": self.sr_time,
                "sr_stop": self.sr_stop, "sr_mute": self.sr_mute}

    # ---- /sr command -------------------------------------------------------------------
    def _access_command(self, cmd, arg):
        if cmd not in ("sr", "screenreader"):
            return False
        a = arg.lower().split()
        if not a or a[0] == "status":
            on = "on" if self.sr_on() else "off"
            self.system("Screen reader mode is %s. Voice: %s (%s). Rate: %s. Alerts: %s. Stats every: %s." % (
                on, self.cfg.get("sr_voice", "auto"), self.speech.backend.name, self.cfg.get("sr_rate", 0),
                "on" if self.cfg.get("sr_alerts", True) else "off",
                ("%d seconds" % self.cfg["sr_interval"]) if self.cfg.get("sr_interval") else "off"))
        elif a[0] in ("on", "off"):
            self._set_extra("screen_reader", a[0] == "on")
        elif a[0] == "help":
            self.system(HELP_TEXT)
            if self.sr_on():
                self.speech.say_now(HELP_TEXT)
        elif a[0] == "voice" and len(a) > 1 and a[1] in speech.CHOICES:
            self._set_extra("sr_voice", a[1])
            if self.sr_on():
                self.set_screen_reader(True, announce=True)
        elif a[0] == "rate" and len(a) > 1 and re.fullmatch(r"-?\d{1,2}", a[1]):
            self.cfg["sr_rate"] = max(-10, min(10, int(a[1])))
            self._save_settings()
            b = self.speech.backend
            if hasattr(b, "set_rate"):
                b.set_rate(self.cfg["sr_rate"])
            self.system("Speech rate %d (Windows voice only)." % self.cfg["sr_rate"])
        elif a[0] == "alerts" and len(a) > 1 and a[1] in ("on", "off"):
            self._set_extra("sr_alerts", a[1] == "on")
            self.system("Alerts %s." % a[1])
        elif a[0] == "interval" and len(a) > 1 and (a[1] == "off" or re.fullmatch(r"\d{1,4}", a[1])):
            secs = self.set_sr_interval(0 if a[1] == "off" else int(a[1]))
            msg = "Stats are read every %d seconds." % secs if secs else "Interval reading is off."
            self.system(msg)
        elif a[0] == "combat":
            if len(a) == 1:
                self.open_combat_filter()
            else:
                cfg = combatfilter.clean_settings(self.cfg.get("sr_combat"))
                which = a[1:]
                if which == ["all"]:
                    cfg["skip"] = {c: True for c in combatfilter.CATEGORIES}
                elif which == ["none"]:
                    cfg["skip"] = {c: False for c in combatfilter.CATEGORIES}
                elif all(w in combatfilter.CATEGORIES for w in which):
                    cfg["skip"] = {c: (c in which) for c in combatfilter.CATEGORIES}
                else:
                    self.system("Usage: /sr combat [all|none|pn nn np pp]   (pn players hit NPCs, nn NPCs fight, "
                                "np NPCs hit players, pp players fight)")
                    return True
                self.cfg["sr_combat"] = cfg
                self._save_settings()
                self.system("Skipping: %s." % (", ".join(c for c in combatfilter.CATEGORIES if cfg["skip"][c]) or "nothing"))
        elif a[0] == "test":
            self.speech.say_now("This is a speech test. If you can hear this, speech is working.")
        else:
            self.system("Usage: /sr on|off|status|help|test, /sr voice auto|nvda|jaws|windows|off, "
                        "/sr rate -10..10, /sr alerts on|off, /sr interval off|SECONDS, /sr combat [all|none|pn nn np pp]")
        return True
