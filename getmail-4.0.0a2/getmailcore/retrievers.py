#!/usr/bin/env python
'''Classes implementing retrievers (message sources getmail can retrieve mail from).

Currently implemented:

  RetrieverSkeleton (base class; not to be instantiated directly)
  POP3initMixIn (mix-in initialization class for non-SSL POP3 classes; not to be instantiated directly)
  POP3SSLinitMixIn (mix-in initialization class for POP3-over-SSL classes; not to be instantiated directly)
  POP3RetrieverBase (base class; not to be instantiated directly)
  MultidropPOP3RetrieverBase (base class; not to be instantiated directly)

  SimplePOP3Retriever
  SimplePOP3SSLRetriever
  MultidropPOP3Retriever
  MultidropPOP3SSLRetriever
  MultidropSPDSRetriever

  SimpleIMAPv4Retriever (incomplete -- IMAP, as a protocol, is a FPOS, and
    it shows.  The Python standard library module imaplib leaves much up to
    the user because of this.)
'''

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
from logging import logger
from pop3ssl import POP3SSL, POP3_ssl_port

#
# Functional classes
#

#######################################
class RetrieverSkeleton(object):
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

      showconf(self) - should invoke logger().info() to display the configuration of
                       the class instance.

    Sub-classes may also wish to extend or over-ride the following base class
    methods:

      __init__(self, **args)
      __del__(self)
      initialize(self)
      checkconf(self)
    '''

    def __init__(self, **args):
        self.log = logger()
        self.log.trace('args: %s\n' % args)
        self.conf = {}
        for (name, value) in args.items():
            self.log.trace('setting %s to %s (%s)\n' % (name, value, type(value)))
            self.conf[name] = value
        self.msgids = []
        self.msgsizes = {}
        self.headercache = {}
        self.oldmail = {}
        self.timestamp = int(time.time())
        self.__confchecked = False
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
        self.log.trace()
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
                if msgid in self.msgids:
                    # This message still in inbox; remember it for next time.
                    f.write('%s\0%i%s' % (msgid, timestamp, os.linesep))
                #else:
                # Message doesn't exist in inbox, no sense remembering it.
            f.close()
            self.log.info('wrote %i uids for %s\n' % (len(self.oldmail), self))
        except IOError, o:
            self.log.error('failed writing oldmail file for %s\n' % self)

    def checkconf(self):
        self.log.trace()
        if self.__confchecked:
            return
        for item in self._confitems:
            self.log.trace('checking %s\n' % item)
            name = item['name']
            dtype = item['type']
            if not self.conf.has_key(name):
                # Not provided
                if item.has_key('default'):
                    self.conf[name] = item['default']
                else:
                    raise getmailConfigurationError('missing required configuration directive %s' % name)
            if type(self.conf[name]) is not dtype:
                try:
                    self.log.debug('converting %s (%s) to type %s\n' % (name, self.conf['name'], dtype))
                    self.conf[name] = dtype(eval(self.conf[name]))
                except StandardError, o:
                    raise getmailConfigurationError('configuration value %s not of required type %s (%s)' % (name, dtype, o))
        self.__confchecked = True
        self.log.trace('done\n')

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
        if not self.headercache.has_key(msgid):
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
        i = self.msgids.index(msgid)
        del self.msgids[i]

#######################################
class POP3initMixIn(object):
    '''Mix-In class to do POP3 non-SSL initialization.
    '''
    def _connect(self):
        self.log.trace()
        try:
            self.conn = poplib.POP3(self.conf['server'], self.conf['port'])
            if self.conf['use_apop']:
                self.conn.apop(self.conf['username'], self.conf['password'])
            else:
                self.conn.user(self.conf['username'])
                self.conn.pass_(self.conf['password'])
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)

#######################################
class POP3SSLinitMixIn(object):
    '''Mix-In class to do POP3 over SSL initialization.
    '''
    def _connect(self):
        self.log.trace()
        if self.conf['keyfile'] is not None and not os.path.isfile(self.conf['keyfile']):
            raise getmailConfiruationError('optional keyfile must be path to a valid file')
        if self.conf['certfile'] is not None and not os.path.isfile(self.conf['certfile']):
            raise getmailConfiruationError('optional certfile must be path to a valid file')
        if not (self.conf['certfile'] == self.conf['keyfile'] == None):
            if self.conf['certfile'] is None or self.conf['keyfile'] is None:
                raise getmailConfiruationError('optional certfile and keyfile must be supplied together')
        try:
            self.conn = POP3SSL(self.conf['server'], self.conf['port'], self.conf['keyfile'], self.conf['certfile'])
            if self.conf['use_apop']:
                self.conn.apop(self.conf['username'], self.conf['password'])
            else:
                self.conn.user(self.conf['username'])
                self.conn.pass_(self.conf['password'])
        except poplib.error_proto, o:
            raise getmailOperationError('POP error (%s)' % o)

#######################################
class POP3RetrieverBase(RetrieverSkeleton):
    '''Base class for single-user POP3 mailboxes.
    '''
    def __init__(self, **args):
        RetrieverSkeleton.__init__(self, **args)
        self.log.trace()
        #self.log.debug('configuration: %s\n' % self.conf)

    def __del__(self):
        self.quit()
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
            msg.sender = address_no_brackets(msg['return-path']) or 'unknown'
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
class SimplePOP3Retriever(POP3RetrieverBase, POP3initMixIn):
    '''Retriever class for single-user POP3 mailboxes.
    '''
    _confitems = (
        {'name' : 'getmaildir', 'type' : str, 'default' : '~/.getmail/'},

        {'name' : 'timeout', 'type' : int, 'default' : 180},
        {'name' : 'server', 'type' : str},
        {'name' : 'port', 'type' : int, 'default' : 110},
        {'name' : 'username', 'type' : str},
        {'name' : 'password', 'type' : str, 'default' : None},
        {'name' : 'use_apop', 'type' : bool, 'default' : False},
    )

    def __str__(self):
        self.log.trace()
        return 'SimplePOP3Retriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('SimplePOP3Retriever(%s)\n' % self._confstring())

#######################################
class SimplePOP3SSLRetriever(POP3RetrieverBase, POP3SSLinitMixIn):
    '''Retriever class for single-user POP3-over-SSL mailboxes.
    '''
    _confitems = (
        {'name' : 'getmaildir', 'type' : str, 'default' : '~/.getmail/'},

        {'name' : 'timeout', 'type' : int, 'default' : 180},
        {'name' : 'server', 'type' : str},
        {'name' : 'port', 'type' : int, 'default' : POP3_ssl_port},
        {'name' : 'username', 'type' : str},
        {'name' : 'password', 'type' : str, 'default' : None},
        {'name' : 'use_apop', 'type' : bool, 'default' : False},
        {'name' : 'keyfile', 'type' : str, 'default' : None},
        {'name' : 'certfile', 'type' : str, 'default' : None},
    )

    def __str__(self):
        self.log.trace()
        return 'SimplePOP3SSLRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('SimplePOP3SSLRetriever(%s)\n' % self._confstring())


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
            if data.has_key(name):
                data[name].append(val)
            else:
                data[name] = [val]

        try:
            line = data[self.envrecipname][self.envrecipnum]
        except (KeyError, IndexError), o:
            raise getmailConfigurationError('envelope_recipient specified header missing (%s)' % self.conf['envelope_recipient'])
        msg.recipient = [address_no_brackets(address) for (name, address) in email.Utils.getaddresses([line])]
        if len(msg.recipient) != 1:
            raise getmailConfigurationError('extracted <> 1 envelope recipient address (%s)' % msg.recipient)
        msg.recipient = msg.recipient[0]
        return msg

#######################################
class MultidropPOP3Retriever(MultidropPOP3RetrieverBase, POP3initMixIn):
    '''Retriever class for multi-drop POP3 mailboxes.
    '''
    _confitems = (
        {'name' : 'getmaildir', 'type' : str, 'default' : '~/.getmail/'},

        {'name' : 'timeout', 'type' : int, 'default' : 180},
        {'name' : 'server', 'type' : str},
        {'name' : 'port', 'type' : int, 'default' : 110},
        {'name' : 'username', 'type' : str},
        {'name' : 'password', 'type' : str, 'default' : None},
        {'name' : 'use_apop', 'type' : bool, 'default' : False},
        {'name' : 'envelope_recipient', 'type' : str},
    )

    def __init__(self, **args):
        MultidropPOP3RetrieverBase.__init__(self, **args)

    def __str__(self):
        self.log.trace()
        return 'MultidropPOP3Retriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('MultidropPOP3Retriever(%s)\n' % self._confstring())

#######################################
class MultidropPOP3SSLRetriever(MultidropPOP3RetrieverBase, POP3SSLinitMixIn):
    '''Retriever class for multi-drop POP3-over-SSL mailboxes.
    '''
    _confitems = (
        {'name' : 'getmaildir', 'type' : str, 'default' : '~/.getmail/'},

        {'name' : 'timeout', 'type' : int, 'default' : 180},
        {'name' : 'server', 'type' : str},
        {'name' : 'port', 'type' : int, 'default' : 110},
        {'name' : 'username', 'type' : str},
        {'name' : 'password', 'type' : str, 'default' : None},
        {'name' : 'use_apop', 'type' : bool, 'default' : False},
        {'name' : 'envelope_recipient', 'type' : str},
        {'name' : 'keyfile', 'type' : str, 'default' : None},
        {'name' : 'certfile', 'type' : str, 'default' : None},
    )

    def __init__(self, **args):
        MultidropPOP3RetrieverBase.__init__(self, **args)

    def __str__(self):
        self.log.trace()
        return 'MultidropPOP3SSLRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('MultidropPOP3SSLRetriever(%s)\n' % self._confstring())

#######################################
class MultidropSPDSRetriever(SimplePOP3Retriever, POP3initMixIn):
    '''Retriever class for multi-drop SPDS (demon.co.uk) mailboxes.

    Extend POP3 class to include support for Demon's protocol extensions,
    known as SPDS.  A non-standard command (*ENV) is used to retrieve the
    message envelope.  See http://www.demon.net/helpdesk/products/mail/sdps-tech.shtml
    for details.

    Support originally requested by Paul Clifford for getmail v.2/3.
    '''
    _confitems = (
        {'name' : 'getmaildir', 'type' : str, 'default' : '~/.getmail/'},

        {'name' : 'timeout', 'type' : int, 'default' : 180},
        {'name' : 'server', 'type' : str},
        {'name' : 'port', 'type' : int, 'default' : 110},
        {'name' : 'username', 'type' : str},
        {'name' : 'password', 'type' : str, 'default' : None},
        #{'name' : 'use_apop', 'type' : bool, 'default' : False},
    )

    def __init__(self, **args):
        SimplePOP3Retriever.__init__(self, **args)

    def __str__(self):
        self.log.trace()
        return 'MultidropSPDSRetriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

    def showconf(self):
        self.log.trace()
        self.log.info('MultidropSPDSRetriever(%s)\n' % self._confstring())

    def _getmsgbyid(self, msgid):
        self.log.trace()
        msg = SimplePOP3Retriever._getmsgbyid(self, msgid)

        # The magic of SPDS is the "*ENV" command.  Implement it:
        try:
            msgnum = self._getmsgnumbyid(msgid)
            resp, lines, octets = self.conn._longcmd('*ENV %i' % msgnum)
        except poplib.error_proto, o:
            raise getmailConfigurationError('server does not support *ENV (%s)' % o)
        if len(lines) < 4:
            raise getmailOperationError('short *ENV response (%s)' % lines)
        msg.sender = lines[2]
        msg.recipient = lines[3]
        return msg

#######################################
class SimpleIMAPv4Retriever(RetrieverSkeleton):
    '''Retriever class for single-user IMAPv4 mailboxes.

    Incomplete.
    '''
    _confitems = (
        {'name' : 'getmaildir', 'type' : str, 'default' : '~/.getmail/'},

        {'name' : 'timeout', 'type' : int, 'default' : 180},
        {'name' : 'server', 'type' : str},
        {'name' : 'port', 'type' : int, 'default' : 143},
        {'name' : 'username', 'type' : str},
        {'name' : 'password', 'type' : str, 'default' : None},
        {'name' : 'use_cram_md5', 'type' : bool, 'default' : False},
    )

    def __init__(self, **args):
        RetrieverSkeleton.__init__(self, **args)
        self.log.trace()
        #self.log.debug('configuration: %s\n' % self.conf)

    def __del__(self):
        self.quit()
        RetrieverSkeleton.__del__(self)

    def __str__(self):
        self.log.trace()
        return 'SimpleIMAPv4Retriever:%s@%s:%s' % (
            self.conf.get('username', 'username'),
            self.conf.get('server', 'server'),
            self.conf.get('port', 'port')
        )

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
            response, msglist, octets = self.conn.list()
            for line in msglist:
                msgnum = int(line.split()[0])
                msgsize = int(line.split()[1])
                self.msgsizes[self.msgids[msgnum - 1]] = msgsize
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

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
            msg.sender = address_no_brackets(msg['return-path']) or 'unknown'
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

    def _getheaderbyid(self, msgid):
        self.log.trace()
        msgnum = self._getmsgnumbyid(msgid)
        response, headerlist, octets = self.conn.top(msgnum, 0)
        parser = email.Parser.Parser(strict=False)
        return parser.parsestr(os.linesep.join(headerlist), headersonly=True)

    def showconf(self):
        self.log.trace()
        self.log.info('SimpleIMAPv4Retriever(%s)\n' % self._confstring())

    def initialize(self):
        self.log.trace()
        # Handle password
        if self.conf.get('password', None) is None:
            self.conf['password'] = getpass.getpass('Enter password for %s:  ' % self)
        RetrieverSkeleton.initialize(self)
        socket.setdefaulttimeout(self.conf['timeout'])
        try:
            self.conn = imaplib.IMAP4(self.conf['server'], self.conf['port'])
            if self.conf['use_cram_md5']:
                self.conn.login_cram_md5(self.conf['username'], self.conf['password'])
            else:
                self.conn.login(self.conf['username'], self.conf['password'])
            # FIXME: todo
            msgcount = self.conn.select()
            self._getmsglist()
            self.log.debug('msgids: %s\n' % self.msgids)
            self.log.debug('msgsizes: %s\n' % self.msgsizes)
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)

    def abort(self):
        self.log.trace()
        try:
            self.conn.rset()
            self.conn.quit()
        except imaplib.IMAP4.error:
            pass
        del self.conn

    def quit(self):
        try:
            self.conn.close()
            self.conn.logout()
            self.conn = None
        except imaplib.IMAP4.error, o:
            raise getmailOperationError('IMAP error (%s)' % o)
