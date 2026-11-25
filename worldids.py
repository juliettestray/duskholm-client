"""Stable world IDs, so the things tied to a world (rules, buttons, pane layouts, clock settings) follow the world when
its name is changed.

Every saved world has an `id` (random, made once, kept in the settings). A rule or button that works in only one world
stores that world's id as `world_id` and, as a courtesy for reading the file and for the lists, its name as `world`.
`link(cfg)` keeps the two in step: a rule that only has a name (made before ids, imported, or edited in a form) is tied to
the saved world of that name, and every tied rule gets the world's current name. Pane layouts (`world_panes`) and clock
settings (`world_time`) were keyed by the lower-case name; they are re-keyed by id. A world that is not saved has no id and
is still told apart by its name, as before."""
import re
import uuid

ID_RE = re.compile(r"^[0-9a-f]{8,32}$")
RULE_LISTS = ("triggers", "alias_rules", "buttons")


def valid_id(x):
    return isinstance(x, str) and bool(ID_RE.match(x))


def new_id(taken=()):
    taken = set(taken)
    while True:
        i = uuid.uuid4().hex[:10]
        if i not in taken:
            return i


def assign_ids(worlds):
    """Give every world in the list a valid, unique `id` (kept if it already has one). Returns the same list."""
    seen = set()
    for w in worlds:
        if isinstance(w, dict) and valid_id(w.get("id")) and w["id"] not in seen:
            seen.add(w["id"])
        elif isinstance(w, dict):
            w["id"] = ""
    for w in worlds:
        if isinstance(w, dict) and not w.get("id"):
            w["id"] = new_id(seen)
            seen.add(w["id"])
    return worlds


def key_for(world_id, name):
    """The key per-world tables use: the id for a saved world, the lower-case name otherwise."""
    return world_id or str(name or "").strip().lower()


def link(cfg):
    """Bring rules, buttons, pane layouts and clock settings in line with the saved worlds' ids and names (in place).
    Returns True if anything changed."""
    worlds = [w for w in (cfg.get("worlds") or []) if isinstance(w, dict) and valid_id(w.get("id"))]
    by_id = {w["id"]: w for w in worlds}
    by_name = {str(w["name"]).strip().lower(): w for w in worlds}
    changed = False
    for key in RULE_LISTS:
        for r in cfg.get(key) or []:
            if not isinstance(r, dict) or r.get("global", True) is not False:
                continue
            w = by_id.get(r.get("world_id"))
            if w is None:
                w = by_name.get(str(r.get("world", "")).strip().lower())       # a name only, or an id that no longer exists
            if w is None:
                continue
            if r.get("world_id") != w["id"]:
                r["world_id"], changed = w["id"], True
            if r.get("world") != w["name"]:
                r["world"], changed = w["name"], True
    for table in ("world_time", "world_panes"):
        t = cfg.get(table)
        if not isinstance(t, dict):
            continue
        for k in list(t):
            w = by_name.get(str(k).strip().lower()) if not valid_id(k) or k not in by_id else None
            if w is not None and w["id"] not in t:
                t[w["id"]] = t.pop(k)
                changed = True
    return changed
