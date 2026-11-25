"""CRT scanlines over the DOS look: an option, off by default, a see-through click-through window that follows the main one."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import crt
import sanctuary as sc
import tkinter as tk

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x700+30+30")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def shown():
    w = getattr(app, "_crt", None)
    return w is not None and w.winfo_exists() and w.state() == "normal" and w.winfo_viewable()


pump(0.6)
assert any(k == "crt_lines" for k, *_ in sc.EXTRA_CHOICES) and app.cfg["crt_lines"] == "off"
assert sc.clean_settings({"host": "x", "crt_lines": "bogus"})["crt_lines"] == "off"
assert all(v in sc.CHOICE_WORDS for v in ("light", "medium", "strong"))
assert not shown() and getattr(app, "_crt", None) is None, "off: nothing is even created"

# in the normal look it never shows, whatever the setting
app._set_extra("crt_lines", "medium"); pump(0.3)
assert not shown() and app.crt_wanted() is False

# the DOS look: it covers the client area, see-through and click-through
app.set_dos_mode(True); pump(0.8)
assert shown() and app.crt_wanted()
w = app._crt
assert w._through is True and abs(float(w.attributes("-alpha")) - crt.LEVELS["medium"]) < 0.02, w.attributes("-alpha")
assert str(w.attributes("-transparentcolor")).lower() == crt.KEY, w.attributes("-transparentcolor")
assert (w.winfo_width(), w.winfo_height()) == (root.winfo_width(), root.winfo_height())
assert (w.winfo_rootx(), w.winfo_rooty()) == (root.winfo_rootx(), root.winfo_rooty())
lines = w._cv.find_all()
assert len(lines) >= (root.winfo_height() + crt.GAP - 1) // crt.GAP and len(lines) == w._rows and all(w._cv.itemcget(i, "fill") == "black" for i in lines[:5])
import ctypes
from ctypes import wintypes
u = ctypes.windll.user32
u.GetWindowLongW.argtypes, u.GetWindowLongW.restype = [wintypes.HWND, ctypes.c_int], ctypes.c_long
u.GetAncestor.argtypes, u.GetAncestor.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
ex = u.GetWindowLongW(u.GetAncestor(w.winfo_id(), 2), -20)
for bit in (0x20, 0x80000, 0x80, 0x08000000):
    assert ex & bit, hex(ex)
# the mouse goes straight through it: Windows says the window under a point in the middle is not the overlay
u.WindowFromPoint.argtypes, u.WindowFromPoint.restype = [wintypes.POINT], wintypes.HWND
mid = wintypes.POINT(root.winfo_rootx() + root.winfo_width() // 2, root.winfo_rooty() + root.winfo_height() // 2)
over = u.GetAncestor(w.winfo_id(), 2)
hit = u.WindowFromPoint(mid)
assert hit and u.GetAncestor(hit, 2) != over, "clicks reach the program under the lines"
app.input.focus_set(); pump(0.2)
assert root.focus_get() is not w and root.focus_get() is not w._cv, "it never takes the keyboard"

# it leaves the window alone when nothing changed: moving or re-stacking it again made the main window send another event,
# which moved it again (about 30 times a second), and the lines flickered
placed = []
real_place = app._crt_place
app._crt_place = lambda: (placed.append(1), real_place())[1]
before = root.winfo_geometry()
pump(1.5)
assert len(placed) <= 2 and root.winfo_geometry() == before, "idle: %d placements" % len(placed)
app._append([("some text" + chr(10), None)] * 20); pump(0.5)
assert len(placed) <= 2, "text arriving does not move it: %d" % len(placed)
app._crt_place = real_place

# it follows the main window: moved, resized
root.geometry("900x600+80+60"); pump(0.6)
assert (w.winfo_width(), w.winfo_height()) == (root.winfo_width(), root.winfo_height()) and w.winfo_rootx() == root.winfo_rootx()
n = len(w._cv.find_all())
assert n * crt.GAP >= root.winfo_height(), "enough lines to cover the window"
root.geometry("800x500+80+60"); pump(0.5)
assert len(w._cv.find_all()) == n, "a smaller window does not redraw the lines"

# it checks itself: all well means it does nothing and says nothing; anything wrong is put right and remembered
pump(2.6)
assert app._crt_log == [] and app._crt_problems() == [], (app._crt_log, app._crt_problems())
w.withdraw()
assert app._crt_problems() == ["hidden"] and app._crt_verify() == ["hidden"]; pump(0.3)
assert shown() and app._crt_problems() == []
w.geometry("300x200+5+5"); pump(0.1)
assert "misplaced" in app._crt_problems(); app._crt_verify(); pump(0.3)
assert (w.winfo_width(), w.winfo_height()) == (root.winfo_width(), root.winfo_height()) and app._crt_problems() == []
ex = u.GetWindowLongW(u.GetAncestor(w.winfo_id(), 2), -20)
u.SetWindowLongW.argtypes, u.SetWindowLongW.restype = [wintypes.HWND, ctypes.c_int, ctypes.c_long], ctypes.c_long
u.SetWindowLongW(u.GetAncestor(w.winfo_id(), 2), -20, ex & ~0x20)               # the mouse would now be blocked
assert "lost click-through" in app._crt_problems(); app._crt_verify(); pump(0.3)
assert u.GetWindowLongW(u.GetAncestor(w.winfo_id(), 2), -20) & 0x20 and app._crt_problems() == []
assert [r for _t, r in app._crt_log] == ["hidden", "misplaced", "lost click-through"], app._crt_log
n_log = len(app._crt_log); pump(2.5)
assert len(app._crt_log) == n_log, "once put right it is left alone"
app.input.delete(0, "end"); app.input.insert(0, "/crt"); app._on_enter(None); pump(0.2)
t = app.out.get("1.0", "end").replace(chr(10), " ")
assert "CRT scanlines: medium; showing; put right:" in t and "lost click-through" in t, t[-300:]

# strength changes; off hides it
app._set_extra("crt_lines", "strong"); pump(0.3)
assert abs(float(w.attributes("-alpha")) - crt.LEVELS["strong"]) < 0.02 and shown()
app._set_extra("crt_lines", "off"); pump(0.3)
assert not shown()
app._set_extra("crt_lines", "light"); pump(0.4)
assert shown() and abs(float(w.attributes("-alpha")) - crt.LEVELS["light"]) < 0.02

# minimised: it goes; restored: it comes back
root.iconify(); pump(0.5)
assert not shown(), "hidden while minimised"
root.deiconify(); pump(0.7)
assert shown()

# leaving the DOS look hides it; going back shows it again
app.set_dos_mode(False); pump(0.4)
assert not shown()
app.set_dos_mode(True); pump(0.6)
assert shown()

# text still goes in and the screen still works under it
app._append([("line %d\n" % i, None) for i in range(300)]); pump(0.3)
assert "line 299" in app.out.get("end-3l", "end")
app.set_dos_mode(False); pump(0.3)
root.destroy()
print("crt tests OK")
