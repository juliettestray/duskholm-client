"""Integration test against the LOCAL throwaway game instance (see testserver/).

Skips itself unless something is listening on 127.0.0.1:3500. It only ever connects to
localhost; never point it at a live game.
"""
import os, socket, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from duskholm_client import Terminal

HOST, PORT = "127.0.0.1", 3500


def main():
    try:
        s = socket.create_connection((HOST, PORT), timeout=2)
    except OSError:
        print("SKIP: no local test server on %s:%d (run testserver/setup.sh)" % (HOST, PORT))
        return 0

    term, state = Terminal(), {"screen": "", "echo_events": [], "sent": []}

    def pump(wait=1.0):
        end = time.time() + wait
        s.settimeout(0.2)
        while time.time() < end:
            try:
                d = s.recv(4096)
            except socket.timeout:
                continue
            if not d:
                break
            for ev in term.feed(d):
                if ev[0] == "send":
                    s.sendall(ev[1]); state["sent"].append(ev[1])
                elif ev[0] == "text":
                    state["screen"] += ev[1]
                elif ev[0] == "echo":
                    state["echo_events"].append(ev[1])

    def say(line):
        s.sendall(line.encode() + b"\r\n"); pump(1.0)

    pump()
    assert "colour" in state["screen"].lower(), state["screen"]
    say("y")
    assert term.mxp, "server offered MXP; client should have accepted"
    assert bytes([255, 253, 91]) in state["sent"], state["sent"]
    state["screen"] = ""
    say("Testacct")

    # Existing account asks for one password; a freshly reset one asks to set and retype it.
    for _ in range(3):
        if not term.echo_off:
            break
        say("testpass1")
    assert False in state["echo_events"] and True in state["echo_events"], state["echo_events"]
    assert "testpass1" not in state["screen"], "password must never appear in output"
    assert "Characters" in state["screen"] or "character" in state["screen"].lower(), state["screen"][-200:]
    assert not term.echo_off, "echo should be restored after login"
    s.close()
    print("local server integration OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
