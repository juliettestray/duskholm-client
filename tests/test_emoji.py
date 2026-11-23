"""Emoji shortcodes, both ways, and the toggle (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import emojis
import sanctuary as sc
import tkinter as tk

assert emojis._NAMES and all(k in emojis._FWD for k in emojis._NAMES), "every listed shortcode resolves"
assert emojis.lookup("smile") == "\U0001F604" and emojis.lookup("SMILE") == "\U0001F604"
assert emojis.lookup("rolling_on_the_floor_laughing") == "\U0001F923", "official names work too"
for bad in ("space", "a", "", "x" * 100, "nonsense_name", None, 5, "one two"):
    assert emojis.lookup(bad) is None, bad
assert emojis.expand("hi :smile: and :fire:!") == "hi \U0001F604 and \U0001F525!"
assert emojis.expand("12:30:45 :space: :: :nope:") == "12:30:45 :space: :: :nope:"
assert emojis.expand(None) is None and emojis.expand("plain") == "plain"
assert emojis.shorten("ok \U0001F604\U0001F525 é") == "ok :smile::fire: é"
assert emojis.shorten("heart ❤️") == "heart :heart:", "variation selectors are dropped"
assert emojis.shorten("plain ascii") == "plain ascii"
for n in ("smile", "fire", "heart", "full_moon", "+1"):
    assert emojis.name_of(emojis.lookup(n)) in (n, emojis._REV[emojis.lookup(n)]), n
assert emojis.expand(emojis.shorten("a \U0001F680 b")) == "a \U0001F680 b", "round trip"

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x650+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


sent = []
app.conn = type("C", (), {"send": lambda self, b: sent.append(b) or True, "close": lambda self, *a: None})()
app.connected = True
assert app.cfg["emoji"] is False, "off by default"
app._on_data(b"say :smile: now\n\r"); pump(0.2)
assert ":smile:" in app.out.get("1.0", "end"), "off: text is left alone"
app._set_extra("emoji", True)
app._on_data(b"say :smile: now see https://example.com/x\n\r"); pump(0.2)
txt = app.out.get("1.0", "end")
assert "say \U0001F604 now" in txt, "on: shortcodes become emoji"
i = app.out.search("https://example.com/x", "1.0")
assert i and "link" in app.out.tag_names(i), "links after an emoji are still found"
assert app.out.get(*app.out.tag_ranges("link")[:2]) == "https://example.com/x"
app.send_line("say hi \U0001F525")
assert sent[-1] == b"say hi :fire:\r\n", sent[-1]
app._set_extra("emoji", False)
app.send_line("say hi \U0001F525")
assert sent[-1] == b"say hi \r\n", "off: the game's ASCII rule still drops it"
root.update(); root.destroy()
print("emoji tests OK")
