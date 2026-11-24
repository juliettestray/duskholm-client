"""Importing triggers and aliases from a Mudlet package (pure: no window, no network)."""
import io
import os
import re
import sys
import zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import clientimport as CI
import mudletimport as MU
import triggers as T
from mushimport import ImportProblem

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE MudletPackage>\n<MudletPackage version="1.001">\n'


def trig(pats, name="t", command="", script="", flags="", active="yes", fg="#ff0000", bg="#ffff00", sound="", multi="no"):
    strings = "".join("<string>%s</string>" % p for p, _ in pats)
    kinds = "".join("<integer>%d</integer>" % k for _, k in pats)
    attrs = {"isActive": active, "isFolder": "no", "isMultiline": multi, "isPerlSlashGOption": "no",
             "isColorizerTrigger": "no", "isFilterTrigger": "no", "isSoundTrigger": "no"}
    attrs.update(re.findall(r'(\w+)="(\w+)"', flags))
    head = " ".join('%s="%s"' % kv for kv in attrs.items())
    return ("<Trigger %s><name>%s</name><script>%s</script><mCommand>%s</mCommand><mSoundFile>%s</mSoundFile>"
            "<mFgColor>%s</mFgColor><mBgColor>%s</mBgColor><regexCodeList>%s</regexCodeList>"
            "<regexCodePropertyList>%s</regexCodePropertyList></Trigger>"
            % (head, name, script, command, sound, fg, bg, strings, kinds))


def als(regex, command="", script="", active="yes", name="a"):
    return ('<Alias isActive="%s" isFolder="no"><name>%s</name><script>%s</script><command>%s</command>'
            '<packageName></packageName><regex>%s</regex></Alias>\n' % (active, name, script, command, regex))


def doc(t="", a="", extra=""):
    return (HEAD + "<TriggerPackage>\n" + t + "</TriggerPackage>\n<AliasPackage>\n" + a + "</AliasPackage>\n" + extra +
            "</MudletPackage>\n").encode("utf-8")


# ---- detection and the friend's real shapes ---------------------------------------------------------------------------
assert CI.detect(doc()) == "mudlet" and CI.detect(b"<muclient>") == "mushclient"
kind, r = CI.read(doc(trig([("Hello there", 0)], name="greet", command="wave"), als("^hi$", command="smile")))
assert kind == "mudlet" and r["world"] is None
t = r["triggers"][0]
assert t["name"] == "greet" and t["mode"] == "plain" and t["pattern"] == "Hello there" and t["ignore_case"] is False
assert t["actions"] == [{"type": "send", "text": "wave", "echo": True}] and "global" not in t and t["enabled"]
assert r["aliases"][0] == {"name": "hi", "enabled": True, "body": "smile"}
assert "Read as a Mudlet file." in CI.report(kind, r)[0]

# ---- pattern types ------------------------------------------------------------------------------------------------------
r = MU.parse(doc(trig([("a*b", 0), ("^start", 2), ("whole line", 3), ("(\\d+) gold", 1), ("x", 4), ("y", 5), ("z", 6)], command="go")))
got = [(x["mode"], x["pattern"]) for x in r["triggers"]]
assert got == [("regex", "a\\*b"), ("regex", "^\\^start"), ("plain", "^whole line$"), ("regex", "(\\d+) gold")], got
assert T.match_trigger(r["triggers"][0], "xa*by") and not T.match_trigger(r["triggers"][0], "xaby"), "a star is a star here"
assert T.match_trigger(r["triggers"][2], "whole line") and not T.match_trigger(r["triggers"][2], "the whole line!")
assert T.match_trigger(r["triggers"][3], "you find 12 gold")
assert any("a Lua function" in n and "a line spacer" in n and "a colour pattern" in n for n in r["notes"]), r["notes"]
assert len({x["name"].lower() for x in r["triggers"]}) == 4, "names stay different"
r = MU.parse(doc(trig([("Hello", 0)], name="Tell", command="x") + trig([("Hello", 0)], name="Tell", command="y")))
assert [x["name"] for x in r["triggers"]] == ["Tell", "Tell (2)"]
r = MU.parse(doc(trig([("zzz", 4)], command="x")))
assert not r["triggers"] and r["skipped"][0][0] == "trigger" and "Lua function" in r["skipped"][0][2]
r = MU.parse(doc(trig([("a", 0), ("b", 0)], multi="yes", command="x")))
assert not r["triggers"] and "several lines" in r["skipped"][0][2]
r = MU.parse(doc(trig([("a", 0)])))
assert not r["triggers"] and "nothing" in r["skipped"][0][2]
r = MU.parse(doc(trig([("a", 0)], active="no", command="x")))
assert r["triggers"][0]["enabled"] is False, "off stays off"

