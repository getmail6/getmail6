#!/usr/bin/python
'''getmail.py - POP3 mail retriever with reliable Maildir and mbox delivery.
Copyright (C) 2001 Charles Cazabon <getmail @ discworld.dyndns.org>

This program is free software; you can redistribute it and/or
modify it under the terms of version 2 of the GNU General Public License
as published by the Free Software Foundation.  A copy of this license should
be included in the file COPYING.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

'''

__version__ = '2.2.0'
__author__ = 'Charles Cazabon <getmail @ discworld.dyndns.org>'

#
# Imports
#

# Try importing timeoutsocket.  If it does not exist, just skip it.
try:
    import timeoutsocket
    Timeout = timeoutsocket.Timeout
except ImportError:
    # Prevent errors later for references to timeoutsocket
    Timeout = None
    class null_timeoutsocket:
        def getDefaultSocketTimeout (self):
            return 0
        def setDefaultSocketTimeout (self, val):
            pass
    timeoutsocket = null_timeoutsocket ()

# Configuration file parser
import ConfParser

# Main Python library
import sys
import os
import string
import re
import time
import socket
import poplib
import fcntl
import rfc822
import cStringIO
import stat
import traceback
import getopt
import getpass
import signal
import sha
from types import *


#
# Exception classes
#

# Base class for all getmail exceptions
class getmailException (Exception):
    pass

# Specific exception classes
class getmailConfigException (getmailException):
    pass

class getmailTimeoutException (getmailException):
    pass

class getmailSocketException (getmailException):
    pass

class getmailProtoException (getmailException):
    pass

class getmailDeliveryException (getmailException):
    pass

class getmailNetworkError (getmailException):
    pass

class getmailUnhandledException (Exception):
    pass

#
# Defaults
#
# These can mostly be overridden with commandline arguments or via getmailrc.
#

defs = {
    'help' :            0,                  # Leave this alone.
    'dump' :            0,                  # Leave this alone.
    'verbose' :         1,                  # show what is happening

    'getmaildir' :      '~/.getmail/',      # getmail config directory path
                                            #   leading ~[user]/ will be expanded
    'rcfilename' :      'getmailrc',        # getmail control file name

    'timeout' :         180,                # Socket timeout value in seconds
    'port' :            poplib.POP3_PORT,   # POP3 port number
    'use_apop' :        0,                  # Use APOP instead of PASS for
                                            #   authentication

    'readall' :         1,                  # Retrieve all mail, not just new
    'delete' :          0,                  # Do not delete mail after retrieval
    'delete_after' :    0,                  # Delete after X days

    'no_delivered_to' : 0,                  # Don't add Delivered-To: header
    'no_received' :     0,                  # Don't add Received: header
    'eliminate_duplicates' :    0,          # Eliminate duplicate messages
    'max_message_size' :        0,          # Maximum message size to retrieve

    'message_log' :     '',                 # Log info about getmail actions
                                            #   leading ~[user]/ will be expanded
                                            #   Will be prepended with value of
                                            #   getmaildir if message_log is not
                                            #   absolute after ~ expansion.

    'recipient_header' :    [               # Headers to search for local
                            'Delivered-To', #   recipient addresses
                            'Envelope-To',
                            'Apparently-To',
                            'X-Envelope-To',
                            'Resent-To',
                            'Resent-cc',
                            'Resent-bcc',
                            'To',
                            'cc',
                            'bcc',
                            'Received'
                            ],
    'extension_sep' :   '-',                # Extension address separator
    'extension_depth' : 1,                  # Number of local-part pieces to
                                            #   consider part of the base
    }


#
# Globals
#

# For signal handling
getmailobj = None

# name getmail was invoked with
me = None

# Options recognized in configuration getmailrc file
intoptions = ('verbose', 'readall', 'delete', 'timeout', 'use_apop',
    'no_delivered_to', 'no_received', 'eliminate_duplicates',
    'max_message_size', 'delete_after', 'extension_depth')
stringoptions = ('message_log', 'recipient_header', 'extension_sep')

# Exit codes
exitcodes = {
    'OK' : 0,
    'ERROR' : -1
    }

# Names for output logging levels
(TRACE, DEBUG, INFO, WARN, ERROR, FATAL) = range (1, 7)

# Count of deliveries for getmail; used in Maildir delivery
deliverycount = 0

# File object for the message logfile
f_msglog = None

# Line ending conventions
line_end = {
    'pop3' : '\r\n',
    'maildir' : '\n',
    'mbox' : '\n'
    }

res = {
    # Simple re to determine if a string might be an email address
    'mailaddr' : re.compile ('.+@.+\..+'),
    # Regular expression object to escape "From ", ">From ", ">>From ", ...
    # with ">From ", ">>From ", ... in mbox deliveries.  This is for mboxrd format
    # mboxes.
    'escapefrom' : re.compile (r'^(?P<gts>\>*)From ', re.MULTILINE),
    # Regular expression object to find line endings
    'eol' : re.compile (r'\r?\n\s*', re.MULTILINE),
    # Regular expression to do POP3 leading-dot unescapes
    'leadingdot' : re.compile (r'^\.\.', re.MULTILINE),
}

#
# Utility functions
#

#######################################
def log (level=INFO, msg='', opts={'verbose' : 1}):
    if msg and ((level >= INFO and opts['verbose'] > 0) or (opts['verbose'] > 1)):
        if level >= ERROR:
            file = sys.stderr
        else:
            file = sys.stdout
        file.write (msg)
        file.flush ()

#######################################
def msglog (msg='', opts=None, close=0):
    global f_msglog
    if not opts['message_log']:  return
    if msg:
        if not f_msglog:
            filename = os.path.join (opts['getmaildir'],
                os.path.expanduser (opts['message_log']))
            f_msglog = open (filename, 'a')
        f_msglog.write ('%s %s\n' % (string.replace (timestamp (), ' ', '_'),
            string.strip (msg)))
        f_msglog.flush ()
    if f_msglog and close == 1:
        f_msglog.close ()
        f_msglog = None

#######################################
def timestamp ():
    '''Return the current time in a standard format.'''
    t = time.gmtime (time.time ())
    return time.strftime ('%d %b %Y %H:%M:%S -0000', t)

#######################################
def mbox_timestamp ():
    '''Return the current time in the format expected in an mbox From_ line.'''
    return time.asctime (time.gmtime (time.time ()))

#######################################
def format_header (name, line):
    '''Take a long line and return rfc822-style multiline header.
    '''
    header = ''
    # Ensure 'line' is formatted as a single long line, and add header name.
    line = string.strip (name) + ': ' + res['eol'].sub (' ', string.rstrip (line))
    # Split into lines of maximum 78 characters long plus newline, if
    # possible.  A long line may result if no space characters are present.
    while 1:
        l = len (line)
        if l <= 78:  break
        i = string.rfind (line, ' ', 0, 78)
        if i == -1:  break
        if header:  header = header + '\n  '
        header = header + line[:i]
        line = string.lstrip (line[i:])
    if header:  header = header + '\n  '
    header = header + string.lstrip (line) + '\n'
    return header

