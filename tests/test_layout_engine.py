"""Tests for layout.py (pane layout engine).  Run: python tests/test_layout_engine.py"""
import copy
import json
import os
import random
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import layout as L  # noqa: E402

CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


# ---------------------------------------------------------------- helpers

def overlap(a, b):
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and
            a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def all_rects(res):
    out = [('main', res['main'])]
    for rid, g in res['regions'].items():
        out.append((rid, g['rect']))
    return out


def check_invariants(res, W, H, hh):
    rects = all_rects(res)
    for name, r in rects:
        assert len(r) == 4 and all(type(v) is int for v in r), (name, r)
        assert r[2] > 0 and r[3] > 0, (name, r)
        assert r[0] >= 0 and r[1] >= 0 and r[0] + r[2] <= W and r[1] + r[3] <= H, (name, r, W, H)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not overlap(rects[i][1], rects[j][1]), (rects[i], rects[j])
    for rid, g in res['regions'].items():
        x, y, w, h = g['rect']
        assert g['header'] == (x, y, w, hh), (g, hh)
        assert g['body'] == (x, y + hh, w, h - hh), g
        assert g['body'][3] > 0
    for rid in res['hidden']:
        assert rid not in res['regions']


def mk(*regions, mmc=80):
    return {'regions': [dict(id='x', side=s, size=sz, weight=w, panes=list(p))
                        for (s, sz, w, p) in regions], 'min_main_cols': mmc}


def rand_layout(rnd):
    regs = []
    for _ in range(rnd.randint(0, 5)):
        side = rnd.choice(L.SIDES + ('bogus',))
        regs.append({'side': side,
                     'size': rnd.choice([rnd.randint(-5, 120), 'x', 3.5, None, True]),
                     'weight': rnd.choice([rnd.randint(-2, 12), None, 'a']),
                     'panes': ['P%d' % rnd.randint(0, 20) for _ in range(rnd.randint(0, 4))]})
    return {'regions': regs, 'min_main_cols': rnd.choice([80, 40, 200, 10, 999, None, 'z'])}


# ------------------------------------------------------------ validators

@check
def pane_defaults_and_clamps():
    p = L.validate_pane({'name': '  OOC  '})
    assert p == {'name': 'OOC', 'title': 'OOC', 'max_lines': 2000, 'timestamps': False}, p
    assert L.validate_pane({'name': 'a', 'max_lines': 5})['max_lines'] == 100
    assert L.validate_pane({'name': 'a', 'max_lines': 10 ** 9})['max_lines'] == 20000
    assert L.validate_pane({'name': 'a', 'max_lines': 100})['max_lines'] == 100
    assert L.validate_pane({'name': 'a', 'max_lines': 20000})['max_lines'] == 20000
    assert L.validate_pane({'name': 'a', 'max_lines': 1.5})['max_lines'] == 2000
    assert L.validate_pane({'name': 'a', 'max_lines': True})['max_lines'] == 2000
    assert L.validate_pane({'name': 'a', 'max_lines': -3})['max_lines'] == 100
    assert L.validate_pane({'name': 'a', 'timestamps': 1})['timestamps'] is False
    assert L.validate_pane({'name': 'a', 'timestamps': True})['timestamps'] is True
    assert L.validate_pane({'name': 'a', 'title': 'T'})['title'] == 'T'
    assert L.validate_pane({'name': 'a', 'title': '   '})['title'] == 'a'
    assert L.validate_pane({'name': 'a', 'title': 5})['title'] == 'a'


@check
def pane_name_rules():
    for bad in (None, 5, [], 'str', {}, {'name': ''}, {'name': '   '}, {'name': 7},
                {'name': '\x00\x01\n\t'}, {'title': 'x'}):
        assert L.validate_pane(bad) is None, bad
    p = L.validate_pane({'name': 'a\x00b\x1b[31m\nc'})
    assert p['name'] == 'ab[31mc', p
    big = L.validate_pane({'name': 'x' * 10000, 'title': 'y' * 10000})
    assert len(big['name']) == 24 and len(big['title']) == 24
    assert L.validate_pane({'name': 'a' * 23 + ' ' + 'b'})['name'] == 'a' * 23


@check
def pane_no_mutation():
    d = {'name': ' x ', 'max_lines': 7}
    c = copy.deepcopy(d)
    L.validate_pane(d)
    assert d == c


