#!/bin/bash
# Idempotent bootstrap for a throwaway Haven-Duskholm test instance.
# Usage: bootstrap.sh [REPO_COPY_DIR] [PORT]   (defaults: ~/haven-test, 3500)
# Requires REPO_COPY_DIR/src/haven to be built already. Only touches REPO_COPY_DIR (+ ~/haven-run.log).
# Creates minimal runtime fixtures (the repo is source-only), then starts the server.
# Test account: Testacct / testpass1 (created in "trustee" state, first login sets the password).
set -u
R="${1:-$HOME/haven-test}"
PORT="${2:-3500}"
[ -x "$R/src/haven" ] || { echo "missing $R/src/haven (build first: cd $R/src && make -j16)"; exit 1; }
cd "$R" || exit 1

pkill -9 -f "haven $PORT" 2>/dev/null; sleep 1

mkdir -p log accounts/back{1..7} gods player/{back{1..7},remort,delete,drafts} \
         data/{back{1..7},archives,notes,plots,quotes,vmaps,chests,guild,vessel,port,country,corpses}

mk() { [ -e "$1" ] || printf '%s' "$2" > "$1"; }     # create only if missing

# --- loop-style data files: "#END" terminates an empty list -------------------
for f in operations cabals graves lairs roster storylines fantasies destiny gallery pages \
         playerrooms institute phonebook stories plots storyideas petitions news research \
         encounters patrols anniversaries decrees grouptexts texthistories matches profiles \
         chatrooms locations neighborhoods events weeklycharacters gateways houses domains \
         properties containers dorms rent rents container market; do
  mk data/$f.txt $'#END\n'
done
mk data/plots/txt $'#END\n'              # PLOT_FILE has a typo'd path in the _WIN32 branch
mk data/archives/archive.index $'#END\n'
# name lists are NOT '#'-prefixed: bare words terminated by END
mk data/mname.txt $'Adam\nEND\n'
mk data/fname.txt $'Eve\nEND\n'
# notes system: empty files are accepted
for f in groups noteboards notes; do mk data/notes/$f.dat ''; done
# AI csv queues (empty)
for f in ai_in ai_out ai_sum_in ai_sum_out; do mk data/$f.csv ''; done

# --- factions: update.c ai_log_job derefs clan_lookup(FACTION_SYNDICATE=5) every minute
if [ ! -e data/clans.txt ] || [ "$(head -c 4 data/clans.txt)" = "#END" ]; then
  { for p in "5 Syndicate" "6 Union" "7 Community"; do set -- $p
      printf '#FACTION\nName %s~\nVnum %s\nType 1\nEnd\n\n' "$2" "$1"; done
    echo '#END'; } > data/clans.txt
fi

# --- areas ---------------------------------------------------------------------
cd area
mk music.txt $'#\n'
# boot expects area vnums (= load order index) 22..25 to exist (offworld_weather_update derefs
# get_area_data(25)). Real areas dskhlm(0), abyss(1) + empty stubs 2..30 + limbo(31).
for i in $(seq 2 30); do
  n=$(printf 'stub%02d' $i); lo=$((900000+i*100)); hi=$((lo+99))
  [ "$i" = 2 ] && continue
  [ -e $n.are ] || printf '#AREADATA\nName %s~\nVNUMs %d %d\nCompleted 0\nWorld 0\nRange 0 0 0 0\nEnd\n\n#$\n' $n $lo $hi > $n.are
done
# stub02 carries the HELPS the login code needs (greeting/motd/introstory/infernohelp)
mk stub02.are '#AREADATA
Name stub02~
VNUMs 900200 900299
Completed 0
World 0
Range 0 0 0 0
End

#HELPS
Keyword greeting~
Level 0
Online 0
Type 0
Text Welcome to the local test instance.
What is your name? ~
End
Keyword motd~
Level 0
Online 0
Type 0
Text Test MOTD.
~
End
Keyword introstory~
Level 0
Online 0
Type 0
Text Test intro story.
~
End
Keyword infernohelp~
Level 0
Online 0
Type 0
Text Test help.
~
End
#0

#$
'
# rooms 1 (limbo), 3 (ROOM_VNUM_CREATION), 50 (school); 'Y ~' sets subarea (else atoi(NULL) crash)
if [ ! -e limbo.are ]; then
  { printf '#AREADATA\nName testlimbo~\nVNUMs 1 99\nCompleted 0\nWorld 0\nRange 0 0 0 0\nEnd\n\n#ROOMS\n'
    for v in 1 3 50; do printf '#%d\nTest Room %d~\nA bare test room.\n~\n0 0 0\nY ~\nS\n' $v $v; done
    printf '#0\n\n#$\n'; } > limbo.are
fi
# area list (rewritten every run; keeps the two real areas first so vnums stay stable)
{ echo dskhlm.are; echo abyss.are
  for i in $(seq 2 30); do printf 'stub%02d.are\n' $i; done
  echo limbo.are; echo '$'; } > area.lst
cd ..

# --- test account in "trustee" state (server then prompts for a new password) ---
printf 'Name Testacct~\nPassword trustee~\nEnd\n' > accounts/Testacct
rm -f accounts/back*/Testacct

# --- start (must run from area/, same as bin/startup) ---------------------------
cd area
nohup ../src/haven "$PORT" > "$HOME/haven-run.log" 2>&1 &
for i in $(seq 1 30); do
  grep -q "ready to rock" "$HOME/haven-run.log" 2>/dev/null && break
  sleep 1
done
if grep -q "ready to rock" "$HOME/haven-run.log" && pgrep -f "haven $PORT" >/dev/null; then
  echo "OK: listening on $PORT (pid $(pgrep -f "haven $PORT" | head -1)); log: $HOME/haven-run.log"
else
  echo "FAILED to boot; tail of log:"; tail -15 "$HOME/haven-run.log"; exit 1
fi
