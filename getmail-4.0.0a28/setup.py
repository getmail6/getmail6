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
args = sys.argv[1:]
for (pos, arg) in enumerate(args):
    # hack hack hack
    if arg.startswith('--home=') or arg.startswith('--prefix='):
        # hack hack hack hack hack
        prefix = arg.split('=', 1)[1]
    elif arg in ('--home', '--prefix'):
        # hack hack hack hack hack hack hack
        prefix = args[pos + 1]
    
if not os.path.isdir(prefix):
    print 'Warning: specified home or prefix directory %s does not exist, will create it' % prefix

GETMAILDOCDIR = os.path.join(
    prefix,
    'doc',
    'getmail-%s' % __version__
)

GETMAILMANDIR = os.path.join(
    prefix,
    'man',
    'man1'
)

setup(
    name='getmail',
    version=__version__,
    description='a mail retrieval, sorting, and delivering system',
    long_description=('getmail is a multi-protocol mail retrieval system with'
        'support for simple and domain POP3 mailboxes, domain SPDS mailboxes, '
        'mail sorting, filtering, and delivery to Maildirs, Mboxrd files, '
        'external MDAs, and other advanced features.'),
    author='Charles Cazabon',
    author_email='getmail@discworld.dyndns.org',
    url='http://www.qcc.ca/~charlesc/software/getmail-4',
    download_url='http://www.qcc.ca/~charlesc/software/getmail-4/#download',
    classifiers=[
        'Development Status :: 3 - Alpha',
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
	'getmail_maildir',
	'getmail_mbox'
    ],
    data_files=[
        (GETMAILDOCDIR, [
            './README',
            'docs/BUGS',
            'docs/COPYING',
            'docs/CHANGELOG',
            'docs/TODO',
            'docs/THANKS',
            'docs/documentation.html',
            'docs/faq.html',
            'docs/configuration.html',
            'docs/troubleshooting.html',
            'docs/documentation.txt',
            'docs/faq.txt',
            'docs/configuration.txt',
            'docs/troubleshooting.txt',
            'docs/getmaildocs.css',
            'docs/getmailrc-example',
        ]),
        (GETMAILMANDIR, [
            'docs/getmail.1',
            'docs/getmail_maildir.1',
            'docs/getmail_mbox.1',
        ]),
    ],
)
