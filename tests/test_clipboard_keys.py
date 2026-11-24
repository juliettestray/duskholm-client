"""Ctrl+C on text dragged over in the output or a pane, Ctrl+V into the entry, Ctrl+A on the entry line, and the
world-swap keys being changeable (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import extras
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")
CR = chr(13) + chr(10)


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def clip():
    try:
        return root.clipboard_get()
    except tk.TclError:
        return ""


def drag(w, word, extra=""):
    """Press at the start of `word` and drag to the end of it (plus `extra` characters): a real mouse selection."""
    pos = w.search(word, "1.0")
    assert pos, word
    a = w.bbox(pos)
    b = w.bbox(pos + "+%dc" % (len(word) + len(extra) - 1))
    assert a and b, (word, a, b)
    w.event_generate("<ButtonPress-1>", x=a[0] + 1, y=a[1] + a[3] // 2)
    w.event_generate("<B1-Motion>", x=b[0] + b[2] - 1, y=b[1] + b[3] // 2)
    w.event_generate("<ButtonRelease-1>", x=b[0] + b[2] - 1, y=b[1] + b[3] // 2)
    pump(0.3)


pump(0.4)
app.connected = True
app.cfg["triggers"] = [{"name": "t", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "Tells"}]}]
app._on_data(("The quick brown fox jumps over the lazy dog" + CR).encode()); pump(0.3)
app._on_data(("Goose tells you 'meet me at the fountain'" + CR).encode()); pump(0.5)
e = app.input

# ---- drag over text in the output, Ctrl+C, Ctrl+V elsewhere ---------------------------------------------------
drag(app.out, "brown fox jumps")
assert app.out.tag_ranges("sel") and app.out.get("sel.first", "sel.last") == "brown fox jumps"
root.clipboard_clear()
e.focus_force(); pump(0.1)
e.event_generate("<Control-c>"); pump(0.2)
assert clip() == "brown fox jumps", "Ctrl+C with the keyboard back in the entry box: " + repr(clip())
e.delete(0, "end")
app.out.focus_force(); pump(0.1)
app.out.event_generate("<Control-v>"); pump(0.3)
assert e.get() == "brown fox jumps", "Ctrl+V from the output goes into the entry box: " + repr(e.get())
# Ctrl+Insert / Shift+Insert are the same
root.clipboard_clear()
e.event_generate("<Control-Insert>"); pump(0.2)
assert clip() == "brown fox jumps"
e.delete(0, "end"); app.out.focus_force()
app.out.event_generate("<Shift-Insert>"); pump(0.2)
assert e.get() == "brown fox jumps"
e.delete(0, "end")

# ---- a pane: a click hands the keyboard to the entry box, and Ctrl+C still copies the dragged text ---------------
pt = app._panes["tells"]["text"]
drag(pt, "meet me at")
assert pt.tag_ranges("sel") and pt.get("sel.first", "sel.last") == "meet me at"
pump(0.3)                                                      # (the click's after_idle has moved the focus)
root.clipboard_clear()
e.focus_force(); pump(0.1)
e.event_generate("<Control-c>"); pump(0.2)
assert clip() == "meet me at", repr(clip())
# a selection in the entry box wins over an older one in the text: the entry's own copy runs
e.delete(0, "end"); e.insert(0, "typed words"); e.select_range(0, "end"); pump(0.1)
root.clipboard_clear()
e.event_generate("<Control-c>"); pump(0.2)
assert clip() == "typed words", repr(clip())
e.delete(0, "end")
# nothing selected anywhere: Ctrl+C does nothing harmful
for w in (app.out, pt):
    w.tag_remove("sel", "1.0", "end")
root.clipboard_clear(); root.clipboard_append("keep me")
e.event_generate("<Control-c>"); pump(0.2)
assert clip() == "keep me", "a copy with nothing selected leaves the clipboard alone"
# a multi-line paste becomes one line, as always
root.clipboard_clear(); root.clipboard_append("one" + chr(10) + "two")
app.out.focus_force(); app.out.event_generate("<Control-v>"); pump(0.2)
assert e.get() == "one two"
e.delete(0, "end")
# the DOS look: the same
app.set_dos_mode(True); pump(0.6)
drag(app.out, "quick brown")
root.clipboard_clear(); e.focus_force(); e.event_generate("<Control-c>"); pump(0.2)
assert clip() == "quick brown", repr(clip())
app.set_dos_mode(False); pump(0.4)

# ---- Ctrl+A: the whole entry line (rebindable); Aliases is Alt+A now ------------------------------------------
assert dict((a, s) for a, _t, s in app.hotkey_table())["select_input"] == "Ctrl-A"
assert dict((a, s) for a, _t, s in app.hotkey_table())["aliases"] == "Alt-A"
e.delete(0, "end"); e.insert(0, "a whole line"); e.icursor(3); e.select_clear(); e.focus_force(); pump(0.1)
e.event_generate("<Control-a>"); pump(0.2)
assert e.selection_present() and e.selection_get() == "a whole line" and e.index("insert") == len("a whole line")
e.insert("insert", "!")                                          # typing replaces nothing until you type over the selection
e.select_range(0, "end"); e.event_generate("<Key>", keysym="x")  # (a key over a selection replaces it)
pump(0.1)
app.hotkey_table()
# Alt+A opens the alias list, Ctrl+A no longer does
app.dos_close_overlay()
root.event_generate("<Alt-a>"); pump(0.4)
assert getattr(app, "_alias_win", None) is not None or app._overlay_open(), "Alt+A opens the aliases"
try:
    app._alias_win.destroy()
except (AttributeError, tk.TclError):
    pass
app._alias_win = None
# rebinding: Ctrl+J instead
ok, msg = app.set_hotkeys({"select_input": "Ctrl-J"}); assert ok, msg
e.delete(0, "end"); e.insert(0, "second try"); e.select_clear(); e.icursor(0); e.focus_force(); pump(0.1)
e.event_generate("<Control-j>"); pump(0.2)
assert e.selection_present() and e.selection_get() == "second try"
assert not e.bind("<Control-a>") and not root.bind("<Control-a>"), "Ctrl+A is no longer ours (Tk's own default applies)"
assert e.bind("<Control-j>") and root.bind("<Control-j>")
# a clash is refused and nothing changes
ok, msg = app.set_hotkeys({"select_input": "Alt-A"}); assert not ok and "same key" in msg, msg
assert dict((a, s) for a, _t, s in app.hotkey_table())["select_input"] == "Ctrl-J"
ok, msg = app.set_hotkeys({}); assert ok
assert dict((a, s) for a, _t, s in app.hotkey_table())["select_input"] == "Ctrl-A"
e.delete(0, "end")

# ---- the world-swap keys -------------------------------------------------------------------------------------
w1 = app.sessions[0]
w2 = app.open_new_world("Second"); pump(0.3)
w3 = app.open_new_world("Third"); pump(0.3)
app.goto_world(1); pump(0.3)
assert app.world_key_prefix() == "Ctrl-F"
root.event_generate("<Control-F2>"); pump(0.4)
assert app._shown is w2, "the default keys: Ctrl+F2"
root.event_generate("<Control-Next>"); pump(0.4)
assert app._shown is w3, "Ctrl+PageDown: next world"
root.event_generate("<Control-Next>"); pump(0.4)
assert app._shown is w1, "...and it wraps round"
root.event_generate("<Control-Prior>"); pump(0.4)
assert app._shown is w3, "Ctrl+PageUp: previous world"
# a new prefix for all twelve
vals = {a: shown for a, _t, shown in app._hotkey_rows()}
assert vals["world_keys"] == "Ctrl-F" and not any(a.startswith("world_") and a[6:].isdigit() for a in vals)
vals["world_keys"] = "Alt-F"
ok, msg = app.set_hotkeys(app._wanted_from_form(vals))
assert not ok and "Alt-F4" in msg, "Alt-F4 is the window's: " + msg
assert app.world_key_prefix() == "Ctrl-F", "nothing changed"
vals["world_keys"] = "Ctrl-Alt-F"
ok, msg = app.set_hotkeys(app._wanted_from_form(vals)); assert ok, msg
assert app.world_key_prefix() == "Ctrl-Alt-F"
assert ("Ctrl-Alt-F1..Ctrl-Alt-F12", "Show world 1..12") in app.help_key_lines()
app.goto_world(1); pump(0.3)
root.event_generate("<Control-F2>"); pump(0.4)
assert app._shown is w1, "the old key does nothing now"
root.event_generate("<Control-Alt-F2>"); pump(0.4)
assert app._shown is w2, "the new one does"
# one world on its own key (the prefix row then reads "(custom)" and leaves it alone)
ok, msg = app.set_hotkeys({**{a: s for a, _t, s in app.hotkey_table()}, "world_3": "Ctrl-Alt-J"}); assert ok, msg
assert app.world_key_prefix() == "" and dict((a, s) for a, _t, s in app._hotkey_rows())["world_keys"] == "(custom)"
root.event_generate("<Control-Alt-j>"); pump(0.4)
assert app._shown is w3
vals = {a: shown for a, _t, shown in app._hotkey_rows()}
ok, msg = app.set_hotkeys(app._wanted_from_form(vals)); assert ok, msg
assert dict((a, s) for a, _t, s in app.hotkey_table())["world_3"] == "Ctrl-Alt-J", "(custom) is left as it was"
# the form opens in both looks
f = app.open_hotkeys(); assert isinstance(f, tk.Toplevel); f.destroy(); pump(0.2)
app.set_dos_mode(True); pump(0.5)
app.open_hotkeys(); pump(0.3); assert app._overlay_open(); app.dos_close_overlay()
app.set_dos_mode(False); pump(0.3)
# close the world on screen with its key
ok, msg = app.set_hotkeys({}); assert ok
w3.connected = False
app.goto_world(3); pump(0.3)
n = len(app.sessions)
root.event_generate("<Control-Shift-W>"); pump(0.5)
assert len(app.sessions) == n - 1 and w3 not in app.sessions, "Ctrl+Shift+W closes it"

root.update(); root.destroy()
print("clipboard and key tests OK")
