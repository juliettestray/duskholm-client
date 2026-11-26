"""The Windows spell checker (ISpellChecker, Windows 8 and later) called straight through ctypes, so there is nothing to
install or bundle. Everything here is main-thread only (it is called from Tk callbacks).

    sp = WinSpell.create()            # None when the checker is not there
    sp.check("I recieve teh letter")  # [(start, end, kind)] in str indices; kind 'spelling', 'repeat' or 'other'
    sp.suggest("recieve")             # ['receive']
"""
import ctypes
import sys
import uuid
from ctypes import POINTER, WINFUNCTYPE, byref, c_int, c_long, c_ulong, c_void_p, c_wchar_p

_CLSID_FACTORY = "7AB36653-1796-484B-BDFA-E74F1DB7C1DC"
_IID_FACTORY = "8E018A9D-2415-4677-BF08-794EA61F94BB"
MAX_CHECK = 20000            # characters handed to Windows in one call
LANGUAGES = ("en-US", "en-GB")
_ACTIONS = {3: "repeat"}     # CORRECTIVE_ACTION_DELETE: a repeated word (1 is get suggestions, 2 is replace)


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]


def _guid(text):
    g = _GUID()
    ctypes.memmove(byref(g), uuid.UUID(text).bytes_le, 16)
    return g


def _method(obj, index, *argtypes):
    """COM method number `index` of `obj` (a raw interface pointer) as a Python callable, `this` filled in."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    fn = WINFUNCTYPE(c_long, c_void_p, *argtypes)(vtbl[index])
    return lambda *a: fn(obj, *a)


def _release(obj):
    try:
        if obj:
            _method(obj, 2)()
    except Exception:
        pass


def utf16_to_str_index(text, u16):
    """Windows counts UTF-16 code units; Python counts characters. They differ after an astral character (an emoji)."""
    n = 0
    for i, ch in enumerate(text):
        if n >= u16:
            return i
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def default_languages():
    """The user's Windows language first, then the fallbacks."""
    out = []
    try:
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
            out.append(buf.value)
    except Exception:
        pass
    return out + [x for x in LANGUAGES if x not in out]


class WinSpell:
    def __init__(self, factory, checker, language):
        self._factory, self._checker, self.language = factory, checker, language

    @classmethod
    def create(cls, languages=None):
        """A checker for the first of `languages` that Windows has a dictionary for, or None."""
        if not sys.platform.startswith("win"):
            return None
        try:
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)                      # (already initialised by something else is fine)
            ole32.CoCreateInstance.argtypes = [POINTER(_GUID), c_void_p, c_ulong, POINTER(_GUID), POINTER(c_void_p)]
            ole32.CoCreateInstance.restype = c_long
            factory = c_void_p()
            if ole32.CoCreateInstance(byref(_guid(_CLSID_FACTORY)), None, 1 | 4, byref(_guid(_IID_FACTORY)), byref(factory)) != 0:
                return None
            for lang in languages or default_languages():
                sup = c_int()
                if _method(factory, 4, c_wchar_p, POINTER(c_int))(lang, byref(sup)) == 0 and sup.value:
                    checker = c_void_p()
                    if _method(factory, 5, c_wchar_p, POINTER(c_void_p))(lang, byref(checker)) == 0 and checker.value:
                        return cls(factory, checker, lang)
            _release(factory)
        except Exception:
            pass
        return None

    def check(self, text):
        """[(start, end, kind)] for each problem in `text`, as str indices. Never raises."""
        text = text[:MAX_CHECK]
        if not text.strip():
            return []
        out = []
        enum = c_void_p()
        try:
            if _method(self._checker, 4, c_wchar_p, POINTER(c_void_p))(text, byref(enum)) != 0 or not enum.value:
                return []
            for _ in range(2000):
                err = c_void_p()
                if _method(enum.value, 3, POINTER(c_void_p))(byref(err)) != 0 or not err.value:
                    break
                start, length, action = c_ulong(), c_ulong(), c_int()
                _method(err.value, 3, POINTER(c_ulong))(byref(start))
                _method(err.value, 4, POINTER(c_ulong))(byref(length))
                _method(err.value, 5, POINTER(c_int))(byref(action))
                _release(err.value)
                a = utf16_to_str_index(text, start.value)
                b = utf16_to_str_index(text, start.value + length.value)
                if b > a:
                    out.append((a, b, _ACTIONS.get(action.value, "spelling")))
        except Exception:
            return out
        finally:
            _release(enum.value)
        return out

    def suggest(self, word, limit=8):
        out = []
        enum = c_void_p()
        try:
            if _method(self._checker, 5, c_wchar_p, POINTER(c_void_p))(word[:100], byref(enum)) != 0 or not enum.value:
                return []
            while len(out) < limit:
                s, got = c_void_p(), c_ulong()
                if _method(enum.value, 3, c_ulong, POINTER(c_void_p), POINTER(c_ulong))(1, byref(s), byref(got)) != 0 or not got.value:
                    break
                out.append(ctypes.wstring_at(s.value))
                ctypes.windll.ole32.CoTaskMemFree(c_void_p(s.value))
        except Exception:
            pass
        finally:
            _release(enum.value)
        return out
