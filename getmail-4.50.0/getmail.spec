%define python_sitelib %(%{__python} -c 'from distutils import sysconfig; print sysconfig.get_python_lib()')

Summary: POP3 mail retriever with reliable Maildir delivery
Name: getmail
Version: 4.50.0
Release: 1
License: GPL
Group: Applications/Internet
URL: http://pyropus.ca/software/getmail/

Source: http://pyropus.ca/software/getmail/old-versions/getmail-%{version}.tar.gz
Buildroot: %{_tmppath}/%{name}-%{version}-%{release}-root

BuildArch: noarch
BuildRequires: python-devel >= 2.3.3
Requires: python >= 2.3.3

%description
getmail is intended as a simple replacement for fetchmail for those people
who do not need its various and sundry configuration options, complexities,
and bugs.  It retrieves mail from one or more POP3 servers for one or more
email accounts, and reliably delivers into a Maildir specified on a
per-account basis.  It can also deliver into mbox files, although this
should not be attempted over NFS.  getmail is written entirely in python.

%prep
%setup -q

%build

%install
%{__rm} -rf %{buildroot}
%{__python} setup.py install --root="%{buildroot}"

%clean
%{__rm} -rf %{buildroot}

%files
%defattr(-, root, root, 0755)
%doc docs/BUGS docs/CHANGELOG docs/COPYING docs/THANKS docs/TODO 
%doc docs/configuration.html docs/configuration.txt docs/documentation.html 
%doc docs/documentation.txt docs/faq.html docs/faq.txt docs/getmaildocs.css 
%doc docs/getmailrc-examples docs/troubleshooting.html docs/troubleshooting.txt
%doc %{_mandir}/man1/getmail.1*
%doc %{_mandir}/man1/getmail_fetch.1*
%doc %{_mandir}/man1/getmail_maildir.1*
%doc %{_mandir}/man1/getmail_mbox.1*
%{_bindir}/getmail
%{_bindir}/getmail_fetch
%{_bindir}/getmail_maildir
%{_bindir}/getmail_mbox
%{python_sitelib}/getmailcore/

%changelog
* Mon Jul 11 2016 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.50.0

* Wed Jan 13 2016 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.49.0

* Sun May 31 2015 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.48.0

* Wed Feb 25 2015 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.47.0

* Sun Apr 06 2014 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.46.0

* Sun Apr 06 2014 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.46.0

* Sun Mar 30 2014 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.45.0

* Sun Mar 30 2014 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.45.0

* Sun Mar 30 2014 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.44.0

* Sun Mar 30 2014 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.44.0

* Sun Mar 30 2014 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.44.0

* Sat Mar 22 2014 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.44.0

* Sat Mar 22 2014 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.44.0

* Sun Aug 25 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.43.0

* Sun Aug 25 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.43.0

* Sat Aug 03 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.42.0

* Sat Aug 03 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.42.0

* Sat Aug 03 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.42.0

* Sat Aug 03 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.42.0

* Sat Aug 03 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.42.0

* Sun May 26 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.41.0

* Fri May 10 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.40.3

* Wed May 08 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.40.2

* Mon Apr 22 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.40.1

* Sun Apr 21 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.40.0

* Sun Mar 10 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.39.1

* Fri Feb 22 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.39.0

* Fri Feb 22 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.39.0

* Fri Feb 22 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.39.0

* Sat Feb 16 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.38.0

* Sat Feb 16 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.38.0

* Sun Jan 27 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.37.0

* Sun Jan 27 2013 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.37.0

* Sat Dec 15 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.36.0

* Wed Oct 24 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.35.0

* Sat Sep 08 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.34.0

* Tue Aug 07 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.33.0

* Fri Jul 06 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.32.0

* Thu Jul 05 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.31.0

* Wed Jun 27 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.30.2

* Thu Jun 21 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.30.1

* Thu Jun 21 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.30.1

* Thu Jun 21 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.30.0

* Thu Jun 21 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.30.0

* Thu Jun 21 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.30.0

* Tue Jun 19 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.29.0

* Tue Jun 19 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.29.0

* Sun May 20 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.27.0

* Sun May 20 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.27.0

* Sat Apr 14 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.26.0

* Wed Feb 01 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.25.0

* Tue Jan 03 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.25.0

* Tue Jan 03 2012 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.25.0

* Sun Dec 11 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.24.0

* Sun Nov 20 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.23.0

* Sat Nov 12 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.22.2

* Fri Sep 30 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.22.1

* Sun Sep 25 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.22.0

* Fri Sep 23 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.21.0

* Sat Jul 16 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.20.4

* Mon May 30 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.20.3

* Mon May 30 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.20.3

* Sat Apr 09 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.20.2

* Thu Apr 07 2011 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.20.1

* Tue Jun 29 2010 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.20.0

* Tue Jun 29 2010 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.19.0

* Sat Jun 26 2010 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.18.0

* Sat Jun 26 2010 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.18.0

* Fri Apr 30 2010 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.17.0

* Tue Jan 05 2010 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.16.0

* Wed Dec 02 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.15.0

* Mon Nov 23 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.14.0

* Tue Oct 13 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.13.0

* Tue Oct 13 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.12.0

* Wed Oct 07 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.12.0

* Sat Aug 08 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.11.0

* Thu Aug 06 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.10.0

* Thu Jul 16 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.9.2

* Mon Jun 01 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.9.1

* Sun Apr 05 2009 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.9.0

* Fri Sep 26 2008 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.8.4

* Mon Aug 11 2008 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.8.3

* Sat Aug 02 2008 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.8.2

* Wed Mar 26 2008 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.8.1

* Tue Feb 19 2008 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.8.0

* Tue Feb 05 2008 Charles Cazabon <charlesc-getmail-rpm@pyropus.ca>
-update to version 4.7.8

* Mon Aug 13 2007 Dries Verachtert <dries@ulyssis.org> - 4.7.6-1
- Updated to release 4.7.6.

* Thu Jun 07 2007 Dries Verachtert <dries@ulyssis.org> - 4.7.5-1
- Updated to release 4.7.5.

* Wed May 09 2007 Dries Verachtert <dries@ulyssis.org> - 4.7.4-1
- Updated to release 4.7.4.

* Mon Mar 19 2007 Dries Verachtert <dries@ulyssis.org> - 4.7.3-1
- Updated to release 4.7.3.

* Sun Mar 04 2007 Dag Wieers <dag@wieers.com> - 4.7.2-1
- Initial package. (using DAR)
