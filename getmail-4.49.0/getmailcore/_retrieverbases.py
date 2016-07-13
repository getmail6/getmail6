#!/usr/bin/env python2.3
'''Base and mix-in classes implementing retrievers (message sources getmail can
retrieve mail from).

None of these classes can be instantiated directly.  In this module:

Mix-in classes for SSL/non-SSL initialization:

  POP3initMixIn
  Py23POP3SSLinitMixIn
  Py24POP3SSLinitMixIn
  IMAPinitMixIn
  IMAPSSLinitMixIn

Base classes:

  RetrieverSkeleton
  POP3RetrieverBase
  MultidropPOP3RetrieverBase
  IMAPRetrieverBase
  MultidropIMAPRetrieverBase
'''

__all__ = [
    'IMAPinitMixIn',
    'IMAPRetrieverBase',
    'IMAPSSLinitMixIn',
    'MultidropPOP3RetrieverBase',
    'MultidropIMAPRetrieverBase',
    'POP3_ssl_port',
    'POP3initMixIn',
    'POP3RetrieverBase',
    'POP3SSLinitMixIn',
    'RetrieverSkeleton',
]

import sys
import os
import socket
import time
import email
import poplib
import imaplib
import re
import select

try:
    # do we have a recent pykerberos?
    HAVE_KERBEROS_GSS = False
    import kerberos
    if 'authGSSClientWrap' in dir(kerberos):
        HAVE_KERBEROS_GSS = True
except ImportError:
    pass

# hashlib only present in python2.5, ssl in python2.6; used together
# in SSL functionality below
try:
    import ssl
except ImportError:
    ssl = None
try:
    import hashlib
except ImportError:
    hashlib = None

# If we have an ssl module:
if ssl:
    # Is it recent enough to have hostname matching (Python 3.2+)?
    try:
        ssl_match_hostname = ssl.match_hostname
    except AttributeError:
    # Running a Python with no hostname matching
        def _dnsname_match(dn, hostname, max_wildcards=1):
            """Matching according to RFC 6125, section 6.4.3
            http://tools.ietf.org/html/rfc6125#section-6.4.3
            """
            pats = []
            if not dn:
                return False
        
            parts = dn.split(r'.')
            leftmost = parts[0]
            remainder = parts[1:]
        
            wildcards = leftmost.count('*')
            if wildcards > max_wildcards:
                # Issue #17980: avoid denials of service by refusing more
                # than one wildcard per fragment.  A survery of established
                # policy among SSL implementations showed it to be a
                # reasonable choice.
                raise getmailOperationError(
                    "too many wildcards in certificate DNS name: " + repr(dn))
        
            # speed up common case w/o wildcards
            if not wildcards:
                return dn.lower() == hostname.lower()
        
            # RFC 6125, section 6.4.3, subitem 1.
            # The client SHOULD NOT attempt to match a presented identifier
            # in which the wildcard character comprises a label other than
            # the left-most label.
            if leftmost == '*':
                # When '*' is a fragment by itself, it matches a non-empty
                # dotless fragment.
                pats.append('[^.]+')
            elif leftmost.startswith('xn--') or hostname.startswith('xn--'):
                # RFC 6125, section 6.4.3, subitem 3.
                # The client SHOULD NOT attempt to match a presented identifier
                # where the wildcard character is embedded within an A-label or
                # U-label of an internationalized domain name.
                pats.append(re.escape(leftmost))
            else:
                # Otherwise, '*' matches any dotless string, e.g. www*
                pats.append(re.escape(leftmost).replace(r'\*', '[^.]*'))
        
            # add the remaining fragments, ignore any wildcards
            for frag in remainder:
                pats.append(re.escape(frag))
        
            pat = re.compile(r'\A' + r'\.'.join(pats) + r'\Z', re.IGNORECASE)
            return pat.match(hostname)
        
        
        def ssl_match_hostname(cert, hostname):
            """Verify that *cert* (in decoded format as returned by
            SSLSocket.getpeercert()) matches the *hostname*. RFC 2818 and
            RFC 6125 rules are followed, but IP addresses are not accepted
            for *hostname*.
        
            getmailOperationError is raised on failure. On success, the function
            returns nothing.
            """
            if not cert:
                raise ValueError("empty or no certificate, ssl_match_hostname "
                                 "needs an SSL socket or SSL context with "
                                 "either CERT_OPTIONAL or CERT_REQUIRED")
            dnsnames = []
            san = cert.get('subjectAltName', ())
            for key, value in san:
                if key == 'DNS':
                    if _dnsname_match(value, hostname):
                        return
                    dnsnames.append(value)
            if not dnsnames:
                # The subject is only checked when there is no dNSName entry
                # in subjectAltName
                for sub in cert.get('subject', ()):
                    for key, value in sub:
                        # XXX according to RFC 2818, the most specific
                        # Common Name must be used.
                        if key == 'commonName':
                            if _dnsname_match(value, hostname):
                                return
                            dnsnames.append(value)
            if len(dnsnames) > 1:
                raise getmailOperationError("hostname %s "
                    "doesn't match either of %s"
                    % (hostname, ', '.join(map(repr, dnsnames))))
            elif len(dnsnames) == 1:
                raise getmailOperationError("hostname %s "
                    "doesn't match %s"
                    % (hostname, dnsnames[0]))
            else:
                raise getmailOperationError("no appropriate commonName or "
                    "subjectAltName fields were found")
        
try:
    from email.header import decode_header
except ImportError, o:
    # python < 2.5
    from email.Header import decode_header

from getmailcore.compatibility import *
from getmailcore.exceptions import *
from getmailcore.constants import *
from getmailcore.message import *
from getmailcore.utilities import *
from getmailcore._pop3ssl import POP3SSL, POP3_ssl_port
from getmailcore.baseclasses import *
import getmailcore.imap_utf7        # registers imap4-utf-7 codec


NOT_ENVELOPE_RECIPIENT_HEADERS = (
    'to',
    'cc',
    'bcc',
    'received',
    'resent-to',
    'resent-cc',
    'resent-bcc'
)

# How long a vanished message is kept in the oldmail state file for IMAP
# retrievers before we figure it's gone for good.  This is to allow users
# to only occasionally retrieve mail from certain IMAP folders without
# losing their oldmail state for that folder.  This is in seconds, so it's
# 30 days.
VANISHED_AGE = (60 * 60 * 24 * 30)

# Regex used to remove problematic characters from oldmail filenames
STRIP_CHAR_RE = r'[/\:;<>|]+'

# Kerberos authentication state constants
(GSS_STATE_STEP, GSS_STATE_WRAP) = (0, 1)

# For matching imap LIST responses
IMAP_LISTPARTS = re.compile(
    r'^\s*'
    r'\((?P<attributes>[^)]*)\)'
    r'\s+'
    r'"(?P<delimiter>[^"]+)"'
    r'\s+'
    # I *think* this should actually be a double-quoted string "like/this"
    # but in testing we saw an MSexChange response that violated that
    # expectation:
    #   (\HasNoChildren) "/" Calendar"
    # i.e. the leading quote on the mailbox name was missing.  The following
    # works for both by treating the leading/trailing double-quote as optional,
    # even when mismatched.
    r'("?)(?P<mailbox>.+?)("?)'
    r'\s*$'
)


# Constants used in socket module
NO_OBJ = object()
EAI_NONAME = getattr(socket, 'EAI_NONAME', NO_OBJ)
EAI_NODATA = getattr(socket, 'EAI_NODATA', NO_OBJ)
EAI_FAIL = getattr(socket, 'EAI_FAIL', NO_OBJ)


# Constant for POPSSL
POP3_SSL_PORT = 995