#######################################
def pop3_unescape (msg):
    '''Do leading dot replacement in retrieved message.
    '''
    return res['leadingdot'].sub ('.', msg)

#######################################
def lock_file (file):
    '''Do fcntl file locking
    '''
    fcntl.flock (file.fileno (), fcntl.LOCK_EX)

#######################################
def unlock_file (file):
    '''Do fcntl file unlocking
    '''
    fcntl.flock (file.fileno (), fcntl.LOCK_UN)

#
# Classes
#

#######################################
class getmailAddressList (rfc822.AddressList):
    '''Override buggy function in rfc822.py implementation of AddrList.
    '''
    ###################################
    def getaddress (self):
        """Parse the next address."""
        self.commentlist = []
        self.gotonext()

        oldpos = self.pos
        oldcl = self.commentlist
        plist = self.getphraselist()

        self.gotonext()
        returnlist = []

        if self.pos >= len(self.field):
            # Bad email address technically, no domain.
            if plist:
                returnlist = [(string.join(self.commentlist), plist[0])]

        elif self.field[self.pos] in '.@':
            # email address is just an addrspec
            # this isn't very efficient since we start over
            self.pos = oldpos
            self.commentlist = oldcl
            addrspec = self.getaddrspec()
            returnlist = [(string.join(self.commentlist), addrspec)]

        elif self.field[self.pos] == ':':
            # address is a group
            returnlist = []

            self.pos = self.pos + 1
            while self.pos < len(self.field):
                if self.field[self.pos] == ';':
                    self.pos = self.pos + 1
                    break
                returnlist = returnlist + self.getaddress()
                self.gotonext()

        elif self.field[self.pos] == '<':
            # Address is a phrase then a route addr
            routeaddr = self.getrouteaddr()

            if self.commentlist:
                returnlist = [(string.join(plist) + ' (' + \
                         string.join(self.commentlist) + ')', routeaddr)]
            else: returnlist = [(string.join(plist), routeaddr)]

        else:
            if plist:
                returnlist = [(string.join(self.commentlist), plist[0])]
            elif self.field[self.pos] in self.specials:
                self.pos = self.pos + 1

        self.gotonext()
        if self.pos < len(self.field) and self.field[self.pos] == ',':
            self.pos = self.pos + 1
        return returnlist

