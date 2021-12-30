load 'test_helper/common'

: '

cd /tmp/mailserver
test/bats/bin/bats test/test_getmail_with_docker_mailserver.bats

'

#source config/self_sign.sh
#export PSS TESTEMAIL NAME
cd config/getmail6/test
source prepare_test.sh
cd ../../..

run_only_test() {
    if [ "$BATS_TEST_NUMBER" -ne "$1" ]; then
        skip
    fi
}

function setup() {
    # run_only_test 3
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

@test "checking ports" {
  run d_ports_test
  assert_success
}

bats_check_mail(){
  run d_retrieve
  assert_success # expect mail retrieval without error
  run d_grep_mail "$TESTGREP"
  assert_success # expect a mail which contains "$TESTGREP"
  run d_grep_mail utf-8
  assert_failure # expect no utf-8 encoding of INBOX
}

bats_simple_dest_maildir (){
  run d_simple_dest_maildir "$@"
  #bats_check_mail # moved into simple_dest_maildir, because it failed
}

@test "SimplePOP3Retriever, destination Maildir" {
  bats_simple_dest_maildir POP3
}
@test "SimplePOP3SSLRetriever, destination Maildir" {
  bats_simple_dest_maildir POP3SSL
}
@test "SimpleIMAPRetriever, destination Maildir" {
  bats_simple_dest_maildir IMAP
}
@test "SimpleIMAPSSLRetriever, destination Maildir" {
  bats_simple_dest_maildir IMAPSSL
}

bats_simple_dest_procmail_filter() {
  run d_simple_dest_procmail_filter "$@"
  assert_success
}

@test "SimplePOP3Retriever, destination MDA_external (procmail), filter spamassassin clamav" {
  bats_simple_dest_procmail_filter POP3
}
@test "SimplePOP3SSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
  bats_simple_dest_procmail_filter POP3SSL
}
@test "SimpleIMAPRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
  bats_simple_dest_procmail_filter IMAP
}
@test "SimpleIMAPSSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
  bats_simple_dest_procmail_filter IMAPSSL
}

bats_config_test(){
  run d_config_test "$@"
  run d_retrieve
  assert_success # expect mail retrieval without error
}

#896 is message size

@test "BrokenUIDLPOP3Retriever, config test" {
bats_config_test "BrokenUIDLPOP3Retriever 110 800 False False"
bats_config_test "BrokenUIDLPOP3Retriever 110 900 True  False"
}
@test "BrokenUIDLPOP3SSLRetriever, config test" {
bats_config_test "BrokenUIDLPOP3SSLRetriever 995 800 0 0"
bats_config_test "BrokenUIDLPOP3SSLRetriever 995 900 1 1"
}
@test "SimpleIMAPRetriever, config test" {
bats_config_test "SimpleIMAPRetriever 143 800 false true"
bats_config_test "SimpleIMAPRetriever 143 900 false true"
}
@test "SimpleIMAPSSLRetriever, config test" {
bats_config_test "SimpleIMAPSSLRetriever 993 800 False False"
bats_config_test "SimpleIMAPSSLRetriever 993 900 True  True"
}

bats_multidrop_test() {
  run d_multidrop_test "$@"
  run d_retrieve
  assert_success
}

@test "MultidropPOP3Retriever" {
bats_multidrop_test "SimplePOP3Retriever 110"
bats_multidrop_test "MultidropPOP3Retriever 110"
}
@test "MultidropPOP3SSLRetriever" {
bats_multidrop_test "SimplePOP3SSLRetriever 995"
bats_multidrop_test "MultidropPOP3SSLRetriever 995"
}
@test "MultidropIMAPRetriever" {
bats_multidrop_test "SimpleIMAPRetriever 143"
bats_multidrop_test "MultidropIMAPRetriever 143"
}
@test "MultidropIMAPSSLRetriever" {
bats_multidrop_test "SimpleIMAPSSLRetriever 993"
bats_multidrop_test "MultidropIMAPSSLRetriever 993"
}


bats_multisorter_test() {
  run d_multisorter_test "$@"
  assert_success
}

@test "MultidropPOP3Retriever, Multisorter" {
bats_multisorter_test "MultidropPOP3Retriever 110"
}
@test "MultidropPOP3SSLRetriever, Multisorter" {
bats_multisorter_test "MultidropPOP3SSLRetriever 995"
}
@test "MultidropIMAPRetriever, Multisorter" {
bats_multisorter_test "MultidropIMAPRetriever 143"
}
@test "MultidropIMAPSSLRetriever, Multisorter" {
bats_multisorter_test "MultidropIMAPSSLRetriever 993"
}

bats_lmtp_test_py() {
  run d_lmtp_test_py "$@"
  run d_retrieve
  assert_success
}

bats_check_lmtp_delivery() {
  run d_grep_mail "$TESTGREP"
  assert_failure # expect no mail because the mail was delivered to $TESTEMAIL's vmail mailbox
  run d_maildir_clean_retrieve IMAP
  assert_success # retrieves the mail we delivered using LMTP into our maildir
  run d_grep_mail "$TESTGREP"
  assert_success
}

bats_lmtp_test_override() {
  run d_lmtp_test_override "$@"
  run d_retrieve
  assert_success
  bats_check_lmtp_delivery
  run d_grep_mail "Subject: lmtp_test_override_x"
  assert_success
}

bats_lmtp_test_override_fallback() {
  run d_lmtp_test_override_fallback "$@"
  run d_retrieve
  assert_success
  bats_check_lmtp_delivery
  run d_grep_mail "Subject: lmtp_test_override_fallback_x"
  assert_success
}


@test "MDA_lmtp" {
bats_lmtp_test_py "SimpleIMAPRetriever 143"
bats_lmtp_test_override "SimpleIMAPRetriever 143"
bats_lmtp_test_override_fallback "SimpleIMAPRetriever 143"
}

bats_imap_search() {
  run d_imap_search "$@"
  bats_check_mail
}

@test "SimpleIMAPSSLRetriever, ALL, no delete" {
  bats_imap_search "ALL false"
}
@test "SimpleIMAPRetriever, UNSEEN, set seen" {
  bats_imap_search "UNSEEN true"
}
@test "SimpleIMAPRetriever, UNSEEN, no unseen" {
  run d_imap_search "UNSEEN true"
  run d_retrieve
  assert_success # expect mail retrieval without error
  run d_grep_mail "$TESTGREP"
  assert_failure # expect no mail mail which contains "test"
}
@test "SimpleIMAPSSLRetriever, ALL, delete" {
  bats_imap_search "ALL true"
}

bats_override() {
  run d_override_test
}
@test "IMAP override via command line -s" {
  bats_override
}


bats_local_mbox(){
  run d_local_mbox
}
@test "getmail_mbox test" {
  bats_local_mbox
}

bats_local_maildir(){
  run d_local_maildir
}
@test "getmail_maildir test" {
  bats_local_maildir
}

bats_fetch_maildir(){
  run d_fetch_maildir
}
@test "getmail_fetch test" {
  bats_fetch_maildir
}

