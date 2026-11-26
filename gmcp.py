"""GMCP: game data the server sends on a side channel (telnet option 201).

The byte layer lives in sanctuary.Terminal (it answers WILL GMCP, subscribes, and keeps the last message
for each package in term.gmcp). This file is the part the player meets: the /gmcp command, plain-words
descriptions of the data, and the screen-reader preset that speaks changes."""
import copy
import json
import re
import time

OPTION_ON = "gmcp"            # cfg: use GMCP when the game offers it (takes effect on the next connect)
OPTION_SR = "gmcp_sr"         # cfg: screen reader mode speaks GMCP changes
CHANNEL_KEEP = 200            # channel lines remembered for /gmcp channels
SHOW_MAX = 2000               # longest dump of one package /gmcp show prints

TOPICS = ("vitals", "status", "here", "who", "items", "skills", "afflictions", "channels", "damage", "scan", "map", "show")


# ---- plain-words helpers (pure) -------------------------------------------------------------------------
def names_of(data):
    """The names in a Room.Players / Room.Mobs / Afflictions / Who list, in order."""
    out = []
    for e in data if isinstance(data, list) else []:
        n = e.get("name") if isinstance(e, dict) else None
        if isinstance(n, str) and n:
            out.append(n)
    return out


def diff_names(old, new):
    """(arrived, left) between two name lists. A name that appears twice counts twice."""
    left = list(old)
    arrived = []
    for n in new:
        if n in left:
            left.remove(n)
        else:
            arrived.append(n)
    return arrived, left


def _num(v, default=0):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def offset_words(x, y, z=0):
    """'2 east, 3 south' for scan coordinates (x east+, y north+, z up+). 'here' for 0,0,0."""
    bits = []
    for v, plus, minus in ((_num(y), "north", "south"), (_num(x), "east", "west"), (_num(z), "up", "down")):
        if v:
            bits.append("%d %s" % (abs(int(v)), plus if v > 0 else minus))
    return ", ".join(bits) or "here"


def describe_scan(scan):
    """Combat.Scan read nearest-first, one line per person or point."""
    if not isinstance(scan, dict):
        return []
    lines = []
    for p in scan.get("people") if isinstance(scan.get("people"), list) else []:
        if not isinstance(p, dict) or p.get("me"):
            continue
        s = "%s, %s, %s" % (p.get("name") or p.get("label") or "someone", "hostile" if p.get("hostile") else "friendly",
                            offset_words(p.get("x"), p.get("y"), p.get("z")))
        if p.get("target"):
            s += ", %s %s" % (p.get("action") or "fighting", p["target"])
        if p.get("cover"):
            s += ", behind " + str(p["cover"])
        lines.append(s)
    for p in scan.get("points") if isinstance(scan.get("points"), list) else []:
        if isinstance(p, dict):
            lines.append("%s point, %s" % (p.get("type") or "map", offset_words(p.get("x"), p.get("y"))))
    return lines


def describe_vitals(v):
    if not isinstance(v, dict) or "hp" not in v:
        return ""
    s = "Health %d of %d" % (_num(v.get("hp")), _num(v.get("maxhp")))
    for key, word in (("wounds", "wounds"), ("debuff", "debuffs"), ("lag", "seconds of lag")):
        if _num(v.get(key)) > 0:
            s += ", %d %s" % (v[key], word)
    return s


def describe_status(st):
    if not isinstance(st, dict) or not st:
        return ""
    s = str(st.get("position") or "")
    if st.get("fighting"):
        s += ", fighting" + (" (%s)" % st["combat"] if st.get("combat") not in (None, "", "none") else "")
    return s.strip(", ")


def describe_combat_status(st):
    if not isinstance(st, dict) or not st:
        return ""
    s = "Facing %s" % st.get("facing", "?")
    s += ", attack %ds, move %ds" % (_num(st.get("attack")), _num(st.get("move")))
    for key, word in (("fatigued", "fatigued"), ("carrier", "carrying the bag")):
        if st.get(key):
            s += ", " + word
    if st.get("cover"):
        s += ", behind " + str(st["cover"])
    if st.get("target"):
        s += ", %s %s" % (st.get("action") or "fighting", st["target"])
    return s


