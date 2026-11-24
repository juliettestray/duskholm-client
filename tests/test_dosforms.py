"""DOS look: pick-from-a-list fields, the paragraph editor, the gradient maker and the customize form
(modes, lists, interface mode against pretend game output)."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import colortools as ct
import custom
import dosui
import dosgrad
import tkinter as tk

home = tempfile.mkdtemp()
os.environ["USERPROFILE"] = os.environ["HOME"] = home
sc.SETTINGS_PATH = os.path.join(home, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
json.dump({"ui_mode": "dos"}, open(sc.SETTINGS_PATH, "w"))
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x720+10+10")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def key(w, ks):
    w.event_generate("<%s>" % ks); pump(0.35)


def overlay():
    return app._overlay if app._overlay_open() else None


def focus_field(d, k):
    i = [f["key"] for f in d._fields].index(k)
    d._set_focus(d._stops.index(("field", i))); pump(0.1)


def focus_ed(d, kind, what=None):
    d._set_focus(d._order.index((kind, what))); pump(0.1)


def menu_pick(label):
    m = overlay(); assert isinstance(m, dosui.DosMenu), type(m)
    names = [it["label"] if it else None for it in m._items]
    m.select(names.index(next(n for n in names if n and n.startswith(label)))); pump(0.1)
    key(m, "Return")


pump(0.8)
assert app.dos
sent = []
app.conn = type("C", (), {"send": lambda self, b: sent.append(b.decode().rstrip("\r\n")) or True, "close": lambda self, *a: None})()
app.connected = True

# ---- the dialog field type itself
got = []
d = dosui.DosDialog(app.root, "T", [{"key": "a", "label": "Pick", "type": "pick", "value": "one", "width": 12},
                                    {"key": "b", "label": "Text", "type": "text", "value": "hello", "width": 10}],
                    [("OK", "ok")], app._dc(), app.f_norm, lambda r, v: got.append((r, v)), width=40)
app._overlay = d; d.open(); pump(0.3)
assert d.values() == {"a": "one", "b": "hello"}
key(d, "Return")
assert got and got[0][0] == ("pick", "a") and got[0][1]["a"] == "one", got
# a click on the field does the same
got.clear(); d = dosui.DosDialog(app.root, "T", [{"key": "a", "label": "Pick", "type": "pick", "value": "x", "width": 12}],
                                 [("OK", "ok")], app._dc(), app.f_norm, lambda r, v: got.append(r), width=40)
app._overlay = d; d.open(); pump(0.3)
col, row = d._hits[0][2] + 1, d._hits[0][4]
d._on_click(type("E", (), {"x": col * d.cw + 2, "y": row * d.lh + 2})()); pump(0.2)
assert got == [("pick", "a")], got

# ---- the paragraph editor
done = []
ed = app.dos_edit_text("Description", "first\nsecond", lambda t: done.append(t)); pump(0.3)
assert isinstance(ed, dosui.DosTextEditor) and ed.is_open() and app._overlay_open()
assert ed.text() == "first\nsecond" and ed._cv.focus_get() is ed._cv
ed._cv.insert("end", "\nthird"); ed._cv.event_generate("<Control-s>"); pump(0.3)
assert done == ["first\nsecond\nthird"] and not app._overlay_open(), "Ctrl-S keeps the text"
ed = app.dos_edit_text("Description", "keep me", lambda t: done.append(t)); pump(0.3)
ed._cv.insert("end", " changed"); ed._cv.event_generate("<Escape>"); pump(0.3)
assert done[-1] is None and not app._overlay_open(), "Esc throws the changes away"
ed = app.dos_edit_text("x", "", lambda t: done.append(t)); pump(0.2)
app.input.focus_force(); pump(0.2); app.input.event_generate("<Escape>"); pump(0.3)
assert not app._overlay_open(), "Esc closes it even when focus strayed"

# ---- gradient maker: swatches you can see, lists behind Enter
app._grad_state = {"pattern": "Fire", "mode": "stretch", "text": "", "prefix": "", "smooth": True}
d = app.open_gradient(); pump(0.4)
assert isinstance(d, dosgrad.DosGradientEditor) and d._stops_list == ct.PRESETS["Fire"] and d._pattern == "Fire"
focus_ed(d, "pick", "pattern"); key(d, "Return")
m = overlay(); assert isinstance(m, dosui.DosMenu)
labels = [it["label"] for it in m._items if it]
assert "Fire" in labels and "Rainbow" in labels and "Create new..." in labels and "Import a shared one..." in labels
assert "Delete one of mine..." not in labels, "nothing of mine to delete yet"
assert m._items[labels.index("Fire")].get("swatch"), "each pattern shows a colour swatch"
menu_pick("Ocean"); pump(0.4)
assert app._grad_state["pattern"] == "Ocean"
d = overlay(); assert d._pattern == "Ocean" and d._stops_list == ct.PRESETS["Ocean"]
focus_ed(d, "pick", "mode"); key(d, "Return")
m = overlay(); labels = [it["label"] for it in m._items if it]
assert any(l.startswith("edges") and "middle" in l for l in labels), labels
menu_pick("edges"); pump(0.4)
assert app._grad_state["mode"] == "edges" and overlay()._mode == "edges"
# create a pattern by typing colours
d = overlay(); focus_ed(d, "pick", "pattern"); key(d, "Return"); menu_pick("Create new"); pump(0.4)
d = overlay(); assert isinstance(d, dosui.DosDialog)
d._fields[0]["entry"].insert(0, "My Blues"); d._fields[1]["entry"].insert(0, "17 21 27 #00ccff")
d._press(0); pump(0.5)
assert [g["name"] for g in app.cfg["gradients"]] == ["My Blues"] and len(app.cfg["gradients"][0]["colours"]) == 4
assert app._grad_state["pattern"] == "My Blues" and overlay()._pattern == "My Blues"
# a bad one keeps the dialog open with the reason
d = overlay(); focus_ed(d, "pick", "pattern"); key(d, "Return"); menu_pick("Create new"); pump(0.4)
d = overlay(); d._fields[0]["entry"].insert(0, "Bad"); d._fields[1]["entry"].insert(0, "999 nonsense")
d._press(0); pump(0.5)
d = overlay(); assert isinstance(d, dosui.DosDialog) and "Colours" in [f["label"] for f in d._fields] and len(app.cfg["gradients"]) == 1
d._press(1); pump(0.4)                                     # Cancel goes back to the gradient maker
# share and import
d = overlay(); assert isinstance(d, dosgrad.DosGradientEditor) and d._title == "Gradient"
d._press([b["result"] for b in d._buttons].index("share")); pump(0.5)
assert app.root.clipboard_get().startswith("sgrad1:My Blues:17,21,27,"), app.root.clipboard_get()
line = app.root.clipboard_get()
app.delete_pattern("My Blues"); assert app.cfg["gradients"] == []
d = overlay(); focus_ed(d, "pick", "pattern"); key(d, "Return"); menu_pick("Import a shared"); pump(0.4)
d = overlay(); d._fields[0]["entry"].insert(0, "garbage"); d._press(0); pump(0.5)
d = overlay(); assert "not a shared gradient" in d._message and app.cfg["gradients"] == []
d._fields[0]["entry"].delete(0, "end"); d._fields[0]["entry"].insert(0, "here: " + line); d._press(0); pump(0.5)
assert [g["name"] for g in app.cfg["gradients"]] == ["My Blues"] and app._grad_state["pattern"] == "My Blues"
d = overlay(); focus_ed(d, "pick", "pattern"); key(d, "Return")
assert "Delete one of mine..." in [it["label"] for it in overlay()._items if it]
menu_pick("Delete one"); pump(0.4); menu_pick("My Blues"); pump(0.5)
assert app.cfg["gradients"] == []
app.dos_close_overlay(); pump(0.2)

# ---- editing the colours: keyboard
app._grad_state = {"pattern": "Fire", "mode": "stretch", "text": "hello world", "prefix": "", "smooth": True}
d = app.open_gradient(); pump(0.4); d._cv.focus_force(); pump(0.1)
n0 = len(d._stops_list); assert d._sel == 0 and d._focus_is("stops")
key(d, "Right"); assert d._sel == 1
key(d, "End"); assert d._sel == n0 - 1
key(d, "Insert"); assert len(d._stops_list) == n0 + 1 and d._pattern == "custom" and d._sel == n0
key(d, "Delete"); assert len(d._stops_list) == n0 and d._stops_list == ct.PRESETS["Fire"], "an added stop between neighbours can be removed again"
d._stops_list[:] = [196, 226, 46]; d._sel = 0
d._cv.event_generate("<Control-Right>"); pump(0.3); assert d._stops_list == [226, 196, 46] and d._sel == 1
# the palette: Enter on a swatch
key(d, "Return"); pal = d._palette
assert isinstance(pal, dosgrad.DosPalette) and pal.is_open() and pal._current == 196
key(pal, "Right"); key(pal, "Return")
assert not pal.is_open() and d._stops_list[1] != 196 and d._stops_list[0] == 226 and d._stops_list[2] == 46 and d._pattern == "custom"
changed = d._stops_list[1]
key(d, "Return"); pal = d._palette; key(pal, "Escape")
assert d._stops_list[1] == changed, "Esc in the palette keeps the colour"
# typing a hex colour snaps to the nearest xterm colour
key(d, "Return"); pal = d._palette
pal._var.set("#ff8800"); pal._hex_typed(apply=True); pump(0.3)
assert d._stops_list[1] == ct.from_hex("#ff8800")[0] == 208
# the mouse: a swatch, then the same swatch again opens the palette; [+] and [-]
d._cv.focus_force(); pump(0.1)
def click(w, kind, what=None):
    hit = next(h for h in w._hits if h[0] == kind and (what is None or h[1] == what))
    ev = type("E", (), {"x": hit[2] * w.cw + 2, "y": hit[4] * w.lh + 2})()
    w._on_click(ev); pump(0.4)
click(d, "stop", 2); assert d._sel == 2 and d._palette is None
n1 = len(d._stops_list); click(d, "add"); assert len(d._stops_list) == n1 + 1
click(d, "del"); assert len(d._stops_list) == n1
click(d, "stop", 2); pal = d._palette; assert isinstance(pal, dosgrad.DosPalette), "clicking the selected one opens the palette"
hit = next(h for h in pal._hits if h[0] == "cell" and h[1] == (4, 3))
pal._on_click(type("E", (), {"x": hit[2] * pal.cw + 2, "y": hit[4] * pal.lh + 2})()); pump(0.4)
assert d._stops_list[2] == pal._index((4, 3)) and not pal.is_open(), "a click on a palette colour chooses it"
# the live bar and preview are drawn, and the whole editor fits
assert d._stops_list and d._wpx <= app._holder.winfo_width() and d._hpx <= app._holder.winfo_height()
# Reverse and Save
st0 = list(d._stops_list)
d._press([b["result"] for b in d._buttons].index("reverse")); pump(0.5)
d = overlay(); assert d._stops_list == st0[::-1], "reverse turns the colours round"
d._press([b["result"] for b in d._buttons].index("save")); pump(0.5)
sv = overlay(); assert isinstance(sv, dosui.DosDialog) and sv._title == "Save pattern"
sv._fields[0]["entry"].insert(0, "Mine"); sv._press(0); pump(0.6)
assert [g["name"] for g in app.cfg["gradients"]] == ["Mine"] and app.cfg["gradients"][0]["colours"] == st0[::-1]
d = overlay(); assert d._pattern == "Mine"
app.delete_pattern("Mine"); app.dos_close_overlay(); pump(0.2)

# ---- the customize form
app._cust_mode, app._cust_type, app._cust_values = "cli", "clothing", custom.blank()
d = app._dos_customize(custom.blank(), 1); pump(0.4)
types = {f["key"]: f["type"] for f in d._fields}
assert types["_mode"] == types["_type"] == types["size"] == types["layer"] == "pick" and types["item"] == types["names"] == "text"
assert "itype" not in types and "count" not in types, "game-editor fields are hidden in command-line mode"
assert all(len(f["label"]) <= d._labw for f in d._fields) and "Item word" in [f["label"] for f in d._fields]
focus_field(d, "size"); key(d, "Return"); menu_pick("large"); pump(0.4)
assert app._cust_values["size"] == "large" and overlay()._fields[[f["key"] for f in overlay()._fields].index("size")]["shown"] == "large"
d = overlay(); focus_field(d, "layer"); key(d, "Return"); menu_pick("3"); pump(0.4)
assert app._cust_values["layer"] == "3"
d = overlay(); d._fields[[f["key"] for f in d._fields].index("names")]["entry"].insert(0, "red scarf")
d._press([b["result"] for b in d._buttons].index("next")); pump(0.5)
d = overlay(); assert "Page 2" in d._title or "page 2" in d._title
assert app._cust_values["names"] == "red scarf" and app._cust_values["size"] == "large", "page 1 is remembered"
focus_field(d, "cover"); key(d, "Return")
m = overlay(); labels = [it["label"] for it in m._items if it]
assert labels[:3] == ["hands", "forearms", "upperarms"] and len(labels) == 19 and labels[-1] == "Done"
menu_pick("neck"); pump(0.4)
m = overlay()
neck_items = [it for it in m._items if it and it["label"] == "neck"]
assert neck_items[0]["checked"], "ticked"
menu_pick("chest"); pump(0.4)
menu_pick("Done"); pump(0.5)
assert app._cust_values["cover"] == "neck, chest", app._cust_values["cover"]
d = overlay(); assert d._fields[0]["shown"] == "neck, chest"
focus_field(d, "description"); key(d, "Return")
ed = overlay(); assert isinstance(ed, dosui.DosTextEditor)
ed._cv.insert("1.0", "Soft silk.\nIt smells of rain."); ed._cv.event_generate("<Control-s>"); pump(0.5)
assert app._cust_values["description"] == "Soft silk.\nIt smells of rain."
d = overlay(); assert d._fields[[f["key"] for f in d._fields].index("description")]["shown"] == "Soft silk. (+1 lines)"
# send in command-line mode
app._cust_values["item"] = "scarf"; sent.clear()
d._press([b["result"] for b in d._buttons].index("send")); pump(0.5)
assert sent[0] == "customize scarf names red scarf" and "customize scarf cover clear" in sent and "customize scarf cover chest" in sent
assert sent[-4:] == ["customize scarf description", "Soft silk.", "It smells of rain.", "@"], sent
app.dos_close_overlay()

# ---- interface mode: against pretend game output
app._cust_mode = "interface"
d = app._dos_customize(dict(custom.blank(), mode="interface", itype="Clothing", cost="5", names="red scarf",
                            shortstring="a red scarf", cover="neck"), 1); pump(0.4)
types = {f["key"]: f["type"] for f in d._fields}
assert "item" not in types and types["itype"] == "pick" and "count" in types, "interface mode shows the editor's fields"
focus_field(d, "itype"); key(d, "Return")
labels = [it["label"] for it in overlay()._items if it]
assert labels[0] == "(leave alone)" and labels[1:] == list(custom.ITEM_TYPES)
menu_pick("Phone"); pump(0.4)
assert app._cust_values["itype"] == "Phone"
sent.clear()
ok, msg = app.send_customize(dict(app._cust_values), back=lambda: None)
assert ok and sent == ["type Phone", "cost 5", "names red scarf", "short a red scarf", "cover clear", "cover neck"], sent
assert "customize" not in " ".join(sent), "no 'customize <item>' prefix in the game's editor"
app.dos_close_overlay(); pump(0.2)
screen_before = app.out.get("1.0", "end")
for l in ("Done.", "Object", "Type: Phone.", "Cost: 5.000000", "Size: Small", "Names: red scarf", "Short: a red scarf",
          "Long: ", "Description:", "", "Wear: ", "Coverage cleared.", "Done.", "Object", "Type: Phone.", "Cost: 5.000000",
          "Names: red scarf", "Short: a red scarf", "Description:", "A nice phone.", "Wear: ",
          "Bob says, 'hello there'", "Options are: hands, forearms and clear"):
    app._on_data((l + "\n\r").encode())
pump(0.3)
mid = app.out.get("1.0", "end")
assert "Names: red scarf" not in mid and "Cost: 5.000000" not in mid, "the editor's chatter is gathered, not scrolled"
assert app._iface is not None
pump(1.6)
after = app.out.get("1.0", "end")
assert after.count("Names: red scarf") == 1 and after.count("Object") == 1, "only the finished item is shown"
assert "A nice phone." in after and "Bob says, 'hello there'" in after and "Options are: hands" in after, "chat and errors are not lost"
assert "Coverage cleared." not in after and "Size: Small" not in after
rv = overlay(); assert isinstance(rv, dosui.DosDialog) and rv._title == "Game item editor"
sent.clear(); rv._press([b["result"] for b in rv._buttons].index("done")); pump(0.4)
assert sent == ["done"], "Done sends 'done' to the game"
# not in the editor: nothing is hidden
app._cust_values = dict(custom.blank(), mode="interface", names="x")
sent.clear(); ok, m = app.send_customize(app._cust_values)
for l in ("You can't do that.", "What?"):
    app._on_data((l + "\n\r").encode())
pump(1.6)
after = app.out.get("1.0", "end")
assert "You can't do that." in after and "What?" in after and "did not see the game's item editor" in after
assert not app._overlay_open()
# nothing to send / not connected
assert not app.send_customize(dict(custom.blank(), mode="interface"))[0]
app.connected = False
assert app.send_customize(dict(custom.blank(), mode="interface", names="x"))[1] == "Not connected."
app.connected = True; app._cust_mode = "cli"


# ---- one page when the screen is big enough, two when it must be
real_height = app.root.winfo_height
app.root.winfo_height = lambda: 3000
assert len(app._customize_pages("cli")) == 1 and len(app._customize_pages("interface")) == 1
d = app._dos_customize(custom.blank(), 1); pump(0.4)
keys = [f["key"] for f in d._fields]
assert d._title == "Customize" and "item" in keys and "cover" in keys and "description" in keys and "_mode" in keys
assert [b["result"] for b in d._buttons] == ["send", "save", "book", "clear", "cancel"], "no Next / Back on one page"
d2 = app._dos_customize(custom.blank(), 2); pump(0.3)
assert overlay() is d or overlay()._title == "Customize", "asking for page 2 of a one-page form shows the form"
app.dos_close_overlay(); pump(0.2)
app.root.winfo_height = lambda: 300
pages = app._customize_pages("cli"); assert len(pages) == 2 and pages[0][0] == "item" and pages[1][0] == "cover"
d = app._dos_customize(custom.blank(), 1); pump(0.4)
assert "page 1 of 2" in d._title and "next" in [b["result"] for b in d._buttons]
# Alt+Right is Next, Alt+Left is Back
d.event_generate("<Alt-Right>") if False else None
d._cv.event_generate("<Alt-Key>", keysym="Right"); pump(0.5)
d = overlay(); assert "page 2 of 2" in d._title, d._title
d._cv.event_generate("<Alt-Key>", keysym="Left"); pump(0.5)
d = overlay(); assert "page 1 of 2" in d._title
d._cv.event_generate("<Alt-Key>", keysym="Left"); pump(0.4)
assert not app._overlay_open(), "with no Back button, Alt+Left is Esc"
app.root.winfo_height = real_height

# ---- Alt+Left / Alt+Right in menus
app.dos_colors_menu(); pump(0.4)
m = overlay(); assert isinstance(m, dosui.DosMenu)
labels = [it["label"] if it else None for it in m._items]
m.select(labels.index(next(l for l in labels if l and l.startswith("Skin")))); pump(0.1)
m._cv.event_generate("<Alt-Key>", keysym="Right"); pump(0.5)
sk = overlay(); assert isinstance(sk, dosui.DosMenu) and sk is not m and any(it and it["label"] == "Plain" for it in sk._items), "Alt+Right goes into an entry that leads somewhere"
sk._cv.event_generate("<Alt-Key>", keysym="Left"); pump(0.5)
m2 = overlay(); assert isinstance(m2, dosui.DosMenu) and any(it and it["label"].startswith("Skin") for it in m2._items), "Alt+Left goes back to the menu it came from"
m2._cv.event_generate("<Alt-Key>", keysym="Left"); pump(0.4)
assert not app._overlay_open()
app.dos_options_menu(); pump(0.4)
m = overlay(); n_checked = sum(1 for it in m._items if it and it.get("checked"))
m._cv.event_generate("<Alt-Key>", keysym="Right"); pump(0.3)
assert overlay() is m and sum(1 for it in m._items if it and it.get("checked")) == n_checked, "Alt+Right does nothing on an entry that just flips a setting"
app.dos_close_overlay(); pump(0.2)

# a plain Left or Right (even with Num Lock on, which Windows reports as state 0x8) does NOT go back or forward
app.dos_colors_menu(); pump(0.4)
m = overlay(); labels = [it["label"] if it else None for it in m._items]
m.select(labels.index(next(l for l in labels if l and l.startswith("Skin")))); pump(0.1)
for st in (0, 0x8, 0x10, 0x2):
    m._cv.event_generate("<Key>", keysym="Left", state=st); pump(0.2)
    assert overlay() is m, "a plain Left leaves the menu alone (state %#x)" % st
    m._cv.event_generate("<Key>", keysym="Right", state=st); pump(0.2)
    assert overlay() is m, "a plain Right leaves the menu alone (state %#x)" % st
m._cv.event_generate("<Key>", keysym="Left", state=0x20000); pump(0.4)
assert overlay() is not m, "Alt+Left (state 0x20000) goes back"
app.dos_close_overlay(); pump(0.2)
d = app._dos_customize(custom.blank(), 1); pump(0.3)
if d is not None and d._title != "Customize":
    for st in (0, 0x8):
        d._cv.event_generate("<Key>", keysym="Right", state=st); pump(0.3)
        assert overlay() is d, "a plain Right does not change page"
app.dos_close_overlay(); pump(0.2)

# ---- choosing a skin must not leave menus stacked behind each other (Esc used to step through them)
def open_menus():
    return [w for w in app.root.winfo_children() if isinstance(w, dosui.DosMenu) and w.is_open()]
app.dos_colors_menu(); pump(0.4)
for name in ("Plain", "Moody", "Retro Amber"):
    menu_pick("Skin"); pump(0.4)
    menu_pick(name); pump(0.6)
    assert app._skin_name() == name and len(open_menus()) == 1, (name, len(open_menus()))
key(overlay(), "Escape"); pump(0.4)
assert not open_menus() and not app._overlay_open(), "one Esc closes it all"
app.set_skin("Retro DOS"); pump(0.3)
app.dos_skin_menu(); pump(0.4)
menu_pick("Plain"); pump(0.5)
assert not open_menus(), "picking from the skin menu (F5) closes it"

# ---- gradients in the paragraph editor
app._grad_state = {"pattern": "Fire", "mode": "stretch", "text": "", "prefix": "", "smooth": False}
kept = []
ed = app.dos_edit_text("Description", "Soft silk.\nIt smells of rain.", lambda t: kept.append(t)); pump(0.4)
ed._cv.event_generate("<Control-g>"); pump(0.6)
dlg = overlay(); assert isinstance(dlg, dosgrad.DosGradientEditor) and dlg._title == "Colour the text" and "all of the text" in dlg._message
assert not dlg._entry_keys, "no text boxes when the text is being edited elsewhere"
focus_ed(dlg, "pick", "pattern"); key(dlg, "Return"); menu_pick("Ocean"); pump(0.5)
dlg = overlay(); assert dlg._pattern == "Ocean" and "all of the text" in dlg._message, "the choice comes back to this editor, not the gradient maker"
focus_ed(dlg, "pick", "mode"); key(dlg, "Return"); menu_pick("cycle"); pump(0.5)
dlg = overlay(); dlg._press(0); pump(0.6)
ed = overlay(); assert isinstance(ed, dosui.DosTextEditor), "back in the editor"
txt = ed.text()
assert ct.strip_codes(txt) == "Soft silk.\nIt smells of rain." and txt.count("`") > 10 and txt.endswith("`x")
assert app._grad_state["pattern"] == "Ocean" and app._grad_state["mode"] == "cycle", "and it remembers what you chose"
pump(0.4)
assert ed._cv.tag_ranges("xcode") and any(t.startswith("xc") and t != "xcode" for t in ed._cv.tag_names()), "the codes are dimmed and the text is in colour"
colour = [t for t in ed._cv.tag_names() if t.startswith("xc") and t != "xcode"][0]
assert ed._cv.tag_cget(colour, "foreground").lower() in [c.lower() for c in ct.XTERM]
# a selection only
ed._cv.delete("1.0", "end"); ed._cv.insert("1.0", "plain COLOURED plain"); ed._cv.tag_add("sel", "1.6", "1.14")
ed._cv.event_generate("<Control-g>"); pump(0.6)
dlg = overlay(); assert "selected text" in dlg._message
dlg._press(0); pump(0.6); ed = overlay()
t2 = ed.text(); assert t2.startswith("plain `") and t2.endswith("`x plain") and ct.strip_codes(t2) == "plain COLOURED plain", t2
# take them off again
ed._cv.event_generate("<Control-k>"); pump(0.6)
ed = overlay(); assert isinstance(ed, dosui.DosTextEditor) and ed.text() == "plain COLOURED plain"
# cancel in the gradient dialog goes back to the editor unchanged
ed._cv.event_generate("<Control-g>"); pump(0.6); dlg = overlay(); dlg._press(1); pump(0.5)
ed = overlay(); assert isinstance(ed, dosui.DosTextEditor) and ed.text() == "plain COLOURED plain"
ed._cv.event_generate("<Control-s>"); pump(0.4)
assert kept == ["plain COLOURED plain"] and not app._overlay_open()
# the whole path through the customize form
d = app._dos_customize_pick("description", dict(custom.blank(), description="Soft silk."), 1); pump(0.5)
ed = overlay(); ed._cv.event_generate("<Control-g>"); pump(0.6); overlay()._press(0); pump(0.6)
overlay()._cv.event_generate("<Control-s>"); pump(0.6)
assert "`" in app._cust_values["description"] and ct.strip_codes(app._cust_values["description"]) == "Soft silk."
root.update(); root.destroy()
print("dos forms tests OK")
