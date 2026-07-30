#!/bin/bash
# Configure and run a send-only Postfix that DKIM-signs everything it sends.
#
# Written as an entrypoint rather than baked into the image so the hostname and domain come
# from the environment — the same image works for staging without a rebuild.
set -euo pipefail

MAIL_DOMAIN="${MAIL_DOMAIN:-serverally.firevps.net}"
MAIL_HOSTNAME="${MAIL_HOSTNAME:-$MAIL_DOMAIN}"
DKIM_SELECTOR="${DKIM_SELECTOR:-mail}"
# Who may relay through us.
#
# Deliberately NARROW. The first version trusted 127.0.0.0/8 plus all of 172.16.0.0/12,
# 192.168.0.0/16 and 10.0.0.0/8 — which is every private range, so every container sharing
# the network could relay anything to anywhere. Testing it looked like a pass only because
# the test container was itself inside the trusted range; the check could never have failed.
#
# Now: loopback, plus the one subnet compose actually puts our services on, passed in
# explicitly. Safety here rests on TWO things, not one — this list, and the fact that the
# compose service publishes no port, so nothing off the host can reach 25 at all.
#
# The compose subnet is DISCOVERED from our own interface rather than hardcoded or pinned:
# every service on this network shares it, so our own address identifies exactly the set of
# containers that may send — no wider, and no compose network changes needed on a live stack.
_own_cidr() {
  local addr prefix base
  addr="$(ip -o -f inet addr show scope global 2>/dev/null | awk "{print \$4; exit}")"
  [ -n "$addr" ] || return 1
  prefix="${addr#*/}"
  base="$(ip route 2>/dev/null | awk "/proto kernel/ {print \$1; exit}")"
  # Prefer the kernel route, which is already the network address in CIDR form.
  if [ -n "$base" ]; then echo "$base"; else echo "${addr%/*}/$prefix"; fi
}
RELAY_NETWORKS="${RELAY_NETWORKS:-127.0.0.0/8 $(_own_cidr || echo "")}"

echo ">>> Configuring Postfix for $MAIL_DOMAIN (host $MAIL_HOSTNAME)"

# Log to the container's stdout, not to syslog. In a container syslog usually is not
# running, which means Postfix's errors go NOWHERE — the reason a relay that accepted and
# instantly dropped every connection looked like a silent mystery. `docker logs` is the
# right place for a container's logs anyway. (Postfix 3.4+; Ubuntu 22.04 ships 3.6.)
postconf -e "maillog_file = /dev/stdout"

postconf -e "myhostname = $MAIL_HOSTNAME"
postconf -e "mydomain = $MAIL_DOMAIN"
postconf -e "myorigin = \$mydomain"
# Accept mail only from our own containers. `inet_interfaces = all` is safe ONLY because
# the port is never published — see the compose file, which deliberately has no `ports:`.
postconf -e "inet_interfaces = all"
postconf -e "inet_protocols = ipv4"
postconf -e "mynetworks = $RELAY_NETWORKS"
# We are nobody's final destination: this box has no mailboxes, so accepting local delivery
# would mean quietly swallowing mail into /var/mail that nobody ever reads.
postconf -e "mydestination ="
postconf -e "local_recipient_maps ="
postconf -e "local_transport = error:local delivery is disabled on a send-only relay"
postconf -e "relay_domains ="
# Deliver straight to the recipient's MX. Outbound 25 is open on this host (verified).
postconf -e "relayhost ="
# Use TLS when the receiving server offers it, but never refuse to deliver because it does
# not — an alert that fails to arrive is worse than one that travelled unencrypted.
postconf -e "smtp_tls_security_level = may"
postconf -e "smtp_tls_CApath = /etc/ssl/certs"
postconf -e "smtpd_tls_security_level = none"
postconf -e "biff = no"
postconf -e "append_dot_mydomain = no"
postconf -e "maximal_queue_lifetime = 1d"
postconf -e "bounce_queue_lifetime = 1d"
# No open relay: only our networks may send, and only to real addresses.
postconf -e "smtpd_recipient_restrictions = permit_mynetworks, reject_unauth_destination"
postconf -e "smtpd_relay_restrictions = permit_mynetworks, reject_unauth_destination"

