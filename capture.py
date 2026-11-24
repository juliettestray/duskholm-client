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
WRAP_MIN = 40              # a line shorter than this was not cut short by the game's wrapping, so nothing continues it
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
