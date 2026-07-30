# Send-only mail relay for ServerAlly's own notifications.
#
# Built from Ubuntu packages rather than a third-party image on purpose: this container
# holds the DKIM private key that vouches for every alert we send, so it is worth being
# able to read every line that configures it.
#
# It only ever SENDS. There is no inbound MX, no mailbox, no user accounts, and the port is
# never published — the app reaches it by service name on the internal compose network.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Postfix asks for its configuration type interactively; preseed it or the build hangs
# forever on a dialog no one can see.
RUN echo "postfix postfix/main_mailer_type select Internet Site" | debconf-set-selections \
 && echo "postfix postfix/mailname string serverally.firevps.net" | debconf-set-selections \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      postfix opendkim opendkim-tools ca-certificates iproute2 \
 && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 25
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
