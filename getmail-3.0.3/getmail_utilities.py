#!/usr/bin/python

import string
import sys
import time
import signal
import stat
import glob
import traceback
import getopt
import getpass
from types import *

from getmail_constants import *
from getmail_classes import *
from getmail_defaults import *
import ConfParser

# For trace output
newline = 1

#
# Utility functions
#

#######################################
def log (level, msg, opts):
    global newline
    if level < opts['log_level']:
        return
    if level == TRACE:
        if not newline:
            msg = '\n' + msg
        if not msg:  msg = '\n'
        trace = traceback.extract_stack ()[-3]
        msg = '%s() [%s:%i] %s' % (trace[FUNCNAME],
            os.path.split (trace[FILENAME])[-1],
            trace[LINENO], msg)
    msg = res['percent'].sub ('%%', msg) % opts
    if level >= WARN:
        sys.stderr.write (msg)
        sys.stderr.flush ()
    else:
        sys.stdout.write (msg)
        sys.stdout.flush ()

    if msg and msg[-1] == '\n':
        newline = 1
    else:
        newline = 0

#######################################
def pop3_unescape (msg):
    '''Do leading dot replacement in retrieved message.
    '''
    return res['leadingdot'].sub ('.', msg)

#######################################
def timestamp ():
    '''Return the current time in a standard format.'''
    t = time.gmtime (time.time ())
    return time.strftime ('%d %b %Y %H:%M:%S -0000', t)

#######################################
def format_header (name, line):
    '''Take a long line and return rfc822-style multiline header.
    '''
    header = ''
    # Ensure 'line' is formatted as a single long line, and add header name.
    line = string.strip (name) + ': ' + res['eol'].sub (' ', string.rstrip (line))
    # Split into lines of maximum 78 characters long plus newline, if
    # possible.  A long line may result if no space characters are present.
    while line and len (line) > 78:
        i = string.rfind (line, ' ', 0, 78)
        if i == -1:
            # No space in first 78 characters, try a long line
            i = string.rfind (line, ' ')
            if i == -1:
                # No space at all
                break
        if header:  header = header + '\n  '
        header = header + line[:i]
        line = string.lstrip (line[i:])
    if header:
        header = header + '\n  '
    if line:
        header = header + string.lstrip (line) + '\n'
    return header

###################################
def alarm_handler (dummy, unused):
    '''Handle an alarm (should never happen).'''
    raise IOError, 'Maildir delivery timeout'

#######################################
def deliver_maildir (maildirpath, msg, hostname, deliverycount=None):
    '''Reliably deliver a mail message into a Maildir.  Uses Dan Bernstein's
    documented rules for maildir delivery, and the updated naming convention
    for new files (modern delivery identifiers).  See
    http://cr.yp.to/proto/maildir.html for details.
    '''
    # Set a 24-hour alarm for this delivery
    signal.signal (signal.SIGALRM, alarm_handler)
    signal.alarm (24 * 60 * 60)

    info = {
        'deliverycount' : deliverycount,
        'hostname' : string.replace (string.replace (hostname, '/', '\\057'), ':', '\\072'),
        'pid' : os.getpid (),
    }
    dir_tmp = os.path.join (maildirpath, 'tmp')
    dir_new = os.path.join (maildirpath, 'new')
    if not (os.path.isdir (maildirpath) and os.path.isdir (dir_tmp) and os.path.isdir (dir_new)):
        raise getmailDeliveryException, 'not a Maildir (%s)' % maildirpath

    got_file = 0
    for unused in range (3):
        t = time.time ()
        info['secs'] = int (t)
        info['usecs'] = int ((t - int (t)) * 1000000)
        if deliverycount is None:
            filename = '%(secs)s.M%(usecs)dP%(pid)s.%(hostname)s' % info
        else:
            filename = '%(secs)s.M%(usecs)dP%(pid)sQ%(deliverycount)s.%(hostname)s' % info
        fname_tmp = os.path.join (dir_tmp, filename)
        fname_new = os.path.join (dir_new, filename)
    
        # File must not already exist
        if os.path.exists (fname_tmp):
            # djb says sleep two seconds and try again
            time.sleep (2)
            continue

        # Be generous and check cur/file[:...] just in case
        curpat = os.path.join (maildirpath, 'cur', filename) + ':*'
        collision = glob.glob (curpat)
        if collision:
            # There is a message in maildir/cur/ which could be clobbered by
            # a dumb MUA, and which shouldn't be there.  Abort.
            raise getmailDeliveryException, 'collision with %s' % collision

        # Found an unused filename
        got_file = 1
        break

    if not got_file:        
        signal.alarm (0)
        raise getmailDeliveryException, 'failed to allocate file in maildir'

    # Get user & group of maildir
    s_maildir = os.stat (maildirpath)
    uid = s_maildir[stat.ST_UID]
    gid = s_maildir[stat.ST_GID]

    # Open file to write
    try:
        f = open (fname_tmp, 'wb')
        os.chmod (fname_tmp, 0600)
        try:
            # If root, change the message to be owned by the Maildir
            # owner
            os.chown (fname_tmp, uid, gid)
        except OSError:
            # Not running as root, can't chown file
            pass
        f.write (msg)
        f.flush ()
        os.fsync (f.fileno())
        f.close ()

    except IOError:
        signal.alarm (0)
        raise getmailDeliveryException, 'failure writing file ' + fname_tmp

    # Move message file from Maildir/tmp to Maildir/new
    try:
        os.link (fname_tmp, fname_new)
        os.unlink (fname_tmp)

    except OSError:
        signal.alarm (0)
        try:
            os.unlink (fname_tmp)
        except:
            pass
        raise getmailDeliveryException, 'failure renaming "%s" to "%s"' \
               % (fname_tmp, fname_new)

    # Delivery done

    # Cancel alarm
    signal.alarm (0)
    signal.signal (signal.SIGALRM, signal.SIG_DFL)

    return 'Maildir "%s"' % maildirpath

