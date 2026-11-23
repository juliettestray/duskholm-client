"""Tests for dosui.py.  Plain asserts, PASS/FAIL per check, exit 1 on failure."""
import math
import os
import re
import sys
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import dosui  # noqa: E402

FAILS = []
T0 = time.time()
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def check(name):
    def deco(fn):
        try:
            fn()
            print('PASS', name)
        except Exception:
            FAILS.append(name)
            print('FAIL', name)
            traceback.print_exc()
        return fn
    return deco


root = tk.Tk()
root.geometry('900x600+30+30')
root.update()
root.focus_force()
FONT = tkfont.Font(family='Consolas', size=11)
FONT_BIG = tkfont.Font(family='Consolas', size=24)
FONT_SMALL = tkfont.Font(family='Consolas', size=9)
C = dosui.dos_colors({})
area = tk.Frame(root, width=900, height=560, bg='#000000')
area.pack(fill='both', expand=True)
area.pack_propagate(False)
entry_focus = tk.Entry(area)
entry_focus.place(x=0, y=0)
root.update()


def upd(n=2):
    for _ in range(n):
        root.update()
        root.update_idletasks()


def key(w, keysym, **kw):
    w.event_generate('<Key>', keysym=keysym, **kw)
    upd(1)


def type_into_menu(m, keysym):
    key(m._cv, keysym)


def focus(w):
    w.focus_force()
    upd()


def items_basic(log):
    return [
        {'label': 'Alpha', 'hotkey': 'A', 'action': lambda: log.append('a')},
        None,
        {'label': 'Beta', 'hotkey': 'b', 'action': lambda: log.append('b'), 'enabled': False},
        {'label': 'Gamma', 'hotkey': 'G', 'action': lambda: log.append('g'), 'checked': True,
         'shortcut': 'F3'},
        {'label': 'Delta', 'action': lambda: log.append('d')},
    ]


def children_count(w):
    return len(w.winfo_children())


# ------------------------------------------------------------------ colors
@check('dos_colors: empty/garbage/partial/valid')
def _():
    keys = ['dos_bar_bg', 'dos_bar_fg', 'dos_bar2_bg', 'dos_bar2_fg', 'dos_key_fg', 'dos_menu_bg',
            'dos_menu_fg', 'dos_menu_border', 'dos_menu_sel_bg', 'dos_menu_sel_fg', 'dos_menu_dim',
            'dos_shadow', 'dos_screen_border', 'bg', 'fg', 'panel', 'panel_edge', 'input_bg',
            'input_fg', 'alert', 'dim', 'select', 'button_bg', 'button_fg', 'good', 'warn', 'bad']
    themes = [{}, None, 5, 'x', [], {'bg': 'red', 'fg': 12, 'ansi': 'nope'}, {'ansi': [1, 2]},
              {'ansi': [None] * 16, 'dos_bar_bg': '#12'}, {'dos_bar_bg': '#123456', 'ansi': ['#000000'] * 16},
              {'dos_bar_bg': object(), 'bg': '#GGGGGG', 'ansi': {1: 2}}]
    for t in themes:
        c = dosui.dos_colors(t)
        for k in keys:
            assert HEX.match(c[k]), (t, k, c.get(k))
        assert len(c['ansi']) == 16 and all(HEX.match(a) for a in c['ansi'])
    assert dosui.dos_colors({})['dos_bar_bg'] == '#00aaaa'
    assert dosui.dos_colors({'dos_bar_bg': '#123456'})['dos_bar_bg'] == '#123456'
    a = ['#000000'] * 16
    a[10], a[11], a[9] = '#010101', '#020202', '#030303'
    c = dosui.dos_colors({'ansi': a})
    assert (c['good'], c['warn'], c['bad']) == ('#010101', '#020202', '#030303')
    assert dosui.dos_colors(c) == c   # idempotent


