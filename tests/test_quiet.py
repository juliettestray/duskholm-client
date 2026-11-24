"""Under the test runner the system bell is silenced (a window on the invisible desktop still beeps through the
speakers otherwise); the client's own bell settings keep working (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk

QUIET = bool(os.environ.get("SANCTUARY_QUIET"))
import sanctuary as sc

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("900x500+20+20")
root.update()
if QUIET:
    # the runner sets the flag: Tk's bell command is an empty procedure now, whoever rings it
    assert root.tk.eval("info body bell") == "", "bell does nothing"
    root.bell()
    root.tk.call("bell")
    app.cfg["bell"] = True
    app._do_effect(("beep",))                       # a trigger's beep action goes through the same call
    app.root.bell()
else:
    print("(not run through run_tests.py: the quiet flag is off, so nothing to check)")
# the settings still decide what rings: a test that swaps in its own counter sees every call
rang = []
app.root.bell = lambda *a, **k: rang.append(1)
app.cfg["bell"] = True
app._do_effect(("beep",))
assert rang == [1], rang
app.cfg["bell"] = False
app._do_effect(("beep",))
assert rang == [1], "the Beep option still turns it off"
root.destroy()
print("quiet bell tests OK")
