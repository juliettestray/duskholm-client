"""Scrollback length, and reloading the end of it between sessions (no network)."""
import json, os, sys, tempfile, time
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
app.v_host.set("h.example"); app.v_port.set("4000")          # (switching worlds copies the host box back into the world)
answer[0] = False
app._set_extra("keep_backscroll", True); pump(0.1)
assert asked and "slower" in asked[0] and "plain text" in asked[0] and "longer" in asked[0], asked
assert app.cfg["keep_backscroll"] is False and app._xvars["keep_backscroll"].get() is False
assert app.backscroll_save(app.session) is False and not os.path.exists(app._backscroll_dir())
answer[0] = True
app._set_extra("keep_backscroll", True); pump(0.1)
assert app.cfg["keep_backscroll"] is True and len(asked) == 2
assert "slower start" in [l for k, d, l, dl, h in sc.EXTRA_BOOLS if k == "keep_backscroll"][0]

# saving: plain text, the last `keep` lines only
app.clear()
feed(3000)
assert app.backscroll_save(app.session) is True
path = os.path.join(app._backscroll_dir(), "h.example_4000.txt")
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

# loading: above a new world's text, once, with a line saying so; a new world at another address gets nothing
s2 = app.open_new_world("Second"); pump(0.3)
s2.host, s2.port = "h.example", 4000
app.session = s2
app._append([("fresh output\n", None)])
n = app.backscroll_load(s2)
assert n == 1000, n
t = s2.out.get("1.0", "end-1c").splitlines()
assert t[0] == "L201" and t[999] == "L1200" and "Earlier text" in t[1000] and "1000 lines" in t[1000] and t[1001] == "fresh output", (t[0], t[999], t[1000:1003])
assert app.backscroll_load(s2) == 0, "once per world"
s3 = app.open_new_world("Third"); pump(0.3)
s3.host, s3.port = "else.example", 23
app.session = s3
assert app.backscroll_load(s3) == 0 and s3.out.get("1.0", "end-1c") == ""
app.session = app._shown
app.goto_world(0); pump(0.3)
app.close_world(s3); pump(0.2); app.close_world(s2); pump(0.2)
assert os.path.exists(os.path.join(app._backscroll_dir(), "h.example_4000.txt"))

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

# start-up: the next run puts the saved text back on its own, above its first message
app.cfg["keep_lines"] = "1000"
app.clear(); feed(400, "Z")
app.on_quit()                                   # saves on the way out (and closes the window)
assert os.path.exists(os.path.join(tmp, "backscroll", "h.example_4000.txt"))
root2 = tk.Tk()
app2 = sc.App(root2)
root2.geometry("1250x720+20+20")
end = time.time() + 0.8
while time.time() < end:
    root2.update(); time.sleep(0.01)
t = app2.out.get("1.0", "end-1c").splitlines()
assert t[0] == "Z1" and t[399] == "Z400" and "Earlier text" in t[400], (t[:2], t[398:402])
assert app2.out.yview()[1] >= 0.999, "a new session starts at the bottom, with the newest text, not at the top of the old"
app2._append([("brand new line\n", None)])
end = time.time() + 0.3
while time.time() < end:
    root2.update(); time.sleep(0.01)
assert app2.out.yview()[1] >= 0.999 and app2.out.bbox("end-2l") is not None, "and new text keeps following"
assert app2.cfg["keep_backscroll"] is True and app2.cfg["keep_lines"] == "1000"
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert saved["scrollback_lines"] == "20000" and saved["keep_backscroll"] is True
root2.destroy()
print("backscroll tests OK")