# Python added poplib._MAXLINE somewhere along the way.  As far as I can
# see, it serves no purpose except to introduce bugs into any software
# using poplib.  Any computer running Python will have at least some megabytes
# of userspace memory; arbitrarily causing message retrieval to break if any
# "line" exceeds 2048 bytes is absolutely stupid.
poplib._MAXLINE = 1 << 20   # 1MB; decrease this if you're running on a VIC-20


#
# Mix-in classes
#

#######################################
class POP3initMixIn(object):
    '''Mix-In class to do POP3 non-SSL initialization.
    '''
    SSL = False
    def _connect(self):
        self.log.trace()
        try:
            self.conn = poplib.POP3(self.conf['server'], self.conf['port'])
            self.setup_received(self.conn.sock)
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)
        except socket.timeout:
            raise
            #raise getmailOperationError('timeout during connect')
        except socket.gaierror, o:
            raise getmailOperationError(
                'error resolving name %s during connect (%s)'
                % (self.conf['server'], o)
            )

        self.log.trace('POP3 connection %s established' % self.conn
                       + os.linesep)


#######################################
class POP3_SSL_EXTENDED(poplib.POP3_SSL):
    # Extended SSL support for POP3 (certificate checking, 
    # fingerprint matching, cipher selection, etc.)

    def __init__(self, host, port=POP3_SSL_PORT, keyfile=None,
                 certfile=None, ssl_version=None, ca_certs=None,
                 ssl_ciphers=None):
        self.host = host
        self.port = port
        self.keyfile = keyfile
        self.certfile = certfile
        self.ssl_version = ssl_version
        self.ca_certs = ca_certs
        self.ssl_ciphers = ssl_ciphers

        self.buffer = ''
        msg = "getaddrinfo returns an empty list"
        self.sock = None
        for res in socket.getaddrinfo(self.host, self.port, 0,
                                      socket.SOCK_STREAM):
            (af, socktype, proto, canonname, sa) = res
            try:
                self.sock = socket.socket(af, socktype, proto)
                self.sock.connect(sa)
            except socket.error, msg:
                if self.sock:
                    self.sock.close()
                self.sock = None
                continue
            break
        if not self.sock:
            raise socket.error(msg)
        extra_args = {}
        if self.ssl_version:
            extra_args['ssl_version'] = self.ssl_version
        if self.ca_certs:
            extra_args['cert_reqs'] = ssl.CERT_REQUIRED
            extra_args['ca_certs'] = self.ca_certs
        if self.ssl_ciphers:
            extra_args['ciphers'] = self.ssl_ciphers

        self.file = self.sock.makefile('rb')
        self.sslobj = ssl.wrap_socket(self.sock, self.keyfile,
                                      self.certfile, **extra_args)
        self._debugging = 0
        self.welcome = self._getresp()


#######################################
class Py24POP3SSLinitMixIn(object):
    '''Mix-In class to do POP3 over SSL initialization with Python 2.4's
    poplib.POP3_SSL class.
    '''
    SSL = True
    def _connect(self):
        self.log.trace()
        if not hasattr(socket, 'ssl'):
            raise getmailConfigurationError(
                'SSL not supported by this installation of Python'
            )
        (keyfile, certfile) = check_ssl_key_and_cert(self.conf)
        ca_certs = check_ca_certs(self.conf)
        ssl_version = check_ssl_version(self.conf)
        ssl_fingerprints = check_ssl_fingerprints(self.conf)
        ssl_ciphers = check_ssl_ciphers(self.conf)
        using_extended_certs_interface = False
        try:
            if ca_certs or ssl_version or ssl_ciphers:
                using_extended_certs_interface = True
                # Python 2.6 or higher required, use above class instead of
                # vanilla stdlib one
                msg = ''
                if keyfile:
                    msg += 'with keyfile %s, certfile %s' % (keyfile, certfile)
                if ssl_version:
                    if msg:
                        msg += ', '
                    msg += ('using protocol version %s'
                            % self.conf['ssl_version'].upper())
                if ca_certs:
                    if msg:
                        msg += ', '
                    msg += 'with ca_certs %s' % ca_certs

                self.log.trace(
                    'establishing POP3 SSL connection to %s:%d %s'
                    % (self.conf['server'], self.conf['port'], msg)
                    + os.linesep
                )
                self.conn = POP3_SSL_EXTENDED(
                    self.conf['server'], self.conf['port'], keyfile, certfile,
                    ssl_version, ca_certs, ssl_ciphers
                )
            elif keyfile:
                self.log.trace(
                    'establishing POP3 SSL connection to %s:%d with '
                    'keyfile %s, certfile %s'
                    % (self.conf['server'], self.conf['port'], keyfile,
                       certfile)
                    + os.linesep
                )
                self.conn = poplib.POP3_SSL(
                    self.conf['server'], self.conf['port'], keyfile, certfile
                )
            else:
                self.log.trace('establishing POP3 SSL connection to %s:%d'
                               % (self.conf['server'], self.conf['port'])
                               + os.linesep)
                self.conn = poplib.POP3_SSL(self.conf['server'],
                                            self.conf['port'])
            self.setup_received(self.conn.sock)
            if ssl and hashlib:
                sslobj = self.conn.sslobj
                peercert = sslobj.getpeercert(True)
                ssl_cipher = sslobj.cipher()
                if ssl_cipher:
                    ssl_cipher = '%s:%s:%s' % ssl_cipher
                if not peercert:
                    actual_hash = None
                else:
                    actual_hash = hashlib.sha256(peercert).hexdigest().lower()
            else:
                actual_hash = None
                ssl_cipher = None

            # Ensure cert is for server we're connecting to
            if ssl and self.conf['ca_certs']:
                ssl_match_hostname(self.conn.sslobj.getpeercert(),
                               self.conf['server'])

            if ssl_fingerprints:
                if not actual_hash:
                    raise getmailOperationError(
                        'socket ssl_fingerprints mismatch (no cert provided)'
                    )

                any_matches = False
                for expected_hash in ssl_fingerprints:
                    if expected_hash == actual_hash:
                        any_matches = True
                if not any_matches:
                    raise getmailOperationError(
                        'socket ssl_fingerprints mismatch (got %s)'
                        % actual_hash
                    )

        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)
        except socket.timeout:
            #raise getmailOperationError('timeout during connect')
            raise
        except socket.gaierror, o:
            raise getmailOperationError(
                'error resolving name %s during connect (%s)'
                % (self.conf['server'], o)
            )

        self.conn.sock.setblocking(1)
        self.log.trace('POP3 connection %s established' % self.conn
                       + os.linesep)


#######################################
class Py23POP3SSLinitMixIn(object):
    '''Mix-In class to do POP3 over SSL initialization with custom-implemented
    code to support SSL with Python 2.3's poplib.POP3 class.
    '''
    SSL = True
    def _connect(self):
        self.log.trace()
        if not hasattr(socket, 'ssl'):
            raise getmailConfigurationError(
                'SSL not supported by this installation of Python'
            )
        (keyfile, certfile) = check_ssl_key_and_cert(self.conf)
        ca_certs = check_ca_certs(self.conf)
        ssl_version = check_ssl_version(self.conf)
        ssl_fingerprints = check_ssl_fingerprints(self.conf)
        ssl_ciphers = check_ssl_ciphers(self.conf)
        if ca_certs or ssl_version or ssl_ciphers or ssl_fingerprints:
            raise getmailConfigurationError(
                'SSL extended options are not supported by this'
                 ' installation of Python'
            )
        try:
            if keyfile:
                self.log.trace(
                    'establishing POP3 SSL connection to %s:%d with keyfile '
                    '%s, certfile %s'
                    % (self.conf['server'], self.conf['port'],
                       keyfile, certfile)
                    + os.linesep
                )
                self.conn = POP3SSL(self.conf['server'], self.conf['port'],
                                    keyfile, certfile)
            else:
                self.log.trace(
                    'establishing POP3 SSL connection to %s:%d'
                    % (self.conf['server'], self.conf['port'])
                    + os.linesep
                )
                self.conn = POP3SSL(self.conf['server'], self.conf['port'])

            self.setup_received(self.conn.rawsock)
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)
        except socket.timeout:
            #raise getmailOperationError('timeout during connect')
            raise
        except socket.gaierror, o:
            raise getmailOperationError('socket error during connect (%s)' % o)
        except socket.sslerror, o:
            raise getmailOperationError(
                'socket sslerror during connect (%s)' % o
            )

        self.log.trace('POP3 SSL connection %s established' % self.conn
                       + os.linesep)


