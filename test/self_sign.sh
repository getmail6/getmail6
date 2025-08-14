#!/usr/bin/env bash

export TESTPSSWD="ТЕСТПАСС"
#export TESTPSSWD="testpass"
export TESTEMAIL="address@domain.tld"
export CONTAINERNAME="mail.domain.tld"

: ' manual_self_sign:
/tmp/mailserver
docker-compose ps
docker exec -u 0 -it mail.domain.tld bash
cd /tmp/docker-mailserver/ssl
rm -rf *
cd /tmp/docker-mailserver/
ls
./self_sign.sh
exit
'

export CATOP="/tmp/docker-mailserver/ssl/demoCA"
export SUBJ="/C=US/ST=domain/L=tld/O=Dis/CN="

# does not persist, but no need to run, because done in
# /tmp/mailserver/target/scripts/startup/setup-stack.sh:1033
function install_demo_CA() {
    ##$CATOP/cacert.pem needs to be added to the system's list of trusted CA's
    #cp -f ${CATOP}/cacert.pem \
    #    /usr/share/ca-certificates/cacert.crt
    ## can be used to remove as well (without the -p)
    #dpkg-reconfigure -p critical ca-certificates
    cp -f ${CATOP}/cacert.pem \
        /usr/local/share/ca-certificates/cacert.crt
    update-ca-certificates
}

# persists
function create_demo_CA() {
    # from /usr/lib/ssl/misc/CA.pl
    mkdir -p $CATOP -m 0777
    mkdir -p $CATOP/certs -m 0777
    mkdir -p $CATOP/crl -m 0777
    mkdir -p $CATOP/newcerts -m 0777
    mkdir -p $CATOP/private -m 0777
    touch $CATOP/index.txt
    cat > $CATOP/crlnumber << EOF
01
EOF
    SUBJCA="${SUBJ}for.test.ca"
    CONFIG="-subj $SUBJCA -passin pass:$TESTPSSWD -passout pass:$TESTPSSWD"
    openssl req $CONFIG -new -keyout $CATOP/private/cakey.pem -out $CATOP/careq.pem 2> /dev/null
    openssl ca -subj $SUBJCA -passin pass:$TESTPSSWD -create_serial \
            -out $CATOP/cacert.pem $CADAYS -batch \
            -keyfile $CATOP/private/cakey.pem \
            -selfsign -extensions v3_ca -infiles $CATOP/careq.pem 2> /dev/null
}

# persists
function generate_self_signed() {
    SSL_CFG_PATH="/tmp/docker-mailserver/ssl"
    if [[ -f ${CATOP}/private/cakey.pem ]]; then
        return 0
    fi
    #from /usr/local/bin/generate-ssl-certificate
    if [[ -z ${1} ]]
    then
      FQDN="$(hostname --fqdn)"
    else
      FQDN="${1}"
    fi
    if [[ ! -d ${SSL_CFG_PATH} ]]
    then
      mkdir "${SSL_CFG_PATH}"
    fi
    cd "${SSL_CFG_PATH}" || { echo "cd ${SSL_CFG_PATH} error" ; exit ; }

    rm -rf *
    create_demo_CA

    # Create an unpassworded private key and create an unsigned public key certificate
    openssl req -subj "${SUBJ}{$FQDN}" \
        -new -nodes -keyout "${SSL_CFG_PATH}"/"${FQDN}"-key.pem \
        -out "${SSL_CFG_PATH}"/"${FQDN}"-req.pem -days 3652 2> /dev/null

    [[ -f "${SSL_CFG_PATH}"/"${FQDN}"-key.pem ]] && echo "${FQDN}-key.pem is there"
    [[ -f "${SSL_CFG_PATH}"/"${FQDN}"-req.pem ]] && echo "${FQDN}-req.pem is there"

    # Sign the public key certificate with CA certificate
    openssl ca -out "${SSL_CFG_PATH}"/"${FQDN}"-cert.pem -batch \
        -passin pass:$TESTPSSWD -infiles "${SSL_CFG_PATH}"/"${FQDN}"-req.pem 2> /dev/null

    [[ -f "${SSL_CFG_PATH}"/"${FQDN}"-cert.pem ]] && echo "${FQDN}-cert.pem is there"

    # Combine certificates for courier
    cat "${SSL_CFG_PATH}"/"${FQDN}"-key.pem \
        "${SSL_CFG_PATH}"/"${FQDN}"-cert.pem > "${SSL_CFG_PATH}"/"${FQDN}"-combined.pem


    [[ -f "${SSL_CFG_PATH}"/"${FQDN}"-combined.pem ]] && echo "${FQDN}-combined.pem is there"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  generate_self_signed
fi

