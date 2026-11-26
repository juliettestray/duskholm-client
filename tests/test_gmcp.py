"""GMCP: negotiation, parsing, the /gmcp command and the screen-reader speech."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import gmcp
from sanctuary import Terminal, IAC, WILL, WONT, DO, DONT, SB, SE
import tkinter as tk


def sends(evs):
    return [e[1] for e in evs if e[0] == "send"]


def msg(text):
    return bytes([IAC, SB, 201]) + text.encode("utf-8").replace(b"\xff", b"\xff\xff") + bytes([IAC, SE])


# ---- the byte layer ----
t = Terminal()                                           # off by default: refused, as before
assert sends(t.feed(bytes([IAC, WILL, 201]))) == [bytes([IAC, DONT, 201])] and not t.gmcp_on
t = Terminal(want_gmcp=True)
evs = t.feed(bytes([IAC, WILL, 201]))
s = sends(evs)
assert s[0] == bytes([IAC, DO, 201]) and t.gmcp_on and ("gmcp_on",) in evs
assert s[1].startswith(bytes([IAC, SB, 201]) + b"Core.Supports.Set [") and s[1].endswith(bytes([IAC, SE]))
assert b'"Combat 1"' in s[1] and b'"Char.Skills 1"' in s[1]
assert t.feed(bytes([IAC, WILL, 201])) == [], "a repeated offer is not answered twice"
evs = t.feed(msg('Char.Vitals {"hp":21,"maxhp":25,"wounds":0,"debuff":0,"lag":2}') + b"text\r\n")
assert ("gmcp", "Char.Vitals", {"hp": 21, "maxhp": 25, "wounds": 0, "debuff": 0, "lag": 2}) in evs
assert any(e[0] == "text" and "text" in e[1] for e in evs), "text after a message still shows"
assert not any(e[0] == "text" and "Vitals" in e[1] for e in evs), "the message itself never shows as text"
assert t.gmcp["Char.Vitals"]["hp"] == 21
# an IAC byte inside the message (doubled) and split across reads
data = msg('Comm.Channel.Text {"channel":"ooc","text":"aÿb"}')
t.feed(data[:20]); evs = t.feed(data[20:])
assert any(e[0] == "gmcp" and e[1] == "Comm.Channel.Text" for e in evs)
# a long message (a skill list) is kept whole, not cut at the old limit
big = json.dumps([{"name": "Skill%d" % i, "group": "Skills", "rank": 3} for i in range(400)])
assert len(big) > 4096
evs = t.feed(msg("Char.Skills.List " + big) + b"after\r\n")
assert any(e[0] == "gmcp" and len(e[2]) == 400 for e in evs) and any(e[0] == "text" and "after" in e[1] for e in evs)
# junk is ignored, never raised
for junk in (b"Char.Vitals {not json", b"", b" ", b"X"):
    t.feed(bytes([IAC, SB, 201]) + junk + bytes([IAC, SE]))
t.feed(msg("Core.Ping"))
assert t.gmcp["Core.Ping"] is None
for i in range(200):
    t.feed(msg("Pkg%d 1" % i))
assert len(t.gmcp) <= 64, len(t.gmcp)
assert ("gmcp_off",) in t.feed(bytes([IAC, WONT, 201])) and not t.gmcp_on
assert t.feed(msg("Char.Name {}")) == [], "ignored while off"

# ---- helpers ----
assert gmcp.diff_names(["a", "b"], ["b", "c"]) == (["c"], ["a"])
assert gmcp.offset_words(2, -3, 0) == "3 south, 2 east" and gmcp.offset_words(0, 0) == "here"
scan = {"points": [{"type": "extraction", "x": 12, "y": -3}], "people": [
    {"label": "Me", "name": "Val", "me": True, "x": 0, "y": 0, "z": 0},
    {"label": "Ta", "name": "A tall man", "me": False, "hostile": True, "x": -2, "y": -2, "z": 0, "target": "Val", "action": "fighting"}]}
d = gmcp.describe_scan(scan)
assert d[0] == "A tall man, hostile, 2 south, 2 west, fighting Val" and d[1].startswith("extraction point"), d
assert gmcp.describe_scan(None) == [] and gmcp.describe_scan({"people": 3}) == []
assert gmcp.describe_vitals({"hp": 5, "maxhp": 10, "wounds": 1, "lag": 2}) == "Health 5 of 10, 1 wounds, 2 seconds of lag"

# ---- the client ----
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")


def pump(t=0.2):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


wire = []
app.conn = type("C", (), {"send": lambda self, b: wire.append(b) or True, "close": lambda self, *a: None})()
app.connected = True
spoken = []
app.speech.say_now = lambda text: spoken.append(text)
pump(0.3)
assert app.cfg["gmcp"] is False and app.cfg["gmcp_sr"] is True
assert any(k == "gmcp" for k, *_ in sc.EXTRA_BOOLS)
assert sc.clean_settings({"host": "x", "gmcp": "yes"})["gmcp"] is False

app._local("/gmcp")
assert "GMCP is off" in app.out.get("end-6l", "end")
app._local("/gmcp on"); assert app.cfg["gmcp"] is True
app.term = Terminal(want_mxp=True, want_gmcp=True)       # what the next connect builds
app._on_data(bytes([IAC, WILL, 201]))
assert app.term.gmcp_on and any(w.startswith(bytes([IAC, DO, 201])) for w in wire) and any(b"Core.Supports.Set" in w for w in wire)
app._on_data(msg('Char.Vitals {"hp":25,"maxhp":25,"wounds":0,"debuff":0,"lag":0}')); pump(0.1)
app._local("/gmcp vitals"); assert "Health 25 of 25" in app.out.get("end-4l", "end")
app._local("/gmcp"); assert "Char.Vitals" in app.out.get("end-8l", "end")

# speech is off until screen reader mode is on
app._on_data(msg('Room.Info {"num":1,"name":"a room","exits":{"n":2}}'))
app._on_data(msg('Room.Players [{"name":"Sam"}]'))
app._on_data(msg('Room.Players [{"name":"Sam"},{"name":"Kai"}]')); assert spoken == []
app.set_screen_reader(True); pump(0.3); spoken.clear()
app._on_data(msg('Room.Players [{"name":"Sam"},{"name":"Kai"},{"name":"A tall man"}]'))
assert spoken == ["A tall man arrives"], spoken
spoken.clear()
app._on_data(msg('Room.Players [{"name":"Kai"},{"name":"A tall man"}]')); assert spoken == ["Sam leaves"], spoken
spoken.clear()
app._on_data(msg('Room.Mobs [{"name":"a grey wolf"}]')); assert spoken == [] , "first list for a room is the baseline"
app._on_data(msg('Room.Mobs []')); assert spoken == ["a grey wolf leaves"], spoken
# moving: the new room's lists are not news
spoken.clear()
app._on_data(msg('Room.Info {"num":2,"name":"hall","exits":{"s":1}}'))
app._on_data(msg('Room.Players [{"name":"Zed"}]')); assert spoken == [], spoken
app._on_data(msg('Room.Players []')); assert spoken == ["Zed leaves"], spoken
# health: spoken once per band, and the prompt alert stays quiet for it
spoken.clear()
app._on_data(msg('Char.Vitals {"hp":25,"maxhp":25,"wounds":0,"debuff":0,"lag":0}'))
app._on_data(msg('Char.Vitals {"hp":5,"maxhp":25,"wounds":0,"debuff":0,"lag":0}'))
assert len(spoken) == 1 and spoken[0].startswith("Health 20 percent"), spoken
assert app._gmcp_speaks("Char.Vitals")
spoken.clear()
app._on_data(msg('Char.Status {"fighting":false,"combat":"none","position":"standing"}'))
app._on_data(msg('Char.Status {"fighting":true,"combat":"fast","position":"fighting"}')); assert spoken == ["Fight started"], spoken
# the speech option off: silence
app._local("/gmcp sr off"); spoken.clear()
app._on_data(msg('Room.Players [{"name":"Q"}]')); assert spoken == []
assert not app._gmcp_speaks("Char.Vitals")
# channels are kept for /gmcp channels
app._on_data(msg('Comm.Channel.Text {"channel":"ooc","text":"[OOC] Sam: hi"}'))
app._local("/gmcp channels 5"); assert "[OOC] Sam: hi" in app.out.get("end-4l", "end")
app._on_data(msg("Combat.Scan " + json.dumps(scan)))
app._local("/gmcp scan"); assert "A tall man, hostile" in app.out.get("end-6l", "end")
app._local("/gmcp show char.vitals"); assert '"maxhp": 25' in app.out.get("end-4l", "end")
app._local("/gmcp bogus"); assert "Unknown topic" in app.out.get("end-4l", "end")
# ---- bars and panes from the live data ----
def pane_text(name):
    return app._panes[name.lower()]["text"].get("1.0", "end").strip()


app.term = Terminal(want_mxp=True, want_gmcp=True)
app._on_data(bytes([IAC, WILL, 201])); app.set_screen_reader(False); pump(0.2)
app._on_data(msg('Char.Status {"fighting":false,"combat":"none","position":"standing"}'))
app._on_data(msg('Char.Vitals {"hp":21,"maxhp":25,"wounds":1,"debuff":14,"lag":2}'))
v = app._prompt_view()
assert v["hp"] == (21, 25, "DF") and ("ST", 14) in v["counters"] and ("WN", 1) in v["counters"] and "Standing" in v["text"], v
assert app.statbar.data is v or app.statbar.data == v, "the stat bar shows the live data"
app._on_data(msg('Combat.Status {"facing":"west","x":42,"y":19,"size":50,"attack":3,"move":2,"fatigued":false,"carrier":false,"cover":"a burnt-out car"}'))
v = app._prompt_view(); assert ("K", 3) in v["cooldowns"] and ("M", 2) in v["cooldowns"] and any(t.startswith("W 42/50") for t in v["text"])
app._on_data(msg('Combat.Scan {"operation":{"task":"securing the area","percent":40},"points":[],"people":[]}'))
assert "Securing the area 40%" in app._prompt_view()["text"]
app._on_data(msg('Combat.Scan {"points":[],"people":[]}'))
assert not any("%" in t for t in app._prompt_view()["text"]), "no operation: no percentage"
app.dos and app.set_dos_mode(False)
assert app.statbar.winfo_ismapped() or app.statbar.winfo_manager() == "pack"

app._local("/gmcp layout")
assert app.cfg["gmcp_layout"] == "duskholm"
app._on_data(msg('Room.Info {"num":1,"name":"a master bedroom","area":"Haven Township","exits":{"n":2,"e":3}}'))
app._on_data(msg('Room.Players [{"name":"Sam"}]')); app._on_data(msg('Room.Mobs []')); pump(0.4)
sides = [(r["side"], r["panes"]) for r in app.cfg["layout"]["regions"]]
assert sides == [("right", ["Here"]), ("right", ["Chat", "Phone"])], sides
assert "a master bedroom" in pane_text("Here") and "People: Sam" in pane_text("Here") and "Exits: e n" in pane_text("Here")
app._on_data(msg('Room.Players [{"name":"Sam"},{"name":"Kai"}]')); pump(0.2)
assert "Sam, Kai" in pane_text("Here")
app._on_data(msg('Comm.Channel.Text {"channel":"faction","text":"Your faction comms say push left"}'))
app._on_data(msg('Comm.Channel.Text {"channel":"ooc","text":"[OOC] Sam: hi"}')); pump(0.2)
assert "[faction] Your faction comms say push left" in pane_text("Chat") and "[OOC] Sam: hi" in pane_text("Chat")
app._on_data(msg('Comm.Channel.Text {"channel":"text","text":"[Nov 26 05:36]46: Hello from B"}'))
app._on_data(msg('Comm.Channel.Text {"channel":"text","text":"[Nov 26 05:36]46: Hello from B"}'))
app._on_data(msg('Comm.Channel.Text {"channel":"text","text":"You text 46: Hi B"}')); pump(0.2)
ph = pane_text("Phone").splitlines()
assert ph[0] == "[Nov 26 05:36]46: Hello from B" and len(ph) == 2 and ph[1].endswith("You > 46: Hi B"), ph
# a fight: the layout changes by itself
app._on_data(msg('Char.Status {"fighting":true,"combat":"slow","position":"standing"}')); pump(0.4)
sides = [(r["side"], r["panes"]) for r in app.cfg["layout"]["regions"]]
assert sides == [("right", ["Map"]), ("right", ["Chat", "Phone"]), ("right", ["Damage"]), ("right", ["Allies"]), ("bottom", ["Scan"])], sides
app._on_data(msg("Combat.Scan " + json.dumps({"points": [], "people": [
    {"label": "Me", "name": "Gmcpa", "me": True, "hostile": False, "x": 0, "y": 0, "z": 0, "distance": 1, "carrier": False},
    {"label": "Ma", "name": "A man", "me": False, "hostile": True, "x": -2, "y": -2, "z": 0, "distance": 2, "carrier": False, "target": "Gmcpa", "action": "fighting", "cover": "a car"},
    {"label": "Sa", "name": "Sam", "me": False, "hostile": False, "x": 3, "y": 0, "z": 0, "distance": 3, "carrier": False}]})))
app._on_data(msg('Combat.Map {"facing":"west","rows":["^^////  ","^^//MeMa","^^//  Sa"]}')); pump(0.4)
assert "A man  2S 2W  D2  fighting Gmcpa  behind a car" in pane_text("Scan"), pane_text("Scan")
assert "Sam  3E" in pane_text("Allies") and "A man" not in pane_text("Allies")
assert "^^//MeMa" in pane_text("Map")
assert "You: facing west  behind a burnt-out car" in pane_text("Scan")
# combat type, damage, says and emotes
app._on_data(msg('Combat.Status {"combat":"slow","facing":"west","x":42,"y":19,"size":50,"attack":0,"move":2,"fatigued":false,"carrier":false}'))
assert "Slow combat" in app._prompt_view()["text"]
for d in ('{"dir":"out","target":"A man","attack":"Striking","damage":22,"stagger":10}',
          '{"dir":"in","source":"A man","attack":"Striking","damage":19,"stagger":15}',
          '{"dir":"in","attack":"Carbines","damage":7,"stagger":3}',
          '{"dir":"out","damage":4}', '{"dir":"sideways"}', '5'):
    app._on_data(msg("Combat.Damage " + d))
pump(0.3)
dl = pane_text("Damage").splitlines()
assert dl[0] == "---- new fight ----" or dl[0] == "You > A man  Striking  22  stagger +10", dl
dl = [x for x in dl if not x.startswith("----")]
assert dl == ["You > A man  Striking  22  stagger +10", "A man > you  Striking  19  stagger +15", "Hit you  Carbines  7  stagger +3", "You  4"], dl
app._local("/gmcp damage 2"); assert "Hit you  Carbines" in app.out.get("end-4l", "end") and "You  4" in app.out.get("end-4l", "end")
app._on_data(msg("Comm.Channel.Text " + json.dumps({"channel": "say", "text": 'A man says "Hi back."'})))
app._on_data(msg('Comm.Channel.Text {"channel":"emote","text":"A man nods slowly."}')); pump(0.2)
assert 'A man says "Hi back."' in pane_text("Chat") and "A man nods slowly." in pane_text("Chat")
assert gmcp.damage_line({"dir": "in"}) == [("Hit you", "bad")] and gmcp.damage_line([]) is None
# the main window keeps everything: emotes and combat text are copied to the panes, never taken from the text
for line in ("Gmcpa swings wildly. ", "(You attempt to knock A man out.)", "It is A man's turn to attack.",
             "A man swings wildly. ", "[Your best Striking attack hits. Reducing defenses by 22, increasing stagger by 10]"):
    app._on_data((line + chr(13) + chr(10)).encode())
app._on_data(msg("Comm.Channel.Text " + json.dumps({"channel": "emote", "text": "A man swings wildly."})))
pump(0.3)
main = app.out.get("1.0", "end")
for line in ("Gmcpa swings wildly.", "(You attempt to knock A man out.)", "It is A man's turn to attack.", "A man swings wildly.", "increasing stagger by 10"):
    assert line in main, line
assert "A man swings wildly." in pane_text("Chat"), "and the emote is in the Chat pane as well"
# 'Me' sits in the middle of the Map pane, across and down
mg = {"Combat.Map": {"rows": ["^^////  ", "^^//MeMa", "^^//  Sa"]}, "Combat.Scan": {"people": [{"label": "Me", "me": True}]}}
ml = gmcp.map_lines(mg, 36, 7)
mrow = "".join(t for t, _r in ml[3])
assert mrow.index("Me") + 1 == 18 and len(ml) == 3 + 2, (mrow, len(ml))
assert gmcp.map_lines(mg, 4, 2)[1][0][0].startswith("^^"), "a pane narrower than the map is not padded"
assert gmcp.map_me(mg) == (1, 4) and gmcp.map_me({}) is None
app._on_data(msg('Char.Status {"fighting":false,"combat":"none","position":"standing"}')); pump(0.3)
assert len(app.cfg["layout"]["regions"]) == 5, "it holds the fight layout through a short lull"
sc_hold = gmcp.FIGHT_HOLD_MS; pump(sc_hold / 1000.0 + 0.5)
assert len(app.cfg["layout"]["regions"]) == 2, "and goes back when the fight is over"
# DOS: the same panes, narrower
app.set_dos_mode(True); pump(0.6)
assert app.cfg["layout"]["regions"][0]["size"] == 30
app.set_dos_mode(False); pump(0.4)
assert app.cfg["layout"]["regions"][0]["size"] == 36
app._local("/gmcp layout off"); pump(0.3)
assert app.cfg["gmcp_layout"] == "off" and "Here" not in [n for r in app.cfg["layout"]["regions"] for n in r["panes"]]
# not connected with GMCP: a helpful line, not a crash
app.term = Terminal(want_mxp=True)
app._local("/gmcp vitals"); assert "not sending GMCP" in app.out.get("end-3l", "end")
root.destroy()
print("gmcp tests OK")
