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

VERSION = '1.11'

#
# Imports
#

import sys, os, string, time, socket, poplib, getopt, fcntl, \
    rfc822, cStringIO, pwd, getpass
from types import *


#
# Defaults
#
# These can all be overridden with commandline arguments.
#

DEF_PORT =              110             # Normal POP3 port
DEF_DELETE =            0               # Delete mail after retrieving (0, 1)
DEF_READ_ALL =          1               # Retrieve all mail (1) or just new (0)
DEF_RCFILE =            '.getmailrc'    # Default.getmailrc filename
ENV_GETMAIL =           'GETMAIL'       # Env. variable to get configuration/
                                        #  data directory name from
ENV_GETMAILOPTS =       'GETMAILOPTS'   # Default options can be put in this
                                        #  environment variable


#
# Options
#

opt_host =              []
opt_port =              []
opt_account =           []
opt_password =          []
opt_delete_retrieved =  []
opt_retrieve_read =     []
opt_dest =              []
opt_accounttype =       []
opt_reciplist =         []
opt_verbose =           0
opt_rcfile =            None
opt_configdir =         None
opt_dump =              0
opt_ignoreconfig =      0
opt_showhelp =          0


#
# Data
#

# Constants
true, false             = (('true', 'yes', '1', 't', 'y'),
                            ('false', 'no', '0', 'f', 'n'))
mailbox, domainbox      = 0, 1
DEST, UID, GID, ADDR    = 0, 1, 2, 3

CR              = '\r'
LF              = '\n'
deliverycount   = 0
argv            = sys.argv
stderr          = sys.stderr.write

# Exit codes
OK, ERROR       = (0, -1)
RC_NEWMAIL      = 0
RC_NOMAIL       = 1
RC_DEBUG        = 100
RC_HELP         = 101


# Headers to parse for recipient addresses
RECIPIENT_HEADERS = (
    ('envelope-to', ),
    ('x-envelope-to', ),
    ('resent-to', 'resent-cc', 'resent-bcc'),
    ('to', 'cc', 'bcc'),
    ('received', )
    )

# Parser exceptions

