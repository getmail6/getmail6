# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

'''Base classes used elsewhere in the package.

'''

__all__ = [
    'run_command',
    'ConfigurableBase',
    'ForkingBase',
    'ConfInstance',
    'ConfString',
    'ConfBool',
    'ConfInt',
    'ConfTupleOfStrings',
    'ConfTupleOfUnicode',
    'ConfTupleOfTupleOfStrings',
    'ConfPassword',
    'ConfDirectory',
    'ConfFile',
    'ConfMaildirPath',
    'ConfMboxPath',
]

import sys
import os
import time
import signal
import types
import codecs
from collections import namedtuple
import tempfile
import errno
from threading import Condition

from argparse import Namespace
import subprocess

from getmailcore.exceptions import *
import getmailcore.logging
from getmailcore.utilities import *

if sys.version_info.major > 2:
    TemporaryFile23 = lambda: tempfile.TemporaryFile('bw+')
else:
    TemporaryFile23 = lambda: tempfile.TemporaryFile('w+')

#######################################
def run_command(command, args):
    # Simple subprocess wrapper for running a command and fetching its exit 
    # status and output/stderr.
    if args is None:
        args = []
    if type(args) == tuple:
        args = list(args)

    # Programmer sanity checks
    assert type(command) in (bytes, unicode), (
        'command is %s (%s)' % (command, type(command))
    )
    assert type(args) == list, (
        'args is %s (%s)' % (args, type(args))
    )
    for arg in args:
        assert type(arg) in (bytes, unicode), 'arg is %s (%s)' % (arg, type(arg))

    stdout = tempfile.TemporaryFile()
    stderr = tempfile.TemporaryFile()

    cmd = [command] + args

    try:
        p = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
    except OSError as o:
        if o.errno == errno.ENOENT:
            # no such file, command not found
            raise getmailConfigurationError('Program "%s" not found' % command)
        #else:
        raise

    rc = p.wait()
    stdout.seek(0)
    stderr.seek(0)
    if sys.version_info.major == 2:
        return (rc, stdout.read().strip(), stderr.read().strip())
    else:
        return (rc, stdout.read().decode().strip(), stderr.read().decode().strip())

#
# Base classes
#


class ConfItem:
    securevalue = False
    def __init__(self, name, dtype, default=None, required=True):
        self.log = getmailcore.logging.Logger()
        self.name = name
        self.dtype = dtype
        self.default = default
        self.required = required

    def validate(self, configuration, val=None):
        if val is None:
            # If not passed in by subclass
            val = configuration.get(self.name, None)
        if val is None:
            # Not provided.
            if self.required:
                raise getmailConfigurationError(
                    '%s: missing required configuration parameter' % self.name
                )
            # Use default.
            return self.default
        if not isinstance(val,self.dtype) and val != self.default:
            # Got value, but not of expected type.  Try to convert.
            if self.securevalue:
                self.log.debug('converting %s to type %s\n'
                               % (self.name, self.dtype))
            else:
                self.log.debug('converting %s (%s) to type %s\n'
                               % (self.name, val, self.dtype))

            try:
                if self.dtype == bool:
                    val = eval_bool(val)
                else:
                    val = self.dtype(eval(val))
            except (ValueError, SyntaxError, TypeError) as o:
                raise getmailConfigurationError(
                    '%s: configuration value (%s) not of required type %s (%s)'
                    % (self.name, val, self.dtype, o)
                )
        return val

class ConfInstance(ConfItem):
    def __init__(self, name, default=None, required=True):
        ConfItem.__init__(self, name, object, default=default,
                          required=required)

class ConfString(ConfItem):
    def __init__(self, name, default=None, required=True):
        ConfItem.__init__(self, name, str, default=default, required=required)

class ConfBool(ConfItem):
    def __init__(self, name, default=None, required=True):
        ConfItem.__init__(self, name, bool, default=default, required=required)

