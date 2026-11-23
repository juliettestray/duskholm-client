"""Stat bar (prompt parsing + widget) and font selection. Local only."""
import json, os, socket, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as dc
import tkinter as tk
import tkinter.font as tkfont

# ---------------- prompt parser ----------------------------------------------------------
p = dc.parse_prompt("[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] ")
assert p == {"hp": (350, 350, "DF"), "counters": [("ST", 0), ("WN", 0), ("LG", 0)],
             "cooldowns": [("M", 0), ("K", 0)], "facing": "", "tags": []}, p

p = dc.parse_prompt("[120/350DF 2ST 1WN 3LG M:4 K:0 (North 3/5:2/5)] (Sprawled) [Fatigued] (Carrier)")
assert p["hp"] == (120, 350, "DF") and p["facing"] == "North 3/5:2/5", p
assert p["cooldowns"] == [("M", 4), ("K", 0)]
assert p["tags"] == ["Sprawled", "Fatigued", "Carrier"], p["tags"]

assert dc.parse_prompt("(W1) (I2) [10/20DF 0ST 0WN 0LG M:0 K:0 ( )]")["hp"] == (10, 20, "DF")
# two prompts on one line: the last one wins
assert dc.parse_prompt("[1/9DF M:0] [5/9DF M:2]")["hp"][0] == 5
# a prompt with fewer fields still works
q = dc.parse_prompt("[7/7DF]")
assert q["hp"] == (7, 7, "DF") and q["counters"] == [] and q["cooldowns"] == []

# things that are NOT prompts
for junk in ("[Enter] to continue", "[1] First option", "Players online [3/4]", "[x/y]",
             "[999999999999/1DF]", "", "[", "hello", "[3/4DF M:x]"):
    assert dc.parse_prompt(junk) is None, junk

# hostile lines must be fast (no regex blow-up)
t0 = time.time()
for bad in ("[1/1A" + " 1A" * 20000, "[1/1A" + " M:1" * 20000, "[1/1A" + " " * 50000,
            "[1" * 30000, "[1/1A (" + "(" * 50000, "[1/1A]" + "x" * 100000):
    dc.parse_prompt(bad)
assert time.time() - t0 < 2.0, time.time() - t0

# HP colours follow the game's %d bands (80/60/40/20)
C = dc.ANSI16
assert dc.hp_color(350, 350) == C[2] and dc.hp_color(280, 350) == C[2]
assert dc.hp_color(279, 350) == C[3] and dc.hp_color(210, 350) == C[3]
assert dc.hp_color(209, 350) == C[11] and dc.hp_color(140, 350) == C[11]
assert dc.hp_color(139, 350) == C[1] and dc.hp_color(70, 350) == C[1]
assert dc.hp_color(69, 350) == C[9] and dc.hp_color(-5, 350) == C[9] and dc.hp_color(1, 0) == C[2]

# ---------------- settings ----------------------------------------------------------------
c = dc.clean_settings({"font_family": 12, "font_size": 9999, "statbar": "no"})
assert c["font_family"] is None and c["font_size"] == dc.MAX_FONT and c["statbar"] is True
assert dc.clean_settings({"font_size": 1})["font_size"] == dc.MIN_FONT
assert dc.clean_settings({"font_family": "  Consolas "})["font_family"] == "Consolas"

# ---------------- GUI ----------------------------------------------------------------------
tmp = tempfile.mkdtemp()
dc.SETTINGS_PATH = os.path.join(tmp, "settings.json")
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
port = srv.getsockname()[1]
box = []
def serve():
    c_, _ = srv.accept(); box.append(c_)
threading.Thread(target=serve, daemon=True).start()

root = tk.Tk()
app = dc.App(root)
app.v_host.set("127.0.0.1"); app.v_port.set(str(port)); app.v_tls.set(False)

def pump(secs, until=None):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)
        if until and until(): return True
    return bool(until and until())

app.toggle_connection()
assert pump(3, lambda: app.connected and box)
assert not app.statbar.winfo_ismapped(), "no bar before the first prompt"

# first prompt, coloured the way the game does it
box[0].sendall(b"Welcome\n\r\x1b[1;32m[350/350DF 0ST 0WN 0LG M:0 K:0 ( )]\x1b[0m ")
assert pump(2, lambda: app.statbar.winfo_ismapped())
assert app.statbar.data["hp"] == (350, 350, "DF")
texts = [t for t, _ in app.statbar.specs()]
assert texts == ["ST 0", "WN 0", "LG 0", "M:0", "K:0"], texts
cols = dict(app.statbar.specs())
assert cols["M:0"] == dc.ANSI16[10], "ready cooldown is green"

# next prompt arrives split across two reads, mid-number
box[0].sendall(b"\n\rYou are hit.\n\r[2")
pump(0.3)
assert app.statbar.data["hp"] == (350, 350, "DF"), "a partial prompt must not change the bar"
box[0].sendall(b"00/350DF 1ST 2WN 0LG M:3 K:2 (North 1/5:1/5)] (Sprawled) ")
assert pump(2, lambda: app.statbar.data["hp"][0] == 200)
specs = dict(app.statbar.specs())
assert specs["M:3"] == dc.ANSI16[9] and specs["K:2"] == dc.ANSI16[9], "cooling down is red"
assert "North 1/5:1/5" in specs and "Sprawled" in specs and specs["ST 1"] == dc.ALERT_FG

