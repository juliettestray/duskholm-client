"""Update check and install against a fake local GitHub (never the real one)."""
import hashlib, http.server, io, json, os, subprocess, sys, tempfile, threading, time, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import updater as up
import version

# ---------------------------------------------------------------- pure parts
assert up.parse_version("v1.2.3") == (1, 2, 3) and up.parse_version("1.2") == (1, 2, 0) and up.parse_version("V3") == (3, 0, 0)
for bad in ("", "latest", "1.2.3.4", "1.x", "v", None, "1.2.3-beta", "99999"):
    assert up.parse_version(bad) is None, bad
assert up.is_newer("v1.0.1", "1.0.0") and up.is_newer("2.0", "1.9.9") and not up.is_newer("1.0.0", "1.0.0")
assert not up.is_newer("0.9", "1.0.0") and not up.is_newer("junk", "1.0.0") and not up.is_newer("1.0.1", "junk")
assert up.is_newer("v99.0.0") and not up.is_newer("v0.0.1"), "compared with this build's own version"
H = up._host_ok
assert H("https://api.github.com/x", False) and H("https://github.com/a/b", False)
assert H("https://objects.githubusercontent.com/z", False) and H("https://release-assets.githubusercontent.com/z", False)
for bad in ("http://github.com/x", "https://evil.example/github.com", "https://github.com.evil.example/x", "https://notgithub.com/x",
            "ftp://github.com/x", "file:///c:/x", "https://githubusercontent.com.evil.io/", "javascript:alert(1)", "http://127.0.0.1/x"):
    assert not H(bad, False), bad
assert H("http://127.0.0.1:8000/x", True) and not H("http://evil.example/x", True) and not H("https://127.0.0.1/x", False)
sha = "ab" * 32
assert up.read_checksum(sha + "  Sanctuary-1-win64.zip\n", "Sanctuary-1-win64.zip") == sha
assert up.read_checksum(sha.upper() + " *Sanctuary-1-win64.zip", "Sanctuary-1-win64.zip") == sha
assert up.read_checksum(sha, "x.zip") == sha and up.read_checksum(sha + "  other.zip", "x.zip") == ""
assert up.read_checksum("not a hash", "x.zip") == "" and up.read_checksum("", "x") == ""
for bad in (None, 5, [], {}, {"tag_name": 5}, {"tag_name": "latest"}):
    try:
        up.parse_release(bad); assert False, bad
    except up.UpdateError:
        pass
r = up.parse_release({"tag_name": "v1.2.0", "name": "N", "body": "notes", "html_url": "https://github.com/x/y/releases/v1.2.0",
                      "assets": [{"name": "a.zip", "browser_download_url": "https://github.com/a", "size": 5, "digest": "sha256:" + sha.upper()},
                                 "junk", {"name": 5}, {"name": "b", "browser_download_url": "https://github.com/b", "size": True}]})
assert r["version"] == (1, 2, 0) and len(r["assets"]) == 2 and r["assets"][0]["sha256"] == sha and r["assets"][1]["size"] == 0
for names in ([], ["readme.txt"], ["Sanctuary-1.0.0-win32.zip"], ["../Sanctuary-1.0.0-win64.zip"]):
    try:
        up.pick_assets({"assets": [{"name": n, "url": "u", "size": 0, "sha256": ""} for n in names]}); assert False, names
    except up.UpdateError:
        pass

# ---------------------------------------------------------------- a fake GitHub
def make_zip(members, exe=b"MZ" + b"\x90" * 300):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (members if members is not None else [(up.EXE_MEMBER, exe)]):
            z.writestr(name, data)
    return bio.getvalue()


STATE = {}


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/octet-stream", extra=None):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        base = "http://127.0.0.1:%d" % self.server.server_address[1]
        if self.path == "/api/latest":
            if STATE.get("api_fail"):
                return self._send(500, b"oops")
            z = STATE["zip"]
            assets = [{"name": "Sanctuary-1.2.0-win64.zip", "browser_download_url": base + "/dl/zip", "size": len(z)}]
            if STATE.get("sumfile"):
                assets.append({"name": "Sanctuary-1.2.0-win64.zip.sha256", "browser_download_url": base + "/dl/sum", "size": 100})
            if STATE.get("digest"):
                assets[0]["digest"] = "sha256:" + STATE["digest"]
            body = json.dumps({"tag_name": STATE.get("tag", "v1.2.0"), "name": "Release", "body": "What is new: everything.",
                               "html_url": "https://github.com/juliettestray/sanctuary/releases/tag/v1.2.0", "assets": assets})
            return self._send(200, body.encode(), "application/json")
        if self.path == "/dl/zip":
            if STATE.get("redirect"):
                return self._send(302, b"", extra={"Location": "https://evil.example/x.zip"})
            return self._send(200, STATE["zip"])
        if self.path == "/dl/sum":
            return self._send(200, STATE["sumfile"].encode())
        self._send(404, b"nope")


srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]
API = BASE + "/api/latest"


def setup(zipbytes, sumfile=True, digest=None, **kw):
    STATE.clear()
    STATE.update(zip=zipbytes, **kw)
    good = hashlib.sha256(zipbytes).hexdigest()
    if sumfile:
        STATE["sumfile"] = (sumfile if isinstance(sumfile, str) else good + "  Sanctuary-1.2.0-win64.zip\n")
    if digest:
        STATE["digest"] = digest
    return good


good = setup(make_zip(None))
rel = up.fetch_latest(API, True)
assert rel["tag"] == "v1.2.0" and up.is_newer(rel["tag"], "1.0.0") and rel["notes"].startswith("What is new")
work = tempfile.mkdtemp()
exe = up.prepare(rel, work, True)
assert os.path.basename(exe) == "Sanctuary.new.exe" and open(exe, "rb").read(2) == b"MZ", "good download installs"
prog = []
up.download(BASE + "/dl/zip", os.path.join(work, "p.zip"), up.MAX_ZIP, True, lambda g, t: prog.append((g, t)))
assert prog and prog[-1][0] == prog[-1][1]

def fails(why, **kw):
    z = kw.pop("zip", None)
    setup(z if z is not None else make_zip(None), **kw)
    rel = up.fetch_latest(API, True)
    try:
        up.prepare(rel, tempfile.mkdtemp(), True)
        assert False, why
    except up.UpdateError as e:
        return str(e)

assert "checksum" in fails("wrong checksum", sumfile="%s  Sanctuary-1.2.0-win64.zip" % ("0" * 64))
assert "does not publish a checksum" in fails("no checksum", sumfile=False)
assert "checksum" in fails("garbage checksum file", sumfile="nonsense")
assert "does not match" in fails("wrong digest field", sumfile=False, digest="1" * 64)
setup(make_zip(None), sumfile=False)
STATE["digest"] = hashlib.sha256(STATE["zip"]).hexdigest()        # of THIS zip (a different one is made every second)
assert up.prepare(up.fetch_latest(API, True), tempfile.mkdtemp(), True), "the API's own digest field is enough"
assert "does not contain" in fails("no exe in zip", zip=make_zip([("Sanctuary/readme.txt", b"hi")]))
assert "does not contain" in fails("path traversal member", zip=make_zip([("../Sanctuary.exe", b"MZxx"), ("Sanctuary/../../x.exe", b"MZ")]))
assert "not a Windows program" in fails("not an exe", zip=make_zip([(up.EXE_MEMBER, b"#!/bin/sh\necho hi")]))
assert "not a valid zip" in fails("not a zip", zip=b"this is not a zip file at all")
assert "not GitHub" in fails("redirect off GitHub", redirect=True)
setup(make_zip(None), api_fail=True)
try:
    up.fetch_latest(API, True); assert False
except up.UpdateError as e:
    assert "500" in str(e)
try:
    up.fetch_latest("http://127.0.0.1:1/none", True); assert False
except up.UpdateError as e:
    assert "reach" in str(e)
try:
    up.fetch_latest("https://evil.example/api", False); assert False
except up.UpdateError as e:
    assert "Refusing" in str(e)
try:
    up.download(BASE + "/dl/zip", os.path.join(work, "big.zip"), 10, True); assert False
except up.UpdateError as e:
    assert "bigger" in str(e)
setup(make_zip(None), tag="latest")
try:
    up.fetch_latest(API, True); assert False
except up.UpdateError as e:
    assert "odd version" in str(e)

# ---------------------------------------------------------------- swapping files in (the batch file, run for real, no start)
def _find_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq find.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return {l.split(",")[1].strip('"') for l in out.splitlines() if l.startswith('"find.exe"')}


FIND_BEFORE = _find_pids() if sys.platform.startswith("win") else set()


