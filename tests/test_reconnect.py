"""Auto-reconnect behaviour, against a local fake server only."""
import os, socket, sys, tempfile, threading, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import duskholm_client as dc
import tkinter as tk

dc.RECONNECT_SECONDS = 2
dc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "settings.json")


class Fake:
    """Listens on one port; can be stopped/started to simulate the game going down and up."""
    def __init__(self, port=0):
        self.port, self.conns, self.accepted, self.sock = port, [], 0, None
        self.start()

    def start(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", self.port)); s.listen(5)
        self.port = s.getsockname()[1]
        self.sock = s
        threading.Thread(target=self._loop, args=(s,), daemon=True).start()

    def _loop(self, s):
        while True:
            try:
                c, _ = s.accept()
            except OSError:
                return
            self.accepted += 1
            self.conns.append(c)
            try:
                c.sendall(b"hello\n\r")
            except OSError:
                pass

    def drop_all(self):
        for c in self.conns:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            c.close()
        self.conns = []

    def stop(self):
        self.drop_all()
        self.sock.close()


root = tk.Tk()
app = dc.App(root)
fake = Fake()
app.v_host.set("127.0.0.1"); app.v_port.set(str(fake.port)); app.v_tls.set(False)


def pump(secs, until=None):
    end = time.time() + secs
    while time.time() < end:
        root.update(); time.sleep(0.01)
        if until and until():
            return True
    return until() if until else None


def body():
    return app.out.get("1.0", "end-1c")


# 1. toggle OFF (default): an unexpected drop does NOT reconnect
assert app.cfg["auto_reconnect"] is False
app.toggle_connection(); assert pump(3, lambda: app.connected)
fake.drop_all()
assert pump(3, lambda: not app.connected)
pump(3.5)
assert not app.connected and not app._retrying and fake.accepted == 1, (app._retrying, fake.accepted)

# 2. toggle ON: drop -> countdown -> reconnect on its own
app.v_auto.set(True); app._auto_toggled()
app.toggle_connection(); assert pump(3, lambda: app.connected)
n = fake.accepted
fake.drop_all()
assert pump(3, lambda: not app.connected)
assert app._retrying and app.btn.cget("text") == "Cancel retry"
assert "Reconnecting in" in app.status.cget("text"), app.status.cget("text")
t0 = time.time()
assert pump(6, lambda: app.connected), "should have reconnected by itself"
assert 1.0 <= time.time() - t0 <= 5.0, time.time() - t0
assert fake.accepted == n + 1 and not app._retrying
assert "Reconnecting to" in body()

# 3. server down: keeps retrying; comes back up -> connects; no stacking of timers
fake.stop()
before = body().count("Reconnecting to")
assert pump(3, lambda: not app.connected)
assert pump(8, lambda: body().count("Reconnecting to") >= before + 2), "should retry repeatedly"
assert app._retrying and not app.connected
fake = Fake(port=int(app.v_port.get()))
assert pump(8, lambda: app.connected), "should connect once the server is back"
assert not app._retrying and app._reconnect_job is None

# 4. user cancels the retry: it stops and stays stopped
fake.drop_all()
assert pump(3, lambda: not app.connected) and app._retrying
app.toggle_connection()                         # "Cancel retry"
assert not app._retrying and app._reconnect_job is None and app.btn.cget("text") == "Connect"
a = fake.accepted
pump(3.5)
assert not app.connected and fake.accepted == a, "no connection after cancel"

# 5. deliberate disconnect never reconnects, even with the toggle on
app.toggle_connection(); assert pump(3, lambda: app.connected)
app.toggle_connection()                         # user Disconnect
a = fake.accepted
pump(3.5)
assert not app.connected and not app._retrying and fake.accepted == a

# 6. "quit" then the server closes: intentional, no reconnect
app.toggle_connection(); assert pump(3, lambda: app.connected)
app.input.insert(0, "quit"); app._on_enter(None); pump(0.3)
fake.drop_all()
assert pump(3, lambda: not app.connected)
assert not app._retrying and "will not reconnect" in body()
a = fake.accepted
pump(3.5)
assert not app.connected and fake.accepted == a

# 7. turning the option off while waiting cancels the pending retry
app.toggle_connection(); assert pump(3, lambda: app.connected)
fake.drop_all()
assert pump(3, lambda: app._retrying)
app.v_auto.set(False); app._auto_toggled()
assert not app._retrying and app._reconnect_job is None
a = fake.accepted
pump(3.5)
assert fake.accepted == a

# 8. certificate errors are not retried
app.v_auto.set(True); app._auto_toggled()
app._retrying = True
app._handle_event("failed", "certificate verify failed: CERTIFICATE_VERIFY_FAILED")
assert not app._retrying and app._reconnect_job is None

# 9. the setting is validated
assert dc.clean_settings({"auto_reconnect": "yes"})["auto_reconnect"] is False
assert dc.clean_settings({"auto_reconnect": True})["auto_reconnect"] is True
print("reconnect tests OK")
root.update(); root.destroy()
