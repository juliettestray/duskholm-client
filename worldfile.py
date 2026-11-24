"""World settings files (.snc): export a world's setup and import someone else's, safely.

A file holds the world (name, host, port, TLS, note) and, optionally, the triggers, aliases, pane
layout, custom prompt formats, gradients and designs that go with it. It is plain JSON. Importing
never runs anything: every part is re-validated, and anything that could send commands to the game
(triggers with a send action, aliases) arrives switched OFF for the person to look over."""
import json

FORMAT = "sanctuary-world"
VERSION = 1
MAX_BYTES = 1_000_000
EXT = ".snc"
PARTS = ("triggers", "aliases", "panes", "prompts", "gradients", "designs")


def build(cfg, world, parts):
    """The bundle (a dict) for `world` (a cleaned world dict) with the chosen parts of cfg."""
    b = {"format": FORMAT, "version": VERSION, "world": dict(world)}
    b["world"].pop("last", None)
    parts = set(parts or ())
    if "triggers" in parts:
        b["triggers"] = list(cfg.get("triggers", []))
    if "aliases" in parts:
        b["alias_rules"] = list(cfg.get("alias_rules", []))
    if "panes" in parts:
        b["panes"] = list(cfg.get("panes", []))
        b["layout"] = cfg.get("layout")
    if "prompts" in parts:
        b["prompt_custom"] = list(cfg.get("prompt_custom", []))
    if "gradients" in parts:
        b["gradients"] = list(cfg.get("gradients", []))
    if "designs" in parts:
        b["designs"] = list(cfg.get("designs", []))
    return b


def dumps(bundle):
    return json.dumps(bundle, indent=1, ensure_ascii=False, sort_keys=True)


def loads(text):
    """(bundle or None, problem). Only checks that it is one of ours; contents are cleaned on import."""
    if not isinstance(text, str) or len(text) > MAX_BYTES:
        return None, "That file is too big to be a world file."
    try:
        d = json.loads(text)
    except (ValueError, RecursionError):
        return None, "That is not a Sanctuary world file."
    if not isinstance(d, dict) or d.get("format") != FORMAT:
        return None, "That is not a Sanctuary world file."
    v = d.get("version")
    if not isinstance(v, int) or isinstance(v, bool) or v < 1 or v > VERSION:
        return None, "That file is from a newer Sanctuary (version %s)." % str(v)[:6]
    return d, ""


def _sends(trigger):
    return any(isinstance(a, dict) and a.get("type") == "send" for a in trigger.get("actions", []))


def merge(cfg, bundle, tools):
    """Merge a loaded bundle into cfg (changed in place). `tools` provides the cleaners:
    clean_world, validate_trigger, validate_alias, validate_prompt, validate_panes, validate_layout,
    validate_gradients, validate_designs. Returns a list of sentences telling what happened."""
    said = []
    w = tools["clean_world"](bundle.get("world"))
    if w is None:
        said.append("The file's world entry is not usable, so no world was added.")
    else:
        names = {x["name"].lower() for x in cfg.get("worlds", [])}
        name, n = w["name"], 2
        while name.lower() in names:
            name = "%s (%d)" % (w["name"][:34], n)
            n += 1
        w["name"] = name
        cfg["worlds"] = list(cfg.get("worlds", [])) + [w]
        said.append("Added the world '%s' (%s:%d)." % (name, w["host"], w["port"]))

    if isinstance(bundle.get("triggers"), list):
        have = {(t["name"].lower(), t.get("pattern")) for t in cfg.get("triggers", [])}
        added = off = 0
        for raw in bundle["triggers"][:500]:
            t = tools["validate_trigger"](raw)
            if t is None or (t["name"].lower(), t.get("pattern")) in have or len(cfg["triggers"]) >= 500:
                continue
            if _sends(t):
                t["enabled"] = False
                off += 1
            cfg["triggers"] = list(cfg["triggers"]) + [t]
            have.add((t["name"].lower(), t.get("pattern")))
            added += 1
        if added:
            said.append("Added %d trigger%s%s." % (added, "" if added == 1 else "s",
                                                  "; %d that send commands %s switched off until you check %s"
                                                  % (off, "is" if off == 1 else "are", "it" if off == 1 else "them")
                                                  if off else ""))
    if isinstance(bundle.get("alias_rules"), list):
        have = {a["name"].lower() for a in cfg.get("alias_rules", [])}
        added = 0
        for raw in bundle["alias_rules"][:200]:
            a = tools["validate_alias"](raw)
            if a is None or a["name"].lower() in have or len(cfg["alias_rules"]) >= 200:
                continue
            a["enabled"] = False
            cfg["alias_rules"] = list(cfg["alias_rules"]) + [a]
            have.add(a["name"].lower())
            added += 1
        if added:
            said.append("Added %d alias%s, switched off (turn on the ones you want in Alt+A)."
                        % (added, "" if added == 1 else "es"))
    if isinstance(bundle.get("panes"), list):
        panes = tools["validate_panes"](bundle["panes"])
        mine = {p["name"].lower() for p in cfg.get("panes", [])}
        new = [p for p in panes if p["name"].lower() not in mine]
        if not cfg.get("layout", {}).get("regions") and panes:
            cfg["panes"] = list(cfg.get("panes", [])) + new
            cfg["layout"] = tools["validate_layout"](bundle.get("layout"), [p["name"] for p in cfg["panes"]])
            said.append("Adopted the file's pane layout (%d panes)." % len(panes))
        elif new:
            cfg["panes"] = list(cfg.get("panes", [])) + new
            said.append("Added %d pane%s (your own layout was kept; place them in Ctrl+P)."
                        % (len(new), "" if len(new) == 1 else "s"))
    if isinstance(bundle.get("prompt_custom"), list):
        have = {p["name"].lower() for p in cfg.get("prompt_custom", [])}
        added = 0
        for raw in bundle["prompt_custom"][:20]:
            p = tools["validate_prompt"](raw)
            if p is not None and p["kind"] == "regex" and p["name"].lower() not in have and len(cfg["prompt_custom"]) < 20:
                cfg["prompt_custom"] = list(cfg["prompt_custom"]) + [p]
                have.add(p["name"].lower())
                added += 1
        if added:
            said.append("Added %d prompt format%s." % (added, "" if added == 1 else "s"))
    for key, label in (("gradients", "gradient pattern"), ("designs", "design")):
        if isinstance(bundle.get(key), list):
            cleaned = tools["validate_" + key](bundle[key])
            have = {x["name"].lower() + "|" + x.get("type", "") for x in cfg.get(key, [])}
            new = [x for x in cleaned if x["name"].lower() + "|" + x.get("type", "") not in have]
            if new:
                cfg[key] = tools["validate_" + key](list(cfg.get(key, [])) + new)
                said.append("Added %d %s%s." % (len(new), label, "" if len(new) == 1 else "s"))
    return said
