# -*- coding: utf-8 -*-
# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

'''Base and mix-in classes implementing retrievers (message sources getmail can
retrieve mail from).

None of these classes can be instantiated directly.  In this module:

Mix-in classes for SSL/non-SSL initialization:

  POP3initMixIn
  POP3SSLinitMixIn
  IMAPinitMixIn
  IMAPSSLinitMixIn

Base classes:

  RetrieverSkeleton
  POP3RetrieverBase
  MultidropPOP3RetrieverBase
  IMAPRetrieverBase
  MultidropIMAPRetrieverBase
'''

import sys
import os
import socket
from socket import _socket
from ssl import CertificateError
import time
import email
import codecs
try:
    from email.Header import decode_header
    import email.Parser as Parser
except ImportError:
    from email.header import decode_header
    import email.parser as Parser
import poplib
import imaplib
import re
import select
import base64

try:
    # do we have a recent pykerberos?
    HAVE_KERBEROS_GSS = False
    import kerberos
    if 'authGSSClientWrap' in dir(kerberos):
        HAVE_KERBEROS_GSS = True
except ImportError:
    pass

###
# Monkey-patch imaplib to support the ID command ([RFC 2971](https://www.rfc-editor.org/rfc/rfc2971)) - begin
###
imaplib.Commands['ID'] = ('AUTH', 'SELECTED')
def imap_id_rfc2971(self, *kv_pairs, **kw):
    """(typ, [data]) = <instance>.id(kv_pairs)
    'kv_pairs' is a possibly empty list of keys and values.
    'data' is a list of ID key value pairs or NIL.
    NB: a single argument is assumed to be correctly formatted and is passed through unchanged
    (for backward compatibility with earlier version).
    Exchange information for problem analysis and determination.
    The ID extension is defined in RFC 2971. """

    name = 'ID'

    if not kv_pairs:
        data = 'NIL'
    elif len(kv_pairs) == 1:
        data = kv_pairs[0]     # Assume invoker passing correctly formatted string (back-compat)
    else:
        data = '(%s)' % ' '.join([(arg and self._quote(arg) or 'NIL') for arg in kv_pairs])

    return self._simple_command(name, data, **kw)

imaplib.IMAP4.id = imap_id_rfc2971
###
# Monkey-patch imaplib to support the ID command (RFC 2971) - end
###

try:
  import ssl
  SSLError = ssl.SSLError
except:
  ssl = None
  SSLError = Exception
import hashlib

__all__ = [
    'IMAPinitMixIn',
    'IMAPRetrieverBase',
    'IMAPSSLinitMixIn',
    'MultidropIMAPRetrieverBase',
    'MultidropPOP3RetrieverBase',
    'POP3_SSL_PORT',
    'POP3initMixIn',
    'POP3RetrieverBase',
    'POP3SSLinitMixIn',
    'RetrieverSkeleton',
]

tocode = lambda x: isinstance(x,bytes) and x or x.encode()

# If we have an ssl module:
has_sni = ssl and getattr(ssl, 'HAS_SNI', False)

proto_best = ssl and getattr(ssl, 'PROTOCOL_TLS', None)
if not proto_best:
    proto_best = ssl and getattr(ssl, 'PROTOCOL_SSLv23', None)

has_ciphers = sys.hexversion >= 0x2070000

# Monkey-patch SNI use into SSL.wrap_socket() if supported
def wrap_socket(sock, keyfile=None, certfile=None,
                server_side=False, cert_reqs=ssl.CERT_NONE,
                ssl_version=proto_best, ca_certs=None,
                do_handshake_on_connect=True,
                suppress_ragged_eofs=True,
                ciphers=None, server_hostname=None):
    if server_side and not certfile:
        raise ValueError("certfile must be specified for server-side "
                         "operations")
    if keyfile and not certfile:
        raise ValueError("certfile must be specified")
    context = ssl.SSLContext(ssl_version)
    context.verify_mode = cert_reqs
    if ca_certs:
        context.load_verify_locations(ca_certs)
    if certfile:
        context.load_cert_chain(certfile, keyfile)
    if ciphers:
        context.set_ciphers(ciphers)
    return context.wrap_socket(
        sock=sock, server_side=server_side,
        do_handshake_on_connect=do_handshake_on_connect,
        suppress_ragged_eofs=suppress_ragged_eofs,
        server_hostname=has_sni and server_hostname or None
    )
if ssl:
    ssl.wrap_socket = wrap_socket

##############################################
# to avoid deprecation warnings
# match_hostname from Python 3.10 ssl.py
# starting here down to ssl_match_hostname_END
##############################################

