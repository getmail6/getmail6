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

__version__ = '2.3.9'
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
import traceback
import getopt
import getpass
import signal
import sha
from types import *
from stat import *

#
# Exception classes
#

# Base class for all getmail exceptions
class getmailException (Exception):
    pass

# Specific exception classes
class getmailConfigException (getmailException):
    pass

class getmailDeliveryException (getmailException):
    pass

class getmailNetworkError (getmailException):
    pass

class getmailUnhandledException (Exception):
    pass

# Names for output logging levels
loglevels = {
    'TRACE' : 1,
    'DEBUG' : 2,
    'INFO' : 3,
    'WARN' : 4,
    'ERROR' : 5,
    'FATAL' : 6,
}
(TRACE, DEBUG, INFO, WARN, ERROR, FATAL) = range (1, 7)

#
# Defaults
#
# These can mostly be overridden with commandline arguments or via getmailrc.
#

defs = {
    'help' :            0,                  # Leave this alone.
    'dump' :            0,                  # Leave this alone.
    'log_level' :       INFO,
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
    'max_messages_per_session' : 0,         # Stop after X messages; 0 for no
                                            #   limit.
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
    'relaxed_address_match' :   0,          # How strictly to check whether a
                                            #   string is an email address
    'extension_sep' :   '-',                # Extension address separator
    'extension_depth' : 1,                  # Number of local-part pieces to
                                            #   consider part of the base
    }


#
# Globals
#

# For signal handling
getmailobj = None

# Options recognized in configuration getmailrc file
intoptions = (
    'delete',
    'delete_after',
    'eliminate_duplicates',
    'extension_depth',
    'log_level',
    'max_message_size',
    'max_messages_per_session',
    'no_delivered_to',
    'no_received',
    'port',
    'readall',
    'relaxed_address_match',
    'timeout',
    'use_apop',
    'verbose'
)
stringoptions = (
    'extension_sep',
    'message_log',
    'recipient_header'
)

# For these headers, only the first will be parsed
envelope_recipient_headers = ('delivered-to', 'envelope-to', 'x-envelope-to')

# Exit codes
exitcodes = {
    'OK' : 0,
    'ERROR' : -1
    }

# Components of stack trace (indices to tuple)
FILENAME, LINENO, FUNCNAME = 0, 1, 2        #SOURCELINE = 3 ; not used

# Count of deliveries for getmail; used in Maildir delivery
deliverycount = 0

# Line ending conventions
line_end = {
    'pop3' : '\r\n',
    'maildir' : '\n',
    'mbox' : '\n'
    }

res = {
    # Simple re to determine if a string might be an email address
    'mailaddr' : re.compile ('.+?@.+?\..+'),
    # Regular expression object to escape "From ", ">From ", ">>From ", ...
    # with ">From ", ">>From ", ... in mbox deliveries.  This is for mboxrd format
    # mboxes.
    'escapefrom' : re.compile (r'^(?P<gts>\>*)From ', re.MULTILINE),
    # Regular expression object to find line endings
    'eol' : re.compile (r'\r?\n\s*', re.MULTILINE),
    # Regular expression to do POP3 leading-dot unescapes
    'leadingdot' : re.compile (r'^\.\.', re.MULTILINE),
    # Regular expression to extract addresses from 'for' clauses in
    # Received: header fields
    'received_for' : re.compile (r'\s+for\s+<(?P<addr>.*?(?=>))', re.IGNORECASE),
    # Percent sign escapes
    'percent' : re.compile (r'%(?!\([\S]+\)[si])'),
}

# For trace output
newline = 1

#
# Utility functions
#

#######################################
def log (level, msg, opts):
    global newline
    if level < opts['log_level']:
        return
    if level == TRACE:
        if not newline:
            log (level, '\n', opts)
        if not msg:  msg = '\n'
        trace = traceback.extract_stack ()[-3]
        msg = '%s() [%s:%i] %s' % (trace[FUNCNAME],
            os.path.split (trace[FILENAME])[-1],
            trace[LINENO], msg)
    msg = res['percent'].sub ('%%', msg) % opts
    if level >= WARN:
        sys.stderr.write (msg)
        sys.stderr.flush ()
    else:
        sys.stdout.write (msg)
        sys.stdout.flush ()

    if msg and msg[-1] == '\n':
        newline = 1
    else:
        newline = 0

