# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

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

__all__ = [
    'DeliverySkeleton',
    'Maildir',
    'Mboxrd',
    'MDA_qmaillocal',
    'MDA_external',
    'MultiDestinationBase',
    'MultiDestination',
    'MultiSorterBase',
    'MultiSorter',
]

import sys
import os
import re
import types

try:
    import email.Utils as Utils
except ImportError:
    import email.utils as Utils

import pwd

from getmailcore.exceptions import *
from getmailcore.utilities import *
from getmailcore.baseclasses import *

def exit_with(stderr,errmsg):
    stderr.write(errmsg.encode())
    stderr.flush()
    os.fsync(stderr.fileno())
    os._exit(127)

#######################################
class DeliverySkeleton(ConfigurableBase):
    '''Base class for implementing message-delivery classes.

    Sub-classes should provide the following data attributes and methods:

      _confitems - a tuple of dictionaries representing the parameters the class
                   takes.  Each dictionary should contain the following key,
                   value pairs:
                     - name - parameter name
                     - type - a type function to compare the parameter value
                     against (i.e. str, int, bool)
                     - default - optional default value.  If not preseent, the
                     parameter is required.

      __str__(self) - return a simple string representing the class instance.

      showconf(self) - log a message representing the instance and configuration
                       from self._confstring().

      initialize(self) - process instantiation parameters from self.conf.
                         Raise getmailConfigurationError on errors.  Do any
                         other validation necessary, and set self.__initialized
                         when done.

      retriever_info(self, retriever) - extract information from retriever and
                        store it for use in message deliveries.

      _deliver_message(self, msg, delivered_to, received) - accept the message
                        and deliver it, returning a string describing the
                        result.

    See the Maildir class for a good, simple example.
    '''
    def __init__(self, **args):
        ConfigurableBase.__init__(self, **args)
        try:
            self.initialize()
        except KeyError as o:
            raise getmailConfigurationError(
                'missing required configuration parameter %s' % o
            )
        self.received_from = None
        self.received_with = None
        self.received_by = None
        self.retriever = None
        self.log.trace('done\n')

    def retriever_info(self, retriever):
        self.log.trace()
        self.received_from = retriever.received_from
        self.received_with = retriever.received_with
        self.received_by = retriever.received_by
        self.retriever = retriever

    def deliver_message(self, msg, delivered_to=True, received=True):
        self.log.trace()
        msg.received_from = self.received_from
        msg.received_with = self.received_with
        msg.received_by = self.received_by
        return self._deliver_message(msg, delivered_to, received)

    def some_security(self):
        if ((os.geteuid() == 0 or os.getegid() == 0)
                and not self.conf['allow_root_commands']):
            raise getmailConfigurationError(
                'refuse to invoke external commands as root '
                'or GID 0 by default'
            )