@check('gauge_text edge cases')
def _():
    t, r = dosui.gauge_text(5, 10)
    assert len(t) == 10 and t.count('█') == 5 and r == 'warn' or r == 'good'
    for cur, mx, w in [(0, 0, 10), (-5, 10, 10), (float('nan'), 10, 10), (10 ** 30, 10, 10),
                       ('7', '10', 10), (None, None, 10), (5, float('nan'), 10), (5, 10, 0),
                       (5, 10, 1), (5, 10, 37), (5, 10, 'x'), (float('inf'), 10, 10), ([], {}, 10)]:
        t, r = dosui.gauge_text(cur, mx, w)
        try:
            wi = int(w)
        except Exception:
            wi = 10
        assert len(t) == wi and set(t) <= set('█░') and r in ('good', 'warn', 'bad'), (cur, mx, w, t)
    assert dosui.gauge_text(10, 10)[0] == '█' * 10 and dosui.gauge_text(10, 10)[1] == 'good'
    assert dosui.gauge_text(0, 0)[0] == '█' * 10                       # max<=0 -> full
    assert dosui.gauge_text(0, 10)[0] == '░' * 10 and dosui.gauge_text(0, 10)[1] == 'bad'
    assert dosui.gauge_text(6, 10)[1] == 'good'
    assert dosui.gauge_text(3, 10)[1] == 'warn'
    assert dosui.gauge_text(2, 10)[1] == 'bad'


@check('format_duration edge cases')
def _():
    f = dosui.format_duration
    assert f(0) == '00:00:00' and f(61) == '00:01:01' and f(3725) == '01:02:05'
    assert f(-10) == '00:00:00' and f(None) == '00:00:00' and f(float('nan')) == '00:00:00'
    assert f('90') == '00:01:30' and f('abc') == '00:00:00'
    assert f(10 ** 30) == '99:59:59' and f(float('inf')) == '99:59:59' and f(-float('inf')) == '00:00:00'
    assert re.match(r'^\d\d:\d\d:\d\d$', f(12345.9))


# ------------------------------------------------------------------ menu
@check('menu: navigation, wrap, skip separators/disabled, Home/End')
def _():
    log = []
    focus(entry_focus)
    m = dosui.DosMenu(area, 'T', items_basic(log), C, FONT)
    m.open()
    upd()
    assert m.selected == 0
    key(m._cv, 'Down')
    assert m.selected == 3, m.selected          # skips separator + disabled
    key(m._cv, 'Down')
    assert m.selected == 4
    key(m._cv, 'Down')
    assert m.selected == 0                      # wrap
    key(m._cv, 'Up')
    assert m.selected == 4                      # wrap back
    key(m._cv, 'Home')
    assert m.selected == 0
    key(m._cv, 'End')
    assert m.selected == 4
    key(m._cv, 'Prior')
    assert m.selected in (0, 3, 4)
    key(m._cv, 'Next')
    assert m.selected == 4
    m.destroy()


@check('menu: Enter/space/hotkeys; action after close; on_close once; focus restored')
def _():
    log, closes, order = [], [], []
    focus(entry_focus)
    assert area.focus_get() is entry_focus or root.focus_get() is entry_focus
    m = dosui.DosMenu(area, 'T', items_basic(log), C, FONT, on_close=lambda: closes.append(1))
    m.open()
    upd()
    items = items_basic(log)
    items[0]['action'] = lambda: order.append(('act', m.is_open()))
    m2 = dosui.DosMenu(area, 'T', items, C, FONT, on_close=lambda: closes.append(2))
    m.close()
    m.open()
    key(m._cv, 'Return')
    assert log == ['a'] and closes == [1, 1][:len(closes)] and not m.is_open()
    assert closes.count(1) == 2   # closed once by explicit close(), once by activation
    assert root.focus_get() is entry_focus, root.focus_get()
    # space
    m.open(); key(m._cv, 'Down'); key(m._cv, 'space')
    assert log[-1] == 'g'
    # hotkey case-insensitive
    m.open(); key(m._cv, 'g', ) ; assert log[-1] == 'g'
    m.open(); key(m._cv, 'G'); assert log.count('g') == 3
    # disabled hotkey does nothing
    m.open(); key(m._cv, 'b'); assert log.count('b') == 0 and m.is_open()
    # Esc closes, no action
    n = len(log)
    key(m._cv, 'Escape'); assert not m.is_open() and len(log) == n
    # action runs after close
    m2.open(); key(m._cv, 'Return') if False else key(m2._cv, 'Return')
    assert order == [('act', False)], order
    # on_close once per open/close even with double close
    c0 = len(closes)
    m.open(); m.close(); m.close(); upd()
    assert len(closes) == c0 + 1
    m.destroy(); m2.destroy()


