#!/usr/bin/env python2.3
'''Classes implementing destinations (files, directories, or programs getmail
can deliver mail to).

Currently implemented:

  Maildir
  Mboxrd
  MDA_qmaillocal (deliver though qmail-local as external MDA)
  MDA_external (deliver through an arbitrary external MDA)
  MultiSorter (deliver to a selection of maildirs/mbox files based on matching
    recipient address patterns)
'''

import os
import socket
import re
import signal
import types
import time

# Only on Unix
try:
    import pwd
except ImportError:
    pass

from exceptions import *
from utilities import *
from baseclasses import ConfigurableBase

#######################################
class DeliverySkeleton(ConfigurableBase):
    '''Base class for implementing message-delivery classes.

    Sub-classes should provide the following data attributes and methods:

      _confitems - a tuple of dictionaries representing the parameters the class
                   takes.  Each dictionary should contain the following key, value
                   pairs:
                     - name - parameter name
                     - type - a type function to compare the parameter value against (i.e. str, int, bool)
                     - default - optional default value.  If not preseent, the parameter is required.

      __str__(self) - return a simple string representing the class instance.

      showconf(self) - log a message representing the instance and configuration
                       from self._confstring().

      initialize(self) - process instantiation parameters from self.conf.
                         Raise getmailConfigurationError on errors.  Do any
                         other validation necessary, and set self.__initialized
                         when done.

      retriever_info(self, retriever) - extract information from retriever and store
                         it for use in message deliveries.

      _deliver_message(self, msg, delivered_to, received) - accept the message and deliver
                         it, returning a string describing the result.

    See the Maildir class for a good, simple example.
    '''
    def __init__(self, **args):
        ConfigurableBase.__init__(self, **args)
        try:
            self.initialize()
        except KeyError, o:
            raise getmailConfigurationError('missing required configuration parameter %s' % o)
        self.received_from = None
        self.received_with = None
        self.received_by = None
        self.log.trace('done\n')

    def retriever_info(self, retriever):
        self.log.trace()
        self.received_from = retriever.received_from
        self.received_with = retriever.received_with
        self.received_by = retriever.received_by

    def deliver_message(self, msg, delivered_to=True, received=True):
        self.log.trace()
        msg.received_from = self.received_from
        msg.received_with = self.received_with
        msg.received_by = self.received_by
        return self._deliver_message(msg, delivered_to, received)

#######################################
class Maildir(DeliverySkeleton):
    '''Maildir destination.

    Parameters:

      path - path to maildir, which will be expanded for leading '~/' or
      '~USER/', as well as environment variables.

    getmail will attempt to chown the file created to the UID and GID of the
    maildir.  If this fails (i.e. getmail does not have sufficient permissions),
    no error is raised.
    '''
    _confitems = (
        {'name' : 'path', 'type' : str},
    )

    def initialize(self):
        self.log.trace()
        self.hostname = socket.getfqdn()
        self.dcount = 0
        self.conf['path'] = expand_user_vars(self.conf['path'])
        if not self.conf['path'].endswith('/'):
            raise getmailConfigurationError('maildir path missing trailing / (%s)' % self.conf['path'])
        if not is_maildir(self.conf['path']):
            raise getmailConfigurationError('not a maildir (%s)' % self.conf['path'])

    def __str__(self):
        self.log.trace()
        return 'Maildir %s' % self.conf['path']

    def showconf(self):
        self.log.info('Maildir(%s)\n' % self._confstring())

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        f = deliver_maildir(self.conf['path'], msg.flatten(delivered_to, received), self.hostname, self.dcount)
        self.log.debug('maildir file %s' % f)
        self.dcount += 1
        return 'Maildir %snew/%s' % (self.conf['path'], f)

