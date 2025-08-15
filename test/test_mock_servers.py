import multiprocessing
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader
import sys
import tempfile
import textwrap
import glob
import socket
import os
import re
from typing import NamedTuple
import pytest
import email.message

@pytest.fixture(scope="session", autouse=True)
def always_spawn():
    multiprocessing.set_start_method("fork")

class FetchSize(NamedTuple):
    uid: int
    size: int

def pop3_uidl(uidls):
    return "\n".join(
        ("+OK Unique-IDs follow...",)
        + tuple(f"{index + 1} {uidl}" for index, uidl in enumerate(uidls))
        + (".", "")
    )

def pop3_list(sizes):
    return "\n".join(
        ("+OK {len(sizes)} messages ({sum(sizes)} octets)",)
        + tuple(f"{index + 1} {size}" for index, size in enumerate(sizes))
        + (".", "")
    )

def pop3_retr(message):
    return "\n".join((f"+OK {len(message)} octets", message, ".", ""))


def imap_reply_capability(tag):
    return f"* CAPABILITY IMAP4\r\n{tag} OK hello\r\n"


def imap_reply_login(tag):
    return f"{tag} OK [] Logged in\r\n"


def imap_reply_examine_inbox(tag, exists=1, uidvalidity=1):
    return textwrap.dedent(
        f"""\
        * {exists} EXISTS\r
        * OK [UIDVALIDITY {uidvalidity}] UIDs valid\r
        {tag} OK [READ-ONLY]\r
        """
    )


def imap_reply_fetch_s(tag, start, fetch_sizes):
    return "\r\n".join(
        tuple(
            f"* {index+start} FETCH (UID {fetch_size.uid} RFC822.SIZE {fetch_size.size})"
            for index, fetch_size in enumerate(fetch_sizes)
        )
        + (f"{tag} OK Fetch completed", "")
    )


def imap_reply_fetch_body(tag, index, uid, size=3, body="a"):
    return textwrap.dedent(
        f"""\
        * {index} FETCH (UID {uid} BODY[] {{{size}}}\r
        {body}\r
        )\r
        {tag} OK Fetch completed\r
        """
    )


def imap_reply_logout(tag):
    return textwrap.dedent(
        f"""\
        * BYE Logging out\r
        {tag} OK Logout completed.\r
        """
    )


def imap_close(tag):
    return f"{tag} OK Close completed\r\n"


class MockTCP:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)

    def accept(self):
        self.socket, _ = self.server.accept()

    def send(self, buf):
        self.socket.send(buf.encode("utf8"))

    def expect(self, expr):
        buf = self.socket.recv(1024).decode("utf8")
        m = re.match(expr, buf)
        assert m, f"{expr} != {buf}"
        return m

    def close(self):
        self.socket.close()


def get_getmail():
    # This is a hack because ../getmail doesn't have a .py extension and
    # cannot be normally imported
    spec = spec_from_loader("getmail", SourceFileLoader("getmail", "getmail"))
    getmail = module_from_spec(spec)
    spec.loader.exec_module(getmail)
    getmail.main()


def mbox_init(tmpdir):
    destination_path = f"{tmpdir}/inbox"
    with open(destination_path, "w") as f:
        pass
    return f"path = {destination_path}"


def maildir_init(tmpdir):
    destination_path = f"{tmpdir}/Maildir/"
    for d in ("cur", "new", "tmp"):
        os.makedirs(f"{destination_path}{d}")
    return f"path = {destination_path}"

def qmail_init(tmpdir):
    return "qmaillocal = /bin/true"

def generate_email():
    m = email.message.EmailMessage()
    m.set_content("Hello World!")
    m["Subject"] = "Hello World"
    m["From"] = "from@example.com"
    m["To"] = "to@example.com"
    m["Delivered-To"] = "to@example.com"
    return m.as_string()


def mda_external_init(tmpdir):
    return "path = /bin/true"

@pytest.mark.parametrize("destination_type,destination_init".split(','),
                         [("Mboxrd", mbox_init),
                          ("Maildir", maildir_init),
                          ("MDA_external", mda_external_init)])