#######################################
class IMAPinitMixIn(object):
    '''Mix-In class to do IMAP non-SSL initialization.
    '''
    SSL = False
    def _connect(self):
        self.log.trace()
        try:
            self.conn = imaplib.IMAP4(self.conf['server'], self.conf['port'])
            self.setup_received(self.conn.sock)
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)
        except socket.timeout:
            #raise getmailOperationError('timeout during connect')
            raise
        except socket.gaierror, o:
            raise getmailOperationError('socket error during connect (%s)' % o)

        self.log.trace('IMAP connection %s established' % self.conn
                       + os.linesep)


#######################################
class IMAP4_SSL_EXTENDED(imaplib.IMAP4_SSL):
    # Similar to above, but with extended support for SSL certificate checking,
    # fingerprints, etc.
    def __init__(self, host='', port=imaplib.IMAP4_SSL_PORT, keyfile=None, 
                 certfile=None, ssl_version=None, ca_certs=None, 
                 ssl_ciphers=None):
       self.ssl_version = ssl_version
       self.ca_certs = ca_certs
       self.ssl_ciphers = ssl_ciphers
       imaplib.IMAP4_SSL.__init__(self, host, port, keyfile, certfile)

    def open(self, host='', port=imaplib.IMAP4_SSL_PORT):
       self.host = host
       self.port = port
       self.sock = socket.create_connection((host, port))
       extra_args = {}
       if self.ssl_version:
           extra_args['ssl_version'] = self.ssl_version
       if self.ca_certs:
           extra_args['cert_reqs'] = ssl.CERT_REQUIRED
           extra_args['ca_certs'] = self.ca_certs
       if self.ssl_ciphers:
           extra_args['ciphers'] = self.ssl_ciphers

       self.sslobj = ssl.wrap_socket(self.sock, self.keyfile, self.certfile, 
                                     **extra_args)
       self.file = self.sslobj.makefile('rb')


#######################################
class IMAPSSLinitMixIn(object):
    '''Mix-In class to do IMAP over SSL initialization.
    '''
    SSL = True
    def _connect(self):
        self.log.trace()
        if not hasattr(socket, 'ssl'):
            raise getmailConfigurationError(
                'SSL not supported by this installation of Python'
            )
        (keyfile, certfile) = check_ssl_key_and_cert(self.conf)
        ca_certs = check_ca_certs(self.conf)
        ssl_version = check_ssl_version(self.conf)
        ssl_fingerprints = check_ssl_fingerprints(self.conf)
        ssl_ciphers = check_ssl_ciphers(self.conf)
        using_extended_certs_interface = False
        try:
            if ca_certs or ssl_version or ssl_ciphers:
                using_extended_certs_interface = True
                # Python 2.6 or higher required, use above class instead of
                # vanilla stdlib one
                msg = ''
                if keyfile:
                    msg += 'with keyfile %s, certfile %s' % (keyfile, certfile)
                if ssl_version:
                    if msg:
                        msg += ', '
                    msg += ('using protocol version %s' 
                            % self.conf['ssl_version'].upper())
                if ca_certs:
                    if msg:
                        msg += ', '
                    msg += 'with ca_certs %s' % ca_certs

                self.log.trace(
                    'establishing IMAP SSL connection to %s:%d %s'
                    % (self.conf['server'], self.conf['port'], msg)
                    + os.linesep
                )
                self.conn = IMAP4_SSL_EXTENDED(
                    self.conf['server'], self.conf['port'], keyfile, certfile, 
                    ssl_version, ca_certs, ssl_ciphers
                )
            elif keyfile:
                self.log.trace(
                    'establishing IMAP SSL connection to %s:%d with keyfile '
                    '%s, certfile %s'
                    % (self.conf['server'], self.conf['port'],
                       keyfile, certfile)
                    + os.linesep
                )
                self.conn = imaplib.IMAP4_SSL(
                    self.conf['server'], self.conf['port'], keyfile, certfile
                )
            else:
                self.log.trace(
                    'establishing IMAP SSL connection to %s:%d'
                    % (self.conf['server'], self.conf['port']) + os.linesep
                )
                self.conn = imaplib.IMAP4_SSL(self.conf['server'],
                                              self.conf['port'])
            self.setup_received(self.conn.sock)
            if ssl and hashlib:
                sslobj = self.conn.ssl()
                peercert = sslobj.getpeercert(True)
                ssl_cipher = sslobj.cipher()
                if ssl_cipher:
                    ssl_cipher = '%s:%s:%s' % ssl_cipher
                if not peercert:
                    actual_hash = None
                else:
                    actual_hash = hashlib.sha256(peercert).hexdigest().lower()
            else:
                actual_hash = None
                ssl_cipher = None

            # Ensure cert is for server we're connecting to
            if ssl and self.conf['ca_certs']:
                ssl_match_hostname(self.conn.ssl().getpeercert(),
                               self.conf['server'])

            if ssl_fingerprints:
                if not actual_hash:
                    raise getmailOperationError(
                        'socket ssl_fingerprints mismatch (no cert provided)'
                    )

                any_matches = False
                for expected_hash in ssl_fingerprints:
                    if expected_hash == actual_hash:
                        any_matches = True
                if not any_matches:
                    raise getmailOperationError(
                        'socket ssl_fingerprints mismatch (got %s)' 
                        % actual_hash
                    )

        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)
        except socket.timeout:
            #raise getmailOperationError('timeout during connect')
            raise
        except socket.gaierror, o:
            errcode = o[0]
            if errcode in (EAI_NONAME, EAI_NODATA):
                # No such DNS name
                raise getmailDnsLookupError(
                    'no address for %s (%s)' % (self.conf['server'], o)
                )
            elif errcode == EAI_FAIL:
                # DNS server failure
                raise getmailDnsServerFailure(
                    'DNS server failure looking up address for %s (%s)' 
                    % (self.conf['server'], o)
                )
            else:
                raise getmailOperationError('socket error during connect (%s)' 
                                            % o)
        except socket.sslerror, o:
            raise getmailOperationError(
                'socket sslerror during connect (%s)' % o
            )

        fingerprint_message = ('IMAP SSL connection %s established'
                               % self.conn)
        if actual_hash:
            fingerprint_message += ' with fingerprint %s' % actual_hash
        if ssl_cipher:
            fingerprint_message += ' using cipher %s' % ssl_cipher
        fingerprint_message += os.linesep

        if self.app_options['fingerprint']:
            self.log.info(fingerprint_message)
        else:
            self.log.trace(fingerprint_message)

#
# Base classes
#

