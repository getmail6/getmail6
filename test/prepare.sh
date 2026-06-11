export TESTEMAIL="user1@example.test"
export TESTPSSWD="ТЕСТПАСС"
export CONTAINERNAME="mail.example.test"
#echo $TESTEMAIL $TESTPSSWD $CONTAINERNAME
export MAILDIR="/home/user1/Mail/$TESTEMAIL"
export MAILDIRIN=$MAILDIR/INBOX
declare -A PORTNR
PORTNR["POP3"]=110
PORTNR["IMAP"]=143
PORTNR["IMAPSSL"]=993
PORTNR["POP3SSL"]=995
PORTNR["SMTP"]=25
PORTNR["SMTPSSL"]=587
export PORTNR

dms_install_getmail() {
apt-get -qq remove getmail6
apt-get -qq update
apt-get -qq install iputils-ping nmap make python3 python3-pip bats procmail
#apt-get -qq install jq vim git
cd /tmp/docker-mailserver/getmail6/test
source prepare.sh
cd /tmp/docker-mailserver/getmail6
pip3 install -e . --break-system-packages
getmail --version
yes | setup email del $TESTEMAIL &> /dev/null
yes | setup email del user2 &> /dev/null
setup email add $TESTEMAIL $TESTPSSWD &> /dev/null
setup email add user2@example.test $TESTPSSWD &> /dev/null
useradd -m -s /bin/bash user1 &> /dev/null
usermod -a -G postfix user1
useradd -m -s /bin/bash user2 &> /dev/null
usermod -a -G postfix user2
}

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
docker exec -u 0 -w /tmp/docker-mailserver/getmail6/test -t ${CONTAINERNAME} bash -c "source prepare.sh && dms_install_getmail"
}

d_root(){
docker exec -u 0 -it $CONTAINERNAME bash
}

d_user(){
docker exec -u user1 -w /tmp/docker-mailserver/getmail6/test -it $CONTAINERNAME bash
}

d_docker(){
docker exec -u user1 -w /tmp/docker-mailserver/getmail6/test $CONTAINERNAME bash -c "source prepare.sh
$@
"
}

d_bats(){
d_docker "bats getmaildms.bats"
}


# TODO ==========
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
docker exec -u 0 $CONTAINERNAME -w /tmp/docker-mailserver/getmail6/test bash -c "
source prepare.sh
doveadm mailbox create -u '$TESTEMAIL' 'idle1' 2>/dev/null
doveadm mailbox create -u '$TESTEMAIL' 'idle2' 2>/dev/null
_send
sleep 1
doveadm move -u '$TESTEMAIL' 'idle1' mailbox 'INBOX' all
sleep 1
_send
sleep 2
_send
sleep 1
doveadm move -u '$TESTEMAIL' 'idle2' mailbox 'INBOX' all
echo idle1
ls -1A /var/mail/example.test/user1/.idle1/new
echo idle2
ls -1A /var/mail/example.test/user1/.idle2/new
"
}

n_idle(){
  local idlemails=$(ls /home/user1/Mail/new | wc -l)
  return $idlemails
}
d_n_idle(){
  local x=$(d_docker check_n_idle)
  local xwant=$1
  return $((x==xwant))
}