class ConfInt(ConfItem):
    def __init__(self, name, default=None, required=True):
        ConfItem.__init__(self, name, int, default=default, required=required)

class ConfTupleOfStrings(ConfString):
    def __init__(self, name, default=None, required=True):
        ConfString.__init__(self, name, default=default, required=required)

    def validate(self, configuration):
        val = ConfItem.validate(self, configuration)
        try:
            if not val:
                val = '()'
            tup = eval(val)
            if type(tup) != tuple:
                raise ValueError('not a tuple')
            val = tup
        except (ValueError, SyntaxError) as o:
            raise getmailConfigurationError(
                '%s: incorrect format (%s)' % (self.name, o)
            )
        result = [str(item) for item in val]
        return tuple(result)

class ConfTupleOfUnicode(ConfString):
    def __init__(self, name, default=None, required=True, allow_specials=()):
        ConfString.__init__(self, name, default=default, required=required)
        self.specials = allow_specials

    def validate(self, configuration):
        _locals = dict([(v, v) for v in self.specials])
        val = ConfItem.validate(self, configuration)
        try:
            if not val:
                val = '()'
            tup = eval(val, {}, _locals)
            if tup in self.specials:
                val = [tup]
            else:
                if type(tup) != tuple:
                    raise ValueError('not a tuple')
                vals = []
                for item in tup:
                    try:
                        item = item.encode()
                        vals.append(codecs.decode(item,'ascii'))
                    except:
                        try:
                            vals.append(codecs.decode(item,'utf-8'))
                        except UnicodeError as o:
                            raise ValueError('not ascii or utf-8: %s' % item)
                val = vals
        except (ValueError, SyntaxError) as o:
            raise getmailConfigurationError(
                '%s: incorrect format (%s)' % (self.name, o)
            )
        return tuple(val)

class ConfTupleOfTupleOfStrings(ConfString):
    def __init__(self, name, default=None, required=True):
        ConfString.__init__(self, name, default=default, required=required)

    def validate(self, configuration):
        val = ConfItem.validate(self, configuration)
        try:
            if not val:
                val = '()'
            tup = eval(val)
            if type(tup) != tuple:
                raise ValueError('not a tuple')
            val = tup
        except (ValueError, SyntaxError) as o:
            raise getmailConfigurationError(
                '%s: incorrect format (%s)' % (self.name, o)
            )
        for tup in val:
            if type(tup) != tuple:
                raise ValueError('contained value "%s" not a tuple' % tup)
            if len(tup) != 2:
                raise ValueError('contained value "%s" not length 2' % tup)
            for part in tup:
                if type(part) != str:
                    raise ValueError('contained value "%s" has non-string part '
                                     '"%s"' % (tup, part))

        return val

class ConfPassword(ConfString):
    securevalue = True

class ConfDirectory(ConfString):
    def __init__(self, name, default=None, required=True):
        ConfString.__init__(self, name, default=default, required=required)

    def validate(self, configuration):
        val = ConfString.validate(self, configuration)
        if val is None:
            return None
        val = expand_user_vars(val)
        if not os.path.isdir(val):
            raise getmailConfigurationError(
                '%s: specified directory "%s" does not exist' % (self.name, val)
            )
        return val

class ConfFile(ConfString):
    def __init__(self, name, default=None, required=True):
        ConfString.__init__(self, name, default=default, required=required)

    def validate(self, configuration):
        val = ConfString.validate(self, configuration)
        if val is None:
            return None
        val = expand_user_vars(val)
        if not os.path.isfile(val):
            raise getmailConfigurationError(
                '%s: specified file "%s" does not exist' % (self.name, val)
            )
        return val

class ConfMaildirPath(ConfDirectory):
    def validate(self, configuration):
        val = ConfDirectory.validate(self, configuration)
        if val is None:
            return None
        if not val.endswith('/'):
            raise getmailConfigurationError(
                '%s: maildir must end with "/"' % self.name
            )
        for subdir in ('cur', 'new', 'tmp'):
            subdirpath = os.path.join(val, subdir)
            if not os.path.isdir(subdirpath):
                raise getmailConfigurationError(
                    '%s: maildir subdirectory "%s" does not exist'
                    % (self.name, subdirpath)
                )
        return val