#######################################
class getmail:
    '''pop_processor implements the main logic to retrieve mail from a
    specified POP3 server and account, and deliver retrieved mail to the
    appropriate Maildir(s) and/or mbox file(s).
    '''

    ###################################
    def __init__ (self, account, opts, users, logfunc=log):
        global getmailobj
        self.logfunc = logfunc
        accountcopy = account.copy ()
        if accountcopy.has_key ('password'):
            accountcopy['password'] = '*' * len (accountcopy['password'])
        self.logfunc (TRACE, '__init__():  account="%s", opts="%s", '
            'users="%s"\n' % (accountcopy, opts, users), opts)
        self.timestamp = int (time.time ())
        for key in ('server', 'port', 'username', 'password'):
            if not account.has_key (key):
                raise getmailConfigException, \
                    'account missing key (%s)' % key

        self.account = account.copy ()
        self.account['shorthost'] = string.split (self.account['server'], '.')[0]
        try:
            self.account['ipaddr'] = socket.gethostbyname (self.account['server'])
        except socket.error, txt:
            # Network unreachable, PPP down, etc
            raise getmailNetworkError, 'network error (%s)' % txt

        msglog ('getmail started for %(username)s@%(server)s:%(port)i' \
                % self.account, opts)

        for key in ('readall', 'delete'):
            if not opts.has_key (key):
                raise getmailConfigException, 'opts missing key (' + key + \
                    ') for %(username)s@%(server)s:%(port)i' % self.account
        self.opts = opts

        timeoutsocket.setDefaultSocketTimeout (self.opts['timeout'])

        try:
            # Get default delivery target (postmaster) -- first in list
            self.default_delivery = os.path.expanduser (users[0][1])
            del users[0]
        except Exception, txt:
            raise getmailConfigException, \
                'no default delivery for %(username)s@%(server)s:%(port)i' \
                % self.account

        # Construct list of (re_obj, delivery_target) pairs
        self.users = []
        for (re_s, target) in users:
            self.users.append ( {'re' : re.compile (re_s, re.IGNORECASE),
                'target' : os.path.expanduser (target)} )
            self.logfunc (TRACE, '__init__():  User #%i:  re="%s", target="%s"\n'
                % (len (self.users), re_s, self.users[-1]['target']), self.opts)

        self.oldmail_filename = os.path.join (
            os.path.expanduser (self.opts['getmaildir']),
            'oldmail-%(server)s-%(port)i-%(username)s' % self.account)
        self.oldmail = self.read_oldmailfile ()

        # Misc. info
        self.info = {}
        # Store local hostname plus short version
        self.info['hostname'] = socket.gethostname ()
        self.info['shorthost'] = string.split (self.info['hostname'], '.')[0]
        self.info['pid'] = os.getpid ()
        self.info['msgcount'] = 0
        self.info['localscount'] = 0
        getmailobj = self
        self.msgs_delivered = {}

    ###################################
    def __del__ (self):
        try:
            msglog ('getmail finished for %(username)s@%(server)s:%(port)i' \
                    % self.account, self.opts)
            msglog ('', self.opts, close=1)
            timeoutsocket.setDefaultSocketTimeout (defs['timeout'])
        except:
            pass

    ###################################
    def read_oldmailfile (self):
        '''Read contents of oldmail file.'''
        oldmail = {}
        try:
            f = open (self.oldmail_filename, 'r')
            lock_file (f)
            for line in f.readlines ():
                line = string.strip (line)
                msgid, timestamp = string.split (line, '\0', 1)
                oldmail[msgid] = int (timestamp)
            unlock_file (f)
            f.close ()
            self.logfunc (TRACE, 'read_oldmailfile():  read %i' % len (oldmail)
                + ' uids for %(server)s:%(username)s\n' % self.account,
                self.opts)
        except IOError:
            self.logfunc (TRACE, 'read_oldmailfile():  no oldmail file for '
                '%(server)s:%(username)s\n' % self.account, self.opts)
        return oldmail

    ###################################
    def write_oldmailfile (self, cur_messages):
        '''Write oldmail info to oldmail file.'''
        try:
            f = open (self.oldmail_filename, 'w')
            lock_file (f)
            for msgid, timestamp in self.oldmail.items ():
                if msgid in cur_messages:
                    # This message still in inbox; remember it for next time.
                    f.write ('%s\0%i\n' % (msgid, timestamp))
                #else:
                # Message doesn't exist in inbox, no sense remembering it.
            unlock_file (f)
            f.close ()
            self.logfunc (TRACE, 'write_oldmailfile():  wrote %i'
                % len (self.oldmail)
                + ' uids for %(server)s:%(username)s\n' % self.account,
                self.opts)
        except IOError, txt:
            self.logfunc (TRACE, 'write_oldmailfile():  failed '
                'writing oldmail file for %(server)s:%(username)s'
                % self.account + ' (%s)\n' % txt, self.opts)

    ###################################
    def connect (self):
        '''Connect to POP3 server.'''
        try:
            session = poplib.POP3 (self.account['server'], self.account['port'])
            self.logfunc (INFO, '%(server)s:  POP3 session initiated on port %(port)s for "%(username)s"\n'
                    % self.account, self.opts)
            self.logfunc (INFO, '%(server)s:' % self.account
                + '  POP3 greeting:  %s\n' % session.welcome, self.opts)
            msglog ('POP3 connect for %(username)s on %(server)s:%(port)i'
                % self.account + ' (%s)' % session.welcome, self.opts)
        except Timeout, txt:
            txt = 'Timeout connecting to %(server)s' % self.account
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('timeout during POP3 connect for %(username)s on %(server)s:%(port)i'
                % self.account, self.opts)
            raise getmailTimeoutException, txt
        except poplib.error_proto, response:
            txt = '%(server)s:' % self.account \
                + '  connect failed (%s)' % response
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('POP3 connect failed for %(username)s on %(server)s:%(port)i'
                % self.account + ' (%s)' % response, self.opts)
            raise getmailProtoException, txt
        except socket.error, txt:
            txt = 'Socket exception connecting to %(server)s' % self.account \
                + ' (%s)' % txt
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('socket error during POP3 connect for %(username)s on %(server)s:%(port)i'
                % self.account + ' (%s)' % txt, self.opts)
            raise getmailSocketException, txt
        except KeyboardInterrupt:
            raise
        except Exception, txt:
            txt = 'Unknown exception connecting to %(server)s' % self.account \
                + ' (%s)' % txt
            self.logfunc (FATAL, txt + '\n', self.opts)
            msglog ('unknown error during POP3 connect for %(username)s on %(server)s:%(port)i'
                % self.account + ' (%s)' % txt, self.opts)
            raise getmailUnhandledException, txt

        return session

    ###################################
    def login (self):
        '''Issue the POP3 USER and PASS directives.'''
        try:
            logged_in = 0
            if self.opts['use_apop']:
                try:
                    rc = self.session.apop (self.account['username'],
                        self.account['password'])
                    self.logfunc (INFO, '%(server)s:' % self.account
                        + '  POP3 APOP response:  %s\n' % rc, self.opts)
                    logged_in = 1
                except poplib.error_proto:
                    self.logfunc (WARN, 'Warning:  server does not support '
                        'APOP authentication, trying USER/PASS...\n', self.opts)
            if not logged_in:
                rc = self.session.user (self.account['username'])
                self.logfunc (INFO, '%(server)s:' % self.account
                    + '  POP3 user response:  %s\n' % rc, self.opts)
                rc = self.session.pass_ (self.account['password'])
                self.logfunc (INFO, '%(server)s:' % self.account
                    + '  POP3 PASS response:  %s\n' % rc, self.opts)
            msglog ('POP3 login successful', self.opts)
        except Timeout, txt:
            txt = 'Timeout during login to %(server)s' % self.account
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('timeout during POP3 login', self.opts)
            raise getmailTimeoutException, txt
        except poplib.error_proto, response:
            txt = '%(server)s:' % self.account + '  login failed (%s)' % response
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('POP3 login failed (%s)' % response, self.opts)
            raise getmailProtoException, txt
        except socket.error, txt:
            txt = 'Socket exception during POP3 login with %(server)s' \
                % self.account + ' (%s)' % txt
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('socket error during POP3 login (%s)' % txt, self.opts)
            raise getmailSocketException, txt
        except KeyboardInterrupt:
            raise
        except Exception, txt:
            txt = 'Unknown exception during login to %(server)s' \
                % self.account + ' (%s)' % txt
            self.logfunc (ERROR, txt + '\n', self.opts)
            msglog ('unknown error during POP3 login (%s)' % txt, self.opts)
            raise getmailUnhandledException, txt

        return rc

    ###################################
    def get_msglist (self):
        '''Retrieve message list for this user.'''
        try:
            response = self.session.list ()
            rc, msglist_txt = response[0:2]
            self.logfunc (INFO, '%(server)s:' % self.account
                + '  POP3 list response:  %s\n' % rc, self.opts)
            msglog ('POP3 list (%s)' % rc, self.opts)
        except Timeout, txt:
            txt = 'Timeout retrieving message list from %(server)s' % self.account
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('timeout during POP3 list', self.opts)
            raise getmailTimeoutException, txt
        except poplib.error_proto, response:
            txt = '%(server)s:' % self.account + '  list failed (%s)' % response
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('POP3 list failed (%s)' % response, self.opts)
            raise getmailProtoException, txt
        except socket.error, txt:
            txt = 'Socket exception during POP3 session with %(server)s' \
                % self.account + ' (%s)' % txt
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('socket error during POP3 list (%s)' % txt, self.opts)
            raise getmailSocketException, txt
        except KeyboardInterrupt:
            raise
        except Exception, txt:
            txt = 'Unknown exception for list command on %(server)s' \
                % self.account + ' (%s)' % txt
            self.logfunc (ERROR, txt + '\n', self.opts)
            msglog ('unknown error during POP3 list (%s)' % txt, self.opts)
            raise getmailUnhandledException, txt
        msglist = []
        for s in msglist_txt:
            # Handle broken POP3 servers which return something after the length
            msgnum, msginfo = string.split (s, None, 1)
            try:
                msgnum = int (msgnum)
            except ValueError, txt:
                self.logfunc (ERROR, 'Error:  POP3 server violates RFC1939 '
                    + '("%s"), skipping line...\n' % s, self.opts)
                continue
            # Keep track of length of message
            try:
                msglen = int (string.split (msginfo)[0])
            except:
                msglen = 0
            msglist.append ( (msgnum, msglen) )
        msglist.append ( (None, None) )
        return msglist

    ###################################
    def report_mailbox_size (self):
        '''Retrieve mailbox size for this user.'''
        try:
            msgs, octets = self.session.stat ()
            self.logfunc (INFO, '%(server)s:' % self.account
                + '  POP3 stat response:  %i messages, %i octets\n' % (msgs, octets), self.opts)
        except Timeout, txt:
            txt = 'Timeout during POP3 stat from %(server)s' % self.account
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('timeout during POP3 stat', self.opts)
            raise getmailTimeoutException, txt
        except socket.error, txt:
            txt = 'Socket exception during POP3 session with %(server)s' \
                % self.account + ' (%s)' % txt
            self.logfunc (DEBUG, txt + '\n', self.opts)
            msglog ('socket error during POP3 stat (%s)' % txt, self.opts)
            raise getmailSocketException, txt
        except KeyboardInterrupt:
            raise
        except:
            # Other problems are non-fatal, just ignore them.
            pass

    ###################################
    def extract_recipients (self, mess822):
        recipients = {}
        header_types = self.opts['recipient_header']
        if type (header_types) != type ([]):
            header_types = [header_types]
        for header_type in header_types:
            self.logfunc (TRACE, 'extract_recipients():  parsing header "%s"\n'
                % header_type, self.opts)
            # Handle Received: headers specially
            if string.lower (header_type) == 'received':
                # Construct list of strings, one Received: header per string
                raw_received = mess822.getallmatchingheaders ('received')
                received = []
                current_line = ''
                for line in raw_received:
                    if line[0] not in string.whitespace:
                        if string.strip (current_line):
                            received.append (current_line)
                        current_line = line
                    else:
                        current_line = current_line + ' ' + string.strip (line)
                if string.strip (current_line):
                    received.append (current_line)

                # Process each reconstructed Received: header
                for line in received:
                    recips = getmailAddressList (line).addresslist
                    for (name, address) in recips:
                        if address and res['mailaddr'].search (address):
                            # Looks like an email address, keep it
                            recipients[string.lower (address)] = None
                            self.logfunc (TRACE,
                                'extract_recipients():  found address "%s"\n'
                                % address, self.opts)

            elif mess822.has_key (header_type):
                recips = mess822.getaddrlist (header_type)
                for (name, address) in recips:
                    if address and res['mailaddr'].search (address):
                        # Looks like an email address, keep it
                        recipients[string.lower (address)] = None
                        self.logfunc (TRACE,
                            'extract_recipients():  found address "%s"\n'
                            % address, self.opts)
        self.logfunc (TRACE,
            'extract_recipients():  found %i recipients\n'
            % len (recipients.keys ()), self.opts)

        return recipients.keys ()

    ###################################
    def process_msg (self, msg):
        '''Process retrieved message and deliver to appropriate recipients.'''

        # Extract envelope sender address from last Return-Path: header
        f = cStringIO.StringIO (msg)
        mess = rfc822.Message (f)
        addrlist = mess.getaddrlist ('return-path')
        msgid = mess.get ('message-id', 'None')
        if addrlist:
            env_sender = addrlist[0][1]
        else:
            # No Return-Path: header
            self.logfunc (DEBUG, 'no Return-Path: header in message\n',
                self.opts)
            env_sender = '<#@[]>'
        # Export envelope sender address to environment
        os.environ['SENDER'] = env_sender or ''

        self.logfunc (TRACE, 'process_msg():  found envelope sender "%s"\n'
            % env_sender, self.opts)

        if len (self.users):
            # Extract possible recipients
            recipients = self.extract_recipients (mess)
            msglog ('new message "%s": from <%s>, to: %s'
                % (msgid, env_sender, string.join (recipients, ', ')[:80]),
                self.opts)

        else:
            # No local configurations, just send to postmaster
            recipients = []
            msglog ('new message "%s": from <%s>' % (msgid, env_sender),
                self.opts)

        count = self.do_deliveries (recipients, msg, msgid, env_sender)

        if count == 0:
            # Made no deliveries of this message; send it to the default delivery
            # target.
            dt = self.deliver_msg (self.default_delivery,
                self.message_add_info (msg,
                    'postmaster@%(hostname)s' % self.info),
                 env_sender)
            msglog ('delivered to default %s' % dt, self.opts)

        self.logfunc (TRACE, 'process_msg():  do_deliveries did %i deliveries\n'
            % count, self.opts)

        msglog ('finished message:  %i local recipients' % count, self.opts)

        return count

    #######################################
    def do_deliveries (self, recipients, msg, msgid, env_sender):
        '''Determine which configured local recipients to send a copy of this
        message to, and dispatch to the deliver_msg() method.
        '''
        delivered = 0

        try:
            body_start = string.index (msg, line_end['pop3'] * 2)
        except ValueError:
            self.logfunc (TRACE, 'do_deliveries():  message appears to have no body',
                self.opts)
            body_start = 0
        digestobj = sha.new (msg[body_start:])
        digest = digestobj.digest ()
        self.logfunc (TRACE, 'do_deliveries():  msgid "%s", message digest "%s", body "%s..."'
            % (msgid, digestobj.hexdigest (), msg[body_start:body_start + 40]),
            self.opts)

        # Test each recipient address against the compiled regular expression
        # objects for each configured user for this POP3 mailbox.  If the
        # recipient address matches a given user's re, deliver at most one copy
        # to the target associated with that re.
        for user in self.users:
            do_delivery = 0
            self.logfunc (TRACE, 'do_deliveries():  checking user re "%s"'
                % user['re'].pattern + ', target "%s"\n' % user['target'],
                self.opts)
            for recipient in recipients:
                if user['re'].match (recipient):
                    self.logfunc (TRACE,
                        'do_deliveries():  user re matched recipient "%s"\n'
                        % recipient, self.opts)
                    do_delivery = 1

                    # Export the envelope recipient address to the environment
                    os.environ['RECIPIENT'] = recipient
                    # Try to determine the address extension of the recipient
                    # address.  Export it to the environment.
                    os.environ['EXT'] = ''
                    try:
                        local_part = recipient[:string.rindex (recipient, '@')]
                        parts = string.split (local_part, self.opts['extension_sep'], self.opts['extension_depth'])
                        if len (parts) == self.opts['extension_depth'] + 1:
                            os.environ['EXT'] = parts[-1]
                    except ValueError:
                        pass

                    # Stop as soon as we match a recipient address
                    break

            if do_delivery:
                if self.opts['eliminate_duplicates']:
                    if self.msgs_delivered.has_key (digest):
                        if user['target'] in self.msgs_delivered[digest]:
                            # Never deliver multiple copies of a message to same destination
                            self.logfunc (TRACE,
                                'do_deliveries():  already delivered to target "%(target)s", skipping...\n'
                                % user, self.opts)
                            do_delivery = 0
                            # Add a delivery, so it doesn't go to postmaster
                            delivered = delivered + 1
                            # Skip to next local user
                            continue

                        else:
                            # Deliver to this recipient and keep track
                            self.msgs_delivered[digest].append (user['target'])

                    else:
                        # First recipient of this message, keep track
                        self.msgs_delivered[digest] = [user['target']]

                # Deliver the message to this user
                dt = self.deliver_msg (user['target'],
                    self.message_add_info (msg, recipient), env_sender)
                msglog ('delivered to %s for <%s>' % (dt, recipient),
                    self.opts)
                self.logfunc (TRACE,
                    'do_deliveries():  delivered to "%(target)s"\n'
                    % user, self.opts)
                delivered = delivered + 1

        return delivered

    #######################################
    def deliver_msg (self, dest, msg, env_sender):
        '''Determine the type of destination and dispatch to appropriate
        delivery routine.  Currently understands Maildirs and mboxrd-style mbox
        files.  The destination must exist; i.e. getmail will not create an mbox
        file if the specified destination does not exist.  `touch` the file
        first if you want to deliver to an empty mbox file.
        '''
        if not dest:
            raise getmailDeliveryException, 'destination is blank'

        # Handle command delivery first
        if dest[0] == '|':
            dest = dest[1:]
            # Ensure command exists
            cmd = string.split (dest)[0]
            if not os.path.exists (cmd):
                raise getmailDeliveryException, \
                    'destination command "%s" does not exist' % cmd
            return self.deliver_command (dest, msg, env_sender)

        # Ensure destination path exists
        if not os.path.exists (dest):
            raise getmailDeliveryException, \
                'destination "%s" does not exist' % dest

        # If destination ends with '/', assume Maildir delivery
        if dest[-1] == '/':
            return self.deliver_maildir (dest, msg)

        # Refuse to deliver to an mbox if it's a symlink, to prevent symlink
        # attacks.
        if os.path.islink (dest):
            raise getmailDeliveryException, \
                'destination "%s" is a symlink' % dest

        # If destination is a regular file, try an mbox delivery
        if os.path.isfile (dest):
            return self.deliver_mbox (dest, msg, env_sender)

        # Unknown destination type
        raise getmailDeliveryException, \
            'destination "%s" is not a Maildir or mbox' % dest

    ###################################
    def message_add_info (self, message, recipient):
        '''Add Delivered-To: and Received: info to headers of message.
        '''
        # Extract local_part of recipient address
        localsep = string.rfind (recipient, '@')
        if localsep == -1:
            _local = recipient
        else:
            _local = recipient[:localsep]

        if self.opts['no_delivered_to']:
            delivered_to = ''
        else:
            # Construct Delivered-To: header with address local_part@localhostname
            delivered_to = format_header ('Delivered-To',
                '%s@%s\n' % (_local, self.info['hostname']))

        if self.opts['no_received']:
            received = ''
        else:
            # Construct Received: header
            info = 'from %(server)s (%(ipaddr)s)' % self.account \
                + ' by %(hostname)s' % self.info \
                + ' with POP3 for <%s>; ' % recipient \
                + timestamp ()
            received = format_header ('Received', info)

        return delivered_to + received + message

    #######################################
    def deliver_maildir (self, maildir, msg):
        'Reliably deliver a mail message into a Maildir.'
        # Uses Dan Bernstein's recommended naming convention for maildir
        # delivery.  See http://cr.yp.to/proto/maildir.html for details.
        global deliverycount
        self.info['time'] = int (time.time ())
        self.info['deliverycount'] = deliverycount
        filename = '%(time)s.%(pid)s_%(deliverycount)s.%(hostname)s' % self.info

        # Set a 24-hour alarm for this delivery
        signal.signal (signal.SIGALRM, alarm_handler)
        signal.alarm (24 * 60 * 60)

        dir_tmp = os.path.join (maildir, 'tmp')
        dir_new = os.path.join (maildir, 'new')
        if not (os.path.isdir (dir_tmp) and os.path.isdir (dir_new)):
            raise getmailDeliveryException, 'not a Maildir (%s)' % maildir

        fname_tmp = os.path.join (dir_tmp, filename)
        fname_new = os.path.join (dir_new, filename)

        # File must not already exist
        if os.path.exists (fname_tmp):
            raise getmailDeliveryException, fname_tmp + 'already exists'
        if os.path.exists (fname_new):
            raise getmailDeliveryException, fname_new + 'already exists'

        # Get user & group of maildir
        s_maildir = os.stat (maildir)
        maildir_owner = s_maildir[stat.ST_UID]
        maildir_group = s_maildir[stat.ST_GID]

        # Open file to write
        try:
            f = open (fname_tmp, 'wb')
            try:
                os.chown (fname_tmp, maildir_owner, maildir_group)
            except OSError:
                # Not running as root, can't chown file
                pass
            os.chmod (fname_tmp, 0600)
            f.write (string.replace (msg, line_end['pop3'], line_end['maildir']))
            f.flush ()
            os.fsync (f.fileno())
            f.close ()

        except IOError:
            raise getmailDeliveryException, 'failure writing file ' + fname_tmp

        # Move message file from Maildir/tmp to Maildir/new
        try:
            os.link (fname_tmp, fname_new)
            os.unlink (fname_tmp)

        except OSError:
            try:
                os.unlink (fname_tmp)
            except:
                pass
            raise getmailDeliveryException, 'failure renaming "%s" to "%s"' \
                   % (fname_tmp, fname_new)

        # Delivery done

        # Cancel alarm
        signal.alarm (0)
        signal.signal (signal.SIGALRM, signal.SIG_DFL)

        self.logfunc (TRACE, 'deliver_maildir():  delivered to Maildir "%s"\n'
            % maildir, self.opts)

        deliverycount = deliverycount + 1
        return 'Maildir "%s"' % maildir

    #######################################
    def deliver_mbox (self, mbox, msg, env_sender):
        'Deliver a mail message into an mbox file.'

        global deliverycount
        # Construct mboxrd-style 'From_' line
        delivery_date = mbox_timestamp ()
        fromline = 'From %s %s\n' % (env_sender, delivery_date)

        try:
            # Open mbox file
            f = open (mbox, 'rb+')
            lock_file (f)
            status_old = os.fstat (f.fileno())
            # Check if it _is_ an mbox file
            # mbox files must start with "From " in their first line, or
            # are 0-length files.
            f.seek (0, 0)                   # Seek to start
            first_line = f.readline ()
            if first_line != '' and first_line[:5] != 'From ':
                # Not an mbox file; abort here
                unlock_file (f)
                f.close ()
                raise getmailDeliveryException, \
                    'destination "%s" is not an mbox file' % mbox

            f.seek (0, 2)                   # Seek to end
            f.write (fromline)

            # Replace lines beginning with "From ", ">From ", ">>From ", ...
            # with ">From ", ">>From ", ">>>From ", ...
            msg = res['escapefrom'].sub ('>\g<gts>From ', msg)
            # Add trailing newline if last line incomplete
            if msg[-1] != '\n':  msg = msg + '\n'

            # Write out message
            f.write (string.replace (msg, line_end['pop3'], line_end['mbox']))
            # Add trailing blank line
            f.write ('\n')
            f.flush ()
            os.fsync (f.fileno())
            # Unlock and close file
            status_new = os.fstat (f.fileno())
            unlock_file (f)
            f.close ()
            # Reset atime
            os.utime (mbox, (status_old[stat.ST_ATIME], status_new[stat.ST_MTIME]))

        except IOError, txt:
            try:
                unlock_file (f)
                f.close ()
            except:
                pass
            raise getmailDeliveryException, \
                'failure writing message to mbox file "%s" (%s)' % (mbox, txt)

        # Delivery done
        self.logfunc (TRACE, 'deliver_mbox():  delivered to mbox "%s"\n'
            % mbox, self.opts)

        deliverycount = deliverycount + 1
        return 'mbox file "%s"' % mbox

    #######################################
    def deliver_command (self, command, msg, env_sender):
        'Deliver a mail message to a command.'
        global deliverycount

        # At least some security...
        if os.geteuid () == 0:
            raise getmailDeliveryException, 'refuse to deliver to commands as root'

        # Construct mboxrd-style 'From_' line
        delivery_date = mbox_timestamp ()
        fromline = 'From %s %s\n' % (env_sender, delivery_date)

        self.logfunc (TRACE, 'deliver_command():  delivering to command "%s"\n'
            % command, self.opts)

        try:
            import popen2

            popen2._cleanup()
            cmd = popen2.Popen3 (command, 1, bufsize=-1)
            cmdout, cmdin, cmderr = cmd.fromchild, cmd.tochild, cmd.childerr
            cmdin.write (fromline)
            cmdin.write (string.replace (msg, line_end['pop3'], line_end['mbox']))
            # Add trailing blank line
            cmdin.write ('\n')
            cmdin.flush ()
            cmdin.close ()

            r = cmd.wait ()
            err = string.strip (cmderr.read ())
            cmderr.close ()
            out = string.strip (cmdout.read ())
            cmdout.close ()

            if err or r:
                if r and os.WIFEXITED (r):
                    exitcode = 'exited %i' % os.WEXITSTATUS (r)
                    if os.WIFSIGNALED (r):
                        exitsignal = 'signal %i' % os.WTERMSIG (r)
                    else:
                        exitsignal = 'no signal'
                else:
                    exitcode = 'no exit?'
                    exitsignal = ''
                raise getmailDeliveryException, 'command "%s" %s %s (%s)' \
                     % (command, exitcode, exitsignal, err)
            if out:
                # Command wrote something to stdout
                self.logfunc (INFO, 'command "%s" said "%s"' % (command, out),
                    self.opts)
                msglog (INFO, 'command "%s" said "%s"' % (command, out),
                    self.opts)

        except ImportError:
            raise getmailDeliveryException, 'popen2 module not found'

        except getmailDeliveryException:
            raise

        except Exception, txt:
            raise getmailDeliveryException, \
                'failure delivering message to command "%s" (%s)' % (command, txt)

        # Delivery done
        self.logfunc (TRACE, 'deliver_command():  delivered to command "%s"\n'
            % command, self.opts)

        deliverycount = deliverycount + 1
        return 'command "%s"' % command

    ###################################
    def abort (self, txt):
        '''Some error has occurred after logging in to POP3 server.  Reset the
        server and close the session cleanly if possible.'''

        self.logfunc (WARN, 'Resetting connection and aborting...\n', self.opts)
        msglog ('Aborting... (%s)' % txt, self.opts)

        # Ignore exceptions with this session, as abort() is invoked after
        # errors are already detected.
        try:
            self.session.rset ()
        except:
            pass
        try:
            self.session.quit ()
        except:
            pass

    ###################################
    def go (self):
        '''Main method to retrieve mail from one POP3 account, process it,
        and deliver it to appropriate local recipients.'''
        # Establish POP3 connection
        try:
            # Establish POP3 connection
            self.session = self.connect ()
            # Log in to server
            self.login ()
            # Let the user know what they're in for
            self.report_mailbox_size ()
            # Retrieve message list for this user.
            msglist = self.get_msglist ()
        except (getmailException, Timeout), txt:
            # Failed to connect; return to skip this user.
            self.logfunc (WARN, 'failed to retrieve message list '
                'for "%(username)s"' % self.account + ' (%s)\n' % txt,
                self.opts)
            self.abort (txt)
            return

        max_message_size = self.opts['max_message_size']
        # Process messages in list
        try:
            inbox = []
            for (msgnum, msglen) in msglist:
                if msgnum == msglen == None:
                    # No more messages; POP3.list() returns a final int
                    self.logfunc (INFO, '%(server)s:  finished retrieving messages\n'
                        % self.account, self.opts)
                    break
                self.logfunc (INFO, '  msg #%i/%i : len %s ... '
                    % (msgnum, len (msglist) - 1, msglen), self.opts)
                if msglen and max_message_size and msglen > max_message_size:
                    self.logfunc (INFO, 'over max message size of %i, skipping ...\n'
                        % max_message_size, self.opts)
                    msglog ('message #%i over max message size of %i, skipping ...\n'
                        % (msgnum, max_message_size), self.opts)
                    continue

                try:
                    rc = self.session.uidl (msgnum)
                    self.logfunc (TRACE, 'UIDL response "%s" ... ' % rc, self.opts)
                    msgid = string.strip (string.split (rc, ' ', 2)[2])
                    # Append msgid to list of current inbox contents
                    inbox.append (msgid)
                except poplib.error_proto, txt:
                    msgid = None
                    self.logfunc (WARN, 'POP3 server failed UIDL command' \
                        ' (%s), retrieving message ... ' % txt, self.opts)

                # Retrieve this message if:
                #   "get all mail" option is set, OR
                #   server does not support UIDL (msgid is None), OR
                #   this is a new message (not in oldmail)
                if self.opts['readall'] or msgid is None \
                    or not self.oldmail.has_key (msgid):
                    rc, msglines, octets = self.session.retr (msgnum)
                    msg = string.join (msglines, line_end['pop3'])
                    self.logfunc (INFO, 'retrieved', self.opts)
                    msglog ('retrieved message "%s"\n' % msgid, self.opts)
                    self.info['msgcount'] = self.info['msgcount'] + 1
                    msg = pop3_unescape (msg)

                    # Find recipients for this message and deliver to them.
                    count = self.process_msg (msg)
                    if count == 0:
                        self.logfunc (INFO, ' ... delivered to postmaster',
                            self.opts)
                        count = 1
                    elif count == 1:
                        self.logfunc (INFO, ' ... delivered 1 copy', self.opts)
                    else:
                        self.logfunc (INFO, ' ... delivered %i copies' % count,
                            self.opts)

                    self.info['localscount'] = self.info['localscount'] + count

                else:
                    self.logfunc (INFO, 'previously retrieved ...',
                        self.opts)
                    msglog ('message "%s" previously retrieved ...'
                        % msgid, self.opts)

                # Delete this message if the "delete" or "delete_after" options
                # are set
                if self.opts['delete']:
                    rc = self.session.dele (msgnum)
                    self.logfunc (INFO, ', deleted', self.opts)
                    msglog (' deleted', self.opts)
                    # Remove msgid from list of current inbox contents
                    if msgid is not None:  del inbox[-1]
                if self.opts['delete_after']:
                    if self.oldmail.get (msgid, None):
                        self.logfunc (TRACE, ' originally seen %s'
                            % time.strftime ('%Y-%m-%d %H:%M:%S',
                            time.localtime (self.oldmail[msgid])),
                            self.opts)
                    else:
                        self.logfunc (TRACE, ' not previously seen', self.opts)
                    if self.oldmail.has_key (msgid) and self.oldmail[msgid] < (self.timestamp - self.opts['delete_after'] * 86400):
                        rc = self.session.dele (msgnum)
                        self.logfunc (INFO, ' ... older than %i days, deleted'
                            % self.opts['delete_after'], self.opts)
                        msglog (' ... older than %i days, deleted'
                            % self.opts['delete_after'], self.opts)
                        # Remove msgid from list of current inbox contents
                        if msgid is not None:  del inbox[-1]

                if msgid is not None and not self.oldmail.get (msgid, None):
                    self.oldmail[msgid] = self.timestamp
                # Finished delivering this message
                self.logfunc (INFO, '\n', self.opts)
                msglog ('\n', self.opts)

            # Done processing messages; process oldmail contents
            self.write_oldmailfile (inbox)

            # Close session and display summary
            self.session.quit ()
            self.logfunc (INFO,
                '%(server)s:  POP3 session completed for "%(username)s"\n'
                % self.account, self.opts)
            self.logfunc (INFO,
                '%(server)s:' % self.account
                + '  retrieved %(msgcount)i messages for %(localscount)i local recipients\n'
                % self.info, self.opts)

        except (getmailException, Timeout), txt:
            # Failed to process a message; return to skip this user.
            self.logfunc (WARN, 'failed to process message list for "%(username)s"'
                    % self.account + ' (%s)\n' % txt, self.opts)
            self.abort (txt)

        except poplib.error_proto, txt:
            # Server isn't speaking POP3?
            self.logfunc (WARN, 'POP3 protocol error; possible POP3 server bug, skipping user "%(username)s"'
                    % self.account + ' (%s)\n' % txt, self.opts)
            self.abort (txt)

        except socket.error, txt:
            txt = 'Socket error during session with %(server)s' % self.account \
                + ' (%s)' % txt
            self.logfunc (WARN, txt + '\n', self.opts)
            msglog ('socket error during session for %(username)s on %(server)s:%(port)i'
                % self.account + ' (%s)' % txt, self.opts)
            self.abort (txt)

        except MemoryError:
            txt = 'Memory exhausted during session with %(server)s' % self.account
            self.logfunc (WARN, txt + '\n', self.opts)
            msglog ('Memory exhausted during session for %(username)s on %(server)s:%(port)i'
                % self.account, self.opts)
            self.abort ('Out of memory')

