"""Layout engine for in-client capture panes (stdlib only, no GUI imports).

Panes are grouped into regions docked to one side of the main text area.
Everything here is pure data in / pure data out; every input is untrusted.
"""

import math
import re

MIN_MAIN_COLS = 80
SIDES = ('top', 'bottom', 'left', 'right')
MAX_REGIONS = 4
MAX_PANES = 12

_BANDS = ('top', 'bottom')
_NAME_MAX = 24
_SCAN_LIMIT = 200          # never look at more than this many list items
_MIN_MAIN_ROWS = 6         # main area minimum height, in text lines
_MIN_BAND_ROWS = 3
_MIN_COL_COLS = 16
_SIDE_LABEL = {'top': 'Top strip', 'bottom': 'Bottom strip',
               'left': 'Left column', 'right': 'Right column'}
_SIDE_PHRASE = {'top': 'top strip', 'bottom': 'bottom strip',
                'left': 'left column', 'right': 'right column'}


# ---------------------------------------------------------------- helpers

def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _clamp_int(v, lo, hi, default):
    """Strict int (no bool/float) clamped to lo..hi, else default."""
    if not _is_int(v):
        return default
    return max(lo, min(hi, v))


def _clean_name(s):
    """Printable, stripped, at most 24 chars; '' when nothing is left."""
    if not isinstance(s, str):
        return ''
    s = s[:256]
    s = ''.join(c for c in s if c.isprintable()).strip()
    return s[:_NAME_MAX].strip()


# ------------------------------------------------------------- validators

def validate_pane(d):
    if not isinstance(d, dict):
        return None
    name = _clean_name(d.get('name'))
    if not name:
        return None
    title = _clean_name(d.get('title')) or name
    ts = d.get('timestamps')
    out = {
        'name': name,
        'title': title,
        'max_lines': _clamp_int(d.get('max_lines'), 100, 20000, 2000),
        'timestamps': ts if isinstance(ts, bool) else False,
    }
    if d.get('show_sent') is False:             # "show what I send" is on unless it was turned off
        out['show_sent'] = False
    win = d.get('window')                       # where the pane's own window was, and whether it was out
    if isinstance(win, dict):
        w = {}
        if isinstance(win.get('out'), bool):
            w['out'] = win['out']
        if isinstance(win.get('top'), bool):
            w['top'] = win['top']
        if isinstance(win.get('input'), bool):
            w['input'] = win['input']
        if win.get('phone') in ('iphone', 'android'):     # drawn as a phone (see phonelook.py); off when absent
            w['phone'] = win['phone']
        pre = win.get('prefix')                       # what the window's own input bar puts in front of what you type
        if isinstance(pre, str):
            pre = ' '.join(''.join(ch for ch in pre if ch.isprintable()).split())[:40]
            if pre:
                w['prefix'] = pre
        g = win.get('geometry')
        if isinstance(g, str) and len(g) <= 40 and re.match(r'^\d+x\d+([+-]-?\d+){0,2}$', g):
            w['geometry'] = g
        if w:
            out['window'] = w
    return out


def validate_panes(lst):
    out = []
    if not isinstance(lst, (list, tuple)):
        return out
    seen = set()
    for item in lst[:_SCAN_LIMIT * 5]:
        p = validate_pane(item)
        if p is None:
            continue
        key = p['name'].casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
        if len(out) >= MAX_PANES:
            break
    return out


def _known_set(known_panes):
    if known_panes is None:
        return None
    out = set()
    try:
        for i, n in enumerate(known_panes):
            if i > 10000:
                break
            c = _clean_name(n)
            if c:
                out.add(c.casefold())
    except Exception:
        pass
    return out


def validate_layout(d, known_panes=None):
    out = {'regions': [], 'min_main_cols': MIN_MAIN_COLS}
    try:
        if not isinstance(d, dict):
            return out
        out['min_main_cols'] = _clamp_int(d.get('min_main_cols'), 40, 200,
                                          MIN_MAIN_COLS)
        regions = d.get('regions')
        if not isinstance(regions, (list, tuple)):
            return out
        known = _known_set(known_panes)
        seen = set()
        for r in regions[:_SCAN_LIMIT]:
            if len(out['regions']) >= MAX_REGIONS:
                break
            if not isinstance(r, dict):
                continue
            side = r.get('side')
            if not isinstance(side, str):
                continue
            side = side.strip().lower()
            if side not in SIDES:
                continue
            if side in _BANDS:
                size = _clamp_int(r.get('size'), 3, 40, 6)
            else:
                size = _clamp_int(r.get('size'), 16, 100, 36)
            weight = _clamp_int(r.get('weight'), 1, 9, 1)
            panes = []
            raw = r.get('panes')
            if isinstance(raw, (list, tuple)):
                for n in raw[:_SCAN_LIMIT]:
                    if len(panes) >= MAX_PANES:
                        break
                    c = _clean_name(n)
                    if not c:
                        continue
                    key = c.casefold()
                    if key in seen:
                        continue
                    if known is not None and key not in known:
                        continue
                    seen.add(key)
                    panes.append(c)
            out['regions'].append({
                'id': 'r%d' % (len(out['regions']) + 1),
                'side': side, 'size': size, 'weight': weight,
                'panes': panes})
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- presets

