# Sanctuary

A small, dependency-free telnet client for MUDs, built for Duskholm and other Haven-style games.
A handful of Python files (`sanctuary.py` is the program; the rest are its parts: `dosui.py`
DOS-look widgets, `prompts.py` prompt formats, `triggers.py` triggers and aliases, `layout.py` pane
geometry, `extras.py` timers/clock/notepad/hotkeys, `toolsui.py` colour tools and the customize
form, `colortools.py`, `custom.py`, `moon.py`, `emojis.py`, `boxes.py`, `worldfile.py`, `speech.py` and `access.py` for screen reader mode), tkinter
only (ships with the standard Windows Python installer; Pillow is used for JPEG/WebP pictures if
it happens to be installed).
Keep them together. Double-click `Sanctuary.pyw`, or run `pythonw sanctuary.py`, to start it
without a console window.

```
python sanctuary.py [host [port]] [--screen-reader]
```

Defaults to `duskholm.com:3001` (TLS). Port 3000 is plain telnet.

*Formerly "Duskholm client".* Your old settings (`~/.duskholm_client.json`) and skins
(`~/.duskholm_skins/`) are copied to the new names on first start; nothing is moved or deleted.

## What it handles

- **TLS or plain** connections, with a checkbox that swaps the stock ports.
- **Password prompts**: when the server sends `WILL ECHO`, input is masked and
  never echoed locally, saved to history, or written to the settings file. (The game
  forgets to send `WONT ECHO` after a brand-new account is created, so the mask is also
  lifted once a real game prompt appears; nothing less certain ever lifts it.)
- **MXP**: accepts the server's offer and renders `<color fore=#rrggbb>`,
  `</color>`, `<b>`, `<i>`, `<u>` and the `&lt; &gt; &amp;` entities. Other tags
  are ignored (their text still shows).
- **Colour**: ANSI 16-colour, xterm-256 (`38;5;N`) and truecolor.
- **Outgoing text is cleaned to what the game accepts.** The server keeps only printable
  ASCII from typed lines, so smart quotes, em-dashes, ellipses, accents and tabs would
  otherwise vanish silently. The client converts them (`don’t` → `don't`, `—` → `--`,
  `é` → `e`) and tells you if anything had to be dropped. Pastes are flattened to one line
  and never sent automatically.
- Connection safety: sends never block the window, cancelling aborts a stalled TLS
  handshake, and a late event from an old connection can't disconnect a new one.
- **Auto-reconnect** (Options menu, off by default). If the connection drops unexpectedly it
  retries every 30 seconds, showing a countdown, until it gets back in; you land on the
  game's login prompt (passwords are never stored). It does not retry after you disconnect
  yourself, after you send `quit` (the game closes the connection), when you press
  **Cancel retry**, or on a TLS certificate error, which retrying can't fix.
- **Stat bar** (View menu, on by default). Reads the game's default prompt, e.g.
  `[350/350DF 0ST 0WN 0LG M:0 K:0 ( )]`, and shows an HP bar (coloured in the game's own
  80/60/40/20% bands), the labelled counters exactly as the game names them, the `M`/`K`
  cooldowns (green when ready, red while cooling down), facing while fighting, and any
  status tags such as `(Sprawled)`. It appears after the first prompt and disappears on
  disconnect. The prompt line stays in the scrollback too. A prompt in a custom format that
  doesn't match is simply ignored.
- **Font** (View > Font…): pick any installed *monospace* family and a size (7–40) with a
  live preview; `Ctrl +/-` and `Ctrl+wheel` still zoom. The choice is saved. The input line
  and stat bar always stay on screen, even at large sizes.
