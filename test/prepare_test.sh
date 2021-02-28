#!/usr/bin/env bash

# cwd = getmail/test

: '
# force renew of /tmp/mailserver:
rm /tmp/mailserver/python?

/tmp/mailserver
docker-compose ps
docker-compose up -d
docker exec -u 0 -it mail.domain.tld bash
docker exec -u getmail -it mail.domain.tld bash

# test ports
docker exec -t mail.domain.tld bash -c " \
    nmap -p25 localhost && \
    nmap -p143 localhost && \
    nmap -p587 localhost && \
    nmap -p993 localhost "

# update
apt-get update
apt-get -y install git make procmail iputils-ping nmap python-pip python3-pip
cd /tmp/docker-mailserver/getmail6
pip3 install .

# TESTEMAIL from self_sign.sh
source /tmp/docker-mailserver/self_sign.sh
export TESTEMAIL

# add email
addmailuser $TESTEMAIL test

# send email
testmail(){
  cat > /tmp/smtponly.txt << EOF
HELO mail.localhost
MAIL FROM: ${TESTEMAIL}
RCPT TO: ${TESTEMAIL}
DATA
Subject: test
This is the test text.
.
QUIT
EOF
nc 0.0.0.0 25 < /tmp/smtponly.txt
}
testmail

# getmail test
PORTNR=993
KIND=IMAP
TMPMAIL=/tmp/Mail
MAILDIRPATH=$TMPMAIL/$TESTEMAIL/INBOX
mkdir -p $MAILDIRPATH/{cur,tmp,new}
cat > $TMPMAIL/getmail <<EOF
[retriever]
type = Simple${KIND}SSLRetriever
server = localhost
username = $TESTEMAIL
port = $PORTNR
password = "test"
[destination]
type = Maildir
path = $MAILDIRPATH/
[options]
read_all = true
delete = true
EOF
getmail --rcfile=getmail --getmaildir=$TMPMAIL

exit
'

CWD="$(pwd)"
echo $CWD
TESTREPO=${CWD%/*}

source self_sign.sh
export PSS TESTEMAIL NAME

MAILSERVERSOURCE="${HOME}/msrc/docker-mailserver"
if [[ ! -d "$MAILSERVERSOURCE" ]]; then
    MAILSERVERSOURCE='https://github.com/docker-mailserver/docker-mailserver'
fi
echo $MAILSERVERSOURCE

PYVER=3

function clone_mailserver() {
    new_clone="no"
    # clone to reuse bats scripts
    if [[ ! -f /tmp/mailserver/python$PYVER ]]; then
        if [[ -d /tmp/mailserver ]]; then
            cd /tmp/mailserver
            docker-compose down
            cd $CWD
            sudo rm -rf /tmp/mailserver
        fi
        git clone --recursive $MAILSERVERSOURCE /tmp/mailserver
        git checkout tags/v9.0.1
        touch /tmp/mailserver/python$PYVER
        yes | cp -f $CWD/docker-compose.yml /tmp/mailserver/
        cat > /tmp/mailserver/.env << EOF
HOSTNAME=mail
DOMAINNAME=domain.tld
CONTAINER_NAME=${NAME}
SELINUX_LABEL=
EOF
        chmod a+x /tmp/mailserver/setup.sh
        new_clone="yes"
    fi
}

function copy_tests() {
    yes | cp -f *.bats /tmp/mailserver/test/
    yes | cp -f self_sign.sh /tmp/mailserver/config/

    cd  /tmp/mailserver/config
    rm -rf getmail6
    #git clone $TESTREPO
    cp -R $TESTREPO getmail6
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
        #pip2 is 2.7.16
        #pip3 is 3.7.3
        docker exec -u 0 -t ${NAME} bash -c "cd /tmp/docker-mailserver/getmail6 && pip$PYVER install ."
        docker exec -u 0 -t ${NAME} bash -c "useradd -m -s /bin/bash getmail"
    fi
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
