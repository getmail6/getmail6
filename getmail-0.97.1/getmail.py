#!/usr/bin/python
#
# getmail.py Copyright (C) 2000 Charles Cazabon <getmail@discworld.dyndns.org>
#
# Licensed under the GNU General Public License version 2. See the file COPYING
# for details.
#
# getmail is a simple POP3 mail retriever with robust Maildir delivery.
# It can now also deliver to mbox-style files.
# It is intended as a simple replacement for 'fetchmail' for those people
# who don't need its various and sundry options, bugs, and configuration
# difficulties.  It currently supports retrieving mail for multiple accounts
# from multiple POP3 hosts, with delivery to Maildirs specified on a
# per-account basis.
#
# getmail returns 0 when it retrieves mail, 1 if there is no mail to retrieve,
#, -1 on error.  100 and 101 are debugging/diagnostic codes for now.
#
# Basic usage:
#
# Run without arguments for help.
#
# To retrieve mail for accounts on a one-time basis, run with arguments as
# follows:
#  getmail.py [options] user1@mailhost1[:port],destination[,password1] \
#    user2@mailhost2[:port],destination[,password2]
#
# If port is omitted, it defaults to the standard POP3 port, 110.
# If passwords are omitted, they will be prompted for.
# 'destination' is the delivery target; getmail currently supports Maildirs
# and mbox files.  getmail will complain if a directory is given but is
# not a Maildir.  If a regular file is given, getmail assumes it is an mbox
# file.
#
# To regularly retrieve from the same accounts, it is easiest to use a
# configuration file and data directory.  Create a directory named '.getmail'
# in your home directory, and a file named '.getmailrc' in this directory.
# The format of this file is described in the file USAGE.
# The configuration file can be specified on the commandline with the -r or
# --rcfile options, and the directory can be overridden with the contents of
# the GETMAIL environment variable or the --configdir or -c options.
#
# Use of a config/data directory allows getmail to keep track of messages it
# has already seen, and can then retrieve only new mail if desired.
#
# Maildir is the mail storage format designed by Dan Bernstein, author of
# qmail (among other things).  It is supported by many Unix MUAs, including
# mutt (www.mutt.org) and modified versions of pine. For more information
# on the Maildir format, see http://cr.yp.to/proto/maildir.html.
#

VERSION = '0.97.1'

#
# Imports
#

import sys, os, string, time, socket, poplib, getopt, termios, TERMIOS, fcntl, \
	rfc822, cStringIO, ConfigParser
from types import *


#
# Defaults
#
# These can all be overridden with commandline arguments.
#

DEF_PORT =				110				# Normal POP3 port
DEF_DELETE =			0				# Delete mail after retrieving (0, 1)
DEF_READ_ALL =			1				# Retrieve all mail (1) or just new (0)
DEF_RCFILE =			'.getmailrc'	# Default.getmailrc filename
ENV_GETMAIL =			'GETMAIL'		# Env. variable to get configuration/
										#  data directory name from
ENV_GETMAILOPTS =		'GETMAILOPTS'	# Default options can be put in this
										#  environment variable
DEF_ADDREXT =			'-'				# Default character used for matching
										#  qmail-style extension addresses


#
# Options
#

opt_host =				[]
opt_port =				[]
opt_account =			[]
opt_password =			[]
opt_delete_retrieved =	[]
opt_retrieve_read =		[]
opt_dest =				[]
opt_verbose =			0
opt_rcfile =			None
opt_configdir =			None
opt_dump =				0
opt_ignoreconfig =		0
opt_addrext =			DEF_ADDREXT
opt_showhelp =			0


#
# Data
#

true, false = ['true', 'yes', '1'], ['false', 'no', '0']

CR =			'\r'
LF =			'\n'
deliverycount = 0
argv = 			sys.argv
stderr = 		sys.stderr.write

# Exit codes
OK, ERROR = (0, -1)
RC_NEWMAIL	= 0
RC_NOMAIL	= 1
RC_DEBUG	= 100
RC_HELP		= 101


#
# Functions
#