class ConfMboxPath(ConfString):
    def __init__(self, name, default=None, required=True):
        ConfString.__init__(self, name, default=default, required=required)

    def validate(self, configuration):
        val = ConfString.validate(self, configuration)
        if val is None:
            return None
        val = expand_user_vars(val)
        if not os.path.isfile(val):
            raise getmailConfigurationError(
                '%s: specified mbox file "%s" does not exist' % (self.name, val)
            )
        fd = os.open(val, os.O_RDWR)
        status_old = os.fstat(fd)
        f = os.fdopen(fd, 'r+')
        # Check if it _is_ an mbox file.  mbox files must start with "From "
        # in their first line, or are 0-length files.
        f.seek(0, 0)
        first_line = f.readline()
        if first_line and first_line[:5] != 'From ':
            # Not an mbox file; abort here
            raise getmailConfigurationError('%s: not an mboxrd file' % val)
        # Reset atime and mtime
        try:
            os.utime(val, (status_old.st_atime, status_old.st_mtime))
        except OSError as o:
            # Not root or owner; readers will not be able to reliably
            # detect new mail.  But you shouldn't be delivering to
            # other peoples' mboxes unless you're root, anyways.
            pass

        return val


#######################################
class ConfigurableBase(object):
    '''Base class for user-configurable classes.

    Sub-classes must provide the following data attributes and methods:

      _confitems - a tuple of dictionaries representing the parameters the class
                   takes.  Each dictionary should contain the following key,
                   value pairs:
                     - name - parameter name
                     - type - a type function to compare the parameter value
                       against (i.e. str, int, bool)
                     - default - optional default value.  If not preseent, the
                       parameter is required.
    '''

    def __init__(self, **args):
        self.log = getmailcore.logging.Logger()
        self.log.trace()
        self.conf = {}
        allowed_params = set([item.name for item in self._confitems])
        for (name, value) in args.items():
            if not name in allowed_params:
                self.log.warning('Warning: ignoring unknown parameter "%s" '
                                 '(value: %s)\n' % (name, value))
                continue
            if name.lower() == 'password':
                self.log.trace('setting %s to * (%s)\n' % (name, type(value)))
            else:
                self.log.trace('setting %s to "%s" (%s)\n'
                               % (name, value, type(value)))
            self.conf[name] = value
        self.__confchecked = False
        self.checkconf()

    def checkconf(self):
        self.log.trace()
        if self.__confchecked:
            return
        for item in self._confitems:
            # New class-based configuration item
            self.log.trace('checking %s\n' % item.name)
            self.conf[item.name] = item.validate(self.conf)
        unknown_params = frozenset(self.conf.keys()).difference(
            frozenset([item.name for item in self._confitems])
        )
        for param in sorted(list(unknown_params), key=str.lower):
            self.log.warning('Warning: ignoring unknown parameter "%s" '
                             '(value: %s)\n' % (param, self.conf[param]))
        self.__confchecked = True
        self.log.trace('done\n')

    def _confstring(self):
        self.log.trace()
        confstring = ''
        for name in list(sorted(self.conf.keys())):
            if name.lower() == 'configparser':
                continue
            if confstring:
                confstring += ', '
            if name.lower() == 'password':
                confstring += '%s="*"' % name
            else:
                confstring += '%s="%s"' % (name, self.conf[name])
        return confstring

#######################################

