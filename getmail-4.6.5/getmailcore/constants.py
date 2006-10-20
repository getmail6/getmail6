#!/usr/bin/env python2.3

# Log levels
(TRACE, DEBUG, MOREINFO, INFO, WARNING, ERROR, CRITICAL) = range(1, 8)

# Components of stack trace (indices to tuple)
FILENAME = 0
LINENO = 1
FUNCNAME = 2
#SOURCELINE = 3 ; not used
