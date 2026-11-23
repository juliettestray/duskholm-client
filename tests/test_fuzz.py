"""Adversarial property/fuzz checks for duskholm_client.Terminal (stdlib only).

Run:  python tests/test_fuzz.py
Every check runs; PASS/FAIL printed per check with a minimal reproducer; exit 1 on any FAIL.
"""
import os, sys, time, random, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import duskholm_client as dc
from duskholm_client import Terminal, IAC, WILL, WONT, DO, DONT, SB, SE, GA

MB = 1 << 20
NOP = 241
DEFAULT_KEY = (None, None, False, False, False, False)
INFO = []


def info(s):
    INFO.append(s)


def rep(b, n=170):
    r = repr(b)
    return r if len(r) <= n else r[:n - 3] + "..."


def mxp_on():
    t = Terminal()
    t.feed(bytes([IAC, WILL, 91, IAC, SB, 91, IAC, SE]))
    assert t.mxp
    return t


def make(mode):
    return mxp_on() if mode == "mxp" else Terminal()


def ddmin(data, pred, budget=3.0):
    end = time.time() + budget
    chunk = max(1, len(data) // 2)
    while len(data) > 1 and time.time() < end:
        i, changed = 0, False
        while i < len(data) and time.time() < end:
            cand = data[:i] + data[i + chunk:]
            if cand and pred(cand):
                data, changed = cand, True
            else:
                i += chunk
        if not changed:
            if chunk == 1:
                break
            chunk //= 2
    return data


def loc(e):
    where = "?"
    for fr in traceback.extract_tb(e.__traceback__):
        if fr.filename.endswith("duskholm_client.py"):
            where = "%s() line %d" % (fr.name, fr.lineno)
    return "%s: %s @ %s" % (type(e).__name__, str(e)[:60], where)


def exc_of(data, mode="plain", chunk=None):
    t = make(mode)
    try:
        if chunk:
            for i in range(0, len(data), chunk):
                t.feed(data[i:i + chunk])
        else:
            t.feed(data)
    except Exception as e:  # noqa: BLE001
        return e
    return None


def exc_check(cases, chunk=None):
    """cases: list of (label, bytes). Runs plain+mxp. Returns None or message (unique causes only)."""
    found = {}
    for label, data in cases:
        for mode in ("plain", "mxp"):
            e = exc_of(data, mode, chunk)
            if e is None:
                continue
            key = loc(e)
            if key in found:
                continue

            def pred(d, mode=mode, key=key):
                x = exc_of(d, mode, chunk)
                return x is not None and loc(x) == key
            small = ddmin(data, pred) if len(data) > 1 else data
            found[key] = "%s [%s] repro=%s" % (key, mode, rep(small))
    return None if not found else " || ".join(found.values())


# ----------------------------------------------------------------- corpus
FRAGS = [
    b"\x1b[0m", b"\x1b[1;31m", b"\x1b[38;5;196m", b"\x1b[48;5;21m", b"\x1b[38;2;1;2;3m", b"\x1b[m",
    b"\x1b[6z", b"\x1b[2J", b"hello ", b"wor\xc3\xa9ld ", "☃".encode(), "\U0001F600".encode(),
    b"\r\n", b"\x07", b"<b>", b"</b>", b"<i>", b"</i>", b"<u>", b"</u>", b"<color fore=#ff8800>",
    b"</color>", b"<color red>", b"<br>", b"<send href='x'>", b"&lt;", b"&gt;", b"&amp;", b"&#65;",
    b"&bogus;", b"&", b"<", b">", b";", bytes([IAC, IAC]), bytes([IAC, WILL, 1]), bytes([IAC, WONT, 1]),
    bytes([IAC, WILL, 91]), bytes([IAC, WONT, 91]), bytes([IAC, WILL, 3]), bytes([IAC, DO, 31]),
    bytes([IAC, DONT, 5]), bytes([IAC, GA]), bytes([IAC, NOP]), bytes([IAC, SB, 24, 1, IAC, SE]),
    bytes([IAC, SB, 24, IAC, IAC, IAC, SE]), b"\x1b", b"\x1b[", b"\x1b[3", b"\xc3", b"\xe2\x98",
]


def corpus():
    s = []
    s.append(("colour", b"\x1b[0m\x1b[1;31mred\x1b[0m \x1b[38;5;196mX\x1b[48;5;21mY\x1b[38;2;1;2;3mZ\x1b[m end\r\n"))
    s.append(("negotiation", bytes([IAC, WILL, 1]) + b"Password: " + bytes([IAC, WONT, 1]) +
              bytes([IAC, WILL, 91, IAC, WILL, 3, IAC, DO, 31, IAC, WILL, 200, IAC, DONT, 5]) +
              b"[10hp] " + bytes([IAC, GA, IAC, NOP, IAC, SB, 24, 1, IAC, SE]) + b"after\r\n"))
    s.append(("mxp", bytes([IAC, WILL, 91]) + b"hello " + bytes([IAC, SB, 91, IAC, SE]) +
              b"\x1b[6z<color fore=#ff8800>amber</color> a &lt;b&gt; &amp; &quot; &#65; &#x41; &bogus; &"
              b"<b>bold<i>it</i></b></b><u>u</u><br>x<color red>r</color><send href='x'>link</send> t&amp;lt; end"))
    s.append(("utf8", ("héllo wörld ☃ 日本語 \U0001F600 ").encode() +
              b"\x1b[31m" + "☃".encode() + b"\x1b[0m" + bytes([IAC, IAC]) + b"\xc3" + bytes([IAC, GA]) + b"\xa9z"))
    s.append(("bell_crlf", b"ding\x07\r\nline2\r\n\x00x\x01y\ttab\r\n\r\r\n"))
    s.append(("utf8_in_escape", b"\x1b[3\xc3\xa9m" + b"q\x1b[38;5;\xe2\x98\x83" + b"w\x1b[1;3" + "é".encode() + b"1mE"))
    s.append(("mxp_utf8_tags", bytes([IAC, SB, 91, IAC, SE]) + "<color fore=#fff>é</color>&#233;&am".encode() + b"p;<b>\xe2\x98\x83</b>"))
    s.append(("trailing_partials", bytes([IAC, SB, 91, IAC, SE]) + b"text &am"))
    s.append(("trailing_esc", b"text \x1b"))
    s.append(("trailing_lt", bytes([IAC, SB, 91, IAC, SE]) + b"a <b"))
    rng = random.Random(1234)
    for n in range(150):
        parts = []
        if rng.random() < 0.5:
            parts.append(bytes([IAC, WILL, 91, IAC, SB, 91, IAC, SE]))  # MXP only as a prefix (SB-MXP ordering has its own check)
        for _ in range(rng.randint(4, 22)):
            parts.append(rng.choice(FRAGS))
        s.append(("rand%d" % n, b"".join(parts)))
    return s


def summarize(evs, t):
    chars, others, inter = [], [], []
    for ev in evs:
        if ev[0] == "text":
            for ch in ev[1]:
                chars.append((ch, ev[2]))
        else:
            others.append(ev)
            inter.append((len(chars), ev))
    return chars, others, (t.mxp, t.echo_off), inter


def run_chunks(chunks):
    t = Terminal()
    evs = []
    for c in chunks:
        evs.extend(t.feed(c))
    return summarize(evs, t)


def schemes(d, rng):
    yield "bytewise", [d[i:i + 1] for i in range(len(d))]
    for k in range(1, len(d)):
        yield "split@%d" % k, [d[:k], d[k:]]
    for r in range(3):
        out, i = [], 0
        while i < len(d):
            n = rng.randint(1, 3 + 12 * r)
            out.append(d[i:i + n])
            i += n
        yield "rand%d" % r, out


def variance(d, inter=False, first_only=True):
    ref = run_chunks([d])
    rng = random.Random(7)
    for name, ch in schemes(d, rng):
        alt = run_chunks(ch)
        if inter:
            if alt[3] != ref[3]:
                return name, "event/text interleave differs: whole=%s alt=%s" % (rep(ref[3], 120), rep(alt[3], 120))
        else:
            if alt[0] != ref[0]:
                a, b = ref[0], alt[0]
                i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
                return name, "chars/style differ at %d: whole=%s alt=%s" % (i, rep(a[max(0, i - 3):i + 5], 100), rep(b[max(0, i - 3):i + 5], 100))
            if alt[1] != ref[1]:
                return name, "send/echo/bell/prompt events differ: whole=%s alt=%s" % (rep(ref[1], 100), rep(alt[1], 100))
            if alt[2] != ref[2]:
                return name, "final (mxp,echo_off) differ: whole=%s alt=%s" % (ref[2], alt[2])
    return None


def chunk_check(inter):
    bad = []
    for name, d in corpus():
        r = variance(d, inter)
        if r:
            small = ddmin(d, lambda x: variance(x, inter) is not None)
            r2 = variance(small, inter)
            bad.append("%s: %s scheme=%s %s repro=%s" % (name, "", r2[0], r2[1], rep(small)))
            if len(bad) >= 3:
                break
    return None if not bad else " || ".join(bad)


def chk_chunk_invariance():
    return chunk_check(False)


def chk_chunk_interleave():
    return chunk_check(True)


def chk_sb_mxp_flush_order():
    d = b"a<b>c" + bytes([IAC, SB, 91, IAC, SE]) + b"d"
    t = Terminal()
    whole = "".join(e[1] for e in t.feed(d) if e[0] == "text")
    t = Terminal()
    t.feed(b"a<b>c")
    t2 = "".join(e[1] for e in t.feed(bytes([IAC, SB, 91, IAC, SE]) + b"d") if e[0] == "text")
    if whole != "a<b>cd":
        return "text sent BEFORE `IAC SB 91 IAC SE` in the same feed is parsed as MXP: repro=%s got %s expected 'a<b>cd' (split before SB gives literal) cause=_telnet_byte sb_iac/SE sets mxp without _flush_text()" % (rep(d), rep(whole))


def chk_long_tag_chunking():
    d = bytes([IAC, SB, 91, IAC, SE]) + b"<" + b"x" * 700 + b">tail"
    r = variance(d)
    if r:
        return "'<' tag longer than 600 bytes handled differently by chunking (%s %s) repro='IAC SB 91 IAC SE' + '<' + 'x'*700 + '>tail' cause=_process '<' branch n-i<600 heuristic" % r
    return None


# ----------------------------------------------------------------- 2: no exceptions
def chk_exc_random():
    rng = random.Random(42)
    d = rng.randbytes(200000)
    return exc_check([("uniform200k", d)], chunk=1021) or exc_check([("uniform200k", d)], chunk=1)


def chk_exc_biased():
    rng = random.Random(43)
    alpha = [IAC] * 8 + [27] * 6 + [ord(c) for c in "<&[;>mz"] * 3 + [ord(c) for c in "0123456789"] * 2 + \
        [250, 240, 251, 252, 253, 254, 249, 91, 1, 3, 24, 255, 38, 5] + list(range(32, 127))
    ds = []
    for i in range(20):
        ds.append(("biased%d" % i, bytes(rng.choice(alpha) for _ in range(5000))))
    return exc_check(ds, chunk=333)


def chk_exc_utf8():
    rng = random.Random(44)
    glyphs = ["é", "☃", "\U0001F600", "日", "²", "٣", "①"]
    cases = []
    for i in range(3000):
        b = b""
        for _ in range(rng.randint(1, 8)):
            k = rng.random()
            if k < .35:
                b += rng.choice(glyphs).encode()[:rng.randint(1, 4)]
            elif k < .55:
                b += bytes([rng.randint(0x80, 0xff)])
            elif k < .7:
                b += b"\x1b["
            elif k < .8:
                b += rng.choice([b"<b>", b"&#", b"&", b"<", b";", b"m", b"</color>"])
            else:
                b += rng.choice(glyphs).encode()
        cases.append(("utf8-%d" % i, b))
    cases += [("sup2-in-csi", b"\x1b[\xc2\xb2m"), ("arabic-digit-csi", b"\x1b[\xd9\xa3m"), ("circled-1", b"\x1b[\xe2\x91\xa0m"),
              ("sup2-entity", b"&#\xc2\xb2;"), ("arabic-entity", b"&#\xd9\xa3;")]
    return exc_check(cases)


def chk_exc_telnet_exhaustive():
    cases = [("2byte-%d" % x, bytes([IAC, x])) for x in range(256)]
    found = None
    for mode in ("plain", "mxp"):
        for c in range(256):
            for o in range(256):
                e = exc_of(bytes([IAC, c, o]) + b"ok", mode)
                if e is not None:
                    return "IAC %d %d [%s]: %s" % (c, o, mode, loc(e))
    for x in (0, 24, 91, 250, 255):
        for y in range(256):
            cases.append(("sb-%d-%d" % (x, y), bytes([IAC, SB, x, IAC, y, 65, IAC, SE])))
    return exc_check(cases)


def chk_exc_sgr():
    big = "9" * 5000
    sg = ["99999999999999999999999", big, ";" * 5000, "38;5;999", "38;2;300;-1;x", "-1", "1;;;2", "38;5;", "38;2;",
          "38;2;1;2", "38:2::1:2:3", ":::", "?25h", "0" * 10000, "1;" * 10000, "48;5;-5", "38;5;" + big, "38;2;" + big + ";1;1",
          "²", "٣", "①", "1;²", "4294967296", "38;2;1;2;3;4;5", "38;38;38;5;5", "48;2;;;"]
    cases = []
    for p in sg:
        cases.append(("sgr:" + p[:12], b"\x1b[" + p.encode("utf-8") + b"m"))
        cases.append(("csi:" + p[:12], b"\x1b[" + p.encode("utf-8")))  # no final
    return exc_check(cases)


def chk_exc_mxp():
    cases = []
    tags = [b"<color fore=>", b"<color back=#zzzzzz>", b"<color fore=#ff>", b'<color fore="">', b"<color fore='#fff>",
            b"<color =>", b"<color ==>", b"<>", b"< >", b"</>", b"<//>", b"</", b"<b/>", b"<b b b>", b"<!ELEMENT x>",
            b"<!-->", b'<a href=">', b"<" * 100 + b">", b"<<<>>>", b"</b></b></b>", b"<b>" * 10000, b"</b>" * 10000,
            b"<i>" * 10000 + b"</i>" * 20000, b"<color " + b"fore=red " * 5000 + b">", b"<color red blue>", b"<c f=#fff b=>",
            b"<\xff>", b"<color fore=\x00>", b"<color \xc3\xa9=1>", b"<1>", b"</1>", b"</ b>", b"<color\tfore\n=\r#fff>"]
    ents = [b"&#99999999999;", b"&#;", b"&#x41;", b"&;", b"&#1114112;", b"&#1114111;", b"&#55296;", b"&#0;", b"&#27;",
            b"&#\xc2\xb2;", b"&" * 1000, b"&#" * 1000, b"&amp" * 1000, b"&&&&;;;;", b"&#-1;", b"&#99999999999999;", b"&#0000000065;"]
    for x in tags + ents:
        cases.append(("mxp:" + x[:14].decode("latin1"), x))
    return exc_check(cases)


# ----------------------------------------------------------------- 3: bounded memory
def buf_size(t):
    n = 0
    for k, v in vars(t).items():
        if k == "style":
            continue
        if isinstance(v, (str, bytes, bytearray, list, dict, tuple)):
            n += len(v)
    n += len(t._decoder.getstate()[0])
    return n


def mem_probe(prep, first, pattern, chunk=65536, total=5 * MB, tbox=2.5, limit=MB):
    t = prep()
    fed, peak, maxev, stop = 0, 0, 0, "fed all %dMB" % (total // MB)
    base = (pattern * (chunk // len(pattern) + 2))
    t0 = time.time()
    first_done = False
    while fed < total:
        c = (first + base)[:chunk] if not first_done else base[:chunk]
        first_done = True
        evs = t.feed(c)
        fed += len(c)
        for e in evs:
            if e[0] == "text" and len(e[1]) > maxev:
                maxev = len(e[1])
        sz = buf_size(t)
        peak = max(peak, sz)
        if sz > limit:
            stop = "internal buffers exceeded 1MB"
            break
        if time.time() - t0 > tbox:
            stop = "time-boxed"
            break
    return t, dict(fed=fed, peak=peak, maxev=maxev, stop=stop, secs=time.time() - t0, chunk=chunk)


def mem_verdict(name, t, r, extra=""):
    desc = "%s: fed %.2fMB in %.1fs (chunks=%d), peak internal buffers=%d bytes, max text event=%d chars, stop=%s" % (
        name, r["fed"] / MB, r["secs"], r["chunk"], r["peak"], r["maxev"], r["stop"])
    bad = r["peak"] > MB or r["maxev"] > 65536 or (r["fed"] >= 256 * 1024 and r["peak"] > 0.8 * r["fed"])
    if bad:
        return desc + extra
    info("ok " + desc)
    return None


def chk_mem_csi():
    t, r = mem_probe(Terminal, b"\x1b[", b"1234567;89;")
    return mem_verdict("ESC[ + digits/;, no final byte", t, r,
                       " | repro: b'\\x1b[' + b'12;'*N; cause: _process() leaves unterminated CSI in _pending (line ~239 `break`) with no length cap, and re-scans it every feed (quadratic)")


def chk_mem_lt():
    t, r = mem_probe(mxp_on, b"", b"<" + b"x" * 99)
    return mem_verdict("MXP '<' w/o '>'", t, r)


def chk_mem_amp():
    t, r = mem_probe(mxp_on, b"", b"&abcde")
    return mem_verdict("MXP '&' w/o ';'", t, r)


def chk_mem_sb():
    t, r = mem_probe(Terminal, bytes([IAC, SB, 24]), b"x" * 64)
    swallowed = "".join(e[1] for e in t.feed(b"hello\r\n") if e[0] == "text")
    return mem_verdict("IAC SB 24 + data, no IAC SE", t, r,
                       " | later text after the unterminated SB is %s (all game output swallowed until IAC SE); cause: _sb bytearray in _telnet_byte 'sb' state has no cap/timeout (line ~164)" % rep(swallowed))


def chk_mem_iac():
    t, r = mem_probe(Terminal, b"", bytes([IAC, IAC]), chunk=4096, total=5 * MB, tbox=2.5)
    return mem_verdict("IAC IAC run", t, r)


# ----------------------------------------------------------------- 4: performance
def timed_feed(prep, chunks):
    t = prep()
    t0 = time.time()
    for c in chunks:
        t.feed(c)
    return time.time() - t0


def chk_perf_dense_sgr():
    blk = b"".join(b"abcdefghij klmn\x1b[38;5;%dm" % (i % 256) for i in range(2000))
    big = blk * (5 * MB // len(blk) + 1)
    res = {}
    for size in (5 * MB // 4, 5 * MB):
        data = big[:size]
        res[size] = timed_feed(Terminal, [data[i:i + 4096] for i in range(0, len(data), 4096)])
    a, b = res[5 * MB // 4], res[5 * MB]
    info("dense SGR 4KB chunks: 1.25MB=%.2fs 5MB=%.2fs (ratio %.1f, linear=4.0)" % (a, b, b / a))
    if b > 10 or b / a > 6:
        return "dense SGR 5MB took %.2fs (1.25MB %.2fs, ratio %.1f)" % (b, a, b / a)


def chk_perf_partial_tag():
    def gen(total):
        pay = b"word " * 818
        out = []
        for k in range(total // 4096):
            out.append((b"o>" if k else b"") + pay[:4090] + b"<fo")
        return out
    res = {}
    for total in (MB // 2, 2 * MB):
        res[total] = timed_feed(mxp_on, gen(total))
    a, b = res[MB // 2], res[2 * MB]
    info("partial '<' at every chunk end: 0.5MB=%.2fs 2MB=%.2fs (ratio %.1f)" % (a, b, b / a))
    if b > 10 or b / a > 6:
        return "partial-tag 2MB took %.2fs (0.5MB %.2fs, ratio %.1f)" % (b, a, b / a)


def chk_perf_attr_regex():
    ts = {}
    for n in (4000, 8000, 16000):
        t = mxp_on()
        d = b"<color " + b"a" * n + b">x"
        t0 = time.time()
        t.feed(d)
        ts[n] = time.time() - t0
        if ts[n] > 5:
            break
    info("`<color aaaa..>` timings: %s" % ", ".join("%d:%.2fs" % kv for kv in ts.items()))
    ns = sorted(ts)
    if len(ns) >= 2 and ts[ns[-1]] > 0.3 and ts[ns[-1]] / max(ts[ns[-2]], 1e-6) > 3:
        return ("quadratic: '<color ' + 'a'*N + '>' takes %s; ATTR_RE ([A-Za-z]+)\\s*= backtracks O(N^2) per tag "
                "(_mxp_tag finditer/search, line ~341/346); one recv(8192) can hold an 8KB tag" % ", ".join("N=%d:%.2fs" % kv for kv in ts.items()))


def chk_perf_emit_concat():
    ts = {}
    for n in (25000, 50000, 100000):
        t = mxp_on()
        d = b"a<foo>" * n
        t0 = time.time()
        t.feed(d)
        ts[n] = time.time() - t0
        if ts[n] > 4:
            break
    info("single feed of 'a<foo>'*N: %s" % ", ".join("%d:%.2fs" % kv for kv in ts.items()))
    ns = sorted(ts)
    if len(ns) >= 2 and ts[ns[-1]] > 0.5 and ts[ns[-1]] / max(ts[ns[-2]], 1e-6) > 3.2:
        return "quadratic in single-feed size (_emit tuple concat ev[-1][1]+s, line ~219): " + ", ".join("N=%d:%.2fs" % kv for kv in ts.items())


def chk_perf_lt_flood():
    d = b"<" * (MB)
    t = timed_feed(mxp_on, [d[i:i + 8192] for i in range(0, len(d), 8192)])
    info("1MB of '<' in 8KB feeds: %.2fs" % t)
    if t > 10:
        return "1MB of '<' in 8KB chunks took %.2fs (s.find('>') rescans per '<')" % t


# ----------------------------------------------------------------- 5: style / text invariants
def chk_ansi_reset():
    rng = random.Random(5)
    codes = ["0", "1", "3", "4", "7", "22", "23", "24", "27", "39", "49", "5", "9", "38;5;%d", "48;5;%d", "38;2;%d;7;9"] + \
        [str(x) for x in list(range(30, 38)) + list(range(40, 48)) + list(range(90, 98)) + list(range(100, 108))]
    for i in range(3000):
        pre = b""
        for _ in range(rng.randint(1, 5)):
            c = rng.choice(codes)
            if "%d" in c:
                c = c % rng.randint(0, 300)
            pre += b"\x1b[" + ";".join([c] + [rng.choice(codes).replace("%d", "3") for _ in range(rng.randint(0, 2))]).encode() + b"m"
        for rs in (b"\x1b[0m", b"\x1b[m", b"\x1b[00m"):
            d = pre + rs + b"X"
            t = Terminal()
            ev = t.feed(d)
            x = [e for e in ev if e[0] == "text"]
            if not x or x[-1][1][-1] != "X" or x[-1][2] != DEFAULT_KEY:
                return "reset did not restore default: repro=%s key=%s" % (rep(d), x[-1][2] if x else None)
    return None


def chk_mxp_depth_nonneg():
    rng = random.Random(6)
    tags = [b"<b>", b"</b>", b"<i>", b"</i>", b"<u>", b"</u>", b"</b>", b"</i>", b"</u>", b"x", b"<color red>", b"</color>"]
    for i in range(500):
        d = b"".join(rng.choice(tags) for _ in range(rng.randint(1, 30)))
        t = mxp_on()
        t.feed(d)
        if min(t.style.mb, t.style.mi, t.style.mu) < 0:
            return "negative depth repro=%s" % rep(d)
    t = mxp_on()
    ev = t.feed(b"</b></b></b><b>y</b>z")
    k = {e[1]: e[2] for e in ev if e[0] == "text"}
    if not k.get("y", (0, 0, False))[2] or k.get("z", (0, 0, True))[2]:
        return "unbalanced closers poison later <b>: repro=b'</b></b></b><b>y</b>z' keys=%s" % k
    return None


def _bad_chars(s):
    return [c for c in s if c in "\x1b\x00\r"]


def chk_text_no_controls():
    rng = random.Random(8)
    cases = [b"&#0;", b"&#27;", b"&#13;", b"x&#27;[31m", b"&#0;&#13;&#27;"]
    alpha = list(b"\x1b[0m;<>&#0123456789x\r\n\x00") + [IAC] * 3
    for i in range(300):
        cases.append(bytes(rng.choice(alpha) for _ in range(60)))
    for d in cases:
        for mode in ("plain", "mxp"):
            t = make(mode)
            for e in t.feed(d):
                if e[0] == "text" and _bad_chars(e[1]):
                    small = ddmin(d, lambda x: any(ee[0] == "text" and _bad_chars(ee[1]) for ee in make(mode).feed(x)))
                    got = [ee[1] for ee in make(mode).feed(small) if ee[0] == "text"]
                    return "text event contains ESC/NUL/CR: repro=%s [%s] text=%s cause=_process() '&' branch chr(int(...)) emits any code point (line ~269)" % (rep(small), mode, rep(got))
    return None


def chk_text_encodable():
    for d in (b"&#55296;", b"&#57343;", b"a&#56000;b"):
        t = mxp_on()
        for e in t.feed(d):
            if e[0] == "text":
                try:
                    e[1].encode("utf-8")
                except UnicodeEncodeError:
                    return "lone surrogate emitted, str.encode('utf-8') raises (App logfile.write would too): repro=%s cause=_process() '&' branch chr(int()) line ~269 (no surrogate/control filter)" % rep(d)
    return None


def chk_iac_commands_not_leaked():
    rng = random.Random(9)
    for i in range(400):
        parts, exp = [], []
        for _ in range(rng.randint(1, 15)):
            k = rng.random()
            if k < .35:
                w = rng.choice(["ab", "Hello", " ", "\n", "x1"])
                parts.append(w.encode()); exp.append(w)
            elif k < .6:
                parts.append(bytes([IAC, rng.choice([WILL, WONT, DO, DONT]), rng.choice([1, 3, 24, 31, 91, 200, 255, 0])]))
            elif k < .75:
                parts.append(bytes([IAC, rng.choice([GA, NOP, 242, 243, 244, 245, 246, 247, 248, SE])]))
            else:
                parts.append(bytes([IAC, SB, rng.choice([24, 91, 31, 0]), rng.randint(0, 254), IAC, SE]))
        d = b"".join(parts)
        t = Terminal()
        got = "".join(e[1] for e in t.feed(d) if e[0] == "text")
        want = "".join(exp)
        if got != want:
            small = ddmin(d, lambda x: "".join(e[1] for e in Terminal().feed(x) if e[0] == "text") !=
                          "".join(c for c in x.decode("latin1") if False) and False)
            return "telnet command/option bytes leaked or text lost: repro=%s got=%s want=%s" % (rep(d), rep(got), rep(want))
    return None


def chk_iac_iac_is_u00ff():
    t = Terminal()
    # IAC IAC is the data byte 0xFF. The game's text is UTF-8, where 0xFF is invalid, so the
    # decoder turns it into exactly one U+FFFD. What matters: one char, nothing leaked, no crash.
    got = "".join(e[1] for e in t.feed(bytes([IAC, IAC])) if e[0] == "text")
    if got != "�":
        return "IAC IAC emits %s, expected a single U+FFFD" % rep(got)


def chk_mxp_off_transparent():
    rng = random.Random(10)
    alpha = list("<>&;#amp lgt0123456789xyz\n\t")
    for i in range(500):
        s = "".join(rng.choice(alpha) for _ in range(rng.randint(1, 120)))
        t = Terminal()
        out, p = "", 0
        while p < len(s):
            n = rng.randint(1, 20)
            out += "".join(e[1] for e in t.feed(s[p:p + n].encode()) if e[0] == "text")
            p += n
        if out != s:
            return "MXP off but text altered: repro=%s got=%s" % (rep(s), rep(out))


# ----------------------------------------------------------------- 6: negotiation
def sends_of(evs):
    return [e[1] for e in evs if e[0] == "send"]


def chk_neg_will_mxp_sga():
    for o in (91, 3):
        s = sends_of(Terminal().feed(bytes([IAC, WILL, o]) * 100000))
        if len(s) > 5:
            return "IAC WILL %d x100000 -> %d replies" % (o, len(s))


def chk_neg_will_echo():
    t = Terminal()
    evs = t.feed(bytes([IAC, WILL, 1]) * 100000)
    s = sends_of(evs)
    n_echo = sum(1 for e in evs if e[0] == "echo")
    if len(s) > 5:
        return "IAC WILL 1 x100000 -> %d `send` (IAC DO 1) replies and %d `echo` events; expected <=1 each (RFC 1143: ignore redundant WILL when already enabled) cause=_negotiate WILL/OPT_ECHO branch has no state check (line ~179)" % (len(s), n_echo)


def chk_neg_do():
    t = Terminal()
    d = b"".join(bytes([IAC, DO, o]) for o in range(256)) * 400
    s = sends_of(t.feed(d))
    if len(s) > 256 * 3:
        return "IAC DO n for n in 0..255 repeated 400x (%d cmds) -> %d IAC WONT replies; expected <=1 per option (RFC 1143: don't answer a DO for an option already refused) cause=_negotiate DO branch always replies (line ~200)" % (len(d) // 3, len(s))


def chk_neg_will_unknown():
    s = sends_of(Terminal().feed(bytes([IAC, WILL, 200]) * 100000))
    if len(s) > 5:
        return "IAC WILL 200 x100000 -> %d IAC DONT replies; expected <=1 (cause=_negotiate WILL else-branch line ~192, no _us/refused tracking)" % len(s)


def chk_neg_wont_echo():
    s = sends_of(Terminal().feed(bytes([IAC, WONT, 1]) * 100000))
    if len(s) > 5:
        return "IAC WONT 1 x100000 (echo already on) -> %d IAC DONT replies; unsolicited ack of a no-op change can loop with a peer (cause=_negotiate WONT/OPT_ECHO line ~194-197 replies unconditionally)" % len(s)


def chk_neg_wellformed():
    rng = random.Random(11)
    t = Terminal()
    d = bytearray()
    for _ in range(30000):
        d += bytes([IAC, rng.choice([WILL, WONT, DO, DONT]), rng.randint(0, 255)])
        if rng.random() < .1:
            d += bytes([IAC, rng.randint(0, 255)])
        if rng.random() < .1:
            d += b"zz"
    for s in sends_of(t.feed(bytes(d))):
        if len(s) != 3 or s[0] != IAC or s[1] not in (WILL, WONT, DO, DONT):
            return "malformed reply %s" % rep(s)
    # reply verb pairing
    pair = {WILL: (DO, DONT), DO: (WILL, WONT), WONT: (DONT,), DONT: ()}
    for v in (WILL, WONT, DO, DONT):
        for o in range(256):
            for s in sends_of(Terminal().feed(bytes([IAC, v, o]))):
                if s[1] not in pair[v] or s[2] != o:
                    return "IAC %d %d answered with %s (bad verb/option pairing)" % (v, o, rep(s))


def chk_neg_rewill_mxp():
    t = Terminal()
    s = sends_of(t.feed(bytes([IAC, WILL, 91, IAC, WONT, 91, IAC, WILL, 91])))
    if len(s) != 2:
        return "WILL MXP, WONT MXP, WILL MXP -> %d DO replies (expected 2: _us[91] is never cleared on WONT) cause=_negotiate WONT/OPT_MXP line ~198 doesn't reset self._us" % len(s)


def chk_mxp_disabled():
    t = Terminal(want_mxp=False)
    s = sends_of(t.feed(bytes([IAC, WILL, 91, IAC, SB, 91, IAC, SE]) + b"<b>x"))
    txt = "".join(e[1] for e in t.feed(b"<b>y") if e[0] == "text")
    if t.mxp or s != [bytes([IAC, DONT, 91])] or txt != "<b>y":
        return "want_mxp=False: mxp=%s sends=%s text=%s" % (t.mxp, s, rep(txt))


# ----------------------------------------------------------------- 7: misc adversarial
def chk_sb_iac_iac():
    t = Terminal()
    txt = "".join(e[1] for e in t.feed(bytes([IAC, SB, 24, 1, IAC, IAC, 2, IAC, SE]) + b"ok") if e[0] == "text")
    if txt != "ok":
        return "IAC IAC inside SB leaked/lost text: got %s" % rep(txt)
    return None


def chk_iac_se_outside_sb():
    t = Terminal()
    txt = "".join(e[1] for e in t.feed(b"a" + bytes([IAC, SE]) + b"b" + bytes([IAC, SB, 91]) + bytes([IAC, SE]) + b"c") if e[0] == "text")
    if txt != "abc" or not t.mxp:
        return "IAC SE outside SB: text=%s mxp=%s" % (rep(txt), t.mxp)


def chk_esc_end_then_data():
    t = Terminal()
    e1 = t.feed(b"A\x1b")
    e2 = t.feed(b"[31mB")
    txt = "".join(e[1] for e in e1 + e2 if e[0] == "text")
    key = [e for e in e2 if e[0] == "text"][-1][2]
    if txt != "AB" or key[0] != dc.ANSI16[1]:
        return "ESC | [31mB -> text=%s key=%s" % (rep(txt), key)


def chk_esc_esc_csi():
    t = Terminal()
    ev = t.feed(b"\x1b\x1b[31mX")
    txt = "".join(e[1] for e in ev if e[0] == "text")
    if txt != "X":
        return ("(arguable) ESC ESC [ 31 m X -> text=%s: a stray ESC swallows the next byte (here the 2nd ESC), so the CSI is printed literally; "
                "cause=_process ESC branch `i += 2` for any non-'[' (line ~233)" % rep(txt))


def chk_esc_swallows_next():
    t = Terminal()
    txt = "".join(e[1] for e in t.feed(b"a\x1b\nb") if e[0] == "text")
    if txt != "a\nb":
        return "(arguable) bare ESC eats the following char: b'a\\x1b\\nb' -> %s (cause=_process line ~233, any non-'[' byte after ESC is dropped, incl. newline/printable)" % rep(txt)


def chk_lone_specials_withheld():
    bad = []
    for d in (b"a < b\r\n", b"AT&T rocks\r\n", b"R&D\r\n", b"x & y\r\n", b"if (a<b) go\r\n"):
        t = mxp_on()
        got = "".join(e[1] for e in t.feed(d) if e[0] == "text")
        want = d.decode().replace("\r", "")
        if got != want:
            bad.append("%s -> %s (rest %s held in _pending)" % (rep(d), rep(got), rep(t._pending)))
    if bad:
        return ("MXP on: text after a lone '<' (<600 bytes with no '>') or '&' (<12 bytes, no ';') is held back even after a full line ended in LF, "
                "e.g. prompt/line shows late or never: " + "; ".join(bad[:3]) + " cause=_process '<' (line ~249) and '&' (line ~260) break heuristics; GA also doesn't flush pending")


def chk_entity_semantics():
    t = mxp_on()
    txt = "".join(e[1] for e in t.feed(b"&amp;lt; &#x41; &#65; &quot;") if e[0] == "text")
    bad = []
    if not txt.startswith("&lt; "):
        bad.append("double-decode %s" % rep(txt))
    if "&#x41;" in txt:
        bad.append("(note) hex entity &#x41; not decoded, shown literally: %s" % rep(txt))
    if bad:
        return "; ".join(bad) + " cause=_process '&' branch handles only decimal &#N; (line ~268)"


CHECKS = [
    ("01_CHUNKING_INVARIANCE chars/style/events/final-state", chk_chunk_invariance),
    ("01b_CHUNKING_INTERLEAVE text/event ordering positions", chk_chunk_interleave),
    ("01c_SB_MXP_FLUSHES_PRECEDING_TEXT", chk_sb_mxp_flush_order),
    ("01d_LONG_TAG_CHUNK_INDEPENDENT (>600 byte tag)", chk_long_tag_chunking),
    ("02a_NO_EXC random 200k bytes", chk_exc_random),
    ("02b_NO_EXC biased IAC/ESC/</&/[/; random", chk_exc_biased),
    ("02c_NO_EXC truncated/invalid UTF-8 + unicode digits", chk_exc_utf8),
    ("02d_NO_EXC all 2/3-byte telnet prefixes + SB combos", chk_exc_telnet_exhaustive),
    ("02e_NO_EXC absurd SGR params", chk_exc_sgr),
    ("02f_NO_EXC garbage MXP tags/entities", chk_exc_mxp),
    ("03a_MEM ESC[ digits no final", chk_mem_csi),
    ("03b_MEM MXP '<' no '>'", chk_mem_lt),
    ("03c_MEM MXP '&' no ';'", chk_mem_amp),
    ("03d_MEM IAC SB 24 no IAC SE", chk_mem_sb),
    ("03e_MEM endless IAC IAC", chk_mem_iac),
    ("04a_PERF 5MB dense SGR 4KB chunks", chk_perf_dense_sgr),
    ("04b_PERF 2MB partial '<' at every chunk end", chk_perf_partial_tag),
    ("04c_PERF attr regex on long tag", chk_perf_attr_regex),
    ("04d_PERF single huge feed _emit concat", chk_perf_emit_concat),
    ("04e_PERF '<' flood", chk_perf_lt_flood),
    ("05a_ANSI_RESET ESC[0m restores defaults", chk_ansi_reset),
    ("05b_MXP_DEPTH never negative / closers don't poison", chk_mxp_depth_nonneg),
    ("05c_TEXT_NO_ESC_NUL_CR", chk_text_no_controls),
    ("05d_TEXT_UTF8_ENCODABLE (no lone surrogates)", chk_text_encodable),
    ("05e_IAC_COMMAND_BYTES_NOT_LEAKED", chk_iac_commands_not_leaked),
    ("05f_IAC_IAC_IS_ONE_REPLACEMENT_CHAR", chk_iac_iac_is_u00ff),
    ("05g_MXP_OFF_TEXT_TRANSPARENT", chk_mxp_off_transparent),
    ("06a_NEG WILL MXP/SGA x100k bounded", chk_neg_will_mxp_sga),
    ("06b_NEG WILL ECHO x100k bounded", chk_neg_will_echo),
    ("06c_NEG DO n repeated bounded", chk_neg_do),
    ("06d_NEG WILL unknown x100k bounded", chk_neg_will_unknown),
    ("06e_NEG WONT ECHO x100k bounded", chk_neg_wont_echo),
    ("06f_NEG replies well-formed & correctly paired", chk_neg_wellformed),
    ("06g_NEG WILL MXP again after WONT MXP is answered", chk_neg_rewill_mxp),
    ("06h_NEG want_mxp=False refuses MXP", chk_mxp_disabled),
    ("07a_SB containing IAC IAC", chk_sb_iac_iac),
    ("07b_IAC SE outside SB", chk_iac_se_outside_sb),
    ("07c_ESC at end of chunk then more data", chk_esc_end_then_data),
    ("07d_ESC ESC [ restarts CSI (arguable)", chk_esc_esc_csi),
    ("07e_BARE ESC eats next char (arguable)", chk_esc_swallows_next),
    ("07f_LONE '<' / '&' text not withheld (MXP on)", chk_lone_specials_withheld),
    ("07g_ENTITY semantics (no double decode, hex)", chk_entity_semantics),
]


def main():
    only = sys.argv[1:]
    fails = 0
    t_all = time.time()
    for name, fn in CHECKS:
        if only and not any(o in name for o in only):
            continue
        t0 = time.time()
        del INFO[:]
        try:
            msg = fn()
        except Exception as e:  # noqa: BLE001
            msg = "CHECK CRASHED: %s" % loc(e)
        dt = time.time() - t0
        if msg:
            fails += 1
            print(("FAIL %s (%.1fs)\n     %s" % (name, dt, msg)).encode("ascii", "backslashreplace").decode())
        else:
            print("PASS %s (%.1fs)" % (name, dt))
        for i in INFO:
            print("     . " + i)
        sys.stdout.flush()
    print("\n%d check(s) failed, total %.1fs" % (fails, time.time() - t_all))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