def describe_items(data):
    if not isinstance(data, dict):
        return ""
    names = names_of(data.get("items"))
    return "%s: %s" % (data.get("location", "items"), ", ".join(names) if names else "nothing")


# ---- the status bar and the live panes (pure: data in, lines out) ---------------------------------------
FACING = {"north": "N", "northeast": "NE", "east": "E", "southeast": "SE", "south": "S", "southwest": "SW",
          "west": "W", "northwest": "NW"}
BAR_LABEL = "DF"
# A line is a list of (text, role); the roles are mapped to colours by the client.
ROLES = ("normal", "dim", "good", "warn", "bad", "cyan", "magenta", "blue", "head")


def short_offset(x, y, z=0):
    """'2S 2W' (and 'U1' / 'D1' for floors) for scan coordinates; 'here' when all are 0."""
    bits = []
    y, x, z = _num(y), _num(x), _num(z)
    if y:
        bits.append("%d%s" % (abs(int(y)), "N" if y > 0 else "S"))
    if x:
        bits.append("%d%s" % (abs(int(x)), "E" if x > 0 else "W"))
    if z:
        bits.append("%s%d" % ("U" if z > 0 else "D", abs(int(z))))
    return " ".join(bits) or "here"


def operation_text(scan):
    """'Securing the area 40%' from Combat.Scan's operation entry, or ''."""
    op = scan.get("operation") if isinstance(scan, dict) else None
    if not isinstance(op, dict) or not isinstance(op.get("percent"), (int, float)):
        return ""
    task = str(op.get("task") or "Operation").strip()
    return "%s %d%%" % (task[:1].upper() + task[1:], max(0, min(100, int(op["percent"]))))


def view_from_gmcp(g):
    """What the stat bars draw (the same shape prompts.parse_prompt gives), from the live data. None until
    Char.Vitals has arrived."""
    v = g.get("Char.Vitals")
    if not isinstance(v, dict) or not _num(v.get("maxhp")):
        return None
    cs = g.get("Combat.Status") if isinstance(g.get("Combat.Status"), dict) else {}
    st = g.get("Char.Status") if isinstance(g.get("Char.Status"), dict) else {}
    hp, mx = int(_num(v.get("hp"))), int(_num(v.get("maxhp")))
    text = []
    if st.get("position"):
        text.append(str(st["position"]).capitalize())
    if cs.get("combat") in ("fast", "slow"):
        text.append("%s combat" % cs["combat"].capitalize())
    face = FACING.get(cs.get("facing"))
    if face and cs.get("size"):
        text.append("%s %d/%d:%d/%d" % (face, _num(cs.get("x")), _num(cs.get("size")), _num(cs.get("y")), _num(cs.get("size"))))
    op = operation_text(g.get("Combat.Scan"))
    if op:
        text.append(op)
    return {"gauges": [(BAR_LABEL, hp, mx)], "hp": (hp, mx, BAR_LABEL),
            "counters": [("ST", int(_num(v.get("debuff")))), ("WN", int(_num(v.get("wounds")))), ("LG", int(_num(v.get("lag"))))],
            "cooldowns": [("M", int(_num(cs.get("move")))), ("K", int(_num(cs.get("attack"))))],
            "text": text, "live": True}


DAMAGE_KEEP = 200


def damage_line(d):
    """One hit as a pane line: 'You > A man  Striking 22  stagger +10' or 'A man > you  Striking 22  stagger +10'.
    Only what the game showed: a field it left out is left out here."""
    if not isinstance(d, dict) or d.get("dir") not in ("out", "in"):
        return None
    out = d["dir"] == "out"
    other = str(d.get("target" if out else "source") or "")
    head = ("You > " + other) if out else ((other + " > you") if other else "Hit you")
    bits = [(head.strip(" >"), "good" if out else "bad")]
    if d.get("attack"):
        bits.append(("  " + str(d["attack"]), "normal"))
    if isinstance(d.get("damage"), (int, float)):
        bits.append(("  %d" % d["damage"], "warn"))
    if isinstance(d.get("stagger"), (int, float)):
        bits.append(("  stagger +%d" % d["stagger"], "magenta"))
    return bits