#######################################
class RetrieverSkeleton(ConfigurableBase):
    '''Base class for implementing message-retrieval classes.

    Sub-classes should provide the following data attributes and methods:

      _confitems - a tuple of dictionaries representing the parameters the class
                   takes.  Each dictionary should contain the following key,
                   value pairs:
                     - name - parameter name
                     - type - a type function to compare the parameter value
                     against (i.e. str, int, bool)
                     - default - optional default value.  If not present, the
                     parameter is required.

      __str__(self) - return a simple string representing the class instance.

      _getmsglist(self) - retieve a list of all available messages, and store
                          unique message identifiers in the dict
                          self.msgnum_by_msgid.
                          Message identifiers must be unique and persistent
                          across instantiations.  Also store message sizes (in
                          octets) in a dictionary self.msgsizes, using the
                          message identifiers as keys.

      _delmsgbyid(self, msgid) - delete a message from the message store based
                                 on its message identifier.

      _getmsgbyid(self, msgid) - retreive and return a message from the message
                                 store based on its message identifier.  The
                                 message is returned as a Message() class
                                 object. The message will have additional data
                                 attributes "sender" and "recipient".  sender
                                 should be present or "unknown".  recipient
                                 should be non-None if (and only if) the
                                 protocol/method of message retrieval preserves
                                 the original message envelope.

      _getheaderbyid(self, msgid) - similar to _getmsgbyid() above, but only the
                                 message header should be retrieved, if
                                 possible.  It should be returned in the same
                                 format.

      showconf(self) - should invoke self.log.info() to display the
                                configuration of the class instance.

    Sub-classes may also wish to extend or over-ride the following base class
    methods:

      __init__(self, **args)
      __del__(self)
      initialize(self, options)
      checkconf(self)
    '''
    def __init__(self, **args):
        self.headercache = {}
        self.deleted = {}
        self.set_new_timestamp()
        self.__oldmail_written = False
        self.__initialized = False
        self.gotmsglist = False
        self._clear_state()
        self.conn = None
        self.supports_idle = False
        ConfigurableBase.__init__(self, **args)

    def set_new_timestamp(self):
        self.timestamp = int(time.time())

    def _clear_state(self):
        self.msgnum_by_msgid = {}
        self.msgid_by_msgnum = {}
        self.sorted_msgnum_msgid = ()
        self.msgsizes = {}
        self.oldmail = {}
        self.__delivered = {}
        self.deleted = {}
        self.mailbox_selected = False
        
    def setup_received(self, sock):
        serveraddr = sock.getpeername()
        if len(serveraddr) == 2:
            # IPv4
            self.remoteaddr = '%s:%s' % serveraddr
        elif len(serveraddr) == 4:
            # IPv6
            self.remoteaddr = '[%s]:%s' % serveraddr[:2]
        else:
            # Shouldn't happen
            self.log.warn('unexpected peer address format %s', str(serveraddr))
            self.remoteaddr = str(serveraddr)
        self.received_from = '%s (%s)' % (self.conf['server'], 
                                          self.remoteaddr)

    def __str__(self):
        self.log.trace()
        return str(self.conf)

    def list_mailboxes(self):
        raise NotImplementedError('virtual')

    def select_mailbox(self, mailbox):
        raise NotImplementedError('virtual')

    def __len__(self):
        self.log.trace()
        return len(self.msgnum_by_msgid)

    def __getitem__(self, i):
        self.log.trace('i == %d' % i)
        if not self.__initialized:
            raise getmailOperationError('not initialized')
        return self.sorted_msgnum_msgid[i][1]

    def _oldmail_filename(self, mailbox):
        assert (mailbox is None 
                or (isinstance(mailbox, (str, unicode)) and mailbox)), (
            'bad mailbox %s (%s)' % (mailbox, type(mailbox))
        )
        filename = self.oldmail_filename
        if mailbox is not None:
            if isinstance(mailbox, str):
                mailbox = mailbox.decode('utf-8')
            mailbox = re.sub(STRIP_CHAR_RE, '.', mailbox)
            mailbox = mailbox.encode('utf-8')
            # Use oldmail file per IMAP folder
            filename += '-' + mailbox
        # else:
            # mailbox is None, is POP, just use filename
        return filename

    def oldmail_exists(self, mailbox):
        '''Test whether an oldmail file exists for a specified mailbox.'''
        return os.path.isfile(self._oldmail_filename(mailbox))

    def read_oldmailfile(self, mailbox):
        '''Read contents of an oldmail file.  For POP, mailbox must be 
        explicitly None.
        '''
        assert not self.oldmail, (
            'still have %d unflushed oldmail' % len(self.oldmail)
        )
        self.log.trace('mailbox=%s' % mailbox)
        
        filename = self._oldmail_filename(mailbox)
        logname = '%s:%s' % (self, mailbox or '')
        try:
            f = open(filename, 'rb')
        except IOError:
            self.log.moreinfo('no oldmail file for %s%s'
                              % (logname, os.linesep))
            return
            
        for line in f:
            line = line.strip()
            if not line or not '\0' in line:
                # malformed
                continue
            try:
                (msgid, timestamp) = line.split('\0', 1)
                if msgid.count('/') == 2:
                    # Was pre-4.22.0 file format, which includes the
                    # mailbox name in the msgid, in the format
                    # 'uidvalidity/mailbox/serveruid'.
                    # Strip it out.
                    fields = msgid.split('/')
                    msgid = '/'.join([fields[0], fields[2]])
                self.oldmail[msgid] = int(timestamp)
            except ValueError:
                # malformed
                self.log.info(
                    'skipped malformed line "%r" for %s%s'
                    % (line, logname, os.linesep)
                )
        self.log.moreinfo(
            'read %i uids for %s%s'
            % (len(self.oldmail), logname, os.linesep)
        )
        self.log.moreinfo('read %i uids in total for %s%s'
                          % (len(self.oldmail), logname, os.linesep))

    def write_oldmailfile(self, mailbox):
        '''Write oldmail info to oldmail file.'''
        self.log.trace('mailbox=%s' % mailbox)
        
        filename = self._oldmail_filename(mailbox)
        logname = '%s:%s' % (self, mailbox or '')
        
        oldmailfile = None
        wrote = 0
        msgids = frozenset(
            self.__delivered.keys()
        ).union(frozenset(self.oldmail.keys()))
        try:
            oldmailfile = updatefile(filename)
            for msgid in msgids:
                self.log.debug('msgid %s ...' % msgid)
                t = self.oldmail.get(msgid, self.timestamp)
                self.log.debug(' timestamp %s' % t + os.linesep)
                oldmailfile.write('%s\0%i%s' % (msgid, t, os.linesep))
                wrote += 1
            oldmailfile.close()
            self.log.moreinfo('wrote %i uids for %s%s'
                              % (wrote, logname, os.linesep))
        except IOError, o:
            self.log.error('failed writing oldmail file for %s (%s)'
                           % (logname, o) + os.linesep)
            if oldmailfile:
                oldmailfile.abort()
        self.__oldmail_written = True

    def initialize(self, options):
        # Options - dict of application-wide settings, including ones that 
        # aren't used in initializing the retriever.
        self.log.trace()
        self.checkconf()
        # socket.ssl() and socket timeouts are incompatible in Python 2.3
        if 'timeout' in self.conf:
            socket.setdefaulttimeout(self.conf['timeout'])
        else:
            # Explicitly set to None in case it was previously set
            socket.setdefaulttimeout(None)

        # Construct base filename for oldmail files.
        # strip problematic characters from oldmail filename.  Mostly for
        # non-Unix systems; only / is illegal in a Unix path component
        oldmail_filename = re.sub(
            STRIP_CHAR_RE, '-',
            'oldmail-%(server)s-%(port)i-%(username)s' % self.conf
        )
        self.oldmail_filename = os.path.join(self.conf['getmaildir'], 
                                             oldmail_filename)

        self.received_from = None
        self.app_options = options
        self.__initialized = True

    def quit(self):
        if self.mailbox_selected is not False:
            self.write_oldmailfile(self.mailbox_selected)
        self._clear_state()

    def abort(self):
        '''On error conditions where you do not want modified state to be saved,
        call this before .quit().
        '''
        self._clear_state()

    def delivered(self, msgid):
        self.__delivered[msgid] = None

    def getheader(self, msgid):
        if not self.__initialized:
            raise getmailOperationError('not initialized')
        if not msgid in self.headercache:
            self.headercache[msgid] = self._getheaderbyid(msgid)
        return self.headercache[msgid]

    def getmsg(self, msgid):
        if not self.__initialized:
            raise getmailOperationError('not initialized')
        return self._getmsgbyid(msgid)

    def getmsgsize(self, msgid):
        if not self.__initialized:
            raise getmailOperationError('not initialized')
        try:
            return self.msgsizes[msgid]
        except KeyError:
            raise getmailOperationError('no such message ID %s' % msgid)

    def delmsg(self, msgid):
        if not self.__initialized:
            raise getmailOperationError('not initialized')
        self._delmsgbyid(msgid)
        self.deleted[msgid] = True


