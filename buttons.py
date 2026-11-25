"""Buttons: a bar of clickable buttons, each sending a few commands, optionally on a hotkey.

A button is a label, some commands (the same `;`-separated form an alias uses, run exactly as if you had typed them, so
aliases and /local commands work), an optional hotkey, and whether it belongs to every world or to one. The bar docks at the
top (under the world tabs) or the bottom (above the entry box), in both looks, and only shows buttons that apply to the world
on screen. Manage them from File > Buttons (Alt+B), or with /button.

Buttons are plain dicts, validated here: {"name", "body", "key", "enabled"} plus {"global": False, "world": name} for one tied
to a world (the same way triggers and aliases are)."""
import tkinter as tk
from tkinter import messagebox

import dosui
import extras
import triggers

MAX_BUTTONS = 48
MAX_LABEL = 24
MAX_BODY = triggers.MAX_ALIAS_BODY
DOCKS = ("top", "bottom", "off")


def validate_button(d):
    """A clean button dict, or None. Never raises. A hotkey that does not parse is dropped (the button stays)."""
    try:
        if not isinstance(d, dict):
            return None
        name = triggers._clean_text(d.get("name"), MAX_LABEL)
        body = triggers._clean_text(d.get("body"), MAX_BODY)
        if name is None or body is None:
            return None
        key = ""
        raw = d.get("key")
        if isinstance(raw, str) and raw.strip():
            try:
                key = extras.parse_hotkey(raw)[1]
            except ValueError:
                key = ""
        out = {"name": name, "body": body, "key": key, "enabled": triggers._bool(d.get("enabled", True), True)}
        out.update(triggers._world_part(d))
        return out
    except Exception:
        return None


def scope_key(b):
    return str(b.get("world", "")).strip().lower() if b.get("global", True) is False else ""


def clean_buttons(raw):
    """The settings list, checked: valid ones only, no two with the same label in the same scope, at most MAX_BUTTONS."""
    out, seen = [], set()
    if not isinstance(raw, list):
        return out
    for d in raw[:MAX_BUTTONS * 2]:
        b = validate_button(d)
        if b is None:
            continue
        k = (b["name"].lower(), scope_key(b))
        if k in seen:
            continue
        seen.add(k)
        out.append(b)
        if len(out) >= MAX_BUTTONS:
            break
    return out