#######################################
def address_no_brackets (address):
    address = string.strip (address)
    if address[0] == '<' and address[-1] == '>':
        return address[1:-1]
    return address

#######################################
def envelope_recipient (config, message):
    '''Find the envelope recipient address for this message.'''
    # User configured a header field where the envelope recipient
    # address is recorded by the MTA on the POP3 server.  Use it
    # and only it.
    hdrname = config['recipient_header']
    try:
        hdrname, hdrnum = string.split (hdrname, ':', 1)
        hdrnum = int (hdrnum)
        if hdrnum < 1:
            raise ValueError
    except ValueError:
        # No name:num split, use first
        hdrnum = 1
    
    return address_no_brackets (message.get_specific_header (hdrname, hdrnum))

#######################################
def blurb ():
    print 'getmail - POP3 mail retriever with reliable Maildir and command delivery.'
    print

#######################################
def version (v):
    print 'getmail version %s ' % v
    print
    print 'Copyright (C) 2001 Charles Cazabon'
    print
    print 'Licensed under the GNU General Public License version 2.  See the file'
    print 'COPYING for details.'
    print
    print 'Written by Charles Cazabon <getmail @ discworld.dyndns.org>'

#######################################
def dump_config (cmdopts, mail_configs):
    print 'Current configuration:'
    print
    print '  Commandline:'
    print '    ' + string.join (sys.argv)
    print
    print '  Defaults after commandline options:'
    keys = cmdopts.keys ()
    keys.sort ()
    for key in keys:
        print '    %s:  %s' % (key, cmdopts[key])
    print
    print '  Account configurations:'
    for (account, locals) in mail_configs:
        print '    Account:'
        keys = account.keys ()
        keys.sort ()
        for key in keys:
            if key == 'password':
                print '      %s:  %s' % (key, '*')
            else:
                print '      %s:  %s' % (key, account[key])
        print '      Local Users/Deliveries:'
        locals.sort ()
        for (re_s, target) in locals:
            print '        %s:  %s' % (re_s or 'postmaster', target)
        print


#######################################
def help (ec=exitcodes['ERROR']):
    blurb ()
    print 'Usage:  getmail [OPTION] ...'
    print
    print 'Options:'
    print '  -h or --help                      display brief usage information and exit'
    print '  -V or --version                   display version information and exit'
    print '  -g or --getmaildir <dir>          use <dir> for getmail data directory'
    print '                                      (default:  %(getmaildir)s)' \
        % defs
    print '  -r or --rcfile <filename>         use <filename> for getmailrc file'
    print '                                      (default:  <getmaildir>/%(rcfilename)s)' \
        % defs
    print '  -t or --timeout <secs>            set socket timeout to <secs> seconds'
    print '                                      (default:  %(timeout)i seconds)' \
        % defs
    print '  --dump                            dump configuration and quit (debugging)'
    print '  --trace                           debugging output to stdout'
    print
    print 'The following options override those specified in any getmailrc file.'
    print 'If contradictory options are specified (i.e. --delete and --dont-delete),'
    print 'the last one one is used.'
    print
    print '  -d or --delete                    delete mail after retrieving'
    print '  -l or --dont-delete               leave mail on server after retrieving'
    if defs['delete']:
        print '                                      (default:  delete)'
    else:
        print '                                      (default:  leave on server)'
    print '  -a or --all                       retrieve all messages'
    print '  -n or --new                       retrieve only unread messages'
    if defs['readall']:
        print '                                      (default:  all messages)'
    else:
        print '                                      (default:  new messages)'
    print '  -v or --verbose                   be verbose during operation'
    print '  -q or --quiet                     be quiet during operation'
    if defs['log_level'] < WARN:
        print '                                      (default:  verbose)'
    else:
        print '                                      (default:  quiet)'
    print '  -m or --message-log <file>        log retrieval info to <file>'
    print
    sys.exit (ec)

