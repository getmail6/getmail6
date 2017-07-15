"""A reliable mail-retriever toolkit.

getmail is a reliable, modular, extensible mail retriever with support for
simple and multidrop POP3 mailboxes, multidrop SDPS mailboxes, simple and
multidrop IMAP mailboxes.  Also supports POP3- and IMAP-over-SSL, message
filtering, and other features.

getmail is Copyright (C) 1998-2010 Charles Cazabon.  All rights reserved.
Distributed under the terms of the GNU General Public License version 2 (only).
You should have received a copy of the license in the file COPYING.
"""

import sys
if sys.version_info[:2] < (2, 5):
    raise ImportError('getmail version 5 requires Python version 2.5 or later')

__version__ = '5.0.0a1'

__all__ = [
    'baseclasses',
    'destinations',
    'exceptions',
    'filters',
    'logging',
    'message',
    'retrievers',
    'sslwrappers',
    'utilities',
]
