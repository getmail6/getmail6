import sys
import textwrap
import subprocess
import unittest.mock as mock

from getmailcore.message import Message
from getmailcore.exceptions import *
from getmailcore.destinations import MDA_lmtp
import getmailcore.logging as getmail_logging

import os, smtplib, ssl
import pytest
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader


greetru = "привет"
greetde = "Grüße"
byeru = 'пока'

def test_add_header():
    m = EmailMessage()
    m["Subject"] = "test"
    m["From"] = "my@gmail.com"
    m["To"] = "your@gmail.com"
    t = greetru.encode('Windows-1251')
    m.set_content(t,'text','plain')
    #m.as_string()
    #m.get_content()
    #m.get_content_charset()
    #m.get_charsets()
    gm = Message(fromstring=m.as_bytes())
    #te.decode('Windows-1251')
    gm.add_header('X-byeru',byeru)
    assert gm.content()['X-byeru'] == byeru
    ge = greetde.encode('latin1')
    gm.add_header('X-greetde',ge)
    #gm.content()['X-greetde']
    assert gm.content()['X-greetde'] != greetde

def test_add_header1():
    m = EmailMessage()
    m["Subject"] = "test"
    m["From"] = "my@gmail.com"
    m["To"] = "your@gmail.com"
    t = greetru.encode('Windows-1251')
    m.set_content(t,'text','plain')
    m.set_param('charset','Windows-1251')
    #m.as_string()
    #m.get_content()
    #m.get_content_charset()
    #m.get_charsets()
    gm = Message(fromstring=m.as_bytes())
    te = byeru.encode('Windows-1251')
    #te.decode('Windows-1251')
    gm.add_header('X-byeru',te)
    assert gm.content()['X-byeru'] == byeru
    ge = greetde.encode('latin1')
    gm.add_header('X-greetde',ge)
    #gm.content()['X-greetde']
    ### if coding is really wrong: no way
    assert gm.content()['X-greetde'] != greetde

def test_add_header2():
    mm = MIMEMultipart("alternative")
    mm["Subject"] = "multipart test"
    mm["From"] = "my@gmail.com"
    mm["To"] = "your@gmail.com"
    p1 = MIMEText(greetru, "plain")
    p1.set_param('charset','Windows-1251')
    p2 = MIMEText(greetde, "plain")
    p2.set_param('charset','latin1')
    mm.attach(p1)
    mm.attach(p2)
    #mm.get_charsets()
    gmm = Message(fromstring=mm.as_bytes())
    te = byeru.encode('Windows-1251')
    #te.decode('Windows-1251')
    gmm.add_header('X-byeru',te)
    assert gmm.content()['X-byeru'] == byeru
    ge = greetde.encode('latin1')
    gmm.add_header('X-greetde',ge)
    #gmm.content()['X-greetde']
    ### if coding is really wrong: no way
    assert gmm.content()['X-greetde'] != greetde
    #mm.as_string()

def test_spam_1():
    fl = os.path.join(os.path.split(__file__)[0],'spam.eml')
    with open(fl,'br') as f:
        spam_eml = f.read()
    gm = Message(fromstring=spam_eml)
    gmfl = gm.flatten(None,None)
    assert b'corrupt' in gmfl # check recover

def test_spam_2():
    fl = os.path.join(os.path.split(__file__)[0],'spam.eml')
    gmm = Message(fromfile=open(fl,'rb'))
    try:
        gmfl = gmm.flatten(None,None)
    except getmailDeliveryError as o:
        assert 'could not recover' in str(o) # noqa: PT017

def test_imap_ssl_parameters(capfd):
    for d in ("cur", "new", "tmp"):
        os.makedirs(f"/tmp/ssl/Maildir/{d}",exist_ok=True)
    sys.argv = ["getmail", "--getmaildir", "/tmp/ssl"]
    with open("/tmp/ssl/getmailrc", "w") as f:
        f.write(
            textwrap.dedent(
                """
                [retriever]
                type = SimpleIMAPSSLRetriever
                server = imap.gmail.com
                port = 993
                mailboxes = ALL
                username = doesntmatter@gmail.com
                password = doesntmatter
                ca_certs = /etc/ssl/certs/ca-certificates.crt
                [destination]
                type = Maildir
                path = /tmp/ssl/Maildir/
                [options]
                read_all = false
                delete = false
                """
            )
        )
    spec = spec_from_loader("getmail", SourceFileLoader("getmail", "getmail"))
    getmail = module_from_spec(spec)
    spec.loader.exec_module(getmail)
    try:
        getmail.main()
    except SystemExit:
        c = capfd.readouterr()
        assert c.err.index("AUTHENTICATIONFAILED") > 0


@pytest.fixture(autouse=False)
def clean_logger():
    """Clear stale Logger handlers that may have been set up by other tests."""
    getmail_logging.Logger.clearhandlers()
    yield
    getmail_logging.Logger.clearhandlers()