# ---- colours, sound, per-world tie ----------------------------------------------------------------------------------------
r = MU.parse(doc(trig([("gold", 0)], flags='isColorizerTrigger="yes"', fg="#00ff00", bg="#000000")))
assert r["triggers"][0]["actions"] == [{"type": "highlight", "fg": "#00ff00", "bg": None, "bold": False, "scope": "match"}]
r = MU.parse(doc(trig([("gold", 0)], flags='isColorizerTrigger="yes"')))
assert r["triggers"][0]["actions"][0]["bg"] == "#ffff00" and r["triggers"][0]["actions"][0]["fg"] == "#ff0000"
r = MU.parse(doc(trig([("gold", 0)], flags='isSoundTrigger="yes"', sound="C:/a.wav")))
assert r["triggers"][0]["actions"] == [{"type": "beep"}] and any("beep" in n for n in r["notes"])
r = MU.parse(doc(trig([("gold", 0)], command="x")), world_name="Duskholm")
assert r["triggers"][0]["global"] is False and r["triggers"][0]["world"] == "Duskholm"

# ---- commands: separators and percent signs --------------------------------------------------------------------------------
r = MU.parse(doc(trig([("a", 0)], command="one;;two&#10;three 50%")))
assert [x["text"] for x in r["triggers"][0]["actions"]] == ["one;two;three 50%%"], r["triggers"][0]["actions"]
r = MU.parse(doc(a=als("^noob", command="feet 5;inches 5;birthday 1999 2 11")))
assert r["aliases"][0]["body"] == "feet 5;inches 5;birthday 1999 2 11"

# ---- the one kind of Lua we read: send("text" .. matches[n]) ---------------------------------------------------------------
lua = 'local target = matches[2] or ""&#10;send("name " .. matches[2])&#10;send("short " .. matches[2])&#10;-- done&#10;send("long " .. matches[2], false)'
r = MU.parse(doc(a=als("^mn (.+)", script=lua)))
assert r["aliases"] == [{"name": "mn", "enabled": True, "body": "name %*;short %*;long %*"}], r["aliases"]
assert T.expand_alias(r["aliases"][0], "Bo Peep") == ["name Bo Peep", "short Bo Peep", "long Bo Peep"]
r = MU.parse(doc(a=als("^unstash (\\S+)$", script='send("get " .. matches[2] .. " stash")')))
assert r["aliases"][0]["body"] == "get %1 stash"
r = MU.parse(doc(a=als("^w (.*)", script='send(matches[1])')))
assert r["aliases"][0]["body"] == "w %*", "matches[1] is everything typed"
r = MU.parse(doc(a=als("^go$", command="look", script='send("say 100%")')))
assert r["aliases"][0]["body"] == "look;say 100%%"
r = MU.parse(doc(a=als("^q$", script='send("a" .. matches[3])')))
assert not r["aliases"] and "Lua script" in r["skipped"][0][2], r["skipped"]
r = MU.parse(doc(a=als("^q (.+)", script='send("a" .. matches[2])\nos.execute("x")')))
assert not r["aliases"], "anything but send() lines is not read, and never run"
r = MU.parse(doc(a=als("^q$", command="look", script='os.execute("x")')))
assert r["aliases"][0]["body"] == "look" and any("Lua script is not run" in n for n in r["notes"])
r = MU.parse(doc(trig([("(\\w+) waves", 1)], script='send("wave " .. matches[2])&#10;send("hi")')))
assert [x["text"] for x in r["triggers"][0]["actions"]] == ["wave %1", "hi"], r["triggers"][0]["actions"]
r = MU.parse(doc(trig([("a", 0)], script='send("a" .. matches[1])')))
assert r["triggers"][0]["actions"][0]["text"] == "a%0"