NoOptionError = 'NoOptionError'
NoSectionError = 'NoSectionError'
BadConfigFileError = 'BadConfigFileError'
DuplicateSectionError = 'DuplicateSectionError'
FileIOError = 'FileIOError'
ParsingError = 'ParsingError'                   # Not currently used
DefaultsError = 'DefaultsError'


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
            msg = pop3_unescape (msg)
            delivered = 0
            if opt_accounttype[i] == domainbox:
                # Domain mailbox
                recips = domainbox_find_recipients (msg)
                for recip in recips:
                    for j in range (len (opt_reciplist[i])):
                        if recip == opt_reciplist[i][j][ADDR]:
                            try:
                                rc = deliver_msg (opt_reciplist[i][j][DEST],
                                                  msg,
                                                  uid=opt_reciplist[i][j][UID],
                                                  gid=opt_reciplist[i][j][GID])
                                output ('Delivered message for %s to %s'
                                        % (opt_reciplist[i][j][ADDR], rc))
                                delivered = 1

                            except:
                                tmpmail_save (msg)

            if not delivered:
                # No match in domain mailbox, or this is a regular mailbox
                # Do default delivery.
                try:
                    rc = deliver_msg (opt_dest[i][DEST], msg,
                                      uid=opt_dest[i][UID],
                                      gid=opt_dest[i][GID])
                    output ('Delivered message to default %s' % rc)

                except:
                    tmpmail_save (msg)

    if deliverycount:   sys.exit (RC_NEWMAIL)
    else:               sys.exit (RC_NOMAIL)


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
        output ('%s:  POP3 session initiated on port %s for "%s"'
                % (shorthost, port, account))
        rc = session.getwelcome ()
        output ('%s:  POP3 greeting:  %s' % (shorthost, rc))
    except poplib.error_proto, response:
        stderr ('%s:  returned greeting "%s"\n' % (shorthost, response))
        return []
    except socket.error, txt:
        stderr ('Exception connecting to %s:  %s\n' % (host, txt))
        return []

    try:
        rc = session.user (account)
        output ('%s:  POP3 user reponse:  %s' % (shorthost, rc))
        rc = session.pass_ (password)
        output ('%s:  POP3 password response:  %s' % (shorthost, rc))
    except poplib.error_proto, response:
        stderr ('%s:  returned "%s" during login\n' % (shorthost, response))
        return []

    # Retrieve message list
    try:
        list = session.list ()
        rc = list[0]
        msglist = list[1]
        output ('%s:  POP3 list response:  %s' % (shorthost, rc))

    except poplib.error_proto, response:
        stderr ('Error retrieving message list, skipping ...\n')

    try:
        for item in msglist:
            if type (item) == IntType:
                # No more messages; POP3.list() returns a final int
                output ('%s:  finished retrieving messages' % shorthost)
                break
            msgnum, msglen = string.split (item)
            output ('  msg %i : len %i ...' % (int (msgnum), int (msglen)),
                    nl=0)

            rc = session.uidl (msgnum)
            uidl = string.strip (string.split (rc, ' ', 2)[2])

            if getall or ('%s\n' % uidl) not in oldmail:
                result = session.retr (int (msgnum))
                rc = result[0]
                msg = result[1]

                messages.append (msg)
                retrieved = retrieved + 1

                output ('retrieved', nl=0)
                if delete:
                    rc = session.dele (int (msgnum))
                    output ('... deleted', nl=0)
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
                        output ('... wrote to oldmail file', nl=0)
                    except IOError:
                        stderr ('\nError:  failed writing oldmail file\n')

            else:
                output ('previously retrieved, skipping ...', nl=0)

            output ('')

    except poplib.error_proto, response:
        stderr ('%s:  exception "%s" during retrieval, resetting...\n'
                % (shorthost, response))
        session.rset ()

    output ('%s:  POP3 session completed for "%s"' % (shorthost, account))

    session.quit ()

    output ('%s:  POP3 connection closed\n%i messages retrieved\n'
         % (shorthost, retrieved))

    return messages


#######################################
def domainbox_find_recipients (message):
    '''Examine a mail message retrieved from a domain (or 'multidrop') mailbox
    and figure out who the envelope recipient was.  Non-trivial, as this
    information is not preserved in a standard way by MTAs/MDAs.
    '''
    recipients = []
    f = cStringIO.StringIO ()

    while 1:
        t = string.strip (message[0])
        if not t or t[0 : 5] == 'From ':
            # Get rid of blank or LF-only lines, or mbox-style 'From ' lines
            del message[0]
        else:
            break

    if string.find (message[0], 'Delivered-To: ') == 0:
        # Only use Deliver-To: if it is the first real header line
        f.writelines (message[0])
        f.seek (0)
        m = rfc822.Message (f)
        addrlist = m.getaddrlist ('delivered-to')
        if addrlist:
            for item in addrlist:
                recipients.append (item [1])    # Get email address

        else:
            # ??? Can't happen
            stderr ('Error:  failure parsing Delivered-To: header\n')

    f.truncate (0)
    f.writelines (message)
    f.seek (0)
    m = rfc822.Message (f)

    # Look for recipients in particular headers, one group at a time.  Quit
    # after first group which returns a match.  Note all headers in a given
    # group will be searched or not; it does not quit partway through a group.
    for group in RECIPIENT_HEADERS:
        if not recipients:
            for header in group:
                addrlist = m.getaddrlist (header)
                for item in addrlist:
                    recipients.append (item [1])    # Get email address

    f.close ()

    # Force lowercase
    recipients = map (string.lower, recipients)

    return recipients


