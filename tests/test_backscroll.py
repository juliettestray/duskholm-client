"""Scrollback length, and reloading the end of it between sessions (no network)."""
import json, os, socket, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import backscroll as bs
import tkinter as tk

# ---- the pieces -----------------------------------------------------------------------------------------------------
assert bs.total_lines({}) == 20000 and bs.total_lines({"scrollback_lines": "5000"}) == 5000
assert bs.total_lines({"scrollback_lines": "junk"}) == 20000
assert bs.keep_lines({}) == 2000 and bs.keep_lines({"keep_lines": "20000", "scrollback_lines": "5000"}) == 5000
c = {"scrollback_lines": "5000", "keep_lines": "20000"}
assert bs.clamp_keep(c) is True and c["keep_lines"] == "5000"
c = {"scrollback_lines": "5000", "keep_lines": "2000"}
assert bs.clamp_keep(c) is False and c["keep_lines"] == "2000"
c = {"scrollback_lines": "10000", "keep_lines": "20000"}
assert bs.clamp_keep(c) is True and c["keep_lines"] == "10000"
assert all(k in sc.CHOICE_WORDS for k in bs.TOTAL_CHOICES + bs.KEEP_CHOICES)
assert all(int(k) <= int(bs.TOTAL_CHOICES[-1]) for k in bs.KEEP_CHOICES)
assert bs.file_key("Duskholm.COM", 4000) == "duskholm.com_4000" and "/" not in bs.file_key("a/b\\c", 1)
cfg = sc.clean_settings({"host": "x", "scrollback_lines": "5000", "keep_lines": "20000"})
assert cfg["keep_lines"] == "5000", "what is kept is never more than the length"
cfg = sc.clean_settings({"host": "x", "scrollback_lines": "bogus", "keep_lines": "bogus", "keep_backscroll": "yes"})
assert (cfg["scrollback_lines"], cfg["keep_lines"], cfg["keep_backscroll"]) == ("20000", "2000", False)

