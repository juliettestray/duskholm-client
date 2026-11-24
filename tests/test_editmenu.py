"""Right-click Cut / Copy / Paste in the entry box and the text areas, in both looks (no network)."""
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
shown = []
app._popup_menu = lambda m, x, y: shown.append(m)         # tk_popup would wait for a click


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def clip():
    try:
        return root.clipboard_get()
    except tk.TclError:
        return ""


def items(w, x=None, y=None):
    return {label: (enabled, action) for label, _hk, enabled, action in app._edit_items(w, x, y)}


pump(0.4)
app.connected = True
e = app.input
# ---- the entry box ---------------------------------------------------------------------------------
e.delete(0, "end")
it = items(e)
assert list(it) == ["Cut", "Copy", "Paste", "Select all", "Clear"]
assert not it["Cut"][0] and not it["Copy"][0] and not it["Select all"][0] and not it["Clear"][0], "nothing typed: nothing to do"
e.insert(0, "hello brave world")
it = items(e)
assert it["Select all"][0] and it["Clear"][0] and not it["Cut"][0], "no selection yet"
it["Select all"][1](); pump(0.1)
assert e.selection_present() and items(e)["Cut"][0] and items(e)["Copy"][0]
items(e)["Copy"][1](); pump(0.2)
assert clip() == "hello brave world" and e.get() == "hello brave world", "copy leaves it in place"
items(e)["Cut"][1](); pump(0.2)
assert e.get() == "" and clip() == "hello brave world", "cut takes it out and keeps it on the clipboard"
items(e)["Paste"][1](); pump(0.2)
assert e.get() == "hello brave world"
items(e)["Clear"][1](); assert e.get() == ""
# paste goes through the usual clean-up: a multi-line paste becomes one line, never sent
root.clipboard_clear(); root.clipboard_append("line one" + chr(10) + "line two" + chr(9) + "tabbed")
assert items(e)["Paste"][0]
items(e)["Paste"][1](); pump(0.1)
assert e.get() == "line one line two tabbed" and "\n" not in e.get(), repr(e.get())
e.delete(0, "end")
root.clipboard_clear()
assert not items(e)["Paste"][0], "nothing on the clipboard: Paste is greyed out"
# a password being typed: nothing leaves the box
app.term.echo_off = True; e.configure(show="*"); e.insert(0, "secret")
e.select_range(0, "end")
it = items(e)
assert not it["Cut"][0] and not it["Copy"][0], "Cut and Copy are off for a masked box"
app.term.echo_off = False; e.configure(show=""); e.delete(0, "end")

# the right button opens the menu (ordinary look)
shown.clear()
e.insert(0, "abc"); e.select_range(0, "end")
e.event_generate("<Button-3>", x=10, y=5); pump(0.2)
assert len(shown) == 1 and isinstance(shown[0], tk.Menu)
m = shown[0]
labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1)]
assert labels == ["Cut", "Copy", "Paste", "Select all", "Clear"], labels
assert m.entrycget(0, "state") == "normal" and m.entrycget(1, "state") == "normal"
assert m.entrycget(2, "state") == "disabled", "built while the clipboard was empty: Paste was greyed out"
m.invoke(0); pump(0.2)                                           # Cut from the real menu
assert e.get() == "" and clip() == "abc"
shown.clear()
e.event_generate("<Button-3>", x=10, y=5); pump(0.2)             # open it again: now there is something to paste
m = shown[0]
assert m.entrycget(2, "state") == "normal"
m.invoke(2); pump(0.2)                                           # Paste
assert e.get() == "abc"
e.delete(0, "end")

# ---- the main text and the panes -----------------------------------------------------------------------
app._on_data(("A line with a link https://example.com/x in it" + CR).encode()); pump(0.4)
it = items(app.out, 5, 5)
assert list(it) == ["Copy", "Select all"] and not it["Copy"][0], "no link under the pointer, nothing selected"
it["Select all"][1](); pump(0.1)
assert items(app.out, 5, 5)["Copy"][0]
items(app.out, 5, 5)["Copy"][1](); pump(0.2)
assert "A line with a link" in clip(), clip()[:60]
app.out.tag_remove("sel", "1.0", "end")
# right-click on the link
pos = app.out.search("https://example.com/x", "1.0")
bb = app.out.bbox(pos + "+3c")
it = items(app.out, bb[0] + 1, bb[1] + 1)
assert list(it) == ["Open link", "Copy link", "Copy", "Select all"], list(it)
it["Copy link"][1](); assert clip() == "https://example.com/x"
opened = []
sc.webbrowser.open = lambda u, *a, **k: opened.append(u)
it["Open link"][1](); assert opened == ["https://example.com/x"]
shown.clear()
app.out.event_generate("<Button-3>", x=bb[0] + 1, y=bb[1] + 1); pump(0.2)
assert shown and shown[0].entrycget(0, "label") == "Open link"
# a pane has the same menu
app.cfg["triggers"] = [{"name": "t", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "Tells"}]}]
app._on_data(("Goose tells you 'hi'" + CR).encode()); pump(0.5)
pt = app._panes["tells"]["text"]
shown.clear()
pt.event_generate("<Button-3>", x=20, y=10); pump(0.2)
assert shown and [shown[0].entrycget(i, "label") for i in range(shown[0].index("end") + 1)] == ["Copy", "Select all"]

# ---- the DOS look: the same choices as a DOS menu ----------------------------------------------------------
app.set_dos_mode(True); pump(0.6)
e.delete(0, "end"); e.insert(0, "dos text"); e.select_range(0, "end")
shown.clear()
e.event_generate("<Button-3>", x=10, y=5); pump(0.3)
assert app._overlay_open() and not shown, "a DOS menu, not a pop-up"
ov = app._overlay
labels = [i["label"] for i in ov._items if i]
assert labels == ["Cut", "Copy", "Paste", "Select all", "Clear"], labels
cut = [i for i in ov._items if i and i["label"] == "Cut"][0]
assert cut["enabled"] and cut["hotkey"] == "T"
cut["action"](); pump(0.3)
assert e.get() == "" and clip() == "dos text"
app.dos_close_overlay(); pump(0.2)
# the keyboard still works as it always did
e.delete(0, "end"); e.insert(0, "keys"); e.select_range(0, "end"); e.focus_force(); pump(0.1)
e.event_generate("<<Copy>>"); pump(0.1); assert clip() == "keys"
e.event_generate("<<Cut>>"); pump(0.1); assert e.get() == ""
e.event_generate("<<Paste>>"); pump(0.1); assert e.get() == "keys"
app.set_dos_mode(False); pump(0.3)

root.update(); root.destroy()
print("edit menu tests OK")
