"""The Settings window: every option on a topic page, controls that change the real option, a find box, and a
'Recently changed' section in the Options menu that stays in step with it."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import settingsui
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1250x720+20+20")


def pump(t=0.2):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


pump(0.4)
defs = app._option_defs()
# every option is on exactly one page, and nothing needed an 'Other' page
pages = settingsui.pages_for(defs)
placed = [k for _n, ks in pages for k in ks]
assert sorted(placed) == sorted(defs) and len(placed) == len(set(placed)), "every option once"
assert [n for n, _k in pages if n == settingsui.OTHER] == [], "new options must be given a page in settingsui.PAGES"
assert {k for k, *_ in sc.EXTRA_BOOLS} | {k for k, *_ in sc.EXTRA_CHOICES} <= set(defs)
assert settingsui.clean_recent(["a", "a", 5, "", "x" * 40, "b"]) == ["a", "b"]
assert sc.clean_settings({"host": "x", "opt_recent": "no"})["opt_recent"] == [] and sc.clean_settings({"host": "x", "opt_recent": ["links", 7]})["opt_recent"] == ["links"]
import extras
assert extras.HOTKEYS["settings"][1] == "Ctrl-Shift-O" and "settings" in extras.effective_keys(None)

# open it: a page per topic, and the first page's options are there
app.open_settings(); pump(0.4)
win = app._settings_win; top = win["top"]
lbs = [w for w in walk(top) if w.winfo_class() == "Listbox"]
assert len(lbs) == 1 and [lbs[0].get(i) for i in range(lbs[0].size())] == [n for n, _k in pages]
app.open_settings(); assert app._settings_win is win, "opening it again brings the same window up"


def controls():
    return [w for w in walk(top) if w.winfo_class() in ("Checkbutton", "Radiobutton", "Menubutton", "Button")]


def page(name):
    win["select"](name); pump(0.2)


# every option can be reached on its page
for name, keys in pages:
    page(name)
    texts = [str(w.cget("text")) for w in walk(top) if w.winfo_class() in ("Checkbutton", "Label", "Button")]
    for k in keys:
        d = defs[k]
        want = d["label"] if d["kind"] in ("bool", "button") else (d["short"] or d["label"]) + ":"
        assert want in texts, (name, k, want)

# a check box changes the real option and goes to the top of 'Recently changed'
app.cfg["opt_recent"] = []
page("Display and text")
cb = next(w for w in controls() if w.winfo_class() == "Checkbutton" and str(w.cget("text")) == defs["links"]["label"])
before = app.cfg["links"]
cb.invoke(); pump(0.1)
assert app.cfg["links"] is (not before) and app.cfg["opt_recent"][0] == "links"
app._fill_options_menu(); assert app._options_menu.entrycget(0, "label") == "Recently changed"
# changing it from elsewhere (a command, the menu) updates the window's control
app._set_extra("links", before); pump(0.1)
assert app.option_var("links").get() is before
# a choice with a few values is a row of radio buttons; the clock has three
rb = [w for w in controls() if w.winfo_class() == "Radiobutton"]
assert {str(w.cget("text")) for w in rb} >= {"off", "my local time", "game time (US Eastern)"}
next(w for w in rb if str(w.cget("text")) == "my local time").invoke(); pump(0.1)
assert app.cfg["clock"] == "real" and app.cfg["opt_recent"][0] == "clock"
next(w for w in rb if str(w.cget("text")) == "off").invoke()
# a long choice is a drop-down list
page("Logging and scrollback")
mb = [w for w in controls() if w.winfo_class() == "Menubutton"]
assert len(mb) >= 2, "scrollback length and backscroll lines are drop-downs"
menu = top.nametowidget(str(mb[0].cget("menu")))
last = menu.index("end"); menu.invoke(last); pump(0.1)
assert app.cfg["scrollback_lines"] == defs["scrollback_lines"]["values"][-1], app.cfg["scrollback_lines"]
app._set_extra("scrollback_lines", defs["scrollback_lines"]["values"][0]); pump(0.1)
assert str(mb[0].cget("text")) == defs["scrollback_lines"]["words"][defs["scrollback_lines"]["values"][0]], "the drop-down follows a change from elsewhere"
# the screen reader page: a timed-reading drop-down and the combat lines button
page("Screen reader")
labels = [str(w.cget("text")) for w in controls()]
assert "Screen reader: combat lines..." in labels
mb = [w for w in controls() if w.winfo_class() == "Menubutton"]
menu = top.nametowidget(str(mb[-1].cget("menu"))) if len(mb) > 1 else top.nametowidget(str(mb[0].cget("menu")))
app.set_sr_interval(30); pump(0.1)
assert app.cfg["opt_recent"][0] == "@sr_interval"

# find: matches by words in the label or the topic, across pages; clears back to the page
search = win["search"]
search.delete(0, "end"); search.insert(0, "scan"); search.event_generate("<KeyRelease>"); pump(0.2)
texts = [str(w.cget("text")) for w in walk(top) if w.winfo_class() in ("Menubutton", "Label", "Checkbutton")]
assert any("scanlines" in t.lower() or "CRT" in t for t in texts), texts
search.delete(0, "end"); search.insert(0, "xyzzy"); pump(0.2)
assert any("No setting matches" in str(w.cget("text")) for w in walk(top) if w.winfo_class() == "Label")
search.delete(0, "end"); pump(0.2)
assert any(str(w.cget("text")) == "Screen reader" for w in walk(top) if w.winfo_class() == "Label"), "back to the page"

# closing
top.event_generate("<Escape>"); pump(0.3)
assert app._settings_win is None and not top.winfo_exists()
# the DOS look keeps its own menu
app.set_dos_mode(True); pump(0.4)
app.open_settings(); pump(0.3)
assert app._overlay_open(), "the DOS Options menu opens instead"
app.dos_close_overlay(); app.set_dos_mode(False); pump(0.3)
root.destroy()
print("settings tests OK")
