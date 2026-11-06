import os
import signal
import subprocess
import sys
import textwrap
import time

from getmailcore.utilities import updatefile


def _lines(path):
    with open(path) as f:
        return sum(1 for _ in f)


def _original(tmp_path, n=100):
    path = tmp_path / 'oldmail'
    path.write_text(''.join('old%d\n' % i for i in range(n)))
    return str(path)


def test_close_replaces_the_file(tmp_path):
    path = _original(tmp_path)
    f = updatefile(path)
    f.write('new\n')
    f.close()
    assert _lines(path) == 1
    assert os.listdir(str(tmp_path)) == ['oldmail']


def test_interrupted_writer_leaves_the_original(tmp_path):
    path = _original(tmp_path)

    def save():
        f = updatefile(path)
        f.write('partial\n')
        raise KeyboardInterrupt

    try:
        save()
    except KeyboardInterrupt:
        pass
    assert _lines(path) == 100
    assert os.listdir(str(tmp_path)) == ['oldmail']


def test_deleted_without_close_leaves_the_original(tmp_path):
    path = _original(tmp_path)
    f = updatefile(path)
    f.write('partial\n')
    del f
    assert _lines(path) == 100
    assert os.listdir(str(tmp_path)) == ['oldmail']


def test_abort_leaves_the_original(tmp_path):
    path = _original(tmp_path)
    f = updatefile(path)
    f.write('partial\n')
    f.abort()
    f.close()
    assert _lines(path) == 100
    assert os.listdir(str(tmp_path)) == ['oldmail']


def test_sigterm_during_save_leaves_the_original(tmp_path):
    # As bin/getmail does it: SIGTERM becomes KeyboardInterrupt.
    n = 200000
    path = _original(tmp_path, n)
    code = textwrap.dedent('''
        import signal, sys
        from getmailcore.utilities import updatefile
        def to_sigint(*a):
            raise KeyboardInterrupt('from signal')
        signal.signal(signal.SIGTERM, to_sigint)
        try:
            f = updatefile(sys.argv[1])
            print('writing', flush=True)
            while True:
                f.write('new\\n')
        except KeyboardInterrupt:
            pass
    ''')
    env = dict(os.environ, PYTHONPATH=os.getcwd())
    p = subprocess.Popen([sys.executable, '-c', code, path], env=env,
                         stdout=subprocess.PIPE)
    p.stdout.readline()
    time.sleep(0.2)
    p.send_signal(signal.SIGTERM)
    p.wait(30)
    assert _lines(path) == n
    assert os.listdir(str(tmp_path)) == ['oldmail']