def _make_lmtp_msg(sender='sender@example.com', recipient='recipient@example.com'):
    msg = mock.MagicMock()
    msg.sender = sender
    msg.recipient = recipient
    return msg


def test_lmtp_successful_delivery():
    with mock.patch('smtplib.LMTP') as mock_lmtp_cls:
        mock_server = mock.MagicMock()
        mock_lmtp_cls.return_value = mock_server
        mock_server.send_message.return_value = {}

        dest = MDA_lmtp(host='localhost', port=24)
        dest._deliver_message(_make_lmtp_msg(), True, True)

        mock_lmtp_cls.assert_called_once_with('localhost', 24)
        mock_server.send_message.assert_called_once()


def test_lmtp_retry_on_disconnected(clean_logger):
    with mock.patch('smtplib.LMTP') as mock_lmtp_cls:
        mock_server = mock.MagicMock()
        mock_lmtp_cls.return_value = mock_server
        mock_server.send_message.side_effect = [
            smtplib.SMTPServerDisconnected('connection lost'),
            {},
        ]

        dest = MDA_lmtp(host='localhost', port=24)
        dest._deliver_message(_make_lmtp_msg(), True, True)

        # Initial connect in initialize() + one reconnect on retry
        assert mock_lmtp_cls.call_count == 2
        assert mock_server.send_message.call_count == 2


def test_lmtp_retry_on_sender_refused(clean_logger):
    with mock.patch('smtplib.LMTP') as mock_lmtp_cls:
        mock_server = mock.MagicMock()
        mock_lmtp_cls.return_value = mock_server
        mock_server.send_message.side_effect = [
            smtplib.SMTPSenderRefused(550, b'Sender refused', b'sender@example.com'),
            {},
        ]

        dest = MDA_lmtp(host='localhost', port=24)
        dest._deliver_message(_make_lmtp_msg(), True, True)

        assert mock_lmtp_cls.call_count == 2
        assert mock_server.send_message.call_count == 2


def test_lmtp_no_infinite_retry(clean_logger):
    with mock.patch('smtplib.LMTP') as mock_lmtp_cls:
        mock_server = mock.MagicMock()
        mock_lmtp_cls.return_value = mock_server
        mock_server.send_message.side_effect = smtplib.SMTPServerDisconnected('connection lost')

        dest = MDA_lmtp(host='localhost', port=24)

        with pytest.raises(smtplib.SMTPServerDisconnected):
            dest._deliver_message(_make_lmtp_msg(), True, True)

        # Exactly two send attempts: initial + one retry (no further retries)
        assert mock_server.send_message.call_count == 2



from getmailcore._retrieverbases import IMAPRetrieverBase


def _make_imap_retriever():
    r = IMAPRetrieverBase.__new__(IMAPRetrieverBase)
    r.log = mock.MagicMock()
    r.conf = {'record_mailbox': False}
    r.conn = mock.MagicMock()
    r.conn.capabilities = []
    r._getmboxuidbymsgid = lambda msgid: b'1'
    return r


def test_getmsgpartbyid_skips_unsolicited_response():
    """Regression test for issue #278.

    When delete=true, the IMAP server may send an unsolicited FLAGS
    response (plain bytes) ahead of the real (metadata, body) FETCH
    tuple. Naively taking response[0][1] indexes into those bytes and
    returns an int instead of the message body, crashing downstream
    with AttributeError. The retriever should skip such entries and
    find the actual (metadata, body) tuple wherever it appears.
    """
    r = _make_imap_retriever()
    r._parse_imapuidcmdresponse = lambda cmd, *args: [
        b'1 (FLAGS (\\Seen \\Deleted))',
        (b'1 (UID 1 RFC822 {35}', b'Return-Path: <a@b.com>\r\n\r\nbody'),
    ]

    msg = r._getmsgpartbyid('1', '(RFC822)')

    assert msg.content()['Return-Path'] == '<a@b.com>'


def test_getmsgpartbyid_normal_response_unaffected():
    """Control: a well-formed response (no unsolicited entries) still works."""
    r = _make_imap_retriever()
    r._parse_imapuidcmdresponse = lambda cmd, *args: [
        (b'1 (UID 1 RFC822 {35}', b'Return-Path: <c@d.com>\r\n\r\nbody'),
        b')',
    ]

    msg = r._getmsgpartbyid('1', '(RFC822)')

    assert msg.content()['Return-Path'] == '<c@d.com>'


def test_getmsgpartbyid_no_body_raises_retrieval_error():
    """Control: if no entry has a usable body, a getmailRetrievalError is raised."""
    r = _make_imap_retriever()
    r._parse_imapuidcmdresponse = lambda cmd, *args: [
        b'1 (FLAGS (\\Seen \\Deleted))',
    ]

    with pytest.raises(getmailRetrievalError):
        r._getmsgpartbyid('1', '(RFC822)')
