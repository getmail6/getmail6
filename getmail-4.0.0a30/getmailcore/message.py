#!/usr/bin/env python2.3
'''The getmail Message class.

'''

import os
import time
import cStringIO
import email
from email.Generator import Generator

from exceptions import *
from utilities import mbox_from_escape, format_header

#######################################
class Message(object):
    '''Message class for getmail.  Does sanity-checking on attribute accesses
    and provides some convenient interfaces to an underlying email.Message()
    object.
    '''
    __slots__ = (
        '__msg',
        #'log',
        'sender',
        'received_by',
        'received_from',
        'received_with',
        'recipient',
    )
    def __init__(self, fromlines=None, fromstring=None, fromfile=None):
        #self.log = logger()
        self.recipient = None
        self.received_by = None
        self.received_from = None
        self.received_with = None

        if fromlines:
            self.__msg = email.message_from_string(os.linesep.join(fromlines), strict=False)
        elif fromstring:
            self.__msg = email.message_from_string(fromstring, strict=False)
        elif fromfile:
            self.__msg = email.message_from_file(fromfile, strict=False)
        else:
            # Can't happen?
            raise SystemExit('Message() called with wrong arguments')

        self.sender = self.__msg['return-path'] or 'unknown'

    def content(self):
        return self.__msg

    def copyattrs(self, othermsg):
        for attr in ('sender', 'received_by', 'received_from', 'received_with', 'recipient'):
            setattr(self, attr, getattr(othermsg, attr))

    def flatten(self, delivered_to, received, mangle_from=False, include_from=False):
        '''Return a string with native EOL convention.
        
        The email module apparently doesn't always use native EOL, so we
        force it by writing out what we need, letting the generator write out the
        message, splitting it into lines, and joining them with the platform EOL.
        '''
        f = cStringIO.StringIO()
        if include_from:
            # This needs to be written out first, so we can't rely on the generator
            f.write('From %s %s' % (mbox_from_escape(self.sender), time.asctime()) + os.linesep)
        # Write the Return-Path: header
        f.write(format_header('Return-Path', self.sender))
        # Maybe remove previous Return-Path: header fields?
        if delivered_to:
            f.write(format_header('Delivered-To', self.recipient or 'unknown'))
        if received:
            content = 'from %s by %s with %s' % (self.received_from, self.received_by, self.received_with)
            if self.recipient is not None:
                content += ' for <%s>' % self.recipient
            content += '; ' + time.strftime('%d %b %Y %H:%M:%S -0000', time.gmtime())
            f.write(format_header('Received', content))
        gen = Generator(f, mangle_from, 0)
        # From_ handled above, always tell the generator not to include it
        gen.flatten(self.__msg, False)
        f.seek(0)
        return os.linesep.join(f.read().splitlines() + [''])

    def add_header(self, name, content):
        self.__msg[name] = content.rstrip()

    def headers(self):
        return self.__msg._headers
