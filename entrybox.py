"""An entry box that grows as you type (Options > Entry box grows to ...; off by default).

When it is on, the one-line entry is replaced by GrowEntry: a Text widget that answers the handful of tk.Entry calls the
client makes (get, delete, insert, icursor, select_range ...), wraps at the window edge, and gets taller with its text up
to the number of lines you chose. Enter sends, as ever; Shift+Enter and Ctrl+Enter put a line break in the box instead.
A box with line breaks in it sends each line as its own command, in order (the same as typing them one after another).
A password is never typed into it: while the game has echo off the plain one-line entry takes over, so the masking
works exactly as before, and the text moves back and forth with the swap."""
import tkinter as tk

MAX_LINES_TOTAL = 200                      # most lines the box will hold (a paste is cut here)
MAX_SEND_CHARS = 20000                     # most sent in one go: the game holds about 24,000 waiting characters


class GrowEntry(tk.Text):
    """tk.Text with the tk.Entry methods the client uses, that grows to fit up to `max_lines` lines."""

    def __init__(self, master, max_lines=4, **kw):
        kw.setdefault("wrap", "word")
        kw.setdefault("height", 1)
        kw.setdefault("width", 1)
        kw.setdefault("padx", 0)
        kw.setdefault("pady", 0)
        kw.setdefault("undo", False)
        kw.setdefault("spacing1", 0)
        kw.setdefault("spacing3", 0)
        super().__init__(master, **kw)
        self.max_lines = max(1, int(max_lines))
        self._fit_job = None
        self.on_resize = None
        self.bind("<<Modified>>", self._modified)
        self.bind("<Configure>", lambda e: self._schedule_fit(), add="+")

    # ---- growing ------------------------------------------------------------------------------------
    def _modified(self, _e=None):
        try:
            self.edit_modified(False)
        except tk.TclError:
            return
        self._schedule_fit()

    def _schedule_fit(self):
        if self._fit_job is None:
            try:
                self._fit_job = self.after_idle(self.fit)
            except tk.TclError:
                pass

    def lines_wanted(self):
        try:
            n = int(self.tk.call(self._w, "count", "-displaylines", "1.0", "end-1c")) + 1
        except (tk.TclError, ValueError, TypeError):
            n = int(tk.Text.index(self, "end-1c").split(".")[0])
        return max(1, min(self.max_lines, n))

    def fit(self):
        self._fit_job = None
        try:
            want = self.lines_wanted()
            if want != int(self.cget("height")):
                self.configure(height=want)
                if self.on_resize:
                    self.on_resize(want)
            if want < self.max_lines:
                self.yview_moveto(0)
            self.see("insert")
        except tk.TclError:
            pass

    # ---- the tk.Entry calls ----------------------------------------------------------------------------
    @staticmethod
    def _ix(i):
        if isinstance(i, int):
            return "1.0+%dc" % i
        if i == "end":
            return "end-1c"
        return i                                           # insert, sel.first, sel.last ...

    def get(self, *_a):
        return tk.Text.get(self, "1.0", "end-1c")

    def delete(self, first, last=None):
        a = self._ix(first)
        b = self._ix(last) if last is not None else a + "+1c"
        tk.Text.delete(self, a, b)

    def insert(self, index, chars, *tags):
        tk.Text.insert(self, self._ix(index), chars, *tags)

    def index(self, i):
        return len(tk.Text.get(self, "1.0", tk.Text.index(self, self._ix(i))))

    def icursor(self, i):
        self.mark_set("insert", self._ix(i))
        self.see("insert")

    def selection_present(self):
        return bool(self.tag_ranges("sel"))

    def selection_clear(self):
        self.tag_remove("sel", "1.0", "end")

    def select_range(self, first, last):
        self.tag_remove("sel", "1.0", "end")
        self.tag_add("sel", self._ix(first), self._ix(last))

    selection_range = select_range

    def configure(self, cnf=None, **kw):
        kw.pop("show", None)                               # a password never goes in this box (see the module note)
        if cnf is None and "selectbackground" in kw:
            kw.setdefault("inactiveselectbackground", kw["selectbackground"])      # it stays visible when focus leaves
        return tk.Text.configure(self, cnf, **kw) if cnf is not None else tk.Text.configure(self, **kw)

    config = configure

    def cget(self, key):
        if key == "show":
            return ""
        return tk.Text.cget(self, key)

    def display_line_edge(self, up):
        """True when the cursor is on the first (up=True) or last display line, so Up / Down should walk the history."""
        try:
            if up:
                return int(self.tk.call(self._w, "count", "-displaylines", "1.0", "insert")) == 0
            return int(self.tk.call(self._w, "count", "-displaylines", "insert", "end-1c")) == 0
        except (tk.TclError, ValueError, TypeError):
            return True