@check
def panes_list_rules():
    assert L.validate_panes(None) == []
    assert L.validate_panes('abc') == []
    out = L.validate_panes([{'name': 'A'}, {'name': 'a'}, 3, {'name': 'B'}, {'name': ' b '}, None])
    assert [p['name'] for p in out] == ['A', 'B'], out
    many = [{'name': 'n%d' % i} for i in range(100)]
    out = L.validate_panes(many)
    assert len(out) == L.MAX_PANES and out[0]['name'] == 'n0' and out[-1]['name'] == 'n11'
    assert L.validate_panes([{'name': 'z'}, {'name': 'a'}])[0]['name'] == 'z'
    assert len(L.validate_panes([{'name': 'q%d' % i} for i in range(200000)])) == 12


@check
def layout_garbage():
    empty = {'regions': [], 'min_main_cols': 80}
    for g in (None, 5, 'x', [], [[]], {}, {'regions': 5}, {'regions': None},
              {'regions': {'a': 1}}, {'regions': ['x', 1, None, [], {}]},
              {'regions': [{'side': 'middle'}]}, {'regions': [{'side': 5}]}):
        assert L.validate_layout(g) == empty, g
    assert L.validate_layout(g) is not L.validate_layout(g)


@check
def layout_clamps():
    v = L.validate_layout({'regions': [
        {'side': 'top', 'size': 1, 'weight': 0},
        {'side': 'bottom', 'size': 99, 'weight': 99},
        {'side': 'left', 'size': 2, 'weight': -1},
        {'side': 'right', 'size': 1000, 'weight': 5}], 'min_main_cols': 5})
    r = v['regions']
    assert [x['id'] for x in r] == ['r1', 'r2', 'r3', 'r4']
    assert (r[0]['size'], r[0]['weight']) == (3, 1)
    assert (r[1]['size'], r[1]['weight']) == (40, 9)
    assert (r[2]['size'], r[2]['weight']) == (16, 1)
    assert (r[3]['size'], r[3]['weight']) == (100, 5)
    assert v['min_main_cols'] == 40
    assert L.validate_layout({'regions': [], 'min_main_cols': 500})['min_main_cols'] == 200
    assert L.validate_layout({'regions': [], 'min_main_cols': 120})['min_main_cols'] == 120
    # defaults for non-ints
    for junk in (None, 'a', 2.5, True, [], {}):
        v = L.validate_layout({'regions': [{'side': 'top', 'size': junk, 'weight': junk},
                                           {'side': 'left', 'size': junk, 'weight': junk}],
                               'min_main_cols': junk})
        assert (v['regions'][0]['size'], v['regions'][0]['weight']) == (6, 1), junk
        assert (v['regions'][1]['size'], v['regions'][1]['weight']) == (36, 1), junk
        assert v['min_main_cols'] == 80
    # exact bounds
    v = L.validate_layout({'regions': [{'side': 'top', 'size': 3}, {'side': 'top', 'size': 40},
                                       {'side': 'left', 'size': 16}, {'side': 'left', 'size': 100}]})
    assert [x['size'] for x in v['regions']] == [3, 40, 16, 100]


@check
def layout_ids_sides_truncation():
    regs = [{'id': 'zzz', 'side': 'TOP '}, {'side': 'nope'}, {'id': 'r1', 'side': 'left'},
            {'side': 'right'}, {'side': 'bottom'}, {'side': 'top'}, {'side': 'top'}, {'side': 'left'}, {'side': 'right'}]
    v = L.validate_layout({'regions': regs})
    assert [r['id'] for r in v['regions']] == ['r1', 'r2', 'r3', 'r4', 'r5', 'r6']
    assert [r['side'] for r in v['regions']] == ['top', 'left', 'right', 'bottom', 'top', 'top']
    assert len(L.validate_layout({'regions': [{'side': 'top'}] * 5000})['regions']) == L.MAX_REGIONS
    assert L.validate_layout({'regions': [{'side': 'top', 'panes': []}]})['regions'][0]['panes'] == []
    assert L.validate_layout({'regions': [{'side': 'top'}]})['regions'][0]['panes'] == []