#######################################
def main ():
	'''getmail.py, a POP3 mail retriever with reliable maildir delivery.
	Copyright (C) 2000 Charles Cazabon <getmail@discworld.dyndns.org>
	Licensed under the GNU General Public License version 2.  See the file
	COPYING for details.  Run without arguments for help.
	'''
	about ()
	parse_options (sys.argv)

	for i in range (len (opt_account)):
		print
		mail = get_mail (opt_host[i], opt_port[i], opt_account[i],
						 opt_password[i], opt_configdir,
						 opt_delete_retrieved[i], opt_retrieve_read[i],
						 opt_verbose)

		for msg in mail:
			try:
				rc = deliver_msg (opt_dest[i], pop3_unescape (msg))
				if opt_verbose:
					print 'Delivered message to %s' % rc
					sys.stdout.flush ()

			except:
				stderr ('Error encountered during delivery\n  (%s)\n' % cause)

				t = 'tmpmail.%s:%s:%s' % (time.time (), os.getpid (),
										  len (msg))
				f = open (t, 'w')
				f.writelines (pop3_unescape (msg))
				f.close ()
				stderr ('Message saved to file "%s"\n' % t)
				time.sleep (1)

	if deliverycount:	sys.exit (RC_NEWMAIL)
	else:				sys.exit (RC_NOMAIL)


#######################################
def get_mail (host, port, account, password, datadir, delete, getall, verbose):
	'Retrieve messages from a POP3 server for one account.'

	messages, retrieved = [], 0
	shorthost = string.split (host, '.') [0]
	oldmailfile = os.path.join (datadir, 'oldmail:%s:%s' % (host, account))
	oldmail = []

	try:
		f = open (oldmailfile, 'r')
		for line in f.readlines ():
			oldmail.append (line)
		f.close ()
	except IOError:
		pass

	try:
		session = poplib.POP3 (host, port)
		if opt_verbose:
			print '%s:  POP3 session initiated on port %s for "%s"' \
				% (shorthost, port, account)
		rc = session.getwelcome ()
		if verbose:  print '%s:  POP3 greeting:  %s' % (shorthost, rc)
	except poplib.error_proto, response:
		stderr ('%s:  returned greeting "%s"\n' % (shorthost, response))
		return []
	except socket.error, txt:
		stderr ('Exception connecting to %s:  %s\n' % (opt_host, txt))
		return []

	try:
		rc = session.user (account)
		if verbose:  print '%s:  POP3 user reponse:  %s' % (shorthost, rc)
		rc = session.pass_ (password)
		if verbose:  print '%s:  POP3 password response:  %s' % (shorthost, rc)
	except poplib.error_proto, response:
		stderr ('%s:  returned "%s" during login\n' % (shorthost, response))
		return []

	# Retrieve message list
	try:
		list = session.list ()
		rc = list[0]
		msglist = list[1]
		if verbose:  print '%s:  POP3 list response:  %s' % (shorthost, rc)

	except poplib.error_proto, response:
		stderr ('Error retrieving message list, skipping ...\n')

	try:
		for item in msglist:
			if type (item) == IntType:
				# No more messages; POP3.list() returns a final int
				if verbose:
					print '%s:  finished retrieving messages' % shorthost
				break
			msgnum, msglen = string.split (item)
			if verbose:
				print '  msg %i : len %i ...' % (int (msgnum), int (msglen)),
				sys.stdout.flush ()

			rc = session.uidl (msgnum)
			uidl = rc [ string.find (rc, '<') : string.find (rc, '>') + 1 ]

			if getall or ('%s\n' % uidl) not in oldmail:
				result = session.retr (int (msgnum))
				rc = result[0]
				msg = result[1]

				messages.append (msg)
				retrieved = retrieved + 1

				if verbose:  print 'retrieved',; sys.stdout.flush ()
				if delete:
					rc = session.dele (int (msgnum))
					if verbose:  print '... deleted',; sys.stdout.flush ()
					try:
						# Deleting mail, no need to remember uidl's now
						os.remove (oldmailfile)
					except:
						pass
				else:
					try:
						f = open (oldmailfile, 'a')
						f.seek (0, 2) # Append to end.
						f.write ('%s\n' % uidl)
						f.close ()
						if verbose:
							print '... wrote to oldmail file',
							sys.stdout.flush ()
					except IOError:
						stderr ('\nError:  failed writing oldmail file\n')

			else:
				print 'previously retrieved, skipping ...',

			if verbose:  print ''; sys.stdout.flush ()

	except poplib.error_proto, response:
		stderr ('%s:  exception "%s" during retrieval, resetting...\n'
				% (shorthost, response))
		session.rset ()

	if verbose:
		print '%s:  POP3 session completed for "%s"' % (shorthost, account)

	session.quit ()

	if verbose:
		print '%s:  POP3 connection closed' % shorthost
		print '%i messages retrieved\n' % retrieved

	return messages