#######################################
class Maildir(DeliverySkeleton, ForkingBase):
    '''Maildir destination.

    Parameters:

      path - path to maildir, which will be expanded for leading '~/' or
      '~USER/', as well as environment variables.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfMaildirPath(name='path'),
        ConfString(name='user', required=False, default=None),
        ConfString(name='filemode', required=False, default='0600'),
    )

    def initialize(self):
        self.log.trace()
        self.hostname = localhostname()
        self.dcount = 0
        try:
            self.conf['filemode'] = int(self.conf['filemode'], 8)
        except ValueError as o:
            raise getmailConfigurationError('filemode %s not valid: %s'
                                            % (self.conf['filemode'], o))

    def __str__(self):
        self.log.trace()
        return 'Maildir %s' % self.conf['path']

    def showconf(self):
        self.log.info('Maildir(%s)\n' % self._confstring())

    def __deliver_message_maildir(self, uid, gid, msg, delivered_to, received,
                                  stdout, stderr):
        '''Delivery method run in separate child process.
        '''
        try:
            if os.name == 'posix':
                if uid:
                    change_uidgid(None, uid, gid)
                if os.geteuid() == 0:
                    raise getmailConfigurationError(
                        'refuse to deliver mail as root'
                    )
                if os.getegid() == 0:
                    raise getmailConfigurationError(
                        'refuse to deliver mail as GID 0'
                    )
            f = deliver_maildir(
                self.conf['path'], msg.flatten(delivered_to, received),
                self.hostname, self.dcount, self.conf['filemode']
            )
            stdout.write(f.encode())
            stdout.flush()
            os.fsync(stdout.fileno())
            os._exit(0)
        except Exception as o:
            exit_with(stderr, 'maildir delivery process failed (%s)' % o)

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        uid = None
        gid = None
        user = self.conf['user']
        if os.name == 'posix':
            if user and uid_of_user(user) != os.geteuid():
                # Config specifies delivery as user other than current UID
                uid = uid_of_user(user)
                gid = gid_of_uid(uid)
                if uid == 0:
                    raise getmailConfigurationError(
                        'refuse to deliver mail as root'
                    )
                if gid == 0:
                    raise getmailConfigurationError(
                        'refuse to deliver mail as GID 0'
                    )

        child = self.forkchild(
            lambda o,e: self.__deliver_message_maildir(
                uid, gid, msg, delivered_to, received, o, e)
            )

        self.log.debug('maildir delivery process %d exited %d\n'
                       % (child.childpid, child.exitcode))
        if child.exitcode or child.err:
            raise getmailDeliveryError('maildir delivery %d error (%d, %s)'
                                       % (child.childpid, child.exitcode, child.err))
        self.dcount += 1
        self.log.debug('maildir file %s' % child.out)
        return self

#######################################
class Mboxrd(DeliverySkeleton, ForkingBase):
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
        ConfInstance(name='configparser', required=False),
        ConfMboxPath(name='path'),
        ConfString(name='locktype', required=False, default='lockf'),
        ConfString(name='user', required=False, default=None),
    )

    def initialize(self):
        self.log.trace()
        if self.conf['locktype'] not in ('lockf', 'flock'):
            raise getmailConfigurationError('unknown mbox lock type: %s'
                                            % self.conf['locktype'])

    def __str__(self):
        self.log.trace()
        return 'Mboxrd %s' % self.conf['path']

    def showconf(self):
        self.log.info('Mboxrd(%s)\n' % self._confstring())

    def __deliver_message_mbox(self, uid, gid, msg, delivered_to, received,
                               stdout, stderr):
        '''Delivery method run in separate child process.
        '''
        try:
            if os.name == 'posix':
                if uid:
                    change_uidgid(None, uid, gid)
                if os.geteuid() == 0:
                    raise getmailConfigurationError(
                        'refuse to deliver mail as root'
                    )
                if os.getegid() == 0:
                    raise getmailConfigurationError(
                        'refuse to deliver mail as GID 0'
                    )

            if not os.path.exists(self.conf['path']):
                raise getmailDeliveryError('mboxrd does not exist (%s)'
                                           % self.conf['path'])
            if not os.path.isfile(self.conf['path']):
                raise getmailDeliveryError('not an mboxrd file (%s)'
                                           % self.conf['path'])

            # Open mbox file, refusing to create it if it doesn't exist
            fd = os.open(self.conf['path'], os.O_RDWR)
            status_old = os.fstat(fd)
            f = os.fdopen(fd, 'br+')
            lock_file(f, self.conf['locktype'])
            # Check if it _is_ an mbox file.  mbox files must start with "From "
            # in their first line, or are 0-length files.
            f.seek(0, 0)
            first_line = f.readline()
            if first_line and not first_line.startswith(b'From '):
                # Not an mbox file; abort here
                unlock_file(f, self.conf['locktype'])
                raise getmailDeliveryError('not an mboxrd file (%s)'
                                           % self.conf['path'])
            # Seek to end
            f.seek(0, 2)
            try:
                # Write out message plus blank line with native EOL
                f.write(msg.flatten(delivered_to, received, include_from=True,
                                    mangle_from=True) + os.linesep.encode())
                f.flush()
                os.fsync(fd)
                status_new = os.fstat(fd)
                # Reset atime
                try:
                    os.utime(self.conf['path'], (status_old.st_atime,
                             status_new.st_mtime))
                except OSError as o:
                    # Not root or owner; readers will not be able to reliably
                    # detect new mail.  But you shouldn't be delivering to
                    # other peoples' mboxes unless you're root, anyways.
                    stdout.write(b'failed to update mtime/atime of mbox')
                    stdout.flush()
                    os.fsync(stdout.fileno())

                unlock_file(f, self.conf['locktype'])

            except IOError as o:
                try:
                    if not f.closed:
                        # If the file was opened and we know how long it was,
                        # try to truncate it back to that length
                        # If it's already closed, or the error occurred at
                        # close(), then there's not much we can do.
                        f.truncate(status_old.st_size)
                except KeyboardInterrupt:
                    raise
                except Exception:
                    pass
                raise getmailDeliveryError(
                    'failure writing message to mbox file "%s" (%s)'
                    % (self.conf['path'], o)
                )

            os._exit(0)

        except Exception as o:
            exit_with(stderr, 'mbox delivery process failed (%s)' % o)

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        uid = None
        gid = None
        # Get user & group of mbox file
        st_mbox = os.stat(self.conf['path'])
        user = self.conf['user']
        if os.name == 'posix':
            if user and uid_of_user(user) != os.geteuid():
                # Config specifies delivery as user other than current UID
                uid = uid_of_user(user)
                gid = gid_of_uid(uid)
            if uid == 0:
                raise getmailConfigurationError(
                    'refuse to deliver mail as root'
                )
            if gid == 0:
                raise getmailConfigurationError(
                    'refuse to deliver mail as GID 0'
                )

        child = self.forkchild(
            lambda o,e: self.__deliver_message_mbox(
                uid, gid, msg, delivered_to, received, o, e)
            )

        self.log.debug('mboxrd delivery process %d exited %d\n'
                       % (child.childpid, child.exitcode))
        if child.exitcode or child.err:
            raise getmailDeliveryError('mboxrd delivery %d error (%d, %s)'
                                       % (child.childpid, child.exitcode, child.err))

        if child.out:
            self.log.debug('mbox delivery: %s' % child.out)

        return self


#######################################
class MDA_qmaillocal(DeliverySkeleton, ForkingBase):
    '''qmail-local MDA destination.

    Passes the message to qmail-local for delivery.  qmail-local is invoked as:

      qmail-local -nN user homedir local dash ext domain sender defaultdelivery

    Parameters (all optional):

      qmaillocal - complete path to the qmail-local binary.  Defaults
                to "/var/qmail/bin/qmail-local".

      user - username supplied to qmail-local as the "user" argument.  Defaults
            to the login name of the current effective user ID.  If supplied,
            getmail will also change the effective UID to that of the user
            before running qmail-local.

      group - If supplied, getmail will change the effective GID to that of the
            named group before running qmail-local.

      homedir - complete path to the directory supplied to qmail-local as the
            "homedir" argument. Defaults to the home directory of the current
            effective user ID.

      localdomain - supplied to qmail-local as the "domain" argument.  Defaults
            to localhostname().

      defaultdelivery - supplied to qmail-local as the "defaultdelivery"
            argument.  Defaults to "./Maildir/".

      conf-break - supplied to qmail-local as the "dash" argument and used to
            calculate ext from local.  Defaults to "-".

      localpart_translate - a string representing a Python 2-tuple of strings
            (i.e. "('foo', 'bar')"). If supplied, the retrieved message
            recipient address will have any leading instance of "foo" replaced
            with "bar" before being broken into "local" and "ext" for qmail-
            local (according to the values of "conf-break" and "user").  This
            can be used to add or remove a prefix of the address.

      strip_delivered_to - if set, existing Delivered-To: header fields will be
            removed from the message before processing by qmail-local.  This may
            be necessary to prevent qmail-local falsely detecting a looping
            message if (for instance) the system retrieving messages otherwise
            believes it has the same domain name as the POP server.
            Inappropriate use, however, may cause message loops.

      allow_root_commands (boolean, optional) - if set, external commands are
            allowed when running as root.  The default is not to allow such
            behaviour.

    For example, if getmail is run as user "exampledotorg", which has virtual
    domain "example.org" delegated to it with a virtualdomains entry of
    "example.org:exampledotorg", and messages are retrieved with envelope
    recipients like "trimtext-localpart@example.org", the messages could be
    properly passed to qmail-local with a localpart_translate value of
    "('trimtext-', '')" (and perhaps a defaultdelivery value of
    "./Maildirs/postmaster/" or similar).
    '''

    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfFile(name='qmaillocal', required=False,
                 default='/var/qmail/bin/qmail-local'),
        ConfString(name='user', required=False,
                   default=pwd.getpwuid(os.geteuid()).pw_name),
        ConfString(name='group', required=False, default=None),
        ConfDirectory(name='homedir', required=False,
                      default=pwd.getpwuid(os.geteuid()).pw_dir),
        ConfString(name='localdomain', required=False, default=localhostname()),
        ConfString(name='defaultdelivery', required=False,
                   default='./Maildir/'),
        ConfString(name='conf-break', required=False, default='-'),
        ConfTupleOfStrings(name='localpart_translate', required=False,
                           default="('', '')"),
        ConfBool(name='strip_delivered_to', required=False, default=False),
        ConfBool(name='allow_root_commands', required=False, default=False),
    )

    def initialize(self):
        self.log.trace()

    def __str__(self):
        self.log.trace()
        return 'MDA_qmaillocal %s' % self._confstring()

    def showconf(self):
        self.log.info('MDA_qmaillocal(%s)\n' % self._confstring())

    def _deliver_qmaillocal(self, msg, msginfo, delivered_to, received, stdout,
            stderr):
        try:
            args = (
                self.conf['qmaillocal'], self.conf['qmaillocal'],
                '--', self.conf['user'], self.conf['homedir'],
                msginfo['local'], msginfo['dash'], msginfo['ext'],
                self.conf['localdomain'], msginfo['sender'],
                self.conf['defaultdelivery']
            )
            # Modify message
            if self.conf['strip_delivered_to']:
                msg.remove_header('delivered-to')
                # Also don't insert a Delivered-To: header.
                delivered_to = None

            change_usergroup(self.log, self.conf['user'], self.conf['group'])
            self.some_security()
            self.child_replace_me(msg,
                            delivered_to, received, False,
                            stdout, stderr, args)
        except Exception as o:
            exit_with(stderr,'exec of qmail-local failed (%s)' % o)

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        if msg.recipient == None:
            raise getmailConfigurationError(
                'MDA_qmaillocal destination requires a message source that '
                'preserves the message envelope'
            )
        msginfo = {
            'sender' : msg.sender.strip(),
            'local' : '@'.join(msg.recipient.strip().lower().split('@')[:-1])
        }

        self.log.debug('recipient: extracted local-part "%s"\n'
                       % msginfo['local'])
        xlate_from, xlate_to = self.conf['localpart_translate']
        if xlate_from or xlate_to:
            if msginfo['local'].startswith(xlate_from):
                self.log.debug('recipient: translating "%s" to "%s"\n'
                               % (xlate_from, xlate_to))
                msginfo['local'] = xlate_to + msginfo['local'][len(xlate_from):]
            else:
                self.log.debug('recipient: does not start with xlate_from '
                               '"%s"\n' % xlate_from)
        self.log.debug('recipient: translated local-part "%s"\n'
                       % msginfo['local'])
        if self.conf['conf-break'] in msginfo['local']:
            msginfo['dash'] = self.conf['conf-break']
            msginfo['ext'] = self.conf['conf-break'].join(
                msginfo['local'].split(self.conf['conf-break'])[1:]
            )
        else:
            msginfo['dash'] = ''
            msginfo['ext'] = ''
        self.log.debug('recipient: set dash to "%s", ext to "%s"\n'
                       % (msginfo['dash'], msginfo['ext']))

        child = self.forkchild(
            lambda o,e: self._deliver_qmaillocal(
                msg, msginfo, delivered_to, received, o, e)
            )


        self.log.debug('qmail-local %d exited %d\n' % (child.childpid, child.exitcode))

        if child.exitcode == 111:
            raise getmailDeliveryError('qmail-local %d temporary error (%s)'
                                       % (child.childpid, child.err))
        elif child.exitcode:
            raise getmailDeliveryError('qmail-local %d error (%d, %s)'
                                       % (child.childpid, child.exitcode, child.err))

        if child.out and child.err:
            info = '%s:%s' % (child.out, child.err)
        else:
            info = child.out or child.err

        return 'MDA_qmaillocal (%s)' % info

#######################################
class MDA_external(DeliverySkeleton, ForkingBase):
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
                    %(mailbox) - for IMAP retrievers, the name of the
                        server-side mailbox/folder the message was retrieved
                        from.  Will be empty for POP.

                  Warning: the text of these replacements is taken from the
                  message and is therefore under the control of a potential
                  attacker. DO NOT PASS THESE VALUES TO A SHELL -- they may
                  contain unsafe shell metacharacters or other hostile
                  constructions.

                  example:

                    path = /path/to/mymda
                    arguments = ('--demime', '-f%(sender)', '--', '%(recipient)')

      user (string, optional) - if provided, the external command will be run as
            the specified user.  This requires that the main getmail process
            have permission to change the effective user ID.

      group (string, optional) -  if provided, the external command will be run
            with the specified group ID.  This requires that the main getmail
            process have permission to change the effective group ID.

      allow_root_commands (boolean, optional) - if set, external commands are
            allowed when running as root.  The default is not to allow such
            behaviour.

      ignore_stderr (boolean, optional) - if set, getmail will not consider the
            program writing to stderr to be an error.  The default is False.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfFile(name='path'),
        ConfTupleOfStrings(name='arguments', required=False, default="()"),
        ConfString(name='user', required=False, default=None),
        ConfString(name='group', required=False, default=None),
        ConfBool(name='allow_root_commands', required=False, default=False),
        ConfBool(name='unixfrom', required=False, default=False),
        ConfBool(name='ignore_stderr', required=False, default=False),
    )

    def initialize(self):
        self.log.trace()
        self.conf['command'] = os.path.basename(self.conf['path'])
        if not os.access(self.conf['path'], os.X_OK):
            raise getmailConfigurationError('%s not executable'
                                            % self.conf['path'])
        if type(self.conf['arguments']) != tuple:
            raise getmailConfigurationError(
                'incorrect arguments format; see documentation (%s)'
                % self.conf['arguments']
            )

    def __str__(self):
        self.log.trace()
        return 'MDA_external %s (%s)' % (self.conf['command'],
                                         self._confstring())

    def showconf(self):
        self.log.info('MDA_external(%s)\n' % self._confstring())

    def _deliver_command(self, msg, msginfo, delivered_to, received,
                         stdout, stderr):
        try:
            args = [self.conf['path'], self.conf['path']]
            msginfo['mailbox'] = self.retriever.mailbox_selected or ''
            if sys.version_info.major == 2:
                msginfo['mailbox'] = msginfo['mailbox'].encode('utf-8')
            for arg in self.conf['arguments']:
                arg = expand_user_vars(arg)
                for (key, value) in msginfo.items():
                    arg = arg.replace('%%(%s)' % key, value)
                args.append(arg)

            change_usergroup(self.log, self.conf['user'], self.conf['group'])
            self.some_security()
            self.child_replace_me(msg,
                            delivered_to, received, self.conf['unixfrom'],
                            stdout, stderr, args)
        except Exception as o:
            exit_with(stderr, 'exec of command %s failed (%s)'
                         % (self.conf['command'], o))

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        msginfo = self.get_msginfo(msg)

        child = self.forkchild(
            lambda o,e: self._deliver_command(
                msg, msginfo, delivered_to, received, o, e)
            )

        self.log.debug('command %s %d exited %d\n'
                       % (self.conf['command'], child.childpid, child.exitcode))
        if child.exitcode:
            raise getmailDeliveryError(
                'command %s %d error (%d, %s)'
                % (self.conf['command'], child.childpid, child.exitcode, child.err)
            )
        elif child.err:
            if not self.conf['ignore_stderr']:
                raise getmailDeliveryError(
                    'command %s %d wrote to stderr: %s'
                    % (self.conf['command'], child.childpid, child.err)
                )
            #else:
            # User said to ignore stderr, just log it.
            self.log.info('command %s: %s' % (self, child.err))
        return 'MDA_external command %s (%s)' % (self.conf['command'], child.out)

#######################################
class MultiDestinationBase(DeliverySkeleton):
    '''Base class for destinations which hand messages off to other
    destinations.

    Sub-classes must provide the following attributes and methods:

      conf - standard ConfigurableBase configuration dictionary

      log - getmailcore.logging.Logger() instance

    In addition, sub-classes must populate the following list provided by
    this base class:

      _destinations - a list of all destination objects messages could be
                      handed to by this class.
    '''

    def _get_destination(self, path):
        p = expand_user_vars(path)
        if p.startswith('[') and p.endswith(']'):
            destsectionname = p[1:-1]
            if not destsectionname in self.conf['configparser'].sections():
                raise getmailConfigurationError(
                    'destination specifies section name %s which does not exist'
                    % path
                )
            # Construct destination instance
            self.log.debug('  getting destination for %s\n' % path)
            destination_type = self.conf['configparser'].get(destsectionname,
                                                             'type')
            self.log.debug('    type="%s"\n' % destination_type)
            destination_func = globals().get(destination_type, None)
            if not callable(destination_func):
                raise getmailConfigurationError(
                    'configuration file section %s specifies incorrect '
                    'destination type (%s)'
                    % (destsectionname, destination_type)
                )
            destination_args = {'configparser' : self.conf['configparser']}
            for (name, value) in self.conf['configparser'].items(destsectionname):
                if name in ('type', 'configparser'):
                    continue
                self.log.debug('    parameter %s="%s"\n' % (name, value))
                destination_args[name] = value
            self.log.debug('    instantiating destination %s with args %s\n'
                           % (destination_type, destination_args))
            dest = destination_func(**destination_args)
        elif (p.startswith('/') or p.startswith('.')) and p.endswith('/'):
            dest = Maildir(path=p)
        elif (p.startswith('/') or p.startswith('.')):
            dest = Mboxrd(path=p)
        else:
            raise getmailConfigurationError(
                'specified destination %s not of recognized type' % p
            )
        return dest

    def initialize(self):
        self.log.trace()
        self._destinations = []

    def retriever_info(self, retriever):
        '''Override base class to pass this to the encapsulated destinations.
        '''
        self.log.trace()
        DeliverySkeleton.retriever_info(self, retriever)
        # Pass down to all destinations
        for destination in self._destinations:
            destination.retriever_info(retriever)

#######################################
class MultiDestination(MultiDestinationBase):
    '''Send messages to one or more other destination objects unconditionally.

    Parameters:

      destinations - a tuple of strings, each specifying a destination that
                messages should be delivered to.  These strings will be expanded
                for leading "~/" or "~user/" and environment variables,
                then interpreted as maildir/mbox/other-destination-section.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfTupleOfStrings(name='destinations'),
    )

    def initialize(self):
        self.log.trace()
        MultiDestinationBase.initialize(self)
        dests = [expand_user_vars(item) for item in self.conf['destinations']]
        for item in dests:
            try:
                dest = self._get_destination(item)
            except getmailConfigurationError as o:
                raise getmailConfigurationError('%s destination error %s'
                                                % (item, o))
            self._destinations.append(dest)
        if not self._destinations:
            raise getmailConfigurationError('no destinations specified')

    def _confstring(self):
        '''Override the base class implementation.
        '''
        self.log.trace()
        confstring = ''
        for dest in self._destinations:
            if confstring:
                confstring += ', '
            confstring += '%s' % dest
        return confstring

    def __str__(self):
        self.log.trace()
        return 'MultiDestination (%s)' % self._confstring()

    def showconf(self):
        self.log.info('MultiDestination(%s)\n' % self._confstring())

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        for dest in self._destinations:
            dest.deliver_message(msg, delivered_to, received)
        return self

