#!/usr/bin/python
'''getmail_mbox.py - mboxrd delivery agent, using flock locking.
Reads a message from stdin and delivers it to an mbox file specified as
a commandline argument.  Expects the envelope sender address to be in the
environment variable SENDER.
Copyright (C) 2001-2003 Charles Cazabon <getmail @ discworld.dyndns.org>

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

__version__ = '1.0.0'
__author__ = 'Charles Cazabon <getmail @ discworld.dyndns.org>'

#
# Imports
#


import sys
import os
import time
import fcntl
import stat
import re

res = {
    # Regular expression object to escape "From ", ">From ", ">>From ", ...
    # with ">From ", ">>From ", ... in mbox deliveries.  This is for mboxrd format
    # mboxes.
    'escapefrom' : re.compile (r'^(?P<gts>\>*)From ', re.MULTILINE),
}

#######################################
class DeliveryException (Exception):
    pass

#######################################
def mbox_timestamp ():
    '''Return the current time in the format expected in an mbox From_ line.'''
    return time.asctime (time.gmtime (int (time.time ())))

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

#######################################
def deliver_mbox (mbox, msg, env_sender):
    'Deliver a mail message into an mbox file.'
    # Construct mboxrd-style 'From_' line
    fromline = 'From %s %s\n' % (env_sender, mbox_timestamp ())
    try:
        # When orig_length is None, we haven't opened the file yet
        orig_length = None
        # Open mbox file
        f = open (mbox, 'ab+')
        lock_file (f)
        status_old = os.fstat (f.fileno())
        orig_length = status_old[stat.ST_SIZE]  # Save original length
        # Check if it _is_ an mbox file
        # mbox files must start with "From " in their first line, or
        # are 0-length files.
        f.seek (0, 0)                   # Seek to start
        first_line = f.readline ()
        if first_line != '' and first_line[:5] != 'From ':
            # Not an mbox file; abort here
            unlock_file (f)
            f.close ()
            raise DeliveryException, 'destination "%s" is not an mbox file' % mbox
        f.write (fromline)
        # Replace lines beginning with "From ", ">From ", ">>From ", ...
        # with ">From ", ">>From ", ">>>From ", ...
        msg = res['escapefrom'].sub ('>\g<gts>From ', msg)
        # Add trailing newline if last line incomplete
        if msg[-1] != '\n':  msg = msg + '\n'
        # Write out message
        f.write (msg)
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
            os.utime (mbox, (status_old[stat.ST_ATIME], status_new[stat.ST_MTIME]))
        except OSError, txt:
            # Not root or owner; readers will not be able to reliably
            # detect new mail.  But you shouldn't be delivering to
            # other peoples' mboxes unless you're root, anyways.
            sys.stderr.write ('Warning:  failed to update atime/mtime of mbox file (%s)...\n' % txt)

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
        raise DeliveryException, 'failure writing message to mbox file "%s" (%s)' % (mbox, txt)