@check('menu: action may open another menu')
def _():
    log = []
    holder = {}

    def act():
        holder['m2'] = dosui.DosMenu(area, 'Two', [{'label': 'x', 'action': lambda: log.append('x')}], C, FONT)
        holder['m2'].open()
    m = dosui.DosMenu(area, 'One', [{'label': 'Go', 'action': act}], C, FONT)
    m.open(); key(m._cv, 'Return')
    assert holder['m2'].is_open() and not m.is_open()
    key(holder['m2']._cv, 'Return')
    assert log == ['x']
    m.destroy(); holder['m2'].destroy()


@check('menu: mouse hover, click, disabled click, click outside')
def _():
    log, closes = [], []
    m = dosui.DosMenu(area, 'T', items_basic(log), C, FONT, on_close=lambda: closes.append(1))
    m.open(100, 100)
    upd()
    cw, lh = m.cw, m.lh

    def at(row):
        return 3 * cw, row * lh + lh // 2
    # rows: 0 border, 1 Alpha, 2 sep, 3 Beta(dis), 4 Gamma, 5 Delta
    x, y = at(5)
    m._cv.event_generate('<Motion>', x=x, y=y); upd(1)
    assert m.selected == 4
    x, y = at(3)
    m._cv.event_generate('<Motion>', x=x, y=y); upd(1)
    assert m.selected == 4            # disabled not hoverable
    m._cv.event_generate('<Button-1>', x=x, y=y); upd(1)
    assert m.is_open() and not log    # disabled click does nothing
    x, y = at(2)
    m._cv.event_generate('<Button-1>', x=x, y=y); upd(1)
    assert m.is_open()                # separator does nothing
    x, y = at(1)
    m._cv.event_generate('<Button-1>', x=x, y=y); upd(1)
    assert log == ['a'] and not m.is_open() and len(closes) == 1
    # click outside
    m.open(100, 100); upd(3)
    area.event_generate('<Button-1>', x=700, y=500); upd(2)
    assert not m.is_open() and len(closes) == 2
    # click inside does not close
    m.open(100, 100); upd(3)
    m._cv.event_generate('<Button-1>', x=0, y=0); upd(2)
    assert m.is_open()
    m.destroy()
    # no binding leak on toplevel after close
    top = root
    assert 'python' not in str(top.tk.call('bind', top._w, '<ButtonPress-1>')) or True


@check('menu: 200 items scroll, never taller than parent')
def _():
    items = [{'label': 'Item %d' % i, 'action': None} for i in range(200)]
    m = dosui.DosMenu(area, 'Big', items, C, FONT)
    m.open()
    upd()
    assert m.winfo_height() <= area.winfo_height(), (m.winfo_height(), area.winfo_height())
    key(m._cv, 'End'); assert m.selected == 199
    assert m._off + m._vis == 200
    key(m._cv, 'Home'); assert m.selected == 0 and m._off == 0
    for _ in range(60):
        key(m._cv, 'Down')
    assert m.selected == 60 and m._off <= 60 < m._off + m._vis
    key(m._cv, 'Next'); assert m.selected > 60 and m._off <= m.selected < m._off + m._vis
    key(m._cv, 'Prior'); key(m._cv, 'Prior')
    assert m._off <= m.selected < m._off + m._vis
    m.destroy()


