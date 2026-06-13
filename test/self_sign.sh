#!/usr/bin/env bash

: '
./self_sign.sh
'

CWD="$(pwd)"
export SSL_CFG_PATH="$CWD/ssl"
export CATOP="$CWD/ssl/demoCA"
# compose.yml maps to these
# export SSL_CFG_PATH="/tmp/docker-mailserver/ssl"
# export CATOP="/tmp/docker-mailserver/ssl/demoCA"
export OPENSSL_CONF="$CWD/openssl.cnf"

export SUBJ="/C=US/ST=domain/L=tld/O=Dis/CN="

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
    cd "${SSL_CFG_PATH}" || { echo "cd ${SSL_CFG_PATH} error" ; exit ; }
    openssl req  -subj $SUBJCA -passin pass:TESTPSSWD -passout pass:TESTPSSWD -new -keyout $CATOP/private/cakey.pem -out $CATOP/careq.pem
    openssl ca -subj $SUBJCA -passin pass:TESTPSSWD -create_serial -out $CATOP/cacert.pem -days 365 -batch -keyfile $CATOP/private/cakey.pem -selfsign -extensions v3_ca -infiles $CATOP/careq.pem
}

function generate_self_signed() {
    if [[ -f ${CATOP}/private/cakey.pem ]]; then
        return 0
    fi
    FQDN="$(hostname --fqdn)"
    if [[ ! -d ${SSL_CFG_PATH} ]]
    then
      mkdir "${SSL_CFG_PATH}"
    fi
    cd "${SSL_CFG_PATH}" || { echo "cd ${SSL_CFG_PATH} error" ; exit ; }

    rm -rf *
    create_demo_CA

    # Create an unpassworded private key and create an unsigned public key certificate
    openssl req -subj "${SUBJ}{$FQDN}" -new -nodes -keyout "${SSL_CFG_PATH}"/"${FQDN}"-key.pem -out "${SSL_CFG_PATH}"/"${FQDN}"-req.pem -days 3652

    [[ -f "${SSL_CFG_PATH}"/"${FQDN}"-key.pem ]] && echo "${FQDN}-key.pem is there"
    [[ -f "${SSL_CFG_PATH}"/"${FQDN}"-req.pem ]] && echo "${FQDN}-req.pem is there"

    # Sign the public key certificate with CA certificate
    openssl ca -out "${SSL_CFG_PATH}"/"${FQDN}"-cert.pem -batch -passin pass:TESTPSSWD -infiles "${SSL_CFG_PATH}"/"${FQDN}"-req.pem

    [[ -f "${SSL_CFG_PATH}"/"${FQDN}"-cert.pem ]] && echo "${FQDN}-cert.pem is there"

    # Combine certificates for courier
    cat "${SSL_CFG_PATH}"/"${FQDN}"-key.pem "${SSL_CFG_PATH}"/"${FQDN}"-cert.pem > "${SSL_CFG_PATH}"/"${FQDN}"-combined.pem


    [[ -f "${SSL_CFG_PATH}"/"${FQDN}"-combined.pem ]] && echo "${FQDN}-combined.pem is there"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  generate_self_signed
fi

