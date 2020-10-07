# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

'''Classes implementing retrievers (message sources getmail can retrieve mail
from).

Currently implemented:

  SimplePOP3Retriever
  SimplePOP3SSLRetriever
  BrokenUIDLPOP3Retriever
  BrokenUIDLPOP3SSLRetriever
  MultidropPOP3Retriever
  MultidropPOP3SSLRetriever
  MultidropSDPSRetriever
  SimpleIMAPRetriever -- IMAP, as a protocol, is a FPOS, and it shows.
    The Python standard library module imaplib leaves much up to
    the user because of this.
  SimpleIMAPSSLRetriever - the above, for IMAP-over-SSL.
  MultidropIMAPRetriever
  MultidropIMAPSSLRetriever
'''

__all__ = [
    'SimplePOP3Retriever',
    'SimplePOP3SSLRetriever',
    'BrokenUIDLPOP3Retriever',
    'BrokenUIDLPOP3SSLRetriever',
    'MultidropPOP3Retriever',
    'MultidropPOP3SSLRetriever',
    'MultidropSDPSRetriever',
    'SimpleIMAPRetriever',
    'SimpleIMAPSSLRetriever',
    'MultidropIMAPRetriever',
    'MultidropIMAPSSLRetriever',
]

import os
import poplib
import imaplib
import types

from getmailcore.exceptions import *
from getmailcore.constants import *
from getmailcore.utilities import *
from getmailcore.baseclasses import *
from getmailcore._retrieverbases import *


#
# Functional classes
#

#######################################
class SimplePOP3Retriever(POP3RetrieverBase, POP3initMixIn):
    '''Retriever class for single-user POP3 mailboxes.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=110),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfBool(name='use_apop', required=False, default=False),
        ConfBool(name='delete_dup_msgids', required=False, default=False),
    )
    received_from = None
    received_with = 'POP3'
    received_by = localhostname()

    def __str__(self):
        self.log.trace()
        return 'SimplePOP3Retriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('SimplePOP3Retriever(%s)' % self._confstring()
                      + os.linesep)

#######################################
class SimplePOP3SSLRetriever(POP3RetrieverBase, POP3SSLinitMixIn):
    '''Retriever class for single-user POP3-over-SSL mailboxes.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=POP3_SSL_PORT),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfBool(name='use_apop', required=False, default=False),
        ConfBool(name='delete_dup_msgids', required=False, default=False),
        ConfFile(name='keyfile', required=False, default=None),
        ConfFile(name='certfile', required=False, default=None),
        ConfFile(name='ca_certs', required=False, default=None),
        ConfTupleOfStrings(name='ssl_fingerprints', required=False, default=()),
        ConfString(name='ssl_version', required=False, default=None),
        ConfString(name='ssl_ciphers', required=False, default=None),
        ConfString(name='ssl_cert_hostname', required=False, default=None),
    )
    received_from = None
    received_with = 'POP3-SSL'
    received_by = localhostname()

    def __str__(self):
        self.log.trace()
        return 'SimplePOP3SSLRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('SimplePOP3SSLRetriever(%s)' % self._confstring()
                      + os.linesep)

#######################################
class BrokenUIDLPOP3RetrieverBase(POP3RetrieverBase):
    '''Retriever base class for single-user POP3 mailboxes on servers that do
    not properly assign unique IDs to messages.  Since with these broken servers
    we cannot rely on UIDL, we have to use message numbers, which are unique
    within a POP3 session, but which change across sessions.  This class
    therefore can not be used to leave old mail on the server and download only
    new mail.
    '''
    received_from = None
    received_by = localhostname()

    def _read_oldmailfile(self):
        '''Force list of old messages to be empty by making this a no-op, so
        duplicated IDs are always treated as new messages.'''
        self.log.trace()

    def write_oldmailfile(self, unused, **kwargs):
        '''Short-circuit writing the oldmail file.'''
        self.log.trace()

    def _getmsglist(self):
        '''Don't rely on UIDL; instead, use just the message number.'''
        self.log.trace()
        try:
            (response, msglist, octets) = self.conn.list()
            for line in msglist:
                msgnum = int(line.split()[0])
                msgsize = int(line.split()[1])
                self.msgnum_by_msgid[msgnum] = msgnum
                self.msgid_by_msgnum[msgnum] = msgnum
                self.msgsizes[msgnum] = msgsize
            self.sorted_msgnum_msgid = sorted(self.msgid_by_msgnum.items())
        except poplib.error_proto as o:
            raise getmailOperationError('POP error (%s)' % o)
        self.gotmsglist = True