###################################
def alarm_handler (dummy, unused):
    '''Handle an alarm (should never happen).'''
    getmailobj.abort ('Maildir delivery timeout')

#
# Main script code and helper functions
#

#######################################
def blurb ():
    print
    print 'getmail v.%s - POP3 mail retriever with reliable Maildir and mbox delivery.' \
        % __version__
    print '  (ConfParser version %s)' % ConfParser.__version__,
    try:
        import timeoutsocket
        result = re.search (r'\d+\.\d+', timeoutsocket.__version__)
        if result:
            print '(timeoutsocket version %s)' % result.group (),
        else:
            print '(timeoutsocket version ?)',
    except ImportError:
        pass
    print '\n'
    print 'Copyright (C) 2001 Charles Cazabon <getmail @ discworld.dyndns.org>'
    print 'Licensed under the GNU General Public License version 2.  See the file'
    print 'COPYING for details.'
    print

#######################################
def help (ec=exitcodes['ERROR']):
    blurb ()
    print 'Usage:  %s [options]' % me
    print
    print 'Options:'
    print '  -h or --help                      this text'
    print '  -g or --getmaildir <dir>          use <dir> for getmail data directory'
    print '                                      (default:  %(getmaildir)s)' \
        % defs
    print '  -r or --rcfile <filename>         use <filename> for getmailrc file'
    print '                                      (default:  <getmaildir>/%(rcfilename)s)' \
        % defs
    print '  -t or --timeout <secs>            set socket timeout to <secs> seconds'
    print '                                      (default:  %(timeout)i seconds)' \
        % defs
    print '  --dump                            dump configuration and quit (debugging)'
    print
    print 'The following options override those specified in any getmailrc file.'
    print 'If contradictory options are specified (i.e. --delete and --dont-delete),'
    print 'the last one one is used.'
    print
    print '  -d or --delete                    delete mail after retrieving'
    print '  -l or --dont-delete               leave mail on server after retrieving'
    if defs['delete']:
        print '                                      (default:  delete)'
    else:
        print '                                      (default:  leave on server)'
    print '  -a or --all                       retrieve all messages'
    print '  -n or --new                       retrieve only unread messages'
    if defs['readall']:
        print '                                      (default:  all messages)'
    else:
        print '                                      (default:  new messages)'
    print '  -v or --verbose                   be verbose during operation'
    print '  -q or --quiet                     be quiet during operation'
    if defs['verbose']:
        print '                                      (default:  verbose)'
    else:
        print '                                      (default:  quiet)'
    print '  -m or --message-log <file>        log mail info to <file>'
    print
    sys.exit (ec)

