import sys
import os.path
import poplib
import imaplib
import socket
import logging

from getmailcore.exceptions import *
import getmailcore.baseclasses

__all__ = [
    'SSL_CERTIFICATE_VALIDATION',
    'checkSslOptions',
    'Pop3Ssl',
    'Imap4Ssl',
]

try:
    import ssl
    HAVE_SSL_MODULE = True
    HAVE_SOCKET_SSL = None  # don't care

    class SSL_CERTIFICATE_VALIDATION(getmailcore.baseclasses.ConfigEnumeration):
        REQUIRED = ssl.CERT_REQUIRED
        OPTIONAL = ssl.CERT_OPTIONAL
        IGNORED = ssl.CERT_NONE

except ImportError, o:
    # Python 2.5 lacks the ssl module; Python 2.6 throws an ImportError as well
    # if Python is built without OpenSSL support.
    HAVE_SSL_MODULE = False
    try:
        # Python 2.5 may or may not have socket.ssl depending on how it's built
        socket.ssl
        HAVE_SOCKET_SSL = True
    except AttributeError, o:
        HAVE_SOCKET_SSL = False

    class SSL_CERTIFICATE_VALIDATION(getmailcore.baseclasses.ConfigEnumeration):
        REQUIRED = 0
        OPTIONAL = 1
        IGNORED = 2




log = logging.getLogger('')


def checkSslOptions(conf):
    """Check configuration of SSL-related options in a getmail config instance,
    possibly modifying it in-place.  Raises getmailConfigurationError if
    inconsistent or incorrect settings are detected.
    """
    keyfile = conf['keyfile']
    certfile = conf['certfile']
    if keyfile and not os.path.isfile(keyfile):
        raise getmailConfigurationError(
            'optional keyfile must be path to a valid file'
        )
    if certfile and not os.path.isfile(certfile):
        raise getmailConfigurationError(
            'optional certfile must be path to a valid file'
        )
    if keyfile and not certfile:
        raise getmailConfigurationError(
            'certfile must be specified when keyfile specified'
        )
    if not (HAVE_SSL_MODULE or HAVE_SOCKET_SSL):
        raise getmailConfigurationError(
            'This Python installation lacks all SSL support.  Use a non-SSL '
            'retriever class instead.'
        )
    certificateMode = conf['certificatemode'].lower()
    if not HAVE_SSL_MODULE:
        # Python 2.5 doesn't have SSL certificate validation support; Python 2.6
        # may not have it.
        if certificateMode != 'ignored':
            raise getmailConfigurationError(
                'This Python installation lacks the ssl module (available but '
                'optional in Python 2.6 and up) and therefore cannot perform '
                'SSL certificate validation.  certificateMode must be set to '
                '"ignored".  Note the security implications of not validating '
                'certificates before using this setting.'
            )
    if not SSL_CERTIFICATE_VALIDATION.valid(certificateMode):
        raise getmailConfigurationError(
            'certificateMode must be "required" (default), "optional", '
            'or "ignored"'
        )
    if certificateMode == 'ignored':
        conf['caCertificatesFile'] = None
    else:
        caCertificatesFile = conf['cacertificatesfile']
        if not caCertificatesFile:
            raise getmailConfigurationError(
                'caCertificatesFile required when certificateMode != "ignored"'
            )
        if not os.path.isfile(caCertificatesFile):
            raise getmailConfigurationError(
                'caCertificatesFile must be path to a valid file'
            )