def here_lines(g):
    room = g.get("Room.Info") if isinstance(g.get("Room.Info"), dict) else None
    if room is None:
        return [[("Nothing in sight yet.", "dim")]]
    lines = [[(str(room.get("name") or "somewhere"), "head")]]
    if room.get("area"):
        lines.append([(str(room["area"]), "dim")])
    for label, pkg in (("People", "Room.Players"), ("Creatures", "Room.Mobs")):
        names = names_of(g.get(pkg))
        lines.append([(label + ": ", "dim"), (", ".join(names) if names else "none", "normal")])
    ex = room.get("exits")
    if isinstance(ex, dict):
        lines.append([("Exits: ", "dim"), (" ".join(sorted(ex)) or "none", "normal")])
    return lines


def _people(scan):
    out = []
    for p in scan.get("people") if isinstance(scan, dict) and isinstance(scan.get("people"), list) else []:
        if isinstance(p, dict):
            out.append(p)
    return out


def _person_line(p):
    bits = [(str(p.get("name") or p.get("label") or "someone"), "bad" if p.get("hostile") else "cyan"),
            ("  " + short_offset(p.get("x"), p.get("y"), p.get("z")), "normal")]
    if _num(p.get("distance")):
        bits.append(("  D%d" % p["distance"], "dim"))
    if p.get("target"):
        bits.append(("  %s %s" % (p.get("action") or "fighting", p["target"]), "warn"))
    if p.get("cover"):
        bits.append(("  behind " + str(p["cover"]), "dim"))
    if p.get("carrier"):
        bits.append(("  has the bag", "magenta"))
    return bits


def scan_lines(g):
    """The hostile people scan shows, nearest first, with their cover; your own cover on top."""
    scan, cs = g.get("Combat.Scan"), g.get("Combat.Status")
    lines = []
    if isinstance(cs, dict) and cs:
        me = [("You: facing " + str(cs.get("facing", "?")), "head")]
        if cs.get("cover"):
            me.append(("  behind " + str(cs["cover"]), "good"))
        lines.append(me)
    foes = [p for p in _people(scan) if p.get("hostile") and not p.get("me")]
    lines += [_person_line(p) for p in foes]
    for p in scan.get("points") if isinstance(scan, dict) and isinstance(scan.get("points"), list) else []:
        if isinstance(p, dict):
            lines.append([("%s point %s" % (str(p.get("type") or "map").capitalize(), p.get("label") or ""), "magenta"),
                          ("  " + short_offset(p.get("x"), p.get("y")), "normal")])
    return lines or [[("No enemies in sight.", "dim")]]


def allies_lines(g):
    """The friendly people scan shows (not you), nearest first."""
    allies = [p for p in _people(g.get("Combat.Scan")) if not p.get("hostile") and not p.get("me")]
    return [_person_line(p) for p in allies] or [[("Nobody you can see.", "dim")]]


_TERRAIN = {"}": "blue", "E": "warn", "C": "magenta"}


def map_me(g):
    """(row, character column of the first of the two characters) where 'Me' is on Combat.Map, or None."""
    m = g.get("Combat.Map")
    rows = m.get("rows") if isinstance(m, dict) and isinstance(m.get("rows"), list) else []
    for r, row in enumerate(rows[:60]):
        row = str(row)
        for i in range(0, len(row), 2):
            if row[i:i + 2] == "Me":
                return r, i
    return None


