import os
import socket
import subprocess
import sys

GETMAIL_FETCH = os.path.join(os.path.dirname(__file__), os.pardir,
                             'getmail_fetch')


def test_message_option_delivers_the_file(tmp_path):
    maildir = tmp_path / 'maildir'
    for sub in ('cur', 'new', 'tmp'):
        (maildir / sub).mkdir(parents=True)
    startmsg = tmp_path / 'start.eml'
    startmsg.write_bytes(b'Subject: start\n\nbody \xff\n')
    # Nothing listens on this port, so the run stops with a socket error,
    # which happens after the --message file has been delivered.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    result = subprocess.run(
        [sys.executable, GETMAIL_FETCH, '-m', str(startmsg),
         '-p', str(port), '-t', '10', '127.0.0.1', 'user', 'password',
         str(maildir) + '/'],
        env=dict(os.environ, PYTHONPATH=os.path.dirname(GETMAIL_FETCH)),
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert 'TypeError' not in result.stderr
    delivered = list((maildir / 'new').iterdir())
    assert len(delivered) == 1
    assert b'Subject: start' in delivered[0].read_bytes()
    assert result.returncode == 10  # socket error