# the prompt text itself is still in the scrollback
assert "[200/350DF 1ST 2WN 0LG M:3 K:2" in app.out.get("1.0", "end-1c")

# menu toggle hides / shows
app.v_statbar.set(False); app._statbar_toggled()
assert not app.statbar.winfo_ismapped() and app.cfg["statbar"] is False
app.v_statbar.set(True); app._statbar_toggled(); root.update()
assert app.statbar.winfo_ismapped()

# password mask stuck on (server never sends WONT ECHO after account creation): a real game
# prompt lifts it, ordinary text does not
box[0].sendall(bytes([255, 251, 1]) + b"\n\rPlease retype password: ")
assert pump(2, lambda: app.term.echo_off) and app.input.cget("show") == "*"
box[0].sendall(b"\n\rAccount created, type 'create'.\n\r")
pump(0.4)
assert app.term.echo_off and app.input.cget("show") == "*", "plain text must not lift the mask"
box[0].sendall(b"\n\r[1/1] Not a prompt line without a label ")
pump(0.4)
assert app.term.echo_off, "a non-prompt bracket line must not lift the mask"
box[0].sendall(b"\n\rYou are in the world.\n\r[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] ")
assert pump(2, lambda: not app.term.echo_off) and app.input.cget("show") == ""

# disconnect hides it and forgets the stats
box[0].close()
assert pump(3, lambda: not app.connected)
assert not app.statbar.winfo_ismapped() and app._last_prompt is None

# ---------------- fonts --------------------------------------------------------------------
mono = app.mono_families()
assert mono and app.font_family in mono
fams = set(tkfont.families())
assert all(app._is_mono(f) for f in mono)
for prop in ("Arial", "Times New Roman", "Segoe UI", "Calibri"):
    if prop in fams:
        assert prop not in mono, prop + " is proportional and must not be offered"
assert not app.apply_font("Arial", 14) or "Arial" in mono, "non-monospace family must be refused"
other = next((f for f in mono if f != app.font_family), mono[0])
assert app.apply_font(other, 17)
assert app.f_norm.actual("family") == other or app.f_norm.cget("family") == other
assert app.f_norm.cget("size") == 17 and app.f_bold.cget("size") == 17
assert app.out.cget("font") and app.input.cget("font")
assert app.apply_font(size=999) and app.cfg["font_size"] == dc.MAX_FONT
assert app.apply_font(size=-3) and app.cfg["font_size"] == dc.MIN_FONT
app.apply_font(size=14)
saved = json.load(open(dc.SETTINGS_PATH))
assert saved["font_family"] == other and saved["font_size"] == 14, saved
app._zoom(+1); app._zoom(+1)
assert app.cfg["font_size"] == 16 and app.f_norm.cget("size") == 16

# dialog: lists only monospace fonts, OK applies the selection
top = app.choose_font(); root.update()
def walk(w):
    yield w
    for ch in w.winfo_children():
        yield from walk(ch)
lb = next(w for w in walk(top) if isinstance(w, tk.Listbox))
assert list(lb.get(0, "end")) == mono
target = mono[-1]
lb.selection_clear(0, "end"); lb.selection_set(mono.index(target)); lb.event_generate("<<ListboxSelect>>")
sp = next(w for w in walk(top) if isinstance(w, tk.Spinbox))
sp.delete(0, "end"); sp.insert(0, "19")
next(w for w in walk(top) if isinstance(w, tk.Button) and w.cget("text") == "OK").invoke(); root.update()
assert app.font_family == target and app.cfg["font_size"] == 19, app.cfg
# Cancel changes nothing
top = app.choose_font(); root.update()
next(w for w in walk(top) if isinstance(w, tk.Button) and w.cget("text") == "Cancel").invoke(); root.update()
assert app.font_family == target and app.cfg["font_size"] == 19
root.update(); root.destroy()

# a saved font that is not monospace (hand-edited file) falls back to the default
json.dump({"font_family": "Arial" if "Arial" in fams else "No Such Font", "font_size": 12},
          open(dc.SETTINGS_PATH, "w"))
root2 = tk.Tk(); app2 = dc.App(root2)
assert app2.font_family == app2._default_family() and app2.f_norm.cget("size") == 12
root2.update(); root2.destroy()
# layout regression: a big font in a modest window must never push the input line or the
# stat bar off the bottom (the output pane used to request 24 rows and squeeze them out)
json.dump({"font_size": dc.MAX_FONT}, open(dc.SETTINGS_PATH, "w"))
root3 = tk.Tk(); app3 = dc.App(root3); root3.geometry("800x420+40+40")
app3._on_data(b"hello\n\r[204/350DF 1ST 2WN 0LG M:3 K:0 ( )] ")
for _ in range(40):
    root3.update(); time.sleep(0.02)
H = root3.winfo_height()
assert app3.statbar.winfo_ismapped()
assert app3.input.winfo_y() + app3.input.winfo_height() <= H + 1, (app3.input.winfo_y(), H)
assert app3.statbar.winfo_y() + app3.statbar.winfo_height() <= app3.input.winfo_y() + 1
assert app3.input.winfo_height() > 5 and app3.out.winfo_height() > 5
root3.update(); root3.destroy()
print("statbar + font tests OK")
