"""What's new: after an update, a window listing what changed (every version since the one last shown), and /changes.

The text is in changes.py (newest first). The last version whose news was shown is kept in the settings as
`changes_seen`. A brand-new install shows nothing; an install from before this existed shows the current version only;
after that, a jump over several versions lists every one it skipped."""
import re
import tkinter as tk

import changes
import version


def vkey(v):
    """'1.2.10' -> (1, 2, 10); anything odd sorts first."""
    try:
        return tuple(int(x) for x in str(v).lstrip("vV").split("."))
    except ValueError:
        return (0,)


def entries_since(seen, current=None, entries=None):
    """[(version, text)] newer than `seen` and no newer than `current`, newest first. seen=None: only `current`'s own."""
    current = current or version.__version__
    entries = changes.CHANGES if entries is None else entries
    top = vkey(current)
    if seen is None:
        return [(v, t) for v, t in entries if vkey(v) == top][:1]
    low = vkey(seen)
    return [(v, t) for v, t in sorted(entries, key=lambda e: vkey(e[0]), reverse=True) if low < vkey(v) <= top]


def plain(text):
    """The Markdown-ish release text as plain lines: bullets, no ** or `."""
    out = []
    for ln in str(text).replace("\r", "").split("\n"):
        ln = re.sub(r"\*\*|`", "", ln)
        out.append(("  • " + ln[2:]) if ln.startswith("- ") else ln)
    return "\n".join(out)


def render(entries):
    parts = []
    for v, t in entries:
        parts.append("Version %s\n%s" % (v, plain(t)))
    return "\n\n".join(parts)


class WhatsNewMixin:
    def maybe_show_whatsnew(self):
        """Once at start-up: show the news the person has not seen. Remembers that it has."""
        cur = version.__version__
        seen = self.cfg.get("changes_seen") or ""
        if seen == cur:
            return None
        if not seen and not getattr(self, "_had_settings", False):
            self.cfg["changes_seen"] = cur                  # a new install: nothing to catch up on
            self._save_settings()
            return None
        ents = entries_since(seen or None, cur)
        self.cfg["changes_seen"] = cur
        self._save_settings()
        if not ents:
            return None
        return self.open_whatsnew(ents, intro="Sanctuary has been updated to %s." % cur)

    def open_whatsnew(self, entries=None, intro=""):
        entries = entries if entries is not None else entries_since(None)
        if not entries:
            self.system("No news for this version.")
            return None
        text = render(entries)
        head = intro or ("What's new in Sanctuary %s" % entries[0][0] if len(entries) == 1 else "What's new in Sanctuary")
        if self.dos:                                         # the DOS look: into the main text, where it scrolls and can be read
            self.system(head)
            for ln in text.split("\n"):
                self.system(ln)
            return None
        old = getattr(self, "_news_win", None)
        try:
            if old is not None and old.winfo_exists():
                old.destroy()
        except tk.TclError:
            pass
        top = tk.Toplevel(self.root)
        self._news_win = top
        top.title("What's new")
        top.transient(self.root)
        tk.Label(top, text=head, justify="left", font=self.f_bold).pack(anchor="w", padx=12, pady=(10, 4))
        frame = tk.Frame(top)
        frame.pack(fill="both", expand=True, padx=12, pady=4)
        sb = tk.Scrollbar(frame)
        sb.pack(side="right", fill="y")
        box = tk.Text(frame, width=76, height=20, wrap="word", font=self.f_norm, yscrollcommand=sb.set)
        sb.configure(command=box.yview)
        box.pack(side="left", fill="both", expand=True)
        box.tag_configure("ver", font=self.f_bold)
        for line in text.split("\n"):
            box.insert("end", line + "\n", "ver" if line.startswith("Version ") else ())
        box.configure(state="disabled")
        bf = tk.Frame(top)
        bf.pack(pady=8)

        def close(_e=None):
            top.destroy()
            self._news_win = None
            try:
                self.input.focus_set()
            except tk.TclError:
                pass
            return "break"
        tk.Button(bf, text="Close", width=10, command=close).pack()
        top.bind("<Escape>", close)
        top.protocol("WM_DELETE_WINDOW", close)
        top._text = box
        self._theme_tree(top)
        box.focus_set()                                      # (a reader can step through it; Escape or Close ends)
        return top

    def _whatsnew_command(self, arg):
        """/changes   /changes all   /changes 1.1.4 (that version, and everything after it)"""
        a = arg.strip().lower()
        if a == "all":
            self.open_whatsnew(entries_since("0"))
        elif a:
            ents = [e for e in entries_since("0") if vkey(e[0]) >= vkey(a)]
            if ents:
                self.open_whatsnew(ents)
            else:
                self.system("No news from %s on. /changes all shows every version." % a[:20])
        else:
            self.open_whatsnew()
