source prepare_test.sh

@test "checking ports" {
run ports_test
}

@test "SSL Parameters IMAP, destination Maildir" {
run ssl_parameters_imap_maildir
}

@test "SimplePOP3Retriever, destination Maildir" {
run simple_dest_maildir POP3 true true
}
@test "SimplePOP3SSLRetriever, destination Maildir" {
run simple_dest_maildir POP3SSL true true
}
@test "SimpleIMAPRetriever, destination Maildir" {
run simple_dest_maildir IMAP true true record_mailbox=true
}
@test "SimpleIMAPSSLRetriever, destination Maildir" {
run simple_dest_maildir IMAPSSL true true
}
@test "SimpleIMAPRetriever, destination Maildir, uid_cache=uid.txt" {
run check_uid_cache
}
@test "SimpleIMAPRetriever, destination Maildir, uid_cache=true" {
run simple_dest_maildir IMAP false false uid_cache=true
}

@test "SimplePOP3Retriever, destination MDA_external (procmail), filter spamassassin clamav" {
run simple_dest_procmail_filter POP3
}
@test "SimplePOP3SSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
run simple_dest_procmail_filter POP3SSL
}
@test "SimpleIMAPRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
run simple_dest_procmail_filter IMAP
}
@test "SimpleIMAPSSLRetriever, destination MDA_external (procmail), filter spamassassin clamav" {
run simple_dest_procmail_filter IMAPSSL
}

@test "BrokenUIDLPOP3Retriever 110 800 False False" {
run config_test "BrokenUIDLPOP3Retriever 110 800 False False"
}
@test "BrokenUIDLPOP3Retriever 110 900 True  False" {
run config_test "BrokenUIDLPOP3Retriever 110 900 True  False"
}
@test "BrokenUIDLPOP3SSLRetriever 995 800 0 0" {
run config_test "BrokenUIDLPOP3SSLRetriever 995 800 0 0"
}
@test "BrokenUIDLPOP3SSLRetriever 995 900 1 1" {
run config_test "BrokenUIDLPOP3SSLRetriever 995 900 1 1"
}
@test "SimpleIMAPRetriever 143 800 false true" {
run config_test "SimpleIMAPRetriever 143 800 false true"
}
@test "SimpleIMAPRetriever 143 900 false true" {
run config_test "SimpleIMAPRetriever 143 900 false true"
}
@test "SimpleIMAPSSLRetriever 993 800 False False" {
run config_test "SimpleIMAPSSLRetriever 993 800 False False"
}
@test "SimpleIMAPSSLRetriever 993 900 True  True" {
run config_test "SimpleIMAPSSLRetriever 993 900 True  True"
}


@test "SimplePOP3Retriever 110" {
run multidrop_test "SimplePOP3Retriever 110"
}
@test "MultidropPOP3Retriever 110" {
run multidrop_test "MultidropPOP3Retriever 110"
}
@test "SimplePOP3SSLRetriever 995" {
run multidrop_test "SimplePOP3SSLRetriever 995"
}
@test "MultidropPOP3SSLRetriever 995" {
run multidrop_test "MultidropPOP3SSLRetriever 995"
}
@test "SimpleIMAPRetriever 143" {
run multidrop_test "SimpleIMAPRetriever 143"
}
@test "MultidropIMAPRetriever 143" {
run multidrop_test "MultidropIMAPRetriever 143"
}
@test "SimpleIMAPSSLRetriever 993" {
run multidrop_test "SimpleIMAPSSLRetriever 993"
}
@test "MultidropIMAPSSLRetriever 993" {
run multidrop_test "MultidropIMAPSSLRetriever 993"
}


@test "MultidropPOP3Retriever, Multisorter" {
run multisorter_test "MultidropPOP3Retriever 110"
}
@test "MultidropPOP3SSLRetriever, Multisorter" {
run multisorter_test "MultidropPOP3SSLRetriever 995"
}
@test "MultidropIMAPRetriever, Multisorter" {
run multisorter_test "MultidropIMAPRetriever 143"
}
@test "MultidropIMAPSSLRetriever, Multisorter" {
run multisorter_test "MultidropIMAPSSLRetriever 993"
}

# @test "MDA_lmtp" {
# run check_mda_lmtp
# }

@test "SimpleIMAPSSLRetriever, ALL, no delete" {
run imap_search ALL false
run retrieve
run checkmail
run grep_mail utf-8
}
@test "SimpleIMAPRetriever, UNSEEN, set seen" {
run imap_search UNSEEN true
run retrieve
run checkmail
run grep_mail utf-8
}
@test "SimpleIMAPRetriever, UNSEEN, no unseen" {
run imap_search UNSEEN true
run retrieve
}
@test "SimpleIMAPSSLRetriever, ALL, delete" {
run imap_search ALL true
run retrieve
run checkmail
run grep_mail utf-8
}

@test "SimpleIMAPSSLRetrieverMarkRead, new email, fetch and mark_read" {
run mark_read "mark_read"
run retrieve
run checkmail
run grep_mail utf-8
}

@test "SimpleIMAPSSLRetrieverMarkRead, mark_read check SEEN" {
run imap_search SEEN true
run retrieve
run checkmail
run grep_mail utf-8
}

## @test "idle1" {
## run idle_mailboxes
## run getmail_idle '("idle1",)'
## run n_idle 99
## }

@test "IMAP override via command line -s" {
run override_test
}

@test "getmail_mbox test" {
run local_mbox
}

@test "getmail_maildir test" {
run local_maildir
}

@test "getmail_fetch test" {
run fetch_maildir
}

