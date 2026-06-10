#!/usr/bin/env bash
# shellcheck disable=0..999999

: '

cd getmail6
make test

'

# cwd = getmail/test
CWD="$(pwd)"
# echo $CWD
GETMAIL6REPO=${CWD%/*}

export TESTEMAIL="user1@example.test"
export TESTPSSWD="ТЕСТПАСС"
#export TESTPSSWD="testpass"
export CONTAINERNAME="mail.example.test"
#echo $TESTEMAIL $TESTPSSWD $CONTAINERNAME


function restart_dms() {
docker compose down
docker compose up --detach --force-recreate
local STARTTIME=${SECONDS}
until bash -c "docker logs ${CONTAINERNAME} | grep 'is up and running'"; do
  sleep 1
  echo "Waiting a second" >&2
  if [[ $(( SECONDS - STARTTIME )) -gt 66 ]]; then
    echo "Timed out on command: ${*}" >&2
    return 1
  fi
done
docker exec -u 0 -t ${CONTAINERNAME} bash -c "freshclam &> /dev/null"
docker exec -u 0 -t ${CONTAINERNAME} bash -c "cd /tmp/docker-mailserver/getmail6/test && source prepare_test.sh && dms_install_getmail"
}

dms_install_getmail() {
apt-get -qq remove getmail6
apt-get -qq update
apt-get -qq install iputils-ping nmap make python3 python3-pip bats
#apt-get -qq install jq vim git
cd /tmp/docker-mailserver/getmail6/test
source prepare_test.sh
cd /tmp/docker-mailserver/getmail6
pip3 install -e . --break-system-packages
getmail --version
yes | setup email del $TESTEMAIL &> /dev/null
yes | setup email del user2 &> /dev/null
setup email add $TESTEMAIL $TESTPSSWD &> /dev/null
setup email add user2@example.test user2 &> /dev/null
useradd -m -s /bin/bash user1 &> /dev/null
usermod -a -G postfix user1
useradd -m -s /bin/bash user2 &> /dev/null
usermod -a -G postfix user2
}


d_prompt(){
docker exec -u $1 -it $CONTAINERNAME bash
}

#---- for getmail.bats ----#

export TMPMAIL=/home/user1/Mail
export MAILDIR=$TMPMAIL/$TESTEMAIL
export MAILDIRIN=$MAILDIR/INBOX
declare -A PORTNR
PORTNR["POP3"]=110
PORTNR["IMAP"]=143
PORTNR["IMAPSSL"]=993
PORTNR["POP3SSL"]=995
PORTNR["SMTP"]=25
PORTNR["SMTPSSL"]=587
export PORTNR

d_info(){
   cat > $HOME/d_info.sh << EOF
RANDOMTXT="$RANDOMTXT"
EOF
}

d_docker(){
docker exec -u user1 $CONTAINERNAME bash -c "cd /tmp/docker-mailserver/getmail6/test
source prepare_test.sh
$@
"
}

ports_test(){
nmap -n -Pn localhost -p25 -oG - | grep '/open/'
nmap -n -Pn localhost -p143 -oG - | grep '/open/'
nmap -n -Pn localhost -p587 -oG - | grep '/open/'
nmap -n -Pn localhost -p993 -oG - | grep '/open/'
}
d_ports_test(){
d_docker ports_test
}

randomtext(){
tr -dc A-Za-z0-9 </dev/urandom | head -c $1; echo
}

testmail(){
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
d_info
sleep 2
}

retrieve(){
getmail --rcfile=getmailrc --getmaildir=/home/user1
sleep 1
}

grep_mail(){
grep "$1" $MAILDIRIN/new/*
}

checkmail(){
BASH_ENV=$HOME/d_info.sh grep_mail "${RANDOMTXT}"
}

mail_clean(){
  rm -rf $MAILDIR
  mkdir -p $MAILDIRIN/{cur,tmp,new}
}

ssl_parameters_imap_maildir() {
  testmail
  mail_clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleSSLRetriever
server = localhost
port = 993
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
  retrieve
  checkmail
}

dest_maildir() {
  TYP=$1
  PORT=${PORTNR[$1]}
  READALL=$2
  DEL=$3
  EXTRALINE=$4
  mail_clean
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

simple_dest_maildir() {
  testmail
  dest_maildir "$@"
  retrieve
  checkmail
}

simple_dest_procmail_filter() {
  TYP=$1
  PORT=${PORTNR[$TYP]}
  testmail
  mail_clean
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
retrieve
checkmail
}

just_configure() {
  RETRIEVER=$1
  PORT=$2
  MAX=$3
  READALL=$4
  DEL=$5
  testmail
  mail_clean
  touch $MAILDIR/mbx
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = $TESTEMAIL
port = $PORT
password_command = ('/home/user1/pass',)
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
message_log = ~/getmail_message.log
EOF
  cat > /home/user1/pass <<EOF
#!/bin/bash
echo $TESTPSSWD
EOF
  chmod +x /home/user1/pass
}
config_test(){
just_configure "$@"
retrieve
checkmail
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
sleep 1
}

multidrop_configure() {
  RETRIEVER=$1
  PORT=$2
  multidropmail
  mail_clean
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

multidrop_test() {
multidrop_configure "$@"
retrieve
}

multisorter_configure() {
  RETRIEVER=$1
  PORT=$2
  multidropmail
  mail_clean
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
multisorter_test() {
multisorter_configure "$@"
retrieve
}

lmtp_test_py() {
  RETRIEVER=$1
  PORT=$2
  testmail
  mail_clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = ${RETRIEVER}
server = localhost
username = $TESTEMAIL
port = $PORT
password = $TESTPSSWD
[destination]
type = MDA_lmtp
host = 127.0.0.1
port = 23218
[options]
read_all = True
delete = True
EOF
  cat > /home/user1/lmtpd.py <<EOF
from smtpd import SMTPChannel, SMTPServer
import asyncore
class LMTPChannel(SMTPChannel):
  def smtp_LHLO(self, arg):
    self.smtp_HELO(arg)
class LMTPServer(SMTPServer):
  def __init__(self, localaddr, remoteaddr):
    SMTPServer.__init__(self, localaddr, remoteaddr)
  def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
    return
  def handle_accept(self):
    conn, addr = self.accept()
    channel = LMTPChannel(self, conn, addr)
server = LMTPServer(('localhost', 23218), None)
asyncore.loop()
EOF
  python3 /home/user1/lmtpd.py &
}
d_lmtp_test_py() {
d_docker "lmtp_test_py $@"
}

lmtp_test_unix_socket() {
  RETRIEVER=$1
  PORT=$2
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: user1@example.test
RCPT TO: ${TESTEMAIL}
DATA
From: user1@example.test
To: ${TESTEMAIL}
Subject: lmtp_test_unix_socket_x
This is the test text:
я αβ один süße créme in Tromsœ.
.
QUIT
EOF
  sleep 1
  mail_clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = ${RETRIEVER}
server = localhost
username = $TESTEMAIL
port = $PORT
password = $TESTPSSWD
[destination]
type = MDA_lmtp
# use docker-mailserver/dovecot's lmtp listener
host = /var/run/dovecot/lmtp
[options]
read_all = True
delete = True
EOF
}
d_lmtp_test_unix_socket() {
d_docker "lmtp_test_unix_socket $@"
}

lmtp_test_override() {
  RETRIEVER=$1
  PORT=$2
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: user1@example.test
RCPT TO: user2@example.test
DATA
From: user1@example.test
To: nonexistent-user@example.test
Subject: lmtp_test_override_x
This is the test text:
я αβ один süße créme in Tromsœ.
.
QUIT
EOF
  sleep 1
  mail_clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = ${RETRIEVER}
server = localhost
username = user2@example.test
port = $PORT
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
d_lmtp_test_override() {
d_docker "lmtp_test_override $@"
}

lmtp_test_override_fallback() {
  RETRIEVER=$1
  PORT=$2
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: user1@example.test
RCPT TO: user2@example.test
DATA
From: user1@example.test
To: nonexistent-user@example.test
Subject: lmtp_test_override_fallback_x
This is the test text:
я αβ один süße créme in Tromsœ.
.
QUIT
EOF
  sleep 1
  mail_clean
  cat > /home/user1/getmailrc <<EOF
[retriever]
type = ${RETRIEVER}
server = localhost
username = user2@example.test
port = $PORT
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
d_lmtp_test_override_fallback() {
d_docker "lmtp_test_override_fallback $@"
}

imap_search() {
  DELETE=$2
  RETRIEVER=IMAPSSL
  PORT=${PORTNR[$RETRIEVER]}
  IMAPSEARCH=$1
  IMAPDELETE="(\Seen)"
  [[ "$1" == "ALL" ]] && testmail
  [[ "$1" == "ALL" ]] && IMAPDELETE=""
  [[ "$1" == "ALL" ]] && IMAPSEARCH=""
  mail_clean
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
d_imap_search() {
d_docker "imap_search $@"
}


mark_read() {
  RETRIEVER=IMAPSSL
  PORT=${PORTNR[$RETRIEVER]}
  [[ "$1" == "mark_read" ]] && testmail
  mail_clean
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
d_mark_read() {
d_docker "mark_read $@"
}

override_test(){
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s,
grep_mail "$RANDOMTXT"
mail_clean
#(Unseen \Seen) so this time 0
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s,
[[ "$(grep "$RANDOMTXT" $MAILDIRIN/new/* -l | wc -l)" == "0" ]]
mail_clean
getmail --rcfile=getmailrc --getmaildir=/home/user1 --searchset UNSEEN --searchset ,SEEN
[[ "$(grep "$RANDOMTXT" $MAILDIRIN/new/* -l | wc -l)" == "0" ]]
mail_clean
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "FROM \"domain\" ,SEEN"
grep_mail "$RANDOMTXT"
mail_clean
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "TEXT \"Troms\" ,SEEN"
grep_mail "$RANDOMTXT"
mail_clean
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "TEXT \"NotThere\""
[[ "$(grep "$RANDOMTXT" $MAILDIRIN/new/* -l | wc -l)" == "0" ]]
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "ALL ,SEEN"
grep_mail "$RANDOMTXT"
mail_clean
getmail --rcfile=getmailrc --getmaildir=/home/user1 -s "ALL"
grep_mail "$RANDOMTXT"
}

d_override_test() {
d_docker "imap_search ALL true"
d_docker override_test
}

local_mbox(){
mail_clean
touch $MAILDIR/mbx
echo 'βσSß' | getmail_mbox $MAILDIR/mbx
grep 'βσSß' $MAILDIR/mbx
}

d_local_mbox(){
d_docker local_mbox
}

local_maildir(){
simple_dest_maildir POP3
echo 'βσSß' | getmail_maildir $MAILDIRIN/
grep_mail 'βσSß'
}

d_local_maildir(){
d_docker local_maildir
}

fetch_maildir() {
PORT=${PORTNR["POP3"]}
testmail
mail_clean
getmail_fetch -p $PORT localhost $TESTEMAIL $TESTPSSWD $MAILDIRIN/
checkmail
}
d_fetch_maildir(){
d_docker fetch_maildir
}


getmail_idle(){
rm -rf /home/user1/Mail
mkdir -p /home/user1/Mail/{cur,tmp,new}
cat > /home/user1/getmailrc <<EOF
[retriever]
type = SimpleIMAPRetriever
server = localhost
username=${TESTEMAIL}
password=${TESTPSSWD}
[destination]
type = Maildir
path = /home/user1/Mail/
[options]
read_all = true
delete = true
EOF
getmail --rcfile=getmailrc --getmaildir=/home/user1  --idle=
#getmail --rcfile=getmailrc --getmaildir=/home/user1  --idle=idle1
#getmail -vvv --rcfile=getmailrc --getmaildir=/home/user1  --idle=idle2
}
d_getmail_idle(){
  d_docker getmail_idle
}

d_idle_mailboxes(){
docker exec -u 0 $CONTAINERNAME bash -c "
cat > /usr/lib/dovecot/sieve-global/before/plus_at_sieve.sieve <<EOF
echo 'require [\"envelope\", \"fileinto\", \"mailbox\", \"subaddress\", \"variables\"];
if envelope :detail :matches \"to\" \"idle1\" {
  if mailboxexists \"idle1\" {
    fileinto \"idle1\";
  } else {
    fileinto :create \"idle1\";
  }
}
if envelope :detail :matches \"to\" \"idle2\" {
  if mailboxexists \"idle2\" {
    fileinto \"idle2\";
  } else {
    fileinto :create \"idle2\";
  }
}
EOF
rm -rf ~/.dovecot.sieve
ln -s /usr/lib/dovecot/sieve-global/before/plus_at_sieve.sieve ~/.dovecot.sieve
cat >> /etc/dovecot/conf.d/10-mail.conf <<EOF
mail_uid = 5000
mail_gid = 5000
log_debug = category=sieve
EOF
dovecot reload
"
docker exec -u 0 $CONTAINERNAME bash -c "
cd /tmp/docker-mailserver/getmail6/test
source prepare_test.sh
doveadm mailbox create -u '$TESTEMAIL' 'idle1' 2>/dev/null
doveadm mailbox create -u '$TESTEMAIL' 'idle2' 2>/dev/null
testmail
sleep 1
doveadm move -u '$TESTEMAIL' 'idle1' mailbox 'INBOX' all
sleep 1
testmail
sleep 2
testmail
sleep 1
doveadm move -u '$TESTEMAIL' 'idle2' mailbox 'INBOX' all
echo idle1
ls -1A /var/mail/example.test/user1/.idle1/new
echo idle2
ls -1A /var/mail/example.test/user1/.idle2/new
"
}

n_idle(){
  idlemails=$(ls /home/user1/Mail/new | wc -l)
  return $idlemails
}
d_n_idle(){
  x=$(d_docker check_n_idle)
  xwant=$1
  return $((x==xwant))
}

check_uid_cache(){
simple_dest_maildir IMAP false false uid_cache=uid.txt
sleep 1
n1=$(cat /home/user1/uid.txt | cut -d" " -f 3)
simple_dest_maildir IMAP false false uid_cache=uid.txt
sleep 1
n2=$(cat /home/user1/uid.txt | cut -d" " -f 3)
[[ $(( n2 - n1 )) != 0 ]]
}


check_lmtp_delivery() {
checkmail
maildir_clean_retrieve IMAP
checkmail
}

check_mda_lmtp(){
lmtp_test_py SimpleIMAPRetriever 143
retrieve
lmtp_test_unix_socket SimpleIMAPRetriever 143
retrieve
check_lmtp_delivery
grep_mail "Subject: lmtp_test_unix_socket_x"
lmtp_test_override SimpleIMAPRetriever 143
retrieve
check_lmtp_delivery
grep_mail "Subject: lmtp_test_override_x"
lmtp_test_override_fallback SimpleIMAPRetriever 143
retrieve
check_lmtp_delivery
grep_mail "Subject: lmtp_test_override_fallback_x"
}


