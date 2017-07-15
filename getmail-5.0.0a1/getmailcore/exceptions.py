"""Exceptions raised by getmail.
"""

__all__ = [
    'getmailError',
    'getmailInvocationError',
    'getmailSSLError',
    'getmailConfigurationError',
    'getmailOperationError',
    'getmailFilterError',
    'getmailRetrievalError',
    'getmailDeliveryError',
]

# Base class for all getmail exceptions
class getmailError(Exception):
    """Base class for all getmail exceptions."""
    pass

# Specific exception classes
class getmailInvocationError(getmailError):
    """Exception raised when a command error is detected."""
    pass

class getmailSSLError(getmailError):
    """Exception raised when an SSL security error is detected, such as a
    server certificate that fails validation."""
    pass

class getmailConfigurationError(getmailError):
    """Exception raised when a user configuration error is detected."""
    pass

class getmailOperationError(getmailError):
    """Exception raised when a runtime error is detected."""
    pass

class getmailRetrievalError(getmailOperationError):
    """Exception raised when a server (cough MSExchange cough) fails to 
    hand over a message it claims to have."""
    pass

class getmailFilterError(getmailOperationError):
    """Exception raised when problems occur during message filtering.
    Subclass of getmailOperationError.
    """
    pass

class getmailDeliveryError(getmailOperationError):
    """Exception raised when problems occur during message delivery.
    Subclass of getmailOperationError.
    """
    pass
