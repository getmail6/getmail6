#!/usr/bin/python

VERSION = '0.1'

#
# Imports
#

import sys, os, string, time, socket, poplib
from types import *

from debugutil import *


#
# Defaults
#

DEF_PORT =				110				# Normal POP3 port
DEF_DELETE =			0				# Delete mail after retrieving (0, 1)
DEF_READ_ALL =			0				# Retrieve all mail (1) or just new (0)
DEF_PASSWORD_STDIN =	0				# Read POP3 password from stdin (0, 1)


#
# Options
#

opt_host =				None
opt_port =				DEF_PORT
opt_account =			None
opt_password =			None
opt_password_stdin =	DEF_PASSWORD_STDIN
opt_delete_retrieved =	DEF_DELETE
opt_retrieve_read =		DEF_READ_ALL
opt_maildir =			None
opt_verbose =			0

#
# Data
#

OK, ERROR = (0, -1)

CR =			'\r'
LF =			'\n'
EOT =			int (-1)
POP3_EOL =		CR+LF					# POP3 demands CR+LF as end-of-line
POP3_OK =		'+OK'					# Mandated by standard (rfc1939)
POP3_ERR =		'-ERR'					# ditto
POP3_TERM =		'.'						# termination octect

argv = sys.argv
stderr = sys.stderr.write

deliverycount = 0

#DEBUG = debugutil.DEBUG

#
# Functions
#

#######################################
def main ():
	''''getmail.py, a POP3 mail retriever.
	Copyright (C) 1999 Charles Cazabon
	Licensed under the GNU General Public License version 2.
	Run without arguments for help.
	'''
	DEBUG ()
	about ()
	parse_options (sys.argv)
	
	session = poplib.POP3 (opt_host, opt_port)

	if opt_verbose:
		print '%s POP3 session initiated' % opt_host
	
	rc = session.getwelcome ()
	if string.index (rc, POP3_OK) != 0:
		DEBUG (FATAL, 'server %s returned greeting "%s"' % (opt_host, rc))
		sys.exit (ERROR)
	if opt_verbose:
		print '%s POP3 greeting:  %s' % (opt_host, rc)
	
	rc = session.user (opt_account)
	if string.index (rc, POP3_OK) != 0:
		DEBUG (FATAL, 'server %s returned "%s", to USER command' % (opt_host, rc))
		sys.exit (ERROR)
	if opt_verbose:
		print '%s POP3 password prompt:  %s' % (opt_host, rc)
	
	rc = session.pass_ (opt_password)
	if string.index (rc, POP3_OK) != 0:
		DEBUG (FATAL, 'server %s returned "%s" to PASS command'  % (opt_host, rc))
		sys.exit (ERROR)
	if opt_verbose:
		print '%s POP3 password response:  %s' % (opt_host, rc)
	
	# Retrieve message list
	try:
		list = session.list ()
		rc = list[0]
		msglist = list[1]
		if string.index (rc, POP3_OK) != 0:
			DEBUG (FATAL, 'server %s returned "%s" to LIST command'
				 % (opt_host, rc))
			sys.exit (ERROR)
		DEBUG (TRACE, '%s list response:  %s' % (opt_host, list))
		if opt_verbose:
			print '%s POP3 list response:  %s\n\tmessage list:  %s' \
					% (opt_host, rc, msglist)

	except poplib.error_proto:
		DEBUG (ERROR, 'exception retrieving messages, resetting...')
		session.rset ()
		session.quit ()
		sys.exit (ERROR)

	for item in msglist:
		if type (item) == IntType:
			# No more messages; POP3.list() returns a final int
			if opt_verbose:
				print '%s:  finished retrieving messages' % opt_host
			break
		msgnum, msglen = string.split (item)
		if opt_verbose:
			print 'msg %i, len %i' % (int (msgnum), int (msglen))
		result = session.retr (int (msgnum))
		rc = result[0]
		if string.index (rc, POP3_OK) != 0:
			stderr ('Error retrieving msg %i len %i\n'
					% (int (msgnum), int (msglen)))
			continue
		msg = result[1]
		maildirdeliver (opt_maildir, (unescape_lines (msg)))
		if opt_verbose:
			print 'delivered msg %i len %i' % (int (msgnum), int (msglen))
		if opt_delete_retrieved:
			rc = session.dele (int (msgnum))
			if string.index (rc, POP3_OK) != 0:
				stderr ('error deleting msg %i len %i\n' \
						% (int (msgnum), int (msglen)))
			


	if opt_verbose:
		print '%s POP3 session completed' % opt_host
	
	# DEBUG 
	# session.rset ()
	session.quit ()

	if opt_verbose:
		print '%s POP3 connection closed' % opt_host

	sys.exit (OK)
	