class EntryBoxMixin:
    def _init_grow_input(self):
        """Called once, after the plain entry exists: build the growing one next to it (not shown until switched on)."""
        self._entry = self.input
        self._input_secret = False
        self._grow = self._reg(GrowEntry(self._inbox, max_lines=4, font=self.f_norm, highlightthickness=0,
                                         borderwidth=0), "input")
        g = self._grow
        g.bind("<FocusIn>", lambda e: self._inbox_focus(True), add="+")
        g.bind("<FocusOut>", lambda e: self._inbox_focus(False), add="+")
        g.bind("<Return>", self._on_enter)
        g.bind("<KP_Enter>", self._on_enter)
        for seq in ("<Shift-Return>", "<Control-Return>", "<Shift-KP_Enter>", "<Control-KP_Enter>"):
            g.bind(seq, self._grow_newline)
        g.bind("<Up>", lambda e: self._grow_walk(-1))
        g.bind("<Down>", lambda e: self._grow_walk(+1))
        g.bind("<Prior>", lambda e: self.out.yview_scroll(-1, "pages"))
        g.bind("<Next>", lambda e: self.out.yview_scroll(1, "pages"))
        g.bind("<Escape>", lambda e: g.delete(0, "end"))
        g.bind("<<Paste>>", self._on_paste)
        g.bind("<Control-v>", self._on_paste)
        g.bind("<Tab>", self._grow_tab)
        g.on_resize = self._grow_resized
        self._bind_edit_menu(g, entry=True)
        self.spell_attach(g, "input")                                            # (underlines, when Options turns it on)

    def _grow_tab(self, e):
        try:
            self.tk.call("tk::TabToWindow", self.tk.call("tk_focusNext", str(e.widget)))
        except tk.TclError:
            pass
        return "break"

    def _grow_newline(self, _e):
        g = self._grow
        if tk.Text.get(g, "1.0", "end-1c").count("\n") + 1 < MAX_LINES_TOTAL:
            if g.selection_present():
                g.delete("sel.first", "sel.last")
            g.insert("insert", "\n")
        return "break"

    def _grow_walk(self, d):
        """Up / Down: inside a box of several lines they move the cursor; on the first / last line they walk the history."""
        g = self._grow
        if g.display_line_edge(d < 0):
            return self._hist(d)
        return None

    def _grow_resized(self, _lines):
        """The box got taller or shorter: keep the newest output in view if that is where you were."""
        try:
            if self.out.yview()[1] >= 0.999:
                self.root.after_idle(lambda: self.out.yview_moveto(1.0))
        except tk.TclError:
            pass

    def entry_lines(self):
        """How many lines the box may grow to (0: it does not grow)."""
        try:
            return max(0, min(12, int(self.cfg.get("entry_grow", "off"))))
        except (TypeError, ValueError):
            return 0

    def _inputs(self):
        return tuple(w for w in (getattr(self, "_entry", None), getattr(self, "_grow", None)) if w is not None) or (self.input,)

    def _input_show(self, show):
        """Mask (show='*') or unmask the entry; a masked box is always the plain one."""
        self._input_secret = bool(show)
        self._entry.configure(show=show)
        self._apply_entry_mode()

    def _pack_input(self):
        self.input.pack(fill="x", padx=(4, 8), ipady=2 if self.dos else 5)       # side padding keeps the end of a line clear
        self._apply_keep_box()                                                   # (the 'Keep text' checkbox, if switched on)

    def _apply_entry_mode(self):
        """Show the growing box or the plain one, whichever the setting and the game's echo call for."""
        if not hasattr(self, "_grow"):
            return
        lines = self.entry_lines()
        want = self._grow if (lines > 0 and not self._input_secret) else self._entry
        self._grow.max_lines = max(1, lines)
        if want is self.input:
            if want is self._grow:
                self._grow.fit()
            return
        old = self.input
        try:
            focused = self.root.focus_get() is old
        except (tk.TclError, KeyError):
            focused = False
        text = old.get() if not (self._input_secret and old is self._entry) else ""
        if want is self._entry:
            text = text.replace("\n", " ")
        old.pack_forget()
        want.delete(0, "end")
        want.insert(0, text)
        self.input = want
        self._in_pad = None
        self._pack_input()
        want.icursor("end")
        if want is self._grow:
            want.fit()
        self._fit_input()
        self._inbox_focus(focused)
        if focused:
            want.focus_set()
