"""Importing triggers and aliases from a MUSHclient file (pure: no window, no network)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import clientimport as CI
import mushimport as M
import triggers as T

HEAD = '<?xml version="1.0" encoding="iso-8859-1"?>\n<!DOCTYPE muclient>\n<muclient>\n'
WORLD = ('<world name="Testworld" site="mud.example.org" port="4000" script_language="Lua" '
         'script_filename="C:\\scripts\\thing.lua" use_ssl="y" command_stack_character=";" > </world>\n')
COLOURS = ('<colours><ansi><normal><colour seq="1" rgb="black" /></normal></ansi><custom>'
           '<colour seq="3" name="Custom3" text="#80FF80" back="black" />'
           '<colour seq="4" name="Custom4" text="aqua" back="navy" /></custom></colours>\n')


def trig(attrs, send=None):
    body = "<send>%s</send>" % send if send is not None else ""
    return "<trigger %s>%s</trigger>\n" % (attrs, body)


def alias(attrs, send):
    return "<alias %s><send>%s</send></alias>\n" % (attrs, send)


def doc(triggers="", aliases="", extra="", world=WORLD, colours=COLOURS):
    return (HEAD + world + colours + "<triggers>\n" + triggers + "</triggers>\n<aliases>\n" + aliases +
            "</aliases>\n" + extra + "</muclient>\n").encode("iso-8859-1")


def one(result):
    assert len(result["triggers"]) == 1, result
    return result["triggers"][0]


# ---- colours ----------------------------------------------------------------------------------------
assert M.colour("saddlebrown") == "#8b4513" and M.colour("#D13000") == "#d13000" and M.colour("WhiteSmoke") == "#f5f5f5"
assert M.colour("") is None and M.colour("notacolour") is None and M.colour(None) is None
assert M.colour("mediumslateblue") == "#7b68ee" and M.colour("slategray") == "#708090" and M.colour("lime") == "#00ff00"

# ---- the world -------------------------------------------------------------------------------------------
r = M.parse(doc())
assert r["world"] == {"name": "Testworld", "host": "mud.example.org", "port": 4000, "tls": True,
                      "note": "imported from MUSHclient"}
assert any("thing.lua" in n and "not run" in n for n in r["notes"])
assert M.parse(doc(world="<world></world>"))["world"] is None

# ---- trigger colours ---------------------------------------------------------------------------------------
r = M.parse(doc(trig('match=" agate" regexp="y" enabled="y" sequence="100" keep_evaluating="y" ignore_case="y" '
                     'custom_colour="17" other_text_colour="#D13000" group="Minerals"')))
t = one(r)
assert t["mode"] == "regex" and t["pattern"] == " agate" and t["enabled"] and t["ignore_case"] and not t["stop"]
assert t["actions"] == [{"type": "highlight", "fg": "#d13000", "bg": None, "bold": False, "scope": "match"}]
assert t["priority"] == 0 and t["name"] == "Minerals: agate" and t["global"] is False and t["world"] == "Testworld"
# a custom colour from the world's palette (3: green on black = no background), and one with a background (4)
t = one(M.parse(doc(trig('match="foo" regexp="y" enabled="y" custom_colour="3"'))))
assert t["actions"][0]["fg"] == "#80ff80" and t["actions"][0]["bg"] is None
t = one(M.parse(doc(trig('match="foo" regexp="y" enabled="y" custom_colour="4"'))))
assert t["actions"][0]["fg"] == "#00ffff" and t["actions"][0]["bg"] == "#000080"
# a stock palette when the file does not carry one
t = one(M.parse(doc(trig('match="foo" regexp="y" enabled="y" custom_colour="1"'), colours="")))
assert t["actions"][0]["fg"] == "#ff8080"
# 'other' colours with a named background; bold
t = one(M.parse(doc(trig('match="x y" regexp="y" enabled="y" custom_colour="17" other_text_colour="white" '
                         'other_back_colour="maroon" make_bold="y"'))))
assert t["actions"][0] == {"type": "highlight", "fg": "#ffffff", "bg": "#800000", "bold": True, "scope": "match"}
# no custom colour set: MUSHclient does nothing with other_text_colour, so neither do we (and we say so)
r = M.parse(doc(trig('match="foo" regexp="y" enabled="y" other_text_colour="#FAFD80"')))
assert not r["triggers"] and r["skipped"][0][0] == "trigger" and "does nothing" in r["skipped"][0][2]
# italic / underline are said to be lost; the colour stays
r = M.parse(doc(trig('match="foo" regexp="y" enabled="y" custom_colour="3" make_underline="y"')))
assert one(r)["actions"][0]["fg"] == "#80ff80" and any("underline" in n for n in r["notes"])

# ---- patterns ------------------------------------------------------------------------------------------------
# MUSHclient's own wildcards match the whole line; ours are the plain mode with anchors
t = one(M.parse(doc(trig('match="* tells you *" enabled="y" custom_colour="3"'))))
assert t["mode"] == "plain" and t["pattern"] == "^* tells you *$"
res = T.match_trigger(dict(t, enabled=True), "Ann tells you 'hello there'")
assert res and res["captures"]["1"] == "Ann" and res["captures"]["2"] == "'hello there'", res
assert T.match_trigger(t, "Ann tells you 'x'") and not T.match_trigger(t, "Ann says hello to you")
# a literal ? or ^ or $ in a wildcard pattern cannot be plain: it becomes an exact regex
t = one(M.parse(doc(trig('match="Really? * now" enabled="y" custom_colour="3"'))))
assert t["mode"] == "regex" and T.match_trigger(t, "Really? yes now") and not T.match_trigger(t, "Really yes now")
assert T.match_trigger(t, "Really? yes now")["captures"]["1"] == "yes"
t = one(M.parse(doc(trig('match="Cost: $5" enabled="y" custom_colour="3"'))))
assert T.match_trigger(t, "Cost: $5") and not T.match_trigger(t, "Cost: $55")
# case: MUSHclient is case sensitive unless ignore_case="y"
t = one(M.parse(doc(trig('match="Hello" enabled="y" custom_colour="3"'))))
assert not t["ignore_case"] and not T.match_trigger(t, "hello") and T.match_trigger(t, "Hello")
# priority runs the other way round (sequence: low first); keep_evaluating decides 'stop'
a = M.parse(doc(trig('match="a" regexp="y" enabled="y" custom_colour="3" sequence="10"') +
                trig('match="b" regexp="y" enabled="y" custom_colour="3" sequence="200" keep_evaluating="y"')))
assert [x["priority"] for x in a["triggers"]] == [90, -100] and [x["stop"] for x in a["triggers"]] == [True, False]
# disabled stays disabled; names stay unique
a = M.parse(doc(trig('match="same" regexp="y" enabled="n" custom_colour="3"') +
                trig('match="same" regexp="y" enabled="y" custom_colour="3"')))
assert [x["enabled"] for x in a["triggers"]] == [False, True] and a["triggers"][0]["name"] != a["triggers"][1]["name"]
# an invalid regex is left out with the reason
r = M.parse(doc(trig('match="(unclosed" regexp="y" enabled="y" custom_colour="3"')))
assert not r["triggers"] and r["skipped"] and r["skipped"][0][0] == "trigger"

# ---- what a trigger does ---------------------------------------------------------------------------------------
t = one(M.parse(doc(trig('match="alizarin" regexp="y" enabled="y" omit_from_output="y" custom_colour="17" '
                         'other_text_colour="red"'))))
assert [a["type"] for a in t["actions"]] == ["highlight", "gag"]
t = one(M.parse(doc(trig('match="^(\\w+) arrives" regexp="y" enabled="y"', send="wave at %1\ngreet %&lt;who&gt;"))))
assert t["actions"] == [{"type": "send", "text": "wave at %1;greet %{who}", "echo": True}], t["actions"]
t = one(M.parse(doc(trig('match="x" regexp="y" enabled="y" send_to="2"', send="seen it"))))
assert t["actions"] == [{"type": "note", "text": "seen it"}]
t = one(M.parse(doc(trig('match="x" regexp="y" enabled="y" send_to="3"', send="low health"))))
assert t["actions"] == [{"type": "status", "text": "low health"}]
t = one(M.parse(doc(trig('match="x" regexp="y" enabled="y" send_to="10"', send="look"))))
assert t["actions"][0]["type"] == "send"
t = one(M.parse(doc(trig('match="x" regexp="y" enabled="y" sound="C:\\a.wav"'))))
assert t["actions"] == [{"type": "beep"}]
t = one(M.parse(doc(trig('match="x" regexp="y" enabled="y" sound="(No sound)" custom_colour="3"'))))
assert [a["type"] for a in t["actions"]] == ["highlight"]
# scripts are never run: the part that is not a script comes across, a script-only trigger is left out
r = M.parse(doc(trig('match="x" regexp="y" enabled="y" send_to="12"', send="Note(1)") +
                trig('match="y" regexp="y" enabled="y" script="OnY"') +
                trig('match="z" regexp="y" enabled="y" script="OnZ" custom_colour="3"')))
assert [t["pattern"] for t in r["triggers"]] == ["z"] and len(r["skipped"]) == 2
assert any("script function OnZ" in n for n in r["notes"]) and any("a script" in n for n in r["notes"])
# multi-line and repeat
r = M.parse(doc(trig('match="x" regexp="y" enabled="y" custom_colour="3" lines_to_match="3"') +
                trig('match="y" regexp="y" enabled="y" custom_colour="3" repeat="y"')))
assert len(r["triggers"]) == 2 and any("several lines" in n for n in r["notes"])
assert r["triggers"][0]["actions"][0]["scope"] == "match" and r["triggers"][1]["actions"][0]["scope"] == "all", \
    "repeat colours every match"
t = one(M.parse(doc(trig('match="foo" enabled="y" custom_colour="3" repeat="y"'))))
assert t["actions"][0]["scope"] == "match", "repeat means nothing for a wildcard pattern (which matches the whole line)"
# a long command is cut between commands, never inside one
cmds = ";".join("emote does something number %d" % i for i in range(12))
t = one(M.parse(doc(trig('match="x" regexp="y" enabled="y"', send=cmds.replace(";", "\n")))))
sends = [a["text"] for a in t["actions"] if a["type"] == "send"]
assert len(sends) >= 2 and all(len(s) <= T.MAX_TEXT for s in sends) and ";".join(sends) == cmds

# ---- aliases -----------------------------------------------------------------------------------------------------
r = M.parse(doc(aliases=alias('match="dc" enabled="y"', "trash corpse") +
                alias('match="emit *" enabled="y"', "emote %0") +
                alias('match="gt *" enabled="y"', "say %1") +
                alias('match="^go (.*)$" enabled="y" regexp="y"', "walk %1;look") +
                alias('match="two words" enabled="y"', "x") +
                alias('match="a * b *" enabled="y"', "y") +
                alias('match="scr" enabled="y" send_to="12"', "Note(1)") +
                alias('match="dc" enabled="y"', "again")))
by = {a["name"]: a for a in r["aliases"]}
assert by["dc"]["body"] == "trash corpse"
assert by["emit"]["body"] == "emote emit %*", "MUSHclient's %0 is the whole line, the word included"
assert by["gt"]["body"] == "say %*" and by["go"]["body"] == "walk %*;look"
assert set(by) == {"dc", "emit", "gt", "go"} and all(a["world"] == "Testworld" and a["global"] is False for a in by.values())
reasons = {label: why for kind, label, why in r["skipped"] if kind == "alias"}
assert "two words" in reasons and "a * b *" in reasons and "scr" in reasons and "dc" in reasons, reasons
assert any("%0" in n and "emit" in n for n in r["notes"])
# a typed alias behaves
assert T.expand_alias(by["gt"], "hello there") == ["say hello there"]
assert T.expand_alias(by["go"], "north") == ["walk north", "look"]

# ---- counts and the rest of the file ------------------------------------------------------------------------------
extra = ('<timers><timer name="t1" /><timer name="t2" /></timers>\n'
         '<macros><macro name="up" type="send_now"><send>up</send></macro></macros>\n'
         '<keypad><key name="8"><send>north</send></key><key name="Ctrl+8"></key></keypad>\n'
         '<include name="C:\\plugins\\Thing_One.xml" plugin="y" />\n')
r = M.parse(doc(extra=extra))
assert r["counts"] == {"triggers_seen": 0, "aliases_seen": 0, "timers": 2, "macros": 1, "keys": 1, "plugins": 1}, r["counts"]
assert any("2 timers not imported" in n for n in r["notes"]) and any("Thing_One.xml" in n for n in r["notes"])
lines = M.describe(r)
assert lines[0].startswith("World: Testworld") and any("Macros and keypad keys" in l for l in lines)
# a plugin file: the same triggers, with a note that its script is not run
plug = (HEAD + '<plugin name="Colours" language="Lua" id="abc" ></plugin>\n<triggers>\n' +
        trig('match="foo" regexp="y" enabled="y" custom_colour="3"') + '</triggers>\n<script><![CDATA[ function x() end ]]></script>\n</muclient>\n').encode()
r = M.parse(plug)
assert r["plugin"] and len(r["triggers"]) == 1 and r["world"] is None and any("plugin" in n.lower() for n in r["notes"])
assert r["triggers"][0].get("global", True) is True, "no world in the file: the rules are not tied to one"
r = M.parse(plug, world_name="Mine")
assert r["triggers"][0]["world"] == "Mine" and r["triggers"][0]["global"] is False

# ---- files that are refused -----------------------------------------------------------------------------------------
for bad, why in ((b"<html><body>hi</body></html>", "not a MUSHclient"), (b"not xml at all", "XML"),
                 (b'<?xml version="1.0"?><!DOCTYPE muclient [<!ENTITY x "y">]><muclient>&x;</muclient>', "entities"),
                 (b'<?xml version="1.0"?><!DOCTYPE muclient SYSTEM "http://evil.example/x.dtd"><muclient/>', None),
                 (b"x" * (M.MAX_BYTES + 1), "too big"), (None, "not a file")):
    try:
        M.parse(bad)
    except M.ImportProblem as e:
        assert why is None or why.lower() in str(e).lower(), (why, str(e))
    else:
        if why is not None:
            raise AssertionError("should have been refused: %r" % (bad[:40] if bad else bad))
# text works as well as bytes
assert M.parse(doc().decode("iso-8859-1"))["world"]["name"] == "Testworld"

# ---- the front door ------------------------------------------------------------------------------------------------------
assert CI.detect(doc()) == "mushclient" and CI.detect(b"\xef\xbb\xbf" + doc()) == "mushclient" and CI.detect(b"hello") is None
try:
    CI.read(b"just some text")
except M.ImportProblem as e:
    assert "MUSHclient" in str(e)
kind, res = CI.read(doc(trig('match="foo" regexp="y" enabled="y" custom_colour="3"', send="hi"),
                        alias('match="dc" enabled="y"', "trash corpse")))
assert kind == "mushclient" and CI.report(kind, res)[0] == "Read as a MUSHclient file."

# apply: validated, tied to the world, sends and aliases switched off unless trusted
tools = {"clean_world": lambda w: dict(w, port=int(w["port"])) if w.get("host") else None,
         "validate_trigger": T.validate_trigger, "validate_alias": T.validate_alias}
cfg = {"worlds": [], "triggers": [], "alias_rules": []}
said, scope = CI.apply(cfg, res, tools, add_world=True)
assert scope == "Testworld" and len(cfg["triggers"]) == 1 and len(cfg["alias_rules"]) == 1 and len(cfg["worlds"]) == 1
assert cfg["triggers"][0]["enabled"] is False, "a trigger that sends is switched off"
assert cfg["alias_rules"][0]["enabled"] is False
assert cfg["triggers"][0]["world"] == "Testworld" and cfg["alias_rules"][0]["world"] == "Testworld"
assert any("Added the world 'Testworld'" in s for s in said) and any("switched off" in s for s in said)
said, _ = CI.apply(cfg, res, tools, add_world=True)                      # again: nothing doubles
assert len(cfg["triggers"]) == 1 and len(cfg["alias_rules"]) == 1 and len(cfg["worlds"]) == 1
assert any("already" in s for s in said), said
cfg = {"worlds": [], "triggers": [], "alias_rules": []}
CI.apply(cfg, res, tools, trust=True)
assert cfg["triggers"][0]["enabled"] is True and cfg["alias_rules"][0]["enabled"] is True and not cfg["worlds"]
# another world's name; colour-only triggers are on, since they cannot send anything
cfg = {"worlds": [], "triggers": [], "alias_rules": []}
_k, res2 = CI.read(doc(trig('match="foo" regexp="y" enabled="y" custom_colour="3"')))
CI.apply(cfg, res2, tools, world_name="Elsewhere")
assert cfg["triggers"][0]["enabled"] is True and cfg["triggers"][0]["world"] == "Elsewhere"
# an empty world name: the rules work in every world
cfg = {"worlds": [], "triggers": [], "alias_rules": []}
CI.apply(cfg, res2, tools, world_name="")
assert "world" not in cfg["triggers"][0] and cfg["triggers"][0].get("global", True) is True
# the limits
cfg = {"worlds": [], "triggers": [{"name": "n%d" % i, "mode": "plain", "pattern": "p%d" % i, "enabled": True,
                                   "ignore_case": True, "priority": 0, "stop": False,
                                   "actions": [{"type": "gag"}]} for i in range(CI.MAX_TRIGGERS - 1)],
       "alias_rules": []}
many = doc("".join(trig('match="m%d" regexp="y" enabled="y" custom_colour="3"' % i) for i in range(5)))
said, _ = CI.apply(cfg, CI.read(many)[1], tools)
assert len(cfg["triggers"]) == CI.MAX_TRIGGERS and any("did not fit" in s for s in said), said

print("importer tests OK")
