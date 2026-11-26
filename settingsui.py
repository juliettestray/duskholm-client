"""The Options menu and the Settings window (normal look; the DOS look keeps its own Options menu).

The Options menu is short: the options you changed most recently (so the ones you flip often stay a click away),
then Settings... The Settings window lists every option by topic, with a find box. A menu entry and a window control for
the same option share one variable, so each shows what the other changed. What the options are comes from the App
(_option_defs); this file only lays them out."""
import tkinter as tk

PAGES = [
    ("Connection", ("verify", "keepalive", "auto_reconnect", "update_check")),
    ("Display and text", ("links", "link_images", "emoji", "emoji_pics", "emoji_pics_dos", "connect_boxes", "hide_prompt",
                          "walk_preview", "clock", "timestamps", "world_tabs", "button_dock", "crt_lines")),
    ("Input and sending", ("entry_grow", "keep_box", "scroll_on_send", "show_echo", "custom_form")),
    ("Spell checking", ("spell_input", "spell_notepad", "spell_custom")),
    ("Sound", ("bell", "bell_new")),
    ("Logging and scrollback", ("log_echo", "scrollback_lines", "keep_backscroll", "keep_lines")),
    ("Game data (GMCP)", ("gmcp", "gmcp_layout")),
    ("Screen reader", ("screen_reader", "sr_alerts", "gmcp_sr", "sr_voice", "@sr_interval", "@sr_combat")),
]
OTHER = "Other"
RECENT_SHOWN = 5             # entries under "Recently changed"
RECENT_KEPT = 12             # remembered (some may be options a later version removed)
SR_INTERVALS = ((0, "off"), (10, "every 10 seconds"), (15, "every 15 seconds"), (30, "every 30 seconds"),
                (60, "every minute"), (120, "every 2 minutes"), (300, "every 5 minutes"))
MAX_RADIO = 4               # a choice with more values than this is a drop-down list
BUILTIN_BOOLS = {"verify": "v_verify", "bell": "v_bell", "keepalive": "v_keep", "auto_reconnect": "v_auto",
                 "hide_prompt": "v_hideprompt"}


def clean_recent(lst):
    """The 'recently changed' list as stored: short strings, no duplicates, newest first, bounded."""
    out = []
    for k in lst if isinstance(lst, (list, tuple)) else []:
        if isinstance(k, str) and 0 < len(k) <= 30 and k not in out:
            out.append(k)
        if len(out) >= RECENT_KEPT:
            break
    return out


def pages_for(defs):
    """[(page name, [keys])] for the window: the fixed topics, then an 'Other' page for any option not placed."""
    placed, out = set(), []
    for name, keys in PAGES:
        ks = [k for k in keys if k in defs]
        placed.update(ks)
        if ks:
            out.append((name, ks))
    rest = [k for k in defs if k not in placed]
    if rest:
        out.append((OTHER, rest))
    return out


def matches(defs, key, query):
    """True when every word typed in the find box is in the option's label or its topic."""
    words = query.lower().split()
    if not words:
        return False
    page = next((n for n, ks in PAGES if key in ks), OTHER)
    hay = ("%s %s %s" % (defs[key]["label"], defs[key].get("short", ""), page)).lower()
    return all(w in hay for w in words)


