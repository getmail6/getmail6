# docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
# Please refer to the git history regarding who changed what and when in this file.

'''Utility classes and functions for getmail.
'''

__all__ = [
    'address_no_brackets',
    'change_usergroup',
    'change_uidgid',
    'format_header',
    'check_ssl_key_and_cert',
    'check_ca_certs',
    'check_ssl_version',
    'check_ssl_fingerprints',
    'check_ssl_ciphers',
    'deliver_maildir',
    'eval_bool',
    'expand_user_vars',
    'is_maildir',
    'localhostname',
    'lock_file',
    'logfile',
    'mbox_from_escape',
    'safe_open',
    'unlock_file',
    'gid_of_uid',
    'uid_of_user',
    'updatefile',
    'get_password',
    'tostr',
    'unicode',
]


import os
import os.path
import socket
import signal
import stat
import time
import glob
import re
import fcntl
import pwd
import grp
import getpass
import subprocess
import sys

if sys.version_info.major > 2:
    unicode = str
    tostr = lambda lts: lts.decode()
else:
    unicode = unicode
    tostr = lambda lts: lts

try:
    import ssl
except ImportError:
    ssl = None
try:
    import hashlib
except ImportError:
    hashlib = None

# Optional gnome-keyring integration
try:
    import gnomekeyring
    # And test to see if it's actually available
    if not gnomekeyring.is_available():
        gnomekeyring = None
except ImportError:
    gnomekeyring = None
# Optional Python keyring integration
try:
    import keyring
except ImportError:
    keyring = None

from getmailcore.exceptions import *

logtimeformat = '%Y-%m-%d %H:%M:%S'
_bool_values = {
    'true'  : True,
    'yes'   : True,
    'on'    : True,
    '1'     : True,
    'false' : False,
    'no'    : False,
    'off'   : False,
    '0'     : False
}
osx_keychain_binary = '/usr/bin/security'


#######################################
def lock_file(file, locktype):
    '''Do file locking.'''
    assert locktype in ('lockf', 'flock'), 'unknown lock type %s' % locktype
    if locktype == 'lockf':
        fcntl.lockf(file, fcntl.LOCK_EX)
    elif locktype == 'flock':
        fcntl.flock(file, fcntl.LOCK_EX)

#######################################
def unlock_file(file, locktype):
    '''Do file unlocking.'''
    assert locktype in ('lockf', 'flock'), 'unknown lock type %s' % locktype
    if locktype == 'lockf':
        fcntl.lockf(file, fcntl.LOCK_UN)
    elif locktype == 'flock':
        fcntl.flock(file, fcntl.LOCK_UN)

#######################################
def safe_open(path, mode, permissions=0o600):
    '''Open a file path safely.
    '''
    if os.name != 'posix':
        return open(path, mode)
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, permissions)
        file = os.fdopen(fd, mode)
    except OSError as o:
        raise getmailDeliveryError('failure opening %s (%s)' % (path, o))
    return file

#######################################
class updatefile(object):
    '''A class for atomically updating files.

    A new, temporary file is created when this class is instantiated. When the
    object's close() method is called, the file is synced to disk and atomically
    renamed to replace the original file.  close() is automatically called when
    the object is deleted.
    '''
    def __init__(self, filename):
        self.closed = False
        self.filename = filename
        self.tmpname = filename + '.tmp.%d' % os.getpid()
        # If the target is a symlink, the rename-on-close semantics of this
        # class would break the symlink, replacing it with the new file.
        # Instead, follow the symlink here, and replace the target file on
        # close.
        while os.path.islink(filename):
            filename = os.path.join(os.path.dirname(filename),
                                    os.readlink(filename))
        try:
            f = safe_open(self.tmpname, 'w')
        except IOError as msg:
            raise IOError('%s, opening output file "%s"' % (msg, self.tmpname))
        self.file = f
        self.write = f.write
        self.flush = f.flush

    def __del__(self):
        self.close()

    def abort(self):
        try:
            if hasattr(self, 'file'):
                self.file.close()
        except IOError:
            pass
        self.closed = True

    def close(self):
        if self.closed or not hasattr(self, 'file'):
            return
        self.file.flush()
        os.fsync(self.file.fileno())
        self.file.close()
        os.rename(self.tmpname, self.filename)
        self.closed = True

