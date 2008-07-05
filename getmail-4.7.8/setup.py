#!/usr/bin/env python

import sys
if sys.hexversion < 0x2030300:
    raise ImportError('getmail version 4 requires Python version 2.3.3 or later')

import os.path
from distutils.core import setup
import distutils.sysconfig

from getmailcore import __version__

#
# distutils doesn't seem to handle documentation files specially; they're
# just "data" files.  The problem is, there's no easy way to say "install
# the doc files under <prefix>/doc/<package>-<version>/ (obeying any
# --home=<althome> or --prefix=<altprefix>, which would be "normal".
# This hacks around this limitation.
#
prefix = distutils.sysconfig.get_config_var('prefix')
datadir = None
args = sys.argv[1:]
for (pos, arg) in enumerate(args):
    # hack hack hack
    if arg.startswith('--prefix='):
        # hack hack hack hack hack
        prefix = arg.split('=', 1)[1]
    elif arg == '--prefix':
        # hack hack hack hack hack hack hack
        prefix = args[pos + 1]
    elif arg.startswith('--install-data='):
        # hack hack hack hack hack
        datadir = arg.split('=', 1)[1]
    elif arg == '--install-data':
        # hack hack hack hack hack hack hack
        datadir = args[pos + 1]

GETMAILDOCDIR = os.path.join(
    datadir or prefix,
    'share',
    'doc',
    'getmail-%s' % __version__
)

GETMAILMANDIR = os.path.join(
    datadir or prefix,
    'share',
    'man',
    'man1'
)

if '--show-default-install-dirs' in args:
    print 'Default installation directories:'
    print '  scripts :        %s' % distutils.sysconfig.get_config_var('BINDIR')
    print '  Python modules : %s' % os.path.join(distutils.sysconfig.get_config_var('LIBP'), 'site-packages')
    print '  documentation :  %s' % GETMAILDOCDIR
    print '  man(1) pages :   %s' % GETMAILMANDIR
    raise SystemExit()

setup(
    name='getmail',
    version=__version__,
    description='a mail retrieval, sorting, and delivering system',
    long_description=('getmail is a multi-protocol mail retrieval system with'
        'support for simple and domain POP3 and IMAP4 mailboxes, domain SDPS '
        'mailboxes, POP3-over-SSL and IMAP-over-SSL, mail sorting, message '
        'filtering, and delivery to Maildirs, Mboxrd files, external MDAs, and '
        'other advanced features.'),
    author='Charles Cazabon',
    author_email='charlesc-getmail@pyropus.ca',
    license='GNU GPL version 2',
    url='http://pyropus.ca/software/getmail/',
    download_url='http://pyropus.ca/software/getmail/#download',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Topic :: Communications :: Email',
        'Topic :: Communications :: Email :: Filters',
        'Topic :: Communications :: Email :: Post-Office :: IMAP',
        'Topic :: Communications :: Email :: Post-Office :: POP3',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
    ],
    packages=[
        'getmailcore'
    ],
    scripts=[
    'getmail',
    'getmail_fetch',
    'getmail_maildir',
    'getmail_mbox'
    ],
    data_files=[
        (GETMAILDOCDIR, [
            './README',
            './getmail.spec',
            'docs/BUGS',
            'docs/COPYING',
            'docs/CHANGELOG',
            'docs/TODO',
            'docs/THANKS',
            'docs/configuration.html',
            'docs/configuration.txt',
            'docs/documentation.html',
            'docs/documentation.txt',
            'docs/faq.html',
            'docs/faq.txt',
            'docs/getmaildocs.css',
            'docs/getmailrc-examples',
            'docs/troubleshooting.html',
            'docs/troubleshooting.txt',
        ]),
        (GETMAILMANDIR, [
            'docs/getmail.1',
            'docs/getmail_fetch.1',
            'docs/getmail_maildir.1',
            'docs/getmail_mbox.1',
        ]),
    ],
)
