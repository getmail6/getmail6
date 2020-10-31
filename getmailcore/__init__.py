# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

'''A reliable mail-retriever toolkit.

getmail is a reliable, modular, extensible mail retriever with support for
simple and multidrop POP3 mailboxes, multidrop SDPS mailboxes, simple and
multidrop IMAP mailboxes.  Also supports POP3- and IMAP-over-SSL, message
filtering, and other features.
'''

import sys

__version__ = '6.9'
__license__ = 'GNU GPL version 2'

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
