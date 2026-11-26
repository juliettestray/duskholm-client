"""A game prompt stuck to the front of a line (the HP bar, then the text) is not part of the message: rules see the line without it."""
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


def pump(t=0.25):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.005)


sent = []
app.conn = type("C", (), {"send": lambda self, b: sent.append(b) or True, "close": lambda self, *a: None})()
pump(0.5)
app.connected = True


def P(k):
    return "[510/510DF 0ST 0WN 0LG M:0 K:%d (Nw 31/50:45/50)] " % k


def feed(s):
    app._on_data(s.encode()); pump()


def typed(text):
    app.input.delete(0, "end"); app.input.insert(0, text); app._on_enter(None); pump(0.3)


def pane(key="channels"):
    p = app._panes.get(key)
    return [l for l in p["text"].get("1.0", "end").split(chr(10)) if l] if p else []


def fresh(*rules):
    for k, p in list(app._panes.items()):
        app.pane_clear(k)
    app.cfg["triggers"] = list(rules)
    app.clear(); pump(0.2)


def route(pattern="^[OOC]*", pane="Channels", **extra):
    return {"name": "r", "mode": "plain", "pattern": pattern, "enabled": True, "priority": 0,
            "actions": [dict({"type": "route", "pane": pane}, **extra)]}


assert app.cfg["hide_prompt"] is False, "the prompt is shown (the case that failed)"

# ---- captured, wherever the game put the line relative to the prompt
fresh(route())
feed(P(41)); feed(CR + "[OOC] Dizzy: 'own line'" + CR)
feed(P(41)); typed("ooc glass dog"); feed("[OOC] Kitten: 'glass dog'" + CR + P(38))          # the game answers right after your command
feed(P(26)); feed("[OOC] Kitten: 'stuck to the prompt'" + CR)
feed(P(41) + "[OOC] Kitten: 'same burst'" + CR)
feed(P(20)); feed("[OOC] Kitten: 'before the echo'" + CR); typed("ooc x"); feed(P(19))
assert pane() == ["[OOC] Dizzy: 'own line'", "[OOC] Kitten: 'glass dog'", "[OOC] Kitten: 'stuck to the prompt'",
                  "[OOC] Kitten: 'same burst'", "[OOC] Kitten: 'before the echo'"], pane()
assert all("510/510" not in l for l in pane()), "the HP bar is not in the pane"
shown = app.out.get("1.0", "end")
assert "510/510DF" in shown and "[OOC] Kitten: 'stuck to the prompt'" in shown, "the main window still shows the whole line"

# ---- a highlight colours the message, not the prompt in front of it
def fg_at(text, offset=0):
    idx = app.out.search(text, "1.0")
    assert idx, text
    names = [n for n in app.out.tag_names("%s+%dc" % (idx, offset)) if n.startswith("s") and "|" in n]
    return app.out.tag_cget(names[0], "foreground").lower() if names else None


fresh({"name": "h", "mode": "plain", "pattern": "^[OOC]*", "enabled": True, "priority": 0,
       "actions": [{"type": "highlight", "fg": 14, "scope": "line"}]})
feed(P(41) + "[OOC] Kitten: 'colour me'" + CR)         # (in one burst: a prompt that was already drawn alone is never recoloured)
cy = app.theme["ansi"][14]
assert fg_at("[OOC] Kitten: 'colour me'") in (cy, sc.ensure_contrast(cy, app.theme["bg"], app.theme["min_contrast"]))
assert fg_at("510/510DF") != fg_at("[OOC] Kitten: 'colour me'"), "the prompt keeps its own colours"

# ---- "hide from the main window" takes the message away and leaves the HP bar
fresh(route(gag=True))
feed(P(41) + "[OOC] Kitten: 'hidden'" + CR + P(40))
assert pane() == ["[OOC] Kitten: 'hidden'"], pane()
main = app.out.get("1.0", "end")
assert "hidden" not in main and "510/510DF" in main, main

# ---- a rule that is about the prompt itself still works (when nothing matches without it)
fresh({"name": "n", "mode": "plain", "pattern": "*Nw 31*", "enabled": True, "priority": 0,
       "actions": [{"type": "note", "text": "prompt rule saw it"}]})
feed(P(41) + "You hear a distant bell." + CR)
assert "prompt rule saw it" in app.out.get("1.0", "end"), "the whole line is still tried"
fresh({"name": "n", "mode": "plain", "pattern": "*Nw 31*", "enabled": True, "priority": 0,
       "actions": [{"type": "note", "text": "prompt only"}]})
feed(P(41) + CR)
assert "prompt only" in app.out.get("1.0", "end"), "a line that is only a prompt is matched as it always was"

# ---- both: a message rule wins on the trimmed line, and does not run twice
fresh(route(), {"name": "x", "mode": "plain", "pattern": "*Kitten*", "enabled": True, "priority": 0,
                "actions": [{"type": "note", "text": "hello Kitten"}]})
feed(P(41) + "[OOC] Kitten: 'once'" + CR)
assert pane() == ["[OOC] Kitten: 'once'"] and app.out.get("1.0", "end").count("hello Kitten") == 1

# ---- route-once (the phone) sees the same, so a text stuck to a prompt is not missed or doubled
once = {"name": "p", "mode": "regex", "ignore_case": False, "priority": 0, "enabled": True,
        "pattern": "^\[[A-Z][a-z]{2} [ 0-9][0-9] [0-9]{2}:[0-9]{2}\]",
        "actions": [{"type": "route", "pane": "Phone", "once": True}]}
fresh(once)
T1 = "[Nov 25 02:46]7108390: catherine says u are going australia???????"
feed(P(41) + T1 + CR); pump(0.8)
feed(P(41) + T1 + CR); pump(0.8)
assert pane("phone") == [T1], pane("phone")
root.update(); root.destroy()
print("glued prompt tests OK")