#######################################
def timestamp ():
    '''Return the current time in a standard format.'''
    t = time.gmtime (time.time ())
    return time.strftime ('%d %b %Y %H:%M:%S -0000', t)

#######################################
def mbox_timestamp ():
    '''Return the current time in the format expected in an mbox From_ line.'''
    return time.asctime (time.gmtime (int (time.time ())))

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
    '''getmail.go() implements the main logic to retrieve mail from a
    specified POP3 server and account, and deliver retrieved mail to the
    appropriate Maildir(s) and/or mbox file(s).
    '''

    ###################################
    def __init__ (self, account, users):
        global getmailobj
        self.conf = account.copy ()
        confcopy = account.copy ()
        if confcopy.has_key ('password'):
            confcopy['password'] = '*' * len (confcopy['password'])
        self.logfunc (TRACE, 'account="%s", users="%s"\n'
            % (confcopy, users))
        self.timestamp = int (time.time ())
        for key in ('server', 'port', 'username', 'password'):
            if not account.has_key (key):
                raise getmailConfigException, \
                    'account missing key (%s)' % key

        self.conf['shorthost'] = string.split (self.conf['server'], '.')[0]
        try:
            self.conf['ipaddr'] = socket.gethostbyname (self.conf['server'])
        except socket.error, txt:
            # Network unreachable, PPP down, etc
            raise getmailNetworkError, 'network error (%s)' % txt

        self.logfunc (INFO, 'getmail started for %(username)s@%(server)s:%(port)i\n')

        for key in ('readall', 'delete'):
            if not self.conf.has_key (key):
                raise getmailConfigException, 'opts missing key (' + key + \
                    ') for %(username)s@%(server)s:%(port)i' % self.conf

        timeoutsocket.setDefaultSocketTimeout (self.conf['timeout'])

        try:
            # Get default delivery target (postmaster) -- first in list
            self.default_delivery = os.path.expanduser (users[0][1])
            del users[0]
        except Exception, txt:
            raise getmailConfigException, \
                'no default delivery for %(username)s@%(server)s:%(port)i' \
                % self.conf

        # Construct list of (re_obj, delivery_target) pairs
        self.users = []
        for (re_s, target) in users:
            self.users.append ( {'re' : re.compile (re_s, re.IGNORECASE),
                'target' : os.path.expanduser (target)} )
            self.logfunc (TRACE, 'User #%i:  re="%s", target="%s"\n'
                % (len (self.users), re_s, self.users[-1]['target']))

        self.oldmail_filename = os.path.join (
            os.path.expanduser (self.conf['getmaildir']),
            string.replace ('oldmail-%(server)s-%(port)i-%(username)s'
                % self.conf, '/', '-'))
        self.oldmail = self.read_oldmailfile ()

        # Misc. info
        self.info = {}
        # Store local hostname plus short version
        self.info['hostname'] = socket.gethostname ()
        self.info['shorthost'] = string.split (self.info['hostname'], '.')[0]
        self.info['pid'] = os.getpid ()
        self.info['msgcount'] = 0
        self.info['localscount'] = 0

        if self.conf['message_log']:
            try:
                filename = os.path.join (os.path.expanduser (self.conf['getmaildir']),
                    os.path.expanduser (self.conf['message_log']))
                self.logfile = open (filename, 'a')
            except IOError, txt:
                raise getmailConfigException, 'failed to open log file %s (%s)' \
                    % (filename, txt)
        else:
            self.logfile = None

        self.msglog ('Started for %(username)s@%(server)s:%(port)i')

        getmailobj = self
        self.msgs_delivered = {}

    ###################################
    def __del__ (self):
        global getmailobj
        try:
            self.logfunc (INFO, 'getmail finished for %(username)s@%(server)s:%(port)i\n')
            if self.logfile and not self.logfile.closed:  self.logfile.close ()
            timeoutsocket.setDefaultSocketTimeout (defs['timeout'])
        except:
            pass
        getmailobj = None

    ###################################
    def logfunc (self, level, msg):
        log (level, msg, self.conf)

    ###################################
    def msglog (self, msg):
        if not self.conf['message_log']:
            return
        msg = res['percent'].sub ('%%', msg) % self.conf
        ts = time.strftime ('%d %b %Y %H:%M:%S ', time.localtime (time.time ()))
        self.logfile.write (ts + msg + '\n')
        self.logfile.flush ()

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
            self.logfunc (TRACE, 'read %i' % len (oldmail)
                + ' uids for %(server)s:%(username)s\n')
        except IOError:
            self.logfunc (TRACE, 'no oldmail file for %(server)s:%(username)s\n')
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
            self.logfunc (TRACE, 'wrote %i' % len (self.oldmail)
                + ' uids for %(server)s:%(username)s\n')
        except IOError, txt:
            self.logfunc (WARN,
                'failed writing oldmail file for %%(server)s:%%(username)s (%s)\n'
                % txt)

    ###################################
    def connect (self):
        '''Connect to POP3 server.'''
        session = poplib.POP3 (self.conf['server'], self.conf['port'])
        self.logfunc (TRACE, 'POP3 session initiated on port %(port)s for "%(username)s"\n')
        self.logfunc (INFO, '  POP3 greeting:  %s\n' % session.welcome)

        return session

    ###################################
    def login (self):
        '''Issue the POP3 USER and PASS directives.'''
        logged_in = 0
        if self.conf['use_apop']:
            try:
                rc = self.session.apop (self.conf['username'],
                    self.conf['password'])
                self.logfunc (INFO, '  POP3 APOP response:  %s\n' % rc)
                logged_in = 1
            except poplib.error_proto:
                self.logfunc (WARN, 'Warning:  server does not support '
                    'APOP authentication, trying USER/PASS...\n')
        if not logged_in:
            rc = self.session.user (self.conf['username'])
            self.logfunc (INFO, '  POP3 user response:  %s\n' % rc)
            rc = self.session.pass_ (self.conf['password'])
            self.logfunc (INFO, '  POP3 PASS response:  %s\n' % rc)

        return rc

    ###################################
    def get_msglist (self):
        '''Retrieve message list for this user.'''
        response = self.session.list ()
        rc, msglist_txt = response[0:2]
        self.logfunc (INFO, '  POP3 list response:  %s\n' % rc)

        msglist = []
        for s in msglist_txt:
            # Handle broken POP3 servers which return something after the length
            msgnum, msginfo = string.split (s, None, 1)
            try:
                msgnum = int (msgnum)
            except ValueError, txt:
                self.logfunc (ERROR,
                    '  Error:  POP3 server violates RFC1939 ("%s"), skipping line...\n' % s)
                continue
            # Keep track of length of message
            try:
                msglen = int (string.split (msginfo)[0])
            except:
                msglen = 0
            msglist.append (list ((msgnum, msglen)))

        try:
            rc = self.session.uidl ()
            self.logfunc (TRACE, 'UIDL response "%s"\n' % rc[0])
            uidls = map (lambda x:  string.split (x, None, 1), rc[1])
            if len (uidls) != len (msglist):
                self.logfunc (ERROR, 'POP3 server returned %i UIDs for %i messages, will retrieve all messages'
                    % (len (uidls), len (msglist)))
                uidls = [(None, None)] * len (msglist)
        except poplib.error_proto, txt:
            self.logfunc (WARN,
                'POP3 server failed UIDL command, will retrieve all messages (%s)'
                % txt)
            uidls = [(None, None)] * len (msglist)

        for i in range (len (msglist)):
            msglist[i].append (uidls[i][1])

        msglist.append ( (None, None, None) )
        return msglist

    ###################################
    def report_mailbox_size (self):
        '''Retrieve mailbox size for this user.'''
        msgs, octets = self.session.stat ()
        self.logfunc (INFO, '  POP3 stat response:  %i messages, %i octets\n'
            % (msgs, octets))
        self.msglog ('STAT: %i messages %i octets' % (msgs, octets))

    ###################################
    def extract_recipients (self, mess822):
        recipients = {}
        if type (self.conf['recipient_header']) != type ([]):
            self.conf['recipient_header'] = [self.conf['recipient_header']]
        for header_type in self.conf['recipient_header']:
            if not mess822.has_key (header_type):
                continue
            self.logfunc (TRACE, 'parsing header "%s"\n' % header_type)
            if string.lower (header_type) == 'received':
                # Handle Received: headers specially
                recips = self.extract_recipients_received (mess822)
            elif string.lower (header_type) in envelope_recipient_headers:
                # Handle envelope recipient headers differently; only
                # look at first matching header
                hdr = mess822.getfirstmatchingheader (header_type)
                if not hdr:  continue
                recips = rfc822.AddrlistClass(string.join (hdr)).getaddrlist ()
            else:
                # Handle all other header fields
                recips = mess822.getaddrlist (header_type)
            for (name, address) in recips:
                if address and (res['mailaddr'].search (address) or self.conf['relaxed_address_match']):
                    # Looks like an email address, keep it
                    recipients[string.lower (address)] = None
                    self.logfunc (TRACE, 'found address "%s"\n' % address)
                else:
                    # Hmmm, bogus
                    self.logfunc (TRACE, 'not an address: "%s"\n' % address)

        self.logfunc (TRACE, 'found %i recipients\n' % len (recipients.keys ()))

        return recipients.keys ()

    ###################################
    def extract_recipients_received (self, mess822):
        # Handle Received: headers specially
        recipients = []
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
            self.logfunc (TRACE, 'checking header "%s"\n' % line)
            _match = res['received_for'].search (line)
            if not _match:
                continue
            recipients.append ( (None, _match.groupdict()['addr']) )

        return recipients

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
            self.logfunc (DEBUG, 'no Return-Path: header in message\n')
            env_sender = '<#@[]>'
        # Export envelope sender address to environment
        os.environ['SENDER'] = env_sender or ''

        self.logfunc (TRACE, 'found envelope sender "%s"\n' % env_sender)
        self.msglog ('New msg "%s" from "%s"' % (msgid, env_sender))

        if len (self.users):
            # Extract possible recipients
            recipients = self.extract_recipients (mess)

        else:
            # No local configurations, just send to postmaster
            recipients = []

        count = self.do_deliveries (recipients, msg, msgid, env_sender)

        if count == 0:
            # Made no deliveries of this message; send it to the default delivery
            # target.
            dt = self.deliver_msg (self.default_delivery,
                self.message_add_info (msg,
                    'postmaster@%(hostname)s' % self.info),
                 env_sender)
            self.msglog ('Delivered to postmaster %s' % dt)

        self.logfunc (TRACE, 'do_deliveries did %i deliveries\n' % count)

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
            self.logfunc (TRACE, 'message appears to have no body\n')
            body_start = 0
        digestobj = sha.new (msg[body_start:])
        digest = digestobj.digest ()
        self.logfunc (TRACE, 'msgid "%s", message digest "%s", body "%s..."'
            % (msgid, digestobj.hexdigest (), msg[body_start:body_start + 40]))

        # Test each recipient address against the compiled regular expression
        # objects for each configured user for this POP3 mailbox.  If the
        # recipient address matches a given user's re, deliver at most one copy
        # to the target associated with that re.
        for user in self.users:
            do_delivery = 0
            self.logfunc (TRACE, 'checking user re "%s"' % user['re'].pattern
                + ', target "%s"\n' % user['target'])
            for recipient in recipients:
                if user['re'].match (recipient):
                    self.logfunc (TRACE, 'user re matched recipient "%s"\n'
                        % recipient)
                    do_delivery = 1

                    # Export the envelope recipient address to the environment
                    os.environ['RECIPIENT'] = recipient
                    # Try to determine the address extension of the recipient
                    # address.  Export it to the environment.
                    os.environ['EXT'] = ''
                    try:
                        local_part = recipient[:string.rindex (recipient, '@')]
                        parts = string.split (local_part, self.conf['extension_sep'], self.conf['extension_depth'])
                        if len (parts) == self.conf['extension_depth'] + 1:
                            os.environ['EXT'] = parts[-1]
                    except ValueError:
                        pass

                    # Stop as soon as we match a recipient address
                    break

            if not do_delivery:
                continue

            if self.conf['eliminate_duplicates']:
                if not self.msgs_delivered.has_key (digest):
                    # First recipient of this message, keep track
                    self.msgs_delivered[digest] = [user['target']]
                else:
                    if not user['target'] in self.msgs_delivered[digest]:
                        # Deliver to this recipient and keep track
                        self.msgs_delivered[digest].append (user['target'])
                    else:
                        # Never deliver multiple copies of a message to same destination
                        self.logfunc (TRACE,
                            'already delivered to target "%(target)s", skipping...\n')
                        do_delivery = 0
                        self.msglog ('Duplicate message, skipping')
                        # Add a delivery, so it doesn't go to postmaster
                        delivered = delivered + 1
                        # Skip to next local user
                        continue

            # Deliver the message to this user
            dt = self.deliver_msg (user['target'],
                self.message_add_info (msg, recipient), env_sender)
            self.logfunc (TRACE, 'delivered to "%(target)s"\n')
            self.msglog ('Delivered to %s' % dt)
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
            'destination "%s" is not a Maildir, mbox, or command' % dest

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

        if self.conf['no_delivered_to']:
            delivered_to = ''
        else:
            # Construct Delivered-To: header with address local_part@localhostname
            delivered_to = format_header ('Delivered-To',
                '%s@%s\n' % (_local, self.info['hostname']))

        if self.conf['no_received']:
            received = ''
        else:
            # Construct Received: header
            info = 'from %(server)s (%(ipaddr)s)' % self.conf \
                + ' by %(hostname)s' % self.info \
                + ' with POP3 for <%s>; ' % recipient \
                + timestamp ()
            received = format_header ('Received', info)

        return delivered_to + received + message

    #######################################
    def deliver_maildir (self, maildir, msg):
        'Reliably deliver a mail message into a Maildir.'
        # Uses Dan Bernstein's documented naming convention for maildir
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
        maildir_owner = s_maildir[ST_UID]
        maildir_group = s_maildir[ST_GID]

        # Open file to write
        try:
            f = open (fname_tmp, 'wb')
            os.chmod (fname_tmp, 0600)
            try:
                # If root, change the message to be owned by the Maildir
                # owner
                os.chown (fname_tmp, maildir_owner, maildir_group)
            except OSError:
                # Not running as root, can't chown file
                pass
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

        self.logfunc (TRACE, 'delivered to Maildir "%s"\n' % maildir)

        deliverycount = deliverycount + 1
        return 'Maildir "%s"' % maildir

    #######################################
    def deliver_mbox (self, mbox, msg, env_sender):
        'Deliver a mail message into an mbox file.'

        global deliverycount
        # Construct mboxrd-style 'From_' line
        fromline = 'From %s %s\n' % (env_sender, mbox_timestamp ())

        try:
            # When orig_length is None, we haven't opened the file yet
            orig_length = None
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
            orig_length = f.tell ()         # Save original length
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
            try:
                os.utime (mbox, (status_old[ST_ATIME], status_new[ST_MTIME]))
            except OSError, txt:
                # Not root or owner; readers will not be able to reliably
                # detect new mail.  But you shouldn't be delivering to
                # other peoples' mboxes unless you're root, anyways.
                self.logfunc (WARN,
                    'Warning:  failed to update atime/mtime of mbox file (%s)...\n' % txt)

        except IOError, txt:
            try:
                if not f.closed and not orig_length is None:
                    # If the file was opened and we know how long it was,
                    # try to truncate it back to that length
                    # If it's already closed, or the error occurred at close(),
                    # then there's not much we can do.
                    f.truncate (orig_length)
                unlock_file (f)
                f.close ()
            except:
                pass
            raise getmailDeliveryException, \
                'failure writing message to mbox file "%s" (%s)' % (mbox, txt)

        # Delivery done
        self.logfunc (TRACE, 'delivered to mbox "%s"\n' % mbox)

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
        fromline = 'From %s %s\n' % (env_sender, mbox_timestamp ())

        self.logfunc (TRACE, 'delivering to command "%s"\n' % command)

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

            if r:
                if os.WIFEXITED (r):
                    exitcode = 'exited %i' % os.WEXITSTATUS (r)
                    exitsignal = ''
                elif os.WIFSIGNALED (r):
                    exitcode = 'abnormal exit'
                    exitsignal = 'signal %i' % os.WTERMSIG (r)
                else:
                    # Stopped, etc.
                    exitcode = 'no exit?'
                    exitsignal = ''
                raise getmailDeliveryException, 'command "%s" %s %s (%s)' \
                     % (command, exitcode, exitsignal, err)

            elif err:
                raise getmailDeliveryException, 'command "%s" exited 0 but wrote to stderr (%s)' \
                     % (command, err)

            if out:
                # Command wrote something to stdout
                self.logfunc (INFO, '  command "%s" said "%s"\n' % (command, out))

        except ImportError:
            raise getmailDeliveryException, 'popen2 module not found'

        except StandardError, txt:
            raise getmailDeliveryException, \
                'failure delivering message to command "%s" (%s)' % (command, txt)

        # Delivery done
        self.logfunc (TRACE, 'delivered to command "%s"\n' % command)

        deliverycount = deliverycount + 1
        return 'command "%s"' % command

    ###################################
    def abort (self, txt):
        '''Some error has occurred after logging in to POP3 server.  Reset the
        server and close the session cleanly if possible.'''

        self.logfunc (WARN, 'Resetting connection and aborting (%s)\n' % txt)
        self.msglog ('Aborted (%s)' % txt)

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

            inbox = []
            for (msgnum, msglen, msgid) in msglist:
                if msgnum == msglen == msgid == None:
                    # No more messages; POP3.list() returns a final int
                    self.logfunc (INFO, '  finished retrieving messages\n')
                    break

                # Append msgid to list of current inbox contents
                inbox.append (msgid)

                if self.conf['max_messages_per_session']:
                    if self.info['msgcount'] == self.conf['max_messages_per_session']:
                        self.logfunc (INFO, '  retrieved %(max_messages_per_session)i messages, quitting.\n')
                        continue
                    elif self.info['msgcount'] > self.conf['max_messages_per_session']:
                        continue

                self.logfunc (INFO, '  msg #%i/%i : len %s ... '
                    % (msgnum, len (msglist) - 1, msglen))

                if msglen and self.conf['max_message_size'] and msglen > self.conf['max_message_size']:
                    self.logfunc (INFO,
                        'over max message size of %(max_message_size)i, skipping ...\n')
                    continue

                # Retrieve this message if:
                #   "get all mail" option is set, OR
                #   server does not support UIDL (msgid is None), OR
                #   this is a new message (not in oldmail)
                if self.conf['readall'] or msgid is None \
                    or not self.oldmail.has_key (msgid):
                    rc, msglines, octets = self.session.retr (msgnum)
                    msg = string.join (msglines, line_end['pop3'])
                    self.logfunc (INFO, 'retrieved')
                    self.info['msgcount'] = self.info['msgcount'] + 1
                    msg = pop3_unescape (msg)

                    # Find recipients for this message and deliver to them.
                    count = self.process_msg (msg)
                    if count == 0:
                        self.logfunc (INFO, ' ... delivered to postmaster')
                        count = 1
                    elif count == 1:
                        self.logfunc (INFO, ' ... delivered 1 copy')
                    else:
                        self.logfunc (INFO, ' ... delivered %i copies' % count)

                    self.info['localscount'] = self.info['localscount'] + count

                else:
                    self.logfunc (INFO, 'previously retrieved ...')

                # Delete this message if the "delete" or "delete_after" options
                # are set
                if self.conf['delete']:
                    rc = self.session.dele (msgnum)
                    self.logfunc (INFO, ', deleted')
                    # Remove msgid from list of current inbox contents
                    if msgid is not None:  del inbox[-1]
                if self.conf['delete_after']:
                    if self.oldmail.get (msgid, None):
                        self.logfunc (TRACE,
                            ' originally seen '
                            + time.strftime ('%Y-%m-%d %H:%M:%S',
                                    time.localtime (self.oldmail[msgid])))
                    else:
                        self.logfunc (TRACE, ' not previously seen')
                    if self.oldmail.has_key (msgid) and self.oldmail[msgid] < (self.timestamp - self.conf['delete_after'] * 86400):
                        rc = self.session.dele (msgnum)
                        self.logfunc (INFO,
                            ' ... older than %(delete_after)i days, deleted')
                        # Remove msgid from list of current inbox contents
                        if msgid is not None:  del inbox[-1]

                if msgid is not None and not self.oldmail.get (msgid, None):
                    self.oldmail[msgid] = self.timestamp
                # Finished delivering this message
                self.logfunc (INFO, '\n')

            # Done processing messages; process oldmail contents
            self.write_oldmailfile (inbox)

            # Close session and display summary
            self.session.quit ()
            self.logfunc (INFO, 'POP3 session completed for "%(username)s"\n')
            self.logfunc (INFO,
                'Retrieved %(msgcount)i messages for %(localscount)i local recipients\n\n'
                % self.info)
            self.msglog ('Finished')

        except SystemExit:
            raise

        except MemoryError:
            self.logfunc (ERROR, '  Memory exhausted\n')
            self.abort ('Out of memory')

        except Timeout, txt:
            txt = 'TCP timeout'
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except poplib.error_proto, txt:
            txt = 'POP3 protocol error (%s)' % txt
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except socket.error, txt:
            txt = 'Socket error (%s)' % txt
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except getmailConfigException, txt:
            txt = 'Configuration error (%s)' % txt
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except getmailDeliveryException, txt:
            txt = 'Delivery error (%s)' % txt
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except getmailNetworkError, txt:
            txt = 'Network error (%s)' % txt
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except KeyboardInterrupt:
            txt = 'User aborted'
            self.logfunc (WARN, '  %s\n' % txt)
            self.abort (txt)
            raise SystemExit

        except getmailUnhandledException, txt:
            txt = 'Unknown error (%s)' % txt
            self.logfunc (FATAL, '  %s\n' % txt)
            self.msglog (txt)
            raise getmailUnhandledException, txt

