"""Speech output for screen reader mode (stdlib only).

Sanctuary speaks through a screen reader that is already running (NVDA through its controller
DLL, JAWS through its COM interface when pywin32 is installed) or, failing that, through the
Windows voice. Speech happens on a worker thread so a slow reader can never freeze the window.
Everything that decides *what* to say is a plain function that can be tested without any sound."""
import collections
import ctypes
import os
import queue
import re
import subprocess
import sys
import threading
import time
import unicodedata

try:
    import emojis
except ImportError:
    emojis = None

MAX_SPOKEN = 600
HISTORY = 500


# ======================================================================================
# turning a screen line into something worth hearing
# ======================================================================================
_URL = re.compile(r"https?://([^\s/<>\"'`]+)[^\s<>\"'`]*")
_ART = re.compile(r"([-_=*#~+.:<>^'`\\/|])\1{3,}")        # runs like ----- or ===== or .....
_ONLY_SYMBOLS = re.compile(r"^[\W_]*$")


def clean_for_speech(text):
    """A line of game output prepared for a speech engine: no colour codes, no line-drawing, no art,
    links named, emoji named. Returns '' when there is nothing worth saying."""
    if not isinstance(text, str):
        return ""
    t = re.sub(r"`(?:\d{3}|#[0-9a-fA-F]{6}|[A-Za-z*/])", "", text)           # game colour codes
    t = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", t)                            # stray escape sequences
    t = _URL.sub(lambda m: "link " + m.group(1), t)
    out = []
    for ch in t:
        o = ord(ch)
        if 0x2500 <= o <= 0x259F:                                              # box drawing, blocks, shades
            out.append(" ")
        elif o < 32 or o == 127:
            out.append(" ")
        elif o > 0x2000 and emojis is not None and emojis._is_emoji(ch):
            try:
                out.append(" %s " % unicodedata.name(ch).lower().replace("-", " "))
            except ValueError:
                out.append(" ")
        elif o in (0xFE0F, 0xFE0E, 0x200D):
            continue
        else:
            out.append(ch)
    t = "".join(out)
    t = _ART.sub(" ", t)
    t = t.replace("|", " ")
    t = " ".join(t.split())
    if _ONLY_SYMBOLS.match(t):
        return ""
    return t[:MAX_SPOKEN]


LABEL_WORDS = {"ST": "stun", "WN": "wounds", "M": "move timer", "K": "attack timer"}


def describe_prompt(p, labels=None):
    """The stat bar as a sentence, from a parse_prompt() result (or the client's cooled-down view)."""
    if not p:
        return "No stats yet."
    words = dict(LABEL_WORDS, **(labels or {}))
    bits = []
    hp = p.get("hp")
    if hp:
        cur, mx, label = hp
        w = words.get(label, label)
        pct = " (%d percent)" % round(100.0 * cur / mx) if mx else ""
        bits.append("%s %d of %d%s" % (w, cur, mx, pct))
    for label, cur, mx in (p.get("gauges") or [])[1:]:
        w = words.get(label, label)
        bits.append("%s %d of %d" % (w, cur, mx) if mx is not None else "%s %d" % (w, cur))
    for label, n in p.get("counters") or []:
        bits.append("%s %d" % (words.get(label, label), n))
    for label, n in p.get("cooldowns") or []:
        w = words.get(label, label + " timer")
        bits.append("%s ready" % w if n <= 0 else "%s %d second%s" % (w, n, "" if n == 1 else "s"))
    for t in p.get("text") or []:
        if t.strip():
            bits.append(clean_for_speech(t))
    return ". ".join(b for b in bits if b) + "."


