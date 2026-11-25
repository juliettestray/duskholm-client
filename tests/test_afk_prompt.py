"""The game's AFK prompt ('[AFK] ', no line break after it) must not glue lines together or leak into captured lines (no network)."""
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


def feed(text, wait=0.5):
    app._on_data(text.encode()); pump(wait)


def type_main(text):
    app.input.focus_force()
    app.input.delete(0, "end"); app.input.insert(0, text)
    app.input.event_generate("<Return>"); pump(0.3)


def pane(key):
    p = app._panes.get(key)
    return [l for l in p["text"].get("1.0", "end").split(chr(10)) if l] if p else []


def screen():
    return [l for l in app.out.get("1.0", "end-1c").split(chr(10)) if not l.startswith("[Captured lines")]


pump(0.5)
app.cfg["triggers"] = [
    {"name": "in", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0, "actions": [{"type": "route", "pane": "Tells"}]},
    {"name": "out", "mode": "plain", "pattern": "^You tell *", "enabled": True, "priority": 0, "actions": [{"type": "route", "pane": "Tells"}]},
    {"name": "hello", "mode": "plain", "pattern": "^Hello*", "enabled": True, "priority": 0, "actions": [{"type": "route", "pane": "Greet"}]},
    {"name": "who", "mode": "plain", "pattern": "*Mara*", "enabled": True, "priority": 0, "actions": [{"type": "route", "pane": "Who"}]}]

# the game's reply to what I typed, as it really arrives: the tell, the prompt, no line break anywhere
feed("Evelyn tells you OOCly 'birb here'[AFK] ")                  # arrives, then silence: the prompt is drawn
assert screen()[-1] == "Evelyn tells you OOCly 'birb here'[AFK] ", screen()[-3:]
type_main("reply very nice")                                       # Enter: the row ends here, and the tell is a line of its own
assert pane("tells") == ["Evelyn tells you OOCly 'birb here'"], pane("tells")
feed("You tell Evelyn OOCly 'very nice'[AFK] ")
assert screen()[-2:] == ["Evelyn tells you OOCly 'birb here'[AFK] reply very nice", "You tell Evelyn OOCly 'very nice'[AFK] "], screen()[-3:]
# the next thing the game says starts with a line break (it was not a reply to a command)
feed(CR + "RP Prompt: What is the most human part of you?" + CR + "[AFK] ")
assert pane("tells") == ["Evelyn tells you OOCly 'birb here'", "You tell Evelyn OOCly 'very nice'"], pane("tells")
assert "RP Prompt: What is the most human part of you?" in screen()

# an empty Enter at the prompt ends its row, and the reply is a line of its own (an anchored rule sees it)
type_main("")
feed("Hello there." + CR)
assert pane("greet") == ["Hello there."], pane("greet")
assert not any("AFK" in l for l in pane("greet"))

# a whole line that ends with the prompt (the line break did come): captured without it, shown as it was
feed("Goose tells you 'hi'[AFK] " + CR + "[AFK] ")
assert pane("tells")[-1] == "Goose tells you 'hi'" and len(pane("tells")) == 3, pane("tells")
assert "Goose tells you 'hi'[AFK] " in screen()

# an [AFK] mark that is not a prompt (no space after it, as in a list of who is here) is kept
feed("Mara Quinn [AFK]" + CR)
assert pane("who")[-1] == "Mara Quinn [AFK]", pane("who")

# a prompt alone never reaches a rule or the screen reader, and the screen still shows it
n = [len(pane(k)) for k in ("tells", "greet", "who")]
feed("[AFK] "); type_main("")
feed("[AFK] "); type_main("")
assert [len(pane(k)) for k in ("tells", "greet", "who")] == n
assert screen().count("[AFK] ") >= 2

# with the commands not echoed there is nothing to end the row, and nothing changes: no crash, lines still complete
app.cfg["show_echo"] = False
feed("[AFK] "); type_main("look")
feed("Mara looks at you." + CR)
assert pane("who")[-1] in ("Mara looks at you.", "[AFK] Mara looks at you."), pane("who")
app.cfg["show_echo"] = True

root.update(); root.destroy()
print("afk prompt tests OK")
