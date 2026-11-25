"""Capture a log that the game shows again and again (a phone's messages, say) onto a pane without ever doubling a line.

A route action with "once" set sends a line to its pane only when that pane has not already been given it. The game lists a
phone's whole message log every time you look at it, each message starting with its own date and time, so the same lines come
round again and again; this tells the new ones from the old.

A "message" is the line that matched, plus the lines straight after it that did not match anything while the line before
them was long enough to have been wrapped (the game wraps a long text onto further lines). It ends at a blank line, a
prompt, a line that matches again (the next message), or a pause. A message is told by its first line alone, so a stray
line that got carried along once never makes it look new later. Two
messages can be word for word the same inside one minute (their timestamp is only to the minute), so lines are counted, not
just remembered: in one listing the kth copy of a message is shown only when fewer than k copies were seen in an earlier
listing. Clearing the pane forgets what it was given, so the next look fills it again. Nothing here is saved: a new session
starts with an empty pane and an empty memory, which agree."""
import time

GAP = 3.0                  # seconds: lines further apart than this are not one listing
WRAP_MIN = 50              # a line shorter than this was not cut short by the game's wrapping, so nothing continues it
SETTLE_MS = 500            # the last message of a listing is shown this long after its last line
MAX_REMEMBERED = 4000


class CaptureMixin:
    def _once_table(self):
        t = self.__dict__.get("_once")
        if t is None:
            t = self.__dict__["_once"] = {}
        return t

    def _once_of(self, pane):
        table = self._once_table()
        key = (id(self.session), str(pane).strip().lower())
        st = table.get(key)
        if st is None:
            st = table[key] = {"key": key, "session": self.session, "pane": str(pane).strip(), "pending": None,
                               "stored": {}, "burst": {}, "last": -9, "t": 0.0, "job": None}
        return st

    def _once_line(self, plain):
        """Every line passes here first: a blank line or a prompt ends whatever is being collected; others count along."""
        table = self.__dict__.get("_once")
        if not plain.strip():
            for st in list((table or {}).values()):
                if st["session"] is self.session:
                    self._once_finish(st)
            return
        self._line_serial = self.__dict__.get("_line_serial", 0) + 1
        if table and self._leading_prompt_len(plain) > 0:
            for st in list(table.values()):
                if st["session"] is self.session:
                    self._once_finish(st)

    def _once_begin(self, pane, snapshot, plain):
        """`plain` matched a route-once rule for `pane`: it starts a new message."""
        st = self._once_of(pane)
        now = time.time()
        contiguous = st["last"] == self._line_serial - 1 and now - st["t"] < GAP
        if st["pending"] is not None:
            self._once_commit(st)
        if not contiguous:
            self._once_end_burst(st)
        st["pending"] = {"snaps": [snapshot], "plains": [plain]}
        self._once_touch(st, now)

    def _once_continue(self, snapshot, plain):
        """`plain` matched nothing: when it follows a message line directly it is that message going on."""
        table = self.__dict__.get("_once")
        if not table:
            return
        now = time.time()
        for st in list(table.values()):
            if st["session"] is self.session and st["pending"] is not None and st["last"] == self._line_serial - 1 \
                    and now - st["t"] < GAP and len(st["pending"]["plains"][-1]) >= WRAP_MIN:
                st["pending"]["snaps"].append(snapshot)
                st["pending"]["plains"].append(plain)
                self._once_touch(st, now)

    def _once_touch(self, st, now):
        st["last"], st["t"] = self._line_serial, now
        if st["job"] is not None:
            try:
                self.root.after_cancel(st["job"])
            except Exception:
                pass
        st["job"] = self.root.after(SETTLE_MS, lambda: self._once_finish(st))

    def _once_commit(self, st):
        """The message being collected is complete: show it unless this pane already has it."""
        msg, st["pending"] = st["pending"], None
        if msg is None:
            return
        key = msg["plains"][0]                        # told by its first line (date, time, who, how it starts)
        n = st["burst"][key] = st["burst"].get(key, 0) + 1
        if n <= st["stored"].get(key, 0):
            return
        if st["session"] not in self.sessions:
            return
        prev, self.session = self.session, st["session"]
        try:
            for snap in msg["snaps"]:
                self.pane_append(st["pane"], snap)
        finally:
            self.session = prev

    def _once_end_burst(self, st):
        for k, n in st["burst"].items():
            if n > st["stored"].get(k, 0):
                st["stored"][k] = n
        st["burst"] = {}
        if len(st["stored"]) > MAX_REMEMBERED:
            st["stored"].clear()

    def _once_finish(self, st):
        """A listing is over: show its last message and fold what it held into what is remembered."""
        if st["job"] is not None:
            try:
                self.root.after_cancel(st["job"])
            except Exception:
                pass
            st["job"] = None
        self._once_commit(st)
        self._once_end_burst(st)
        st["last"] = -9

    def _once_forget(self, pane):
        """The pane was cleared: what it had been given is no longer there to repeat."""
        st = self.__dict__.get("_once", {}).pop((id(self.session), str(pane).strip().lower()), None)
        if st is not None and st["job"] is not None:
            try:
                self.root.after_cancel(st["job"])
            except Exception:
                pass


