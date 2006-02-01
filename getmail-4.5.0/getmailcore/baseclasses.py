#!/usr/bin/env python2.3
'''Base classes used elsewhere in the package.

'''

__all__ = [
    'ConfigurableBase',
    'ForkingBase',
]

import os
import time
import signal
import sets

from getmailcore.exceptions import *
from getmailcore.logging import logger
from getmailcore.utilities import eval_bool

#
# Base classes
#

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
        self.log = logger()
        self.log.trace()
        self.conf = {}
        for (name, value) in args.items():
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
            self.log.trace('checking %s\n' % item)
            name = item['name']
            dtype = item['type']
            if not name in self.conf:
                # Not provided
                if 'default' in item:
                    self.conf[name] = item['default']
                else:
                    raise getmailConfigurationError('missing required'
                        ' configuration parameter %s' % name)
            elif type(self.conf[name]) is not dtype:
                # Value supplied, but not of expected type.  Try to convert.
                try:
                    val = self.conf[name]
                    if name.lower() == 'password':
                        self.log.debug('converting password to type %s\n'
                            % dtype)
                    else:
                        self.log.debug('converting %s (%s) to type %s\n'
                            % (name, val, dtype))
                    if dtype == bool:
                        self.conf[name] = eval_bool(val)
                    else:
                        self.conf[name] = dtype(eval(val))
                except (ValueError, SyntaxError, TypeError), o:
                    raise getmailConfigurationError('configuration value'
                        ' %s (%s) not of required type %s (%s)'
                        % (name, val, dtype, o))
        unknown_params = sets.ImmutableSet(self.conf.keys()).difference(
            sets.ImmutableSet([item['name'] for item in self._confitems]))
        for param in unknown_params:
            self.log.warning('Warning: ignoring unknown parameter "%s" '
                '(value: %s)\n' % (param, self.conf[param]))
        self.__confchecked = True
        self.log.trace('done\n')

    def _confstring(self):
        self.log.trace()
        confstring = ''
        names = self.conf.keys()
        names.sort()
        for name in names:
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

        log - an object of type getmailcore.logger()

    '''
    def _child_handler(self, sig, stackframe):
        self.log.trace('handler called for signal %s' % sig)
        try:
            pid, r = os.wait()
        except OSError, o:
            # No children on SIGCHLD.  Can't happen?
            self.log.warning('handler called, but no children (%s)' % o)
            return
        signal.signal(signal.SIGCHLD, self.__orig_handler)
        self.__child_pid = pid
        self.__child_status = r
        self.log.trace('handler reaped child %s with status %s' % (pid, r))
        self.__child_exited = True

    def _prepare_child(self):
        self.log.trace('')
        self.__child_exited = False
        self.__child_pid = None
        self.__child_status = None
        self.__orig_handler = signal.signal(signal.SIGCHLD, self._child_handler)

    def _wait_for_child(self, childpid):
        while not self.__child_exited:
            # Could implement a maximum wait time here
            self.log.trace('waiting for child %d' % childpid)
            time.sleep(1.0)
            #raise getmailDeliveryError('failed waiting for commands %s %d (%s)'
            #   % (self.conf['command'], childpid, o))
        if self.__child_pid != childpid:
            #self.log.error('got child pid %d, not %d' % (pid, childpid))
            raise getmailOperationError('got child pid %d, not %d'
                % (self.__child_pid, childpid))

        if os.WIFSTOPPED(self.__child_status):
            raise getmailOperationError('child pid %d stopped by signal %d'
                % (self.__child_pid, os.WSTOPSIG(self.__child_status)))
        if os.WIFSIGNALED(self.__child_status):
            raise getmailOperationError('child pid %d killed by signal %d'
                % (self.__child_pid, os.WTERMSIG(self.__child_status)))
        if not os.WIFEXITED(self.__child_status):
            raise getmailOperationError('child pid %d failed to exit'
                % self.__child_pid)
        exitcode = os.WEXITSTATUS(self.__child_status)

        return exitcode
