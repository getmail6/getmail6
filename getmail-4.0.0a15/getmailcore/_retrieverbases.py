#!/usr/bin/env python2.3
'''Base and mix-in classes implementing retrievers (message sources getmail can retrieve mail from).

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

__all__ = ['POP3_ssl_port', 'POP3initMixIn', 'POP3SSLinitMixIn', 'IMAPinitMixIn',
    'IMAPSSLinitMixIn', 'RetrieverSkeleton', 'POP3RetrieverBase', 'MultidropPOP3RetrieverBase',
    'IMAPRetrieverBase', 'MultidropIMAPRetrieverBase'
]

import os
import socket
import time
import getpass
import email
import poplib
import imaplib

from exceptions import *
from constants import *
from utilities import updatefile, address_no_brackets
from _pop3ssl import POP3SSL, POP3_ssl_port
from baseclasses import ConfigurableBase

#
# Mix-in classes
#

#######################################
class POP3initMixIn(object):
    '''Mix-In class to do POP3 non-SSL initialization.
    '''
    def _connect(self):
        self.log.trace()
        try:
            self.conn = poplib.POP3(self.conf['server'], self.conf['port'])
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)

        self.log.trace('POP3 connection %s established\n' % self.conn)

#######################################
class POP3SSLinitMixIn(object):
    '''Mix-In class to do POP3 over SSL initialization.
    '''
    def _connect(self):
        self.log.trace()
        if self.conf['keyfile'] is not None and not os.path.isfile(self.conf['keyfile']):
            raise getmailConfigurationError('optional keyfile must be path to a valid file')
        if self.conf['certfile'] is not None and not os.path.isfile(self.conf['certfile']):
            raise getmailConfigurationError('optional certfile must be path to a valid file')
        if not (self.conf['certfile'] == self.conf['keyfile'] == None):
            if self.conf['certfile'] is None or self.conf['keyfile'] is None:
                raise getmailConfigurationError('optional certfile and keyfile must be supplied together')
        try:
            if self.conf['certfile'] and self.conf['keyfile']:
                self.log.trace('establishing POP3 SSL connection to %s:%d with keyfile %s, certfile %s\n' % (self.conf['server'], self.conf['port'], self.conf['keyfile'], self.conf['certfile']))
                self.conn = POP3SSL(self.conf['server'], self.conf['port'], self.conf['keyfile'], self.conf['certfile'])
            else:
                self.log.trace('establishing POP3 SSL connection to %s:%d\n' % (self.conf['server'], self.conf['port']))
                self.conn = POP3SSL(self.conf['server'], self.conf['port'])
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)

        self.log.trace('POP3 SSL connection %s established\n' % self.conn)

#######################################
class IMAPinitMixIn(object):
    '''Mix-In class to do IMAP non-SSL initialization.
    '''
    def _connect(self):
        self.log.trace()
        try:
            self.conn = imaplib.IMAP4(self.conf['server'], self.conf['port'])
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

        self.log.trace('IMAP connection %s established\n' % self.conn)

#######################################
class IMAPSSLinitMixIn(object):
    '''Mix-In class to do IMAP over SSL initialization.
    '''
    def _connect(self):
        self.log.trace()
        if self.conf['keyfile'] is not None and not os.path.isfile(self.conf['keyfile']):
            raise getmailConfigurationError('optional keyfile must be path to a valid file')
        if self.conf['certfile'] is not None and not os.path.isfile(self.conf['certfile']):
            raise getmailConfigurationError('optional certfile must be path to a valid file')
        if not (self.conf['certfile'] == self.conf['keyfile'] == None):
            if self.conf['certfile'] is None or self.conf['keyfile'] is None:
                raise getmailConfigurationError('optional certfile and keyfile must be supplied together')
        try:
            if self.conf['certfile'] and self.conf['keyfile']:
                self.log.trace('establishing IMAP SSL connection to %s:%d with keyfile %s, certfile %s\n' % (self.conf['server'], self.conf['port'], self.conf['keyfile'], self.conf['certfile']))
                self.conn = imaplib.IMAP4_SSL(self.conf['server'], self.conf['port'], self.conf['keyfile'], self.conf['certfile'])
            else:
                self.log.trace('establishing IMAP SSL connection to %s:%d\n' % (self.conf['server'], self.conf['port']))
                self.conn = imaplib.IMAP4_SSL(self.conf['server'], self.conf['port'])
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

        self.log.trace('IMAP SSL connection %s established\n' % self.conn)

#
# Base classes
#

#######################################
class RetrieverSkeleton(ConfigurableBase):
    '''Base class for implementing message-retrieval classes.

    Sub-classes should provide the following data attributes and methods:

      _confitems - a tuple of dictionaries representing the parameters the class
                   takes.  Each dictionary should contain the following key, value
                   pairs:
                     - name - parameter name
                     - type - a type function to compare the parameter value against (i.e. str, int, bool)
                     - default - optional default value.  If not preseent, the parameter is required.

      __str__(self) - return a simple string representing the class instance.

      _getmsglist(self) - retieve a list of all available messages, and store
                          unique message identifiers in the list self.msgids.
                          Message identifiers must be unique and persistent across
                          instantiations.  Also store message sizes (in octets)
                          in a dictionary self.msgsizes, using the message identifiers
                          as keys.

      _delmsgbyid(self, msgid) - delete a message from the message store based
                                 on its message identifier.

      _getmsgbyid(self, msgid) - retreive and return a message from the message
                                 store based on its message identifier.  The message
                                 is returned as an email.Message() class object.
                                 The message should have additional data attributes
                                 "sender" and "recipient" if (and only if) the
                                 protocol/method of message retrieval preserves the
                                 original message envelope.

      _getheaderbyid(self, msgid) - similar to _getmsgbyid() above, but only the message
                                    header should be retrieved, if possible.  It should
                                    be returned in the same format.

      showconf(self) - should invoke self.log.info() to display the configuration of
                       the class instance.

    Sub-classes may also wish to extend or over-ride the following base class
    methods:

      __init__(self, **args)
      __del__(self)
      initialize(self)
      checkconf(self)
    '''

    def __init__(self, **args):
        ConfigurableBase.__init__(self, **args)
        self.msgids = []
        self.msgsizes = {}
        self.headercache = {}
        self.oldmail = {}
        self.deleted = {}
        self.timestamp = int(time.time())
        self.__initialized = False

    def __del__(self):
        self.log.trace()
        self._write_oldmailfile()

    def __str__(self):
        self.log.trace()
        return str(self.conf)

    def __len__(self):
        self.log.trace()
        return len(self.msgids)

    def __getitem__(self, i):
        self.log.trace('i == %d' % i)
        if not self.__initialized:
            raise getmailOperationError('not initialized')
        return self.msgids[i]

    def _read_oldmailfile(self):
        '''Read contents of oldmail file.'''
        self.log.trace()
        try:
            for (msgid, timestamp) in [line.strip().split('\0', 1) for line in open(self.oldmail_filename, 'rb').xreadlines() if line.strip()!='']:
                self.oldmail[msgid] = int(timestamp)
            self.log.info('read %i uids for %s\n' % (len(self.oldmail), self))
        except IOError:
            self.log.info('no oldmail file for %s\n' % self)

    def _write_oldmailfile(self):
        '''Write oldmail info to oldmail file.'''
        self.log.trace()
        if not self.__initialized:
            return
        try:
            f = updatefile(self.oldmail_filename)
            for msgid, timestamp in self.oldmail.items():
                if msgid in self.msgids and not msgid in self.deleted:
                    # This message still in inbox; remember it for next time.
                    f.write('%s\0%i%s' % (msgid, timestamp, os.linesep))
                #else:
                # Message doesn't exist in inbox, no sense remembering it.
            f.close()
            self.log.info('wrote %i uids for %s\n' % (len(self.oldmail), self))
        except IOError, o:
            self.log.error('failed writing oldmail file for %s (%s)\n' % (self, o))

    def _confstring(self):
        self.log.trace()
        confstring = ''
        names = self.conf.keys()
        names.sort()
        for name in names:
            if confstring:  confstring += ', '
            if name.lower() == 'password':
                confstring += '%s="*"' % name
            else:
                confstring += '%s="%s"' % (name, self.conf[name])
        return confstring

    def initialize(self):
        self.log.trace()
        self.checkconf()
        self.oldmail_filename = os.path.join(
            os.path.expanduser(self.conf['getmaildir']),
            ('oldmail-%(server)s-%(port)i-%(username)s' % self.conf).replace('/', '-').replace(':', '-')
        )
        self._read_oldmailfile()
        self.__initialized = True

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
        #self.log.debug('configuration: %s\n' % self.conf)

    def __del__(self):
        RetrieverSkeleton.__del__(self)

    def _getmsgnumbyid(self, msgid):
        self.log.trace()
        if not msgid in self.msgids:
            raise getmailOperationError('no such message ID %s' % msgid)
        return self.msgids.index(msgid) + 1

    def _getmsglist(self):
        self.log.trace()
        try:
            response, msglist, octets = self.conn.uidl()
            self.log.debug('UIDL response "%s", %d octets\n' % (response, octets))
            self.msgids = [line.split(None, 1)[1] for line in msglist]
            self.log.debug('Message IDs: %s\n' % self.msgids)
            response, msglist, octets = self.conn.list()
            for line in msglist:
                msgnum = int(line.split()[0])
                msgsize = int(line.split()[1])
                self.msgsizes[self.msgids[msgnum - 1]] = msgsize
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)

    def _delmsgbyid(self, msgid):
        self.log.trace()
        msgnum = self._getmsgnumbyid(msgid)
        self.conn.dele(msgnum)

    def _getmsgbyid(self, msgid):
        self.log.debug('msgid %s\n' % msgid)
        msgnum = self._getmsgnumbyid(msgid)
        self.log.debug('msgnum %i\n' % msgnum)
        try:
            response, lines, octets = self.conn.retr(msgnum)
            self.log.debug('RETR response "%s", %d octets\n' % (response, octets))
            msg = email.message_from_string(os.linesep.join(lines))
            msg.mid = msgid
            msg.sender = address_no_brackets(msg['return-path'] or 'unknown')
            if msgid in self.oldmail:
                msg.new = False
                msg.seentime = self.oldmail[msgid]
            else:
                msg.new = True
                msg.seentime = int(time.time())
                self.oldmail[msgid] = msg.seentime
            return msg
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)

    def _getheaderbyid(self, msgid):
        self.log.trace()
        msgnum = self._getmsgnumbyid(msgid)
        response, headerlist, octets = self.conn.top(msgnum, 0)
        parser = email.Parser.Parser(strict=False)
        return parser.parsestr(os.linesep.join(headerlist), headersonly=True)

    def initialize(self):
        self.log.trace()
        # Handle password
        if self.conf.get('password', None) is None:
            self.conf['password'] = getpass.getpass('Enter password for %s:  ' % self)
        RetrieverSkeleton.initialize(self)
        socket.setdefaulttimeout(self.conf['timeout'])
        try:
            self._connect()
            if self.conf['use_apop']:
                self.conn.apop(self.conf['username'], self.conf['password'])
            else:
                self.conn.user(self.conf['username'])
                self.conn.pass_(self.conf['password'])
            self._getmsglist()
            self.log.debug('msgids: %s\n' % self.msgids)
            self.log.debug('msgsizes: %s\n' % self.msgsizes)
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)

    def abort(self):
        self.log.trace()
        try:
            self.conn.rset()
            self.conn.quit()
        except poplib.error_proto:
            pass
        del self.conn

    def quit(self):
        try:
            self.conn.quit()
            self.conn = None
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)
        except AttributeError:
            pass

#######################################
class MultidropPOP3RetrieverBase(POP3RetrieverBase):
    '''Base retriever class for multi-drop POP3 mailboxes.

    Envelope is reconstructed from Return-Path: (sender) and a header specified
    by the user (recipient).  This header is specified with the "envelope_recipient"
    parameter, which takes the form <field-name>[:<field-number>].  field-number
    defaults to 1 and is counted from top to bottom in the message.  For instance,
    if the envelope recipient is present in the second Delivered-To: header field
    of each message, envelope_recipient should be specified as "delivered-to:2".
    '''

    def initialize(self):
        self.log.trace()
        POP3RetrieverBase.initialize(self)
        self.envrecipname = self.conf['envelope_recipient'].split(':')[0].lower()
        self.envrecipnum = 0
        try:
            self.envrecipnum = int(self.conf['envelope_recipient'].split(':', 1)[1]) - 1
            if self.envrecipnum < 0:
                raise ValueError(self.conf['envelope_recipient'])
        except IndexError:
            pass
        except ValueError, o:
            raise getmailConfigurationError('invalid envelope_recipient specification format (%s)' % o)

    def _getmsgbyid(self, msgid):
        self.log.trace()
        msg = POP3RetrieverBase._getmsgbyid(self, msgid)
        data = {}
        for (name, val) in msg._headers:
            name = name.lower()
            val = val.strip()
            if name in data:
                data[name].append(val)
            else:
                data[name] = [val]

        try:
            line = data[self.envrecipname][self.envrecipnum]
        except (KeyError, IndexError), unused:
            raise getmailConfigurationError('envelope_recipient specified header missing (%s)' % self.conf['envelope_recipient'])
        msg.recipient = [address_no_brackets(address) for (name, address) in email.Utils.getaddresses([line]) if address]
        if len(msg.recipient) != 1:
            raise getmailConfigurationError('extracted <> 1 envelope recipient address (%s)' % msg.recipient)
        msg.recipient = msg.recipient[0]
        return msg

#######################################
class IMAPRetrieverBase(RetrieverSkeleton):
    '''Base class for single-user IMAP mailboxes.
    '''
    def __init__(self, **args):
        RetrieverSkeleton.__init__(self, **args)
        self.log.trace()
        self.mailbox = None
        #self.log.debug('configuration: %s\n' % self.conf)

    def __del__(self):
        RetrieverSkeleton.__del__(self)

    def _getmboxuidbymsgid(self, msgid):
        self.log.trace()
        if not msgid in self.msgids:
            raise getmailOperationError('no such message ID %s' % msgid)
        mailbox, uid = self._mboxuids[msgid]
        return mailbox, uid

    def _parse_imapcmdresponse(self, cmd, *args):
        self.log.trace()
        result, resplist = getattr(self.conn, cmd)(*args)
        if result != 'OK':
            raise getmailOperationError('IMAP error (command %s returned %s)' % ('%s %s' % (cmd, args), result))
        if cmd.lower().startswith('login'):
            self.log.debug('login command response %s\n' % resplist)
        else:
            self.log.debug('command %s response %s\n' % ('%s %s' % (cmd, args), resplist))
        return resplist

    def _parse_imapuidcmdresponse(self, cmd, *args):
        self.log.trace()
        result, resplist = self.conn.uid(cmd, *args)
        if result != 'OK':
            raise getmailOperationError('IMAP error (command %s returned %s)' % ('%s %s' % (cmd, args), result))
        self.log.debug('command uid %s response %s\n' % ('%s %s' % (cmd, args), resplist))
        return resplist

    def _parse_imapuidresponse(self, line):
        self.log.trace('parsing uid response line %s\n' % line)
        r = {}
        try:
            parts = line[line.index('(') + 1:line.rindex(')')].split()
            if len(parts) % 2:
                # Not zero -- i.e. an uneven number of parts
                raise ValueError
            while parts:
                # Interesting; RHS is evaluated first, breaking this expression...
                # r[parts.pop(0).lower()] = parts.pop(0)
                name = parts.pop(0).lower()
                r[name] = parts.pop(0)
        except ValueError:
            raise getmailOperationError('IMAP error (failed to parse UID response line %s)' % line)
        self.log.trace('got %s\n' % r)
        return r

    def _selectmailbox(self, mailbox):
        self.log.trace()
        if mailbox == self.mailbox:
            return
        self.log.debug('selecting mailbox "%s"\n' % mailbox)
        response = self._parse_imapcmdresponse('SELECT', mailbox)
        c = int(response[0])
        self.log.debug('select(%s) returned message count of %d\n' % (mailbox, c))
        self.mailbox = mailbox

    def _getmsglist(self):
        self.log.trace()
        self.msgids = []
        self._mboxuids = {}
        self.msgsizes = {}
        for mailbox in self.conf['mailboxes']:
            try:
                self._selectmailbox(mailbox)
                # Get UIDs for messages in mailbox
                response = self._parse_imapuidcmdresponse('SEARCH', 'ALL')
                uids = response[0].split()
                if not uids:
                    continue
                self.log.debug('uid("SEARCH", "ALL") returned %d UIDs (%s)\n' % (len(uids), uids))
                # Get message sizes
                response = self._parse_imapuidcmdresponse('FETCH', ','.join(uids), 'RFC822.SIZE')
                for line in response:
                    r = self._parse_imapuidresponse(line)
                    msgid = '%s/%s' % (mailbox, r['uid'])
                    self._mboxuids[msgid] = (mailbox, r['uid'])
                    self.msgids.append(msgid)
                    self.msgsizes[msgid] = int(r['rfc822.size'])

            except imaplib.IMAP4.error, o:
                raise getmailOperationError('IMAP error (%s)' % o)

    def _delmsgbyid(self, msgid):
        self.log.trace()
        try:
            mailbox, uid = self._getmboxuidbymsgid(msgid)
            self._selectmailbox(mailbox)
            # Delete message
            if self.conf['move_on_delete']:
                self.log.debug('copying message to folder "%s"\n' % self.conf['move_on_delete'])
                response = self._parse_imapuidcmdresponse('COPY', uid, self.conf['move_on_delete'])
            self.log.debug('deleting message "%s"\n' % uid)
            response = self._parse_imapuidcmdresponse('STORE', uid, 'FLAGS', '(\Deleted)')
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

    def _getmsgpartbyid(self, msgid, part):
        self.log.trace()
        try:
            mailbox, uid = self._getmboxuidbymsgid(msgid)
            self._selectmailbox(mailbox)
            # Retrieve message
            self.log.debug('retrieving body for message "%s"\n' % uid)
            response = self._parse_imapuidcmdresponse('FETCH', uid, part)
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
            msg = email.message_from_string(response[0][1])
            msg.mid = msgid
            msg.sender = address_no_brackets(msg['return-path'] or 'unknown')
            if msgid in self.oldmail:
                msg.new = False
                msg.seentime = self.oldmail[msgid]
            else:
                msg.new = True
                msg.seentime = int(time.time())
                self.oldmail[msgid] = msg.seentime
            return msg

        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

    def _getmsgbyid(self, msgid):
        self.log.trace()
        return self._getmsgpartbyid(msgid, '(RFC822)')

    def _getheaderbyid(self, msgid):
        self.log.trace()
        return self._getmsgpartbyid(msgid, '(RFC822[header])')

    def initialize(self):
        self.log.trace()
        # Handle password
        if self.conf.get('password', None) is None:
            self.conf['password'] = getpass.getpass('Enter password for %s:  ' % self)
        RetrieverSkeleton.initialize(self)
        # socket.ssl() and socket timeouts are incompatible in Python 2.3
        if 'timeout' in self.conf:
            socket.setdefaulttimeout(self.conf['timeout'])
        try:
            self.log.trace('trying self._connect()\n')
            self._connect()
            self.log.trace('logging in\n')
            if self.conf['use_cram_md5']:
                self._parse_imapcmdresponse('login_cram_md5', self.conf['username'], self.conf['password'])
            else:
                self._parse_imapcmdresponse('login', self.conf['username'], self.conf['password'])
            self.log.trace('logged in, getting message list\n')
            self._getmsglist()
            self.log.debug('msgids: %s\n' % self.msgids)
            self.log.debug('msgsizes: %s\n' % self.msgsizes)
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)

    def abort(self):
        self.log.trace()
        self.quit()

    def quit(self):
        try:
            self.conn.close()
            self.conn.logout()
            self.conn = None
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

#######################################
class MultidropIMAPRetrieverBase(IMAPRetrieverBase):
    '''Base retriever class for multi-drop IMAP mailboxes.

    Envelope is reconstructed from Return-Path: (sender) and a header specified
    by the user (recipient).  This header is specified with the "envelope_recipient"
    parameter, which takes the form <field-name>[:<field-number>].  field-number
    defaults to 1 and is counted from top to bottom in the message.  For instance,
    if the envelope recipient is present in the second Delivered-To: header field
    of each message, envelope_recipient should be specified as "delivered-to:2".
    '''

    def initialize(self):
        self.log.trace()
        IMAPRetrieverBase.initialize(self)
        self.envrecipname = self.conf['envelope_recipient'].split(':')[0].lower()
        self.envrecipnum = 0
        try:
            self.envrecipnum = int(self.conf['envelope_recipient'].split(':', 1)[1]) - 1
            if self.envrecipnum < 0:
                raise ValueError(self.conf['envelope_recipient'])
        except IndexError:
            pass
        except ValueError, o:
            raise getmailConfigurationError('invalid envelope_recipient specification format (%s)' % o)

    def _getmsgbyid(self, msgid):
        self.log.trace()
        msg = IMAPRetrieverBase._getmsgbyid(self, msgid)
        data = {}
        for (name, val) in msg._headers:
            name = name.lower()
            val = val.strip()
            if name in data:
                data[name].append(val)
            else:
                data[name] = [val]

        try:
            line = data[self.envrecipname][self.envrecipnum]
        except (KeyError, IndexError), unused:
            raise getmailConfigurationError('envelope_recipient specified header missing (%s)' % self.conf['envelope_recipient'])
        msg.recipient = [address_no_brackets(address) for (name, address) in email.Utils.getaddresses([line]) if address]
        if len(msg.recipient) != 1:
            raise getmailConfigurationError('extracted <> 1 envelope recipient address (%s)' % msg.recipient)
        msg.recipient = msg.recipient[0]
        return msg
