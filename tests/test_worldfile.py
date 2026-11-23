"""World settings files: export, import, and hostile files (no network)."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import worldfile as wf
import sanctuary as sc
import tkinter as tk

home = tempfile.mkdtemp()
os.environ["USERPROFILE"] = os.environ["HOME"] = home
sc.SETTINGS_PATH = os.path.join(home, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x650+20+20")


def pump(t=0.2):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


# build up a setup
presets = {p["name"]: p for p in sc.trigger_presets()}
app._store_trigger(None, dict(presets["Capture OOC to a pane"], enabled=True))
app._store_trigger(None, {"name": "Auto heal", "mode": "plain", "pattern": "You are hurt*", "priority": 0, "enabled": True,
                          "actions": [{"type": "send", "text": "cast heal", "echo": True}]})
app.cfg["alias_rules"] = [{"name": "gg", "enabled": True, "body": "look;say hi"}]
app._panes_save(["top 4 OOC", "right 36 Tells"]); pump(0.3)
app.cfg["gradients"] = [{"name": "Mine", "colours": [1, 2]}]
app.cfg["designs"] = [{"name": "Scarf", "type": "clothing", "values": {"names": "red scarf"}}]
app.v_host.set("example.org"); app.v_port.set("4000")

path = os.path.join(home, "out.snc")
ok, m = app.export_world_file(path); assert ok, m
d = json.load(open(path, encoding="utf-8"))
assert d["format"] == "sanctuary-world" and d["version"] == 1 and d["world"]["host"] == "example.org" and "last" not in d["world"]
assert {"triggers", "alias_rules", "panes", "layout", "gradients", "designs"} <= set(d)
assert not app.export_world_file(path)[0], "never overwrites"
assert os.path.exists(path) and app.export_world_file(os.path.join(home, "noext"))[1].endswith("(%d bytes)." % os.path.getsize(os.path.join(home, "noext.snc")))
ok, m = app.export_world_file(os.path.join(home, "partial.snc"), ["triggers"]); assert ok
dp = json.load(open(os.path.join(home, "partial.snc"), encoding="utf-8"))
assert "alias_rules" not in dp and "panes" not in dp and "triggers" in dp
assert not app.export_world_file("")[0]

# import into a clean setup
app.cfg["triggers"], app.cfg["alias_rules"], app.cfg["panes"] = [], [], []
app.cfg["layout"] = {"regions": [], "min_main_cols": 80}; app.cfg["gradients"] = []; app.cfg["designs"] = []
app.cfg["worlds"] = [w for w in app.cfg["worlds"] if w["host"] != "example.org"]
ok, said = app.import_world_file(path); assert ok, said
text = " ".join(said)
assert "Added the world" in text and "2 triggers" in text and "1 that send commands is switched off" in text, text
assert [t["enabled"] for t in app.cfg["triggers"]] == [True, False], "the trigger that sends commands arrives off"
assert [(a["name"], a["enabled"]) for a in app.cfg["alias_rules"]] == [("gg", False)]
assert len(app.cfg["panes"]) == 2 and len(app.cfg["layout"]["regions"]) == 2
assert app.cfg["gradients"][0]["name"] == "Mine" and app.cfg["designs"][0]["name"] == "Scarf"
assert any(w["host"] == "example.org" for w in app.cfg["worlds"])
# again: nothing duplicated, the world gets a new name
n_w, n_t = len(app.cfg["worlds"]), len(app.cfg["triggers"])
ok, said = app.import_world_file(path); assert ok
assert len(app.cfg["worlds"]) == n_w + 1 and len(app.cfg["triggers"]) == n_t and len(app.cfg["alias_rules"]) == 1
assert any("(2)" in w["name"] for w in app.cfg["worlds"])
# a user layout is kept
app.cfg["layout"] = {"regions": [{"id": "r1", "side": "left", "size": 20, "weight": 1, "panes": ["OOC"]}], "min_main_cols": 80}
bundle = {"format": "sanctuary-world", "version": 1, "world": {"name": "W", "host": "h.example", "port": 1},
          "panes": [{"name": "Brand New"}], "layout": {"regions": [{"side": "top", "size": 5, "panes": ["Brand New"]}]}}
bp = os.path.join(home, "b.snc"); json.dump(bundle, open(bp, "w"))
ok, said = app.import_world_file(bp); assert ok
assert app.cfg["layout"]["regions"][0]["side"] == "left" and any(p["name"] == "Brand New" for p in app.cfg["panes"])

# hostile and broken files
def bad(content, binary=False):
    p = os.path.join(home, "bad.snc")
    open(p, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"})).write(content)
    ok, said = app.import_world_file(p)
    assert not ok and said, content[:40]
    return said[0]
assert "not a Sanctuary" in bad("not json {{{")
assert "not a Sanctuary" in bad("[1,2,3]") and "not a Sanctuary" in bad('{"format": "other"}')
assert "newer" in bad('{"format": "sanctuary-world", "version": 99}')
assert "newer" in bad('{"format": "sanctuary-world", "version": true}')
assert "too big" in bad('{"format": "sanctuary-world", "version": 1, "x": "' + "a" * 1_100_000 + '"}')
assert "Could not read" in bad(b"\xff\xfe\x00bad bytes", binary=True)
assert "not a Sanctuary" in bad("[" * 200000)
assert not app.import_world_file(os.path.join(home, "missing.snc"))[0]
assert not app.import_world_file("")[0]
# a file full of junk entries imports without harm
junk = {"format": "sanctuary-world", "version": 1, "world": {"name": "x", "host": "-bad host", "port": "no"},
        "triggers": [5, None, {"pattern": "(a+)+$", "mode": "regex"}, {"name": "ok"}], "alias_rules": "zzz",
        "panes": "x", "prompt_custom": [1], "gradients": [{"name": "Fire", "colours": [1]}], "designs": 5}
jp = os.path.join(home, "junk.snc"); json.dump(junk, open(jp, "w"))
n_t = len(app.cfg["triggers"])
ok, said = app.import_world_file(jp); assert ok and "not usable" in said[0], said
assert len(app.cfg["triggers"]) == n_t, "invalid triggers are dropped"
assert not any(w["host"].startswith("-") for w in app.cfg["worlds"])

# a BOM (Notepad) does not matter
bom = os.path.join(home, "bom.snc")
open(bom, "w", encoding="utf-8-sig").write(wf.dumps(wf.build(app.cfg, app._current_world(), ["triggers"])))
assert app.import_world_file(bom)[0]
app.cfg["panes_hidden"] = ["r2"]
bundle2 = {"format": "sanctuary-world", "version": 1, "world": {"name": "L", "host": "l.example", "port": 5},
           "panes": [{"name": "Z"}], "layout": {"regions": [{"side": "top", "size": 5, "panes": ["Z"]}]}}
app.cfg["panes"], app.cfg["layout"] = [], {"regions": [], "min_main_cols": 80}
json.dump(bundle2, open(os.path.join(home, "l.snc"), "w"))
assert app.import_world_file(os.path.join(home, "l.snc"))[0] and app.cfg["panes_hidden"] == [], "folds are reset with a new layout"

# the dialogs open in both looks; the commands work
app._local("/export " + os.path.join(home, "viacmd.snc")); assert os.path.exists(os.path.join(home, "viacmd.snc"))
app._local("/import " + os.path.join(home, "viacmd.snc")); app._local("/import " + os.path.join(home, "nope.snc"))
app.open_export().destroy()
app.set_dos_mode(True); pump(0.4)
app.open_export(); pump(0.3); assert app._overlay_open(); app.dos_close_overlay()
app.open_import(); pump(0.3); assert app._overlay_open(); app.dos_close_overlay()
app.set_dos_mode(False); pump(0.3)
root.update(); root.destroy()
print("worldfile tests OK")