@check
def layout_panes_dedupe_and_known():
    v = L.validate_layout({'regions': [
        {'side': 'top', 'panes': ['OOC', 'ooc', ' Tells ', 7, None, '', 'Guide']},
        {'side': 'left', 'panes': ['TELLS', 'Guide ', 'New']}]})
    assert v['regions'][0]['panes'] == ['OOC', 'Tells', 'Guide']
    assert v['regions'][1]['panes'] == ['New']
    v = L.validate_layout({'regions': [{'side': 'top', 'panes': ['A', 'B', 'C']},
                                       {'side': 'left', 'panes': ['D', 'a']}]},
                          known_panes=['b', 'D', 'zzz', None, 5])
    assert v['regions'][0]['panes'] == ['B'] and v['regions'][1]['panes'] == ['D']
    v = L.validate_layout({'regions': [{'side': 'top', 'panes': ['A']}]}, known_panes=[])
    assert v['regions'][0]['panes'] == []
    v = L.validate_layout({'regions': [{'side': 'top', 'panes': ['A']}]}, known_panes=iter(['a']))
    assert v['regions'][0]['panes'] == ['A']
    v = L.validate_layout({'regions': [{'side': 'top', 'panes': ['A']}]}, known_panes=12345)
    assert v['regions'][0]['panes'] == []
    v = L.validate_layout({'regions': [{'side': 'top', 'panes': ['p%d' % i for i in range(50)]}]})
    assert len(v['regions'][0]['panes']) == 12
    v = L.validate_layout({'regions': [{'side': 'top', 'panes': 'abc'}]})
    assert v['regions'][0]['panes'] == []
    v = L.validate_layout({'regions': [{'side': 'top', 'panes': ['x' * 10000, 'a\x00\x01']}]})
    assert v['regions'][0]['panes'] == ['x' * 24, 'a']


@check
def layout_hostile():
    hostile = [
        {'regions': [[[[]]]], 'min_main_cols': [[]]},
        {'regions': [{'side': 'top', 'size': {'a': 1}, 'weight': [1], 'panes': [[1], {'a': 1}, {1, 2}]}]},
        {'regions': [{'side': 'top', 'size': -1e308, 'weight': float('nan'), 'panes': None}],
         'min_main_cols': float('inf')},
        {'regions': [{'side': 'left', 'size': 10 ** 100, 'weight': -10 ** 100}]},
        {'regions': ('tuple', 'of', 'junk')},
        {'regions': [{'side': 'top\x00', 'panes': ['\x00' * 5000]}]},
        {'regions': [{'side': 'top', 'panes': ['x'] * 100000}]},
        {'regions': [{'side': 'top', 'size': True, 'weight': False}]},
    ]
    for h in hostile:
        v = L.validate_layout(h)
        assert v == L.validate_layout(v), h
        json.dumps(v)
    rec = []
    rec.append(rec)
    L.validate_layout({'regions': rec})
    L.validate_layout({'regions': [{'side': 'top', 'panes': rec}]})


@check
def layout_idempotent_and_nomutation_random():
    rnd = random.Random(1)
    for _ in range(500):
        raw = rand_layout(rnd)
        snap = copy.deepcopy(raw)
        known = rnd.choice([None, ['P1', 'p2', 'P3', 'P4', 'P5']])
        v = L.validate_layout(raw, known)
        assert raw == snap
        assert L.validate_layout(v, known) == v
        assert L.validate_layout(v) == v
        names = L.region_pane_names(v)
        assert len({n.casefold() for n in names}) == len(names)
        assert len(v['regions']) <= L.MAX_REGIONS
        json.dumps(v)


# --------------------------------------------------------------- presets

EXPECTED_PRESETS = ['Long strip on top', 'Long strip on the bottom', 'Right column',
                    'Right column, two stacked', 'Left column', 'Top strip + right column']


@check
def presets_structure():
    assert list(L.PRESETS) == EXPECTED_PRESETS
    shape = {n: [(r['side'], r['size']) for r in p['regions']] for n, p in L.PRESETS.items()}
    assert shape['Long strip on top'] == [('top', 6)]
    assert shape['Long strip on the bottom'] == [('bottom', 6)]
    assert shape['Right column'] == [('right', 36)]
    assert shape['Right column, two stacked'] == [('right', 36), ('right', 36)]
    assert shape['Left column'] == [('left', 36)]
    assert shape['Top strip + right column'] == [('top', 5), ('right', 34)]
    ws = [r['weight'] for r in L.PRESETS['Right column, two stacked']['regions']]
    assert ws[0] == ws[1]
    for n, p in L.PRESETS.items():
        assert isinstance(p['description'], str) and p['description']
        for r in p['regions']:
            assert 'panes' not in r
        lay = {'regions': [dict(r, panes=[]) for r in p['regions']]}
        v = L.validate_layout(lay)
        assert [(r['side'], r['size'], r['weight']) for r in v['regions']] == \
               [(r['side'], r['size'], r['weight']) for r in p['regions']], n


