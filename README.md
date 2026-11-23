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
- Command history, aliases, session logging, font zoom (Ctrl +/- or
  Ctrl+wheel), 20,000-line scrollback, keep-alive, optional bell.

Settings live in `~/.duskholm_client.json`.

## Local commands

Local commands start with `/` (the game has none). `//text` sends `/text`.

| Command | Does |
| --- | --- |
| `/connect [host [port]]`, `/disconnect`, `/quit` | connection control |
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

## Layout

`Terminal` is pure protocol logic (bytes in, events out) and is what the tests
exercise. `Connection` owns the socket thread. `App` is the tkinter UI.
