#!/usr/bin/env python2.3
'''Provide an SSL-capable POP3 class.

'''

__all__ = [
    'POP3_ssl_port',
    'sslsocket',
    'POP3SSL',
]

import socket
from poplib import POP3, CR, LF, CRLF, error_proto

from getmailcore.exceptions import *
import getmailcore.logging
log = getmailcore.logging.Logger()

POP3_ssl_port = 995

class sslsocket(object):
    '''The Python poplib.POP3() class mixes socket-like .sendall() and
    file-like .readline() for communications.  That would be okay, except that
    the new socket.ssl objects provide only read() and write(), so they
    don't act like a socket /or/ like a file.  Argh.

    This class takes a standard, connected socket.socket() object, sets it
    to blocking mode (required for socket.ssl() to work correctly, though
    apparently not documented), wraps .write() for .sendall() and implements
    .readline().

    The modified POP3 class below can then use this to provide POP3-over-SSL.

    Thanks to Frank Benkstein for the inspiration.
    '''
    def __init__(self, sock, keyfile=None, certfile=None):
        log.trace()
        self.sock = sock
        self.sock.setblocking(1)
        if keyfile and certfile:
            self.ssl = socket.ssl(self.sock, keyfile, certfile)
        else:
            self.ssl = socket.ssl(self.sock)
        self.buf = ''
        self.bufsize = 128

    def _fillbuf(self):
        '''Fill an internal buffer for .readline() to use.
        '''
        log.trace()
        want = self.bufsize - len(self.buf)
        log.trace('want %i bytes\n' % want)
        if want <= 0:
            return
        s = self.ssl.read(want)
        got = len(s)
        log.trace('got %i bytes\n' % got)
        self.buf += s

    def close(self):
        self.sock.close()
        self.ssl = None

    # self.sock.sendall
    def sendall(self, s):
        # Maybe only set blocking around this call?
        self.ssl.write(s)

    # self.file.readline
    def readline(self):
        '''Simple hack to implement .readline() on a non-file object that
        only supports .read().
        '''
        log.trace()
        line = ''
        try:
            if not self.buf:
                self._fillbuf()
            log.trace('checking self.buf\n')
            if self.buf:
                log.trace('self.buf = "%r", len %i\n'
                          % (self.buf, len(self.buf)))
                while True:
                    log.trace('looking for EOL\n')
                    i = self.buf.find('\n')
                    if i != -1:
                        log.trace('EOL found at %d\n' % i)
                        line += self.buf[:i + 1]
                        self.buf = self.buf[i + 1:]
                        break
                    # else
                    log.trace('EOL not found, trying to fill self.buf\n')
                    line += self.buf
                    self.buf = ''
                    self._fillbuf()
                    if not self.buf:
                        log.trace('nothing read, exiting\n')
                        break
                    log.trace('end of loop\n')
            log.trace('returning line "%r"\n' % line)
            return line
        except (socket.sslerror, socket.error), o:
            raise getmailOperationError(
                'socket/ssl error while reading from server (%s)' % o
            )

class POP3SSL(POP3):
    '''Thin subclass to add SSL functionality to the built-in POP3 class.
    Note that Python's socket module does not do certificate verification
    for SSL connections.

    This gets rid of the .file attribute from os.makefile(rawsock) and relies on
    sslsocket() above to provide .readline() instead.
    '''
    def __init__(self, host, port=POP3_ssl_port, keyfile=None, certfile=None):
        if not ((certfile and keyfile) or (keyfile == certfile == None)):
            raise getmailConfigurationError('certfile requires keyfile')
        self.host = host
        self.port = port
        msg = "getaddrinfo returns an empty list"
        self.rawsock = None
        self.sock = None
        for res in socket.getaddrinfo(self.host, self.port, 0,
                                      socket.SOCK_STREAM):
            (af, socktype, proto, canonname, sa) = res
            try:
                self.rawsock = socket.socket(af, socktype, proto)
                self.rawsock.connect(sa)
                if certfile and keyfile:
                    self.sock = sslsocket(self.rawsock, keyfile, certfile)
                else:
                    self.sock = sslsocket(self.rawsock)
            except socket.error, msg:
                if self.rawsock:
                    self.rawsock.close()
                self.rawsock = None
                continue
            break
        if not self.sock:
            raise socket.error, msg
        self._debugging = 0
        self.welcome = self._getresp()

    # Internal: return one line from the server, stripping CRLF.
    # This is where all the CPU time of this module is consumed.
    # Raise error_proto('-ERR EOF') if the connection is closed.
    def _getline(self):
        line = self.sock.readline()
        if self._debugging > 1:
            print '*get*', `line`
        if not line:
            raise error_proto('-ERR EOF')
        octets = len(line)
        # server can send any combination of CR & LF
        # however, 'readline()' returns lines ending in LF
        # so only possibilities are ...LF, ...CRLF, CR...LF
        if line[-2:] == CRLF:
            return line[:-2], octets
        if line[0] == CR:
            return line[1:-1], octets
        return line[:-1], octets

    def quit(self):
        """Signoff: commit changes on server, unlock mailbox, close connection.
        """
        try:
            resp = self._shortcmd('QUIT')
        except (error_proto, socket.error), val:
            resp = val
        self.sock.close()
        del self.sock
        return resp