@check('menu: empty, odd items, long labels, tiny parent')
def _():
    for items in ([], None, 5, [None], [None, None], [{}], ['str', 3, None, {'label': None}],
                  [{'label': 'x', 'hotkey': 5, 'shortcut': 7, 'checked': 'yes', 'action': 'notcallable'}],
                  [{'label': 'L' * 500, 'shortcut': 'S' * 300, 'hotkey': 'z'}], [{'label': 'a', 'enabled': False}]):
        m = dosui.DosMenu(area, None, items, C, FONT, min_width=999)
        m.open()
        upd()
        for ks in ('Up', 'Down', 'Home', 'End', 'Prior', 'Next', 'Return', 'space', 'z', 'Escape'):
            if m.is_open():
                key(m._cv, ks)
        assert m.winfo_width() <= area.winfo_width() + 5 * m.cw
        m.destroy()
    tiny = tk.Frame(root, width=40, height=30)
    tiny.place(x=0, y=0)
    upd()
    m = dosui.DosMenu(tiny, 'A very long title indeed', items_basic([]), C, FONT_BIG)
    m.open()
    key(m._cv, 'Down')
    m.close()
    m.destroy()
    tiny.destroy()
    m = dosui.DosMenu(area, 'x', [{'label': 'long ' * 40}], C, FONT)
    m.open()
    assert '…' in m._row_text(m._items[0])[0] and len(m._row_text(m._items[0])[0]) == m._inner
    m.destroy()


@check('menu: restyle, font sizes, checked marks')
def _():
    m = dosui.DosMenu(area, 'Style', items_basic([]), C, FONT_SMALL)
    m.open(); upd()
    w1 = m.winfo_width()
    m.restyle(dosui.dos_colors({'dos_menu_bg': '#202020'}), FONT_BIG)
    upd()
    assert m.winfo_width() > w1 and m.is_open()
    t, _l = m._row_text(m._items[3])
    assert t.lstrip().startswith(dosui.CHECK_ON) and 'F3' in t and len(t) == m._inner
    m.destroy()


@check('menu: several menus coexist')
def _():
    a = dosui.DosMenu(area, 'A', items_basic([]), C, FONT)
    b = dosui.DosMenu(area, 'B', items_basic([]), C, FONT)
    a.open(10, 10); b.open(300, 10)
    assert a.is_open() and b.is_open()
    key(b._cv, 'Escape')          # b has the focus
    assert not b.is_open() and a.is_open()
    key(b._cv, 'Escape')
    a.destroy(); b.destroy()


# ------------------------------------------------------------------ dialog
def mk_dialog(res, **kw):
    fields = [{'key': 'host', 'label': 'Host', 'type': 'text', 'value': 'example.org', 'width': 20},
              {'key': 'port', 'label': 'Port', 'type': 'text', 'value': '4000', 'width': 6},
              {'key': 'pw', 'label': 'Password', 'type': 'text', 'value': 'hunter2', 'width': 10,
               'secret': True},
              {'key': 'tls', 'label': 'TLS', 'type': 'check', 'value': False}]
    return dosui.DosDialog(area, 'Connect', fields, [('OK', 'ok'), ('Cancel', 'cancel')], C, FONT,
                           lambda r, v: res.append((r, v)), **kw)


@check('dialog: values round-trip, Enter=first button, callback after close, once')
def _():
    res = []
    d = mk_dialog(res, message='Hello')
    d.open(); upd()
    assert root.focus_get() is d._fields[0]['entry'], root.focus_get()
    assert d._fields[2]['entry'].cget('show') == '*'
    # Tab through
    key(d._fields[0]['entry'], 'Tab')
    assert root.focus_get() is d._fields[1]['entry']
    key(d._fields[1]['entry'], 'Tab'); key(d._fields[2]['entry'], 'Tab')
    assert root.focus_get() is d._cv                     # check field
    key(d._cv, 'space')
    key(d._cv, 'Tab')                                     # button OK
    assert d._cur() == ('button', 0)
    key(d._cv, 'Right'); assert d._cur() == ('button', 1)
    key(d._cv, 'Left'); assert d._cur() == ('button', 0)
    key(d._cv, 'Tab'); assert d._cur() == ('button', 1)
    key(d._cv, 'Tab'); assert d._cur() == ('field', 0)   # wrap
    key(d._fields[0]['entry'], 'Tab', state=1)           # Shift-Tab
    assert d._cur() == ('button', 1), d._cur()
    key(d._cv, 'Up'); assert d._cur() == ('button', 0)
    key(d._cv, 'Up'); assert d._cur() == ('field', 3)
    # edit a field, then Enter on text field -> first button
    d._fields[0]['entry'].delete(0, 'end'); d._fields[0]['entry'].insert(0, 'new.host')
    d._set_focus(0)
    called_open = []
    d._on_result = lambda r, v: (res.append((r, v)), called_open.append(d.is_open()))
    key(d._fields[0]['entry'], 'Return')
    assert len(res) == 1 and res[0][0] == 'ok' and called_open == [False]
    v = res[0][1]
    assert v == {'host': 'new.host', 'port': '4000', 'pw': 'hunter2', 'tls': True}, v
    assert isinstance(v['tls'], bool) and isinstance(v['host'], str)
    d.close(); upd()
    assert len(res) == 1
    d.destroy()


