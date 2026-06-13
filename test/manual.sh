# dump of manual shell
# manual_ to call line-by-line

# cwd = getmail/test
CWD="$(pwd)"
# echo $CWD
GETMAIL6REPO=${CWD%/*}

manual_as_user_DMS() {
d_user
source prepare.sh
simple_dest_maildir IMAP false false "uid_cache=uid.txt"
exit
}

manual_uid_cache(){
simple_dest_maildir IMAP false false uid_cache=uid.txt
n1=$(cat /home/user1/uid.txt | cut -d" " -f 3)
simple_dest_maildir IMAP false false uid_cache=uid.txt
n2=$(cat /home/user1/uid.txt | cut -d" " -f 3)
[[ $(( n2 - n1 )) != 0 ]]
echo $n1
echo $n2
simple_dest_maildir IMAP false false uid_cache=true
}

manual_cycle_one_test(){
cd $GETMAIL6REPO/test
source prepare.sh
simple_dest_maildir IMAP false false uid_cache=uid.txt
}

#----------------------------------------------------------
lines_test_idle(){
d_idle_setup_sieve
}


# https://github.com/getmail6/getmail6/issues/265
d_test_idle_manual_setup(){
getmail --version
apt-get -qq remove getmail6
apt-get -qq update
apt-get -qq install jq
apt-get -qq install python3 python3-pip
apt-get -qq install -y vim
apt-get -qq install git
mkdir -p /home/docker
chown 5000:5000 /home/docker
ls /etc/dovecot/conf.d/
doveadm user hello@example.test
doveadm user john.doe@example.test
doveconf -f service=lda mail_plugins
vim /etc/dovecot/conf.d/10-mail.conf
# set
# mail_uid = 5000
# mail_gid = 5000
# log_debug = category=sieve
mkdir -p /usr/lib/dovecot/sieve-global/before
echo 'require ["envelope", "fileinto", "mailbox", "subaddress", "variables"];
# Check if the mail recipient address uses the expected subaddress tag (sourced from `:detail`)
if envelope :detail :matches "to" "sieve-example" {
  # Store into `+` mailbox:
  if mailboxexists "+" {
    fileinto "+";
  } else {
    fileinto :create "+";
  }
  # Store into `@` mailbox:
  if mailboxexists "@" {
    fileinto "@";
  } else {
    fileinto :create "@";
  }
}' > /usr/lib/dovecot/sieve-global/before/plus_at_sieve.sieve
ls /usr/lib/dovecot/sieve-global/before
less /usr/lib/dovecot/sieve-global/before/plus_at_sieve.sieve
less /etc/dovecot/conf.d/90-sieve.conf
rm -rf ~/.dovecot.sieve
ln -s /usr/lib/dovecot/sieve-global/before/plus_at_sieve.sieve ~/.dovecot.sieve
dovecot reload
ps aux
exit
}

# https://github.com/getmail6/getmail6/issues/265
d_test_idle_manual_user(){
cd ~
python3 -m venv /home/docker/venv
source /home/docker/venv/bin/activate
git clone https://github.com/getmail6/getmail6
cd getmail6
pip install -e .
getmail --version
mkdir -p /home/docker/getmailrc.d
echo '
[retriever]
type = SimpleIMAPRetriever
server = localhost
username = john.doe@example.test
password = johndoe
# mailboxes = ("+", "@")
mailboxes = ("INBOX.Social",)
[destination]
type = Maildir
path = /home/docker/Mail/
# [destination]
# type = MDA_external
# path = /usr/lib/dovecot/deliver
# allow_root_commands = true
# arguments =("-d","john.doe@example.test")
[options]
imap_search=SEEN
read_all = true
delete = true
' > /home/docker/getmailrc.d/john.doe.rc
less /home/docker/getmailrc.d/john.doe.rc
mkdir -p /home/docker/Mail/{cur,tmp,new}
#
swaks --silent --server mail.example.test \
  --from 'hello@example.test' \
  --to 'john.doe+sieve-example@example.test' \
  --header 'sieve' \
  --body "Sieve."
ls -1A /var/mail/example.test/john.doe
ls -1A /var/mail/example.test/john.doe/.+/new
ls -1A /var/mail/example.test/john.doe/.+/cur
ls -1A /var/mail/example.test/john.doe/.@/new
cd /var/log
less mail.log
# rm /etc/getmailrc.d/oldmail*
# getmail-service.sh
getmail -vvv --getmaildir /home/docker/getmailrc.d --rcfile john.doe.rc
swaks --silent --server mail.example.test --from 'hello@example.test' --to 'john.doe@example.test' --header 'normal' --body "Normal."
getmail -vvv --getmaildir /home/docker/getmailrc.d --rcfile john.doe.rc --idle=
#
doveadm mailbox create -u 'john.doe@example.test' 'INBOX.Social'
# Manually invoke moving all the mail content from INBOX into the mailbox INBOX.Social
doveadm move -u 'john.doe@example.test' 'INBOX.Social' mailbox 'INBOX' all
ls -1a /var/mail/example.test/john.doe/new
ls -1a /var/mail/example.test/john.doe/.INBOX.Social/new
# Here's another command to query mail from all mailboxes of the account,
# the JSON returned will be filtered to each mail item only having
# `mailbox` and `subject` header properties.
swaks --silent --server mail.example.test \
  --from 'hello@example.test' \
  --to 'john.doe@example.test' \
  --header 'Subject: 42 people noticed you' \
  --body "You're getting noticed by someone from GitHub."
doveadm -f json fetch -u 'john.doe@example.test' 'mailbox hdr.subject' MAILBOX '*' | jq
getmail -vvv --getmaildir /home/docker/getmailrc.d --rcfile john.doe.rc --idle=INBOX.Social
getmail -vvv --getmaildir /home/docker/getmailrc.d --rcfile john.doe.rc --idle=
exit
}


# https://github.com/getmail6/getmail6/issues/265
test_idle_manual(){
docker run --rm -itd --name dms-example --hostname mail.example.test ghcr.io/docker-mailserver/docker-mailserver:15.1
docker ps
docker exec -it dms-example setup email add hello@example.test eoeaee
docker exec -it dms-example setup email add john.doe@example.test johndoe
docker exec -it dms-example bash
d_test_idle_manual_setup
docker exec -it -u 5000:5000 dms-example bash
d_test_idle_manual_user
docker stop dms-example
docker ps
}

# https://github.com/getmail6/getmail6/issues/265
mail_server_via_docker_compose(){
echo '
services:
  dms:
    image: ghcr.io/docker-mailserver/docker-mailserver:15.1
    hostname: mail.example.test
    environment:
      PERMIT_DOCKER: container
      ENABLE_SPAMASSASSIN: 1
    configs:
      - source: dms-accounts
        target: /tmp/docker-mailserver/postfix-accounts.cf
      - source: sieve
        target: /tmp/docker-mailserver/john.doe@example.test.dovecot.sieve
configs:
  dms-accounts:
    content: |
      jane.doe@example.test|{SHA512-CRYPT}$$6$$sbgFRCmQ.KWS5ryb$$EsWrlYosiadgdUOxCBHY0DQ3qFbeudDhNMqHs6jZt.8gmxUwiLVy738knqkHD4zj4amkb296HFqQ3yDq4UXt8.
      john.doe@example.test|{SHA512-CRYPT}$$6$$sbgFRCmQ.KWS5ryb$$EsWrlYosiadgdUOxCBHY0DQ3qFbeudDhNMqHs6jZt.8gmxUwiLVy738knqkHD4zj4amkb296HFqQ3yDq4UXt8.

  sieve:
    content: |
      if envelope :detail :regex "to" "^(promotions|social)$" {
        set :lower :upperfirst "tag" "$${1}";
        fileinto :create "INBOX.$${tag}";
      }
' > compose.yaml
docker compose up --detach --force-recreate
docker exec -it -u 5000:5000 mailserver-dms-1 bash
}



      PASSWD_HASH=$(doveadm pw -s SHA512-CRYPT -u "${MAIL_ACCOUNT}" -p "${PASSWD}")
