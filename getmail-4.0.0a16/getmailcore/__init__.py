#!/usr/bin/env python2.3
'''A reliable mail-retriever toolkit.

getmail is a reliable, modular, extensible mail retriever with support for 
simple and multidrop POP3 mailboxes, multidrop SPDS mailboxes, and (unfinished) 
IMAP mailboxes.
'''

import sys
if sys.hexversion < 0x2030300:
    raise ImportError('getmail requires Python version 2.3.3 or later')

__version__ = '4.0.0a16'

__all__ = ['constants', 'destinations', 'exceptions', 'filters', 'logging', 'retrievers', 'utilities']