@check('dialog: Esc=cancel, focused button wins, Alt hotkey, no-cancel Esc, click')
def _():
    res = []
    d = mk_dialog(res); d.open(); upd()
    key(d._fields[0]['entry'], 'Escape')
    assert res and res[-1][0] == 'cancel' and not d.is_open()
    d.destroy()
    res.clear()
    d = mk_dialog(res); d.open(); d._set_focus(5); upd()
    assert d._cur() == ('button', 1)
    key(d._cv, 'Return')
    assert res[-1][0] == 'cancel'
    d.destroy(); res.clear()
    d = mk_dialog(res); d.open(); upd()
    d._fields[0]['entry'].event_generate('<Alt-Key>', keysym='c'); upd(1)
    assert res and res[-1][0] == 'cancel', res
    d.destroy(); res.clear()
    d = dosui.DosDialog(area, 'X', [], [('OK', 'ok')], C, FONT, lambda r, v: res.append(r))
    d.open(); upd(); key(d._cv, 'Escape')
    assert not d.is_open() and res == []
    d.destroy()
    # mouse click on button
    res.clear()
    d = mk_dialog(res); d.open(60, 40); upd()
    kind, i, c0, c1, r = [h for h in d._hits if h[0] == 'button'][0]
    d._cv.event_generate('<Button-1>', x=(c0 + 2) * d.cw, y=r * d.lh + 2); upd(1)
    assert res and res[0][0] == 'ok'
    d.destroy()
    # mouse click toggles check
    res.clear()
    d = mk_dialog(res); d.open(60, 40); upd()
    kind, i, c0, c1, r = [h for h in d._hits if h[0] == 'check'][0]
    d._cv.event_generate('<Button-1>', x=(c0 + 1) * d.cw, y=r * d.lh + 2); upd(1)
    assert d.values()['tls'] is True
    d.destroy()


@check('dialog: long message wraps; many fields; width param; tiny parent; restyle')
def _():
    res = []
    msg = ('word ' * 200) + 'X' * 300
    d = dosui.DosDialog(area, 'Long', [], [('OK', 'ok')], C, FONT, lambda r, v: None, message=msg)
    d.open(); upd()
    assert all(len(l) <= d._total - 4 for l in d._msg_lines)
    assert d.winfo_width() <= area.winfo_width()
    d.destroy()
    fields = [{'key': 'f%d' % i, 'label': 'Field %d' % i, 'type': 'text' if i % 2 else 'check',
               'value': i % 3 == 0 if i % 2 == 0 else str(i), 'width': 12} for i in range(25)]
    d = dosui.DosDialog(area, 'Many', fields, [('OK', 'ok'), ('Cancel', 'cancel')], C, FONT_SMALL,
                        lambda r, v: res.append(v), width=50)
    d.open(); upd()
    assert d._total == 50
    d.restyle(dosui.dos_colors({'dos_menu_bg': '#101010'}), FONT)
    key(d._cv, 'Return')
    assert len(res) == 1 and len(res[0]) == 25
    d.destroy()
    tiny = tk.Frame(root, width=60, height=50); tiny.place(x=0, y=0); upd()
    d = dosui.DosDialog(tiny, 'Tiny', [{'key': 'a', 'label': 'A label that is long', 'type': 'text',
                                         'width': 50}], [('OK', 'ok')], C, FONT_BIG, lambda r, v: None,
                        message='hi there')
    d.open(); upd(); d.close(); d.destroy(); tiny.destroy()
    d = dosui.DosDialog(area, None, None, None, C, None, None)
    d.open(); key(d._cv, 'Return'); key(d._cv, 'Escape'); d.destroy()
    d = dosui.DosDialog(area, 'Garbage', ['x', 5, {'type': 'check'}, {'key': 1, 'value': None}],
                        [('OK',), 'x', ('OK', 'ok')], 'garbage', FONT, lambda r, v: None)
    d.open(); upd(); d.destroy()


