#!/usr/bin/env python2.3
'''Compatibility class declarations used elsewhere in the package.

'''

__all__ = [
    'set',
    'frozenset',
]

import sys
import imaplib
import new


if sys.version_info < (2, 4, 0):
    # set/frozenset not built-in until Python 2.4
    import sets
    set = sets.Set
    frozenset = sets.ImmutableSet
set = set
frozenset = frozenset


if sys.version_info < (2, 5, 0):
    # Python < 2.5.0 has a bug with the readonly flag on imaplib's select().
    # Monkey-patch it in.

    def py25_select(self, mailbox='INBOX', readonly=False):
        """Select a mailbox.

        Flush all untagged responses.

        (typ, [data]) = <instance>.select(mailbox='INBOX', readonly=False)

        'data' is count of messages in mailbox ('EXISTS' response).

        Mandated responses are ('FLAGS', 'EXISTS', 'RECENT', 'UIDVALIDITY'), so
        other responses should be obtained via <instance>.response('FLAGS') etc.
        """
        self.untagged_responses = {}    # Flush old responses.
        self.is_readonly = readonly
        if readonly:
            name = 'EXAMINE'
        else:
            name = 'SELECT'
        typ, dat = self._simple_command(name, mailbox)
        if typ != 'OK':
            self.state = 'AUTH'     # Might have been 'SELECTED'
            return typ, dat
        self.state = 'SELECTED'
        if 'READ-ONLY' in self.untagged_responses \
                and not readonly:
            if __debug__:
                if self.debug >= 1:
                    self._dump_ur(self.untagged_responses)
            raise self.readonly('%s is not writable' % mailbox)
        return typ, self.untagged_responses.get('EXISTS', [None])

    imaplib.IMAP4.select = new.instancemethod(py25_select, None, imaplib.IMAP4)


if sys.version_info < (2, 5, 3):
    # A serious imaplib bug (http://bugs.python.org/issue1389051) was
    # fixed in 2.5.3.  Earlier Python releases need a work-around.
    # Monkey-patch it in.
    def fixed_read(self, size):
        """Read 'size' bytes from remote."""
        # sslobj.read() sometimes returns < size bytes
        chunks = []
        read = 0
        while read < size:
            data = self.sslobj.read(min(size-read, 16384))
            read += len(data)
            chunks.append(data)
        return ''.join(chunks)

    imaplib.IMAP4_SSL.read = new.instancemethod(fixed_read, None, 
                                                imaplib.IMAP4_SSL)