#######################################
class POP3RetrieverBase(RetrieverSkeleton):
    '''Base class for single-user POP3 mailboxes.
    '''
    def __init__(self, **args):
        RetrieverSkeleton.__init__(self, **args)
        self.log.trace()

    def select_mailbox(self, mailbox):
        assert mailbox is None, (
            'POP does not support mailbox selection (%s)' % mailbox
        )
        if self.mailbox_selected is not False:
            self.write_oldmailfile(self.mailbox_selected)

        self._clear_state()

        if self.oldmail_exists(mailbox):
            self.read_oldmailfile(mailbox)
        self.mailbox_selected = mailbox

        self._getmsglist()

    def _getmsgnumbyid(self, msgid):
        self.log.trace()
        if not msgid in self.msgnum_by_msgid:
            raise getmailOperationError('no such message ID %s' % msgid)
        return self.msgnum_by_msgid[msgid]

    def _getmsglist(self):
        self.log.trace()
        try:
            (response, msglist, octets) = self.conn.uidl()
            self.log.debug('UIDL response "%s", %d octets'
                           % (response, octets) + os.linesep)
            for (i, line) in enumerate(msglist):
                try:
                    (msgnum, msgid) = line.split(None, 1)
                    # Don't allow / in UIDs we store, as we look for that to 
                    # detect old-style oldmail files.  Shouldn't occur in POP3
                    # anyway.
                    msgid = msgid.replace('/', '-')
                except ValueError:
                    # Line didn't contain two tokens.  Server is broken.
                    raise getmailOperationError(
                        '%s failed to identify message index %d in UIDL output'
                        ' -- see documentation or use '
                        'BrokenUIDLPOP3Retriever instead'
                        % (self, i)
                    )
                msgnum = int(msgnum)
                if msgid in self.msgnum_by_msgid:
                    # UIDL "unique" identifiers weren't unique.
                    # Server is broken.
                    if self.conf.get('delete_dup_msgids', False):
                        self.log.debug('deleting message %s with duplicate '
                                       'msgid %s' % (msgnum, msgid)
                                       + os.linesep)
                        self.conn.dele(msgnum)
                    else:
                        raise getmailOperationError(
                            '%s does not uniquely identify messages '
                            '(got %s twice) -- see documentation or use '
                            'BrokenUIDLPOP3Retriever instead'
                            % (self, msgid)
                        )
                else:
                    self.msgnum_by_msgid[msgid] = msgnum
                    self.msgid_by_msgnum[msgnum] = msgid
            self.log.debug('Message IDs: %s'
                           % sorted(self.msgnum_by_msgid.keys()) + os.linesep)
            self.sorted_msgnum_msgid = sorted(self.msgid_by_msgnum.items())
            (response, msglist, octets) = self.conn.list()
            for line in msglist:
                msgnum = int(line.split()[0])
                msgsize = int(line.split()[1])
                msgid = self.msgid_by_msgnum.get(msgnum, None)
                # If no msgid found, it's a message that wasn't in the UIDL
                # response above.  Ignore it and we'll get it next time.
                if msgid is not None:
                    self.msgsizes[msgid] = msgsize

            # Remove messages from state file that are no longer in mailbox,
            # but only if the timestamp for them are old (30 days for now).
            # This is because IMAP users can have one state file but multiple
            # IMAP folders in different configuration rc files.
            for msgid in self.oldmail.keys():
                timestamp = self.oldmail[msgid]
                age = self.timestamp - timestamp
                if not self.msgsizes.has_key(msgid) and age > VANISHED_AGE:
                    self.log.debug('removing vanished old message id %s' % msgid
                                   + os.linesep)
                    del self.oldmail[msgid]

        except poplib.error_proto, o:
            raise getmailOperationError(
                'POP error (%s) - if your server does not support the UIDL '
                'command, use BrokenUIDLPOP3Retriever instead'
                 % o
            )
        self.gotmsglist = True

    def _delmsgbyid(self, msgid):
        self.log.trace()
        msgnum = self._getmsgnumbyid(msgid)
        self.conn.dele(msgnum)

    def _getmsgbyid(self, msgid):
        self.log.debug('msgid %s' % msgid + os.linesep)
        msgnum = self._getmsgnumbyid(msgid)
        self.log.debug('msgnum %i' % msgnum + os.linesep)
        try:
            response, lines, octets = self.conn.retr(msgnum)
            self.log.debug('RETR response "%s", %d octets'
                           % (response, octets) + os.linesep)
            msg = Message(fromlines=lines+[''])
            return msg
        except poplib.error_proto, o:
            raise getmailRetrievalError(
                'failed to retrieve msgid %s; server said %s' 
                % (msgid, o)
            )

    def _getheaderbyid(self, msgid):
        self.log.trace()
        msgnum = self._getmsgnumbyid(msgid)
        response, headerlist, octets = self.conn.top(msgnum, 0)
        parser = email.Parser.HeaderParser()
        return parser.parsestr(os.linesep.join(headerlist))

    def initialize(self, options):
        self.log.trace()
        # POP doesn't support different mailboxes
        self.mailboxes = (None, )
        # Handle password
        if self.conf.get('password', None) is None:
            self.conf['password'] = get_password(
                self, self.conf['username'], self.conf['server'],
                self.received_with, self.log
            )
        RetrieverSkeleton.initialize(self, options)
        try:
            self._connect()
            if self.conf['use_apop']:
                self.conn.apop(self.conf['username'], self.conf['password'])
            else:
                self.conn.user(self.conf['username'])
                self.conn.pass_(self.conf['password'])
            self._getmsglist()
            self.log.debug('msgids: %s'
                           % sorted(self.msgnum_by_msgid.keys()) + os.linesep)
            self.log.debug('msgsizes: %s' % self.msgsizes + os.linesep)
            # Remove messages from state file that are no longer in mailbox
            for msgid in self.oldmail.keys():
                if not self.msgsizes.has_key(msgid):
                    self.log.debug('removing vanished message id %s' % msgid
                                   + os.linesep)
                    del self.oldmail[msgid]
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)

    def abort(self):
        self.log.trace()
        RetrieverSkeleton.abort(self)
        if not self.conn:
            return
        try:
            self.conn.rset()
            self.conn.quit()
        except (poplib.error_proto, socket.error), o:
            pass
        self.conn = None

    def quit(self):
        RetrieverSkeleton.quit(self)
        self.log.trace()
        if not self.conn:
            return
        try:
            self.conn.quit()
        except (poplib.error_proto, socket.error), o:
            raise getmailOperationError('POP error (%s)' % o)
        except AttributeError:
            pass
        self.conn = None