#######################################
def maildirdeliver (maildir, message):
	DEBUG ()
	# Uses Dan Bernstein's recommended naming convention for maildir delivery
	# See http://cr.yp.to/proto/maildir.html
	global deliverycount
	_time = time.time ()
	pid = os.getpid ()
	hostname = socket.gethostname ()
	filename = '%s.%s_%s.%s' % (_time, pid, deliverycount, hostname)
	
	fname_tmp = os.path.join (maildir, 'tmp', filename)
	fname_new = os.path.join (maildir, 'new', filename)

	# Try to open file for reading first
	try:
		f = open (fname_tmp, 'rb')
		f.close ()
		DEBUG (ERROR, 'delivery failure:  file "%s" exists\n' % fname_tmp)
		raise 'error:  file "%s" exists' % fname_tmp

	except IOError:
		# Good, file doesn't exist.
		pass
		
	# Open it to write
	try:
		f = open (fname_tmp, 'wb')
		f.writelines (message)
		f.close ()

	except IOError:
		DEBUG (ERROR, 'delivery failure writing file "%s"\n' % fname_tmp)
		raise 'error: failure writing file "%s"' % fname_tmp
		
	# Move from tmp to new
	try:
		os.rename (fname_tmp, fname_new)

	except OSError:
		DEBUG (ERROR, 'delivery failure moving file "%s" to "%s"\n'
			   % (fname_tmp, fname_new))
		raise 'error: failure moving file "%s" to "%s"' \
			   % (fname_tmp, fname_new)

	# Delivery done		
	deliverycount = deliverycount + 1
	return


#######################################
def unescape_line (raw_line):
	'''Receive a raw line (in POP3 format) and convert to internal
	Python format (e.g. EOL convention).  Also strip leading doubled periods,
	and anything trailing the POP3 termination octect (which is '.' surrounded
	by CR+LF pairs).
	'''
	#
	DEBUG ()
	DEBUG (TRACE, 'raw_line == %s' % raw_line)
	line = string.replace (string.replace (raw_line, CR, ''), LF, '')
	if line == POP3_TERM:
		return ''
	elif len (line) >= 2 and line[0:1] == '..':
		line = line[1:]
	line = '%s\n' % line
	DEBUG (TRACE, 'line == %s' % line)
	return line


#######################################
def unescape_lines (raw_lines):
	'''Receive a message in raw POP3 format and convert to internal
	Python format (e.g. EOL convention).  Also strip leading doubled periods,
	and anything trailing the POP3 termination octect (which is '.' surrounded
	by CR+LF pairs).
	'''
	#
	DEBUG ()
	lines = []
	for raw_line in raw_lines:
		line = string.replace (string.replace (raw_line, CR, ''), LF, '')
		if line == POP3_TERM:
			continue
		elif len (line) >= 2 and line[0:1] == '..':
			line = line[1:]
		line = '%s\n' % line
		lines.append (line)
	return lines


#######################################
def about ():
	DEBUG ()
	print 'getmail v.%s\n' \
		  'Copyright (C) 1999 Charles Cazabon <getmail@discworld.dyndns.org>\n' \
		  'Licensed under the GNU General Public License version 2.\n\n' \
		  % VERSION
	return
	

#######################################
def usage ():
	DEBUG ()
	me = string.strip (os.path.split (sys.argv[0])[-1])
	# Set up default option displays
	def_delete_s = def_dontdelete_s = def_readall_s = def_readnew_s \
		= def_stdin_s = ''
	if DEF_DELETE:			def_delete_s = '(default)'
	else:					def_dontdelete_s = '(default)'
	if DEF_READ_ALL:		def_readall_s = '(default)'
	else:					def_readnew_s = '(default)'
	if DEF_PASSWORD_STDIN:	def_stdin_s = '(default)'
	
	stderr ('\n'
	'Usage:  %s <--host value> <--name value> <--pass value | --stdin> \\\n'
	'           <--maildir value> [options]\n\n'
	'Options:\n'
	'  -h or --host <hostname>    POP3 hostname                 (required)\n'
	'  -n or --name <account>     POP3 account name             (required)\n'
	'  -d or --maildir <maildir>  maildir to deliver to         (required)\n'
	'  -P or --port <portnum>     POP3 port                     (default: %i)\n'
	'  -p or --pass <password>    POP3 password\n'
	'  -s or --stdin              read POP3 password from stdin %s\n'
	'  -a or --all                retrieve all messages         %s\n'
	'  -n or --new (NOT IMPLEMENTED)retrieve only new messages    %s\n'
	'  -d or --delete             delete mail after retrieving  %s\n'
	'  -l or --dont-delete        leave mail on server          %s\n'
	'  -v or --verbose            output more information\n'
	'\n'
		% (me, DEF_PORT, def_stdin_s, def_readall_s, def_readnew_s, def_delete_s,
		   def_dontdelete_s))
	return
	