# ---- alias shapes ---------------------------------------------------------------------------------------------------------------
r = MU.parse(doc(a=als("^text ywellia (.+)", script='send("text yoinkyraccoonmaskedthief " .. matches[2])') +
                   als("^a b$", command="x") + als("^(\\w+) go", command="x") + als("^a b c d$", command="x")))
assert [(a["name"], a["body"]) for a in r["aliases"]] == [("text ywellia", "text yoinkyraccoonmaskedthief %*"), ("a b", "x")], r["aliases"]
assert len(r["skipped"]) == 2 and all("more than" in s[2] for s in r["skipped"]), r["skipped"]
assert T.find_alias_line("text ywellia hi there", r["aliases"])[0] is r["aliases"][0]
assert T.expand_alias(r["aliases"][0], " hi there") == ["text yoinkyraccoonmaskedthief hi there"]
r = MU.parse(doc(a=als("^go$", command="a") + als("^Go$", command="b")))
assert len(r["aliases"]) == 1 and "same name" in r["skipped"][0][2]
r = MU.parse(doc(a=als("^go$", command="a", active="no")))
assert r["aliases"][0]["enabled"] is False

# ---- folders: nested, and a switched-off folder switches off what is inside ------------------------------------------------------
folder = ('<TriggerGroup isActive="no" isFolder="yes"><name>f</name>\n' + trig([("in folder", 0)], name="inner", command="x") +
          '<TriggerGroup isActive="yes" isFolder="yes"><name>g</name>' + trig([("deeper", 0)], name="deep", command="y") +
          '</TriggerGroup></TriggerGroup>\n')
r = MU.parse(doc(t=folder + trig([("outside", 0)], name="out", command="z")))
assert [(x["name"], x["enabled"]) for x in r["triggers"]] == [("inner", False), ("deep", False), ("out", True)], r["triggers"]
afolder = ('<AliasGroup isActive="yes" isFolder="yes"><name>n</name>' + als("^noob", command="feet 5") + '</AliasGroup>')
assert MU.parse(doc(a=afolder))["aliases"][0]["name"] == "noob"

# ---- what is not read is said ---------------------------------------------------------------------------------------------------
r = MU.parse(doc(extra='<TimerPackage><Timer isActive="yes" isFolder="no"><name>x</name></Timer></TimerPackage>'
                       '<ScriptPackage><Script isActive="yes" isFolder="no"><name>s</name></Script></ScriptPackage>'))
assert any("1 timer" in n and "1 script" in n for n in r["notes"]), r["notes"]

# ---- a package inside a zip -----------------------------------------------------------------------------------------------------
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("config.lua", 'mpackage = "x"')
    z.writestr("x.xml", doc(trig([("zip trigger", 0)], command="x")))
assert CI.detect(buf.getvalue()) == "mudlet"
assert CI.read(buf.getvalue())[1]["triggers"][0]["pattern"] == "zip trigger"
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("readme.txt", "no xml here")
assert CI.detect(buf.getvalue()) is None

# ---- refusals ------------------------------------------------------------------------------------------------------------------
for bad in (b'<?xml version="1.0"?><!DOCTYPE MudletPackage [<!ENTITY a "b">]><MudletPackage/>',
            b"<MudletPackage><TriggerPackage></MudletPackage>", b"<other/>"):
    try:
        MU.parse(bad)
        raise AssertionError("should have refused")
    except ImportProblem:
        pass
assert MU.parse(doc())["triggers"] == []
print("mudlet import tests OK")
