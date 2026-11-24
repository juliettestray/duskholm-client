"""DOS-look forms that let you *pick* instead of type (mixed into the App).

The DOS look is the main look of Sanctuary, so these screens are designed for it first: where the
valid answers are known (a list of body parts, a kind of item, a gradient pattern) Enter on the line
opens the list; where the answer is a paragraph Enter opens a text page like the game's own editor."""
import re
import time

import colortools as ct
import custom
import dosgrad
import dosui

MODE_SHORT = {"cli": "Command line", "interface": "Game item editor"}
NONE_TEXT = "(leave alone)"


class DosFormsMixin:
    def _forms_init(self):
        self._cust_mode = "cli"
        self._iface = None                   # a game item editor session being captured (see below)
        self._iface_job = None

    # ---- generic helpers -----------------------------------------------------------------
    def _unless_chosen(self, flag, fn):
        """A DosMenu closes (and so runs `back`) before it runs the chosen item's action. This waits a
        beat and only goes back if no item was chosen (Esc)."""
        def later():
            if not flag[0] and fn is not None:
                fn()
        return lambda: self.root.after_idle(later)

    def dos_choose(self, title, options, current, on_pick, back=None):
        """A list to pick from. options: [(label, value)] or [(label, value, swatch)]. on_pick(value)
        runs once the list has closed; Esc leaves things as they were (and runs `back`)."""
        items, initial, chosen = [], 0, [False]
        for n, o in enumerate(options):
            label, value = o[0], o[1]
            if value == current:
                initial = n

            def act(v=value):
                chosen[0] = True
                on_pick(v)
            it = {"label": label, "checked": value == current, "action": act}
            if len(o) > 2 and o[2]:
                it["swatch"] = o[2]
            items.append(it)
        return self._dos_menu(title, items, initial=initial, back=self._unless_chosen(chosen, back))

    def dos_multi_choose(self, title, options, selected, on_done, initial=0):
        """Tick several: Enter flips an entry and the list comes back where it was; the last entry (or
        Esc) finishes. on_done(list of values)."""
        sel = list(selected)
        items, chosen = [], [False]
        for n, (label, value) in enumerate(options):
            def flip(v=value, n=n):
                chosen[0] = True
                new = [x for x in sel if x != v] if v in sel else sel + [v]
                self._reopen(self.dos_multi_choose, title, options, new, on_done, n)
            items.append({"label": label, "checked": value in sel, "action": flip})
        items.append(None)

        def finish():
            chosen[0] = True
            on_done(list(sel))
        items.append({"label": "Done", "hotkey": "D", "action": finish})
        return self._dos_menu(title, items, initial=initial,
                              back=self._unless_chosen(chosen, lambda: on_done(list(sel))))

    def dos_edit_text(self, title, text, on_done):
        """A page for paragraphs. on_done(text) when kept (Ctrl-S), on_done(None) when cancelled (Esc).
        Ctrl-G colours the selected text (or all of it) with a gradient; Ctrl-K takes the colours off."""
        if self._overlay_open():
            return None

        def asked(res):
            if not isinstance(res, tuple):
                on_done(res)
                return
            what, cur, rng = res
            if what == "strip":
                self._reopen(self.dos_edit_text, title, ct.strip_colour(cur, rng), on_done)
            else:
                st = {k: self._grad_state[k] for k in ("pattern", "mode", "smooth")}
                self._reopen(self._dos_text_gradient, st, title, cur, rng, on_done)
        ed = dosui.DosTextEditor(self._holder, title, text, self._dc(), self.f_norm, asked)
        self._overlay = ed
        ed.open()
        return ed

    # ---- gradients -----------------------------------------------------------------------
    def _grad_stops(self, st):
        """The colours of the pattern in `st` (a name, or the colours typed out)."""
        try:
            return list(self._pattern_colours(st["pattern"])) or [196, 226]
        except ValueError:
            return [196, 226]

    def _grad_label(self, st, stops):
        """What the Pattern field shows: its name while the colours are still that pattern's, else 'custom'."""
        named = ct.find_pattern(st["pattern"], self.cfg.get("gradients", []))
        return st["pattern"] if named is not None and list(named) == list(stops) else "custom"

    @staticmethod
    def _grad_from_editor(st, es):
        """The gradient state after the editor: keeps a pattern's name, otherwise the colours as typed text."""
        pat = es["pattern"] if es["pattern"] != "custom" else ct.stops_text(es["stops"])
        return dict(st, pattern=pat, mode=es["mode"], smooth=es["smooth"], text=es.get("text", st.get("text", "")),
                    prefix=es.get("prefix", st.get("prefix", "")))

    def _grad_mode_list(self, new, again):
        self._reopen(lambda: self.dos_choose(
            "Apply", [("%-8s %s" % (m, ct.MODE_HELP[m]), m) for m in ct.MODES], new["mode"],
            lambda m: self._reopen(again, dict(new, mode=m)), back=lambda: again(new)))

    def _dos_save_pattern(self, st, back):
        """Ask for a name and keep the colours as a pattern."""
        stops = self._grad_stops(st)

        def result(res, v):
            if res != "ok":
                self._reopen(back, st)
                return
            ok, msg = self.save_pattern(v.get("name", ""), ct.stops_text(stops))
            self.system(msg)
            if ok:
                self._reopen(back, dict(st, pattern=" ".join(v["name"].split())[:30]))
            else:
                self._reopen(self._dos_save_pattern, st, back)
        self._dos_dialog("Save pattern", [{"key": "name", "label": "Name", "type": "text", "value": "", "width": 28}],
                         [("Save", "ok"), ("Cancel", "cancel")], result, width=52,
                         message="Keeps these %d colours under a name you can pick again." % len(stops))

    def _dos_gradient(self, st):
        st = dict(st)
        self._grad_state = st
        stops = self._grad_stops(st)
        state = {"stops": stops, "mode": st["mode"], "smooth": st["smooth"], "text": st["text"],
                 "prefix": st["prefix"], "pattern": self._grad_label(st, stops)}

        def result(res, es):
            new = self._grad_from_editor(st, es)
            self._grad_state = new
            if isinstance(res, tuple):
                if res[1] == "pattern":
                    self._reopen(self._dos_pick_pattern, new)
                else:
                    self._grad_mode_list(new, self.open_gradient)
                return
            if res == "cancel":
                return
            if res == "reverse":
                self._reopen(self.open_gradient, dict(new, pattern=ct.stops_text(es["stops"][::-1])))
                return
            if res == "save":
                self._reopen(self._dos_save_pattern, new, self.open_gradient)
                return
            if res == "share":
                try:
                    cols = self._pattern_colours(new["pattern"])
                    name = new["pattern"] if ct.find_pattern(new["pattern"], self.cfg.get("gradients", [])) else "Pattern"
                    line = ct.share_string(name, cols)
                except ValueError as e:
                    self.system(str(e))
                else:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(line)
                    self.system("Copied to the clipboard: " + line)
                self._reopen(self.open_gradient, new)
                return
            coded, why = self.make_gradient(new)
            if coded is None:
                self.system(why)
                self._reopen(self.open_gradient, new)
                return
            if res == "preview":
                self.show_coloured(coded)
                self._reopen(self.open_gradient, new)
            elif res == "send":
                if "\n" in coded:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(coded)
                    self.system("Several lines: copied to the clipboard.")
                else:
                    self.put_in_input(coded)
        ed = dosgrad.DosGradientEditor(
            self.root, "Gradient", state,
            [("Preview", "preview"), ("To input", "send"), ("Reverse", "reverse", "v"), ("Save", "save"),
             ("Share", "share", "h"), ("Cancel", "cancel")],
            self._dc(), self.f_norm, result, text=True,
            message="Use \\n for new lines in the text.")
        self._overlay = ed
        ed.open()
        return ed

    def _dos_text_gradient(self, st, title, cur, rng, on_done, note=None):
        """Pick colours and how to apply them, then go back to the editor with the text coloured."""
        st = dict(st)
        self._grad_state = dict(self._grad_state, **{k: st[k] for k in ("pattern", "mode", "smooth")})
        stops = self._grad_stops(st)
        state = {"stops": stops, "mode": st["mode"], "smooth": st["smooth"], "pattern": self._grad_label(st, stops)}
        again = lambda s: self._dos_text_gradient(s, title, cur, rng, on_done)
        what = "the selected text" if rng else "all of the text"

        def result(res, es):
            new = self._grad_from_editor(st, es)
            if isinstance(res, tuple):
                if res[1] == "pattern":
                    self._reopen(self._dos_pick_pattern, new, again)
                else:
                    self._grad_mode_list(new, again)
                return
            if res == "apply":
                try:
                    out = ct.colour_text(cur, self._pattern_colours(new["pattern"]), new["mode"], new["smooth"], rng)
                except ValueError as e:
                    self._reopen(self._dos_text_gradient, new, title, cur, rng, on_done, str(e))
                    return
                self._grad_state = dict(self._grad_state, **{k: new[k] for k in ("pattern", "mode", "smooth")})
                self._reopen(self.dos_edit_text, title, out, on_done)
            else:
                self._reopen(self.dos_edit_text, title, cur, on_done)
        ed = dosgrad.DosGradientEditor(
            self.root, "Colour the text", state, [("Apply", "apply"), ("Cancel", "cancel")],
            self._dc(), self.f_norm, result, text=False,
            message=note or "This colours %s. Colours already in it are replaced." % what)
        self._overlay = ed
        ed.open()
        return ed

    def _dos_pick_pattern(self, st, cont=None):
        cont = cont or self.open_gradient
        saved = self.cfg.get("gradients", [])
        options = []
        for name in ct.all_pattern_names(saved):
            cols = ct.find_pattern(name, saved)
            options.append((name, name, ct.XTERM[cols[len(cols) // 2]] if cols else None))
        options.append(("Create new...", "\x00new"))
        options.append(("Import a shared one...", "\x00import"))
        if saved:
            options.append(("Delete one of mine...", "\x00del"))
        again = lambda: cont(st)

        def picked(v):
            if v == "\x00new":
                self._reopen(self._dos_new_pattern, st, None, "", "", cont)
            elif v == "\x00import":
                self._reopen(self._dos_import_pattern, st, None, cont)
            elif v == "\x00del":
                self._reopen(lambda: self.dos_choose(
                    "Delete which?", [(s["name"], s["name"]) for s in saved], "",
                    lambda n: (self.delete_pattern(n), self.system("Deleted '%s'." % n), self._reopen(cont, st)),
                    back=again))
            else:
                self._reopen(cont, dict(st, pattern=v))
        self.dos_choose("Pattern", options, st["pattern"], picked, back=again)

    def _dos_new_pattern(self, st, note=None, name="", cols="", cont=None):
        cont = cont or self.open_gradient
        fields = [{"key": "name", "label": "Name", "type": "text", "value": name, "width": 28},
                  {"key": "cols", "label": "Colours", "type": "text", "value": cols, "width": 46}]

        def result(res, v):
            if res != "ok":
                self._reopen(cont, st)
                return
            ok, msg = self.save_pattern(v.get("name", ""), v.get("cols", ""))
            self.system(msg)
            if ok:
                self._reopen(cont, dict(st, pattern=" ".join(v["name"].split())[:30]))
            else:
                self._reopen(self._dos_new_pattern, st, msg, v.get("name", ""), v.get("cols", ""), cont)
        return self._dos_dialog("New pattern", fields, [("Save", "ok"), ("Cancel", "cancel")], result, width=70,
                                message=note or "Colours: xterm numbers (0-255) or hex, separated by spaces: 196 202 208 #ffcc00")

    def _dos_import_pattern(self, st, note=None, cont=None):
        cont = cont or self.open_gradient
        fields = [{"key": "line", "label": "Shared line", "type": "text", "value": "", "width": 56}]

        def result(res, v):
            if res != "ok":
                self._reopen(cont, st)
                return
            try:
                name, cols = ct.parse_share(v.get("line", ""))
            except ValueError as e:
                self._reopen(self._dos_import_pattern, st, str(e), cont)
                return
            ok, msg = self.save_pattern(name, ",".join(str(c) for c in cols))
            self.system(msg)
            self._reopen(cont, dict(st, pattern=name) if ok else st)
        return self._dos_dialog("Import a pattern", fields, [("Import", "ok"), ("Cancel", "cancel")], result, width=76,
                                message=note or "Paste a line like sgrad1:Fire:196,202,208,214,220,226")

    # ---- customize: the form -------------------------------------------------------------
    def _customize_pages(self, mode):
        """[keys of page 1, keys of page 2]: one page when the DOS screen has room for every line,
        two only when it must."""
        def shown(k):
            return not (mode == "interface" and k in ("item", "extra", "extra_text")) and \
                not (mode == "cli" and k in ("itype", "count"))
        p1 = [k for k in custom.PAGE1 if shown(k)]
        p2 = [k for k in custom.PAGE2 if shown(k)]
        try:
            lh = max(1, self.f_norm.metrics("linespace") + self._spacing())
            avail = self.root.winfo_height() // lh - 4              # the bars above and below take a few rows
        except Exception:
            avail = 0
        need = 2 + len(p1) + len(p2) + 9                            # mode + type, the fields, frame/message/buttons
        return [p1 + p2] if need <= avail else [p1, p2]

    def _dos_customize(self, vals, page=1):
        vals = custom.clean_values(vals)
        vals["mode"] = self._cust_mode if self._cust_mode in custom.MODES else "cli"
        self._cust_values = vals                       # what is on the form now
        mode = vals["mode"]
        pages = self._customize_pages(mode)
        page = 1 if len(pages) == 1 else max(1, min(2, page))
        keys = pages[page - 1]
        fields = []
        if page == 1:
            fields.append({"key": "_mode", "label": "Mode", "type": "pick", "value": MODE_SHORT[mode], "width": 20})
            fields.append({"key": "_type", "label": "Design type", "type": "pick", "value": self._cust_type, "width": 14})
        widths = {f[0]: f[3] for f in custom.FIELDS}
        for k in keys:
            label = custom.SHORT[k]
            if k in custom.MULTILINE:
                fields.append({"key": k, "label": label, "type": "pick", "mark": "►", "width": 44,
                               "value": custom.summary(vals[k], 40)})
            elif k in custom.PICKED:
                shown = vals[k] if vals[k] else NONE_TEXT
                if k in ("cover", "zips"):
                    shown = vals[k] if vals[k] else NONE_TEXT
                fields.append({"key": k, "label": label, "type": "pick", "value": shown, "width": 44 if k in ("cover", "zips") else 18})
            else:
                fields.append({"key": k, "label": label, "type": "text", "value": vals[k], "width": min(widths[k], 46)})
        text_keys = [f["key"] for f in fields if f["type"] == "text"]

        def result(res, got):
            new = dict(vals)
            for k in text_keys:
                new[k] = got.get(k, "")
            self._cust_values = new
            again = lambda: self._dos_customize(new, page)
            if isinstance(res, tuple):
                self._reopen(self._dos_customize_pick, res[1], new, page)
                return
            if res == "cancel":
                return
            if res == "next":
                self._reopen(self._dos_customize, new, 2)
            elif res == "back":
                self._reopen(self._dos_customize, new, 1)
            elif res == "send":
                ok, m = self.send_customize(new, back=again)
                self.system(m)
                if not ok:
                    self._reopen(self._dos_customize, new, page)
            elif res == "save":
                self._dos_save_design(new, again)
            elif res == "book":
                self._dos_design_book(lambda d: self._reopen(self._dos_customize, dict(d["values"], item=new["item"]), 1),
                                      again)
            elif res == "clear":
                self._reopen(self._dos_customize, custom.blank(), 1)
        buttons = [("Send", "send"), ("Save", "save"), ("Book", "book"), ("Clear", "clear")]
        if len(pages) == 2:
            buttons.append(("Next >" if page == 1 else "< Back", "next" if page == 1 else "back"))
        buttons.append(("Cancel", "cancel"))
        msg = ("Enter on a line opens its list or its text page (Ctrl-G colours text there)." if mode == "cli" else
               "Game item editor: you must already be in it. Nothing finishes until you say Done.")
        title = "Customize" if len(pages) == 1 else "Customize (page %d of 2)" % page
        return self._dos_dialog(title, fields, buttons, result, width=76, message=msg)

    def _dos_customize_pick(self, key, new, page):
        again = lambda: self._dos_customize(new, page)
        setv = lambda k, v: self._reopen(self._dos_customize, dict(new, **{k: v}), page)
        if key == "_mode":
            self.dos_choose("Mode", [(custom.MODE_TEXT[m], m) for m in custom.MODES], new["mode"],
                            lambda m: (setattr(self, "_cust_mode", m), self._reopen(self._dos_customize, dict(new, mode=m), page)),
                            back=again)
        elif key == "_type":
            self.dos_choose("Design type (for the design book)", [(t, t) for t in custom.TYPES], self._cust_type,
                            lambda t: (setattr(self, "_cust_type", t), self._reopen(self._dos_customize, new, page)), back=again)
        elif key == "itype":
            self.dos_choose("Kind of item", [(NONE_TEXT, "")] + [(t, t) for t in custom.ITEM_TYPES], new["itype"],
                            lambda v: setv("itype", v), back=again)
        elif key == "size":
            self.dos_choose("Size", [(NONE_TEXT, ""), ("small", "small"), ("large", "large")], new["size"],
                            lambda v: setv("size", v), back=again)
        elif key == "layer":
            self.dos_choose("Layer", [(NONE_TEXT, "")] + [(str(n), str(n)) for n in range(6)], new["layer"],
                            lambda v: setv("layer", v), back=again)
        elif key in ("cover", "zips"):
            parts, _bad = custom.parse_parts(new[key])
            title = "Cover" if key == "cover" else "Zips (parts that stay covered when unzipped)"

            def done(sel):
                setv(key, ", ".join(sel))
            self.dos_multi_choose(title + ": Enter ticks", [(p, p) for p in custom.COVER_PARTS], parts, done)
        elif key in custom.MULTILINE:
            title = {"description": "Description", "taste": "Taste", "playlist": "Playlist",
                     "extra_text": "Extra description"}[key]

            def done(text):
                if text is not None:
                    new[key] = text
                self._reopen(self._dos_customize, new, page)
            self.dos_edit_text("%s: type it as you would in the game. Ctrl-S done, Esc cancel" % title, new[key], done)

    # ---- the game's own item editor ("interface mode") ----------------------------------------
    _EDITOR_LABEL = re.compile(r"^(?:Object|Type:|Cost:|Size:|Bites:|Drinks:|Uses:|Names:|Short:|Long:|Description:|Wear:|"
                               r"Alcohol Content:|Scent|Effect|Layer:|Cover|Zips?|Taste|Playlist|Dye|Height|Bust|"
                               r"Done\.|Coverage (?:added|removed|cleared)\.)", re.I)

    def send_customize(self, values, back=None):
        """Send the form: as `customize <item> ...` lines, or into the game's item editor."""
        v = custom.clean_values(values)
        if self._cust_mode == "interface" or v.get("mode") == "interface":
            return self.send_interface(v, back)
        cmds, problems = custom.build_commands(v)
        if problems:
            return False, problems[0]
        for c in cmds:
            self.send_line(c, expand=False)       # text lines must reach the game's editor untouched
        return True, "Sent %d lines." % len(cmds)

    def send_interface(self, values, back=None):
        cmds, problems = custom.build_interface_commands(values)
        if problems:
            return False, problems[0]
        if not self.connected:
            return False, "Not connected."
        self._iface = {"lines": [], "back": back, "n": len(cmds)}
        for c in cmds:
            self.send_line(c, echo=False, expand=False)
        self._iface_arm()
        return True, "Sent %d lines to the game's item editor; its replies are gathered, not scrolled." % len(cmds)

    def _iface_arm(self):
        if self._iface_job is not None:
            try:
                self.root.after_cancel(self._iface_job)
            except Exception:
                pass
        try:
            self._iface_job = self.root.after(900, self._iface_finish)       # quiet for a moment: it has answered
        except Exception:
            self._iface_job = None

    def iface_capture(self, pieces, plain):
        """A line of game output while an editor session is being gathered. True = swallowed."""
        if self._iface is None:
            return False
        self._iface["lines"].append((pieces, plain))
        self._iface_arm()
        return True

    def _iface_finish(self):
        """Show the editor as it stands now, plus anything that was not the editor talking."""
        self._iface_job = None
        sess, self._iface = self._iface, None
        if not sess:
            return
        lines = sess["lines"]
        last_obj = max((i for i, (_p, t) in enumerate(lines) if t.strip() == "Object"), default=None)
        in_desc = False
        shown = []
        for i, (pieces, plain) in enumerate(lines):
            t = plain.strip()
            is_editor = bool(self._EDITOR_LABEL.match(t)) or in_desc or not t
            if t.lower().startswith("description:"):
                in_desc = True
            elif in_desc and t.lower().startswith("wear:"):
                in_desc = False
            if last_obj is not None and i >= last_obj:
                shown.append((pieces, plain))              # the finished item, as the game shows it
            elif not is_editor:
                shown.append((pieces, plain))              # chat, errors, anything else
        if last_obj is None:
            shown = list(lines)                            # no editor in sight: hide nothing
        self._settle()
        for pieces, plain in shown:
            segs = [(t, self._tag_for(k)) for t, k in pieces]
            segs.append(("\n", None))
            self._append(segs, _internal=True)
        if last_obj is None:
            self.system("I did not see the game's item editor. Are you in it?")
            return
        self._iface_review(sess)

    def _iface_review(self, sess):
        back = sess.get("back")
        msg = "The item is as shown above. Done sends 'done' to the game to finish it."
        if self.sr_on():
            self.speech.say_now(msg)
        if self.dos:
            def result(res, _v):
                if res == "done":
                    self.send_line("done", expand=False)
                elif res == "back" and back:
                    self._reopen(back)
            self._dos_dialog("Game item editor", [], [("Done", "done"), ("Back to form", "back"), ("Close", "close")],
                             result, width=64, message=msg)
            return
        from tkinter import messagebox
        if messagebox.askyesno("Game item editor", msg + "\n\nFinish it now (send 'done')?", parent=self.root):
            self.send_line("done", expand=False)
        else:
            self.system("Not finished. Change things in the form, or type 'done' in the game.")
