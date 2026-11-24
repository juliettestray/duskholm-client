"""Two worlds at once against two LOCAL fake game servers (127.0.0.1 only, never a real game):
separate scrollbacks, input going to the world on screen, a hidden world dropping and reconnecting by itself,
logging per world, closing a world mid-traffic, and leaving with both open."""
import os, socket, sys, tempfile, threading, time, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sanctuary as sc
import tkinter as tk

CR = chr(13) + chr(10)


class FakeGame:
    """A tiny game: greets with a banner and a prompt, answers each line, accepts reconnects."""

    def __init__(self, name, hp=100):
        self.name, self.hp = name, hp
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        self.client = None
        self.clients = 0
        self.received = []
        self.eof = threading.Event()
        self._stop = False
        threading.Thread(target=self._accept, daemon=True).start()

    def prompt(self):
        return "[%d/100DF 50ST 50WN 0LG M:0 K:0 ()] " % self.hp

    def _accept(self):
        while not self._stop:
            try:
                c, _a = self.srv.accept()
            except OSError:
                return
            self.client = c
            self.clients += 1
            self.eof.clear()
            try:
                c.sendall(("Welcome to %s" % self.name + CR + self.prompt()).encode())
            except OSError:
                pass
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c):
        buf = b""
        while True:
            try:
                d = c.recv(4096)
            except OSError:
                d = b""
            if not d:
                self.eof.set()
                return
            buf += d
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("latin-1").strip()
                self.received.append(line)
                try:
                    c.sendall((CR + "%s heard: %s" % (self.name, line) + CR + self.prompt()).encode())
                except OSError:
                    pass

    def push(self, text):
        try:
            self.client.sendall(text.encode())
        except (OSError, AttributeError):
            pass

    def drop(self):
        try:
            self.client.shutdown(socket.SHUT_RDWR)
        except (OSError, AttributeError):
            pass
        try:
            self.client.close()
        except (OSError, AttributeError):
            pass

    def close(self):
        self._stop = True
        self.drop()
        try:
            self.srv.close()
        except OSError:
            pass


