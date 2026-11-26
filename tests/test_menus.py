"""The menu bar: grouped sensibly, nothing lost, every option reachable (in Options or Settings), and menu text as large as the main text (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk
from tkinter import font as tkfont

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1250x720+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


pump(0.5)
bar = app._menubar


def entries(m):
    out = []
    for i in range(m.index("end") + 1):
        t = m.type(i)
        out.append((t, m.entrycget(i, "label") if t != "separator" else None, i))
    return out


top = {bar.entrycget(i, "label"): bar.nametowidget(bar.entrycget(i, "menu")) for i in range(bar.index("end") + 1) if bar.type(i) == "cascade"}
assert list(top) == ["File", "Edit", "View", "Automate", "Tools", "Options", "Help"], list(top)

# tidy: no separator first, last, or doubled, in any menu or sub-menu
def walk(m, path):
    es = entries(m)
    types = [t for t, _l, _i in es]
    assert types and types[0] != "separator" and types[-1] != "separator", (path, types)
    assert not any(a == b == "separator" for a, b in zip(types, types[1:])), (path, types)
    for t, l, i in es:
        if t == "cascade":
            walk(m.nametowidget(m.entrycget(i, "menu")), path + "/" + l)
for name, m in top.items():
    walk(m, name)

# where things live
def labels(name):
    return [l for t, l, _i in entries(top[name]) if l]
def has(name, text):
    return any(l.startswith(text) for l in labels(name))
for name, want in {
        "File": ["Connect / Disconnect", "Worlds...", "Close this world", "Start/stop logging", "Export world settings",
                 "Import world settings", "Import from another client", "Quit"],
        "Edit": ["Find...", "Find next", "Copy without my commands", "Clear screen"],
        "View": ["Skin", "Colours", "Font", "Bigger font", "Smaller font", "DOS terminal look", "Full screen", "Stat bar",
                 "Prompt bar format", "Panes / layout", "Lock pane sizes"],
        "Automate": ["Triggers", "Aliases", "Buttons", "Timer", "Customize form"],
        "Tools": ["Notepad", "Game time", "Moon", "Gradient maker", "Hex to xterm", "Emoji picker"],
        "Help": ["Help", "Hotkeys", "Check for updates", "About"]}.items():
    for text in want:
        assert has(name, text), (name, text, labels(name))
for name in ("Edit", "View", "Automate", "Tools", "Help"):
    assert len(labels(name)) <= 12, "short menus: " + name
assert len(labels("File")) <= 12

# Options is short now: what you changed lately (when anything), then Settings...
app.cfg["opt_recent"] = []; app._fill_options_menu()
o = top["Options"]
assert [l for t, l, _i in entries(o) if l] == ["Settings...   Ctrl+Shift+O"], "nothing changed yet: just Settings..."
app._set_extra("links", False); app._set_extra("clock", "real"); app.option_set("bell", False); app._fill_options_menu()
es = entries(o)
assert es[0][1] == "Recently changed" and o.entrycget(0, "state") == "disabled"
assert [l for t, l, _i in es if l][1:4] == ["Beep on server bell", "Clock", "Clickable links"], [l for t, l, _i in es if l]
assert es[-1][1].startswith("Settings...") and es[-2][0] == "separator"
idx = next(i for t, l, i in es if l == "Beep on server bell")
o.invoke(idx); assert app.cfg["bell"] is True; o.invoke(idx)
idx = next(i for t, l, i in es if l == "Clickable links")
o.invoke(idx); assert app.cfg["links"] is True; app._set_extra("links", True)
sub = o.nametowidget(o.entrycget(next(i for t, l, i in es if l == "Clock"), "menu"))
sub.invoke(2); assert app.cfg["clock"] == "game"; sub.invoke(0); assert app.cfg["clock"] == "off"
for i in range(10):
    app.option_set("bell", bool(i % 2))
assert len(app.cfg["opt_recent"]) <= 12 and app.cfg["opt_recent"][0] == "bell"
app._fill_options_menu(); assert len([1 for t, l, _i in entries(o) if t in ("checkbutton", "cascade")]) <= 5, "only the last few"

# Edit > Find next and Clear screen run
app.out.configure(state="normal"); app.out.insert("end", "needle one\n"); app.out.configure(state="disabled")
ed = top["Edit"]
ed.invoke(next(i for t, l, i in entries(ed) if l and l.startswith("Clear screen"))); pump(0.2)
assert "needle one" not in app.out.get("1.0", "end")
ed.invoke(next(i for t, l, i in entries(ed) if l and l.startswith("Find next"))); pump(0.2)     # (nothing to find: no crash)

# menu text is as large as the main text, and follows it
mf = tkfont.nametofont("TkMenuFont")
assert abs(int(mf.cget("size"))) >= max(10, min(sc.MENU_FONT_MAX, int(app.cfg["font_size"]))) - 0, mf.actual()
app.apply_font(size=16); pump(0.2)
assert int(mf.cget("size")) == 16, mf.cget("size")
app.apply_font(size=34); pump(0.2)
assert int(mf.cget("size")) == sc.MENU_FONT_MAX, "never absurdly large"
app.apply_font(size=8); pump(0.2)
assert int(mf.cget("size")) == 10, "and not tiny"
if "Segoe UI" in tkfont.families(root):
    assert mf.cget("family") == "Segoe UI"

root.update(); root.destroy()
print("menu tests OK")
