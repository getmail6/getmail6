#!/usr/bin/env python

import sys
if sys.hexversion < 0x2030300:
    raise ImportError('getmail requires Python version 2.3.3 or later')

from getmailcore import __version__

from distutils.core import setup

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
        ('/usr/local/share/doc/getmail-4/', ['README', 'docs/BUGS', 'docs/COPYING', 'docs/CHANGELOG', 'docs/documentation.txt', 'docs/getmailrc-example', 'docs/TODO']),
        #('/etc/', [])
    ],
)
      