def _dnsname_match(dn, hostname):
    """Matching according to RFC 6125, section 6.4.3

    - Hostnames are compared lower case.
    - For IDNA, both dn and hostname must be encoded as IDN A-label (ACE).
    - Partial wildcards like 'www*.example.org', multiple wildcards, sole
      wildcard or wildcards in labels other then the left-most label are not
      supported and a CertificateError is raised.
    - A wildcard must match at least one character.
    """
    if not dn:
        return False

    wildcards = dn.count('*')
    # speed up common case w/o wildcards
    if not wildcards:
        return dn.lower() == hostname.lower()

    if wildcards > 1:
        raise CertificateError(
            "too many wildcards in certificate DNS name: {!r}.".format(dn))

    dn_leftmost, sep, dn_remainder = dn.partition('.')

    if '*' in dn_remainder:
        # Only match wildcard in leftmost segment.
        raise CertificateError(
            "wildcard can only be present in the leftmost label: "
            "{!r}.".format(dn))

    if not sep:
        # no right side
        raise CertificateError(
            "sole wildcard without additional labels are not support: "
            "{!r}.".format(dn))

    if dn_leftmost != '*':
        # no partial wildcard matching
        raise CertificateError(
            "partial wildcards in leftmost label are not supported: "
            "{!r}.".format(dn))

    hostname_leftmost, sep, hostname_remainder = hostname.partition('.')
    if not hostname_leftmost or not sep:
        # wildcard must match at least one char
        return False
    return dn_remainder.lower() == hostname_remainder.lower()


def _inet_paton(ipname):
    """Try to convert an IP address to packed binary form

    Supports IPv4 addresses on all platforms and IPv6 on platforms with IPv6
    support.
    """
    # inet_aton() also accepts strings like '1', '127.1', some also trailing
    # data like '127.0.0.1 whatever'.
    try:
        addr = _socket.inet_aton(ipname)
    except OSError:
        # not an IPv4 address
        pass
    else:
        if _socket.inet_ntoa(addr) == ipname:
            # only accept injective ipnames
            return addr
        else:
            # refuse for short IPv4 notation and additional trailing data
            raise ValueError(
                "{!r} is not a quad-dotted IPv4 address.".format(ipname)
            )

    try:
        return _socket.inet_pton(_socket.AF_INET6, ipname)
    except OSError:
        raise ValueError("{!r} is neither an IPv4 nor an IP6 "
                         "address.".format(ipname))
    except AttributeError:
        # AF_INET6 not available
        pass

    raise ValueError("{!r} is not an IPv4 address.".format(ipname))


def _ipaddress_match(cert_ipaddress, host_ip):
    """Exact matching of IP addresses.

    RFC 6125 explicitly doesn't define an algorithm for this
    (section 1.7.2 - "Out of Scope").
    """
    # OpenSSL may add a trailing newline to a subjectAltName's IP address,
    # commonly with IPv6 addresses. Strip off trailing \n.
    ip = _inet_paton(cert_ipaddress.rstrip())
    return ip == host_ip


def match_hostname(cert, hostname):
    """Verify that *cert* (in decoded format as returned by
    SSLSocket.getpeercert()) matches the *hostname*.  RFC 2818 and RFC 6125
    rules are followed.

    The function matches IP addresses rather than dNSNames if hostname is a
    valid ipaddress string. IPv4 addresses are supported on all platforms.
    IPv6 addresses are supported on platforms with IPv6 support (AF_INET6
    and inet_pton).

    CertificateError is raised on failure. On success, the function
    returns nothing.
    """
    # warnings.warn(
    #     "ssl.match_hostname() is deprecated",
    #     category=DeprecationWarning,
    #     stacklevel=2
    # )
    if not cert:
        raise ValueError("empty or no certificate, match_hostname needs a "
                         "SSL socket or SSL context with either "
                         "CERT_OPTIONAL or CERT_REQUIRED")
    try:
        host_ip = _inet_paton(hostname)
    except ValueError:
        # Not an IP address (common case)
        host_ip = None
    dnsnames = []
    san = cert.get('subjectAltName', ())
    for key, value in san:
        if key == 'DNS':
            if host_ip is None and _dnsname_match(value, hostname):
                return
            dnsnames.append(value)
        elif key == 'IP Address':
            if host_ip is not None and _ipaddress_match(value, host_ip):
                return
            dnsnames.append(value)
    if not dnsnames:
        # The subject is only checked when there is no dNSName entry
        # in subjectAltName
        for sub in cert.get('subject', ()):
            for key, value in sub:
                # XXX according to RFC 2818, the most specific Common Name
                # must be used.
                if key == 'commonName':
                    if _dnsname_match(value, hostname):
                        return
                    dnsnames.append(value)
    if len(dnsnames) > 1:
        raise CertificateError("hostname %r "
            "doesn't match either of %s"
            % (hostname, ', '.join(map(repr, dnsnames))))
    elif len(dnsnames) == 1:
        raise CertificateError("hostname %r "
            "doesn't match %r"
            % (hostname, dnsnames[0]))
    else:
        raise CertificateError("no appropriate commonName or "
            "subjectAltName fields were found")

def ssl_match_hostname(cert, hostname):
    try:
        return match_hostname(cert, hostname)
    except (ValueError, CertificateError) as e:
        raise getmailOperationError("%s"%e)

##############################################
# match_hostname from Python 3.10 ssl.py
# ssl_match_hostname_END
##############################################

from getmailcore.exceptions import *
from getmailcore.constants import *
from getmailcore.message import *
from getmailcore.utilities import *
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
def mailbox_names(resplist):
    mailboxes = []
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
        mailboxes.append(g['mailbox'])
    return mailboxes