#######################################
def read_configfile (filename, overrides):
    '''Read in configuration file and extract configuration information.
    '''
    # Resulting list of configurations
    configs = []

    if not os.path.isfile (filename):
        return None

    s = os.stat (filename)
    mode = stat.S_IMODE (s[stat.ST_MODE])
    if (mode & 022):
        raise getmailConfigException, 'file is group- or world-writable'

    # Instantiate configuration file parser
    conf = ConfParser.ConfParser (defs)

    try:
        conf.read (filename)
        sections = conf.sections ()

        # Read options from config file
        options = {}
        for key in intoptions + stringoptions:
            try:
                if key in intoptions:
                    options[key] = conf.getint ('default', key)
                else:
                    options[key] = conf.get ('default', key)
            except ConfParser.NoOptionError:
                options[key] = defs[key]

        # Apply commandline overrides to options
        options.update (overrides)

        # Remainder of sections are accounts to retrieve mail from.
        for section in sections:
            account, loptions, locals = {}, {}, []

            # Read required parameters
            for item in ('server', 'port', 'username'):
                try:
                    if item == 'port':
                        account[item] = conf.getint (section, item)
                    else:
                        account[item] = conf.get (section, item)
                except ConfParser.NoOptionError, txt:
                    raise getmailConfigException, \
                        'section [%s] missing required option (%s)' \
                        % (section, item)

            # Read in password if supplied; otherwise prompt for it.
            try:
                account['password'] = conf.get (section, 'password')
            except ConfParser.NoOptionError, txt:
                try:
                    account['password'] = getpass.getpass (
                        'Enter password for %(username)s@%(server)s:%(port)s :  '
                        % account)
                except KeyboardInterrupt:
                    log (INFO, '\nUser aborted.  Exiting...\n')
                    sys.exit (exitcodes['OK'])

            # Read integer options
            for item in intoptions:
                loptions[item] = conf.getint (section, item)

            # Read string options
            for item in stringoptions:
                loptions[item] = conf.get (section, item)

            # Apply commandline overrides to loptions
            loptions.update (overrides)

            # Read local user regex strings and delivery targets
            try:
                locals.append ( (None, conf.get (section, 'postmaster')) )
            except ConfParser.NoOptionError, txt:
                raise getmailConfigException, \
                    'section [%s] missing required option (postmaster)' \
                    % section

            try:
                conflocals = conf.get (section, 'local')
            except ConfParser.NoOptionError:
                conflocals = []
            if type (conflocals) != ListType:
                conflocals = [conflocals]
            for _local in conflocals:
                try:
                    recip_re, target = string.split (_local, ',', 1)
                except ValueError, txt:
                    raise getmailConfigException, \
                        'section [%s] syntax error in local (%s)' \
                        % (section, _local)
                locals.append ( (recip_re, target) )

            configs.append ( (account.copy(), loptions.copy(), locals) )

    except ConfParser.ConfParserException, txt:
        log (FATAL, '\nError:  error in getmailrc file (%s)\n' % txt)
        sys.exit (exitcodes['ERROR'])

    return configs, options

