"""Screen reader mode end to end, with a fake voice (no sound, no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import speech
import tkinter as tk

home = tempfile.mkdtemp()
os.environ["USERPROFILE"] = os.environ["HOME"] = home
sc.SETTINGS_PATH = os.path.join(home, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
# never start a real voice in tests
speech.make_backend = lambda choice="auto", rate=0: (speech.FakeBackend(), "Speaking through a test voice.")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def feed(*lines):
    for l in lines:
        app._on_data((l + "\n\r").encode())
    pump(0.2)


app.connected = True; app._online_since = time.time()


def prompt(text):
    app._on_data(text.encode()); pump(0.2)


assert not app.sr_on() and isinstance(app.speech.backend, speech.NullBackend), "off by default"
feed("Nothing is spoken yet")

# ---- turning it on
app.set_dos_mode(True); pump(0.4)
assert app.dos
app._set_extra("screen_reader", True); pump(0.3)
fb = app.speech.backend
assert app.sr_on() and isinstance(fb, speech.FakeBackend)
assert not app.dos, "screen reader mode uses the plain look"
assert any("Screen reader mode on" in t for t in fb.said), fb.said
app.set_dos_mode(True); pump(0.2)
assert not app.dos and "not available" in app.out.get("1.0", "end"), "the DOS look is refused"
assert app.root.title() == "Sanctuary (screen reader mode)"
fb.said.clear()

# ---- hearing the game
feed("You hit the goblin.", "| ,______________, |", "-----", "[350/350DF 80ST 1WN 0LG M:3 K:2 (North 1/5:1/5)] ")
assert fb.said[:1] == ["You hit the goblin."] and len(fb.said) <= 3, fb.said
assert all("350/350DF" not in t for t in fb.said), "the prompt line is never read"
feed("[350/350DF 80ST 1WN 0LG M:3 K:2 (North 1/5:1/5)] The goblin dies.")
assert fb.said[-1] == "The goblin dies.", "text after a prompt is read, the prompt is not"
fb.said.clear()
app._on_data(b"Partial text with no newline"); pump(0.4)
assert fb.said == [], "unfinished lines (prompts) are not read until they are whole lines"
app._on_data(b"\n\r"); pump(0.2); assert fb.said == ["Partial text with no newline"]
fb.said.clear()

# ---- triggers: speak and silence, and pane prefixes
presets = {p["name"]: p for p in sc.trigger_presets()}
app._store_trigger(None, dict(presets["Capture OOC to a pane"], enabled=True))
app._store_trigger(None, {"name": "spam", "mode": "plain", "pattern": "The wind howls*", "priority": 0, "enabled": True,
                          "actions": [{"type": "silence"}]})
app._store_trigger(None, {"name": "danger", "mode": "plain", "pattern": "You are bleeding*", "priority": 0, "enabled": True,
                          "actions": [{"type": "speak", "text": "Danger. Bleeding.", "interrupt": True}]})
feed("[OOC] Bob: 'anyone around?'")
assert "OOC: [OOC] Bob: 'anyone around?'" in fb.said, fb.said
n = len(fb.said)
feed("The wind howls through the trees.")
assert len(fb.said) == n, "silenced lines are not read"
assert app.speech.history[-1].startswith("The wind howls"), "...but can still be reviewed"
feed("You are bleeding badly.")
assert "Danger. Bleeding." in fb.said and ("say", "Danger. Bleeding.", True) in fb.events
assert fb.said[-1] == "You are bleeding badly." or fb.said[-2] == "You are bleeding badly."
t = sc.values_from_trigger(app.cfg["triggers"][-1])
assert t["speak"] == "Danger. Bleeding." and t["speak_int"] is True
t2, _ = sc.trigger_from_values(dict(t, silence=True))
assert [a["type"] for a in t2["actions"]] == ["speak", "silence"]
assert sc.trigger_from_values(sc.values_from_trigger(app.cfg["triggers"][1]))[0]["actions"] == [{"type": "silence"}]

# ---- system messages
fb.said.clear(); app.system("Connected to somewhere"); assert fb.said == ["Connected to somewhere"]

# ---- review keys
app.speech.history.clear(); app.speech.review = None
feed("first line", "second line", "third line")
fb.said.clear()
app.sr_prev(); app.sr_prev(); assert fb.said == ["third line", "second line"], fb.said
app.sr_next(); assert fb.said[-1] == "third line"
app.sr_next(); assert fb.said[-1] == "third line. Bottom."
app.sr_prev(); app.sr_prev(); app.sr_prev(); app.sr_prev()
assert fb.said[-1] == "first line. Top."
app.sr_last(); assert fb.said[-1] == "third line"
app.sr_stop(); assert ("stop",) in fb.events

# ---- stats and alerts
prompt("[350/350DF 10ST 0WN 0LG M:0 K:0 (North 1/5:1/5)] ")
fb.said.clear(); app.sr_stats()
assert fb.said == ["DF 350 of 350 (100 percent). stun 10. wounds 0. LG 0. move timer ready. attack timer ready. North 1/5:1/5."], fb.said
fb.said.clear()
prompt("[350/350DF 60ST 0WN 0LG M:2 K:1 (North 1/5:1/5)] ")
assert "Stun 60" in fb.said, fb.said
prompt("[350/350DF 80ST 0WN 0LG M:2 K:1 (North 1/5:1/5)] ")
assert "Stun 80" in fb.said, "crossing 75 is announced"
n = len(fb.said)
prompt("[350/350DF 82ST 0WN 0LG M:2 K:1 (North 1/5:1/5)] ")
assert len(fb.said) == n, "no repeat inside the same band"
prompt("[160/350DF 82ST 0WN 0LG M:2 K:1 (North 1/5:1/5)] ")
assert any("percent" in t for t in fb.said[n:]), fb.said
n = len(fb.said)
app._last_prompt = dict(app._last_prompt, cooldowns=[("M", 2), ("K", 1)]); app._prompt_time = time.time() - 2.5
app.sr_alerts(app._prompt_view())
assert "Move ready" in fb.said[n:] and "Attack ready" in fb.said[n:], fb.said[n:]
app.cfg["sr_alerts"] = False; n = len(fb.said)
prompt("[350/350DF 99ST 0WN 0LG M:2 K:1 (North 1/5:1/5)] ")
assert len(fb.said) == n, "alerts can be switched off"
app.cfg["sr_alerts"] = True

# ---- other keys, mute, commands
fb.said.clear(); app.sr_time(); assert fb.said and fb.said[-1].startswith("The time is") and "moon" in fb.said[-1]
app.sr_pane(); assert "OOC" in fb.said[-1] and "anyone around" in fb.said[-1], fb.said[-1]
app.sr_mute(); fb.said.clear(); feed("muted line"); assert fb.said == [] and app.speech.history[-1] == "muted line"
app.sr_mute(); assert fb.said[-1] == "Speech on."
app._local("/sr status"); assert "Screen reader mode is on" in app.out.get("1.0", "end")
app._local("/sr test"); assert "speech test" in fb.said[-1]
app._local("/sr rate 3"); assert app.cfg["sr_rate"] == 3
app._local("/sr alerts off"); assert app.cfg["sr_alerts"] is False
app._local("/sr bogus"); app._local("/sr voice windows"); assert app.cfg["sr_voice"] == "windows"
fb = app.speech.backend                                  # a new voice was made
app._local("/sr help"); assert "Alt R" in fb.said[-1]

# ---- hotkeys are real keys, and can be changed
app.root.focus_force(); pump(0.3)
called = []
app.sr_last = lambda: called.append("last")
app._bind_hotkeys()
app.root.event_generate("<Alt-r>"); pump(0.2)
assert called == ["last"], called
ok, m = app.set_hotkeys({"sr_last": "Ctrl-Shift-J"}); assert ok, m
app.root.event_generate("<Alt-r>"); pump(0.2); assert called == ["last"]
app.set_hotkeys({}); del app.sr_last
ok, m = app.set_hotkeys({"sr_last": "Alt-S"}); assert not ok, "Alt-S is already the stats key"
app.set_hotkeys({})

# ---- off again, and with it off the keys just explain
app._set_extra("screen_reader", False); pump(0.3)
assert not app.sr_on() and isinstance(app.speech.backend, speech.NullBackend) and app.root.title() == "Sanctuary"
app.sr_prev(); assert "Screen reader mode is off" in app.out.get("1.0", "end")
app.set_dos_mode(True); pump(0.3); assert app.dos, "the DOS look is back once it is off"
app.set_dos_mode(False); pump(0.3)

# ---- settings
c = sc.clean_settings({"host": "x", "screen_reader": "yes", "sr_voice": "robot", "sr_rate": 99, "sr_alerts": 5})
assert c["screen_reader"] is False and c["sr_voice"] == "auto" and c["sr_rate"] == 10 and c["sr_alerts"] is True
assert sc.clean_settings({"host": "x", "sr_rate": True})["sr_rate"] == 0

root.update(); root.destroy()
print("access tests OK")
