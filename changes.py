"""What changed in each version, newest first. Shown after an update (and by /changes), and the same text is used for the
release notes on GitHub (publish: the footer about downloading is added there). Write the entry for a new version here
BEFORE releasing it. Each entry is (version, text); text is Markdown-ish: "- " bullets, **bold**, `code`."""

CHANGES = [
    ("1.3.0", """- **CRT scanlines.** In the DOS look, Options > *CRT scanlines in the DOS look* (off, light, medium, strong; off by default) lays thin dark lines over the screen like an old monitor. Printing text is no slower, the mouse goes straight through, and `/crt` says whether they are showing.
- **Ctrl+Tab swaps worlds.** It goes back to the world you were in just before this one, and again to come back, so two worlds you are moving between swap whatever else is open. It can be changed under `/hotkeys` (*Swap with the last world*).
- **Plain skin is true.** The default skin was washed out: its background was a blue-grey, white text was grey, and dark colours were lightened (black text turned grey, dark blue turned pale). Plain is now a black screen, neutral greys, the standard bright terminal colours and no lightening, so black is black and every colour is shown as the game sent it. If a dark colour is hard to read, `Ctrl+*` raises the minimum contrast (`Ctrl+/` lowers it), and the other skins are unchanged.
- **Keep text in the DOS look.** The hotkey for *Keep-text checkbox* in the DOS Options menu was the same as another option; it is now `5`."""),
    ("1.2.2", """- **A smaller download.** The program is about half the size (12 MB instead of 25 MB): a library Sanctuary never used was being packed into it. Nothing you can see has changed."""),
    ("1.2.1", """- **Backscroll is kept per world.** Reloaded backscroll used to be saved by server address, so two worlds on the same address (two characters on one game, say) shared one file and their text got mixed. Each world now has its own, and a saved world keeps its history through a rename or a new address. Text saved by an older version goes to the first world that asks for it."""),
    ("1.2.0", """- **What's new.** After an update Sanctuary shows what changed, and if you skipped several versions it lists every one you missed, newest first. `/changes` shows the latest again, `/changes all` shows them all, and it is in the Help menu.
- **Keep text.** Options > *Show a 'Keep text' checkbox by the input box* puts a small checkbox at the right end of the input box. Tick it and Enter sends what you typed and leaves it there, so you can walk the same way many times by pressing Enter. Untick it to go back. `/keep [on|off]` does the same from the keyboard. Passwords are never kept.
- **Search panes.** Find has a new *Search panes* box (off by default). With it ticked, Find looks in your capture panes and pop-out windows as well as the main text, main window first, and says which pane a match is in. With it off, panes are left out, so nothing shows up twice.
- **Buttons in world files.** Exporting a world (.snc) can now include its buttons: the ones for every world and the ones tied to that world. They arrive switched off, as aliases do, so you can look them over (Alt+B). A hotkey you already use is kept by your own button.
- **JAWS without extras.** `/sr voice jaws` now works without installing pywin32.
- **Walk line.** The status line shows `Walk: <name> <walk> in from the right.`, matching the game's display.
- **Backscroll.** With reloaded backscroll on, a new session starts at the bottom, with the newest text."""),
    ("1.1.7", """- **JAWS now works without installing anything.** Choosing JAWS (`/sr voice jaws`) used to fail with "needs the pywin32 package" in the packaged program. It now reaches JAWS through a small built-in helper, so there is nothing to install. If JAWS is not running you are told so plainly.
- **Walk status line.** The line shown when you set a walk now reads `Walk: <name> <walk> in from the right.`, matching the game's own display.
- **Backscroll starts at the bottom.** With reloaded backscroll on, a new session now opens at the newest text instead of the top of the old text."""),
    ("1.1.6", """- **Menus, tidied.** The menu bar is now File, Edit, View, Automate, Tools, Options and Help, each holding what belongs together: File (worlds, logging, import/export, quit), Edit (Find, Copy without my commands, Clear screen), View (skin, colours, font, DOS look, stat bar, panes and layout), Automate (triggers, aliases, buttons, timer, customize form), Tools (notepad, game time, moon, gradient maker, hex to xterm, emoji picker), Options (in groups: connection, display, sending, sound, logging and backscroll, screen reader) and Help (help, hotkeys, updates, about). Nothing was removed.
- **Bigger menu text.** The drop-down and right-click menus now use the same size as the main text (between 10 and 22) and follow `Ctrl +` / `Ctrl -`. The strip of menu names along the top is drawn by Windows, so it keeps Windows' size; it stays a real Windows menu so screen readers read it as before."""),
    ("1.1.5", """- **Pictures open at the right.** Clicking a picture link now shows it in a pane at the right of the window instead of covering the whole main area, so you can keep typing. *Enlarge* makes it fill the main area (*Shrink* puts it back), *Close* dismisses it, and *Open original* opens it in your browser. After clicking the picture, `E` enlarges, `Esc` closes and `O` opens the original."""),
    ("1.1.4", """- **Find.** `Ctrl+F` opens Find and `Ctrl+Shift+F` finds the next match, searching from the bottom (newest first) or from the top (oldest first), with an optional *Match case*. Also `/find` and `/findnext`.
- **Rules follow the world, not its name.** Triggers, aliases, buttons, pane layouts and the game clock are now tied to a stable world ID, so you can rename a world without losing any of them. Older settings are converted automatically.
- **Worlds are named properly.** The first world is named after its saved world instead of "World 1", including when you open a second one.
- **Captures no longer wait.** A line the game leaves without a line break (a received tell, say) is captured after a moment instead of waiting for the next line or Enter.
- **AFK prompt.** The `[AFK]` prompt no longer glues lines together or leaks into captured lines.
- **Update relaunch delay.** After `/update`, Sanctuary waits a few seconds before relaunching so the installer's clean-up has finished (fixes a temp-folder error on restart)."""),
    ("1.1.3", """- **Scrollback length, and reloading it.** Options > *Scrollback length* (5,000 to 100,000 lines; 20,000 as before). A separate, off-by-default option, *Reload earlier backscroll at start*, saves the end of each world's text as plain text (no colours) when you quit and puts it back the next time you connect, with *Backscroll to reload* (500 to 20,000 lines, never more than the length) saying how much. The more you reload, the slower start-up is, so turning it on asks first; turning it off deletes what was saved.
- **Clone** worlds, triggers, aliases and buttons: a *Clone* button (also `Ctrl+D` in the list, or `C` in the DOS look) copies the selected entry under a new name. A cloned trigger starts switched off and a cloned button has no hotkey, so nothing fires twice or fights over a key.
- **Copy without my commands.** Right-click in the main text > *Copy without my commands*, or `/copyplain`, copies the selection with the commands you typed left out.
- **Leave my commands out of the log.** Options > *Put the commands I send in the log file* (on by default).
- **No gap where a hidden message was.** When a trigger hides a message, the blank line the game puts after it no longer leaves a hole.
- Includes 1.1.2's fix for the "Failed to load Python DLL" error after `/update`."""),
    ("1.1.2", """- **Fixes the "Failed to load Python DLL" error after `/update`.** The new program is now started without the old one's temporary-folder settings, so it unpacks its own. If you hit the error while updating to this version, the update itself went through: just run `Sanctuary.exe` again."""),
    ("1.1.1", """- **World tabs you can click.** In the normal look the worlds are a row of tabs centred under the toolbar: click one to switch, right-click for Close, `+` opens the Worlds list. A world with news gets a yellow dot. (Options > World tabs: always, only with two or more worlds, or off.) In the DOS look every key hint in the top row can be clicked too.
- **Buttons** (`Alt+B`, File > Buttons, `/button`). A bar of clickable buttons that send commands, each with an optional hotkey, for every world or just one, docked at the top or bottom (Options > Button bar) in both looks.
- **An entry box that grows as you type** (Options > Entry box grows to ...; off by default). `Shift+Enter` or `Ctrl+Enter` puts a line break in; a box with several lines sends each line as its own command.
- **Phone texts on a pane.** A new trigger preset, *Capture phone texts (no repeats)*, sends every date-stamped text (whether it pops up as it arrives or is listed when you look at the phone) to a Phone pane, never twice however often you look; wrapped texts stay in one piece. It uses a new "skip lines it already has" option on pane capture, so any log the game repeats can be captured the same way.
- **Your own side of a conversation.** Trigger rules can now match the commands you send, and *Capture my texts to a pane* puts `[Nov 24 18:33]You > Mara: ...` in the Phone pane. Every pane has a **Show what I send** switch (the pop-out window's *Show mine* box, the right-click menu on its tab, or `/panesent <pane>`) that also covers your own tells.
- **Pop-out windows can have an input bar of their own** (the *Input* box, or `/popinput <pane>`), with a *Send:* box whose text goes in front of every line, such as `text Mara`, so a Phone window pinned to a second monitor can be answered from there."""),
    ("1.1.0", """- **Pop a pane out into a window of its own** (handy on a second monitor): the arrow at the right of a pane area's header, or `/popout <pane>`. The window shows the pane's history and every new line, with colours, links, emoji, time stamps and follow-the-newest-line; Dock, closing it, or `/dock <pane>` brings it back. Where it was is remembered per world.
- **Keep a pane window on top** of other windows (the "On top" box, or `/ontop <pane>`).
- **Tear a pane off by dragging its tab** out of its area and letting go outside the header, as long as pane sizes are unlocked (`/panelock off`).
- **Import triggers and aliases from other clients** (File > Import from another client, or `/import file`): **MUSHclient** worlds, plugins and trigger files, and **Mudlet** packages (`.xml` and `.mpackage`). The file is read and described first; nothing in it is ever run, and anything that sends commands arrives switched off unless you say you trust the file. What cannot come across (scripts, timers, multi-line matching ...) is listed, not dropped silently.
- **Aliases can be two or three words** (`/alias "text ann" text annabelle %*`): the longest name that matches what you typed wins.
- A trigger that colours can now colour **every** match on a line ("Every match" in the trigger editor), and the limits are 1500 triggers and 300 aliases."""),
    ("1.0.9", """- **Copy and paste the way you expect.** Drag over text in the output or a pane, press `Ctrl+C`, and `Ctrl+V` pastes it into the entry box from wherever the keyboard is (also `Ctrl+Insert` / `Shift+Insert`). Right-click gives Cut / Copy / Paste in the entry box and Copy / Select all / Open link / Copy link in the text and panes.
- **`Ctrl+A` selects the whole entry line**, as in MUSHclient. Aliases moved to `Alt+A` to make room; both are rebindable.
- **Every world key can be changed** (`/hotkeys`): one row sets the prefix for all twelve (`Ctrl-F` gives Ctrl-F1 .. Ctrl-F12), and there are new keys for the next world, the previous world and closing a world.
- **Optional time stamps** (Options > Time stamps, off by default) in the main text, and a separate switch for each capture pane: put `(time)` after a pane's name in Panes / layout, or `/stamps <pane> on|off`.
- The DOS emoji list stays open until you close it, so you can add several.

**Fixes**
- Capture panes now keep following the newest line, including the first time a burst of lines fills a new pane, and after a resize, a font change or switching between the two looks. Only your own scrolling stops them.
- The entry box could hide the end of the last character when a line filled it exactly. It no longer does, in either look.
- The Hotkeys form could not save PageUp / PageDown keys."""),
    ("1.0.8", """- **Resize the pane areas with the mouse.** `/panelock off` (or File > Lock pane sizes), then drag the border of an area, or the divider between two stacked areas. It is locked by default so nothing moves by accident. In the DOS look the bars sit on the frame lines and the scrollbars step aside while it is unlocked.
- **A game clock for each world** (File > Game time, `/gametime`). Duskholm's (Eastern, 1:1) by default; each world can have its own zone and an IC:OOC time ratio, and `/timer game 21:30` follows it.
- **Colour emoji.** Emoji are drawn in Windows' own colour look in the text and the panes (on in the ordinary look; Options > "Colour emoji in the DOS look" turns it on there, off by default). And an **emoji picker** (`Alt+E`, `/emoji heart`), since Windows' emoji panel cannot put its choice into a Tk entry box. Pasted emoji stay in the box.
- **Each look keeps its own font, size and line spacing**, so changing one no longer changes the other.
- **Walk preview** stays up (per world), is read from `display`, shows your name instead of a long intro, and clears on login.

**Fixes**
- With "Hide prompt line" on, prompts that arrive in the same burst as the text after them (operations, combat) are now hidden too.
- Lines that arrive in parts keep their whole text and colours in the panes.
- The picture viewer, the notepad and the DOS dialogs stay above the panes; clicking a picture no longer opens your browser (use the Open original button or O)."""),
    ("1.0.7", """**Fixes for several worlds at once**
- A capture trigger firing in a world you were not looking at could add its pane to the world you were looking at. Each world now keeps its own panes.
- Your character's name, the status-line text and the "last call" time of a saved world now follow the world they belong to, instead of whichever one was on screen.
- The "Connected to ..." message names the world that actually connected.

Also new behind the scenes: tests that run two worlds against local fake servers (drops and reconnects, logging, closing mid-traffic) and a random-operations stress test."""),
    ("1.0.6", """**New**
- **A friendlier gradient editor**, in both the DOS look and the normal look: the colours are a row of swatches you can see and click (click to select, click again to change; `[+]` / `[-]` add and remove; `Ctrl`+arrows move one), with a live blend bar and a preview in the real colours. Changing a colour opens a picker: in the normal look a saturation square, a hue slider, a hex box and the 256 colours grouped by hue; in the DOS look the colours grouped by hue plus a hex box. Everything snaps to the nearest xterm colour, which is what the game can show. Keyboard and mouse both work. *Reverse* turns the colours round and *Save* keeps them as a named pattern.
- **Several gradients in one text**: in the paragraph editors, highlight a part and press `Ctrl-G`, then highlight another part and repeat. A highlight never cuts a colour code in half.
- **Close this world**: in the main menu (DOS) or File menu, or `Ctrl+Shift+W`; asks before hanging up a connected world.

**Fixes**
- Pressing Enter now ends an unfinished game line (for example a tell that arrives without its newline), so your command and the game's reply no longer run into it, and the Tells pane gets each tell as its own line. A prompt is still followed by what you type.
- Switching worlds lands on the latest line (a world you scrolled back in keeps its place)."""),
    ("1.0.5", """**New: several worlds at once**
- Dial a saved world while you are connected and it opens in its own tab (up to 12). `Ctrl+F1` to `Ctrl+F12` switch worlds; `/world`, `/newworld` and `/closeworld` do the same by command.
- Tabs sit in the top bar (DOS look) or the toolbar (normal look). A world with new text while you look elsewhere gets a `*` and one beep.
- Each world has its own scrollback, connection, history, half-typed line and pane areas; pane settings save automatically as you change them.
- Triggers and aliases have a **Global (all worlds)** setting, on by default. Turn it off and the rule works only in its own world. Existing rules are unchanged.
- The stat bar, status line and screen reader follow only the world on screen."""),
    ("1.0.4", """**New**
- DOS look first: pick lists for gradients and the customize form, a full-screen paragraph editor for descriptions (Ctrl-G gradient, Ctrl-K strip colours, colours shown as you write), one-page customize when the screen fits, Alt+Left / Alt+Right for back and next.
- Customize can also send through the game's own item editor, with the noisy replies hidden.
- Gradients: an "edges to middle" mode and a shareable pattern format. Retro Amber skin. Ctrl-* / Ctrl-/ change text contrast.

**Fixes**
- Esc no longer steps back through menus you had already left; plain Left/Right no longer act as back/next."""),
    ("1.0.3", """**Fixes**
- The built-in updater could leave a console window stuck on `find.exe` and never restart Sanctuary (and keep launching new windows if you closed it). The helper now uses no pipes and a hidden console, waits for Sanctuary to close, keeps the old program as `Sanctuary.old.exe`, restarts the new one, and gives up safely instead of looping.

**If you are on 1.0.1 or 1.0.2, update by hand once:** download `Sanctuary-1.0.3-win64.zip` below, close Sanctuary, and replace your `Sanctuary.exe` with the one in the zip. From 1.0.3 on, `/update` works. (If a stuck `find.exe` window appeared, just close it and end any `cmd.exe` window that is running a `swap.bat`.)"""),
    ("1.0.2", """**Fixes and additions**
- The lines the game prints when your defence (DF) is back to full now fill the DF gauge immediately.
- Setting any walk (credit, ego, changeling form, true form, ...) shows a preview on the status line, next to TLS in the DOS bar. (Options > Walk preview.)
- What you type is no longer echoed into the middle of a line that is still arriving (this could pull your command into a capture pane).
- Link clicks now work even if some text is selected; coming back to the window puts the keyboard focus back; Esc closes an open DOS menu even if focus had strayed.
- Screen reader mode: a combat-line manager (`/sr combat`) can leave other people's fights unread while keeping lines about you; "def" reading and the interval reader were added earlier.
- "Beep on new output" only beeps when Sanctuary is not the window in front; the DOS Options menu keeps its place; a real F1 help; DOS text is never wrapped or cut."""),
    ("1.0.1", """**Fixes**
- Picture links (.png, .jpg, ...) now open in a full-size viewer that fills the main window and fits the picture to it. Esc closes it; O or a click opens the original in your browser. (Before, they opened in a pane that could be tiny.)
- "Beep on new output" now beeps only when Sanctuary is not the window in front (it was beeping for everything). The choices are in a more useful order.
- DOS look: the Options menu keeps your place after you change a setting.
- F1 help is rebuilt from the real keys (Alt+M is the moon), with a help window in the normal look too.
- DOS look: text is never wrapped out of place or cut off; the top hint bar drops whole hints when the window is narrow instead of cutting one in half."""),
    ("1.0.0", """First public release of Sanctuary, a retro-friendly MUD client built for Duskholm and friends.

**Highlights**
- Normal look and a DOS terminal look (Alt+D), skins and an editable palette
- Triggers, aliases and capture panes (OOC, tells, ...) with presets and a layout preview
- Combat readout with self-ticking move/attack timers
- Clickable links (pictures open in the client), emoji, joined ASCII boxes (both optional)
- Timers, clock, notepad, moon, gradient maker, hex-to-xterm, customize form with a design book
- World settings files (.snc), remappable hotkeys
- **Screen reader mode**: speaks through NVDA, JAWS or the Windows voice, with review keys, alerts and an interval def/stun reader
- In-program update check (`/update`), checked against the SHA-256 published here"""),
]