@check
def preset_layout_distribution():
    v = L.preset_layout('Right column, two stacked', ['A', 'B', 'C', 'D', 'E'])
    assert v['regions'][0]['panes'] == ['A', 'C', 'E']
    assert v['regions'][1]['panes'] == ['B', 'D']
    v = L.preset_layout('Top strip + right column', ['OOC'])
    assert v['regions'][0]['panes'] == ['OOC'] and v['regions'][1]['panes'] == []
    for name in L.PRESETS:
        v = L.preset_layout(name, [])
        assert v == L.validate_layout(v)
        assert len(v['regions']) == len(L.PRESETS[name]['regions'])
        assert all(r['panes'] == [] for r in v['regions'])
        v = L.preset_layout(name, ['a', 'b', 'c', 'd', 'e', 'f', 'g'])
        assert v == L.validate_layout(v)
        assert sorted(L.region_pane_names(v)) == list('abcdefg')
    v = L.preset_layout('No such preset', ['A'])
    assert v['regions'][0]['side'] == 'top' and v['regions'][0]['panes'] == ['A']
    assert L.preset_layout(None, None)['regions'][0]['side'] == 'top'
    assert L.preset_layout(['x'], 'junk')['regions'][0]['panes'] == []
    v = L.preset_layout('Left column', ['A', 'a', 'B'])
    assert v['regions'][0]['panes'] == ['A', 'B']
    assert L.preset_layout('Left column', [{'name': 'Z'}])['regions'][0]['panes'] == ['Z']
    snap = copy.deepcopy(L.PRESETS)
    L.preset_layout('Right column', ['A'])
    assert L.PRESETS == snap


# --------------------------------------------------------- compute_layout

@check
def presets_at_several_sizes():
    sizes = [(1400, 900), (1000, 600), (800, 500), (700, 450), (900, 700), (2000, 1200),
             (656, 96), (640, 300), (1280, 400)]
    for name in L.PRESETS:
        lay = L.preset_layout(name, ['A', 'B', 'C'])
        for (W, H) in sizes:
            for (cw, lh) in ((8, 16), (7, 14), (10, 20)):
                hh = lh + 4
                res = L.compute_layout(lay, W, H, cw, lh)
                check_invariants(res, W, H, hh)
                need_w, need_h = 80 * cw + 16, 6 * lh
                if W >= need_w and H >= need_h:
                    assert res['main'][2] >= need_w and res['main'][3] >= need_h, (name, W, H, res)


@check
def big_window_no_adjustments():
    lay = L.preset_layout('Top strip + right column', ['A', 'B'])
    res = L.compute_layout(lay, 1600, 1000, 8, 16)
    assert res['notes'] == [] and res['hidden'] == []
    assert res['regions']['r1']['rect'] == (0, 0, 1600, 5 * 16 + 20)
    assert res['regions']['r2']['rect'][2] == 34 * 8 + 16


