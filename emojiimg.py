"""Colour emoji in the text areas, in Windows' own emoji look.

Tk draws text with single-colour glyphs, so an emoji comes out flat. With this on, each emoji is drawn as a small
picture (rendered in colour from the Segoe UI Emoji font by Pillow) placed in the text. The emoji character itself
stays in the text, hidden, so copying, searching and the logs still see the emoji. The fonts stay monospaced: the
pictures are one line high and about two cells wide, which is what an emoji takes up anyway.

Options: "Colour emoji" for the ordinary look (on by default) and "Colour emoji in the DOS look" (off by default, for
those who like their terminal plain). Without Pillow or the font, nothing changes."""
import os
import re
import sys
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
except ImportError:                       # the plain glyphs stay
    Image = None

# the pictorial emoji (not flags, which need a shaping engine; and not joined sequences, which fall back to text)
_CLUSTER = re.compile("(?:[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\U0001F170-\U0001F1E5\U0001F200-\U0001F251"
                      "\U0001F004\U0001F0CF][\uFE0F\U0001F3FB-\U0001F3FF]*)(\u200d)?")
_FONT_NAMES = ("seguiemj.ttf",)
TAG_HIDE = "emoelide"
_ICON_MIN, _ICON_MAX = 10, 64


def _font_path():
    d = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for n in _FONT_NAMES:
        p = os.path.join(d, n)
        if os.path.exists(p):
            return p
    return None


class EmojiImageMixin:
    _emo_cache = None              # (cluster, size) -> PhotoImage
    _emo_fonts = None              # point size -> ImageFont
    _emo_units_cache = None
    _emo_applied = None            # (on, size) the text areas currently show
    _emo_job = None

    # ---- is it on, and can it be ------------------------------------------------------------
    def _emoji_available(self):
        return Image is not None and sys.platform.startswith("win") and _font_path() is not None

    def _emoji_pics_on(self):
        key = "emoji_pics_dos" if self.dos else "emoji_pics"
        return bool(self.cfg.get(key)) and self._emoji_available()

    def _emoji_size(self):
        try:
            return max(_ICON_MIN, min(_ICON_MAX, int(self.f_norm.metrics("linespace"))))
        except tk.TclError:
            return 16

    def _emoji_units(self):
        """How many positions one emoji takes in a Tk text index (2 where Tk counts UTF-16 halves)."""
        if self._emo_units_cache is None:
            n = 2
            try:
                t = tk.Text(self.root)
                t.insert("end", chr(0x1F600))
                n = int(t.count("1.0", "end-1c", "chars")[0])
                t.destroy()
            except (tk.TclError, TypeError, ValueError, IndexError):
                pass
            self._emo_units_cache = n
        return self._emo_units_cache

    # ---- making the pictures ------------------------------------------------------------------
    def _emoji_photo(self, cluster, size):
        if self._emo_cache is None:
            self._emo_cache, self._emo_fonts = {}, {}
        key = (cluster, size)
        ph = self._emo_cache.get(key)
        if ph is not None:
            return ph
        try:
            path = _font_path()
            big = size * 2
            probe = self._emo_fonts.get(100)
            if probe is None:
                probe = self._emo_fonts[100] = ImageFont.truetype(path, 100)
            l, t, r, b = probe.getbbox(cluster)
            span = max(1, max(r - l, b - t))
            fs = max(8, int(100 * (big * 0.94) / span))
            font = self._emo_fonts.get(fs)
            if font is None:
                font = self._emo_fonts[fs] = ImageFont.truetype(path, fs)
            l, t, r, b = font.getbbox(cluster)
            im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
            ImageDraw.Draw(im).text(((big - (r - l)) / 2 - l, (big - (b - t)) / 2 - t), cluster, font=font,
                                    embedded_color=True)
            ph = ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS), master=self.root)
        except Exception:                  # a font Pillow cannot draw: leave that emoji as text
            ph = False
        if len(self._emo_cache) > 600:
            self._emo_cache.clear()
        self._emo_cache[key] = ph
        return ph or None

    # ---- putting them in a text area ---------------------------------------------------------------
    def _emojify(self, w, start="1.0", end="end-1c", size=None):
        """Replace the emoji between two indexes of a Text widget (which must be editable right now) with
        pictures. Call only when `_emoji_pics_on()`."""
        try:
            txt = w.get(start, end)
        except tk.TclError:
            return
        if txt.isascii():
            return
        size = size or self._emoji_size()
        w.tag_configure(TAG_HIDE, elide=True)
        u = self._emoji_units()
        line0, col0 = (int(x) for x in w.index(start).split("."))
        found = []
        for n, line in enumerate(txt.split("\n")):
            if line.isascii():
                continue
            joined_end = -1
            for m in _CLUSTER.finditer(line):
                follows_join = m.start() == joined_end
                joined_end = m.end() if m.group(1) else -1
                if m.group(1) or follows_join:      # part of a joined sequence: pictures cannot show it whole
                    continue
                off = sum(u if ord(c) > 0xFFFF else 1 for c in line[:m.start()])
                found.append((line0 + n, (col0 if n == 0 else 0) + off, m.group(0), sum(u if ord(c) > 0xFFFF else 1 for c in m.group(0))))
        for ln, col, cluster, length in reversed(found):          # last first: earlier positions stay valid
            ph = self._emoji_photo(cluster, size)
            if ph is None:
                continue
            a = "%d.%d" % (ln, col)
            b = "%d.%d" % (ln, col + length)
            try:
                if w.get(a, b) != cluster or TAG_HIDE in w.tag_names(a):
                    continue
                tags = [t for t in w.tag_names(a) if t not in ("sel", TAG_HIDE, "link")]
                w.image_create(b, image=ph, padx=0, align="center")
                for t in tags:                                          # the picture wears what the character wore
                    w.tag_add(t, b, "%s+1c" % b)
                w.tag_add(TAG_HIDE, a, b)
            except tk.TclError:
                continue

    def _emoji_strip(self, w):
        """Back to plain emoji characters in one Text widget (which must be editable right now)."""
        try:
            imgs = w.dump("1.0", "end", image=True)
        except tk.TclError:
            return
        for _k, _name, index in reversed(imgs):
            try:
                w.delete(index)
            except tk.TclError:
                pass
        try:
            w.tag_remove(TAG_HIDE, "1.0", "end")
        except tk.TclError:
            pass

    def _emoji_refresh(self, force=False):
        """Make every text area match the options and the font size now: pictures on, off, or resized."""
        on, size = self._emoji_pics_on(), self._emoji_size()
        if not force and self._emo_applied == (on, size):
            return
        self._emo_applied = (on, size)
        if self._emo_cache:
            self._emo_cache.clear()
        for w in self._text_widgets():
            try:
                state = str(w.cget("state"))
                w.configure(state="normal")
                self._emoji_strip(w)
                if on:
                    self._emojify(w, size=size)
                w.configure(state=state)
            except tk.TclError:
                pass

    def _emoji_watch(self):
        """Once a second: notice a font-size change or a look change that did not announce itself."""
        self._emo_job = None
        try:
            self._emoji_refresh()
            self._emo_job = self.root.after(1000, self._emoji_watch)
        except tk.TclError:
            self._emo_job = None

    def _emoji_start(self):
        if self._emo_job is None:
            self._emoji_watch()
