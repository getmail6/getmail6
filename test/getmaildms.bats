: '

cd ..
make dockertest

'

save_random_env(){
   cat > $HOME/random.env << EOF
RANDOMTXT="$RANDOMTXT"
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
MAIL FROM: ${TESTEMAIL}
RCPT TO: ${TESTEMAIL}
DATA
Subject: test
The random text is:
${RANDOMTXT}
.
QUIT
EOF
save_random_env
sleep 2
}

_gm(){
getmail --rcfile=getmailrc --getmaildir=/home/user1
}

_grep(){
grep "$1" $MAILDIRIN/new/*
}

_verify(){
BASH_ENV=$HOME/random.env _grep "${RANDOMTXT}"
}

_clean(){
  rm -rf $MAILDIR
  mkdir -p $MAILDIRIN/{cur,tmp,new}
}

gm_ssl_params() {
  source prepare.sh
  _send
  _clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPSSLRetriever
port = 993
server = localhost
username = $TESTEMAIL
password = $TESTPSSWD
ca_certs = /tmp/docker-mailserver/ssl/demoCA/cacert.pem
certfile = /tmp/docker-mailserver/ssl/demoCA/cacert.pem
keyfile = /tmp/docker-mailserver/ssl/demoCA/private/cakey.pem
[destination]
type = Maildir
path = $MAILDIRIN/
[options]
read_all = false
delete = false

EOF
  _gm 2>&1 | grep "Permission denied"
}

maildir_rc() {
  source prepare.sh
  local TYP=$1
  local PORT=${PORTNR[$1]}
  local READALL=$2
  local DEL=$3
  local EXTRALINE=$4
  _clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = Simple${TYP}Retriever
server = localhost
username = $TESTEMAIL
port = $PORT
password = $TESTPSSWD
$EXTRALINE
[destination]
type = Maildir
path = $MAILDIRIN/
[options]
read_all = $READALL
delete = $DEL

EOF
}

gm_maildir() {
  _send
  maildir_rc "$@"
  _gm
  _verify
}

gm_procmail_filter() {
  source prepare.sh
  local TYP=$1
  local PORT=${PORTNR[$TYP]}
  _send
  _clean
  mkdir -p $MAILDIR/tests/{cur,tmp,new}
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = Simple${TYP}Retriever
server = localhost
username = $TESTEMAIL
port = $PORT
password = $TESTPSSWD
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
MAILDIR=$MAILDIR
DEFAULT=\$MAILDIR/INBOX
:0
* ^Subject:.*test.*
tests/
:0
\$DEFAULT/
EOF
_gm
}

just_rc() {
  source prepare.sh
  local RETRIEVER=$1
  local PORT=$2
  local MAX=$3
  local READALL=$4
  local DEL=$5
  _send
  _clean
  touch $MAILDIR/mbx
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = $TESTEMAIL
port = $PORT
password_command = ('/home/user1/passwordstub',)
[destination]
type = Mboxrd
path = $MAILDIR/mbx
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
echo $TESTPSSWD
EOF
  chmod +x /home/user1/passwordstub
}
gm_via_config(){
just_rc $@
_gm
local howmany=$(find $MAILDIR -iname '*' -type f | wc -l)
[ $((howmany>=1)) -gt 0 ]
}


multidropmail(){
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: ${TESTEMAIL}
RCPT TO: ${TESTEMAIL}
DATA
Subject: test
X-Envelope-To: ${TESTEMAIL}
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
sleep 2
}

multidrop_rc() {
  source prepare.sh
  local RETRIEVER=$1
  local PORT=$2
  multidropmail
  _clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = $TESTEMAIL
port = $PORT
password = $TESTPSSWD
envelope_recipient = X-Envelope-To
[destination]
type = Maildir
path = $MAILDIRIN/
[options]
read_all = True
delete = True
EOF
}

gm_multidrop() {
multidrop_rc "$@"
_gm
_verify
}

multisorter_rc() {
  source prepare.sh
  local RETRIEVER=$1
  local PORT=$2
  multidropmail
  _clean
  touch $MAILDIR/mbx
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = $TESTEMAIL
port = $PORT
password = $TESTPSSWD
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
path = $MAILDIRIN/
user = user1
[localuser2]
type = Mboxrd
path = $MAILDIR/mbx
[options]
read_all = True
delete = True
EOF
}
gm_multisorter() {
multisorter_rc "$@"
_gm
_verify
}

lmtp_rc() {
  source prepare.sh
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: user1@example.test
RCPT TO: ${TESTEMAIL}
DATA
From: user1@example.test
To: ${TESTEMAIL}
Subject: lmtp_rc
This is the test text:
я αβ один süße créme in Tromsœ.
.
QUIT
EOF
  sleep 2
  _clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPRetriever
server = localhost
username = $TESTEMAIL
password = $TESTPSSWD
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
  source prepare.sh
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: user1@example.test
RCPT TO: user2@example.test
DATA
From: user1@example.test
To: nonexistent-user@example.test
Subject: lmtp_override_x
This is the test text:
я αβ один süße créme in Tromsœ.
.
QUIT
EOF
  sleep 2
  _clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPRetriever
server = localhost
username = user2@example.test
port = 143
password = $TESTPSSWD
[destination]
type = MDA_lmtp
host = /var/run/dovecot/lmtp
override = $TESTEMAIL
[options]
read_all = True
delete = True
EOF
}

lmtp_override_fallback_rc() {
  source prepare.sh
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: user1@example.test
RCPT TO: user2@example.test
DATA
From: user1@example.test
To: nonexistent-user@example.test
Subject: lmtp_override_fallback_x
This is the test text:
я αβ один süße créme in Tromsœ.
.
QUIT
EOF
  sleep 2
  _clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPRetriever
server = localhost
username = user2@example.test
port = 143
password = $TESTPSSWD
[destination]
type = MDA_lmtp
host = /var/run/dovecot/lmtp
override = another-nonexistent-user
fallback = $TESTEMAIL
[options]
read_all = True
delete = True
EOF
}

imap_search_rc() {
  source prepare.sh
  local DELETE=$2
  local RETRIEVER=IMAPSSL
  local PORT=${PORTNR[$RETRIEVER]}
  local IMAPSEARCH=$1
  local IMAPDELETE="(\Seen)"
  [[ "$1" == "ALL" ]] && _send
  [[ "$1" == "ALL" ]] && IMAPDELETE=""
  [[ "$1" == "ALL" ]] && IMAPSEARCH=""
  _clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = Simple${RETRIEVER}Retriever
server = localhost
username = $TESTEMAIL
port = $PORT
password = $TESTPSSWD
imap_search = $IMAPSEARCH
imap_on_delete = $IMAPDELETE
[destination]
type = Maildir
path = $MAILDIRIN/
[options]
read_all = true
delete = $DELETE
EOF
}

mark_read_rc() {
  source prepare.sh
  local RETRIEVER=IMAPSSL
  local PORT=${PORTNR[$RETRIEVER]}
  _clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = Simple${RETRIEVER}Retriever
server = localhost
username = $TESTEMAIL
port = $PORT
password = $TESTPSSWD
[destination]
type = Maildir
path = $MAILDIRIN/
[options]
mark_read = true
EOF
}



gm_uid_cache(){
gm_maildir IMAP false false uid_cache=uid.txt
sleep 1
n1=$(cat /home/user1/uid.txt | cut -d" " -f 3)
gm_maildir IMAP false false uid_cache=uid.txt
sleep 1
n2=$(cat /home/user1/uid.txt | cut -d" " -f 3)
[[ $(( n2 - n1 )) != 0 ]]
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
gm_ssl_params
}

@test "SimplePOP3Retriever, destination Maildir" {
gm_maildir POP3 true true
}
@test "SimplePOP3SSLRetriever, destination Maildir" {
gm_maildir POP3SSL true true
}
@test "SimpleIMAPRetriever, destination Maildir" {
gm_maildir IMAP true true record_mailbox=true
}
@test "SimpleIMAPSSLRetriever, destination Maildir" {
gm_maildir IMAPSSL true true
}
@test "SimpleIMAPRetriever, destination Maildir, uid_cache=uid.txt" {
gm_uid_cache
}
@test "SimpleIMAPRetriever, destination Maildir, uid_cache=true" {
gm_maildir IMAP false false uid_cache=true
}

@test "SimplePOP3Retriever, destination MDA_external (procmail), filter spamassassin clamav" {
gm_procmail_filter POP3
}
@test "SimplePOP3SSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
gm_procmail_filter POP3SSL
}
@test "SimpleIMAPRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
gm_procmail_filter IMAP
}
@test "SimpleIMAPSSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
gm_procmail_filter IMAPSSL
}

@test "BrokenUIDLPOP3Retriever 110 800 False False" {
gm_via_config BrokenUIDLPOP3Retriever 110 800 False False
}
@test "BrokenUIDLPOP3Retriever 110 900 True  False" {
gm_via_config BrokenUIDLPOP3Retriever 110 900 True  False
}
@test "BrokenUIDLPOP3SSLRetriever 995 800 0 0" {
gm_via_config BrokenUIDLPOP3SSLRetriever 995 800 0 0
}
@test "BrokenUIDLPOP3SSLRetriever 995 900 1 1" {
gm_via_config BrokenUIDLPOP3SSLRetriever 995 900 1 1
}
@test "SimpleIMAPRetriever 143 800 false true" {
gm_via_config SimpleIMAPRetriever 143 800 false true
}
@test "SimpleIMAPRetriever 143 900 false true" {
gm_via_config SimpleIMAPRetriever 143 900 false true
}
@test "SimpleIMAPSSLRetriever 993 800 False False" {
gm_via_config SimpleIMAPSSLRetriever 993 800 False False
}
@test "SimpleIMAPSSLRetriever 993 900 True  True" {
gm_via_config SimpleIMAPSSLRetriever 993 900 True  True
}


@test "SimplePOP3Retriever 110" {
gm_multidrop SimplePOP3Retriever 110
}
@test "MultidropPOP3Retriever 110" {
gm_multidrop MultidropPOP3Retriever 110
}
@test "SimplePOP3SSLRetriever 995" {
gm_multidrop SimplePOP3SSLRetriever 995
}
@test "MultidropPOP3SSLRetriever 995" {
gm_multidrop MultidropPOP3SSLRetriever 995
}
@test "SimpleIMAPRetriever 143" {
gm_multidrop SimpleIMAPRetriever 143
}
@test "MultidropIMAPRetriever 143" {
gm_multidrop MultidropIMAPRetriever 143
}
@test "SimpleIMAPSSLRetriever 993" {
gm_multidrop SimpleIMAPSSLRetriever 993
}
@test "MultidropIMAPSSLRetriever 993" {
gm_multidrop MultidropIMAPSSLRetriever 993
}


@test "MultidropPOP3Retriever, Multisorter" {
gm_multisorter MultidropPOP3Retriever 110
}
@test "MultidropPOP3SSLRetriever, Multisorter" {
gm_multisorter MultidropPOP3SSLRetriever 995
}
@test "MultidropIMAPRetriever, Multisorter" {
gm_multisorter MultidropIMAPRetriever 143
}
@test "MultidropIMAPSSLRetriever, Multisorter" {
gm_multisorter MultidropIMAPSSLRetriever 993
}

@test "MDA lmtp_rc" {
lmtp_rc
#doveadm purge -A
_gm
#grep "Subject: lmtp_rc" /var/mail/example.test/user1/cur/*
}
@test "MDA lmtp_override_x" {
lmtp_override_rc
#doveadm purge -A
_gm
#grep "Subject: lmtp_override_x" /var/mail/example.test/user2/cur/*
}
@test "MDA lmtp_override_fallback_x" {
lmtp_override_fallback_rc
#doveadm purge -A
_gm
#grep "Subject: lmtp_override_fallback_x" /var/mail/example.test/user1/cur/*
}

#TODO check
## @test "SimpleIMAPSSLRetriever, imap_search" {
## _send
## imap_search_rc ALL false
## _gm
## _verify
## _grep utf-8
## imap_search_rc UNSEEN true
## _gm
## _verify
## _grep utf-8
## imap_search_rc UNSEEN true
## _gm
## # TODO check no unseen
## imap_search_rc ALL true
## _gm
## _verify
## _grep utf-8
## imap_search_rc SEEN true
## _gm
## _verify
## _grep utf-8
## _send
## mark_read_rc
## _gm
## _verify
## _grep utf-8
## }
## 
## @test "IMAP override via command line -s" {
## _send
## imap_search_rc ALL true
## getmail --rcfile=getmailrc --getmaildir=/home/user1 -s,
## _grep "$RANDOMTXT"
## _clean
## #(Unseen \Seen) so this time 0
## getmail --rcfile=getmailrc --getmaildir=/home/user1 -s,
## [[ "$(grep "$RANDOMTXT" $MAILDIRIN/new/* -l | wc -l)" == "0" ]]
## _clean
## getmail --rcfile=getmailrc --getmaildir=/home/user1 --searchset UNSEEN --searchset ,SEEN
## [[ "$(grep "$RANDOMTXT" $MAILDIRIN/new/* -l | wc -l)" == "0" ]]
## _clean
## getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "FROM \"domain\" ,SEEN"
## _grep "$RANDOMTXT"
## _clean
## getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "TEXT \"Troms\" ,SEEN"
## _grep "$RANDOMTXT"
## _clean
## getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "TEXT \"NotThere\""
## [[ "$(grep "$RANDOMTXT" $MAILDIRIN/new/* -l | wc -l)" == "0" ]]
## getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "ALL ,SEEN"
## _grep "$RANDOMTXT"
## _clean
## getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "ALL"
## _grep "$RANDOMTXT"
## }
## 
## @test "getmail_mbox test" {
## _clean
## touch $MAILDIR/mbx
## echo 'βσSß' | getmail_mbox $MAILDIR/mbx
## grep 'βσSß' $MAILDIR/mbx
## 
## }
## 
## @test "getmail_maildir test" {
## gm_maildir "POP3 true true"
## echo 'βσSß' | getmail_maildir $MAILDIRIN/
## _grep 'βσSß'
## }
## 
## @test "getmail_fetch test" {
## source prepare.sh
## PORT=${PORTNR["POP3"]}
## _send
## _clean
## getmail_fetch -p $PORT localhost $TESTEMAIL $TESTPSSWD $MAILDIRIN/
## _verify
## }
## 
## @test "idle1" {
## idle_mailboxes
## getmail_idle '("idle1",)'
## n_idle 99
## }
## 
