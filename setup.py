import sys

import os.path
from setuptools import setup
import distutils.sysconfig
import site

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

DOCDIR = os.path.join('share','doc','getmail-%s' % __version__)
GETMAILDOCDIR = os.path.join(datadir or prefix, DOCDIR)

MANDIR = os.path.join('share','man','man1')
GETMAILMANDIR = os.path.join( datadir or prefix, MANDIR)

if '--show-default-install-dirs' in args:
    print('Default installation directories:')
    print('  scripts :        %s' % distutils.sysconfig.get_config_var('BINDIR'))
    print('  Python modules : %s' % distutils.sysconfig.get_python_lib())
    print('  documentation :  %s' % GETMAILDOCDIR)
    print('  man(1) pages :   %s' % GETMAILMANDIR)
    raise SystemExit()

setup(
    name='getmail6',
    version=__version__,
    description='a mail retrieval, sorting, and delivering system',
    long_description=open('README').read(),
    author='Charles Cazabon, Roland Puntaier, and others',
    author_email='charlesc-getmail@pyropus.ca',
    maintainer_email='roland.puntaier@gmail.com',
    license='GNU GPL version 2',
    url='https://www.getmail6.org/',
    download_url='https://github.com/getmail6/getmail6/releases',
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
        'getmail_mbox',
        'getmail-gmail-xoauth-tokens',
    ],
    data_files=[
        (DOCDIR, [
            './README',
            'docs/BUGS',
            'docs/COPYING',
            'docs/CHANGELOG',
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
        (MANDIR, [
            'docs/getmail.1',
            'docs/getmail_fetch.1',
            'docs/getmail_maildir.1',
            'docs/getmail_mbox.1',
        ]),
    ],
)
