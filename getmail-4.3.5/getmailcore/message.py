#!/usr/bin/env python2.3
'''The getmail Message class.

'''

__all__ = [
    'Message',
]

import os
import time
import cStringIO
import email
import email.Errors
import email.Utils
from email.Generator import Generator

from exceptions import *
from utilities import mbox_from_escape, format_header, address_no_brackets
import logging

message_attributes = (
    'sender',
    'received_by',
    'received_from',
    'received_with',
    'recipient'
)

#######################################
def corrupt_message(why, fromlines=None, fromstring=None):
    log = logging.logger()
    log.error('failed to parse retrieved message; constructing container for '
        'contents\n')
    if fromlines == fromstring == None:
        raise SystemExit('corrupt_message() called with wrong arguments')
    msg = email.message_from_string('')
    msg['From'] = '"unknown sender" <>'
    msg['Subject'] = 'Corrupt message received'
    msg['Date'] = email.Utils.formatdate(localtime=True)
    body = ['A badly-corrupt message was retrieved and could not be parsed',
        'for the following reason:',
        '',
        '    %s' % why,
        '',
        'Below the following line is the original message contents.',
        '',
        '--------------------------------------------------------------',
    ]
    if fromlines:
        body.extend([line.rstrip() for line in fromlines])
    elif fromstring:
        body.extend([line.rstrip() for line in fromstring.splitlines()])
    msg.set_payload(os.linesep.join(body))
    for attr in message_attributes:
        setattr(msg, attr, '')
    return msg

#######################################
class Message(object):
    '''Message class for getmail.  Does sanity-checking on attribute accesses
    and provides some convenient interfaces to an underlying email.Message()
    object.
    '''
    __slots__ = (
        '__msg',
        '__raw',
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
        self.__raw = None

        # Message is instantiated with fromlines for POP3, fromstring for
        # IMAP (both of which can be badly-corrupted or invalid, i.e. spam,
        # MS worms, etc).  It's instantiated with fromfile for the output
        # of filters, etc, which should be saner.
        if fromlines:
            try:
                self.__msg = email.message_from_string(os.linesep.join(
                    fromlines), strict=False)
            except email.Errors.MessageError, o:
                self.__msg = corrupt_message(o, fromlines=fromlines)
            self.__raw = os.linesep.join(fromlines)
        elif fromstring:
            try:
                self.__msg = email.message_from_string(fromstring, strict=False)
            except email.Errors.MessageError, o:
                self.__msg = corrupt_message(o, fromstring=fromstring)
            self.__raw = fromstring
        elif fromfile:
            try:
                self.__msg = email.message_from_file(fromfile, strict=False)
            except email.Errors.MessageError, o:
                # Shouldn't happen
                self.__msg = corrupt_message(o, fromstring=fromfile.read())
            # fromfile is only used by getmail_maildir, getmail_mbox, and
            # from reading the output of a filter.  Ignore __raw here.
        else:
            # Can't happen?
            raise SystemExit('Message() called with wrong arguments')

        self.sender = address_no_brackets(self.__msg['return-path']
            or 'unknown')

    def content(self):
        return self.__msg

    def copyattrs(self, othermsg):
        for attr in message_attributes:
            setattr(self, attr, getattr(othermsg, attr))

    def flatten(self, delivered_to, received, mangle_from=False,
            include_from=False):
        '''Return a string with native EOL convention.

        The email module apparently doesn't always use native EOL, so we force
        it by writing out what we need, letting the generator write out the
        message, splitting it into lines, and joining them with the platform
        EOL.
        '''
        f = cStringIO.StringIO()
        if include_from:
            # This needs to be written out first, so we can't rely on the
            # generator
            f.write('From %s %s' % (mbox_from_escape(self.sender),
                time.asctime()) + os.linesep)
        # Write the Return-Path: header
        f.write(format_header('Return-Path', '<%s>' % self.sender))
        # Remove previous Return-Path: header fields.
        del self.__msg['Return-Path']
        if delivered_to:
            f.write(format_header('Delivered-To', self.recipient or 'unknown'))
        if received:
            content = 'from %s by %s with %s' % (self.received_from,
                self.received_by, self.received_with)
            if self.recipient is not None:
                content += ' for <%s>' % self.recipient
            content += '; ' + time.strftime('%d %b %Y %H:%M:%S -0000',
                time.gmtime())
            f.write(format_header('Received', content))
        gen = Generator(f, mangle_from, 0)
        # From_ handled above, always tell the generator not to include it
        try:
            gen.flatten(self.__msg, False)
            f.seek(0)
            return os.linesep.join(f.read().splitlines() + [''])
        except TypeError, o:
            # email module chokes on some badly-misformatted messages, even
            # late during flatten().  Hope this is fixed in Python 2.4.
            if self.__raw == None:
                # Argh -- a filter took a correctly-formatted message
                # and returned a badly-misformatted one?
                raise getmailDeliveryError('failed to parse retrieved message '
                    'and could not recover (%s)' % o)
            self.__msg = corrupt_message(o, fromstring=self.__raw)
            return self.flatten(delivered_to, received, mangle_from, 
                include_from)

    def add_header(self, name, content):
        self.__msg[name] = content.rstrip()

    def headers(self):
        return self.__msg._headers

    def get_all(self, name, failobj=None):
        return self.__msg.get_all(name, failobj)