@check
def exact_case_right_column():
    lay = L.preset_layout('Right column', ['A'])
    res = L.compute_layout(lay, 1000, 600, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['main'] == (0, 0, 696, 600), res
    g = res['regions']['r1']
    assert g['rect'] == (696, 0, 304, 600)
    assert g['header'] == (696, 0, 304, 20)
    assert g['body'] == (696, 20, 304, 580)
    assert res['hidden'] == [] and res['notes'] == []


@check
def exact_case_top_right_with_gap():
    lay = L.preset_layout('Top strip + right column', ['A', 'B'])
    res = L.compute_layout(lay, 1000, 600, 8, 16, header_h=20, gap=4, pad_x=16)
    assert res['main'] == (0, 104, 708, 496), res
    assert res['regions']['r1']['rect'] == (0, 0, 1000, 100)
    assert res['regions']['r2']['rect'] == (712, 104, 288, 496)
    assert res['regions']['r1']['body'] == (0, 20, 1000, 80)


@check
def exact_case_weighted_stack():
    lay = mk(('right', 36, 1, ['A']), ('right', 36, 3, ['B']))
    res = L.compute_layout(lay, 1000, 620, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['main'] == (0, 0, 696, 620), res
    assert res['regions']['r1']['rect'] == (696, 0, 304, 173), res['regions']
    assert res['regions']['r2']['rect'] == (696, 173, 304, 447), res['regions']
    res = L.compute_layout(lay, 1000, 620, 8, 16, header_h=20, gap=10, pad_x=16)
    r1, r2 = res['regions']['r1']['rect'], res['regions']['r2']['rect']
    assert r1[1] == 0 and r2[1] == r1[1] + r1[3] + 10 and r2[1] + r2[3] == 620
    assert res['main'] == (0, 0, 1000 - 304 - 10, 620)


@check
def exact_case_left_bottom():
    lay = mk(('left', 20, 1, ['A']), ('bottom', 4, 1, ['B']))
    res = L.compute_layout(lay, 1000, 500, 8, 16, header_h=20, gap=2, pad_x=16)
    # bottom thickness 4*16+20=84 ; left thickness 20*8+16=176
    assert res['regions']['r2']['rect'] == (0, 416, 1000, 84)
    assert res['regions']['r1']['rect'] == (0, 0, 176, 414)
    assert res['main'] == (178, 0, 822, 414), res


@check
def shrink_then_hide_right():
    lay = L.preset_layout('Right column', ['A'])
    res = L.compute_layout(lay, 800, 600, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['regions']['r1']['rect'][2] == 16 * 8 + 16
    assert res['main'][2] == 656
    assert res['notes'] == ['Right column narrowed to 16 columns to keep 80 columns of main text'], res['notes']
    res = L.compute_layout(lay, 900, 600, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['regions']['r1']['rect'][2] == 28 * 8 + 16 and res['main'][2] == 660
    assert res['notes'] == ['Right column narrowed to 28 columns to keep 80 columns of main text']
    res = L.compute_layout(lay, 700, 600, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['hidden'] == ['r1'] and res['regions'] == {}
    assert res['main'] == (0, 0, 700, 600)
    assert res['notes'] == ['Right column hidden: window too small']


@check
def shrink_band_rows():
    lay = L.preset_layout('Long strip on top', ['A'])
    # need_h = 96; top thickness 6*16+20=116 ; H=200 -> mid 84 deficit 12 -> 1 row
    res = L.compute_layout(lay, 1000, 200, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['regions']['r1']['rect'] == (0, 0, 1000, 5 * 16 + 20), res
    assert res['main'] == (0, 100, 1000, 100)
    assert res['notes'] == ['Top strip reduced to 5 rows to keep 6 lines of main text'], res['notes']
    res = L.compute_layout(lay, 1000, 150, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['hidden'] == ['r1'] and res['notes'] == ['Top strip hidden: window too small']
    assert res['main'] == (0, 0, 1000, 150)


@check
def hiding_order_last_declared_first():
    lay = mk(('top', 6, 1, ['A']), ('left', 36, 1, ['B']), ('right', 36, 1, ['C']))
    # width so small that the columns cannot fit even at 16 cols: 656+144+144 = 944
    res = L.compute_layout(lay, 800, 600, 8, 16, header_h=20, gap=0, pad_x=16)
    # right (last declared) goes first; then left would still not fit (656+144=800) -> fits exactly
    assert res['hidden'] == ['r3'], res
    assert res['notes'][0] == 'Right column hidden: window too small'
    assert 'r1' in res['regions'] and 'r2' in res['regions']
    res = L.compute_layout(lay, 700, 600, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['hidden'] == ['r2', 'r3'] and 'r1' in res['regions'], res
    assert res['notes'][:2] == ['Right column hidden: window too small',
                                'Left column hidden: window too small'], res['notes']
    # a band is not hidden to cure a width deficit
    lay = mk(('left', 36, 1, ['B']), ('top', 6, 1, ['A']))
    res = L.compute_layout(lay, 700, 600, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['hidden'] == ['r1'] and 'r2' in res['regions']
    # height deficit: bottom (declared last) first
    lay = mk(('top', 6, 1, ['A']), ('bottom', 6, 1, ['B']))
    res = L.compute_layout(lay, 1000, 250, 8, 16, header_h=20, gap=0, pad_x=16)
    # 2 bands min 3 rows: 2*(48+20)=136 -> 114 left (>=96) fits after shrinking
    check_invariants(res, 1000, 250, 20)
    assert res['main'][3] >= 96
    res = L.compute_layout(lay, 1000, 200, 8, 16, header_h=20, gap=0, pad_x=16)
    assert res['hidden'] == ['r2'], res
    assert 'Bottom strip hidden: window too small' in res['notes']


@check
def shared_thickness_and_weights():
    lay = mk(('top', 4, 1, ['A']), ('top', 8, 1, ['B']), ('top', 5, 2, ['C']))
    res = L.compute_layout(lay, 1200, 900, 8, 16, header_h=20, gap=0, pad_x=16)
    rs = [res['regions'][k]['rect'] for k in ('r1', 'r2', 'r3')]
    assert all(r[3] == 8 * 16 + 20 and r[1] == 0 for r in rs), rs
    assert rs[0][0] == 0 and rs[1][0] == rs[0][0] + rs[0][2] and rs[2][0] == rs[1][0] + rs[1][2]
    assert rs[2][0] + rs[2][2] == 1200
    # weights 1:1:2 -> widths roughly 300,300,600 (minus min rounding)
    assert abs(rs[0][2] - 300) <= 8 and abs(rs[1][2] - 300) <= 8 and abs(rs[2][2] - 600) <= 8, rs
    lay = mk(('left', 20, 1, ['A']), ('left', 30, 2, ['B']))
    res = L.compute_layout(lay, 1200, 900, 8, 16)
    a, b = res['regions']['r1']['rect'], res['regions']['r2']['rect']
    assert a[2] == b[2] == 30 * 8 + 16 and a[1] == 0 and b[1] == a[3] and b[1] + b[3] == 900
    assert b[3] > a[3] and abs(b[3] - 2 * a[3]) <= 40


@check
def declaration_order_stacking():
    lay = mk(('right', 30, 1, ['A']), ('left', 30, 1, ['B']), ('right', 30, 1, ['C']))
    res = L.compute_layout(lay, 1400, 800, 8, 16)
    assert res['regions']['r1']['rect'][1] < res['regions']['r3']['rect'][1]
    lay = mk(('bottom', 5, 1, ['A']), ('bottom', 5, 1, ['B']))
    res = L.compute_layout(lay, 1400, 800, 8, 16)
    assert res['regions']['r1']['rect'][0] < res['regions']['r2']['rect'][0]


@check
def empty_regions_are_laid_out():
    lay = mk(('right', 30, 1, []))
    res = L.compute_layout(lay, 1400, 800, 8, 16)
    assert 'r1' in res['regions']


@check
def tiny_window_and_absurd_inputs():
    lay = L.preset_layout('Top strip + right column', ['A', 'B'])
    for (W, H) in ((1, 1), (10, 10), (100, 50), (300, 80), (80 * 8 + 16, 6 * 16), (655, 95)):
        res = L.compute_layout(lay, W, H, 8, 16)
        check_invariants(res, W, H, 20)
        if W < 656 or H < 96:
            assert res['regions'] == {} and res['main'] == (0, 0, W, H), (W, H, res)
            assert sorted(res['hidden']) == ['r1', 'r2']
    vals = [None, 'x', 0, -5, 1.5, float('nan'), float('inf'), -float('inf'), 10 ** 30,
            True, False, [], {}, 2 ** 70, -2 ** 70, 0.2, 1e300]
    for v in vals:
        for pos in range(6):
            args = [1000, 600, 8, 16, None, 0]
            args[pos] = v
            res = L.compute_layout(lay, *args)
            W = res['main'][0] + res['main'][2]
            assert all(type(x) is int for x in res['main'])
            assert res['main'][2] > 0 and res['main'][3] > 0
        res = L.compute_layout(lay, 1000, 600, 8, 16, 20, 0, v)
        assert res['main'][2] > 0
    for bad in (None, 5, 'x', [], {'regions': 3}, {'regions': [None]}):
        res = L.compute_layout(bad, 500, 300, 8, 16)
        assert res['main'] == (0, 0, 500, 300) and res['regions'] == {} and res['hidden'] == []
    res = L.compute_layout(lay, 10 ** 12, 10 ** 12, 8, 16)
    assert res['main'][2] > 0 and res['main'][3] > 0
    res = L.compute_layout(lay, 1000.9, 600.2, 8.7, 16.1)
    check_invariants(res, 1000, 600, 20)
    res = L.compute_layout(lay, 1000, 600, 8, 16, header_h=-3)
    assert res['regions']['r1']['header'][3] == 20
    res = L.compute_layout(lay, 1000, 600, 8, 16, header_h=30)
    assert res['regions']['r1']['header'][3] == 30


@check
def random_invariants_3000():
    rnd = random.Random(20261123)
    for i in range(3000):
        raw = rand_layout(rnd) if i % 3 else {'regions': [
            {'side': rnd.choice(L.SIDES), 'size': rnd.randint(3, 100), 'weight': rnd.randint(1, 9),
             'panes': ['a%d' % k]} for k in range(rnd.randint(1, 4))],
            'min_main_cols': rnd.choice([40, 80, 120, 200])}
        W = rnd.choice([rnd.randint(1, 3000), rnd.randint(200, 1400)])
        H = rnd.choice([rnd.randint(1, 2000), rnd.randint(100, 900)])
        cw = rnd.randint(1, 20)
        lh = rnd.randint(1, 40)
        hh = rnd.choice([None, rnd.randint(1, 60)])
        gap = rnd.choice([0, 0, rnd.randint(0, 12)])
        pad = rnd.choice([16, 0, rnd.randint(0, 30)])
        res = L.compute_layout(raw, W, H, cw, lh, hh, gap, pad)
        v = L.validate_layout(raw)
        eh = lh + 4 if hh is None else hh
        check_invariants(res, W, H, eh)
        need_w = v['min_main_cols'] * cw + pad
        need_h = 6 * lh
        if W >= need_w and H >= need_h:
            assert res['main'][2] >= need_w and res['main'][3] >= need_h, (raw, W, H, cw, lh, hh, gap, pad, res)
        ids = {r['id'] for r in v['regions']}
        assert set(res['regions']) | set(res['hidden']) == ids
        assert not set(res['regions']) & set(res['hidden'])
        assert (not res['hidden']) or res['notes']


@check
def determinism_and_no_mutation():
    rnd = random.Random(5)
    for _ in range(200):
        raw = rand_layout(rnd)
        snap = copy.deepcopy(raw)
        a = L.compute_layout(raw, 900, 600, 8, 16, None, 2, 16)
        b = L.compute_layout(copy.deepcopy(raw), 900, 600, 8, 16, None, 2, 16)
        assert a == b and raw == snap
    lay = L.preset_layout('Right column', ['A'])
    snap = copy.deepcopy(lay)
    L.compute_layout(lay, 300, 300, 8, 16)
    assert lay == snap


@check
def performance_compute():
    lay = L.preset_layout('Right column, two stacked', ['A', 'B', 'C'])
    t = time.time()
    for i in range(3000):
        L.compute_layout(lay, 800 + i % 600, 500 + i % 300, 8, 16, None, 2)
    dt = time.time() - t
    assert dt < 3.0, dt


# --------------------------------------------------------------- preview

@check
def preview_shape_and_labels():
    for name in L.PRESETS:
        lay = L.preset_layout(name, ['OOC', 'Tells', 'Guide'])
        for (c, r) in ((60, 18), (80, 24), (40, 12), (120, 40)):
            out = L.ascii_preview(lay, c, r)
            assert len(out) == r and all(len(s) == c for s in out), (name, c, r)
            txt = '\n'.join(out)
            assert 'MAIN' in txt, name
            if r >= 18:
                assert 'OOC' in txt, (name, txt)
            assert '┌' in txt and '┘' in txt
        out = L.ascii_preview(L.preset_layout(name, []))
        assert 'MAIN' in '\n'.join(out) and len(out) == 18
    out = L.ascii_preview(L.preset_layout('Long strip on top', ['OOC', 'Tells']))
    assert any('OOC | Tells' in s for s in out), out
    out = L.ascii_preview(L.preset_layout('Right column, two stacked', ['AAA', 'BBB']))
    txt = '\n'.join(out)
    assert 'AAA' in txt and 'BBB' in txt
    assert any('├' in s or '┬' in s for s in out)
    out = L.ascii_preview(L.preset_layout('Top strip + right column', ['X', 'Y']))
    assert '┬' in '\n'.join(out) or '┼' in '\n'.join(out) or '├' in '\n'.join(out)


@check
def preview_visual_sample():
    lay = L.preset_layout('Right column', ['OOC', 'Tells'])
    out = L.ascii_preview(lay, 60, 18)
    assert out[0].startswith('┌') and out[0].endswith('┐')
    assert out[-1].startswith('└') and out[-1].endswith('┘')
    main_row = [s for s in out if 'MAIN' in s][0]
    assert main_row.index('MAIN') < 30
    assert any('OOC | Tells' in s for s in out)


@check
def preview_hidden_line_and_ellipsis():
    lay = L.preset_layout('Right column', ['OOC', 'Tells'])
    out = L.ascii_preview(lay, 60, 18, ref_cells=(90, 40))
    assert out[-1].startswith('hidden:') and 'OOC' in out[-1] and len(out[-1]) == 60
    assert len(out) == 18 and all(len(s) == 60 for s in out)
    out = L.ascii_preview(L.preset_layout('Long strip on top',
                                          ['A' * 24, 'B' * 24, 'C' * 24, 'D' * 24]), 40, 14)
    assert any('…' in s for s in out)
    assert all(len(s) == 40 for s in out)
    lay = L.preset_layout('Right column, two stacked', ['x%d' % i for i in range(12)])
    out = L.ascii_preview(lay, 60, 18)
    assert any('…' in s for s in out)


@check
def preview_never_raises():
    rnd = random.Random(77)
    for i in range(400):
        raw = rand_layout(rnd)
        c = rnd.choice([1, 2, 3, 5, 10, 60, 100, 0, -4, None, 'x', 2.5, True])
        r = rnd.choice([1, 2, 3, 5, 18, 40, 0, -1, None, 'q'])
        rc = rnd.choice([(160, 48), (10, 5), (1, 1), (0, 0), None, 'ab', (None, 3), (300, 90)])
        out = L.ascii_preview(raw, c, r, rc)
        ec = int(c) if (isinstance(c, (int, float)) and not isinstance(c, bool) and int(c) > 0) else 60
        er = int(r) if (isinstance(r, (int, float)) and not isinstance(r, bool) and int(r) > 0) else 18
        assert len(out) == er and all(isinstance(s, str) and len(s) == ec for s in out), (c, r, out)
    for bad in (None, 5, 'x', [], {}):
        out = L.ascii_preview(bad)
        assert len(out) == 18 and all(len(s) == 60 for s in out)
    assert L.ascii_preview(None, 1000, 1000) is not None


# --------------------------------------------------------------- helpers

@check
def summary_and_helpers():
    lay = L.validate_layout({'regions': [
        {'side': 'right', 'size': 36, 'panes': ['OOC', 'Tells']},
        {'side': 'top', 'size': 6, 'panes': ['Guide']}]})
    assert L.layout_summary(lay) == 'right column 36 cols: OOC, Tells | top strip 6 rows: Guide', L.layout_summary(lay)
    assert L.layout_summary({'regions': [], 'min_main_cols': 80}) == 'no panes docked'
    assert L.layout_summary(None) == 'no panes docked'
    assert 'left column 20 cols' in L.layout_summary({'regions': [{'side': 'left', 'size': 20}]})
    assert 'bottom strip 4 rows' in L.layout_summary({'regions': [{'side': 'bottom', 'size': 4}]})
    assert L.region_pane_names(lay) == ['OOC', 'Tells', 'Guide']
    assert L.region_pane_names(None) == []
    assert L.find_region(lay, 'ooc')['side'] == 'right'
    assert L.find_region(lay, ' GUIDE ')['side'] == 'top'
    assert L.find_region(lay, 'nope') is None
    assert L.find_region(lay, None) is None
    assert L.find_region(lay, 5) is None
    assert L.find_region(None, 'a') is None
    snap = copy.deepcopy(lay)
    L.layout_summary(lay)
    L.find_region(lay, 'OOC')
    assert lay == snap


@check
def constants():
    assert L.MIN_MAIN_COLS == 80 and L.SIDES == ('top', 'bottom', 'left', 'right')
    assert L.MAX_REGIONS == 6 and L.MAX_PANES == 12


# ------------------------------------------------------------------ main

def main():
    t0 = time.time()
    failed = 0
    for fn in CHECKS:
        try:
            fn()
            print('PASS', fn.__name__)
        except Exception:
            failed += 1
            print('FAIL', fn.__name__)
            traceback.print_exc()
    print('%d checks, %d failed, %.2fs' % (len(CHECKS), failed, time.time() - t0))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
