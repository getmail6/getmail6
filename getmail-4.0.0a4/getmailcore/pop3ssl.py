#!/usr/bin/env python2.3
'''Provide an SSL-capable POP3 class.

'''

import socket
from poplib import *

from exceptions import *

POP3_ssl_port = 995

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
                    self.sock = socket.ssl(self.rawsock, keyfile, certfile)
                else:
                    self.sock = socket.ssl(self.rawsock)
            except socket.error, msg:
                if self.rawsock:
                    self.rawsock.close()
                self.rawsock = None
                continue
            break
        if not self.sock:
            raise socket.error, msg
        self.file = self.sock.makefile('rb')
        self._debugging = 0
        self.welcome = self._getresp()