def run_swap(cur, new, pid, limit=60):
    """Start the swap exactly as the program does (hidden console), wait for it to finish."""
    bat = up.write_swap_script(cur, new, pid, start=False)
    run_swap.text = open(bat, encoding="mbcs").read()                 # (the script deletes itself when done)
    t0 = time.time()
    proc = subprocess.Popen(["cmd", "/c", bat], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("the swap helper hung (the old updater left a console window waiting forever)")
    return bat, time.time() - t0


if sys.platform.startswith("win"):
    d = os.path.join(tempfile.mkdtemp(), "50% off (x86)")
    os.makedirs(d)
    cur, new = os.path.join(d, "Sanctuary.exe"), os.path.join(d, "Sanctuary.new.exe")
    open(cur, "wb").write(b"MZold"); open(new, "wb").write(b"MZnew")
    bat, secs = run_swap(cur, new, 99999999)
    assert "50%% off" in run_swap.text
    assert open(cur, "rb").read() == b"MZnew" and open(os.path.join(d, "Sanctuary.old.exe"), "rb").read() == b"MZold"
    assert not os.path.exists(new) and not os.path.exists(bat), "the script cleans up after itself"
    assert secs < 15, secs
    # a second update replaces the old backup
    open(new, "wb").write(b"MZthird")
    run_swap(cur, new, 99999999)
    assert open(cur, "rb").read() == b"MZthird" and open(os.path.join(d, "Sanctuary.old.exe"), "rb").read() == b"MZnew"
    # the real situation: the old program is still running (and so locked) for a few seconds
    d2 = tempfile.mkdtemp()
    cur2, new2 = os.path.join(d2, "Sanctuary.exe"), os.path.join(d2, "Sanctuary.new.exe")
    import shutil
    shutil.copy(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "PING.EXE"), cur2)
    orig = open(cur2, "rb").read()
    open(new2, "wb").write(b"MZnewest")
    running = subprocess.Popen([cur2, "-n", "5", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    bat, secs = run_swap(cur2, new2, running.pid)
    running.wait(timeout=20)
    assert open(cur2, "rb").read() == b"MZnewest", "the new program is in place"
    assert open(os.path.join(d2, "Sanctuary.old.exe"), "rb").read() == orig, "and the old one is kept beside it"
    assert secs >= 3, "it waited for the old program to finish (%.1fs)" % secs
    # nothing is left running from the helper (a stuck find.exe from some earlier broken update is not ours)
    def find_pids():
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq find.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
        return {l.split(",")[1].strip('"') for l in out.splitlines() if l.startswith('"find.exe"')}
    assert find_pids() <= FIND_BEFORE, "the helper left a find.exe behind: %s" % (find_pids() - FIND_BEFORE)

assert up.running_exe() is None, "from source there is no exe to replace"

# ---------------------------------------------------------------- in the client
import sanctuary as sc
import tkinter as tk
import tkinter.messagebox as mb
import webbrowser

home = tempfile.mkdtemp()
os.environ["USERPROFILE"] = os.environ["HOME"] = home
sc.SETTINGS_PATH = os.path.join(home, "s.json")
sc.user_skin_dir = lambda: os.path.join(tempfile.mkdtemp(), "none")
root = tk.Tk()
app = sc.App(root)
root.geometry("1100x650+20+20")


def pump(t=0.3):
    end = time.time() + t
    while time.time() < end:
        root.update(); time.sleep(0.01)


def wait(cond, secs=10):
    end = time.time() + secs
    while time.time() < end and not cond():
        pump(0.1)
    assert cond(), "timed out"


txt = lambda: app.out.get("1.0", "end")
assert version.__version__ in app.about_text() and "Valicene" in app.about_text() and "Claude" in app.about_text()
assert "retro-friendly" in app.about_text()
app._upd_api, app._upd_local = API, True
setup(make_zip(None), tag="v0.0.9")
app.check_for_updates(manual=True); wait(lambda: "latest version" in txt())
assert not app._upd_busy
setup(make_zip(None), api_fail=True)
app.check_for_updates(manual=True); wait(lambda: "GitHub answered 500" in txt())
setup(make_zip(None), api_fail=True)
n = len(txt()); app.check_for_updates(manual=False); wait(lambda: not app._upd_busy); pump(0.3)
assert len(txt()) == n, "a quiet check says nothing when there is nothing to say"
opened = []
webbrowser.open = lambda u, *a, **k: opened.append(u) or True
good = setup(make_zip(None))
app.check_for_updates(manual=True); wait(lambda: "is available" in txt()); pump(0.4)
tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
assert tops and tops[-1].title() == "Update available", "from source: offers the download page"
tops[-1].destroy()
app._upd_choice("page", up.fetch_latest(API, True)); assert opened == ["https://github.com/juliettestray/sanctuary/releases/tag/v1.2.0"]
app._upd_choice("skip", {"tag": "v1.2.0", "page": ""}); assert app.cfg["update_skip"] == "v1.2.0"
before = txt().count("is available")
app.check_for_updates(manual=False); wait(lambda: not app._upd_busy); pump(0.3)
assert txt().count("is available") == before, "a skipped version is not mentioned by the quiet check"
app.check_for_updates(manual=True); wait(lambda: txt().count("is available") == before + 1)
[w.destroy() for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
app.install_update(up.fetch_latest(API, True)); assert "git pull" in txt(), "no in-place update from source"

# a packaged exe: download, check, offer a restart (swap and quit are recorded, not done)
fake_exe = os.path.join(tempfile.mkdtemp(), "Sanctuary.exe"); open(fake_exe, "wb").write(b"MZcurrent")
up.running_exe = lambda: fake_exe
swaps, quits = [], []
up.launch_swap = lambda cur, new, start=True: swaps.append((cur, open(new, "rb").read()[:2]))
app.on_quit = lambda: quits.append(1)
asked = []
mb.askyesno = lambda *a, **k: asked.append(a[0]) or False
setup(make_zip(None))
app.install_update(up.fetch_latest(API, True)); wait(lambda: asked)
assert "Restart to update" in asked and swaps == [] and "left for later" in txt(), "'no' changes nothing"
mb.askyesno = lambda *a, **k: True
app._upd_busy = False
app.install_update(up.fetch_latest(API, True)); wait(lambda: quits)
assert swaps == [(fake_exe, b"MZ")] and quits == [1]
setup(make_zip(None), sumfile="%s  x" % ("0" * 64))
swaps.clear(); app._upd_busy = False
app.install_update(up.fetch_latest(API, True)); wait(lambda: "checksum" in txt().split("Restart")[-1] or "does not match" in txt())
assert swaps == [], "a bad checksum never gets as far as a restart"
# DOS look
app._upd_busy = False
setup(make_zip(None))
app.set_dos_mode(True); pump(0.4)
app.check_for_updates(manual=True); wait(lambda: app._overlay_open()); pump(0.2)
assert app._overlay_open(); app.dos_close_overlay()
app.set_dos_mode(False); pump(0.3)
assert sc.clean_settings({"host": "x", "update_skip": "<script>"})["update_skip"] == ""
assert sc.clean_settings({"host": "x", "update_skip": "v1.2.0"})["update_skip"] == "v1.2.0"
assert sc.clean_settings({"host": "x"})["update_check"] is False, "never checks by itself unless switched on"
app._local("/update"); pump(0.2)

# the relaunched exe must not inherit the old one's PyInstaller temp-folder variables ("Failed to load Python DLL")
e = up.clean_env({"PATH": "x", "_MEIPASS2": "C:\\t\\_MEI1", "_PYI_APPLICATION_HOME_DIR": "a", "_pyi_archive_file": "b",
                  "_PYI_PARENT_PROCESS_LEVEL": "0", "HOME": "h", "MEIPASS": "keep"})
assert e == {"PATH": "x", "HOME": "h", "MEIPASS": "keep"}, e
os.environ["_PYI_APPLICATION_HOME_DIR"] = "zz"
assert not any(k.upper().startswith(("_MEI", "_PYI")) for k in up.clean_env()), "default: the real environment"
del os.environ["_PYI_APPLICATION_HOME_DIR"]

# the new program is started a few seconds after the swap, so the old one has finished removing its temp folder
_d = tempfile.mkdtemp()
_bat = up.write_swap_script(os.path.join(_d, "Sanctuary.exe"), os.path.join(_d, "Sanctuary.new.exe"), 99999999, start=True)
_lines = open(_bat, encoding="mbcs").read().splitlines()
_st = [i for i, l in enumerate(_lines) if l.startswith('start ""')]
assert len(_st) == 1 and up.RELAUNCH_DELAY >= 3
assert "PING.EXE" in _lines[_st[0] - 1] and "-n %d " % (up.RELAUNCH_DELAY + 1) in _lines[_st[0] - 1], _lines[_st[0] - 2:_st[0] + 1]
_bat2 = up.write_swap_script(os.path.join(_d, "Sanctuary.exe"), os.path.join(_d, "Sanctuary.new.exe"), 99999999, start=False)
assert not any(l.startswith('start ""') for l in open(_bat2, encoding="mbcs").read().splitlines())

root.update(); root.destroy(); srv.shutdown()
print("updater tests OK")