#######################################
def deliver_msg (dest, message):
	'''Determine the type of destination and dispatch to appropriate delivery
	routine.  Currently understands Maildirs and assumes any regular file is
	an mbox file.
	'''
	mdir_new = os.path.join (dest, 'new')
	mdir_tmp = os.path.join (dest, 'tmp')

	if os.path.isdir (mdir_new) and os.path.isdir (mdir_tmp):
		maildirdeliver (dest, message)
		return 'Maildir "%s"' % dest

	elif os.path.isfile (dest):
		mboxdeliver (dest, message)
		return 'mbox file "%s"' % dest

	elif not os.path.exists (dest):
		stderr ('Error:  "%s" does not exist\n' % dest)
		raise 'error:  "%s" does not exist\n' % dest

	else:
		stderr ('Error:  "%s" is not a Maildir or mbox\n' % dest)
		raise 'error:  "%s" is not a Maildir or mbox' % dest

	# Can't reach
	return


#######################################
def maildirdeliver (maildir, message):
	'Reliably deliver a mail message into a Maildir.'
	# Uses Dan Bernstein's recommended naming convention for maildir delivery
	# See http://cr.yp.to/proto/maildir.html
	global deliverycount
	_time = int (time.time ())
	pid = os.getpid ()
	unique = '%s_%s' % (pid, deliverycount)
	hostname = string.split (socket.gethostname (), '.')[0]
	filename = '%s.%s.%s' % (_time, unique, hostname)

	fname_tmp = os.path.join (maildir, 'tmp', filename)
	fname_new = os.path.join (maildir, 'new', filename)

	# Try to open file for reading first
	try:
		f = open (fname_tmp, 'rb')
		f.close ()
		stderr ('Error:  file "%s" exists\n' % fname_tmp)
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
		stderr ('Error:  failure writing file "%s"\n' % fname_tmp)
		raise 'error: failure writing file "%s"' % fname_tmp

	# Move from tmp to new
	try:
		os.rename (fname_tmp, fname_new)

	except OSError:
		stderr ('Error: failure moving file "%s" to "%s"\n' \
			   % (fname_tmp, fname_new))
		raise 'error: failure moving file "%s" to "%s"' \
			   % (fname_tmp, fname_new)

	# Delivery done
	deliverycount = deliverycount + 1
	return


#######################################
def mboxdeliver (mbox, message):
	'Deliver a mail message into an mbox file.'
	global deliverycount
	dtime = time.asctime (time.gmtime (time.time ()))

	f = cStringIO.StringIO ()
	f.writelines (message)
	f.flush ()
	f.seek (0)

	m = rfc822.Message (f)
	addrlist = m.getaddrlist ('return-path')
	try:
		env_sender = addrlist[0][1]
	except IndexError:
		# No Return-Path: header
		stderr ('Warning:  no Return-Path: header in message\n')
		env_sender = '<@[]>'

	f.close ()

	env_sender = string.replace (string.replace (env_sender, '<', ''), '>', '')

	fromline = 'From %s %s\n' % (env_sender, dtime)

	# Open mbox
	try:
		f = open (mbox, 'a')
		fcntl.flock (f.fileno (), fcntl.LOCK_EX)
		f.seek (0, 2) 					# Seek to end
		f.write (fromline)
		esc_from = 0
		for line in message:
			if esc_from and line[0 : 5] == 'From ':
				line = '>%s' % line
			f.write (line)
			if line == '\n':	esc_from = 1
			else:				esc_from = 0
		f.write ('\n')
		f.flush ()
		fcntl.flock (f.fileno (), fcntl.LOCK_UN)
		f.close ()

	except IOError, cause:
		# ???
		stderr ('Error:  failure writing message to mbox file "%s":  %s\n'
				% (cause, mbox))
		raise

	# Delivery done
	deliverycount = deliverycount + 1
	return