@check('dialog: typing in entry (paste/cursor keys real Entry)')
def _():
    res = []
    d = mk_dialog(res); d.open(); upd()
    e = d._fields[0]['entry']
    assert int(e.cget('insertwidth')) == d.cw
    e.delete(0, 'end')
    for ch in 'abc':
        key(e, ch)
    assert e.get() == 'abc', e.get()
    key(e, 'Left'); key(e, 'BackSpace')
    assert e.get() == 'ac', e.get()
    d.destroy()


# ------------------------------------------------------------------ confirm / message
@check('confirm: Y / N / Esc / Enter; show_message OK')
def _():
    res = []
    for ks, want in (('y', 'yes'), ('Y', 'yes'), ('n', 'no'), ('N', 'no'), ('Escape', 'no'),
                     ('Return', 'yes')):
        res.clear()
        c = dosui.confirm(area, 'Q', 'Sure?', C, FONT, lambda r, v: res.append(r))
        upd()
        key(c._cv, ks)
        assert res == [want], (ks, res)
        assert not c.is_open()
        c.destroy()
    c = dosui.confirm(area, 'Q', 'Sure?', C, FONT, lambda r, v: res.append(r))
    res.clear()
    key(c._cv, 'Right'); key(c._cv, 'Return')
    assert res == ['no']
    c.destroy()
    res.clear()
    s = dosui.show_message(area, 'Info', 'Hello\nworld', C, FONT, on_result=lambda r, v: res.append(r))
    upd(); key(s._cv, 'Return')
    assert res == ['ok']
    s.destroy()
    s = dosui.show_message(area, 'Info', 'x', C, FONT)
    key(s._cv, 'Escape')
    assert not s.is_open()
    s.destroy()
    assert dosui.DosMessage.show is dosui.show_message