class ForkingBase(object):
    '''Base class for classes which fork children and wait for them to exit.

    Sub-classes must provide the following data attributes and methods:

        log - an object of type getmailcore.logging.Logger()

    '''
    def _child_handler(self, sig, stackframe):
        self.log.trace('handler called for signal %s' % sig)
        try:
            pid, r = os.wait()
        except OSError as o:
            # No children on SIGCHLD.  Can't happen?
            self.log.warning('handler called, but no children (%s)' % o)
            return
        signal.signal(signal.SIGCHLD, self.__orig_handler)
        self.__child_pid = pid
        self.__child_status = r
        self.log.trace('handler reaped child %s with status %s' % (pid, r))
        self.__child_exited.acquire()
        self.__child_exited.notify_all()
        self.__child_exited.release()

    def _prepare_child(self):
        self.log.trace('')
        self.__child_exited = Condition()
        self.__child_pid = None
        self.__child_status = None
        self.__orig_handler = signal.signal(signal.SIGCHLD, self._child_handler)

    def _wait_for_child(self, childpid):
        self.__child_exited.acquire()
        while not self.__child_exited.wait(1):
            # Could implement a maximum wait time here
            self.log.trace('waiting for child %d' % childpid)
            #raise getmailDeliveryError('failed waiting for commands %s %d (%s)'
            #                           % (self.conf['command'], childpid, o))
        self.__child_exited.release()
        if self.__child_pid != childpid:
            #self.log.error('got child pid %d, not %d' % (pid, childpid))
            raise getmailOperationError(
                'got child pid %d, not %d'
                % (self.__child_pid, childpid)
            )
        if os.WIFSTOPPED(self.__child_status):
            raise getmailOperationError(
                'child pid %d stopped by signal %d'
                % (self.__child_pid, os.WSTOPSIG(self.__child_status))
            )
        if os.WIFSIGNALED(self.__child_status):
            raise getmailOperationError(
                'child pid %d killed by signal %d'
                % (self.__child_pid, os.WTERMSIG(self.__child_status))
            )
        if not os.WIFEXITED(self.__child_status):
            raise getmailOperationError('child pid %d failed to exit'
                                        % self.__child_pid)
        exitcode = os.WEXITSTATUS(self.__child_status)
        return exitcode

    def _pipemail(self, msg, delivered_to, received, unixfrom, stdout, stderr):
        # Write out message
        msgfile = TemporaryFile23()
        msgfile.write(msg.flatten(delivered_to, received, include_from=unixfrom))
        msgfile.flush()
        os.fsync(msgfile.fileno())
        # Rewind
        msgfile.seek(0)
        # Set stdin to read from this file
        os.dup2(msgfile.fileno(), 0)
        # Set stdout and stderr to write to files
        os.dup2(stdout.fileno(), 1)
        os.dup2(stderr.fileno(), 2)

    def child_replace_me(self, msg, delivered_to, received, unixfrom,
                         stdout, stderr, args, nolog=False):
        self._pipemail(msg, delivered_to, received, unixfrom, stdout, stderr)
        nolog or self.log.debug('about to execl() with args %s\n' % str(args))
        os.execl(*args)

    def forkchild(self, childfun, with_out=True):
        self._prepare_child()
        child = Namespace()
        child.stdout = TemporaryFile23()
        child.stderr = TemporaryFile23()
        child.childpid = os.fork()
        if child.childpid == 0:
            childfun(child.stdout, child.stderr)
        else:
            self.log.debug('spawned child %d\n' % child.childpid)
            child.exitcode = self._wait_for_child(child.childpid)
            child.stderr.seek(0)
            child.err = child.stderr.read().strip().decode()
            child.stdout.seek(0)
            if with_out:
                child.out = child.stdout.read().strip()
            return child

    def get_msginfo(self, msg):
        msginfo = {}
        msginfo['sender'] = msg.sender.strip()
        if msg.recipient != None:
            rcpnt = msg.recipient.strip()
            msginfo['recipient'] = rcpnt
            msginfo['domain'] = rcpnt.lower().split('@')[-1]
            msginfo['local'] = '@'.join(rcpnt.split('@')[:-1])
        self.log.debug('msginfo "%s"\n' % msginfo)
        return msginfo

