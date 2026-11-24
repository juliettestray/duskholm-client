"""Colour emoji: pictures in the text areas, the options (on in the ordinary look, off in the DOS look), resizing,
and that copying, links and colours are unharmed (no network)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import emojiimg
import tkinter as tk

if not (emojiimg.Image is not None and emojiimg._font_path()):
    print("emoji picture tests SKIP (no Pillow or no Segoe UI Emoji font)")
    sys.exit(0)

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x760+20+20")
ESC = chr(27)
CR = chr(13) + chr(10)
GRIN, HEART_EYES, FIRE = chr(0x1F600), chr(0x1F60D), chr(0x1F525)


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def feed(text):
    app._on_data(text.encode("utf-8") + CR.encode())
    pump(0.3)


def images(w):
    return [i for _k, _n, i in w.dump("1.0", "end", image=True)]


def text(w=None):
    return (w or app.out).get("1.0", "end-1c")


# ---- the defaults and the settings file -----------------------------------------------------
assert sc.clean_settings({"host": "x"})["emoji_pics"] is True, "on in the ordinary look"
assert sc.clean_settings({"host": "x"})["emoji_pics_dos"] is False, "off in the DOS look"
assert sc.clean_settings({"host": "x", "emoji_pics": "yes", "emoji_pics_dos": 1})["emoji_pics"] is True
pump(0.3)
app.connected = True
app.cfg["emoji"] = True
assert app.cfg["emoji_pics"] is True and app.cfg["emoji_pics_dos"] is False and not app.dos and app._emoji_pics_on()

# ---- pictures in the main text ----------------------------------------------------------------
feed("hello :grinning: world")
assert "hello " + GRIN + " world" in text(), "the emoji character is still in the text (copy, search, logs)"
imgs = images(app.out)
assert len(imgs) == 1, imgs
size = app._emoji_size()
photo = app._emoji_photo(GRIN, size)
assert photo is not None and photo.width() == size and photo.height() == size
pos = app.out.search(GRIN, "1.0", elide=True)
assert emojiimg.TAG_HIDE in app.out.tag_names(pos), "the character itself is hidden under its picture"
assert app.out.get("1.0", "end-1c").count(GRIN) == 1
# two on a line, a link after them, colours kept
feed("a :grinning: b :heart_eyes: https://example.com/page c")
ranges = app.out.tag_ranges("link")
assert ranges and app.out.get(ranges[-2], ranges[-1]) == "https://example.com/page", "links still line up after pictures"
assert len(images(app.out)) == 3
feed(ESC + "[31mred :fire: text" + ESC + "[0m")
fire_pos = app.out.search(FIRE, "1.0", elide=True)
img_at = [i for i in images(app.out) if app.out.compare(i, ">", fire_pos)][0]
char_tags = {t for t in app.out.tag_names(fire_pos) if t != emojiimg.TAG_HIDE}
assert char_tags and char_tags <= set(app.out.tag_names(img_at)), "the picture wears the character's colour tags"
# a line that arrives in two pieces
n = len(images(app.out))
app._on_data(b"first part :grinning:"); pump(0.4)
app._on_data(b" second :heart_eyes:" + CR.encode()); pump(0.4)
assert len(images(app.out)) == n + 2
# a joined sequence and a flag stay as text
before = len(images(app.out))
feed("family " + chr(0x1F468) + chr(0x200D) + chr(0x1F469) + " flag " + chr(0x1F1E8) + chr(0x1F1E6))
assert len(images(app.out)) == before, "sequences pictures cannot show whole stay plain"

# ---- a pane gets them too ----------------------------------------------------------------------
app.cfg["triggers"] = [{"name": "t", "mode": "plain", "pattern": "*tells you*", "enabled": True, "priority": 0,
                        "actions": [{"type": "route", "pane": "Tells"}]}]
feed("Goose tells you :fire:")
assert images(app._panes["tells"]["text"]), "the pane line has its picture"

# ---- the options ---------------------------------------------------------------------------------
app._set_extra("emoji_pics", False); pump(0.3)
assert not images(app.out) and not app.out.tag_ranges(emojiimg.TAG_HIDE), "off: plain glyphs again"
assert "hello " + GRIN + " world" in text() and text().count(GRIN) >= 3, "and the text is untouched"
assert not images(app._panes["tells"]["text"])
feed("while off :grinning:")
assert not images(app.out)
app._set_extra("emoji_pics", True); pump(0.3)
assert len(images(app.out)) >= 5 and images(app._panes["tells"]["text"]), "on again: every earlier line gets its pictures"
assert images(app.out)[-1]

# ---- a new font size resizes them -------------------------------------------------------------
app._set_font_size(18); pump(0.4)
photo2 = app._emoji_photo(GRIN, app._emoji_size())
assert app._emoji_size() > size and photo2.height() == app._emoji_size()
first_img = images(app.out)[0]
assert app.out.image_cget(first_img, "image") == str(photo2) or int(app.out.tk.call("image", "height", app.out.image_cget(first_img, "image"))) == app._emoji_size(), "existing pictures follow the font size"
app._set_font_size(11); pump(0.4)

# ---- the DOS look: off unless asked ------------------------------------------------------------
app.set_dos_mode(True); pump(0.6)
assert app.dos and not app._emoji_pics_on() and not images(app.out), "DOS look: plain by default"
feed("dos :grinning:")
assert not images(app.out)
app._set_extra("emoji_pics_dos", True); pump(0.3)
assert app._emoji_pics_on() and len(images(app.out)) >= 5, "the DOS toggle turns them on there"
feed("dos again :fire:")
assert len(images(app.out)) >= 6
app._set_extra("emoji_pics_dos", False); pump(0.3)
assert not images(app.out)
app._set_extra("emoji_pics_dos", True); pump(0.3)
app.set_dos_mode(False); pump(0.6)
assert not app.dos and app._emoji_pics_on() and images(app.out), "and back in the ordinary look it follows its own option"
app._set_extra("emoji_pics_dos", False)
app.set_dos_mode(True); pump(0.5)
assert not images(app.out), "DOS look with its option off: plain, whatever the other look does"
app.set_dos_mode(False); pump(0.5)
assert images(app.out)

# ---- a hidden world keeps its own ----------------------------------------------------------------
second = app.open_new_world("Other"); pump(0.3)
app.switch_session(app.sessions[0]); pump(0.3)
second.q.put((second.conn.gen, "data", (":grinning: from afar" + CR).encode())); pump(0.6)
assert len(images(second.out)) == 1 and GRIN in second.out.get("1.0", "end-1c"), "a world off screen gets pictures too"
assert second.out is not app.out

# ---- the picker window shows them ----------------------------------------------------------------
win = app.open_emoji_picker(); pump(0.3)
box = [w for w in win.winfo_children()[1].winfo_children() if isinstance(w, tk.Text)][0]
win._search.delete(0, "end"); win._search.insert(0, "grinning"); win._render(); pump(0.3)
assert images(box), "the picker has pictures"
app.input.delete(0, "end")
img = images(box)[0]
bb = box.bbox(img)
assert bb, "the picture is on screen"
box.event_generate("<Button-1>", x=bb[0] + 3, y=bb[1] + 3); pump(0.2)
assert app.input.get() == GRIN, "clicking a picture adds that emoji: " + repr(app.input.get())
win.destroy(); pump(0.2)

root.update(); root.destroy()
print("emoji picture tests OK")