#######################################
class Mboxrd(DeliverySkeleton):
    '''mboxrd destination with fcntl-style locking.

    Parameters:

      path - path to mboxrd file, which will be expanded for leading '~/'
      or '~USER/', as well as environment variables.

    Note the differences between various subtypes of mbox format (mboxrd, mboxo,
    mboxcl, mboxcl2) and differences in locking; see the following for details:
    http://qmail.org/man/man5/mbox.html
    http://groups.google.com/groups?selm=4ivk9s%24bok%40hustle.rahul.net
    '''
    _confitems = (
        {'name' : 'path', 'type' : str},
    )

    def initialize(self):
        self.log.trace()
        self.conf['path'] = expand_user_vars(self.conf['path'])
        if os.path.exists(self.conf['path']) and not os.path.isfile(self.conf['path']):
            raise getmailConfigurationError('not an mboxrd file (%s)' % self.conf['path'])
        elif not os.path.exists(self.conf['path']):
            self.f = open(self.conf['path'], 'w+b')
            # Get user & group of containing directory
            s_dir = os.stat(os.path.dirname(self.conf['path']))
            try:
                # If root, change the new mbox file to be owned by the directory
                # owner and make it mode 0600
                os.chmod(self.conf['path'], 0600)
                os.chown(self.conf['path'], s_dir.st_uid, s_dir.st_gid)
            except OSError:
                # Not running as root, can't chown file
                pass
            self.log.debug('created mbox file %s' % self.conf['path'])
        else:
            # Check if it _is_ an mbox file.  mbox files must start with "From " in their first line, or
            # are 0-length files.
            self.f = open(self.conf['path'], 'r+b')
            lock_file(self.f)
            self.f.seek(0, 0)
            first_line = self.f.readline()
            unlock_file(self.f)
            if first_line and first_line[:5] != 'From ':
                # Not an mbox file; abort here
                raise getmailConfigurationError('destination "%s" is not an mbox file' % self.conf['path'])

    def __del__(self):
        # Unlock and close file
        self.log.trace()
        if hasattr(self, 'f'):
            unlock_file(self.f)
            self.f.close()

    def __str__(self):
        self.log.trace()
        return 'Mboxrd %s' % self.conf['path']

    def showconf(self):
        self.log.info('Mboxrd(%s)\n' % self._confstring())

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        status_old = os.fstat(self.f.fileno())
        lock_file(self.f)
        # Seek to end
        self.f.seek(0, 2)
        try:
            # Write out message plus blank line with native EOL
            self.f.write(msg.flatten(delivered_to, received, include_from=True, mangle_from=True) + os.linesep)
            self.f.flush()
            os.fsync(self.f.fileno())
            status_new = os.fstat(self.f.fileno())

            # Reset atime
            try:
                os.utime(self.conf['path'], (status_old.st_atime, status_new.st_mtime))
            except OSError, o:
                # Not root or owner; readers will not be able to reliably
                # detect new mail.  But you shouldn't be delivering to
                # other peoples' mboxes unless you're root, anyways.
                self.log.warn('failed to update atime/mtime of mbox file %s (%s)' % (self.conf['path'], o))

            unlock_file(self.f)

        except IOError, o:
            try:
                if not self.f.closed:
                    # If the file was opened and we know how long it was,
                    # try to truncate it back to that length
                    # If it's already closed, or the error occurred at close(),
                    # then there's not much we can do.
                    self.f.truncate(status_old.st_size)
            except:
                pass
            raise getmailDeliveryError('failure writing message to mbox file "%s" (%s)' % (self.conf['path'], o))

        return 'Mboxrd %s' % self.conf['path']

