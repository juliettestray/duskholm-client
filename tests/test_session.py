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
root.destroy()
print("session tests OK")
