"""The emoji picker: search, the window in both looks, and what ends up in the entry box (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import emojipick as ep
import sanctuary as sc
import tkinter as tk

grin, heart = chr(0x1F600), chr(0x2764)
cat = ep.catalog()
assert len(cat) > 200 and len({c for c, _n, _t in cat}) == len(cat), "every emoji once"
assert all(len(c) == 1 for c, _n, _t in cat)
assert ep.search("")[0][0] and len(ep.search("")) <= 300 and len(ep.search("")) < len(cat), "blank: the familiar ones"
hits = ep.search("grinning")
assert hits and hits[0][0] == grin and "grinning" in hits[0][1], hits[:3]
assert any(c == heart or "heart" in n for c, n in ep.search("heart")), "by part of a name"
assert ep.search("face smil") and all("face" in n or "smil" in n for _c, n in ep.search("face smil")[:5]), "every word must match"
assert ep.search(":fire:") and ep.search("FIRE") == ep.search("fire"), "colons and case do not matter"
assert ep.search("zzzzqqq") == [] and ep.search(None) == ep.search("")
assert len(ep.search("e")) <= 300

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x700+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


pump(0.3)
win = app.open_emoji_picker(); pump(0.3)
assert win.winfo_exists() and app._emoji_win is win and win._search.get() == ""
assert app.open_emoji_picker() is win, "one picker at a time"
text = [w for w in win.winfo_children()[1].winfo_children() if isinstance(w, tk.Text)][0]
assert len(text.get("1.0", "end").split()) > 50, "the familiar ones are listed"
# searching
win._search.delete(0, "end"); win._search.insert(0, "grinning"); win._render(); pump(0.2)
assert text.get("1.0", "end").split()[0] == grin
# clicking one puts it in the entry box where the cursor is
app.input.delete(0, "end"); app.input.insert(0, "hi "); app.input.icursor("end")
bb = text.bbox("1.0")
assert bb, "the first emoji is on screen"
text.event_generate("<Button-1>", x=bb[0] + 2, y=bb[1] + 2); pump(0.2)
assert app.input.get() == "hi " + grin, repr(app.input.get())
# Enter in the search box adds the first match; it is sent as :name: with the converter on
win._search.event_generate("<Return>"); pump(0.2)
assert app.input.get() == "hi " + grin + grin
sent = []
app.conn = type("C", (), {"gen": 0, "send": lambda self, b: sent.append(b) or True, "close": lambda *a: None})()
app.connected = True
app.cfg["emoji"] = True
app._on_enter(None); pump(0.2)
assert sent[-1] == b"hi :grinning::grinning:" + bytes([13, 10]), sent[-1]
# /emoji with words lists matches and opens the picker with them
win.destroy(); pump(0.2); assert app._emoji_win is None
app._local("/emoji heart"); pump(0.3)
assert "Emoji matching 'heart'" in app.out.get("1.0", "end") and app._emoji_win is not None
assert app._emoji_win._search.get() == "heart"
app._emoji_win.event_generate("<Escape>"); pump(0.2); assert app._emoji_win is None

# the DOS look: ask what to look for, then pick from the list
app.set_dos_mode(True); pump(0.5)
app.input.delete(0, "end")
app.open_emoji_picker(); pump(0.3)
assert app._overlay_open(), "a dialog asks what to look for"
app.dos_close_overlay(); pump(0.2)
app._dos_emoji_list("grinning"); pump(0.3)
assert app._overlay_open()
menu = app._overlay
assert menu._items[0]["label"].endswith(grin) and menu._items[0]["action"]
menu._items[0]["action"](); pump(0.3)
assert app.input.get() == grin, repr(app.input.get())
app.dos_close_overlay(); pump(0.2)
app._dos_emoji_list("zzzzqqq"); pump(0.3)
assert "No emoji match" in app.out.get("1.0", "end") and app._overlay_open(), "no match: ask again"
app.dos_close_overlay()
app.set_dos_mode(False); pump(0.3)

# the hotkey is in the table, and help lists it
assert any(a == "emoji" and shown == "Alt-E" for a, _t, shown in app.hotkey_table())
assert any("Emoji picker" in what for _k, what in app.help_key_lines())

root.update(); root.destroy()
print("emoji picker tests OK")