def test_pop3(destination_type, destination_init):
    mock_tcp = MockTCP()
    with tempfile.TemporaryDirectory() as tmpdir:
        sys.argv = ["getmail", "--getmaildir", tmpdir]
        with open(f"{tmpdir}/getmailrc", "w") as f:
            f.write(
                textwrap.dedent(
                    f"""
                    [retriever]
                    type = SimplePOP3Retriever
                    server = 127.0.0.1
                    port = {mock_tcp.server.getsockname()[1]}
                    username = account_name
                    password = my_mail_password

                    [destination]
                    type = {destination_type}
                    {destination_init(tmpdir)}
                    """
                )
            )
        p = multiprocessing.Process(target=get_getmail, args=())
        p.start()
        mock_tcp.accept()
        mock_tcp.send("+OK:\n")
        mock_tcp.expect("USER account_name")
        mock_tcp.send("+OK:\n")
        mock_tcp.expect("PASS my_mail_password")
        mock_tcp.send("+OK:\n")
        mock_tcp.expect("UIDL")
        uidls = (
            "293c295a-1295-4783-9340-13f5b2b02fb6",
            "528df16f-9e10-4fa1-ac4a-6f79c4773bc1",
        )
        mock_tcp.send(pop3_uidl(uidls))
        mock_tcp.expect("LIST")
        mock_tcp.send(pop3_list((1, 1)))
        mock_tcp.expect("UIDL")
        mock_tcp.send(pop3_uidl(uidls))
        mock_tcp.expect("LIST")
        mock_tcp.send(pop3_list((1, 1)))
        mock_tcp.expect("RETR 1")
        mock_tcp.send(pop3_retr(generate_email()))
        mock_tcp.expect("RETR 2")
        mock_tcp.send(pop3_retr(generate_email()))
        mock_tcp.expect("QUIT")
        mock_tcp.send("+OK:")
        mock_tcp.close()
        p.join()


@pytest.mark.parametrize("destination_type,destination_init".split(','),
                         [("Mboxrd", mbox_init),
                          ("Maildir", maildir_init),
                          ("MDA_external", mda_external_init)])
def test_pop3_broken_uidl(destination_type, destination_init):
    mock_tcp = MockTCP()
    with tempfile.TemporaryDirectory() as tmpdir:
        sys.argv = ["getmail", "--getmaildir", tmpdir]
        with open(f"{tmpdir}/getmailrc", "w") as f:
            f.write(
                textwrap.dedent(
                    f"""
                    [retriever]
                    type = BrokenUIDLPOP3Retriever
                    server = 127.0.0.1
                    port = {mock_tcp.server.getsockname()[1]}
                    username = account_name
                    password = my_mail_password

                    [destination]
                    type = {destination_type}
                    {destination_init(tmpdir)}
                    """
                )
            )
        p = multiprocessing.Process(target=get_getmail, args=())
        p.start()
        mock_tcp.accept()
        mock_tcp.send("+OK:\n")
        mock_tcp.expect("USER account_name")
        mock_tcp.send("+OK:\n")
        mock_tcp.expect("PASS my_mail_password")
        mock_tcp.send("+OK:\n")
        mock_tcp.expect("LIST")
        mock_tcp.send(pop3_list((1, 1)))
        mock_tcp.expect("LIST")
        mock_tcp.send(pop3_list((1, 1)))
        mock_tcp.expect("RETR 1")
        mock_tcp.send(pop3_retr(generate_email()))
        mock_tcp.expect("RETR 2")
        mock_tcp.send(pop3_retr(generate_email()))
        mock_tcp.expect("QUIT")
        mock_tcp.send("+OK:")
        mock_tcp.close()
        p.join()


def multidest_init(tmpdir):
    destination_paths = (f"{tmpdir}/Maildir1/", f"{tmpdir}/Maildir2/")

    for destination_path in destination_paths:
        for d in ("cur", "new", "tmp"):
            os.makedirs(f"{destination_path}{d}")

    tpl = '\', \''.join(destination_paths)
    return f"destinations = ('{tpl}')"

def multisort_init(tmpdir):
    destination_paths = (f"{tmpdir}/Maildir1/", f"{tmpdir}/Maildir2/")

    for destination_path in destination_paths:
        for d in ("cur", "new", "tmp"):
            os.makedirs(f"{destination_path}{d}")

    return textwrap.dedent(
        """\
        default = [maildir1]
        [maildir1]
        type = MDA_external
        path = /bin/true

        [maildir2]
        type = MDA_external
        path = /bin/true
        """
    )

