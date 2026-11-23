"""Record raw server bytes for the login flow against the LOCAL test instance (port 3500).

Usage: python capture_flow.py new|mxp|nocolour
'new' needs a freshly bootstrapped server (bootstrap.sh resets the test account).
"""
import os, socket, time, sys, re
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'captures')

def session(name, steps, reply_mxp=False):
    raw = open(os.path.join(OUT, f'capture_{name}.bin'), 'wb')
    tx = open(os.path.join(OUT, f'capture_{name}.txt'), 'w')
    s = socket.create_connection(('localhost', 3500), timeout=3)
    allb = b''

    def rd(w=1.5):
        s.settimeout(w)
        out = b''
        try:
            while True:
                d = s.recv(65536)
                if not d:
                    out += b'<<EOF>>'
                    break
                out += d
        except socket.timeout:
            pass
        return out

    def step(send):
        nonlocal allb
        if send is not None:
            b = send.encode() + b'\r\n'
            s.sendall(b)
            raw.write(b'\n<<SENT %r>>\n' % b)
            tx.write('>>> %r\n' % send)
        o = rd()
        allb += o
        raw.write(o)
        tx.write('<<< %r\n' % o)
        if reply_mxp and b'\xff\xfb[' in o:
            s.sendall(b'\xff\xfd[')
            raw.write(b'\n<<SENT IAC DO MXP>>\n')
            tx.write('>>> IAC DO MXP\n')
            o2 = rd()
            allb += o2
            raw.write(o2)
            tx.write('<<< %r\n' % o2)

    step(None)
    for x in steps:
        step(x)
    tx.write('\nTELNET SEQS: %s\n' % sorted(set(re.findall(rb'\xff[\xf0-\xff][\x00-\xff]?', allb))))
    tx.write('GA(ff f9)=%s EOR(ff ef)=%s WILL_ECHO(ff fb 01)=%s WONT_ECHO(ff fc 01)=%s WILL_MXP(ff fb 5b)=%s MXP_SB(ff fa 5b)=%s\n' % (
        b'\xff\xf9' in allb, b'\xff\xef' in allb, b'\xff\xfb\x01' in allb, b'\xff\xfc\x01' in allb,
        b'\xff\xfb[' in allb, b'\xff\xfa[' in allb))
    tx.close(); raw.close(); s.close()
    return allb

which = sys.argv[1]
if which == 'new':
    session('1_colour_new_account_create', ['y', 'Testacct', 'testpass1', 'testpass1', 'create', 'look'])
elif which == 'mxp':
    session('2_colour_relogin_mxp_accept', ['y', 'Testacct', 'testpass1', 'create', 'look'], reply_mxp=True)
elif which == 'nocolour':
    session('3_nocolour_relogin', ['n', 'Testacct', 'testpass1', 'create', 'look'])
