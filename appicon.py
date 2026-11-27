"""The window and taskbar icon (sanctuary.ico, next to this file, or inside the packaged exe)."""
import os
import sys

NAME = "sanctuary.ico"
APP_ID = "Sanctuary.MudClient"      # so the taskbar shows our icon, not the Python one, when run from source


def icon_path():
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, NAME)


def apply(root):
    """Give every window of the program the icon. Quietly does nothing where it cannot (no file, not Windows)."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    p = icon_path()
    if not os.path.exists(p):
        return False
    try:
        root.iconbitmap(default=p)
        return True
    except Exception:
        return False
