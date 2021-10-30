#!/usr/bin/env bash

# cwd = getmail/test

DOCKER_CONFIG="/tmp/docker-mailserver"
HOST_CONFIG="/tmp/mailserver/config"

: '
#----------------------------------------------------------

# requires pytest, docker, docker-compose < V2 (V2 does not work)

cd getmail6

# run all tests
make test
# run only python2 tests
make test2
# run only python3 tests
make test3

# force renew of /tmp/mailserver when running `make test`:
rm /tmp/mailserver/python?

# manual commands as root on docker
#----------------------------------------------------------

cd test
. ./prepare_test.sh
export PYVER=3
clone_mailserver

# check mailserver after clone_mailserver
/tmp/mailserver
docker-compose ps
docker-compose up -d

# interactive as root
docker exec -u 0 -it mail.domain.tld bash

# install in mailserver
apt-get update
apt-get -y install git make procmail iputils-ping nmap python-pip python3-pip vim

#install getmail6 copied via prepare_test.sh copy_tests
cd /tmp/docker-mailserver/getmail6
cat setup.py | sed "s/^\s*download_url.*//p" | python2 - install
cat setup.py | sed "s/^\s*download_url.*//p" | python3 - install

# self_sign
/tmp/docker-mailserver/self_sign.sh

# TESTEMAIL from self_sign.sh
source /tmp/docker-mailserver/self_sign.sh

