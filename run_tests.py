"""Run the tests without their windows touching your screen, keyboard focus or mouse.

    python run_tests.py                # every tests/test_*.py
    python run_tests.py test_panes ... # just these

On Windows the tests run on a separate, invisible desktop (the same mechanism that keeps a screen
saver or lock screen apart from your session). Their windows open and are measured as usual but can
never take your focus or your keystrokes. Elsewhere, or with --here, they simply run normally.
Exit status is 0 only if every test passed."""
import ctypes
import glob
import os
import re
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, "tests")
TIMEOUT = 600
GOOD = re.compile(r"OK|SKIP|PASS|\b0 failed|0 check|0/11|0 failures", re.I)


def passed(last_line, code):
    return code == 0 and bool(GOOD.search(last_line or "")) and not re.search(r"\b[1-9]\d* (failed|check\(s\) failed)", last_line or "")


# ------------------------------------------------------------------ the hidden desktop
class HiddenDesktop:
    def __init__(self):
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.CreateDesktopW.restype = wintypes.HANDLE
        u.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
                                     wintypes.DWORD, ctypes.c_void_p]
        u.CloseDesktop.argtypes = [wintypes.HANDLE]
        self.name = "SanctuaryTests%d" % os.getpid()
        self.handle = u.CreateDesktopW(self.name, None, None, 0, 0x10000000, None)    # GENERIC_ALL
        if not self.handle:
            raise OSError("could not create a desktop (error %d)" % ctypes.get_last_error())
        self._u = u

    def close(self):
        try:
            self._u.CloseDesktop(self.handle)
        except Exception:
            pass

    def run(self, command_line, cwd, timeout):
        """Run a command line on the hidden desktop; returns its exit code (or None on timeout)."""
        k = ctypes.WinDLL("kernel32", use_last_error=True)

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                        ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                        ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                        ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                        ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                        ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(si)
        si.lpDesktop = self.name
        pi = PROCESS_INFORMATION()
        k.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL,
                                     wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOW),
                                     ctypes.POINTER(PROCESS_INFORMATION)]
        buf = ctypes.create_unicode_buffer(command_line)
        if not k.CreateProcessW(None, buf, None, None, False, 0x08000000, None, cwd, ctypes.byref(si), ctypes.byref(pi)):
            raise OSError("CreateProcess failed (error %d)" % ctypes.get_last_error())
        k.CloseHandle(pi.hThread)
        res = k.WaitForSingleObject(pi.hProcess, int(timeout * 1000))
        code = None
        if res == 0:
            c = wintypes.DWORD()
            k.GetExitCodeProcess(pi.hProcess, ctypes.byref(c))
            code = c.value
        else:                                                    # timed out: end the whole tree
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pi.dwProcessId)], capture_output=True)
        k.CloseHandle(pi.hProcess)
        return code


def run_one(path, desktop):
    out = tempfile.NamedTemporaryFile(prefix="sanctuary-test-", suffix=".txt", delete=False)
    out.close()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    os.environ.update(env)
    cmd = 'cmd /c ""%s" "%s" > "%s" 2>&1"' % (sys.executable, path, out.name)
    t0 = time.time()
    if desktop is not None:
        code = desktop.run(cmd, HERE, TIMEOUT)
    else:
        try:
            code = subprocess.run(cmd, cwd=HERE, shell=True, timeout=TIMEOUT).returncode
        except subprocess.TimeoutExpired:
            code = None
    text = open(out.name, encoding="utf-8", errors="replace").read()
    try:
        os.remove(out.name)
    except OSError:
        pass
    lines = [l for l in text.splitlines() if l.strip()]
    return code, (lines[-1] if lines else ""), text, time.time() - t0


def main(argv):
    here = "--here" in argv
    names = [a for a in argv if not a.startswith("--")]
    files = sorted(glob.glob(os.path.join(TESTS, "test_*.py")))
    if names:
        want = {n if n.startswith("test_") else "test_" + n for n in (os.path.splitext(x)[0] for x in names)}
        files = [f for f in files if os.path.splitext(os.path.basename(f))[0] in want]
    desktop = None
    if sys.platform.startswith("win") and not here:
        try:
            desktop = HiddenDesktop()
        except OSError as e:
            print("(no hidden desktop: %s; running in the open)" % e)
    bad = []
    try:
        for f in files:
            code, last, text, secs = run_one(f, desktop)
            ok = passed(last, code)
            print("%s %-28s %5.1fs  %s" % ("ok  " if ok else "FAIL", os.path.basename(f), secs, last[:90]))
            if not ok:
                bad.append(os.path.basename(f))
                print("\n".join("      " + l for l in text.splitlines()[-12:]))
    finally:
        if desktop is not None:
            desktop.close()
    print("\n%d test file(s), %d failed%s" % (len(files), len(bad), (": " + ", ".join(bad)) if bad else ""))
    return 1 if bad or not files else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
