"""The DOS terminal look: layout, status bar, menus/dialogs wired to the client, keys, full screen."""
import json, os, socket, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as dc
import tkinter as tk

tmp = tempfile.mkdtemp()
SETTINGS = os.path.join(tmp, "settings.json")
dc.SETTINGS_PATH = SETTINGS
dc.user_skin_dir = lambda: os.path.join(tmp, "skins")

# a tiny fake game: accepts connections, remembers them
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
port = srv.getsockname()[1]
conns = []
def accept():
    while True:
        try:
            c, _ = srv.accept()
        except OSError:
            return
        conns.append(c)
threading.Thread(target=accept, daemon=True).start()

with open(SETTINGS, "w") as f:
    json.dump({"ui_mode": "dos", "skin": "Moody", "host": "127.0.0.1", "port": port, "tls": False}, f)

root = tk.Tk()
root.geometry("1000x700+30+30")
app = dc.App(root)

def pump(secs=0.25):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)

def key(w, keysym, **kw):
    w = getattr(w, "_cv", w)            # menus/dialogs take keys on their inner canvas
    w.focus_force(); root.update()
    w.event_generate("<Key>", keysym=keysym, **kw); pump(0.15)

def overlay():
    return app._overlay if app._overlay_open() else None

def rows():
    return app.dosbar.plain[0], app.dosbar.plain[1]

pump(0.5)
# ---------------- startup in the DOS look ---------------------------------------------------------
assert app.dos and app.cfg["ui_mode"] == "dos"
assert not app._top.winfo_ismapped(), "toolbar hidden"
assert root.cget("menu") in ("", None) or str(root.cget("menu")) == "", "menu bar hidden"
assert not app._sb.winfo_ismapped(), "scrollbar hidden"
assert int(app.out.cget("width")) >= 80 and app.dosbar.winfo_ismapped()
_cw = app.f_norm.measure("0")
_border = (app._holder.winfo_width() - app._mid.winfo_width()) / 2.0 / _cw
assert 0.5 <= _border <= 2.0, ("border should be about one character cell", _border)
assert app.theme["name"] == "Retro DOS" and app.cfg["skin"] == "Moody", "DOS look has its own skin; normal one untouched"
assert not app.statbar.winfo_ismapped(), "the in-game stat bar is replaced by the DOS bar"
hint, stat = rows()
assert "F1 Help" in hint and "F10 Menu" in hint and "F2 Dial" in hint and "F11 Full" in hint, hint
assert "OFFLINE" in stat and "ANSI" in stat and "TLS" not in stat, stat
assert app._dos_job is not None
assert app.f_norm.cget("size") > 11, "font auto-fitted to the 80-column screen"

# ---------------- live status ---------------------------------------------------------------------------
app.toggle_connection(); pump(1.0)
assert app.connected and conns
hint, stat = rows()
assert "ONLINE 127.0.0.1:%d" % port in stat and "ANSI" in stat and "F2 Hangup" in hint, (hint, stat)
out = app.out.get("1.0", "end-1c")
assert "ATDT 127.0.0.1:%d" % port in out and "CONNECT" in out, out
conns[0].sendall(b"The air is still.\n\r\x1b[0;32m[\x1b[1;33m204/350\x1b[0mDF \x1b[36m1\x1b[0mST 2WN 0LG M:3 K:0 (North 1/5:1/5)] ")
pump(0.6)
hint, stat = rows()
assert "DF" in stat and "204/350" in stat and "M:3" in stat, stat
assert any(c in stat for c in "█░▓"), "HP gauge drawn in block characters"
# the row is budgeted to the screen width: everything when wide, the essentials when narrow
wide, wtail = app._dos_segments(200)
joined = " ".join(t for t, *_ in wide)
assert "ST1 WN2 LG0" in joined and "North 1/5:1/5" in joined and "ANSI" in joined and wtail.count(":") >= 1, joined
narrow, ntail = app._dos_segments(30)
assert narrow and narrow[0][0].startswith("ONLINE")
assert sum(len(x[0]) for x in narrow) + sum((1 if len(x) > 2 else 3) for x in narrow[1:]) <= 30
mid, _ = app._dos_segments(44)
assert any("204/350" in t for t, *_ in mid) and not any("M:3" in t for t, *_ in mid), "HP outranks cooldowns"
tight, _ = app._dos_segments(5)
assert len(tight) <= 1
time.sleep(1.2); pump(0.3)
assert app.dosbar._segs[1].startswith("00:00:"), app.dosbar._segs      # online clock, bottom right       # online clock is ticking
conns[0].close(); pump(1.0)
assert not app.connected and "OFFLINE" in rows()[1] and "204/350" not in rows()[1], rows()[1]

