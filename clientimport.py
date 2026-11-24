"""Importing triggers and aliases from other MUD clients: one door for all of them.

`read(data)` finds out what kind of file it is and parses it into the common result (see mushimport.parse), and
`apply(cfg, result, tools, ...)` merges that result into the settings the same careful way a world file is merged: every
rule is re-validated, duplicates are skipped, and anything that could send commands to the game arrives switched OFF
(unless the person says they trust the file). Nothing in an imported file is ever run."""
import mushimport
from mushimport import ImportProblem

from triggers import MAX_TRIGGERS, MAX_ALIASES

KINDS = {"mushclient": "MUSHclient"}
PARSERS = {"mushclient": mushimport.parse}


def detect(data):
    """'mushclient' (or another kind as importers are added), or None."""
    head = bytes(data[:6000]).lstrip(b"\xef\xbb\xbf \r\n\t").lower() if isinstance(data, (bytes, bytearray)) else \
        str(data[:6000]).lstrip("﻿ \r\n\t").lower().encode("utf-8", "replace")
    if b"<muclient" in head or b"<!doctype muclient" in head:
        return "mushclient"
    return None


def read(data, world_name=None):
    """(kind, result). Raises ImportProblem with a sentence for the person when the file is not one we can read."""
    kind = detect(data)
    if kind is None:
        raise ImportProblem("I do not know what kind of file that is. I can read MUSHclient world, plugin and "
                            "trigger files (.MCL / .xml).")
    return kind, PARSERS[kind](data, world_name)


def report(kind, result, limit=8):
    return ["Read as a %s file." % KINDS.get(kind, kind)] + mushimport.describe(result, limit)


def _sends(rule):
    return any(isinstance(a, dict) and a.get("type") == "send" for a in rule.get("actions", []))


def apply(cfg, result, tools, add_world=False, trust=False, world_name=None):
    """Merge `result` into cfg in place. `tools` has clean_world, validate_trigger, validate_alias.
    world_name: None ties the rules to the file's own world (none if it has none), a name ties them to that world, and
    '' leaves them working in every world. Returns (sentences, world name used)."""
    said = []
    scope = (world_name if world_name is not None else (result.get("world") or {}).get("name") or "").strip()
    if add_world and result.get("world"):
        w = tools["clean_world"](result["world"])
        if w is None:
            said.append("The file's world entry is not usable (no host or port), so no world was added.")
        else:
            names = {x["name"].lower() for x in cfg.get("worlds", [])}
            if w["name"].lower() in names:
                said.append("A world called '%s' is already saved, so it was left as it is." % w["name"])
            else:
                cfg["worlds"] = list(cfg.get("worlds", [])) + [w]
                said.append("Added the world '%s' (%s:%d)." % (w["name"], w["host"], w["port"]))
    retarget = world_name is not None and scope != (result.get("world") or {}).get("name")

    def tie(rule):
        rule = dict(rule)
        if scope and (retarget or rule.get("global") is False):
            rule.update({"global": False, "world": scope})
        elif not scope:
            rule.pop("global", None)
            rule.pop("world", None)
        return rule
    have = {(t["name"].lower(), t.get("pattern"), str(t.get("world", "")).lower()) for t in cfg.get("triggers", [])}
    added = off = dup = full = 0
    for raw in result.get("triggers", []):
        t = tools["validate_trigger"](tie(raw))
        if t is None:
            continue
        key = (t["name"].lower(), t.get("pattern"), str(t.get("world", "")).lower())
        if key in have:
            dup += 1
            continue
        if len(cfg["triggers"]) >= MAX_TRIGGERS:
            full += 1
            continue
        if _sends(t) and not trust:
            t["enabled"] = False
            off += 1
        cfg["triggers"] = list(cfg["triggers"]) + [t]
        have.add(key)
        added += 1
    if added or dup or full:
        bits = ["Added %d trigger%s" % (added, "" if added == 1 else "s")]
        if off:
            bits.append("%d that send%s commands %s switched off until you check %s"
                        % (off, "s" if off == 1 else "", "is" if off == 1 else "are", "it" if off == 1 else "them"))
        if dup:
            bits.append("%d already there" % dup)
        if full:
            bits.append("%d did not fit (at most %d)" % (full, MAX_TRIGGERS))
        said.append("; ".join(bits) + ".")
    have = {(a["name"].lower(), str(a.get("world", "")).lower()) for a in cfg.get("alias_rules", [])}
    added = dup = full = 0
    for raw in result.get("aliases", []):
        a = tools["validate_alias"](tie(raw))
        if a is None:
            continue
        key = (a["name"].lower(), str(a.get("world", "")).lower())
        if key in have:
            dup += 1
            continue
        if len(cfg["alias_rules"]) >= MAX_ALIASES:
            full += 1
            continue
        if not trust:
            a["enabled"] = False
        cfg["alias_rules"] = list(cfg["alias_rules"]) + [a]
        have.add(key)
        added += 1
    if added or dup or full:
        said.append("Added %d alias%s%s%s%s." % (
            added, "" if added == 1 else "es",
            ", switched off (turn on the ones you want in Alt+A)" if added and not trust else "",
            "; %d already there" % dup if dup else "", "; %d did not fit (at most %d)" % (full, MAX_ALIASES) if full else ""))
    if not said:
        said.append("Nothing new to add.")
    return said, scope
