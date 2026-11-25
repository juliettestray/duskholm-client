"""A world nobody named takes the name of the saved world with its address (no 'World 1' once a second world opens)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
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


def names():
    return [app._world_name(s) for s in app.sessions]


pump(0.4)
first = app.sessions[0]
# the first world points at the saved Duskholm from the start, so it is named from the start
assert first.name == "Duskholm" and names() == ["Duskholm"], names()
assert first._auto_named is True

# --- a world whose address is not a saved one stays a placeholder, until it points at a saved one
app.cfg["worlds"] = [{"name": "Duskholm", "host": "duskholm.com", "port": 4000, "tls": True, "note": "", "last": 0},
                     {"name": "Other", "host": "other.example", "port": 23, "tls": False, "note": "", "last": 0}]
app._rename_world(first, "")
first.name = ""; first._auto_named = False
first.host, first.port = "mystery.example", 1234
app.v_host.set("mystery.example"); app.v_port.set("1234")
assert app._auto_name_world(first) is False and names() == ["World 1"]
# rules, a button and the clock setting scoped to the placeholder
app.cfg["triggers"] = [{"name": "t1", "mode": "plain", "pattern": "x", "enabled": True, "priority": 0, "global": False,
                        "world": "World 1", "actions": [{"type": "beep"}]},
                       {"name": "t2", "mode": "plain", "pattern": "y", "enabled": True, "priority": 0, "global": False,
                        "world": "Somewhere else", "actions": [{"type": "beep"}]},
                       {"name": "t3", "mode": "plain", "pattern": "z", "enabled": True, "priority": 0,
                        "actions": [{"type": "beep"}]}]
app.cfg["alias_rules"] = [{"name": "a1", "body": "look", "enabled": True, "global": False, "world": "World 1"}]
app.cfg["buttons"] = [{"name": "B", "body": "look", "key": "", "enabled": True, "global": False, "world": "World 1"}]
app.cfg["world_time"] = {"world 1": {"mode": "x"}}
# opening a second world while the first is pointed at a saved address names the first
app.v_host.set("duskholm.com"); app.v_port.set("4000")
second = app.open_new_world(); pump(0.4)
assert names() == ["Duskholm", "World 2"], names()
assert app.sessions[0].name == "Duskholm"
assert app.cfg["triggers"][0]["world"] == "Duskholm" and app.cfg["triggers"][1]["world"] == "Somewhere else"
assert "world" not in app.cfg["triggers"][2]
assert app.cfg["alias_rules"][0]["world"] == "Duskholm" and app.cfg["buttons"][0]["world"] == "Duskholm"
assert list(app.cfg["world_time"]) == ["duskholm"], app.cfg["world_time"]
assert "Duskholm" in app.world_tabs_text()
app.close_world(second); pump(0.3)

# --- a name you chose (dialling a saved world) is left alone, and so is one another open world already has
s = app.sessions[0]
s._auto_named = False; s.name = "Mine"
assert app._auto_name_world(s) is False and s.name == "Mine"
s.name, s._auto_named = "", False
s.host, s.port = "mystery.example", 1234
app.v_host.set("mystery.example"); app.v_port.set("1234")
w2 = app.open_new_world("Duskholm"); pump(0.3)             # another open world already called Duskholm
app.goto_world(1); pump(0.3)
s.host, s.port = "duskholm.com", 4000
assert app._auto_name_world(s) is False and s.name == "", "a name another world has is not taken twice"
app.close_world(w2); pump(0.3)
assert app._auto_name_world(s) is True and s.name == "Duskholm"

# --- a name it was given this way follows the address; no saved world there: it keeps what it has
s.host, s.port = "other.example", 23
assert app._auto_name_world(s) is True and s.name == "Other"
s.host, s.port = "nowhere.example", 1
assert app._auto_name_world(s) is False and s.name == "Other"
s.host, s.port = "OTHER.example", 23
assert app._auto_name_world(s) is False, "same saved world (host compared ignoring case): nothing to change"
s.host, s.port = "duskholm.com", "not a port"
assert app._auto_name_world(s) is False

# --- the connect path names it too
s.name, s._auto_named = "", False
s.host, s.port = "duskholm.com", 4000
app.v_host.set("duskholm.com"); app.v_port.set("4000")
calls = []
sc.Connection.open = lambda self, *a, **k: calls.append(a)
app._start_connect(); pump(0.3)
assert s.name == "Duskholm" and calls, (s.name, calls)

root.update(); root.destroy()
print("world name tests OK")
