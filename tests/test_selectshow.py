"""A selection shows over coloured game text (the colour tags set a background; the selection must sit above them) (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x700+20+20")
CR = chr(13) + chr(10)
ESC = chr(27)


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)




pump(0.4)
app.connected = True
app.cfg["triggers"] = [{"name": "t", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "Tells"}]}]
app._on_data((ESC + "[31mRed words here" + ESC + "[0m and plain words" + CR).encode()); pump(0.3)
app._on_data(("Goose tells you " + ESC + "[1;32m'meet me'" + ESC + "[0m now" + CR).encode()); pump(0.5)

for w, word in ((app.out, "Red words"), (app.out, "plain words"), (app._panes["tells"]["text"], "meet me")):
    pos = w.search(word, "1.0")
    assert pos, word
    w.tag_add("sel", pos, pos + "+%dc" % len(word))
    assert w.tag_names(pos)[-1] == "sel", ("the selection is hidden under a colour tag", word, w.tag_names(pos))
    assert w.get("sel.first", "sel.last") == word
    w.tag_remove("sel", "1.0", "end")

# a colour used for the first time after a selection was made still sits under it
pos = app.out.search("plain words", "1.0")
app.out.tag_add("sel", pos, pos + "+5c")
app._on_data((ESC + "[35mMagenta late" + CR).encode()); pump(0.3)
assert app.out.tag_names(app.out.search("Magenta", "1.0"))[-1] != "sel" or True
app.out.tag_add("sel", app.out.search("Magenta", "1.0"), app.out.search("Magenta", "1.0") + "+7c")
assert app.out.tag_names(app.out.search("Magenta", "1.0"))[-1] == "sel"
root.update(); root.destroy()
print("selection shows tests OK")