IMAP_ATOM_SPECIAL=re.compile(r'[\x00-\x1F\(\)\{ %\*"\\\]]')

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

#######################################
class CertMixIn(object):
    def ssl_cipher_hash(self):
        if sys.version_info.major == 2:
            sslobj = self.conn.sslobj
        else:
            sslobj = self.conn.sock
        self.setup_received(sslobj)
        peercert = sslobj.getpeercert(True)
        ssl_cipher = sslobj.cipher()
        if ssl_cipher:
            ssl_cipher = '%s:%s:%s' % ssl_cipher
        if not peercert:
            actual_hash = None
        else:
            actual_hash = hashlib.sha256(peercert).hexdigest().lower()
        # Ensure cert is for server we're connecting to
        if ssl and self.conf['ca_certs']:
            ssl_match_hostname(
                sslobj.getpeercert(),
                self.conf.get('ssl_cert_hostname', None)
                    or self.conf['server']
            )
        ssl_fingerprints = check_ssl_fingerprints(self.conf)
        if ssl_fingerprints:
            any_matches = False
            for expected_hash in ssl_fingerprints:
                if expected_hash == actual_hash:
                    any_matches = True
            if not any_matches:
                raise getmailOperationError(
                    'socket ssl_fingerprints mismatch (got %s)'
                    % actual_hash
                )
        return ssl_cipher, actual_hash


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
        except poplib.error_proto as o:
            raise getmailOperationError('POP error (%s)' % o)
        except socket.timeout:
            raise
            #raise getmailOperationError('timeout during connect')
        except socket.gaierror as o:
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
            except socket.error as e:
                msg = e
                if self.sock:
                    self.sock.close()
                self.sock = None
                continue
            break
        if not self.sock:
            if isinstance(msg, Exception):
              raise msg
            else:
              raise socket.error(msg)
        extra_args = { 'server_hostname': host }
        if self.ssl_version:
            extra_args['ssl_version'] = self.ssl_version
        if self.ca_certs:
            extra_args['cert_reqs'] = ssl and ssl.CERT_REQUIRED
            extra_args['ca_certs'] = self.ca_certs
        if self.ssl_ciphers:
            extra_args['ciphers'] = self.ssl_ciphers

        if ssl:
            self.sock = ssl.wrap_socket(self.sock, self.keyfile,
                                        self.certfile, **extra_args)

        self.file = self.sock.makefile('rb')
        self._debugging = 0
        self.welcome = self._getresp()


#######################################
class POP3SSLinitMixIn(CertMixIn):
    '''Mix-In class to do POP3 over SSL with the poplib.POP3_SSL class.
    '''
    SSL = True
    def _connect(self):
        self.log.trace()
        (keyfile, certfile) = check_ssl_key_and_cert(self.conf)
        ca_certs = check_ca_certs(self.conf)
        ssl_version = check_ssl_version(self.conf)
        ssl_ciphers = check_ssl_ciphers(self.conf)
        using_extended_certs_interface = False
        try:
            if ca_certs or ssl_version or ssl_ciphers:
                using_extended_certs_interface = True
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
            ssl_cipher, actual_hash = self.ssl_cipher_hash()
        except poplib.error_proto as o:
            raise getmailOperationError('POP error (%s)' % o)
        except socket.timeout:
            #raise getmailOperationError('timeout during connect')
            raise
        except socket.gaierror as o:
            raise getmailOperationError(
                'error resolving name %s during connect (%s)'
                % (self.conf['server'], o)
            )

        fingerprint_message = ('POP3 SSL connection %s established'
                               % self.conn)
        fingerprint_message += ' with fingerprint %s' % actual_hash
        fingerprint_message += ' using cipher %s' % ssl_cipher
        fingerprint_message += os.linesep

        if self.app_options.get('fingerprint', False):
            self.log.info(fingerprint_message)
        else:
            self.log.trace(fingerprint_message)


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
        except imaplib.IMAP4.error as o:
            raise getmailOperationError('IMAP error (%s)' % o)
        except socket.timeout:
            #raise getmailOperationError('timeout during connect')
            raise
        except socket.gaierror as o:
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
       self.keyfile = keyfile
       self.certfile = certfile
       try:
           imaplib.IMAP4_SSL.__init__(self, host, port, keyfile, certfile)
       except TypeError:
           imaplib.IMAP4_SSL.__init__(self, host, port)


    def open(self, host='', port=imaplib.IMAP4_SSL_PORT, timeout=None):
       self.host = host
       self.port = port
       self.sock = socket.create_connection((host, port))

       # Note timeout is available in python 3.9 in native imaplib's/ssl's open,
       # but wrap_socket does not support it.  Keep it for the future.
       self.timeout = timeout

       extra_args = { 'server_hostname': host }
       if self.ssl_version:
           extra_args['ssl_version'] = self.ssl_version
       if self.ca_certs:
           extra_args['cert_reqs'] = ssl and ssl.CERT_REQUIRED
           extra_args['ca_certs'] = self.ca_certs
       if self.ssl_ciphers:
           extra_args['ciphers'] = self.ssl_ciphers

       if ssl:
           self.sock = ssl.wrap_socket(self.sock, self.keyfile, self.certfile,
                                     **extra_args)

       self.file = self.sock.makefile('rb')


