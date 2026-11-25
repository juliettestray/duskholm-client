"""How much text the main window keeps (the scrollback length), and keeping the end of it between sessions.

The length is an Option (5,000 to 100,000 lines, default 20,000; the oldest lines go first). Reloading is a separate,
off-by-default option: when it is on, the last N lines of each world's text are saved as PLAIN TEXT (no colours) in a
`backscroll` folder next to the settings, one file per WORLD (a saved world by its id, so two worlds on the same address
keep separate text), and put back above that world's new text the next time it is connected (or at start-up for the world on
screen). N (kept) can never be more than the scrollback length. Loading
a long history makes starting up slower, which is why it is a choice. Nothing is saved while the option is off, and
switching it off deletes what was saved."""
import os
import re
import tkinter as tk
from tkinter import messagebox

TOTAL_CHOICES = ("5000", "10000", "20000", "50000", "100000")
KEEP_CHOICES = ("500", "1000", "2000", "5000", "10000", "20000")
DEFAULT_TOTAL, DEFAULT_KEEP = "20000", "2000"
SAVE_EVERY_MS = 5 * 60 * 1000
MAX_FILE_BYTES = 40 * 1024 * 1024               # never read more than this back, whatever is on disk

WARNING = ("Reloading earlier backscroll makes Sanctuary slower to start: the more lines you keep, the longer the load-up "
           "takes (a few thousand is quick; tens of thousands is not).\n\n"
           "It is saved as plain text, without colours, in the 'backscroll' folder next to your settings, so anyone who can "
           "open that folder can read what the game showed you. Switching the option off deletes it.\n\n"
           "Turn it on?")


def total_lines(cfg):
    try:
        return max(1000, int(cfg.get("scrollback_lines", DEFAULT_TOTAL)))
    except (TypeError, ValueError):
        return int(DEFAULT_TOTAL)


def keep_lines(cfg):
    """How many lines are saved: the chosen number, but never more than the scrollback length."""
    try:
        want = int(cfg.get("keep_lines", DEFAULT_KEEP))
    except (TypeError, ValueError):
        want = int(DEFAULT_KEEP)
    return max(1, min(want, total_lines(cfg)))


def clamp_keep(cfg):
    """Make cfg['keep_lines'] one of the offered numbers that is not above the scrollback length. True if it changed."""
    total = total_lines(cfg)
    try:
        cur = int(cfg.get("keep_lines", DEFAULT_KEEP))
    except (TypeError, ValueError):
        cur = int(DEFAULT_KEEP)
    if cur <= total:
        return False
    cfg["keep_lines"] = [k for k in KEEP_CHOICES if int(k) <= total][-1]
    return True


def file_key(host, port):
    return "%s_%s" % (re.sub(r"[^a-z0-9.\-]", "_", str(host or "").lower())[:80] or "world", port)


