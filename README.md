# Duskholm client

A small, dependency-free telnet client for the Haven-Duskholm MUD. Three Python files
(`duskholm_client.py`, `dosui.py` for the DOS-look widgets, `prompts.py` for configurable prompt
formats), tkinter only (ships with the standard Windows Python installer). Keep them together.
Start it with `pythonw duskholm_client.py` to avoid the console window.

```
python duskholm_client.py [host [port]]
```

Defaults to `duskholm.com:3001` (TLS). Port 3000 is plain telnet.

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
- **Skins and a user-adjustable palette** (View > Skin, View > Colours…). Five built in:
  *Plain* (neutral dark, the default), *Plain Light*, *Moody* (violet-black, tarnished gold,
  spectral teal), *Retro Phosphor* (green-screen CRT) and *Retro DOS* (16-colour VGA, blue
  panels, chunky buttons). A skin sets every colour, the 16-colour game palette, button
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
    `~/.duskholm_skins/`; drop in files from others (or hand-write one) and they appear in the
    Skin menu. Bad or oversized files are ignored.
  - Windows draws the menu bar and scrollbar itself, so those keep the system look.
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
  menu with your current font pre-selected. The DOS look remembers its own font size, separate
  from the normal look.
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
- **Line spacing**: extra pixels between lines, 0-12 (Font dialog, or F7 in the DOS look).
- Command history, aliases, session logging, font zoom (Ctrl +/- or
  Ctrl+wheel), 20,000-line scrollback, keep-alive, optional bell.

Settings live in `~/.duskholm_client.json`.

## Local commands

Local commands start with `/` (the game has none). `//text` sends `/text`.

| Command | Does |
| --- | --- |
| `/connect [host [port]]`, `/disconnect`, `/reconnect`, `/quit` | connection control |
| `/alias name a;b $*` | define an alias; `;` separates commands, `$*` is the arguments (otherwise they are appended to the last command) |
| `/unalias name`, `/aliases` | remove / list aliases |
| `/log [file]` | start or stop logging |
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
python tests/test_local_server.py # needs the local test server, skips otherwise
```

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
