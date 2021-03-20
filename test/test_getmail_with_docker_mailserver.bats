load 'test_helper/common'

source config/self_sign.sh
export PSS TESTEMAIL NAME

function setup() {
    setup_file
}

function teardown() {
    run_teardown_file_if_necessary
}

function setup_file() {
    source '.env'
    export HOSTNAME DOMAINNAME CONTAINER_NAME SELINUX_LABEL
    wait_for_finished_setup_in_container ${NAME}
    local STATUS=0
    repeat_until_success_or_timeout --fatal-test "container_is_running ${NAME}" "${TEST_TIMEOUT_IN_SECONDS}" sh -c "docker logs ${NAME} | grep 'is up and running'" || STATUS=1
    if [[ ${STATUS} -eq 1 ]]; then
        echo "Last ${NUMBER_OF_LOG_LINES} lines of container \`${NAME}\`'s log"
        docker logs "${NAME}" | tail -n "${NUMBER_OF_LOG_LINES}"
    fi
    return ${STATUS}
}

function teardown_file() {
    : # docker-compose down
}

@test "first" {
  skip 'this test must come first to reliably identify when to run setup_file'
}

@test "checking ssl" {
  run docker exec $NAME /bin/bash -c "\
    openssl s_client -connect 0.0.0.0:25 -starttls smtp -CApath /etc/ssl/certs/"
  assert_success
}

# declare -A PORTNR
# PORTNR["POP3"]=110
# PORTNR["IMAP"]=143
# PORTNR["IMAPSSL"]=993
# PORTNR["POP3SSL"]=995
# PORTNR["SMTP"]=25
# PORTNR["SMTPSSL"]=587

testmail(){
  docker exec $NAME bash -c "nc 0.0.0.0 25 << EOF
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
"
sleep 1
}

simple_dest_maildir() {
  RETRIEVER=$1
  PORT=$2
  testmail
  TMPMAIL=/home/getmail/Mail
  MAILDIR=$TMPMAIL/$TESTEMAIL
  MAILDIRIN=$MAILDIR/INBOX
  run docker exec -u getmail $NAME bash -c "
rm -rf $MAILDIR && \
mkdir -p $MAILDIRIN/{cur,tmp,new} && \
cat > /home/getmail/getmail <<EOF
[retriever]
type = ${RETRIEVER}
server = localhost
username = $TESTEMAIL
port = $PORT
password = $PSS
[destination]
type = Maildir
path = $MAILDIRIN/
[options]
read_all = true
delete = true
EOF"
  assert_success
  run docker exec -u getmail $NAME bash -c " \
  getmail --rcfile=getmail --getmaildir=/home/getmail"
  assert_success
}

@test "SimplePOP3Retriever, destination Maildir" {
  simple_dest_maildir SimplePOP3Retriever 110
}
@test "SimplePOP3SSLRetriever, destination Maildir" {
  simple_dest_maildir SimplePOP3SSLRetriever 995
}
@test "SimpleIMAPRetriever, destination Maildir" {
  simple_dest_maildir SimpleIMAPRetriever 143
}
@test "SimpleIMAPSSLRetriever, destination Maildir" {
  simple_dest_maildir SimpleIMAPSSLRetriever 993
}


simple_dest_procmail_filter() {
  RETRIEVER=$1
  PORT=$2
  testmail
  TMPMAIL=/home/getmail/Mail
  MAILDIR=$TMPMAIL/$TESTEMAIL
  MAILDIRIN=$MAILDIR/INBOX
  run docker exec -u getmail $NAME bash -c " \
rm -rf $MAILDIR && \
mkdir -p $MAILDIRIN/{cur,tmp,new} && \
mkdir -p $MAILDIR/tests/{cur,tmp,new} && \
cat > /home/getmail/getmail <<EOF
[retriever]
type = ${RETRIEVER}
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
EOF"
  assert_success
  run docker exec -u getmail $NAME bash -c " \
cat > /home/getmail/procmail <<EOF
MAILDIR=$MAILDIR
DEFAULT=\$MAILDIR/INBOX
:0
* ^Subject:.*test.*
tests/
:0
\$DEFAULT/
EOF"
  assert_success
  run docker exec -u getmail $NAME bash -c " \
  getmail --rcfile=getmail --getmaildir=/home/getmail"
  assert_success
}

@test "SimplePOP3Retriever, destination MDA_external (procmail), filter spamassassin clamav" {
  simple_dest_procmail_filter SimplePOP3Retriever 110
}
@test "SimplePOP3SSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
  simple_dest_procmail_filter SimplePOP3SSLRetriever 995
}
@test "SimpleIMAPRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
  simple_dest_procmail_filter SimpleIMAPRetriever 143
}
@test "SimpleIMAPSSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
  simple_dest_procmail_filter SimpleIMAPSSLRetriever 993
}