###################################
def alarm_handler (dummy, unused):
    '''Handle an alarm (should never happen).'''
    getmailobj.abort ('Maildir delivery timeout')

#
# Main script code and helper functions
#

#######################################
def blurb ():
    print 'getmail - POP3 mail retriever with reliable Maildir and mbox delivery.'
    print

#######################################
def version ():
    print 'getmail version %s ' % __version__
    print
    print 'Copyright (C) 2001 Charles Cazabon'
    print
    print 'Licensed under the GNU General Public License version 2.  See the file'
    print 'COPYING for details.'
    print
    print 'Written by Charles Cazabon <getmail @ discworld.dyndns.org>'

#######################################
def help (ec=exitcodes['ERROR']):
    blurb ()
    print 'Usage:  getmail [OPTION] ...'
    print
    print 'Options:'
    print '  -h or --help                      display brief usage information and exit'
    print '  -V or --version                   display version information and exit'
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
    print '  --trace                           debugging output to stdout'
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
    if defs['log_level'] < WARN:
        print '                                      (default:  verbose)'
    else:
        print '                                      (default:  quiet)'
    print '  -m or --message-log <file>        log retrieval info to <file>'
    print
    sys.exit (ec)

#######################################
def read_configfile (filename, default_config):
    '''Read in configuration file and extract configuration information.
    '''
    # Resulting list of configurations
    configs = []

    if not os.path.isfile (filename):
        raise getmailConfigException, 'no such file "%s"' % filename

    s = os.stat (filename)
    mode = S_IMODE (s[ST_MODE])
    if (mode & 022):
        raise getmailConfigException, 'file is group- or world-writable'

    # Instantiate configuration file parser
    conf = ConfParser.ConfParser (defs)

    try:
        conf.read (filename)
        sections = conf.sections ()

        # Read options from config file
        options = default_config.copy ()
        for key in conf.options ('default'):
            if key in intoptions:
                options[key] = conf.getint ('default', key)
                if key == 'verbose':
                    if options[key]:
                        options['log_level'] = INFO
                    else:
                        options['log_level'] = WARN
            elif key in stringoptions:
                options[key] = conf.get ('default', key)
            else:
                log (TRACE, 'unrecognized option "%s" in section "default"\n'
                    % key, options)

        # Remainder of sections are accounts to retrieve mail from.
        for section in sections:
            account, locals = options.copy (), []

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
                account['password'] = getpass.getpass (
                    'Enter password for %(username)s@%(server)s:%(port)s :  '
                    % account)

            for key in conf.options (section):
                if key in ('server', 'port', 'username', 'password'):
                    continue
                if key in intoptions:
                    account[key] = conf.getint (section, key)
                    if key == 'verbose':
                        if account[key]:
                            account['log_level'] = INFO
                        else:
                            account['log_level'] = WARN
                elif key in stringoptions:
                    account[key] = conf.get (section, key)
                else:
                    log (TRACE, 'unrecognized option "%s" in section "%s"\n'
                        % (key, section), options)

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

            configs.append ( (account.copy(), locals) )

    except ConfParser.ConfParserException, txt:
        log (FATAL, '\nError:  error in getmailrc file (%s)\n' % txt,
            default_config)
        sys.exit (exitcodes['ERROR'])

    return options, configs

