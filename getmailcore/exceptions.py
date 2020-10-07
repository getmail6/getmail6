# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

'''Exceptions raised by getmail.
'''

__all__ = [
    'getmailError',
    'getmailConfigurationError',
    'getmailDnsLookupError',
    'getmailDnsServerFailure',
    'getmailOperationError',
    'getmailFilterError',
    'getmailRetrievalError',
    'getmailDeliveryError',
    'getmailCredentialError',
    'getmailLoginRefusedError',
    'getmailMailboxSelectError',
]

# Base class for all getmail exceptions
class getmailError(Exception):
    '''Base class for all getmail exceptions.'''
    pass

# Specific exception classes
class getmailConfigurationError(getmailError):
    '''Exception raised when a user configuration error is detected.'''
    pass

class getmailOperationError(getmailError):
    '''Exception raised when a runtime error is detected.'''
    pass

class getmailRetrievalError(getmailOperationError):
    '''Exception raised when a server (cough MSExchange cough) fails to
    hand over a message it claims to have.'''
    pass

class getmailFilterError(getmailOperationError):
    '''Exception raised when problems occur during message filtering.
    Subclass of getmailOperationError.
    '''
    pass

class getmailDeliveryError(getmailOperationError):
    '''Exception raised when problems occur during message delivery.
    Subclass of getmailOperationError.
    '''
    pass

class getmailDnsError(getmailOperationError):
    '''Base class for errors looking up hosts in DNS to connect to.'''
    pass

class getmailDnsLookupError(getmailDnsError):
    '''No such DNS name, or name found but no address records for it.'''
    pass

class getmailDnsServerFailure(getmailDnsError):
    '''DNS server failed when trying to look up name.'''
    pass

class getmailCredentialError(getmailOperationError):
    '''Error raised when server says "bad password", "no such user", etc
    (when that is possible to detect).'''
    pass

class getmailLoginRefusedError(getmailOperationError):
    '''Error raised when the server is just refusing logins due to reasons
    other than credential problems (when that is possible to detect):  server
    too busy, service shutting down, etc.'''
    pass

class getmailMailboxSelectError(getmailOperationError):
    '''Error raised when the server responds NO to an (IMAP) select mailbox
    command -- no such mailbox, no permissions, etc.
    '''
    pass
