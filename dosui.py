"""dosui - early-1990s DOS terminal look (Telix / Terminate style) widgets for tkinter.

Self-contained: stdlib tkinter only, no ttk, no images.  Everything is drawn on
tk.Canvas objects with monospace text and Unicode box-drawing characters, laid
out on a strict character-cell grid (cell = font.measure('M') x linespace).

Public API:
    dos_colors(theme) -> dict
    gauge_text(cur, maximum, width=10) -> (text, role)
    format_duration(seconds) -> 'HH:MM:SS'
    parse_hex_color(text) -> '#rrggbb' | None
    DosMenu, DosDialog, DosColorPicker, DosTable, DosStatusBar, show_message(), confirm(), DosMessage
"""
import math
import re
import sys
import textwrap
import tkinter as tk
import tkinter.font as tkfont

__all__ = ['BOX_DOUBLE', 'BOX_SINGLE', 'dos_colors', 'gauge_text', 'format_duration',
           'parse_hex_color', 'DosMenu', 'DosDialog', 'DosColorPicker', 'DosStatusBar', 'DosMessage', 'show_message', 'confirm',
           'DosScrollbar', 'DosTable']

BOX_DOUBLE = '╔═╗║╚╝'     # tl, horizontal, tr, vertical, bl, br
BOX_SINGLE = '┌─┐│└┘'
SEP_LEFT, SEP_FILL, SEP_RIGHT = '╟', '─', '╢'
GAUGE_FULL, GAUGE_EMPTY = '█', '░'
CHECK_ON, CHECK_OFF = '√', ' '
ELLIPSIS = '…'

_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
_HEX_INPUT = re.compile(r'#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})')


def parse_hex_color(text):
    """'#rgb' / 'rgb' / '#rrggbb' / 'rrggbb' (any case, surrounding spaces ok) -> '#rrggbb'.

    Anything else (None, other types, newlines, non-ASCII digits, wrong length) -> None."""
    if not isinstance(text, str):
        return None
    m = _HEX_INPUT.fullmatch(text.strip(' '))
    if not m:
        return None
    h = m.group(1).lower()
    if len(h) == 3:
        h = ''.join(ch * 2 for ch in h)
    return '#' + h


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _hex(v, default):
    if isinstance(v, str) and _HEX.match(v.strip()):
        return v.strip().lower()
    return default


def _lum(h):
    try:
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    except Exception:
        return 0.0


def dos_colors(theme):
    """Resolve a theme dict into a complete DOS colour dict (never raises)."""
    if not isinstance(theme, dict):
        theme = {}
    g = lambda k, d: _hex(theme.get(k), d)
    ansi = theme.get('ansi')
    if not isinstance(ansi, (list, tuple)):
        ansi = []

    def an(i, d):
        try:
            return _hex(ansi[i], d)
        except Exception:
            return d

    c = {}
    c['bg'] = g('bg', '#000000')
    c['fg'] = g('fg', '#aaaaaa')
    c['panel'] = g('panel', '#0000aa')
    c['panel_edge'] = g('panel_edge', '#00aaaa')
    c['input_bg'] = g('input_bg', '#000000')
    c['input_fg'] = g('input_fg', '#aaaaaa')
    c['alert'] = g('alert', '#ff5555')
    c['dim'] = g('dim', '#8888cc')
    c['select'] = g('select', '#00aaaa')
    c['button_bg'] = g('button_bg', '#00aaaa')
    c['button_fg'] = g('button_fg', '#000000')
    c['dos_bar_bg'] = g('dos_bar_bg', '#00aaaa')
    c['dos_bar_fg'] = g('dos_bar_fg', '#000000')
    c['dos_bar2_bg'] = g('dos_bar2_bg', '#0000aa')
    c['dos_bar2_fg'] = g('dos_bar2_fg', '#ffffff')
    c['dos_key_fg'] = g('dos_key_fg', '#ffff55')
    c['dos_menu_bg'] = g('dos_menu_bg', '#0000aa')
    c['dos_menu_fg'] = g('dos_menu_fg', '#ffffff')
    c['dos_menu_border'] = g('dos_menu_border', '#ffffff')
    c['dos_menu_sel_bg'] = g('dos_menu_sel_bg', '#00aaaa')
    c['dos_menu_sel_fg'] = g('dos_menu_sel_fg', '#000000')
    c['dos_menu_dim'] = g('dos_menu_dim', c['dim'])
    c['dos_shadow'] = g('dos_shadow', '#2a2a2a' if _lum(c['bg']) < 0.08 else '#000000')
    c['dos_screen_border'] = g('dos_screen_border', '#0000aa')
    c['ansi'] = [an(i, d) for i, d in enumerate(
        ['#000000', '#aa0000', '#00aa00', '#aa5500', '#0000aa', '#aa00aa', '#00aaaa', '#aaaaaa',
         '#555555', '#ff5555', '#55ff55', '#ffff55', '#5555ff', '#ff55ff', '#55ffff', '#ffffff'])]
    c['good'] = an(10, '#55ff55')
    c['warn'] = an(11, '#ffff55')
    c['bad'] = an(9, '#ff5555')
    return c


def _num(v, default=0.0):
    try:
        f = float(v)
    except Exception:
        return default
    if f != f:
        return default
    return f


def gauge_text(cur, maximum, width=10):
    """Block gauge. Returns (text of exactly `width` chars, role good/warn/bad)."""
    try:
        width = int(width)
    except Exception:
        width = 10
    width = max(0, min(width, 500))
    m = _num(maximum, 0.0)
    c = _num(cur, 0.0)
    if m <= 0:
        prop = 1.0
    else:
        prop = c / m
        if prop != prop:
            prop = 0.0
        prop = max(0.0, min(1.0, prop))
    n = int(prop * width + 0.5)
    n = max(0, min(width, n))
    role = 'good' if prop >= 0.6 else ('warn' if prop >= 0.3 else 'bad')
    return GAUGE_FULL * n + GAUGE_EMPTY * (width - n), role