#######################################
def parse_options (args):
    o = {}
    shortopts = 'adg:hlm:nqr:t:v'
    longopts = ['all', 'delete', 'dont-delete', 'dump', 'getmaildir=', 'help',
                'message-log=', 'new', 'quiet', 'rcfile=', 'timeout=',
                'trace', 'verbose']
    try:
        opts, args = getopt.getopt (args, shortopts, longopts)

    except getopt.error, cause:
        log (FATAL, '\nError:  failed to parse options (%s)\n' % cause)
        help ()

    if args:
        for arg in args:
            log (FATAL, '\nError:  unknown argument (%s)\n' % arg)
        help ()

    for option, value in opts:
        # parse options
        if option == '--help' or option == '-h':
            o['help'] = 1
        elif option == '--delete' or option == '-d':
            o['delete'] = 1
        elif option == '--dont-delete' or option == '-l':
            o['delete'] = 0
        elif option == '--all' or option == '-a':
            o['readall'] = 1
        elif option == '--new' or option == '-n':
            o['readall'] = 0
        elif option == '--verbose' or option == '-v':
            o['verbose'] = 1
        elif option == '--trace':
            o['verbose'] = 2
            ConfParser.debug = 1
        elif option == '--quiet' or option == '-q':
            o['verbose'] = 0
        elif option == '--message-log' or option == '-m':
            o['message_log'] = value
        elif option == '--timeout' or option == '-t':
            try:
                o['timeout'] = int (value)
            except:
                log (FATAL,
                    '\nError:  invalid integer value for timeout (%s)\n'
                    % value)
                help ()
        elif option == '--rcfile' or option == '-r':
            o['rcfilename'] = value
        elif option == '--getmaildir' or option == '-g':
            o['getmaildir'] = value
        elif option == '--dump':
            o['dump'] = 1
        else:
            # ? Can't happen
            log (FATAL, '\nError:  unknown option (%s)\n' % option)
            help ()

    return o

