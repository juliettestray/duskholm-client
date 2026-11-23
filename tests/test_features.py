"""ATDT / fake telnet / saved worlds / prompt profiles / line spacing, end to end (local fake server only)."""
import json, os, socket, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as dc
import dosui, prompts
import tkinter as tk

# ============================== pure helpers ===============================================================
W = [{"name": "Local Test", "host": "127.0.0.1", "port": 3500, "tls": False, "note": "", "last": 0},
     {"name": "Duskholm", "host": "duskholm.com", "port": 3001, "tls": True, "note": "", "last": 0}]
pt = dc.parse_dial_target
assert pt("duskholm.com 3001") == ("duskholm.com", 3001, True, None)
assert pt("duskholm.com:3000") == ("duskholm.com", 3000, False, None)
assert pt("example.org 4000 tls") == ("example.org", 4000, True, None)
assert pt("example.org 3001 plain") == ("example.org", 3001, False, None)
assert pt("example.org") == ("example.org", dc.TLS_PORT, True, None), "no port: the client's usual TLS port"
assert pt("example.org", default_port=23) == ("example.org", 23, False, None), "telnet default port"
assert pt("local test", W) == ("127.0.0.1", 3500, False, "Local Test"), "names with spaces work"
assert pt("LOCAL TEST plain", W)[:3] == ("127.0.0.1", 3500, False)
named = pt("DUSKHOLM", W)
assert named == ("duskholm.com", 3001, True, "Duskholm"), named
assert pt("duskholm plain", W) == ("duskholm.com", 3001, False, "Duskholm")
for bad in ("", "   ", "a b c", "-evil.com 1", ".x 5", "host!name 80", "host 0", "host 65536", "host 1x", "host ٣",
            "bad host.com", "x" * 300, "host:99999", "a:b:c"):
    try:
        pt(bad, W)
    except ValueError as e:
        assert str(e)
    else:
        raise AssertionError("should have rejected %r" % bad)

cw = dc.clean_world
assert cw({"name": "A", "host": "h.com", "port": "80", "tls": 1, "note": "n", "last": 5}) == \
    {"name": "A", "host": "h.com", "port": 80, "tls": True, "note": "n", "last": 5}
for bad in (None, 5, [], {}, {"name": "", "host": "h", "port": 1}, {"name": "x", "host": "bad host", "port": 1},
            {"name": "x", "host": "h", "port": 0}, {"name": "x", "host": "h", "port": True},
            {"name": "x", "host": "h", "port": 70000}, {"name": "x", "host": "-h", "port": 1},
            {"name": 5, "host": "h", "port": 1}, {"name": "x", "host": "h", "port": [1]}):
    assert cw(bad) is None, bad
assert cw({"name": "n\x00\x01ame" + "z" * 100, "host": "h", "port": 5, "note": "\x07" * 5 + "ok" * 100, "last": -5})["last"] == 0
assert len(cw({"name": "z" * 100, "host": "h", "port": 5})["name"]) == 40
assert dc.clean_worlds(None)[0]["name"] == "Duskholm" and dc.clean_worlds("x")[0]["name"] == "Duskholm"
assert dc.clean_worlds([]) == []
many = [{"name": "w%d" % i, "host": "h", "port": 1} for i in range(500)] + ["junk", None]
assert len(dc.clean_worlds(many)) == 200
assert len(dc.clean_worlds([{"name": "Dup", "host": "a", "port": 1}, {"name": "dup", "host": "b", "port": 2}])) == 1

c = dc.clean_settings({"line_spacing": 999, "worlds": "x", "prompt_custom": "no", "prompt_profile": 5})
assert c["line_spacing"] == 12 and c["worlds"][0]["name"] == "Duskholm" and c["prompt_custom"] == []
assert c["prompt_profile"] == prompts.DEFAULT_PRESET
assert dc.clean_settings({"line_spacing": -4})["line_spacing"] == 0
evil = {"name": "Evil", "kind": "regex", "pattern": "(a+)+$", "gauges": [{"label": "HP", "cur": "a"}]}
good = prompts.get_preset("Simple brackets"); good["name"] = "Mine"
cc = dc.clean_settings({"prompt_custom": [evil, good, {"name": "Haven / Duskholm", "kind": "regex"}, 5, None] * 30})
assert [p["name"] for p in cc["prompt_custom"]] == ["Mine"], cc["prompt_custom"]

