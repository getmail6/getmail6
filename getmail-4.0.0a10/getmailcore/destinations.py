#!/usr/bin/env python2.3
'''Classes implementing destinations (files, directories, or programs getmail can deliver mail to).

Currently implemented:

  Maildir
  Mboxrd
  MDA_qmaillocal (deliver though qmail-local as external MDA)
  MDA_external (deliver through an arbitrary external MDA)
  MultiSorter (deliver to a selection of maildirs/mbox files based on matching recipient address patterns)
'''

import os
import socket
import re
import pwd
import signal

from exceptions import *
from utilities import is_maildir, deliver_maildir, mbox_from_escape, mbox_timestamp, lock_file, unlock_file
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

      _deliver_message(self, msg) - accept the message and deliver it, returning
                                    a string describing the result.

    See the Maildir class for a good, simple example.
    '''
    def __init__(self, **args):
        ConfigurableBase.__init__(self, **args)
        try:
            self.initialize()
        except KeyError, o:
            raise getmailConfigurationError('missing parameter %s' % o)
        self.log.trace('done\n')

    def deliver_message(self, msg):
        self.log.trace()
        return self._deliver_message(msg)

#######################################
class Maildir(DeliverySkeleton):
    '''Maildir destination.

    Parameters:

      path - path to maildir, which will be expanded for leading '~/' or '~USER/'.

    getmail will attempt to chown the file created to the UID and GID of the
    maildir.  If this fails (i.e. getmail does not have sufficient permissions),
    no error is raised.
    '''
    _confitems = (
        {'name' : 'path', 'type' : str},
    )

    def initialize(self):
        self.log.trace()
        self.hostname = socket.gethostname()
        self.dcount = 0
        self.conf['path'] = os.path.expanduser(self.conf['path'])
        if not self.conf['path'].endswith('/'):
            raise getmailConfigurationError('maildir path missing trailing / (%s)' % self.conf['path'])
        if not is_maildir(self.conf['path']):
            raise getmailConfigurationError('not a maildir (%s)' % self.conf['path'])

    def __str__(self):
        self.log.trace()
        return 'Maildir %s' % self.conf['path']

    def showconf(self):
        self.log.info('Maildir(%s)\n' % self._confstring())

    def _deliver_message(self, msg):
        self.log.trace()
        data = os.linesep.join(msg.as_string(unixfrom=False).splitlines())
        f = deliver_maildir(self.conf['path'], data, self.hostname, self.dcount)
        self.log.debug('maildir file %s' % f)
        self.dcount += 1
        return 'Maildir %snew/%s' % (self.conf['path'], f)

#######################################
class Mboxrd(DeliverySkeleton):
    '''mboxrd destination with fcntl-style locking.

    Parameters:

      path - path to mboxrd file, which will be expanded for leading '~/' or '~USER/'.

    Note the differences between various subtypes of mbox format (mboxrd, mboxo,
    mboxcl, mboxcl2) and differences in locking; see
    http://qmail.org/man/man5/mbox.html for details.
    '''
    _confitems = (
        {'name' : 'path', 'type' : str},
    )
    # Regular expression object to escape "From ", ">From ", ">>From ", ...
    # with ">From ", ">>From ", ... in mbox deliveries.  This is for mboxrd format
    # mboxes.
    efrom = re.compile(r'^(?P<gts>\>*)From ', re.MULTILINE)

    def initialize(self):
        self.log.trace()
        self.conf['path'] = os.path.expanduser(self.conf['path'])
        if os.path.exists(self.conf['path']) and not os.path.isfile(self.conf['path']):
            raise getmailConfigurationError('not an mboxrd file (%s)' % self.conf['path'])
        elif not os.path.exists(self.conf['path']):
            self.f = file(self.conf['path'], 'w+b')
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
            self.f = file(self.conf['path'], 'r+b')
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

    def _deliver_message(self, msg):
        self.log.trace()
        status_old = os.fstat(self.f.fileno())
        lock_file(self.f)
        # Seek to end
        self.f.seek(0, 2)
        try:
            self.f.write('From %s %s%s' % (mbox_from_escape(msg.sender), mbox_timestamp(), os.linesep))
            lines = self.efrom.sub('>\g<gts>From ', msg.as_string(unixfrom=False)).splitlines()
            # Write out message with native EOL convention
            self.f.write(os.linesep.join(lines + ['', '']))
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
             the current effective user ID.

      homedir - complete path to the directory supplied to qmail-local as the "homedir" argument.
                Defaults to the home directory of the current effective user ID.

      localdomain - supplied to qmail-local as the "domain" argument.  Defaults to socket.gethostname().

      defaultdelivery - supplied to qmail-local as the "defaultdelivery" argument.  Defaults to "./Maildir/".

      conf-break - supplied to qmail-local as the "dash" argument.  Defaults to "-".

      localparttranslate - a string representing a Python 2-tuple of strings (i.e. "('foo', 'bar')").
                           If supplied, the retrieved message recipient address will have any leading instance of
                           "foo" replaced with "bar" before being broken into "local" and "ext" for qmail-local
                           (according to the values of "conf-break" and "user").  This can be used to add or remove a prefix of
                           the address.

    For example, if getmail is run as user "exampledotorg", which has virtual domain
    "example.org" delegated to it with a virtualdomains entry of "example.org:exampledotorg",
    and messages are retrieved with envelope recipients like "trimtext-localpart@example.org",
    the messages could be properly passed to qmail-local with a localparttranslate value of
    "('trimtext-', '')" (and perhaps a defaultdelivery value of "./Maildirs/postmaster/" or
    similar).

    FIXME:  Processing of retrieved addresses should be cleaned up.
    '''

    _confitems = (
        {'name' : 'qmaillocal', 'type' : str, 'default' : '/var/qmail/bin/qmail-local'},
        {'name' : 'user', 'type' : str, 'default' : pwd.getpwuid(os.geteuid()).pw_name},
        {'name' : 'homedir', 'type' : str, 'default' : pwd.getpwuid(os.geteuid()).pw_dir},
        {'name' : 'localdomain', 'type' : str, 'default' : socket.gethostname()},
        {'name' : 'defaultdelivery', 'type' : str, 'default' : './Maildir/'},
        {'name' : 'conf-break', 'type' : str, 'default' : '-'},
        {'name' : 'localparttranslate', 'type' : tuple, 'default' : ('', '')},
    )

    def initialize(self):
        self.log.trace()
        self.conf['qmaillocal'] = os.path.expanduser(self.conf['qmaillocal'])
        self.conf['homedir'] = os.path.expanduser(self.conf['homedir'])
        if not os.path.isdir(self.conf['homedir']):
            raise getmailConfigurationError('no such directory %s' % self.conf['homedir'])

    def __str__(self):
        self.log.trace()
        return 'MDA_qmaillocal %s' % self._confstring()

    def showconf(self):
        self.log.info('MDA_qmaillocal(%s)\n' % self._confstring())

    def _deliver_qmaillocal(self, msg, msginfo, stdout, stderr):
        args = (self.conf['qmaillocal'], self.conf['qmaillocal'], '--', self.conf['user'], self.conf['homedir'], msginfo['local'], msginfo['dash'], msginfo['ext'], self.conf['localdomain'], msginfo['sender'], self.conf['defaultdelivery'])
        self.log.debug('about to execl() with args %s\n' % str(args))
        # Modify message
        del msg['return-path']
        # Write out message with native EOL convention
        msgfile = os.tmpfile()
        lines = msg.as_string(unixfrom=False).splitlines()
        msgfile.write(os.linesep.join(lines))
        msgfile.flush()
        os.fsync(msgfile.fileno())
        # Rewind
        msgfile.seek(0)
        # Set stdin to read from this file
        os.dup2(msgfile.fileno(), 0)
        # Set stdout and stderr to write to files
        os.dup2(stdout.fileno(), 1)
        os.dup2(stderr.fileno(), 2)
        try:
            os.execl(*args)
        except OSError, o:
            raise getmailDeliveryError('exec of qmail-local failed (%s)' % o)

    def _deliver_message(self, msg):
        self.log.trace()
        try:
            msginfo = {
                'sender' : msg.sender,
                'local' : '@'.join(msg.recipient.lower().split('@')[:-1])
            }
        except AttributeError, o:
            raise getmailConfigurationError('MDA_qmaillocal destination requires a message source that preserves the message envelope (%s)' % o)

        self.log.debug('recipient: extracted local-part "%s"\n' % msginfo['local'])
        xlate_from, xlate_to = self.conf['localparttranslate']
        if xlate_from or xlate_to:
            if msginfo['local'].startswith(xlate_from):
                self.log.debug('recipient: translating "%s" to "%s"\n' % (xlate_from, xlate_to))
                msginfo['local'] = xlate_to + msginfo['local'][len(xlate_from):]
            else:
                self.log.debug('recipient: does not start with xlate_from "%s"\n' % xlate_from)
        self.log.debug('recipient: translated local-part "%s"\n' % msginfo['local'])
        if self.conf['conf-break'] in msginfo['local']:
            msginfo['dash'] = '-'
            msginfo['ext'] = '-'.join(msginfo['local'].split('-')[1:])
        else:
            msginfo['dash'] = ''
            msginfo['ext'] = ''
        self.log.debug('recipient: set dash to "%s", ext to "%s"\n' % (msginfo['dash'], msginfo['ext']))

        # At least some security...
        if os.geteuid() == 0:
            raise getmailConfigurationError('refuse to invoke external commands as root')

        orighandler = signal.getsignal(signal.SIGCHLD)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

        stdout = os.tmpfile()
        stderr = os.tmpfile()
        childpid = os.fork()

        if not childpid:
            # Child
            self._deliver_qmaillocal(msg, msginfo, stdout, stderr)
        self.log.debug('spawned child %d\n' % childpid)

        # Parent
        try:
            pid, r = os.waitpid(childpid, 0)
        except OSError, o:
            raise getmailDeliveryError('failed waiting for qmail-local %d (%s)' % (childpid, o))

        signal.signal(signal.SIGCHLD, orighandler)
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
    '''
    _confitems = (
        {'name' : 'path', 'type' : str},
        {'name' : 'arguments', 'type' : tuple, 'default' : ()},
        {'name' : 'unixfrom', 'type' : bool, 'default' : False},
    )

    def initialize(self):
        self.log.trace()
        self.conf['path'] = os.path.expanduser(self.conf['path'])
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

    def _deliver_command(self, msg, msginfo, stdout, stderr):
        args = [self.conf['path'], self.conf['path']]
        for arg in self.conf['arguments']:
            for (key, value) in msginfo.items():
                arg = arg.replace('%%(%s)' % key, value)
            args.append(arg)
        self.log.debug('about to execl() with args %s\n' % str(args))
        # Modify message
        del msg['return-path']
        # Write out message with native EOL convention
        msgfile = os.tmpfile()
        lines = msg.as_string(unixfrom=self.conf['unixfrom']).splitlines()
        msgfile.write(os.linesep.join(lines))
        msgfile.flush()
        os.fsync(msgfile.fileno())
        # Rewind
        msgfile.seek(0)
        # Set stdin to read from this file
        os.dup2(msgfile.fileno(), 0)
        # Set stdout and stderr to write to files
        os.dup2(stdout.fileno(), 1)
        os.dup2(stderr.fileno(), 2)
        try:
            os.execl(*args)
        except OSError, o:
            raise getmailDeliveryError('exec of command %s failed (%s)' % (self.conf['command'], o))

    def _deliver_message(self, msg):
        self.log.trace()
        msginfo = {}
        if hasattr(msg, 'sender'):
            msginfo['sender'] = msg.sender
        if hasattr(msg, 'recipient'):
            msginfo['recipient'] = msg.recipient
            msginfo['domain'] = msg.recipient.lower().split('@')[-1]
            msginfo['local'] = '@'.join(msg.recipient.split('@')[:-1])
        self.log.debug('msginfo "%s"\n' % msginfo)

        # At least some security...
        if os.geteuid() == 0:
            raise getmailConfigurationError('refuse to invoke external commands as root')

        orighandler = signal.getsignal(signal.SIGCHLD)
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)

        stdout = os.tmpfile()
        stderr = os.tmpfile()
        childpid = os.fork()

        if not childpid:
            # Child
            self._deliver_command(msg, msginfo, stdout, stderr)
        self.log.debug('spawned child %d\n' % childpid)

        # Parent
        try:
            pid, r = os.waitpid(childpid, 0)
        except OSError, o:
            raise getmailDeliveryError('failed waiting for command %s %d (%s)' % (self.conf['command'], childpid, o))

        signal.signal(signal.SIGCHLD, orighandler)
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
               be delivered to the corresponding maildir or mbox file.  Multiple patterns may match
               a given recipient address; the message will be delivered to /all/ maildirs
               with matching patterns.  Patterns are matched case-insensitively.
               If the destination ends with a slash, it is assumed to be a maildir;
               else, it is an mbox file.

               example:

                 default = /home/kellyw/Mail/postmaster/
                 locals = jason@example.org             /home/jasonk/Maildir/
                   sales@example.org                    /home/karlyk/Mail/sales
                   abuse@(example.org|example.net)      /home/kellyw/Mail/abuse/
                   ^(jeff|jefferey)(\.s(mith)?)?@.*$    /home/jeffs/inbox
                   ^.*@(mail.)?rapinder.example.org$    /home/rapinder/Maildir/

               In it's simplest form, locals is merely a list of pairs of
               email addresses and corresponding maildir/mbox paths.  Don't worry
               about the details of regular expressions if you aren't familiar
               with them.

    FIXME: handle program delivery?  Ugh, difficult to get program arguments
    into a single string-type declaration of the destination like v.3.
    '''
    _confitems = (
        {'name' : 'default', 'type' : str},
        {'name' : 'locals', 'type' : str, 'default' : ''},
    )

    def initialize(self):
        self.log.trace()
        self.hostname = socket.gethostname()
        p = os.path.expanduser(self.conf['default'])
        if p.endswith('/'):
            self.default = Maildir(path=p)
        else:
            self.default = Mboxrd(path=p)
        self.targets = []
        try:
            for (pattern, path) in [line.strip().split(None, 1) for line in self.conf['locals'].split(os.linesep) if line.strip()]:
                p = os.path.expanduser(path)
                if p.endswith('/'):
                    dest = Maildir(path=p)
                else:
                    dest = Mboxrd(path=p)
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

    def _deliver_message(self, msg):
        self.log.trace()
        matched = []
        try:
            for (pattern, dest) in self.targets:
                self.log.debug('checking recipient %s against pattern %s\n' % (msg.recipient, pattern.pattern))
                if pattern.search(msg.recipient):
                    self.log.debug('recipient %s matched target %s\n' % (msg.recipient, dest))
                    dest.deliver_message(msg)
                    matched.append(str(dest))
            if not matched:
                if self.targets:
                    self.log.debug('recipient %s not matched; using default %s\n' % (msg.recipient, self.default))
                else:
                    self.log.debug('using default %s\n' % self.default)
                return 'MultiSorter (default %s)' % self.default.deliver_message(msg)
            return 'MultiSorter (%s)' % matched
        except AttributeError, o:
            raise getmailConfigurationError('MultiSorter recipient matching requires a retriever (message source) that preserves the message envelope (%s)' % o)
