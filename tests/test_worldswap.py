"""Ctrl+Tab swaps between the last two worlds you looked at (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import extras
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")


def pump(t=0.2):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def at():
    return app.sessions.index(app._shown) + 1


pump(0.5)
assert extras.HOTKEYS["world_swap"] == ("Swap with the last world", "Ctrl-Tab")
assert extras.effective_keys({})["world_swap"] == ("<Control-Tab>", "Ctrl-Tab")
assert app.root.bind("<Control-Tab>") and app.input.bind("<Control-Tab>"), "bound on the window and the entry box"
assert any(r[0] == "world_swap" and r[2] == "Ctrl-Tab" for r in app.hotkey_table()), "it is in the hotkeys form"

# one world: nowhere to go, and it says so
assert app.swap_world() is False and "Only one world" in app.out.get("1.0", "end")
for i in range(2, 6):
    app.open_new_world("W%d" % i); pump(0.15)
assert len(app.sessions) == 5
# nothing switched between yet apart from opening them: the last one opened came from world 4
app.goto_world(1); pump(0.2)
app.goto_world(3); pump(0.2)
app.goto_world(5); pump(0.2)
assert at() == 5
assert app.swap_world() and at() == 3
assert app.swap_world() and at() == 5
assert app.swap_world() and at() == 3, "it keeps swapping between the same two"
# a new pair: 3 -> 2 makes 3 and 2 the last two
app.goto_world(2); pump(0.2)
assert app.swap_world() and at() == 3 and app.swap_world() and at() == 2
# clicking a world tab (switch_session) counts the same as the number keys and Ctrl+PageDown
app.cycle_world(+1); pump(0.2)
assert at() == 3 and app.swap_world() and at() == 2
# closing the world it would have gone back to: it says so instead of guessing
app.goto_world(5); pump(0.2); app.goto_world(1); pump(0.2)
app.close_world(app.sessions[4]); pump(0.3)          # (world 5, the one we came from, is gone)
before = at()
assert app.swap_world() is False and at() == before and "No earlier world" in app.out.get("end-4l", "end")
# the key can be changed in the hotkeys form like the others
app.cfg["keys"] = extras.clean_keys({"world_swap": "Ctrl-J"})
app._bind_hotkeys(); pump(0.1)
assert app.cfg["keys"] == {"world_swap": "Ctrl-J"} and app.root.bind("<Control-j>")
root.destroy()
print("world swap tests OK")