#######################################
class BrokenUIDLPOP3Retriever(BrokenUIDLPOP3RetrieverBase, POP3initMixIn):
    '''For broken POP3 servers without SSL.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=110),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfBool(name='use_apop', required=False, default=False),
    )
    received_with = 'POP3'

    def __str__(self):
        self.log.trace()
        return 'BrokenUIDLPOP3Retriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('BrokenUIDLPOP3Retriever(%s)' % self._confstring()
                      + os.linesep)

#######################################
class BrokenUIDLPOP3SSLRetriever(BrokenUIDLPOP3RetrieverBase, POP3SSLinitMixIn):
    '''For broken POP3 servers with SSL.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=POP3_SSL_PORT),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfBool(name='use_apop', required=False, default=False),
        ConfFile(name='keyfile', required=False, default=None),
        ConfFile(name='certfile', required=False, default=None),
        ConfFile(name='ca_certs', required=False, default=None),
        ConfTupleOfStrings(name='ssl_fingerprints', required=False, default=()),
        ConfString(name='ssl_version', required=False, default=None),
        ConfString(name='ssl_ciphers', required=False, default=None),
        ConfString(name='ssl_cert_hostname', required=False, default=None),
    )
    received_with = 'POP3-SSL'

    def __str__(self):
        self.log.trace()
        return 'BrokenUIDLPOP3SSLRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('BrokenUIDLPOP3SSLRetriever(%s)' % self._confstring()
                      + os.linesep)

#######################################
class MultidropPOP3Retriever(MultidropPOP3RetrieverBase, POP3initMixIn):
    '''Retriever class for multi-drop POP3 mailboxes.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=110),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfBool(name='use_apop', required=False, default=False),
        ConfString(name='envelope_recipient'),
    )
    received_from = None
    received_with = 'POP3'
    received_by = localhostname()

    def __str__(self):
        self.log.trace()
        return 'MultidropPOP3Retriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('MultidropPOP3Retriever(%s)' % self._confstring()
                      + os.linesep)

#######################################
class MultidropPOP3SSLRetriever(MultidropPOP3RetrieverBase, POP3SSLinitMixIn):
    '''Retriever class for multi-drop POP3-over-SSL mailboxes.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=POP3_SSL_PORT),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfBool(name='use_apop', required=False, default=False),
        ConfString(name='envelope_recipient'),
        ConfFile(name='keyfile', required=False, default=None),
        ConfFile(name='certfile', required=False, default=None),
        ConfFile(name='ca_certs', required=False, default=None),
        ConfTupleOfStrings(name='ssl_fingerprints', required=False, default=()),
        ConfString(name='ssl_version', required=False, default=None),
        ConfString(name='ssl_ciphers', required=False, default=None),
        ConfString(name='ssl_cert_hostname', required=False, default=None),
    )
    received_from = None
    received_with = 'POP3-SSL'
    received_by = localhostname()

    def __str__(self):
        self.log.trace()
        return 'MultidropPOP3SSLRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('MultidropPOP3SSLRetriever(%s)' % self._confstring()
                      + os.linesep)

#######################################
class MultidropSDPSRetriever(SimplePOP3Retriever, POP3initMixIn):
    '''Retriever class for multi-drop SDPS (demon.co.uk) mailboxes.

    Extend POP3 class to include support for Demon's protocol extensions, known
    as SDPS.  A non-standard command (*ENV) is used to retrieve the message
    envelope.  See http://www.demon.net/helpdesk/products/mail/sdps-tech.shtml
    for details.

    Support originally requested by Paul Clifford for getmail v.2/3.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=110),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        # Demon apparently doesn't support APOP
        ConfBool(name='use_apop', required=False, default=False),
    )

    received_from = None
    received_with = 'SDPS'
    received_by = localhostname()

    def __str__(self):
        self.log.trace()
        return 'MultidropSDPSRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('MultidropSDPSRetriever(%s)' % self._confstring()
                      + os.linesep)

    def _getmsgbyid(self, msgid):
        self.log.trace()
        msg = SimplePOP3Retriever._getmsgbyid(self, msgid)

        # The magic of SDPS is the "*ENV" command.  Implement it:
        try:
            msgnum = self._getmsgnumbyid(msgid)
            resp, lines, octets = self.conn._longcmd('*ENV %i' % msgnum)
        except poplib.error_proto as o:
            raise getmailConfigurationError(
                'server does not support *ENV (%s)' % o
            )
        if len(lines) < 4:
            raise getmailOperationError('short *ENV response (%s)' % lines)
        msg.sender = lines[2]
        msg.recipient = lines[3]
        return msg

#######################################
class SimpleIMAPRetriever(IMAPRetrieverBase, IMAPinitMixIn):
    '''Retriever class for single-user IMAPv4 mailboxes.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=imaplib.IMAP4_PORT),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfTupleOfUnicode(name='mailboxes', required=False,
                           default="('INBOX', )", allow_specials=('ALL',)),
        ConfBool(name='use_peek', required=False, default=True),
        ConfString(name='move_on_delete', required=False, default=None),
        ConfBool(name='record_mailbox', required=False, default=True),
        # imaplib.IMAP4.login_cram_md5() requires the (unimplemented)
        # .authenticate(), so we can't do this yet (?).
        ConfBool(name='use_cram_md5', required=False, default=False),
        ConfBool(name='use_kerberos', required=False, default=False),
        ConfBool(name='use_xoauth2', required=False, default=False),
    )
    received_from = None
    received_with = 'IMAP4'
    received_by = localhostname()

    def __str__(self):
        self.log.trace()
        return 'SimpleIMAPRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('SimpleIMAPRetriever(%s)' % self._confstring()
                      + os.linesep)

