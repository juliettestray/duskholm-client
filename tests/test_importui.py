"""Import from another client in the app: /import, the question, what lands in the settings, 'every match' colouring,
the trigger editor keeping it, and both looks (no network)."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import triggers
import worldfile
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")
TMP = tempfile.mkdtemp()

XML = ('<?xml version="1.0" encoding="iso-8859-1"?>\n<!DOCTYPE muclient>\n<muclient>\n'
       '<world name="Imported" site="mud.example.org" port="4321" />\n'
       '<triggers>\n'
       '<trigger match=" agate" regexp="y" enabled="y" custom_colour="17" other_text_colour="#D13000" repeat="y" '
       'ignore_case="y" keep_evaluating="y" sequence="100" group="Minerals"></trigger>\n'
       '<trigger match="* tells you *" enabled="y" custom_colour="3" sequence="100"></trigger>\n'
       '<trigger match="^(\\w+) arrives$" regexp="y" enabled="y" sequence="100"><send>wave at %1</send></trigger>\n'
       '<trigger match="gone" regexp="y" enabled="y" omit_from_output="y" sequence="100"></trigger>\n'
       '<trigger match="script only" regexp="y" enabled="y" script="OnThing"></trigger>\n'
       '</triggers>\n<aliases>\n'
       '<alias match="dc" enabled="y"><send>trash corpse</send></alias>\n'
       '<alias match="two words" enabled="y"><send>x</send></alias>\n'
       '</aliases>\n<timers><timer name="t" /></timers>\n</muclient>\n')


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def out():
    return app.out.get("1.0", "end-1c")


def write(name, data, mode="w", **kw):
    p = os.path.join(TMP, name)
    with open(p, mode, **kw) as f:
        f.write(data)
    return p


pump(0.4)
good = write("world.MCL", XML.encode("iso-8859-1"), "wb")

# ---- /import reads the file, says what is in it, then asks ----------------------------------------------------------
app._local('/import "%s"' % good); pump(0.4)
text = out()
assert "Read as a MUSHclient file." in text and "World: Imported (mud.example.org:4321)" in text, text[-600:]
assert "Triggers: 4 of 5 can be imported" in text and "Aliases: 1 of 2 can be imported" in text, text[-600:]
assert "script only" in text and "OnThing" in text, "what was left out, and why"
assert "two words" in text and "1 timer not imported" in text
win = app._import_win
assert win is not None and win.winfo_exists(), "then it asks"
# nothing has changed yet
assert not app.cfg["triggers"] and not app.cfg["alias_rules"]
labels = [w.cget("text") for w in win.winfo_children() if isinstance(w, tk.Checkbutton)]
assert any("Also save the world 'Imported'" in l for l in labels) and any("trust" in l for l in labels), labels
entry = [w for w in win.winfo_children() if isinstance(w, tk.Entry)][0]
assert entry.get() == "Imported", "tied to the file's own world by default"
# Import (the window's own button)
[b for b in [c for f in win.winfo_children() if isinstance(f, tk.Frame) for c in f.winfo_children()]
 if b.cget("text") == "Import"][0].invoke(); pump(0.4)
assert app._import_win is None and not win.winfo_exists()
trigs, als = app.cfg["triggers"], app.cfg["alias_rules"]
assert len(trigs) == 4 and len(als) == 1
assert all(t["world"] == "Imported" and t["global"] is False for t in trigs + als)
by = {t["name"]: t for t in trigs}
assert by["Minerals: agate"]["enabled"] and by["Minerals: agate"]["actions"][0]["scope"] == "all"
assert by["tells you"]["enabled"] if "tells you" in by else True
sends = [t for t in trigs if any(a["type"] == "send" for a in t["actions"])]
assert len(sends) == 1 and sends[0]["enabled"] is False, "a trigger that sends arrives switched off"
assert all(t["enabled"] for t in trigs if t not in sends), "colours and hiding are on"
assert als[0]["name"] == "dc" and als[0]["enabled"] is False, "aliases arrive switched off"
assert any(w["name"] == "Imported" and w["host"] == "mud.example.org" and w["port"] == 4321 for w in app.cfg["worlds"]), \
    "the world was saved"
assert "Added 4 triggers; 1 that sends commands is switched off" in out() and "Added 1 alias" in out()
assert "work in the world called 'Imported'" in out()
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert len(saved["triggers"]) == 4 and saved["alias_rules"][0]["name"] == "dc"
# the same file again adds nothing
n = len(out())
app._local('/import "%s"' % good); pump(0.3)
[b for b in [c for f in app._import_win.winfo_children() if isinstance(f, tk.Frame) for c in f.winfo_children()]
 if b.cget("text") == "Import"][0].invoke(); pump(0.3)
assert len(app.cfg["triggers"]) == 4 and "already there" in out()[n:], out()[n:]

# ---- the rules work, only in their own world ---------------------------------------------------------------------------
def shown(line, world):
    app.session.name = world
    key = (None, None, False, False, False, False)
    pieces, effects = app._run_triggers([(line, key)], line, False)
    return pieces, effects


first = app.session
pieces, _e = shown("an agate, a bigger agate and an agate", "Imported")
hits = [t for t, k in pieces if k[0] == "#d13000"]
assert hits == [" agate", " agate", " agate"], "every match is coloured (repeat): %r" % pieces
pieces, _e = shown("an agate", "Duskholm")
assert all(k[0] is None for _t, k in pieces), "in another world they do nothing"
pieces, effects = shown("gone", "Imported")
assert pieces is None, "the hide-line trigger hides it"
first.name = "Imported"
# ---- 'every match' survives the trigger editor -----------------------------------------------------------------------------
t = by["Minerals: agate"]
v = sc.values_from_trigger(t)
assert v["every"] is True and v["whole"] is False
t2, msg = sc.trigger_from_values(v)
assert t2["actions"][0]["scope"] == "all", msg
v["whole"] = True
assert sc.trigger_from_values(v)[0]["actions"][0]["scope"] == "line"
v["whole"] = False; v["every"] = False
assert sc.trigger_from_values(v)[0]["actions"][0]["scope"] == "match"
assert triggers.validate_trigger(dict(t, actions=[{"type": "highlight", "fg": 1, "scope": "all"}]))["actions"][0]["scope"] == "all"
assert triggers.validate_trigger(dict(t, actions=[{"type": "highlight", "fg": 1, "scope": "sideways"}])) is None
assert triggers.all_spans({"mode": "plain", "pattern": "ab", "ignore_case": True}, "ab ab AB") == [(0, 2), (3, 5), (6, 8)]
assert triggers.all_spans({"mode": "plain", "pattern": "a*b", "ignore_case": True}, "a1b a2b") == [(0, 7)] or \
    len(triggers.all_spans({"mode": "plain", "pattern": "a*b", "ignore_case": True}, "a1b a2b")) == 1
assert triggers.all_spans({"mode": "regex", "pattern": "x*", "ignore_case": True}, "abc") == [], "empty matches are skipped"
assert triggers.all_spans(None, "x") == [] and triggers.all_spans({"mode": "regex", "pattern": "(", "ignore_case": True}, "x") == []
# the editor windows open on it in both looks
app.cfg["triggers"] = list(app.cfg["triggers"])
ed = app.open_triggers(); pump(0.3)
try:
    ed.destroy()
except (tk.TclError, AttributeError):
    pass

# ---- trusting the file: everything on, in every world ----------------------------------------------------------------------
app.cfg["triggers"], app.cfg["alias_rules"] = [], []
app._local('/import "%s"' % good); pump(0.3)
win = app._import_win
entry = [w for w in win.winfo_children() if isinstance(w, tk.Entry)][0]
entry.delete(0, "end")                                            # empty: every world
for cb in win.winfo_children():
    if isinstance(cb, tk.Checkbutton) and "trust" in cb.cget("text"):
        cb.invoke()
[b for b in [c for f in win.winfo_children() if isinstance(f, tk.Frame) for c in f.winfo_children()]
 if b.cget("text") == "Import"][0].invoke(); pump(0.3)
assert len(app.cfg["triggers"]) == 4 and all(t["enabled"] for t in app.cfg["triggers"])
assert app.cfg["alias_rules"][0]["enabled"] is True
assert all("world" not in t and t.get("global", True) is True for t in app.cfg["triggers"] + app.cfg["alias_rules"])
assert not any("Added the world" in l for l in out().splitlines()[-6:]), "the world was already saved"

# ---- other files -----------------------------------------------------------------------------------------------------------------
n = len(out())
app._local('/import "%s"' % write("notes.txt", "just some words")); pump(0.2)
assert "I do not know what kind of file" in out()[n:] and app._import_win is None
n = len(out())
app._local('/import "%s"' % os.path.join(TMP, "missing.xml")); pump(0.2)
assert "Could not read that file" in out()[n:]
bomb = write("bomb.xml", '<?xml version="1.0"?><!DOCTYPE muclient [<!ENTITY a "aaaa">]><muclient>&a;</muclient>')
n = len(out()); app._local('/import "%s"' % bomb); pump(0.2)
assert "entities" in out()[n:] and app._import_win is None
empty = write("empty.xml", '<?xml version="1.0"?><muclient><triggers></triggers></muclient>')
n = len(out()); app._local('/import "%s"' % empty); pump(0.2)
assert "nothing in that file" in out()[n:] and app._import_win is None
# a Sanctuary world file still goes through /import as it always did
snc = write("mine.snc", worldfile.dumps({"format": worldfile.FORMAT, "version": worldfile.VERSION,
                                        "world": {"name": "From Snc", "host": "snc.example.org", "port": 9000, "tls": False,
                                                  "note": "", "last": 0}}))
n = len(out()); app._local('/import "%s"' % snc); pump(0.3)
assert any(w["name"] == "From Snc" for w in app.cfg["worlds"]) and "Added the world 'From Snc'" in out()[n:]

# ---- the DOS look: a dialog for the file, a dialog for the question ----------------------------------------------------------------
app.cfg["triggers"], app.cfg["alias_rules"] = [], []
app.set_dos_mode(True); pump(0.6)
app._local("/import"); pump(0.4)
assert app._overlay_open(), "no file given: it asks for one"
d = app._overlay
fields = {f["key"]: f for f in d._fields}
fields["path"]["entry"].delete(0, "end"); fields["path"]["entry"].insert(0, good)
app.dos_close_overlay(); pump(0.2)
assert app.import_client_file(good) is True; pump(0.4)
assert app._overlay_open()
d = app._overlay
keys = [f["key"] for f in d._fields]
assert keys[0] == "world" and "trust" in keys, keys
app.dos_close_overlay(); pump(0.2)
import clientimport
res = clientimport.read(open(good, "rb").read())[1]
app._import_apply("mushclient", res, "Imported", False, False)
assert len(app.cfg["triggers"]) == 4
app.set_dos_mode(False); pump(0.3)
# the File menu has the entry
labels = []
bar = app._menubar
for i in range(bar.index("end") + 1):
    if bar.type(i) == "cascade":
        m = bar.nametowidget(bar.entrycget(i, "menu"))
        for j in range(m.index("end") + 1):
            if m.type(j) == "command":
                labels.append(m.entrycget(j, "label"))
assert "Import from another client..." in labels and "Import world settings..." in labels, labels

root.update(); root.destroy()
print("import ui tests OK")