# ---- my own side of a conversation: shown in the pane when the pane's "show what I send" switch is on -------------------------------
MINE_STYLE = (14, None, False, False, False, False)        # bright cyan, like the commands you send


class SentMixin:
    def _pane_shows_mine(self, pane):
        """Is the pane showing my own side? Yes unless it was switched off (a pane nobody has made yet shows it)."""
        def look():
            d = self._find_pane_def(pane)
            return not (d is not None and d.get("show_sent") is False)
        return self._in_world_cfg(look)

    def set_pane_sent(self, name, on):
        """The pane's "show what I send" switch (remembered with the pane)."""
        d = self._find_pane_def(name)
        if d is None:
            return False
        if on:
            d.pop("show_sent", None)
        else:
            d["show_sent"] = False
        pane = self._panes.get(d["name"].lower()) or self._panes.get(str(name).strip().lower())
        view = pane.get("popout") if pane else None
        if view and view.get("mine_var") is not None:
            view["mine_var"].set(bool(on))
        self._save_settings()
        return True

    def _game_stamp(self):
        """The time the way the game stamps a text, 'Nov 24 18:31' (the day is padded with a space), in the world's own clock."""
        import gametime
        try:
            dt = gametime.local_dt(self.world_time(self.session), time.time())
            return "%s %2d %02d:%02d" % (dt.strftime("%b"), dt.day, dt.hour, dt.minute)
        except Exception:
            t = time.localtime()
            return time.strftime("%b", t) + " %2d %02d:%02d" % (t.tm_mday, t.tm_hour, t.tm_min)

    def _capture_sent(self, line):
        """A command was just sent: rules that match what I send route their own side to a pane."""
        import triggers
        if not self.cfg.get("triggers"):
            return
        rules = [t for t in triggers.for_world(self.cfg["triggers"], *self._scope(self.session))
                 if t.get("when") == "sent" and t.get("enabled", True)]
        if not rules:
            return
        for trig, m in triggers.match_line(line, rules):
            for act in trig["actions"]:
                if act["type"] != "route":
                    continue
                if not self._pane_shows_mine(act["pane"]):
                    continue
                text = triggers.expand(act.get("format") or "%0", m["captures"])
                text = text.replace("{time}", self._game_stamp()).replace("{name}", self._char_name() or "You")
                self.pane_append(act["pane"], [(text, MINE_STYLE)])

    def _panesent_command(self, cmd, arg):
        """/panesent <pane> [on|off]: whether a pane shows what I send (no on/off: flip it)."""
        if cmd != "panesent":
            return False
        words = (arg or "").split()
        d = self._find_pane_def(words[0]) if words else None
        if d is None:
            self.system("Say which pane: /panesent <pane> [on|off]." if not words else "No pane called '%s'." % words[0])
            return True
        now = d.get("show_sent") is not False
        want = (words[1].lower() in ("on", "yes", "1")) if len(words) > 1 and words[1].lower() in (
            "on", "off", "yes", "no", "1", "0") else (not now)
        self.set_pane_sent(d["name"], want)
        self.system("%s shows what I send: %s." % (d["name"], "on" if want else "off"))
        return True

    def _pane_menu(self, event, key):
        """Right-click on a pane's tab."""
        import tkinter as tk
        d = self._find_pane_def(key)
        if d is None:
            return
        m = tk.Menu(self.root, tearoff=0)
        var = tk.BooleanVar(value=d.get("show_sent") is not False)
        m.add_checkbutton(label="Show what I send", variable=var, command=lambda: self.set_pane_sent(key, var.get()))
        m.add_command(label="Pop out", command=lambda: self.pop_out_pane(key))
        m.add_command(label="Clear", command=lambda: self.pane_clear(key))
        self._popup_menu(m, event.x_root, event.y_root)
