#!/usr/bin/env python
'''Classes implementing message filters.

Currently implemented:

'''

import os
import signal
import email

from exceptions import *
from utilities import is_maildir, deliver_maildir, mbox_from_escape, mbox_timestamp, lock_file, unlock_file
from logging import logger

#######################################
class FilterSkeleton(object):
    '''Base class for implementing message-filtering classes.

    Sub-classes should provide the following data attributes and methods:

      conf - a dictionary containing all configuration data for the instance.

      __str__(self) - return a simple string representing the class instance.

      _process_args(self, **args) - process instantiation parameters **args and
                                    store in self.conf.  Don't worry about missing
                                    required values; KeyError will be converted
                                    into getmailConfigurationError by the base class'
                                    __init__().  Do any other validation necessary,
                                    raising getmailConfigurationError on error.

      showconf(self) - log a message representing the instance and configuration
                       from self._confstring().

      _filter_message(self, msg) - accept the message and deliver it, returning
                                   a tuple (exitcode, newmsg, err).
                                   exitcode should be 0 for success, 99 or 100
                                   for success but drop the message, anything
                                   else for error.
                                   err should be an empty string on success,
                                   or an error message otherwise.
                                   newmsg is an email.Message() object representing
                                   the message in filtered form, or None on
                                   error or when dropping the message.

    See the Filter_external class for a good (though not simple) example.
    '''
    def __init__(self, **args):
        self.log = logger()
        self.log.trace()
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
        try:
            self._process_args(**args)
        except KeyError, o:
            raise getmailConfigurationError('missing argument %s' % o)
        self.log.trace('done\n')

    def _confstring(self):
        self.log.trace()
        confstring = ''
        names = self.conf.keys()
        names.sort()
        for name in names:
            if confstring:  confstring += ', '
            confstring += '%s="%s"' % (name, self.conf[name])
        return confstring

    def filter_message(self, msg):
        self.log.trace()
        exitcode, newmsg, err = self._filter_message(msg)
        if exitcode in (99, 100):
            # Drop message
            self.log.info('filter %s returned %d; dropping message\n' % (self, exitcode))
            return None
        elif exitcode or err:
            raise getmailOperationError('filter %s returned %d (%s)\n' % (self, exitcode, err))

        # Copy envelope info from original message
        if hasattr(msg, 'sender'):
            newmsg.sender = msg.sender
        if hasattr(msg, 'recipient'):
            newmsg.recipient = msg.recipient

        return newmsg

#######################################
class Filter_external(FilterSkeleton):
    '''Arbitrary external filter destination.

    Parameters:

      path - path to the external filter binary.

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

                    path = /path/to/myfilter
                    arguments = ('--demime', '-f%(sender)', '--', '%(recipient)')
    '''
    _confitems = (
        {'name' : 'path', 'type' : str},
        {'name' : 'unixfrom', 'type' : bool, 'default' : False},
        {'name' : 'arguments', 'type' : tuple, 'default' : '()'},
    )

    def _process_args(self, **args):
        self.log.trace()
        try:
            self.conf = {
                'path' : os.path.expanduser(args['path']),
                'command' : os.path.basename(args['path']),
                'arguments' : eval(args.get('arguments', '()')),
                'unixfrom' : bool(args.get('unixfrom', False)),
            }
        except SyntaxError, o:
            raise getmailConfigurationError('invalid syntax for arguments ; see documentation (%s)' % o)
        if not os.path.isfile(self.conf['path']):
            raise getmailConfigurationError('no such command %s' % self.conf['path'])
        if not os.access(self.conf['path'], os.X_OK):
            raise getmailConfigurationError('%s not executable' % self.conf['path'])
        if type(self.conf['arguments']) != tuple:
            raise getmailConfigurationError('incorrect arguments format; see documentation (%s)' % self.conf['arguments'])

    def __str__(self):
        self.log.trace()
        return 'Filter_external %s' % str(self.conf)


    def showconf(self):
        self.log.info('Filter_external(%s)\n' % self._confstring())

    def _filter_command(self, msg, msginfo, stdout, stderr):
        args = [self.conf['path'], self.conf['path']]
        for arg in self.conf['arguments']:
            for (key, value) in msginfo.items():
                arg = arg.replace('%%(%s)' % key, value)
            args.append(arg)
        self.log.debug('about to execl() with args %s\n' % str(args))
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
            raise getmailOperationError('exec of filter %s failed (%s)' % (self.conf['command'], o))

    def _filter_message(self, msg):
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
            self._filter_command(msg, msginfo, stdout, stderr)
        self.log.debug('spawned child %d\n' % childpid)

        # Parent
        try:
            pid, r = os.waitpid(childpid, 0)
        except OSError, o:
            raise getmailOperationError('failed waiting for command %s %d (%s)' % (self.conf['command'], childpid, o))

        signal.signal(signal.SIGCHLD, orighandler)
        stdout.seek(0)
        stderr.seek(0)
        err = stderr.read().strip()

        if os.WIFSTOPPED(r):
            raise getmailOperationError('command %s %d stopped by signal %d' % (self.conf['command'], pid, os.WSTOPSIG(r)))
        if os.WIFSIGNALED(r):
            raise getmailOperationError('command %s %d killed by signal %d' % (self.conf['command'], pid, os.WTERMSIG(r)))
        if not os.WIFEXITED(r):
            raise getmailOperationError('command %s %d failed to exit' % (self.conf['command'], pid))
        exitcode = os.WEXITSTATUS(r)

        self.log.debug('command %s %d exited %d\n' % (self.conf['command'], pid, exitcode))

        newmsg = email.message_from_file(stdout, strict=False)

        return exitcode, newmsg, err