#######################################
def parse_options (args):
    o = {}
    shortopts = 'adg:hlm:nqr:t:vV'
    longopts = ['all', 'delete', 'dont-delete', 'dump', 'getmaildir=', 'help',
                'message-log=', 'new', 'quiet', 'rcfile=', 'timeout=',
                'trace', 'verbose', 'version']
    try:
        opts, args = getopt.getopt (args, shortopts, longopts)

    except getopt.error, cause:
        log (FATAL, '\nError:  failed to parse options (%s)\n' % cause, defs)
        help ()

    if args:
        for arg in args:
            log (FATAL, 'Error:  unknown argument (%s)\n' % arg, defs)
        help ()

    for option, value in opts:
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
            o['log_level'] = INFO
        elif option == '--trace':
            o['log_level'] = TRACE
        elif option == '--quiet' or option == '-q':
            o['log_level'] = WARN
        elif option == '--message-log' or option == '-m':
            o['message_log'] = value
        elif option == '--timeout' or option == '-t':
            try:
                o['timeout'] = int (value)
            except:
                log (FATAL,
                    '\nError:  invalid integer value for timeout (%s)\n' % value,
                    defs)
                help ()
        elif option == '--version' or option == '-V':
            version ()
            sys.exit (0)
        elif option == '--rcfile' or option == '-r':
            o['rcfilename'] = value
        elif option == '--getmaildir' or option == '-g':
            o['getmaildir'] = value
        elif option == '--dump':
            o['dump'] = 1
        else:
            # ? Can't happen
            log (FATAL, '\nError:  unknown option (%s)\n' % option, defs)
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
    for (account, locals) in mail_configs:
        print '    Account:'
        keys = account.keys ()
        keys.sort ()
        for key in keys:
            if key == 'password':
                print '      %s:  %s' % (key, '*' * len (account[key]))
            else:
                print '      %s:  %s' % (key, account[key])
        print '      Local Users/Deliveries:'
        locals.sort ()
        for (re_s, target) in locals:
            print '        %s:  %s' % (re_s or 'postmaster', target)
        print