#######################################
class MultiSorterBase(MultiDestinationBase):
    '''Base class for multiple destinations with address matching.
    '''

    def initialize(self):
        self.log.trace()
        MultiDestinationBase.initialize(self)
        self.default = self._get_destination(self.conf['default'])
        self._destinations.append(self.default)
        self.targets = []
        try:
            _locals = self.conf['locals']
            # Special case for convenience if user supplied one base 2-tuple
            if (len(_locals) == 2 and type(_locals[0]) == str
                    and type(_locals[1]) == str):
                _locals = (_locals, )
            for item in _locals:
                if not (type(item) == tuple and len(item) == 2
                        and type(item[0]) == str and type(item[1]) == str):
                    raise getmailConfigurationError(
                        'invalid syntax for locals; see documentation'
                    )
            for (pattern, path) in _locals:
                try:
                    dest = self._get_destination(path)
                except getmailConfigurationError as o:
                    raise getmailConfigurationError(
                        'pattern %s destination error %s' % (pattern, o)
                    )
                self.targets.append((re.compile(pattern, re.IGNORECASE), dest))
                self._destinations.append(dest)
        except re.error as o:
            raise getmailConfigurationError('invalid regular expression %s' % o)

    def _confstring(self):
        '''
        Override the base class implementation; locals isn't readable that way.
        '''
        self.log.trace()
        confstring = 'default=%s' % self.default
        for (pattern, destination) in self.targets:
            confstring += ', %s->%s' % (pattern.pattern, destination)
        return confstring

