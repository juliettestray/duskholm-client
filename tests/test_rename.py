"""The rename from "Duskholm client": name constant, new file locations, and the settings migration."""
import json, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

assert sc.APP_NAME == "Sanctuary"
assert sc.SETTINGS_PATH.endswith(".sanctuary.json") and sc.user_skin_dir().endswith(".sanctuary_skins")

# ---------------- migration copies, never moves or overwrites ----------------------------------------
tmp = tempfile.mkdtemp()
old_s, new_s = os.path.join(tmp, ".duskholm_client.json"), os.path.join(tmp, ".sanctuary.json")
old_k, new_k = os.path.join(tmp, ".duskholm_skins"), os.path.join(tmp, ".sanctuary_skins")
json.dump({"skin": "Moody", "font_size": 17, "fullscreen": True}, open(old_s, "w"))
os.makedirs(old_k)
json.dump({"name": "Mine", "bg": "#101010"}, open(os.path.join(old_k, "mine.json"), "w"))
open(os.path.join(old_k, "notes.txt"), "w").write("not a skin")
open(os.path.join(old_k, "huge.json"), "w").write("x" * 70000)
os.makedirs(os.path.join(old_k, "sub.json"))
done = sc.migrate_legacy_files(old_s, new_s, old_k, new_k)
assert done == ["settings", "skins"], done
assert json.load(open(new_s))["skin"] == "Moody" and os.path.exists(old_s), "copied, old file kept"
assert sorted(os.listdir(new_k)) == ["mine.json"], "only small .json files come across"
assert os.path.exists(os.path.join(old_k, "mine.json"))
# a second start changes nothing, even if the new settings differ
json.dump({"skin": "Plain"}, open(new_s, "w"))
assert sc.migrate_legacy_files(old_s, new_s, old_k, new_k) == []
assert json.load(open(new_s))["skin"] == "Plain", "never overwrites"
# nothing to migrate / unwritable targets do not raise
fresh = tempfile.mkdtemp()
assert sc.migrate_legacy_files(os.path.join(fresh, "a"), os.path.join(fresh, "b"), os.path.join(fresh, "c"), os.path.join(fresh, "d")) == []
assert sc.migrate_legacy_files(old_s, os.path.join(fresh, "nodir", "x.json"), old_k, os.path.join(fresh, "nodir", "k")) is not None

# ---------------- the visible name comes from the constant ---------------------------------------------
tmp2 = tempfile.mkdtemp()
sc.SETTINGS_PATH = os.path.join(tmp2, "s.json")
sc.user_skin_dir = lambda: os.path.join(tmp2, "skins")
root = tk.Tk(); app = sc.App(root); root.geometry("900x600+20+20")
for _ in range(20):
    root.update(); time.sleep(0.01)
assert root.title() == "Sanctuary"
assert "Sanctuary client" in app.out.get("1.0", "end-1c") and "Duskholm client" not in app.out.get("1.0", "end-1c")
assert app.cfg["worlds"][0]["name"] == "Duskholm" and app.cfg["worlds"][0]["host"] == "duskholm.com", "the game keeps its name"
app.set_dos_mode(True)
for _ in range(30):
    root.update(); time.sleep(0.01)
assert "SANCTUARY TERMINAL" in app.out.get("1.0", "end-1c")
app.dos_confirm_quit(); root.update()
assert app._overlay_open()
root.update(); root.destroy()

# ---------------- the launcher shim and the old module name ---------------------------------------------
shim = open(os.path.join(HERE, "Sanctuary.pyw"), encoding="utf-8").read()
assert "from sanctuary import main" in shim and "main()" in shim
assert not os.path.exists(os.path.join(HERE, "duskholm_client.py")), "the old module file is gone"
r = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r); import sanctuary" % os.path.abspath(HERE)],
                   capture_output=True, text=True, timeout=60)
assert r.returncode == 0, r.stderr
print("rename tests OK")
