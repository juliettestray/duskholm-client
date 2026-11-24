"""An emoji picker inside Sanctuary (Alt+E, /emoji, File menu).

Windows' own emoji panel (Win+.) cannot put its choice into a Tk entry box: the emoji shows while the panel is open
and vanishes when it closes, because Tk does not accept what that panel hands over. This picker puts the emoji into
the entry box itself (they are sent as :name: when the emoji option is on, like any other you type or paste).

Search is by part of a name: 'heart', 'cat', 'fire', 'face smile'. An empty search lists the familiar ones."""
import tkinter as tk
import tkinter.font as tkfont
import unicodedata

import emojis

_BLOCKS = ((0x1F300, 0x1FAFF), (0x2600, 0x27BF))      # where the pictorial emoji live
_CAT = None
MAX_SHOWN = 300


def catalog():
    """[(char, name, searchable text)]: the familiar ones first (with their short names), then the rest."""
    global _CAT
    if _CAT is not None:
        return _CAT
    out, seen = [], set()
    aliases = {}
    for code, ch in emojis._FWD.items():
        aliases.setdefault(ch, []).append(code.replace("_", " "))
    for ch, names in aliases.items():
        seen.add(ch)
        out.append((ch, names[0], " ".join(names)))
    for a, b in _BLOCKS:
        for cp in range(a, b + 1):
            ch = chr(cp)
            if ch in seen:
                continue
            try:
                name = unicodedata.name(ch).lower()
            except ValueError:
                continue
            if "variation selector" in name or "modifier" in name or not emojis._is_emoji(ch):
                continue
            seen.add(ch)
            out.append((ch, name, name))
    _CAT = out
    return out


def search(query, limit=MAX_SHOWN):
    """Matches for `query` (every word must appear in the name), best first."""
    terms = str(query or "").lower().replace("_", " ").replace(":", " ").split()
    cat = catalog()
    if not terms:
        return [(c, n) for c, n, _t in cat[:min(limit, len(emojis._FWD))]]
    hits = []
    for ch, name, text in cat:
        if all(t in text for t in terms):
            starts = any(w.startswith(terms[0]) for w in text.split())
            hits.append((0 if starts else 1, len(name), ch, name))
    hits.sort(key=lambda h: h[:2])
    return [(ch, name) for _a, _b, ch, name in hits[:limit]]


