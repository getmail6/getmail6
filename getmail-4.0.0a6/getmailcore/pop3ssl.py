#!/usr/bin/env python2.3
'''Provide an SSL-capable POP3 class.

'''

import socket
from poplib import *

from exceptions import *

POP3_ssl_port = 995

class pseudofile(object):
    '''Implement something with semantics like a Python file() object on top
    of something that supports at least read() and write().

    Warning:  don't intermix calls to readline() and read().  You could get
    data out of order.
    '''
    def __init__(self, f, sizehint=512):
        self.read = f.read
        self.write = f.write
        self.buf = ''
        self.bufsize = sizehint

    def fillbuf(self):
        want = self.bufsize - len(self.buf)
        if not want:
            return
        got = self.read(want)
        self.buf += got

    def readline(self):
        line = ''
        if not self.buf:
            self.fillbuf()
        if not self.buf:
            return ''
        while True:
            i = self.buf.find('\n')
            if i != -1:
                line += self.buf[:i + 1]
                self.buf = self.buf[i + 1:]
                return line
            if i == -1:
                line += self.buf
                self.buf = ''
                self.fillbuf()
                if not self.buf:
                    return line

class sslwrapper(object):
    def __init__(self, sock, keyfile=None, certfile=None):
        if keyfile and certfile:
            self.ssl = socket.ssl(sock, keyfile, certfile)
        else:
            self.ssl = socket.ssl(sock)
        self.write = self.ssl.write
        self.read = self.ssl.read
        self.recv = self.ssl.read
        self.send = self.ssl.write

    def sendall(self, s, flags=None):
        tosend = len(s)
        while tosend > 0:
            i = self.send(s)
            tosend -= i
            s = s[i:]

class POP3SSL(POP3):
    '''Thin subclass to add SSL functionality to the built-in POP3 class.
    Note that Python's socket module does not do certificate verification
    for SSL connections.
    '''
    def __init__(self, host, port=POP3_ssl_port, keyfile=None, certfile=None):
        if not ((certfile and keyfile) or (keyfile == certfile == None)):
            raise getmailConfigurationError('certfile requires keyfile')
        self.host = host
        self.port = port
        msg = "getaddrinfo returns an empty list"
        self.rawsock = None
        self.sock = None
        for res in socket.getaddrinfo(self.host, self.port, 0, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            try:
                self.rawsock = socket.socket(af, socktype, proto)
                self.rawsock.connect(sa)
                if certfile and keyfile:
                    self.sock = sslwrapper(self.rawsock, keyfile, certfile)
                else:
                    self.sock = sslwrapper(self.rawsock)
            except socket.error, msg:
                if self.rawsock:
                    self.rawsock.close()
                self.rawsock = None
                continue
            break
        if not self.sock:
            raise socket.error, msg
        #self.file = self.sock.makefile('rb')
        self.file = pseudofile(self.sock)
        self._debugging = 0
        self.welcome = self._getresp()
