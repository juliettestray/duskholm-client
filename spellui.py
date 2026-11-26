"""Spell checking in the text boxes that can show it, using the Windows spell checker (winspell.py) plus the game's own
words (spellterms.py) and your own dictionary. Three switches in Options, all off by default:

  * the input box, when it is the growing one (a plain one-line box cannot underline a word),
  * the notepad,
  * the multi-line boxes of the customize form.

A misspelled word gets a red underline a moment after you stop typing; right-click it for suggestions, "Add to my
dictionary" and "Ignore all". /spell lists the commands (it also works in the DOS look and with a screen reader)."""
import re
import tkinter as tk

import spelltext
import spellterms
import winspell

KINDS = ("input", "notepad", "custom")
KIND_NAMES = {"input": "the growing input box", "notepad": "the notepad", "custom": "the customize form"}
DELAY_MS = 350
MARGIN_LINES = 30            # lines either side of what is on screen that are checked
MAX_WORDS = 2000
MAX_WORD_LEN = 40
TAG = "spell_bad"
_WORD_OK = re.compile(r"^[^\W\d_]+(?:['’][^\W\d_]+)*$", re.U)


def clean_words(lst):
    """The personal dictionary as stored: lower-case words, no duplicates, bounded."""
    out, seen = [], set()
    for w in lst if isinstance(lst, (list, tuple)) else []:
        if not isinstance(w, str):
            continue
        w = w.strip().casefold()
        if 1 < len(w) <= MAX_WORD_LEN and _WORD_OK.match(w) and w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= MAX_WORDS:
            break
    return out