- **Skins and a user-adjustable palette** (View > Skin, View > Colours…). Six built in:
  *Plain* (neutral dark, the default), *Plain Light*, *Moody* (violet-black, tarnished gold,
  spectral teal), *Retro Phosphor* (green-screen CRT), *Retro Amber* (amber CRT) and *Retro DOS*
  (16-colour VGA, blue panels, chunky buttons). `Ctrl+*` and `Ctrl+/` raise and lower the minimum
  text contrast by half a step. A skin sets every colour, the 16-colour game palette, button
  style and a preferred monospace font (used unless you've picked a font yourself).
  - **Edit anything live**: click any of the 16 game colours or 13 interface colours to
    change it; the whole window, the stat bar and the *existing scrollback* recolour at once.
    Edits are saved per skin; *Reset this skin* undoes them, *Cancel changes* restores how
    things were when you opened the dialog.
  - **Minimum text contrast** (1.0–7.0): any text colour too close to its background (dark
    blues, "black" on black, near-black 256-colour shades) is lifted until it's readable,
    keeping its hue. It applies to every colour the game can send, not just the 16. `1.0`
    shows colours exactly as sent.
  - **Your own skins**: *Save as new skin…* writes a small JSON file to
    `~/.sanctuary_skins/`; drop in files from others (or hand-write one) and they appear in the
    Skin menu. Bad or oversized files are ignored.
  - Windows draws the menu bar and scrollbar itself, so those keep the system look.
- **Menus.** Seven menus, grouped by what they are for: **File** (worlds, logging, import/export, quit), **Edit**
  (Find, Copy without my commands, Clear screen), **View** (skin, colours, font, DOS look, stat bar, panes
  and layout), **Automate** (triggers, aliases, buttons, timer, customize form), **Tools** (notepad, game time,
  moon, gradient maker, hex to xterm, emoji picker), **Options** (in groups: connection, display, sending,
  sound, logging and backscroll, screen reader) and **Help** (help, hotkeys, updates, about). The text in the
  drop-down and right-click menus is the same size as the main text (never below 10, never above 22) and
  follows Ctrl +/Ctrl -. The strip of menu names along the top is drawn by Windows and keeps Windows' size
  (it follows Windows' own text-size setting).
- **DOS terminal look** (`Alt+D`, or View > DOS terminal look; off by default), modelled on
  early-90s terminal software such as Telix and Terminate. The menu bar, toolbar and scrollbar
  go away; the game fills the window with a one-character coloured border on each side (the
  screen is as many columns wide as fit), and when there is something to scroll a text-mode
  scrollbar takes the place of the right-hand border (arrows scroll a line, clicking the track
  pages up or down, both repeat while held, and the thumb drags). The font
  is auto-sized so at least 80 columns and about 25 rows fit; turn that off with F7 > Auto-fit
  size to pick your own size, and the border stays one character either way. Underneath: an input line and a two-row status bar, with
  function-key hints on top and live status below (connection, online clock, HP as a block
  gauge, counters and cooldowns), budgeted to the screen width. Menus and dialogs are boxed
  with double lines and drop shadows, and work from the keyboard (arrows, Enter, Esc, hotkey
  letters). It keeps its own skin choice (default *Retro DOS*), so your normal skin is
  untouched.

  | Key | Action | Key | Action |
  | --- | --- | --- | --- |
  | `F1` | Help | `F2` | Connect / disconnect |
  | `F3` | Log to file | `F5` | Skins |
  | `F6` | Colours | `F7` | Font |
  | `F10` / `Alt+M` | Main menu | `Alt+X` | Exit (asks first) |
  | `F11` / `Alt+Enter` | Full screen | `Alt+D` | Back to the normal look |

  The Retro skins use a bitmap-style DOS font if one is installed (*Perfect DOS VGA 437*,
  *More Perfect DOS VGA*, *Nouveau IBM* or *Px437*), otherwise Lucida Console or Consolas.

  **Colours (`F6`) and Font (`F7`) are DOS-style too**: a menu tree for the skin, the 16 game
  colours (listed with colour swatches), the interface colours, the DOS screen colours and
  the minimum contrast, with a classic red/green/blue mixer and New/Old preview for editing
  a colour. Changes apply live to the whole screen; `Enter` keeps a colour, `Esc` puts the
  old one back and steps back one menu level. *Revert changes* undoes everything since you
  opened the screen, and *Save as new skin* writes a skin file. The font list is a scrolling
  menu with your current font pre-selected. Each look remembers its own font family, size and line
  spacing: changing the font in one never touches the other (an older settings file gives the DOS look
  a copy of your font the first time).
- **Full screen** (`F11` or `Alt+Enter`, both looks): real full screen, hiding the title bar,
  borders and taskbar. Saved between runs.
- **Tabs line up like MUSHclient.** The game lays out tables (such as the unread-notes screen)
  with TAB characters, so the client expands each tab to the next multiple of 8 columns itself
  instead of relying on the text widget's own tab stops. Bold and italic text also keep the same
  character width as normal text, so bitmap-style fonts stay on the grid.
- **Worlds / dialing directory** (`Ctrl+W`, or `/worlds`): saved addresses with name, host,
  port, TLS and a note, plus the date of your last call. In the DOS look it is a Telix-style
  directory (`Enter` dial, `A` add, `E` edit, `Del` remove, `Esc` close); in the normal look it is
  an ordinary list window. *Duskholm* is saved by default.
- **Several worlds at once.** Dialing a saved world while this one is connected opens it in its own
  tab (up to 12); dialing one that is already open switches to it. `Ctrl+F1` .. `Ctrl+F12` show
  the 1st .. 12th world, `Ctrl+PageDown` / `Ctrl+PageUp` the next and previous one, `/world [n|name]`,
  `/newworld [name]` and `/closeworld` do the same by command (all of these keys can be changed under
  `/hotkeys`: one row sets the prefix for all twelve, e.g. `Ctrl-Alt-F`; world 1-12 can also be set
  one by one in the settings file). **Close this world** (main menu, or `Ctrl+Shift+W`) hangs up, after asking, and closes the tab. In the normal look the worlds are a row of **clickable tabs**, centred under the toolbar (click one to
  switch, right-click for Close, `+` opens the Worlds list; the shown tab is highlighted, and a world with new
  text while hidden gets a yellow dot and one beep). Options > World tabs: always (the default, so you can see
  there is room for more), only with two or more worlds, or off (the old label in the toolbar). In the DOS look
  the worlds are key hints in the top row, `[bracketed]` when on screen and `*` when there is news, and **every key
  hint in that row can be clicked** (`^F2` switches to world 2, `F1` opens help, and so on). Each world has its
  own scrollback, connection, command history and half-typed line; the stat bar, status line and
  screen reader follow only the world you are looking at.
  Pane areas are kept per world and saved as you change them. Triggers and aliases have a
  **Global (all worlds)** setting, on by default; turn it off and the rule works only in the world
  it was made in. Existing rules are all global, and are stored exactly as before.
- **Dial by hand.** While not connected, type `ATDT <host> <port>` (also `ATD`, `ATDP`, `ATT`,
  `host:port`, a saved world's name, and an optional `tls`/`plain`) and the client answers like a
  modem: `DIALING ...`, `CONNECT` or `NO CARRIER`. Typing `telnet` gives a small pretend telnet
  command line (`open host port`, `status`, `?`, `quit`), or `telnet host port` connects
  directly. Both only act while offline; once connected, everything you type goes to the game.
  Port 3001 means TLS, anything else plain unless you say `tls`.
- **Prompt bar formats.** The stat bar / DOS status row reads your game's prompt. The default is
  the Haven/Duskholm style (`[350/350DF 0ST 0WN 0LG M:0 K:0 ( )]`). Presets for stock ROM/Diku
  prompts and a simple `[HP: x/y MP: x/y]` style are built in, and you can design your own
  (View/F10 menu > Prompt bar format, or `/prompt`): a regular-expression pattern with named
  groups, plus which groups are gauges, counters, cooldowns or text, with a live test line.
  Patterns are checked for safety (no catastrophic backtracking, backreferences or lookbehind).
- **Line spacing**: extra pixels between lines, 0-12 (Font dialog, or F7 in the DOS look), kept
  separately for each look.
- **Triggers** (`Ctrl+T`, or `/triggers`). A trigger watches the lines the game sends and does
  something when one matches: *highlight* the match or the whole line, *hide* the line from the
  screen (it stays in your log), *send* a command, *beep*, or print a client *note*. Patterns are
  either **plain** (`*` is a wildcard that you can reuse as `%1`, `%2`; `^` and `$` anchor to the
  start or end of the line; matching is anywhere in the line and ignores case) or **regular
  expressions** (a toggle in the editor), where `%0` is the whole match, `%1`-`%9` the groups and
  `%{name}` a named group. A trigger can have a priority (higher runs first) and can stop the
  ones after it. The editor has a live test line. Ready-made presets match Duskholm's real wording:
  `[OOC] Name: 'text'` and friends (Guide, Newbie, Legends), and `Name tells you 'text'` /
  `... tells you OOCly 'text'`. Safety: regexes are checked against catastrophic backtracking,
  commands a trigger sends are split on `;` *before* captures are filled in (so text from other
  players can never add commands), and a rate limit stops a runaway loop.
  Plain patterns stop a `*` at the first possible end, so end a pattern with `$` to take the
  whole rest of a line (`* tells you *$`).
- **Aliases** (`Alt+A`, or `/alias name body`, `/unalias`, `/aliases`). An alias is a first word
  that expands to commands: `;` separates them and `%1`-`%9` / `%*` are your arguments. With no `%`
  in the body, what you type after the alias is added to the last command. Old aliases written
  with `$*` are converted to `%*` automatically. An alias name can be up to **three words**
  (`text ann` as well as `text`): the longest name that matches the start of what you typed wins, whole
  words only, so `text ann hello` can send to someone's long name while `text bob hi` still uses a plain
  `text` alias. In `/alias` a name of two or three words goes in quotes: `/alias "text ann" text annabelle %*`.
- **Buttons** (`Alt+B`, Automate > Buttons..., or `/button`). A bar of clickable buttons, each sending its commands (the same
  `;` form an alias uses, run exactly as if you had typed them, so aliases and `/commands` work; they are not added to
  your command history). A button can have a **hotkey** (`Alt-F5`, `Ctrl-Alt-S`, `Shift-F9` ...; one that is already a
  built-in key or another button's is refused with the reason) and belongs to every world or to just one: the bar shows,
  and the hotkeys work, only for the buttons of the world on screen. Dock it at the **top** (under the world tabs, the
  default) or the **bottom** (above the entry box) in Options > Button bar, or turn the bar off; it wraps onto more rows
  when the window is narrow, and shows only when the world has buttons. In the DOS look the buttons are text-mode labels.
  `/button add Sneak = sneak;hide`, `/button key Sneak Alt-F5` (or `none`), `/button run|del|on|off Sneak`,
  `/button list`, `/button dock top|bottom|off`. The list window adds, edits, switches on and off, removes and reorders.
- **World names.** A world you did not dial from the Worlds list (the Connect button, or the address it started with) is
  named after the saved world with the same address, so the tabs say `Duskholm` rather than `World 1`, including when a
  second world is opened. Rules, buttons and clock settings that were set for "only this world" under the placeholder name
  move to the real name. A world with no matching saved world stays `World 1`, and a name you chose is never changed.
- **Rename a world freely.** Every saved world has a permanent id (kept in the settings; you never see it). Triggers,
  aliases and buttons set for "only this world", the world's pane layout and its game-clock settings are tied to that id,
  not to the name, so renaming the world in the Worlds list (Edit) keeps all of them, renames its open tab, and updates the
  name shown in the lists. Rules saved before this existed are tied to the matching saved world automatically the first
  time the new version starts. A world that is not in the Worlds list has no id and goes by its name, as before. World
  files (`.snc`) carry names only, never ids, so importing one never collides with your own.
- **The AFK prompt.** The game's `[AFK] ` prompt has no line break after it, so it used to stick to the line before it and,
  when you pressed Enter, to the game's reply, which made triggers and capture panes see (and copy) lines like
  `Evelyn tells you ... [AFK] You tell Evelyn ...` as one. Pressing Enter at the prompt now ends that row, and the prompt
  is left out of what triggers and panes see (the screen still shows it as the game sent it). Only `[AFK] ` with a space
  after it counts, so an `[AFK]` mark in a list is untouched.
- **Lines the game leaves unfinished.** Some of the game's messages, a tell you receive among them, arrive with no line
  break at the end. The text is shown straight away, but a trigger or capture pane only sees a finished line, so it used
  to wait for the next thing the game sent or for you to press Enter. Now an unfinished line that is text (not a prompt)
  and has been quiet for about 0.4 seconds is treated as a whole line (the screen does not change, and your next command
  still goes on its own row). Prompts are left alone: a line ending in a space (`Password: `, `> `, `[AFK] `) or
  matching your prompt format waits for what you type, as before. If a long line stalls half way, it is one row on screen
  but captured in two pieces.
- **Clone** (the *Clone* button, or `Ctrl+D` in the list, or `C` in the DOS look) in the Worlds, Triggers, Aliases and
  Buttons lists copies the selected entry right underneath it under a new name (`Name copy`, `Name copy 2` ...; an alias
  becomes `name2`, so it stays one word you can type). Then edit the copy. A cloned **trigger starts switched off**, so the
  two do not both fire until you have changed it; a cloned **button has no hotkey** (two buttons cannot share one); a cloned
  **world** has the same address and note but no "last call" (its triggers, aliases and buttons are separate: a rule that
  belongs to one world stays with that world).
- **Find** (`Ctrl+F`, or `/find [words]`). A small Find box looks through the main text of the world on screen (plain
  words, ignoring case unless *Match case* is ticked; the selected text is filled in for you). *Enter* finds the next match and `Ctrl+Shift+F` (or
  `/findnext`) does the same with the box closed. **Start from the bottom** (the default) begins at the newest line and
  works up, so the first match is the latest and each next one is older; **from the top** begins at the oldest line and
  works down. Both choices are remembered. Past the last match it says so and starts again from the far end. The match is
  shown in reverse colours and scrolled into view; the status line says what happened. In the DOS look the box is a
  dialog with a *Start from the top* tick. Both keys can be changed in the Hotkeys form.
- **Copy without my commands.** Right-click in the main text > *Copy without my commands*, or select and type
  `/copyplain`: the selection goes to the clipboard with the lines you typed (the commands the client echoed) left out.
  Ordinary `Ctrl+C` is unchanged and copies everything.
- **Logging** (`/log`, F3): Options > *Put the commands I send in the log file* (on by default) can be switched off to keep
  what you typed out of the log; the game's text and the client's notes are still logged.
- **Scrollback length and reloading it** (Options). *Scrollback length* is how many lines of text each world keeps in the
  window before the oldest go: 5,000, 10,000, 20,000 (the default), 50,000 or 100,000. *Reload earlier backscroll at
  start* (off by default) saves the end of each world's text when you quit (and every five minutes, and when you close a
  world) and puts it back above the new text the next time you connect to that address (at start-up for the world on
  screen), with a line saying where the old text ends. *Backscroll to reload* is how many lines are saved and put back:
  500 to 20,000, and never more than the scrollback length (lowering the length lowers it too). **The more lines you
  reload, the longer start-up takes**, which is why this is a choice and why turning it on asks first. It is plain text,
  without colours or highlights, kept in a `backscroll` folder next to the settings (so anyone who can open that folder
  can read it); switching the option off deletes it. Capture panes are not saved.
- **No gap where a message was hidden.** When a trigger hides a message and the screen already ends in a blank line, the
  blank line the game puts after the message is dropped with it (one blank line only), so hiding something does not
  leave a hole.
- **Capture panes** (`Ctrl+P`, View > Panes / layout). Lines can be copied into small in-client
  panes (OOC, Tells, Guide ...) docked to the top, bottom, left or right of the main text. In the
  DOS look they are plain regions of the screen with a tab row, not windows. A trigger's *Send to
  pane* field names the pane (it is created on first use); the line **stays in the main window**
  unless the rule's *hide from the main window* box is ticked. Presets: Long strip on top / on the
  bottom, Right column (one or two stacked), Left column, Top strip + right column, or define up to
  three areas yourself as `side size panes` (e.g. `right 40 OOC, Tells`) with a live preview. The
  main text always keeps at least 80 columns: areas that would squeeze it are narrowed, then hidden.
  Several panes in one area become tabs (`Ctrl+1`..`9` select, `*3` shows unread lines). Ready-made
  trigger presets capture OOC, tells and Guide/Newbie, and **phone texts**: *Capture phone texts (no repeats)* sends
  every date-stamped message line (`[Jun  9 12:34]Name: ...`) to a Phone pane, whether it pops up the moment it
  arrives (while you hold the phone) or is listed when you look at the phone, and
  only the ones that pane does not already have, however often you look: a text the game wrapped onto a second line
  comes along with it, two word-for-word identical texts in the same minute are both kept (and not doubled on the
  next look), and clearing the pane makes the next look fill it again. It is a route action with the box *Skip lines it
  already has* (`once`), so any log the game repeats can be captured the same way.
  **Your own side:** the game answers a text you send with just "Sent.", so *Capture my texts to a pane* matches the
  command as you type it (a trigger with *Matches the commands I send, not what the game shows*: it sees what actually
  goes out, so an alias, a button or a pop-out window's input bar counts too, and never a password) and puts
  `[Nov 24 18:33]You > Mara: yes, after eight` in the Phone pane, stamped the way the game stamps. Such a rule's
  *Pane line* box sets what the pane gets (`%1`-`%9`, `{time}`, `{name}`). Every pane has a **Show what I send**
  switch (the pop-out window's *Show mine* box, the right-click menu on its tab, or `/panesent <pane> [on|off]`, remembered
  per pane and world): rules marked *My own side* only run while it is on, which includes *Capture your own tells to a
  pane*, so tells, texts and the rest all turn on and off the same way, and what others send you is never affected. `text history`
  prints both sides with the game's own names, so those lines can repeat what was shown for what you sent.
  Each pane area has a small fold button (`-`); `Alt+1`..`9` fold away or bring back the area
  holding that pane and `Alt+0` all of them. Folded panes keep collecting; the bar says
  `Unread: OOC*3`. In the DOS look everything sits in one double-line frame whose joins match.
  **Pop a pane out** into a window of its own (a second monitor, say): the `\u2197` arrow at the right of an
  area's header pops out its active tab, or `/popout <pane>`; the window's Dock button, closing it, or
  `/dock <pane>` brings it back. The window shows the pane's history and then every new line, with its colours,
  links, colour emoji, time stamps and follow-the-newest-line, and a selection in it copies with Ctrl+C. The pane's
  tab leaves the main window while it is out, and an area whose panes are all out goes away (the main text gets the
  room). A pane belongs to a world and keeps updating while that world is not on screen; closing the world closes its
  windows. Where the window was, and whether it was out, is remembered per world and comes back next time.
  **Input bar:** the "Input" box in the window (or `/popinput <pane> [on|off]`) gives it an input bar of its own, so a pane
  pinned to a second monitor can be answered from there: what you type is sent to that window's world as if typed in the
  main window (aliases, `/commands` and the history all work; a line starting with `/` stays local), and the "Send:" box
  beside it is put in front of every line (`text Mara`, for a Phone window; `/popinput <pane> prefix <text>` sets it
  too). Up and Down recall what you typed there, a password prompt in its world shows as dots and is never kept, and the
  bar and its prefix are remembered with the pane.
  **Tear-off:** while the pane sizes are unlocked (`/panelock off`), drag a pane's tab out of its area and let go
  anywhere outside the header: it becomes a window right there (the pointer changes while you are far enough out;
  letting go over the header is just a click, and while locked the status line says how to unlock). **On top:** the
  "On top" box in the window, or `/ontop <pane> [on|off]`, keeps it above other windows; it is remembered with the
  pane.
  **Resize with the mouse:** unlock with View > Lock pane sizes (or `/panelock off`), then drag the
  border between the main text and an area, or the divider between two areas stacked on one side (in
  the DOS look these are the frame lines, a whole cell thick, and the scrollbars step aside while it is
  unlocked). It is locked by default, so nothing moves by accident.
- **Combat readout.** Stun, wounds, the other counters and the move/attack timers sit together
  beside HP. Stun changes colour as it climbs (50 warm, 75 bad). `M:` and `K:` count down on their
  own once a second, as the game does, instead of waiting for the next prompt. The lines the game
  prints when your defence is back to full (`Your shield pulses briefly...`, `You recover your
  defenses.` and the rest) fill the DF gauge at once.
- **Status line message.** A trigger can show a short message on the status line (*Status line*
  field). Separately, setting any walk (credit, ego form, changeling form, true form, ...) shows
  `Walk: <your name> <walk> in from the right.` on the status line (worded like the game's `display` command) (next to TLS in the DOS bar),
  so you can see how it will read. Options > Walk preview turns that off.
- **Links.** `http(s)` links in the output (and in panes) are underlined and clickable, in both
  looks. Pictures (`.png .jpg .gif .webp .bmp`) open in a pane at the right, scaled
  to fit, while you keep typing. *Enlarge* makes it cover the main area (*Shrink* puts it back), *Close*
  dismisses it, *Open original* opens it in your browser. After clicking the picture, `E` enlarges,
  `Esc` closes and `O` opens the original; every
  other link opens in your browser. Both are options (Options menu).
- **Emoji** (option, off by default). `:smile:` in incoming text is shown as the emoji and any
  emoji you type is sent as `:smile:`, since the game only takes plain ASCII. About 100 familiar
  shortcodes plus every emoji's official name (`:rolling_on_the_floor_laughing:`). Windows' own emoji
  panel (`Win+.`) cannot put its choice into a Tk entry box, so Sanctuary has its own picker: `Alt+E`
  (or `/emoji heart`, or Tools > Emoji picker) searches by part of a name and adds the emoji to what you
  are typing. Emoji you paste are kept in the box too.
  **Colour emoji** (on by default in the ordinary look; Options > Colour emoji): Tk draws text in single
  colours, so an emoji would come out flat. Each one is instead drawn as a small colour picture in
  Windows' own emoji look (rendered from the Segoe UI Emoji font by Pillow), one line high, placed in
  the text and the panes. The emoji character stays in the text, hidden, so copying, searching and logs
  still see it. The DOS look keeps plain glyphs unless you turn on Options > "Colour emoji in the DOS
  look" (off by default). Flags and joined emoji (family, couples) stay plain; without Pillow or the
  font nothing changes.
- **Join ASCII boxes** (option, off by default). The game's `| - _ . , '` boxes are redrawn with
  solid line characters (`┌─┐`), without changing any column, so the colours stay put.
- **Timer** (`Alt+T`, `/timer 10m label`, `/timer 21:30`, `/timer game 21:30`, `/timer list`,
  `/timer cancel [n]`). Counts down, or waits for a time on your clock or the game's.
- **Clock** (Options > Clock): your local time, or the game's own clock.
- **Time stamps** (optional, off by default). Options > Time stamps puts a dim `[HH:MM]` (or
  `[HH:MM:SS]`) on each line the game sends, in the main text. Each capture pane has its own switch:
  put `(time)` after its name in Panes / layout (`right 40 OOC (time), Tells`) or use
  `/stamps <pane> on|off` (`/stamps` shows where they are on; `/stamps main hh:mm|hh:mm:ss|off`). A
  pane that stamps uses the main text's format, or HH:MM when that is off. Stamps are your own clock,
  never reach triggers, logs or the screen reader, and are not put on prompts, blank lines, your own
  commands or the client's messages.
- **Right-click menu**: in the entry box, Cut / Copy / Paste / Select all / Clear; in the text and the
  panes, Copy / Select all, and Open link / Copy link on a link. In the DOS look the same choices come
  up as a DOS menu. Ctrl+X, Ctrl+C and Ctrl+V work as always; a multi-line paste is flattened to one
  line and never sent by itself.
- **Game time, per world** (Tools > Game time, `/gametime`). Every world has its own game clock, set
  to Duskholm's by default: US Eastern (EST/EDT) running 1:1 with real time. A world can use a fixed
  offset (`/gametime zone -5`, `+5:30`, `utc`), take its offset from the game's `time` command
  (`/gametime zone learn`), or run at another speed: `/gametime ratio 3:1` is three in-character
  hours per real hour, `1:24` is one game hour per real day (`/gametime set 14:30` says what its clock
  reads now, and the game's own `time` output re-sets it). The clock and `/timer game 21:30` follow
  the world on screen; `/gametime reset` goes back to Duskholm's. The client also learns your
  character's name from the game's `display` output, only ever from what the game prints, never from
  what you type.
- **Notepad** (`Alt+N`): a scratch page saved in `~/.sanctuary_notes.txt` as you type.
- **Moon** (`Alt+M`, `/moon`): the phase, how much is lit, and the next full and new moon, worked
  out the way the game does it (so they agree); a picture in the DOS look.
- **Gradient maker** (`Alt+G`, `/gradient text`): choose a pattern of xterm colours, choose how it
  is applied (stretch, cycle, middle-out, edges-in, bounce, random, per word, per line) and see it;
  send it to the input line or the clipboard. In the DOS look, Enter on *Pattern* or *Apply* opens
  the list (the patterns have colour swatches, and *Create new...* and *Import a shared one...* are
  in it). Patterns can be shared as one line of text, `sgrad1:Fire:196,202,208,214,220,226`
  (*Share* copies it, `/gradient share [name]`, `/gradient import <line>`).
  The colours are a row of swatches you can see and click: click one to select it, click it again
  (or press `Enter`) to change it, `[+]` / `[-]` (or `Ins` / `Del`) add and remove colours,
  `Ctrl`+arrows move one, and a live bar shows how they blend. Changing a colour opens a picker:
  in the normal look a saturation square, a hue slider, a hex box and the 256 colours grouped by
  hue; in the DOS look the colours grouped by hue plus a hex box (everything snaps to the nearest
  xterm colour, which is what the game can show). Both work with the mouse or the keyboard alone.
  *Reverse* turns the colours round and *Save* keeps them as a named pattern.
- **Hex to xterm** (`Alt+H`, `/hex ff8800`): the closest xterm colour and its code (`` `208 ``).
- **Customize form** (`Alt+K`, or just type `customize`): fill in an item's fields and send them
  all at once. Two ways to send: as `customize <item> ...` command lines for an item you have, or
  *into the game's own item editor* (the one a new shop item is made in, which has no command
  line): the client types the editor's commands for you, gathers its long replies instead of
  scrolling them, shows you only the finished item (plus any errors or chat that came in), and
  asks you to say Done. Where the answers are known you pick them: Enter on a line opens the list
  (item kind, size, layer, the body parts a garment covers or zips) and Enter on a description,
  taste or playlist opens a text page like the game's own editor (`Ctrl-S` keeps it, `Esc` cancels).
  On that page `Ctrl-G` colours the highlighted text (or all of it if nothing is highlighted) with a
  gradient, so several gradients in one text are just: highlight a part, `Ctrl-G`, highlight another, repeat. It is picked from the
  same list, and `Ctrl-K` takes the colours off; the codes are dimmed and the text shows in
  its colour as you write. The form is one page when the screen has room for every line, two
  (Next / Back) only when it must.
  Save what you made in the **design book**, sorted by type, and load it later. (`customize <item>
  ...` with arguments typed in the game still goes straight to the game.)
- **Screen reader mode** (Options > Screen reader mode, `/sr on`, or start with `--screen-reader`).
  The client keeps to its plain window (the DOS look is switched off) and *speaks*: new game lines
  (never the prompt, never line-drawing or art), client messages, pane lines with the pane's name
  (`OOC: ...`), links as "link example.com", emoji by name. It announces stun at 50/75/100, health
  falling below 50/25/10 percent, and when the move or attack timer is ready. It talks through NVDA
  when NVDA is running (it uses NVDA's controller library, found in NVDA's folder), through JAWS
  when you choose it (`/sr voice jaws`; it uses JAWS's COM interface through PowerShell, so nothing
  needs installing, or through `pywin32` if that happens to be installed), or otherwise through the Windows voice, which
  needs nothing installed. Speech runs on its own thread, so it can never freeze the window; a flood
  of lines is cut short with "N lines skipped".
  Keys (all changeable under `/hotkeys`): `Alt+Up` / `Alt+Down` step back and forward through recent
  lines, `Alt+R` repeat the last line, `Alt+S` read your stats, `Alt+P` read recent pane lines,
  `Alt+C` read the time and the moon, `Alt+Q` stop speaking, `Alt+Z` mute. `/sr help` says it all
  again. Triggers gain two actions, **Speak** (say a message, optionally interrupting) and **Don't
  read this line aloud**. `/sr voice auto|nvda|jaws|windows|off`, `/sr rate -10..10` (Windows voice),
  `/sr alerts on|off`, `/sr test`. **Combat lines** (`/sr combat`, or Options > Screen reader:
  combat lines): while a fight is on, lines that are not about you can be left unread (they stay on
  screen and in the review keys): other players hitting NPCs, NPCs fighting each other, NPCs
  hitting other players, players fighting players. Lines that say you/your or use your name are
  never skipped. The game does not say who is a player, so it is a guess (one capitalised word is a
  player, `the goblin` / `a tall man` and names of several words are NPCs) that you can correct with
  lists of players, NPCs and words that must always be read. Defence is read as "def". `/sr interval 30` (or Options >
  Screen reader: read def and stun) reads your def and stun aloud every 30 seconds while connected;
  `/sr interval off` stops it.
  This mode has only been exercised with a fake voice so far; feedback from people who use a
  screen reader every day is very welcome.
- **World settings files** (File > Export / Import world settings, `/export`, `/import`): one
  `.snc` file holds a world and, optionally, its triggers, aliases, pane layout, prompt formats,
  gradients and designs. Importing is careful: triggers that send commands and all aliases arrive
  switched off for you to check; nothing is overwritten.
- **Import from another client** (File > Import from another client..., or `/import file`). Reads a
  **MUSHclient** world (`.MCL`), plugin or trigger file and brings across its triggers and aliases. First it
  tells you in the output window what is in the file: what can be imported, what cannot and why, and what
  comes across approximately; then it asks which world the rules belong to (the file's own world by
  default; empty means every world), whether to save the file's world too, and whether you trust the file.
  Nothing in it is ever run (a file that declares XML entities is refused). Without trust, triggers that
  send commands and all aliases arrive switched off; colouring and hiding rules are on. What maps:
  wildcard and regular-expression patterns (MUSHclient's wildcards match the whole line, as they do here),
  case, priority (`sequence`) and "keep evaluating", the colour change (custom colours 1-16 from the file's
  own palette, or its "other" colour and background), bold, omit from output, "repeat" (colour every match on
  the line: a regular-expression trigger can now do that, "Every match" in the trigger editor), sounds (as a
  beep), and `send` text to the world, output (a note) or the status line, with `%1`-`%9`, `%<name>` and
  several lines turned into `;` commands. Aliases of one word, optionally followed by anything (`emit *`), come
  across; MUSHclient's `%0` (everything you typed, the word too) becomes `word %*`, and the report says so. What
  does not: scripts (Lua, VBScript) and `send to script`, notepad and variable targets, multi-line matching (one
  line at a time here), italic and underline, timers (use `/timer`), macros and keypad keys, and plugin files
  that a world file merely names (import each plugin file on its own). The limits are now 1500 triggers and
  300 aliases. **Mudlet** packages (`.xml`, or an `.mpackage` zip holding one) read the same way: substring,
  start-of-line, exact-line and regular-expression patterns (several patterns on one trigger become one rule
  each; Mudlet is case-sensitive, so they are too), the colour of a highlight trigger, the command box (`;;` and
  new lines become `;`), sounds (as a beep), folders (a switched-off folder switches off what is in it), and
  aliases of up to three words, optionally followed by one capture (`^mn (.+)`, `^text ann (.+)`). The only Lua read is a script made
  of `send("text" .. matches[2])` lines, which becomes the same commands with `%*`/`%1` (triggers: `%1`...);
  any other script is not run and the report says so. Not read: multi-line triggers, Lua-function, line-spacer,
  colour and prompt patterns, timers, keys, scripts and buttons. More clients (TinTin++) are planned.
- **Hotkeys** (`/hotkeys`, Help menu): the Ctrl/Alt command keys can be changed (including the world keys
  and `Ctrl+A`, below); F-keys are fixed.
- **An entry box that grows as you type** (Options > Entry box grows to (lines): off, 2, 3, 5 or 8; off by
  default). The line wraps at the window edge and the box gets taller with it, up to the limit you chose, and goes
  back down when you send. **Shift+Enter** or **Ctrl+Enter** puts a line break in the box; Enter sends. A box with
  line breaks sends each line as its own command, in order (empty lines are skipped), and pasted text keeps its
  lines (up to 30). Up and Down walk your command history from the first / last line and move the cursor in
  between. While the game has echo off (a password) the ordinary one-line entry takes over, masked, so nothing
  you type there is ever shown or wrapped, and your text moves back when it is over.
- **Ctrl+A selects the whole entry line**, as in MUSHclient (rebindable like the rest; Aliases moved to
  `Alt+A`). **Copy and paste**: drag over text in the output or a pane, press `Ctrl+C` (`Ctrl+Insert`),
  and `Ctrl+V` (`Shift+Insert`) pastes it into the entry box from wherever the keyboard is, even though a
  click in a pane hands the keyboard back to the entry box. A multi-line paste is flattened to one line.
  In the DOS look `Alt+Left` goes back (out of a menu, or to the previous page of a form) and
  `Alt+Right` goes forward (into an entry that opens a list, or to the next page).
- **Other options:** bell on new output (always / window not in front / scrolled up), jump to the
  bottom when you send, show or hide your own commands. Your typed-command colour is also under
  *DOS screen colours*.
- **Whole lines.** To act on lines before they are drawn, the client now collects each line first.
  An unfinished line (a prompt) still appears after about a tenth of a second, and the stat bar
  sees it immediately. *Options > Hide the prompt line* keeps the prompt off the screen (the bar
  still shows it).
- Command history, aliases, session logging, font zoom (Ctrl +/- or
  Ctrl+wheel), 20,000-line scrollback, keep-alive, optional bell.

Settings live in `~/.sanctuary.json`.

## Updating, and making a release

**Updating.** `/update` (or Help > Check for updates) asks GitHub whether a newer release exists.
It never runs by itself unless you switch on *Options > Check for updates when Sanctuary starts*,
and it sends nothing about you. If there is one you see what is new and choose *Install update*,
*Skip this version* or *Later*. The download is checked against the SHA-256 published with the
release and only then offered; Sanctuary closes, swaps itself and starts again (the old program is
kept as `Sanctuary.old.exe` next to it). Running from the Python source, it only tells you where to
download, since you update with `git pull`. A checksum shows the download is what was published; it
does not prove who published it. Windows may also show a SmartScreen warning for an unsigned program.

**Making a release** (for the maintainer):

```
# 1. bump version.py (e.g. 1.0.1), commit, push
# 2. python make_exe.py          -> dist/Sanctuary-1.0.1-win64.zip and .zip.sha256
# 3. tag the commit v1.0.1 and publish a GitHub release for the tag with both files attached
#    and the changes in its description (that text is what the update window shows)
```

## Local commands

Local commands start with `/` (the game has none). `//text` sends `/text`.

| Command | Does |
| --- | --- |
| `/connect [host [port]]`, `/disconnect`, `/reconnect`, `/quit` | connection control |
| `/alias name a;b %*` | define an alias (`/alias "two words" ...` for a longer name); `;` separates commands, `$*` is the arguments (otherwise they are appended to the last command) |
| `/unalias name`, `/aliases` | remove / list aliases |
| `/log [file]` | start or stop logging |
| `/copyplain` | copy the selected text without the commands you sent |
| `/timer 10m [label]`, `/timer list`, `/timer cancel [n]` | timers (also `21:30`, `game 21:30`) |
| `/moon`, `/notes`, `/hotkeys` | the moon window, notepad, hotkey editor |
| `/hex ff8800`, `/gradient text`, `/customize` | colour tools and the customize form |
| `/export [file]`, `/import file` | world settings files (`.snc`); `/import` also reads MUSHclient and Mudlet files |
| `/clear`, `/help` | |

## License

GPL-3.0, see [LICENSE](LICENSE).

## Tests

```
python tests/test_client.py       # parser assertions, then the GUI against a fake server
python tests/test_hardening.py    # outgoing cleanup, passwords, cancel, stale events, settings
python tests/test_fuzz.py         # 41 adversarial parser checks (~10 s)
python tests/test_reconnect.py    # auto-reconnect against a fake server that goes up and down
python tests/test_statbar_fonts.py # prompt parsing, stat bar, font choice, layout at big sizes
python tests/test_skins.py        # skins, palette edits, contrast, persistence, the colour dialog
python tests/test_theme_pure.py   # adversarial checks on the colour maths and skin-file loading
python tests/test_dosui.py        # the DOS-style menus, dialogs and status bar widgets
python tests/test_dos_mode.py     # the DOS look wired into the client: keys, menus, status, full screen
python tests/test_dos_dialogs.py  # the DOS-style Colours and Font screens, end to end
python tests/test_layout.py       # tab alignment, bold width, one-cell DOS border, DOS scrollbar
python tests/test_polish.py       # skin switch re-fit, readable DOS colours, scrollbar in the border
python tests/test_prompts.py      # the prompt-format engine (parsing, validation, safety)
python tests/test_features.py     # ATDT, fake telnet, worlds, prompt editors, line spacing
python tests/test_rename.py       # the name, settings migration from the old name, the launcher
python tests/test_triggers.py     # the trigger/alias engine (matching, safety, expansion)
python tests/test_rules.py        # triggers, aliases and whole-line output, end to end
python tests/test_layout_engine.py  # pane geometry (pure)
python tests/test_panes.py        # capture panes, routing, manager, both looks
python tests/test_panesize.py    # dragging pane borders and dividers, the lock, both looks
python tests/test_gametime.py    # each world's game clock: zone, IC:OOC ratio, timers
python tests/test_emojipick.py   # the emoji picker
python tests/test_emojiimg.py    # colour emoji pictures, the two options, resizing
python tests/test_lookfonts.py   # each look keeps its own font, size and line spacing
python tests/test_panefollow.py  # capture areas keep the newest line in view, and where you scrolled them
python tests/test_popout.py      # a pane in its own window: lines, docking, position, worlds, looks
python tests/test_stamps.py      # optional time stamps, main text and per pane
python tests/test_editmenu.py    # right-click Cut / Copy / Paste, both looks
python tests/test_entryfit.py    # the entry box never clips the last character of a full line
python tests/test_clipboard_keys.py  # Ctrl+C/V on dragged text, Ctrl+A on the entry line, world keys
python tests/test_combat.py       # stun colours, grouped readout, self-ticking timers
python tests/test_status.py       # status-line action, credit-walk preview
python tests/test_links.py        # links, image panes, bell/scroll/echo options
python tests/test_emoji.py        # :name: both ways
python tests/test_boxes.py        # joining ASCII boxes (fuzzed)
python tests/test_moon.py         # moon phases against published times, Eastern time
python tests/test_extras.py       # timers, clock, notepad, moon window, hotkeys
python tests/test_colortools.py   # hex to xterm, gradients (fuzzed)
python tests/test_custom.py       # the customize form's commands and the design book
python tests/test_tools.py        # those tools in both looks
python tests/test_worldfile.py    # .snc export/import, including hostile files
python tests/test_importers.py   # MUSHclient file import (pure): patterns, colours, sends, aliases, refusals
python tests/test_sent_capture.py # my own side of a conversation: rules on what I send, the per-pane switch
python tests/test_popinput.py     # a pop-out window's own input bar: prefix, history, worlds, passwords
python tests/test_capture_once.py # route-once capture: the phone preset, wrapped texts, identical texts, no doubles
python tests/test_worldids.py     # world ids: rules, buttons, layouts and clock follow a renamed world; old settings migrate
python tests/test_idle_line.py    # a line with no line break is captured after a short quiet, prompts are not
python tests/test_afk_prompt.py   # the AFK prompt: no gluing, clean captured lines, screen unchanged
python tests/test_worldname.py    # a world nobody named takes its saved world's name; rules scoped to 'World 1' follow
python tests/test_find.py         # Ctrl+F / Ctrl+Shift+F: from the bottom or top, wrapping, the box, /find, worlds, DOS look
python tests/test_backscroll.py   # scrollback length, kept <= length, warning, save/load plain text, start-up, both looks
python tests/test_clone_echo.py   # clone worlds / triggers / aliases / buttons, log without my commands, copy without them, no gap
python tests/test_buttons.py      # buttons: bar, hotkeys, per-world scope, docking, manager, both looks
python tests/test_worldtabs_ui.py  # the row of world tabs, and clickable key hints in the DOS look
python tests/test_entrybox.py     # the growing entry box: lines, Shift+Enter, history, passwords, both looks
python tests/test_mudlet.py      # Mudlet package import (pure): pattern types, folders, the send() Lua shape, zips
python tests/test_importui.py    # importing in the app: the question, every-match colouring, both looks
python tests/test_speech.py      # what is spoken: cleaning, stats sentence, flood control, review
python tests/test_access.py       # screen reader mode end to end with a fake voice
python tests/test_updater.py      # update check/install against a fake local GitHub
python tests/test_dosforms.py     # DOS pick lists, the text page, gradient maker and customize form (both modes)
python tests/test_session.py      # several worlds: tabs, keys, per-world panes and rules, closing
python tests/test_multiworld_net.py   # two worlds against two local fake servers (drops, reconnects, logging)
python tests/test_multiworld_fuzz.py  # random world operations with the invariants checked
python tests/test_echo_line.py    # Enter ends an unfinished game line but not a prompt
python tests/test_dos_fit.py      # every DOS screen: nothing wrapped out of place or cut off
python tests/test_combatfilter.py # skipping other people's fights for the voice
python tests/test_local_server.py # needs the local test server, skips otherwise
```

`python run_tests.py [names]` runs them all (or just the ones named) on a separate invisible
Windows desktop, so their windows can never grab your focus or keystrokes, and exits non-zero if any
fail. It also sets `SANCTUARY_QUIET=1`, which turns Tk's bell into a no-op (a window on another desktop
still beeps through your speakers otherwise); `python tests/test_quiet.py` checks it.

The Tk-based tests open a window briefly. `test_fuzz.py` checks that any chunking of a
stream parses identically, that malformed input never raises, that buffers stay bounded
and parsing stays linear, and that negotiation can never produce a reply storm.

## Local test server

The game repo is source-only (no player files or most data), so `testserver/` builds a
throwaway instance with minimal fixtures. It is for **local testing only**; nothing here
touches a live game. Run inside WSL/Linux (needs `g++-11`, `ccache`,
`libcurl4-openssl-dev`, `libcrypt-dev`):

```
bash testserver/setup.sh /path/to/haven-duskholm [~/haven-test] [3500]
bash testserver/stop.sh [3500]
```

`setup.sh` copies the checkout to a scratch directory, builds it, creates the fixtures
and starts the game on the given port (plain telnet, no TLS). `bootstrap.sh` alone
re-creates fixtures and restarts an already-built copy. The test account is
`Testacct` / `testpass1`; bootstrap resets it to a fresh state each run. The server log
goes to `~/haven-run.log`.

`python tests/test_local_server.py` logs in through the client's protocol code (colour
prompt, MXP, password masking) and skips itself if nothing is listening on 3500.
`testserver/capture_flow.py` records raw login bytes into `testserver/captures/`.

## Layout

`Terminal` is pure protocol logic (bytes in, events out) and is what the tests
exercise. `Connection` owns the socket thread. `App` is the tkinter UI.