#######################################
class MultidropPOP3RetrieverBase(POP3RetrieverBase):
    '''Base retriever class for multi-drop POP3 mailboxes.

    Envelope is reconstructed from Return-Path: (sender) and a header specified
    by the user (recipient).  This header is specified with the
    "envelope_recipient" parameter, which takes the form <field-name>[:<field-
    number>].  field-number defaults to 1 and is counted from top to bottom in
    the message.  For instance, if the envelope recipient is present in the
    second Delivered-To: header field of each message, envelope_recipient should
    be specified as "delivered-to:2".
    '''

    def initialize(self, options):
        self.log.trace()
        POP3RetrieverBase.initialize(self, options)
        self.envrecipname = (
            self.conf['envelope_recipient'].split(':')[0].lower()
        )
        if self.envrecipname in NOT_ENVELOPE_RECIPIENT_HEADERS:
            raise getmailConfigurationError(
                'the %s header field does not record the envelope '
                'recipient address'
            )
        self.envrecipnum = 0
        try:
            self.envrecipnum = int(
                self.conf['envelope_recipient'].split(':', 1)[1]
            ) - 1
            if self.envrecipnum < 0:
                raise ValueError(self.conf['envelope_recipient'])
        except IndexError:
            pass
        except ValueError, o:
            raise getmailConfigurationError(
                'invalid envelope_recipient specification format (%s)' % o
            )

    def _getmsgbyid(self, msgid):
        self.log.trace()
        msg = POP3RetrieverBase._getmsgbyid(self, msgid)
        data = {}
        for (name, val) in msg.headers():
            name = name.lower()
            val = val.strip()
            if name in data:
                data[name].append(val)
            else:
                data[name] = [val]

        try:
            line = data[self.envrecipname][self.envrecipnum]
        except (KeyError, IndexError), unused:
            raise getmailConfigurationError(
                'envelope_recipient specified header missing (%s)'
                % self.conf['envelope_recipient']
            )
        msg.recipient = address_no_brackets(line.strip())
        return msg


