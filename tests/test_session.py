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
root.destroy()
print("session tests OK")
