"""The program icon: the file is there with every size Windows asks for, and applying it sets the window's icon."""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
import appicon

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


p = appicon.icon_path()
check("icon file exists", os.path.exists(p))
data = open(p, "rb").read()
n = struct.unpack("<H", data[4:6])[0]
sizes = sorted((data[6 + 16 * i] or 256) for i in range(n))
check("has 16 to 256 px sizes", sizes == [16, 24, 32, 48, 64, 128, 256])

root = tk.Tk()
check("apply returns True", appicon.apply(root) is True)
root.destroy()

appicon.NAME = "nothere.ico"
root = tk.Tk()
check("missing file is quietly skipped", appicon.apply(root) is False)
root.destroy()

print("FAILED: %s" % fails if fails else "all passed")
sys.exit(1 if fails else 0)
