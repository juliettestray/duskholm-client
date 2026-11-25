"""Things tied to a world follow its id, so the world can be renamed (no network)."""
import copy, json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import triggers as T
import worldids as W
import worldfile
import buttons
import tkinter as tk

# ---- the pieces ---------------------------------------------------------------------------------------------------------------
assert W.valid_id("a3f9c0de12") and not W.valid_id("XYZ") and not W.valid_id("short") and not W.valid_id(5)
ws = [{"name": "A", "id": "aaaaaaaa11"}, {"name": "B"}, {"name": "C", "id": "aaaaaaaa11"}, {"name": "D", "id": "bad id"}]
W.assign_ids(ws)
ids = [w["id"] for w in ws]
assert ids[0] == "aaaaaaaa11" and all(W.valid_id(i) for i in ids) and len(set(ids)) == 4, ids
assert W.key_for("abcdef1234", "Name") == "abcdef1234" and W.key_for("", " Name ") == "name"

# a rule tied by id applies to the world with that id, whatever either is called; a name-only rule still goes by name
r = {"name": "r", "global": False, "world": "Old name", "world_id": "aaaaaaaa11"}
assert T.rule_applies(r, "New name", "aaaaaaaa11") and not T.rule_applies(r, "Old name", "bbbbbbbb22")
assert T.rule_applies(r, "old NAME", ""), "a world that is not saved has no id: its name is compared"
legacy = {"name": "r", "global": False, "world": "Old name"}
assert T.rule_applies(legacy, "old name", "aaaaaaaa11") and not T.rule_applies(legacy, "New name", "aaaaaaaa11")
assert T.rule_applies({"name": "g"}, "x", "y") and len(T.for_world([r, legacy, {"name": "g"}], "Old name", "aaaaaaaa11")) == 3
kept = T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "global": False, "world": "W", "world_id": "aaaaaaaa11",
                           "actions": [{"type": "beep"}]})
assert kept["world_id"] == "aaaaaaaa11" and kept["world"] == "W"
bad = T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "global": False, "world": "W", "world_id": "<script>",
                          "actions": [{"type": "beep"}]})
assert "world_id" not in bad and bad["world"] == "W"
assert "world_id" not in T.validate_trigger({"name": "t", "mode": "plain", "pattern": "x", "world_id": "aaaaaaaa11",
                                             "actions": [{"type": "beep"}]}), "a global rule has no world"
assert T.validate_alias({"name": "a", "body": "b", "global": False, "world": "W", "world_id": "aaaaaaaa11"})["world_id"] == "aaaaaaaa11"
assert buttons.validate_button({"name": "b", "body": "x", "global": False, "world": "W", "world_id": "aaaaaaaa11"})["world_id"] == "aaaaaaaa11"

# link(): names -> ids, ids -> current names, orphans re-tied, tables re-keyed
cfg = {"worlds": [{"name": "Duskholm", "id": "aaaaaaaa11"}, {"name": "Other", "id": "bbbbbbbb22"}],
       "triggers": [{"name": "t1", "global": False, "world": "duskholm"},
                    {"name": "t2", "global": False, "world": "Renamed", "world_id": "bbbbbbbb22"},
                    {"name": "t3", "global": False, "world": "Gone", "world_id": "cccccccc33"},
                    {"name": "t4", "global": False, "world": "Other", "world_id": "cccccccc33"},
                    {"name": "t5"}, {"name": "t6", "global": False, "world": "World 1"}],
       "alias_rules": [{"name": "a", "global": False, "world": "DUSKHOLM"}],
       "buttons": [{"name": "b", "global": False, "world": "other"}],
       "world_time": {"duskholm": {"x": 1}, "world 1": {"y": 2}, "bbbbbbbb22": {"z": 3}},
       "world_panes": {"other": {"p": 1}}}
assert W.link(cfg) is True
t = {x["name"]: x for x in cfg["triggers"]}
assert (t["t1"]["world_id"], t["t1"]["world"]) == ("aaaaaaaa11", "Duskholm"), "a name becomes the id, and the name is the saved one"
assert (t["t2"]["world_id"], t["t2"]["world"]) == ("bbbbbbbb22", "Other"), "the id wins; the shown name is refreshed"
assert (t["t3"]["world_id"], t["t3"]["world"]) == ("cccccccc33", "Gone"), "no such world at all: left as it is"
assert (t["t4"]["world_id"], t["t4"]["world"]) == ("bbbbbbbb22", "Other"), "an id that no longer exists: re-tied by name"
assert "world" not in t["t5"] and "world_id" not in t["t6"] and t["t6"]["world"] == "World 1", "global and placeholder rules untouched"
assert cfg["alias_rules"][0]["world_id"] == "aaaaaaaa11" and cfg["buttons"][0]["world_id"] == "bbbbbbbb22"
assert cfg["world_time"] == {"aaaaaaaa11": {"x": 1}, "world 1": {"y": 2}, "bbbbbbbb22": {"z": 3}}, cfg["world_time"]
assert cfg["world_panes"] == {"bbbbbbbb22": {"p": 1}}
assert W.link(cfg) is False, "nothing left to do the second time"

