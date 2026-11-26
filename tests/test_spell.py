"""Spell checking: the Windows engine, which complaints are shown, and the three places it underlines."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import winspell, spelltext, spellterms, spellui
import sanctuary as sc
import tkinter as tk

# ---- the engine ----
sp = winspell.WinSpell.create()
assert sp is not None, "the Windows spell checker is not available on this machine"
text = "I recieve teh letter"
found = sp.check(text)
assert [text[a:b] for a, b, _k in found] == ["recieve", "teh"], found
assert "receive" in sp.suggest("recieve") and sp.check("This is fine.") == [] and sp.check("") == []
assert [text2[a:b] for text2 in ["the the cat"] for a, b, k in sp.check(text2) if k == "repeat"] == ["the"], sp.check("the the cat")
assert winspell.utf16_to_str_index("a\U0001F600bc", 3) == 2, "an emoji is two UTF-16 units but one character"
emo = "\U0001F600 recieve"
assert [emo[a:b] for a, b, _k in sp.check(emo)] == ["recieve"], "positions after an emoji line up"
assert sp.check("x" * 50000) is not None                           # (long input is bounded, never an error)

# ---- which complaints are shown ----
def words(t, allowed=frozenset(), prose=False):
    return [t[a:b] for a, b, _k in spelltext.find_problems(sp, t, allowed, prose)]
assert words("I recieve teh letter") == ["recieve", "teh"]
assert words("I recieve teh letter", {"teh"}) == ["recieve"], "your own words are left alone"
assert words("Welcome to Duskholm") == ["Duskholm"] and words("Welcome to Duskholm", set(spellterms.TERMS)) == []
assert "duskholm" in spellterms.TERMS and "the" not in spellterms.TERMS, "only words Windows does not know"
assert "elseborn" in spellterms.TERMS and "fleshformed" in spellterms.TERMS and "fleshforming" in spellterms.TERMS
assert words("see https://exampel.com/recieve now") == [], "links are skipped"
assert words("the OOC channel and GMCP") == [], "acronyms are skipped"
assert words("use /recieve or @teh or #tehh or %recieve") == [], "command and handle prefixes are skipped"
assert words("room12 recieve") == ["recieve"], "words with digits are not judged"
assert words("east", prose=True) == [] and words("recieve", prose=True) == [], "a lone command word is not checked"
assert words("get recieve", prose=True) == [], "two words is still a command"
assert words("say recieve", prose=True) == ["recieve"], "a talking command is checked"
assert words("get the recieve", prose=True) == ["recieve"], "three words is prose"
assert words("/emote recieve teh letter", prose=True) == [], "a / command is not checked"
assert words("east\nI recieve teh letter now", prose=True) == ["recieve", "teh"], "each line is judged on its own"
assert spelltext.reads_like_prose("'hello") and not spelltext.reads_like_prose("") and not spelltext.reads_like_prose("north")
assert spelltext.history_words(["Say Hello there", "get sword"]) >= {"say", "hello", "sword"}
assert spelltext.find_problems(None, "recieve") == []

# ---- the dictionary ----
assert spellui.clean_words(["Foo", "foo", "a", "x" * 50, "b4d", 5, None, " bar "]) == ["foo", "bar"]
c = sc.clean_settings({"host": "x", "spell_words": ["Zork", "zork", 7]})
assert c["spell_words"] == ["zork"] and sc.clean_settings({"host": "x", "spell_words": "no"})["spell_words"] == []
assert all(k in [e[0] for e in sc.EXTRA_BOOLS] for k in ("spell_input", "spell_notepad", "spell_custom"))
keys = [e[4] for e in sc.EXTRA_BOOLS + sc.EXTRA_CHOICES if e[4]]
assert len(keys) == len(set(keys)), "every DOS option hotkey is different"

# ---- the client ----
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
NOTES = os.path.join(tempfile.mkdtemp(), "notes.txt")
root = tk.Tk()
app = sc.App(root)
app.notes_path = lambda: NOTES
root.geometry("1200x700+20+20")
def pump(t=0.2):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)
def bad(w):
    out, r = [], w.tag_ranges("spell_bad")
    for i in range(0, len(r), 2):
        out.append(tk.Text.get(w, str(r[i]), str(r[i + 1])))
    return out
pump(0.4)
assert app.cfg["spell_input"] is False and app.cfg["spell_notepad"] is False and app.cfg["spell_custom"] is False

# the growing input box
app._set_extra("entry_grow", "3"); pump(0.4)
g = app._grow
assert app.input is g
app._set_extra("spell_input", True); pump(0.2)
g.focus_force(); g.delete(0, "end"); g.insert(0, "I recieve teh letter from Zorbulon and Duskholm"); g.event_generate("<KeyRelease>", keysym="x"); pump(0.8)
assert bad(g) == ["recieve", "teh", "Zorbulon"], (bad(g), "the game's own words are not underlined")
app.cfg["spell_words"] = ["zorbulon"]; app.spell_refresh_all(); pump(0.2)
assert bad(g) == ["recieve", "teh"], "your dictionary hides a word"
g.delete(0, "end"); g.insert(0, "recieve"); g.event_generate("<KeyRelease>", keysym="x"); pump(0.8)
assert bad(g) == [], "a one-word command is not underlined"
g.delete(0, "end"); g.insert(0, "say I recieve teh letter"); g.event_generate("<KeyRelease>", keysym="x"); pump(0.8)
assert bad(g) == ["recieve", "teh"]
# the right-click menu on a misspelled word
r = g.tag_ranges("spell_bad")
bb = g.bbox(str(r[0])); assert bb, "the word is on screen"
items = app._edit_items(g, bb[0] + 2, bb[1] + 2)
labels = [i[0] for i in items]
assert "receive" in labels and any(l.startswith("Add") for l in labels) and "Ignore all" in labels and "Cut" in labels, labels
[i for i in items if i[0] == "receive"][0][3](); pump(0.8)
assert tk.Text.get(g, "1.0", "end-1c") == "say I receive teh letter" and bad(g) == ["teh"]
r = g.tag_ranges("spell_bad"); bb = g.bbox(str(r[0]))
items = app._edit_items(g, bb[0] + 2, bb[1] + 2)
[i for i in items if i[0].startswith("Add")][0][3](); pump(0.8)
assert "teh" in app.cfg["spell_words"] and bad(g) == [], "added to my dictionary"
assert app._edit_items(g, 2000, 5)[0][0] == "Cut", "elsewhere: the usual menu"
g.delete(0, "end"); g.insert(0, "say the the cat sat"); g.event_generate("<KeyRelease>", keysym="x"); pump(0.8)
assert bad(g) == ["the"]
r = g.tag_ranges("spell_bad"); bb = g.bbox(str(r[0]))
items = app._edit_items(g, bb[0] + 2, bb[1] + 2)
assert items[0][0] == "Delete the repeated word"; items[0][3](); pump(0.5)
assert tk.Text.get(g, "1.0", "end-1c") == "say the cat sat", tk.Text.get(g, "1.0", "end-1c")
g.delete(0, "end"); g.insert(0, "say I recieve you"); g.event_generate("<KeyRelease>", keysym="x"); pump(0.8)
r = g.tag_ranges("spell_bad"); bb = g.bbox(str(r[0]))
[i for i in app._edit_items(g, bb[0] + 2, bb[1] + 2) if i[0] == "Ignore all"][0][3](); pump(0.5)
assert bad(g) == [], "ignored for this session"
# words already sent to the game are not second-guessed
app.history.append("say flurbo is my friend"); g.delete(0, "end"); g.insert(0, "say flurbo is here"); g.event_generate("<KeyRelease>", keysym="x"); pump(0.8)
assert bad(g) == []
# switched off: the underlines go; a plain one-line box never has any
app._set_extra("spell_input", False); pump(0.3)
assert bad(g) == []
app._set_extra("spell_input", True); g.delete(0, "end"); g.insert(0, "say I recieve teh now"); g.event_generate("<KeyRelease>", keysym="x"); pump(0.8)
app._set_extra("entry_grow", "off"); pump(0.4)
assert app.input is not g and not hasattr(app.input, "tag_ranges")
app._set_extra("spell_input", False)

# the notepad
app.open_notepad(); pump(0.3)
t = app._notepad["text"]
t.insert("1.0", "Dear diary, I mispel wrods in Duskholm.\nSecond line is fine.\n"); pump(0.2)
assert bad(t) == [], "off: nothing underlined"
app._set_extra("spell_notepad", True); pump(0.6)
assert bad(t) == ["mispel", "wrods"], bad(t)
t.insert("end", "Another mispelled word here."); t.event_generate("<KeyRelease>", keysym="x"); pump(0.8)
assert bad(t)[-1] == "mispelled"
r = t.tag_ranges("spell_bad"); bb = t.bbox(str(r[0]))
labels = [i[0] for i in app._spell_items(t, bb[0] + 2, bb[1] + 2)]
assert "misspell" in labels and "Ignore all" in labels, labels
app.close_notepad(); pump(0.2)
app._set_extra("spell_notepad", False)

# the customize form's multi-line boxes
box = tk.Text(root, width=40, height=3); box.pack()
app.spell_attach(box, "custom"); app._spell_custom_boxes = [box]
box.insert("1.0", "A frist sentance box"); app._set_extra("spell_custom", True); pump(0.6)
assert bad(box) == ["frist", "sentance"], bad(box)
app._set_extra("spell_custom", False); pump(0.3); assert bad(box) == []

# /spell
app._local("/spell"); assert "Windows spell checker" in app.out.get("end-5l", "end") and "nothing (off by default)" in app.out.get("end-5l", "end")
app._local("/spell on"); assert app.cfg["spell_input"] and app.cfg["spell_notepad"] and app.cfg["spell_custom"]
app._local("/spell notepad off"); assert not app.cfg["spell_notepad"] and app.cfg["spell_input"]
app._local("/spell add Zorbulon"); assert "zorbulon" in app.cfg["spell_words"]
app._local("/spell words"); assert "zorbulon" in app.out.get("end-3l", "end")
app._local("/spell remove zorbulon"); assert "zorbulon" not in app.cfg["spell_words"]
app._set_extra("entry_grow", "3"); pump(0.4); app.input.delete(0, "end"); app.input.insert(0, "say I definately dislike you")
app._local("/spell check"); assert "definately: definitely" in app.out.get("end-4l", "end")
app._local("/spell off"); assert not app.cfg["spell_input"]
root.destroy()
print("spell tests OK")