#######################################
def parse_options (argv):
	'''Parse commandline options.  Options handled:
	--delete -d, --dont-delete -l, --all -a, --new -n, --stdin -s,
	--port -P <portnum>,--host -h <hostname>, --name -n <account>,
	--pass -p <password>, --maildir -d <maildir>, --verbose -v
	'''
	#
	DEBUG ()
	global opt_delete_retrieved, opt_retrieve_read, opt_password_stdin, opt_port, \
		opt_host, opt_account, opt_password, opt_maildir, opt_verbose
	error = 0

	DEBUG (TRACE, 'argv == %s' % argv)
	
	for option in argv:
		# parse options
		if option == '--delete' or option == '-d':
			opt_delete_retrieved = 1
			DEBUG (TRACE, 'option --delete')

		elif option == '--dont-delete' or option == '-l':
			opt_delete_retrieved = 1
			DEBUG (TRACE, 'option --dont-delete')

		elif option == '--all' or option == '-a':
			opt_retrieve_read = 1
			DEBUG (TRACE, 'option --all')

		elif option == '--new' or option == '-n':
			# Not implemented
			opt_retrieve_read = 0
			DEBUG (TRACE, 'option --unread')

		elif option == '--stdin' or option == '-s':
			opt_password_stdin = 1
			DEBUG (TRACE, 'option --stdin')

		elif option == '--verbose' or option == '-v':
			opt_verbose = 1
			DEBUG (TRACE, 'option --verbose')

		elif option == '--port' or option == '-P':
			try:
				opt_port = int (argv[argv.index ('--port') + 1])
				DEBUG (TRACE, 'option --port == %i' % opt_port)
			except ValueError:
				try:
					opt_port = int (argv[argv.index ('-P') + 1])
					DEBUG (TRACE, 'option --port == %i' % opt_port)
				except ValueError:
					DEBUG (FATAL, 'option --port with no value')
					stderr ('Error:  option --port supplied without value\n')
					error = 1

		elif option == '--host' or option == '-h':
			try:
				opt_host = argv[argv.index ('--host') + 1]
				DEBUG (TRACE, 'option --host == %s' % opt_host)
			except ValueError:
				try:
					opt_host = argv[argv.index ('-h') + 1]
					DEBUG (TRACE, 'option --host == %s' % opt_host)
				except ValueError:
					DEBUG (FATAL, 'option --host with no value')
					stderr ('Error:  option --host supplied without value\n')
					error = 1

		elif option == '--name' or option == '-n':
			try:
				opt_account = argv[argv.index ('--name') + 1]
				DEBUG (TRACE, 'option --account == %s' % opt_account)
			except ValueError:
				try:
					opt_account = argv[argv.index ('-n') + 1]
					DEBUG (TRACE, 'option --account == %s' % opt_account)
				except ValueError:
					DEBUG (FATAL, 'option --name with no value')
					stderr ('Error:  option --name supplied without value\n')
					error = 1

		elif option == '--pass' or option == '-p':
			try:
				opt_password = argv[argv.index ('--pass') + 1]
				DEBUG (TRACE, 'option --pass == %s' % opt_password)
			except ValueError:
				try:
					opt_password = argv[argv.index ('-p') + 1]
					DEBUG (TRACE, 'option --pass == %s' % opt_password)
				except ValueError:
					DEBUG (FATAL, 'option --pass with no value')
					stderr ('Error:  option --pass supplied without value\n')
					error = 1

		elif option == '--maildir' or option == '-d':
			try:
				opt_maildir = argv[argv.index ('--maildir') + 1]
				DEBUG (TRACE, 'option --maildir == %s' % opt_maildir)
			except ValueError:
				try:
					opt_maildir = argv[argv.index ('-d') + 1]
					DEBUG (TRACE, 'option --maildir == %s' % opt_maildir)
				except ValueError:
					DEBUG (FATAL, 'option --maildir with no value')
					stderr ('Error:  option --maildir supplied without value\n')
					error = 1

	# Read password from stdin if requested
	if opt_password_stdin:
		try:
			print 'Enter password:  ',
			t = sys.stdin.readline ()
			t = string.replace (string.replace (t, CR, ''), LF, '')
			opt_password = string.strip (t)
			if not t:  raise ValueError
			DEBUG (TRACE, 'opt_password from stdin == %s' % opt_password)
		except ValueError:
			DEBUG (FATAL, 'failed to read password from stdin')
			stderr ('Error:  failed to read password from stdin\n')
			error = 1
		
	# Check mandatory options
	if not opt_host:
		DEBUG (FATAL, 'no host')
		stderr ('Error:  no host supplied\n')
		error = 1
	if not opt_account:
		DEBUG (FATAL, 'no account')
		stderr ('Error:  no account supplied\n')
		error = 1
	if not opt_password:
		DEBUG (FATAL, 'no password')
		stderr ('Error:  no password supplied\n')
		error = 1
	if not opt_maildir:
		DEBUG (FATAL, 'no maildir')
		stderr ('Error:  no maildir supplied\n')
		error = 1

	if error:
		usage ()
		sys.exit (ERROR)

	return


#######################################
if __name__ == '__main__':
	main ()

					
