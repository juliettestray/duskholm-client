"""Hardening tests: outgoing sanitising, settings validation, password handling,
stale connection events, cancelling a stalled connection. All local, no real game."""
import os, queue, socket, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as dc

# ---- sanitize_outgoing --------------------------------------------------------------
clean, dropped, trunc = dc.sanitize_outgoing("“don’t” — café\t… ok\nx")
assert clean == '"don\'t" -- cafe ... ok x', repr(clean)
assert dropped == 0 and not trunc
clean, dropped, _ = dc.sanitize_outgoing("hi \U0001F600 there 中")
assert clean == "hi  there " and dropped == 2, (repr(clean), dropped)
clean, dropped, trunc = dc.sanitize_outgoing("a" * 7000)
assert len(clean) == dc.MAX_LINE and trunc
assert dc.sanitize_outgoing("\x00\x07\x1b[31m\xff")[0] == "[31my"      # controls gone; U+00FF -> y, never an IAC byte
assert all(" " <= c <= "~" for c in dc.sanitize_outgoing("éüñßﬁ")[0])

# ---- clean_settings -----------------------------------------------------------------
c = dc.clean_settings({"host": 5, "port": "abc", "font_size": 9999, "tls": "yes",
                       "aliases": {"ok": "look", "bad key": "x", 3: "y", "n": 4}, "geometry": "junk"})
assert c["host"] == dc.DEFAULT_HOST and c["port"] == dc.TLS_PORT and c["font_size"] == dc.MAX_FONT
assert c["tls"] is True and c["aliases"] == {"ok": "look"} and "geometry" not in c
assert dc.clean_settings({"aliases": ["nope"], "port": 99999})["port"] == 65535
assert dc.clean_settings({"geometry": "800x600+10+20"})["geometry"] == "800x600+10+20"

# ---- GUI scenarios against a fake server --------------------------------------------
IAC, WILL, WONT = 255, 251, 252
received, ready = bytearray(), threading.Event()
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
port = srv.getsockname()[1]
conn_box = []

def serve():
    c, _ = srv.accept()
    conn_box.append(c)
    c.sendall(b"Name: ")
    ready.set()
    c.settimeout(5)
    try:
        while True:
            d = c.recv(4096)
            if not d: break
            received.extend(d)
    except OSError:
        pass
threading.Thread(target=serve, daemon=True).start()

import tkinter as tk
tmp = tempfile.mkdtemp()
dc.SETTINGS_PATH = os.path.join(tmp, "settings.json")
root = tk.Tk()
app = dc.App(root)
app.v_host.set("127.0.0.1"); app.v_port.set(str(port)); app.v_tls.set(False)

def pump(secs):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)

app.toggle_connection(); pump(0.8)
assert app.connected and ready.is_set()

# password prompt: no alias expansion, no '//' unescape, nothing echoed or remembered
app.cfg["aliases"]["gg"] = "look;say hi"
conn_box[0].sendall(bytes([IAC, WILL, 1])); pump(0.4)
assert app.term.echo_off
for pw in ("gg", "//secret", "päss"):
    app.input.insert(0, pw); app._on_enter(None)
pump(0.5)
assert bytes(received) == bytes([IAC, 253, 1]) + b"gg\r\n//secret\r\npass\r\n", bytes(received)
body = app.out.get("1.0", "end-1c")
assert "secret" not in body and "gg\n" not in body, body
assert app.history == [], app.history
conn_box[0].sendall(bytes([IAC, WONT, 1])); pump(0.3)
assert not app.term.echo_off

# normal input: smart quotes converted, user told about dropped characters
received.clear()
app.input.insert(0, "say “hi” \U0001F600"); app._on_enter(None); pump(0.4)
assert bytes(received) == b'say "hi" \r\n', bytes(received)
assert "can't accept" in app.out.get("1.0", "end-1c")

# a stale event from an older connection is ignored
app.q.put((app.conn.gen - 1, "closed", "stale"))
pump(0.2)
assert app.connected, "stale 'closed' must not disconnect the live connection"

# an exception inside event handling must not kill the pump
orig = app._on_data
app._on_data = lambda data: (_ for _ in ()).throw(RuntimeError("boom"))
conn_box[0].sendall(b"x"); pump(0.3)
app._on_data = orig
received.clear()
app.input.insert(0, "look"); app._on_enter(None); pump(0.4)
assert bytes(received) == b"look\r\n", "pump must keep running after an internal error"
assert "Internal error" in app.out.get("1.0", "end-1c")

# server drops us: reported once, UI back to disconnected
conn_box[0].close(); pump(0.6)
assert not app.connected and app.btn.cget("text") == "Connect"

# ---- cancelling a stalled TLS handshake frees the thread quickly -----------------------
stall = socket.socket(); stall.bind(("127.0.0.1", 0)); stall.listen(5)
sport = stall.getsockname()[1]
app.v_port.set(str(sport)); app.v_tls.set(True)
app.toggle_connection(); pump(0.5)
assert app.connecting and not app.connected
thread = app.conn._thread
app.toggle_connection()                      # Cancel
t0 = time.time(); thread.join(3)
assert not thread.is_alive() and time.time() - t0 < 3, "cancel should abort the handshake"
pump(0.3)
assert not app.connected and not app.connecting

print("hardening tests OK")
root.update(); root.destroy()