# ============================== a fake game ===================================================================
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(10)
PORT = srv.getsockname()[1]
conns, received = [], bytearray()
def accept():
    while True:
        try:
            c_, _ = srv.accept()
        except OSError:
            return
        conns.append(c_)
        def rd(c_=c_):
            try:
                while True:
                    d = c_.recv(4096)
                    if not d:
                        return
                    received.extend(d)
            except OSError:
                return
        threading.Thread(target=rd, daemon=True).start()
threading.Thread(target=accept, daemon=True).start()
dead = socket.socket(); dead.bind(("127.0.0.1", 0)); DEAD = dead.getsockname()[1]; dead.close()   # a closed port

tmp = tempfile.mkdtemp()
SETTINGS = os.path.join(tmp, "settings.json")
dc.SETTINGS_PATH = SETTINGS
dc.user_skin_dir = lambda: os.path.join(tmp, "skins")
root = tk.Tk()
root.geometry("1100x760+20+20")
app = dc.App(root)

def pump(secs=0.3):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)

def out():
    return app.out.get("1.0", "end-1c")

def type_line(text, wait=0.35):
    app.input.delete(0, "end"); app.input.insert(0, text); app._on_enter(None); pump(wait)

def key(w, keysym):
    w = getattr(w, "_cv", w)
    w.focus_force(); root.update(); w.event_generate("<Key>", keysym=keysym); pump(0.2)

def overlay():
    return app._overlay if app._overlay_open() else None

def hangup():
    if app.connected or app.connecting:
        app.toggle_connection(); pump(0.3)
    for c_ in list(conns):
        try: c_.close()
        except OSError: pass
    conns.clear()

pump(0.5)
assert app.cfg["worlds"][0]["name"] == "Duskholm", "the default saved world"

# ============================== ATDT ===========================================================================
type_line("AT"); assert out().rstrip().endswith("OK")
type_line("atz"); type_line("ATH0")
app.clear()
type_line("ATDT")
assert "ERROR" in out() and not app.connected
type_line("atdt bad_host!! 80"); assert "ERROR" in out() and "valid host" in out()
type_line("ATDT 127.0.0.1 99999 plain"); assert "ERROR" in out()
app.clear()
type_line("ATDT 127.0.0.1 %d plain" % PORT, wait=1.0)
assert app.connected, out()
o = out()
assert "ATDT 127.0.0.1 %d plain" % PORT in o and "DIALING 127.0.0.1:%d" % PORT in o and "CONNECT" in o, o
assert app.v_host.get() == "127.0.0.1" and app.v_port.get() == str(PORT) and app.v_tls.get() is False
# online, the same text is just game input
received.clear()
type_line("ATDT 127.0.0.1 1 plain"); type_line("telnet"); type_line("AT")
assert b"ATDT 127.0.0.1 1 plain" in bytes(received) and b"telnet" in bytes(received) and b"AT\r\n" in bytes(received)
hangup()
# variants: ATT, ATD, ATDP, lower case, comma, host:port; a saved world's name
for variant in ("ATT", "atd", "AtDp"):
    app.clear(); type_line("%s 127.0.0.1:%d plain" % (variant, PORT), wait=1.0)
    assert app.connected, variant; hangup()