#######################################
def main ():
    '''Main entry point for getmail.
    '''
    config = defs.copy ()
    cmdline_opts = parse_options (sys.argv[1:])
    config.update (cmdline_opts)

    if config['help']:
        help (exitcodes['OK'])

    filename = os.path.join (os.path.expanduser (config['getmaildir']),
        os.path.expanduser (config['rcfilename']))

    try:
        config, mail_configs = read_configfile (filename, config)
        # Need to re-apply commandline overrides here
        config.update (cmdline_opts)

        for (account, _locals) in mail_configs:
            # Apply commandline overrides to options
            account.update (cmdline_opts)
    
        if not mail_configs:
            log (FATAL,
                '\nError:  no POP3 account configurations found in getmailrc file (%s)\n'
                % filename, config)
            help ()

        # Everything is go.
        if config['log_level'] < WARN:
            blurb ()
            version ()

        if config['dump']:
            dump_config (config, mail_configs)
            sys.exit (exitcodes['OK'])

        for (account, _locals) in mail_configs:
            try:
                getmail (account, _locals).go ()

            except getmailNetworkError, txt:
                log (WARN, '%s\n' % txt, config)

    except SystemExit:
        raise

    except getmailConfigException, txt:
        txt = 'Configuration error (%s)' % txt
        log (FATAL, '  %s\n' % txt, config)
        sys.exit (exitcodes['ERROR'])

    except:
        log (FATAL,
            '\ngetmail bug:  please include the following information in any bug report:\n\n',
            config)
        log (FATAL, '  getmail version %s\n' % __version__, config)
        log (FATAL, '  ConfParser version %s\n' % ConfParser.__version__, config)
        log (FATAL, '  Python version %s\n\n' % sys.version, config)
        log (FATAL, 'Unhandled exception follows:\n', config)
        exc_type, value, tb = sys.exc_info ()
        tblist = traceback.format_tb (tb, None) + \
               traceback.format_exception_only (exc_type, value)
        if type (tblist) != ListType:
            tblist = [tblist]
        for line in tblist:
            log (FATAL, '  ' + string.rstrip (line) + '\n', config)

        log (FATAL, '\n\Please also include configuration information from running getmail\n',
            config)
        log (FATAL, 'with your normal options plus "--dump".\n', config)

        sys.exit (exitcodes['ERROR'])

    sys.exit (exitcodes['OK'])

#######################################
if __name__ == '__main__':
    main ()
