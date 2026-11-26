"""A phone look for a popped-out pane (the Phone pane, say): the texts drawn as chat bubbles on a phone, an iPhone or an Android.

It is only a picture of what the pane already holds. The window's ordinary text area keeps filling underneath, hidden, so
nothing about capture, history, find or docking changes, and "Normal" in the window's Look box puts it back at once. Each
line of the pane is read as a text: `[Nov 24 18:31]7108390: hello` is from 7108390 (grey, on the left), and
`[Nov 24 18:33]You > Mara: hi` is yours (coloured, on the right); a line with no date and time in front is the end of the
text before it, which the game wrapped. It is off by default, a choice per window, remembered with the pane, and it never
shows in the DOS look or in screen reader mode (a picture cannot be read by a screen reader; the text area can).
Windows only, like the rest of the client."""
import re
import time
import tkinter as tk
from tkinter import font as tkfont

SKINS = {
    "iphone": dict(label="iPhone", edge="#c9c5bd", bezel="#0b0b0c", screen="#ffffff", head_bg="#f7f7f8", head_fg="#000000",
                   sub="#8e8e93", line="#d1d1d6", in_bg="#e9e9eb", in_fg="#000000", out_bg="#007aff", out_fg="#ffffff",
                   accent="#007aff", radius=18, hint="iMessage", island=True),
    "android": dict(label="Android", edge="#3c4043", bezel="#050505", screen="#ffffff", head_bg="#ffffff", head_fg="#202124",
                    sub="#5f6368", line="#ffffff", in_bg="#f1f3f4", in_fg="#202124", out_bg="#d3e3fd", out_fg="#041e49",
                    accent="#1a73e8", radius=20, hint="Text message", island=False),
}
LOOKS = ("normal",) + tuple(SKINS)                     # what the window's Look box offers
LABELS = {"normal": "Normal", "iphone": "iPhone", "android": "Android"}
MAX_SHOWN = 200                                         # texts drawn (the newest); the text area keeps them all
SEPARATE_AFTER = 60                                     # minutes of quiet between two texts that earns a time heading
BACKDROP = "#2b2b2e"
PORTRAIT = (400, 800)                                   # the size a window takes when it first becomes a phone
MIN_WIDTH = 560                                         # (wide enough for the window's row of buttons)
RATIO = 0.49                                            # width / height of the phone

HEAD = re.compile(r"^(?:\[\d\d:\d\d(?::\d\d)?\] )?\[(?P<when>[A-Z][a-z]{2} [ 0-9][0-9] \d\d:\d\d)\](?P<who>[^:]{1,40}?): ?(?P<msg>.*)$")


def parse_messages(lines):
    """[{when, who, mine, text, note}] from the pane's plain lines. `who` is the other person (the one you wrote to, for a
    text of yours)."""
    out = []
    for ln in lines:
        m = HEAD.match(ln)
        if m:
            who = m.group("who").strip()
            mine = who.lower().startswith("you >")
            out.append({"when": m.group("when"), "who": who[5:].strip() if mine else who, "mine": mine,
                        "text": m.group("msg").strip(), "note": False})
        elif ln.strip():
            if out and not out[-1]["note"]:
                out[-1]["text"] = (out[-1]["text"] + " " + ln.strip()).strip()          # the game wrapped it onto this line
            else:
                out.append({"when": "", "who": "", "mine": False, "text": ln.strip(), "note": True})
    return out


_MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}


def stamp_minutes(when):
    """'Nov 24 18:31' -> minutes since the start of the year (a rough clock, enough to see a gap or a new day), or None."""
    try:
        mon, day, hm = when.split()
        hh, mm = hm.split(":")
        return ((_MONTHS[mon] * 31 + int(day)) * 24 + int(hh)) * 60 + int(mm)
    except (ValueError, KeyError):
        return None


def heading_before(prev, cur):
    """The time heading to draw between two texts ('' for none): the first text, a new day, or a long quiet."""
    if not cur["when"]:
        return ""
    if prev is None or not prev["when"]:
        return cur["when"]
    a, b = stamp_minutes(prev["when"]), stamp_minutes(cur["when"])
    if a is None or b is None or prev["when"].split()[:2] != cur["when"].split()[:2] or b - a >= SEPARATE_AFTER:
        return cur["when"]
    return ""


