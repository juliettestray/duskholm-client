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

    # An existing account asks for one password. A freshly reset (trustee) account asks to set
    # and then retype it. Send the password only while the server is actually asking for one.
    asking = "password" in state["screen"].lower()
    for _ in range(3):
        if not (asking and term.echo_off):
            break
        mark = len(state["screen"])
        say("testpass1")
        asking = "password" in state["screen"][mark:].lower()
    assert False in state["echo_events"], state["echo_events"]
    assert "testpass1" not in state["screen"], "password must never appear in output"
    new_account = "Account created" in state["screen"]
    if new_account:
        # Known game quirk: after account creation the server never sends WONT ECHO
        # (comm.c state_confirm_new_account_password), so echo stays off here.
        assert term.echo_off
    else:
        assert True in state["echo_events"], state["echo_events"]
        assert not term.echo_off, "echo should be restored after login"
        assert "character" in state["screen"].lower(), state["screen"][-200:]
    s.close()
    print("local server integration OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