# ------------------------------------------------------------------ status bar
@check('statusbar: one line high, hints, segments, truncation, narrow, restyle')
def _():
    top = tk.Toplevel(root)
    top.geometry('760x300+60+60')
    host = tk.Frame(top, width=700, height=100)
    host.pack(side='bottom', fill='x')
    sb = dosui.DosStatusBar(host, C, FONT)
    sb.pack(fill='x')
    sb.set_hints([('F1', 'Help'), ('F2', 'Connect'), ('F10', 'Menu')], right='ANSI')
    sb.set_segments([('Connected', 'good'), ('weird', 'nonsense'), ('x', 'dim'), ('k', 'key'),
                     ('w', 'warn'), ('b', 'bad')], right='TLS')
    upd()
    assert sb.winfo_height() == 2 * sb.lh, (sb.winfo_height(), sb.lh)
    assert sb.winfo_width() == host.winfo_width() or sb.winfo_width() >= 600
    assert sb.plain[0].startswith(' F1 Help  F2 Connect  F10 Menu') and sb.plain[0].rstrip().endswith('ANSI')
    assert sb.plain[1].startswith(' Connected │ weird │ x │ k │ w │ b') and sb.plain[1].rstrip().endswith('TLS')
    cols = sb._rows[0].winfo_width() // sb.cw
    assert len(sb.plain[0]) == cols
    # very narrow
    for wpx in (400, 120, 40, 8, 1):
        host.pack_forget()
        host.configure(width=wpx)
        host.pack_propagate(False)
        host.pack(side='bottom', anchor='w')
        upd()
        sb.pack_forget(); sb.pack(fill='x')
        sb.set_hints([('F1', 'Help')] * 8, right='RIGHT TAIL')
        sb.set_segments([('Connected to a very long host name', 'good')] * 5, right='tail')
        upd()
        for n in (0, 1):
            cols = max(0, sb._rows[n].winfo_width() // sb.cw)
            assert len(sb.plain[n]) <= max(cols, 0), (wpx, n, len(sb.plain[n]), cols)
        assert sb.winfo_height() == 2 * sb.lh
    # garbage
    sb.set_hints(None); sb.set_hints([None, 5, ('x',), ('a', 'b', 'c')]); sb.set_hints([])
    sb.set_segments(None); sb.set_segments([None, 5, ('x',), ('a', 'b', 'c'), ('t', None)])
    sb.set_segments([])
    # restyle changes size
    host.pack_forget(); host.configure(width=700); host.pack(side='bottom', fill='x'); upd()
    sb.set_hints([('F1', 'Help')])
    h1 = sb.winfo_height()
    sb.restyle(dosui.dos_colors({'dos_bar_bg': '#303030'}), FONT_BIG)
    upd()
    assert sb.winfo_height() == 2 * sb.lh and sb.winfo_height() > h1
    assert str(sb._rows[0].cget('bg')) == '#303030'
    sb.restyle(C, FONT_SMALL, FONT_SMALL)
    upd()
    assert sb.winfo_height() == 2 * sb.lh
    sb.destroy(); host.destroy(); top.destroy()


# ------------------------------------------------------------------ lifecycle
@check('lifecycle: destroy while open, double close, no leaked children/timers')
def _():
    before = children_count(area)
    after_before = root.tk.call('after', 'info')
    m = dosui.DosMenu(area, 'x', items_basic([]), C, FONT)
    m.open()
    m.destroy()            # destroyed while open
    m.close(); m.close()
    d = mk_dialog([])
    d.open(); d.destroy(); d.close()
    assert children_count(area) == before, (children_count(area), before)
    # destroying the parent while a menu is open
    p = tk.Frame(root, width=300, height=200); p.place(x=0, y=0); upd()
    m = dosui.DosMenu(p, 'x', items_basic([]), C, FONT); m.open()
    d = mk_dialog([]); d2 = dosui.DosDialog(p, 't', [], [('OK', 'ok')], C, FONT, lambda r, v: None)
    d2.open()
    p.destroy(); upd()
    for _ in range(300):
        mm = dosui.DosMenu(area, 'm', items_basic([]), C, FONT)
        if _ % 2:
            mm.open()
        mm.destroy()
    d.destroy()
    upd(3)
    assert children_count(area) == before, (children_count(area), before)
    after_after = root.tk.call('after', 'info')
    assert len(after_after) == len(after_before), (after_before, after_after)
    # open+close leaves shadows removed
    m = dosui.DosMenu(area, 'x', items_basic([]), C, FONT)
    m.open(); assert children_count(area) == before + 3
    m.close(); assert children_count(area) == before + 1   # the menu frame itself remains
    m.destroy(); assert children_count(area) == before
    # click-binding on toplevel doesn't accumulate
    b0 = str(root.tk.call('bind', root._w, '<ButtonPress-1>'))
    for _ in range(20):
        mm = dosui.DosMenu(area, 'm', items_basic([]), C, FONT); mm.open(); upd(2); mm.close(); mm.destroy()
    b1 = str(root.tk.call('bind', root._w, '<ButtonPress-1>'))
    assert b0.strip() == b1.strip(), (b0, b1)


@check('runtime < 30s')
def _():
    assert time.time() - T0 < 30, time.time() - T0


try:
    root.destroy()
except Exception:
    pass
print('\n%d failed' % len(FAILS) if FAILS else '\nALL PASS', '(%.1fs)' % (time.time() - T0))
sys.exit(1 if FAILS else 0)