#######################################
class IMAPRetrieverBase(RetrieverSkeleton):
    '''Base class for single-user IMAP mailboxes.
    '''
    def __init__(self, **args):
        RetrieverSkeleton.__init__(self, **args)
        self.log.trace()
        self.gss_step = 0
        self.gss_vc = None
        self.gssapi = False

    def _clear_state(self):
        RetrieverSkeleton._clear_state(self)
        self.mailbox = None
        self.uidvalidity = None
        self.msgnum_by_msgid = {}
        self.msgid_by_msgnum = {}
        self.sorted_msgnum_msgid = ()
        self._mboxuids = {}
        self._mboxuidorder = []
        self.msgsizes = {}
        self.oldmail = {}
        self.__delivered = {}

    def checkconf(self):
        RetrieverSkeleton.checkconf(self)
        if self.conf['use_kerberos'] and not HAVE_KERBEROS_GSS:
            raise getmailConfigurationError(
                'cannot use kerberos authentication; Python kerberos support '
                'not installed or does not support GSS'
            )

    def gssauth(self, response):
        if not HAVE_KERBEROS_GSS:
            # shouldn't get here
            raise ValueError('kerberos GSS support not available')
        data = ''.join(str(response).encode('base64').splitlines())
        if self.gss_step == GSS_STATE_STEP:
            if not self.gss_vc:
                (rc, self.gss_vc) = kerberos.authGSSClientInit(
                    'imap@%s' % self.conf['server']
                )
                response = kerberos.authGSSClientResponse(self.gss_vc)
            rc = kerberos.authGSSClientStep(self.gss_vc, data)
            if rc != kerberos.AUTH_GSS_CONTINUE:
               self.gss_step = GSS_STATE_WRAP
        elif self.gss_step == GSS_STATE_WRAP:
            rc = kerberos.authGSSClientUnwrap(self.gss_vc, data)
            response = kerberos.authGSSClientResponse(self.gss_vc)
            rc = kerberos.authGSSClientWrap(self.gss_vc, response,
                                            self.conf['username'])
        response = kerberos.authGSSClientResponse(self.gss_vc)
        if not response:
            response = ''
        return response.decode('base64')
 
    def _getmboxuidbymsgid(self, msgid):
        self.log.trace()
        if not msgid in self.msgnum_by_msgid:
            raise getmailOperationError('no such message ID %s' % msgid)
        uid = self._mboxuids[msgid]
        return uid

    def _parse_imapcmdresponse(self, cmd, *args):
        self.log.trace()
        try:
            result, resplist = getattr(self.conn, cmd)(*args)
        except imaplib.IMAP4.error, o:
            if cmd == 'login':
                # Percolate up
                raise
            else:
                raise getmailOperationError('IMAP error (%s)' % o)
        if result != 'OK':
            raise getmailOperationError(
                'IMAP error (command %s returned %s %s)'
                % ('%s %s' % (cmd, args), result, resplist)
            )
        if cmd.lower().startswith('login'):
            self.log.debug('login command response %s' % resplist + os.linesep)
        else:
            self.log.debug(
                'command %s response %s'
                % ('%s %s' % (cmd, args), resplist)
                + os.linesep
            )
        return resplist

    def _parse_imapuidcmdresponse(self, cmd, *args):
        self.log.trace()
        try:
            result, resplist = self.conn.uid(cmd, *args)
        except imaplib.IMAP4.error, o:
            if cmd == 'login':
                # Percolate up
                raise
            else:
                raise getmailOperationError('IMAP error (%s)' % o)
        if result != 'OK':
            raise getmailOperationError(
                'IMAP error (command %s returned %s %s)'
                % ('%s %s' % (cmd, args), result, resplist)
            )
        self.log.debug('command uid %s response %s'
                       % ('%s %s' % (cmd, args), resplist) + os.linesep)
        return resplist

    def _parse_imapattrresponse(self, line):
        self.log.trace('parsing attributes response line %s' % line
                       + os.linesep)
        r = {}
        try:
            parts = line[line.index('(') + 1:line.rindex(')')].split()
            while parts:
                # Flags starts a parenthetical list of valueless flags
                if parts[0].lower() == 'flags' and parts[1].startswith('('):
                    while parts and not parts[0].endswith(')'):
                        del parts[0]
                    if parts:
                        # Last one, ends with ")"
                        del parts[0]
                    continue
                if len(parts) == 1:
                    # Leftover part -- not name, value pair.
                    raise ValueError
                name = parts.pop(0).lower()
                r[name] = parts.pop(0)
        except (ValueError, IndexError, AttributeError), o:
            raise getmailOperationError(
                'IMAP error (failed to parse attr response line "%s": %s)' 
                % (line, o)
            )
        self.log.trace('got %s' % r + os.linesep)
        return r

    def list_mailboxes(self):
        '''List (selectable) IMAP folders in account.'''
        mailboxes = []
        cmd = ('LIST', )
        resplist = self._parse_imapcmdresponse(*cmd)
        for item in resplist:
            m = IMAP_LISTPARTS.match(item)
            if not m:
                raise getmailOperationError(
                    'no match for list response "%s"' % item
                )
            g = m.groupdict()
            attributes = g['attributes'].split()
            if r'\Noselect' in attributes:
                # Can't select this mailbox, don't include it in output
                continue
            try:
                mailbox = g['mailbox'].decode('imap4-utf-7')
                mailboxes.append(mailbox)
                #log.debug(u'%20s : delimiter %s, attributes: %s',
                #          mailbox, g['delimiter'], ', '.join(attributes))
            except Exception, o:
                raise getmailOperationError('error decoding mailbox "%s"' 
                                            % g['mailbox'])
        return mailboxes

    def close_mailbox(self):
        # Close current mailbox so deleted mail is expunged.  One getmail
        # user had a buggy IMAP server that didn't do the automatic expunge,
        # so we do it explicitly here if we've deleted any messages.
        if self.deleted:
            self.conn.expunge()
        self.conn.close()
        self.write_oldmailfile(self.mailbox_selected)
        # And clear some state
        self.mailbox_selected = False
        self.mailbox = None
        self.uidvalidity = None
        self.msgnum_by_msgid = {}
        self.msgid_by_msgnum = {}
        self.sorted_msgnum_msgid = ()
        self._mboxuids = {}
        self._mboxuidorder = []
        self.msgsizes = {}
        self.oldmail = {}
        self.__delivered = {}

    def select_mailbox(self, mailbox):
        self.log.trace()
        assert mailbox in self.mailboxes, (
            'mailbox not in config (%s)' % mailbox
        )
        if self.mailbox_selected is not False:
            self.close_mailbox()

        self._clear_state()

        if self.oldmail_exists(mailbox):
            self.read_oldmailfile(mailbox)

        self.log.debug('selecting mailbox "%s"' % mailbox + os.linesep)
        try:
            if (self.app_options['delete'] or self.app_options['delete_after'] 
                    or self.app_options['delete_bigger_than']):
                read_only = False
            else:
                read_only = True
            (status, count) = self.conn.select(mailbox.encode('imap4-utf-7'), 
                                               read_only)
            if status == 'NO':
                # Specified mailbox doesn't exist, no permissions, etc.
                raise getmailMailboxSelectError(mailbox)
                
            self.mailbox_selected = mailbox
            # use *last* EXISTS returned
            count = int(count[-1])
            uidvalidity = self.conn.response('UIDVALIDITY')[1][0]
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)
        except (IndexError, ValueError), o:
            raise getmailOperationError(
                'IMAP server failed to return correct SELECT response (%s)'
                % o
            )
        self.log.debug('select(%s) returned message count of %d'
                       % (mailbox, count) + os.linesep)
        self.mailbox = mailbox
        self.uidvalidity = uidvalidity

        self._getmsglist(count)

        return count

    def _getmsglist(self, msgcount):
        self.log.trace()
        try:
            if msgcount:
                # Get UIDs and sizes for all messages in mailbox
                response = self._parse_imapcmdresponse(
                    'FETCH', '1:%d' % msgcount, '(UID RFC822.SIZE)'
                )
                for line in response:
                    if not line:
                        # One user had a server that returned a null response
                        # somehow -- try to just skip.
                        continue
                    r = self._parse_imapattrresponse(line)
                    # Don't allow / in UIDs we store, as we look for that to 
                    # detect old-style oldmail files.  Can occur with IMAP, at 
                    # least with some servers.
                    uid = r['uid'].replace('/', '-')
                    msgid = '%s/%s' % (self.uidvalidity, uid)
                    self._mboxuids[msgid] = r['uid']
                    self._mboxuidorder.append(msgid)
                    self.msgnum_by_msgid[msgid] = None
                    self.msgsizes[msgid] = int(r['rfc822.size'])

            # Remove messages from state file that are no longer in mailbox,
            # but only if the timestamp for them are old (30 days for now).
            # This is because IMAP users can have one state file but multiple
            # IMAP folders in different configuration rc files.
            for msgid in self.oldmail.keys():
                timestamp = self.oldmail[msgid]
                age = self.timestamp - timestamp
                if not self.msgsizes.has_key(msgid) and age > VANISHED_AGE:
                    self.log.debug('removing vanished old message id %s' % msgid
                                   + os.linesep)
                    del self.oldmail[msgid]

        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)
        self.gotmsglist = True

    def __getitem__(self, i):
        return self._mboxuidorder[i]

    def _delmsgbyid(self, msgid):
        self.log.trace()
        try:
            uid = self._getmboxuidbymsgid(msgid)
            #self._selectmailbox(mailbox)
            # Delete message
            if self.conf['move_on_delete']:
                self.log.debug('copying message to folder "%s"'
                               % self.conf['move_on_delete'] + os.linesep)
                response = self._parse_imapuidcmdresponse(
                    'COPY', uid, self.conf['move_on_delete']
                )
            self.log.debug('deleting message "%s"' % uid + os.linesep)
            response = self._parse_imapuidcmdresponse(
                'STORE', uid, 'FLAGS', '(\Deleted)'
            )
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

    def _getmsgpartbyid(self, msgid, part):
        self.log.trace()
        try:
            uid = self._getmboxuidbymsgid(msgid)
            # Retrieve message
            self.log.debug('retrieving body for message "%s"' % uid
                           + os.linesep)
            try:
                response = self._parse_imapuidcmdresponse('FETCH', uid, part)
            except (imaplib.IMAP4.error, getmailOperationError), o:
                # server gave a negative/NO response, most likely.  Bad server,
                # no doughnut.
                raise getmailRetrievalError(
                    'failed to retrieve msgid %s; server said %s' 
                    % (msgid, o)
                )
            # Response is really ugly:
            #
            # [
            #   (
            #       '1 (UID 1 RFC822 {704}',
            #       'message text here with CRLF EOL'
            #   ),
            #   ')',
            #   <maybe more>
            # ]
            
            # MSExchange is broken -- if a message is badly formatted enough
            # (virus, spam, trojan), it can completely fail to return the
            # message when requested.
            try:
                try:
                    sbody = response[0][1]
                except Exception, o:
                    sbody = None
                if not sbody:
                    self.log.error('bad message from server!')
                    sbody = str(response)
                msg = Message(fromstring=sbody)
            except TypeError, o:
                # response[0] is None instead of a message tuple
                raise getmailRetrievalError('failed to retrieve msgid %s' 
                                            % msgid)

            # record mailbox retrieved from in a header
            msg.add_header('X-getmail-retrieved-from-mailbox', 
                           self.mailbox_selected)

            # google extensions: apply labels, etc
            if 'X-GM-EXT-1' in self.conn.capabilities:
                metadata = self._getgmailmetadata(uid, msg)
                for (header, value) in metadata.items():
                    msg.add_header(header, value)

            return msg

        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

    def _getgmailmetadata(self, uid, msg):
        """
        Add Gmail labels and other metadata which Google exposes through an
        IMAP extension to headers in the message.
        
        See https://developers.google.com/google-apps/gmail/imap_extensions
        """
        try:
            # ['976 (X-GM-THRID 1410134259107225671 X-GM-MSGID '
            #   '1410134259107225671 X-GM-LABELS (labels space '
            #   'separated) UID 167669)']
            response = self._parse_imapuidcmdresponse('FETCH', uid,
                '(X-GM-LABELS X-GM-THRID X-GM-MSGID)')
        except imaplib.IMAP4.error, o:
            self.log.warning('Could not fetch google imap extensions: %s' % o)
            return {}

        if not response:
            return {}
            
        ext = re.search(
            'X-GM-THRID (?P<THRID>\d+) X-GM-MSGID (?P<MSGID>\d+)'
            ' X-GM-LABELS \((?P<LABELS>.*)\) UID',
            response[0]
        )
        if not ext:
            self.log.warning(
                'Could not parse google imap extensions. Server said: %s'
                % repr(response)
            )
            return {}

        results = ext.groupdict()
        metadata = {}
        for item in ('LABELS', 'THRID', 'MSGID'):
            if item in results and results[item]:
                metadata['X-GMAIL-%s' % item] = results[item]

        return metadata

    def _getmsgbyid(self, msgid):
        self.log.trace()
        if self.conf.get('use_peek', True):
            part = '(BODY.PEEK[])'
        else:
            part = '(RFC822)'
        return self._getmsgpartbyid(msgid, part)

    def _getheaderbyid(self, msgid):
        self.log.trace()
        if self.conf.get('use_peek', True):
            part = '(BODY.PEEK[header])'
        else:
            part = '(RFC822[header])'
        return self._getmsgpartbyid(msgid, part)

    def initialize(self, options):
        self.log.trace()
        self.mailboxes = self.conf.get('mailboxes', ('INBOX', ))
        # Handle password
        if (self.conf.get('password', None) is None
                and not (HAVE_KERBEROS_GSS and self.conf['use_kerberos'])):
            self.conf['password'] = get_password(
                self, self.conf['username'], self.conf['server'], 
                self.received_with, self.log
            )
            
        RetrieverSkeleton.initialize(self, options)
        try:
            self.log.trace('trying self._connect()' + os.linesep)
            self._connect()
            try:
                self.log.trace('logging in' + os.linesep)
                if self.conf['use_kerberos'] and HAVE_KERBEROS_GSS:
                    self.conn.authenticate('GSSAPI', self.gssauth)
                elif self.conf['use_cram_md5']:
                    self._parse_imapcmdresponse(
                        'login_cram_md5', self.conf['username'],
                        self.conf['password']
                    )
                else:
                    self._parse_imapcmdresponse('login', self.conf['username'],
                                                self.conf['password'])
            except imaplib.IMAP4.abort, o:
                raise getmailLoginRefusedError(o)
            except imaplib.IMAP4.error, o:
                raise getmailCredentialError(o)

            self.log.trace('logged in' + os.linesep)
            """
            self.log.trace('logged in, getting message list' + os.linesep)
            self._getmsglist()
            self.log.debug('msgids: %s'
                           % sorted(self.msgnum_by_msgid.keys()) + os.linesep)
            self.log.debug('msgsizes: %s' % self.msgsizes + os.linesep)
            # Remove messages from state file that are no longer in mailbox,
            # but only if the timestamp for them are old (30 days for now).
            # This is because IMAP users can have one state file but multiple
            # IMAP folders in different configuration rc files.
            for msgid in self.oldmail.keys():
                timestamp = self.oldmail[msgid]
                age = self.timestamp - timestamp
                if not self.msgsizes.has_key(msgid) and age > VANISHED_AGE:
                    self.log.debug('removing vanished old message id %s' % msgid
                                   + os.linesep)
                    del self.oldmail[msgid]
            """
            # Some IMAP servers change the available capabilities after 
            # authentication, i.e. they present a limited set before login.
            # The Python stlib IMAP4 class doesn't take this into account
            # and just checks the capabilities immediately after connecting.
            # Force a re-check now that we've authenticated.
            (typ, dat) = self.conn.capability()
            if dat == [None]:
                # No response, don't update the stored capabilities
                self.log.warn('no post-login CAPABILITY response from server\n')
            else:
                self.conn.capabilities = tuple(dat[-1].upper().split())

            if 'IDLE' in self.conn.capabilities:
                self.supports_idle = True
                imaplib.Commands['IDLE'] = ('AUTH', 'SELECTED')

            if self.mailboxes == ('ALL', ):
                # Special value meaning all mailboxes in account
                self.mailboxes = tuple(self.list_mailboxes())

        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

    def abort(self):
        self.log.trace()
        RetrieverSkeleton.abort(self)
        if not self.conn:
            return
        try:
            self.quit()
        except (imaplib.IMAP4.error, socket.error), o:
            pass
        self.conn = None

    def go_idle(self, folder, timeout=300):
        """Initiates IMAP's IDLE mode if the server supports it

        Waits until state of current mailbox changes, and then returns. Returns
        True if the connection still seems to be up, False otherwise.

        May throw getmailOperationError if the server refuses the IDLE setup
        (e.g. if the server does not support IDLE)

        Default timeout is 5 minutes.
        """

        if not self.supports_idle:
            self.log.warning('IDLE not supported, so not idling\n')
            raise getmailOperationError(
                'IMAP4 IDLE requested, but not supported by server'
            )


        if self.SSL:
            sock = self.conn.ssl()
        else:
            sock = self.conn.socket()

        # Based on current imaplib IDLE patch: http://bugs.python.org/issue11245
        self.conn.untagged_responses = {}
        self.conn.select(folder)
        tag = self.conn._command('IDLE')
        data = self.conn._get_response() # read continuation response

        if data is not None:
            raise getmailOperationError(
                'IMAP4 IDLE requested, but server refused IDLE request: %s' 
                % data
            )

        self.log.debug('Entering IDLE mode (server says "%s")\n' 
                       % self.conn.continuation_response)

        try:
            aborted = None
            (readable, unused, unused) = select.select([sock], [], [], timeout)
        except KeyboardInterrupt, o:
            # Delay raising this until we've stopped IDLE mode
            aborted = o

        if aborted is not None:
            self.log.debug('IDLE mode cancelled\n')
        elif readable:
            # The socket has data waiting; server has updated status
            self.log.info('IDLE message received\n')
        else:
            self.log.debug('IDLE timeout (%ds)\n' % timeout)

        try:
            self.conn.untagged_responses = {}
            self.conn.send('DONE\r\n')
            self.conn._command_complete('IDLE', tag)
        except imaplib.IMAP4.error, o:
            return False

        if aborted:
            raise aborted

        return True

    def quit(self):
        self.log.trace()
        if not self.conn:
            return
        try:
            if self.mailbox_selected is not False:
                self.close_mailbox()
            self.conn.logout()
        except imaplib.IMAP4.error, o:
            #raise getmailOperationError('IMAP error (%s)' % o)
            self.log.warning('IMAP error during logout (%s)' % o + os.linesep)
        RetrieverSkeleton.quit(self)
        self.conn = None


