#!/usr/bin/python

import poplib
from getmail_constants import *

#
# Defaults
#
# These can mostly be overridden with commandline arguments or via getmailrc.
#

defs = {
    'help' :            0,                  # Leave this alone.
    'dump' :            0,                  # Leave this alone.
    'log_level' :       INFO,
    'getmaildir' :      '~/.getmail/',      # getmail config directory path
                                            #   leading ~[user]/ will be expanded
    'rcfilename' :      'getmailrc',        # getmail control file name

    'timeout' :         180,                # Socket timeout value in seconds
    'port' :            poplib.POP3_PORT,   # POP3 port number
    'use_apop' :        0,                  # Use APOP instead of PASS for
                                            #   authentication

    'readall' :         1,                  # Retrieve all mail, not just new
    'delete' :          0,                  # Do not delete mail after retrieval
    'delete_after' :    0,                  # Delete after X days

    'no_delivered_to' : 0,                  # Don't add Delivered-To: header
    'no_received' :     0,                  # Don't add Received: header
    'max_message_size' :    0,              # Maximum message size to retrieve
    'max_messages_per_session' : 0,         # Stop after X messages; 0 for no
                                            #   limit.
    'message_filter' :  None,               # Unix-style stdin->stdout filters
                                            #   to pass messages through after
                                            #   retrieval and before delivery
    'message_log' :     '',                 # Log info about getmail actions
                                            #   leading ~[user]/ will be expanded
                                            #   Will be prepended with value of
                                            #   getmaildir if message_log is not
                                            #   absolute after ~ expansion.

    'envelope_recipient' :    None,         # Header containing the original
                                            #   envelope recipient address.
                                            # Topmost Delivered-To: header is
                                            #   "delivered-to:1".  Second-from-top
                                            # Envelope-To: header would be
                                            #   "envelope-to:2".

    'extension_sep' :   '-',                # Extension address separator
    'extension_depth' : 1,                  # Number of local-part pieces to
                                            #   consider part of the base
    'use_*env' :        0,                  # Use Demon's SPDS *ENV command
                                            #   to retrieve envelope.
    }
                