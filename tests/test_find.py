"""Find (Ctrl+F) and find next (Ctrl+Shift+F) in the main text, from the bottom or from the top (no network)."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import extras
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1250x720+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def hit():
    """(line, matched text) of the highlighted match, or None."""
    r = app.out.tag_ranges("findhit")
    return (int(str(r[0]).split(".")[0]), app.out.get(r[0], r[1])) if r else None


def notice():
    return app.notice.cget("text")


pump(0.4)
assert extras.HOTKEYS["find"][1] == "Ctrl-F" and extras.HOTKEYS["find_next"][1] == "Ctrl-Shift-F"
assert extras.parse_hotkey("Ctrl-Shift-F")[0] == "<Control-Shift-f>"
assert app.find_from() == "bottom" and app.cfg["find_from"] == "bottom"
assert sc.clean_settings({"host": "x", "find_from": "sideways"})["find_from"] == "bottom"
assert sc.clean_settings({"host": "x", "find_from": "top"})["find_from"] == "top"

app.clear()
for t in ("Alpha one", "beta", "alpha two", "gamma", "ALPHA three", "-dash here", "delta"):
    app._append([(t + "\n", None)])

# from the bottom (the default): the newest match first, then older ones, then round again
app.find_set_term("alpha")
assert app.find_next() and hit() == (5, "ALPHA"), hit()          # (ignoring case)
assert "Found 'alpha'" in notice() and "bottom" in notice()
assert app.find_next() and hit() == (3, "alpha")
assert app.find_next() and hit() == (1, "Alpha")
assert app.find_next() and hit() == (5, "ALPHA") and "Wrapped" in notice(), notice()
# it scrolled to the match, and drew it in reverse colours
assert app.out.tag_cget("findhit", "background") == str(app.out.cget("foreground"))
assert app.out.tag_cget("findhit", "foreground") == str(app.out.cget("background"))

# from the top: the oldest first, then newer ones
app.find_set_from("top")
assert app.cfg["find_from"] == "top" and json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))["find_from"] == "top"
assert app.find_next() and hit() == (1, "Alpha")
assert app.find_next() and hit() == (3, "alpha")
assert app.find_next() and hit() == (5, "ALPHA")
assert app.find_next() and hit() == (1, "Alpha") and "Wrapped" in notice()
app.find_set_from("bottom")

# a new word starts over; nothing found says so and clears the mark
app.find_set_term("delta"); assert app.find_next() and hit() == (7, "delta")
app.find_set_term("zzz"); assert app.find_next() is False and hit() is None and "Not found: zzz" in notice()
app.find_set_term("-dash"); assert app.find_next() and hit() == (6, "-dash"), "a word that starts with a dash is not an option"
app.find_set_term("a b" + chr(10) + "c"); assert "\n" not in app._find["term"]

# several hits on one line, one after the other
app.clear(); app._append([("ab ab ab\n", None)])
app.find_set_term("ab")
spots = []
for _ in range(4):
    app.find_next(); spots.append(str(app.out.tag_ranges("findhit")[0]))
assert spots == ["1.6", "1.3", "1.0", "1.6"], spots

# match case: off by default (ignores case), on only finds the same capitals; changing it starts the search over
assert app.find_case() is False and app.cfg["find_case"] is False
assert sc.clean_settings({"host": "x", "find_case": "yes"})["find_case"] is False
app.clear()
for t in ("Alpha one", "alpha two", "ALPHA three"):
    app._append([(t + "\n", None)])
app.find_set_term("alpha")
app.find_set_case(True)
assert app.cfg["find_case"] is True and json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))["find_case"] is True
assert app.find_next() and hit() == (2, "alpha")
assert app.find_next() and hit() == (2, "alpha") and "Wrapped" in notice(), "the only exact match: round again onto itself"
app.find_set_term("Alpha"); assert app.find_next() and hit() == (1, "Alpha")
app.find_set_term("alpha"); app.find_set_case(False)
assert app.find_next() and hit() == (3, "ALPHA"), "off again: every capital counts, from the bottom"
app.find_set_term("Alp"); app.find_set_case(True); app.find_next(); assert hit() == (1, "Alp")
app.find_set_term("ALP"); assert app.find_next() and hit() == (3, "ALP")
app.find_set_term("aLP"); assert app.find_next() is False and "Not found" in notice()
app.find_set_case(False)

# the keys: Ctrl+F opens the box (with what is selected in it), Ctrl+Shift+F is next
app.clear()
for t in ("one fish", "two fish", "red fish", "blue fish"):
    app._append([(t + "\n", None)])
app._find["term"], app._find["pos"] = "", None
app.out.tag_add("sel", "2.4", "2.8")
app.input.focus_force(); pump(0.2)
app.input.event_generate("<Control-f>"); pump(0.4)
win = app._find["win"]
assert win is not None and win.winfo_exists() and win._term.get() == "fish", (win and win._term.get())
assert win._from.get() == "bottom" and [r.cget("text") for r in win._radios] == ["from the bottom (newest first)", "from the top (oldest first)"]
win._entry.event_generate("<Return>"); pump(0.3)
assert hit() == (4, "fish") and win._msg.cget("text") == "Found it."
app.input.focus_force(); pump(0.2)
app.input.event_generate("<Control-Shift-F>"); pump(0.3)
assert hit() == (3, "fish"), hit()
app.input.event_generate("<Control-Shift-f>"); pump(0.3)
assert hit() == (2, "fish"), hit()
# Match case: a tick box in the window
assert win._case.get() is False and win._matchcase.cget("text") == "Match case"
win._matchcase.invoke(); pump(0.2)
assert app.find_case() is True and app.cfg["find_case"] is True
win._matchcase.invoke(); pump(0.2)
assert app.find_case() is False
# the radio: from the top, remembered
win._radios[1].invoke(); pump(0.2)
assert app.find_from() == "top" and app.cfg["find_from"] == "top"
win._entry.focus_force(); pump(0.2)
win._entry.event_generate("<Return>"); pump(0.3)
assert hit() == (1, "fish"), "starts again from the top when the direction changes"
win._entry.event_generate("<Return>"); pump(0.3)
assert hit() == (2, "fish")
# Ctrl+F again just brings the box back; Escape closes it and clears the mark
app.input.focus_force(); app.input.event_generate("<Control-f>"); pump(0.3)
assert app._find["win"] is win
win._entry.event_generate("<Escape>"); pump(0.3)
assert app._find["win"] is None and hit() is None
# Ctrl+Shift+F with nothing to look for opens the box
app._find["term"] = ""
app.input.event_generate("<Control-Shift-F>"); pump(0.4)
assert app._find["win"] is not None
app._find["win"]._close(); pump(0.2)
app.find_set_from("bottom")

# /find
app._local("/find red"); pump(0.3)
assert hit() == (3, "red")
app.find_set_term("fish"); app._find["pos"] = None
app._local("/findnext"); pump(0.2)
assert hit() == (4, "fish")
app._local("/find"); pump(0.3)
assert app._find["win"] is not None
app._find["win"]._close(); pump(0.2)

# the hotkey editor knows the two keys, and they can be changed
rows = {a: (t, s) for a, t, s in app.hotkey_table()}
assert rows["find"] == ("Find in the text", "Ctrl-F") and rows["find_next"] == ("Find next", "Ctrl-Shift-F"), rows

# each world searches its own text
s2 = app.open_new_world("Other"); pump(0.4)
app._append([("only in the second world: fish\n", None)])
app._find["term"], app._find["pos"] = "fish", None
assert app.find_next() and s2.out.tag_ranges("findhit") and not app.sessions[0].out.tag_ranges("findhit")
app.goto_world(1); pump(0.3)
assert app.find_next() and app.out.tag_ranges("findhit") and hit() == (4, "fish")
app.close_world(s2); pump(0.2)

# the DOS look: a dialog with the word and a tick for "from the top"
app.set_dos_mode(True); pump(0.6)
app._find["term"], app._find["pos"] = "", None
app.find_set_from("bottom")
app.root.event_generate("<Control-f>"); pump(0.4)
d = app._overlay
labels = [f.get("label") for f in d._fields]
assert d is not None and labels == ["Find", "Start from the top (off: from the bottom)", "Match case", "Search panes"], labels
d.close()
d._on_result("find", {"term": "fish", "top": True}); pump(0.4)
assert app.find_from() == "top" and hit() == (1, "fish"), (app.find_from(), hit())
app.find_set_from("bottom")
app.set_dos_mode(False); pump(0.5)

root.update(); root.destroy()
print("find tests OK")