# add email
which addmailuser
ls /usr/local/bin/*mail*
echo $TESTEMAIL $PSS
addmailuser $TESTEMAIL $PSS
listmailuser

# delete
delmailuser $TESTEMAIL
exit

# run commands as user on docker
#----------------------------------------------------------

## prepare_test.sh used in test_getmail_with_docker_mailserver.bats
cd /home/roland/mine/getmail6/test
source prepare_test.sh
echo $GETMAIL6REPO
yes | cp test_getmail_with_docker_mailserver.bats /tmp/mailserver/test/test_getmail_with_docker_mailserver.bats
yes | cp prepare_test.sh /tmp/mailserver/config/getmail6/test/prepare_test.sh
cd /tmp/mailserver
  d_simple_dest_maildir POP3
  d_imap_search "ALL true"
  d_retrieve
  d_override_test
  d_config_test "BrokenUIDLPOP3Retriever 110 800 False False"
  d_docker "cat /home/getmail/getmail"
  d_docker "rm /home/getmail/getmail"

docker-compose down
copy_tests
docker_up

cd /tmp/mailserver
docker exec -u getmail -it mail.domain.tld bash
  cat /home/getmail/getmail
  ls /home/getmail
cd /tmp/docker-mailserver/getmail6/test/
source prepare_test.sh
echo ${PORTNR[IMAPSSL]}

simple_dest_maildir IMAPSSL
grep_mail "$TESTGREP" && echo "success expected"
grep_mail utf_8 || echo "fail expected"
imap_search ALL false
imap_search UNSEEN true
imap_search ALL true
config_test BrokenUIDLPOP3Retriever 110 800 False False

exit
'

#getmail6/test
CWD="$(pwd)"
# echo $CWD
GETMAIL6REPO=${CWD%/*}

source self_sign.sh
export PSS TESTEMAIL NAME

MAILSERVERSOURCE="${HOME}/msrc/docker-mailserver"
if [[ ! -d "$MAILSERVERSOURCE" ]]; then
    MAILSERVERSOURCE='https://github.com/docker-mailserver/docker-mailserver'
fi
# echo $MAILSERVERSOURCE

PYVER=3

function clone_mailserver() {
    new_clone="no"
    # clone to reuse bats scripts
    if [[ ! -f /tmp/mailserver/python$PYVER ]]; then
        if [[ -d /tmp/mailserver ]]; then
            cd /tmp/mailserver
            docker-compose down &>/dev/null
            cd $CWD
            echo "need sudo to rm /tmp/mailserver"
            sudo rm -rf /tmp/mailserver
        fi
        git clone --recursive $MAILSERVERSOURCE /tmp/mailserver
        cd /tmp/mailserver
        git checkout tags/v9.0.1
        touch /tmp/mailserver/python$PYVER
        yes | cp -f $CWD/docker-compose.yml /tmp/mailserver/
        cat > /tmp/mailserver/.env << EOF
HOSTNAME="mail"
DOMAINNAME="domain.tld"
CONTAINER_NAME="${NAME}"
SELINUX_LABEL=""
EOF
        chmod a+x /tmp/mailserver/setup.sh
        new_clone="yes"
    fi
}

function copy_tests() {
    yes | cp -f $GETMAIL6REPO/test/*.bats /tmp/mailserver/test/
    yes | cp -f $GETMAIL6REPO/test/self_sign.sh /tmp/mailserver/config/

    cd  /tmp/mailserver/config
    sudo rm -rf getmail6
    cp -R $GETMAIL6REPO getmail6
}

function docker_up() {
    cd  /tmp/mailserver

    with_up="no"
    if ! docker exec -t ${NAME} bash -c ":" &>/dev/null ; then
        docker-compose up -d
        docker-compose ps
        with_up="yes"
    fi

    if [[ "$new_clone" == "yes" ]]; then
        docker exec -u 0 -t ${NAME} bash -c "addmailuser ${TESTEMAIL} ${PSS}"
        docker exec -u 0 -t ${NAME} bash -c "/tmp/docker-mailserver/self_sign.sh &> /dev/null"
        docker-compose down
        docker-compose up -d
        with_up="yes"
    fi

    if [[ "$with_up" == "yes" ]]; then
        docker exec -u 0 -t mail.domain.tld bash -c " \
        apt-get update &>/dev/null && \
        apt-get -y install git make procmail iputils-ping nmap python-pip python3-pip &>/dev/null"
        docker exec -u 0 -t ${NAME} bash -c "freshclam &> /dev/null"
        docker exec -u 0 -t ${NAME} bash -c "useradd -m -s /bin/bash getmail"
        #pip2 is 2.7.16
        #pip3 is 3.7.3
        docker exec -u 0 -t ${NAME} bash -c "yes | pip$PYVER uninstall getmail6"
        #docker exec -u 0 -t ${NAME} bash -c "cd /tmp/docker-mailserver/getmail6 && cat setup.py | sed 's/^\s*download_url.*//p' | python$PYVER - install"
        docker exec -u 0 -t ${NAME} bash -c "cd /tmp/docker-mailserver/getmail6 && pip$PYVER install -e ."
    fi
}

#---- for test_getmail_with_docker_mailserver.bats ----#

export TMPMAIL=/home/getmail/Mail
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

d_docker(){
cd /tmp/mailserver
docker exec -u getmail $NAME bash -c "cd /tmp/docker-mailserver/getmail6/test
source prepare_test.sh
$@
"
}

ports_test(){
nmap -p25 localhost
nmap -p143 localhost
nmap -p587 localhost
nmap -p993 localhost
}
d_ports_test(){
d_docker ports_test
}

export TESTGREP="Troms"
testmail(){
  nc 0.0.0.0 25 << EOF
HELO mail.localhost
MAIL FROM: ${TESTEMAIL}
RCPT TO: ${TESTEMAIL}
DATA
Subject: test
This is the test text:
я αβ один süße créme in Tromsœ.
.
QUIT
EOF
sleep 1
}
d_testmail(){
d_docker testmail
}

retrieve(){
getmail --rcfile=getmail --getmaildir=/home/getmail
}
d_retrieve(){
  d_docker retrieve
}

mail_clean(){
  rm -rf $MAILDIR
  mkdir -p $MAILDIRIN/{cur,tmp,new}
}