config_test() {
  RETRIEVER=$1
  PORT=$2
  MAX=$3
  READALL=$4
  DEL=$5
  testmail
  TMPMAIL=/home/getmail/Mail
  MAILDIR=$TMPMAIL/$TESTEMAIL
  MAILDIRIN=$MAILDIR/INBOX
  run docker exec -u getmail $NAME bash -c " \
rm -rf $MAILDIR && mkdir -p $MAILDIRIN/{cur,tmp,new} && \
touch $MAILDIR/inbox && \
cat > /home/getmail/getmail <<EOF
[retriever]
type = ${RETRIEVER}
server = localhost
username = $TESTEMAIL
port = $PORT
password_command = ('/home/getmail/pass',)
[destination]
type = Mboxrd
path = $MAILDIR/inbox
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
"
  assert_success
  run docker exec -u getmail $NAME bash -c " \
cat >/home/getmail/pass <<EOF
#!/bin/bash
echo $PSS
EOF
chmod +x /home/getmail/pass
"
  assert_success
  run docker exec -u getmail $NAME bash -c " \
  getmail --rcfile=getmail --getmaildir=/home/getmail"
  assert_success
}

#896 is message size

@test "BrokenUIDLPOP3Retriever, config test" {
config_test BrokenUIDLPOP3Retriever 110 800 False False
config_test BrokenUIDLPOP3Retriever 110 900 True  False
}
@test "BrokenUIDLPOP3SSLRetriever, config test" {
config_test BrokenUIDLPOP3SSLRetriever 995 800 0 0
config_test BrokenUIDLPOP3SSLRetriever 995 900 1 1
}
@test "SimpleIMAPRetriever, config test" {
config_test SimpleIMAPRetriever 143 800 false true
config_test SimpleIMAPRetriever 143 900 false  true
}
@test "SimpleIMAPSSLRetriever, config test" {
config_test SimpleIMAPSSLRetriever 993 800 False False
config_test SimpleIMAPSSLRetriever 993 900 True  True
}

multidrop(){
  docker exec $NAME bash -c "nc 0.0.0.0 25 << EOF
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
"
sleep 1
}

multidrop_test() {
  RETRIEVER=$1
  PORT=$2
  TMPMAIL=/home/getmail/Mail
  MAILDIR=$TMPMAIL/$TESTEMAIL
  MAILDIRIN=$MAILDIR/INBOX
  multidrop
  run docker exec -u getmail $NAME bash -c " \
rm -rf $MAILDIR && mkdir -p $MAILDIRIN/{cur,tmp,new} && \
cat > /home/getmail/getmail <<EOF
[retriever]
type = ${RETRIEVER}
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
"
  assert_success
  run docker exec -u getmail $NAME bash -c " \
  getmail --rcfile=getmail --getmaildir=/home/getmail"
  assert_success
}

@test "MultidropPOP3Retriever" {
multidrop_test SimplePOP3Retriever 110
multidrop_test MultidropPOP3Retriever 110
}
@test "MultidropPOP3SSLRetriever" {
multidrop_test SimplePOP3SSLRetriever 995
multidrop_test MultidropPOP3SSLRetriever 995
}
@test "MultidropIMAPRetriever" {
multidrop_test SimpleIMAPRetriever 143
multidrop_test MultidropIMAPRetriever 143
}
@test "MultidropIMAPSSLRetriever" {
multidrop_test SimpleIMAPSSLRetriever 993
multidrop_test MultidropIMAPSSLRetriever 993
}

multisorter_test() {
  RETRIEVER=$1
  PORT=$2
  TMPMAIL=/home/getmail/Mail
  MAILDIR=$TMPMAIL/$TESTEMAIL
  MAILDIRIN=$MAILDIR/INBOX
  multidrop
  run docker exec -u getmail $NAME bash -c " \
rm -rf $MAILDIR && mkdir -p $MAILDIRIN/{cur,tmp,new} && \
touch $MAILDIR/inbox && \
cat > /home/getmail/getmail <<EOF
[retriever]
type = ${RETRIEVER}
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
path = $MAILDIR/inbox
[options]
read_all = True
delete = True
EOF
"
  assert_success
  run docker exec -u getmail $NAME bash -c " \
  getmail --rcfile=getmail --getmaildir=/home/getmail"
  assert_success
}

@test "SimplePOP3Retriever, Multisorter" {
multisorter_test SimplePOP3Retriever 110
}
@test "SimplePOP3SSLRetriever, Multisorter" {
multisorter_test SimplePOP3SSLRetriever 995
}
@test "SimpleIMAPRetriever, Multisorter" {
multisorter_test SimpleIMAPRetriever 143
}
@test "SimpleIMAPSSLRetriever, Multisorter" {
multisorter_test SimpleIMAPSSLRetriever 993
}

