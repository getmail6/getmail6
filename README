.. vim: syntax=rst

.. docs/COPYING 2a + DRY: https://github.com/getmail6/getmail6
.. Please refer to the git history regarding who changed what and when in this file.

getmail6
========

getmail6 is a flexible, extensible mail retrieval system with
support for POP3, IMAP4, SSL variants of both, maildirs, mboxrd files,
external MDAs, arbitrary message filtering, single-user and domain-mailboxes,
and many other useful features.

getmail is Copyright (C) 1998-2022 Charles Cazabon and others.
getmail is licensed for use under the GNU General Public License version 2 (only).
See ``docs/COPYING`` for specific terms and distribution information.

getmail6 has adaptations to work with Python 3.
These changes might still contain some bugs.
Please report them at https://github.com/getmail6/getmail6.
See ``docs/BUGS`` for instructions on reporting bugs.

getmail6 will probably not work with Python versions older than 2.7.
Use getmail 5.14 with them.

Installation
------------

To install::

  pip install getmail6

To uninstall::

  pip uninstall getmail6

You can install getmail6 in your home directory if you add ``--user``.

If getmail6 is available via your Linux distribution, you better use that.

Usage
-----

getmail6 is not a python API.
getmail6 provides command line tools:

- getmail
- getmail_maildir,
- getmail_mbox
- getmail_fetch
- getmail-gmail-xoauth-tokens

Before using ``getmail`` you must configure it.
See ``docs/configuration.txt`` and ``docs/getmailrc-examples``.
An example::

  [retriever]
  type = SimpleIMAPSSLRetriever
  server = imap.gmail.com 
  port = 993
  username = <your_email_here>
  #password = ... or
  password_command = ("pass", "<your_email_here>")

  [destination]
  type = Maildir
  path = ~/Mail/<your_email_here>/INBOX/

  [options]
  read_all = true
  delete = true

Google gmail
------------

For **gmail**,
after having enabled 2-Step Authentication,
let google generate an "app password" for you.
Then, for the above example,
use ``pass edit <your_email_here>`` and change to the generate one.

- Go to https://mail.google.com
- If you are signed in, on the left upper corner there is a cogwheel symbol for settings
- Choose "See all Settings"
- "Accounts and Imports" tab, then "Other Google Account Settings"/"Security" brings you to
  https://myaccount.google.com/u/0/security?hl=en
- Turn on "2-Step Verification" (also known as 2-factor-authentication or 2FA)
- In "App passwords", generate a password for your device
- Update this in your password command.

See also: https://support.google.com/accounts/answer/185833

Oauth2 Privacy Policy
---------------------

getmail is a native app.
See
https://developers.google.com/identity/protocols/oauth2/native-app
Still, to download your email from gmail to your computer using OAuth2
you need to grant getmail OAuth2 access to the scope ``https://mail.google.com/``,
as you would to web apps.
Unfortunately, the init step in example 12 in ``docs/getmailrc-examples``
has to be repeated regularly.
This makes the *app password* method above a better alternative.
Don't forget to remove the ``use_xoauth2`` line,
if you switch from Oauth2 to *app password*.

Tests
-----

getmail 5.14 did not come with tests.

There is now a test folder that uses
`docker-mailserver <https://github.com/docker-mailserver/docker-mailserver>`__
for black box testing.

This still tests Python 2.7.

Tests are work in progress.

Documentation
-------------

See the HTML documentation for details on setting up and using ``getmail``.
It is included in the ``docs`` subdirectory,
and will be installed in ``<PREFIX>/doc/getmail-<version>/`` (by default).

::

  docs/documentation.txt
  docs/configuration.txt
  docs/faq.txt
  docs/troubleshooting.txt


