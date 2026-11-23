# Duskholm client

A small, dependency-free telnet client for the Haven-Duskholm MUD. One Python
file, tkinter only (ships with the standard Windows Python installer).

```
python duskholm_client.py [host [port]]
```

Defaults to `duskholm.com:3001` (TLS). Port 3000 is plain telnet.

## What it handles

- **TLS or plain** connections, with a checkbox that swaps the stock ports.
- **Password prompts**: when the server sends `WILL ECHO`, input is masked and
  never echoed locally, saved to history, or written to the settings file.
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
python tests/test_client.py
```

Runs protocol assertions on the telnet/ANSI/MXP parser, then drives the GUI
against a local fake server (it opens a Tk window briefly).

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
