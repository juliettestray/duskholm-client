"""Tab alignment, bold/italic grid width, the DOS look's one-cell border, and the DOS scrollbar."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as dc
import dosui
import tkinter as tk
import tkinter.font as tkfont

E = "\x1b["
text_of = lambda evs: "".join(e[1] for e in evs if e[0] == "text")

# ---------------- tab expansion in the parser -------------------------------------------------------------
t = dc.Terminal()
assert text_of(t.feed(b"A\tB")) == "A" + " " * 7 + "B"
assert text_of(dc.Terminal().feed(b"\tX")) == " " * 8 + "X"
assert text_of(dc.Terminal().feed(b"12345678\tX")) == "12345678" + " " * 8 + "X"
assert text_of(dc.Terminal().feed(b"1234567\tX")) == "1234567 X"
assert text_of(dc.Terminal().feed(b"A\n\r\tB")) == "A\n" + " " * 8 + "B", "newline resets the column"
# columns count visible characters only: colour codes do not move the tab stops
coloured = (E + "1;31mAnnouncements:" + E + "0m\t          0 ").encode()
plain = b"Announcements:\t          0 "
assert text_of(dc.Terminal().feed(coloured)) == text_of(dc.Terminal().feed(plain))
# ... and the split of the stream into network packets never changes the result
for cut in range(1, len(coloured)):
    tt = dc.Terminal()
    got = text_of(tt.feed(coloured[:cut])) + text_of(tt.feed(coloured[cut:]))
    assert got == text_of(dc.Terminal().feed(coloured)), cut
# MXP: tags and entities occupy no columns; <br> starts a new line
mx = dc.Terminal(); mx.feed(bytes([255, 251, 91, 255, 250, 91, 255, 240]))
assert text_of(mx.feed(b"<b>ab</b>&lt;\tX")) == "ab<" + " " * 5 + "X"
assert text_of(mx.feed(b"zz<br>\tY")) == "zz\n" + " " * 8 + "Y"

# the notes screen from the game's own log: every number lands in the same column
notes = ("Unread Notes Per Area:\n\r\n\r"
         + E + "1;31mAnnouncements:" + E + "0m\t          0 \n\r"
         + E + "31mIC:" + E + "0m\t\t          0 \n\r"
         + E + "1;33mOOC:" + E + "0m\t\t          0 \n\r"
         + E + "33mRoster:" + E + "0m\t\t          0 \n\r").encode()
lines = [l for l in text_of(dc.Terminal().feed(notes)).split("\n") if l.strip().endswith("0")]
assert len(lines) == 4 and len({l.rindex("0") for l in lines}) == 1, lines
assert lines[0].rindex("0") == 26

# ---------------- the widget agrees (Tk's own tabs would not) ----------------------------------------------
tmp = tempfile.mkdtemp()
dc.SETTINGS_PATH = os.path.join(tmp, "settings.json")
dc.user_skin_dir = lambda: os.path.join(tmp, "skins")
root = tk.Tk()
app = dc.App(root)
root.geometry("900x700+20+20")
app.out.configure(height=30)


def pump(secs=0.25):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)


def number_xs():
    xs = []
    for line in range(1, 40):
        txt = app.out.get("%d.0" % line, "%d.end" % line)
        if txt.strip().endswith("0") and ("Announcements" in txt or txt.startswith(("IC:", "OOC:", "Roster:"))):
            xs.append(app.out.bbox("%d.%d" % (line, txt.rindex("0")))[0])
    return xs


mono = app.mono_families()
fonts = [f for f in ("Consolas", "Courier New", "Lucida Console", "Cascadia Mono", "Perfect DOS VGA 437 Win",
                     "More Perfect DOS VGA", "Nouveau IBM", "Fixedsys", "Terminal") if f in mono]
assert fonts, "need at least one monospace font"
for fam in fonts:
    for size in (9, 13, 20):
        app.clear(); app._tags.clear(); app._tag_keys.clear()
        app.term = dc.Terminal()
        app.apply_font(fam, size)
        app._on_data(notes); pump(0.15)
        xs = number_xs()
        assert len(xs) == 4 and len(set(xs)) == 1, (fam, size, xs)

# bold / italic variants never change the character width (synthetic bold widens bitmap fonts)
for fam in mono[:40]:
    app.apply_font(fam, 12)
    w = app.f_norm.measure("0")
    for f in (app.f_bold, app.f_ital, app.f_bi):
        for ch in "0Wi.m":
            assert f.measure(ch) == app.f_norm.measure(ch), (fam, f.actual(), ch)
    assert w == app.f_bold.measure("0")

# ---------------- DOS look: one-cell border at every window size -----------------------------------------------
app.apply_font("Consolas" if "Consolas" in mono else mono[0], 12)
app.set_dos_mode(True); pump(0.5)
cw_of = lambda: app.f_norm.measure("0")


def border_cells():
    return (app._holder.winfo_width() - app._mid.winfo_width()) / 2.0 / cw_of()


for geo in ("700x500", "1000x700", "1400x900", "1900x1000", "900x1200"):
    root.geometry(geo); pump(0.8)
    b = border_cells()
    assert 0.5 <= b <= 2.0, (geo, "border (cells)", b)
    assert int(app.out.cget("width")) >= 40
    if app.cfg["dos_autofit"]:
        assert int(app.out.cget("width")) >= 78, (geo, "autofit keeps at least ~80 columns", app.out.cget("width"))
        assert app.out.winfo_height() / app.f_norm.metrics("linespace") >= 22, (geo, "about 25 rows")

# a size chosen by hand (auto-fit off) must still give a one-cell border, whatever the font size
app.cfg["dos_autofit"] = False
for size in (10, 16, 24, 32):
    app._set_font_size(size); root.geometry("1600x900"); pump(0.6)
    b = border_cells()
    assert 0.5 <= b <= 2.0, ("manual size", size, b)
    assert int(app.f_norm.cget("size")) == size
# fixed-width mode keeps exactly the configured columns
app.cfg["dos_fit"] = False; app.cfg["dos_cols"] = 80; app._fit_font(); pump(0.3)
assert int(app.out.cget("width")) == 80
app.cfg["dos_fit"] = True; app.cfg["dos_autofit"] = True; app._fit_font(); pump(0.3)
assert int(app.out.cget("width")) > 80 or app._holder.winfo_width() < 900

# real full screen
app.set_fullscreen(True); pump(1.0)
b = border_cells()
assert 0.5 <= b <= 2.0, ("fullscreen", b)
app.set_fullscreen(False); pump(0.5)

# options: the toggles exist and work from the keyboard
def key(w, keysym):
    w = getattr(w, "_cv", w)
    w.focus_force(); root.update(); w.event_generate("<Key>", keysym=keysym); pump(0.2)

app.dos_options_menu(); pump(0.2)
before = app.cfg["dos_fit"]
key(app._overlay, "w"); pump(0.3)
assert app.cfg["dos_fit"] is (not before)
key(app._overlay, "w"); pump(0.3)
assert app.cfg["dos_fit"] is before
key(app._overlay, "Escape")
app.dos_font_menu(); pump(0.2)
was = app.cfg["dos_autofit"]
key(app._overlay, "a"); pump(0.3)
assert app.cfg["dos_autofit"] is (not was)
key(app._overlay, "Escape")
app.cfg["dos_autofit"] = True

# ---------------- the DOS scrollbar widget ----------------------------------------------------------------------------
colors = dosui.dos_colors({})
font = tkfont.Font(family="Consolas" if "Consolas" in mono else mono[0], size=12)
top = tk.Toplevel(root)
top.geometry("500x400+40+40")
txt = tk.Text(top, width=40, height=15, font=font, wrap="none")
sb = dosui.DosScrollbar(top, txt.yview, colors, font)
txt.configure(yscrollcommand=sb.set)
sb.pack(side="right", fill="y"); txt.pack(side="left", fill="both", expand=True)
for i in range(400):
    txt.insert("end", "line %d\n" % i)
top.update(); pump(0.2)
lh = font.metrics("linespace")
h, ah, ttop_, tbot, track, thumb, avail, room, ttop = sb._geom()
assert sb.winfo_width() == font.measure("0") and ah == lh
assert thumb >= lh and thumb < track and abs(thumb / float(track) - (txt.yview()[1] - txt.yview()[0])) < 0.2
assert ttop == ah, "thumb starts right under the up arrow when at the top"
page = txt.yview()[1] - txt.yview()[0]


def click(y, x=3):
    sb.event_generate("<ButtonPress-1>", x=x, y=y); top.update()


def release():
    sb.event_generate("<ButtonRelease-1>", x=3, y=3); top.update()


txt.yview_moveto(0.5); top.update()
f0 = txt.yview()[0]
click(sb.winfo_height() - 2); release()                      # down arrow: one line
assert 0 < txt.yview()[0] - f0 <= 1.5 / 400 + 1e-6, txt.yview()[0] - f0
f1 = txt.yview()[0]
click(2); release()                                          # up arrow: one line back
assert abs(txt.yview()[0] - f0) < 1e-6, (txt.yview()[0], f0)
# clicking the track below / above the thumb pages
g = sb._geom(); below = g[8] + g[5] + 6
f0 = txt.yview()[0]
click(below); release()
assert abs((txt.yview()[0] - f0) - page) < 3.0 / 400, ("page down", txt.yview()[0] - f0, page)
g = sb._geom(); above = g[8] - 6
f0 = txt.yview()[0]
click(above); release()
assert abs((f0 - txt.yview()[0]) - page) < 3.0 / 400, "page up"
# holding a button repeats, releasing stops
txt.yview_moveto(0.1); top.update(); f0 = txt.yview()[0]
click(sb.winfo_height() - 2); pump(0.9)
held = txt.yview()[0] - f0
release(); pump(0.3); f_after = txt.yview()[0]; pump(0.4)
assert held > 6 / 400.0, ("auto-repeat while held", held)
assert txt.yview()[0] == f_after, "no more scrolling after release"
# dragging the thumb
txt.yview_moveto(0.0); top.update()
g = sb._geom(); y0 = g[8] + g[5] // 2
click(y0)
sb.event_generate("<B1-Motion>", x=3, y=y0 + g[6] // 2); top.update()
mid_pos = txt.yview()[0]
assert 0.3 < mid_pos < 0.7 * (1.0 - page) + 0.2, mid_pos
sb.event_generate("<B1-Motion>", x=3, y=y0 + 5000); top.update()
assert abs(txt.yview()[1] - 1.0) < 1e-6, "dragging past the end clamps to the bottom"
sb.event_generate("<B1-Motion>", x=3, y=y0 - 5000); top.update()
assert txt.yview()[0] == 0.0
release()
# everything fits: the thumb fills the track; garbage to set() is ignored
sb.set(0, 1); g = sb._geom(); assert g[5] == g[4]
sb.set("x", None); sb.set(float("nan"), 1); sb.set(2, -1); sb.set(-5, 99); top.update()
# restyle follows font changes; destroying with a held button leaves no timers
big = tkfont.Font(family=font.actual("family"), size=20)
sb.restyle(colors, big); top.update()
assert sb.winfo_width() == big.measure("0")
click(sb.winfo_height() - 2)
top.destroy(); pump(0.5)

# ---------------- scrollbar inside the client ----------------------------------------------------------------------------
app.set_dos_mode(True); pump(0.4)
app.clear()
for i in range(300):
    app._append([("scrollback line %d\n" % i, None)])
pump(0.4)
assert app._dosscroll.winfo_ismapped() and not app._sb.winfo_ismapped()
assert str(app.out.cget("yscrollcommand")) != "" and app._dosscroll._last - app._dosscroll._first < 0.5
before = app.out.yview()[0]
g = app._dosscroll._geom()
app._dosscroll.event_generate("<ButtonPress-1>", x=3, y=g[8] - 6); app._dosscroll.event_generate("<ButtonRelease-1>", x=3, y=3); pump(0.2)
assert app.out.yview()[0] < before, "clicking the track above the thumb pages up"
key(app.input, "Next"); pump(0.2)                          # PageDown key still works too
assert app.out.yview()[0] > 0
app.set_dos_mode(False); pump(0.4)
assert app._sb.winfo_ismapped() and not app._dosscroll.winfo_ismapped()
assert app.cfg["dos_fit"] is True

root.update(); root.destroy()
print("layout tests OK")