#######################################
class MultidropIMAPRetrieverBase(IMAPRetrieverBase):
    '''Base retriever class for multi-drop IMAP mailboxes.

    Envelope is reconstructed from Return-Path: (sender) and a header specified
    by the user (recipient).  This header is specified with the
    "envelope_recipient" parameter, which takes the form <field-name>[:<field-
    number>].  field-number defaults to 1 and is counted from top to bottom in
    the message.  For instance, if the envelope recipient is present in the
    second Delivered-To: header field of each message, envelope_recipient should
    be specified as "delivered-to:2".
    '''

    def initialize(self, options):
        self.log.trace()
        IMAPRetrieverBase.initialize(self, options)
        self.envrecipname = (self.conf['envelope_recipient'].split(':')
            [0].lower())
        if self.envrecipname in NOT_ENVELOPE_RECIPIENT_HEADERS:
            raise getmailConfigurationError(
                'the %s header field does not record the envelope recipient '
                'address'
            )
        self.envrecipnum = 0
        try:
            self.envrecipnum = int(
                self.conf['envelope_recipient'].split(':', 1)[1]
            ) - 1
            if self.envrecipnum < 0:
                raise ValueError(self.conf['envelope_recipient'])
        except IndexError:
            pass
        except ValueError, o:
            raise getmailConfigurationError(
                'invalid envelope_recipient specification format (%s)' % o
            )

    def _getmsgbyid(self, msgid):
        self.log.trace()
        msg = IMAPRetrieverBase._getmsgbyid(self, msgid)
        data = {}
        for (name, encoded_value) in msg.headers():
            name = name.lower()
            for (val, encoding) in decode_header(encoded_value):
                val = val.strip()
                if name in data:
                    data[name].append(val)
                else:
                    data[name] = [val]

        try:
            line = data[self.envrecipname][self.envrecipnum]
        except (KeyError, IndexError), unused:
            raise getmailConfigurationError(
                'envelope_recipient specified header missing (%s)'
                % self.conf['envelope_recipient']
            )
        msg.recipient = address_no_brackets(line.strip())
        return msg


# Choose right POP-over-SSL mix-in based on Python version being used.
if sys.hexversion >= 0x02040000:
    POP3SSLinitMixIn = Py24POP3SSLinitMixIn
else:
    POP3SSLinitMixIn = Py23POP3SSLinitMixIn
