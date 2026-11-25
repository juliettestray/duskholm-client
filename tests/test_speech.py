"""What gets said for a screen reader: cleaning, prompt sentences, flood control, review (no sound)."""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import speech as sp

C = sp.clean_for_speech
assert C("| Permanent Karma    Hours: 2378 |") == "Permanent Karma Hours: 2378"
assert C(",______________________________________,") == "" and C("┌───┐") == "" and C("-----") == ""
assert C("so... fun") == "so... fun" and C("well -- ok") == "well -- ok", "ordinary punctuation is left alone"
assert C("see https://example.com/a/b?x=1 now") == "see link example.com now"
assert C("`196Hel`208lo`x") == "Hello" and C("\x1b[31mred\x1b[0m") == "red"
assert C("fire \U0001F525") == "fire fire" and C("heart ❤️") == "heart heavy black heart"
assert C("a\x07b\x00c") == "a b c" and C("   ") == "" and C("") == "" and C(None) == "" and C(5) == ""
assert len(C("x" * 5000)) == sp.MAX_SPOKEN and C("[OOC] Bob: 'hi'") == "[OOC] Bob: 'hi'"

P = {"hp": (350, 350, "DF"), "gauges": [("DF", 350, 350)], "counters": [("ST", 80), ("WN", 1), ("LG", 0)],
     "cooldowns": [("M", 3), ("K", 0)], "text": ["North 1/5:1/5"]}
d = sp.describe_prompt(P)
assert d == "def 350 of 350 (100 percent). stun 80. wounds 1. LG 0. move timer 3 seconds. attack timer ready. North 1/5:1/5.", d
assert sp.describe_prompt(None) == "No stats yet." and sp.describe_prompt({}) == "No stats yet." and sp.describe_prompt({"counters": []}) == "."
assert "move timer 1 second." in sp.describe_prompt({"cooldowns": [("M", 1)]})
assert sp.describe_prompt({"hp": (5, 0, "X")}) == "X 5 of 0."
assert sp.describe_interval(P) == "def 350 of 350. stun 80."
assert sp.describe_interval({"hp": (7, 0, "DF")}) == "def 7." and sp.describe_interval(None) == "" and sp.describe_interval({}) == ""
assert sp.describe_interval({"counters": [("WN", 2)]}) == "", "only def and stun are read at intervals"


class Clock:
    t = 100.0
    def __call__(self):
        return self.t


clk, fake = Clock(), sp.FakeBackend()
s = sp.Speech(fake, clock=clk)
assert s.say("You hit Bob.") and fake.said == ["You hit Bob."]
assert not s.say("You hit Bob."), "the same line twice in a row is read once"
clk.t += 3
assert s.say("You hit Bob."), "...but again a little later"
assert s.say("[x]", prefix="OOC") is True and fake.said[-1] == "OOC: [x]"
assert not s.say("") and not s.say("-----")
assert list(s.history)[-1] == "OOC: [x]" and s.review is None
# muted: remembered, never spoken
s.muted = True; n = len(fake.said)
assert not s.say("quiet line") and len(fake.said) == n and s.history[-1] == "quiet line"
assert not s.say_now("urgent"), "mute silences everything"
s.muted = False
# flood control: the rest are skipped and counted
clk.t += 10; fake.said.clear()
for i in range(40):
    s.say("line %d" % i)
assert len(fake.said) == s.flood_lines
clk.t += 5
s.say("after the flood")
assert fake.said[-2] == "28 lines skipped." and fake.said[-1] == "after the flood", fake.said[-3:]
clk.t += 5; fake.said.clear()
for i in range(30):
    s.say("urgent %d" % i, interrupt=True)
assert len(fake.said) == 30, "interrupting lines are never skipped"
# note() records without speaking
before = len(fake.said)
assert s.note("silenced line", "Tells") == "Tells: silenced line" and len(fake.said) == before and s.history[-1] == "Tells: silenced line"
assert s.note("-----") == ""
# review
r = sp.Speech(sp.FakeBackend())
assert r.review_step(-1) == ("", "empty")
for w in ("one", "two", "three"):
    r.note(w)
assert r.review_step(-1) == ("three", "") and r.review_step(-1) == ("two", "") and r.review_step(-1) == ("one", "")
assert r.review_step(-1) == ("one", "top") and r.review_step(+1) == ("two", "")
assert r.review_step(+1) == ("three", "") and r.review_step(+1) == ("three", "bottom")
r.note("four"); assert r.review is None and r.review_step(-1) == ("four", ""), "a new line resets the cursor to live"
assert r.last(2) == ["three", "four"]
big = sp.Speech(sp.FakeBackend())
for i in range(sp.HISTORY + 50):
    big.note("l%d" % i)
assert len(big.history) == sp.HISTORY and big.history[0] == "l50"

# backends: choosing and failing safely
b, msg = sp.make_backend("off"); assert isinstance(b, sp.NullBackend) and "off" in msg
b, msg = sp.make_backend("nonsense", 0)
assert b.name in ("nvda", "windows", "off"), b.name
b.close()
fb = sp.FakeBackend(); s2 = sp.Speech(fb); s2.stop(); s2.set_backend(sp.NullBackend())
assert ("stop",) in fb.events and ("close",) in fb.events
try:
    jb = sp.JAWSBackend()
    jb.close()
except OSError as e:
    assert "JAWS" in str(e) and "pywin32" not in str(e), "no JAWS here: a plain message, never 'needs pywin32'"
sp.NullBackend().speak("x"); sp.NullBackend().stop()

# fuzz: never raises, never returns control characters
rnd = random.Random(5)
alpha = "ab |-_=*#.,'`\\/─█\U0001F600\x1b[0m\n\t\x07é http://x.y/z"
for _ in range(5000):
    t = "".join(rnd.choice(alpha) for _ in range(rnd.randint(0, 60)))
    out = C(t)
    assert len(out) <= sp.MAX_SPOKEN and all(ord(c) >= 32 and ord(c) != 127 for c in out), repr(out)
# the Windows voice helper starts and stays up (nothing is spoken: only control lines are sent)
if sys.platform.startswith("win"):
    import time
    wb = sp.WindowsVoiceBackend(0)
    wb.stop(); wb.set_rate(2); wb.stop()
    time.sleep(3.5)
    assert wb._proc is not None and wb._proc.poll() is None, "the helper is running"
    wb.close(); time.sleep(1.5)
    assert wb._proc.poll() is not None, "and it ends when closed"
print("speech tests OK")