def map_lines(g, cols=None, height=None):
    """Combat.Map with each person coloured: you green, enemies red, friends cyan; water blue, the rest dim.
    Given the pane's size in characters, it is padded so 'Me' sits in the middle of the pane."""
    m, scan = g.get("Combat.Map"), g.get("Combat.Scan")
    rows = m.get("rows") if isinstance(m, dict) and isinstance(m.get("rows"), list) else []
    if not rows:
        return [[("No map outside a fight.", "dim")]]
    who = {str(p.get("label")): p for p in _people(scan) if p.get("label")}
    lines = []
    for row in rows[:60]:
        row, parts = str(row), []
        for i in range(0, len(row), 2):
            cell = row[i:i + 2]
            p = who.get(cell)
            if p is not None:
                role = "good" if p.get("me") else "bad" if p.get("hostile") else "cyan"
            else:
                role = _TERRAIN.get(cell.strip()[:1], "dim") if cell.strip() else "dim"
            if parts and parts[-1][1] == role:
                parts[-1] = (parts[-1][0] + cell, role)
            else:
                parts.append((cell, role))
        lines.append(parts)
    me = map_me(g)
    if me is not None and cols and height:
        lpad = max(0, cols // 2 - (me[1] + 1))
        tpad = max(0, height // 2 - me[0])
        if lpad:
            lines = [[(" " * lpad, "dim")] + parts for parts in lines]
        lines = [[("", "dim")] for _ in range(tpad)] + lines
    return lines


# ---- the Duskholm default layouts --------------------------------------------------------------------
LAYOUT_NAME = "duskholm"
FIGHT_HOLD_MS = 3000          # the fight layout stays this long after the fight ends, so a lull does not flip it
PANE_LINES = {"Here": 200, "Chat": 500, "Phone": 500, "Map": 200, "Damage": 300, "Allies": 200, "Scan": 200}
BAR_PACKAGES = ("char.vitals", "char.status", "combat.status", "combat.scan")
LIVE = {"room.info": ("Here",), "room.players": ("Here",), "room.mobs": ("Here",),
        "combat.scan": ("Scan", "Allies", "Map"), "combat.map": ("Map",), "combat.status": ("Scan",)}
CHAT_COLOUR = {"ooc": "cyan", "faction": "warn", "sect": "warn", "cult": "warn"}
SOCIETY_TAG = {"faction": "[faction] ", "sect": "[sect] ", "cult": "[cult] "}
_TEXT_OUT = re.compile(r"^You text (.+?): (.*)$", re.S)


def duskholm_layout(mode, dos=False):
    """(pane names, layout) for 'calm' or 'fight'. Windows and DOS share the shape; DOS columns are a little narrower."""
    w = 30 if dos else 36
    if mode == "fight":
        regions = [{"side": "right", "size": w, "weight": 9, "panes": ["Map"]},
                   {"side": "right", "size": w, "weight": 2, "panes": ["Chat", "Phone"]},
                   {"side": "right", "size": w, "weight": 2, "panes": ["Damage"]},
                   {"side": "right", "size": w, "weight": 1, "panes": ["Allies"]},
                   {"side": "bottom", "size": 5, "weight": 1, "panes": ["Scan"]}]
    else:
        regions = [{"side": "right", "size": w, "weight": 2, "panes": ["Here"]},
                   {"side": "right", "size": w, "weight": 3, "panes": ["Chat", "Phone"]}]
    names = [n for r in regions for n in r["panes"]]
    return names, {"regions": regions}


def plain_of(pieces):
    return "".join(t for t, _k in pieces)


class GmcpMixin:
    # ---- state ---------------------------------------------------------------------------------------
    def gmcp_active(self):
        return bool(self.connected and self.term.gmcp_on)

    def gmcp_get(self, name, default=None):
        return self.term.gmcp.get(name, default)

    def _gmcp_speaks(self, package):
        """True when the voice reads this package itself (so the prompt-based alert must stay quiet)."""
        return bool(self.cfg.get(OPTION_SR) and self.sr_on() and self.gmcp_active() and package in self.term.gmcp)

    def _gmcp_state(self):
        st = getattr(self.term, "gmcp_extra", None)
        if st is None:
            st = self.term.gmcp_extra = {"channels": [], "base": {}, "room": None, "fight": None}
        return st

    # ---- events from the terminal --------------------------------------------------------------------
    def _gmcp_on_event(self, ev):
        k = ev[0]
        if k == "gmcp_on":
            self._gmcp_state()
        elif k == "gmcp":
            self._gmcp_message(ev[1], ev[2])

    def _gmcp_message(self, name, data):
        self._gmcp_speech(name, data)
        self._gmcp_ui(name, data)

    def _gmcp_speech(self, name, data):
        st = self._gmcp_state()
        key = name.lower()
        if key == "comm.channel.text" and isinstance(data, dict) and isinstance(data.get("text"), str):
            st["channels"].append((str(data.get("channel", "")), data["text"]))
            del st["channels"][:-CHANNEL_KEEP]
            return
        if key == "room.info":
            num = data.get("num") if isinstance(data, dict) else None
            if num != st["room"]:
                st["room"] = num
                st["base"].pop("room.players", None)       # the lists for the new room are the starting point, not news
                st["base"].pop("room.mobs", None)
            return
        if not self._gmcp_speak_wanted():
            if key in ("room.players", "room.mobs"):
                st["base"][key] = names_of(data)
            return
        if key in ("room.players", "room.mobs"):
            new = names_of(data)
            old = st["base"].get(key)
            st["base"][key] = new
            if old is not None:
                arrived, left = diff_names(old, new)
                for n in arrived:
                    self.speech.say_now("%s arrives" % n)
                for n in left:
                    self.speech.say_now("%s leaves" % n)
        elif key == "char.vitals":
            self._gmcp_say_health(data)
        elif key == "char.status" and isinstance(data, dict):
            fight = bool(data.get("fighting"))
            old, st["fight"] = st["fight"], fight
            if old is not None and fight != old:
                self.speech.say_now("Fight started" if fight else "Fight over")

    def _gmcp_speak_wanted(self):
        return bool(self.cfg.get(OPTION_SR) and self.sr_on() and self._here())

    def _gmcp_say_health(self, v):
        """Speak when health crosses one of the same steps the prompt alerts use."""
        if not isinstance(v, dict) or not _num(v.get("maxhp")):
            return
        import access
        frac = 100.0 * _num(v.get("hp")) / v["maxhp"]
        band = sum(1 for s in access.HEALTH_STEPS if frac < s)
        st = self.term.gmcp_extra
        old, st["health"] = st.get("health"), band
        if old is not None and band > old:
            self.speech.say_now("Health %d percent" % round(frac))

    # ---- the /gmcp command ---------------------------------------------------------------------------
    def _gmcp_command(self, arg):
        bits = arg.split(None, 1)
        sub = bits[0].lower() if bits else ""
        rest = bits[1].strip() if len(bits) > 1 else ""
        if sub in ("on", "off"):
            self._set_extra(OPTION_ON, sub == "on")
            self.system("GMCP %s. It takes effect the next time you connect." % ("on" if sub == "on" else "off"))
            return
        if sub == "layout":
            want = rest.lower() or ("off" if self.cfg.get("gmcp_layout") == LAYOUT_NAME else LAYOUT_NAME)
            if want not in ("off", LAYOUT_NAME):
                self.system("Usage: /gmcp layout [duskholm|off]")
                return
            self._set_extra("gmcp_layout", want)
            self.system("GMCP layout: %s." % ("Duskholm default" if want == LAYOUT_NAME else "off"))
            return
        if sub == "sr":
            new = (not self.cfg.get(OPTION_SR)) if rest.lower() not in ("on", "off") else rest.lower() == "on"
            self._set_extra(OPTION_SR, new)
            self.system("Screen reader GMCP speech %s." % ("on" if new else "off"))
            return
        if not sub:
            self._gmcp_status()
            return
        if not self.gmcp_active():
            self.system("The game is not sending GMCP." + ("" if self.cfg.get(OPTION_ON) else
                        " Turn it on first with /gmcp on, then reconnect."))
            return
        text = self._gmcp_topic(sub, rest)
        self.system(text if text else "Nothing received for that yet.")

    def _gmcp_status(self):
        on = self.cfg.get(OPTION_ON)
        lines = ["GMCP is %s%s." % ("on" if on else "off", "" if on else " (type /gmcp on, then reconnect)")]
        if self.gmcp_active():
            lines.append("The game is sending: " + (", ".join(sorted(self.term.gmcp)) or "nothing yet"))
        elif on:
            lines.append("This game has not offered GMCP on this connection.")
        lines.append("Screen reader speech from GMCP: %s (/gmcp sr)." % ("on" if self.cfg.get(OPTION_SR) else "off"))
        lines.append("Layout: %s (/gmcp layout [duskholm|off])." % ("Duskholm default" if self.cfg.get("gmcp_layout") == LAYOUT_NAME else "off"))
        lines.append("Topics: /gmcp " + ", ".join(TOPICS[:-1]) + ", or show <Package.Name>.")
        self.system("\n".join(lines))

    def _gmcp_topic(self, sub, rest):
        g = self.term.gmcp
        if sub == "vitals":
            return describe_vitals(g.get("Char.Vitals"))
        if sub == "status":
            return "; ".join(x for x in (describe_status(g.get("Char.Status")), describe_combat_status(g.get("Combat.Status"))) if x)
        if sub == "here":
            room = g.get("Room.Info") if isinstance(g.get("Room.Info"), dict) else {}
            lines = [room.get("name", "")] if room.get("name") else []
            for label, pkg in (("People", "Room.Players"), ("Creatures", "Room.Mobs")):
                n = names_of(g.get(pkg))
                lines.append("%s: %s" % (label, ", ".join(n) if n else "none"))
            ex = room.get("exits")
            if isinstance(ex, dict):
                lines.append("Exits: " + (", ".join(sorted(ex)) or "none"))
            return "\n".join(lines)
        if sub == "who":
            n = names_of(g.get("Game.Who"))
            return "%d online: %s" % (len(n), ", ".join(n)) if n else ""
        if sub == "items":
            return describe_items(g.get("Char.Items.List"))
        if sub == "skills":
            data = g.get("Char.Skills.List")
            return ", ".join("%s %s" % (e.get("name"), e.get("rank")) for e in data if isinstance(e, dict)) if isinstance(data, list) else ""
        if sub == "afflictions":
            n = names_of(g.get("Char.Afflictions.List"))
            return ", ".join(n) if n else ("none" if "Char.Afflictions.List" in g else "")
        if sub == "damage":
            try:
                count = max(1, min(DAMAGE_KEEP, int(rest or 10)))
            except ValueError:
                count = 10
            return chr(10).join(self._gmcp_state().get("damage", [])[-count:])
        if sub == "channels":
            st = self._gmcp_state()
            try:
                count = max(1, min(CHANNEL_KEEP, int(rest or 10)))
            except ValueError:
                count = 10
            return "\n".join(t for _c, t in st["channels"][-count:])
        if sub == "scan":
            lines = describe_scan(g.get("Combat.Scan"))
            return "\n".join(lines) if lines else ("Nobody in sight." if "Combat.Scan" in g else "")
        if sub == "map":
            m = g.get("Combat.Map")
            rows = m.get("rows") if isinstance(m, dict) else None
            return ("Facing %s\n" % m.get("facing", "?") + "\n".join(str(r) for r in rows)) if rows else ""
        if sub == "show":
            for k, v in g.items():
                if k.lower() == rest.lower():
                    return (k + " " + json.dumps(v, ensure_ascii=False))[:SHOW_MAX]
            return "No data for %s." % (rest or "that package")
        return "Unknown topic. Topics: " + ", ".join(TOPICS[:-1]) + ", show <Package.Name>."

    # ---- the status bars ------------------------------------------------------------------------------
    def _gmcp_view(self):
        """The stat bars' content from the live data (None when the game is not sending Char.Vitals)."""
        if not self.gmcp_active():
            return None
        return view_from_gmcp(self.term.gmcp)

    def _gmcp_bar(self):
        if not self._here():
            return
        view = self._prompt_view()
        if view:
            self.statbar.set_data(view)
            self._statbar_show()
            self.update_dosbar()
            self.sr_alerts(view)

    # ---- events: bars, panes, layout ----------------------------------------------------------------
    def _gmcp_ui(self, name, data):
        key = name.lower()
        if key in BAR_PACKAGES:
            self._gmcp_bar()
        if key == "char.status" and isinstance(data, dict):
            self._gmcp_fight(bool(data.get("fighting")))
        if not self._gmcp_layout_on():
            return
        if key == "comm.channel.text":
            self._gmcp_chat(data)
        elif key == "combat.damage":
            self._gmcp_damage(data)
        elif key in LIVE and self._here():
            for pane in LIVE[key]:
                self._gmcp_live(pane)

    def _gmcp_fight(self, fighting):
        st = self._gmcp_state()
        job = st.pop("fight_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        if fighting:
            if st.get("mode") != "fight":
                st["new_fight"] = True            # the damage pane starts the next fight under a dividing line
            st["mode"] = "fight"
            self._gmcp_layout_apply()
            return
        if st.get("mode") == "fight":
            sess = self.session

            def calm():
                if sess in self.sessions and sess is self.session:
                    self._gmcp_state().pop("fight_job", None)
                    self._gmcp_state()["mode"] = "calm"
                    self._gmcp_layout_apply()
            try:
                st["fight_job"] = self.root.after(FIGHT_HOLD_MS, calm)
            except Exception:
                calm()
        else:
            st["mode"] = "calm"
            self._gmcp_layout_apply()

    # ---- the panes ----------------------------------------------------------------------------------
    def _gmcp_layout_on(self):
        return self.cfg.get("gmcp_layout") == LAYOUT_NAME and self.gmcp_active()

    def _gmcp_key(self, role):
        """The text style (as the main window's tags use) for one of the roles."""
        th = self.theme
        ansi = th["ansi"]
        fg = {"dim": th["dim"], "good": ansi[10], "warn": ansi[11], "bad": ansi[9], "cyan": ansi[14],
              "magenta": ansi[13], "blue": ansi[12], "head": th["alert"]}.get(role)
        return (fg, None, role == "head", False, False, False)

    def _gmcp_pane_size(self, name):
        """The pane's size in characters (columns, rows), or None before it has been laid out."""
        pane = self._panes.get(name.lower())
        if pane is None:
            return None
        try:
            t = pane["text"]
            if t.winfo_width() < 40 or t.winfo_height() < 20:
                return None
            cw, lh = max(1, self.f_norm.measure("0")), max(1, self.f_norm.metrics("linespace"))
            return max(1, (t.winfo_width() - 16) // cw), max(1, (t.winfo_height() - 8) // lh)
        except Exception:
            return None

    def _gmcp_pane_set(self, name, lines, centre_row=None):
        """Replace everything in a live pane, but only when the lines are different from what it shows."""
        pane = self._panes.get(name.lower())
        if pane is None or self._pane_region(name) is None:
            return
        sig = tuple(tuple(l) for l in lines)
        if pane.get("live") == sig:
            return
        self.pane_clear(name)
        for line in lines:
            self.pane_append(name, [(t, self._gmcp_key(r)) for t, r in line])
        pane["unread"] = 0
        pane["live"] = sig
        pane["follow"] = False
        try:
            size = self._gmcp_pane_size(name)
            if centre_row is not None and size and len(lines) > size[1]:      # taller than the pane: keep the middle on you
                pane["text"].yview_moveto(max(0.0, (centre_row - size[1] / 2.0) / len(lines)))
            else:
                pane["text"].yview_moveto(0)
        except Exception:
            pass
        self._style_region_ui()

    def _gmcp_live(self, name):
        g = self.term.gmcp
        if name == "Map":
            size = self._gmcp_pane_size("Map") or (None, None)
            me = map_me(g)
            lines = map_lines(g, size[0], size[1])
            self._gmcp_pane_set("Map", lines, None if me is None else me[0] + len(lines) - len(g["Combat.Map"]["rows"]))
            return
        fn = {"Here": here_lines, "Scan": scan_lines, "Allies": allies_lines}.get(name)
        if fn is not None:
            self._gmcp_pane_set(name, fn(g))

    def _gmcp_map_soon(self):
        sess = self.session
        if getattr(sess, "_gmcp_map_job", None) is not None:
            return

        def redo():
            sess._gmcp_map_job = None
            if sess is self.session and sess is getattr(self, "_shown", sess) and self._gmcp_layout_on():
                self._gmcp_live("Map")
        try:
            sess._gmcp_map_job = self.root.after(120, redo)
        except Exception:
            sess._gmcp_map_job = None

    def _gmcp_live_all(self):
        for name in ("Here", "Scan", "Allies", "Map"):
            self._gmcp_live(name)

    def _gmcp_append_once(self, pane, role_pieces):
        """One line into a pane, unless an identical one is already among the last few (the older text
        capture rules may be filling the same pane)."""
        key = pane.lower()
        p = self._panes.get(key)
        text = plain_of(role_pieces)
        if p is not None and any(plain_of(h) == text for h in p["history"][-30:]):
            return
        self.pane_append(pane, [(t, self._gmcp_key(r)) for t, r in role_pieces])

    def _gmcp_damage(self, data):
        line = damage_line(data)
        if line is None:
            return
        st = self._gmcp_state()
        st.setdefault("damage", []).append(plain_of(line))
        del st["damage"][:-DAMAGE_KEEP]
        pane = self._panes.get("damage")
        if pane is not None and st.get("new_fight") and pane["history"]:
            st["new_fight"] = False
            self.pane_append("Damage", [("---- new fight ----", self._gmcp_key("dim"))])
        st["new_fight"] = False
        self.pane_append("Damage", [(t, self._gmcp_key(r)) for t, r in line])

    def _gmcp_chat(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("text"), str):
            return
        chan, text = str(data.get("channel", "")).lower(), data["text"]
        if chan == "text":
            m = _TEXT_OUT.match(text)
            if m:                                           # your own text: the way the Phone look reads it
                text = "[%s]You > %s: %s" % (self._game_stamp(), m.group(1), m.group(2))
            self._gmcp_append_once("Phone", [(text, "normal")])
            return
        self._gmcp_append_once("Chat", [(SOCIETY_TAG.get(chan, ""), "warn")] * bool(SOCIETY_TAG.get(chan)) +
                               [(text, CHAT_COLOUR.get(chan, "normal"))])

    # ---- the layouts --------------------------------------------------------------------------------
    def _gmcp_layout_apply(self, force=False):
        """Put the calm or the fight layout on screen (when the preset is on and this world is the one shown)."""
        import layout as lay
        if not self._gmcp_layout_on() or not self._here() or lay is None:
            return
        st = self._gmcp_state()
        mode = st.get("mode") or "calm"
        key = (mode, bool(self.dos))
        if not force and st.get("applied") == key:
            return
        names, wanted = duskholm_layout(mode, bool(self.dos))
        if getattr(self.session, "_gmcp_prev", None) is None:
            self.session._gmcp_prev = copy.deepcopy(self.cfg["layout"])
        for n in names:
            if self._find_pane_def(n) is None:
                if len(self.cfg["panes"]) >= lay.MAX_PANES:
                    self.system("Not enough room for the GMCP panes: delete a pane under View > Panes / layout first.")
                    return
                d = lay.validate_pane({"name": n, "max_lines": PANE_LINES.get(n, 300)})
                self.cfg["panes"] = self.cfg["panes"] + [d]
        self.cfg["layout"] = lay.validate_layout(wanted, known_panes=[d["name"] for d in self.cfg["panes"]])
        st["applied"] = key
        for n in names:
            pane = self.pane_ensure(n)
            if n == "Map" and pane is not None and not pane.get("gmcp_bound"):
                pane["gmcp_bound"] = True                      # (the map is centred on you, so it follows the pane's size)
                pane["text"].bind("<Configure>", lambda _e: self._gmcp_map_soon(), add="+")
        self._save_settings()
        self.schedule_layout(5)
        self._gmcp_live_all()

    def _gmcp_world_shown(self):
        """This world has just come to the front: its bars and panes are brought up to date."""
        if not self.gmcp_active():
            return
        self._gmcp_bar()
        if self._gmcp_layout_on():
            self._gmcp_layout_apply(force=True)

    def _gmcp_layout_option(self, old, new):
        import layout as lay
        if new == LAYOUT_NAME:
            if not self.cfg.get(OPTION_ON):
                self.system("The GMCP layout needs GMCP: turn on 'GMCP game data' in Options and reconnect.")
            elif not self.gmcp_active():
                self.system("The GMCP layout starts when the game offers GMCP (reconnect).")
            else:
                self._gmcp_layout_apply(force=True)
        elif old == LAYOUT_NAME and lay is not None:
            prev = getattr(self.session, "_gmcp_prev", None)
            names = [d["name"] for d in self.cfg["panes"]]
            self.cfg["layout"] = (lay.validate_layout(prev, known_panes=names) if prev is not None
                                  else lay.preset_layout("Right column", [n for n in names if n not in PANE_LINES]))
            self.session._gmcp_prev = None
            self._gmcp_state().pop("applied", None)
            self._save_settings()
            self.schedule_layout(5)
