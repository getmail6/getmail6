FROM ghcr.io/docker-mailserver/docker-mailserver:9.0.1

RUN apt-get update && apt-get -y install \
        git \
        iputils-ping \
        make \
        nmap \
        procmail \
        python-pip \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

# add our user to postfix group so we can access dovecot's LMTP unix socket
RUN useradd -m -s /bin/bash getmail \
    && usermod -a -G postfix getmail

COPY entrypoint.sh /
RUN chmod +x /entrypoint.sh

# use our own entrypoint
ENTRYPOINT ["/entrypoint.sh"]
# from https://github.com/docker-mailserver/docker-mailserver/blob/014dddafbc2e329b7c35aada498eeba8b940d83d/Dockerfile#L291
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