#######################################
def deliver_msg (dest, message, uid=None, gid=None):
    '''Determine the type of destination and dispatch to appropriate delivery
    routine.  Currently understands Maildirs and assumes any regular file is
    an mbox file.
    '''
    mdir_new = os.path.join (dest, 'new')
    mdir_tmp = os.path.join (dest, 'tmp')

    if os.path.isdir (mdir_new) and os.path.isdir (mdir_tmp):
        maildirdeliver (dest, message, uid, gid)
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
def maildirdeliver (maildir, message, uid=None, gid=None):
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

    # Change ownership if necessary
    if uid and gid:
        try:
            os.chown (fname_tmp, uid, gid)
        except:
            stderr ('Failed changing owner of message to %d:%d (user "%s")\n'
                % (uid, gid, pwd.getpwuid (uid)[0]))

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
def tmpmail_save (message):
    '''After a failed delivery, save in a temporary file to preserve the
    message.'''
    stderr ('Error encountered during delivery\n')
    t = 'tmpmail.%s:%s:%s' % (time.time (), os.getpid (), len (message))
    f = open (t, 'w')
    f.writelines (message)
    f.close ()
    stderr ('Message saved to temporary file "%s"\n' % t)
    time.sleep (1)


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
        f.seek (0, 2)                   # Seek to end
        f.write (fromline)
        esc_from = 0
        for line in message:
            if esc_from and line[0 : 5] == 'From ':
                line = '>%s' % line
            f.write (line)
            if line == '\n':    esc_from = 1
            else:               esc_from = 0
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
    if DEF_DELETE:          def_del =       '(default)'
    else:                   def_dontdel =   '(default)'
    if DEF_READ_ALL:        def_readall =   '(default)'
    else:                   def_readnew =   '(default)'

    stderr ('\n'
    'Usage:  %s [options] [user@mailhost[:port],destination[,password]] [...]\n'
    'Options:\n'
    '  -a or --all                retrieve all messages                %s\n'
    '  -n or --new                retrieve unread messages             %s\n'
    '  -d or --delete             delete mail after retrieving         %s\n'
    '  -l or --dont-delete        leave mail on server                 %s\n'
    '  -v or --verbose            output more information\n'
    '  -q or --quiet              output less information\n'
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
        % (me, def_readall, def_readnew, def_del, def_dontdel, ENV_GETMAIL,
           DEF_PORT))
    return