errors = []
sc.traceback.print_exc = lambda *a, **k: errors.append(traceback.format_exc())
sc.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
sc.RECONNECT_SECONDS = 1
root = tk.Tk()
app = sc.App(root)
root.geometry("1000x600+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def wait_for(cond, what, t=8.0):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.02)
        if cond():
            return
    raise AssertionError("timed out waiting for " + what)


def type_line(text):
    app.input.delete(0, "end"); app.input.insert(0, text); app._on_enter(None); pump(0.1)


A, B = FakeGame("Alpha", 100), FakeGame("Beta", 10)
for g in (A, B):
    app.cfg["worlds"].append(sc.clean_world({"name": g.name, "host": "127.0.0.1", "port": g.port, "tls": False, "note": ""}))
app.cfg["auto_reconnect"] = True
app.cfg["show_echo"] = True
pump(0.4)
wa, wb = app.cfg["worlds"][-2], app.cfg["worlds"][-1]
txt = lambda s: s.out.get("1.0", "end")

# ---- connect both: the second opens in its own tab
app.dial_world(wa, modem=False)
sa = app.sessions[0]
wait_for(lambda: sa.connected and "Welcome to Alpha" in txt(sa), "Alpha")
app.dial_world(wb, modem=False)
wait_for(lambda: len(app.sessions) == 2 and app.sessions[1].connected and "Welcome to Beta" in txt(app.sessions[1]), "Beta")
sb = app.sessions[1]
assert app._shown is sb and sa.name == "Alpha" and sb.name == "Beta"
assert "Welcome to Beta" not in txt(sa) and "Welcome to Alpha" not in txt(sb), "separate scrollbacks"
assert sa.host == "127.0.0.1" and sa.port == A.port and sb.port == B.port, "each world keeps its own address"

# ---- what you type goes to the world on screen
type_line("hello b"); wait_for(lambda: "hello b" in B.received, "B to get the line")
assert "hello b" not in A.received
wait_for(lambda: "Beta heard: hello b" in txt(sb), "B's answer")
assert "heard" not in txt(sa).split("Welcome to Alpha")[-1], "A saw nothing of it"
app.goto_world(1); pump(0.3)
type_line("hi a"); wait_for(lambda: "hi a" in A.received, "A to get the line")
assert "hi a" not in B.received
wait_for(lambda: "Alpha heard: hi a" in txt(sa), "A's answer")

# ---- a hidden world's traffic only marks it; its prompt does not touch the screen
B.hp = 55
B.push(CR + "news from beta" + CR + B.prompt())
wait_for(lambda: "news from beta" in txt(sb), "B's news")
assert sb.unread and "news from beta" not in txt(sa)
assert sb._last_prompt["hp"][0] == 55 and sa._last_prompt["hp"][0] == 100, "each world keeps its own stats"
assert app._shown is sa and app._last_prompt is sa._last_prompt
assert app.btn.cget("text") == "Disconnect" and app.status.cget("text") == "Connected"

# ---- a hidden world drops, retries and comes back by itself
last = lambda name: next(w for w in app.cfg["worlds"] if w["name"] == name)["last"]
time.sleep(1.1); mark = int(time.time()); a_last = last("Alpha")
B.drop()
wait_for(lambda: not sb.connected, "B to notice the drop")
assert sa.connected and app.btn.cget("text") == "Disconnect" and app.status.cget("text") == "Connected", "the toolbar still shows the world on screen"
wait_for(lambda: sb.connected and B.clients >= 2, "B to reconnect", t=12)
assert txt(sb).count("Welcome to Beta") >= 2 and sa.connected and app._shown is sa
assert "Connected to 127.0.0.1:%d" % B.port in txt(sb) and "127.0.0.1:%d" % A.port not in txt(sb), "the connect message names the world that connected"
assert last("Beta") >= mark and last("Alpha") == a_last, "the 'last call' time goes to the world that connected, not the one on screen"
assert "Welcome to Beta" not in txt(sa)
app.goto_world(2); pump(0.4)
assert app.btn.cget("text") == "Disconnect" and app.v_port.get() == str(B.port), "the host box shows the world on screen"
app.goto_world(1); pump(0.3)
assert app.v_port.get() == str(A.port)

# ---- logging belongs to one world
log = os.path.join(tempfile.mkdtemp(), "a.log")
app.toggle_log(log); assert sa.logfile and not sb.logfile
A.push(CR + "alpha-only line" + CR + A.prompt()); B.push(CR + "beta-only line" + CR + B.prompt())
wait_for(lambda: "alpha-only line" in txt(sa) and "beta-only line" in txt(sb), "both lines")
app.toggle_log(); pump(0.2)
body = open(log, encoding="utf-8").read()
assert "alpha-only line" in body and "beta-only line" not in body, body

# ---- closing a world in the middle of a burst of traffic
app.goto_world(2); pump(0.3)
stop = threading.Event()
def burst():
    for i in range(400):
        if stop.is_set():
            return
        B.push("burst line %d" % i + CR)
        time.sleep(0.002)
t = threading.Thread(target=burst, daemon=True); t.start()
pump(0.3)
n_err = len(errors)
app.goto_world(1)
assert app.close_world(sb); pump(0.5)
stop.set(); t.join(2)
assert sb not in app.sessions and app._shown is sa and len(app.sessions) == 1
assert B.eof.wait(5), "B's server saw the connection close"
assert len(errors) == n_err, errors[n_err:]

# ---- a second tab again, then leave with both open
app.dial_world(wb, modem=False)
wait_for(lambda: len(app.sessions) == 2 and app.sessions[1].connected, "Beta again")
A.eof.clear(); B.eof.clear()
conns = (sa.conn, app.sessions[1].conn)
app.cfg["auto_reconnect"] = False
quit_called = []
orig_destroy = root.destroy
root.destroy = lambda: quit_called.append(1)
app.on_quit()
assert quit_called, "Exit went through"
assert A.eof.wait(5) and B.eof.wait(5), "both worlds were hung up on exit"
assert not errors, errors
root.destroy = orig_destroy
for g in (A, B):
    g.close()
orig_destroy()
print("multiworld net tests OK")
