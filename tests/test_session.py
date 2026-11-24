"""Per-world state lives on a Session; the App forwards to the active one (no network)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)

assert isinstance(app.session, sc.Session)
for n in sc.SESSION_FIELDS:
    assert n not in app.__dict__, n + " must live on the session"
    assert hasattr(app.session, n), n
app.connected = True; app._line = "abc"
assert app.session.connected is True and app.session._line == "abc"
other = sc.Session("two")
app.session, saved = other, app.session
other.__dict__.update({n: getattr(saved, n) for n in sc.SESSION_FIELDS})
other.connected = False
assert app.connected is False and saved.connected is True, "switching session switches the state"
app.session = saved
assert app.connected is True


# ---- two worlds with their own scrollback, both fed while only one is shown
import time
def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)
root.geometry("1000x600+20+20"); pump(0.3)
first = app.session
w2 = app.add_session("two")
assert len(app.sessions) == 2 and w2.out is not first.out and w2.out in app._text_widgets()
for s_, word in ((first, "alpha"), (w2, "bravo")):
    s_.q.put((s_.conn.gen, "data", (word + " line" + chr(13) + chr(10)).encode()))
    s_.connected = True
pump(0.6)
txt = lambda s_: s_.out.get("1.0", "end")
assert "alpha" in txt(first) and "bravo" not in txt(first), txt(first)
assert "bravo" in txt(w2) and "alpha" not in txt(w2), txt(w2)
assert app.session is first, "the pump leaves the shown world alone"
app.switch_session(w2); pump(0.4)
assert app.session is w2 and app.out is w2.out and w2.out.winfo_ismapped() and not first.out.winfo_ismapped()
app.system("hello two"); pump(0.2)
assert "hello two" in txt(w2) and "hello two" not in txt(first)
app.switch_session(first); pump(0.4)
assert first.out.winfo_ismapped() and not w2.out.winfo_ismapped() and "alpha" in txt(first)
# the DOS look too
app.set_dos_mode(True) if hasattr(app, "set_dos_mode") else None; pump(0.5)
app.switch_session(w2); pump(0.4); assert w2.out.winfo_ismapped() and not first.out.winfo_ismapped()
app.switch_session(first); pump(0.3)

# ---- tabs, keys, activity, and what a hidden world may not touch
CR = chr(13) + chr(10)
assert app.session is first and app._shown is first
app.set_dos_mode(False) if getattr(app, "dos", False) else None
pump(0.3)
assert app.world_tabs_text() == "[1 World 1]  2 two", app.world_tabs_text()
hints = app.world_hints()
assert [h[0] for h in hints] == ["^F1", "^F2"] and hints[0][1] == "[World 1]" and hints[1][1] == "two"
# new text in the hidden world marks it (once) and does not touch the shown world
first._last_prompt = None
w2.q.put((w2.conn.gen, "data", ("news from two" + CR).encode())); pump(0.5)
assert w2.unread and "2 two*" in app.world_tabs_text() and not first.unread
assert "news from two" in txt(w2) and "news from two" not in txt(first)
assert app.session is first and app._shown is first
# a prompt arriving in a hidden world does not repaint the shown world's stat bar
shown_before = app.statbar.winfo_ismapped()
w2.q.put((w2.conn.gen, "data", ("[100/100DF 50ST 50WN 0LG M:0 K:0 ()] ").encode())); pump(0.5)
assert w2._last_prompt is not None and first._last_prompt is None and app.statbar.winfo_ismapped() == shown_before
# Ctrl+F2 shows it, Ctrl+F1 goes back, a number with no world does nothing
root.event_generate("<Control-F2>"); pump(0.4)
assert app._shown is w2 and not w2.unread and app.statbar.winfo_ismapped() == (app.cfg.get("statbar") and not app.dos)
root.event_generate("<Control-F1>"); pump(0.4)
assert app._shown is first and not app.goto_world(7) and app._shown is first
# the screen reader only follows the shown world
app.cfg["screen_reader"] = True
assert app.sr_on()
app.session = w2
assert not app.sr_on(), "a hidden world is silent"
app.session = first
app.cfg["screen_reader"] = False
# connection state follows the shown world on the toolbar
w2.connected = True; first.connected = False
app.goto_world(2); pump(0.3); assert app.btn.cget("text") == "Disconnect" and app.status.cget("text") == "Connected"
app.goto_world(1); pump(0.3); assert app.btn.cget("text") == "Connect" and app.status.cget("text") == "Disconnected"
w2.connected = False
# typed text is kept per world
app.input.insert(0, "half a comm"); app.goto_world(2); pump(0.2)
assert app.input.get() == ""; app.goto_world(1); pump(0.2); assert app.input.get() == "half a comm"
app.input.delete(0, "end")
# a saved world opens in its own tab when this one is busy; a busy world is reused
app.cfg["worlds"] = [{"name": "Alpha", "host": "127.0.0.1", "port": 9, "tls": False, "note": ""}]
first.connected = True
n = len(app.sessions)
sc_start = app._start_connect
started = []
app._start_connect = lambda **kw: started.append((app.session.name, app.v_host.get(), kw))
app.dial_world(app.cfg["worlds"][0], modem=False); pump(0.3)
assert len(app.sessions) == n + 1 and app._shown.name == "Alpha" and started and started[0][0] == "Alpha" and started[0][1] == "127.0.0.1"
alpha = app._shown; alpha.connected = True
app.goto_world(1); app.dial_world(app.cfg["worlds"][0], modem=False); pump(0.2)
assert len(app.sessions) == n + 1 and app._shown is alpha, "an open world is switched to, not opened twice"
app._start_connect = sc_start
alpha.connected = first.connected = False
# slash commands
app.goto_world(1)
app._local("/world 2"); assert app._shown is w2
app._local("/world alp"); assert app._shown is alpha
app._local("/world"); app._local("/world nosuch")
# closing
assert app.close_world(alpha) and alpha not in app.sessions and app._shown in app.sessions
app._local("/closeworld"); pump(0.2)
assert len(app.sessions) == 1 and not app.close_world(), "the last world stays"
assert app._shown is app.session is app.sessions[0]
# the DOS look lists the worlds in the top bar
w3 = app.add_session("three")
app.set_dos_mode(True); pump(0.5)
app.update_dosbar(); pump(0.2)
top = app.dosbar.plain[0]
assert "^F1" in top and "^F2" in top and "three" in top, top
app.dosbar.top.winfo_toplevel().update()
app.set_dos_mode(False); pump(0.3)
app.close_world(w3)
root.destroy()
print("session tests OK")
