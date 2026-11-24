"""Time stamps: an optional [HH:MM] (or [HH:MM:SS]) in front of each line the game sends, in the main text, and
independently for each capture pane.

Main text: Options > Time stamps (off by default). Panes: put (time) after a pane's name in the Panes / layout form
("right 40 OOC (time), Tells"), or /stamps <pane> on|off. A pane that has stamps on uses the main text's format, or
HH:MM when the main text has none. Stamps are your own clock, are drawn dimly, and never reach triggers, the log or
the screen reader (only what is drawn on the screen carries them)."""
import re
import time

_PANE_SUFFIX = re.compile(r"^(.*?)\s*\((?:time|ts|stamp|stamps)\)\s*$", re.I)
FORMATS = ("off", "hh:mm", "hh:mm:ss")
_WORDS = {"off": "off", "no": "off", "none": "off", "0": "off",
          "on": "hh:mm", "yes": "hh:mm", "min": "hh:mm", "minutes": "hh:mm", "hh:mm": "hh:mm",
          "sec": "hh:mm:ss", "secs": "hh:mm:ss", "seconds": "hh:mm:ss", "hh:mm:ss": "hh:mm:ss"}


def split_pane_name(token):
    """'OOC (time)' -> ('OOC', True); 'OOC' -> ('OOC', False)."""
    m = _PANE_SUFFIX.match(str(token))
    return (m.group(1).strip(), True) if m else (str(token).strip(), False)


class StampMixin:
    def stamp_text(self, pane=False):
        """The stamp for a line right now ('' when there is none). A pane that stamps always has one."""
        fmt = self.cfg.get("timestamps", "off")
        if fmt == "off":
            if not pane:
                return ""
            fmt = "hh:mm"
        return time.strftime("[%H:%M:%S] " if fmt == "hh:mm:ss" else "[%H:%M] ")

    def _stamp_key(self):
        return (self.theme["dim"], None, False, False, False, False)

    def _stamp_seg(self, plain):
        """[(text, tag)] to put in front of a line that is about to be drawn from its start, or []."""
        text = self.stamp_text()
        if not text:
            return []
        body = (plain or "").strip()
        if not body:
            return []                                      # blank lines stay blank
        try:
            if self._leading_prompt_len(plain) >= len(plain.rstrip()):
                return []                                  # a bare prompt line is not an event
        except Exception:
            pass
        return [(text, self._tag_for(self._stamp_key()))]

    def _stamps_command(self, cmd, arg):
        """/stamps  /stamps main off|hh:mm|hh:mm:ss  /stamps <pane> on|off"""
        if cmd not in ("stamps", "timestamps", "stamp"):
            return False
        words = (arg or "").split()
        fmt = self.cfg.get("timestamps", "off")
        if not words:
            panes = [d["name"] + (" (time)" if d["timestamps"] else "") for d in self.cfg["panes"]]
            self.system("Time stamps: main text %s; panes: %s.   /stamps main hh:mm|hh:mm:ss|off   /stamps <pane> on|off"
                        % (fmt, ", ".join(panes) if panes else "none yet"))
            return True
        target, value = words[0], (words[1].lower() if len(words) > 1 else "")
        if target.lower() in ("main", "text", "all"):
            if value not in _WORDS:
                self.system("Say how: /stamps main off, hh:mm or hh:mm:ss.")
                return True
            self._set_extra("timestamps", _WORDS[value])
            self.system("Time stamps in the main text: %s." % self.cfg["timestamps"])
            return True
        d = self._find_pane_def(target)
        if d is None:
            self.system("No pane called '%s' (/stamps main ... is the main text)." % target)
            return True
        if value not in ("on", "off", "yes", "no"):
            self.system("Say /stamps %s on or /stamps %s off." % (d["name"], d["name"]))
            return True
        d["timestamps"] = value in ("on", "yes")
        self._save_settings()
        self.system("Time stamps in %s: %s." % (d["name"], "on" if d["timestamps"] else "off"))
        return True
