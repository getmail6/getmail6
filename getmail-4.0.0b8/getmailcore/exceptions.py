#!/usr/bin/env python2.3
'''Exceptions raised by getmail.
'''

__all__ = [
    'getmailError',
    'getmailConfigurationError',
    'getmailOperationError',
    'getmailDeliveryError',
]

# Base class for all getmail exceptions
class getmailError(StandardError):
    '''Base class for all getmail exceptions.'''
    pass

# Specific exception classes
class getmailConfigurationError(getmailError):
    '''Exception raised when a user configuration error is detected.'''
    pass

class getmailOperationError(getmailError):
    '''Exception raised when a runtime error is detected.'''
    pass

class getmailDeliveryError(getmailOperationError):
    '''Exception raised when problems occur during message delivery.
    Subclass of getmailOperationError.
    '''
    pass
                