#######################################
def pop3_unescape (raw_lines):
	'''Receive message(s) in raw format as returned by POP3 server, and
	convert to internal format (e.g. Unix EOL convention).  Also strips
	leading doubled periods as required by the POP3 standard.
	'''
	lines = []
	for line in raw_lines:
		line = string.replace (string.replace (line, CR, ''), LF, '')
		if len (line) >= 2 and line[0 : 2] == '..':
			line =  line [1 : ]
		lines.append ('%s\n' % line)
	return lines


#######################################
def about ():
	print 'getmail v.%s\n' \
		  'Copyright (C) 2000 Charles Cazabon <getmail@discworld.dyndns.org>\n' \
		  'Licensed under the GNU General Public License version 2.  See the file\n' \
		  'COPYING for details.\n' \
		  % VERSION
	return


#######################################
def usage ():
	me = string.strip (os.path.split (sys.argv[0])[-1])
	# Set up default option displays
	def_del = def_dontdel = def_readall = def_readnew = ''
	if DEF_DELETE:			def_del =		'(default)'
	else:					def_dontdel =	'(default)'
	if DEF_READ_ALL:		def_readall =	'(default)'
	else:					def_readnew =	'(default)'

	stderr ('\n'
	'Usage:  %s [options] [user@mailhost[:port],destination[,password]] [...]\n'
	'Options:\n'
	'  -a or --all                retrieve all messages                %s\n'
	'  -n or --new                retrieve unread messages             %s\n'
	'  -d or --delete             delete mail after retrieving         %s\n'
	'  -l or --dont-delete        leave mail on server                 %s\n'
	'  -v or --verbose            output more information\n'
	'  -h or --help               this screen\n'
	'  -r or --rcfile <file>      use <file> instead of default .getmailrc\n'
	'  -c or --configdir <dir>    use <dir> as config/data directory,\n'
	'      Default configdir is directory set in "%s" environment variable\n'
	'  -i or --ignoreconfig       don\'t read default config file\n'
	'  --dump                     dump configuration for debugging\n'
	'\n'
	'\'destination\' can be a Maildir or an mbox file.  Do not attempt to deliver\n'
	'to an mbox file over NFS.  To retrieve mail for multiple accounts, use a\n'
	'.getmailrc configuration file, or supply multiple arguments on the commandline.\n'
	'If not supplied, port defaults to %i.  Passwords not supplied will be prompted\n'
	'for.\n\n'
		% (me, def_readall, def_readnew, def_del, def_dontdel, ENV_GETMAIL, DEF_PORT))
	return


#######################################
def read_configfile (file):
	'''Read in configuration file.
	'''
	#
	global opt_delete_retrieved, opt_retrieve_read, \
		opt_port, opt_host, opt_account, opt_password, opt_dest, \
		opt_verbose

	defaults = { 'port'    : '%s' % DEF_PORT,
				 'delete'  : '%s' % DEF_DELETE,
				 'readall' : '%s' % DEF_READ_ALL,
				 'password': ''
			   }

	conf = ConfigParser.ConfigParser (defaults)

	try:
		conf.read (file)
		sections = conf.sections ()
		for section in sections:
			account = conf.get (section, 'account')
			host = conf.get (section, 'host')
			port = int (conf.get (section, 'port'))
			pw = conf.get (section, 'password')
			dest = conf.get (section, 'destination')
			dele = string.lower (conf.get (section, 'delete'))
			rall = string.lower (conf.get (section, 'readall'))

			# Strip 'poison NUL' bytes just in case
			account = string.replace (account, '\0', '')
			host = string.replace (host, '\0', '')
			pw = string.replace (pw, '\0', '')
			dest = string.replace (dest, '\0', '')

			opt_account.append (string.strip (account))
			opt_host.append (string.strip (host))
			opt_port.append (port)
			opt_password.append (string.strip (pw))
			opt_dest.append (string.strip (dest))
			if dele in true:
				opt_delete_retrieved.append (1)
			else:
				opt_delete_retrieved.append (0)
			if rall in true:
				opt_retrieve_read.append (1)
			else:
				opt_retrieve_read.append (0)

	# User configuration errors
	except ConfigParser.NoOptionError, cause:
		stderr ('Error:  required option missing in configuration file "%s"\n'
				'  (%s)\n' % (file, cause))
		sys.exit (ERROR)

	except ConfigParser.MissingSectionHeaderError, cause:
		stderr ('Error:  file "%s" does not appear to be a getmail '
				'configuration file\n  (%s)\n' % (file, cause))
		sys.exit (ERROR)

	except ConfigParser.DuplicateSectionError, cause:
		stderr ('Error:  duplicated section name in configuration file "%s"\n'
				'  (%s)\n' % (file, cause))
		sys.exit (ERROR)

	except ConfigParser.ParsingError, cause:
		stderr ('Warning:  failure reading configuration file "%s"\n'
				'  (%s)\n' % (file, cause))
		# Maybe no config file, just skip it.
		return

	# Bugs in getmail
	except (ConfigParser.NoSectionError,
			ConfigParser.InterpolationError), cause:
		stderr ('Error:  internal error parsing file "%s"\n  (%s)\n'
				% (file, cause))
		sys.exit (ERROR)

	return


