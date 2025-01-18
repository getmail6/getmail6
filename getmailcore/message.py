# -*- coding: utf-8 -*-
# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

'''The getmail Message class.

'''

from __future__ import unicode_literals
import sys
import os
import time
import re
import email
try: #py2
    import email.Errors as Errors
    import email.Utils as Utils
    import email.Parser as Parser
    from email.Generator import Generator
    from email.Header import Header
except ImportError:
    import email.errors as Errors
    import email.utils as Utils
    import email.parser as Parser
    from email.generator import Generator
    from email.header import Header


from getmailcore.exceptions import *
from getmailcore.utilities import mbox_from_escape, format_header, \
    address_no_brackets
import getmailcore.logging

__all__ = [
    'Message',
]


message_attributes = (
    'received_by',
    'received_from',
    'received_with',
    'recipient'
    'sender',
)

_NL = os.linesep.encode()

#######################################
def corrupt_message(why, fromlines=None, fromstring=None):
    log = getmailcore.logging.Logger()
    log.error('failed to parse retrieved message; constructing container for '
              'contents\n')
    if fromlines == fromstring == None:
        raise SystemExit('corrupt_message() called with wrong arguments')
    msg = email.message_from_string('')
    msg['From'] = '"unknown sender" <>'
    msg['Subject'] = 'Corrupt message received'
    msg['Date'] = Utils.formatdate(localtime=True)
    body = [
        b'A badly-corrupt message was retrieved and could not be parsed',
        b'for the following reason:',
        b'',
        b'    %s' % str(why).encode(),
        b'',
        b'Below the following line is the original message contents.',
        b'',
        b'--------------------------------------------------------------',
    ]
    if fromlines:
        body.extend([line.rstrip() for line in fromlines])
    elif fromstring:
        body.extend([line.rstrip() for line in fromstring.splitlines()])
    msg.set_payload(_NL.join(body))
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
        'received_by',
        'received_from',
        'received_with',
        'recipient',
        'sender',
    )
    def __init__(self, fromlines=None, fromstring=None, fromfile=None):
        #self.log = Logger()
        self.recipient = None
        self.received_by = None
        self.received_from = None
        self.received_with = None
        self.__raw = None
        try:
            parser = Parser.BytesParser()
            parsestr = parser.parsebytes
        except: #py2
            parser = Parser.Parser()
            parsestr = parser.parsestr


        # Message is instantiated with fromlines for POP3, fromstring for
        # IMAP (both of which can be badly-corrupted or invalid, i.e. spam,
        # MS worms, etc).  It's instantiated with fromfile for the output
        # of filters, etc, which should be saner.
        if fromlines:
            try:
                self.__msg = parsestr(_NL.join(fromlines))
                #_msg = ucparse(parsestr,_NL.join(["über".encode('latin-1'),"Höhen".encode('latin-1')]))
                #type(_msg) #<class 'email.message.Message'>
            except (Errors.MessageError,UnicodeDecodeError) as o:
                self.__msg = corrupt_message(o, fromlines=fromlines)
            self.__raw = _NL.join(fromlines)
        elif fromstring:
            try:
                self.__msg = parsestr(fromstring)
                #_msg = ucparse(parsestr,"über\nHöhen".encode('latin-1'))
            except (Errors.MessageError,UnicodeDecodeError) as o:
                self.__msg = corrupt_message(o, fromstring=fromstring)
            self.__raw = fromstring
        elif fromfile:
            try:
                self.__msg = parser.parse(fromfile)
                #from io import BytesIO
                #fromfile=BytesIO(_NL.join(["über".encode('latin-1'),"Höhen".encode('latin-1')]))
                #_msg = ucparse(parser.parse,fromfile)
            except (Errors.MessageError,UnicodeDecodeError) as o:
                # Shouldn't happen
                self.__msg = corrupt_message(o, fromstring=fromfile.read())
            # fromfile is only used by getmail_maildir, getmail_mbox, and
            # from reading the output of a filter.  Ignore __raw here.
        else:
            # Can't happen?
            raise SystemExit('Message() called with wrong arguments')

        self.sender = address_no_brackets(self.__msg['Return-Path']
                                          or self.__msg['Sender']
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

        Note on mangle_from: the Python Generator class apparently only
        quotes "From ", not ">From " (i.e. it uses mboxo format instead of
        mboxrd).  So we don't use its mangling, and do it by hand instead.
        '''
        if include_from:
            # Mbox-style From line, not rfc822 From: header field.
            fromline = 'From %s %s' % (mbox_from_escape(self.sender),
                                       time.asctime()) + os.linesep
        else:
            fromline = ''
        # Write the Return-Path: header
        rpline = format_header('Return-Path', '<%s>' % self.sender)
        # Remove previous Return-Path: header fields.
        del self.__msg['Return-Path']
        if delivered_to:
            dtline = format_header('Delivered-To', self.recipient or 'unknown')
        else:
            dtline = ''
        if received:
            rcvd = 'from %s by %s with %s' % (
                self.received_from, self.received_by, self.received_with
            )
            rcvd += ' getmail6'
            if received != True:
                rcvd += ' msgid:%s'%received
            if self.recipient is not None:
                rcvd += ' for <%s>' % self.recipient
            rcvd += '; ' + time.strftime('%d %b %Y %H:%M:%S -0000',
                                            time.gmtime())
            rcvline = format_header('Received', rcvd)
        else:
            rcvline = ''
        # From_ handled above, always tell the generator not to include it
        try:
            try: #py3
                bmsg = self.__msg.as_bytes(
                    policy=self.__msg.policy.clone(linesep=os.linesep))
            except AttributeError: #py2
                bmsg = self.__msg.as_string()
                bmsg = _NL.join(bmsg.splitlines() + [b''])
            if mangle_from:
                # do mboxrd-style "From " line quoting (add one '>')
                RE_FROMLINE = re.compile(b'^(>*From )', re.MULTILINE)
                bmsg = RE_FROMLINE.sub(b'>\\1', bmsg)

            return ((fromline+rpline+dtline+rcvline).encode('ASCII',errors="replace")+bmsg)

        except (TypeError,UnicodeEncodeError) as o:
            if self.__raw is None:
                # Argh -- a filter took a correctly-formatted message
                # and returned a badly-misformatted one?
                raise getmailDeliveryError('failed to parse retrieved message '
                                           'and could not recover (%s)' % o)
            self.__msg = corrupt_message(o, fromstring=self.__raw)
            return self.flatten(delivered_to, received, mangle_from, include_from)


    def add_header(self, name, content):
        content_rstriped = content.rstrip()
        try:
            self.__msg[name] = Header(content_rstriped)
        except (UnicodeDecodeError, LookupError):
            for chs in self.__msg.get_charsets():
                if chs is None:
                    continue
                try:
                    self.__msg[name] = Header(content_rstriped,chs)
                    return
                except UnicodeError:
                    continue
            self.__msg[name] = Header(content_rstriped,'utf-8',errors="replace")

    def remove_header(self, name):
        del self.__msg[name]

    def headers(self):
        return self.__msg._headers

    def get_all(self, name, failobj=None):
        return self.__msg.get_all(name, failobj)