#######################################
def read_configfile (file):
    '''Read in configuration file.
    '''
    #
    global opt_delete_retrieved, opt_retrieve_read, \
        opt_port, opt_host, opt_account, opt_password, opt_dest, \
        opt_verbose, opt_accounttype, opt_reciplist

    recips = []
    defaults = { 'port'         : '%s' % DEF_PORT,
                 'delete'       : '%s' % DEF_DELETE,
                 'readall'      : '%s' % DEF_READ_ALL,
                 'password'     : '',
                 'type'         : 'mailbox'
               }

    ignore = ('account', 'host', 'port', 'destination', 'password', 'delete',
              'readall', 'type', 'default', '__section__')

    if not os.path.isfile (file):
        return

    conf = ConfParser (defaults)

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
            mtype = string.lower (conf.get (section, 'type'))

            # Strip 'poison NUL' bytes just in case
            account, host, pw, dest = map (lambda x:
                                           string.replace (x, '\0', ''),
                                           (account, host, pw, dest))
            opt_account.append (account)
            opt_host.append (host)
            opt_port.append (port)
            opt_password.append (pw)

            if dele in true:  opt_delete_retrieved.append (1)
            else:             opt_delete_retrieved.append (0)
            if rall in true:  opt_retrieve_read.append (1)
            else:             opt_retrieve_read.append (0)

            # Destination
            try:
                dest, user = string.split (dest, ':')
                pwd_item = pwd.getpwnam (user)
                uid, gid = pwd_item[2], pwd_item[3]
                opt_dest.append ( (dest, uid, gid) )

            except ValueError:
                # Wrong number of items in option value
                opt_dest.append ( (dest, None, None) )

            except KeyError:
                stderr ('Error:  no such user in /etc/passwd ("%s")\n'
                        '  for destination "%s"\n'
                        '  POP3 account "%s@%s:%d"\n'
                    % (user, dest, opt_account[-1], opt_host[-1], opt_port[-1]))
                opt_dest.append ( (dest, None, None) )

            if mtype == 'domainbox':
                opt_accounttype.append (domainbox)
                # Get list of addresses from remainder of options
                for option in conf.options (section):
                    if option in ignore:
                        continue
                    # Not a recognized option, must be
                    # 'email=destination[:uid:gid]'
                    val = conf.get (section, option)
                    try:
                        dest, user = string.split (val, ':')
                        pwd_item = pwd.getpwnam (user)
                        uid, gid = pwd_item[2], pwd_item[3]
                        recips.append ( (dest, uid, gid, string.lower (option)) )

                    except ValueError:
                        # Wrong number of items in option value
                        recips.append ( (val, None, None, string.lower (option)) )

                    except KeyError:
                        stderr ('Error:  no such user in /etc/passwd ("%s")\n'
                                '  for destination "%s"\n'
                                '  POP3 account "%s@%s:%d"\n'
                            % (user, dest, opt_account[-1], opt_host[-1],
                               opt_port[-1]))
                        recips.append ( (dest, None, None, string.lower (option)) )

                opt_reciplist.append (recips)
            else:
                opt_accounttype.append (mailbox)
                opt_reciplist.append (None)

    # User configuration errors
    except NoOptionError, cause:
        stderr ('Error:  required option missing in configuration file "%s"\n'
                '  (%s)\n' % (file, cause))
        sys.exit (ERROR)

    except BadConfigFileError, cause:
        stderr ('Error:  file "%s" does not appear to be a valid getmail '
                'configuration file\n  (%s)\n' % (file, cause))
        sys.exit (ERROR)

    except DuplicateSectionError, cause:
        stderr ('Error:  duplicated section name in configuration file "%s"\n'
                '  (%s)\n' % (file, cause))
        sys.exit (ERROR)

    except FileIOError, cause:
        stderr ('Warning:  failure reading configuration file "%s"\n'
                '  (%s)\n' % (file, cause))
        sys.exit (ERROR)

    # Bugs in getmail
    #except getmailparser.ParsingError, cause:
    #   stderr ('Error:  internal error parsing configuration file\n  (%s)\n'
    #           % cause)
    #   sys.exit (ERROR)

    except DefaultsError, cause:
        stderr ('Error:  defaults not a dictionary\n  (%s)\n' % cause)
        sys.exit (ERROR)

    except NoSectionError, cause:
        stderr ('Error:  no such section in file "%s"\n  (%s)\n'
                % (file, cause))
        sys.exit (ERROR)

    return


#######################################
def output (msg, nl=1, force=0):
    if not (opt_verbose or force):  return
    sys.stdout.write (msg)
    if nl:  sys.stdout.write ('\n')
    sys.stdout.flush ()


#######################################
def parse_options (argv):
    '''Parse commandline options.  Options handled:
    --delete -d, --dont-delete -l, --all -a, --new -n, --verbose -v,
    --help -h, --rcfile -r <configfile>, --configdir -c <configdir>
    --ignoreconfig -i, --dump, --quiet -q
    '''
    #
    global opt_delete_retrieved, opt_retrieve_read, \
        opt_port, opt_host, opt_account, opt_password, opt_dest, \
        opt_verbose, opt_rcfile, opt_configdir, opt_dump, opt_ignoreconfig, \
        opt_showhelp, opt_accounttype, opt_reciplist

    delete, retrieve_read = DEF_DELETE, DEF_READ_ALL
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

    opts = 'ac:dhilnqr:v'
    longopts = ['all', 'configdir=', 'delete', 'dont-delete', 'dump', 'help',
                'ignoreconfig', 'new', 'quiet', 'rcfile=', 'verbose']

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

        elif option == '--quiet' or option == '-q':
            opt_verbose = 0

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
                retrieve_read = 1

    # Read config file, setting default if necessary
    if not opt_ignoreconfig:
        if not opt_rcfile:
            opt_rcfile = os.path.join (opt_configdir, DEF_RCFILE)
            output ('Using default .getmailrc file "%s"' % opt_rcfile)
        else:
            output ('Using .getmailrc file "%s"' % opt_rcfile)

        read_configfile (opt_rcfile)

    else:
        output ('Skipping configuration file...')

    # Parse arguments given in user@mailhost[:port],dest[,password] format
    for arg in args:
        arg = string.replace (arg, '\0', '')    # Strip 'poison NUL' bytes
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

        opt_dest.append ( (dest, None, None) )
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

    # account type always 'mailbox' for commandline email accounts
    while len (opt_accounttype) < len (opt_account):
        opt_accounttype.append (mailbox)
    while len (opt_reciplist) < len (opt_account):
        opt_reciplist.append (None)

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
            opt_password[i] = getpass.getpass ('Enter password for %s@%s:  '
                                               % (opt_account[i], opt_host[i]))

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
            print '  %s,%s:%s,%s,"%s" delete=%s readall=%s' \
                % (opt_account[i], opt_host[i], opt_port[i], opt_dest[i],
                   opt_password[i], opt_delete_retrieved[i],
                   opt_retrieve_read[i])
        sys.exit (RC_DEBUG)

    if error:
        usage ()
        sys.exit (ERROR)

    return