#######################################
class IMAPSSLinitMixIn(CertMixIn):
    '''Mix-In class to do IMAP over SSL.
    '''
    SSL = True
    def _connect(self):
        self.log.trace()
        (keyfile, certfile) = check_ssl_key_and_cert(self.conf)
        ca_certs = check_ca_certs(self.conf)
        ssl_version = check_ssl_version(self.conf)
        ssl_ciphers = check_ssl_ciphers(self.conf)
        using_extended_certs_interface = False
        try:
            if ca_certs or ssl_version or ssl_ciphers:
                using_extended_certs_interface = True
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
                self.conn = IMAP4_SSL_EXTENDED(
                    self.conf['server'], self.conf['port'], keyfile, certfile
                )
            else:
                self.log.trace(
                    'establishing IMAP SSL connection to %s:%d'
                    % (self.conf['server'], self.conf['port']) + os.linesep
                )
                self.conn = imaplib.IMAP4_SSL(self.conf['server'],
                                              self.conf['port'])
            ssl_cipher, actual_hash = self.ssl_cipher_hash()
        except imaplib.IMAP4.error as o:
            raise getmailOperationError('IMAP error (%s)' % o)
        except socket.timeout:
            #raise getmailOperationError('timeout during connect')
            raise
        except socket.gaierror as o:
            try:
                errcode = o[0]
            except TypeError:
                errcode = o.args[0]
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
        except SSLError as o:
            raise getmailOperationError(
                (ssl and 'SSLError' or 'Error')+' during connect (%s)' % o
            )

        fingerprint_message = ('IMAP SSL connection %s established'
                               % self.conn)
        fingerprint_message += ' with fingerprint %s' % actual_hash
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

      _getmsglist(self) - retrieve a list of all available messages, and store
                          unique message identifiers in the dict
                          self.msgnum_by_msgid.
                          Message identifiers must be unique and persistent
                          across instantiations.  Also store message sizes (in
                          octets) in a dictionary self.msgsizes, using the
                          message identifiers as keys.

      _flagmsgbyid(self, msgid) - On default flag message msgid for deletion.
                                  For IMAP imap_on_delete allows other flag:
                                  return True if `Deleted` is among the flags.

      _getmsgbyid(self, msgid) - retrieve and return a message from the message
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
        self.supports_id = False
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
            self.log.warning('unexpected peer address format %s' % str(serveraddr))
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
                or (isinstance(mailbox, (unicode, bytes)))), (
            'bad mailbox %s (%s)' % (mailbox, type(mailbox))
        )
        filename = self.oldmail_filename
        if mailbox is not None:
            mailbox = re.sub(STRIP_CHAR_RE, '.', mailbox)
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
            f = open(filename)
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
        f.close()
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
                self.oldmail[msgid] = t
                wrote += 1
            oldmailfile.close()
            self.log.moreinfo('wrote %i uids for %s%s'
                              % (wrote, logname, os.linesep))
        except IOError as o:
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
        if self.app_options.get('to_oldmail_on_each_mail',False):
            self.write_oldmailfile(self.mailbox_selected)
            self.__delivered = {}

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
        deleted = self._flagmsgbyid(msgid)
        self.deleted[msgid] = deleted
        return deleted

    def run_password_command(self):
        command = self.conf['password_command'][0]
        args = self.conf['password_command'][1:]
        rc, stdout, stderr = run_command(command,args)
        if rc:
            raise getmailOperationError(
                'External program error (%s exited with %d)' % (command,rc)
            )
        if stderr:
            self.log.warning(
                'External password program "%s" wrote to stderr: %s'
                % (command, stderr)
            )
        password = stdout
        self.conf['password'] = password
        return password




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
                    (msgnum, msgid) = tostr(line).split(None, 1)
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
                           % list(sorted(self.msgnum_by_msgid.keys())) + os.linesep)
            self.sorted_msgnum_msgid = sorted(self.msgid_by_msgnum.items())
            (response, msglist, octets) = self.conn.list()
            for line in msglist:
                tostrline = tostr(line)
                msgnum = int(tostrline.split()[0])
                msgsize = int(tostrline.split()[1])
                msgid = self.msgid_by_msgnum.get(msgnum, None)
                # If no msgid found, it's a message that wasn't in the UIDL
                # response above.  Ignore it and we'll get it next time.
                if msgid is not None:
                    self.msgsizes[msgid] = msgsize

            # Remove messages from state file that are no longer in mailbox,
            # but only if the timestamp for them are old (30 days for now).
            # This is because IMAP users can have one state file but multiple
            # IMAP folders in different configuration rc files.
            for msgid in list(self.oldmail.keys()):
                timestamp = self.oldmail[msgid]
                age = self.timestamp - timestamp
                if msgid not in self.msgsizes and age > VANISHED_AGE:
                    self.log.debug('removing vanished old message id %s' % msgid
                                   + os.linesep)
                    del self.oldmail[msgid]

        except poplib.error_proto as o:
            raise getmailOperationError(
                'POP error (%s) - if your server does not support the UIDL '
                'command, use BrokenUIDLPOP3Retriever instead'
                 % o
            )
        self.gotmsglist = True

    def _flagmsgbyid(self, msgid):
        self.log.trace()
        msgnum = self._getmsgnumbyid(msgid)
        self.conn.dele(msgnum)
        return True

    def _getmsgbyid(self, msgid):
        self.log.debug('msgid %s' % msgid + os.linesep)
        msgnum = self._getmsgnumbyid(msgid)
        self.log.debug('msgnum %i' % msgnum + os.linesep)
        try:
            response, lines, octets = self.conn.retr(msgnum)
            self.log.debug('RETR response "%s", %d octets'
                           % (response, octets) + os.linesep)
            msg = Message(fromlines=lines+[b''])
            return msg
        except poplib.error_proto as o:
            raise getmailRetrievalError(
                'failed to retrieve msgid %s; server said %s'
                % (msgid, o)
            )

    def _getheaderbyid(self, msgid):
        self.log.trace()
        msgnum = self._getmsgnumbyid(msgid)
        response, headerlist, octets = self.conn.top(msgnum, 0)
        try:
            parser = Parser.BytesHeaderParser()
            return parser.parsebytes(os.linesep.encode().join(headerlist))
        except: #py2
            parser = Parser.HeaderParser()
            return parser.parsestr(os.linesep.join(headerlist))

    def initialize(self, options):
        self.log.trace()
        # POP doesn't support different mailboxes
        self.mailboxes = (None, )
        # Handle password
        if self.conf.get('password', None) is None:
            if self.conf.get('password_command', None):
                # Retrieve from an arbitrary external command
                self.run_password_command()
            else:
                self.conf['password'] = get_password(
                    self, self.conf['username'], self.conf['server'],
                    self.received_with, self.log
                )
        RetrieverSkeleton.initialize(self, options)
        try:
            self._connect()

            if self.conf['use_apop']:
                self.conn.apop(self.conf['username'],
                               self.conf['password'])
            elif self.conf['use_xoauth2']:
                # octal 1 / ctrl-A used as separator
                auth = 'user=%s\1auth=Bearer %s\1\1' % (self.conf['username'],
                                                        self.conf['password'])
                auth = base64.b64encode(auth.encode()).decode()
                self.conn._shortcmd('AUTH XOAUTH2 %s' % auth)
            else:
                self.conn.user(self.conf['username'])
                self.conn.pass_(self.conf['password'])
            self._getmsglist()
            self.log.debug('msgids: %s'
                           % list(sorted(self.msgnum_by_msgid.keys())) + os.linesep)
            self.log.debug('msgsizes: %s' % self.msgsizes + os.linesep)
            # Remove messages from state file that are no longer in mailbox
            for msgid in list(self.oldmail.keys()):
                if msgid not in self.msgsizes:
                    self.log.debug('removing vanished message id %s' % msgid
                                   + os.linesep)
                    del self.oldmail[msgid]
        except poplib.error_proto as o:
            raise getmailOperationError('POP error (%s)' % o)

    def abort(self):
        self.log.trace()
        RetrieverSkeleton.abort(self)
        if not self.conn:
            return
        try:
            self.conn.rset()
            self.conn.quit()
        except (poplib.error_proto, socket.error) as o:
            pass
        self.conn = None

    def quit(self):
        RetrieverSkeleton.quit(self)
        self.log.trace()
        if not self.conn:
            return
        try:
            self.conn.quit()
        except (poplib.error_proto, socket.error) as o:
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
                % self.envrecipname
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
        except ValueError as o:
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
        except (KeyError, IndexError) as unused:
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
        self._mboxmaxuid = 1

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
        data = b''.join(codecs.encode(response,'base64').splitlines())
        if self.gss_step == GSS_STATE_STEP:
            if not self.gss_vc:
                (rc, self.gss_vc) = kerberos.authGSSClientInit(
                    'imap@%s' % self.conf['server']
                )
                response = kerberos.authGSSClientResponse(self.gss_vc)
            rc = kerberos.authGSSClientStep(self.gss_vc, data.decode('ascii'))
            if rc != kerberos.AUTH_GSS_CONTINUE:
               self.gss_step = GSS_STATE_WRAP
        elif self.gss_step == GSS_STATE_WRAP:
            rc = kerberos.authGSSClientUnwrap(self.gss_vc, data.decode('ascii'))
            response = kerberos.authGSSClientResponse(self.gss_vc)
            rc = kerberos.authGSSClientWrap(self.gss_vc, response,
                                            self.conf['username'])
        response = kerberos.authGSSClientResponse(self.gss_vc)
        if not response:
            response = ''
        return codecs.decode(response.encode('ascii'),'base64')

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
        except imaplib.IMAP4.error as o:
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
                % (cmd, resplist) # don't print password: % ('%s %s' % (cmd, args), resplist)
                + os.linesep
            )

        return resplist

    def _parse_imapuidcmdresponse(self, cmd, *args):
        self.log.trace()
        try:
            result, resplist = self.conn.uid(cmd, *args)
        except imaplib.IMAP4.error as o:
            if cmd == 'login':
                # Percolate up
                raise
            else:
                raise getmailOperationError('IMAP error (%s)' % o)
        if result != 'OK':
            raise getmailOperationError(
                'IMAP error (command %s returned %s %s)'
                % (cmd, result, str(resplist)) # don't print password: % ('%s %s' % (cmd, args), result, resplist)
            )
        self.log.debug('command uid %s response %s'
                       % ('%s %s' % (cmd, str(args)),
                          str(resplist)) + os.linesep)
        return resplist

    def _parse_imapattrresponse(self, line):
        self.log.trace('parsing attributes response line %s' % line
                       + os.linesep)
        r = {}
        try:
            parts = line[line.index(b'(') + 1:line.rindex(b')')].split()
            while parts:
                # Flags starts a parenthetical list of valueless flags
                if parts[0].lower() == b'flags' and parts[1].startswith(b'('):
                    while parts and not parts[0].endswith(b')'):
                        del parts[0]
                    if parts:
                        # Last one, ends with ")"
                        del parts[0]
                    continue
                if len(parts) == 1:
                    # Leftover part -- not name, value pair.
                    raise ValueError
                name = parts.pop(0).lower()
                r[tostr(name)] = tostr(parts.pop(0))
        except (ValueError, IndexError, AttributeError) as o:
            raise getmailOperationError(
                'IMAP error (failed to parse attr response line "%s": %s)'
                % (line, o)
            )
        self.log.trace('got %s' % r + os.linesep)
        return r

    def id(self):
        server_id = self.conn.id('name', 'getmail', 'version', '6.0.0')
        return server_id

    def list_mailboxes(self):
        '''List (selectable) IMAP folders in account.'''
        cmd = ('LIST', )
        resplist = self._parse_imapcmdresponse(*cmd)
        return mailbox_names(
            codecs.decode(x,'imap4-utf-7')
            for x in resplist)

    def close_mailbox(self):
        # Close current mailbox so deleted mail is expunged.  One getmail
        # user had a buggy IMAP server that didn't do the automatic expunge,
        # so we do it explicitly here if we've deleted any messages.
        if any(self.deleted):
            self.conn.expunge()
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
        self._mboxmaxuid = 1
        self.conn.close()

    def _uidfile(self):
        filename = self.conf['uid_cache']
        getmaildir = self.conf['getmaildir']
        f = os.path.expanduser(filename)
        if not os.path.isabs(f) and getmaildir:
            f = os.path.join(getmaildir, f)
        return(f)

    def _uidvalidity(self):
        return self.uidvalidity.replace(" ","_")

    def _uidfindmax(self):
        self._mboxmaxuid = 1
        self._mboxmaxuid_changed = False
        if (not self.conf['uid_cache']
            or not self.uidvalidity):
            return
        try:
            with open(self._uidfile()) as C:
                for line in C:
                    (mbox, oldvalidity, uid) = line.split(" ")
                    if mbox == self.mailbox:
                        if oldvalidity == self._uidvalidity():
                            self._mboxmaxuid = int(uid)
                        return
        except ValueError:
            return
        except FileNotFoundError:
            return

    def _uidsavemax(self):
        if (not self.conf['uid_cache']
            or not self._mboxmaxuid_changed
            or not self.uidvalidity):
            return
        uidcache = {}
        try:
            with open(self._uidfile()) as C:
                for line in C:
                    (mbox, oldvalidity, uid) = line.split(" ")
                    uidcache[mbox] = line
        except FileNotFoundError:
            pass
        uidcache[self.mailbox] = " ".join((self.mailbox, self._uidvalidity(), str(self._mboxmaxuid)))+"\n"
        with open(self._uidfile(),"w") as C:
            for line in uidcache.values():
                print(line, file=C, end="")

    def _uidoldest(self):
        oldest = None
        response = self._parse_imapcmdresponse('FETCH','1','(UID)')
        for line in response:
            if not line:
                continue
            r = self._parse_imapattrresponse(line)
            if 'uid' not in r:
                continue
            uid = r['uid'].replace('/', '-')
            msgid = '%s/%s' % (self.uidvalidity, uid)
            oldest = msgid
        return oldest

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
            if (len(mailbox) < 2 or (
                mailbox[0],mailbox[-1]) != ('"','"')
                ) and IMAP_ATOM_SPECIAL.search(mailbox):
                (status, count) = self.conn.select(
                    codecs.encode(
                        self.conn._quote(mailbox),
                        'imap4-utf-7'),
                    read_only)
            else:
                (status, count) = self.conn.select(
                    codecs.encode(
                        mailbox,
                        'imap4-utf-7'),
                    read_only)
            if status == 'NO':
                # Specified mailbox doesn't exist, no permissions, etc.
                raise getmailMailboxSelectError(mailbox)

            self.mailbox_selected = mailbox
            # use *last* EXISTS returned
            count = int(count[-1])
            uidvalidity = tostr(self.conn.response('UIDVALIDITY')[1][0] or b"") or None
        except imaplib.IMAP4.error as o:
            raise getmailOperationError('IMAP error (%s)' % o)
        except (IndexError, ValueError) as o:
            raise getmailOperationError(
                'IMAP server failed to return correct SELECT response (%s)'
                % o
            )
        self.log.debug('select(%s) returned message count of %d'
                       % (mailbox, count) + os.linesep)
        self.mailbox = mailbox
        self.uidvalidity = uidvalidity
        self._uidfindmax()

        imap_search = self.conf['imap_search']
        if imap_search:
            result, data = self.conn.search(None, imap_search)
            data = [d for d in data if d is not None]
            if result == 'OK' and data:
                msgs = b','.join(data[0].split())
                if sys.version_info.major > 2:
                    msgs = msgs.decode()
                self._getmsglist(msgs)
        else:
            self._getmsglist(count, start=self._mboxmaxuid)

        self._uidsavemax()

        return count

    def _remove_from_oldmail(self, oldest):
        # Remove messages from the oldmail state file that are no longer in mailbox,
        # but only if the timestamp for them are old (30 days for now).
        # This is because IMAP users can have one oldmail state file but multiple
        # IMAP folders in different configuration rc files.
        if oldest:
            (ov,ou) = oldest.split('/')
        for msgid in list(self.oldmail):
            timestamp = self.oldmail[msgid]
            age = self.timestamp - timestamp
            if msgid not in self.msgsizes and age > VANISHED_AGE:
                # Don't delete oldmails that might still be around
                # if we are only doing partial reads of the mailbox
                if oldest:
                    (mv,mu) = msgid.split('/')
                    if (ov == mv and ou < mu):
                        continue
                self.log.debug('removing vanished old message id %s' % msgid
                                + os.linesep)
                del self.oldmail[msgid]


    def _getmsglist(self, msgcount, start=1):
        self.log.trace()
        oldest = None
        try:
            if msgcount:
                # Get UIDs and sizes for all messages in mailbox
                if start > 1:
                    fetchcmd=['UID', 'FETCH']
                    fetchcmd.append("%d:*"%start)
                else:
                    fetchcmd=['FETCH']
                    fetchcmd.append(isinstance(msgcount,str) and msgcount or '1:%d'%(msgcount))
                fetchcmd.append(('(UID)' if self.app_options['skip_imap_fetch_size'] else
                                 '(UID RFC822.SIZE)'))
                response = self._parse_imapcmdresponse(*fetchcmd)
                for line in response:
                    if not line:
                        # One user had a server that returned a null response
                        # somehow -- try to just skip.
                        continue
                    r = self._parse_imapattrresponse(line)


                    # RFC 3501, 6.1.2 states:
                    # Since any command can return a status update as untagged data, the
                    # NOOP command can be used as a periodic poll for new messages or
                    # message status updates during a period of inactivity (this is the
                    # preferred method to do this).
                    #
                    # This means also a FETCH command can contain a status update.
                    # ProtonMail Bridge does so, a session can look like:
                    #
                    # a LOGIN me@domain password
                    # ...
                    # a SELECT INBOX
                    # ...
                    # a FETCH 1:50000 (UID RFC822.SIZE)
                    # * 1 FETCH (UID 1 RFC822.SIZE 8938)
                    # ...
                    # * 49999 FETCH (UID 50001 RFC822.SIZE 15500)
                    # * 50000 FETCH (UID 50002 RFC822.SIZE 9614)
                    # * 51868 FETCH (FLAGS (NonJunk) UID 51958)
                    # a OK FETCH completed
                    #
                    # While fetching, UID 51958 saw an update and gained new flags.
                    # So we need to check whether FETCH response lines contain the
                    # requested items.
                    if 'uid' not in r:
                        continue

                    if (not self.app_options['skip_imap_fetch_size']) and ('rfc822.size' not in r):
                        continue

                    # Don't allow / in UIDs we store, as we look for that to
                    # detect old-style oldmail files.  Can occur with IMAP, at
                    # least with some servers.
                    uid = r['uid'].replace('/', '-')

                    try:
                        nuid = int(uid)
                        if nuid > self._mboxmaxuid:
                            self._mboxmaxuid = nuid
                            self._mboxmaxuid_changed = True
                    except ValueError:
                        # Presumably non-numeric UID, which should be illegal but according to comment above it can happen
                        pass

                    msgid = '%s/%s' % (self.uidvalidity, uid)
                    self._mboxuids[msgid] = r['uid']
                    self._mboxuidorder.append(msgid)
                    self.msgnum_by_msgid[msgid] = None
                    self.msgsizes[msgid] = (0 if
                        self.app_options['skip_imap_fetch_size']
                                        else int(r['rfc822.size']))
                if start > 1:
                    oldest = self._uidoldest()
            self._remove_from_oldmail(oldest)
        except imaplib.IMAP4.error as o:
            raise getmailOperationError('IMAP error (%s)' % o)
        self.gotmsglist = True

    def __getitem__(self, i):
        return self._mboxuidorder[i]

    def _flagmsgbyid(self, msgid):
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

            # On GMail you need to remove LABELS before deleting
            if 'X-GM-EXT-1' in self.conn.capabilities:
                self._parse_imapuidcmdresponse('STORE', uid,'X-GM-LABELS', '()')

            flag = self.conf.get('imap_on_delete',None) or r'(\Deleted \Seen)'
            response = self._parse_imapuidcmdresponse(
                'STORE', uid, 'FLAGS', flag
            )
            return 'Deleted' in flag
        except imaplib.IMAP4.error as o:
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
            except (imaplib.IMAP4.error, getmailOperationError) as o:
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
                except Exception as o:
                    sbody = None
                if not sbody:
                    raise getmailRetrievalError('bad message from server!')
                msg = Message(fromstring=sbody)
            except TypeError as o:
                # response[0] is None instead of a message tuple
                raise getmailRetrievalError('failed to retrieve msgid %s'
                                            % msgid)

            # record mailbox retrieved from in a header
            if self.conf['record_mailbox']:
                msg.add_header('X-getmail-retrieved-from-mailbox',
                               tocode(self.mailbox_selected))

            # google extensions: apply labels, etc
            if 'X-GM-EXT-1' in self.conn.capabilities:
                metadata = self._getgmailmetadata(uid, msg)
                for (header, value) in metadata.items():
                    msg.add_header(header, value)

            return msg

        except imaplib.IMAP4.error as o:
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
        except imaplib.IMAP4.error as o:
            self.log.warning('Could not fetch google imap extensions: %s' % o)
            return {}

        if not response or not response[0]:
            return {}

        ext = re.search(
            b'X-GM-THRID (?P<THRID>\\d+) X-GM-MSGID (?P<MSGID>\\d+)'
            b' X-GM-LABELS \\((?P<LABELS>.*)\\) UID',
            response[0]
        )
        if not ext:
            self.log.warning(
                'Could not parse google imap extensions. Server said: %s'
                % repr(response))
            return {}


        results = ext.groupdict()
        metadata = {}
        for item in ('LABELS', 'THRID', 'MSGID'):
            if results.get(item):
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
        if ((self.conf.get('password', None) is None or self.conf['use_xoauth2'])
                and not (HAVE_KERBEROS_GSS and self.conf['use_kerberos'])):
            if self.conf['password_command']:
                # Retrieve from an arbitrary external command
                self.run_password_command()
            else:
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
                elif self.conf['use_xoauth2']:
                    # octal 1 / ctrl-A used as separator
                    auth = 'user=%s\1auth=Bearer %s\1\1' % (self.conf['username'],
                                                            self.conf['password'])
                    self.conn.authenticate('XOAUTH2', lambda unused: auth)
                else:
                    self._parse_imapcmdresponse('login', self.conf['username'],
                                                self.conf['password'])
            except imaplib.IMAP4.abort as o:
                raise getmailLoginRefusedError(o)
            except imaplib.IMAP4.error as o:
                if '[UNAVAILABLE]' in str(o):
                    raise getmailLoginRefusedError(o)
                else:
                    raise getmailCredentialError(o)

            self.log.trace('logged in' + os.linesep)
            # Some IMAP servers change the available capabilities after
            # authentication, i.e. they present a limited set before login.
            # The Python stlib IMAP4 class doesn't take this into account
            # and just checks the capabilities immediately after connecting.
            # Force a re-check now that we've authenticated.
            (typ, dat) = self.conn.capability()
            if dat == [None]:
                # No response, don't update the stored capabilities
                self.log.warning('no post-login CAPABILITY response from server\n')
            else:
                self.conn.capabilities = tuple(tostr(dat[-1]).upper().split())

            if 'IDLE' in self.conn.capabilities:
                self.supports_idle = True
                imaplib.Commands['IDLE'] = ('AUTH', 'SELECTED')

            if 'ID' in self.conn.capabilities:
                self.supports_id = True

            if self.supports_id and self.conf['imap_id_extension']:
                self.id()

            if self.mailboxes == ('ALL', ):
                # Special value meaning all mailboxes in account
                self.mailboxes = tuple(self.list_mailboxes())

        except imaplib.IMAP4.error as o:
            raise getmailOperationError('IMAP error (%s)' % o)

    def abort(self):
        self.log.trace()
        RetrieverSkeleton.abort(self)
        if not self.conn:
            return
        try:
            self.quit()
        except (imaplib.IMAP4.error, socket.error) as o:
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
            (readable, unused, _) = select.select([self.conn.sock], [], [], timeout)
        except KeyboardInterrupt as o:
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
            self.conn.send(b'DONE\r\n')
            self.conn._command_complete('IDLE', tag)
        except imaplib.IMAP4.error as o:
            return False
        except BrokenPipeError as o:
            # The underlying connection closed during IDLE
            self.log.info('BrokenPipeError after IDLE\n')
            return False
        except TimeoutError as o:
            self.log.info('TimeoutError after IDLE\n')
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
        except imaplib.IMAP4.error as o:
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
                % self.envrecipname
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
        except ValueError as o:
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
        except (KeyError, IndexError) as unused:
            raise getmailConfigurationError(
                'envelope_recipient specified header missing (%s)'
                % self.conf['envelope_recipient']
            )
        msg.recipient = address_no_brackets(line.strip())
        return msg