@pytest.mark.parametrize("destination_type,destination_init".split(','),
                         [("MDA_qmaillocal", qmail_init),
                          ("MultiDestination", multidest_init),
                          ("MultiSorter", multisort_init)])
def test_pop3_multidrop(destination_type, destination_init):
    mock_tcp = MockTCP()
    with tempfile.TemporaryDirectory() as tmpdir:
        sys.argv = ["getmail", "--getmaildir", tmpdir]
        with open(f"{tmpdir}/getmailrc", "w") as f:
            f.write(
                textwrap.dedent(
                    f"""
                    [retriever]
                    type = MultidropPOP3Retriever
                    server = 127.0.0.1
                    port = {mock_tcp.server.getsockname()[1]}
                    username = account_name
                    password = my_mail_password
                    envelope_recipient = delivered-to:1

                    [destination]
                    type = {destination_type}
                    {destination_init(tmpdir)}
                    """
                )
            )
        p = multiprocessing.Process(target=get_getmail, args=())
        p.start()
        mock_tcp.accept()
        mock_tcp.send("+OK:\n")
        mock_tcp.expect("USER account_name")
        mock_tcp.send("+OK:\n")
        mock_tcp.expect("PASS my_mail_password")
        mock_tcp.send("+OK:\n")
        mock_tcp.expect("UIDL")
        uidls = (
            "293c295a-1295-4783-9340-13f5b2b02fb6",
            "528df16f-9e10-4fa1-ac4a-6f79c4773bc1",
        )
        mock_tcp.send(pop3_uidl(uidls))
        mock_tcp.expect("LIST")
        mock_tcp.send(pop3_list((1, 1)))
        mock_tcp.expect("UIDL")
        mock_tcp.send(pop3_uidl(uidls))
        mock_tcp.expect("LIST")
        mock_tcp.send(pop3_list((1, 1)))
        mock_tcp.expect("RETR 1")
        mock_tcp.send(pop3_retr(generate_email()))
        mock_tcp.expect("RETR 2")
        mock_tcp.send(pop3_retr(generate_email()))
        mock_tcp.expect("QUIT")
        mock_tcp.send("+OK:")
        mock_tcp.close()
        p.join()


@pytest.mark.parametrize("destination_type,destination_init".split(','),
                         [("Mboxrd", mbox_init),
                          ("Maildir", maildir_init),
                          ("MDA_external", mda_external_init)])
def test_imap(destination_type, destination_init):
    mock_tcp = MockTCP()
    with tempfile.TemporaryDirectory() as tmpdir:
        sys.argv = ["getmail", "--getmaildir", tmpdir]
        with open(f"{tmpdir}/getmailrc", "w") as f:
            f.write(
                textwrap.dedent(
                    f"""
                    [retriever]
                    type = SimpleIMAPRetriever
                    server = 127.0.0.1
                    port = {mock_tcp.server.getsockname()[1]}
                    username = account_name
                    password = my_mail_password

                    [destination]
                    type = {destination_type}
                    {destination_init(tmpdir)}
                    """
                )
            )
        p = multiprocessing.Process(target=get_getmail, args=())
        p.start()
        mock_tcp.accept()
        mock_tcp.send("* OK\r\n")
        tag = mock_tcp.expect("([^ ]*) CAPABILITY").group(1)
        mock_tcp.send(imap_reply_capability(tag))
        tag = mock_tcp.expect('([^ ]*) LOGIN account_name "my_mail_password"').group(1)
        mock_tcp.send(imap_reply_login(tag))
        tag = mock_tcp.expect("([^ ]*) CAPABILITY").group(1)
        mock_tcp.send(imap_reply_capability(tag))
        tag = mock_tcp.expect("([^ ]*) EXAMINE INBOX").group(1)
        mock_tcp.send(imap_reply_examine_inbox(tag, exists=2, uidvalidity=1))
        tag = mock_tcp.expect(r"([^ ]*) FETCH 1:2 \(UID RFC822.SIZE\)").group(1)
        mock_tcp.send(imap_reply_fetch_s(tag, 1, (FetchSize(1, 3), (FetchSize(2, 3)))))
        tag = mock_tcp.expect(r"([^ ]*) UID FETCH 1 \(BODY.PEEK\[]\)").group(1)
        mock_tcp.send(imap_reply_fetch_body(tag, 1, 1))
        tag = mock_tcp.expect(r"([^ ]*) UID FETCH 2 \(BODY.PEEK\[]\)").group(1)
        mock_tcp.send(imap_reply_fetch_body(tag, 2, 2))
        tag = mock_tcp.expect("([^ ]*) CLOSE").group(1)
        mock_tcp.send(imap_close(tag))
        tag = mock_tcp.expect("([^ ]*) LOGOUT").group(1)
        mock_tcp.send(imap_reply_logout(tag))
        mock_tcp.close()
        p.join()