#######################################
class ConfParser:
    '''Class to parse a configuration file without all the limitations in
    ConfigParser.py, but without the dictionary formatting options either.
    '''
    #######################################
    def __init__ (self, defaults = {}):
        'Constructor..'

        self.__rawdata = []
        self.__data = []
        self.__sects = []
        self.__opts = []
        self.__defs = {}

        try:
            for key in defaults.keys ():
                self.__defs[key] = defaults[key]

        except AttributeError:
            raise DefaultsError, 'defaults "%s" not a dictionary' % defaults


    #######################################
    def read (self, filename):
        'Read configuration file.'
        try:
            f = open (filename, 'r')
            self.__rawdata = f.readlines ()
            f.close ()

        except IOError:
            raise FileIOError, 'error reading configuration file "%s"' \
                % filename

        n = 0
        for line in self.__rawdata:
            try:
                line = line [ : string.index (line, '#')]
            except ValueError:
                pass
            line = string.strip (line)
            if line:
                self.__data.append ( (n, line) )
            n = n + 1

        self.__parse ()
        return self


    #######################################
    def __parse (self):
        'Parse the read-in configuration file.'
        in_section = 0
        for (lineno, line) in self.__data:
            if line[0] == '[':
                in_section = 1
                try:
                    sect_name = string.lower (line [1:string.index (line, ']')])

                except ValueError:
                    raise BadConfigFileError, \
                        'malformed section title in line %i:  "%s"' \
                        % (lineno, line)

                if sect_name in self.__sects:
                    raise DuplicateSectionError, \
                        'duplicate section "%s" found at line %i' \
                        % (sect_name, lineno)

                self.__sects.append (sect_name)

                self.__opts.append ({'__section__' : sect_name})

                # Insert defaults
                for key in self.__defs.keys ():
                    self.__opts[-1][key] = self.__defs[key]

                continue

            if in_section:
                optname = string.strip (line [ : string.find (line, '=') ])
                try:
                    optval = string.strip (line [string.index (line, '=') + 1:])
                    if (optval[0] == optval[-1] == "'"
                        or optval[0] == optval[-1] == '"'):
                        optval = optval[1:-1]
                except ValueError:
                    optval = ''
                self.__opts [-1][optname] = optval

        return


    #######################################
    def sections (self):
        return self.__sects


    #######################################
    def options (self, section):
        'Return list of options in section.'
        try:
            s = self.__sects.index (string.lower (section))

        except ValueError:
            raise NoSectionError, 'file has no section "%s"' % section

        return self.__opts[s].keys ()


    #######################################
    def get (self, section, option):
        'Return an option value.'
        try:
            s = self.__sects.index (string.lower (section))
        except ValueError:
            raise NoSectionError, 'file has no section "%s"' % section

        if not self.__opts[s].has_key (option):
            raise NoOptionError, 'section "%s" has no option "%s"' \
                % (section, option)

        return self.__opts[s][option]


#######################################
if __name__ == '__main__':
    main ()
