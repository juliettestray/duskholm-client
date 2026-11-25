"""A line the game leaves without its line break (a received tell, say) is captured once it has been quiet for a moment,
not only when the next thing arrives or you press Enter; prompts are left alone (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1250x720+20+20")
CR = chr(13) + chr(10)
sent = []
app.conn = type("C", (), {"gen": 0, "send": lambda self, b: sent.append(b) or True, "close": lambda *a: None})()
app.connected = True


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def feed(text, wait=0.0):
    app._on_data(text.encode()); pump(wait)


def type_main(text):
    app.input.focus_force()
    app.input.delete(0, "end"); app.input.insert(0, text)
    app.input.event_generate("<Return>"); pump(0.3)


def pane(key):
    p = app._panes.get(key)
    return [l for l in p["text"].get("1.0", "end").split(chr(10)) if l] if p else []


def screen():
    lines = [l for l in app.out.get("1.0", "end-1c").split(chr(10)) if not l.startswith("[Captured lines")]
    if lines and lines[-1] == "":
        lines.pop()                                    # (the row after the last line break is not a line of text)
    return lines


assert 0.1 < sc.PARTIAL_FINISH_MS / 1000 < 1.0
pump(0.5)
for _n in ('Tells', 'Mara', 'Auth', 'Stat'):
    app.pane_ensure(_n)                                    # (so the client's one-time note about new panes stays out of the way)
pump(0.3)
app.cfg["triggers"] = [
    {"name": "tell", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0, "actions": [{"type": "route", "pane": "Tells"}]},
    {"name": "mara", "mode": "plain", "pattern": "^Mara says*", "enabled": True, "priority": 0, "actions": [{"type": "route", "pane": "Mara"}]},
    {"name": "auth", "mode": "plain", "pattern": "*Password*", "enabled": True, "priority": 0, "actions": [{"type": "route", "pane": "Auth"}]},
    {"name": "stat", "mode": "plain", "pattern": "*350*", "enabled": True, "priority": 0, "actions": [{"type": "route", "pane": "Stat"}]}]

# a tell with no line break at the end: shown at once, captured after a short quiet, not left waiting for Enter
feed("Goose tells you 'hello'", 0.2)
assert screen()[-1] == "Goose tells you 'hello'", screen()[-2:]
assert pane("tells") == [], "not yet: it might still be arriving"
pump(0.45)
assert pane("tells") == ["Goose tells you 'hello'"], pane("tells")
pump(0.8)
assert pane("tells") == ["Goose tells you 'hello'"], "and only once"
# pressing Enter afterwards puts your command on its own row, and nothing is captured twice
type_main("look")
assert screen()[-2:] == ["Goose tells you 'hello'", "look"], screen()[-3:]
assert pane("tells") == ["Goose tells you 'hello'"]
# the game's next output starts with its own line break: no empty row appears
feed("Goose tells you 'two'", 0.9)
assert pane("tells")[-1] == "Goose tells you 'two'" and len(pane("tells")) == 2
feed(CR + "Next line." + CR, 0.3)
assert screen()[-3:] == ["look", "Goose tells you 'two'", "Next line."], screen()[-4:]
assert len(pane("tells")) == 2

# a line that does end with its line break is captured at once, and once
feed("Goose tells you 'three'" + CR, 0.1)
assert len(pane("tells")) == 3
pump(0.9)
assert len(pane("tells")) == 3

# a line that stalls part way is shown as one row, captured in two pieces (the game rarely does this)
feed("Mara says 'one two", 0.9)
assert pane("mara") == ["Mara says 'one two"]
feed(" three'" + CR, 0.3)
assert screen()[-1] == "Mara says 'one two three'", screen()[-2:]

# prompts are left alone: a question that ends with a space, and the stat prompt
feed("Password: ", 0.9)
assert pane("auth") == [] and screen()[-1] == "Password: "
type_main("hunter2")
assert screen()[-1] == "Password: hunter2", "what you type goes after the prompt"
feed(CR)
feed("[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] (Sprawled)", 0.9)
assert pane("stat") == [], pane("stat")
type_main("look")
assert screen()[-1].startswith("[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] (Sprawled)") and screen()[-1].endswith("look"), screen()[-1]

# a line still arriving in pieces is never split when the pieces come close together
n = len(pane("tells"))
feed(CR + "Goose tells you 'part", 0.05)
feed(" two'" + CR, 0.5)
assert len(pane("tells")) == n + 1 and pane("tells")[-1] == "Goose tells you 'part two'"

# a hidden world's partial line finishes too, in its own world
second = app.open_new_world("Elsewhere"); pump(0.4)
first = app.sessions[0]
first.q.put((first.conn.gen, "data", ("Zed tells you 'while away'").encode())); pump(1.0)
assert "Zed tells you 'while away'" in first._panes["tells"]["text"].get("1.0", "end"), "captured in the world it belongs to"
app.close_world(second); pump(0.3)

root.update(); root.destroy()
print("idle line tests OK")
