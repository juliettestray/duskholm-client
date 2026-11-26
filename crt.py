"""CRT scanlines for the DOS look (an option, off by default).

The text itself is never touched. A borderless, see-through window sits over the client area of the main window and
holds a pattern of dark horizontal lines (every other screen row) at a low opacity. Windows composites it on its own, so
printing text, scrolling and redrawing cost nothing extra; the only work is moving and resizing it with the main window.
It ignores the mouse (clicks and selection go straight through), never takes the keyboard, stays out of Alt-Tab, hides
when the window is minimised or when you leave the DOS look, and is off in screen reader mode (which has no DOS look).
Windows only."""
import sys
import time
import tkinter as tk
from tkinter import messagebox

LEVELS = {"light": 0.12, "medium": 0.22, "strong": 0.38}      # how dark the lines are (window opacity)
KEY = "#fe00fe"                                               # the colour that is see-through (never drawn)
GAP = 2                                                       # a line every GAP screen rows
LONG = 16384                                                  # lines are this long (the window shows only what fits)

WARNING = ("Scanlines can tire the eyes or bring on a headache in some people, especially over long sessions, with "
           "migraines, or on high-resolution screens. If you feel any discomfort, turn them off: Options > CRT scanlines "
           "in the DOS look, or type /crt off.")

_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT, _WS_EX_LAYERED, _WS_EX_TOOLWINDOW, _WS_EX_NOACTIVATE = 0x20, 0x80000, 0x80, 0x08000000


def click_through(win):
    """Make the Tk toplevel `win` ignore the mouse, never take focus and stay out of Alt-Tab. True if it worked."""
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.GetAncestor.argtypes, u.GetAncestor.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
        u.GetWindowLongW.argtypes, u.GetWindowLongW.restype = [wintypes.HWND, ctypes.c_int], ctypes.c_long
        u.SetWindowLongW.argtypes, u.SetWindowLongW.restype = [wintypes.HWND, ctypes.c_int, ctypes.c_long], ctypes.c_long
        hwnd = u.GetAncestor(win.winfo_id(), 2)               # GA_ROOT: Tk's wrapper window
        if not hwnd:
            return False
        ex = u.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, _GWL_EXSTYLE, ex | _WS_EX_TRANSPARENT | _WS_EX_LAYERED | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE)
        return True
    except Exception:  # noqa: BLE001 - a decoration must never be able to stop the program
        return False


def _api():
    """The few Windows calls the self-check uses (or None where there are none)."""
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.GetAncestor.argtypes, u.GetAncestor.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
        u.GetWindow.argtypes, u.GetWindow.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
        u.GetWindowLongW.argtypes, u.GetWindowLongW.restype = [wintypes.HWND, ctypes.c_int], ctypes.c_long
        u.IsWindowVisible.argtypes, u.IsWindowVisible.restype = [wintypes.HWND], wintypes.BOOL
        return u
    except Exception:  # noqa: BLE001
        return None


WANT_STYLE = _WS_EX_TRANSPARENT | _WS_EX_LAYERED | _WS_EX_TOOLWINDOW | _WS_EX_NOACTIVATE
CHECK_MS = 1000


