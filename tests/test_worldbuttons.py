"""Buttons travel in world files (.snc): which go out, and how they arrive (no network)."""
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


assert "buttons" in wf.PARTS
app.v_host.set("example.org"); app.v_port.set("4000")
app.cfg["worlds"] = [w for w in app.cfg["worlds"] if w["host"] != "example.org"]
app.cfg["worlds"].append(sc.clean_world({"name": "Example", "host": "example.org", "port": 4000, "tls": False, "note": ""}))
app.cfg["buttons"] = [
    {"name": "Look", "body": "look", "key": "", "enabled": True},                                       # every world
    {"name": "Heal", "body": "cast heal", "key": "Alt+H", "enabled": True, "global": False, "world": "Example"},
    {"name": "Other", "body": "wave", "key": "", "enabled": True, "global": False, "world": "Elsewhere"},   # another world's
]
path = os.path.join(home, "b.snc")
ok, m = app.export_world_file(path); assert ok, m
d = json.load(open(path, encoding="utf-8"))
names = [b["name"] for b in d["buttons"]]
assert names == ["Look", "Heal"], ("only the ones that show in this world go out", names)
assert all("world_id" not in b for b in d["buttons"])
ok, m = app.export_world_file(os.path.join(home, "nob.snc"), ["triggers"]); assert ok
assert "buttons" not in json.load(open(os.path.join(home, "nob.snc"), encoding="utf-8"))

# a clean setup: they arrive switched off, tied to the world that came with them (even renamed)
app.cfg["buttons"] = []
ok, said = app.import_world_file(path); assert ok, said
b = {x["name"]: x for x in app.cfg["buttons"]}
assert set(b) == {"Look", "Heal"} and not b["Look"]["enabled"] and not b["Heal"]["enabled"], b
assert b["Heal"]["world"] == "Example (2)" and b["Heal"]["global"] is False, b["Heal"]
assert b["Heal"]["key"] and any("2 buttons" in s and "switched off" in s for s in said), said
assert "Look" not in [x["name"] for x in app.buttons_here()], "a disabled button is not on the bar"

# again: nothing doubles; a clashing hotkey is dropped, the button stays
ok, said = app.import_world_file(path)
assert [x["name"] for x in app.cfg["buttons"]].count("Look") == 1, "a button for every world is not added twice"
assert {x["world"] for x in app.cfg["buttons"] if x["name"] == "Heal"} == {"Example (2)", "Example (3)"}, "one tied to a world follows the new world"
bundle = {"format": "sanctuary-world", "version": 1, "world": {"name": "W", "host": "w.example", "port": 23, "tls": False, "note": ""},
          "buttons": [{"name": "Dup", "body": "x", "key": "Alt+H"}, {"name": "Look", "body": "other body"}, "junk", 5,
                      {"name": "", "body": "no name"}, {"name": "Long" * 30, "body": "x"}]}
tools = app._world_tools()
cfg = {"worlds": [], "buttons": [{"name": "Mine", "body": "m", "key": "Alt-H", "enabled": True}]}
said = wf.merge(cfg, bundle, tools)
got = {x["name"][:4]: x for x in cfg["buttons"]}
assert "Dup" in got and got["Dup"]["key"] == "" and got["Dup"]["enabled"] is False, got
assert len([x for x in cfg["buttons"] if x["name"] == "Look"]) == 1
assert len(cfg["buttons"]) <= tools["max_buttons"]
# the cap
cfg = {"worlds": [], "buttons": []}
big = dict(bundle, buttons=[{"name": "b%d" % i, "body": "x"} for i in range(200)])
wf.merge(cfg, big, tools)
assert len(cfg["buttons"]) == tools["max_buttons"], len(cfg["buttons"])
# a file with no buttons part, or a wrong type, changes nothing
cfg = {"worlds": [], "buttons": []}
wf.merge(cfg, dict(bundle, buttons="nope"), tools); assert cfg["buttons"] == []
root.destroy()
print("world buttons tests OK")