# ── DKIM ─────────────────────────────────────────────────────────────────────
# Without a signature, mail from a generic hosting IP is treated as suspicious by every
# large provider. The key is generated once and kept on a volume: regenerating it would
# invalidate the public key already published in DNS and silently break every send.
KEYDIR="/etc/opendkim/keys/$MAIL_DOMAIN"
mkdir -p "$KEYDIR"
if [ ! -s "$KEYDIR/$DKIM_SELECTOR.private" ]; then
  echo ">>> Generating a new DKIM key ($DKIM_SELECTOR)"
  opendkim-genkey -b 2048 -d "$MAIL_DOMAIN" -D "$KEYDIR" -s "$DKIM_SELECTOR" -v
else
  echo ">>> Reusing the existing DKIM key — the DNS record must match this one"
fi
chown -R opendkim:opendkim /etc/opendkim/keys
chmod 600 "$KEYDIR/$DKIM_SELECTOR.private"

# InternalHosts is the setting that actually decides whether anything gets signed.
#
# opendkim SIGNS mail from hosts it considers internal and merely VERIFIES everything else.
# The default internal list is localhost ONLY — so with the app in another container, every
# message sailed through completely unsigned, with no error anywhere: `Mode s` was set, the
# milter was connected, and postfix's milter_default_action=accept meant nothing complained.
# The absence of a DKIM-Signature header in the queued message was the only symptom.
printf "127.0.0.1\n::1\nlocalhost\n" > /etc/opendkim/InternalHosts
for net in $RELAY_NETWORKS; do echo "$net" >> /etc/opendkim/InternalHosts; done
chown opendkim:opendkim /etc/opendkim/InternalHosts

cat > /etc/opendkim.conf <<EOF
# Log to stderr so problems land in \`docker logs\` — syslog is not running in a container,
# which is why opendkim's own complaints were invisible.
Syslog                  no
LogWhy                  yes
UMask                   007
Mode                    sv
Canonicalization        relaxed/simple
Domain                  $MAIL_DOMAIN
Selector                $DKIM_SELECTOR
KeyFile                 $KEYDIR/$DKIM_SELECTOR.private
Socket                  inet:8891@127.0.0.1
OversignHeaders         From
SubDomains              no
InternalHosts           /etc/opendkim/InternalHosts
EOF

postconf -e "milter_default_action = accept"
postconf -e "milter_protocol = 6"
# 127.0.0.1, never "localhost". Postfix runs smtpd CHROOTED to /var/spool/postfix, which
# has no /etc/resolv.conf or /etc/hosts — so a hostname here cannot be resolved and smtpd
# dies with "Temporary failure in name resolution" on every single connection. The relay
# then accepts a TCP connection and drops it instantly, which looks like a mystery until
# you can see the mail log. A literal address needs no resolver.
postconf -e "smtpd_milters = inet:127.0.0.1:8891"
postconf -e "non_smtpd_milters = inet:127.0.0.1:8891"

# Print the record the operator must publish. Logged on every start so it is always
# recoverable without shelling into the container to cat a file.
echo ""
echo ">>> Publish this DKIM record in DNS:"
cat "$KEYDIR/$DKIM_SELECTOR.txt" || true
echo ""

# ── the chroot needs its own copy of the resolver ────────────────────────────
# Postfix's smtp client runs chrooted to /var/spool/postfix, so it cannot see
# /etc/resolv.conf and cannot look up a single MX record — every message defers with
# "Host or domain name not found ... type=MX". The directory ships EMPTY in this image, so
# nothing works until these are copied in. Done at startup, not build time, because Docker
# writes resolv.conf when the container starts.
#
# Same family as the milter bug above: in a chroot, anything requiring name resolution
# fails, and the failure is invisible until you read the mail log.
mkdir -p /var/spool/postfix/etc
for f in resolv.conf services hosts nsswitch.conf localtime; do
  [ -e "/etc/$f" ] && cp -f "/etc/$f" "/var/spool/postfix/etc/$f" || true
done
echo ">>> Resolver copied into the chroot: $(ls /var/spool/postfix/etc | tr '\n' ' ')"

service opendkim start
echo ">>> opendkim started"

# Postfix in the foreground so the container's lifetime is the mail server's lifetime.
exec /usr/sbin/postfix start-fg
