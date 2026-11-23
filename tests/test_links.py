"""Links, image panes and the small input/output toggles (local HTTP server only)."""
import http.server, os, struct, sys, tempfile, threading, time, zlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

F = sc.App.find_urls
t = "see https://example.com/a_(b), and (http://x.org/y). Also 'https://q.io/p?x=1&y=2'! and [https://z.net/k]"
got = [t[a:b] for a, b in F(t)]
assert got == ["https://example.com/a_(b)", "http://x.org/y", "https://q.io/p?x=1&y=2", "https://z.net/k"], got
assert F("no links here, ftp://nope, http:// alone, https://") == []
assert F("x" * 100000) == [] and len(F("http://a.b/" * 50)) >= 1


def png(w=40, h=30):
    raw = b"".join(b"\x00" + bytes([200, 40, 40]) * w for _ in range(h))
    def chunk(tag, d):
        c = struct.pack(">I", len(d)) + tag + d
        return c + struct.pack(">I", zlib.crc32(tag + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith(".png"):
            body, ctype = png(), "image/png"
        else:
            body, ctype = b"<html>hi</html>", "text/html"
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % srv.server_address[1]

sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1200x700+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


opened = []
sc.webbrowser.open = lambda u, *a, **k: opened.append(u) or True
app.connected = True
app._on_data(("Look: https://example.com/page now\n\r").encode()); pump(0.3)
assert app.out.tag_ranges("link"), "links are tagged"
i = app.out.search("https://example.com/page", "1.0")
assert "link" in app.out.tag_names(i)
assert app.out.get(*app.out.tag_ranges("link")[:2]) == "https://example.com/page"


def click_at(word):
    idx = app.out.search(word, "1.0")
    bbox = app.out.bbox(idx + "+2c")
    assert bbox, "link is on screen"
    ev = type("E", (), {"x": bbox[0] + 1, "y": bbox[1] + 1})()
    return app._link_click(app.out, ev)


assert click_at("https://example.com/page") == "break"
assert opened == ["https://example.com/page"], opened
click_before = len(opened)
app.cfg["links"] = False
assert app._link_click(app.out, type("E", (), {"x": 5, "y": 5})()) is None
app._set_extra("links", False)
assert not app.out.tag_ranges("link"), "turning links off removes them"
app._set_extra("links", True)

# images: fetched, shown in the Images pane
app.open_link(base + "/pic.png"); end = time.time() + 8
while time.time() < end and "images" not in app._panes:
    pump(0.1)
pump(0.5)
assert "images" in app._panes and app._panes["images"].get("img") is not None, "image shown in a pane"
assert opened == ["https://example.com/page"], "images do not go to the browser"
# a non-image under an image-looking name falls back to the browser
app.open_link(base + "/fake.jpg"); end = time.time() + 8
while time.time() < end and len(opened) < 2:
    pump(0.1)
assert opened[-1] == base + "/fake.jpg"
# images off: straight to the browser
app._set_extra("link_images", False)
app.open_link(base + "/other.png"); assert opened[-1] == base + "/other.png"
app.open_link("javascript:alert(1)"); app.open_link("file:///c:/x.png"); app.open_link("ftp://a/b.png")
assert not any(u.startswith(("javascript", "file", "ftp")) for u in opened)

# panes get links too
app.pane_append("OOC", [("visit https://example.org/q please", (None, None, False, False, False, False))]); pump(0.2)
assert app._panes["ooc"]["text"].tag_ranges("link")

# scroll on send / echo / bell on new output
sent = []
app.conn = type("C", (), {"send": lambda self, b: sent.append(b) or True, "close": lambda self, *a: None})()
for _ in range(80):
    app._on_data(b"filler line\n\r")
pump(0.3)
app.out.yview_moveto(0.0); pump(0.1)
app.send_line("look")
assert app.out.yview()[1] >= 0.99, "sending jumps to the bottom"
app.cfg["scroll_on_send"] = False
app.out.yview_moveto(0.0); pump(0.1)
app.send_line("look")
assert app.out.yview()[1] < 0.99, "unless the option is off"
app.cfg["show_echo"] = False
n = app.out.get("1.0", "end").count("look\n")
app.send_line("look"); assert app.out.get("1.0", "end").count("look\n") == n, "no echo when hidden"

beeps = []
app.root.bell = lambda *a, **k: beeps.append(1)
app.cfg["bell_new"] = "off"; app._on_data(b"x\n\r"); assert not beeps
app.cfg["bell_new"] = "always"; app._last_new_bell = 0; app._on_data(b"x\n\r"); assert len(beeps) == 1
app._on_data(b"y\n\r"); assert len(beeps) == 1, "rate limited"
app.cfg["bell_new"] = "scrolled"; app._last_new_bell = 0
app.out.yview_moveto(1.0); pump(0.1)
app.root.focus_force(); pump(0.2)
app._on_data(b"z\n\r")
scrolled_before = len(beeps)
app.out.yview_moveto(0.0); pump(0.1); app._last_new_bell = 0
app._on_data(b"w\n\r"); assert len(beeps) == scrolled_before + 1 or app.out.yview()[1] >= 0.99

# options are cleaned from a hand-edited file
c = sc.clean_settings({"host": "x", "links": "yes", "bell_new": "loud", "emoji": 1})
assert c["links"] is True and c["bell_new"] == "off" and c["emoji"] is False

root.update(); root.destroy(); srv.shutdown()
print("link tests OK")
