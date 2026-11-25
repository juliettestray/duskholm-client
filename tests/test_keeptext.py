"""The 'Keep text' checkbox: an option that shows it, and a tick that leaves what you typed in the box after Enter."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
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


sent = []
app.conn = type("C", (), {"send": lambda self, b: sent.append(b.decode().rstrip("\r\n")) or True, "close": lambda self, *a: None})()
app.connected = True


def type_enter(text):
    app.input.delete(0, "end"); app.input.insert(0, text); app._on_enter(None); pump(0.1)


pump(0.4)
# out of the box: nothing shown, Enter clears as always
assert app.cfg["keep_box"] is False and app.cfg["keep_text"] is False
assert app._keep_chk.winfo_manager() == "", "the checkbox is not on screen until Options asks for it"
type_enter("east"); assert sent == ["east"] and app.input.get() == ""
assert any(k == "keep_box" for k, *_ in sc.EXTRA_BOOLS) and "keep_text" not in [k for k, *_ in sc.EXTRA_BOOLS]

# the option puts the checkbox in the input box; it takes room from the typing area, not from the text
pad0 = app._in_pad
app._set_extra("keep_box", True); pump(0.4)
assert app._keep_chk.winfo_manager() == "place" and app._keep_chk.winfo_ismapped()
assert app._in_pad[1] > pad0[1], (pad0, app._in_pad)
box = app._inbox
assert app._keep_chk.winfo_rootx() + app._keep_chk.winfo_width() <= box.winfo_rootx() + box.winfo_width()
assert app._keep_chk.winfo_rootx() >= app.input.winfo_rootx() + app.input.winfo_width() - 2, "beside the typing area, not over it"
type_enter("east"); assert sent[-1] == "east" and app.input.get() == "", "present but not ticked: still clears"

# ticked: the text stays, and Enter sends it again
app._keep_chk.invoke(); pump(0.1)
assert app.cfg["keep_text"] is True
type_enter("east"); assert sent[-1] == "east" and app.input.get() == "east"
app._on_enter(None); app._on_enter(None); pump(0.1)
assert sent[-3:] == ["east", "east", "east"] and app.input.get() == "east"
assert app.history.count("east") == 1, "repeats are not stacked in the history"
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert saved["keep_text"] is True and saved["keep_box"] is True

# a password is never kept
app.term.echo_off = True
type_enter("hunter2"); assert sent[-1] == "hunter2" and app.input.get() == ""
app.term.echo_off = False

# /keep does the same as the tick, and does not keep itself
app.input.delete(0, "end"); app.input.insert(0, "/keep off"); app._on_enter(None); pump(0.2)
assert app.cfg["keep_text"] is False and app._keep_var.get() is False and app.input.get() == ""
app._local("/keep"); assert app.cfg["keep_text"] is True
app._local("/keep off"); assert app.cfg["keep_text"] is False
app._local("/keep maybe"); assert app.cfg["keep_text"] is False

# switched off in Options: the checkbox goes, and a tick left behind does nothing
app._local("/keep on"); app._set_extra("keep_box", False); pump(0.3)
assert app._keep_chk.winfo_manager() == "" and app._in_pad[1] == pad0[1], (app._in_pad, pad0)
type_enter("west"); assert sent[-1] == "west" and app.input.get() == ""
app._local("/keep"); assert "not switched on" in app.out.get("end-3l", "end")

# the growing box works the same way
app._set_extra("keep_box", True); app._set_extra("entry_grow", "3"); pump(0.4)
assert app.input is app._grow and app._keep_chk.winfo_manager() == "place"
type_enter("north"); assert sent[-1] == "north" and app.input.get() == "north"
app._local("/keep off"); type_enter("south"); assert app.input.get() == ""
app._set_extra("entry_grow", "off"); pump(0.3)

# the DOS look has no mouse checkbox, but /keep still works
app._local("/keep on")
app.set_dos_mode(True); pump(0.5)
assert app._keep_chk.winfo_manager() == ""
type_enter("up"); assert sent[-1] == "up" and app.input.get() == "up"
app.set_dos_mode(False); pump(0.5)
assert app._keep_chk.winfo_manager() == "place"
app._keep_var.set(False); app._keep_clicked(); pump(0.1)
assert app.cfg["keep_text"] is False

# bad settings never stop start-up
c = sc.clean_settings({"host": "x", "keep_box": "yes", "keep_text": 3})
assert c["keep_box"] is False and c["keep_text"] is False
root.destroy()
print("keep text tests OK")