#######################################
class logfile(object):
    '''A class for locking and appending timestamped data lines to a log file.
    '''
    def __init__(self, filename):
        self.closed = False
        self.filename = filename
        try:
            self.file = open(expand_user_vars(self.filename), 'a')
        except IOError as msg:
            raise IOError('%s, opening file "%s"' % (msg, self.filename))

    def __del__(self):
        self.close()

    def __str__(self):
        return 'logfile(filename="%s")' % self.filename

    def close(self):
        if self.closed:
            return
        self.file.flush()
        self.file.close()
        self.closed = True

    def write(self, s):
        try:
            lock_file(self.file, 'flock')
            # Seek to end
            self.file.seek(0, 2)
            self.file.write(time.strftime(logtimeformat, time.localtime())
                            + ' ' + s.rstrip() + os.linesep)
            self.file.flush()
        finally:
            unlock_file(self.file, 'flock')

#######################################
def format_params(d, maskitems=('password', ), skipitems=()):
    '''Take a dictionary of parameters and return a string summary.
    '''
    s = ''
    for key in list(sorted(d.keys())):
        if key in skipitems:
            continue
        if s:
            s += ','
        if key in maskitems:
            s += '%s=*' % key
        else:
            s += '%s="%s"' % (key, d[key])
    return s

###################################
def alarm_handler(*unused):
    '''Handle an alarm during maildir delivery.

    Should never happen.
    '''
    raise getmailDeliveryError('Delivery timeout')

#######################################
def is_maildir(d):
    '''Verify a path is a maildir.
    '''
    dir_parent = os.path.dirname(d.endswith('/') and d[:-1] or d)
    if not os.access(dir_parent, os.X_OK):
        raise getmailConfigurationError(
            'cannot read contents of parent directory of %s '
            '- check permissions and ownership' % d
        )
    if not os.path.isdir(d):
        return False
    if not os.access(d, os.X_OK):
        raise getmailConfigurationError(
            'cannot read contents of directory %s '
            '- check permissions and ownership' % d
        )
    for sub in ('tmp', 'cur', 'new'):
        subdir = os.path.join(d, sub)
        if not os.path.isdir(subdir):
            return False
        if not os.access(subdir, os.W_OK):
            raise getmailConfigurationError(
                'cannot write to maildir %s '
                '- check permissions and ownership' % d
            )
    return True

