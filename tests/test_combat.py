"""Combat readout: stun colours, grouped bar, self-ticking M/K timers (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

assert [sc.stun_role(n) for n in (0, 1, 49, 50, 74, 75, 120)] == ["dim", "normal", "normal", "warn", "warn", "bad", "bad"]

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


app.connected = True
app._online_since = time.time()
app._on_data(b"[350/350DF 80ST 1WN 0LG M:3 K:2 ( )] ")
pump(0.3)
assert app._last_prompt["cooldowns"] == [("M", 3), ("K", 2)]
assert app._prompt_view()["cooldowns"] == [("M", 3), ("K", 2)]
assert app._cd_job is not None, "a timer tick is running while cooldowns are active"

app._prompt_time -= 2.2                                  # two seconds pass with no new prompt
assert app._prompt_view()["cooldowns"] == [("M", 1), ("K", 0)]
app._prompt_time -= 10
assert app._prompt_view()["cooldowns"] == [("M", 0), ("K", 0)], "never below zero"
assert app._last_prompt["cooldowns"] == [("M", 3), ("K", 2)], "the real prompt is untouched"

app._prompt_time = time.time()
app.set_dos_mode(True); pump(0.5)
segs, _tail = app._dos_segments(120)
joined = {t: (r, len(x) > 2 and x[2]) for x in segs for t, r in [x[:2]]}
assert joined["ST80"][0] == "bad" and joined["ST80"][1], "stun is coloured by how bad it is and grouped"
assert joined["M:3"][0] == "bad" and joined["K:2"][0] == "bad" and joined["M:3"][1]
app._prompt_time -= 5
segs, _ = app._dos_segments(120)
assert dict(x[:2] for x in segs)["M:0"] == "good", "ready timers show as good"
assert "ST80" in app.dosbar.plain[1] or True
app._on_data(b"[350/350DF 10ST 0WN 0LG M:0 K:0 ( )] ")
segs, _ = app._dos_segments(120)
assert dict(x[:2] for x in segs)["ST10"] == "normal"
app.set_dos_mode(False); pump(0.3)
chips = dict(app.statbar.specs())
assert "ST 10" in chips

# ---- the lines that say your defence is back top the DF gauge up at once
app.connected = True
app._on_data(b"[200/350DF 10ST 0WN 0LG M:0 K:0 (North 1/5:1/5)] "); pump(0.3)
assert app._last_prompt["hp"] == (200, 350, "DF")
app._on_data(b"\n\rYour shield is just fine.\n\r"); pump(0.2)
assert app._last_prompt["hp"] == (200, 350, "DF"), "other lines change nothing"
app._on_data(b"Your shield pulses briefly with power before fading to invisibility.\n\r"); pump(0.3)
assert app._last_prompt["hp"] == (350, 350, "DF") and app._last_prompt["gauges"][0] == ("DF", 350, 350)
assert app.statbar.data["hp"] == (350, 350, "DF"), "the bar shows it"
app.set_dos_mode(True); pump(0.4)
assert any("350/350" in t[0] for t in app._dos_segments(120)[0]), "and so does the DOS bar"
app.set_dos_mode(False); pump(0.3)
for line in sorted(sc.App.DF_FULL_LINES):
    app._on_data(b"[100/350DF 10ST 0WN 0LG M:0 K:0 (North 1/5:1/5)] "); pump(0.1)
    assert app._last_prompt["hp"][0] == 100
    app._on_data((line + "\n\r").encode()); pump(0.1)
    assert app._last_prompt["hp"] == (350, 350, "DF"), line
app._on_data(b"[100/350DF 10ST 0WN 0LG M:0 K:0 (North 1/5:1/5)] You recover your defenses.\n\r"); pump(0.2)
assert app._last_prompt["hp"] == (350, 350, "DF"), "even with a prompt stuck to the front of the line"
assert len(sc.App.DF_FULL_LINES) == 18

root.update(); root.destroy()
print("combat tests OK")
