load 'test_helper/common'

: '

cd /tmp/mailserver
test/bats/bin/bats test/test_getmail_with_docker_mailserver.bats

'

#source config/self_sign.sh
#export TESTPSSWD TESTEMAIL CONTAINERNAME
cd config/getmail6/test || exit
source prepare_test.sh
cd ../../..

run_only_test() {
    if [ "$BATS_TEST_NUMBER" -ne "$1" ]; then
        skip
    fi
}

function setup() {
    # run_only_test 8
    setup_file
}

function teardown() {
    run_teardown_file_if_necessary
}

function setup_file() {
    wait_for_finished_setup_in_container ${CONTAINERNAME}
    local STATUS=0
    repeat_until_success_or_timeout --fatal-test "container_is_running ${CONTAINERNAME}" "${TEST_TIMEOUT_IN_SECONDS}" sh -c "docker logs ${CONTAINERNAME} | grep 'is up and running'" || STATUS=1
    if [[ ${STATUS} -eq 1 ]]; then
        echo "Last ${NUMBER_OF_LOG_LINES} lines of container \`${CONTAINERNAME}\`'s log"
        docker logs "${CONTAINERNAME}" | tail -n "${NUMBER_OF_LOG_LINES}"
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
  run docker exec $CONTAINERNAME /bin/bash -c "\
    openssl s_client -connect 0.0.0.0:25 -starttls smtp -CApath /etc/ssl/certs/"
  assert_success
}

@test "checking ports" {
  run d_ports_test
  assert_success
}

@test "SimplePOP3Retriever, destination Maildir" {
  run d_simple_dest_maildir "POP3 true true"
}
@test "SimplePOP3SSLRetriever, destination Maildir" {
  run d_simple_dest_maildir "POP3SSL true true"
}
@test "SimpleIMAPRetriever, destination Maildir" {
  run d_simple_dest_maildir "IMAP true true record_mailbox=true"
}
@test "SimpleIMAPSSLRetriever, destination Maildir" {
  run d_simple_dest_maildir "IMAPSSL true true"
}
@test "SimpleIMAPRetriever, destination Maildir, uid_cache=uid.txt" {
  run d_simple_dest_maildir "IMAP false false uid_cache=uid.txt"
  n1=$(d_docker "cat /home/getmailtestuser/uid.txt" | cut -d" " -f 3)
  run d_simple_dest_maildir "IMAP false false uid_cache=uid.txt"
  n2=$(d_docker "cat /home/getmailtestuser/uid.txt" | cut -d" " -f 3)
  [[ $(( n2 - n1 )) != 0 ]]
}
@test "SimpleIMAPRetriever, destination Maildir, uid_cache=true" {
  run d_simple_dest_maildir "IMAP false false uid_cache=true"
}


dest_maildir_with_uid_check() {
testmail
testmail
testmail
dest_maildir IMAPSSL true false "uid_cache=uid.txt"
retrieve
checkmail
testmail
testmail
testmail
dest_maildir IMAPSSL true false "uid_cache=uid.txt"
retrieve
checkmail
}




@test "SimplePOP3Retriever, destination MDA_external (procmail), filter spamassassin clamav" {
  run d_simple_dest_procmail_filter POP3
  assert_success
}
@test "SimplePOP3SSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
  run d_simple_dest_procmail_filter POP3SSL
  assert_success
}
@test "SimpleIMAPRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
  run d_simple_dest_procmail_filter IMAP
  assert_success
}
@test "SimpleIMAPSSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
  run d_simple_dest_procmail_filter IMAPSSL
  assert_success
}

bats_config_test(){
  run d_config_test "$@"
  run d_retrieve
  assert_success
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

check_lmtp_delivery() {
  run d_checkmail
  assert_failure
  run d_maildir_clean_retrieve IMAP
  assert_success
  run d_checkmail
  assert_success
}

@test "MDA_lmtp" {
if head `which getmail` | grep 'python3' ; then
run d_lmtp_test_py "SimpleIMAPRetriever 143"
run d_retrieve
assert_success
run d_lmtp_test_unix_socket "SimpleIMAPRetriever 143"
run d_retrieve
assert_success
check_lmtp_delivery
run d_grep_mail "Subject: lmtp_test_unix_socket_x"
assert_success
run d_lmtp_test_override "SimpleIMAPRetriever 143"
run d_retrieve
assert_success
check_lmtp_delivery
run d_grep_mail "Subject: lmtp_test_override_x"
assert_success
run d_lmtp_test_override_fallback "SimpleIMAPRetriever 143"
run d_retrieve
assert_success
check_lmtp_delivery
run d_grep_mail "Subject: lmtp_test_override_fallback_x"
assert_success
fi
}

@test "SimpleIMAPSSLRetriever, ALL, no delete" {
  run d_imap_search "ALL false"
  run d_retrieve
  assert_success
  run d_checkmail
  assert_success
  run d_grep_mail utf-8
  assert_failure
}
@test "SimpleIMAPRetriever, UNSEEN, set seen" {
  run d_imap_search "UNSEEN true"
  run d_retrieve
  assert_success
  run d_checkmail
  assert_success
  run d_grep_mail utf-8
  assert_failure
}
@test "SimpleIMAPRetriever, UNSEEN, no unseen" {
  run d_imap_search "UNSEEN true"
  run d_retrieve
  assert_success
  run d_checkmail
  assert_failure
}
@test "SimpleIMAPSSLRetriever, ALL, delete" {
  run d_imap_search "ALL true"
  run d_retrieve
  assert_success
  run d_checkmail
  assert_success
  run d_grep_mail utf-8
  assert_failure
}

@test "IMAP override via command line -s" {
  run d_override_test
}

@test "getmail_mbox test" {
  run d_local_mbox
}

@test "getmail_maildir test" {
  run d_local_maildir
}

@test "getmail_fetch test" {
  run d_fetch_maildir
}