def _tpl(rid, side, size, weight=1):
    return {'id': rid, 'side': side, 'size': size, 'weight': weight}


PRESETS = {
    'Long strip on top': {
        'description': 'One wide strip above the main text.',
        'regions': [_tpl('r1', 'top', 6)]},
    'Long strip on the bottom': {
        'description': 'One wide strip below the main text.',
        'regions': [_tpl('r1', 'bottom', 6)]},
    'Right column': {
        'description': 'One column to the right of the main text.',
        'regions': [_tpl('r1', 'right', 36)]},
    'Right column, two stacked': {
        'description': 'Two columns stacked on the right of the main text.',
        'regions': [_tpl('r1', 'right', 36), _tpl('r2', 'right', 36)]},
    'Left column': {
        'description': 'One column to the left of the main text.',
        'regions': [_tpl('r1', 'left', 36)]},
    'Top strip + right column': {
        'description': 'A short strip on top and a column on the right.',
        'regions': [_tpl('r1', 'top', 5), _tpl('r2', 'right', 34)]},
}


def preset_layout(name, panes):
    preset = PRESETS.get(name) if isinstance(name, str) else None
    if preset is None:
        preset = PRESETS[next(iter(PRESETS))]
    names = []
    if isinstance(panes, (list, tuple)):
        for p in panes[:_SCAN_LIMIT]:
            if isinstance(p, dict):
                p = p.get('name')
            names.append(p)
    regions = [dict(t, panes=[]) for t in preset['regions']]
    for i, n in enumerate(names):
        regions[i % len(regions)]['panes'].append(n)
    return validate_layout({'regions': regions,
                            'min_main_cols': MIN_MAIN_COLS})


# ------------------------------------------------------------- geometry

def _num(v, default, hi, allow_zero=False):
    if v is None or isinstance(v, bool):
        return default
    if isinstance(v, float):
        if not math.isfinite(v):
            return default
        v = int(v)
    elif not isinstance(v, int):
        return default
    if v < (0 if allow_zero else 1):
        return default
    return min(v, hi)


def _split(start, length, weights, gap, minlen):
    """Divide `length` among len(weights) items by weight; returns
    [(pos, size)] or None when it cannot give each item `minlen`."""
    n = len(weights)
    avail = length - gap * (n - 1)
    extra = avail - n * minlen
    if extra < 0:
        return None
    total = sum(weights)
    out = []
    pos = start
    cum = 0
    prev = 0
    for w in weights:
        cum += w
        cur = extra * cum // total
        size = minlen + cur - prev
        prev = cur
        out.append((pos, size))
        pos += size + gap
    return out


def _fallback(W, H, ids):
    return {'main': (0, 0, W, H), 'regions': {}, 'hidden': list(ids),
            'notes': []}


def compute_layout(layout, width, height, cw, lh, header_h=None, gap=0,
                   pad_x=16):
    W = _num(width, 1, 10 ** 7)
    H = _num(height, 1, 10 ** 7)
    try:
        return _compute(layout, W, H, cw, lh, header_h, gap, pad_x)
    except Exception:
        return _fallback(W, H, [])