app.cfg["worlds"].append({"name": "Pretend", "host": "127.0.0.1", "port": PORT, "tls": False, "note": "", "last": 0})
app.clear(); type_line("atdt pretend", wait=1.0)
assert app.connected and "CONNECT" in out()
assert [w for w in app.cfg["worlds"] if w["name"] == "Pretend"][0]["last"] > 0, "last call is recorded"
hangup()
# a dead number
app.clear(); type_line("ATDT 127.0.0.1 %d plain" % DEAD, wait=4.0)
assert not app.connected and "NO CARRIER" in out() and "DIALING" in out()
# the old connect paths still say what they used to
app.clear(); app.v_host.set("127.0.0.1"); app.v_port.set(str(PORT)); app.v_tls.set(False)
app.toggle_connection(); pump(0.8)
assert app.connected and "Connected to 127.0.0.1" in out() and "CONNECT" not in out().replace("Connected", "")
hangup()

# ============================== the fake telnet ==================================================================
app.clear()
type_line("telnet")
o = out(); assert "Welcome to the telnet client" in o and o.rstrip().endswith("telnet>"), o
assert app._telnet_cli
type_line("?"); assert "open" in out() and "quit" in out() and out().rstrip().endswith("telnet>")
type_line("status"); assert "No connection." in out()
type_line("close"); assert "?No connection." in out()
type_line("frobnicate"); assert "?Invalid command" in out()
type_line(""); assert out().rstrip().endswith("telnet>")
type_line("open"); assert "usage: open" in out()
type_line("o 127.0.0.1 %d" % DEAD, wait=4.0)
assert "Trying 127.0.0.1..." in out() and "telnet: Unable to connect to remote host" in out()
assert out().rstrip().endswith("telnet>") and app._telnet_cli and not app.connected, "stays in the CLI after a failure"
type_line("o 127.0.0.1 %d plain" % PORT, wait=1.2)
o = out(); assert app.connected and "Connected to 127.0.0.1." in o and "Escape character is '^]'." in o, o
assert not app._telnet_cli, "once connected, input belongs to the game"
received.clear(); type_line("hello game"); assert b"hello game" in bytes(received)
hangup()
# telnet host port on one line, and quit
app.clear(); type_line("telnet 127.0.0.1 %d plain" % PORT, wait=1.2)
assert app.connected and "Trying 127.0.0.1" in out() and not app._telnet_cli
hangup()
type_line("telnet"); type_line("quit")
assert not app._telnet_cli
received.clear()
type_line("quit"); assert not app.connected           # offline, plain text goes nowhere ("Not connected.")
assert "Not connected." in out()
# telnet defaults to port 23 (nothing listens there)
app.clear(); type_line("telnet 127.0.0.1", wait=4.0)
assert "telnet: Unable to connect" in out() or app.connected is False

# ============================== line spacing ===================================================================
assert int(app.out.cget("spacing3")) == 0
assert app.apply_spacing(6) == 6 and int(app.out.cget("spacing2")) == 6 and int(app.out.cget("spacing3")) == 6
assert app.apply_spacing(99) == 12 and app.apply_spacing(-3) == 0
app.apply_spacing(4)
assert json.load(open(SETTINGS))["line_spacing"] == 4
# the ordinary font dialog has the control and applies it
top = app.choose_font(); pump(0.2)
spins = []
def walk(w):
    yield w
    for ch in w.winfo_children():
        yield from walk(ch)
spins = [w for w in walk(top) if isinstance(w, tk.Spinbox)]
assert len(spins) == 2, "size + line spacing"
spins[1].delete(0, "end"); spins[1].insert(0, "7")
next(w for w in walk(top) if isinstance(w, tk.Button) and w.cget("text") == "OK").invoke(); pump(0.2)
assert app.cfg["line_spacing"] == 7 and int(app.out.cget("spacing3")) == 7
app.apply_spacing(0)