simple_dest_maildir() {
  RETRIEVER=$1
  PORT=${PORTNR[$1]}
  testmail
  mail_clean
  cat > /home/getmail/getmail <<EOF
[retriever]
type = Simple${RETRIEVER}Retriever
server = localhost
username = $TESTEMAIL
port = $PORT
password = $PSS
record_mailbox = True
[destination]
type = Maildir
path = $MAILDIRIN/
[options]
read_all = true
delete = true
EOF
retrieve
grep_mail "$TESTGREP"
}
d_simple_dest_maildir() {
d_docker "simple_dest_maildir $@"
}

grep_mail(){
grep "$1" $MAILDIRIN/new/*
}
d_grep_mail(){
d_docker "grep_mail $@"
}


simple_dest_procmail_filter() {
  RETRIEVER=$1
  PORT=${PORTNR[$RETRIEVER]}
  testmail
  mail_clean
  mkdir -p $MAILDIR/tests/{cur,tmp,new}
  cat > /home/getmail/getmail <<EOF
[retriever]
type = Simple${RETRIEVER}Retriever
server = localhost
username = $TESTEMAIL
port = $PORT
password = $PSS
[destination]
type = MDA_external
path = /usr/bin/procmail
arguments = ('-f', '%(sender)', '-m', '/home/getmail/procmail')
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
  cat > /home/getmail/procmail <<EOF
MAILDIR=$MAILDIR
DEFAULT=\$MAILDIR/INBOX
:0
* ^Subject:.*test.*
tests/
:0
\$DEFAULT/
EOF
}
d_simple_dest_procmail_filter(){
d_docker "simple_dest_procmail_filter $@"
}

config_test() {
  RETRIEVER=$1
  PORT=$2
  MAX=$3
  READALL=$4
  DEL=$5
  testmail
  mail_clean
  touch $MAILDIR/mbx
  cat > /home/getmail/getmail <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = $TESTEMAIL
port = $PORT
password_command = ('/home/getmail/pass',)
[destination]
type = Mboxrd
path = $MAILDIR/mbx
[options]
read_all = $READALL
delete = $DEL
max_message_size = $MAX
delete_after = 1
delete_bigger_than = 800
max_messages_per_session = 9
max_bytes_per_session = 3000
verbose = 3
delivered_to = false
received = false
message_log_verbose = true
message_log_syslog = true
fingerprint = true
logfile = /home/getmail/getmail.log
message_log = ~/getmail_message.log
EOF
  cat > /home/getmail/pass <<EOF
#!/bin/bash
echo $PSS
EOF
  chmod +x /home/getmail/pass
}
d_config_test(){
d_docker "config_test $@"
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
d_multidropmail(){
d_docker multidropmail
}

multidrop_test() {
  RETRIEVER=$1
  PORT=$2
  multidropmail
  mail_clean
  cat > /home/getmail/getmail <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = $TESTEMAIL
port = $PORT
password = $PSS
envelope_recipient = X-Envelope-To
[destination]
type = Maildir
path = $MAILDIRIN/
[options]
read_all = True
delete = True
EOF
}
d_multidrop_test() {
d_docker "multidrop_test $@"
}

multisorter_test() {
  RETRIEVER=$1
  PORT=$2
  multidropmail
  mail_clean
  touch $MAILDIR/mbx
  cat > /home/getmail/getmail <<EOF
[retriever]
type = $RETRIEVER
server = localhost
username = $TESTEMAIL
port = $PORT
password = $PSS
envelope_recipient = X-Envelope-To
[destination]
type = MultiSorter
default = [localuser1]
locals = (
     ('address@', '[localuser1]'),
     ('address@', '[localuser2]'),
     )
[localuser1]
type = Maildir
path = $MAILDIRIN/
user = getmail
[localuser2]
type = Mboxrd
path = $MAILDIR/mbx
[options]
read_all = True
delete = True
EOF
}
d_multisorter_test() {
d_docker "multisorter_test $@"
}

lmtp_test() {
  RETRIEVER=$1
  PORT=$2
if head `which getmail` | grep 'python3' ; then
  testmail
  mail_clean
  cat > /home/getmail/getmail <<EOF
[retriever]
type = ${RETRIEVER}
server = localhost
username = $TESTEMAIL
port = $PORT
password = $PSS
[destination]
#type = Maildir
#path = $MAILDIRIN/
type = MDA_lmtp
host = 127.0.0.1
port = 23218
[options]
read_all = True
delete = True
EOF
  cat > /home/getmail/lmtpd.py <<EOF
from smtpd import SMTPChannel, SMTPServer
import asyncore
class LMTPChannel(SMTPChannel):
  def smtp_LHLO(self, arg):
    self.smtp_HELO(arg)
class LMTPServer(SMTPServer):
  def __init__(self, localaddr, remoteaddr):
    SMTPServer.__init__(self, localaddr, remoteaddr)
  def process_message(self, peer, mailfrom, rcpttos, data):
    return
  def handle_accept(self):
    conn, addr = self.accept()
    channel = LMTPChannel(self, conn, addr)
server = LMTPServer(('localhost', 23218), None)
asyncore.loop()
EOF
  python3 /home/getmail/lmtpd.py &
fi
}
d_lmtp_test() {
d_docker "lmtp_test $@"
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
  cat > /home/getmail/getmail <<EOF
[retriever]
type = Simple${RETRIEVER}Retriever
server = localhost
username = $TESTEMAIL
port = $PORT
password = $PSS
record_mailbox = True
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

override_test(){
getmail --rcfile=getmail --getmaildir=/home/getmail -s,
grep_mail "$TESTGREP"
mail_clean
#(Unseen \Seen) so this time 0
getmail --rcfile=getmail --getmaildir=/home/getmail -s,
[[ "$(grep "$TESTGREP" $MAILDIRIN/new/* -l | wc -l)" == "0" ]]
mail_clean
getmail --rcfile=getmail --getmaildir=/home/getmail --searchset UNSEEN --searchset ,SEEN
[[ "$(grep "$TESTGREP" $MAILDIRIN/new/* -l | wc -l)" == "0" ]]
mail_clean
getmail --rcfile=getmail --getmaildir=/home/getmail -s "FROM \"domain\" ,SEEN"
grep_mail "$TESTGREP"
mail_clean
getmail --rcfile=getmail --getmaildir=/home/getmail -s "TEXT \"Troms\" ,SEEN"
grep_mail "$TESTGREP"
mail_clean
getmail --rcfile=getmail --getmaildir=/home/getmail -s "TEXT \"NotThere\""
[[ "$(grep "$TESTGREP" $MAILDIRIN/new/* -l | wc -l)" == "0" ]]
getmail --rcfile=getmail --getmaildir=/home/getmail -s "ALL ,SEEN"
grep_mail "$TESTGREP"
mail_clean
getmail --rcfile=getmail --getmaildir=/home/getmail -s "ALL"
grep_mail "$TESTGREP"
}

d_override_test() {
d_docker "imap_search ALL true"
d_docker override_test
}


d_local_mbox(){
d_docker "mail_clean && \
  touch $MAILDIR/mbx && \
  echo 'βσSß' | getmail_mbox $MAILDIR/mbx && \
  grep 'βσSß' $MAILDIR/mbx"
}

d_local_maildir(){
d_docker "simple_dest_maildir POP3 \
  echo 'βσSß' | getmail_maildir $MAILDIRIN/ && \
  grep_mail 'βσSß'"
}

fetch_maildir() {
  PORT=${PORTNR["POP3"]}
  testmail
  mail_clean
  getmail_fetch -p $PORT localhost $TESTEMAIL $PSS $MAILDIRIN/
  grep_mail "$TESTGREP"
}
d_fetch_maildir(){
d_docker fetch_maildir
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ $# != 1 ]]; then
      echo "usage: ./prepare_test.sh <2 or 3>"
      exit 0
    fi
    export PYVER=${1}
    clone_mailserver
    copy_tests
    docker_up
fi
