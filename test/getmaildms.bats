: '

cd ..
make dockertest

'

ssl_rc() {
  mkdir -p /home/user1/Mail/{cur,tmp,new}
  rm -rf /home/user1/Mail/new/*
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPSSLRetriever
port = 993
server = localhost
username = user1@example.test
password = ТЕСТПАСС
ca_certs = /certs/demoCA/cacert.pem
certfile = /certs/mail.example.test-cert.pem
keyfile = /certs/mail.example.test-key.pem
[destination]
type = Maildir
path = /home/user1/Mail/
[options]
read_all = false
delete = false

EOF
}

maildir_rc() {
  mkdir -p /home/user1/Mail/{cur,tmp,new}
  rm -rf /home/user1/Mail/new/*
  local TYP=$1
  local PORT=$2
  local READALL=$3
  local DEL=$4
  local EXTRALINE=$5
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = Simple${TYP}Retriever
server = localhost
username = user1@example.test
port = $PORT
password = ТЕСТПАСС
$EXTRALINE
[destination]
type = Maildir
path = /home/user1/Mail/
[options]
read_all = $READALL
delete = $DEL

EOF
}

filter_rc() {
  local TYP=$1
  local PORT=$2
  mkdir -p /home/user1/Mail/{cur,tmp,new}
  rm -rf /home/user1/Mail/new/*
  mkdir -p /home/user1/Mail/tests/{cur,tmp,new}
  rm -rf /home/user1/Mail/tests/new/*
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = Simple${TYP}Retriever
server = localhost
username = user1@example.test
port = $PORT
password = ТЕСТПАСС
[destination]
type = MDA_external
path = /usr/bin/procmail
arguments = ('-f', '%(sender)', '-m', '/home/user1/procmail')
#pacman -S spamassassin
[filter-1]
type = Filter_external
path = /usr/bin/spamassassin
ignore_header_shrinkage = True
#pacman -S clamav
[filter-2]
type = Filter_classifier
path = /usr/bin/clamscan
arguments = ('--stdout', '--no-summary', '--scan-mail', '--infected', '-')
exitcodes_drop = (1,)
[options]
read_all = true
delete = true
EOF
  cat > /home/user1/procmail <<EOF
MAILDIR=/home/user1/Mail/
DEFAULT=\$MAILDIR
:0
* ^Subject:.*test.*
tests/
:0
\$DEFAULT/
EOF
}

mbox_rc() {
  mkdir -p /home/user1/Mail
  rm -rf /home/user1/Mail/mbx
  local RETRIEVER=$1
  local PORT=$2
  local MAX=$3
  local READALL=$4
  local DEL=$5
  touch /home/user1/Mail/mbx
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = user1@example.test
port = $PORT
password_command = ('/home/user1/passwordstub',)
[destination]
type = Mboxrd
path = /home/user1/Mail/mbx
[options]
read_all = $READALL
delete = $DEL
max_message_size = $MAX
delete_after = 1
to_oldmail_on_each_mail = true
delete_bigger_than = 800
max_messages_per_session = 9
max_bytes_per_session = 3000
verbose = 3
delivered_to = false
received = false
message_log_verbose = true
message_log_syslog = true
fingerprint = true
logfile = /home/user1/getmail.log
message_log = /home/user1/getmail_message.log
EOF
  cat > /home/user1/passwordstub <<EOF
#!/bin/bash
echo ТЕСТПАСС
EOF
  chmod +x /home/user1/passwordstub
}


multidrop_rc() {
  mkdir -p /home/user1/Mail/{cur,tmp,new}
  rm -rf /home/user1/Mail/new/*
  local RETRIEVER=$1
  local PORT=$2
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = user1@example.test
port = $PORT
password = ТЕСТПАСС
envelope_recipient = X-Envelope-To
[destination]
type = Maildir
path = /home/user1/Mail/
[options]
read_all = True
delete = True
EOF
}

multisorter_rc() {
  mkdir -p /home/user1/Mail/{cur,tmp,new}
  rm -rf /home/user1/Mail/mbx
  rm -rf /home/user1/Mail/new/*
  local RETRIEVER=$1
  local PORT=$2
  touch /home/user1/Mail/mbx
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = user1@example.test
port = $PORT
password = ТЕСТПАСС
envelope_recipient = X-Envelope-To
[destination]
type = MultiSorter
default = [localuser1]
locals = (
     ('user1@', '[localuser1]'),
     ('user2@', '[localuser2]'),
     )
[localuser1]
type = Maildir
path = /home/user1/Mail/
user = user1
[localuser2]
type = Mboxrd
path = /home/user1/Mail/mbx
[options]
read_all = True
delete = True
EOF
}

lmtp_rc() {
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPRetriever
server = localhost
username = user1@example.test
password = ТЕСТПАСС
port = 143
[destination]
type = MDA_lmtp
# use docker-mailserver/dovecot's lmtp listener
host = /var/run/dovecot/lmtp
[options]
read_all = True
delete = True
EOF

}

lmtp_override_rc() {
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPRetriever
server = localhost
username = user2@example.test
port = 143
password = ТЕСТПАСС
[destination]
type = MDA_lmtp
host = /var/run/dovecot/lmtp
override = user1@example.test
[options]
read_all = True
delete = True
EOF
}

lmtp_override_fallback_rc() {
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPRetriever
server = localhost
username = user2@example.test
port = 143
password = ТЕСТПАСС
[destination]
type = MDA_lmtp
host = /var/run/dovecot/lmtp
override = another-nonexistent-user
fallback = user1@example.test
[options]
read_all = True
delete = True
EOF
}

imap_rc() {
  local RETRIEVER=IMAPSSL
  local PORT=993
  local DELETE=$1
  local IMAPSEARCH=$2
  local IMAPDELETE=$3
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = Simple${RETRIEVER}Retriever
server = localhost
username = user1@example.test
port = $PORT
password = ТЕСТПАСС
imap_search = $IMAPSEARCH
imap_on_delete = $IMAPDELETE
[destination]
type = Maildir
path = /home/user1/Mail/
[options]
read_all = true
delete = $DELETE
EOF
}

mark_read_rc() {
  local RETRIEVER=IMAPSSL
  local PORT=993
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = Simple${RETRIEVER}Retriever
server = localhost
username = user1@example.test
port = $PORT
password = ТЕСТПАСС
[destination]
type = Maildir
path = /home/user1/Mail/
[options]
mark_read = true
EOF
}

idle_rc() {
  mkdir -p /home/user1/Mail/{cur,tmp,new}
  rm -rf /home/user1/Mail/new/*
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPRetriever
server = localhost
username=user1@example.test
password=ТЕСТПАСС
$1
[destination]
type = Maildir
path = /home/user1/Mail/
[options]
read_all = true
delete = true
EOF
}


randomtext(){
tr -dc A-Za-z0-9 </dev/urandom | head -c $1; echo
}

_send(){
  RANDOMTXT="$(randomtext ${RANDOMLAST:-13})"
  export RANDOMLAST=$((RANDOMLAST+1))
  export RANDOMTXT
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: user1@example.test
RCPT TO: user1@example.test
DATA
Subject: test
The Troms text is:
${RANDOMTXT}
.
QUIT
EOF
   cat > $HOME/random.env << EOF
RANDOMTXT="$RANDOMTXT"
EOF
  sleep 2.8
}

_send2() {
  RANDOMTXT="$(randomtext ${RANDOMLAST:-13})"
  export RANDOMLAST=$((RANDOMLAST+1))
  export RANDOMTXT
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: user1@example.test
RCPT TO: ${1}
DATA
From: user1@example.test
To: ${2}
Subject: ${3}
This is the test text:
я αβ один süße créme in Tromsœ.
.
QUIT
EOF
   cat > $HOME/random.env << EOF
RANDOMTXT="$RANDOMTXT"
EOF
  sleep 2.8
}

_sendmulti(){
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: user1@example.test
RCPT TO: user1@example.test
DATA
Subject: test
X-Envelope-To: user1@example.test
Content-Type: multipart/mixed; boundary=\"----=_NextPart_000_0012_A796884C.DCABE8FF\"

This is a multi-part message in MIME format.

------=_NextPart_000_0012_A796884C.DCABE8FF
Content-Transfer-Encoding: quoted-printable
Content-Type: text/html

<=21DOCTYPE HTML>

<html><head><title></title>
<meta http-equiv=3D=22X-UA-Compatible=22 content=3D=22IE=3Dedge=22>
</head>
<body style=3D=22margin: 0.4em;=22><p>Dear Sir/Madam,</p>
</body></html>
------=_NextPart_000_0012_A796884C.DCABE8FF--

Content-Type: multipart/mixed; boundary=\"----=_NextPart_000_0012_A796884C.DCABE8FF\"
This is the test text.
------=_NextPart_000_0012_A796884C.DCABE8FF--
.
QUIT
EOF
sleep 2.8
}

_port(){
nmap -n -Pn localhost -p$1 -oG - | grep '/open/'  || return 1
}

@test "checking ports" {
_port 25
_port 143
_port 587
_port 993
}
@test "SSL Parameters IMAP, destination Maildir" {
ssl_rc
getmail --rcfile=getmailrc --getmaildir=/home/user1 2>&1 | grep "Permission denied"
}
@test "SimplePOP3Retriever, destination Maildir" {
_send
maildir_rc POP3 110 true true
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "SimplePOP3SSLRetriever, destination Maildir" {
_send
maildir_rc POP3SSL 995 true true
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "SimpleIMAPRetriever, destination Maildir" {
_send
maildir_rc IMAP 143 true true record_mailbox=true
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "SimpleIMAPSSLRetriever, destination Maildir" {
_send
maildir_rc IMAPSSL 993 true true
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "SimpleIMAPRetriever, destination Maildir, uid_cache=uid.txt" {
rm -rf /home/user1/uid.txt
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
_send
maildir_rc IMAP 143 false false uid_cache=uid.txt
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
sleep 1
n1=$(cat /home/user1/uid.txt | cut -d" " -f 3)
_send
maildir_rc IMAP 143 false false uid_cache=uid.txt
sleep 1
getmail --rcfile=getmailrc --getmaildir=/home/user1
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
sleep 1
n2=$(cat /home/user1/uid.txt | cut -d" " -f 3)
[[ $(( n2 - n1 )) != 0 ]]
}
@test "SimpleIMAPRetriever, destination Maildir, uid_cache=true" {
_send
maildir_rc IMAP 143 false false uid_cache=true
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}

@test "SimplePOP3Retriever, destination MDA_external (procmail), filter spamassassin clamav" {
_send
filter_rc POP3 110
getmail --rcfile=getmailrc --getmaildir=/home/user1 || true
while ! [ -e /home/user1/Mail/tests/new ] ; do
  sleep 1.9
done
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/tests/new/*
}
@test "SimplePOP3SSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
_send
filter_rc POP3SSL 995
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/tests/new/*
}
@test "SimpleIMAPRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
_send
filter_rc IMAP 143
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/tests/new/*
}
@test "SimpleIMAPSSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
_send
filter_rc IMAPSSL 993
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/tests/new/*
}

@test "BrokenUIDLPOP3Retriever 110 800 False False" {
_send
mbox_rc  BrokenUIDLPOP3Retriever 110 800 False False
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -e /home/user1/Mail/mbx ]
}
@test "BrokenUIDLPOP3Retriever 110 900 True  False" {
_send
mbox_rc  BrokenUIDLPOP3Retriever 110 900 True  False
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -e /home/user1/Mail/mbx ]
}
@test "BrokenUIDLPOP3SSLRetriever 995 800 0 0" {
_send
mbox_rc  BrokenUIDLPOP3SSLRetriever 995 800 0 0
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -e /home/user1/Mail/mbx ]
}
@test "BrokenUIDLPOP3SSLRetriever 995 900 1 1" {
_send
mbox_rc  BrokenUIDLPOP3SSLRetriever 995 900 1 1
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -e /home/user1/Mail/mbx ]
}
@test "SimpleIMAPRetriever 143 800 false true" {
_send
mbox_rc  SimpleIMAPRetriever 143 800 false true
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -e /home/user1/Mail/mbx ]
}
@test "SimpleIMAPRetriever 143 900 false true" {
_send
mbox_rc  SimpleIMAPRetriever 143 900 false true
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -e /home/user1/Mail/mbx ]
}
@test "SimpleIMAPSSLRetriever 993 800 False False" {
_send
mbox_rc  SimpleIMAPSSLRetriever 993 800 False False
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -e /home/user1/Mail/mbx ]
}
@test "SimpleIMAPSSLRetriever 993 900 True  True" {
_send
mbox_rc  SimpleIMAPSSLRetriever 993 900 True  True
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -e /home/user1/Mail/mbx ]
}


@test "SimplePOP3Retriever 110" {
_sendmulti
multidrop_rc SimplePOP3Retriever 110
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "MultidropPOP3Retriever 110" {
_sendmulti
multidrop_rc MultidropPOP3Retriever 110
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "SimplePOP3SSLRetriever 995" {
_sendmulti
multidrop_rc SimplePOP3SSLRetriever 995
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "MultidropPOP3SSLRetriever 995" {
_sendmulti
multidrop_rc MultidropPOP3SSLRetriever 995
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "SimpleIMAPRetriever 143" {
_sendmulti
multidrop_rc SimpleIMAPRetriever 143
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "MultidropIMAPRetriever 143" {
_sendmulti
multidrop_rc MultidropIMAPRetriever 143
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "SimpleIMAPSSLRetriever 993" {
_sendmulti
multidrop_rc SimpleIMAPSSLRetriever 993
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "MultidropIMAPSSLRetriever 993" {
_sendmulti
multidrop_rc MultidropIMAPSSLRetriever 993
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "MultidropPOP3Retriever, Multisorter" {
_sendmulti
multisorter_rc MultidropPOP3Retriever 110
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "MultidropPOP3SSLRetriever, Multisorter" {
_sendmulti
multisorter_rc MultidropPOP3SSLRetriever 995
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "MultidropIMAPRetriever, Multisorter" {
_sendmulti
multisorter_rc MultidropIMAPRetriever 143
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}
@test "MultidropIMAPSSLRetriever, Multisorter" {
_sendmulti
multisorter_rc MultidropIMAPSSLRetriever 993
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}

@test "MDA lmtp_rc" {
_send2 user1@example.test user1@example.test lmtp_rc
lmtp_rc
#doveadm purge -A
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
#grep "Subject: lmtp_rc" /var/mail/example.test/user1/cur/*
}
@test "MDA lmtp_override_x" {
_send2 user2@example.test nonexistent-user@example.test lmtp_override_rc
lmtp_override_rc
#doveadm purge -A
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
#grep "Subject: lmtp_override_x" /var/mail/example.test/user2/cur/*
}
@test "MDA lmtp_override_fallback_x" {
_send2 user2@example.test nonexistent-user@example.test lmtp_override_fallback_x
lmtp_override_fallback_rc
#doveadm purge -A
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
#grep "Subject: lmtp_override_fallback_x" /var/mail/example.test/user1/cur/*
}

@test "SimpleIMAPSSLRetriever imap_search imap_on_delete" {
_send
# get all but do not delete
mkdir -p /home/user1/Mail/{cur,tmp,new}
imap_rc false "" ""
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
rm -rf /home/user1/Mail/new/*
# set Seen
imap_rc true UNSEEN "(\Seen)"
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
# get UNSEEN expect none
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
imap_rc true UNSEEN "(\Seen)"
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -z "$(ls /home/user1/Mail/new)" ]
# get SEEN expect 1
imap_rc true SEEN "(\Seen)"
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
# get all expect 1
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
imap_rc true "" ""
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
# mark_read (set SEEN)
_send
mark_read_rc
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
# get UNSEEN expect none
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
imap_rc true UNSEEN "(\Seen)"
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
[ -z "$(ls /home/user1/Mail/new)" ]
# get SEEN expect 1
imap_rc true SEEN "(\Seen)"
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
# get all expect 1
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
imap_rc true "" ""
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}

@test "IMAP override via command line -s" {
_send
imap_rc true "" ""
# "-s," is equivalent to "-s,Seen" so overrides delete=true of config
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s,
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
#(Unseen \Seen) expect none
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
getmail --rcfile=getmailrc --getmaildir=/home/user1 --searchset UNSEEN --searchset ,SEEN
sleep 1.9
[[ "$(grep "$RANDOMTXT" /home/user1/Mail/new/* -l | wc -l)" == "0" ]]
[ -z "$(ls /home/user1/Mail/new)" ]
# search example.test expect 1
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "FROM \"example.test\" ,SEEN"
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
# search Troms expect 1
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "TEXT \"Troms\" ,SEEN"
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
# search NotThere expect none
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "TEXT \"NotThere\""
sleep 1.9
[ -z "$(ls /home/user1/Mail/new)" ]
# get all expect 1
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "ALL ,SEEN"
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
# get all expect 1
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "ALL"
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
# get all expect none
rm -rf /home/user1/Mail/new/*
[ -z "$(ls /home/user1/Mail/new)" ]
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "ALL"
sleep 1.9
[ -z "$(ls /home/user1/Mail/new)" ]
}

@test "getmail_maildir test" {
_send
maildir_rc POP3 110 true true
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1.9
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
echo 'βσSß' | getmail_maildir /home/user1/Mail/
grep 'βσSß' /home/user1/Mail/new/*
}

@test "getmail_fetch test" {
_send
getmail_fetch -p 110 localhost user1@example.test ТЕСТПАСС /home/user1/Mail/
BASH_ENV=$HOME/random.env grep "${RANDOMTXT}" /home/user1/Mail/new/*
}

@test "idle1" {
idle_rc ''
getmail --rcfile=getmailrc --getmaildir=/home/user1
swaks --silent --server mail.example.test --from 'user2@example.test' --to 'user1+idle1@example.test' --header 'idle1' --body "idle1_sieve"
sleep 2.8
swaks --silent --server mail.example.test --from 'user2@example.test' --to 'user1+idle2@example.test' --header 'idle21' --body "idle2_sieve1"
sleep 2.8
swaks --silent --server mail.example.test --from 'user2@example.test' --to 'user1+idle2@example.test' --header 'idle22' --body "idle2_sieve2"
sleep 2.8
ls -1a /var/mail/example.test/user1/.idle1/new
ls -1a /var/mail/example.test/user1/.idle2/new
i1=$(ls -1a /var/mail/example.test/user1/.idle1/new | wc -l)
#echo i1=$i1 >&2
i2=$(ls -1a /var/mail/example.test/user1/.idle2/new | wc -l)
#echo i2=$i2 >&2
idle_rc 'mailboxes=("idle1",)'
pkill getmail || true
sleep 1
getmail --rcfile=getmailrc --getmaildir=/home/user1  --idle= &
sleep 2
pkill getmail
gi=$(ls -1A /home/user1/Mail/new | wc -l)
#echo gi=$gi >&2
[ "$(( gi == (i1-2) ))" -eq 1 ]
}

@test "idle2" {
idle_rc ''
getmail --rcfile=getmailrc --getmaildir=/home/user1
swaks --silent --server mail.example.test --from 'user2@example.test' --to 'user1+idle1@example.test' --header 'idle1' --body "idle1_sieve"
sleep 2.8
swaks --silent --server mail.example.test --from 'user2@example.test' --to 'user1+idle2@example.test' --header 'idle21' --body "idle2_sieve1"
sleep 2.8
swaks --silent --server mail.example.test --from 'user2@example.test' --to 'user1+idle2@example.test' --header 'idle22' --body "idle2_sieve2"
sleep 2.8
i1=$(ls -1a /var/mail/example.test/user1/.idle1/new | wc -l)
#echo i1=$i1 >&2
i2=$(ls -1a /var/mail/example.test/user1/.idle2/new | wc -l)
#echo i2=$i2 >&2
idle_rc 'mailboxes=("idle2",)'
pkill getmail || true
sleep 1
getmail -vvv --rcfile=getmailrc --getmaildir=/home/user1  --idle= &
sleep 2
pkill getmail
gi=$(ls -1A /home/user1/Mail/new | wc -l)
#echo gi=$gi >&2
[ "$(( gi == (i2-2) ))" -eq 1 ]
}

@test "idleidle" {
idle_rc ''
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 2.8
swaks --silent --server mail.example.test --from 'user2@example.test' --to 'user1+idle1@example.test' --header 'idle1' --body "idle1_sieve"
sleep 2.8
swaks --silent --server mail.example.test --from 'user2@example.test' --to 'user1+idle2@example.test' --header 'idle21' --body "idle2_sieve1"
sleep 2.8
swaks --silent --server mail.example.test --from 'user2@example.test' --to 'user1+idle2@example.test' --header 'idle22' --body "idle2_sieve2"
sleep 2.8
i1=$(ls -1a /var/mail/example.test/user1/.idle1/new | wc -l)
# echo i1=$i1 >&2
i2=$(ls -1a /var/mail/example.test/user1/.idle2/new | wc -l)
# echo i2=$i2 >&2
idle_rc 'mailboxes=("idle1","idle2")'
pkill getmail || true
sleep 1
getmail --rcfile=getmailrc --getmaildir=/home/user1  --idle= &
sleep 2
pkill getmail
gi=$(ls -1A /home/user1/Mail/new | wc -l)
#echo gi=$gi >&2
[ "$(( gi == (i1-2+i2-2) ))" -eq 1 ]
}