# world files carry names, not ids
cfg2 = {"triggers": [{"name": "t", "mode": "plain", "pattern": "x", "enabled": True, "priority": 0, "global": False,
                      "world": "Duskholm", "world_id": "aaaaaaaa11", "actions": [{"type": "beep"}]}],
        "alias_rules": [{"name": "a", "body": "look", "enabled": True, "global": False, "world": "Duskholm", "world_id": "aaaaaaaa11"}]}
b = worldfile.build(cfg2, {"name": "Duskholm", "host": "h.example", "port": 4000, "tls": True, "note": "", "id": "aaaaaaaa11",
                           "last": 5}, ["triggers", "aliases"])
assert "id" not in b["world"] and "world_id" not in b["triggers"][0] and b["triggers"][0]["world"] == "Duskholm"
assert "world_id" not in b["alias_rules"][0]
assert cfg2["triggers"][0]["world_id"] == "aaaaaaaa11", "the live settings are not touched"
b["world"]["id"] = "dddddddd44"
b["triggers"][0]["world_id"] = "eeeeeeee55"; b["alias_rules"][0]["world_id"] = "eeeeeeee55"
tools = {"clean_world": sc.clean_world, "validate_trigger": T.validate_trigger, "validate_alias": T.validate_alias}
mine = {"worlds": [], "triggers": [], "alias_rules": []}
worldfile.merge(mine, b, tools)
assert "id" not in mine["worlds"][0] and "world_id" not in mine["triggers"][0] and "world_id" not in mine["alias_rules"][0]