# ============================== saved worlds: the ordinary dialog ============================================
errors, asked = [], []
dc.messagebox.showerror = lambda *a, **k: errors.append(a)
dc.messagebox.askyesno = lambda *a, **k: (asked.append(a) or True)
app.cfg["worlds"] = [dict(W[0]), dict(W[1])]
app.cfg["worlds"][0]["port"] = PORT
app._on_ctrl_w(); pump(0.3)
win = app._worlds_win; assert win is not None and win.winfo_exists()
assert app.open_worlds() is win, "no second window"
lb = win._actions["listbox"]
assert lb.size() == 2 and "Local Test" in lb.get(0) and "Duskholm" in lb.get(1) and "TLS" in lb.get(1)
# add
win._actions["add"](); pump(0.2)
form = [w for w in win.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Add world"][0]
for k, v in (("name", "Added"), ("host", "added.example.org"), ("port", "4001"), ("note", "hi")):
    form._set[k].set(v)
form._tls.set(False); form._ok(); pump(0.2)
assert app.cfg["worlds"][-1]["name"] == "Added" and app.cfg["worlds"][-1]["port"] == 4001 and lb.size() == 3
# duplicate name and invalid input are refused, nothing changes
win._actions["add"](); pump(0.2)
form = [w for w in win.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Add world"][0]
for k, v in (("name", "added"), ("host", "x.org"), ("port", "5")):
    form._set[k].set(v)
form._ok(); pump(0.1)
assert len(app.cfg["worlds"]) == 3 and errors, "duplicate refused"
form._set["name"].set("Other"); form._set["port"].set("notaport"); form._ok(); pump(0.1)
assert len(app.cfg["worlds"]) == 3
form.destroy()
# edit
lb.selection_clear(0, "end"); lb.selection_set(2)
win._actions["edit"](); pump(0.2)
form = [w for w in win.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Edit world"][0]
assert form._set["name"].get() == "Added"
form._set["host"].set("renamed.example.org"); form._ok(); pump(0.2)
assert app.cfg["worlds"][2]["host"] == "renamed.example.org"
# delete asks first
lb.selection_clear(0, "end"); lb.selection_set(2); win._actions["delete"](); pump(0.2)
assert asked and len(app.cfg["worlds"]) == 2
# connect from the dialog
lb.selection_clear(0, "end"); lb.selection_set(0); win._actions["connect"](); pump(1.2)
assert app.connected and app.v_port.get() == str(PORT) and app.v_tls.get() is False
assert app.cfg["worlds"][0]["last"] > 0
assert json.load(open(SETTINGS))["worlds"][0]["name"] == "Local Test"
hangup()

# ============================== saved worlds: the DOS dialing directory ==========================================
app.set_dos_mode(True); pump(0.6)
assert "^W Worlds" in app.dosbar.plain[0]
app.root.focus_force(); app.input.focus_force(); root.update()
app.input.event_generate("<Control-w>"); pump(0.3)
table = overlay(); assert isinstance(table, dosui.DosTable), "Ctrl+W opens the directory"
assert table.row_count == 2 and "Local Test" in " ".join(table.plain) and "Duskholm" in " ".join(table.plain)
app.input.event_generate("<Control-w>"); pump(0.2); assert overlay() is table, "no stacking"
key(table, "Escape"); assert overlay() is None
# add
app.dos_worlds(); table = overlay(); key(table, "a"); d = overlay(); assert isinstance(d, dosui.DosDialog)
ents = {f["key"]: f for f in d._fields}
for k, v in (("name", "Dos Added"), ("host", "dos.example.org"), ("port", "4002")):
    e = ents[k]["entry"]; e.delete(0, "end"); e.insert(0, v)
key(ents["note"]["entry"], "Return"); pump(0.4)
assert app.cfg["worlds"][-1]["name"] == "Dos Added", app.cfg["worlds"]
table = overlay(); assert isinstance(table, dosui.DosTable) and table.row_count == 3, "back in the directory"
assert table.selected == 2, "the new entry is selected"
# a bad entry keeps the form open with the values
key(table, "a"); d = overlay(); ents = {f["key"]: f for f in d._fields}
for k, v in (("name", "Bad"), ("host", "x.org"), ("port", "zzz")):
    e = ents[k]["entry"]; e.delete(0, "end"); e.insert(0, v)
key(ents["note"]["entry"], "Return"); pump(0.4)
d2 = overlay(); assert isinstance(d2, dosui.DosDialog) and {f["key"]: f for f in d2._fields}["port"]["entry"].get() == "zzz"
assert "valid host" in out() and len(app.cfg["worlds"]) == 3
key(d2, "Escape"); pump(0.4)
# edit, then remove with confirmation (No keeps it, Yes removes it)
table = overlay(); table.select(2); key(table, "e"); d = overlay(); ents = {f["key"]: f for f in d._fields}
assert ents["name"]["entry"].get() == "Dos Added"
e = ents["host"]["entry"]; e.delete(0, "end"); e.insert(0, "edited.example.org"); key(ents["note"]["entry"], "Return"); pump(0.4)
assert app.cfg["worlds"][2]["host"] == "edited.example.org"
table = overlay(); table.select(2); key(table, "Delete"); c = overlay(); assert c is not None
key(c, "n"); pump(0.4); assert len(app.cfg["worlds"]) == 3
table = overlay(); assert isinstance(table, dosui.DosTable)
table.select(2); key(table, "Delete"); key(overlay(), "y"); pump(0.5)
assert len(app.cfg["worlds"]) == 2
table = overlay(); assert isinstance(table, dosui.DosTable) and table.row_count == 2
# dial from the directory (modem wording)
app.clear(); table.select(0); key(table, "Return"); pump(1.2)
assert app.connected, out()
assert "DIALING 127.0.0.1:%d" % PORT in out() and "CONNECT" in out()
hangup()
app.set_dos_mode(False); pump(0.3)

# ============================== prompt profiles ====================================================================
app.set_dos_mode(False)
app.toggle_connection() if False else None
app.connected = True            # status paths only need the flag
rom_line = "<20hp 100m 100mv> "
app._on_data(rom_line.encode()); pump(0.2)
assert app._last_prompt is None, "the Haven format does not read a ROM prompt"
assert app.set_prompt_profile("ROM / Diku classic")
app._on_data(b"\n\r<20hp 100m 100mv> "); pump(0.3)
d = app._last_prompt; assert d and [g[0] for g in d["gauges"]] == ["HP", "MN", "MV"], d
assert app.statbar.data["gauges"][0][:2] == ("HP", 20) and app.statbar.winfo_ismapped()
texts = [t for t, _c in app.statbar.specs()]
assert any(t.startswith("MN 100") for t in texts) and any(t.startswith("MV 100") for t in texts), texts
app._on_data(b"\n\r<5/20hp 50/100m 90/120mv> "); pump(0.3)
assert app._last_prompt["hp"] == (5, 20, "HP")
assert json.load(open(SETTINGS))["prompt_profile"] == "ROM / Diku classic"
# DOS status row follows the profile too
app.set_dos_mode(True); pump(0.5); app.update_dosbar()
stat = app.dosbar.plain[1]; assert "HP" in stat and "5/20" in stat, stat
app.set_dos_mode(False); pump(0.3)
# back to the default
assert app.set_prompt_profile(prompts.DEFAULT_PRESET)
app._on_data(b"\n\r[350/350DF 0ST 0WN 0LG M:0 K:0 ( )] "); pump(0.3)
assert app._last_prompt["hp"] == (350, 350, "DF")
assert not app.set_prompt_profile("No such format")

# custom profiles: build from the editor's text fields, validate, save, select, persist, delete
prof, msg = app.profile_from_fields("Arena", r"HP (?P<h>\d+)/(?P<m>\d+) EN (?P<e>\d+)", "HP=h/m, EN=e", "", "", "", "HP 12/30 EN 7")
assert prof and prof["kind"] == "regex", msg
ok, msg = app.save_prompt_profile(prof); assert ok and app.cfg["prompt_profile"] == "Arena", msg
app._on_data(b"\n\rHP 12/30 EN 7 "); pump(0.3)
assert app._last_prompt["gauges"] == [("HP", 12, 30), ("EN", 7, None)] and app._last_prompt["hp"] == (12, 30, "HP")
bad, msg = app.profile_from_fields("Evil", "(a+)+$", "HP=a", "", "", "", "aaa")
assert bad is None and msg, "catastrophic patterns are refused"
bad, msg = app.profile_from_fields("Oops", r"(?P<h>\d+)", "HP=zzz", "", "", "", "5")
assert bad is None, "unknown group"
ok, msg = app.save_prompt_profile({"name": "Haven / Duskholm", "kind": "regex", "pattern": r"(?P<h>\d+)",
                                    "gauges": [{"label": "HP", "cur": "h"}]})
assert not ok and "built-in" in msg
app._save_settings()
saved = json.load(open(SETTINGS)); assert saved["prompt_profile"] == "Arena" and saved["prompt_custom"][0]["name"] == "Arena"
root.update(); root.destroy()
root = tk.Tk(); app = dc.App(root); root.geometry("1100x760+20+20"); pump(0.4)
assert app.cfg["prompt_profile"] == "Arena" and app.current_profile()["name"] == "Arena", "persisted"
# the ordinary editor
top = app.edit_prompt(); pump(0.3)
A = top._actions
A["load"]("New custom..."); pump(0.1)
f = A["fields"]
f["name"][0].set("Editor made"); f["pattern"][0].set(r"(?P<hp>\d+)\|(?P<mp>\d+)")
f["gauges"][0].set("HP=hp, MP=mp"); f["sample"][0].set("120|40"); pump(0.2)
assert "Matched" in A["result"].cget("text") and "HP 120" in A["result"].cget("text"), A["result"].cget("text")
f["pattern"][0].set(r"(?P<hp>\d+)\|(?P<mp"); pump(0.2)
assert "Matched" not in A["result"].cget("text"), "a broken pattern is reported, not crashed on"
f["pattern"][0].set(r"(?P<hp>\d+)\|(?P<mp>\d+)"); pump(0.2)
A["save"](); pump(0.3)
assert app.cfg["prompt_profile"] == "Editor made" and not top.winfo_exists()
top = app.edit_prompt(); A = top._actions
A["load"]("Haven / Duskholm"); assert A["state"]["builtin"] is True
A["load"]("ROM / Diku classic"); assert A["state"]["builtin"] and str(A["fields"]["pattern"][1].cget("state")) == "disabled"
A["var"].set("Editor made"); A["load"]("Editor made"); A["use"](); assert app.cfg["prompt_profile"] == "Editor made"
top.destroy()
# the DOS editor
app.set_dos_mode(True); pump(0.5)
app.dos_prompt_menu(); pm = overlay(); assert isinstance(pm, dosui.DosMenu)
key(pm, "n"); d = overlay(); assert isinstance(d, dosui.DosDialog)
ents = {f["key"]: f for f in d._fields}
for k, v in (("name", "Dos made"), ("pattern", r"\[(?P<a>\d+)/(?P<b>\d+)\]"), ("gauges", "HP=a/b"), ("sample", "[9/10]")):
    e = ents[k]["entry"]; e.delete(0, "end"); e.insert(0, v)
key(ents["sample"]["entry"], "Return"); pump(0.5)
assert app.cfg["prompt_profile"] == "Dos made", (app.cfg["prompt_profile"], out()[-200:])
pm = overlay(); assert isinstance(pm, dosui.DosMenu), "back in the prompt menu"
key(pm, "d"); pump(0.4)
assert app.cfg["prompt_profile"] == prompts.DEFAULT_PRESET and not any(c["name"] == "Dos made" for c in app.cfg["prompt_custom"])
key(overlay(), "Escape")
# line spacing from the DOS font menu
app.dos_font_menu(); fm = overlay(); key(fm, "l"); d = overlay(); assert isinstance(d, dosui.DosDialog)
e = {f["key"]: f for f in d._fields}["n"]["entry"]; e.delete(0, "end"); e.insert(0, "5"); key(e, "Return"); pump(0.4)
assert app.cfg["line_spacing"] == 5 and int(app.out.cget("spacing3")) == 5
b = (app._holder.winfo_width() - app._mid.winfo_width()) / 2.0 / app.f_norm.measure("0")
assert 0.5 <= b <= 2.0, ("border stays one cell with extra line spacing", b)
key(overlay(), "Escape")

root.update(); root.destroy()
print("feature tests OK")
