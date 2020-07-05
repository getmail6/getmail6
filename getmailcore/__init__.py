'''A reliable mail-retriever toolkit.

getmail is a reliable, modular, extensible mail retriever with support for
simple and multidrop POP3 mailboxes, multidrop SDPS mailboxes, simple and
multidrop IMAP mailboxes.  Also supports POP3- and IMAP-over-SSL, message
filtering, and other features.

getmail is Copyright (C) 1998-2019 Charles Cazabon.  All rights reserved.
Distributed under the terms of the GNU General Public License version 2 (only).
You should have received a copy of the license in the file COPYING.
'''

import sys

__version__ = '6.01'

# ROLAND: yet to determine
__py_required__ = '2.7.18'
__py_required_hex__ = 0x20712f0

if sys.hexversion < __py_required_hex__:
    raise ImportError('getmail version %s requires Python version %s '
                      'or later'%(__version__,__py_required__))

__all__ = [
    'baseclasses',
    'constants',
    'destinations',
    'exceptions',
    'filters',
    'imap_utf7',
    'logging',
    'message',
    'retrievers',
    'utilities',
]