class Pop3Ssl(poplib.POP3_SSL):
    def __init__(self, host, port=poplib.POP3_SSL_PORT, keyfile=None, 
                 certfile=None, caCertificatesFile=None,
                 certificateMode='required'):
        # Sanity checks
        assert type(host) == str and host
        assert type(port) == int and 1 <= port <= 65535
        assert keyfile is None or (type(keyfile) == str and keyfile)
        assert certfile is None or (type(certfile) == str and certfile)
        if keyfile:
            assert certfile
            assert os.path.isfile(keyfile)
        if certfile:
            assert os.path.isfile(certfile)
        assert caCertificatesFile is None or (type(caCertificatesFile) == str 
                                              and caCertificatesFile)
        assert certificateMode in ('required', 'optional', 'ignored')
        if certificateMode != 'ignored':
            assert caCertificatesFile
            assert os.path.isfile(caCertificatesFile)
        cert_reqs = SSL_CERTIFICATE_VALIDATION.fromstring(certificateMode)
        # Finally...
        self.host = host
        self.port = port
        self.keyfile = keyfile
        self.certfile = certfile
        self.certificateMode = certificateMode
        self.caCertificatesFile = caCertificatesFile
        self.buffer = ''
        msg = 'getaddrinfo returns an empty list'
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
        self.file = self.sock.makefile('rb')
        try:
            if HAVE_SSL_MODULE:
                self.sslobj = ssl.wrap_socket(
                    self.sock, self.keyfile, self.certfile, 
                    cert_reqs=cert_reqs, ca_certs=caCertificatesFile
                )
            elif HAVE_SOCKET_SSL:
                self.sslobj = socket.ssl(self.sock, self.keyfile, self.certfile)
            else:
                # Can't happen, already checked
                assert False, 'wtf'
        except ssl.SSLError, o:
            log.debug('SSL certificate validation error: %s', o)
            raise getmailcore.exceptions.getmailSSLError(
                'certificate validation for %s failed' % self.host
            )
        except socket.error, o:
            raise getmailcore.exceptions.getmailSSLError(
                'error establishing SSL connection to %s' % self.host
            )
        self._debugging = 0
        self.welcome = self._getresp()



class Imap4Ssl(imaplib.IMAP4_SSL):
    def __init__(self, host, port=imaplib.IMAP4_SSL_PORT, keyfile=None, 
                 certfile=None, caCertificatesFile=None,
                 certificateMode='required'):
        # Sanity checks
        assert type(host) == str and host
        assert type(port) == int and 1 <= port <= 65535
        assert keyfile is None or (type(keyfile) == str and keyfile)
        assert certfile is None or (type(certfile) == str and certfile)
        if keyfile:
            assert certfile
            assert os.path.isfile(keyfile)
        if certfile:
            assert os.path.isfile(certfile)
        assert caCertificatesFile is None or (type(caCertificatesFile) == str 
                                              and caCertificatesFile)
        assert certificateMode in ('required', 'optional', 'ignored')
        if certificateMode != SSL_CERTIFICATE_VALIDATION.IGNORED:
            assert caCertificatesFile
            assert os.path.isfile(caCertificatesFile)
        self.cert_reqs = SSL_CERTIFICATE_VALIDATION.fromstring(certificateMode)
        # Finally...
        self.host = host
        self.port = port
        self.keyfile = keyfile
        self.certfile = certfile
        self.certificateMode = certificateMode
        self.caCertificatesFile = caCertificatesFile
        imaplib.IMAP4.__init__(self, host, port) # :TODO: maybe IMAP4_SSL?

    #def open(self, host='', port=IMAP4_SSL_PORT):
    def open(self, *unused):
        """Setup connection to remote server based on host, port, and SSL
        arguments passed to the constructor.

        This connection will be used by the routines:
            read, readline, send, shutdown.
        """
        # stdlib implementation does this...
        #self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #self.sock.connect((self.host, self.port))
        # ... but we may as well do the full monty like poplib does above.
        msg = 'getaddrinfo returns an empty list'
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

        try:
            if HAVE_SSL_MODULE:
                self.sslobj = ssl.wrap_socket(
                    self.sock, self.keyfile, self.certfile, 
                    cert_reqs=self.cert_reqs, ca_certs=self.caCertificatesFile
                )
            elif HAVE_SOCKET_SSL:
                self.sslobj = socket.ssl(self.sock, self.keyfile, self.certfile)
            else:
                # Can't happen, already checked
                assert False, 'wtf'
        except ssl.SSLError, o:
            log.debug('SSL certificate validation error: %s', o)
            raise getmailcore.exceptions.getmailSSLError(
                'certificate validation for %s failed' % self.host
            )
        except socket.error, o:
            raise getmailcore.exceptions.getmailSSLError(
                'error establishing SSL connection to %s' % self.host
            )
