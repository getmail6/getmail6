#!/bin/bash -e

# add user if it doesn't exist
if ! /usr/local/bin/listmailuser 2>/dev/null | egrep "^${TESTEMAIL}$" > /dev/null; then
    echo "* creating mailuser"
    # the env vars are set by our docker-compose.yml
    /usr/local/bin/addmailuser "${TESTEMAIL}" "${TESTPSSWD}"
    /usr/local/bin/addmailuser "other-user@example.com" "${TESTPSSWD}"
fi

if [[ ! -e "/tmp/docker-mailserver/ssl" ]]; then
    echo "* generating SSL certificate"
    /tmp/docker-mailserver/self_sign.sh
fi

# run original init
exec /usr/bin/dumb-init -- $@
