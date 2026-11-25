"""Build a single-file Windows program and a zip to hand out.

    python make_exe.py

Needs PyInstaller (`pip install pyinstaller`). Writes dist/Sanctuary.exe,
dist/Sanctuary-<version>-win64.zip (the exe, README and licence) and the matching .sha256 file
that the in-program updater checks. Nothing here is needed to
run Sanctuary from source."""
import hashlib
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))


def commit():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or "dev"
    except (OSError, subprocess.SubprocessError):
        return "dev"


def main():
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed", "--exclude-module", "numpy",
           "--name", "Sanctuary", "--distpath", os.path.join(HERE, "dist"),
           "--workpath", os.path.join(HERE, "build"), "--specpath", os.path.join(HERE, "build"),
           os.path.join(HERE, "sanctuary.py")]
    print("Running:", " ".join(cmd))
    if subprocess.call(cmd, cwd=HERE) != 0:
        print("PyInstaller failed.")
        return 1
    exe = os.path.join(HERE, "dist", "Sanctuary.exe")
    if not os.path.exists(exe):
        print("No exe was produced.")
        return 1
    sys.path.insert(0, HERE)
    import version
    zpath = os.path.join(HERE, "dist", "Sanctuary-%s-win64.zip" % version.__version__)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, "Sanctuary/Sanctuary.exe")
        for name in ("README.md", "LICENSE"):
            p = os.path.join(HERE, name)
            if os.path.exists(p):
                z.write(p, "Sanctuary/" + name)
    digest = hashlib.sha256(open(zpath, "rb").read()).hexdigest()
    with open(zpath + ".sha256", "w", encoding="ascii", newline="\n") as f:
        f.write("%s  %s\n" % (digest, os.path.basename(zpath)))
    print("Built", exe)
    print("Zip  ", zpath)
    print("Sum  ", zpath + ".sha256", digest)
    print("Commit", commit())
    return 0


if __name__ == "__main__":
    sys.exit(main())
