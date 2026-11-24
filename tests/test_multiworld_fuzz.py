"""Random sequences of world operations (open, switch, close, data, drops, typing, look and skin changes,
resizes) with the invariants checked as it goes: one world on screen, nothing leaking between worlds' scrollbacks,
no exceptions, no widgets left behind. Fixed seeds, so a failure can be replayed."""
import os, random, sys, tempfile, time, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

CR = chr(13) + chr(10)
ESC = chr(27)
errors = []
sc.traceback.print_exc = lambda *a, **k: errors.append(traceback.format_exc())
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")


class FakeConn:
    gen = 0

    def __init__(self):
        self.sent = []

    def send(self, b):
        self.sent.append(b)
        return True

    def close(self, *a):
        pass

    def open(self, *a, **k):
        pass


root = tk.Tk()
app = sc.App(root)
root.geometry("1000x640+20+20")
app.cfg["auto_reconnect"] = False


def pump(t=0.03):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.005)


def check(step, seed, deep=False):
    assert not errors, "seed %d step %d: %s" % (seed, step, errors[:1])
    assert app.sessions and app.session is app._shown and app._cfg_owner is app._shown, (seed, step, "state")
    assert app._shown in app.sessions
    if deep:
        pump(0.15)
        for s in app.sessions:
            mapped = s.out.winfo_ismapped()
            assert mapped == (s is app._shown), "seed %d step %d: world %r mapped=%s shown=%s" % (
                seed, step, s.name, mapped, s is app._shown)
        for w, _r in app._themed:
            assert w.winfo_exists(), "seed %d step %d: a closed world's widget is still registered" % (seed, step)


def run(seed, steps):
    rnd = random.Random(seed)
    # start from one clean world
    while len(app.sessions) > 1:
        app.close_world(app.sessions[-1])
    app.set_dos_mode(False)
    base = app.sessions[0]
    sent_to = {}                                       # session -> [tokens sent to it]
    ids = {}
    counter = [0]

    def sid(s):
        return ids.setdefault(id(s), len(ids))

    def fresh(s):
        counter[0] += 1
        tok = "TOK%d_%d" % (sid(s), counter[0])
        sent_to.setdefault(s, []).append(tok)
        return tok

    def ensure_conn(s):
        if not isinstance(s.conn, FakeConn):
            s.conn = FakeConn()

    ensure_conn(base)
    base.connected = True
    for step in range(steps):
        op = rnd.choice(["data", "data", "data", "partial", "prompt", "colour", "switch", "switch", "open", "close",
                         "connected", "closed", "type", "dos", "skin", "resize", "burst", "key"])
        live = list(app.sessions)
        s = rnd.choice(live)
        if op == "open" and len(live) < 6:
            n = app.open_new_world("W%d" % rnd.randint(1, 4)); ensure_conn(n)
        elif op == "close" and len(live) > 1:
            victim = rnd.choice(live)
            sent_to.pop(victim, None)
            app.close_world(victim)
        elif op == "switch":
            app.switch_session(s)
        elif op in ("data", "partial", "colour", "burst", "prompt"):
            ensure_conn(s)
            if op == "data":
                text = "line %s here%s" % (fresh(s), CR)
            elif op == "partial":
                text = "unfinished %s" % fresh(s)
            elif op == "colour":
                text = "%s[31m%s%s[0m%s" % (ESC, fresh(s), ESC, CR)
            elif op == "prompt":
                text = "%s[%d/100DF 50ST 50WN 0LG M:0 K:0 ()] " % (CR, rnd.randint(1, 100))
            else:
                text = "".join("burst %s%s" % (fresh(s), CR) for _ in range(rnd.randint(5, 40)))
            s.q.put((s.conn.gen, "data", text.encode()))
        elif op == "connected":
            s.q.put((s.conn.gen, "connected", None))
        elif op == "closed":
            s.q.put((s.conn.gen, "closed", "Connection closed."))
        elif op == "type" and app._shown.connected:
            ensure_conn(app._shown)
            app.input.delete(0, "end"); app.input.insert(0, "cmd%d" % step); app._on_enter(None)
        elif op == "dos":
            app.set_dos_mode(not app.dos)
        elif op == "skin":
            app.set_skin(rnd.choice(["Plain", "Moody", "Retro DOS", "Retro Amber"]) if app.dos is False or True else "Plain")
        elif op == "resize":
            root.geometry("%dx%d+20+20" % (rnd.choice([700, 900, 1100]), rnd.choice([420, 560, 700])))
        elif op == "key":
            root.event_generate("<Control-F%d>" % rnd.randint(1, 8))
        pump(0.03)
        check(step, seed, deep=(step % 12 == 0))
    # flush everything, then every token must be in its own world and nowhere else
    pump(0.6)
    check(steps, seed, deep=True)
    texts = {s: s.out.get("1.0", "end") for s in app.sessions}
    for s, toks in sent_to.items():
        if s not in texts:
            continue
        for tok in toks:
            assert tok in texts[s], "seed %d: %s never reached its world %r" % (seed, tok, s.name)
    for s, txt in texts.items():
        mine = {t for t in sent_to.get(s, [])}
        for other, toks in sent_to.items():
            if other is s:
                continue
            for tok in toks:
                assert tok not in txt, "seed %d: %s (sent to another world) appeared in %r" % (seed, tok, s.name)


pump(0.5)
for seed in (11, 22, 33):
    run(seed, 220)
widgets_before = len(app._themed)
while len(app.sessions) > 1:
    app.close_world(app.sessions[-1])
pump(0.3)
assert len(app._themed) <= widgets_before, "closing worlds releases their widgets"
assert not errors, errors[:1]
root.destroy()
print("multiworld fuzz tests OK")
