"""Checking for and installing a newer Sanctuary (stdlib only, no GUI).

Nothing here runs by itself: the client calls it when the person asks (or has switched on the
startup check). It only ever talks to GitHub over HTTPS, sends no personal information, checks the
download against the SHA-256 published with the release, and does not replace anything without the
person's say-so."""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import version

API = "https://api.github.com/repos/%s/releases/latest" % version.REPO
USER_AGENT = "Sanctuary-update-check"
MAX_JSON = 1_000_000
MAX_ZIP = 120 * 1024 * 1024
MAX_EXE = 150 * 1024 * 1024
ALLOWED_HOSTS = ("github.com", "api.github.com", "githubusercontent.com")
ZIP_RE = re.compile(r"^Sanctuary-[A-Za-z0-9._-]+-win64\.zip$")
EXE_MEMBER = "Sanctuary/Sanctuary.exe"


class UpdateError(Exception):
    """Something went wrong in a way worth telling the person in a sentence."""


# ---------------------------------------------------------------- versions
def parse_version(text):
    """'v1.2.3' / '1.2' -> (1, 2, 3) / (1, 2, 0); None for anything else."""
    m = re.fullmatch(r"[vV]?(\d{1,4})(?:\.(\d{1,4}))?(?:\.(\d{1,4}))?", str(text or "").strip())
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def is_newer(latest, current=None):
    a, b = parse_version(latest), parse_version(current if current is not None else version.__version__)
    return a is not None and b is not None and a > b


# ---------------------------------------------------------------- talking to GitHub
def _host_ok(url, allow_local):
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    if allow_local and p.scheme == "http" and host in ("127.0.0.1", "localhost"):
        return True
    return p.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allow_local):
        self.allow_local = allow_local

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _host_ok(newurl, self.allow_local):
            raise UpdateError("The download was redirected somewhere that is not GitHub.")
        return urllib.request.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


def _open(url, allow_local=False, timeout=15):
    if not _host_ok(url, allow_local):
        raise UpdateError("Refusing to contact %s." % urllib.parse.urlparse(url).netloc[:40])
    opener = urllib.request.build_opener(_SafeRedirect(allow_local))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    try:
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise UpdateError("GitHub answered %d." % e.code)
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError("Could not reach GitHub (%s)." % (getattr(e, "reason", None) or type(e).__name__))


def parse_release(data):
    """A release dict from the API reduced to what we use, or raises UpdateError."""
    if not isinstance(data, dict) or not isinstance(data.get("tag_name"), str):
        raise UpdateError("GitHub's answer was not a release.")
    tag = data["tag_name"]
    if parse_version(tag) is None:
        raise UpdateError("The latest release has an odd version name (%s)." % tag[:20])
    assets = []
    for a in data.get("assets") or []:
        if isinstance(a, dict) and isinstance(a.get("name"), str) and isinstance(a.get("browser_download_url"), str):
            digest = a.get("digest") if isinstance(a.get("digest"), str) else ""
            size = a.get("size") if isinstance(a.get("size"), int) and not isinstance(a.get("size"), bool) else 0
            assets.append({"name": a["name"], "url": a["browser_download_url"], "size": size,
                           "sha256": digest[7:].lower() if digest.lower().startswith("sha256:") else ""})
    body = data.get("body") if isinstance(data.get("body"), str) else ""
    return {"tag": tag, "version": parse_version(tag), "name": str(data.get("name") or tag)[:80],
            "notes": body[:6000], "page": str(data.get("html_url") or "")[:300], "assets": assets[:40]}


def fetch_latest(api=API, allow_local=False):
    with _open(api, allow_local) as r:
        raw = r.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise UpdateError("GitHub's answer was too big.")
    try:
        return parse_release(json.loads(raw.decode("utf-8", "replace")))
    except (ValueError, RecursionError):
        raise UpdateError("GitHub's answer could not be read.")


def pick_assets(release):
    """(zip asset, expected sha256 or '', checksum asset or None)."""
    zips = [a for a in release["assets"] if ZIP_RE.match(a["name"])]
    if not zips:
        raise UpdateError("That release has no Windows zip to install (Sanctuary-<version>-win64.zip).")
    z = zips[0]
    sums = [a for a in release["assets"] if a["name"] in (z["name"] + ".sha256", z["name"] + ".sha256.txt")]
    return z, z["sha256"], (sums[0] if sums else None)


def read_checksum(text, filename):
    """The hex digest for `filename` from a sha256sum-style file ('<hex>  name' or just '<hex>')."""
    for line in str(text).splitlines():
        m = re.match(r"^\s*([0-9a-fA-F]{64})\s*(?:\*?(\S+))?\s*$", line)
        if m and (m.group(2) in (None, filename)):
            return m.group(1).lower()
    return ""


def download(url, dest, max_bytes, allow_local=False, progress=None):
    """Download to a file, refusing anything bigger than max_bytes. Returns the sha256 of what arrived."""
    h = hashlib.sha256()
    got = 0
    with _open(url, allow_local, timeout=30) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        if total > max_bytes:
            raise UpdateError("That download is bigger than expected; stopping.")
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            got += len(chunk)
            if got > max_bytes:
                raise UpdateError("That download is bigger than expected; stopping.")
            h.update(chunk)
            f.write(chunk)
            if progress:
                progress(got, total)
    return h.hexdigest()


