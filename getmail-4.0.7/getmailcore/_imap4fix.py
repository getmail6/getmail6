#!/usr/bin/env python2.3
'''Provide an SSL-capable POP3 class.

'''

__all__ = [
    'getmail_IMAP4_base',
    'getmail_IMAP4',
    'getmail_IMAP4_SSL',
]

from imaplib import *

class getmail_IMAP4_base:
    def select(self, mailbox='INBOX', readonly=None):
        """Select a mailbox.

        Flush all untagged responses.

        (typ, [data]) = <instance>.select(mailbox='INBOX', readonly=None)

        'data' is count of messages in mailbox ('EXISTS' response)
        and UIDVALIDITY value.
        """
        # Mandated responses are ('FLAGS', 'EXISTS', 'RECENT', 'UIDVALIDITY')
        self.untagged_responses = {}    # Flush old responses.
        self.is_readonly = readonly
        if readonly is not None:
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
        responselist = self.untagged_responses.get('EXISTS', [None])
        responselist.extend(self.untagged_responses.get('UIDVALIDITY', [None]))
        return (typ, responselist or [None])

class getmail_IMAP4(getmail_IMAP4_base, IMAP4):
    pass

class getmail_IMAP4_SSL(getmail_IMAP4_base, IMAP4_SSL):
    pass