#######################################
def parse_options (argv):
	'''Parse commandline options.  Options handled:
	--delete -d, --dont-delete -l, --all -a, --new -n, --verbose -v,
	--help -h, --rcfile -r <configfile>, --configdir -c <configdir>
	--ignoreconfig -i, --dump
	'''
	#
	global opt_delete_retrieved, opt_retrieve_read, \
		opt_port, opt_host, opt_account, opt_password, opt_dest, \
		opt_verbose, opt_rcfile, opt_configdir, opt_dump, opt_ignoreconfig, \
		opt_showhelp

	error = 0

	# If the environment variable is set, set the default config/data dir
	try:
		opt_configdir = os.environ[ENV_GETMAIL]
	except KeyError:
		opt_configdir = ''

	# If the environment variable is set, get default options from it
	try:
		oldargv = argv
		newargs = [argv[0]]
		if os.environ.has_key (ENV_GETMAILOPTS):
			for a in string.split (os.environ[ENV_GETMAILOPTS]):
				newargs.append (a)
		for a in argv[1 : ]:
			newargs.append (a)
		argv = newargs
	except KeyError:
		pass

	optslist, args = [], []

	opts = 'ac:dhilnv'
	longopts = ['all', 'configdir=', 'delete', 'dont-delete', 'dump', 'help',
				'ignoreconfig', 'new', 'verbose']

	try:
		global optslist, args
		optslist, args = getopt.getopt (argv[1:], opts, longopts)

	except getopt.error, cause:
		stderr ('Error:  %s\n' % cause)
		usage ()
		sys.exit (ERROR)

	for option, value in optslist:
		# parse options
		if option == '--help' or option == '-h':
			opt_showhelp = 1

		elif option == '--delete' or option == '-d':
			delete = 1

		elif option == '--dont-delete' or option == '-l':
			delete = 0

		elif option == '--all' or option == '-a':
			retrieve_read = 1

		elif option == '--new' or option == '-n':
			retrieve_read = 0

		elif option == '--verbose' or option == '-v':
			opt_verbose = 1

		elif option == '--ignoreconfig' or option == '-i':
			opt_ignoreconfig = 1

		elif option == '--rcfile' or option == '-r':
			if not value:
				stderr ('Error:  option --rcfile supplied without value\n')
				error = 1
			else:
				opt_rcfile = value

		elif option == '--configdir' or option == '-c':
			if not value:
				stderr ('Error:  option --configdir supplied without value\n')
				error = 1
			else:
				opt_configdir = value

		elif option == '--dump':
			opt_dump = 1

		else:
			# ? Can't happen
			stderr ('Error:  unrecognized option %s\n' % option)
			error = 1

	#
	if opt_showhelp:
		usage ()
		sys.exit (RC_HELP)

	# Check for data directory
	if not opt_configdir:
		if os.environ.has_key ('HOME'):
			opt_configdir = os.path.join (os.environ['HOME'], '.getmail')
			if not os.path.isdir (opt_configdir):
				opt_configdir = ''
				stderr ('Warning:  configuration/data directory not supplied, '
						'and "%s" environment\n  variable not set.  Cannot '
						'retrieve only new mail.\n' % ENV_GETMAIL)
				opt_retrieve_read = 1

	# Read config file, setting default if necessary
	if not opt_ignoreconfig:
		if not opt_rcfile:
			opt_rcfile = os.path.join (opt_configdir, DEF_RCFILE)
			if opt_verbose:
				print 'Using default .getmailrc file "%s"' % opt_rcfile
		elif opt_verbose:
			print 'Using .getmailrc file "%s"' % opt_rcfile

		read_configfile (opt_rcfile)

	else:
		if opt_verbose:
			print 'Skipping configuration file...'

	# Parse arguments given in user@mailhost[:port],dest[,password] format
	for arg in args:
		arg = string.replace (arg, '\0', '')	# Strip 'poison NUL' bytes
		try:
			userhost, dest, pw = string.split (arg, ',')
			opt_password.append (pw)
		except ValueError:
			try:
				userhost, dest = string.split (arg, ',')
				opt_password.append (None)
			except ValueError:
				stderr ('Error:  argument "%s" not in format \''
						'user@mailhost[:port],dest[,password]\'\n' % arg)

		opt_dest.append (dest)
		opt_account.append (userhost [ : string.rfind (userhost, '@')])

		try:
			opt_host.append (userhost [string.rfind (userhost, '@') + 1
							 : string.rindex (userhost, ':')])
		except ValueError:
			opt_host.append (userhost [string.rfind (userhost, '@') + 1 : ])
		try:
			opt_port.append (int (userhost [string.rindex (userhost, ':') : ]))
		except ValueError:
			opt_port.append (DEF_PORT)

	# Apply delete/don't-delete/retrieve all/retrieve new options to commandline
	# arguments.
	while len (opt_delete_retrieved) < len (opt_account):
		opt_delete_retrieved.append (delete)
	while len (opt_retrieve_read) < len (opt_account):
		opt_retrieve_read.append (retrieve_read)

	# Check mandatory options
	if not opt_host:
		stderr ('Error:  no host(s) supplied\n')
		error = 1
	if not opt_account:
		stderr ('Error:  no account(s) supplied\n')
		error = 1
	if not opt_dest:
		stderr ('Error:  no destination(s) supplied\n')
		error = 1

	# Read password(s) from stdin if not supplied
	if not error:
		for i in range (len (opt_password)):
			if opt_password[i]:  continue
			fd = sys.stdin.fileno ()
			oldattr = termios.tcgetattr(fd)
			newattr = termios.tcgetattr(fd)
			newattr[3] = newattr[3] & ~TERMIOS.ECHO          # lflags
			try:
				termios.tcsetattr (fd, TERMIOS.TCSADRAIN, newattr)
				opt_password[i] = raw_input ('Enter password for %s@%s:  '
								% (opt_account[i], opt_host[i]))

			finally:
				termios.tcsetattr (fd, TERMIOS.TCSADRAIN, oldattr)
			print

	if opt_dump:
		# Debugging aid, dumps current option config.
		print '\ngetmail (%s) version %s debugging dump\n' \
			% (oldargv[0], VERSION)
		if os.environ.has_key (ENV_GETMAIL):
			print 'ENV_GETMAIL = "%s", contains "%s"' \
				% (ENV_GETMAIL, os.environ[ENV_GETMAIL])
		if os.environ.has_key (ENV_GETMAILOPTS):
			print 'ENV_GETMAILOPTS = "%s", contains "%s"' \
				% (ENV_GETMAILOPTS, os.environ[ENV_GETMAILOPTS])
		print 'In-script defaults:\n' \
			'  DEF_PORT     = "%s"\n' \
			'  DEF_DELETE   = "%s"\n' \
			'  DEF_READ_ALL = "%s"\n' \
			'  DEF_RCFILE   = "%s"' \
			% (DEF_PORT, DEF_DELETE, DEF_READ_ALL, DEF_RCFILE)
		print 'Commandline:\n  ',
		for a in oldargv:
			print '%s' % a,
		print
		print 'Option status:\n' \
			'  opt_verbose = "%s"\n' \
			'  opt_rcfile = "%s"\n' \
			'  opt_configdir = "%s"\n' \
			% (opt_verbose, opt_rcfile, opt_configdir)
		print 'Accounts:'
		for i in range (len (opt_account)):
			print '  %s,%s:%s,%s delete=%s readall=%s' \
				% (opt_account[i], opt_host[i], opt_port[i], opt_dest[i],
				   opt_delete_retrieved[i], opt_retrieve_read[i])
		sys.exit (RC_DEBUG)

	if error:
		usage ()
		sys.exit (ERROR)

	return


#######################################
if __name__ == '__main__':
	main ()
