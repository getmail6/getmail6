#!/usr/bin/python

import os
import string
import cStringIO
import rfc822
import poplib

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

class getmailDataFormatException (getmailException):
    pass

class getmailUnhandledException (Exception):
    pass

#
# Functional classes
#

#######################################
class updatefile:
    def __init__ (self, filename):
        self.closed = 0
        self.filename = filename
        self.tmpname = filename + '.tmp.%d' % os.getpid ()
        try:
            file = open (self.tmpname, 'w')
        except IOError, (code, msg):
            raise IOError, "%s, opening output file '%s'" % (msg, self.tmpname)
        self.file = file
        self.write = file.write
        self.flush = file.flush

    def __del__ (self):
        self.close ()

    def close (self):
        if self.closed:
            return
        self.file.flush ()
        self.file.close ()
        os.rename (self.tmpname, self.filename)
        self.closed = 1

#######################################
class getmailMessage (rfc822.Message):
    '''Provide a way of obtaining a specific header field (i.e. the first
    Delivered-To: field, or the second Received: field, etc).
    It's an enormous oversight that the Python standard library doesn't
    provide this type of functionality.  Also change the constructor to take
    a string, as it's far more useful this way.
    '''
    ###################################
    def __init__ (self, msg):
        f = cStringIO.StringIO (msg)
        rfc822.Message.__init__ (self, f, 1)
        self._parsed_headers = 0
        self.getmailheaders = {}

    ###################################
    def get_specific_header (self, name, num):
        self.getmail_parse_headers ()
        if num < 1:
            raise getmailConfigException, 'num must be positive'
        name = string.lower (name)
        if not self.getmailheaders.has_key (name):
            raise getmailConfigException, 'no matching header fields (%s)' % name
        if len (self.getmailheaders[name]) < num:
            raise getmailConfigException, 'not enough matching header fields (%s:%i)' % (name, num)
        return self.getmailheaders[name][num - 1]

    ###################################
    def getmail_parse_headers (self):
        if self._parsed_headers:
            return

        current = ''
        for line in self.headers:
            if not line:
                # Can't happen?
                raise getmailUnhandledException, 'got empty line (%s)' % self.headers
            if line[0] in string.whitespace:
                # This is a continuation line
                if not current:
                    raise getmailDataFormatException, 'got continuation line with no previous header field (%s)' % self.headers
                current = current + ' ' + string.strip (line)
                continue
            # Not a continuation line
            if current:
                # We're currently working on a header field
                name, val = string.split (current, ':', 1)
                name = string.lower (name)
                val = string.strip (val)
                if self.getmailheaders.has_key (name):
                    self.getmailheaders[name].append (val)
                else:
                    self.getmailheaders[name] = [val]
            # Store current value
            current = string.strip (line)
        # Process last header field stored
        if current:
            name, val = string.split (current, ':', 1)
            name = string.lower (name)
            val = string.strip (val)
            if self.getmailheaders.has_key (name):
                self.getmailheaders[name].append (val)
            else:
                self.getmailheaders[name] = [val]

        self._parsed_headers = 1

#######################################

SPDS_error_proto = poplib.error_proto

#######################################
class SPDS (poplib.POP3):
    '''Extend POP3 class to include support for Demon's protocol extensions,
    known as SPDS.
    See http://www.demon.net/helpdesk/products/mail/sdps-tech.shtml
    for details.  Requested by Paul Clifford.
    '''
    ###################################
    def star_env (self, msgnum):
        '''Implement *ENV command.
        '''
        try:
            resp, lines, octets = self._longcmd ('*ENV %i' % msgnum)
        except poplib.error_proto:
            raise getmailConfigException, 'server does not support *ENV'
        if len (lines) < 4:
            raise SPDS_error_proto, 'short *ENV response (%s)' % lines
        env_sender = lines[2]
        env_recipient = lines[3]
        return env_sender, env_recipient
                