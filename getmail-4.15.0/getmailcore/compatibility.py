#!/usr/bin/env python2.3
'''Compatibility class declarations used elsewhere in the package.

'''

__all__ = [
    'set',
    'frozenset',
]

import sys

if sys.hexversion < 0x2040000:
    # set/frozenset not built-in until Python 2.4
    import sets
    set = sets.Set
    frozenset = sets.ImmutableSet
set = set
frozenset = frozenset

