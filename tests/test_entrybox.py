"""The entry box that grows as you type (Options > Entry box grows to ...): off by default, line breaks, history, passwords (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import entrybox
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1000x700+20+20")
sent = []
app.conn = type("C", (), {"gen": 0, "send": lambda self, b: sent.append(b) or True, "close": lambda *a: None})()
app.connected = True


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def lines_sent():
    return [b.decode().rstrip() for b in sent]


pump(0.5)
plain, grow = app._entry, app._grow

# ---- off by default: the ordinary one-line entry, as always ---------------------------------------------------------------
assert app.cfg["entry_grow"] == "off" and app.input is plain and not grow.winfo_ismapped() and plain.winfo_ismapped()
assert app.entry_lines() == 0

# ---- turned on: the growing box takes over, with the text and the focus ---------------------------------------------------
plain.insert(0, "look north"); plain.focus_force(); pump(0.2)
app._set_extra("entry_grow", "3"); pump(0.4)
assert app.input is grow and grow.winfo_ismapped() and not plain.winfo_ismapped() and grow.max_lines == 3
assert grow.get() == "look north" and root.focus_get() is grow
assert int(grow.cget("height")) == 1 and app.cfg["entry_grow"] == "3"
# the Entry calls the client makes
grow.delete(0, "end"); grow.insert(0, "abcdef"); grow.icursor(3); grow.insert("insert", "X")
assert grow.get() == "abcXdef" and grow.index("insert") == 4
grow.select_range(0, "end"); assert grow.selection_present() and grow.get() == "abcXdef"
grow.delete("sel.first", "sel.last"); assert grow.get() == "" and not grow.selection_present()
assert grow.cget("show") == "" and grow.index("end") == 0

# ---- it grows with its text, up to the limit, and shrinks back ------------------------------------------------------------
grow.focus_force()
grow.insert("end", "one")
app._grow_newline(None); grow.insert("end", "two"); pump(0.3)
assert grow.get() == "one\ntwo" and int(grow.cget("height")) == 2, grow.cget("height")
app._grow_newline(None); grow.insert("end", "three"); app._grow_newline(None); grow.insert("end", "four"); pump(0.3)
assert int(grow.cget("height")) == 3, "stops at the limit"
grow.delete(0, "end"); pump(0.3)
assert int(grow.cget("height")) == 1
grow.insert("end", "word " * 80); pump(0.4)                       # wraps at the window edge
assert 2 <= int(grow.cget("height")) <= 3, grow.cget("height")
grow.delete(0, "end"); pump(0.2)

# ---- Shift+Enter and Ctrl+Enter break the line; Enter sends each line as its own command ---------------------------------------
grow.focus_force(); pump(0.1)
grow.insert("end", "north")
grow.event_generate("<Shift-Return>"); pump(0.1)
grow.insert("end", "look")
grow.event_generate("<Control-Return>"); pump(0.1)
grow.insert("end", "say hi")
assert grow.get() == "north\nlook\nsay hi", repr(grow.get())
sent.clear()
grow.event_generate("<Return>"); pump(0.4)
assert lines_sent() == ["north", "look", "say hi"], lines_sent()
assert grow.get() == "" and app.history[-3:] == ["north", "look", "say hi"]
grow.insert("end", "a"); app._grow_newline(None); app._grow_newline(None); grow.insert("end", "b")
sent.clear()
grow.event_generate("<Return>"); pump(0.3)
assert lines_sent() == ["a", "b"], "empty lines are skipped"
grow.insert("end", "single"); sent.clear()
grow.event_generate("<Return>"); pump(0.3)
assert lines_sent() == ["single"]

# ---- Up and Down: history on the first / last line, the cursor in between ------------------------------------------------------
app.history[:] = ["first cmd", "second cmd"]; app.hist_pos = 2
grow.focus_force(); grow.delete(0, "end")
grow.event_generate("<Up>"); pump(0.2)
assert grow.get() == "second cmd"
grow.delete(0, "end"); grow.insert("end", "top"); app._grow_newline(None); grow.insert("end", "bottom"); pump(0.2)
grow.mark_set("insert", "2.0")
grow.event_generate("<Up>"); pump(0.2)
assert grow.get() == "top\nbottom" and grow.index("insert") <= 3, "Up inside the box moves the cursor, not the history"
grow.mark_set("insert", "1.0"); app.hist_pos = 2
grow.event_generate("<Up>"); pump(0.2)
assert grow.get() == "second cmd", "on the first line it walks the history"
app.hist_pos = 2; grow.delete(0, "end")

# ---- paste keeps the line breaks (cut at the limit) ------------------------------------------------------------------------------
root.clipboard_clear(); root.clipboard_append("one\r\ntwo\nthree”")
grow.focus_force(); grow.event_generate("<Control-v>"); pump(0.3)
assert grow.get() == 'one\ntwo\nthree"', repr(grow.get())
grow.delete(0, "end")
root.clipboard_clear(); root.clipboard_append("\n".join("l%d" % i for i in range(45)))
grow.event_generate("<Control-v>"); pump(0.3)
assert grow.get().count("\n") + 1 == entrybox.MAX_LINES_TOTAL
grow.delete(0, "end")

# ---- Ctrl-A (select the line), hotkeys and the right-click menu work in the growing box ------------------------------------------
grow.insert("end", "some text")
app._select_input_line(); assert grow.selection_present()
grow.select_range(0, 0)
assert any(w is grow for w, _s in app._hotkey_bound), "hotkeys are bound on the growing box too"
items = {lbl: en for lbl, _h, en, _a in app._edit_items(grow)}
assert list(items) == ["Cut", "Copy", "Paste", "Select all", "Clear"] and items["Clear"]
grow.delete(0, "end")

# ---- a password: the plain entry takes over, masked, and the text goes back afterwards ---------------------------------------------
grow.insert("end", "hello")
app.term.echo_off = True
app._input_show("*"); pump(0.3)
assert app.input is plain and plain.cget("show") == "*" and plain.winfo_ismapped() and not grow.winfo_ismapped()
plain.delete(0, "end"); plain.insert(0, "hunter2")
app.term.echo_off = False
app._input_show(""); pump(0.3)
assert app.input is grow and plain.cget("show") == ""
plain.delete(0, "end"); grow.delete(0, "end")

# ---- the DOS look, and turning it off again ---------------------------------------------------------------------------------------
app.set_dos_mode(True); pump(0.7)
assert app.input is grow and grow.winfo_ismapped() and not plain.winfo_ismapped()
grow.insert("end", "dos line"); app._grow_newline(None); grow.insert("end", "two"); pump(0.3)
assert int(grow.cget("height")) == 2
grow.delete(0, "end")
app.set_dos_mode(False); pump(0.7)
assert app.input is grow and grow.winfo_ismapped()
grow.insert("end", "keep" ); app._grow_newline(None); grow.insert("end", "this")
app._set_extra("entry_grow", "off"); pump(0.4)
assert app.input is plain and plain.winfo_ismapped() and not grow.winfo_ismapped()
assert plain.get() == "keep this", repr(plain.get())
app._set_extra("entry_grow", "5"); pump(0.3)
assert app.input is grow and grow.max_lines == 5 and grow.get() == "keep this"
assert sc.clean_settings({"entry_grow": "99"})["entry_grow"] == "off", "unknown values fall back"

root.update(); root.destroy()
print("entry box tests OK")
