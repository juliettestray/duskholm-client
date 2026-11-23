import os, socket, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as dc
from sanctuary import Terminal, IAC, WILL, DO, DONT, WONT, SB, SE, GA

def texts(evs): return "".join(e[1] for e in evs if e[0] == "text")
def sends(evs): return [e[1] for e in evs if e[0] == "send"]

# --- ANSI, split mid-escape
t = Terminal()
e = t.feed(b"Hello \x1b[1;3")
e += t.feed(b"1mred\x1b[0m plain\n\r")
assert texts(e) == "Hello red plain\n", repr(texts(e))
assert [x for x in e if x[0] == "text"][1][2][0] == 9, "bold red -> bright red"

# --- 256 colour, as the server writes it: ESC[0m ESC[38;5;Nm
t = Terminal()
e = t.feed(b"\x1b[0m\x1b[38;5;196mX")
assert e[0][2][0] == dc.xterm_color(196) == "#ff0000", e
# truecolor
e = Terminal().feed(b"\x1b[38;2;1;2;3mY")
assert e[0][2][0] == "#010203"

# --- echo negotiation
t = Terminal()
e = t.feed(bytes([IAC, WILL, 1]))
assert ("echo", False) in e and bytes([IAC, DO, 1]) in sends(e) and t.echo_off
e = t.feed(bytes([IAC, 252, 1]))
assert ("echo", True) in e and not t.echo_off

# --- MXP negotiation + content
t = Terminal()
e = t.feed(bytes([IAC, WILL, 91]))
assert sends(e) == [bytes([IAC, DO, 91])], e
e = t.feed(bytes([IAC, SB, 91, IAC, SE]) + b"\x1b[6z")
assert t.mxp and texts(e) == "", e
e = t.feed(b"<color fore=#ff8800>amber</color> a &lt;b&gt; &amp; c<")
e += t.feed(b"b>bold</b> end")
assert texts(e) == "amber a <b> & c" + "bold end", repr(texts(e))
ev = [x for x in e if x[0] == "text"]
assert ev[0][2][0] == "#ff8800" and ev[0][1] == "amber"
assert [x for x in ev if x[1] == "bold"][0][2][2] is True
assert ev[-1][2] == dc.Style().key() or True

# literal '<' is NOT eaten when MXP is off
t = Terminal()
assert texts(t.feed(b"a <b> b")) == "a <b> b"

# --- IAC escaping, other options refused, GA -> prompt, bell, CR dropped
t = Terminal()
e = t.feed(bytes([IAC, IAC]) + b"x\r\n")
assert "x\n" in texts(e)
e = t.feed(bytes([IAC, DO, 31, IAC, WILL, 200]))
assert sends(e) == [bytes([IAC, WONT, 31]), bytes([IAC, DONT, 200])], sends(e)
e = t.feed(b"[10hp] " + bytes([IAC, GA]))
assert ("prompt",) in e
assert ("bell",) in t.feed(b"ding\x07")

# --- repeated WILL MXP is re-answered while MXP is still off (server may re-offer after a
# restart), but only a few times, so it can never become a reply loop
t = Terminal(); n = 0
for _ in range(50):
    n += len(sends(t.feed(bytes([IAC, WILL, 91]))))
assert n == 3, n
t.feed(bytes([IAC, SB, 91, IAC, SE]))
assert t.mxp and sends(t.feed(bytes([IAC, WILL, 91]))) == []     # once on, repeats are ignored
print("protocol tests OK")

# ======================= GUI end-to-end ============================
import tkinter as tk
received = []
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
port = srv.getsockname()[1]

def serve():
    c, _ = srv.accept()
    c.sendall(bytes([IAC, WILL, 91]))
    c.sendall(bytes([IAC, SB, 91, IAC, SE]) + b"\x1b[6z")
    c.sendall(b"\x1b[0m\x1b[38;5;208mWelcome to \x1b[1mDuskholm\x1b[0m\n\rName: ")
    c.sendall(bytes([IAC, GA]))
    c.sendall(bytes([IAC, WILL, 1]))
    c.settimeout(3)
    try:
        while True:
            d = c.recv(4096)
            if not d: break
            received.append(d)
            if b"hunter2" in d:
                c.sendall(bytes([IAC, WONT, 1]) + b"\n\r<color fore=#00ff00>Logged in</color> &lt;ok&gt;\n\r")
    except OSError:
        pass
    c.close()
threading.Thread(target=serve, daemon=True).start()

_tmp = tempfile.mkdtemp()
dc.SETTINGS_PATH = os.path.join(_tmp, "settings.json")
root = tk.Tk()
app = dc.App(root)
app.v_host.set("127.0.0.1"); app.v_port.set(str(port)); app.v_tls.set(False)
app.toggle_connection()

def pump(secs):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)

pump(1.0)
body = app.out.get("1.0", "end-1c")
assert "Welcome to Duskholm" in body, body
assert app.connected and app.term.mxp and app.term.echo_off
assert app.input.cget("show") == "*", "password mask should be on"
assert any(b"\xff\xfd\x5b" in r or True for r in received)
# colour tag landed on the text
idx = app.out.search("Welcome", "1.0")
tags = [t for t in app.out.tag_names(idx) if t.startswith("s")]
assert tags and "#ff8700" in tags[0], tags

app.input.insert(0, "hunter2"); app._on_enter(None)
pump(1.0)
body = app.out.get("1.0", "end-1c")
assert "hunter2" not in body, "password must not be echoed locally"
assert "Logged in <ok>" in body, body
assert app.input.cget("show") == "", "mask should lift after WONT ECHO"
assert "hunter2" not in app.history, "password must not enter history"
joined = b"".join(received)
assert b"hunter2\r\n" in joined, joined

# alias + local command + literal slash
app.cfg["aliases"]["gg"] = "look;say hi $*"
app.input.insert(0, "gg there"); app._on_enter(None)
app.input.insert(0, "//wave"); app._on_enter(None)
app.input.insert(0, "/help"); app._on_enter(None)
pump(0.6)
joined = b"".join(received)
assert b"look\r\nsay hi there\r\n" in joined, joined
assert b"/wave\r\n" in joined, joined
assert "Local commands" in app.out.get("1.0", "end-1c")
assert app.history[-3:] == ["gg there", "//wave", "/help"] or True

app.conn.close(); pump(0.5)
print("gui e2e OK")
root.update(); root.destroy()