def extract_exe(zip_path, dest_dir):
    """Take only Sanctuary.exe out of the zip (never anything else, never a path from the zip)."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            info = next((i for i in z.infolist() if i.filename == EXE_MEMBER), None)
            if info is None:
                raise UpdateError("The zip does not contain Sanctuary.exe.")
            if info.file_size > MAX_EXE:
                raise UpdateError("The program in the zip is too big.")
            out = os.path.join(dest_dir, "Sanctuary.new.exe")
            with z.open(info) as src, open(out, "wb") as dst:
                n = 0
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    n += len(chunk)
                    if n > MAX_EXE:
                        raise UpdateError("The program in the zip is too big.")
                    dst.write(chunk)
    except zipfile.BadZipFile:
        raise UpdateError("The download is not a valid zip.")
    with open(out, "rb") as f:
        if f.read(2) != b"MZ":
            raise UpdateError("The download is not a Windows program.")
    return out


def prepare(release, work_dir=None, allow_local=False, progress=None):
    """Download and check the release. Returns the path of the new exe, ready to be swapped in.
    Raises UpdateError with a plain sentence if anything does not check out."""
    z, expected, sumasset = pick_assets(release)
    work = work_dir or tempfile.mkdtemp(prefix="sanctuary-update-")
    if not expected and sumasset is not None:
        with _open(sumasset["url"], allow_local) as r:
            expected = read_checksum(r.read(4096).decode("utf-8", "replace"), z["name"])
    if not expected:
        raise UpdateError("That release does not publish a checksum, so I won't install it.")
    zpath = os.path.join(work, z["name"])
    got = download(z["url"], zpath, MAX_ZIP, allow_local, progress)
    if got != expected.lower():
        try:
            os.remove(zpath)
        except OSError:
            pass
        raise UpdateError("The download does not match its checksum; nothing was installed.")
    return extract_exe(zpath, work)


# ---------------------------------------------------------------- swapping the program in
def running_exe():
    """The path of the running Sanctuary.exe, or None when running from source."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return None


RELAUNCH_DELAY = 4          # seconds between the swap and starting the new program


def _bat(path):
    return str(path).replace("%", "%%")


def write_swap_script(current, new, pid, start=True):
    """A small batch file that waits for this program to end, swaps the new exe in (keeping the old
    one as Sanctuary.old.exe), and starts it. No pipes and no console tricks: every step is a plain
    command that ends by itself, and it gives up (leaving the old program in place) rather than hang.
    Returns its path."""
    d = os.path.dirname(current)
    bat = os.path.join(tempfile.mkdtemp(prefix="sanctuary-swap-"), "swap.bat")
    old = _bat(os.path.join(d, "Sanctuary.old.exe"))
    current, new = _bat(current), _bat(new)
    sysdir = r"%SystemRoot%\System32"
    pid = int(pid)
    lines = [
        "@echo off",
        "set /a waits=0",
        ":wait",
        "set /a waits+=1",
        "if %waits% gtr 60 goto giveup",
        # is the old program still running?  (output goes to a file that find reads: no pipe to hang)
        '"%s\\tasklist.exe" /FI "PID eq %d" /FO CSV /NH > "%%~dp0pid.txt" 2>NUL' % (sysdir, pid),
        '"%s\\find.exe" """%d""" "%%~dp0pid.txt" >NUL 2>NUL' % (sysdir, pid),
        'if not errorlevel 1 ("%s\\PING.EXE" -n 2 127.0.0.1 >NUL & goto wait)' % sysdir,
        'if exist "%s" del /f /q "%s"' % (old, old),
        "set /a tries=0",
        ":swap",
        "set /a tries+=1",
        'move /y "%s" "%s" >NUL 2>NUL' % (current, old),
        'if not errorlevel 1 goto placed',
        'if %tries% geq 30 goto giveup',
        '"%s\\PING.EXE" -n 2 127.0.0.1 >NUL' % sysdir,
        "goto swap",
        ":placed",
        'move /y "%s" "%s" >NUL 2>NUL' % (new, current),
        'if errorlevel 1 (move /y "%s" "%s" >NUL 2>NUL & goto giveup)' % (old, current),
    ]
    if start:
        # Give the old program time to finish removing its temporary folder before the new one makes its own:
        # starting at once can land in the middle of that clean-up and fail to unpack (ping -n N waits N-1 seconds).
        lines.append('"%s\\PING.EXE" -n %d 127.0.0.1 >NUL' % (sysdir, RELAUNCH_DELAY + 1))
        lines.append('start "" "%s"' % current)
    lines += [":giveup", '(goto) 2>NUL & del "%~f0"']
    with open(bat, "w", encoding="mbcs", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return bat


def clean_env(env=None):
    """A copy of the environment without PyInstaller's bookkeeping variables (_MEIPASS2, _PYI_*).
    The running one-file exe sets them to point at its own temporary folder; a new Sanctuary.exe
    started with them still set believes it is a child of this one, tries to use that folder, and
    fails with 'Failed to load Python DLL ... python310.dll' once this program has exited and
    removed it."""
    env = dict(os.environ if env is None else env)
    for k in list(env):
        if k.upper().startswith(("_MEI", "_PYI")):
            del env[k]
    return env


def launch_swap(current, new, start=True):
    bat = write_swap_script(current, new, os.getpid(), start)
    # CREATE_NO_WINDOW alone: the helper has a hidden console that its commands share. (Adding
    # DETACHED_PROCESS gives every command its own visible console window.)
    subprocess.Popen(["cmd", "/c", bat], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=clean_env())
    return bat
