#!/usr/bin/python

import re

# Exit codes
exitcodes = {
    'OK' : 0,
    'ERROR' : -1
    }

# Components of stack trace (indices to tuple)
FILENAME, LINENO, FUNCNAME = 0, 1, 2        #SOURCELINE = 3 ; not used

# Names for output logging levels
loglevels = {
    'TRACE' : 1,
    'DEBUG' : 2,
    'INFO' : 3,
    'WARN' : 4,
    'ERROR' : 5,
    'FATAL' : 6,
}

(TRACE, DEBUG, INFO, WARN, ERROR, FATAL) = range (1, 7)

# Options recognized in configuration getmailrc file
intoptions = (
    'delete',
    'delete_after',
    'extension_depth',
    'log_level',
    'max_message_size',
    'max_messages_per_session',
    'no_delivered_to',
    'no_received',
    'port',
    'readall',
    'timeout',
    'use_apop',
    'use_*env',
    'verbose'
)
stringoptions = (
    'envelope_recipient',
    'extension_sep',
    'message_log',
    'postmaster',
)
listoptions = (
)

# Line ending conventions
line_end = {
    'pop3' : '\r\n',
    'maildir' : '\n',
    'mbox' : '\n'
    }

res = {
    # Regular expression object to find line endings
    'eol' : re.compile (r'\r?\n\s*', re.MULTILINE),
    # Regular expression to do POP3 leading-dot unescapes
    'leadingdot' : re.compile (r'^\.\.', re.MULTILINE),
    # Percent sign escapes
    'percent' : re.compile (r'%(?!\([\S]+\)[si])'),
}