#######################################
def deliver_maildir(maildirpath, data, hostname, dcount=None, filemode=0o600):
    '''Reliably deliver a mail message into a Maildir.  Uses Dan Bernstein's
    documented rules for maildir delivery, and the updated naming convention
    for new files (modern delivery identifiers).  See
    http://cr.yp.to/proto/maildir.html and
    http://qmail.org/man/man5/maildir.html for details.
    '''
    if not is_maildir(maildirpath):
        raise getmailDeliveryError('not a Maildir (%s)' % maildirpath)

    # Set a 24-hour alarm for this delivery
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(24 * 60 * 60)

    info = {
        'deliverycount' : dcount,
        'hostname' : hostname.split('.')[0].replace('/', '\\057').replace(
            ':', '\\072'),
        'pid' : os.getpid(),
    }
    dir_tmp = os.path.join(maildirpath, 'tmp')
    dir_new = os.path.join(maildirpath, 'new')

    for unused in range(3):
        t = time.time()
        info['secs'] = int(t)
        info['usecs'] = int((t - int(t)) * 1000000)
        info['unique'] = 'M%(usecs)dP%(pid)s' % info
        if info['deliverycount'] is not None:
            info['unique'] += 'Q%(deliverycount)s' % info
        try:
            info['unique'] += 'R%s' % ''.join(
                ['%02x' % ord(char)
                 for char in open('/dev/urandom').read(8)]
            )
        except Exception:
            pass

        filename = '%(secs)s.%(unique)s.%(hostname)s' % info
        fname_tmp = os.path.join(dir_tmp, filename)
        fname_new = os.path.join(dir_new, filename)

        # File must not already exist
        if os.path.exists(fname_tmp):
            # djb says sleep two seconds and try again
            time.sleep(2)
            continue

        # Be generous and check cur/file[:...] just in case some other, dumber
        # MDA is in use.  We wouldn't want them to clobber us and have the user
        # blame us for their bugs.
        curpat = os.path.join(maildirpath, 'cur', filename) + ':*'
        collision = glob.glob(curpat)
        if collision:
            # There is a message in maildir/cur/ which could be clobbered by
            # a dumb MUA, and which shouldn't be there.  Abort.
            raise getmailDeliveryError('collision with %s' % collision)

        # Found an unused filename
        break
    else:
        signal.alarm(0)
        raise getmailDeliveryError('failed to allocate file in maildir')

    # Get user & group of maildir
    s_maildir = os.stat(maildirpath)

    # Open file to write
    try:
        if sys.version_info.major > 2:
            f = safe_open(fname_tmp, 'bw', filemode)
        else:
            f = safe_open(fname_tmp, 'w', filemode)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
        f.close()

    except IOError as o:
        signal.alarm(0)
        raise getmailDeliveryError('failure writing file %s (%s)'
                                   % (fname_tmp, o))

    # Move message file from Maildir/tmp to Maildir/new
    try:
        # #https://pypi.org/project/getmail_shutils/#description
        # #Version of getmail using shutil instead of os.link to allow it to be used with a shared destination folder in a VM.
        # shutil.copyfile(fname_tmp, fname_new)
        os.link(fname_tmp, fname_new)
        os.unlink(fname_tmp)

    except OSError:
        signal.alarm(0)
        try:
            os.unlink(fname_tmp)
        except KeyboardInterrupt:
            raise
        except Exception:
            pass
        raise getmailDeliveryError('failure renaming "%s" to "%s"'
                                   % (fname_tmp, fname_new))

    # Delivery done

    # Cancel alarm
    signal.alarm(0)
    signal.signal(signal.SIGALRM, signal.SIG_DFL)

    return filename

#######################################
def mbox_from_escape(s):
    '''Escape spaces, tabs, and newlines in the envelope sender address.'''
    return ''.join([(c in (' ', '\t', '\n')) and '-' or c for c in s]) or '<>'

#######################################
def address_no_brackets(addr):
    '''Strip surrounding <> on an email address, if present.'''
    if addr.startswith('<') and addr.endswith('>'):
        return addr[1:-1]
    else:
        return addr

#######################################
def eval_bool(s):
    '''Handle boolean values intelligently.
    '''
    try:
        return _bool_values[str(s).lower()]
    except KeyError:
        raise getmailConfigurationError(
            'boolean parameter requires value to be one of true or false, '
            'not "%s"' % s
        )

#######################################
def gid_of_uid(uid):
    try:
        return pwd.getpwuid(uid).pw_gid
    except KeyError as o:
        raise getmailConfigurationError('no such specified uid (%s)' % o)

#######################################
def uid_of_user(user):
    try:
        return pwd.getpwnam(user).pw_uid
    except KeyError as o:
        raise getmailConfigurationError('no such specified user (%s)' % o)

#######################################
def change_usergroup(logger=None, user=None, group=None):
    '''
    Change the current effective GID and UID to those specified by user and
    group.
    '''
    uid = None
    gid = None
    if group:
        if logger:
            logger.debug('Getting GID for specified group %s\n' % group)
        try:
            gid = grp.getgrnam(group).gr_gid
        except KeyError as o:
            raise getmailConfigurationError('no such specified group (%s)' % o)
    if user:
        if logger:
            logger.debug('Getting UID for specified user %s\n' % user)
        uid = uid_of_user(user)

    change_uidgid(logger, uid, gid)


#######################################
def change_uidgid(logger=None, uid=None, gid=None):
    '''
    Change the current effective GID and UID to those specified by uid
    and gid.
    '''
    try:
        if gid:
            if os.getegid() != gid:
                if logger:
                    logger.debug('Setting egid to %d\n' % gid)
                os.setregid(gid, gid)
        if uid:
            if os.geteuid() != uid:
                if logger:
                    logger.debug('Setting euid to %d\n' % uid)
                os.setreuid(uid, uid)
    except OSError as o:
        raise getmailDeliveryError('change UID/GID to %s/%s failed (%s)'
                                   % (uid, gid, o))


