"""dosui - early-1990s DOS terminal look (Telix / Terminate style) widgets for tkinter.

Self-contained: stdlib tkinter only, no ttk, no images.  Everything is drawn on
tk.Canvas objects with monospace text and Unicode box-drawing characters, laid
out on a strict character-cell grid (cell = font.measure('M') x linespace).

Public API:
    dos_colors(theme) -> dict
    gauge_text(cur, maximum, width=10) -> (text, role)
    format_duration(seconds) -> 'HH:MM:SS'
    DosMenu, DosDialog, DosStatusBar, show_message(), confirm(), DosMessage
"""
import math
import re
import textwrap
import tkinter as tk
import tkinter.font as tkfont

__all__ = ['BOX_DOUBLE', 'BOX_SINGLE', 'dos_colors', 'gauge_text', 'format_duration',
           'DosMenu', 'DosDialog', 'DosStatusBar', 'DosMessage', 'show_message', 'confirm']

BOX_DOUBLE = '╔═╗║╚╝'     # tl, horizontal, tr, vertical, bl, br
BOX_SINGLE = '┌─┐│└┘'
SEP_LEFT, SEP_FILL, SEP_RIGHT = '╟', '─', '╢'
GAUGE_FULL, GAUGE_EMPTY = '█', '░'
CHECK_ON, CHECK_OFF = '√', ' '
ELLIPSIS = '…'

_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


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

    def __init__(self, parent, title, items, colors, font, on_close=None, min_width=0):
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
                            'enabled': bool(it.get('enabled', True))})
            except Exception:
                out.append(None)
        return out

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
        labw = max([len(i['label']) for i in real] or [0])
        shw = max([len(i['shortcut']) for i in real] or [0])
        inner = 1 + self._markw + labw + ((2 + shw) if shw else 0) + 1
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
        room = inner - 1 - self._markw - len(right) - (1 if sh else 0)
        if room < 1 and sh:
            sh, right = '', ' '
            room = inner - 1 - self._markw - 1
        room = max(1, room)
        lab = _trunc(it['label'], room)
        mark = ''
        if self._markw:
            mark = (CHECK_ON if it['checked'] else CHECK_OFF) + ' '
        s = ' ' + mark + lab.ljust(room) + (' ' if sh else '') + right
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
            hk = it['hotkey']
            if hk:
                idx = lab.lower().find(hk.lower())
                if idx >= 0 and lab[idx] != ELLIPSIS:
                    col = 1 + 1 + self._markw + idx
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
            t = 'check' if f.get('type') == 'check' else 'text'
            try:
                fw = int(f.get('width') or 20)
            except Exception:
                fw = 20
            fd = {'key': str(f.get('key', '')), 'label': str(f.get('label', '')), 'type': t,
                  'width': max(1, fw), 'secret': bool(f.get('secret')),
                  'value': f.get('value')}
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
        labw = max([len(f['label']) for f in fields if f['type'] == 'text'] or [0])
        # natural content width
        need = [len(self._title) + 6]
        for f in fields:
            if f['type'] == 'check':
                need.append(4 + len(f['label']) + 2)
            else:
                need.append(2 + labw + 1 + f['width'] + 2)
        btn_w = sum(len(b['label']) + 4 for b in buttons) + 2 * max(0, len(buttons) - 1)
        need.append(btn_w + 4)
        msg_lines_nat = max([len(l) for l in self._message.split('\n')] or [0])
        need.append(min(msg_lines_nat + 4, 60))
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
    def _common(self, e):
        ks = e.keysym
        if ks in ('Tab', 'ISO_Left_Tab'):
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
        if len(e.keysym) == 1:
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
        for _ in range(2):
            cv = tk.Canvas(self, bd=0, highlightthickness=0)
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
        self.configure(bg=c['dos_bar_bg'])

    # -- content ------------------------------------------------------
    def _rebuild(self):
        c = self.colors
        hints, right = self._hints
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
        rr = [(str(right) + ' ', c['dos_bar_fg'], False)] if right not in (None, '') else []
        self._spec[0] = (left, rr)
        segs, right = self._segs
        left = [(' ', c['dos_bar2_fg'], False)]
        col = {'normal': c['dos_bar2_fg'], 'key': c['dos_key_fg'], 'good': c['good'],
               'warn': c['warn'], 'bad': c['bad'], 'dim': c['dim']}
        for n, s in enumerate(segs):
            try:
                text, role = str(s[0]), s[1]
            except Exception:
                text, role = str(s), 'normal'
            if n:
                left.append((' │ ', c['dim'], False))
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
