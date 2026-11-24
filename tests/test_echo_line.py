"""Pressing Enter ends an unfinished game line (a tell without its newline) but not a prompt (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1000x600+20+20")
CR = chr(13) + chr(10)


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


sent = []
app.conn = type("C", (), {"send": lambda self, b: sent.append(b.decode().rstrip(CR)) or True, "close": lambda self, *a: None})()
app.connected = True
txt = lambda: app.out.get("1.0", "end-1c")
pump(0.4)

# a tell that arrives without a newline: the echo starts on its own line
app._on_data(("Savannah tells you OOCly 'Glad to be of service'").encode()); pump(0.4)
assert "service'" in txt() and app._line_plain.endswith("service'")
app.send_line("reply I bet"); pump(0.2)
assert "service'\nreply I bet" in txt(), repr(txt())
assert app._line_plain == "" and app._line == "" and not app._pending, "the line is finished, not left open"
app._on_data(("You tell Savannah OOCly 'I bet'" + CR).encode()); pump(0.3)
assert "'I bet'" in txt() and "service'You tell" not in txt()

# a line that has only just arrived may still be arriving: your echo goes above it, as before
app._on_data(("Bob tells you 'hi'").encode())
app.send_line("reply yo"); pump(0.4)
assert "reply yo\nBob tells you 'hi'" in txt(), repr(txt())
app._on_data(CR.encode()); pump(0.2)

# a trigger sees the finished line, and not the reply glued to it
seen = []
import triggers
app.cfg["triggers"] = [triggers.validate_trigger({"name": "t", "mode": "plain", "pattern": "tells you OOCly *",
                                                  "actions": [{"type": "note", "text": "SAW"}]})]
app._on_data(("Ann tells you OOCly 'one'").encode()); pump(0.3)
app.send_line("reply two"); pump(0.3)
assert txt().count("SAW") >= 1, "the unfinished tell counts as a line once you press Enter"
app.cfg["triggers"] = []

# a prompt is followed by what you type
app._on_data(b"[100/100DF 50ST 50WN 0LG M:0 K:0 ()] "); pump(0.4)
app.send_line("look"); pump(0.2)
assert "()] look" in txt(), repr(txt()[-60:])
# so is a login question that ends in a space
app._on_data(b"What is your name: "); pump(0.4)
app.send_line("bob"); pump(0.2)
assert "What is your name: bob" in txt(), repr(txt()[-60:])
app._on_data(b"Password: "); pump(0.4)
app.send_line("hunter2", echo=False, secret=True); pump(0.2)
assert "hunter2" not in txt()
root.destroy()
print("echo line tests OK")