#######################################
def format_header(name, line):
    '''Take a long line and return rfc822-style multiline header.
    '''
    header = ''
    line = (name.strip() + ': '
            + ' '.join([part.strip() for part in line.splitlines()]))
    # Split into lines of maximum 78 characters long plus newline, if
    # possible.  A long line may result if no space characters are present.
    while line and len(line) > 78:
        i = line.rfind(' ', 0, 78)
        if i == -1:
            # No space in first 78 characters, try a long line
            i = line.rfind(' ')
            if i == -1:
                # No space at all
                break
        if header:
            header += os.linesep + '  '
        header += line[:i]
        line = line[i:].lstrip()
    if header:
        header += os.linesep + '  '
    if line:
        header += line.strip() + os.linesep
    return header

#######################################
def expand_user_vars(s):
    '''Return a string expanded for both leading "~/" or "~username/" and
    environment variables in the form "$varname" or "${varname}".
    '''
    return os.path.expanduser(os.path.expandvars(s))

#######################################
def localhostname():
    '''Return a name for localhost which is (hopefully) the "correct" FQDN.
    '''
    n = socket.gethostname()
    if '.' in n:
        return n
    return socket.getfqdn()

#######################################
def check_ssl_key_and_cert(conf):
    keyfile = conf['keyfile']
    if keyfile is not None:
        keyfile = expand_user_vars(keyfile)
    certfile = conf['certfile']
    if certfile is not None:
        certfile = expand_user_vars(certfile)
    if keyfile and not os.path.isfile(keyfile):
        raise getmailConfigurationError(
            'optional keyfile must be path to a valid file'
        )
    if certfile and not os.path.isfile(certfile):
        raise getmailConfigurationError(
            'optional certfile must be path to a valid file'
        )
    if (keyfile is None) ^ (certfile is None):
        raise getmailConfigurationError(
            'optional certfile and keyfile must be supplied together'
        )
    return (keyfile, certfile)

#######################################
def check_ca_certs(conf):
    ca_certs = conf['ca_certs']
    if ca_certs is not None:
        ca_certs = expand_user_vars(ca_certs)
        if ssl is None:
            raise getmailConfigurationError(
                'specifying ca_certs not supported by this installation of '
                'Python; requires Python 2.6'
            )
    if ca_certs and not os.path.isfile(ca_certs):
        raise getmailConfigurationError(
            'optional ca_certs must be path to a valid file'
        )
    return ca_certs

#######################################
def check_ssl_version(conf):
    ssl_version = conf['ssl_version']
    if ssl_version is None:
        return None
    if ssl is None:
        raise getmailConfigurationError(
            'specifying ssl_version not supported by this installation of '
            'Python; requires Python 2.6'
        )
    def get_or_fail(version, symbol):
        if symbol is not None:
            v = getattr(ssl, symbol, None)
            if v is not None:
                return v
        raise getmailConfigurationError(
            'unknown or unsupported ssl_version "%s"' % version
        )

    ssl_version = ssl_version.lower()
    if ssl_version == 'sslv23':
        return get_or_fail(ssl_version, 'PROTOCOL_SSLv23')
    elif ssl_version == 'sslv3':
        return get_or_fail(ssl_version, 'PROTOCOL_SSLv3')
    elif ssl_version == 'tlsv1':
        return get_or_fail(ssl_version, 'PROTOCOL_TLSv1')
    elif ssl_version == 'tlsv1_1' and 'PROTOCOL_TLSv1_1' in dir(ssl):
        return get_or_fail(ssl_version, 'PROTOCOL_TLSv1_1')
    elif ssl_version == 'tlsv1_2' and 'PROTOCOL_TLSv1_2' in dir(ssl):
        return get_or_fail(ssl_version, 'PROTOCOL_TLSv1_2')
    return get_or_fail(ssl_version, None)

#######################################
def check_ssl_fingerprints(conf):
    ssl_fingerprints = conf['ssl_fingerprints']
    if not ssl_fingerprints:
        return ()
    if ssl is None or hashlib is None:
        raise getmailConfigurationError(
            'specifying ssl_fingerprints not supported by this installation of '
            'Python; requires Python 2.6'
        )

    normalized_fprs = []
    for fpr in ssl_fingerprints:
        fpr = fpr.lower().replace(':','')
        if len(fpr) != 64:
            raise getmailConfigurationError(
                'ssl_fingerprints must each be the SHA256 certificate hash in hex (with or without colons)'
            )
        normalized_fprs.append(fpr)
    return normalized_fprs