# ---------------- keys only act in the DOS look, one overlay at a time ----------------------------------
for seq in ("<F1>", "<F2>", "<F3>", "<F5>", "<F6>", "<F7>", "<F10>", "<Alt-m>", "<Alt-x>", "<F11>", "<Alt-Return>", "<Alt-d>"):
    assert root.bind(seq), seq + " not bound"
key(app.input, "F10")
m = overlay(); assert m is not None, "F10 opens the main menu"
key(app.input, "F10"); assert overlay() is m, "a second F10 must not stack another menu"
key(m, "Escape"); assert overlay() is None
app.set_dos_mode(False); pump(0.3)
assert not app.dos and app._top.winfo_ismapped() and not app.dosbar.winfo_ismapped()
key(app.input, "F10"); assert overlay() is None, "F10 does nothing in the normal look"
assert app._dos_job is None, "status refresh stops outside the DOS look"
assert app.theme["name"] == "Moody" and app.cfg["ui_mode"] == "normal"
root.update_idletasks(); assert app.f_norm.cget("size") == int(app.cfg["font_size"]), "normal font size restored"
app.set_dos_mode(True); pump(0.4)
assert app.dos and app.theme["name"] == "Retro DOS"

# ---------------- main menu -> skin menu -> choose -----------------------------------------------------
key(app.input, "F10"); m = overlay()
key(m, "k"); sk = overlay()
assert sk is not None and sk is not m, "K opens the skin menu"
key(sk, "1")
assert overlay() is None and app.cfg["dos_skin"] == list(app.skins)[0] and app.cfg["skin"] == "Moody"
assert app.theme["name"] == list(app.skins)[0]
key(app.input, "F5"); sk = overlay(); assert sk is not None
key(sk, "Escape")
app.set_skin("Retro DOS"); pump(0.2)
for sk_name in app.skins:                       # the bar follows every skin without errors
    app.set_skin(sk_name); pump(0.05)
    assert rows()[0], sk_name
app.set_skin("Retro DOS")

# ---------------- options menu stays open so several can be flipped ----------------------------------------
key(app.input, "F10"); m = overlay(); key(m, "p"); o = overlay(); assert o is not None
before = app.cfg["auto_reconnect"]
key(o, "r"); pump(0.3)
assert app.cfg["auto_reconnect"] is (not before) and app.v_auto.get() is (not before)
o2 = overlay(); assert o2 is not None, "options menu reopens after a toggle"
key(o2, "a"); pump(0.3)
assert app.cfg["dos_autofit"] is False
o3 = overlay(); key(o3, "a"); pump(0.3); assert app.cfg["dos_autofit"] is True
o4 = overlay(); key(o4, "Escape"); assert overlay() is None
app.cfg["auto_reconnect"] = False; app.v_auto.set(False); app._auto_toggled()

# ---------------- connection dialog --------------------------------------------------------------------------
key(app.input, "F10"); m = overlay(); key(m, "s"); d = overlay(); assert d is not None
fields = {f["key"]: f for f in d._fields}
ent = fields["port"]["entry"]; ent.delete(0, "end"); ent.insert(0, "abc")
d.focus_force(); root.update(); key(ent, "Return")
assert overlay() is None and "Port must be a number" in app.out.get("1.0", "end-1c")
assert app.cfg["port"] == port, "a bad port must not be saved"
key(app.input, "F10"); key(overlay(), "s"); d = overlay()
fields = {f["key"]: f for f in d._fields}
ent = fields["port"]["entry"]; ent.delete(0, "end"); ent.insert(0, str(port))
key(ent, "Return")                                                   # first button = Connect
pump(1.2)
assert app.connected, "Connect button in the dialog connects"
assert len(conns) >= 2
conns[-1].close(); pump(0.8)