def rounded(cv, x1, y1, x2, y2, r, **kw):
    """A rounded rectangle on a canvas (a smoothed polygon)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r, x2, y2,
           x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


class PhoneLookMixin:
    # ---- the setting --------------------------------------------------------------------------------------------------
    def phone_look_of(self, name):
        d = self._find_pane_def(name)
        v = str(((d or {}).get("window") or {}).get("phone") or "")
        return v if v in SKINS else ""

    def set_phone_look(self, name, look):
        """'normal' (or ''), 'iphone' or 'android' for the pane's window. False if there is no such pane or look."""
        look = str(look or "").strip().lower()
        look = "" if look in ("", "normal", "off", "none") else look
        if look and look not in SKINS:
            return False
        d = self._find_pane_def(name)
        if d is None:
            return False
        win = dict(d.get("window") or {})
        was = win.get("phone", "")
        if look:
            win["phone"] = look
        else:
            win.pop("phone", None)
        d["window"] = win
        pane = self._panes.get(d["name"].lower())
        view = pane.get("popout") if pane else None
        if view:
            if look and not was:
                self._phone_portrait(view)
            self._phone_apply(view)
        self._save_settings()
        return True

    def _phone_wanted(self, view):
        return bool(self.phone_look_of(view["key"]) and not self.dos and not self.sr_on())

    def _phone_apply_all(self):
        """The look, the DOS look or screen reader mode changed: every open window shows what it should."""
        for s in list(self.sessions):
            for p in list(s._panes.values()):
                v = p.get("popout")
                if v:
                    prev, self.session = self.session, s
                    try:
                        self._in_world_cfg(lambda v=v: self._phone_apply(v))
                    finally:
                        self.session = prev

    def _phone_portrait(self, view):
        """The first time a window becomes a phone, a landscape window turns upright (the window's size is remembered)."""
        win = view["win"]
        try:
            win.update_idletasks()
            w, h = win.winfo_width(), win.winfo_height()
            if w > h * 0.8:
                ph = min(PORTRAIT[1], max(480, win.winfo_screenheight() - 140))
                win.geometry("%dx%d" % (max(MIN_WIDTH, int(ph * RATIO) + 20), ph))
        except tk.TclError:
            pass

    # ---- showing and hiding ---------------------------------------------------------------------------------------------
    def _phone_apply(self, view):
        """Make the window match its setting: the phone (hiding the text area under it) or the ordinary text area."""
        look = self.phone_look_of(view["key"])
        want = self._phone_wanted(view)
        menu = view.get("look_frame")
        if menu is not None:
            try:
                if self.dos or self.sr_on():
                    menu.pack_forget()
                elif not menu.winfo_manager():
                    menu.pack(side="left", padx=(6, 3))
                view["look_var"].set(LABELS.get(look or "normal", "Normal"))
            except tk.TclError:
                pass
        ph = view.get("ph")
        try:
            if want and ph is None:
                self._phone_build(view, look)
            elif want and ph["skin"] != look:
                ph["skin"] = look
                self._phone_layout(view)
            elif not want and ph is not None:
                self._phone_remove(view)
        except tk.TclError:
            pass

    def _phone_build(self, view, look):
        box = view["box"]
        view["sb"].pack_forget()
        view["text"].pack_forget()
        chrome = tk.Canvas(box, bg=BACKDROP, highlightthickness=0, bd=0)
        chrome.pack(fill="both", expand=True)
        inner = tk.Canvas(chrome, bg="#ffffff", highlightthickness=0, bd=0, takefocus=0)
        ph = {"skin": look, "chrome": chrome, "inner": inner, "size": None, "job": None, "clock": None, "rect": None,
              "fonts": {}, "win_item": None}
        view["ph"] = ph
        chrome.bind("<Configure>", lambda e, v=view: self._phone_layout(v, soon=True))
        for w in (inner, chrome):
            w.bind("<MouseWheel>", lambda e, c=inner: c.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        view["win"].bind("<Prior>", lambda e, c=inner: c.yview_scroll(-1, "pages"), add="+")
        view["win"].bind("<Next>", lambda e, c=inner: c.yview_scroll(1, "pages"), add="+")
        self._phone_layout(view)
        self._phone_tick(view)

    def _phone_remove(self, view):
        ph = view.pop("ph", None)
        if ph is None:
            return
        for k in ("job", "clock"):
            if ph.get(k) is not None:
                try:
                    view["win"].after_cancel(ph[k])
                except tk.TclError:
                    pass
        try:
            ph["chrome"].destroy()
        except tk.TclError:
            pass
        try:
            view["sb"].pack(side="right", fill="y")
            view["text"].pack(side="left", fill="both", expand=True)
            view["text"].see("end")
        except tk.TclError:
            pass

    def _phone_tick(self, view):
        """The phone's clock follows the real one."""
        ph = view.get("ph")
        if ph is None:
            return
        try:
            self._phone_layout(view, soon=False, only_clock=True)
            ph["clock"] = view["win"].after(20000, lambda: self._phone_tick(view))
        except tk.TclError:
            ph["clock"] = None

    # ---- new lines, clearing ----------------------------------------------------------------------------------------------
    def _phone_dirty(self, view):
        """The pane got a line or was cleared: draw the texts again (a burst of lines is one redraw)."""
        ph = view.get("ph")
        if ph is None or ph.get("job") is not None:
            return
        try:
            ph["job"] = view["win"].after(50, lambda: self._phone_redraw_messages(view))
        except tk.TclError:
            ph["job"] = None

    def _phone_lines(self, view):
        pane = view["session"]._panes.get(view["key"])
        if not pane:
            return []
        return ["".join(t for t, _k in pieces) for pieces in pane["history"]]

    # ---- drawing ----------------------------------------------------------------------------------------------------------------
    def _phone_font(self, ph, name, size, weight="normal"):
        key = (name, size, weight)
        f = ph["fonts"].get(key)
        if f is None:
            f = ph["fonts"][key] = tkfont.Font(family="Segoe UI", size=size, weight=weight)
        return f

    def _phone_layout(self, view, soon=False, only_clock=False):
        """Draw the phone (body, status bar, header, the field at the bottom) to fit the window, and put the texts in it."""
        ph = view.get("ph")
        if ph is None:
            return
        cv = ph["chrome"]
        if soon:
            if ph.get("lay") is None:
                ph["lay"] = view["win"].after(40, lambda: (ph.__setitem__("lay", None), self._phone_layout(view)))
            return
        W, H = cv.winfo_width(), cv.winfo_height()
        if W < 120 or H < 200:
            return
        sk = SKINS[ph["skin"]]
        m = 10
        if (W - 2 * m) / max(1, (H - 2 * m)) > RATIO:
            bh = H - 2 * m
            bw = int(bh * RATIO)
        else:
            bw = W - 2 * m
            bh = int(bw / RATIO)
        bx, by = (W - bw) // 2, (H - bh) // 2
        R = int(bw * 0.12)
        bez = max(9, min(16, int(bw * 0.035))) + int(R * 0.2)
        x0, y0, x1, y1 = bx + bez, by + bez, bx + bw - bez, by + bh - bez
        sbh = max(24, min(36, int(bh * 0.045)))
        hh = max(46, min(70, int(bh * 0.085)))
        fh = max(40, min(58, int(bh * 0.07)))
        home = 16
        geom = (W, H, ph["skin"])
        if only_clock:
            if ph.get("clock_item"):
                cv.itemconfigure(ph["clock_item"], text=time.strftime("%H:%M"))
            return
        cv.delete("all")
        ph["win_item"] = None                                   # (the message area went with everything else: it is put back below)
        fs = lambda n: max(8, int(n))
        small = self._phone_font(ph, "s", fs(bh / 62))
        med = self._phone_font(ph, "m", fs(bh / 55))
        bold = self._phone_font(ph, "b", fs(bh / 52), "bold")
        # the body: the frame, the black bezel, then the screen
        rounded(cv, bx - 3, by - 3, bx + bw + 3, by + bh + 3, R + 3, fill=sk["edge"], outline="")
        rounded(cv, bx, by, bx + bw, by + bh, R, fill=sk["bezel"], outline="")
        cv.create_rectangle(x0, y0, x1, y1, fill=sk["screen"], outline="")
        cv.create_rectangle(x0, y0, x1, y0 + sbh + hh, fill=sk["head_bg"], outline="")
        # status bar
        ph["clock_item"] = cv.create_text(x0 + int((x1 - x0) * 0.09), y0 + sbh // 2 + 3, text=time.strftime("%H:%M"),
                                          font=bold, fill=sk["head_fg"], anchor="w")
        ink = sk["head_fg"]
        cx = (x0 + x1) // 2
        if sk["island"]:
            rounded(cv, cx - int(bw * 0.15), y0 + 5, cx + int(bw * 0.15), y0 + 5 + int(sbh * 0.72), int(sbh * 0.36), fill="#000000", outline="")
        else:
            cv.create_oval(cx - 6, y0 + 8, cx + 6, y0 + 20, fill="#000000", outline="")
        rx = x1 - int((x1 - x0) * 0.07)
        by_ = y0 + sbh // 2 + 3
        rounded(cv, rx - 26, by_ - 6, rx, by_ + 6, 3, fill="", outline=ink, width=1)                   # battery
        cv.create_rectangle(rx - 24, by_ - 4, rx - 7, by_ + 4, fill=ink, outline="")
        cv.create_rectangle(rx + 1, by_ - 2, rx + 3, by_ + 2, fill=ink, outline="")
        sx = rx - 38
        for i in range(4):                                                                              # signal
            cv.create_rectangle(sx - 18 + i * 5, by_ + 6 - 3 - i * 3, sx - 14 + i * 5, by_ + 6, fill=ink, outline="")
        wx = sx - 28
        cv.create_arc(wx - 9, by_ - 6, wx + 9, by_ + 12, start=45, extent=90, style="pieslice", fill=ink, outline=ink)   # wi-fi
        # the header: who it is
        msgs = parse_messages(self._phone_lines(view))
        people = []
        for x in msgs:
            if x["who"] and x["who"] not in people:
                people.append(x["who"])
        who = people[0] if len(people) == 1 else "Messages"                       # one person: their name; several: the app's
        hy = y0 + sbh
        ph["who"] = who
        ac = sk["accent"]
        if ph["skin"] == "iphone":
            cv.create_oval(cx - 17, hy + 4, cx + 17, hy + 38, fill="#a8adb7", outline="")
            cv.create_text(cx, hy + 21, text=("✉" if who == "Messages" else (who[:1] or "?").upper()), font=bold, fill="#ffffff")
            cv.create_text(cx, hy + 49, text=who[:24] + "  \u203a", font=small, fill=sk["head_fg"])
            cv.create_text(x0 + 14, hy + hh // 2, text="\u2039", font=self._phone_font(ph, "chev", fs(bh / 28)), fill=ac, anchor="w")
            cv.create_line(x0, y0 + sbh + hh, x1, y0 + sbh + hh, fill=sk["line"])
        else:
            cv.create_text(x0 + 14, hy + hh // 2, text="\u2190", font=bold, fill=ink, anchor="w")
            cv.create_oval(x0 + 44, hy + hh // 2 - 16, x0 + 76, hy + hh // 2 + 16, fill="#9aa0a6", outline="")
            cv.create_text(x0 + 60, hy + hh // 2, text=("✉" if who == "Messages" else (who[:1] or "?").upper()), font=bold, fill="#ffffff")
            cv.create_text(x0 + 86, hy + hh // 2, text=who[:22], font=bold, fill=ink, anchor="w")
            cv.create_text(x1 - 14, hy + hh // 2, text="\u22ee", font=bold, fill=ink, anchor="e")
        # the field at the bottom (a picture: type in the window's Input bar) and the home bar
        fy0, fy1 = y1 - home - fh + 8, y1 - home - 6
        if ph["skin"] == "iphone":
            cv.create_oval(x0 + 10, fy1 - 32, x0 + 42, fy1, fill="#e9e9eb", outline="")
            cv.create_text(x0 + 26, fy1 - 16, text="+", font=bold, fill="#8e8e93")
            rounded(cv, x0 + 50, fy1 - 32, x1 - 12, fy1, 16, fill="#ffffff", outline="#c7c7cc")
            cv.create_text(x0 + 64, fy1 - 16, text=sk["hint"], font=med, fill="#8e8e93", anchor="w")
            cv.create_oval(x1 - 42, fy1 - 28, x1 - 16, fy1 - 4, fill=ac, outline="")
            cv.create_text(x1 - 29, fy1 - 16, text="\u2191", font=small, fill="#ffffff")
            rounded(cv, cx - 55, y1 - 9, cx + 55, y1 - 5, 2, fill="#000000", outline="")
        else:
            cv.create_text(x0 + 24, fy1 - 16, text="+", font=bold, fill="#5f6368")
            rounded(cv, x0 + 44, fy1 - 34, x1 - 12, fy1, 17, fill=sk["in_bg"], outline="")
            cv.create_text(x0 + 60, fy1 - 17, text=sk["hint"], font=med, fill="#5f6368", anchor="w")
            cv.create_text(x1 - 28, fy1 - 17, text="\u27a4", font=med, fill=ac)
            rounded(cv, cx - 40, y1 - 9, cx + 40, y1 - 6, 2, fill="#5f6368", outline="")
        top = y0 + sbh + hh + (1 if ph["skin"] == "iphone" else 0)
        bottom = fy0 - 4
        rect = (x0, top, x1, bottom)
        if ph["win_item"] is None:
            ph["win_item"] = cv.create_window(x0, top, anchor="nw", window=ph["inner"], width=x1 - x0, height=max(10, bottom - top))
        else:
            cv.coords(ph["win_item"], x0, top)
            cv.itemconfigure(ph["win_item"], width=x1 - x0, height=max(10, bottom - top))
            cv.tag_raise(ph["win_item"])
        ph["inner"].configure(bg=sk["screen"])
        ph["rect"], ph["size"] = rect, geom
        self._phone_redraw_messages(view, msgs)

    def _phone_redraw_messages(self, view, msgs=None):
        """The texts as bubbles in the screen area."""
        ph = view.get("ph")
        if ph is None or ph["rect"] is None:
            return
        ph["job"] = None
        sk = SKINS[ph["skin"]]
        cv = ph["inner"]
        x0, top, x1, bottom = ph["rect"]
        width = x1 - x0
        if msgs is None:
            msgs = parse_messages(self._phone_lines(view))
        before = cv.yview()
        at_end = before[1] >= 0.999 or before == (0.0, 1.0)
        top_px = cv.canvasy(0)
        cv.delete("all")
        cv.configure(bg=sk["screen"])
        f = self._phone_font(ph, "msg", max(9, int((bottom - top) / 46)))
        fsmall = self._phone_font(ph, "tiny", max(7, int((bottom - top) / 60)))
        pad, px, py = 10, 12, 7
        maxw = int(width * 0.74) - 2 * px
        y = pad
        prev = None
        for i, msg in enumerate(msgs[-MAX_SHOWN:]):
            head = heading_before(prev, msg)
            if head:
                cv.create_text(width // 2, y + 8, text=head, font=fsmall, fill=sk["sub"])
                y += 24
            if msg["note"]:
                t = cv.create_text(width // 2, y, text=msg["text"], font=fsmall, fill=sk["sub"], width=int(width * 0.86), anchor="n", justify="center")
                y = cv.bbox(t)[3] + 8
                prev = msg
                continue
            side_changed = prev is None or prev["mine"] != msg["mine"] or prev["who"] != msg["who"] or bool(head)
            if not msg["mine"] and side_changed:
                cv.create_text(pad + 6, y, text=msg["who"][:28], font=fsmall, fill=sk["sub"], anchor="nw")
                y += 15
            t = cv.create_text(0, 0, text=msg["text"], font=f, width=maxw, anchor="nw", fill=sk["out_fg"] if msg["mine"] else sk["in_fg"])
            bx0, by0, bx1, by1 = cv.bbox(t)
            tw, th = bx1 - bx0, by1 - by0
            bw_, bh_ = tw + 2 * px, th + 2 * py
            left = width - pad - bw_ if msg["mine"] else pad
            rounded(cv, left, y, left + bw_, y + bh_, min(sk["radius"], bh_ // 2), fill=sk["out_bg"] if msg["mine"] else sk["in_bg"], outline="")
            cv.coords(t, left + px, y + py)
            cv.tag_raise(t)
            y += bh_ + 3
            prev = msg
        y += pad
        cv.configure(scrollregion=(0, 0, width, max(y, bottom - top)))
        if at_end:
            cv.yview_moveto(1.0)
        else:
            cv.yview_moveto(max(0.0, top_px / max(1, y)))


def view_title(app, view):
    d = app._find_pane_def(view["key"])
    return (d or {}).get("title") or "Phone"
