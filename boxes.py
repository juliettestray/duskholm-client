"""Join the game's ASCII boxes into solid line-drawing characters (stdlib only).

The game draws boxes with | - _ . , ' characters, which leave gaps in most fonts. This turns the
ones that really are part of a box into the box-drawing characters that join up, without changing
the length of any line (so colours and columns stay exactly where they were). Ordinary text is
never touched: a line is only a box line when it looks like one."""

_TOP = ".,"
_BOT = "'`"
_CORNERS = _TOP + _BOT
_RUN = "-_"
V, H = "│", "─"
TL, TR, BL, BR = "┌", "┐", "└", "┘"
TEE_DOWN, TEE_UP, TEE_R, TEE_L = "┬", "┴", "├", "┤"


def _is_box_row(s):
    t = s.strip()
    return len(t) >= 2 and t[0] == "|" and t[-1] == "|"


def _is_border(s):
    t = s.strip()
    return len(t) >= 5 and t[0] in _CORNERS + "|" and t[-1] in _CORNERS + "|" and all(c in _CORNERS + _RUN + "|" for c in t)


def connect_line(line):
    """One line (no newline) with its box characters joined; same length as the input."""
    try:
        if len(line) < 3 or len(line) > 4000 or not (_is_box_row(line) or _is_border(line)):
            return line
        out = list(line)
        n = len(line)
        i = 0
        owned = {}                                    # corner index -> 'l' (left of a run), 'r', or 'lr'
        base = set()                                  # corners that belong to an underscore floor
        runs = []
        while i < n:
            if line[i] in _RUN:
                j = i
                while j < n and line[j] in _RUN:
                    j += 1
                if j - i >= 3:
                    runs.append((i, j))
                i = j
            else:
                i += 1
        for a, b in runs:
            if a > 0 and line[a - 1] in _CORNERS + "|" and b < n and line[b] in _CORNERS + "|":
                for k in range(a, b):
                    out[k] = H
                owned[a - 1] = owned.get(a - 1, "") + "l"
                owned[b] = owned.get(b, "") + "r"
                if line[a] == "_":
                    base.update((a - 1, b))                   # an underscore run is the floor of a box
        for k, role in owned.items():
            ch = line[k]
            top = ch in _TOP
            if ch == "|":
                if k in base:
                    out[k] = BL if role == "l" else BR if role == "r" else V
                else:
                    out[k] = TEE_R if role == "l" else TEE_L if role == "r" else V
            elif len(role) == 2:
                out[k] = TEE_DOWN if top else TEE_UP
            elif role == "l":
                out[k] = TL if top else BL
            else:
                out[k] = TR if top else BR
        if _is_box_row(line):
            for k in range(n):
                if line[k] == "|" and out[k] == "|":
                    out[k] = V
        return "".join(out)
    except Exception:
        return line


def connect_text(text):
    """Join the boxes in a block of text (lines separated by newlines); same length."""
    if not isinstance(text, str) or "|" not in text and "-" not in text and "_" not in text:
        return text
    return "\n".join(connect_line(l.rstrip("\r")) + ("\r" if l.endswith("\r") else "") for l in text.split("\n"))


def connect_pieces(pieces, skip_tags=()):
    """[(text, tag)] -> the same pieces with boxes joined. Colours/tags stay on the same columns."""
    try:
        if not pieces:
            return pieces
        keep = [(t[0] if isinstance(t, tuple) and t[:1] == ("echo",) else t) in skip_tags for _x, t in pieces]
        flat = "".join("\0" * len(x) if k else x for (x, _t), k in zip(pieces, keep))
        new = connect_text(flat)
        if new == flat or len(new) != len(flat):
            return pieces
        out, pos = [], 0
        for (x, t), k in zip(pieces, keep):
            out.append((x if k else new[pos:pos + len(x)], t))
            pos += len(x)
        return out
    except Exception:
        return pieces