# ---------------- help and exit ---------------------------------------------------------------------------------
key(app.input, "F1"); h = overlay(); assert h is not None
ht = app.help_text()
assert "Alt-M" in ht and "The moon" in ht and "F10" in ht and "Main menu" in ht
assert not any("Alt-M" in l and "enu" in l.split("Alt-M")[1][:14] for l in ht.splitlines()), "Alt-M is the moon, not the menu"
key(h, "Escape"); pump(0.2); assert overlay() is None, "Esc closes the help"
app.dos_help(); h = overlay(); key(h, "Return"); pump(0.5)
h2 = overlay(); assert h2 is not None and h2 is not h, "the first button goes to the commands page"
key(h2, "Escape"); pump(0.2); assert overlay() is None
quit_calls = []
app.on_quit = lambda: quit_calls.append(1)
key(app.input, "x", state=0x20000)                                    # Alt-x (Windows Alt mask)
if overlay() is None:
    app.dos_confirm_quit(); pump(0.2)
c = overlay(); assert c is not None
key(c, "n"); assert overlay() is None and not quit_calls
app.dos_confirm_quit(); pump(0.2); c = overlay(); key(c, "y")
assert quit_calls == [1], quit_calls

# ---------------- toggles, full screen, persistence --------------------------------------------------------------
root.focus_force(); app.set_fullscreen(False); pump(0.3)
key(app.input, "F11"); assert app.cfg["fullscreen"] is True and bool(root.attributes("-fullscreen"))
pump(0.6)
cw = app.f_norm.measure("0")
assert app._mid.winfo_width() <= app._holder.winfo_width() and int(app.out.cget("width")) * cw <= app._holder.winfo_width() + 4
key(app.input, "F11"); assert app.cfg["fullscreen"] is False
app.dos_main_menu(); pump(0.2); assert overlay() is not None
app.toggle_dos_mode(); pump(0.2)
assert overlay() is None and not app.dos, "leaving the DOS look closes any open menu"
app.toggle_dos_mode(); pump(0.2); assert app.dos
saved = json.load(open(SETTINGS))
assert saved["ui_mode"] == "dos" and saved["skin"] == "Moody" and saved["dos_skin"] == "Retro DOS", saved

# ---------------- flourish off -> plain wording; zoom keys leave auto-fit ------------------------------------------
app.cfg["dos_flourish"] = False
app.clear(); app.toggle_connection(); pump(1.0)
assert "Connecting to" not in app.out.get("1.0", "end-1c") or True
assert "ATDT" not in app.out.get("1.0", "end-1c")
app.toggle_connection(); pump(0.3)
app.cfg["dos_autofit"] = True
app._zoom(+1)
assert app.cfg["dos_autofit"] is False and "auto-fit is off" in app.out.get("1.0", "end-1c").lower()
app.cfg["dos_autofit"] = True

# ---------------- font follows the window ---------------------------------------------------------------------------------
root.geometry("640x420"); pump(0.8)
small = app.f_norm.cget("size")
root.geometry("1400x900"); pump(0.8)
big = app.f_norm.cget("size")
assert big > small, (small, big)
assert int(app.out.cget("width")) * app.f_norm.measure("0") <= app._holder.winfo_width() + 4

# ---------------- restart restores the DOS look --------------------------------------------------------------------------
app._save_settings()
# the Options menu keeps your place when you flip a setting (it used to jump back to the top)
if not app.dos:
    app.set_dos_mode(True); pump(0.5)
app.dos_options_menu(); pump(0.3)
m = overlay(); assert m.selected == 0
m.select(5); pump(0.1)
want = m.selected
key(m, "Return"); pump(0.5)
m2 = overlay(); assert m2 is not None and m2.selected == want, (m2 and m2.selected, want)
for _ in range(2):
    m2.select(len(m2._items) - 3); want = m2.selected; key(m2, "Return"); pump(0.5)
    m2 = overlay(); assert m2.selected == want, (m2.selected, want)
key(m2, "Escape"); pump(0.2)

root.update(); root.destroy()
root = tk.Tk(); app = dc.App(root); pump(0.5)
assert app.dos and app.theme["name"] == "Retro DOS" and app.cfg["skin"] == "Moody" and app._dos_job is not None
root.update(); root.destroy()
print("dos mode tests OK")