# ======================================================================================
# the speaker: remembers what was said, keeps floods under control
# ======================================================================================
class Speech:
    """What to say, and the history to review. `backend` does the actual speaking."""

    def __init__(self, backend=None, clock=time.monotonic):
        self.backend = backend or NullBackend()
        self.muted = False
        self.history = collections.deque(maxlen=HISTORY)
        self.review = None                       # None = following live; else an index into history
        self.last_spoken = ""
        self._clock = clock
        self._recent = collections.deque(maxlen=64)
        self._skipped = 0
        self._last = ("", 0.0)
        self.flood_lines = 12                    # more than this in flood_secs and the rest are skipped
        self.flood_secs = 2.0

    # -- recording ---------------------------------------------------------------------
    def note(self, text, prefix=""):
        """Remember a line for review without speaking it. Returns the cleaned text ('' = nothing)."""
        t = clean_for_speech(text)
        if not t:
            return ""
        if prefix:
            t = "%s: %s" % (prefix, t)
        self.history.append(t)
        self.review = None
        return t

    def say(self, text, interrupt=False, prefix="", record=True):
        """Speak a line (and remember it). False when nothing was spoken."""
        t = clean_for_speech(text)
        if not t:
            return False
        if prefix:
            t = "%s: %s" % (prefix, t)
        if record:
            self.history.append(t)
            self.review = None
        if self.muted:
            return False
        now = self._clock()
        if t == self._last[0] and now - self._last[1] < 2.0:
            return False                          # the same line twice in a row is read once
        self._last = (t, now)
        while self._recent and now - self._recent[0] > self.flood_secs:
            self._recent.popleft()
        if len(self._recent) >= self.flood_lines and not interrupt:
            self._skipped += 1
            return False
        self._recent.append(now)
        if self._skipped:
            self.backend.speak("%d lines skipped." % self._skipped, False)
            self._skipped = 0
        self.last_spoken = t
        self.backend.speak(t, interrupt)
        return True

    def say_now(self, text):
        """Speak something that must be heard immediately (review keys, alerts): never flood-skipped."""
        t = clean_for_speech(text)
        if not t or self.muted:
            return False
        self.last_spoken = t
        self.backend.speak(t, True)
        return True

    def stop(self):
        self.backend.stop()

    def set_backend(self, backend):
        old, self.backend = self.backend, backend
        try:
            old.close()
        except Exception:
            pass

    # -- review ------------------------------------------------------------------------
    def review_step(self, d):
        """Move the review cursor by d lines (-1 older, +1 newer). Returns (text, note) where note is
        '' or 'top' / 'bottom' when the end of the history was hit."""
        if not self.history:
            return "", "empty"
        n = len(self.history)
        if self.review is None:                  # from live: older goes to the newest line, newer is already there
            i = n - 1 if d < 0 else n
        else:
            i = self.review + d
        note = ""
        if i < 0:
            i, note = 0, "top"
        elif i > n - 1:
            i, note = n - 1, "bottom"
        self.review = i
        return self.history[i], note

    def last(self, count=1):
        return list(self.history)[-count:]


# ======================================================================================
# backends
# ======================================================================================
class Backend:
    name = "off"

    def speak(self, text, interrupt=False):
        pass

    def stop(self):
        pass

    def close(self):
        pass


class NullBackend(Backend):
    name = "off"


class FakeBackend(Backend):
    """Records what would have been said (for tests)."""
    name = "fake"

    def __init__(self):
        self.said = []
        self.events = []

    def speak(self, text, interrupt=False):
        self.said.append(text)
        self.events.append(("say", text, interrupt))

    def stop(self):
        self.events.append(("stop",))

    def close(self):
        self.events.append(("close",))


class _Threaded(Backend):
    """Runs the real speaking on its own thread; speak() and stop() return at once."""

    def __init__(self):
        self._q = queue.Queue(maxsize=200)
        self._t = threading.Thread(target=self._run, daemon=True)
        self._started = False

    def _start(self):
        if not self._started:
            self._started = True
            self._t.start()

    def _run(self):
        self._setup()
        while True:
            item = self._q.get()
            if item is None:
                break
            try:
                self._do(*item)
            except Exception:
                pass
        self._teardown()

    def speak(self, text, interrupt=False):
        self._start()
        try:
            self._q.put_nowait(("say", text, interrupt))
        except queue.Full:
            pass

    def stop(self):
        self._start()
        try:
            self._q.put_nowait(("stop", "", True))
        except queue.Full:
            pass

    def close(self):
        if self._started:
            try:
                self._q.put_nowait(None)
            except queue.Full:
                pass

    def _setup(self):
        pass

    def _teardown(self):
        pass

    def _do(self, kind, text, interrupt):
        pass


def _dll_candidates():
    bits = "64" if sys.maxsize > 2 ** 32 else "32"
    name = "nvdaControllerClient%s.dll" % bits
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = [here]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = os.environ.get(env)
        if base:
            dirs.append(os.path.join(base, "NVDA"))
    return [os.path.join(d, name) for d in dirs]


