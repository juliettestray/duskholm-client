"""Status-line action and the credit-walk preview preset (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import triggers
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


pr = [p for p in sc.trigger_presets() if p["name"] == "Preview your credit walk"][0]
ok, msg = app._store_trigger(None, dict(pr, enabled=True))
assert ok, msg
app.connected = True; app._online_since = time.time()
app._on_data(b"Your credit walk string is now: strides boldly\n\r"); pump(0.3)
assert app._notice_text == "Preview: Someone strides boldly in from the north", app._notice_text
assert app.notice.cget("text") == app._notice_text
app._on_data(b"Your ego form walk string is now: slinks\n\r"); pump(0.3)
assert app._notice_text.endswith("Someone slinks in from the north")
app.set_dos_mode(True); pump(0.4)
segs, _ = app._dos_segments(100)
assert any("Someone slinks" in x[0] for x in segs), segs
app.set_notice(""); assert not any("Someone" in x[0] for x in app._dos_segments(100)[0])
app.set_dos_mode(False)
# the editor round trip keeps a status action
t = triggers.validate_trigger({"name": "x", "pattern": "a*", "mode": "plain",
                               "actions": [{"type": "status", "text": "hi %1"}]})
t = t[0] if isinstance(t, tuple) else t
assert sc.values_from_trigger(t)["status"] == "hi %1"
root.update(); root.destroy()
print("status tests OK")
