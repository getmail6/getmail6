#!/usr/bin/python

import string
import rfc822

# FIXME: add version here, and add it to getmail's info output
# Maybe rename this file and move independant functions, data here?

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
class getmailMessage (rfc822.Message):
    '''Provide a way of obtaining a specific header field (i.e. the first
    Delivered-To: field, or the second Received: field, etc).
    It's an enormous oversight that the Python standard library doesn't
    provide this type of functionality.
    '''
    ###################################
    def __init__ (self, file, seekable=0):
        rfc822.Message.__init__ (self, file, seekable)
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

                