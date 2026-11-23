"""Which fighting lines are about you (pure), and the screen reader manager for them (end to end)."""
import os, random, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import combatfilter as cf

D = cf.clean_settings(None)
cl = lambda line, **kw: cf.classify(line, kw.pop("cfg", D), kw.pop("me", "Ywellia"), kw.pop("in_fight", True))
assert cl("Bob hits the goblin.") == "pn" and cl("The goblin hits Bob.") == "np"
assert cl("The goblin hits the dog.") == "nn" and cl("Bob hits Alice.") == "pp"
assert cl("The goblin staggers.") == "nn" and cl("Bob staggers.") == "pp"
assert cl("A tall man hits Bob.") == "np" and cl("Sir Bob the Bold hits the goblin.") == "nn", "several capitalised words: an NPC"
assert cl("(The goblin knocks Bob out.)") == "np"
# about you, chat, scenery and non-fight lines are left alone
for keep in ("You hit the goblin.", "The goblin hits you.", "Your shield pulses.", "The goblin hits Ywellia.", "Bob hits ywellia.",
             "Bob says, 'the goblin hits hard'", "[OOC] Bob: 'he hits'", "Bob tells you 'x'", "The goblin is here.", "Bob waves.",
             "", "   ", "Hits the goblin.", "x" * 500):
    assert cl(keep) is None, keep
assert cl("Bob hits the goblin.", in_fight=False) is None, "only while a fight is on"
assert cl("Bob hits the goblin.", cfg=cf.clean_settings({"only_in_fight": False}), in_fight=False) == "pn"
# the person can correct the guess
c = cf.clean_settings({"players": ["Sir Bob the Bold"], "npcs": ["Bob"], "always": ["Bonnie"]})
assert cl("Sir Bob the Bold hits the goblin.", cfg=c) == "pn" and cl("Bob hits the goblin.", cfg=c) == "nn"
assert cl("Bonnie hits the goblin.", cfg=c) is None and cl("the goblin hits Bonnie", cfg=c) is None
assert cl("Sir Bob hits the goblin.", cfg=cf.clean_settings({"multiword_npc": False})) == "pn"
# skipping
sk = cf.clean_settings({"skip": {"pn": True}})
assert cf.should_skip("Bob hits the goblin.", sk, "Y") and not cf.should_skip("The goblin hits Bob.", sk, "Y")
assert not cf.should_skip("Bob hits the goblin.", D, "Y"), "nothing is skipped by default"
assert not cf.should_skip("You hit the goblin.", cf.clean_settings({"skip": {c: True for c in cf.CATEGORIES}}), "Y")
# settings
assert cf.clean_settings("x") == D and cf.clean_settings({"skip": {"zz": True, "pn": "yes"}}) == D
assert cf.clean_settings({"players": ["a", "A", "", 5, "b" * 99]})["players"] == ["a", "b" * 40]
assert cf.parse_names("Bob, Sir Alan; the guard\n ,") == ["Bob", "Sir Alan", "the guard"] and cf.parse_names(None) == []
rnd = random.Random(2)
for _ in range(4000):
    line = "".join(rnd.choice("ab Bob the hits you'()[],.!\"é") for _ in range(rnd.randint(0, 60)))
    assert cl(line) in (None, "pn", "nn", "np", "pp")

# ---- in the client
import sanctuary as sc
import speech
import tkinter as tk
home = tempfile.mkdtemp()
os.environ["USERPROFILE"] = os.environ["HOME"] = home
sc.SETTINGS_PATH = os.path.join(home, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
speech.make_backend = lambda choice="auto", rate=0: (speech.FakeBackend(), "test voice")
root = tk.Tk(); app = sc.App(root); root.geometry("1100x650+20+20")


def pump(t=0.25):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def feed(*lines):
    for l in lines:
        app._on_data((l + "\n\r").encode())
    pump(0.2)


app.connected = True
app.cfg["char_name"] = "Ywellia"
app._set_extra("screen_reader", True); pump(0.3)
fb = app.speech.backend; fb.said.clear()
app._on_data(b"[350/350DF 0ST 0WN 0LG M:0 K:0 (North 1/5:1/5)] "); pump(0.3)      # a fight is on
feed("Bob hits the goblin.", "The goblin hits Bob.")
assert fb.said == ["Bob hits the goblin.", "The goblin hits Bob."], "nothing is skipped until you say so"
app._local("/sr combat pn np"); pump(0.2)
assert app.cfg["sr_combat"]["skip"] == {"pn": True, "nn": False, "np": True, "pp": False}
fb.said.clear()
feed("Bob hits the goblin.", "The goblin hits Bob.", "The goblin hits the dog.", "The goblin hits you.", "Bob says, 'hello'")
assert fb.said == ["The goblin hits the dog.", "The goblin hits you.", "Bob says, 'hello'"], fb.said
assert "Bob hits the goblin." in list(app.speech.history), "skipped lines can still be reviewed"
assert "Bob hits the goblin." in app.out.get("1.0", "end"), "and are still on screen"
app._on_data(b"[350/350DF 0ST 0WN 0LG M:0 K:0 ()] "); pump(0.3)                    # no longer fighting
fb.said.clear(); feed("Bob hits the goblin.")
assert fb.said == ["Bob hits the goblin."], "outside a fight nothing is skipped"
app._on_data(b"[350/350DF 0ST 0WN 0LG M:0 K:0 (North 1/5:1/5)] "); pump(0.3)
app._local("/sr combat all"); assert all(app.cfg["sr_combat"]["skip"].values())
app._local("/sr combat none"); assert not any(app.cfg["sr_combat"]["skip"].values())
app._local("/sr combat bogus")
top = app.open_combat_filter(); pump(0.3); assert top.winfo_exists(); top.destroy()
app.set_dos_mode(False)
c2 = sc.clean_settings({"host": "x", "sr_combat": {"skip": {"pn": True}, "players": ["Bob"]}})
assert c2["sr_combat"]["skip"]["pn"] is True and c2["sr_combat"]["players"] == ["Bob"]
assert sc.clean_settings({"host": "x", "sr_combat": 5})["sr_combat"] == D
root.update(); root.destroy()
print("combat filter tests OK")
