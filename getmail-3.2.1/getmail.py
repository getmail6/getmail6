#!/usr/bin/python
'''getmail.py - POP3 mail retriever with reliable Maildir and command delivery.
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

__version__ = '3.2.1'
__author__ = 'Charles Cazabon <getmail @ discworld.dyndns.org>'

#
# Imports
#

# Main Python library
import sys
import os
import string
import re
import time
import socket
import traceback
import stat
from types import *

# Other getmail bits
from getmail_classes import *
from getmail_utilities import *
from getmail_constants import *

#
# Globals
#

# Count of deliveries for getmail; used in Maildir delivery
deliverycount = 0

# Incompatible change in Python standard library in Python version 1.6;
# session.retr() used to return the raw message lines, now it returns
# the cooked (unstuffed) lines.  So we only unstuff for older versions of
# Python now.
if sys.hexversion < 0x01060000:
    NEED_REMOVE_LEADING_DOTS = 1
else:
    NEED_REMOVE_LEADING_DOTS = 0
  
#
# Classes
#

#######################################
class getmail:
    '''getmail.go() implements the main logic to retrieve mail from a
    specified POP3 server and account, and deliver retrieved mail to the
    appropriate Maildir(s) and/or commands.
    '''

    ###################################
    def __init__ (self, account, users):
        self.conf = account.copy ()
        confcopy = account.copy ()
        if confcopy.has_key ('password'):
            confcopy['password'] = '*'
        self.logfunc (TRACE, 'account="%s", users="%s"\n' % (confcopy, users))
        self.timestamp = int (time.time ())
        for key in ('server', 'port', 'username', 'password'):
            if not account.has_key (key):
                raise getmailConfigException, 'account missing key (%s)' % key

        self.conf['shorthost'] = string.split (self.conf['server'], '.')[0]
        try:
            self.conf['ipaddr'] = socket.gethostbyname (self.conf['server'])
        except socket.error, txt:
            # Network unreachable, PPP down, etc
            raise getmailNetworkError, 'network error (%s)' % txt

        self.logfunc (INFO, 'getmail started for %s\n' % self)

        for key in ('readall', 'delete'):
            if not self.conf.has_key (key):
                raise getmailConfigException, 'opts missing key (%s) for %s' % (key, self)

        timeoutsocket.setDefaultSocketTimeout (self.conf['timeout'])

        try:
            # Get default delivery target (postmaster)
            self.default_delivery = os.path.expanduser (self.conf['postmaster'])
        except Exception, txt:
            raise getmailConfigException, 'no default delivery for %s' % self

        # Construct list of (re_obj, delivery_target) pairs
        self.users = []
        for (re_s, target) in users:
            self.users.append ( {'re' : re.compile (re_s, re.IGNORECASE),
                'target' : os.path.expanduser (target)} )
            self.logfunc (TRACE, 'User #%i:  re="%s", target="%s"\n'
                % (len (self.users), re_s, self.users[-1]['target']))

        self.oldmail_filename = os.path.join (
            os.path.expanduser (self.conf['getmaildir']),
            string.replace ('oldmail-%(server)s-%(port)i-%(username)s' % self.conf,
            '/', '-'))
        self.read_oldmailfile ()

        # Misc. info
        self.info = {}
        # Store local hostname plus short version
        self.info['hostname'] = socket.gethostname ()
        self.info['shorthost'] = string.split (self.info['hostname'], '.')[0]
        #self.info['pid'] = os.getpid ()
        self.info['msgcount'] = 0
        self.info['localscount'] = 0

        if self.conf['message_log']:
            try:
                filename = os.path.join (os.path.expanduser (self.conf['getmaildir']),
                    os.path.expanduser (self.conf['message_log']))
                self.logfile = open (filename, 'a')
            except IOError, txt:
                raise getmailConfigException, 'failed to open log file %s (%s)' % (filename, txt)
        else:
            self.logfile = None

        self.msglog ('Started for %s' % self)

    ###################################
    def __str__ (self):
        try:
            return '%(username)s@%(server)s:%(port)i' % self.conf
        except:
            return 'getmail object %s' % id (self)

    ###################################
    def __del__ (self):
        try:
            self.logfunc (INFO, 'getmail finished for %s\n' % self)
            if self.logfile and not self.logfile.closed:  self.logfile.close ()
            timeoutsocket.setDefaultSocketTimeout (defs['timeout'])
        except:
            pass

    ###################################
    def logfunc (self, level, msg):
        log (level, msg, self.conf)

    ###################################
    def msglog (self, msg):
        if not self.conf['message_log']:
            return
        msg = res['percent'].sub ('%%', msg) % self.conf
        ts = time.strftime ('%d %b %Y %H:%M:%S ', time.gmtime (time.time ()))
        self.logfile.write (ts + msg + '\n')
        self.logfile.flush ()

    ###################################
    def read_oldmailfile (self):
        '''Read contents of oldmail file.'''
        self.oldmail = {}
        try:
            for line in map (string.strip, open (self.oldmail_filename, 'r').readlines ()):
                msgid, timestamp = string.split (line, '\0', 1)
                self.oldmail[msgid] = int (timestamp)
            self.logfunc (TRACE, 'read %i uids for %s\n' % (len (self.oldmail), self))
        except IOError:
            self.logfunc (TRACE, 'no oldmail file for %s\n' % self)

    ###################################
    def write_oldmailfile (self, cur_messages):
        '''Write oldmail info to oldmail file.'''
        try:
            f = updatefile (self.oldmail_filename)
            for msgid, timestamp in self.oldmail.items ():
                if msgid in cur_messages:
                    # This message still in inbox; remember it for next time.
                    f.write ('%s\0%i\n' % (msgid, timestamp))
                #else:
                # Message doesn't exist in inbox, no sense remembering it.
            f.close ()
            self.logfunc (TRACE, 'wrote %i uids for %%(server)s:%%(username)s\n' % len (self.oldmail))
        except IOError, txt:
            self.logfunc (WARN, 'failed writing oldmail file for %%(server)s:%%(username)s (%s)\n' % txt)

    ###################################
    def connect (self):
        '''Connect to POP3 server.'''
        self.session = SPDS (self.conf['server'], self.conf['port'])
        self.logfunc (TRACE, 'POP3 session initiated on port %(port)s for "%(username)s"\n')
        self.logfunc (INFO, '  POP3 greeting:  %s\n' % self.session.welcome)

    ###################################
    def login (self):
        '''Log in to the server with either APOP or USER/PASS directives.'''
        if self.conf['use_apop']:
            try:
                rc = self.session.apop (self.conf['username'], self.conf['password'])
                self.logfunc (INFO, '  POP3 APOP response:  %s\n' % rc)
            except SPDS_error_proto:
                raise getmailConfigException, 'error during attempted APOP authentication'
        else:
            rc = self.session.user (self.conf['username'])
            self.logfunc (INFO, '  POP3 user response:  %s\n' % rc)
            rc = self.session.pass_ (self.conf['password'])
            self.logfunc (INFO, '  POP3 PASS response:  %s\n' % rc)

    ###################################
    def message_list (self):
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
                self.logfunc (ERROR, '  Error:  POP3 server violates RFC1939 ("%s"), skipping line...\n' % s)
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
        except SPDS_error_proto, txt:
            self.logfunc (WARN, 'POP3 server failed UIDL command, will retrieve all messages (%s)' % txt)
            uidls = [(None, None)] * len (msglist)

        for i in range (len (msglist)):
            msglist[i].append (uidls[i][1])

        msglist.append ( (None, None, None) )
        self.msglist = msglist

    ###################################
    def report_mailbox_size (self):
        '''Retrieve mailbox size for this user.'''
        msgs, octets = self.session.stat ()
        self.logfunc (INFO, '  POP3 stat response:  %i messages, %i octets\n'
            % (msgs, octets))
        self.msglog ('STAT: %i messages %i octets' % (msgs, octets))

    ###################################
    def process_msg (self, msg, msgnum, msgcount, msgsize):
        '''Process retrieved message and deliver to appropriate recipients.'''
        mess = getmailMessage (msg)
        if self.conf['use_*env']:
            env_sender, recipient = self.session.star_env (msgnum)
            self.logfunc (TRACE, '*env envelope sender "%s", recipient "%s"\n' % (env_sender, recipient))
        else:
            try:
                env_sender = address_no_brackets (mess.get_specific_header ('return-path', 1))
            except getmailConfigException, txt:
                self.logfunc (DEBUG, 'no Return-Path: header in message (%s)\n' % txt)
                env_sender = ''
            self.logfunc (TRACE, 'found envelope sender "%s"\n' % env_sender)

            if self.conf['envelope_recipient']:
                recipient = envelope_recipient (self.conf, mess)
            else:
                recipient = ''

        # Export envelope sender address to environment
        os.environ['SENDER'] = env_sender
        # Export the envelope recipient address to the environment
        os.environ['RECIPIENT'] = recipient

        # Try to determine the address extension of the recipient address.
        # Export it to the environment.
        os.environ['EXT'] = ''
        try:
            local_part = recipient[:string.rindex (recipient, '@')]
            parts = string.split (local_part, self.conf['extension_sep'], self.conf['extension_depth'])
            if len (parts) == self.conf['extension_depth'] + 1:
                os.environ['EXT'] = parts[-1]
        except ValueError:
            pass

        msgid = mess.get ('message-id', 'None')
        self.msglog ('New msg %i/%i len %s id "%s" from "%s"' % (msgnum, msgcount, msgsize, msgid, env_sender))

        count = 0
        if len (self.users):
            count = self.do_deliveries (recipient, msg, msgid, env_sender)
        #else:
            # No local configurations, just send to postmaster

        if not count:
            # Made no deliveries of this message; send it to the default delivery
            # target.
            dt = self.deliver_msg (self.default_delivery,
                self.message_add_info (msg,
                    recipient or 'postmaster@%(hostname)s' % self.info),
                 env_sender)
            self.msglog ('Delivered to postmaster %s' % dt)

        self.logfunc (TRACE, 'do_deliveries did %i deliveries\n' % count)

        return count

    #######################################
    def do_deliveries (self, recipient, msg, msgid, env_sender):
        '''Determine which configured local recipients to send a copy of this
        message to, and dispatch to the deliver_msg() method.
        '''
        delivered = 0
        self.logfunc (TRACE, 'msgid "%s"' % msgid)

        # Test recipient address against the compiled regular expression
        # objects for each configured user for this POP3 mailbox.  If the
        # recipient address matches a given user's re, deliver at most one copy
        # to the target associated with that re.
        for user in self.users:
            self.logfunc (TRACE, 'checking user re "%s"' % user['re'].pattern
                + ', target "%s"\n' % user['target'])
            if not user['re'].match (recipient):
                continue

            self.logfunc (TRACE, 'user re matched recipient "%s"\n' % recipient)
            # Deliver the message to this user
            dt = self.deliver_msg (user['target'], self.message_add_info (msg, recipient), env_sender)
            self.logfunc (TRACE, 'delivered to "%s"\n' % user['target'])
            self.msglog ('Delivered to %s' % dt)
            delivered = delivered + 1

        return delivered

    #######################################
    def deliver_msg (self, dest, msg, env_sender):
        '''Determine the type of destination and dispatch to appropriate
        delivery routine.  Currently understands Maildirs and commands.
        The destination must exist; i.e. getmail will not create a maildir
        if the specified destination does not exist.
        '''
        global deliverycount
        # Handle command delivery first
        if dest and dest[0] == '|':
            dest = dest[1:]
            return self.deliver_command (dest, msg, env_sender)

        # If destination ends with '/', assume Maildir delivery
        if dest and dest[-1] == '/':
            deliverycount = deliverycount + 1
            return deliver_maildir (dest, string.replace (msg, line_end['pop3'], line_end['maildir']), self.info['hostname'], deliverycount)

        # Unknown destination type
        raise getmailDeliveryException, 'destination "%s" is not a Maildir or command' % dest

    ###################################
    def message_add_info (self, message, recipient):
        '''Add Delivered-To: and Received: info to headers of message.
        '''
        if self.conf['no_delivered_to']:
            delivered_to = ''
        else:
            # Construct Delivered-To: header with address local_part@localhostname
            delivered_to = 'Delivered-To: %s\n' % (recipient or 'unknown envelope recipient')

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
    def deliver_command (self, command, msg, env_sender):
        'Deliver a mail message to a command.'
        global deliverycount

        # At least some security...
        if os.geteuid () == 0:
            raise getmailDeliveryException, 'refuse to deliver to commands as root'

        # Construct mboxrd-style 'From_' line
        fromline = 'From %s %s\n' % (env_sender or '<>', time.asctime (time.gmtime (int (time.time ()))))

        self.logfunc (TRACE, 'delivering to command "%s"\n' % command)

        try:
            import popen2

            popen2._cleanup()
            #cmd = popen2.Popen3 (command, 1, bufsize=-1)
            cmd = popen2.Popen3 (command, 1, bufsize=512)
            cmdout, cmdin, cmderr = cmd.fromchild, cmd.tochild, cmd.childerr
            if self.conf['command_add_fromline']:
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
                raise getmailDeliveryException, 'command "%s" %s %s (%s)' % (command, exitcode, exitsignal, err)

            elif err:
                raise getmailDeliveryException, 'command "%s" exited 0 but wrote to stderr (%s)' % (command, err)

            if out:
                # Command wrote something to stdout
                self.logfunc (INFO, '  command "%s" said "%s"\n' % (command, out))

        except ImportError:
            raise getmailDeliveryException, 'popen2 module not found'

        except StandardError, txt:
            raise getmailDeliveryException, 'failure delivering message to command "%s" (%s)' % (command, txt)

        # Delivery done
        self.logfunc (TRACE, 'delivered to command "%s"\n' % command)

        deliverycount = deliverycount + 1
        return 'command "%s"' % command

    #######################################
    def filter_message (self, msg, command):
        '''Filter a mail message through a command.
        '''
        self.logfunc (TRACE, 'filtering through command "%s"\n' % command)
        try:
            import popen2
        except ImportError:
            raise getmailDeliveryException, 'popen2 module not found'

        # Set a 30-second alarm for this filter
        signal.signal (signal.SIGALRM, alarm_handler)
        signal.alarm (30)

        try:
            try:
                popen2._cleanup()
                cmd = popen2.Popen3 (command, 1, bufsize=-1)
                cmdout, cmdin, cmderr = cmd.fromchild, cmd.tochild, cmd.childerr
                cmdin.write (string.replace (msg, line_end['pop3'], line_end['mbox']))
                # Add trailing blank line
                cmdin.write ('\n')
                cmdin.flush ()
                cmdin.close ()

                r = cmd.wait ()
                err = string.strip (cmderr.read ())
                cmderr.close ()
                out = cmdout.read ()
                cmdout.close ()

                if not r:
                    # Exited 0, no signal
                    rc = 0
                else:
                    if os.WIFSIGNALED (r):
                        raise getmailDeliveryException, 'command "%s" exited on signal %s' % (command, os.WTERMSIG (r))
                    elif os.WIFSTOPPED (r):
                        raise getmailDeliveryException, 'command "%s" stopped' % command
                    elif not os.WIFEXITED (r):
                        raise getmailDeliveryException, 'command "%s" did not exit' % command
                    rc = os.WEXITSTATUS (r)

                if err:
                    self.logfunc (WARN, '\n  filter command "%s":  %s\n' % (command, err))

                if not out:
                    raise getmailDeliveryException, 'command "%s" did not produce output' % command

            except StandardError, txt:
                # DEBUG
                raise   
                #    raise getmailDeliveryException, 'failure filtering message through command "%s" (%s)' % (command, txt)

        finally:
            # Filter done, cancel alarm
            signal.alarm (0)
            signal.signal (signal.SIGALRM, signal.SIG_DFL)

        self.logfunc (TRACE, 'filtered through command "%s"\n' % command)
        return rc, out

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
            self.connect ()
            # Log in to server
            self.login ()
            # Let the user know what they're in for
            self.report_mailbox_size ()
            # Retrieve message list for this user.
            self.message_list ()

            inbox = []
            for (msgnum, msglen, msgid) in self.msglist:
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

                self.logfunc (INFO, '  msg #%i/%i : len %s ... ' % (msgnum, len (self.msglist) - 1, msglen))

                if msglen and self.conf['max_message_size'] and msglen > self.conf['max_message_size']:
                    self.logfunc (WARN, 'over max message size of %(max_message_size)i, skipping ...\n')
                    continue

                # Retrieve this message if:
                #   "get all mail" option is set, OR
                #   server does not support UIDL (msgid is None), OR
                #   this is a new message (not in oldmail)
                if self.conf['readall'] or msgid is None or not self.oldmail.has_key (msgid):
                    rc, msglines, octets = self.session.retr (msgnum)
                    msg = string.join (msglines + [''], line_end['pop3'])
                    self.logfunc (INFO, 'retrieved')
                    if NEED_REMOVE_LEADING_DOTS:
                        msg = pop3_unescape (msg)

                    try:
                        # Find recipients for this message and deliver to them.
                        count = self.process_msg (msg, msgnum, len (self.msglist) - 1, msglen)
                        if count == -1:
                            pass
                        elif count == 0:
                            self.logfunc (INFO, ' ... delivered to postmaster')
                            self.info['localscount'] = self.info['localscount'] + 1
                        elif count == 1:
                            self.logfunc (INFO, ' ... delivered 1 copy')
                            self.info['localscount'] = self.info['localscount'] + count
                        else:
                            self.logfunc (INFO, ' ... delivered %i copies' % count)
                            self.info['localscount'] = self.info['localscount'] + count

                    except getmailDeliveryException, txt:
                        self.logfunc (ERROR, ' ... failed delivering message (%s), skipping\n' % txt)
                        # Don't remember this message as "read" on error
                        del inbox[-1]
                        # Skip to next message, don't abort
                        continue

                    self.info['msgcount'] = self.info['msgcount'] + 1

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
                        self.logfunc (TRACE, time.strftime (' originally seen %Y-%m-%d %H:%M:%S', time.localtime (self.oldmail[msgid])))
                    else:
                        self.logfunc (TRACE, ' not previously seen')
                    if self.oldmail.has_key (msgid) and self.oldmail[msgid] < (self.timestamp - self.conf['delete_after'] * 86400):
                        rc = self.session.dele (msgnum)
                        self.logfunc (INFO, ' ... older than %(delete_after)i days, deleted')
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
            self.logfunc (INFO, 'Retrieved %(msgcount)i messages for %(localscount)i local recipients\n\n' % self.info)
            self.msglog ('Finished %s' % self)

        except SystemExit:
            raise

        except MemoryError:
            self.logfunc (ERROR, '  Memory exhausted (%s)\n' % self)
            self.abort ('Out of memory')

        except Timeout, txt:
            txt = 'TCP timeout'
            self.logfunc (ERROR, '  %s (%s)\n' % (txt, self))
            self.abort (txt)

        except SPDS_error_proto, txt:
            txt = 'POP3 protocol error (%s) (%s)' % (txt, self)
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except socket.error, txt:
            txt = 'Socket error (%s) (%s)' % (txt, self)
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except getmailConfigException, txt:
            txt = 'Configuration error (%s) (%s)' % (txt, self)
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except getmailNetworkError, txt:
            txt = 'Network error (%s) (%s)' % (txt, self)
            self.logfunc (ERROR, '  %s\n' % txt)
            self.abort (txt)

        except KeyboardInterrupt:
            txt = 'User aborted'
            self.logfunc (WARN, '  %s (%s)\n' % (txt, self))
            self.abort (txt)
            raise SystemExit

        except getmailUnhandledException, txt:
            txt = 'Unknown error (%s) (%s)' % (txt, self)
            self.logfunc (FATAL, '  %s\n' % txt)
            self.msglog (txt)
            raise getmailUnhandledException, txt

#
# Main script code
#

#######################################
def main ():
    '''Main entry point for getmail.
    '''
    config = defs.copy ()
    cmdline_opts = parse_options (sys.argv[1:], __version__)
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
            log (FATAL, '\nError:  no POP3 account configurations found in getmailrc file (%s)\n' % filename, config)
            help ()

        # Everything is go.
        if config['log_level'] < WARN:
            blurb ()
            version (__version__)

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
        log (FATAL, '\ngetmail bug:  please include the following information in any bug report:\n\n', config)
        log (FATAL, '  getmail version %s\n' % __version__, config)
        log (FATAL, '  ConfParser version %s\n' % ConfParser.__version__, config)
        log (FATAL, '  Python version %s\n\n' % sys.version, config)
        log (FATAL, 'Unhandled exception follows:\n', config)
        exc_type, value, tb = sys.exc_info ()
        tblist = traceback.format_tb (tb, None) + traceback.format_exception_only (exc_type, value)
        if type (tblist) != ListType:
            tblist = [tblist]
        for line in tblist:
            log (FATAL, '  ' + string.rstrip (line) + '\n', config)
        log (FATAL, '\n\Please also include configuration information from running getmail\n', config)
        log (FATAL, 'with your normal options plus "--dump".\n', config)
        sys.exit (exitcodes['ERROR'])

    sys.exit (exitcodes['OK'])

#######################################
if sys.hexversion < 0x010502f0:
    blurb ()
    version (__version__)
    sys.exit ('This program requires Python version 1.5.2 or later')
if __name__ == '__main__':
    main ()
