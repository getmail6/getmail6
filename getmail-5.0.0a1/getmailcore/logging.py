"""Logging support for getmail.

The new standard Python libary module logging didn't cut it for me; it doesn't
seem capable of handling some very simple requirements like logging messages of
a certain level to one fd, and other messages of higher levels to a different fd
(i.e. info to stdout, warnings to stderr).
"""

from __future__ import absolute_import

__all__ = [
    'setup',
    'getLogger',
]

import sys
import os
import os.path
import logging
import logging.handlers

import getmailcore.exceptions

#
# Data
#

# Additional logging levels below INFO and DEBUG
MOREINFO = 15
TRACE = 5

# Formatting strings
logFormats = {
    'stdout' : '%(message)s',
    'stderr' : '%(levelname)-8s %(message)s',
    'trace' : '%(asctime)s %(name)s:%(levelname) '
              '%(module)s:%(funcName)s:%(lineno)d %(message)s',
    'message_log' : '%(asctime)s %(levelname)s %(message)s',
    'syslog' : '%(levelname) %(message)',
}

# Keep track of handlers we create so we can remove them later
handlers = set()
msgloghandlers = set()

#
# Class definititions
#

class Logger(logging.Logger):
    """Subclass to add convenience methods for the additional log levels.
    """
    def moreinfo(self, msg, *args, **kwargs):
        return self.log(MOREINFO, msg, *args, **kwargs)

    def trace(self, msg, *args, **kwargs):
        return self.log(TRACE, msg, *args, **kwargs)


class MaxInfoFilter(logging.Filter):
    """Filter to log only INFO and *below* messages.  The Python stdlib logging
    module still doesn't provide an obvious way to do this without having to
    subclass -- there's no `maxlevel` argument to a logger or handler object.
    """
    def filter(self, record):
        if record.levelno > logging.INFO:
            return False
        # Otherwise let the base class implementation decide
        return logging.Filter.filter(self, record)

#
# Functions
#

def getLogger(*args, **kwargs):
    return logging.getLogger(*args, **kwargs)

def setup(options):
    """Reset the logging configuration; each getmail rc file can have a 
    different logging configuration, so we need to start in a known state.
    
    @params
    
        options -- dict -- options dict as parsed from the getmail rc file
    """
#    print '\n\n***\n'
#    import pprint
#    pprint.pprint(options)
#    print '***\n\n'

    assert type(options) == dict
    rootLogger = logging.getLogger('')
    rootLogger.setLevel(0)
    for handler in handlers:
        handler.flush()
        rootLogger.removeHandler(handler)
    handlers.clear()
    msgLogger = logging.getLogger('msglog')
    msgLogger.propagate = False
    for handler in msgloghandlers:
        handler.flush()
        msgLogger.removeHandler(handler)
    msgloghandlers.clear()
    
    # Console logging - info and below to stdout
    assert options['verbose'] in (0, 1, 2, 3), (
        'bad verbose %s' % options['verbose']
    )
    if options['verbose'] == 0:
        # Quiet - no info messages at all, so don't set up stdout
        pass
    else:
        stdout = logging.StreamHandler(sys.stdout)
        if options['verbose'] == 1:
            level = logging.INFO
        elif options['verbose'] == 2:
            level = MOREINFO
        elif options['verbose'] == 3:
            level = logging.DEBUG
        stdout.setLevel(level)
        stdout_formatter = logging.Formatter(logFormats['stdout'])
        stdout.setFormatter(stdout_formatter)
        # Don't log warning and above to stdout; only to stderr
        stdout.addFilter(MaxInfoFilter())
        rootLogger.addHandler(stdout)
        handlers.add(stdout)
    # Console logging - warnings and above to stderr
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setLevel(logging.WARNING)
    stderr_formatter = logging.Formatter(logFormats['stderr'])
    stderr.setFormatter(stderr_formatter)
    rootLogger.addHandler(stderr)
    handlers.add(stderr)
    
    # Message log
    if options['message_log']:
        msglog = logging.handlers.RotatingFileHandler(
            options['message_log'], maxBytes=1<<20, backupCount=10
        )
        msglog.setLevel(MOREINFO if options['message_log_verbose'] 
                        else logging.INFO)
        msglog_formatter = logging.Formatter(logFormats['message_log'])
        msglog.setFormatter(msglog_formatter)
        msgLogger.addHandler(msglog)
        msgloghandlers.add(msglog)
        
    # Syslog
    if options['message_log_syslog']:
        syslog = logging.handlers.SysLogHandler(address='/dev/log', 
                                                facility='LOG_MAIL')
        syslog.setLevel(MOREINFO if options['message_log_verbose'] 
                        else logging.INFO)
        syslog_formatter = logging.Formatter(logFormats['syslog'])
        syslog.setFormatter(syslog_formatter)
        msgLogger.addHandler(syslog)
        msgloghandlers.add(syslog)

    # Trace/debugging logger
    if options['trace']:
        # Trace log, append everything to getmail-trace.log with more info
        for dir in ('.', os.path.expanduser('~'), '/tmp'):
            filename = os.path.join(dir, 'getmail-trace.log')
            if os.access(filename, os.F_OK | os.W_OK):
                break
            if os.path.exists(filename):
                continue
            if os.access(dir, os.F_OK | os.R_OK | os.W_OK | os.X_OK):
                break
        else:
            raise getmailcore.exceptions.getmailInvocationError(
                'Failed to find a writable trace log location; '
                'check ., ~/, /tmp .'
            )
        trace = logging.FileHandler(filename)
        rootLogger.info('Writing trace log %s' % filename)
        trace.setLevel(TRACE)
        trace_formatter = logging.Formatter(logFormats['trace'])
        trace.setFormatter(trace_formatter)
        rootLogger.addHandler(trace)
        handlers.add(trace)

#
# Initialization
#

logging.addLevelName(MOREINFO, 'MOREINFO')
logging.addLevelName(TRACE, 'TRACE')
logging.setLoggerClass(Logger)