#######################################
class MDA_qmaillocal(DeliverySkeleton):
    '''qmail-local MDA destination.

    Passes the message to qmail-local for delivery.  qmail-local is invoked as:

      qmail-local -nN user homedir local dash ext domain sender defaultdelivery

    Parameters (all optional):

      qmaillocal - complete path to the qmail-local binary.  Defaults to "/var/qmail/bin/qmail-local".

      user - username supplied to qmail-local as the "user" argument.  Defaults to the login name of
             the current effective user ID.  If supplied, getmail will also change the effective
             UID to that of the user before running qmail-local.

      group - If supplied, getmail will change the effective GID to that of the named
             group before running qmail-local.

      homedir - complete path to the directory supplied to qmail-local as the "homedir" argument.
                Defaults to the home directory of the current effective user ID.

      localdomain - supplied to qmail-local as the "domain" argument.  Defaults to socket.getfqdn().

      defaultdelivery - supplied to qmail-local as the "defaultdelivery" argument.  Defaults to "./Maildir/".

      conf-break - supplied to qmail-local as the "dash" argument and used to calculate ext
                   from local.  Defaults to "-".

      localpart_translate - a string representing a Python 2-tuple of strings (i.e. "('foo', 'bar')").
                           If supplied, the retrieved message recipient address will have any leading instance of
                           "foo" replaced with "bar" before being broken into "local" and "ext" for qmail-local
                           (according to the values of "conf-break" and "user").  This can be used to add or remove a prefix of
                           the address.

      strip_delivered_to - if set, existing Delivered-To: header fields will be removed from the message before
                           processing by qmail-local.  This may be necessary to prevent qmail-local falsely
                           detecting a looping message if (for instance) the system
                           retrieving messages otherwise believes it has the same domain name as the POP
                           server.  Inappropriate use, however, may cause message loops.

      allow_root_commands (boolean, optional) - if set, external commands are allowed when
                                                running as root.  The default is not to allow
                                                such behaviour.

    For example, if getmail is run as user "exampledotorg", which has virtual domain
    "example.org" delegated to it with a virtualdomains entry of "example.org:exampledotorg",
    and messages are retrieved with envelope recipients like "trimtext-localpart@example.org",
    the messages could be properly passed to qmail-local with a localpart_translate value of
    "('trimtext-', '')" (and perhaps a defaultdelivery value of "./Maildirs/postmaster/" or
    similar).
    '''

    _confitems = (
        {'name' : 'qmaillocal', 'type' : str, 'default' : '/var/qmail/bin/qmail-local'},
        {'name' : 'user', 'type' : str, 'default' : pwd.getpwuid(os.geteuid()).pw_name},
        {'name' : 'group', 'type' : str, 'default' : None},
        {'name' : 'homedir', 'type' : str, 'default' : pwd.getpwuid(os.geteuid()).pw_dir},
        {'name' : 'localdomain', 'type' : str, 'default' : socket.getfqdn()},
        {'name' : 'defaultdelivery', 'type' : str, 'default' : './Maildir/'},
        {'name' : 'conf-break', 'type' : str, 'default' : '-'},
        {'name' : 'localpart_translate', 'type' : tuple, 'default' : ('', '')},
        {'name' : 'strip_delivered_to', 'type' : bool, 'default' : False},
        {'name' : 'allow_root_commands', 'type' : bool, 'default' : False},
    )

    def initialize(self):
        self.log.trace()
        self.conf['qmaillocal'] = expand_user_vars(self.conf['qmaillocal'])
        self.conf['homedir'] = expand_user_vars(self.conf['homedir'])
        if not os.path.isdir(self.conf['homedir']):
            raise getmailConfigurationError('no such directory %s' % self.conf['homedir'])

    def __str__(self):
        self.log.trace()
        return 'MDA_qmaillocal %s' % self._confstring()

    def showconf(self):
        self.log.info('MDA_qmaillocal(%s)\n' % self._confstring())

    def _deliver_qmaillocal(self, msg, msginfo, delivered_to, received, stdout, stderr):
        try:
            args = (self.conf['qmaillocal'], self.conf['qmaillocal'], '--', self.conf['user'], self.conf['homedir'], msginfo['local'], msginfo['dash'], msginfo['ext'], self.conf['localdomain'], msginfo['sender'], self.conf['defaultdelivery'])
            self.log.debug('about to execl() with args %s\n' % str(args))
            # Modify message
            if self.conf['strip_delivered_to']:
                del msg['delivered-to']
            # Write out message
            msgfile = os.tmpfile()
            msgfile.write(msg.flatten(delivered_to, received))
            msgfile.flush()
            os.fsync(msgfile.fileno())
            # Rewind
            msgfile.seek(0)
            # Set stdin to read from this file
            os.dup2(msgfile.fileno(), 0)
            # Set stdout and stderr to write to files
            os.dup2(stdout.fileno(), 1)
            os.dup2(stderr.fileno(), 2)
            change_uidgid(self.log, self.conf['user'], self.conf['group'])
            os.execl(*args)
        except StandardError, o:
            # Child process; any error must cause us to exit nonzero for parent to detect it
            self.log.critical('exec of qmail-local failed (%s)' % o)
            os._exit(127)

    def _child_handler(self, sig, stackframe):
        self.log.trace('handler called for signal %s' % sig)
        try:
            pid, r = os.wait()
        except OSError, o:
            # No children on SIGCHLD.  Can't happen?
            self.log.warning('handler called, but no children (%s)' % o)
        self._child_pid = pid
        self._child_status = r
        self.log.trace('handler reaped child %s with status %s' % (pid, r))
        self._child_exited = True

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        self._child_exited = False
        self._child_pid = None
        self._child_status = None
        try:
            msginfo = {
                'sender' : msg.sender,
                'local' : '@'.join(msg.recipient.lower().split('@')[:-1])
            }
        except AttributeError, o:
            raise getmailConfigurationError('MDA_qmaillocal destination requires a message source that preserves the message envelope (%s)' % o)

        self.log.debug('recipient: extracted local-part "%s"\n' % msginfo['local'])
        xlate_from, xlate_to = self.conf['localpart_translate']
        if xlate_from or xlate_to:
            if msginfo['local'].startswith(xlate_from):
                self.log.debug('recipient: translating "%s" to "%s"\n' % (xlate_from, xlate_to))
                msginfo['local'] = xlate_to + msginfo['local'][len(xlate_from):]
            else:
                self.log.debug('recipient: does not start with xlate_from "%s"\n' % xlate_from)
        self.log.debug('recipient: translated local-part "%s"\n' % msginfo['local'])
        if self.conf['conf-break'] in msginfo['local']:
            msginfo['dash'] = self.conf['conf-break']
            msginfo['ext'] = self.conf['conf-break'].join(msginfo['local'].split(self.conf['conf-break'])[1:])
        else:
            msginfo['dash'] = ''
            msginfo['ext'] = ''
        self.log.debug('recipient: set dash to "%s", ext to "%s"\n' % (msginfo['dash'], msginfo['ext']))

        # At least some security...
        if os.geteuid() == 0 and not self.conf['allow_root_commands']:
            raise getmailConfigurationError('refuse to invoke external commands as root by default')

        signal.signal(signal.SIGCHLD, self._child_handler)

        stdout = os.tmpfile()
        stderr = os.tmpfile()
        childpid = os.fork()

        if not childpid:
            # Child
            self._deliver_qmaillocal(msg, msginfo, delivered_to, received, stdout, stderr)
        self.log.debug('spawned child %d\n' % childpid)

        # Parent
        while not self._child_exited:
            self.log.trace('waiting for child %d' % childpid)
            time.sleep(1.0)
            #raise getmailDeliveryError('failed waiting for qmail-local %d (%s)' % (childpid, o))

        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        pid = self._child_pid
        r = self._child_status

        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read().strip()
        err = stderr.read().strip()

        if os.WIFSTOPPED(r):
            raise getmailDeliveryError('qmail-local %d stopped by signal %d' % (pid, os.WSTOPSIG(r)))
        if os.WIFSIGNALED(r):
            raise getmailDeliveryError('qmail-local %d killed by signal %d' % (pid, os.WTERMSIG(r)))
        if not os.WIFEXITED(r):
            raise getmailDeliveryError('qmail-local %d failed to exit' % pid)
        exitcode = os.WEXITSTATUS(r)

        self.log.debug('qmail-local %d exited %d\n' % (pid, exitcode))

        if exitcode == 111:
            raise getmailDeliveryError('qmail-local %d temporary error (%s)' % (pid, err))
        elif exitcode or err:
            raise getmailDeliveryError('qmail-local %d error (%d, %s)' % (pid, exitcode, err))

        return 'MDA_qmaillocal (%s)' % out