#######################################
def check_ssl_ciphers(conf):
    ssl_ciphers = conf['ssl_ciphers']
    if ssl_ciphers:
        if sys.version_info < (2, 7, 0):
            raise getmailConfigurationError(
                'specifying ssl_ciphers not supported by this installation of '
                'Python; requires Python 2.7'
            )
        if re.search(r'[^a-zA-z0-9, :!\-+@]', ssl_ciphers):
            raise getmailConfigurationError(
                'invalid character in ssl_ciphers'
            )
    return ssl_ciphers

#######################################
keychain_password = None
if os.name == 'posix':
    if keyring:
        def keychain_password(user, server, protocol, logger):
            return keyring.get_password(server,user)
    elif os.path.isfile(osx_keychain_binary):
        def keychain_password(user, server, protocol, logger):
            """Mac OSX: return a keychain password, if it exists.  Otherwise, return

         None.
            """
            # OSX protocol is not an arbitrary string; it's a code limited to
            # 4 case-sensitive chars, and only specific values.
            protocol = protocol.lower()
            if 'imap' in protocol:
                protocol = 'imap'
            elif 'pop' in protocol:
                protocol = 'pop3'
            else:
                # This will break.
                protocol = '????'

            # wish we could pass along a comment to this thing for the user prompt
            cmd = "%s find-internet-password -g -a '%s' -s '%s' -r '%s'" % (
                osx_keychain_binary, user, server, protocol
            )
            (status, output) = subprocess.getstatusoutput(cmd)
            if status != os.EX_OK or not output:
                logger.error('keychain command %s failed: %s %s'
                             % (cmd, status, output))
                return None
            password = None
            for line in output.split('\n'):
                #match = re.match(r'password: "([^"]+)"', line)
                #if match:
                #    password = match.group(1)
                if 'password:' in line:
                    pw = line.split(':', 1)[1].strip()
                    if pw.startswith('"') and pw.endswith('"'):
                        pw = pw[1:-1]
                    password = pw
            if password is None:
                logger.debug('No keychain password found for %s %s %s\n'
                             % (user, server, protocol))
            return password
    elif gnomekeyring:
        def keychain_password(user, server, protocol, logger):
            """Gnome: return a keyring password, if it exists.  Otherwise, return
            None.
            """
            #logger.trace('trying Gnome keyring for user="%s", server="%s", protocol="%s"\n'
            #             % (user, server, protocol))
            try:
                # http://developer.gnome.org/gnome-keyring/3.5/gnome-keyring
                # -Network-Passwords.html#gnome-keyring-find-network-password-sync
                secret = gnomekeyring.find_network_password_sync(
                    # user, domain=None, server, object=None, protocol,
                    # authtype=None, port=0
                    user, None, server, None, protocol, None, 0
                )

                #logger.trace('got keyring result %s' % str(secret))
            except gnomekeyring.NoMatchError:
                logger.debug('gnome-keyring does not know password for %s %s %s\n'
                             % (user, server, protocol))
                return None

            # secret looks like this:
            # [{'protocol': 'imap', 'keyring': 'Default', 'server': 'gmail.com',
            #   'user': 'hiciu', 'item_id': 1L, 'password': 'kielbasa'}]
            if secret and 'password' in secret[0]:
                return secret[0]['password']

            return None
    #else:
        # Posix but no OSX keychain or Gnome keyring.
        # Fallthrough
if keychain_password is None:
    def keychain_password(user, server, protocol, logger):
        """Neither Mac OSX keychain or Gnome keyring available: always return
        None.
        """
        return None


#######################################
def get_password(label, user, server, protocol, logger):
    # try keychain/keyrings first, where available
    password = keychain_password(user, server, protocol, logger)
    if password:
        logger.debug('using password from keychain/keyring\n')
    else:
        # no password found (or not on OSX), prompt in the usual way
        password = getpass.getpass('Enter password for %s:  ' % label)
    return password