def format_duration(seconds):
    """'HH:MM:SS'; never negative, clamped to 99:59:59."""
    s = _num(seconds, 0.0)
    if math.isinf(s):
        s = 359999 if s > 0 else 0
    s = int(max(0, min(s, 359999)))
    return '%02d:%02d:%02d' % (s // 3600, (s // 60) % 60, s % 60)


def _trunc(s, n):
    if n <= 0:
        return ''
    if len(s) <= n:
        return s
    if n == 1:
        return s[:1]
    return s[:n - 1] + ELLIPSIS


def _default_font():
    try:
        return tkfont.nametofont('TkFixedFont')
    except Exception:
        return tkfont.Font(family='Courier', size=10)


def _unbind_one(widget, seq, funcid):
    """Remove only our binding (tkinter 3.10's unbind(seq, funcid) clears all)."""
    try:
        script = widget.tk.call('bind', widget._w, seq)
        keep = [ln for ln in str(script).split('\n') if funcid not in ln]
        widget.tk.call('bind', widget._w, seq, '\n'.join(keep))
    except tk.TclError:
        pass
    try:
        widget.deletecommand(funcid)
    except Exception:
        pass


# --------------------------------------------------------------------------
# shared popup base
# --------------------------------------------------------------------------
class _DosBox(tk.Frame):
    """Cell-grid canvas popup with shadow, focus restore and outside-click handling."""

    _close_on_outside = False

    def __init__(self, parent, colors, font):
        tk.Frame.__init__(self, parent, bd=0, highlightthickness=0, padx=0, pady=0)
        self._parent = parent
        self.colors = dos_colors(colors)
        self._font = font or _default_font()
        self._cv = tk.Canvas(self, bd=0, highlightthickness=0, takefocus=True)
        self._cv.pack(side='top', anchor='nw')
        self._shadows = []
        self._is_open = False
        self._prev_focus = None
        self._after_ids = []
        self._out = None            # (toplevel, funcid)
        self._cols = 1
        self._rows = 1
        self._measure()
        self.configure(bg=self.colors['dos_menu_bg'])

    # -- metrics ------------------------------------------------------
    def _measure(self):
        try:
            self.cw = max(1, int(self._font.measure('M')))
            self.lh = max(1, int(self._font.metrics('linespace')))
        except Exception:
            self.cw, self.lh = 8, 16

    def _parent_size(self):
        p = self._parent
        try:
            p.update_idletasks()
            w, h = p.winfo_width(), p.winfo_height()
            if w <= 1 or h <= 1:
                w, h = p.winfo_reqwidth(), p.winfo_reqheight()
        except tk.TclError:
            w = h = 1
        if w <= 1:
            w = 800
        if h <= 1:
            h = 600
        return w, h

    # -- drawing primitives --------------------------------------------
    def _size_canvas(self, cols, rows):
        self._cols, self._rows = cols, rows
        self._wpx, self._hpx = cols * self.cw, rows * self.lh
        self._cv.configure(width=self._wpx, height=self._hpx, bg=self.colors['dos_menu_bg'])

    def _rect(self, col, row, ncols, bg, nrows=1, tag='deco'):
        if ncols <= 0 or not bg:
            return
        x, y = col * self.cw, row * self.lh
        self._cv.create_rectangle(x, y, x + ncols * self.cw - 1, y + nrows * self.lh - 1,
                                  fill=bg, outline=bg, width=1, tags=tag)

    def _text(self, col, row, s, fg, bg=None, font=None, tag='deco'):
        if not s:
            return
        if bg:
            self._rect(col, row, len(s), bg, tag=tag)
        if any(ch in _BLOCK_SHADES for ch in s):
            # shade blocks (pictures, gauges) are filled cells, so rows join up in any font
            base = bg or self.colors['dos_menu_bg']
            for i, ch in enumerate(s):
                part = _BLOCK_SHADES.get(ch)
                if part is not None:
                    x, y = (col + i) * self.cw, row * self.lh
                    self._cv.create_rectangle(x, y, x + self.cw, y + self.lh, fill=_blend(base, fg, part),
                                              outline='', tags=tag)
            s = ''.join(' ' if ch in _BLOCK_SHADES else ch for ch in s)
        self._cv.create_text(col * self.cw, row * self.lh, text=s, anchor='nw', fill=fg,
                             font=font or self._font, tags=tag)

    def _cells(self, col, row, s, fg, bg=None):
        """Draw one char per cell (guarantees alignment of box glyphs)."""
        if bg:
            self._rect(col, row, len(s), bg)
        for i, ch in enumerate(s):
            if ch != ' ':
                self._cv.create_text((col + i) * self.cw, row * self.lh, text=ch, anchor='nw',
                                     fill=fg, font=self._font, tags='deco')

    def _draw_frame(self, title, sep_rows=()):
        c = self.colors
        cols, rows = self._cols, self._rows
        tl, hz, tr, vt, bl, br = BOX_DOUBLE
        bg, bd = c['dos_menu_bg'], c['dos_menu_border']
        self._rect(0, 0, cols, bg, nrows=rows)
        title = ' %s ' % title if title else ''
        title = _trunc(title, max(0, cols - 4)) if title else ''
        left = (cols - 2 - len(title)) // 2
        top = tl + hz * left + ' ' * len(title) + hz * (cols - 2 - left - len(title)) + tr
        self._cells(0, 0, top[:cols], bd)
        if title:
            self._text(1 + left, 0, title, c['dos_menu_fg'], bg)
        for r in range(1, rows - 1):
            if r in sep_rows:
                self._cells(0, r, SEP_LEFT + SEP_FILL * (cols - 2) + SEP_RIGHT, bd)
            else:
                self._cells(0, r, vt, bd)
                self._cells(cols - 1, r, vt, bd)
        self._cells(0, rows - 1, bl + hz * (cols - 2) + br, bd)

    # -- placement / lifecycle -----------------------------------------
    def _place_box(self, x, y):
        pw, ph = self._parent_size()
        W, H = self._wpx, self._hpx
        if x is None:
            x = (pw - W) // 2
        if y is None:
            y = (ph - H) // 2
        try:
            x, y = int(x), int(y)
        except Exception:
            x, y = 0, 0
        x = max(0, min(x, pw - W - self.cw))
        y = max(0, min(y, ph - H - self.lh))
        self._drop_shadows()
        sh = self.colors['dos_shadow']
        for (sx, sy, sw, shh) in ((x + W, y + self.lh, self.cw, H),
                                  (x + self.cw, y + H, W, self.lh)):
            f = tk.Frame(self._parent, bg=sh, bd=0, highlightthickness=0)
            f.place(x=sx, y=sy, width=sw, height=shh)
            self._shadows.append(f)
        self.place(x=x, y=y)
        self.lift()

    def _drop_shadows(self):
        for f in self._shadows:
            try:
                f.destroy()
            except Exception:
                pass
        self._shadows = []

    def _begin_open(self):
        try:
            self._prev_focus = self._parent.focus_get()
        except Exception:
            self._prev_focus = None
        self._is_open = True

    def _arm_outside(self):
        if not self._close_on_outside:
            return

        def arm():
            self._after_ids = [a for a in self._after_ids if a != aid[0]]
            if self._is_open and self._out is None:
                try:
                    top = self.winfo_toplevel()
                    self._out = (top, top.bind('<ButtonPress-1>', self._on_outside, add='+'))
                except tk.TclError:
                    pass
        aid = [None]
        try:
            aid[0] = self.after_idle(arm)
            self._after_ids.append(aid[0])
        except tk.TclError:
            pass

    def _inside_parent(self, w):
        ps, ws = str(self._parent), str(w)
        return ps == '.' or ws == ps or ws.startswith(ps + '.')

    def _on_outside(self, event):
        if not self._is_open:
            return
        ws = str(event.widget)
        if ws == str(self) or ws.startswith(str(self) + '.'):
            return
        if self._inside_parent(event.widget):
            self.close()

    def _teardown(self):
        for a in self._after_ids:
            try:
                self.after_cancel(a)
            except Exception:
                pass
        self._after_ids = []
        if self._out is not None:
            top, fid = self._out
            self._out = None
            _unbind_one(top, '<ButtonPress-1>', fid)
        self._drop_shadows()

    def _finish_close(self):
        """Common close; returns True if it was open."""
        if not self._is_open:
            return False
        self._is_open = False
        self._teardown()
        try:
            self.place_forget()
        except tk.TclError:
            pass
        prev, self._prev_focus = self._prev_focus, None
        if prev is not None:
            try:
                if prev.winfo_exists():
                    prev.focus_set()
            except Exception:
                pass
        return True

    def is_open(self):
        return self._is_open

    def destroy(self):
        self._is_open = False
        self._teardown()
        try:
            tk.Frame.destroy(self)
        except tk.TclError:
            pass


# --------------------------------------------------------------------------
# DosMenu
# --------------------------------------------------------------------------
class DosMenu(_DosBox):
    _close_on_outside = True

    def __init__(self, parent, title, items, colors, font, on_close=None, min_width=0, initial=0):
        _DosBox.__init__(self, parent, colors, font)
        self._title = '' if title is None else str(title)
        self._on_close = on_close
        try:
            self._min_width = max(0, int(min_width))
        except Exception:
            self._min_width = 0
        self._items = self._norm(items)
        self._sel = -1
        self._off = 0
        self._vis = 1
        self._inner = 1
        self._select(self._first(), render=False)
        self._layout()
        self.select(initial, render=False)
        self._render()
        cv = self._cv
        cv.bind('<Key>', self._on_key)
        cv.bind('<Motion>', self._on_motion)
        cv.bind('<ButtonPress-1>', self._on_click)

    # -- items --------------------------------------------------------
    @staticmethod
    def _norm(items):
        out = []
        try:
            seq = list(items) if items is not None else []
        except Exception:
            seq = []
        for it in seq:
            if it is None:
                out.append(None)
                continue
            if not isinstance(it, dict):
                it = {'label': it}
            try:
                label = it.get('label', '')
                label = '' if label is None else str(label).replace('\n', ' ')
                hk = it.get('hotkey')
                hk = str(hk)[:1] if hk not in (None, '') else ''
                sc = it.get('shortcut')
                sc = '' if sc in (None, '') else str(sc)
                act = it.get('action')
                out.append({'label': label, 'hotkey': hk, 'shortcut': sc,
                            'action': act if callable(act) else None,
                            'checked': None if it.get('checked') is None else bool(it.get('checked')),
                            'swatch': DosMenu._swatch(it.get('swatch')),
                            'enabled': bool(it.get('enabled', True))})
            except Exception:
                out.append(None)
        return out

    @staticmethod
    def _swatch(v):
        return _hex(v, '') if isinstance(v, str) else ''

    def _selectable(self, i):
        it = self._items[i] if 0 <= i < len(self._items) else None
        return it is not None and it['enabled']

    def _first(self):
        for i in range(len(self._items)):
            if self._selectable(i):
                return i
        return -1

    def _last(self):
        for i in range(len(self._items) - 1, -1, -1):
            if self._selectable(i):
                return i
        return -1

    @property
    def selected(self):
        return self._sel

    # -- layout -------------------------------------------------------
    def _layout(self):
        pw, ph = self._parent_size()
        n = len(self._items)
        real = [i for i in self._items if i is not None]
        self._markw = 2 if any(i['checked'] is not None for i in real) else 0
        self._swatchw = 3 if any(i['swatch'] for i in real) else 0
        labw = max([len(i['label']) for i in real] or [0])
        shw = max([len(i['shortcut']) for i in real] or [0])
        inner = 1 + self._markw + self._swatchw + labw + ((2 + shw) if shw else 0) + 1
        title = self._title
        inner = max(inner, (len(title) + 4) if title else 0, self._min_width - 2, 4)
        maxcols = max(6, pw // self.cw - 1)
        total = min(inner + 2, maxcols)
        self._inner = total - 2
        max_rows = max(1, ph // self.lh - 3)
        self._vis = max(1, min(n, max_rows))
        self._size_canvas(total, self._vis + 2)
        self._fit_offset()

    def _fit_offset(self):
        n = len(self._items)
        if self._sel < 0:
            self._off = max(0, min(self._off, n - self._vis))
            return
        if self._sel < self._off:
            self._off = self._sel
        elif self._sel >= self._off + self._vis:
            self._off = self._sel - self._vis + 1
        self._off = max(0, min(self._off, max(0, n - self._vis)))
        if self._sel == self._first():
            self._off = 0
        if self._sel == self._last():
            self._off = max(0, n - self._vis)

    def _row_text(self, it):
        inner = self._inner
        sh = it['shortcut']
        right = (sh + ' ') if sh else ' '
        room = inner - 1 - self._markw - self._swatchw - len(right) - (1 if sh else 0)
        if room < 1 and sh:
            sh, right = '', ' '
            room = inner - 1 - self._markw - self._swatchw - 1
        room = max(1, room)
        lab = _trunc(it['label'], room)
        mark = ''
        if self._markw:
            mark = (CHECK_ON if it['checked'] else CHECK_OFF) + ' '
        s = ' ' + mark + ' ' * self._swatchw + lab.ljust(room) + (' ' if sh else '') + right
        return s[:inner].ljust(inner), lab

    def _render(self):
        cv, c = self._cv, self.colors
        cv.delete('deco')
        n = len(self._items)
        seps = set()
        for r in range(self._vis):
            i = self._off + r
            if i < n and self._items[i] is None:
                seps.add(r + 1)
        self._draw_frame(self._title, seps)
        bg = c['dos_menu_bg']
        self.swatch_cells = []      # (row, col, colour) of drawn swatches (introspection / tests)
        for r in range(self._vis):
            i = self._off + r
            if i >= n:
                break
            it = self._items[i]
            if it is None:
                continue
            row = r + 1
            sel = (i == self._sel)
            if not it['enabled']:
                fg, rbg = c['dos_menu_dim'], bg
            elif sel:
                fg, rbg = c['dos_menu_sel_fg'], c['dos_menu_sel_bg']
            else:
                fg, rbg = c['dos_menu_fg'], bg
            text, lab = self._row_text(it)
            self._text(1, row, text, fg, rbg)
            if it['swatch'] and self._swatchw:
                scol = 2 + self._markw
                x, y = scol * self.cw, row * self.lh
                cv.create_rectangle(x + 1, y + 1, x + 2 * self.cw - 2, y + self.lh - 2,
                                    fill=it['swatch'], outline=fg, width=1, tags='deco')
                self.swatch_cells.append((row, scol, it['swatch']))
            hk = it['hotkey']
            if hk:
                idx = lab.lower().find(hk.lower())
                if idx >= 0 and lab[idx] != ELLIPSIS:
                    col = 1 + 1 + self._markw + self._swatchw + idx
                    hfg = c['dos_key_fg']
                    if sel:
                        hfg = '#aa0000'
                    if not it['enabled']:
                        hfg = c['dos_menu_dim']
                    self._text(col, row, lab[idx], hfg, rbg)
        bd = c['dos_menu_border']
        if self._off > 0:
            self._cells(self._cols - 1, 1, '▲', bd, bg)
        if self._off + self._vis < n:
            self._cells(self._cols - 1, self._vis, '▼', bd, bg)

    # -- selection ----------------------------------------------------
    def _select(self, i, render=True):
        self._sel = i
        self._fit_offset()
        if render:
            self._render()

    def select(self, index, render=True):
        """Pre-select an item: index is clamped, then moved to the nearest selectable item."""
        n = len(self._items)
        if n == 0 or self._first() < 0:
            return
        try:
            i = max(0, min(n - 1, int(index)))
        except Exception:
            i = self._first()
        if not self._selectable(i):
            cand = [j for j in range(n) if self._selectable(j)]
            i = min(cand, key=lambda j: (abs(j - i), j))
        if not (self._off <= i < self._off + self._vis):
            self._off = i - self._vis // 2
        self._select(i, render=render)

    def _move(self, delta):
        n = len(self._items)
        if n == 0 or self._first() < 0:
            return
        i = self._sel
        for _ in range(n):
            i = (i + delta) % n
            if self._selectable(i):
                break
        self._select(i)

    def _page(self, direction):
        if self._first() < 0:
            return
        n = len(self._items)
        step = max(1, self._vis - 1)
        t = max(0, min(n - 1, max(self._sel, 0) + direction * step))
        # snap to nearest selectable in the travel direction, else opposite
        for rng in ((range(t, n) if direction > 0 else range(t, -1, -1)),
                    (range(t, -1, -1) if direction > 0 else range(t, n))):
            for i in rng:
                if self._selectable(i):
                    self._select(i)
                    return

    # -- events -------------------------------------------------------
    def _on_key(self, e):
        ks, ch = e.keysym, e.char
        if ks in ('Left', 'Right') and _alt_down(e):
            if ks == 'Left':
                self.close()                                       # back (the same as Esc)
            else:                                                  # next: go into the entry if it leads somewhere
                it = self._items[self._sel] if 0 <= self._sel < len(self._items) else None
                if it is not None and it['enabled'] and str(it['label']).rstrip().endswith(('...', '>')):
                    self._activate(self._sel)
            return 'break'
        if ks == 'Up':
            self._move(-1)
        elif ks == 'Down':
            self._move(1)
        elif ks == 'Home':
            self._select(self._first())
        elif ks == 'End':
            self._select(self._last())
        elif ks in ('Prior', 'KP_Prior'):
            self._page(-1)
        elif ks in ('Next', 'KP_Next'):
            self._page(1)
        elif ks in ('Return', 'KP_Enter', 'space'):
            self._activate(self._sel)
        elif ks == 'Escape':
            self.close()
        elif ch and len(ch) == 1 and ch.isprintable():
            low = ch.lower()
            for i, it in enumerate(self._items):
                if it is not None and it['enabled'] and it['hotkey'] and it['hotkey'].lower() == low:
                    self._activate(i)
                    break
        return 'break'

    def _index_at(self, e):
        col, row = int(e.x) // self.cw, int(e.y) // self.lh
        if row < 1 or row > self._vis or col < 1 or col > self._cols - 2:
            return -1
        i = self._off + row - 1
        return i if 0 <= i < len(self._items) else -1

    def _on_motion(self, e):
        i = self._index_at(e)
        if i >= 0 and self._selectable(i) and i != self._sel:
            self._select(i)

    def _on_click(self, e):
        i = self._index_at(e)
        if i >= 0:
            self._activate(i)
        try:
            self._cv.focus_set()
        except tk.TclError:
            pass

    def _activate(self, i):
        if not self._selectable(i):
            return
        action = self._items[i]['action']
        self.close()
        if action is not None:
            action()

    # -- public -------------------------------------------------------
    def open(self, x=None, y=None):
        if self._is_open:
            self.close()
        self._begin_open()
        self._layout()
        if self._sel < 0 or not self._selectable(self._sel):
            self._sel = self._first()
        self._fit_offset()
        self._render()
        self._place_box(x, y)
        self._arm_outside()
        try:
            self.update_idletasks()
            self._cv.focus_set()
        except tk.TclError:
            pass

    def close(self):
        if not self._finish_close():
            return
        cb = self._on_close
        if callable(cb):
            cb()

    def restyle(self, colors, font=None):
        self.colors = dos_colors(colors)
        if font is not None:
            self._font = font
        self._measure()
        self.configure(bg=self.colors['dos_menu_bg'])
        self._layout()
        self._render()
        if self._is_open:
            self._place_box(self.winfo_x(), self.winfo_y())


# --------------------------------------------------------------------------
# DosDialog
# --------------------------------------------------------------------------
class DosDialog(_DosBox):
    """Modal-looking form.  `width` is the total width in character cells (incl. border)."""

    def __init__(self, parent, title, fields, buttons, colors, font, on_result,
                 width=None, message=None, esc_result=None):
        _DosBox.__init__(self, parent, colors, font)
        self._title = '' if title is None else str(title)
        self._on_result = on_result
        self._width = width
        self._message = '' if message is None else str(message)
        self._esc = esc_result
        self._done = False
        self._fields = []
        self._entries = {}
        for f in (fields or []):
            if not isinstance(f, dict):
                continue
            t = f.get('type') if f.get('type') in ('check', 'pick') else 'text'
            try:
                fw = int(f.get('width') or 20)
            except Exception:
                fw = 20
            fd = {'key': str(f.get('key', '')), 'label': str(f.get('label', '')), 'type': t,
                  'width': max(1, fw), 'secret': bool(f.get('secret')),
                  'value': f.get('value'), 'mark': str(f.get('mark', '\u25bc'))[:1] or '\u25bc'}
            self._fields.append(fd)
        self._buttons = []
        for b in (buttons or []):
            try:
                label, res = str(b[0]), b[1]
                hk = str(b[2])[:1].lower() if len(b) > 2 and b[2] else (label[:1].lower())
            except Exception:
                continue
            self._buttons.append({'label': label, 'result': res, 'hotkey': hk})
        self._stops = ([('field', i) for i in range(len(self._fields))] +
                       [('button', i) for i in range(len(self._buttons))])
        self._fi = 0
        self._hits = []
        for i, fd in enumerate(self._fields):
            if fd['type'] == 'check':
                fd['state'] = bool(fd['value'])
            elif fd['type'] == 'pick':
                fd['shown'] = '' if fd['value'] is None else str(fd['value'])
            else:
                e = tk.Entry(self._cv, bd=0, highlightthickness=0, relief='flat',
                             show='*' if fd['secret'] else '')
                v = fd['value']
                e.insert(0, '' if v is None else str(v))
                for seq in ('<Tab>', '<ISO_Left_Tab>', '<Up>', '<Down>', '<Return>', '<KP_Enter>',
                            '<Escape>', '<Alt-Key>'):
                    try:
                        e.bind(seq, self._on_entry_key)
                    except tk.TclError:
                        pass     # keysym unknown on this platform (ISO_Left_Tab on Windows)
                e.bind('<FocusIn>', lambda ev, i=i: self._entry_focus(i))
                self._entries[i] = e
                fd['entry'] = e
        cv = self._cv
        cv.bind('<Key>', self._on_key)
        cv.bind('<Alt-Key>', self._on_alt)
        cv.bind('<ButtonPress-1>', self._on_click)
        self._layout()
        self._render()

    # -- layout -------------------------------------------------------
    def _layout(self):
        pw, ph = self._parent_size()
        pcols = max(12, pw // self.cw - 1)
        fields, buttons = self._fields, self._buttons
        labw = max([len(f['label']) for f in fields if f['type'] in ('text', 'pick')] or [0])
        # natural content width
        need = [len(self._title) + 6]
        for f in fields:
            if f['type'] == 'check':
                need.append(4 + len(f['label']) + 2)
            else:
                need.append(2 + labw + 1 + f['width'] + 2)
        btn_w = sum(len(b['label']) + 4 for b in buttons) + 2 * max(0, len(buttons) - 1)
        need.append(btn_w + 4)
        paras = self._message.split('\n')
        msg_lines_nat = max([len(l) for l in paras if not _is_columns(l)] or [0])
        need.append(min(msg_lines_nat + 4, 60))
        # lines laid out in columns (two or more spaces inside) are never wrapped: the box grows to hold them
        need.append(max([len(l[1:].rstrip()) for l in paras if _is_columns(l)] or [0]) + 4
                    if any(map(_is_columns, paras)) else 0)
        if self._width:
            try:
                total = int(self._width)
            except Exception:
                total = max(need)
        else:
            total = max(need)
        total = max(8, min(total, pcols))
        self._total = total
        wrap_w = max(4, total - 4)
        lines = []
        if self._message:
            for para in self._message.split('\n'):
                if _is_columns(para):                      # columns: never wrapped; cut cleanly if still too long
                    lines.append(_trunc(para[1:].rstrip(), wrap_w))
                else:
                    lines.extend(textwrap.wrap(para, wrap_w, break_long_words=True) or [''])
        self._msg_lines = lines
        # rows
        row = 1
        self._blank_top = row
        row += 1
        self._msg_row = row
        row += len(lines)
        if lines:
            row += 1
        self._field_rows = []
        for f in fields:
            self._field_rows.append(row)
            row += 1
        if fields:
            row += 1
        self._btn_row = row
        row += 1 if buttons else 0
        if buttons:
            row += 1
        rows = row + 1
        self._size_canvas(total, rows)
        self._labw = labw
        self._ecol = 2 + labw + 1
        # (re)create entry windows
        self._cv.delete('all')
        for i, f in enumerate(fields):
            if f['type'] == 'pick':
                f['fw'] = max(1, min(f['width'], total - 2 - self._ecol - 1))
                continue
            if f['type'] != 'text':
                continue
            fw = max(1, min(f['width'], total - 2 - self._ecol - 1))
            f['fw'] = fw
            self._cv.create_window(self._ecol * self.cw, self._field_rows[i] * self.lh, anchor='nw',
                                   window=f['entry'], width=fw * self.cw, height=self.lh,
                                   tags='win')
        self._style_entries()

    def _style_entries(self):
        c = self.colors
        for i, f in enumerate(self._fields):
            if f['type'] != 'text':
                continue
            focused = self._stops and self._stops[self._fi] == ('field', i) if self._stops else False
            bg = c['dos_menu_sel_bg'] if focused else c['input_bg']
            fg = c['dos_menu_sel_fg'] if focused else c['input_fg']
            try:
                f['entry'].configure(bg=bg, fg=fg, font=self._font, insertwidth=self.cw,
                                     insertbackground=c['dos_key_fg'] if not focused else '#aa0000',
                                     selectbackground=c['dos_menu_fg'],
                                     selectforeground=c['dos_menu_bg'],
                                     disabledbackground=bg, insertofftime=300, insertontime=600)
            except tk.TclError:
                pass

    def _cur(self):
        return self._stops[self._fi] if self._stops else (None, -1)

    def _render(self):
        c = self.colors
        cv = self._cv
        cv.delete('deco')
        self._hits = []
        self._draw_frame(self._title)
        bg, fg = c['dos_menu_bg'], c['dos_menu_fg']
        for k, line in enumerate(self._msg_lines):
            self._text(2, self._msg_row + k, line[:self._total - 4], fg, bg)
        kind, idx = self._cur()
        for i, f in enumerate(self._fields):
            r = self._field_rows[i]
            focused = (kind, idx) == ('field', i)
            if f['type'] == 'check':
                s = ('[%s] %s' % ('x' if f['state'] else ' ', f['label']))
                s = _trunc(s, self._total - 4)
                self._text(2, r, s, c['dos_menu_sel_fg'] if focused else fg,
                           c['dos_menu_sel_bg'] if focused else bg)
                self._hits.append(('check', i, 2, 2 + len(s), r))
            elif f['type'] == 'pick':
                self._text(2, r, _trunc(f['label'], self._labw).ljust(self._labw), fg, bg)
                fw = f.get('fw', 1)
                cell = _trunc(f['shown'], max(1, fw - 2)).ljust(max(1, fw - 2)) + ' ' + f['mark']
                self._text(self._ecol, r, cell, c['dos_menu_sel_fg'] if focused else c['input_fg'],
                           c['dos_menu_sel_bg'] if focused else c['input_bg'])
                self._hits.append(('pick', i, self._ecol, self._ecol + fw, r))
            else:
                self._text(2, r, _trunc(f['label'], self._labw).ljust(self._labw), fg, bg)
                self._hits.append(('field', i, self._ecol, self._ecol + f.get('fw', 1), r))
        # buttons
        if self._buttons:
            labels = ['[ %s ]' % b['label'] for b in self._buttons]
            total = sum(len(s) for s in labels) + 2 * (len(labels) - 1)
            col = max(1, (self._total - total) // 2)
            for i, (s, b) in enumerate(zip(labels, self._buttons)):
                focused = (kind, idx) == ('button', i)
                s = s[:max(0, self._total - 1 - col)]
                bfg = c['dos_menu_sel_fg'] if focused else fg
                bbg = c['dos_menu_sel_bg'] if focused else bg
                self._text(col, self._btn_row, s, bfg, bbg)
                p = b['label'].lower().find(b['hotkey'])
                if p >= 0 and 2 + p < len(s):
                    self._text(col + 2 + p, self._btn_row, b['label'][p],
                               '#aa0000' if focused else c['dos_key_fg'], bbg)
                self._hits.append(('button', i, col, col + len(s), self._btn_row))
                col += len(labels[i]) + 2

    # -- focus --------------------------------------------------------
    def _set_focus(self, i):
        if not self._stops:
            return
        self._fi = i % len(self._stops)
        kind, idx = self._cur()
        self._style_entries()
        self._render()
        try:
            if kind == 'field' and self._fields[idx]['type'] == 'text':
                e = self._fields[idx]['entry']
                e.focus_set()
                e.selection_range(0, 'end')
                e.icursor('end')
            else:
                self._cv.focus_set()
        except tk.TclError:
            pass

    def _entry_focus(self, i):
        try:
            j = self._stops.index(('field', i))
            if self.focus_get() is not self._entries.get(i):
                return          # stale FocusIn (focus already moved on)
        except (ValueError, KeyError):
            return
        if j != self._fi:
            self._fi = j
            self._style_entries()
            self._render()
        else:
            self._style_entries()

    def _step(self, d):
        self._set_focus(self._fi + d)

    # -- results ------------------------------------------------------
    def values(self):
        out = {}
        for f in self._fields:
            if f['type'] == 'check':
                out[f['key']] = bool(f['state'])
            elif f['type'] == 'pick':
                out[f['key']] = f['shown']
            else:
                try:
                    out[f['key']] = f['entry'].get()
                except tk.TclError:
                    out[f['key']] = ''
        return out

    def _first_button(self):
        return self._buttons[0]['result'] if self._buttons else None

    def _finish(self, result):
        if self._done:
            return
        self._done = True
        vals = self.values()
        self.close()
        cb = self._on_result
        if callable(cb):
            cb(result, vals)

    def _press(self, bi):
        if 0 <= bi < len(self._buttons):
            self._finish(self._buttons[bi]['result'])

    def _enter(self):
        kind, idx = self._cur()
        if kind == 'button':
            self._press(idx)
        elif kind == 'field' and self._fields[idx]['type'] == 'pick':
            self._finish(('pick', self._fields[idx]['key']))        # the caller opens a list or an editor
        elif self._buttons:
            self._press(0)

    def _escape(self):
        names = [b['result'] for b in self._buttons]
        target = self._esc if self._esc is not None else 'cancel'
        if target in names:
            self._finish(target)
        else:
            self.close()

    def _hotkey(self, ch):
        low = ch.lower()
        for i, b in enumerate(self._buttons):
            if b['hotkey'] == low:
                self._press(i)
                return True
        return False

    # -- events -------------------------------------------------------
    def _nav(self, direction):
        """Alt+Left / Alt+Right: press the dialog's Back / Next button if it has one (Left falls back to Esc)."""
        names = {-1: ('back', 'prev', 'previous'), 1: ('next', 'more')}[direction]
        for i, b in enumerate(self._buttons):
            if str(b['result']).lower() in names:
                self._press(i)
                return True
        if direction < 0:
            self._escape()
            return True
        return False

    def _common(self, e):
        ks = e.keysym
        if ks in ('Left', 'Right') and _alt_down(e):
            self._nav(-1 if ks == 'Left' else 1)
        elif ks in ('Tab', 'ISO_Left_Tab'):
            back = ks == 'ISO_Left_Tab' or bool(e.state & 0x1)
            self._step(-1 if back else 1)
        elif ks == 'Down':
            self._step(1)
        elif ks == 'Up':
            self._step(-1)
        elif ks in ('Return', 'KP_Enter'):
            self._enter()
        elif ks == 'Escape':
            self._escape()
        else:
            return False
        return True

    def _on_entry_key(self, e):
        if e.keysym.startswith('Alt') or (e.state & 0x20000 and len(e.keysym) == 1):
            if len(e.keysym) == 1:
                self._hotkey(e.keysym)
            return 'break'
        self._common(e)
        return 'break'

    def _on_alt(self, e):
        if e.keysym in ('Left', 'Right'):
            self._nav(-1 if e.keysym == 'Left' else 1)
        elif len(e.keysym) == 1:
            self._hotkey(e.keysym)
        return 'break'

    def _on_key(self, e):
        if self._common(e):
            return 'break'
        ks = e.keysym
        kind, idx = self._cur()
        if ks in ('Left', 'Right') and kind == 'button':
            self._set_focus(self._fi + (1 if ks == 'Right' else -1)
                            if 0 <= idx + (1 if ks == 'Right' else -1) < len(self._buttons)
                            else self._fi)
        elif ks == 'space':
            if kind == 'button':
                self._press(idx)
            elif kind == 'field' and self._fields[idx]['type'] == 'check':
                self._toggle(idx)
            elif kind == 'field' and self._fields[idx]['type'] == 'pick':
                self._finish(('pick', self._fields[idx]['key']))
        elif e.char and len(e.char) == 1 and e.char.isprintable():
            self._hotkey(e.char)
        return 'break'

    def _toggle(self, i):
        self._fields[i]['state'] = not self._fields[i]['state']
        self._render()

    def _on_click(self, e):
        col, row = int(e.x) // self.cw, int(e.y) // self.lh
        for kind, i, c0, c1, r in self._hits:
            if r == row and c0 <= col < c1:
                if kind == 'button':
                    self._press(i)
                elif kind == 'check':
                    self._set_focus(self._stops.index(('field', i)))
                    self._toggle(i)
                elif kind == 'pick':
                    self._set_focus(self._stops.index(('field', i)))
                    self._finish(('pick', self._fields[i]['key']))
                else:
                    self._set_focus(self._stops.index(('field', i)))
                return
        try:
            self._cv.focus_set()
        except tk.TclError:
            pass

    # -- public -------------------------------------------------------
    def open(self, x=None, y=None):
        if self._is_open:
            self.close()
        self._done = False
        self._begin_open()
        self._layout()
        self._fi = 0
        self._style_entries()
        self._render()
        self._place_box(x, y)
        self._arm_outside()
        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        if self._stops:
            self._set_focus(0)
        else:
            try:
                self._cv.focus_set()
            except tk.TclError:
                pass

    def close(self):
        self._finish_close()

    def restyle(self, colors, font=None):
        self.colors = dos_colors(colors)
        if font is not None:
            self._font = font
        self._measure()
        self.configure(bg=self.colors['dos_menu_bg'])
        self._layout()
        self._render()
        if self._is_open:
            self._place_box(self.winfo_x(), self.winfo_y())


# --------------------------------------------------------------------------
# DosColorPicker
# --------------------------------------------------------------------------
_PARTIAL = ' ▏▎▍▌▋▊▉'


def _chan_bar(v, width=16):
    """Bar of exactly `width` cells for a 0..255 value (255 = completely full)."""
    f = max(0, min(255, int(v))) * width / 255.0
    full = min(width, int(f))
    part = int((f - full) * 8) if full < width else 0
    out = GAUGE_FULL * full
    if full < width:
        out += _PARTIAL[part] if part else GAUGE_EMPTY
        out += GAUGE_EMPTY * (width - full - 1)
    return out


class DosColorPicker(_DosBox):
    """'Mix a colour' box.  on_change(hex) on every change of the current value (not on open);
    on_result('ok', current_hex) / ('cancel', original_hex) once, after the box has closed."""

    BAR = 16
    TOTAL = 34
    CX = 3                      # left content column
    _BUTTONS = (('OK', 'ok', 'o'), ('Reset', 'reset', 'r'), ('Cancel', 'cancel', 'c'))

    def __init__(self, parent, title, initial, colors, font, on_result, on_change=None):
        _DosBox.__init__(self, parent, colors, font)
        self._title = '' if title is None else str(title)
        self._on_result = on_result
        self._on_change = on_change
        self._orig = parse_hex_color(initial) or '#000000'
        self._cur_hex = self._orig
        self._done = False
        self._fi = 0                    # 0..2 channels, 3 hex, 4.. buttons
        self._drag = None
        self._hits = []
        self._syncing = False
        self._var = tk.StringVar(self, self._orig)
        self._entry = tk.Entry(self._cv, bd=0, highlightthickness=0, relief='flat',
                               textvariable=self._var)
        for seq in ('<Tab>', '<ISO_Left_Tab>', '<Up>', '<Down>', '<Return>', '<KP_Enter>',
                    '<Escape>', '<Alt-Key>'):
            try:
                self._entry.bind(seq, self._on_entry_key)
            except tk.TclError:
                pass
        self._entry.bind('<FocusIn>', self._entry_focus)
        self._var.trace_add('write', self._on_var)
        cv = self._cv
        cv.bind('<Key>', self._on_key)
        cv.bind('<Alt-Key>', self._on_alt)
        cv.bind('<ButtonPress-1>', self._on_press)
        cv.bind('<B1-Motion>', self._on_drag)
        cv.bind('<ButtonRelease-1>', self._on_release)
        self._layout()
        self._render()

    # -- value --------------------------------------------------------
    def _rgb(self):
        h = self._cur_hex
        return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)

    def value(self):
        return self._cur_hex

    def set_value(self, hex_value):
        h = parse_hex_color(hex_value)
        if h is None or h == self._cur_hex:
            return
        self._cur_hex = h
        self._sync_entry()
        self._render()
        cb = self._on_change
        if callable(cb):
            cb(h)

    def _set_channel(self, ch, v):
        rgb = list(self._rgb())
        rgb[ch] = max(0, min(255, int(v)))
        self.set_value('#%02x%02x%02x' % tuple(rgb))

    def _sync_entry(self, force=False):
        """Mirror the current value into the entry (unless the entry already means it)."""
        try:
            if not force and parse_hex_color(self._var.get()) == self._cur_hex:
                return
            self._syncing = True
            try:
                self._var.set(self._cur_hex)
            finally:
                self._syncing = False
        except tk.TclError:
            pass

    def _on_var(self, *a):
        if self._syncing:
            return
        try:
            text = self._var.get()
        except tk.TclError:
            return
        h = parse_hex_color(text)
        self._style_entry(h is not None)
        if h is not None:
            self.set_value(h)

    # -- layout -------------------------------------------------------
    def _layout(self):
        self._total = max(self.TOTAL, len(self._title) + 6)
        self._rows_ch = (2, 3, 4)
        self._hex_row = 6
        self._lbl_row = 8
        self._pv_row = 9
        self._btn_row = 13
        self._size_canvas(self._total, 16)
        self._cv.delete('all')
        self._ecol = self.CX + 5
        self._cv.create_window(self._ecol * self.cw, self._hex_row * self.lh, anchor='nw',
                               window=self._entry, width=9 * self.cw, height=self.lh, tags='win')
        self._style_entry()

    def _style_entry(self, valid=None):
        c = self.colors
        if valid is None:
            try:
                valid = parse_hex_color(self._var.get()) is not None
            except tk.TclError:
                valid = True
        focused = self._fi == 3
        bg = c['dos_menu_sel_bg'] if focused else c['input_bg']
        fg = c['dos_menu_sel_fg'] if focused else c['input_fg']
        if not valid:
            fg = '#aa0000' if focused else c['alert']
        try:
            self._entry.configure(bg=bg, fg=fg, font=self._font, insertwidth=self.cw,
                                  insertbackground='#aa0000' if focused else c['dos_key_fg'],
                                  selectbackground=c['dos_menu_fg'],
                                  selectforeground=c['dos_menu_bg'],
                                  insertofftime=300, insertontime=600)
        except tk.TclError:
            pass

    def _bar_col(self):
        return self.CX + 2

    def _render(self):
        c = self.colors
        cv = self._cv
        cv.delete('deco')
        self._hits = []
        self._draw_frame(self._title)
        bg, fg = c['dos_menu_bg'], c['dos_menu_fg']
        sel_bg, sel_fg = c['dos_menu_sel_bg'], c['dos_menu_sel_fg']
        rgb = self._rgb()
        for k, (name, v) in enumerate(zip('RGB', rgb)):
            r = self._rows_ch[k]
            foc = self._fi == k
            b0 = self._bar_col()
            self._text(self.CX, r, name, sel_fg if foc else fg, sel_bg if foc else bg)
            for i, ch in enumerate(_chan_bar(v, self.BAR)):
                x, y = (b0 + i) * self.cw, r * self.lh
                if ch == GAUGE_FULL:
                    self._rect(b0 + i, r, 1, fg)
                elif ch == GAUGE_EMPTY:
                    cv.create_text(x, y, text=ch, anchor='nw', fill=c['dos_menu_dim'],
                                   font=self._font, tags='deco')
                else:       # partial block: exact pixel fraction of the cell, 1/8 steps
                    pw = max(1, self.cw * _PARTIAL.index(ch) // 8)
                    cv.create_rectangle(x, y, x + pw - 1, y + self.lh - 1, fill=fg, outline=fg,
                                        width=1, tags='deco')
            self._text(b0 + self.BAR + 1, r, '%3d' % v, sel_fg if foc else fg, sel_bg if foc else bg)
            self._hits.append(('chan', k, self.CX, b0 + self.BAR + 4, r))
        foc = self._fi == 3
        self._text(self.CX, self._hex_row, 'Hex', sel_fg if foc else fg, sel_bg if foc else bg)
        self._hits.append(('hex', 0, self.CX, self._ecol + 9, self._hex_row))
        # previews
        bw, gap = 12, 4
        x0 = self.CX
        for tag, label, col, colour in (('pv_new', 'New', x0, self._cur_hex),
                                        ('pv_old', 'Old', x0 + bw + gap, self._orig)):
            self._text(col, self._lbl_row, label, fg, bg)
            cv.create_rectangle(col * self.cw, self._pv_row * self.lh,
                                (col + bw) * self.cw - 1, (self._pv_row + 3) * self.lh - 1,
                                fill=colour, outline=c['dos_menu_border'], width=1,
                                tags=('deco', tag))
        # buttons
        labels = ['[ %s ]' % b[0] for b in self._BUTTONS]
        total = sum(len(s) for s in labels) + 2 * (len(labels) - 1)
        col = max(1, (self._total - total) // 2)
        for i, (s, b) in enumerate(zip(labels, self._BUTTONS)):
            foc = self._fi == 4 + i
            s = s[:max(0, self._total - 1 - col)]
            bfg, bbg = (sel_fg, sel_bg) if foc else (fg, bg)
            self._text(col, self._btn_row, s, bfg, bbg)
            p = b[0].lower().find(b[2])
            if p >= 0 and 2 + p < len(s):
                self._text(col + 2 + p, self._btn_row, b[0][p],
                           '#aa0000' if foc else c['dos_key_fg'], bbg)
            self._hits.append(('button', i, col, col + len(s), self._btn_row))
            col += len(labels[i]) + 2

    # -- focus --------------------------------------------------------
    def _set_focus(self, i):
        self._fi = i % (4 + len(self._BUTTONS))
        self._style_entry()
        self._render()
        try:
            if self._fi == 3:
                self._entry.focus_set()
                self._entry.selection_range(0, 'end')
                self._entry.icursor('end')
            else:
                self._cv.focus_set()
        except tk.TclError:
            pass

    def _entry_focus(self, e=None):
        try:
            if self.focus_get() is not self._entry:
                return
        except (tk.TclError, KeyError):
            return
        if self._fi != 3:
            self._fi = 3
            self._render()
        self._style_entry()

    # -- results ------------------------------------------------------
    def _finish(self, name):
        if self._done or not self._is_open:
            return
        self._done = True
        res = self._cur_hex if name == 'ok' else self._orig
        self.close()
        cb = self._on_result
        if callable(cb):
            cb(name, res)

    def _press(self, bi):
        name = self._BUTTONS[bi][1]
        if name == 'reset':
            self.set_value(self._orig)
            self._sync_entry(force=True)
            self._style_entry()
        else:
            self._finish(name)

    def _hotkey(self, ch):
        low = ch.lower()
        for i, b in enumerate(self._BUTTONS):
            if b[2] == low:
                self._press(i)
                return True
        return False

    # -- events -------------------------------------------------------
    def _common(self, e):
        ks = e.keysym
        if ks in ('Tab', 'ISO_Left_Tab'):
            back = ks == 'ISO_Left_Tab' or bool(e.state & 0x1)
            self._set_focus(self._fi + (-1 if back else 1))
        elif ks == 'Down':
            self._set_focus(self._fi + 1)
        elif ks == 'Up':
            self._set_focus(self._fi - 1)
        elif ks in ('Return', 'KP_Enter'):
            if self._fi >= 4:
                self._press(self._fi - 4)
            else:
                self._finish('ok')
        elif ks == 'Escape':
            self._finish('cancel')
        else:
            return False
        return True

    def _on_entry_key(self, e):
        if e.keysym.startswith('Alt') or (e.state & 0x20000 and len(e.keysym) == 1):
            if len(e.keysym) == 1:
                self._hotkey(e.keysym)
            return 'break'
        self._common(e)
        return 'break'

    def _on_alt(self, e):
        if len(e.keysym) == 1:
            self._hotkey(e.keysym)
        return 'break'

    def _on_key(self, e):
        if self._common(e):
            return 'break'
        ks = e.keysym
        big = bool(e.state & 0x5)       # Shift or Ctrl
        if self._fi < 3:
            k = self._fi
            cur = self._rgb()[k]
            if ks in ('Left', 'KP_Left'):
                self._set_channel(k, cur - (16 if big else 1))
            elif ks in ('Right', 'KP_Right'):
                self._set_channel(k, cur + (16 if big else 1))
            elif ks in ('Prior', 'KP_Prior'):
                self._set_channel(k, cur + 16)
            elif ks in ('Next', 'KP_Next'):
                self._set_channel(k, cur - 16)
            elif ks in ('Home', 'KP_Home'):
                self._set_channel(k, 0)
            elif ks in ('End', 'KP_End'):
                self._set_channel(k, 255)
        elif self._fi >= 4:
            bi = self._fi - 4
            if ks == 'Left' and bi > 0:
                self._set_focus(self._fi - 1)
            elif ks == 'Right' and bi < len(self._BUTTONS) - 1:
                self._set_focus(self._fi + 1)
            elif ks == 'space':
                self._press(bi)
        return 'break'

    def _value_at(self, x):
        b0 = self._bar_col() * self.cw
        frac = (float(x) - b0) / float(max(1, self.BAR * self.cw - 1))
        return int(round(max(0.0, min(1.0, frac)) * 255))

    def _on_press(self, e):
        col, row = int(e.x) // self.cw, int(e.y) // self.lh
        for kind, i, c0, c1, r in self._hits:
            if r == row and c0 <= col < c1:
                if kind == 'button':
                    self._press(i)
                    return
                if kind == 'chan':
                    self._set_focus(i)
                    if col >= self._bar_col() and col < self._bar_col() + self.BAR:
                        self._drag = i
                        self._set_channel(i, self._value_at(e.x))
                else:
                    self._set_focus(3)
                return
        try:
            self._cv.focus_set()
        except tk.TclError:
            pass

    def _on_drag(self, e):
        if self._drag is not None and self._is_open:
            self._set_channel(self._drag, self._value_at(e.x))

    def _on_release(self, e):
        self._drag = None

    # -- public -------------------------------------------------------
    def open(self, x=None, y=None):
        if self._is_open:
            self.close()
        self._done = False
        self._drag = None
        self._begin_open()
        self._cur_hex = self._orig
        self._sync_entry()
        self._layout()
        self._fi = 0
        self._style_entry()
        self._render()
        self._place_box(x, y)
        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        self._set_focus(0)

    def close(self):
        """Close silently (no on_result); use Esc / buttons for a result."""
        self._drag = None
        self._finish_close()

    def destroy(self):
        self._done = True
        self._on_change = None
        self._on_result = None
        _DosBox.destroy(self)

    def restyle(self, colors, font=None):
        self.colors = dos_colors(colors)
        if font is not None:
            self._font = font
        self._measure()
        self.configure(bg=self.colors['dos_menu_bg'])
        self._layout()
        self._render()
        if self._is_open:
            self._place_box(self.winfo_x(), self.winfo_y())


# --------------------------------------------------------------------------
# DosTable
# --------------------------------------------------------------------------
_TABLE_ROLES = ('normal', 'dim', 'good', 'warn', 'bad')
_TABLE_NAV = {'Up': 'up', 'KP_Up': 'up', 'Down': 'down', 'KP_Down': 'down',
              'Prior': 'pgup', 'KP_Prior': 'pgup', 'Next': 'pgdn', 'KP_Next': 'pgdn',
              'Home': 'home', 'KP_Home': 'home', 'End': 'end', 'KP_End': 'end'}
_TABLE_KEYS = {'Return': 'select', 'KP_Enter': 'select', 'Escape': 'close', 'a': 'add',
               'Insert': 'add', 'e': 'edit', 'Delete': 'remove', 'r': 'remove'}
_TABLE_SEP = ' │ '          # (drawn as spaces in the row text; the rule is a separate cell)
_TABLE_WHEEL = 3            # rows per wheel notch
_TABLE_EMPTY = '(empty)'


class DosTable(_DosBox):
    """Keyboard-driven list/table ('dialing directory').

    on_action(action_name, selected_index_or_None, table) is called for every mapped key
    (default map: Return/KP_Enter select, Escape close, a/Insert add, e edit, Delete/r remove);
    'close' closes the table first and passes None.  Other actions leave the table open.
    Navigation (Up/Down/PageUp/PageDown/Home/End, mouse wheel, click, double-click) is built in.
    Row indices refer to the rows after None entries were dropped."""

    _close_on_outside = False

    def __init__(self, parent, title, columns, rows, colors, font, on_action, keys=None,
                 hints=None, min_width=0, height=None, selected=0):
        _DosBox.__init__(self, parent, colors, font)
        self._dead = False
        self._title = '' if title is None else str(title).replace('\n', ' ')
        self._on_action = on_action
        self._colspec = self._norm_columns(columns)
        self._data = self._norm_rows(rows)
        self._keymap = self._norm_keys(keys)
        self._hints = self._norm_hints(hints)
        try:
            self._min_width = max(0, int(min_width))
        except Exception:
            self._min_width = 0
        try:
            h = int(height) if height is not None else None
            self._height = h if h is not None and h >= 1 else None
        except Exception:
            self._height = None
        self._pos = (None, None)
        self._vis = 1
        self._inner = 4
        self._widths = []
        self._seps = []
        self.plain = []             # plain text of every canvas row (introspection / tests)
        self._off = 0
        try:
            sel = int(selected)
        except Exception:
            sel = 0
        self._sel = max(0, min(len(self._data) - 1, sel)) if self._data else -1
        self._layout()
        self._fit_offset(centre=True)
        self._render()
        cv = self._cv
        cv.bind('<Key>', self._on_key)
        cv.bind('<ButtonPress-1>', lambda e: self._on_click(e, False))
        cv.bind('<Double-ButtonPress-1>', lambda e: self._on_click(e, True))
        cv.bind('<MouseWheel>', self._on_wheel)
        cv.bind('<Button-4>', lambda e: self._wheel_rows(-_TABLE_WHEEL))
        cv.bind('<Button-5>', lambda e: self._wheel_rows(_TABLE_WHEEL))

    # -- normalisation --------------------------------------------------
    @staticmethod
    def _norm_columns(columns):
        out, flex = [], False
        try:
            seq = list(columns) if columns is not None else []
        except Exception:
            seq = []
        for c in seq:
            if not isinstance(c, dict):
                c = {'title': c}
            try:
                w = int(c.get('width') or 0)
            except Exception:
                w = 0
            if w <= 0:
                if flex:
                    w = 3
                else:
                    flex, w = True, 0
            else:
                w = max(3, w)
            t = c.get('title')
            out.append({'title': '' if t is None else str(t).replace('\n', ' '), 'width': w,
                        'align': 'r' if str(c.get('align', 'l')).lower().startswith('r') else 'l'})
        if not out:
            out = [{'title': '', 'width': 0, 'align': 'l'}]
        return out

    @staticmethod
    def _cell(v):
        return ('' if v is None else str(v)).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')

    @classmethod
    def _norm_rows(cls, rows):
        out = []
        try:
            seq = list(rows) if rows is not None else []
        except Exception:
            seq = []
        for r in seq:
            if r is None:
                continue
            role = 'normal'
            try:
                if isinstance(r, dict):
                    role = r.get('role') if r.get('role') in _TABLE_ROLES else 'normal'
                    cells = r.get('cells')
                    cells = list(cells) if isinstance(cells, (list, tuple)) else []
                elif isinstance(r, (list, tuple)):
                    cells = list(r)
                else:
                    cells = [r]
                out.append((tuple(cls._cell(x) for x in cells), role))
            except Exception:
                out.append(((), 'normal'))
        return out

    @staticmethod
    def _norm_keys(keys):
        src = _TABLE_KEYS if keys is None else keys
        out = {}
        try:
            items = list(src.items())
        except Exception:
            items = list(_TABLE_KEYS.items())
        for k, v in items:
            if k is None or v is None or str(k) == '':
                continue
            out[str(k).lower()] = str(v)
        return out

    @staticmethod
    def _norm_hints(hints):
        out = []
        try:
            seq = list(hints or [])
        except Exception:
            seq = []
        for h in seq:
            try:
                k, lab = str(h[0]), str(h[1])
            except Exception:
                k, lab = str(h), ''
            out.append((k.replace('\n', ' '), lab.replace('\n', ' ')))
        return out

    # -- layout ---------------------------------------------------------
    def _layout(self):
        pw, ph = self._parent_size()
        ncol = len(self._colspec)
        n = len(self._data)
        chrome = 4 + (2 if self._hints else 0)
        max_vis = max(1, ph // self.lh - chrome - 1)
        if self._height is not None:
            vis = min(self._height, max_vis)
        else:
            cap = min(max_vis, max(3, int(ph * 0.6) // self.lh - chrome))
            vis = min(cap, max(n, 3))
        self._vis = max(1, vis)
        fixed = [c['width'] for c in self._colspec]
        flex = fixed.index(0) if 0 in fixed else -1
        widths = list(fixed)
        gaps = len(_TABLE_SEP) * (ncol - 1)
        if flex >= 0:
            k = flex
            m = max([len(self._colspec[k]['title'])] +
                    [min(len(r[0][k]), 60) for r in self._data if k < len(r[0])] or [0])
            widths[k] = max(8, min(m, 40))
        foot = ''
        if self._hints:
            foot = self._footer_text()
        title = self._title
        want = max(2 + gaps + sum(widths), (len(title) + 4) if title else 0,
                   len(foot) + 1 if foot else 0, self._min_width - 2, 4)
        inner = min(want, max(4, max(6, pw // self.cw - 1) - 2))
        if inner > 2 + gaps + sum(widths):
            extra = inner - (2 + gaps + sum(widths))
            widths[flex if flex >= 0 else ncol - 1] += extra
        while 2 + gaps + sum(widths) > inner:
            k = flex if flex >= 0 and widths[flex] > 3 else -1
            if k < 0:
                wmax = max(widths)
                if wmax <= 3:
                    break
                k = widths.index(wmax)
            widths[k] -= 1
        self._widths = widths
        self._inner = inner
        seps, x = [], 1
        for w in widths[:-1]:
            x += w + 1
            if 1 + x < inner + 1:
                seps.append(1 + x)
            x += 2
        self._seps = seps
        rows = self._vis + chrome
        self._size_canvas(inner + 2, rows)
        self._fit_offset()

    def _footer_text(self):
        return ' ' + '  '.join(('%s %s' % (k, lab)).rstrip() for k, lab in self._hints)

    def _fit_offset(self, centre=False):
        n, vis = len(self._data), self._vis
        off = self._off
        if self._sel >= 0:
            if centre and not (off <= self._sel < off + vis):
                off = self._sel - vis // 2
            elif self._sel < off:
                off = self._sel
            elif self._sel >= off + vis:
                off = self._sel - vis + 1
        self._off = max(0, min(off, max(0, n - vis)))

    # -- row text ---------------------------------------------------------
    def _fmt(self, cells):
        """Row text of exactly self._inner chars; separator positions are spaces."""
        parts = []
        for k, w in enumerate(self._widths):
            s = _trunc(cells[k] if k < len(cells) else '', w)
            parts.append(s.rjust(w) if self._colspec[k]['align'] == 'r' else s.ljust(w))
        text = ' ' + (' ' * len(_TABLE_SEP)).join(parts) + ' '
        return text[:self._inner].ljust(self._inner)

    def _with_rules(self, text):
        """Insert the vertical rules into a _fmt() string (plain-text view)."""
        chars = list(text)
        for s in self._seps:
            if 0 <= s - 1 < len(chars):
                chars[s - 1] = '│'
        return ''.join(chars)

    def _scroll_cells(self):
        """Right-border glyph per data row: list of (glyph, kind) ; empty when not scrollable."""
        n, vis = len(self._data), self._vis
        if n <= vis or vis < 2:
            return []
        out = [('║', 'none')] * vis
        out[0] = ('▲', 'arrow')
        out[-1] = ('▼', 'arrow')
        t = vis - 2
        if t >= 1:
            th = max(1, int(round(t * float(vis) / n)))
            pos = int(round((t - th) * self._off / float(n - vis))) if n > vis else 0
            for i in range(t):
                out[1 + i] = ('█', 'thumb') if pos <= i < pos + th else ('░', 'track')
        return out

    # -- drawing ----------------------------------------------------------
    def _render(self):
        cv, c = self._cv, self.colors
        cv.delete('deco')
        bg, bd, fg = c['dos_menu_bg'], c['dos_menu_border'], c['dos_menu_fg']
        cols, vis, inner = self._cols, self._vis, self._inner
        d0 = 3
        has_foot = bool(self._hints)
        tl, hz, tr, vt, bl, br = BOX_DOUBLE
        n = len(self._data)
        self._draw_frame(self._title, (2, vis + 3) if has_foot else (2,))
        plain = []
        # plain text of the frame rows (mirrors _draw_frame)
        title = ' %s ' % self._title if self._title else ''
        title = _trunc(title, max(0, cols - 4)) if title else ''
        left = (cols - 2 - len(title)) // 2
        plain.append((tl + hz * left + title + hz * (cols - 2 - left - len(title)) + tr)[:cols])
        keyfg = c['dos_key_fg'] if c['dos_key_fg'] != bg else fg
        # header
        htext = self._fmt([k['title'] for k in self._colspec])
        self._text(1, 1, htext, keyfg)
        for s in self._seps:
            self._cells(s, 1, '│', bd)
        plain.append(vt + self._with_rules(htext) + vt)
        rule = list(SEP_FILL * inner)
        for s in self._seps:
            jg = '┼' if n else '┴'
            rule[s - 1] = jg
            self._cells(s, 2, jg, bd, bg)
        plain.append(SEP_LEFT + ''.join(rule) + SEP_RIGHT)
        # data rows
        scroll = self._scroll_cells()
        rolefg = {'normal': fg, 'dim': c['dos_menu_dim'], 'good': c['good'], 'warn': c['warn'],
                  'bad': c['bad']}
        for r in range(vis):
            i = self._off + r
            row = d0 + r
            if n == 0:
                text = ' ' * inner
                if r == vis // 2:
                    pad = max(0, (inner - len(_TABLE_EMPTY)) // 2)
                    text = (' ' * pad + _TABLE_EMPTY).ljust(inner)[:inner]
                    self._text(1 + pad, row, _TABLE_EMPTY[:max(0, inner - pad)], c['dos_menu_dim'])
                plain.append(vt + text + vt)
                continue
            if i < n:
                cells, role = self._data[i]
                text = self._fmt(cells)
            else:
                text, role = ' ' * inner, 'normal'
            sel = (i == self._sel)
            if sel:
                rfg, rbg = c['dos_menu_sel_fg'], c['dos_menu_sel_bg']
            else:
                rfg, rbg = rolefg[role], None
            if text.strip():
                self._text(1, row, text, rfg, rbg)
            elif rbg:
                self._rect(1, row, inner, rbg)
            for s in self._seps:
                self._cells(s, row, '│', rfg if sel else bd)
            right = vt
            if scroll:
                right, kind = scroll[r]
                if kind == 'thumb':
                    self._rect(cols - 1, row, 1, bd)
                elif kind == 'track':
                    self._cells(cols - 1, row, right, c['dos_menu_dim'], bg)
                elif kind == 'arrow':
                    lim = (right == '▲' and self._off == 0) or \
                          (right == '▼' and self._off + vis >= n)
                    self._cells(cols - 1, row, right, c['dos_menu_dim'] if lim else bd, bg)
            plain.append(vt + self._with_rules(text) + right)
        # footer / bottom
        if has_foot:
            frule = list(SEP_FILL * inner)
            for s in (self._seps if n else ()):
                frule[s - 1] = '┴'
                self._cells(s, d0 + vis, '┴', bd, bg)
            plain.append(SEP_LEFT + ''.join(frule) + SEP_RIGHT)
            ftxt = self._footer_text()[:inner].ljust(inner)
            frow = d0 + vis + 1
            self._text(1, frow, ftxt, fg)
            plain.append(vt + ftxt + vt)
            self._draw_foot_keys(frow, bg, keyfg)
            plain.append(bl + hz * inner + br)
        else:
            bot = list(hz * inner)
            for s in (self._seps if n else ()):
                bot[s - 1] = '╧'
                self._cells(s, d0 + vis, '╧', bd, bg)
            plain.append(bl + ''.join(bot) + br)
        self.plain = plain

    def _draw_foot_keys(self, frow, bg, keyfg):
        pos = 1                      # inner offset of the first key
        for j, (k, lab) in enumerate(self._hints):
            if j:
                pos += 2
            seg = k[:max(0, self._inner - pos)]
            if seg:
                self._text(1 + pos, frow, seg, keyfg, bg)
            pos += len(('%s %s' % (k, lab)).rstrip())
            if pos >= self._inner:
                break

    # -- selection / scrolling --------------------------------------------
    @property
    def selected(self):
        return self._sel if self._sel >= 0 else None

    @property
    def row_count(self):
        return len(self._data)

    @property
    def offset(self):
        """Index of the first visible data row."""
        return self._off

    @property
    def visible_rows(self):
        """Number of data rows shown at once."""
        return self._vis

    def select(self, index):
        """Select a row (index clamped; no-op when empty or index not a number)."""
        if not self._data:
            return
        try:
            i = max(0, min(len(self._data) - 1, int(index)))
        except Exception:
            return
        self._sel = i
        self._fit_offset(centre=True)
        self._render()

    def _move_to(self, i):
        n = len(self._data)
        if n == 0:
            return
        i = max(0, min(n - 1, i))
        if i == self._sel:
            return
        self._sel = i
        self._fit_offset()
        self._render()

    def _navigate(self, kind):
        if not self._data:
            return
        sel, step = max(self._sel, 0), max(1, self._vis - 1)
        self._move_to({'up': sel - 1, 'down': sel + 1, 'pgup': sel - step, 'pgdn': sel + step,
                       'home': 0, 'end': len(self._data) - 1}[kind])

    def _scroll_by(self, delta):
        """Scroll the window; the selection is pulled into view so it never hides."""
        n, vis = len(self._data), self._vis
        off = max(0, min(self._off + delta, max(0, n - vis)))
        if off == self._off:
            return
        self._off = off
        if self._sel >= 0:
            self._sel = max(off, min(off + vis - 1, self._sel))
        self._render()

    def _wheel_rows(self, rows):
        if not self._dead:
            self._scroll_by(rows)
        return 'break'

    # -- events ------------------------------------------------------------
    def _fire(self, action, index):
        cb = self._on_action
        if self._dead or not callable(cb):
            return
        cb(action, index, self)

    def _do_action(self, action):
        if action == 'close':
            if self._finish_close():
                self._fire('close', None)
        else:
            self._fire(action, self.selected)

    def _on_key(self, e):
        if self._dead:
            return 'break'
        ks = str(e.keysym)
        nav = _TABLE_NAV.get(ks)
        if nav:
            self._navigate(nav)
            return 'break'
        try:
            state = int(e.state)
        except Exception:
            state = 0
        if state & 0x20004:         # Ctrl / Alt combinations are not ours
            return 'break'
        names = [ks.lower()]
        ch = e.char
        if ch and len(ch) == 1 and ch.isprintable():
            names.append(ch.lower())
        for nm in names:
            act = self._keymap.get(nm)
            if act:
                self._do_action(act)
                break
        return 'break'

    def _on_wheel(self, e):
        try:
            d = int(e.delta)
        except Exception:
            d = 0
        if d:
            steps = int(abs(d) / 120) or 1
            self._wheel_rows((-1 if d > 0 else 1) * steps * _TABLE_WHEEL)
        return 'break'

    def _on_click(self, e, double):
        if self._dead:
            return 'break'
        try:
            self._cv.focus_set()
        except tk.TclError:
            pass
        col, row = int(e.x) // self.cw, int(e.y) // self.lh
        vis, d0 = self._vis, 3
        if row < d0 or row >= d0 + vis:
            return 'break'
        if col == self._cols - 1:
            if len(self._data) > vis and vis >= 2:
                r = row - d0
                if r == 0:
                    self._scroll_by(-1)
                elif r == vis - 1:
                    self._scroll_by(1)
                else:
                    cells = self._scroll_cells()
                    if cells and cells[r][1] == 'track':
                        up = any(cells[j][1] == 'thumb' for j in range(r + 1, vis))
                        self._scroll_by(-(vis - 1) if up else vis - 1)
            return 'break'
        if col < 1 or col > self._cols - 2:
            return 'break'
        i = self._off + row - d0
        if 0 <= i < len(self._data):
            if i != self._sel:
                self._sel = i
                self._fit_offset()
                self._render()
            if double:
                act = self._keymap.get('return')
                if act:
                    self._do_action(act)
        return 'break'

    # -- public ------------------------------------------------------------
    def set_rows(self, rows, selected=None):
        """Replace the data.  Selection (and scroll position) are kept where possible."""
        self._data = self._norm_rows(rows)
        n = len(self._data)
        if n == 0:
            self._sel = -1
        else:
            if selected is not None:
                try:
                    self._sel = int(selected)
                except Exception:
                    pass
            self._sel = max(0, min(n - 1, self._sel if self._sel >= 0 else 0))
        old = (self._cols, self._rows)
        self._layout()
        self._fit_offset(centre=selected is not None)
        self._render()
        if self._is_open and (self._cols, self._rows) != old:
            self._place_box(*self._pos)

    def open(self, x=None, y=None):
        if self._is_open:
            self._finish_close()
        self._pos = (x, y)
        self._begin_open()
        self._layout()
        self._fit_offset()
        self._render()
        self._place_box(x, y)
        try:
            self.update_idletasks()
            self._cv.focus_set()
        except tk.TclError:
            pass

    def close(self):
        """Close silently (the 'close' key action calls on_action; this does not)."""
        self._finish_close()

    def restyle(self, colors, font=None):
        self.colors = dos_colors(colors)
        if font is not None:
            self._font = font
        self._measure()
        self.configure(bg=self.colors['dos_menu_bg'])
        self._layout()
        self._render()
        if self._is_open:
            self._place_box(*self._pos)

    def destroy(self):
        self._dead = True
        self._on_action = None
        _DosBox.destroy(self)


# --------------------------------------------------------------------------
# message / confirm
# --------------------------------------------------------------------------
def show_message(parent, title, text, colors, font, buttons=None, on_result=None):
    """OK box.  on_result(result_name, values) is called after the box closes."""
    dlg = DosDialog(parent, title, [], buttons or [('OK', 'ok')], colors, font,
                    on_result or (lambda r, v: None), message=text)
    dlg.open()
    return dlg


def confirm(parent, title, text, colors, font, on_result):
    """Yes/No box (Y / N keys work directly, Esc = No).  on_result('yes'|'no', {})."""
    dlg = DosDialog(parent, title, [], [('Yes', 'yes', 'y'), ('No', 'no', 'n')], colors, font,
                    on_result, message=text, esc_result='no')
    dlg.open()
    return dlg


class DosMessage:
    """Namespace wrapper for show_message / confirm."""
    show = staticmethod(show_message)
    confirm = staticmethod(confirm)


# --------------------------------------------------------------------------
# DosStatusBar
# --------------------------------------------------------------------------
class DosStatusBar(tk.Frame):
    ROLES = ('normal', 'key', 'good', 'warn', 'bad', 'dim')

    def __init__(self, parent, colors, font, bold_font=None):
        tk.Frame.__init__(self, parent, bd=0, highlightthickness=0, padx=0, pady=0)
        self.colors = dos_colors(colors)
        self._font = font or _default_font()
        self._bold = bold_font
        if self._bold is None:
            try:
                self._bold = self._font.copy()
                self._bold.configure(weight='bold')
            except Exception:
                self._bold = None
        self._rows = []
        self._spec = [None, None]       # (left_runs, right_runs) per row
        self.plain = ['', '']           # last rendered plain text per row
        self.top = tk.Frame(parent, bd=0, highlightthickness=0, padx=0, pady=0)   # row 0: the hint row
        for n in range(2):
            cv = tk.Canvas(self.top if n == 0 else self, bd=0, highlightthickness=0)
            cv.pack(side='top', fill='x')
            cv.bind('<Configure>', lambda e: self._render())
            cv.bind('<Map>', lambda e: self._render())
            self._rows.append(cv)
        self._measure()
        self._hints = ([], None)
        self._segs = ([], None)
        self._apply_style()
        self._rebuild()

    def _measure(self):
        try:
            self.cw = max(1, int(self._font.measure('M')))
            self.lh = max(1, int(self._font.metrics('linespace')))
        except Exception:
            self.cw, self.lh = 8, 16

    def _apply_style(self):
        c = self.colors
        for cv, bg in zip(self._rows, (c['dos_bar_bg'], c['dos_bar2_bg'])):
            cv.configure(bg=bg, height=self.lh)
        self.configure(bg=c['dos_bar2_bg'])
        self.top.configure(bg=c['dos_bar_bg'])

    # -- content ------------------------------------------------------
    def _hint_runs(self, hints):
        c = self.colors
        left = [(' ', c['dos_bar_fg'], False)]
        for n, h in enumerate(hints):
            try:
                k, lab = str(h[0]), str(h[1])
            except Exception:
                k, lab = str(h), ''
            if n:
                left.append(('  ', c['dos_bar_fg'], False))
            left.append((k, c['dos_key_fg'] if c['dos_key_fg'] != c['dos_bar_bg'] else c['dos_bar_fg'], True))
            left.append((' ' + lab, c['dos_bar_fg'], False))
        return left

    def _hint_spec(self, cols):
        """The hint row for `cols` cells: whole hints only. When they do not all fit the last ones are
        left out (never half a word); the right-hand text goes before any hint does."""
        c = self.colors
        hints, right = self._hints
        rr = [(str(right) + ' ', c['dos_bar_fg'], False)] if right not in (None, '') else []
        rlen = sum(len(t) for t, _c, _b in rr)
        def prio(i):                                  # optional third item of a hint: higher stays longer
            try:
                return float(hints[i][2])
            except Exception:
                return 5.0
        for keep_right in ((True, False) if rr else (False,)):
            extra = rlen + 1 if keep_right else 0
            shown = list(range(len(hints)))
            while True:
                left = self._hint_runs([hints[i] for i in shown])
                if sum(len(t) for t, _c, _b in left) + extra <= cols:
                    return left, (rr if keep_right else [])
                if not shown:
                    break
                shown.remove(min(shown, key=lambda i: (prio(i), -i)))     # drop the least important, latest first
        return [(' ', c['dos_bar_fg'], False)], []

    def _rebuild(self):
        c = self.colors
        hints, right = self._hints
        rr = [(str(right) + ' ', c['dos_bar_fg'], False)] if right not in (None, '') else []
        self._spec[0] = (self._hint_runs(hints), rr)
        segs, right = self._segs
        left = [(' ', c['dos_bar2_fg'], False)]
        col = {'normal': c['dos_bar2_fg'], 'key': c['dos_key_fg'], 'good': c['good'],
               'warn': c['warn'], 'bad': c['bad'], 'dim': c['dim']}
        for n, s in enumerate(segs):
            try:
                text, role = str(s[0]), s[1]
            except Exception:
                text, role = str(s), 'normal'
            joined = False
            try:
                joined = bool(s[2])
            except Exception:
                pass
            if n:
                left.append((' ' if joined else ' │ ', c['dim'], False))
            left.append((text, col.get(role, col['normal']), role == 'key'))
        rr = [(str(right) + ' ', c['dos_bar2_fg'], False)] if right not in (None, '') else []
        self._spec[1] = (left, rr)
        self._render()

    @staticmethod
    def _flat(runs):
        out = []
        for text, color, bold in runs:
            for ch in text.replace('\n', ' ').replace('\t', ' '):
                out.append((ch, color, bold))
        return out

    def _render(self):
        for n, cv in enumerate(self._rows):
            spec = self._spec[n]
            if spec is None:
                continue
            try:
                wpx = cv.winfo_width() if cv.winfo_ismapped() else cv.winfo_reqwidth()
                cols = max(0, wpx // self.cw)
            except tk.TclError:
                return
            if n == 0:
                spec = self._spec[0] = self._hint_spec(cols)
            left, right = self._flat(spec[0]), self._flat(spec[1])
            if right and len(left) + len(right) + 1 <= cols:
                cells = left + [(' ', left[-1][1] if left else '#000000', False)] * (
                    cols - len(left) - len(right)) + right
            else:
                cells = left
                if len(cells) > cols:
                    cells = cells[:cols]
                    if cols >= 2:
                        cells[-1] = (ELLIPSIS, cells[-1][1], False)
            self.plain[n] = ''.join(ch for ch, _, _ in cells)
            cv.delete('all')
            # shade/block characters (gauges) are drawn as filled cells: whatever font is in use,
            # they then fill the whole cell and join up instead of leaving gaps
            bg = str(cv.cget('bg'))
            for k, (ch, col, bold) in enumerate(cells):
                if ch == '│':                                   # the separator: a full-height line
                    mid = k * self.cw + self.cw // 2
                    cv.create_line(mid, 0, mid, self.lh, fill=col)
                    cells[k] = (' ', col, bold)
                    continue
                part = _BLOCK_SHADES.get(ch)
                if part is not None:
                    cv.create_rectangle(k * self.cw, 0, (k + 1) * self.cw, self.lh,
                                        fill=_blend(bg, col, part), outline='')
                    cells[k] = (' ', col, bold)
            i = 0
            while i < len(cells):
                j = i
                while j < len(cells) and cells[j][1:] == cells[i][1:]:
                    j += 1
                f = self._font
                if cells[i][2] and self._bold is not None:
                    f = self._bold
                cv.create_text(i * self.cw, 0, text=''.join(ch for ch, _, _ in cells[i:j]),
                               anchor='nw', fill=cells[i][1], font=f)
                i = j

    # -- public -------------------------------------------------------
    def set_hints(self, hints, right=None):
        try:
            hints = list(hints or [])
        except Exception:
            hints = []
        self._hints = (hints, right)
        self._rebuild()

    def set_segments(self, segments, right=None):
        try:
            segments = list(segments or [])
        except Exception:
            segments = []
        self._segs = (segments, right)
        self._rebuild()

    def restyle(self, colors, font=None, bold_font=None):
        self.colors = dos_colors(colors)
        if font is not None:
            self._font = font
        if bold_font is not None:
            self._bold = bold_font
        elif font is not None:
            try:
                self._bold = self._font.copy()
                self._bold.configure(weight='bold')
            except Exception:
                pass
        self._measure()
        self._apply_style()
        self._rebuild()


# --------------------------------------------------------------------------
# text-mode scrollbar
# --------------------------------------------------------------------------
class DosScrollbar(tk.Canvas):
    """A vertical scrollbar in the style of old text-mode software: an up-arrow cell, a dotted
    track with a solid thumb, and a down-arrow cell, one character cell wide.

    Clicking an arrow scrolls one line; clicking the track above or below the thumb pages up
    or down; both repeat while the button is held. Dragging the thumb scrolls continuously.
    Use it like tk.Scrollbar: ``text.configure(yscrollcommand=sb.set)`` and ``command=text.yview``.
    """
    REPEAT_FIRST_MS = 350
    REPEAT_MS = 60

    def __init__(self, parent, command, colors, font=None):
        self._font = font or _default_font()
        self._cw = max(6, self._font.measure('0'))
        self._lh = max(8, self._font.metrics('linespace'))
        tk.Canvas.__init__(self, parent, width=self._cw, height=1, highlightthickness=0, bd=0,
                           cursor='arrow')
        self._cmd = command
        self._c = dict(colors) if isinstance(colors, dict) else {}
        self._first, self._last = 0.0, 1.0
        self._job = None
        self._zone = None        # what the held button is doing: 'up' 'down' 'pgup' 'pgdn' 'drag'
        self._grab = 0
        self._press_y = 0
        self.bind('<Configure>', lambda e: self._draw())
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<B1-Motion>', self._motion)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Destroy>', self._on_destroy, add='+')
        self._draw()

    # ---- colours ----------------------------------------------------------------------
    def _col(self, key, default):
        return _hex(self._c.get(key), default)

    def restyle(self, colors, font=None):
        if isinstance(colors, dict):
            self._c = dict(colors)
        if font is not None:
            self._font = font
        self._cw = max(6, self._font.measure('0'))
        self._lh = max(8, self._font.metrics('linespace'))
        try:
            self.configure(width=self._cw)
            self._draw()
        except tk.TclError:
            pass

    # ---- geometry -----------------------------------------------------------------------
    def _geom(self):
        h = max(1, self.winfo_height())
        ah = min(self._lh, h // 2)
        top, bot = ah, max(ah, h - ah)
        track = max(0, bot - top)
        span = min(1.0, max(0.0, self._last - self._first))
        thumb = int(track * span)
        thumb = max(min(self._lh, track), thumb) if track else 0
        avail = max(0, track - thumb)
        room = 1.0 - span
        off = int(round(avail * (self._first / room))) if room > 1e-9 else 0
        off = max(0, min(avail, off))
        return h, ah, top, bot, track, thumb, avail, room, top + off

    def _draw(self):
        try:
            w = max(1, self.winfo_width())
            h, ah, top, bot, track, thumb, avail, room, ttop = self._geom()
        except tk.TclError:
            return
        bg = self._col('dos_menu_bg', '#0000aa')
        dim = self._col('dos_menu_dim', '#9999dd')
        hi = self._col('dos_bar_bg', '#00aaaa')
        self.delete('all')
        self.configure(bg=bg)
        if track:
            self.create_rectangle(0, top, w, bot, fill=dim, outline='', stipple='gray50')
            self.create_rectangle(0, ttop, w, ttop + thumb, fill=hi, outline='')
        if ah > 2:
            for y0, up in ((0, True), (h - ah, False)):
                self.create_rectangle(0, y0, w, y0 + ah, fill=hi, outline='')
                cx, m = w / 2.0, max(2, int(min(w, ah) * 0.28))
                if up:
                    pts = (cx, y0 + m, cx - (w / 2.0 - 2), y0 + ah - m, cx + (w / 2.0 - 2), y0 + ah - m)
                else:
                    pts = (cx, y0 + ah - m, cx - (w / 2.0 - 2), y0 + m, cx + (w / 2.0 - 2), y0 + m)
                self.create_polygon(*pts, fill=bg, outline='')

    # ---- tk.Scrollbar protocol -----------------------------------------------------------------
    def set(self, first, last):
        try:
            f, l = float(first), float(last)
        except (TypeError, ValueError):
            return
        if f != f or l != l:
            return
        f = min(1.0, max(0.0, f))
        l = min(1.0, max(f, l))
        if (f, l) != (self._first, self._last):
            self._first, self._last = f, l
            self._draw()

    # ---- mouse ---------------------------------------------------------------------------------
    def _zone_at(self, y):
        h, ah, top, bot, track, thumb, avail, room, ttop = self._geom()
        if y < ah:
            return 'up'
        if y >= h - ah:
            return 'down'
        if y < ttop:
            return 'pgup'
        if y >= ttop + thumb:
            return 'pgdn'
        return 'drag'

    def _fire(self, zone):
        try:
            if zone == 'up':
                self._cmd('scroll', -1, 'units')
            elif zone == 'down':
                self._cmd('scroll', 1, 'units')
            elif zone == 'pgup':
                self._cmd('scroll', -1, 'pages')
            elif zone == 'pgdn':
                self._cmd('scroll', 1, 'pages')
        except tk.TclError:
            pass

    def _cancel_job(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _press(self, e):
        self._cancel_job()
        self._press_y = e.y
        self._zone = self._zone_at(e.y)
        if self._zone == 'drag':
            self._grab = e.y - self._geom()[8]
            return
        self._fire(self._zone)
        self._job = self.after(self.REPEAT_FIRST_MS, self._repeat)

    def _repeat(self):
        self._job = None
        if self._zone in (None, 'drag'):
            return
        if self._zone in ('pgup', 'pgdn') and self._zone_at(self._press_y) != self._zone:
            return                         # the thumb has reached the pointer: stop paging
        self._fire(self._zone)
        try:
            self._job = self.after(self.REPEAT_MS, self._repeat)
        except tk.TclError:
            self._job = None

    def _motion(self, e):
        if self._zone != 'drag':
            return
        h, ah, top, bot, track, thumb, avail, room, ttop = self._geom()
        if avail <= 0:
            return
        frac = min(1.0, max(0.0, (e.y - self._grab - top) / float(avail)))
        try:
            self._cmd('moveto', frac * room)
        except tk.TclError:
            pass

    def _release(self, _e):
        self._cancel_job()
        self._zone = None

    def _on_destroy(self, e):
        if e.widget is self:
            self._cancel_job()



# --------------------------------------------------------------------------
# box-drawing frame
# --------------------------------------------------------------------------
_BOX_UP, _BOX_DOWN, _BOX_LEFT, _BOX_RIGHT = 1, 2, 4, 8
_BOX_CHARS = {
    _BOX_UP | _BOX_DOWN: '\u2551', _BOX_LEFT | _BOX_RIGHT: '\u2550',
    _BOX_DOWN | _BOX_RIGHT: '\u2554', _BOX_DOWN | _BOX_LEFT: '\u2557',
    _BOX_UP | _BOX_RIGHT: '\u255a', _BOX_UP | _BOX_LEFT: '\u255d',
    _BOX_UP | _BOX_DOWN | _BOX_RIGHT: '\u2560', _BOX_UP | _BOX_DOWN | _BOX_LEFT: '\u2563',
    _BOX_DOWN | _BOX_LEFT | _BOX_RIGHT: '\u2566', _BOX_UP | _BOX_LEFT | _BOX_RIGHT: '\u2569',
    _BOX_UP | _BOX_DOWN | _BOX_LEFT | _BOX_RIGHT: '\u256c',
    _BOX_UP: '\u2551', _BOX_DOWN: '\u2551', _BOX_LEFT: '\u2550', _BOX_RIGHT: '\u2550',
}


def box_cells(cols, rows, rects):
    """Double-line frame for a set of rectangles on a cell grid, as a list of `rows` strings of
    `cols` characters. Each rectangle is (x0, y0, x1, y1) in cells, x1/y1 exclusive, and its
    border is the outermost ring of cells inside it. Rectangles that share an edge share the
    line, and the joins come out as proper T and cross pieces."""
    try:
        cols, rows = max(0, min(int(cols), 1000)), max(0, min(int(rows), 1000))
    except Exception:
        return []
    bits = [[0] * cols for _ in range(rows)]
    for r in list(rects or [])[:64]:
        try:
            x0, y0, x1, y1 = [int(v) for v in r]
        except Exception:
            continue
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(cols, x1), min(rows, y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        for x in range(x0, x1):
            m = (_BOX_LEFT if x > x0 else 0) | (_BOX_RIGHT if x < x1 - 1 else 0)
            bits[y0][x] |= m
            bits[y1 - 1][x] |= m
        for y in range(y0, y1):
            m = (_BOX_UP if y > y0 else 0) | (_BOX_DOWN if y < y1 - 1 else 0)
            bits[y][x0] |= m
            bits[y][x1 - 1] |= m
    return [''.join(_BOX_CHARS.get(b, ' ') for b in row) for row in bits]


# block/shade characters and how much of the foreground they show (used for gauge bars)
_BLOCK_SHADES = {'\u2588': 1.0, '\u2593': 0.75, '\u2592': 0.5, '\u2591': 0.25}


def _blend(bg, fg, part):
    """Colour `part` of the way from bg to fg (both '#rrggbb'; anything else gives fg)."""
    try:
        a = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
        return '#%02x%02x%02x' % tuple(int(round(x + (y - x) * part)) for x, y in zip(a, b))
    except Exception:
        return fg


PRE = '\x01'          # a message line starting with this is laid out by hand (columns, pictures)


def _is_columns(line):
    """A hand-laid-out line: it is never re-wrapped, and is cut cleanly if it cannot fit."""
    return line.startswith(PRE)


# --------------------------------------------------------------------------
# multi-line text editor (the DOS counterpart of the game's own string editor)
# --------------------------------------------------------------------------
class DosTextEditor(tk.Frame):
    """A page you type paragraphs into. Ctrl-S (or F10) keeps the text, Esc throws the changes away.
    Meant to be placed over the main screen (give it the holder frame as parent)."""

    def __init__(self, parent, title, text, colors, font, on_done, hint=None):
        tk.Frame.__init__(self, parent, bd=0, highlightthickness=0)
        self.colors = dos_colors(colors)
        self._font = font
        self._on_done = on_done
        self._open = False
        self._title = str(title)
        self._hint = hint or 'Ctrl-S done   Esc cancel   Ctrl-G gradient   Ctrl-K strip colours'
        self._head = tk.Label(self, anchor='w', padx=8, bd=0)
        self._head.pack(fill='x', side='top')
        self._foot = tk.Label(self, anchor='w', padx=8, bd=0)
        self._foot.pack(fill='x', side='bottom')
        self._cv = tk.Text(self, wrap='word', undo=True, bd=0, highlightthickness=0, padx=8, pady=4)
        self._cv.pack(fill='both', expand=True)
        self._cv.insert('1.0', '' if text is None else str(text))
        self._cv.edit_reset()
        for seq in ('<Control-s>', '<Control-S>', '<F10>'):
            self._cv.bind(seq, lambda e: (self._finish(True), 'break')[1])
        self._cv.bind('<Escape>', lambda e: (self._finish(False), 'break')[1])
        self._asked = None
        for seq, what in (('<Control-g>', 'gradient'), ('<Control-G>', 'gradient'),
                          ('<Control-k>', 'strip'), ('<Control-K>', 'strip')):
            self._cv.bind(seq, lambda e, w=what: (self._ask(w), 'break')[1])
        self._tint_job = None
        self._cv.bind('<<Modified>>', self._modified)
        self.restyle(colors, font)
        self._tint()

    def restyle(self, colors=None, font=None):
        if colors is not None:
            self.colors = dos_colors(colors)
        if font is not None:
            self._font = font
        c = self.colors
        self._head.configure(text=' %s' % self._title, bg=c['dos_bar_bg'], fg=c['dos_bar_fg'], font=self._font)
        self._foot.configure(text=' %s' % self._hint, bg=c['dos_bar2_bg'], fg=c['dos_bar2_fg'], font=self._font)
        self._cv.configure(bg=c['input_bg'], fg=c['input_fg'], font=self._font, insertwidth=self._font.measure('0'),
                           insertbackground=c['dos_key_fg'], selectbackground=c['dos_menu_fg'],
                           selectforeground=c['dos_menu_bg'])

    def _modified(self, _e=None):
        if not self._cv.edit_modified():
            return
        self._cv.edit_modified(False)
        if self._tint_job is not None:
            try:
                self.after_cancel(self._tint_job)
            except tk.TclError:
                pass
        try:
            self._tint_job = self.after(120, self._tint)
        except tk.TclError:
            self._tint_job = None

    def _tint(self):
        self._tint_job = None
        try:
            apply_code_tags(self._cv, self.colors['dos_menu_dim'], self.colors['input_bg'])
        except tk.TclError:
            pass

    def selection(self):
        """(start, end) of the selected text as offsets into text(), or None."""
        try:
            a = self._cv.count('1.0', self._cv.index('sel.first'), 'chars')
            b = self._cv.count('1.0', self._cv.index('sel.last'), 'chars')
            return (int(a[0]), int(b[0])) if a and b and b[0] > a[0] else None
        except (tk.TclError, TypeError, IndexError):
            return None

    def _ask(self, what):
        """Ctrl-G / Ctrl-K: close with a request (the caller shows its own list, then comes back)."""
        if not self._open:
            return
        result = (what, self.text(), self.selection())
        self.close()
        if callable(self._on_done):
            self._on_done(result)

    def open(self, x=None, y=None):
        self._open = True
        self.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.lift()
        self._cv.focus_set()
        self._cv.mark_set('insert', 'end-1c')

    def is_open(self):
        return self._open

    def text(self):
        return self._cv.get('1.0', 'end-1c').rstrip('\n')

    def close(self):
        if not self._open:
            return
        self._open = False
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _finish(self, keep):
        if not self._open:
            return
        result = self.text() if keep else None
        self.close()
        if callable(self._on_done):
            self._on_done(result)


def apply_code_tags(text_widget, dim_colour, bg=None):
    """Show the game's colour codes in a Text widget: each `NNN code is dimmed and the text it
    colours is drawn in that xterm colour (so a gradient can be seen as it is written)."""
    try:
        import colortools as ct
    except ImportError:
        return
    w = text_widget
    for tag in list(w.tag_names()):
        if tag.startswith('xc') or tag == 'xcode':
            w.tag_delete(tag)
    text = w.get('1.0', 'end-1c')
    if '`' not in text:
        return
    w.tag_configure('xcode', foreground=dim_colour)
    for start, end, idx, is_code in ct.spans(text):
        if is_code:
            w.tag_add('xcode', '1.0+%dc' % start, '1.0+%dc' % end)
        elif idx is not None:
            tag = 'xc%d' % idx
            w.tag_configure(tag, foreground=ct.XTERM[idx])
            w.tag_add(tag, '1.0+%dc' % start, '1.0+%dc' % end)


def _alt_down(e):
    """Is Alt held for this key event? (On Windows state bit 0x8 is Num Lock, not Alt.)"""
    try:
        st = int(e.state)
    except (TypeError, ValueError):
        return False
    return bool(st & 0x20000) if sys.platform.startswith('win') else bool(st & 0x88)