class ButtonsMixin:
    # ---- what shows -------------------------------------------------------------------------------------------------
    def buttons_here(self, enabled_only=True):
        """The buttons that apply in the world on screen, in order."""
        rules = triggers.for_world(self.cfg.get("buttons", []), self._world_name(self._shown))
        return [b for b in rules if b["enabled"] or not enabled_only]

    def _build_buttonbar(self):
        self._btnbar = self._reg(tk.Frame(self.root), "panel")
        self._btn_inner = tk.Frame(self._btnbar)
        self._btn_inner.pack(fill="x", padx=6, pady=(3, 3))
        self._btn_widgets = []
        self._btn_sig = None
        self._button_bound = []
        self._btnbar.bind("<Configure>", lambda e: self._layout_buttons(), add="+")

    def _small_colors(self):
        if self.dos:
            c = self._dc()
            return dict(bg=c["dos_bar_bg"], fg=c["dos_bar_fg"], hot=c["dos_key_fg"], bar=c["dos_bar2_bg"])
        th = self.theme
        return dict(bg=th["button_bg"], fg=th["button_fg"], hot=th["select"], bar=th["panel"])

    def _place_buttonbar(self):
        bar = self._btnbar
        dock = self.cfg.get("button_dock", "top")
        try:
            if dock == "bottom":
                anchor = self.statbar if self.statbar.winfo_manager() else self._inbox
                bar.pack(fill="x", before=anchor)
            else:
                if self.dos:
                    anchor = getattr(self.dosbar, "top", None)
                else:
                    anchor = self._tabbar if self._tabbar.winfo_manager() else self._top
                if anchor is not None and anchor.winfo_manager():
                    bar.pack(fill="x", after=anchor)
                else:
                    bar.pack(fill="x")
        except tk.TclError:
            pass

    def _refresh_buttonbar(self, force=False):
        bar = getattr(self, "_btnbar", None)
        if bar is None:
            return
        try:
            dock = self.cfg.get("button_dock", "top")
            items = self.buttons_here() if dock != "off" else []
            self._bind_button_keys(items)
            if not items:
                if bar.winfo_manager():
                    bar.pack_forget()
                self._btn_sig = None
                return
            col = self._small_colors()
            f_plain, f_bold = self._small_fonts() if not self.dos else (self.f_norm, self.f_bold)
            sig = (tuple((b["name"], b["key"]) for b in items), dock, self.dos, col["bg"], col["bar"], col["fg"],
                   str(f_plain.cget("size")), f_plain.cget("family"))
            self._place_buttonbar()
            if sig == self._btn_sig and not force:
                return
            self._btn_sig = sig
            for w in self._btn_inner.winfo_children():
                w.destroy()
            self._btn_widgets = []
            bar.configure(bg=col["bar"])
            self._btn_inner.configure(bg=col["bar"])
            for b in items:
                text = b["name"] + ("  %s" % b["key"] if b["key"] else "")
                if self.dos:
                    w = tk.Label(self._btn_inner, text=" %s " % text, bg=col["bg"], fg=col["fg"], font=f_plain, cursor="hand2",
                                 padx=2, pady=0)
                    w.bind("<Button-1>", lambda e, b=b: self.run_button(b))
                else:
                    w = tk.Button(self._btn_inner, text=text, bg=col["bg"], fg=col["fg"], activebackground=col["hot"],
                                  activeforeground=col["fg"], relief="flat", bd=0, padx=12, pady=3, font=f_plain,
                                  takefocus=0, cursor="hand2", command=lambda b=b: self.run_button(b))
                w.grid(row=0, column=len(self._btn_widgets), padx=(0, 6), pady=2, sticky="w")
                self._btn_widgets.append(w)
            self.root.after_idle(self._layout_buttons)
        except tk.TclError:
            pass

    def _layout_buttons(self):
        """Wrap the buttons onto more rows when they do not fit the window's width."""
        try:
            width = self._btnbar.winfo_width() - 12
            if width < 60 or not self._btn_widgets:
                return
            x = row = col = 0
            for w in self._btn_widgets:
                bw = w.winfo_reqwidth() + 6
                if x + bw > width and col:
                    row, col, x = row + 1, 0, 0
                w.grid(row=row, column=col, padx=(0, 6), pady=2, sticky="w")
                col += 1
                x += bw
        except tk.TclError:
            pass

    # ---- running one ------------------------------------------------------------------------------------------------
    def run_button(self, b):
        """Send the button's commands as if typed (aliases and /commands included), without touching the history."""
        pieces = [p.strip() for p in triggers.split_commands(b["body"])][:triggers.MAX_COMMANDS]
        for p in pieces:
            if p:
                self._submit_line(p, False, remember=False)
        try:
            self.input.focus_set()
        except tk.TclError:
            pass
        return "break"

    # ---- hotkeys ----------------------------------------------------------------------------------------------------
    def _bind_button_keys(self, items):
        for w, seq in getattr(self, "_button_bound", []):
            try:
                w.unbind(seq)
            except tk.TclError:
                pass
        self._button_bound = []
        taken = {pair[0] for pair in extras.effective_keys(self.cfg.get("keys")).values()}
        for b in items:
            if not b["key"]:
                continue
            try:
                seq = extras.parse_hotkey(b["key"])[0]
            except ValueError:
                continue
            if seq in taken:
                continue
            taken.add(seq)
            variants = {seq}
            for s in list(variants):
                parts = s[1:-1].split("-")
                if len(parts[-1]) == 1 and parts[-1].isalpha():
                    variants.add("<%s>" % "-".join(parts[:-1] + [parts[-1].upper()]))
            for s in variants:
                for w in (self.root,) + self._inputs():
                    w.bind(s, lambda e, b=b: self.run_button(b))
                    self._button_bound.append((w, s))

    def button_key_problem(self, text, exclude=None):
        """(display, None) for a usable hotkey, ('', None) for none, or (None, why)."""
        text = (text or "").strip()
        if not text or text.lower() in ("none", "off", "-"):
            return "", None
        try:
            seq, shown = extras.parse_hotkey(text)
        except ValueError as e:
            return None, str(e)
        for action, (s, label) in extras.effective_keys(self.cfg.get("keys")).items():
            if s == seq:
                return None, "%s is used for %s." % (shown, extras.HOTKEYS[action][0])
        for i, other in enumerate(self.cfg.get("buttons", [])):
            if i != exclude and other.get("key") and extras.parse_hotkey(other["key"])[0] == seq \
                    and triggers.rule_applies(other, self._world_name(self._shown)):
                return None, "%s already runs the button '%s'." % (shown, other["name"])
        return shown, None

    # ---- changing the list ------------------------------------------------------------------------------------------
    def store_button(self, index, b):
        """(ok, message): add (index None) or replace button `index`."""
        lst = list(self.cfg.get("buttons", []))
        k = (b["name"].lower(), scope_key(b))
        for i, o in enumerate(lst):
            if i != index and (o["name"].lower(), scope_key(o)) == k:
                return False, "There is already a button called '%s' for that world." % b["name"]
        if index is None:
            if len(lst) >= MAX_BUTTONS:
                return False, "Too many buttons (%d at most)." % MAX_BUTTONS
            lst.append(b)
        else:
            lst[index] = b
        self.cfg["buttons"] = lst
        self._save_settings()
        self._refresh_buttonbar(True)
        return True, "Button '%s' saved." % b["name"]

    def delete_button(self, index):
        lst = list(self.cfg.get("buttons", []))
        if 0 <= index < len(lst):
            gone = lst.pop(index)
            self.cfg["buttons"] = lst
            self._save_settings()
            self._refresh_buttonbar(True)
            return gone
        return None

    def move_button(self, index, delta):
        lst = list(self.cfg.get("buttons", []))
        j = index + delta
        if 0 <= index < len(lst) and 0 <= j < len(lst):
            lst[index], lst[j] = lst[j], lst[index]
            self.cfg["buttons"] = lst
            self._save_settings()
            self._refresh_buttonbar(True)
            return j
        return index

    def clone_button(self, index):
        """Copy a button right after the original under a new label. The hotkey is not copied (two buttons cannot
        share one); give the copy its own. Returns (ok, message, index of the copy)."""
        lst = list(self.cfg.get("buttons", []))
        if not 0 <= (index if index is not None else -1) < len(lst):
            return False, "Nothing is selected to clone.", index
        if len(lst) >= MAX_BUTTONS:
            return False, "Too many buttons (%d at most)." % MAX_BUTTONS, index
        src = lst[index]
        same_scope = [o["name"] for o in lst if scope_key(o) == scope_key(src)]
        new = dict(src, name=triggers.copy_name(src["name"], same_scope, MAX_LABEL), key="")
        b = validate_button(new)
        if b is None:
            return False, "That label cannot be used for a copy. Edit the original's label first.", index
        lst.insert(index + 1, b)
        self.cfg["buttons"] = lst
        self._save_settings()
        self._refresh_buttonbar(True)
        return True, "Cloned as '%s'%s." % (b["name"], " (no hotkey: give it one if you want)" if src["key"] else ""), index + 1

    def toggle_button(self, index):
        lst = list(self.cfg.get("buttons", []))
        if 0 <= index < len(lst):
            lst[index] = dict(lst[index], enabled=not lst[index]["enabled"])
            self.cfg["buttons"] = lst
            self._save_settings()
            self._refresh_buttonbar(True)

    def make_button(self, index, name, body, key, enabled, all_worlds):
        """(button | None, message): check what a form or command gave, including the hotkey."""
        shown, why = self.button_key_problem(key, exclude=index)
        if why:
            return None, why
        d = {"name": name, "body": body, "key": shown or "", "enabled": enabled}
        if not all_worlds:
            d.update({"global": False, "world": self._world_name(self._shown)})
        b = validate_button(d)
        if b is None:
            return None, "Give the button a label (up to %d characters) and the commands it sends." % MAX_LABEL
        return b, ""

    def _find_button(self, name):
        want = " ".join((name or "").split()).lower()
        here = triggers.for_world(self.cfg.get("buttons", []), self._world_name(self._shown))
        for b in here:
            if b["name"].lower() == want:
                return self.cfg["buttons"].index(b), b
        return None, None

    # ---- /button -----------------------------------------------------------------------------------------------------
    def _buttons_command(self, cmd, arg):
        """/button  /button add Label = commands  /button key Label Ctrl-F5  /button del|run Label  /button list  /button dock top|bottom|off"""
        if cmd not in ("button", "buttons"):
            return False
        word, _, rest = arg.partition(" ")
        word, rest = word.lower(), rest.strip()
        if not word:
            self.open_buttons()
        elif word == "list":
            here = self.buttons_here(False)
            self.system("\n".join("%s%s%s = %s" % (b["name"], " (off)" if not b["enabled"] else "",
                                                  " [%s]" % b["key"] if b["key"] else "", b["body"]) for b in here)
                        if here else "No buttons for this world. /button add Label = commands")
        elif word == "add":
            name, eq, body = rest.partition("=")
            b, why = self.make_button(None, name.strip(), body.strip(), "", True, True) if eq else (None, "")
            if b is None:
                self.system(why or "Usage: /button add Label = commands   (; between commands)")
            else:
                self.system(self.store_button(None, b)[1])
        elif word in ("del", "delete", "remove", "run", "on", "off"):
            i, b = self._find_button(rest)
            if b is None:
                self.system("No button called '%s' here. /button list shows them." % rest)
            elif word == "run":
                self.run_button(b)
            elif word in ("on", "off"):
                self.cfg["buttons"][i] = dict(b, enabled=(word == "on"))
                self._save_settings()
                self._refresh_buttonbar(True)
                self.system("Button '%s' is %s." % (b["name"], word))
            else:
                self.delete_button(i)
                self.system("Removed the button '%s'." % b["name"])
        elif word == "key":
            name, _, key = rest.rpartition(" ")
            i, b = self._find_button(name)
            if b is None:
                self.system("Usage: /button key Label Ctrl-F5   (or 'none' to clear it)")
            else:
                shown, why = self.button_key_problem(key, exclude=i)
                if why:
                    self.system(why)
                else:
                    self.cfg["buttons"][i] = dict(b, key=shown)
                    self._save_settings()
                    self._refresh_buttonbar(True)
                    self.system("'%s' now runs on %s." % (b["name"], shown) if shown else "'%s' has no hotkey." % b["name"])
        elif word == "dock":
            if rest.lower() in DOCKS:
                self._set_extra("button_dock", rest.lower())
                self.system("The button bar is %s." % ("hidden" if rest.lower() == "off" else "at the " + rest.lower()))
            else:
                self.system("Usage: /button dock top|bottom|off")
        else:
            self.system("Usage: /button [list | add Label = commands | key Label Ctrl-F5 | run|del|on|off Label | dock top|bottom|off]")
        return True

    # ---- the manager (normal look) ----------------------------------------------------------------------------------
    def open_buttons(self):
        if self.dos:
            return self.dos_buttons()
        win = getattr(self, "_buttons_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    return win
            except tk.TclError:
                pass
        top = self._buttons_win = tk.Toplevel(self.root)
        top.title("Buttons")
        top.transient(self.root)
        tk.Label(top, anchor="w", justify="left",
                 text="Buttons sit in a bar and send their commands when clicked or when their hotkey is pressed.").pack(
            anchor="w", padx=10, pady=(8, 0))
        box = tk.Frame(top)
        box.pack(fill="both", expand=True, padx=10, pady=4)
        lb = tk.Listbox(box, height=12, width=78, exportselection=False, font=self.f_norm, highlightthickness=0, activestyle="none")
        sb = tk.Scrollbar(box, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def refresh(select=None):
            lb.delete(0, "end")
            for b in self.cfg.get("buttons", []):
                scope = "this world: " + b["world"] if b.get("global", True) is False else "all worlds"
                lb.insert("end", "%-3s %-20s %-12s %-26s %s" % ("on" if b["enabled"] else "off", b["name"][:20], b["key"],
                                                                scope[:26], b["body"]))
            if self.cfg.get("buttons"):
                i = max(0, min(len(self.cfg["buttons"]) - 1, select or 0))
                lb.selection_set(i)
                lb.see(i)

        def current():
            sel = lb.curselection()
            return sel[0] if sel else None

        def edit(_e=None):
            i = current()
            if i is not None:
                self._button_form(top, i, refresh)

        def remove():
            i = current()
            if i is not None and messagebox.askyesno("Remove", "Remove the button '%s'?" % self.cfg["buttons"][i]["name"], parent=top):
                self.delete_button(i)
                refresh(max(0, i - 1))

        def move(d):
            i = current()
            if i is not None:
                refresh(self.move_button(i, d))

        def toggle():
            i = current()
            if i is not None:
                self.toggle_button(i)
                refresh(i)

        def clone(_e=None):
            i = current()
            if i is None:
                return "break"
            ok, msg, j = self.clone_button(i)
            if not ok:
                messagebox.showinfo("Clone", msg, parent=top)
            else:
                self.system(msg)
            refresh(j)
            return "break"
        row = tk.Frame(top)
        row.pack(fill="x", padx=10, pady=(0, 10))
        for label, fn in (("Add", lambda: self._button_form(top, None, refresh)), ("Edit", edit), ("On/off", toggle),
                          ("Clone", clone), ("Remove", remove), ("Up", lambda: move(-1)), ("Down", lambda: move(+1))):
            tk.Button(row, text=label, width=8, command=fn).pack(side="left", padx=(0, 4))
        tk.Button(row, text="Close", width=8, command=top.destroy).pack(side="right")
        lb.bind("<Double-1>", edit)
        lb.bind("<Control-d>", clone)
        top.bind("<Escape>", lambda e: top.destroy())
        top.protocol("WM_DELETE_WINDOW", top.destroy)
        refresh()
        top._list = lb
        top._refresh = refresh
        top._clone = clone
        self._theme_tree(top)
        return top

    def _button_form(self, parent, index, refresh):
        ex = self.cfg["buttons"][index] if index is not None else None
        win = tk.Toplevel(parent)
        win.title("Edit button" if ex else "Add button")
        win.transient(parent)
        sv = {"name": tk.StringVar(value=ex["name"] if ex else ""), "body": tk.StringVar(value=ex["body"] if ex else ""),
              "key": tk.StringVar(value=ex["key"] if ex else "")}
        en = tk.BooleanVar(value=ex["enabled"] if ex else True)
        allw = tk.BooleanVar(value=(ex or {}).get("global", True) is not False)
        for r, (label, key, width) in enumerate((("Label", "name", 24), ("Sends", "body", 60), ("Hotkey", "key", 16))):
            tk.Label(win, text=label).grid(row=r, column=0, sticky="w", padx=(10, 6), pady=4)
            tk.Entry(win, textvariable=sv[key], width=width).grid(row=r, column=1, sticky="w", padx=(0, 10), pady=4)
        tk.Label(win, anchor="w", justify="left",
                 text="Sends: commands separated by ; (aliases and /commands work).  Hotkey: Ctrl-F5, Alt-S, F9 ... (empty for none).").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=10)
        tk.Checkbutton(win, text="Enabled", variable=en).grid(row=4, column=1, sticky="w")
        tk.Checkbutton(win, text="In every world (untick: only in %s)" % self._world_name(self._shown), variable=allw).grid(
            row=5, column=1, sticky="w")
        msg = tk.Label(win, text="", anchor="w", fg="#c04040")
        msg.grid(row=6, column=0, columnspan=2, sticky="w", padx=10)

        def ok(_e=None):
            b, why = self.make_button(index, sv["name"].get(), sv["body"].get(), sv["key"].get(), bool(en.get()), bool(allw.get()))
            if b is None:
                msg.configure(text=why)
                return
            good, text = self.store_button(index, b)
            if not good:
                msg.configure(text=text)
                return
            win.destroy()
            refresh(len(self.cfg["buttons"]) - 1 if index is None else index)
        row = tk.Frame(win)
        row.grid(row=7, column=0, columnspan=2, sticky="e", padx=10, pady=10)
        tk.Button(row, text="OK", width=8, command=ok).pack(side="right")
        tk.Button(row, text="Cancel", width=8, command=win.destroy).pack(side="right", padx=6)
        win.bind("<Return>", ok)
        win.bind("<Escape>", lambda e: win.destroy())
        win._vars = (sv, en, allw)
        win._ok = ok
        win._msg = msg
        self._theme_tree(win)
        return win

    # ---- the manager (DOS look) -------------------------------------------------------------------------------------
    def dos_buttons(self, selected=0):
        cols = [{"title": "On", "width": 3}, {"title": "Label", "width": 16}, {"title": "Key", "width": 10},
                {"title": "Where", "width": 10}, {"title": "Sends", "width": 0}]
        hints = [("Enter", "Edit"), ("A", "Add"), ("C", "Clone"), ("Space", "On/Off"), ("U/D", "Move"), ("Del", "Remove"), ("Esc", "Close")]

        def rows():
            return [{"cells": ["yes" if b["enabled"] else "", b["name"], b["key"],
                               b["world"][:10] if b.get("global", True) is False else "all", b["body"]],
                     "role": "normal" if b["enabled"] else "dim"} for b in self.cfg.get("buttons", [])]

        def act(name, idx, table):
            if name in ("select", "edit") and idx is not None:
                table.close()
                self._dos_button_form(idx, None)
            elif name == "add":
                table.close()
                self._dos_button_form(None, None)
            elif name == "toggle" and idx is not None:
                self.toggle_button(idx)
                table.set_rows(rows(), selected=idx)
            elif name == "clone" and idx is not None:
                _ok, msg, j = self.clone_button(idx)
                self.system(msg)
                table.set_rows(rows(), selected=j)
            elif name in ("up", "down") and idx is not None:
                j = self.move_button(idx, -1 if name == "up" else 1)
                table.set_rows(rows(), selected=j)
            elif name == "remove" and idx is not None:
                table.close()
                victim = self.cfg["buttons"][idx]["name"]
                self._overlay = dosui.confirm(
                    self.root, "Remove", "Remove '%s'?" % victim, self._dc(), self.f_norm,
                    lambda r, v: (self.delete_button(idx), self._reopen(self.dos_buttons, max(0, idx - 1)))
                    if r == "yes" else self._reopen(self.dos_buttons, idx))
        keys = {"Return": "select", "KP_Enter": "select", "Escape": "close", "a": "add", "Insert": "add", "e": "edit",
                "Delete": "remove", "r": "remove", "space": "toggle", "u": "up", "d": "down", "c": "clone"}
        table = dosui.DosTable(self.root, "Buttons", cols, rows(), self._dc(), self.f_norm, act, keys=keys, hints=hints,
                               min_width=70, selected=selected)
        self._overlay = table
        table.open()
        return table

    def _dos_button_form(self, index, values):
        if values is None:
            ex = self.cfg["buttons"][index] if index is not None else None
            values = {"name": ex["name"] if ex else "", "body": ex["body"] if ex else "", "key": ex["key"] if ex else "",
                      "enabled": ex["enabled"] if ex else True, "all": (ex or {}).get("global", True) is not False}
        fields = [{"key": "name", "label": "Label", "type": "text", "value": values["name"], "width": 24},
                  {"key": "body", "label": "Sends", "type": "text", "value": values["body"], "width": 46},
                  {"key": "key", "label": "Hotkey", "type": "text", "value": values["key"], "width": 16},
                  {"key": "enabled", "label": "Enabled", "type": "check", "value": bool(values["enabled"])},
                  {"key": "all", "label": "In every world", "type": "check", "value": bool(values["all"])}]

        def result(res, vals):
            values.update(vals)
            if res == "cancel":
                self._reopen(self.dos_buttons, index or 0)
                return
            b, why = self.make_button(index, values["name"], values["body"], values["key"], bool(values["enabled"]),
                                      bool(values["all"]))
            if b is not None:
                good, why = self.store_button(index, b)
                if good:
                    self._reopen(self.dos_buttons, len(self.cfg["buttons"]) - 1 if index is None else index)
                    return
            self.system(why)
            self._reopen(lambda: self._dos_button_form(index, values))
        return self._dos_dialog("Button", fields, [("Save", "save"), ("Cancel", "cancel")], result, width=66,
                                message="Sends: commands separated by ;   Hotkey: Ctrl-F5, Alt-S, F9 (empty: none)")