class SettingsMixin:
    # ---- shared variables ----------------------------------------------------------------------------
    def _option_vars_init(self):
        """One variable per option, made once: the menu entries and the window controls all use it."""
        for key, name in BUILTIN_BOOLS.items():
            setattr(self, name, tk.BooleanVar(value=bool(self.cfg[key])))
        for key, d in self._option_defs().items():
            if d["kind"] == "bool" and key not in BUILTIN_BOOLS:
                self._xvars[key] = tk.BooleanVar(value=bool(self.cfg[key]))
            elif d["kind"] == "choice":
                self._xvars[key] = tk.StringVar(value=self.cfg[key])
        cur = self.cfg.get("sr_interval", 0)
        self._sr_interval_var = tk.IntVar(value=cur if cur in dict(SR_INTERVALS) else -1)

    def option_var(self, key):
        if key in BUILTIN_BOOLS:
            return getattr(self, BUILTIN_BOOLS[key])
        if key == "@sr_interval":
            return self._sr_interval_var
        return self._xvars[key]

    def option_set(self, key, value):
        """Change an option from the menu or the window (the same thing the menu's own check marks did)."""
        if key == "@sr_interval":
            self.set_sr_interval(value)
        elif key in BUILTIN_BOOLS:
            old = self.cfg[key]
            self.cfg[key] = bool(value)
            self.option_var(key).set(bool(value))
            if key == "auto_reconnect":
                self._auto_toggled()
            self._save_settings()
            if old != bool(value):
                self._opt_touch(key)
        else:
            self._set_extra(key, value)

    def _opt_touch(self, key):
        """Remember that this option was just changed (it goes to the top of 'Recently changed')."""
        self.cfg["opt_recent"] = clean_recent([key] + [k for k in self.cfg.get("opt_recent", []) if k != key])

    # ---- the Options menu -------------------------------------------------------------------------------
    def _build_options_menu(self, parent):
        o = tk.Menu(parent, tearoff=0, postcommand=self._fill_options_menu)
        self._options_menu = o
        self._opt_subs = {}
        defs = self._option_defs()
        for key, d in defs.items():                         # one sub-menu per choice, made once and reused
            if d["kind"] in ("choice", "interval"):
                sub = tk.Menu(o, tearoff=0)
                var = self.option_var(key)
                for value, word in self._choice_items(key, d):
                    sub.add_radiobutton(label=word, value=value, variable=var,
                                        command=lambda k=key, v=var: self.option_set(k, v.get()))
                self._opt_subs[key] = sub
        self._extra_menus += list(self._opt_subs.values())
        self._fill_options_menu()
        return o

    def _choice_items(self, key, d):
        if d["kind"] == "interval":
            return list(SR_INTERVALS)
        return [(v, d["words"].get(v, v)) for v in d["values"]]

    def _fill_options_menu(self):
        o, defs = self._options_menu, self._option_defs()
        o.delete(0, "end")
        recent = [k for k in self.cfg.get("opt_recent", []) if k in defs and defs[k]["kind"] != "button"][:RECENT_SHOWN]
        if recent:
            o.add_command(label="Recently changed", state="disabled")
            for key in recent:
                d, var = defs[key], self.option_var(key)
                if d["kind"] == "bool":
                    o.add_checkbutton(label=d["label"], variable=var, command=lambda k=key, v=var: self.option_set(k, v.get()))
                else:
                    o.add_cascade(label=d["short"] or d["label"], menu=self._opt_subs[key])
            o.add_separator()
        o.add_command(label="Settings...   Ctrl+Shift+O", command=self.open_settings)

    # ---- the Settings window ---------------------------------------------------------------------------
    def open_settings(self, page=None):
        if self.dos:
            self.dos_options_menu()
            return
        win = getattr(self, "_settings_win", None)
        try:
            if win and win["top"].winfo_exists():
                win["top"].deiconify()
                win["top"].lift()
                if page:
                    win["select"](page)
                win["search"].focus_set()
                return
        except tk.TclError:
            pass
        defs = self._option_defs()
        pages = pages_for(defs)
        top = tk.Toplevel(self.root)
        top.title("Settings")
        top.transient(self.root)
        top.geometry("860x580")
        top.minsize(640, 420)
        state = {"top": top, "traces": [], "page": pages[0][0]}
        self._settings_win = state

        head = tk.Frame(top)
        head.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(head, text="Find a setting:").pack(side="left")
        find = tk.StringVar()
        search = tk.Entry(head, textvariable=find, width=34)
        search.pack(side="left", padx=6)
        state["search"] = search
        body = tk.Frame(top)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        lb = tk.Listbox(body, exportselection=False, activestyle="dotbox", width=24, height=len(pages))
        lb.pack(side="left", fill="y")
        for name, _ks in pages:
            lb.insert("end", name)
        pane = tk.Frame(body)
        pane.pack(side="left", fill="both", expand=True, padx=(14, 0))

        def clear():
            for w in pane.winfo_children():
                w.destroy()
            for var, tid in state["traces"]:
                try:
                    var.trace_remove("write", tid)
                except (tk.TclError, ValueError):
                    pass
            state["traces"] = []

        def fill(title, keys):
            clear()
            tk.Label(pane, text=title, font=self.f_bold, anchor="w").pack(fill="x", pady=(0, 8))
            for key in keys:
                self._settings_row(pane, key, defs[key], state)
            if not keys:
                tk.Label(pane, text="No setting matches that.", anchor="w").pack(fill="x")
            self._theme_tree(pane)

        def select(name):
            keys = dict(pages).get(name)
            if keys is None:
                return
            state["page"] = name
            if find.get():
                state["quiet"] = True
                find.set("")
                state["quiet"] = False
            lb.selection_clear(0, "end")
            lb.selection_set([n for n, _k in pages].index(name))
            fill(name, keys)

        def on_pick(_e=None):
            sel = lb.curselection()
            if sel:
                select(pages[sel[0]][0])

        def on_find(*_a):
            if state.get("quiet"):
                return
            q = find.get().strip()
            if not q:
                select(state["page"])
                return
            lb.selection_clear(0, "end")
            fill("Settings matching \"%s\"" % q[:30], [k for k in defs if matches(defs, k, q)])

        state["select"] = select
        lb.bind("<<ListboxSelect>>", on_pick)
        find.trace_add("write", on_find)

        def close(_e=None):
            clear()
            self._settings_win = None
            top.destroy()
            self.root.after_idle(self.input.focus_set)
        top.protocol("WM_DELETE_WINDOW", close)
        top.bind("<Escape>", close)
        self._theme_tree(top)
        select(page if page in dict(pages) else pages[0][0])
        lb.focus_set()

    def _settings_row(self, parent, key, d, state):
        """One option as a control in the Settings window, bound to the option's shared variable."""
        kind = d["kind"]
        if kind == "button":
            tk.Button(parent, text=d["label"], command=d["action"]).pack(anchor="w", pady=4)
            return
        var = self.option_var(key)
        if kind == "bool":
            tk.Checkbutton(parent, text=d["label"], variable=var, anchor="w", justify="left",
                           command=lambda k=key, v=var: self.option_set(k, v.get())).pack(fill="x", pady=2)
            return
        row = tk.Frame(parent)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=(d["short"] or d["label"]) + ":", anchor="w").pack(side="left", padx=(0, 10))
        items = self._choice_items(key, d)
        if len(items) <= MAX_RADIO and kind == "choice":
            for value, word in items:
                tk.Radiobutton(row, text=word, value=value, variable=var,
                               command=lambda k=key, v=var: self.option_set(k, v.get())).pack(side="left", padx=(0, 8))
            return
        words = dict(items)
        rev = {w: v for v, w in items}
        disp = tk.StringVar(value=words.get(var.get(), "custom"))
        om = tk.OptionMenu(row, disp, *[w for _v, w in items], command=lambda w, k=key: self.option_set(k, rev[w]))
        om.configure(anchor="w")
        om.pack(side="left")
        tid = var.trace_add("write", lambda *_a: disp.set(words.get(var.get(), "custom")))
        state["traces"].append((var, tid))