# ---- in the app ---------------------------------------------------------------------------------------------------------
tmp = tempfile.mkdtemp()
sc.SETTINGS_PATH = os.path.join(tmp, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
asked = []
sc.messagebox.askokcancel = lambda title, text, **k: (asked.append(text), answer[0])[1]
answer = [True]
root = tk.Tk()
app = sc.App(root)
root.geometry("1250x720+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def nlines(w):
    return int(w.index("end-1c").split(".")[0])


def feed(n, tag="L", w=None):
    app._append([("%s%d\n" % (tag, i), None) for i in range(1, n + 1)])


pump(0.4)
assert app.cfg["scrollback_lines"] == "20000" and app.cfg["keep_backscroll"] is False and app.cfg["keep_lines"] == "2000"
assert any(k == "scrollback_lines" for k, *_ in sc.EXTRA_CHOICES) and any(k == "keep_backscroll" for k, *_ in sc.EXTRA_BOOLS)

# the length: lines past it go, oldest first
app._set_extra("scrollback_lines", "5000"); pump(0.1)
feed(5300)
assert nlines(app.out) <= 5001, nlines(app.out)
assert app.out.get("end-3l", "end-1c").splitlines()[-1] == "L5300" and "L1\n" not in app.out.get("1.0", "1.20")
app._set_extra("scrollback_lines", "10000")
feed(6000, "M")
assert 5001 < nlines(app.out) <= 10001, nlines(app.out)
app.clear()

# kept can never be above total: lowering the length lowers it, and a bigger one is refused down
app._set_extra("scrollback_lines", "20000")
app._set_extra("keep_lines", "20000"); assert app.cfg["keep_lines"] == "20000"
app._set_extra("scrollback_lines", "10000")
assert app.cfg["keep_lines"] == "10000" and app._xvars["keep_lines"].get() == "10000"
app._set_extra("keep_lines", "20000")
assert app.cfg["keep_lines"] == "10000", "cannot keep more than the scrollback"
app._set_extra("scrollback_lines", "5000"); assert app.cfg["keep_lines"] == "5000"
app._set_extra("scrollback_lines", "20000"); app._set_extra("keep_lines", "1000")

# turning reload on warns (and says why); saying no leaves it off
app.cfg["host"] = "h.example"; app.cfg["port"] = 4000
app.session.host, app.session.port = "h.example", 4000
app.session.name, app.session.wid = "", ""                  # (an address that is not a saved world: it is "World 1" now and after a relaunch)
app.v_host.set("h.example"); app.v_port.set("4000")          # (switching worlds copies the host box back into the world)
answer[0] = False
app._set_extra("keep_backscroll", True); pump(0.1)
assert asked and "slower" in asked[0] and "plain text" in asked[0] and "longer" in asked[0], asked
assert app.cfg["keep_backscroll"] is False and app._xvars["keep_backscroll"].get() is False
assert app.backscroll_save(app.session) is False and not os.path.exists(app._backscroll_dir())
answer[0] = True
app._set_extra("keep_backscroll", True); pump(0.1)
assert app.cfg["keep_backscroll"] is True and len(asked) == 2
# a window that is not tied to a world yet (nothing connected) saves nothing: it would replace that world's real text with a banner
assert app.backscroll_save(app.session) is False and not os.path.exists(app._backscroll_dir())
assert app.backscroll_load(app.session) == 0                      # (connecting does this once the world is known)
assert "slower start" in [l for k, d, l, dl, h in sc.EXTRA_BOOLS if k == "keep_backscroll"][0]

# saving: plain text, the last `keep` lines only
app.clear()
feed(3000)
assert app.backscroll_save(app.session) is True
path = app._bs_path(app.session)
assert os.path.basename(path).startswith("n_") and path.endswith(".txt"), path
text = open(path, encoding="utf-8").read()
assert text.splitlines() == ["L%d" % i for i in range(2001, 3001)], (len(text.splitlines()), text[:30])
app._set_extra("keep_lines", "500"); app.backscroll_save(app.session)
assert len(open(path, encoding="utf-8").read().splitlines()) == 500
app._set_extra("keep_lines", "1000"); app.backscroll_save(app.session)

# colours are not kept: it is the words only
app.clear()
app._append([("coloured text\n", "echo"), ("system words\n", "system")]); app.backscroll_save(app.session)
assert open(path, encoding="utf-8").read() == "coloured text\nsystem words\n"
app.clear(); feed(1200)
app.backscroll_save(app.session)

# loading: each world has a file of its own. A second world on the SAME address does not get the first one's text
s2 = app.open_new_world("Second"); pump(0.3)
s2.host, s2.port = "h.example", 4000
app.session = s2
app._append([("fresh output\n", None)])
assert app._bs_path(s2) != path, "same address, different world, different file"
assert app.backscroll_load(s2) == 0 and "Earlier text" not in s2.out.get("1.0", "end-1c"), "worlds are not mushed together"
app.backscroll_save(s2)
assert open(app._bs_path(s2), encoding="utf-8").read() == "fresh output\n" and open(path, encoding="utf-8").read().splitlines()[0] == "L201"
# the world's own text comes back, above its new text, once, with a line saying so
s2b = app.open_new_world("Second again"); pump(0.3)
s2b.host, s2b.port, s2b.name = "h.example", 4000, "Second"        # (the same world again, as after a relaunch)
app.session = s2b
app._append([("newer\n", None)])
assert app.backscroll_load(s2b) == 1
t = s2b.out.get("1.0", "end-1c").splitlines()
assert t[0] == "fresh output" and "Earlier text" in t[1] and "1 lines" in t[1] and t[2] == "newer", t
assert app.backscroll_load(s2b) == 0, "once per world"
app.close_world(s2b); pump(0.2)
# a world that has been saved is keyed by its id: it keeps its text through a rename or a new address
app.cfg["worlds"] = list(app.cfg["worlds"]) + [sc.clean_world({"name": "Saved One", "host": "h.example", "port": 4000, "tls": False, "note": ""})]
app.cfg["worlds"][-1]["id"] = "abcdef0123456789"
s2.name, s2.wid = "Saved One", ""
nm = app._bs_name(s2); assert nm == "w_abcdef0123456789", nm
s2.name, s2.host, s2.port = "Saved One (renamed)", "other.example", 1
s2.wid = "abcdef0123456789"
assert app._bs_name(s2) == nm, "an id does not change when the world is renamed or moved"
app.cfg["worlds"] = [w for w in app.cfg["worlds"] if w.get("id") != "abcdef0123456789"]
# the old file, named after the address, goes to the first world that asks and then is gone
legacy = os.path.join(app._backscroll_dir(), "old.example_23.txt")
open(legacy, "w", encoding="utf-8").write("legacy one\nlegacy two\n")
s4 = app.open_new_world("Fourth"); pump(0.3)
s4.host, s4.port = "old.example", 23
app.session = s4
assert app.backscroll_load(s4) == 2 and not os.path.exists(legacy)
s5 = app.open_new_world("Fifth"); pump(0.3)
s5.host, s5.port = "old.example", 23
app.session = s5
assert app.backscroll_load(s5) == 0, "only one world inherits it"
s3 = app.open_new_world("Third"); pump(0.3)
s3.host, s3.port = "else.example", 23
app.session = s3
assert app.backscroll_load(s3) == 0 and s3.out.get("1.0", "end-1c") == ""
app.session = app._shown
app.goto_world(0); pump(0.3)
for x in (s5, s4, s3, s2):
    app.close_world(x); pump(0.2)
assert os.path.exists(path)

# the timer saves, and starts again
app.clear(); feed(50, "T")
app._bs_job and app.root.after_cancel(app._bs_job)
app._backscroll_tick()
assert open(path, encoding="utf-8").read().splitlines()[-1] == "T50" and app._bs_job

# off: nothing saved any more and what was saved is deleted
app.cfg["keep_backscroll"] = True
app._set_extra("keep_backscroll", False); pump(0.1)
assert not os.path.exists(path) and not os.path.exists(app._backscroll_dir())
assert app.backscroll_save(app.session) is False
assert app.backscroll_load(app.session) == 0

# the DOS look: no dialog, a message that says the same thing
app.set_dos_mode(True); pump(0.5)
n0 = len(asked); answer[0] = False
app._set_extra("keep_backscroll", True); pump(0.1)
assert len(asked) == n0 and app.cfg["keep_backscroll"] is True
assert "slower" in app.out.get("1.0", "end-1c").replace("\n", " ")
labels = []
app.dos_options_menu(); pump(0.3)
shown = app._overlay
txt = "\n".join(str(it.get("label")) for it in shown._items if it)
assert "Scrollback length (lines): 20,000 lines" in txt and "Reload backscroll (slows start-up)" in txt, txt
assert "Backscroll to reload" in txt, txt
shown.close(); pump(0.2)
app.set_dos_mode(False); pump(0.5)

# start-up: nothing is loaded until you connect, because the world last used may not be the one you connect to
srv, srv2 = socket.socket(), socket.socket()
for x in (srv, srv2):
    x.bind(("127.0.0.1", 0)); x.listen(5)
port, port2 = srv.getsockname()[1], srv2.getsockname()[1]
app.cfg.update(host="127.0.0.1", port=port, tls=False, keep_lines="1000")
app.session.host, app.session.port, app.session.tls = "127.0.0.1", port, False
app.session.name, app.session.wid = "", ""
app.v_host.set("127.0.0.1"); app.v_port.set(str(port)); app.v_tls.set(False)
app.backscroll_load(app.session)                 # (as connecting to it does)
app.clear(); feed(400, "Z")
kpath = app._bs_path(app.session)
app.on_quit()                                   # saves on the way out (and closes the window)
assert os.path.exists(kpath)


def start():
    r = tk.Tk()
    a = sc.App(r)
    r.geometry("1250x720+20+20")
    e = time.time() + 0.8
    while time.time() < e:
        r.update(); time.sleep(0.01)
    return r, a


def spin(r, t):
    e = time.time() + t
    while time.time() < e:
        r.update(); time.sleep(0.01)


root2, app2 = start()
t = app2.out.get("1.0", "end-1c")
assert "Z1" not in t and "Earlier text" not in t, "nothing is loaded at start-up"
assert app2.backscroll_save(app2.session) is False, "and quitting without connecting must not overwrite what was saved"
app2.on_quit()
assert open(kpath, encoding="utf-8").read().splitlines()[0] == "Z1", "the saved text is untouched"
root2, app2 = start()
app2.toggle_connection(); spin(root2, 0.8)             # now the world is known: its own text comes back
t = app2.out.get("1.0", "end-1c").splitlines()
assert t[0] == "Z1" and t[399] == "Z400" and "Earlier text" in t[400], (t[:2], t[398:402])
assert app2.out.yview()[1] >= 0.999, "a new session starts at the bottom, with the newest text, not at the top of the old"
app2._append([("brand new line" + chr(10), None)])
spin(root2, 0.3)
assert app2.out.yview()[1] >= 0.999 and app2.out.bbox("end-2l") is not None, "and new text keeps following"
assert app2.cfg["keep_backscroll"] is True and app2.cfg["keep_lines"] == "1000"
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert saved["scrollback_lines"] == "20000" and saved["keep_backscroll"] is True
app2.toggle_connection(); spin(root2, 0.3)
root2.destroy()

# the same window opened, but a DIFFERENT world is connected to: the last world's text is not put into it
root3, app3 = start()
assert "Z1" not in app3.out.get("1.0", "end-1c")
app3.v_port.set(str(port2))
app3.toggle_connection(); spin(root3, 0.8)
t3 = app3.out.get("1.0", "end-1c")
assert "Z1" not in t3 and "Earlier text" not in t3, "another world: none of the last world's backlog"
assert app3.backscroll_save(app3.session) is True and "Z400" not in open(app3._bs_path(app3.session), encoding="utf-8").read()
assert open(kpath, encoding="utf-8").read().splitlines()[0] == "Z1", "the first world's saved text is still its own"
app3.toggle_connection(); spin(root3, 0.3)
root3.destroy()
srv.close(); srv2.close()
print("backscroll tests OK")
