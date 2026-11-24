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
assert app._notice_text == "Preview: Someone strides boldly in from the north", app._notice_text
assert app.notice.cget("text") == app._notice_text
app._on_data(b"Your ego form walk string is now: slinks\n\r"); pump(0.3)
assert app._notice_text == "Preview: Someone slinks in from the north"
app._on_data(b"Your changeling form walk is now: stalks predatorily\n\r"); pump(0.3)
assert app._notice_text == "Preview (changeling form): Someone stalks predatorily in from the north", app._notice_text
app._on_data(b"Your true form walk is now: strides\n\r"); pump(0.2)
assert app._notice_text == "Preview (true form): Someone strides in from the north"
app._on_data(b"[350/350DF 0ST 0WN 0LG M:0 K:0 ()] Your manticore walk is now: prowls\n\r"); pump(0.2)
assert app._notice_text == "Preview (manticore): Someone prowls in from the north", "even with a prompt stuck to the front"
app._on_data(b"Your walk is fine\n\r"); pump(0.1)
assert app._notice_text.startswith("Preview (manticore)"), "other lines do not change it"
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
want = "Preview (changeling form): Someone stalks in from the north"
assert app._notice_text == want and app._notice_until == 0.0 and app._notice_job is None, "no expiry"
app.set_notice("Time's up: tea", 30); assert app._notice_text.startswith("Time's up")
app.set_notice("", 0); assert app._notice_text == want, "a short notice gives way to it again"
app.set_dos_mode(True); pump(0.2); app.set_dos_mode(False); pump(0.2)
assert app._notice_text == want, "toggling DOS keeps it"
first = app.session
w2 = app.open_new_world("Two"); pump(0.3)
assert app._notice_text == "", "another world has its own"
app._on_data(b"[Walk        ] - Ywellia strides in from the right.\n\r"); pump(0.2)
assert app._notice_text == "Preview: Ywellia strides in from the north", "read from the display command: " + app._notice_text
app.switch_session(first); pump(0.2)
assert app._notice_text == want, "and the first world's walk is back"
app.switch_session(w2); pump(0.2)
assert app._notice_text.startswith("Preview: Ywellia")
app.close_world(w2); pump(0.2)
assert app.session is first and app._notice_text == want
# a walk set with no form named
app._on_data(b"Your new walk is: ambles\n\r"); pump(0.2)
assert app._notice_text == "Preview: Someone ambles in from the north" and app.session.form == "credit"
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
# the editor round trip keeps a status action
t = triggers.validate_trigger({"name": "x", "pattern": "a*", "mode": "plain",
                               "actions": [{"type": "status", "text": "hi %1"}]})
t = t[0] if isinstance(t, tuple) else t
assert sc.values_from_trigger(t)["status"] == "hi %1"
root.update(); root.destroy()
print("status tests OK")