class SpellMixin:
    # ---- the engine and the word lists ---------------------------------------------------------------
    def _spell_engine(self):
        sp = getattr(self, "_spell_sp", None)
        if sp is None:
            sp = winspell.WinSpell.create() or False
            self._spell_sp = sp
        return sp or None

    def spell_on(self, kind):
        return bool(self.cfg.get("spell_" + kind)) and self._spell_engine() is not None

    def _spell_allowed(self, kind):
        s = set(spellterms.TERMS)
        s.update(clean_words(self.cfg.get("spell_words")))
        s.update(getattr(self, "_spell_ignored", ()))
        if kind == "input":
            s |= spelltext.history_words(self.history[-300:])
        return s

    def spell_add_word(self, word):
        w = word.strip().casefold()
        words = clean_words(self.cfg.get("spell_words"))
        if len(w) < 2 or len(w) > MAX_WORD_LEN or not _WORD_OK.match(w):
            return False
        if w not in words:
            self.cfg["spell_words"] = (words + [w])[-MAX_WORDS:]
            self._save_settings()
        self.spell_refresh_all()
        return True

    def spell_remove_word(self, word):
        w = word.strip().casefold()
        words = clean_words(self.cfg.get("spell_words"))
        if w not in words:
            return False
        words.remove(w)
        self.cfg["spell_words"] = words
        self._save_settings()
        self.spell_refresh_all()
        return True

    def spell_ignore_word(self, word):
        if not hasattr(self, "_spell_ignored"):
            self._spell_ignored = set()
        self._spell_ignored.add(word.strip().casefold())
        self.spell_refresh_all()

    # ---- underlining ---------------------------------------------------------------------------------
    def spell_attach(self, w, kind):
        """Let a Text widget be spell-checked as `kind`. Cheap: nothing happens until the option is on."""
        if getattr(w, "_spell_kind", None) is not None:
            return
        w._spell_kind = kind
        w._spell_job = None
        for seq in ("<KeyRelease>", "<ButtonRelease-1>"):
            w.bind(seq, lambda _e, w=w: self.spell_soon(w), add="+")
        if kind != "input":
            w.bind("<Button-3>", lambda e, w=w: self._spell_popup(w, e), add="+")
        self.spell_soon(w)

    def spell_soon(self, w):
        if not self.spell_on(w._spell_kind) and not w.tag_ranges(TAG):
            return
        if w._spell_job is not None:
            try:
                w.after_cancel(w._spell_job)
            except tk.TclError:
                pass
        try:
            w._spell_job = w.after(DELAY_MS, lambda: self.spell_run(w))
        except tk.TclError:
            w._spell_job = None

    def spell_clear(self, w):
        try:
            w.tag_remove(TAG, "1.0", "end")
        except tk.TclError:
            pass

    def spell_run(self, w):
        w._spell_job = None
        try:
            if not w.winfo_exists():
                return
            kind = w._spell_kind
            if not self.spell_on(kind) or (kind == "input" and w is not self.input):
                self.spell_clear(w)
                return
            w.tag_configure(TAG, underline=True, underlinefg=self.theme["ansi"][9])
            total = int(tk.Text.index(w, "end-1c").split(".")[0])
            first = int(tk.Text.index(w, "@0,0").split(".")[0])
            last = int(tk.Text.index(w, "@0,%d" % max(1, w.winfo_height())).split(".")[0])
            a, b = max(1, first - MARGIN_LINES), min(total, last + MARGIN_LINES)
            text = tk.Text.get(w, "%d.0" % a, "%d.end" % b)
            found = spelltext.find_problems(self._spell_engine(), text, self._spell_allowed(kind), prose_only=(kind == "input"))
            w.tag_remove(TAG, "%d.0" % a, "%d.end" % b)
            for s, e, _k in found:
                w.tag_add(TAG, "%d.0+%dc" % (a, s), "%d.0+%dc" % (a, e))
        except tk.TclError:
            pass

    def spell_refresh_all(self):
        for w in self._spell_widgets():
            self.spell_clear(w) if not self.spell_on(w._spell_kind) else self.spell_run(w)

    def _spell_widgets(self):
        out = [getattr(self, "_grow", None)]
        np_ = getattr(self, "_notepad", None)
        if np_:
            out.append(np_["text"])
        out += list(getattr(self, "_spell_custom_boxes", ()))
        keep = []
        for w in out:
            try:
                if w is not None and getattr(w, "_spell_kind", None) and w.winfo_exists():
                    keep.append(w)
            except tk.TclError:
                pass
        self._spell_custom_boxes = [w for w in keep if w._spell_kind == "custom"]
        return keep

    # ---- the right-click menu ------------------------------------------------------------------------
    def _spell_range_at(self, w, x, y):
        try:
            idx = tk.Text.index(w, "@%d,%d" % (x, y))
            r = w.tag_prevrange(TAG, idx + "+1c")
            if r and w.compare(r[0], "<=", idx) and w.compare(idx, "<", r[1]):
                return r
        except tk.TclError:
            pass
        return None

    def _spell_items(self, w, x, y):
        """Menu entries for the misspelled word under the pointer: [(label, hotkey, enabled, action)], or []."""
        if not isinstance(w, tk.Text) or getattr(w, "_spell_kind", None) is None:
            return []
        r = self._spell_range_at(w, x, y)
        sp = self._spell_engine()
        if r is None or sp is None:
            return []
        a, b = str(r[0]), str(r[1])
        word = tk.Text.get(w, a, b)
        items = []
        repeat = not sp.check(word)                      # the word itself is fine: it is a repeat of the one before
        if repeat:
            items.append(("Delete the repeated word", "1", True, lambda: self._spell_replace(w, a, b, "", True)))
        else:
            for i, s in enumerate(sp.suggest(word, 6)):
                items.append((s, str(i + 1), True, lambda s=s: self._spell_replace(w, a, b, s)))
            if not items:
                items.append(("(no suggestions)", "1", False, lambda: None))
        shown = word if len(word) <= 20 else word[:19] + "…"
        if not repeat:
            items.append(("Add \"%s\" to my dictionary" % shown, "D", True, lambda: self.spell_add_word(word)))
        items.append(("Ignore all", "I", True, lambda: self.spell_ignore_word(word)))
        return items

    def _spell_replace(self, w, a, b, text, eat_space=False):
        try:
            if eat_space and tk.Text.get(w, a + "-1c", a) == " ":
                a = a + "-1c"
            tk.Text.delete(w, a, b)
            if text:
                tk.Text.insert(w, a, text)
        except tk.TclError:
            return
        self.spell_run(w)

    def _spell_popup(self, w, e):
        """Right-click in the notepad or the customize form: suggestions (when on a misspelled word), then the usual."""
        items = self._spell_items(w, e.x, e.y)
        has_sel = bool(w.tag_ranges("sel"))
        items += [("Cut", "T", has_sel, lambda: w.event_generate("<<Cut>>")),
                  ("Copy", "C", has_sel, lambda: w.event_generate("<<Copy>>")),
                  ("Paste", "P", self._clipboard_has_text(), lambda: w.event_generate("<<Paste>>")),
                  ("Select all", "A", True, lambda: w.tag_add("sel", "1.0", "end-1c"))]
        self._edit_menu(w, e.x_root, e.y_root, items=items, back_to=w)
        return "break"

    # ---- options and /spell -------------------------------------------------------------------------
    def _spell_option_changed(self, key):
        kind = key[len("spell_"):]
        if self.cfg.get(key):
            if self._spell_engine() is None:
                self.system("The Windows spell checker is not available here (it needs Windows 8 or later with a dictionary "
                            "for your language), so nothing will be underlined.")
            elif kind == "input" and not self.entry_lines():
                self.system("Spell checking in the input box needs the growing box: set Options > Entry box grows to (lines).")
        self.spell_refresh_all()

    def _spell_command(self, arg):
        bits = arg.split()
        sub = bits[0].lower() if bits else ""
        rest = bits[1:]
        sp = self._spell_engine()
        if sub in KINDS or sub in ("on", "off"):
            kinds = KINDS if sub in ("on", "off") else (sub,)
            value = (sub == "on") if sub in ("on", "off") else (rest[0].lower() != "off" if rest else not self.cfg.get("spell_" + sub))
            for k in kinds:
                self._set_extra("spell_" + k, value, ask=False)
            self.system("Spell checking: " + ", ".join("%s %s" % (KIND_NAMES[k], "on" if self.cfg.get("spell_" + k) else "off")
                                                       for k in kinds) + ".")
        elif sub == "add" and rest:
            self.system("Added to your dictionary." if self.spell_add_word(" ".join(rest)) else "That is not a word I can add.")
        elif sub in ("remove", "del") and rest:
            self.system("Removed." if self.spell_remove_word(" ".join(rest)) else "That is not in your dictionary.")
        elif sub == "words":
            w = clean_words(self.cfg.get("spell_words"))
            self.system("Your dictionary: " + (", ".join(w) if w else "empty") + ".")
        elif sub == "check":
            text = self.input.get() if hasattr(self.input, "get") else ""
            found = spelltext.find_problems(sp, text, self._spell_allowed("input"))
            lines = []
            for s, e, _k in found:
                word = text[s:e]
                sug = sp.suggest(word, 1) if sp else []
                lines.append("%s: %s" % (word, sug[0] if sug else "no suggestion"))
            self.system("\n".join(lines) if lines else "Nothing misspelled in the input box.")
        else:
            on = [k for k in KINDS if self.cfg.get("spell_" + k)]
            self.system("\n".join([
                "Spell checking uses the Windows spell checker%s." % ((" (%s)" % sp.language) if sp else ", which is not available here"),
                "On for: %s." % (", ".join(KIND_NAMES[k] for k in on) if on else "nothing (off by default)"),
                "/spell on|off, /spell input|notepad|custom [on|off], /spell add|remove <word>, /spell words, /spell check "
                "(the input box, read out)."]))
