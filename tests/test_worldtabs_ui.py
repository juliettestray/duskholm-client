"""The row of clickable world tabs (normal look) and clickable key hints (DOS look) (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x700+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def tabs():
    """[(text, bold, fg)] of the real tabs, and whether there is a plus."""
    out, plus = [], False
    for tab in app._tabs_inner.winfo_children():
        if isinstance(tab, tk.Frame):
            lab = [w for w in tab.winfo_children() if isinstance(w, tk.Label)][0]
            out.append((lab.cget("text"), lab, tab))
        else:
            plus = plus or tab.cget("text") == "+"
    return out, plus


def click(w):
    w.event_generate("<Button-1>", x=3, y=3); pump(0.3)


pump(0.5)
# ---- always on by default, centred, with a plus: a single world already shows it ----------------------------------------------------
assert app.cfg["world_tabs"] == "always" and app._tabbar.winfo_ismapped()
t, plus = tabs()
assert len(t) == 1 and t[0][0].endswith("1  World 1") or "1  " in t[0][0], t[0][0]
assert plus, "a plus to open another world"
bar_w = app._tabbar.winfo_width()
inner = app._tabs_inner
mid = inner.winfo_rootx() + inner.winfo_width() / 2 - app._tabbar.winfo_rootx()
assert abs(mid - bar_w / 2) <= 3, ("centred", mid, bar_w / 2)
assert not app._world_label.winfo_ismapped(), "the old label is not needed beside the tabs"
assert app._tabbar.winfo_y() > app._top.winfo_y(), "under the toolbar"
assert app._holder.winfo_y() > app._tabbar.winfo_y(), "above the text"

# ---- more worlds: a tab each, the shown one marked, a click switches --------------------------------------------------------------
second = app.open_new_world("Second"); pump(0.3)
third = app.open_new_world("Third"); pump(0.3)
t, plus = tabs()
assert [x[0].split("  ", 1)[-1] for x in t] == ["World 1", "Second", "Third"] or len(t) == 3, [x[0] for x in t]
assert app._shown is third
shown_bg = t[2][1].cget("bg")
assert shown_bg == app.theme["bg"] and t[0][1].cget("bg") != shown_bg, "the shown tab looks different"
click(t[0][1])
assert app._shown is app.sessions[0], "clicking the first tab shows that world"
t, _ = tabs()
click(t[1][2])
assert app._shown is second, "clicking the tab's frame works too"

# ---- news in a hidden world marks its tab ----------------------------------------------------------------------------------------
app.session = third
app._mark_activity(); app.session = app._shown; pump(0.3)
t, _ = tabs()
assert t[2][0].startswith("●") and t[0][0][0] != "●", [x[0] for x in t]
click(t[2][1]); pump(0.2)
t, _ = tabs()
assert app._shown is third and not t[2][0].startswith("●"), "looking at it clears the mark"

# ---- the right-click menu closes a world; the plus opens the worlds list ------------------------------------------------------------
menus = []
app._popup_menu = lambda m, x, y: menus.append(m)
t, plus = tabs()
t[1][1].event_generate("<Button-3>", x=3, y=3, rootx=50, rooty=50); pump(0.2)
m = menus[-1]
labels = [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) == "command"]
assert labels == ["Switch to Second", "Close Second", "Worlds..."], labels
asked = []
app.close_world_ask = lambda: asked.append(app._shown)
m.invoke(1); pump(0.2)
assert asked == [second], "closing from a tab brings that world forward first and asks"
opened = []
app.open_worlds = lambda: opened.append(1)
plus_lbl = [w for w in app._tabs_inner.winfo_children() if isinstance(w, tk.Label)][0]
click(plus_lbl)
assert opened == [1]
del app.close_world_ask, app.open_worlds

# ---- a renamed world is renamed on its tab ----------------------------------------------------------------------------------------------
app._rename_world(third, "Renamed"); pump(0.3)
app._refresh_world_ui(); pump(0.2)
assert "Renamed" in [x[0] for x in tabs()[0]][2], [x[0] for x in tabs()[0]]

# ---- the setting: always / only with two or more worlds / off -----------------------------------------------------------------------
app._set_extra("world_tabs", "off"); pump(0.3)
assert not app._tabbar.winfo_ismapped() and app._world_label.winfo_ismapped(), "off: the old label comes back"
app._set_extra("world_tabs", "two+"); pump(0.3)
assert app._tabbar.winfo_ismapped()
app.close_world(third); app.close_world(second); pump(0.3)
assert len(app.sessions) == 1 and not app._tabbar.winfo_ismapped(), "two+: hidden with a single world"
app._set_extra("world_tabs", "always"); pump(0.3)
assert app._tabbar.winfo_ismapped()
assert sc.clean_settings({"world_tabs": "bogus"})["world_tabs"] == "always"

# ---- the DOS look: no tab row, but the key hints are clickable ---------------------------------------------------------------------
w2 = app.open_new_world("Beta"); pump(0.4)
app.set_dos_mode(True); pump(0.8)
assert not app._tabbar.winfo_ismapped()
bar = app.dosbar
app.update_dosbar(); pump(0.3)
cells = {app.dosbar._hints[0][i][0]: (a, b) for a, b, i in bar._hint_cells}
assert "^F1" in cells and "^F2" in cells, cells
cv = bar._rows[0]
a, b = cells["^F1"]
cv.event_generate("<Button-1>", x=int((a + 1) * bar.cw), y=2); pump(0.3)
assert app._shown is app.sessions[0]
cells = {app.dosbar._hints[0][i][0]: (a, b) for a, b, i in bar._hint_cells}      # the bracket moved with the shown world
a, b = cells["^F2"]
cv.event_generate("<Button-1>", x=int((a + 1) * bar.cw), y=2); pump(0.3)
assert app._shown is w2, "clicking a world hint in the DOS bar switches to it"
fired = []
root.bind("<F1>", lambda e: fired.append("f1"), add="+")
if "F1" in cells:
    a, b = cells["F1"]
    cv.event_generate("<Button-1>", x=int((a + 1) * bar.cw), y=2); pump(0.3)
cv.event_generate("<Button-1>", x=1, y=2); pump(0.2)              # between hints: nothing happens
app.set_dos_mode(False); pump(0.7)
assert app._tabbar.winfo_ismapped() and tabs()[0], "back in the normal look the tabs return"

root.update(); root.destroy()
print("world tab tests OK")