# ---- a settings file from before ids: everything is tied to the world's new id on the way in ---------------------------------------
tmp = tempfile.mkdtemp()
sc.SETTINGS_PATH = os.path.join(tmp, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
old = {"host": "duskholm.com", "port": 4000, "tls": True,
       "worlds": [{"name": "Duskholm", "host": "duskholm.com", "port": 4000, "tls": True, "note": "", "last": 0},
                  {"name": "Other", "host": "other.example", "port": 23, "tls": False, "note": "", "last": 0}],
       "triggers": [{"name": "dusk only", "mode": "plain", "pattern": "x", "enabled": True, "priority": 0, "global": False,
                     "world": "Duskholm", "actions": [{"type": "beep"}]},
                    {"name": "other only", "mode": "plain", "pattern": "y", "enabled": True, "priority": 0, "global": False,
                     "world": "other", "actions": [{"type": "beep"}]}],
       "alias_rules": [{"name": "dd", "body": "look", "enabled": True, "global": False, "world": "Duskholm"}],
       "buttons": [{"name": "Dusk", "body": "look", "key": "", "enabled": True, "global": False, "world": "Duskholm"}],
       "world_time": {"duskholm": {"zone": "fixed", "offset": 3600, "ratio": 2.0, "anchor": None}}}
json.dump(old, open(sc.SETTINGS_PATH, "w", encoding="utf-8"))
root = tk.Tk()
app = sc.App(root)
root.geometry("1250x720+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


pump(0.5)
did = {w["name"]: w["id"] for w in app.cfg["worlds"]}
assert all(W.valid_id(i) for i in did.values()) and did["Duskholm"] != did["Other"], did
assert [t["world_id"] for t in app.cfg["triggers"]] == [did["Duskholm"], did["Other"]]
assert app.cfg["alias_rules"][0]["world_id"] == did["Duskholm"] and app.cfg["buttons"][0]["world_id"] == did["Duskholm"]
assert list(app.cfg["world_time"]) == [did["Duskholm"]], app.cfg["world_time"]
first = app.sessions[0]
assert first.name == "Duskholm" and app._world_id(first) == did["Duskholm"] and app._scope(first) == ("Duskholm", did["Duskholm"])
assert app.world_time()["ratio"] == 2.0, "the clock settings came with the world"
assert [t["name"] for t in T.for_world(app.cfg["triggers"], *app._scope(first))] == ["dusk only"]
app._save_settings()
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert saved["worlds"][0]["id"] == did["Duskholm"] and saved["triggers"][0]["world_id"] == did["Duskholm"]

# ---- rename the saved world: everything follows --------------------------------------------------------------------------------
idx = [w["name"] for w in app.cfg["worlds"]].index("Duskholm")
old_world = dict(app.cfg["worlds"][idx])
new_world = sc.clean_world({"name": "Dusky", "host": old_world["host"], "port": old_world["port"], "tls": True, "note": ""})
ok, msg = app._store_world(idx, new_world)
assert ok, msg
assert app.cfg["worlds"][idx]["id"] == did["Duskholm"] and app.cfg["worlds"][idx]["name"] == "Dusky", "same id, new name"
assert first.name == "Dusky" and app._world_id(first) == did["Duskholm"], "the open world takes the new name"
assert "Dusky" in app.world_tabs_text() and "Duskholm" not in app.world_tabs_text()
t0 = app.cfg["triggers"][0]
assert (t0["world"], t0["world_id"]) == ("Dusky", did["Duskholm"]), t0
assert app.cfg["alias_rules"][0]["world"] == "Dusky" and app.cfg["buttons"][0]["world"] == "Dusky"
assert [t["name"] for t in T.for_world(app.cfg["triggers"], *app._scope(first))] == ["dusk only"], "still applies here"
assert [a["name"] for a in T.for_world(app.cfg["alias_rules"], *app._scope(first))] == ["dd"]
assert [b["name"] for b in T.for_world(app.cfg["buttons"], *app._scope(first))] == ["Dusk"]
assert app.world_time()["ratio"] == 2.0 and list(app.cfg["world_time"]) == [did["Duskholm"]]
# and it still does after the settings are read again
saved = json.load(open(sc.SETTINGS_PATH, encoding="utf-8"))
assert saved["triggers"][0]["world"] == "Dusky" and saved["triggers"][0]["world_id"] == did["Duskholm"]
again = sc.clean_settings(copy.deepcopy(saved))
assert [t["name"] for t in T.for_world(again["triggers"], *app._scope(first))] == ["dusk only"]

# a rule made in a form with just a name (that is what the forms store) is tied to the id when saved
app._store_trigger(None, T.validate_trigger({"name": "new one", "mode": "plain", "pattern": "q", "global": False,
                                             "world": "Dusky", "actions": [{"type": "beep"}]}))
assert app.cfg["triggers"][-1]["world_id"] == did["Duskholm"]
# ... and renaming again, through the Worlds window's own save
win = app.open_worlds(); pump(0.3)
win._actions["listbox"].selection_clear(0, "end"); win._actions["listbox"].selection_set(idx)
cur = dict(app.cfg["worlds"][idx])
assert win._actions["save"](idx, sc.clean_world(dict(cur, name="Third name"))) is True
assert app.cfg["worlds"][idx]["id"] == did["Duskholm"] and first.name == "Third name"
assert {t["world"] for t in app.cfg["triggers"] if t.get("world_id") == did["Duskholm"]} == {"Third name"}
win.destroy()

# ---- another world is told apart, a clone is a world of its own, an unsaved world goes by name ----------------------------------
second = app.open_new_world("Other"); pump(0.4)
assert app._world_id(second) == did["Other"]
assert [t["name"] for t in T.for_world(app.cfg["triggers"], *app._scope(second))] == ["other only"]
ok, msg, j = app.clone_world([w["name"] for w in app.cfg["worlds"]].index("Other"))
cl = app.cfg["worlds"][j]
assert ok and cl["id"] != did["Other"] and W.valid_id(cl["id"])
unsaved = app.open_new_world("Scratch"); pump(0.3)
assert app._world_id(unsaved) == "" and app._world_key(unsaved) == "scratch"
app.cfg["triggers"].append({"name": "scratch rule", "mode": "plain", "pattern": "z", "enabled": True, "priority": 0,
                            "global": False, "world": "Scratch", "actions": [{"type": "beep"}]})
app._save_settings()
assert "world_id" not in app.cfg["triggers"][-1]
assert [t["name"] for t in T.for_world(app.cfg["triggers"], *app._scope(unsaved))] == ["scratch rule"]
assert "scratch rule" not in [t["name"] for t in T.for_world(app.cfg["triggers"], *app._scope(first))]
# dialling a saved world that is already open goes to its tab, by id even if the name differs
for s in (second, unsaved):
    app.close_world(s); pump(0.3)

# per-world pane layouts are kept under the id and survive the rename
store = app.cfg["world_panes"]
assert did["Duskholm"] in store or not store, store
assert not any(k in ("duskholm", "dusky", "third name") for k in store), store

root.update(); root.destroy()
print("world id tests OK")
