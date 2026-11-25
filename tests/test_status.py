"""Status-line action and the credit-walk preview preset (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import triggers
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


assert not any("walk" in p["name"].lower() for p in sc.trigger_presets()), "built in, not a preset"
app.connected = True; app._online_since = time.time()
app._on_data(b"Your credit walk string is now: strides boldly\n\r"); pump(0.3)
assert app._notice_text == "Walk: Someone strides boldly in from the right.", app._notice_text
assert app.notice.cget("text") == app._notice_text
app._on_data(b"Your ego form walk string is now: slinks\n\r"); pump(0.3)
assert app._notice_text == "Walk: Someone slinks in from the right."
app._on_data(b"Your changeling form walk is now: stalks predatorily\n\r"); pump(0.3)
assert app._notice_text == "Walk (changeling form): Someone stalks predatorily in from the right.", app._notice_text
app._on_data(b"Your true form walk is now: strides\n\r"); pump(0.2)
assert app._notice_text == "Walk (true form): Someone strides in from the right."
app._on_data(b"[350/350DF 0ST 0WN 0LG M:0 K:0 ()] Your manticore walk is now: prowls\n\r"); pump(0.2)
assert app._notice_text == "Walk (manticore): Someone prowls in from the right.", "even with a prompt stuck to the front"
app._on_data(b"Your walk is fine\n\r"); pump(0.1)
assert app._notice_text.startswith("Walk (manticore)"), "other lines do not change it"
app.cfg["walk_preview"] = False; app.set_notice("")
app._on_data(b"Your credit walk string is now: x\n\r"); pump(0.2)
assert app._notice_text == "", "it can be switched off"
app.cfg["walk_preview"] = True
app._on_data(b"Your ego form walk string is now: slinks\n\r"); pump(0.3)
app.set_dos_mode(True); pump(0.4)
segs, _ = app._dos_segments(100)
assert any("Someone slinks" in x[0] for x in segs), segs
segs, _ = app._dos_segments(100)
texts = [x[0] for x in segs]
assert texts.index([t for t in texts if "Someone slinks" in t][0]) == len(texts) - 2 and texts[-1].startswith("TLS"), \
    "the walk preview sits just left of TLS / ANSI at the bottom"
app.session.walk_text = ""; app.set_notice(""); assert not any("Someone" in x[0] for x in app._dos_segments(100)[0])
app.set_dos_mode(False)
# the walk stays up (no timeout), through other notices, look changes and switching worlds
app._on_data(b"Your changeling form walk is now: stalks\n\r"); pump(0.2)
want = "Walk (changeling form): Someone stalks in from the right."
assert app._notice_text == want and app._notice_until == 0.0 and app._notice_job is None, "no expiry"
app.set_notice("Time's up: tea", 30); assert app._notice_text.startswith("Time's up")
app.set_notice("", 0); assert app._notice_text == want, "a short notice gives way to it again"
app.set_dos_mode(True); pump(0.2); app.set_dos_mode(False); pump(0.2)
assert app._notice_text == want, "toggling DOS keeps it"
first = app.session
w2 = app.open_new_world("Two"); pump(0.3)
assert app._notice_text == "", "another world has its own"
app._on_data(b"[Walk        ] - Ywellia strides in from the right.\n\r"); pump(0.2)
assert app._notice_text == "Walk: Ywellia strides in from the right.", "read from the display command: " + app._notice_text
app._on_data(b"[Name        ] - Ywellia\n\r[Intro       ] - a tall woman with long silver hair\n\r"); pump(0.2)
assert app._notice_text == "Walk: Ywellia strides in from the right.", app._notice_text
app._on_data(b"[Walk        ] - A tall woman with long silver hair glides gracefully in from the right.\n\r"
             b"[Intro       ] - a tall woman with long silver hair\n\r"); pump(0.3)
assert app._notice_text == "Walk: Ywellia glides gracefully in from the right.", "the long intro becomes your name: " + app._notice_text
app.switch_session(first); pump(0.2)
assert app._notice_text == want, "and the first world's walk is back"
app.switch_session(w2); pump(0.2)
assert app._notice_text.startswith("Walk: Ywellia glides")
app.close_world(w2); pump(0.2)
assert app.session is first and app._notice_text == want
# a walk set with no form named
app._on_data(b"Your new walk is: ambles\n\r"); pump(0.2)
assert app._notice_text == "Walk: Ywellia ambles in from the right." and app.session.form == "credit"
# a new login clears it
app._handle_event("connected", None); pump(0.2)
assert app._notice_text == "" and not app.session.walks, "cleared on login"
# a line that trickled in keeps its colours in the pane
app.connected = True
app.cfg["panes"] = [{"name": "Tells", "title": "Tells", "max_lines": 100, "timestamps": False}]
app.cfg["triggers"] = [{"name": "t", "pattern": "tells you", "mode": "plain", "enabled": True,
                        "actions": [{"type": "route", "pane": "Tells"}]}]
app._on_data(b"Goose tells you \x1b[1;32mOOCly\x1b[0m"); pump(0.35)     # arrives in two parts, the first one drawn
app._on_data(b" 'kitten'\n\r"); pump(0.3)
pane = app._panes["tells"]
hist = pane["history"][-1]
assert any(k[0] is not None or k[4] for _t, k in hist), "the pane's line keeps its colour: %r" % (hist,)
assert "".join(t for t, _k in hist) == "Goose tells you OOCly 'kitten'", hist
# pasting emoji: kept in the box when the converter is on, dropped (as before) when it is off
def paste(text):
    app.input.delete(0, "end")
    root.clipboard_clear(); root.clipboard_append(text)
    app._on_paste(None)
    return app.input.get()
app.cfg["emoji"] = True
assert paste("hi \U0001F600 café\tok") == "hi \U0001F600 cafe ok", "emoji stay, the rest is cleaned as usual"
sent = []
app.conn = type("C", (), {"gen": 0, "send": lambda self, b: sent.append(b) or True, "close": lambda *a: None})()
app.connected = True
app.send_line(app.input.get())
assert sent[-1] == b"hi :grinning: cafe ok\r\n", sent[-1]
# an emoji that reaches us as two UTF-16 halves (some input methods) is put back together and sent
half = chr(0xD83D) + chr(0xDE00)
assert sc.join_surrogates("hi " + half + "!") == "hi " + chr(0x1F600) + "!" and sc.join_surrogates("plain") == "plain"
app.input.delete(0, "end")
app.send_line("go " + half)
assert sent[-1] == b"go :grinning:" + bytes([13, 10]), sent[-1]
app.cfg["emoji"] = False
assert paste("hi \U0001F600 there") == "hi  there", "off: as before"
# the editor round trip keeps a status action
t = triggers.validate_trigger({"name": "x", "pattern": "a*", "mode": "plain",
                               "actions": [{"type": "status", "text": "hi %1"}]})
t = t[0] if isinstance(t, tuple) else t
assert sc.values_from_trigger(t)["status"] == "hi %1"
root.update(); root.destroy()
print("status tests OK")
