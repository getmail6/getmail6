#!/usr/bin/env python

# Log levels
(TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL) = range(1, 7)

# Components of stack trace (indices to tuple)
FILENAME = 0
LINENO = 1
FUNCNAME = 2
#SOURCELINE = 3 ; not used
