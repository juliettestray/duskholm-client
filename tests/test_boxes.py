"""Joining ASCII boxes: length-preserving, only real boxes, fuzzed (no GUI for the pure part)."""
import os, random, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import boxes

TOP = "," + "_" * 20 + ","
assert boxes.connect_line(TOP) == "┌" + "─" * 20 + "┐"
assert boxes.connect_line("|" + "_" * 20 + "|") == "└" + "─" * 20 + "┘"
assert boxes.connect_line("| Hours: 2378 |") == "│ Hours: 2378 │"
assert boxes.connect_line("|  .-----.  |") == "│  ┌─────┐  │"
assert boxes.connect_line("|  '-----'  |") == "│  └─────┘  │"
assert boxes.connect_line(".-----.-----.") == "┌─────┬─────┐"
assert boxes.connect_line("|--------|") == "├" + "─" * 8 + "┤"
for plain in ("a well-known | pipe", "so - what", "'quoted' text", "-----", "| only one start", "end only |",
              "[350/350DF 0ST M:0 K:0 ( )] ", "", "|", "||", "|a|b"):
    assert boxes.connect_line(plain) == plain or plain == "|a|b", plain
assert boxes.connect_text("x\r\n| a |\r\ny") == "x\r\n│ a │\r\ny"
# pieces keep their colours and columns
P = [("| ", "g"), ("Hours", "c"), (": 5 |", "g"), ("\n", None)]
Q = boxes.connect_pieces(P)
assert [t for _x, t in Q] == [t for _x, t in P] and "".join(x for x, _ in Q) == "│ Hours: 5 │\n"
assert boxes.connect_pieces([("| hi |", "echo")], skip_tags=("echo",)) == [("| hi |", "echo")]
assert boxes.connect_pieces(None) is None and boxes.connect_pieces([]) == []
# fuzz: never changes length, never raises, idempotent
rnd = random.Random(7)
alpha = "|-_.,'` abcé│"
for _ in range(20000):
    s = "".join(rnd.choice(alpha) for _ in range(rnd.randint(0, 40)))
    o = boxes.connect_line(s)
    assert len(o) == len(s), (s, o)
    assert boxes.connect_line(o) == o, (s, o)
assert boxes.connect_line("|" + "-" * 10000 + "|") is not None
for bad in (None, 5, b"x"):
    assert boxes.connect_text(bad) == bad

import sanctuary as sc
import tkinter as tk
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk(); app = sc.App(root); root.geometry("1000x600+20+20")
def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)
app.connected = True
app._on_data(b"\x1b[32m,____,\x1b[0m\n\r\x1b[32m| \x1b[36mHi\x1b[32m |\x1b[0m\n\r"); pump(0.3)
assert ",____," in app.out.get("1.0", "end"), "off by default"
app._set_extra("connect_boxes", True)
app._on_data(b"\x1b[32m,____,\x1b[0m\n\r\x1b[32m| \x1b[36mHi\x1b[32m |\x1b[0m\n\r"); pump(0.3)
t = app.out.get("1.0", "end")
assert "┌────┐" in t and "│ Hi │" in t
i = app.out.search("Hi", "end", backwards=True)
assert i and any(n.startswith("s") for n in app.out.tag_names(i)), "colours survive"
root.update(); root.destroy()
print("box tests OK")
