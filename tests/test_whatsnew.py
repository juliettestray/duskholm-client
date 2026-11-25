"""What's new after an update: only what was not seen, newest first, once; /changes; the release text matches (no network)."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import whatsnew as wn
import changes, version
import sanctuary as sc
import tkinter as tk

# ---- the pieces
E = [("1.2.0", "- **a** `b`\n- c"), ("1.1.7", "x"), ("1.1.6", "y"), ("1.1.10", "ten"), ("1.0.0", "first")]
assert wn.vkey("1.1.10") > wn.vkey("1.1.9") and wn.vkey("v1.2.0") == (1, 2, 0) and wn.vkey("junk") == (0,)
assert [v for v, _ in wn.entries_since("1.1.6", "1.2.0", E)] == ["1.2.0", "1.1.10", "1.1.7"], "newest first, 1.1.10 after 1.1.9"
assert [v for v, _ in wn.entries_since("1.2.0", "1.2.0", E)] == []
assert [v for v, _ in wn.entries_since("1.1.7", "1.1.10", E)] == ["1.1.10"], "never newer than this build"
assert [v for v, _ in wn.entries_since(None, "1.1.7", E)] == ["1.1.7"]
assert [v for v, _ in wn.entries_since("0", "1.2.0", E)] == ["1.2.0", "1.1.10", "1.1.7", "1.1.6", "1.0.0"]
assert wn.plain("- **a** `b`\n- c") == "  • a b\n  • c"
cur = version.__version__
assert changes.CHANGES[0][0] == cur, "write this version's entry in changes.py before releasing it"
assert len({v for v, _ in changes.CHANGES}) == len(changes.CHANGES) and all(t.strip() for _, t in changes.CHANGES)
assert [wn.vkey(v) for v, _ in changes.CHANGES] == sorted((wn.vkey(v) for v, _ in changes.CHANGES), reverse=True)
assert not any('"""' in t for _, t in changes.CHANGES)

# ---- a brand-new install: nothing to catch up on
home = tempfile.mkdtemp()
sc.SETTINGS_PATH = os.path.join(home, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")


def run(settings, wait=1.9):
    if settings is not None:
        json.dump(settings, open(sc.SETTINGS_PATH, "w", encoding="utf-8"))
    elif os.path.exists(sc.SETTINGS_PATH):
        os.remove(sc.SETTINGS_PATH)
    root = tk.Tk()
    app = sc.App(root)
    root.geometry("1100x650+20+20")
    end = time.time() + wait
    while time.time() < end:
        root.update(); time.sleep(0.01)
    return root, app


def pump(root, t=0.2):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def shown(app):
    w = getattr(app, "_news_win", None)
    try:
        return w._text.get("1.0", "end") if w is not None and w.winfo_exists() else None
    except tk.TclError:
        return None


root, app = run(None)
assert shown(app) is None and app.cfg["changes_seen"] == cur
root.destroy()

# ---- an install that has never been told (settings exist, no record): this version only
root, app = run({"host": "x"})
t = shown(app)
assert t and t.count("Version ") == 1 and t.startswith("Version %s" % cur), t[:60]
assert app.cfg["changes_seen"] == cur and json.load(open(sc.SETTINGS_PATH))["changes_seen"] == cur
root.destroy()

# ---- jumping several versions: everything missed, newest first, once
root, app = run({"host": "x", "changes_seen": "1.1.3"})
t = shown(app)
order = [l for l in t.split("\n") if l.startswith("Version ")]
assert order == ["Version %s" % v for v, _ in changes.CHANGES if wn.vkey("1.1.3") < wn.vkey(v) <= wn.vkey(cur)], order
assert order[0] == "Version " + cur and order[-1] == "Version 1.1.4", order
assert "**" not in t and "`" not in t and "•" in t
assert app._news_win.bind("<Escape>"), "Escape closes it"
app._news_win.destroy(); pump(root); assert shown(app) is None
assert app.maybe_show_whatsnew() is None and shown(app) is None, "only once"

# ---- /changes
app._local("/changes"); pump(root)
t = shown(app); assert t.count("Version ") == 1 and t.startswith("Version " + cur)
app._local("/changes all"); pump(root)
assert shown(app).count("Version ") == len(changes.CHANGES)
app._local("/changes 1.1.6"); pump(root)
assert [l for l in shown(app).split("\n") if l.startswith("Version ")][-1] == "Version 1.1.6"
app._local("/changes 9.9.9"); pump(root)
assert "No news from 9.9.9" in app.out.get("1.0", "end")
app._news_win.destroy()
# the Help menu has it
assert any("What's new" in str(app._menus[7].entrycget(i, "label")) for i in range(app._menus[7].index("end") + 1) if app._menus[7].type(i) == "command")

# ---- the DOS look: into the main text
app.set_dos_mode(True); pump(root, 0.5)
app._local("/changes"); pump(root)
txt = app.out.get("1.0", "end")
assert "Version " + cur in txt and shown(app) is None
app.set_dos_mode(False); pump(root, 0.4)
root.destroy()

# ---- a bad record in the settings is ignored
c = sc.clean_settings({"host": "x", "changes_seen": "<script>"})
assert c["changes_seen"] == ""
print("whats new tests OK")
