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
}

simple_dest_maildir() {
  KIND=$1
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
type = Simple${KIND}Retriever
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
  simple_dest_maildir POP3 110
}
@test "SimplePOP3SSLRetriever, destination Maildir" {
  simple_dest_maildir POP3SSL 995
}
@test "SimpleIMAPRetriever, destination Maildir" {
  simple_dest_maildir IMAP 143
}
@test "SimpleIMAPSSLRetriever, destination Maildir" {
  simple_dest_maildir IMAPSSL 993
}


simple_dest_procmail_filter() {
  KIND=$1
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
type = Simple${KIND}Retriever
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

@test "SimplePOP3Retriever, destination procmail filter spamassassin clamav" {
  simple_dest_procmail_filter POP3 110
}
@test "SimplePOP3SSLRetriever, destination procmail filter spamassassin clamav" {
  simple_dest_procmail_filter POP3SSL 995
}
@test "SimpleIMAPRetriever, destination procmail filter spamassassin clamav" {
  simple_dest_procmail_filter IMAP 143
}
@test "SimpleIMAPSSLRetriever, destination procmail filter spamassassin clamav" {
  simple_dest_procmail_filter IMAPSSL 993
}


config_test() {
  KIND=$1
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
cat > /home/getmail/getmail <<EOF
[retriever]
type = Simple${KIND}Retriever
server = localhost
username = $TESTEMAIL
port = $PORT
password_command = ('/home/getmail/pass',)
[destination]
type = Maildir
path = $MAILDIRIN/
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

@test "SimplePOP3Retriever, config test" {
config_test POP3 110 800 False False
config_test POP3 110 900 True  False
}
@test "SimplePOP3SSLRetriever, config test" {
config_test POP3SSL 995 800 0 0
config_test POP3SSL 995 900 1 1
}
@test "SimpleIMAPRetriever, config test" {
config_test IMAP 143 800 false true
config_test IMAP 143 900 false  true
}
@test "SimpleIMAPSSLRetriever, config test" {
config_test IMAPSSL 993 800 False False
config_test IMAPSSL 993 900 True  True
}