def test_imap_full():
    mock_tcp = MockTCP()
    with tempfile.TemporaryDirectory() as tmpdir:
        sys.argv = ["getmail", "--getmaildir", tmpdir]
        with open(f"{tmpdir}/oldmail-127.0.0.1-{mock_tcp.server.getsockname()[1]}-account_name-INBOX", "w") as f:
            f.write('1/1\x001745765433\n1/2\x001745765433\n')
        with open(f"{tmpdir}/getmailrc", "w") as f:
            f.write(
                textwrap.dedent(
                    f"""
                    [options]
                    delete = true

                    [retriever]
                    type = SimpleIMAPRetriever
                    server = 127.0.0.1
                    port = {mock_tcp.server.getsockname()[1]}
                    username = account_name
                    mailboxes = ALL
                    password_command = ("/usr/bin/echo", "my_mail_password")

                    [destination]
                    type = MDA_external
                    path = /bin/true

                    [filter]
                    type = Filter_external
                    path = /bin/cat
                    """
                )
            )
        p = multiprocessing.Process(target=get_getmail, args=())
        p.start()
        mock_tcp.accept()
        mock_tcp.send("* OK\r\n")
        tag = mock_tcp.expect("([^ ]*) CAPABILITY").group(1)
        mock_tcp.send(imap_reply_capability(tag))
        tag = mock_tcp.expect('([^ ]*) LOGIN account_name "my_mail_password"').group(1)
        mock_tcp.send(imap_reply_login(tag))
        tag = mock_tcp.expect("([^ ]*) CAPABILITY").group(1)
        mock_tcp.send(imap_reply_capability(tag))
        tag = mock_tcp.expect("([^ ]*) LIST  *").group(1)
        mock_tcp.send(f'* LIST (\\HasNoChildren) "/" INBOX\r\n{tag} OK List completed\r\n')
        tag = mock_tcp.expect("([^ ]*) SELECT INBOX").group(1)
        mock_tcp.send(textwrap.dedent(
            f"""\
            * 2 EXISTS\r
            * OK [UIDVALIDITY 1] UIDs valid\r
            {tag} OK [READ-WRITE] Select completed\r
            """
        ))
        tag = mock_tcp.expect(r"([^ ]*) FETCH 1:2 \(UID RFC822.SIZE\)").group(1)
        mock_tcp.send(imap_reply_fetch_s(tag, 1, (FetchSize(1, 3), (FetchSize(2, 3)))))
        tag = mock_tcp.expect(r"([^ ]*) UID FETCH 1 \(BODY.PEEK\[]\)").group(1)
        mock_tcp.send(imap_reply_fetch_body(tag, 1, 1))
        tag = mock_tcp.expect(r"([^ ]*) UID STORE 1 FLAGS \(\\Deleted \\Seen\)").group(1)
        mock_tcp.send(f"{tag} OK completed\r\n")
        tag = mock_tcp.expect(r"([^ ]*) UID FETCH 2 \(BODY.PEEK\[]\)").group(1)
        mock_tcp.send(imap_reply_fetch_body(tag, 2, 2))
        tag = mock_tcp.expect(r"([^ ]*) UID STORE 2 FLAGS \(\\Deleted \\Seen\)").group(1)
        mock_tcp.send(f"{tag} OK completed\r\n")
        tag = mock_tcp.expect(r"([^ ]*) EXPUNGE").group(1)
        mock_tcp.send(f"{tag} OK completed\r\n")
        tag = mock_tcp.expect("([^ ]*) CLOSE").group(1)
        mock_tcp.send(imap_close(tag))
        tag = mock_tcp.expect("([^ ]*) LOGOUT").group(1)
        mock_tcp.send(imap_reply_logout(tag))
        mock_tcp.close()
        p.join()
