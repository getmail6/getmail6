# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

'''Logging support for getmail.

The new standard Python libary module logging didn't cut it for me; it doesn't
seem capable of handling some very simple requirements like logging messages of
a certain level to one fd, and other messages of higher levels to a different fd
(i.e. info to stdout, warnings to stderr).
'''

__all__ = [
    'Logger',
]

import sys
import os.path
import traceback

from getmailcore.constants import *

#######################################
class _Logger(object):
    '''Class for logging.  Do not instantiate directly; use Logger() instead,
    to keep this a singleton.
    '''
    def __init__(self):
        '''Create a logger.'''
        self.handlers = []
        self.newline = False

    def __call__(self):
        return self

    def addhandler(self, stream, minlevel, maxlevel=CRITICAL):
        '''Add a handler for logged messages.

        Logged messages of at least level <minlevel> (and at most level
        <maxlevel>, default CRITICAL) will be output to <stream>.

        If no handlers are specified, messages of all levels will be output to
        stdout.
        '''
        self.handlers.append({'minlevel' : minlevel, 'stream' : stream,
                              'newline' : True, 'maxlevel' : maxlevel})

    def clearhandlers(self):
        '''Clear the list of handlers.

        There should be a way to remove only one handler from a list.  But that
        would require an easy way for the caller to distinguish between them.
        '''
        self.handlers = []

    def log(self, msglevel, msgtxt):
        '''Log a message of level <msglevel> containing text <msgtxt>.'''
        if sys.version_info.major > 2 and isinstance(msgtxt,bytes):
            msgtxt = msgtxt.decode()
        for handler in self.handlers:
            if msglevel < handler['minlevel'] or msglevel > handler['maxlevel']:
                continue
            if not handler['newline'] and msglevel == DEBUG:
                handler['stream'].write('\n')
            handler['stream'].write(msgtxt)
            handler['stream'].flush()
            if msgtxt.endswith('\n'):
                handler['newline'] = True
            else:
                handler['newline'] = False
        if not self.handlers:
            if not self.newline and msglevel == DEBUG:
                sys.stdout.write('\n')
            sys.stdout.write(msgtxt)
            sys.stdout.flush()
            if msgtxt.endswith('\n'):
                self.newline = True
            else:
                self.newline = False

    def trace(self, msg='trace\n'):
        '''Log a message with level TRACE.

        The message will be prefixed with filename, line number, and function
        name of the calling code.
        '''
        trace = traceback.extract_stack()[-2]
        msg = '%s [%s:%i] %s' % (trace[FUNCNAME] + '()',
            os.path.basename(trace[FILENAME]),
            trace[LINENO],
            msg
        )
        self.log(TRACE, msg)

    def debug(self, msg):
        '''Log a message with level DEBUG.'''
        self.log(DEBUG, msg)

    def moreinfo(self, msg):
        '''Log a message with level MOREINFO.'''
        self.log(MOREINFO, msg)

    def info(self, msg):
        '''Log a message with level INFO.'''
        self.log(INFO, msg)

    def warning(self, msg):
        '''Log a message with level WARNING.'''
        self.log(WARNING, msg)

    def error(self, msg):
        '''Log a message with level ERROR.'''
        self.log(ERROR, msg)

    def critical(self, msg):
        '''Log a message with level CRITICAL.'''
        self.log(CRITICAL, msg)

    # aliases
    warn = warning

Logger = _Logger()

