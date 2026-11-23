"""DOS look: no text is ever cut off at the side or wrapped out of place (it never could be on a real
80-column DOS screen). Opens every DOS menu, dialog and message and measures what was drawn."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import dosui
import custom
import tkinter as tk

home = tempfile.mkdtemp()
os.environ["USERPROFILE"] = os.environ["HOME"] = home
sc.SETTINGS_PATH = os.path.join(home, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
json.dump({"ui_mode": "dos", "dos_autofit": False, "dos_cols": 80, "dos_font_size": 12}, open(sc.SETTINGS_PATH, "w"))
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x700+10+10")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


pump(0.8)
assert app.dos
app.connected = True
app._on_data(b"[350/350DF 80ST 1WN 0LG M:5 K:2 (North 1/5:1/5)] "); pump(0.2)
app.cfg["designs"] = custom.save_design([], "Silk scarf", "clothing", {"names": "red scarf"})
rel = {"tag": "v9.9.9", "page": "https://github.com/x/y", "notes": "What's new:\n- one thing\n- another thing that is a rather long line of release notes to see how it wraps",
       "name": "n", "version": (9, 9, 9), "assets": []}
cw = app.f_norm.measure("0")

problems = []


def check(name):
    o = app._overlay
    if o is None or not app._overlay_open():
        problems.append("%s: nothing opened" % name)
        return
    cv = o._cv
    pump(0.15)
    width = int(cv.winfo_reqwidth())
    for item in cv.find_all():
        if cv.type(item) != "text":
            continue
        text = cv.itemcget(item, "text")
        bb = cv.bbox(item)
        if not bb or not text.strip() or all(0x2500 <= ord(ch) <= 0x257F or ch == " " for ch in text):
            continue                                    # the frame itself
        if bb[2] > width - cw // 2:
            problems.append("%s: runs past the box: %r" % (name, text[:50]))
        if "…" in text:
            problems.append("%s: cut off with an ellipsis: %r" % (name, text[:50]))
    rows = o.winfo_reqheight()
    if o.winfo_rooty() + rows > root.winfo_rooty() + root.winfo_height() + 4 and o.winfo_height() > root.winfo_height():
        problems.append("%s: taller than the window" % name)
    app.dos_close_overlay(); pump(0.1)


cases = [
    ("main menu", app.dos_main_menu), ("tools menu", app.dos_tools_menu), ("options", app.dos_options_menu),
    ("skin menu", app.dos_skin_menu), ("colours", app.dos_colors_menu), ("palette", app.dos_palette_menu),
    ("ui colours", lambda: app.dos_key_menu("ui")), ("dos colours", lambda: app.dos_key_menu("dos")),
    ("help keys", app.dos_help), ("help commands", lambda: app.dos_help(2)), ("about", app.open_about),
    ("moon", app.open_moon), ("timer", app.open_timers), ("gradient", app.open_gradient), ("hex", app.open_hex),
    ("customize 1", lambda: app._dos_customize(custom.blank(), 1)), ("customize 2", lambda: app._dos_customize(custom.blank(), 2)),
    ("hotkeys", app.open_hotkeys), ("export", app.open_export), ("import", app.open_import), ("panes", app.open_panes),
    ("connect", app.dos_connect_dialog), ("triggers", lambda: app.dos_rules("trigger")), ("aliases", lambda: app.dos_rules("alias")),
    ("trigger form 1", lambda: app._dos_trigger_form(None, None, 1)), ("trigger form 2", lambda: app._dos_trigger_form(None, None, 2)),
    ("alias form", lambda: app._dos_alias_form(None, None)), ("worlds", app.open_worlds), ("prompt", app.edit_prompt),
    ("font", app.choose_font), ("update", lambda: app.show_update(rel)), ("restart", lambda: app.confirm_restart("x.exe")),
    ("quit", app.dos_confirm_quit), ("design book", lambda: app._dos_design_book(lambda d: None, lambda: None)),
]
for name, fn in cases:
    try:
        fn()
    except Exception as e:                       # a screen that cannot open is a problem too
        problems.append("%s: raised %s: %s" % (name, type(e).__name__, e))
        app.dos_close_overlay()
        continue
    pump(0.2)
    check(name)

# the hint row never shows half a hint, at any width
for wpx in (1100, 900, 700, 500, 360):
    root.geometry("%dx700+10+10" % wpx); pump(0.6)
    app.update_dosbar(); pump(0.2)
    row = app.dosbar.plain[0]
    if "…" in row:
        problems.append("hint bar at %d px is cut off: %r" % (wpx, row))
    for hint in ("F10 Menu",):
        if wpx >= 500 and hint not in row:
            problems.append("hint bar at %d px lost %s: %r" % (wpx, hint, row))
    words = row.split()
    keys = [w for w in words if w.startswith(("F", "^")) and len(w) <= 3]
    for k in keys:
        i = words.index(k)
        if i + 1 >= len(words):
            problems.append("hint bar at %d px has a key with no label: %r" % (wpx, row))

root.update(); root.destroy()
assert not problems, "\n" + "\n".join(problems)
print("dos fit tests OK")