#######################################
def read_configfile (filename, default_config):
    '''Read in configuration file and extract configuration information.
    '''
    # Resulting list of configurations
    configs = []

    if not os.path.isfile (filename):
        raise getmailConfigException, 'no such file "%s"' % filename

    s = os.stat (filename)
    mode = stat.S_IMODE (s[stat.ST_MODE])
    if (mode & 022):
        raise getmailConfigException, 'file is group- or world-writable'

    # Instantiate configuration file parser
    conf = ConfParser.ConfParser (defs)

    try:
        conf.read (filename)
        sections = conf.sections ()

        # Read options from config file
        options = default_config.copy ()
        for key in conf.options ('default'):
            if key in intoptions:
                options[key] = conf.getint ('default', key)
                if key == 'verbose':
                    if options[key]:
                        options['log_level'] = INFO
                    else:
                        options['log_level'] = WARN
            elif key in stringoptions:
                options[key] = conf.get ('default', key)
            elif key != '__name__':
                log (TRACE, 'unrecognized option "%s" in section "default"\n' % key, options)

        # Remainder of sections are accounts to retrieve mail from.
        for section in sections:
            account, locals = options.copy (), []

            # Read required parameters
            for item in ('server', 'port', 'username'):
                try:
                    if item == 'port':
                        account[item] = conf.getint (section, item)
                    else:
                        account[item] = conf.get (section, item)
                except ConfParser.NoOptionError, txt:
                    raise getmailConfigException, 'section [%s] missing required option (%s)' % (section, item)

            # Read in password if supplied; otherwise prompt for it.
            try:
                account['password'] = conf.get (section, 'password')
            except ConfParser.NoOptionError, txt:
                account['password'] = getpass.getpass (
                    'Enter password for %(username)s@%(server)s:%(port)s :  '
                    % account)

            for key in conf.options (section):
                if key in ('server', 'port', 'username', 'password'):
                    continue
                if key in intoptions:
                    account[key] = conf.getint (section, key)
                    if key == 'verbose':
                        if account[key]:
                            account['log_level'] = INFO
                        else:
                            account['log_level'] = WARN
                elif key in stringoptions:
                    account[key] = conf.get (section, key)
                elif key != '__name__':
                    log (TRACE, 'unrecognized option "%s" in section "%s"\n' % (key, section), options)

            # Read local user regex strings and delivery targets
            if not account.has_key ('postmaster'):
                raise getmailConfigException, 'section [%s] missing required option (postmaster)' % section

            try:
                conflocals = conf.get (section, 'local')
            except ConfParser.NoOptionError:
                conflocals = []
            if type (conflocals) != ListType:
                conflocals = [conflocals]
            for _local in conflocals:
                try:
                    recip_re, target = string.split (_local, ',', 1)
                except ValueError, txt:
                    raise getmailConfigException, 'section [%s] syntax error in local (%s)' % (section, _local)
                locals.append ( (recip_re, target) )

            configs.append ( (account.copy(), locals) )

    except ConfParser.ConfParserException, txt:
        log (FATAL, '\nError:  error in getmailrc file (%s)\n' % txt, default_config)
        sys.exit (exitcodes['ERROR'])

    return options, configs

#######################################
def parse_options (args, v):
    o = {}
    shortopts = 'adg:hlm:nqr:t:vV'
    longopts = ['all', 'delete', 'dont-delete', 'dump', 'getmaildir=', 'help',
                'message-log=', 'new', 'quiet', 'rcfile=', 'timeout=',
                'trace', 'verbose', 'version']
    try:
        opts, args = getopt.getopt (args, shortopts, longopts)

    except getopt.error, cause:
        log (FATAL, '\nError:  failed to parse options (%s)\n' % cause, defs)
        help ()

    if args:
        for arg in args:
            log (FATAL, 'Error:  unknown argument (%s)\n' % arg, defs)
        help ()

    for option, value in opts:
        if option == '--help' or option == '-h':
            o['help'] = 1
        elif option == '--delete' or option == '-d':
            o['delete'] = 1
        elif option == '--dont-delete' or option == '-l':
            o['delete'] = 0
        elif option == '--all' or option == '-a':
            o['readall'] = 1
        elif option == '--new' or option == '-n':
            o['readall'] = 0
        elif option == '--verbose' or option == '-v':
            o['log_level'] = INFO
        elif option == '--trace':
            o['log_level'] = TRACE
        elif option == '--quiet' or option == '-q':
            o['log_level'] = WARN
        elif option == '--message-log' or option == '-m':
            o['message_log'] = value
        elif option == '--timeout' or option == '-t':
            try:
                o['timeout'] = int (value)
            except:
                log (FATAL, '\nError:  invalid integer value for timeout (%s)\n' % value, defs)
                help ()
        elif option == '--version' or option == '-V':
            version (v)
            sys.exit (0)
        elif option == '--rcfile' or option == '-r':
            o['rcfilename'] = value
        elif option == '--getmaildir' or option == '-g':
            o['getmaildir'] = value
        elif option == '--dump':
            o['dump'] = 1
        else:
            # ? Can't happen
            log (FATAL, '\nError:  unknown option (%s)\n' % option, defs)
            help ()

    return o