#######################################
class SimpleIMAPSSLRetriever(IMAPRetrieverBase, IMAPSSLinitMixIn):
    '''Retriever class for single-user IMAPv4-over-SSL mailboxes.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        # socket.ssl() and socket timeouts were incompatible in Python 2.3;
        # if you have problems, comment this line out
        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=imaplib.IMAP4_SSL_PORT),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfTupleOfUnicode(name='mailboxes', required=False,
                           default="('INBOX', )", allow_specials=('ALL',)),
        ConfBool(name='use_peek', required=False, default=True),
        ConfString(name='move_on_delete', required=False, default=None),
        ConfBool(name='record_mailbox', required=False, default=True),
        ConfFile(name='keyfile', required=False, default=None),
        ConfFile(name='certfile', required=False, default=None),
        ConfFile(name='ca_certs', required=False, default=None),
        ConfTupleOfStrings(name='ssl_fingerprints', required=False, default=()),
        ConfString(name='ssl_version', required=False, default=None),
        ConfString(name='ssl_ciphers', required=False, default=None),
        # imaplib.IMAP4.login_cram_md5() requires the (unimplemented)
        # .authenticate(), so we can't do this yet (?).
        ConfBool(name='use_cram_md5', required=False, default=False),
        ConfBool(name='use_kerberos', required=False, default=False),
        ConfBool(name='use_xoauth2', required=False, default=False),
        ConfString(name='ssl_cert_hostname', required=False, default=None),
    )
    received_from = None
    received_with = 'IMAP4-SSL'
    received_by = localhostname()

    def __str__(self):
        self.log.trace()
        return 'SimpleIMAPSSLRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('SimpleIMAPSSLRetriever(%s)' % self._confstring()
                      + os.linesep)

#######################################
class MultidropIMAPRetriever(MultidropIMAPRetrieverBase, IMAPinitMixIn):
    '''Retriever class for multi-drop IMAPv4 mailboxes.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=imaplib.IMAP4_PORT),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfTupleOfUnicode(name='mailboxes', required=False,
                           default="('INBOX', )", allow_specials=('ALL',)),
        ConfBool(name='use_peek', required=False, default=True),
        ConfString(name='move_on_delete', required=False, default=None),
        ConfBool(name='record_mailbox', required=False, default=True),
        # imaplib.IMAP4.login_cram_md5() requires the (unimplemented)
        # .authenticate(), so we can't do this yet (?).
        ConfBool(name='use_cram_md5', required=False, default=False),
        ConfBool(name='use_kerberos', required=False, default=False),
        ConfBool(name='use_xoauth2', required=False, default=False),
        ConfString(name='envelope_recipient'),
    )
    received_from = None
    received_with = 'IMAP4'
    received_by = localhostname()

    def __str__(self):
        self.log.trace()
        return 'MultidropIMAPRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('MultidropIMAPRetriever(%s)' % self._confstring()
                      + os.linesep)

#######################################
class MultidropIMAPSSLRetriever(MultidropIMAPRetrieverBase, IMAPSSLinitMixIn):
    '''Retriever class for multi-drop IMAPv4-over-SSL mailboxes.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfDirectory(name='getmaildir', required=False, default='~/.getmail/'),

        # socket.ssl() and socket timeouts were incompatible in Python 2.3;
        # if you have problems, comment this line out
        ConfInt(name='timeout', required=False, default=180),
        ConfString(name='server'),
        ConfInt(name='port', required=False, default=imaplib.IMAP4_SSL_PORT),
        ConfString(name='username'),
        ConfPassword(name='password', required=False, default=None),
        ConfTupleOfStrings(name='password_command', required=False, default=()),
        ConfTupleOfUnicode(name='mailboxes', required=False,
                           default="('INBOX', )", allow_specials=('ALL',)),
        ConfBool(name='use_peek', required=False, default=True),
        ConfString(name='move_on_delete', required=False, default=None),
        ConfBool(name='record_mailbox', required=False, default=True),
        ConfFile(name='keyfile', required=False, default=None),
        ConfFile(name='certfile', required=False, default=None),
        ConfFile(name='ca_certs', required=False, default=None),
        ConfTupleOfStrings(name='ssl_fingerprints', required=False, default=()),
        ConfString(name='ssl_version', required=False, default=None),
        ConfString(name='ssl_ciphers', required=False, default=None),
        # imaplib.IMAP4.login_cram_md5() requires the (unimplemented)
        # .authenticate(), so we can't do this yet (?).
        ConfBool(name='use_cram_md5', required=False, default=False),
        ConfBool(name='use_kerberos', required=False, default=False),
        ConfBool(name='use_xoauth2', required=False, default=False),
        ConfString(name='envelope_recipient'),
        ConfString(name='ssl_cert_hostname', required=False, default=None),
    )
    received_from = None
    received_with = 'IMAP4-SSL'
    received_by = localhostname()

    def __str__(self):
        self.log.trace()
        return 'MultidropIMAPSSLRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('MultidropIMAPSSLRetriever(%s)' % self._confstring()
                      + os.linesep)