class NVDABackend(_Threaded):
    """NVDA, through nvdaControllerClient (found next to the client or in NVDA's own folder)."""
    name = "nvda"

    def __init__(self):
        _Threaded.__init__(self)
        self._dll = None
        for path in _dll_candidates():
            if os.path.exists(path):
                try:
                    dll = ctypes.WinDLL(path)
                    if dll.nvdaController_testIfRunning() == 0:
                        self._dll = dll
                        break
                except (OSError, AttributeError):
                    continue
        if self._dll is None:
            raise OSError("NVDA is not running or its controller library was not found")

    def _do(self, kind, text, interrupt):
        if kind == "stop":
            self._dll.nvdaController_cancelSpeech()
            return
        if interrupt:
            self._dll.nvdaController_cancelSpeech()
        self._dll.nvdaController_speakText(ctypes.c_wchar_p(text))


class JAWSBackend(_Threaded):
    """JAWS, through its COM interface (needs the pywin32 package)."""
    name = "jaws"

    def __init__(self):
        _Threaded.__init__(self)
        try:
            import pythoncom          # noqa: F401
            import win32com.client    # noqa: F401
        except ImportError:
            raise OSError("JAWS needs the pywin32 package")
        self._api = None

    def _setup(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            self._api = win32com.client.Dispatch("FreedomSci.JawsApi")
        except Exception:
            self._api = None

    def _do(self, kind, text, interrupt):
        if self._api is None:
            return
        if kind == "stop":
            self._api.StopSpeech()
        else:
            self._api.SayString(text, bool(interrupt))


_PS_SCRIPT = (
    "Add-Type -AssemblyName System.Speech;"
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "while (($l = [Console]::In.ReadLine()) -ne $null) {"
    " if ($l -eq '<<STOP>>') { $s.SpeakAsyncCancelAll() }"
    " elseif ($l.StartsWith('<<RATE>>')) { try { $s.Rate = [int]$l.Substring(8) } catch {} }"
    " elseif ($l.StartsWith('<<NOW>>')) { $s.SpeakAsyncCancelAll(); [void]$s.SpeakAsync($l.Substring(7)) }"
    " else { [void]$s.SpeakAsync($l) } }"
)


class WindowsVoiceBackend(_Threaded):
    """The Windows built-in voice, through a small PowerShell helper (nothing to install)."""
    name = "windows"

    def __init__(self, rate=0):
        _Threaded.__init__(self)
        if not sys.platform.startswith("win"):
            raise OSError("The Windows voice is only on Windows")
        self.rate = max(-10, min(10, int(rate)))
        self._proc = None

    def _setup(self):
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=flags, text=True, encoding="utf-8")
            self._send("<<RATE>>%d" % self.rate)
        except (OSError, ValueError):
            self._proc = None

    def _send(self, line):
        if self._proc and self._proc.stdin:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()

    def set_rate(self, rate):
        self.rate = max(-10, min(10, int(rate)))
        self._start()
        try:
            self._q.put_nowait(("rate", str(self.rate), False))
        except queue.Full:
            pass

    def _do(self, kind, text, interrupt):
        if self._proc is None:
            return
        line = " ".join(text.split())
        if kind == "stop":
            self._send("<<STOP>>")
        elif kind == "rate":
            self._send("<<RATE>>" + text)
        else:
            self._send(("<<NOW>>" if interrupt else "") + line)

    def _teardown(self):
        try:
            if self._proc:
                self._proc.stdin.close()
                self._proc.terminate()
        except Exception:
            pass


CHOICES = ("auto", "nvda", "jaws", "windows", "off")


def make_backend(choice="auto", rate=0):
    """(backend, message). 'auto' tries NVDA, then the Windows voice."""
    choice = choice if choice in CHOICES else "auto"
    if choice == "off":
        return NullBackend(), "Speech is off."
    order = {"auto": ("nvda", "windows"), "nvda": ("nvda",), "jaws": ("jaws",), "windows": ("windows",)}[choice]
    errors = []
    for name in order:
        try:
            if name == "nvda":
                return NVDABackend(), "Speaking through NVDA."
            if name == "jaws":
                return JAWSBackend(), "Speaking through JAWS."
            return WindowsVoiceBackend(rate), "Speaking with the Windows voice."
        except OSError as e:
            errors.append("%s: %s" % (name, e))
    return NullBackend(), "No speech available (%s)." % "; ".join(errors)