class EmojiPickMixin:
    _emoji_win = None

    def _emoji_into_input(self, ch):
        try:
            self.input.insert("insert", ch)
        except tk.TclError:
            pass

    def _emojipick_command(self, cmd, arg):
        """/emoji [words]: open the picker; with words, list matches here too."""
        if cmd not in ("emoji", "emojis"):
            return False
        if arg:
            hits = search(arg, 24)
            self.system("Emoji matching '%s': %s" % (arg, "  ".join("%s %s" % h for h in hits)
                                                        if hits else "none. Try part of a name, like heart or cat."))
        self.open_emoji_picker(arg)
        return True

    def open_emoji_picker(self, query=""):
        if self.dos:
            return self._dos_emoji_dialog(query)
        win = self._emoji_win
        if win is not None:
            try:
                win.deiconify(); win.lift(); win._search.focus_set()
                if query:
                    win._search.delete(0, "end"); win._search.insert(0, query); win._render()
                return win
            except tk.TclError:
                self._emoji_win = None
        win = tk.Toplevel(self.root)
        win.title("Emoji")
        win.transient(self.root)
        try:
            win.geometry("+%d+%d" % (self.root.winfo_rootx() + 60, self.root.winfo_rooty() + 80))
        except tk.TclError:
            pass
        top = tk.Frame(win)
        top.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(top, text="Look for:").pack(side="left")
        search_var = tk.StringVar(value=query or "")
        ent = tk.Entry(top, textvariable=search_var, width=28)
        ent.pack(side="left", padx=6, fill="x", expand=True)
        fam = self.f_norm.actual("family")
        big = tkfont.Font(family=fam, size=max(14, int(self.f_norm.cget("size")) + 5))
        box = tk.Frame(win)
        box.pack(fill="both", expand=True, padx=8)
        text = tk.Text(box, width=26, height=9, wrap="char", font=big, cursor="hand2", spacing1=4, spacing3=4,
                       bd=0, highlightthickness=0, padx=4, state="disabled")
        sb = tk.Scrollbar(box, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        name_lbl = tk.Label(win, anchor="w", text="Click one to add it to what you are typing.", padx=8)
        name_lbl.pack(fill="x", pady=(4, 0))
        row = tk.Frame(win)
        row.pack(fill="x", padx=8, pady=8)
        tk.Label(row, text="Enter: add the first   Esc: close", anchor="w").pack(side="left")
        tk.Button(row, text="Close", width=8, command=win.destroy).pack(side="right")
        state = {"hits": []}

        def render(_e=None):
            state["hits"] = search(search_var.get())
            text.configure(state="normal")
            text.delete("1.0", "end")
            for n, (ch, _n) in enumerate(state["hits"]):
                text.insert("end", ch, "e%d" % n)              # each emoji carries its own tag: no counting of characters
                text.insert("end", " ")
            text.configure(state="disabled")
            name_lbl.configure(text="%d match%s" % (len(state["hits"]), "" if len(state["hits"]) == 1 else "es")
                               if state["hits"] else "Nothing matches. Try part of a name, like heart or cat.")

        def at(e):
            try:
                tags = text.tag_names(text.index("@%d,%d" % (e.x, e.y)))
            except tk.TclError:
                return None
            for t in tags:
                if t[:1] == "e" and t[1:].isdigit() and int(t[1:]) < len(state["hits"]):
                    return state["hits"][int(t[1:])]
            return None

        def hover(e):
            h = at(e)
            name_lbl.configure(text="%s  %s" % h if h else "")

        def click(e):
            h = at(e)
            if h:
                self._emoji_into_input(h[0])
                name_lbl.configure(text="Added %s  %s" % h)
            return "break"

        def first(_e=None):
            if state["hits"]:
                self._emoji_into_input(state["hits"][0][0])
            return "break"

        text.bind("<Motion>", hover)
        text.bind("<Button-1>", click)
        ent.bind("<KeyRelease>", render)
        ent.bind("<Return>", first)
        win.bind("<Escape>", lambda e: win.destroy())
        win._search, win._render = ent, render
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.bind("<Destroy>", lambda e: setattr(self, "_emoji_win", None) if e.widget is win else None, add="+")
        self._emoji_win = win
        try:
            self._theme_tree(win)
        except Exception:
            pass
        render()
        ent.focus_set()
        return win

    # ---- DOS look: ask what to look for, then pick from the list -------------------------------
    def _dos_emoji_dialog(self, query=""):
        fields = [{"key": "q", "label": "Look for", "type": "text", "value": query or "", "width": 30}]

        def done(result, values):
            if result == "find":
                self._dos_emoji_list(str(values.get("q", "")).strip())
        return self._dos_dialog("Emoji", fields, [("Find", "find"), ("Cancel", "cancel")], done, width=50,
                                message="Part of a name: heart, cat, fire, face smile. Blank: the familiar ones.")

    def _dos_emoji_list(self, query):
        hits = search(query, 120)
        if not hits:
            self.system("No emoji match '%s'. Try part of a name, like heart or cat." % query)
            return self._dos_emoji_dialog(query)

        def pick(ch):
            self._emoji_into_input(ch)
            self.root.after_idle(self.input.focus_set)
        items = [{"label": "%s   %s" % (name, ch), "action": (lambda c=ch: pick(c))} for ch, name in hits]
        return self._dos_menu("Emoji: %s" % (query or "familiar"), items, back=lambda: self._dos_emoji_dialog(query))
