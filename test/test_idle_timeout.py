"""Tests for the configurable IMAP IDLE wait, without network connections."""

from unittest.mock import Mock, patch

import pytest

from getmailcore.exceptions import getmailConfigurationError
from getmailcore.retrievers import (
    SimpleIMAPRetriever,
    SimpleIMAPSSLRetriever,
    MultidropIMAPRetriever,
    MultidropIMAPSSLRetriever,
)


RETRIEVERS = (
    SimpleIMAPRetriever,
    SimpleIMAPSSLRetriever,
    MultidropIMAPRetriever,
    MultidropIMAPSSLRetriever,
)


def make_retriever(tmp_path, retriever_class=SimpleIMAPSSLRetriever, **options):
    args = dict(getmaildir=str(tmp_path), server='mail.example.org',
                username='user@example.org', password='test-password')
    if retriever_class in (MultidropIMAPRetriever, MultidropIMAPSSLRetriever):
        args['envelope_recipient'] = 'delivered-to:1'
    args.update(options)
    return retriever_class(**args)


@pytest.mark.parametrize('retriever_class', RETRIEVERS)
@pytest.mark.parametrize('configured,expected', [(None, 300), ('60', 60)])
def test_idle_timeout_configuration(tmp_path, retriever_class, configured, expected):
    options = {} if configured is None else {'idle_timeout': configured}
    retriever = make_retriever(tmp_path, retriever_class, **options)
    assert retriever.conf['idle_timeout'] == expected
    assert retriever.conf['timeout'] == 180


@pytest.mark.parametrize('retriever_class', RETRIEVERS)
@pytest.mark.parametrize('invalid', ['0', '-1', '"not-an-integer"'])
def test_invalid_idle_timeout(tmp_path, retriever_class, invalid):
    with pytest.raises(getmailConfigurationError):
        make_retriever(tmp_path, retriever_class, idle_timeout=invalid)


@pytest.mark.parametrize('configured,override,expected', [
    (300, None, 300), (60, None, 60), (60, 10, 10),
])
@pytest.mark.parametrize('notification', [False, True])
def test_go_idle_wait_and_completion(tmp_path, configured, override, expected, notification):
    retriever = make_retriever(tmp_path, idle_timeout=configured)
    retriever.supports_idle = True
    retriever.conn = Mock()
    retriever.conn._command.return_value = b'TAG1'
    retriever.conn._get_response.return_value = None
    retriever.select_quoted = Mock()
    readable = [retriever.conn.sock] if notification else []
    with patch('getmailcore._retrieverbases.select.select',
               return_value=(readable, [], [])) as select_mock:
        assert retriever.go_idle('INBOX', timeout=override) is True
    select_mock.assert_called_once_with([retriever.conn.sock], [], [], expected)
    retriever.conn.send.assert_called_once_with(b'DONE\r\n')
    retriever.conn._command_complete.assert_called_once_with('IDLE', b'TAG1')


def test_go_idle_socket_timeout_still_reconnects(tmp_path):
    retriever = make_retriever(tmp_path, idle_timeout=60)
    retriever.supports_idle = True
    retriever.conn = Mock()
    retriever.conn._get_response.return_value = None
    retriever.conn._command_complete.side_effect = TimeoutError()
    retriever.select_quoted = Mock()
    with patch('getmailcore._retrieverbases.select.select', return_value=([], [], [])):
        assert retriever.go_idle('INBOX') is False