#######################################
class MultiSorter(MultiSorterBase):
    '''Multiple destination with envelope recipient address matching.

    Parameters:

      default - the default destination.  Messages not matching any
                "local" patterns (see below) will be delivered here.

      locals - an optional tuple of items, each being a 2-tuple of quoted
            strings. Each quoted string pair is a regular expression and a
            maildir/mbox/other destination. In the general case, an email
            address is a valid regular expression. Each pair is on a separate
            line; the second and subsequent lines need to have leading
            whitespace to be considered a continuation of the "locals"
            configuration.  If the recipient address matches a given pattern, it
            will be delivered to the corresponding destination.  A destination
            is assumed to be a maildir if it starts with a dot or slash and ends
            with a slash. A destination is assumed to be an mboxrd file if it
            starts with a dot or a slash and does not end with a slash.  A
            destination may also be specified by section name, i.e.
            "[othersectionname]". Multiple patterns may match a given recipient
            address; the message will be delivered to /all/ destinations with
            matching patterns.  Patterns are matched case-insensitively.

            example:

             default = /home/kellyw/Mail/postmaster/
             locals = (
               ("jason@example.org", "/home/jasonk/Maildir/"),
               ("sales@example.org", "/home/karlyk/Mail/sales"),
               ("abuse@(example.org|example.net)", "/home/kellyw/Mail/abuse/"),
               ("^(jeff|jefferey)(\.s(mith)?)?@.*$", "[jeff-mail-delivery]"),
               ("^.*@(mail.)?rapinder.example.org$", "/home/rapinder/Maildir/")
               )

               In it's simplest form, locals is merely a list of pairs of email
               addresses and corresponding maildir/mbox paths.  Don't worry
               about the details of regular expressions if you aren't familiar
               with them.
    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfString(name='default'),
        ConfTupleOfTupleOfStrings(name='locals', required=False, default="()"),
    )

    def __str__(self):
        self.log.trace()
        return 'MultiSorter (%s)' % self._confstring()

    def showconf(self):
        self.log.info('MultiSorter(%s)\n' % self._confstring())

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        matched = []
        if msg.recipient == None and self.targets:
            raise getmailConfigurationError(
                'MultiSorter recipient matching requires a retriever (message '
                'source) that preserves the message envelope'
            )
        for (pattern, dest) in self.targets:
            self.log.debug('checking recipient %s against pattern %s\n'
                           % (msg.recipient, pattern.pattern))
            if pattern.search(msg.recipient):
                self.log.debug('recipient %s matched target %s\n'
                               % (msg.recipient, dest))
                dest.deliver_message(msg, delivered_to, received)
                matched.append(str(dest))
        if not matched:
            if self.targets:
                self.log.debug('recipient %s not matched; using default %s\n'
                               % (msg.recipient, self.default))
            else:
                self.log.debug('using default %s\n' % self.default)
            return 'MultiSorter (default %s)' % self.default.deliver_message(
                msg, delivered_to, received
            )
        return 'MultiSorter (%s)' % matched

#######################################
class MultiGuesser(MultiSorterBase):
    '''Multiple destination with header field address matching.

    Parameters:

      default - see MultiSorter for definition.

      locals - see MultiSorter for definition.

    '''
    _confitems = (
        ConfInstance(name='configparser', required=False),
        ConfString(name='default'),
        ConfTupleOfTupleOfStrings(name='locals', required=False, default="()"),
    )

    def __str__(self):
        self.log.trace()
        return 'MultiGuesser (%s)' % self._confstring()

    def showconf(self):
        self.log.info('MultiGuesser(%s)\n' % self._confstring())

    def _deliver_message(self, msg, delivered_to, received):
        self.log.trace()
        matched = []
        header_addrs = []
        fieldnames = (
            ('delivered-to', ),
            ('envelope-to', ),
            ('x-envelope-to', ),
            ('apparently-to', ),
            ('resent-to', 'resent-cc', 'resent-bcc'),
            ('to', 'cc', 'bcc'),
        )
        for fields in fieldnames:
            for field in fields:
                self.log.debug(
                    'looking for addresses in %s header fields\n' % field
                )
                header_addrs.extend(
                    [addr for (name, addr) in Utils.getaddresses(
                        msg.get_all(field, [])
                     ) if addr]
                )
            if header_addrs:
                # Got some addresses, quit here
                self.log.debug('found total of %d addresses (%s)\n'
                               % (len(header_addrs), header_addrs))
                break
            else:
                self.log.debug('no addresses found, continuing\n')

        for (pattern, dest) in self.targets:
            for addr in header_addrs:
                self.log.debug('checking address %s against pattern %s\n'
                               % (addr, pattern.pattern))
                if pattern.search(addr):
                    self.log.debug('address %s matched target %s\n'
                                   % (addr, dest))
                    dest.deliver_message(msg, delivered_to, received)
                    matched.append(str(dest))
                    # Only deliver once to each destination; this one matched,
                    # so we don't need to check any remaining addresses against
                    # this pattern
                    break
        if not matched:
            if self.targets:
                self.log.debug('no addresses matched; using default %s\n'
                               % self.default)
            else:
                self.log.debug('using default %s\n' % self.default)
            return 'MultiGuesser (default %s)' % self.default.deliver_message(
                msg, delivered_to, received
            )
        return 'MultiGuesser (%s)' % matched