#######################################
class MDA_external(DeliverySkeleton):
    '''Arbitrary external MDA destination.

    Parameters:

      path - path to the external MDA binary.

      unixfrom - (boolean) whether to include a Unix From_ line at the beginning
                 of the message.  Defaults to False.

      arguments - a valid Python tuple of strings to be passed as arguments to
                  the command.  The following replacements are available if
                  supported by the retriever:

                    %(sender) - envelope return path
                    %(recipient) - recipient address
                    %(domain) - domain-part of recipient address
                    %(local) - local-part of recipient address

                  Warning: the text of these replacements is taken from the message
                  and is therefore under the control of a potential attacker.
                  DO NOT PASS THESE VALUES TO A SHELL -- they may contain unsafe
                  shell metacharacters or other hostile constructions.

                  example:

                    path = /path/to/mymda
                    arguments = ('--demime', '-f%(sender)', '--', '%(recipient)')

      user (string, optional) - if provided, the external command will be run as the
                                specified user.  This requires that the main getmail
                                process have permission to change the effective user
                                ID.

      group (string, optional) -  if provided, the external command will be run with the
                                specified group ID.  This requires that the main getmail
                                process have permission to change the effective group
                                ID.

      allow_root_commands (boolean, optional) - if set, external commands are allowed when
                                                running as root.  The default is not to allow
                                                such behaviour.
    '''
    _confitems = (
        {'name' : 'path', 'type' : str},
        {'name' : 'arguments', 'type' : tuple, 'default' : ()},
        {'name' : 'unixfrom', 'type' : bool, 'default' : False},
        {'name' : 'user', 'type' : str, 'default' : None},
        {'name' : 'group', 'type' : str, 'default' : None},
        {'name' : 'allow_root_commands', 'type' : bool, 'default' : False},
    )

    def initialize(self):
        self.log.trace()
        self.conf['path'] = expand_user_vars(self.conf['path'])
        self.conf['command'] = os.path.basename(self.conf['path'])
        if not os.path.isfile(self.conf['path']):
            raise getmailConfigurationError('no such command %s' % self.conf['path'])
        if not os.access(self.conf['path'], os.X_OK):
            raise getmailConfigurationError('%s not executable' % self.conf['path'])
        if type(self.conf['arguments']) != tuple:
            raise getmailConfigurationError('incorrect arguments format; see documentation (%s)' % self.conf['arguments'])

    def __str__(self):
        self.log.trace()
        return 'MDA_external %s' % self._confstring()

    def showconf(self):
        self.log.info('MDA_external(%s)\n' % self._confstring())

    def _deliver_command(self, msg, msginfo, delivered_to, received, stdout, stderr):
        try:
            # Write out message with native EOL convention
            msgfile = os.tmpfile()
            msgfile.write(msg.flatten(delivered_to, received, include_from=self.conf['unixfrom']))
            msgfile.flush()
            os.fsync(msgfile.fileno())
            # Rewind
            msgfile.seek(0)
            # Set stdin to read from this file
            os.dup2(msgfile.fileno(), 0)
            # Set stdout and stderr to write to files
            os.dup2(stdout.fileno(), 1)
            os.dup2(stderr.fileno(), 2)
            change_uidgid(self.log, self.conf['user'], self.conf['group'])
            args = [self.conf['path'], self.conf['path']]
            for arg in self.conf['arguments']:
                arg = expand_user_vars(arg)
                for (key, value) in msginfo.items():
                    arg = arg.replace('%%(%s)' % key, value)
                args.append(arg)
            self.log.debug('about to execl() with args %s\n' % str(args))
            os.execl(*args)
        except StandardError, o:
            # Child process; any error must cause us to exit nonzero for parent to detect it
            self.log.critical('exec of command %s failed (%s)' % (self.conf['command'], o))
            os._exit(127)

    def _child_handler(self, sig, stackframe):
        self.log.trace('handler called for signal %s' % sig)
        try:
            pid, r = os.wait()
        except OSError, o:
            # No children on SIGCHLD.  Can't happen?
            self.log.warning('handler called, but no children (%s)' % o)
        self._child_pid = pid
        self._child_status = r
        self.log.trace('handler reaped child %s with status %s' % (pid, r))
        self._child_exited = True

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        self._child_exited = False
        self._child_pid = None
        self._child_status = None
        msginfo = {}
        msginfo['sender'] = msg.sender
        if msg.recipient is not None:
            msginfo['recipient'] = msg.recipient
            msginfo['domain'] = msg.recipient.lower().split('@')[-1]
            msginfo['local'] = '@'.join(msg.recipient.split('@')[:-1])
        self.log.debug('msginfo "%s"\n' % msginfo)

        # At least some security...
        if os.geteuid() == 0 and not self.conf['allow_root_commands'] and self.conf['user'] == None:
            raise getmailConfigurationError('refuse to invoke external commands as root by default')

        signal.signal(signal.SIGCHLD, self._child_handler)

        stdout = os.tmpfile()
        stderr = os.tmpfile()
        childpid = os.fork()

        if not childpid:
            # Child
            self._deliver_command(msg, msginfo, delivered_to, received, stdout, stderr)
        self.log.debug('spawned child %d\n' % childpid)

        # Parent
        while not self._child_exited:
            self.log.trace('waiting for child %d' % childpid)
            time.sleep(1.0)
            #raise getmailDeliveryError('failed waiting for command %s %d (%s)' % (self.conf['command'], childpid, o))

        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        pid = self._child_pid
        r = self._child_status

        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read().strip()
        err = stderr.read().strip()

        if os.WIFSTOPPED(r):
            raise getmailDeliveryError('command %s %d stopped by signal %d' % (self.conf['command'], pid, os.WSTOPSIG(r)))
        if os.WIFSIGNALED(r):
            raise getmailDeliveryError('command %s %d killed by signal %d' % (self.conf['command'], pid, os.WTERMSIG(r)))
        if not os.WIFEXITED(r):
            raise getmailDeliveryError('command %s %d failed to exit' % (self.conf['command'], pid))
        exitcode = os.WEXITSTATUS(r)

        self.log.debug('command %s %d exited %d\n' % (self.conf['command'], pid, exitcode))

        if exitcode or err:
            raise getmailDeliveryError('command %s %d error (%d, %s)' % (self.conf['command'], pid, exitcode, err))

        return 'MDA_external command %s (%s)' % (self.conf['command'], out)

