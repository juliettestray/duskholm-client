"""Highlights on rules that match what I send colour my own echoed line (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import boxes
import triggers as T
import tkinter as tk


def rule(pattern, mode="regex", scope="all", sent=True, **kw):
    d = dict({"name": pattern[:30], "mode": mode, "pattern": pattern,
              "actions": [{"type": "highlight", "fg": 15, "bg": 1, "scope": scope}]}, **kw)
    if sent:
        d["when"] = "sent"
    return T.validate_trigger(d)


def marked(line, *rules):
    return [line[lo:hi] for lo, hi, _a in T.echo_highlights(line, list(rules))]


# ---- the matching -----------------------------------------------------------------------------------------------------------------
typos = dict([p for p in sc.trigger_presets() if p["name"] == "Highlight my typos"][0], enabled=True)
assert marked("say Teh cat adn the hat", typos) == ["Teh", "adn"], "whole words, any case, every one"
assert marked("say tehran is far", typos) == []
assert marked("a teh b teh", rule("teh", "plain", "match")) == ["teh"]
assert marked("a teh b teh", rule("teh", "plain", "line")) == ["a teh b teh"]
long = "emote " + "waits quietly. " * 200 + "then teh end"
assert len(long) > 3000 and marked(long, typos) == ["teh"], "late in a long line"
assert marked(long, rule("teh", "plain")) == ["teh"]
assert marked("x" * 590 + " teh " + "y" * 900, typos) == ["teh"]
assert marked("say word " * 200 + "done", rule("word$")) == [], "'$' is the end of the line, not of a piece of it"
assert marked("say " + "blah " * 300 + "word", rule("word$")) == ["word"]
assert marked("say " + "blah " * 300, rule("^say")) == ["say"]
assert marked("teh", dict(typos, enabled=False)) == []
first = rule("teh", "plain", priority=5, stop=True)
assert len(T.echo_highlights("teh adn", [typos, first])) == 1, "stop ends the run"

# ---- in the app --------------------------------------------------------------------------------------------------------------------
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1000x700+20+20")
sent = []
app.conn = type("C", (), {"gen": 0, "send": lambda self, b: sent.append(b) or True, "close": lambda *a: None})()
app.connected = True


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def coloured():
    """The stretches of the main window that carry a colour tag."""
    out = []
    for name in app._tags:
        r = app.out.tag_ranges(name)
        out += [(app.out.get(r[i], r[i + 1]), name, str(r[i])) for i in range(0, len(r), 2)]
    return out


pump(0.4)
app.cfg["triggers"] = [typos, rule("cat", "plain", sent=False)]
app.out.configure(state="normal"); app.out.delete("1.0", "end"); app.out.configure(state="disabled")
app.send_line("say teh cat adn dog"); pump(0.2)
got = coloured()
assert sorted(t for t, _n, _p in got) == ["adn", "teh"], got
assert sent[-1] == b"say teh cat adn dog\r\n", "what goes to the game is untouched"
assert "say teh cat adn dog\n" in app.out.get("1.0", "end")
_text, name, pos = got[0]
tags = app.out.tag_names(pos)
assert "echo" in tags and name in tags and tags.index(name) > tags.index("echo"), "the colour wins over the echo colour: %r" % (tags,)
assert str(app.out.tag_cget(name, "background")) != str(app.theme["bg"])

# a password is never marked or shown
n = len(app.out.get("1.0", "end"))
app.send_line("teh", echo=True, secret=True); pump(0.2)
assert len(coloured()) == 2

# with typed commands hidden there is nothing to mark
app.cfg["show_echo"] = False
app.send_line("say teh"); pump(0.2)
assert len(coloured()) == 2
app.cfg["show_echo"] = True

# 'log my commands' off still leaves a marked line out of the log, whole
import io
app.cfg["log_echo"] = False
app.logfile = io.StringIO()
app.send_line("say teh end"); pump(0.2)
assert "teh" not in app.logfile.getvalue() and "end" not in app.logfile.getvalue()
app.logfile = None

# joining boxes leaves my marked echo alone, like any echo
pieces = [("|--|\n", ("echo", "x")), ("|--|\n", "echo")]
assert boxes.connect_pieces(pieces, skip_tags=("echo", "system")) == pieces

# the editor keeps such a rule as it is
v = sc.values_from_trigger(typos)
assert v["sent"] and v["every"]
back = sc.trigger_from_values(v)[0]
assert back == typos, back
print("echo highlight tests OK")
root.destroy()