class BackscrollMixin:
    # ---- files -----------------------------------------------------------------------------------------------
    def _bs_name(self, s):
        """The file name (without .txt) for world s: a saved world by its id (which survives a rename or a new address); a
        world that is not saved by its name and address."""
        wid = self._world_id(s)
        if wid:
            return "w_" + re.sub(r"[^0-9a-f]", "", str(wid).lower())
        return "n_" + file_key("%s@%s" % (self._world_name(s), s.host), s.port)

    def _bs_path(self, s):
        return os.path.join(self._backscroll_dir(), self._bs_name(s) + ".txt")

    def _bs_legacy_path(self, s):
        """Before 1.2.1 the file was named after the address only."""
        return os.path.join(self._backscroll_dir(), file_key(s.host, s.port) + ".txt")

    def backscroll_save(self, s):
        """Write the last `keep` lines of world s's text. False when the option is off, there is nothing to write, or it failed."""
        if not self.cfg.get("keep_backscroll"):
            return False
        try:
            out = s.out
            total = int(out.index("end-1c").split(".")[0])
            if out.get("end-2c", "end-1c") == "\n":
                total -= 1                              # the empty line after the last line break is not a line of text
            first = max(1, total - keep_lines(self.cfg) + 1)
            text = out.get("%d.0" % first, "end-1c")
            if not text.strip():
                return False
            if not text.endswith("\n"):
                text += "\n"
            os.makedirs(self._backscroll_dir(), exist_ok=True)
            path = self._bs_path(s)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8", errors="replace", newline="\n") as f:
                f.write(text)
            os.replace(tmp, path)
            return True
        except (OSError, tk.TclError, ValueError):
            return False

    def backscroll_load(self, s):
        """Put the saved text above everything world s shows now, once per world. Returns the number of lines put back."""
        if getattr(s, "_bs_done", False) or not self.cfg.get("keep_backscroll"):
            return 0
        s._bs_done = True
        try:
            path = self._bs_path(s)
            legacy = False
            if not os.path.isfile(path):
                path, legacy = self._bs_legacy_path(s), True        # the old per-address file: the first world to ask has it
            if not os.path.isfile(path) or os.path.getsize(path) > MAX_FILE_BYTES:
                return 0
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            if legacy:
                try:
                    os.remove(path)                                 # (so a second world on that address does not get it too)
                except OSError:
                    pass
        except OSError:
            return 0
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        lines = lines[-keep_lines(self.cfg):]
        if not lines:
            return 0
        out = s.out
        try:
            out.configure(state="normal")
            out.insert("1.0", "[Earlier text from your last session is above this line: %d lines]\n" % len(lines), "system")
            out.insert("1.0", "\n".join(lines) + "\n")
            out.configure(state="disabled")
            out.see("end")                              # a new session always starts at the bottom, with the newest text
            self._backscroll_to_bottom(out)
        except tk.TclError:
            return 0
        return len(lines)

    def _backscroll_to_bottom(self, out):
        """The text was just put in before the window had been laid out, so 'end' was not yet in view and the new
        session began at the top of the old text. Move to the bottom again once the size is known, and once more a
        moment later (the window may still be settling), unless new text has already taken us there."""
        def go():
            try:
                if out.winfo_exists() and out.yview()[1] < 0.999:
                    out.yview_moveto(1.0)
            except tk.TclError:
                pass
        for delay in (0, 150, 500):
            try:
                self.root.after(delay, go) if delay else self.root.after_idle(go)
            except tk.TclError:
                pass

    def backscroll_clear_files(self):
        """Delete every saved backscroll file (our own cache folder only). Returns how many went."""
        gone = 0
        d = self._backscroll_dir()
        try:
            for name in os.listdir(d):
                if name.endswith((".txt", ".tmp")):
                    try:
                        os.remove(os.path.join(d, name))
                        gone += 1
                    except OSError:
                        pass
            os.rmdir(d)
        except OSError:
            pass
        return gone

    def backscroll_save_all(self):
        n = 0
        for s in list(self.sessions):
            n += 1 if self.backscroll_save(s) else 0
        return n

    def _backscroll_tick(self):
        try:
            self.backscroll_save_all()
        except Exception:  # noqa: BLE001 - a timer must never die
            pass
        try:
            self._bs_job = self.root.after(SAVE_EVERY_MS, self._backscroll_tick)
        except tk.TclError:
            self._bs_job = None

    # ---- the options ------------------------------------------------------------------------------------------
    def _backscroll_option_changed(self, key, value):
        """Called from _set_extra for the three options. Returns False when the change was taken back."""
        if key == "scrollback_lines":
            if clamp_keep(self.cfg):
                var = getattr(self, "_xvars", {}).get("keep_lines")
                if var is not None:
                    var.set(self.cfg["keep_lines"])
                self.system("Backscroll to keep lowered to %s lines: it cannot be more than the scrollback." % self.cfg["keep_lines"])
        elif key == "keep_lines":
            if clamp_keep(self.cfg):
                var = getattr(self, "_xvars", {}).get("keep_lines")
                if var is not None:
                    var.set(self.cfg["keep_lines"])
                self.system("Backscroll to keep set to %s lines: it cannot be more than the scrollback (%d)."
                            % (self.cfg["keep_lines"], total_lines(self.cfg)))
        elif key == "keep_backscroll":
            if value:
                if self.dos:
                    self.system("Reload backscroll is ON. " + WARNING.rsplit("\n\n", 1)[0].replace("\n\n", " "))
                elif not messagebox.askokcancel("Reload earlier backscroll", WARNING, parent=self.root):
                    self.cfg["keep_backscroll"] = False
                    var = getattr(self, "_xvars", {}).get("keep_backscroll")
                    if var is not None:
                        var.set(False)
                    return False
            else:
                self.backscroll_clear_files()
                for s in self.sessions:
                    s._bs_done = False
                self.system("Saved backscroll deleted; nothing more will be saved.")
        return True