#######################################
class MultiSorter(DeliverySkeleton):
    '''Multiple maildir/mboxrd destination with recipient address matching.

    Parameters:

      default - the default maildir destination path.  Messages not matching any
                "local" patterns (see below) will be delivered here.

      locals - an optional list of regular expression and maildir/mbox path pairs (whitespace-separated).
               In the general case, an email address is a valid regular expression.
               Each pair is on a separate line; the second and subsequent lines need
               to have leading whitespace to be considered a continuation of the "locals"
               configuration.  If the recipient address matches a given pattern, it will
               be delivered to the corresponding destination.  A destination is assumed to
               be a maildir if it starts with a dot or slash and ends with a slash.
               A destination is assumed to be an mboxrd file if it starts with a dot or
               a slash and does not end with a slash.  A destination may also be specified
               by section name, i.e. "[othersectionname]".
               Multiple patterns may match a given recipient address; the
               message will be delivered to /all/ maildirs with matching
               patterns.  Patterns are matched case-insensitively.

               example:

                 default = /home/kellyw/Mail/postmaster/
                 locals = jason@example.org             /home/jasonk/Maildir/
                   sales@example.org                    /home/karlyk/Mail/sales
                   abuse@(example.org|example.net)      /home/kellyw/Mail/abuse/
                   ^(jeff|jefferey)(\.s(mith)?)?@.*$    [jeff-mail-delivery]
                   ^.*@(mail.)?rapinder.example.org$    /home/rapinder/Maildir/

               In it's simplest form, locals is merely a list of pairs of
               email addresses and corresponding maildir/mbox paths.  Don't worry
               about the details of regular expressions if you aren't familiar
               with them.
    '''
    _confitems = (
        {'name' : 'default', 'type' : str},
        {'name' : 'locals', 'type' : str, 'default' : ''},
        {'name' : 'configparser', 'type' : types.InstanceType, 'default' : None},
    )

    def _get_destination(self, path):
        p = expand_user_vars(path)
        if p.startswith('[') and p.endswith(']'):
            destsectionname = p[1:-1]
            if not destsectionname in self.conf['configparser'].sections():
                raise getmailConfigurationError('destination specifies section name %s which does not exist' % path)
            # Construct destination instance
            log.debug('  getting destination for %s\n' % path)
            destination_type = self.conf['configparser'].get(destsectionname, 'type')
            log.debug('    type="%s"\n' % destination_type)
            destination_func = getattr(globals(), destination_type)
            if not callable(destination_func):
                raise getmailConfigurationError('configuration file section %s specifies incorrect destination type (%s)' % (destsectionname, destination_type))
            destination_args = {'configparser' : self.conf['configparser']}
            for (name, value) in self.conf['configparser'].items(destsectionname):
                if name in ('type', 'configparser'): continue
                log.debug('    parameter %s="%s"\n' % (name, value))
                destination_args[name] = value
            log.debug('    instantiating destination %s with args %s\n' % (destination_type, destination_args))
            dest = destination_func(**destination_args)
        elif (p.startswith('/') or p.startswith('.')) and p.endswith('/'):
            dest = Maildir(path=p)
        elif (p.startswith('/') or p.startswith('.')):
            dest = Mboxrd(path=p)
        else:
            raise getmailConfigurationError('specified destination %s not of recognized type' % p)
        return dest

    def initialize(self):
        self.log.trace()
        self.hostname = socket.getfqdn()
        self.default = self._get_destination(self.conf['default'])
        self.targets = []
        try:
            for (pattern, path) in [line.strip().split(None, 1) for line in self.conf['locals'].split(os.linesep) if line.strip()]:
                try:
                    dest = self._get_destination(path)
                except getmailConfigurationError, o:
                    raise getmailConfigurationError('pattern %s destination error %s' % (pattern, o))
                self.targets.append( (re.compile(pattern.replace('\\', '\\\\'), re.IGNORECASE), dest) )
        except re.error, o:
            raise getmailConfigurationError('invalid regular expression %s' % o)
        except ValueError, o:
            raise getmailConfigurationError('invalid syntax for locals ; see documentation (%s)' % o)

    def _confstring(self):
        '''Override the base class implementation; locals isn't readable that way.'''
        self.log.trace()
        confstring = 'default=%s' % self.default
        for (pattern, destination) in self.targets:
            confstring += ',%s->%s' % (pattern.pattern, destination)
        return confstring

    def __str__(self):
        self.log.trace()
        return 'MultiSorter %s' % self._confstring()

    def showconf(self):
        self.log.info('MultiSorter(%s)\n' % self._confstring())

    def retriever_info(self, retriever):
        '''Override base class to pass this to the encapsulated destinations.
        '''
        self.log.trace()
        DeliverySkeleton.retriever_info(self, retriever)
        self.default.retriever_info(retriever)
        for (unused, destination) in self.targets:
            destination.retriever_info(retriever)

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        matched = []
        try:
            for (pattern, dest) in self.targets:
                self.log.debug('checking recipient %s against pattern %s\n' % (msg.recipient, pattern.pattern))
                if pattern.search(msg.recipient):
                    self.log.debug('recipient %s matched target %s\n' % (msg.recipient, dest))
                    dest.deliver_message(msg, delivered_to, received)
                    matched.append(str(dest))
            if not matched:
                if self.targets:
                    self.log.debug('recipient %s not matched; using default %s\n' % (msg.recipient, self.default))
                else:
                    self.log.debug('using default %s\n' % self.default)
                return 'MultiSorter (default %s)' % self.default.deliver_message(msg, delivered_to, received)
            return 'MultiSorter (%s)' % matched
        except AttributeError, o:
            raise getmailConfigurationError('MultiSorter recipient matching requires a retriever (message source) that preserves the message envelope (%s)' % o)