#######################################
def dump_config (cmdopts, mail_configs):
    print 'Current configuration:'
    print
    print '  Commandline:'
    print '    ' + string.join (sys.argv)
    print
    print '  Defaults after commandline options:'
    keys = cmdopts.keys ()
    keys.sort ()
    for key in keys:
        print '    %s:  %s' % (key, cmdopts[key])
    print
    print '  Account configurations:'
    for (account, loptions, locals) in mail_configs:
        print '    Account:'
        keys = account.keys ()
        keys.sort ()
        for key in keys:
            if key == 'password':
                print '      %s:  %s' % (key, '*' * len (account[key]))
            else:
                print '      %s:  %s' % (key, account[key])
        print '      Local Options:'
        keys = loptions.keys ()
        keys.sort ()
        for key in keys:
            if key not in intoptions + stringoptions:  continue
            print '        %s:  %s' % (key, loptions[key])
        print '      Local Users/Deliveries:'
        locals.sort ()
        for (re_s, target) in locals:
            print '        %s:  %s' % (re_s or 'postmaster', target)
        print

#######################################
def main ():
    '''Main entry point for getmail.
    '''
    global me
    me, args = os.path.split (sys.argv[0])[-1], sys.argv[1:]
    overrides = {
        'getmaildir' : defs['getmaildir'],
        'rcfilename' : defs['rcfilename'],
        }
    cmdline_opts = parse_options (args)
    overrides.update (cmdline_opts)

    if overrides.get ('help', None):
        help (exitcodes['OK'])

    configdir = os.path.expanduser (overrides['getmaildir'])
    configfile = os.path.expanduser (overrides['rcfilename'])
    filename = os.path.join (configdir, configfile)

    try:
        mail_configs, conf_default = read_configfile (filename, overrides)
    except getmailConfigException, txt:
        log (FATAL, '\nError:  configuration error in getmailrc file (%s):  %s\n'
            % (filename, txt))
        sys.exit (exitcodes['ERROR'])
    except TypeError:
        # No file to read
        log (FATAL, '\nError reading default getmailrc file (%s)\n' % filename)
        help ()

    overrides.update (conf_default)
    overrides.update (cmdline_opts)

    if mail_configs is None:
        log (FATAL, '\nError:  no such getmailrc file (%s)\n' % filename)
        help ()

    if not mail_configs:
        log (FATAL,
            '\nError:  no POP3 account configurations found in getmailrc file (%s)\n'
            % filename)
        help ()

    # Everything is go.
    if overrides.get ('verbose', None):
        blurb ()

    if overrides.get ('dump', None):
        dump_config (overrides, mail_configs)
        sys.exit (exitcodes['OK'])

    for (account, loptions, locals) in mail_configs:
        try:
            mail = getmail (account, loptions, locals)
            mail.go ()
            try:
                del mail
            except:
                pass
        except getmailNetworkError, txt:
            # Network not up (PPP, etc)
            log (INFO, 'Network error, skipping...\n')
            break
        except KeyboardInterrupt, txt:
            # User aborted
            log (INFO, 'User aborted...\n')
            try:
                del mail
            except:
                pass
        except:
            log (FATAL,
                '\ngetmail bug:  please include the following information in any bug report:\n')
            log (FATAL, 'getmail version %s\n\n' % __version__)
            exc_type, value, tb = sys.exc_info()
            tblist = traceback.format_tb (tb, None) + \
                   traceback.format_exception_only (exc_type, value)
            del tb
            if type (tblist) != ListType:
                tblist = [tblist]
            for line in tblist:
                log (FATAL, string.rstrip (line) + '\n')

            log (FATAL, '\n\Please also include configuration information from running getmail\n')
            log (FATAL, 'with your normal options plus "--dump".\n')

            sys.exit (exitcodes['ERROR'])

    sys.exit (exitcodes['OK'])

#######################################
if __name__ == '__main__':
    main ()