class CrtMixin:
    def crt_wanted(self):
        return bool(self.dos and self.cfg.get("crt_lines", "off") in LEVELS and sys.platform.startswith("win"))

    def _crt_option_changed(self, old, new, ask=True):
        """Turning the lines on (from off) warns first: a dialog in the normal look that can be answered No (False: taken
        back), a DOS dialog in the DOS look, and a line of text when it came from /crt. Going from one strength to another,
        or off, says nothing. True when the change stands (in the DOS look it stands until the dialog says otherwise)."""
        if old != "off" or new == "off":
            return True
        if not ask:
            self.system("Warning: " + WARNING)
            return True
        if self.dos:
            def answered(res, _vals):
                if res == "off":
                    self._set_extra("crt_lines", "off")
                self._reopen(self.dos_options_menu)
            self.root.after_idle(lambda: self._dos_dialog(
                "CRT scanlines", [], [("Keep them on", "keep"), ("Turn them off", "off")], answered, width=66,
                message=WARNING, esc_result="off") if self.dos and not self._overlay_open() else None)
            return True
        return messagebox.askokcancel("CRT scanlines: a warning", WARNING + chr(10) * 2 + "Turn them on?", parent=self.root)

    def _apply_crt(self):
        """Show, move or hide the lines to match the settings and the main window. True if they had to be moved."""
        try:
            if self.crt_wanted():
                return bool(self._crt_show())
            self._crt_hide()
        except tk.TclError:
            pass
        return False

    def _crt_hide(self):
        win = getattr(self, "_crt", None)
        if win is not None:
            try:
                win.withdraw()
            except tk.TclError:
                pass

    def _crt_make(self):
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.title("")
        win.transient(self.root)                              # owned by the main window: always just above it, never above other programs
        cv = tk.Canvas(win, bg=KEY, bd=0, highlightthickness=0, cursor="arrow", takefocus=0)
        cv.pack(fill="both", expand=True)
        win.attributes("-transparentcolor", KEY)
        win.update_idletasks()
        win._cv, win._rows, win._level = cv, 0, None
        win._through = click_through(win)
        self._crt, self._crt_job = win, None
        self.root.bind("<Configure>", self._crt_follow, add="+")
        self.root.bind("<Unmap>", self._crt_follow, add="+")
        self.root.bind("<Map>", self._crt_follow, add="+")
        self.root.bind("<FocusIn>", self._crt_focus, add="+")
        self._crt_log = []
        self._crt_check_job = self.root.after(CHECK_MS, self._crt_check)
        return win

    def _crt_show(self):
        win = getattr(self, "_crt", None) or self._crt_make()
        return self._crt_place()

    def _crt_follow(self, e=None):
        """The main window moved, changed size, was minimised or came back: follow it (several events become one move)."""
        if e is not None and e.widget is not self.root:
            return
        if getattr(self, "_crt_job", None) is None and getattr(self, "_crt", None) is not None:
            try:
                self._crt_job = self.root.after(20, self._crt_run)
            except tk.TclError:
                self._crt_job = None

    def _crt_run(self):
        self._crt_job = None
        if self._apply_crt():                                 # it moved: look once more soon (the window's position can lag its size)
            try:
                self._crt_job = self.root.after(120, self._crt_run)
            except tk.TclError:
                self._crt_job = None

    def _crt_place(self):
        win = self._crt
        try:
            visible = self.root.state() != "iconic" and self.root.winfo_viewable()
        except tk.TclError:
            visible = False
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if not visible or w < 50 or h < 50:
            win.withdraw()
            return False
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        geom = (w, h, x, y)
        changed = geom != getattr(win, "_geom", None)
        level = self.cfg.get("crt_lines", "off")
        up = win.state() == "normal"
        if up and not changed and win._level == level:
            return False                                      # nothing to do: touching the window again would only make the
        win._geom = geom                                      # main window send another event, and the lines would flicker
        if changed:
            win.geometry("%dx%d+%d+%d" % geom)
        if win._level != level:
            win.attributes("-alpha", LEVELS[level])
            win._level = level
        if win._rows * GAP < h:                               # lines are drawn once, long and tall enough, and only added if the window grows past them:
            cv = win._cv                                      # a resize then moves the window and nothing else
            tall = max(h, self.root.winfo_vrootheight()) + 4 * GAP
            for yy in range(win._rows * GAP, tall, GAP):
                cv.create_line(0, yy, LONG, yy, fill="black")
            win._rows = (tall + GAP - 1) // GAP
        if not up:
            win.deiconify()
            if not win._through:
                win._through = click_through(win)
            win.lift(self.root)                               # (only when it appears: moving it is not re-stacking it)
        return changed

    # ---- the self-check: anything that has gone wrong with it is put right ----------------------------------------------
    def _crt_focus(self, e=None):
        if e is not None and e.widget is not self.root:
            return
        try:
            self.root.after(150, self._crt_verify)                 # (after whatever came back to the window has settled)
        except tk.TclError:
            pass

    def _crt_check(self):
        self._crt_check_job = None
        try:
            self._crt_verify()
            self._crt_check_job = self.root.after(CHECK_MS, self._crt_check)
        except tk.TclError:
            pass

    def _crt_problems(self):
        """What is wrong with the lines right now, as short words ([] when all is well)."""
        win = getattr(self, "_crt", None)
        if win is None or not self.crt_wanted():
            return []
        try:
            if self.root.state() == "iconic" or not self.root.winfo_viewable():
                return []                                           # (the main window is away: the lines are meant to be)
            if getattr(self, "_crt_job", None) is not None:
                return []                                           # (it is just being moved with the window)
            out = []
            if win.state() != "normal":
                out.append("hidden")
            w, h = self.root.winfo_width(), self.root.winfo_height()
            if win.state() == "normal" and (win.winfo_width(), win.winfo_height(), win.winfo_rootx(), win.winfo_rooty())                     != (w, h, self.root.winfo_rootx(), self.root.winfo_rooty()):
                out.append("misplaced")
            u = _api()
            if u is not None and win.state() == "normal":
                o, r = u.GetAncestor(win.winfo_id(), 2), u.GetAncestor(self.root.winfo_id(), 2)
                if o and r:
                    if not u.IsWindowVisible(o):
                        out.append("not shown")
                    if (u.GetWindowLongW(o, _GWL_EXSTYLE) & WANT_STYLE) != WANT_STYLE:
                        out.append("lost click-through")
                    h2, n = u.GetWindow(r, 3), 0                     # GW_HWNDPREV: the windows above the main one, nearest first
                    while h2 and n < 200 and h2 != o:
                        h2, n = u.GetWindow(h2, 3), n + 1
                    if h2 != o:
                        out.append("behind the window")
            return out
        except tk.TclError:
            return []

    def _crt_verify(self):
        """Put right whatever _crt_problems finds, and remember what it was (/crt tells). Does nothing when all is well."""
        bad = self._crt_problems()
        if not bad:
            return []
        win = self._crt
        try:
            win._geom = None                                        # (so the next placement really does it)
            if "lost click-through" in bad:
                win._through = click_through(win)
            if "hidden" in bad or "not shown" in bad or "behind the window" in bad:
                win.withdraw()                                      # (a fresh show also puts it above the main window again)
            self._apply_crt()
        except tk.TclError:
            pass
        self._crt_log = (self._crt_log + [(time.strftime("%H:%M:%S"), ", ".join(bad))])[-8:]
        return bad

    def _crt_command(self, arg):
        """/crt  /crt off|light|medium|strong"""
        a = arg.strip().lower()
        if a in ("off", "light", "medium", "strong"):
            self._set_extra("crt_lines", a, ask=False)       # (typed on purpose: the warning is a line of text, not a dialog)
            if not self.dos:
                self.system("CRT scanlines %s (they show in the DOS look, Alt+D)." % a)
            return
        shown = getattr(self, "_crt", None) is not None and self._crt.state() == "normal"
        self.system("CRT scanlines: %s; %s%s." % (self.cfg.get("crt_lines", "off"),
                    "showing" if shown else ("not showing (DOS look only)" if not self.dos else "not showing"),
                    "" if not getattr(self, "_crt_log", None) else "; put right: " + "; ".join("%s %s" % x for x in self._crt_log[-4:])))