def _compute(layout, W, H, cw, lh, header_h, gap, pad_x):
    lay = validate_layout(layout)
    cw = _num(cw, 8, 10 ** 4)
    lh = _num(lh, 16, 10 ** 4)
    hh = _num(header_h, lh + 4, 10 ** 5)
    gap = _num(gap, 0, 10 ** 4, allow_zero=True)
    pad = _num(pad_x, 16, 10 ** 5, allow_zero=True)
    regions = lay['regions']
    mmc = lay['min_main_cols']
    need_w = mmc * cw + pad
    need_h = _MIN_MAIN_ROWS * lh

    by_side = {s: [] for s in SIDES}
    for i, r in enumerate(regions):
        by_side[r['side']].append(i)
    base_units = {s: max(regions[i]['size'] for i in by_side[s])
                  for s in SIDES if by_side[s]}
    last_idx = {s: max(by_side[s]) for s in base_units}

    def thick(s, u):
        return u * lh + hh if s in _BANDS else u * cw + pad

    def attempt(vis):
        units = {s: base_units[s] for s in vis}
        notes = []
        bands = [s for s in vis if s in _BANDS]
        cols = [s for s in vis if s not in _BANDS]

        def mids():
            mh = H - sum(thick(s, units[s]) for s in bands) - gap * len(bands)
            mw = W - sum(thick(s, units[s]) for s in cols) - gap * len(cols)
            return mw, mh

        mw, mh = mids()
        # shrink bands for height, last-declared side first
        dh = need_h - mh
        for s in sorted(bands, key=lambda k: -last_idx[k]):
            if dh <= 0:
                break
            take = min(units[s] - _MIN_BAND_ROWS, -(-dh // lh))
            if take > 0:
                units[s] -= take
                dh -= take * lh
                notes.append('%s reduced to %d rows to keep %d lines of '
                             'main text' % (_SIDE_LABEL[s], units[s],
                                            _MIN_MAIN_ROWS))
        dw = need_w - mw
        for s in sorted(cols, key=lambda k: -last_idx[k]):
            if dw <= 0:
                break
            take = min(units[s] - _MIN_COL_COLS, -(-dw // cw))
            if take > 0:
                units[s] -= take
                dw -= take * cw
                notes.append('%s narrowed to %d columns to keep %d columns '
                             'of main text' % (_SIDE_LABEL[s], units[s], mmc))
        mw, mh = mids()
        bad_w = mw < need_w
        bad_h = mh < need_h
        viol = []
        for s in vis:
            ws = [regions[i]['weight'] for i in by_side[s]]
            if s in _BANDS:
                ok = _split(0, W, ws, gap, cw) is not None
            else:
                ok = _split(0, mh, ws, gap, hh + lh) is not None
            if not ok:
                viol.append(s)
        ok = not (bad_w or bad_h or viol)
        return ok, units, notes, bad_w, bad_h, viol, mw, mh

    hidden = []
    hide_notes = []
    while True:
        vis = [s for s in SIDES if s in base_units and s not in hidden]
        if not vis:
            res = None
            break
        res = attempt(vis)
        if res[0]:
            break
        _, _, _, bad_w, bad_h, viol, _, _ = res
        if bad_w and not bad_h:
            cand = [s for s in vis if s not in _BANDS]
        elif bad_h and not bad_w:
            cand = [s for s in vis if s in _BANDS]
        elif bad_w and bad_h:
            cand = list(vis)
        else:
            cand = list(viol)
        if not cand:
            cand = list(vis)
        victim = max(cand, key=lambda k: last_idx[k])
        hidden.append(victim)
        hide_notes.append('%s hidden: window too small'
                          % _SIDE_LABEL[victim])

    if res is None:
        return {'main': (0, 0, W, H), 'regions': {},
                'hidden': [r['id'] for r in regions], 'notes': hide_notes}

    _, units, shrink_notes, _, _, _, mw, mh = res
    top_t = thick('top', units['top']) if 'top' in units else 0
    bot_t = thick('bottom', units['bottom']) if 'bottom' in units else 0
    left_t = thick('left', units['left']) if 'left' in units else 0
    right_t = thick('right', units['right']) if 'right' in units else 0
    mid_y = top_t + (gap if 'top' in units else 0)
    mid_x = left_t + (gap if 'left' in units else 0)
    out_regions = {}

    def put(rid, x, y, w, h):
        out_regions[rid] = {'rect': (x, y, w, h),
                            'header': (x, y, w, hh),
                            'body': (x, y + hh, w, h - hh)}

    for s in SIDES:
        if s not in units:
            continue
        idxs = by_side[s]
        ws = [regions[i]['weight'] for i in idxs]
        t = thick(s, units[s])
        if s in _BANDS:
            parts = _split(0, W, ws, gap, cw)
            y = 0 if s == 'top' else H - t
            for i, (px, sz) in zip(idxs, parts):
                put(regions[i]['id'], px, y, sz, t)
        else:
            parts = _split(mid_y, mh, ws, gap, hh + lh)
            x = 0 if s == 'left' else W - t
            for i, (py, sz) in zip(idxs, parts):
                put(regions[i]['id'], x, py, t, sz)

    hidden_ids = [r['id'] for r in regions if r['side'] in hidden]
    return {'main': (mid_x, mid_y, mw, mh), 'regions': out_regions,
            'hidden': hidden_ids, 'notes': hide_notes + shrink_notes}


# ---------------------------------------------------------------- preview

_U, _D, _L, _R = 1, 2, 4, 8
_BOX = {0: ' ', _U: '│', _D: '│', _U | _D: '│', _L: '─', _R: '─',
        _L | _R: '─', _D | _R: '┌', _D | _L: '┐', _U | _R: '└',
        _U | _L: '┘', _U | _D | _R: '├', _U | _D | _L: '┤',
        _L | _R | _D: '┬', _L | _R | _U: '┴', _U | _D | _L | _R: '┼'}
for _m in range(16):
    if _m not in _BOX:
        # three-way combos not listed above already; this covers none, but
        # keep the table total so rendering can never KeyError.
        _BOX[_m] = '┼'


def _fit_text(s, width):
    if width <= 0:
        return ''
    if len(s) <= width:
        return s
    if width == 1:
        return '…'
    return s[:width - 1] + '…'


def _blank(cols, rows):
    return [' ' * cols for _ in range(rows)]


def ascii_preview(layout, cols=60, rows=18, ref_cells=(160, 48)):
    cols = _num(cols, 60, 500)
    rows = _num(rows, 18, 200)
    try:
        return _preview(layout, cols, rows, ref_cells)
    except Exception:
        return _blank(cols, rows)


def _preview(layout, cols, rows, ref_cells):
    lay = validate_layout(layout)
    rc, rr = 160, 48
    if isinstance(ref_cells, (list, tuple)) and len(ref_cells) == 2:
        rc = _num(ref_cells[0], 160, 2000)
        rr = _num(ref_cells[1], 48, 2000)
    comp = compute_layout(lay, rc, rr, 1, 1, header_h=1, gap=0, pad_x=0)
    hidden = comp['hidden']
    by_id = {r['id']: r for r in lay['regions']}
    diag_rows = rows - 1 if (hidden and rows >= 2) else rows

    def mx(v):
        return (v * (cols - 1) + rc // 2) // rc

    def my(v):
        return (v * (diag_rows - 1) + rr // 2) // rr

    grid = [[0] * cols for _ in range(diag_rows)]
    text = {}

    def hline(y, xa, xb):
        for x in range(xa, xb):
            grid[y][x] |= _R
            grid[y][x + 1] |= _L

    def vline(x, ya, yb):
        for y in range(ya, yb):
            grid[y][x] |= _D
            grid[y + 1][x] |= _U

    def put_text(y, xa, xb, s):
        inner = xb - xa - 1
        s = _fit_text(s, inner)
        if not s:
            return
        start = xa + 1 + (inner - len(s)) // 2
        for k, ch in enumerate(s):
            text[(y, start + k)] = ch

    def box(rect, label, header):
        x, y, w, h = rect
        x0, x1 = mx(x), mx(x + w)
        y0, y1 = my(y), my(y + h)
        if x1 <= x0 or y1 <= y0:
            return
        hline(y0, x0, x1)
        hline(y1, x0, x1)
        vline(x0, y0, y1)
        vline(x1, y0, y1)
        if header:
            if y1 - y0 >= 4:
                hline(y0 + 2, x0, x1)
                put_text(y0 + 1, x0, x1, label)
            elif y1 - y0 >= 2:
                put_text(y0 + 1, x0, x1, label)
        else:
            put_text((y0 + y1) // 2, x0, x1, label)

    box(comp['main'], 'MAIN', False)
    for rid, g in comp['regions'].items():
        names = by_id[rid]['panes']
        box(g['rect'], ' | '.join(names) if names else '(empty)', True)

    lines = []
    for y in range(diag_rows):
        chars = []
        for x in range(cols):
            chars.append(text.get((y, x)) or _BOX[grid[y][x]])
        lines.append(''.join(chars))
    if diag_rows < rows:
        items = []
        for rid in hidden:
            names = by_id[rid]['panes']
            items.append('%s (%s)' % (rid, ', '.join(names) if names
                                      else 'empty'))
        last = _fit_text('hidden: ' + ', '.join(items), cols)
        lines.append(last.ljust(cols))
    return lines


# --------------------------------------------------------------- helpers

def layout_summary(layout):
    lay = validate_layout(layout)
    if not lay['regions']:
        return 'no panes docked'
    parts = []
    for r in lay['regions']:
        unit = 'rows' if r['side'] in _BANDS else 'cols'
        names = ', '.join(r['panes']) if r['panes'] else '(empty)'
        parts.append('%s %d %s: %s' % (_SIDE_PHRASE[r['side']], r['size'],
                                       unit, names))
    return ' | '.join(parts)


def region_pane_names(layout):
    lay = validate_layout(layout)
    out = []
    for r in lay['regions']:
        out.extend(r['panes'])
    return out


def find_region(layout, pane_name):
    if not isinstance(pane_name, str):
        return None
    key = pane_name.strip().casefold()
    lay = validate_layout(layout)
    for r in lay['regions']:
        for n in r['panes']:
            if n.casefold() == key:
                return r
    return None
