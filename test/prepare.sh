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
useradd -m -s /bin/bash user1 -p ТЕСТПАСС &> /dev/null
usermod -a -G postfix user1
useradd -m -s /bin/bash user2 -p ТЕСТПАСС &> /dev/null
usermod -a -G postfix user2
cp /tmp/docker-mailserver/user1@example.test.dovecot.sieve /var/mail/example.test/user1/home/.dovecot.sieve
doveadm mailbox create -u 'user1@example.test' 'idle1'
doveadm mailbox create -u 'user1@example.test' 'idle2'
}

function restart_dms() {
docker compose down -v
docker compose up --detach --force-recreate
local STARTTIME=${SECONDS}
until bash -c "docker logs mail.example.test | grep 'is up and running'"; do
  sleep 1
  echo "Waiting a second" >&2
  if [[ $(( SECONDS - STARTTIME )) -gt 66 ]]; then
    echo "Timed out on command: ${*}" >&2
    return 1
  fi
done
docker exec -u 0 -t mail.example.test bash -c "freshclam &> /dev/null"
docker exec -u 0 -w /tmp/docker-mailserver/getmail6/test -t mail.example.test bash -c "source prepare.sh && dms_install_getmail"
}

d_root(){
docker exec -u 0 -it mail.example.test bash
}

d_user(){
docker exec -u user1 -w /tmp/docker-mailserver/getmail6/test -it mail.example.test bash
}

d_docker(){
docker exec -u user1 -w /tmp/docker-mailserver/getmail6/test mail.example.test bash -c "source prepare.sh
$@
"
}

d_bats(){
d_docker "bats getmaildms.bats"
}


user_pw(){
local MAIL_ACCOUNT=${1}
local PASSWD=${2}
PASSWD_HASH=$(doveadm pw -s SHA512-CRYPT -u "${MAIL_ACCOUNT}" -p "${PASSWD}")
echo "$MAIL_ACCOUNT@example.test|$PASSWD_HASH" | sed "s/\\$/\\$\\$/g"
}
: '
#for compose.yml
user_pw user1 ТЕСТПАСС
user_pw user2 ТЕСТПАСС
'

