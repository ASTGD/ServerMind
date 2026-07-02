---
slug: ssl-troubles
title: SSL/HTTPS Problems — Diagnose & Fix
triggers: ssl error, certificate expired, cert expired, https not working, ssl not working, not secure, certificate error, renew certificate, renew ssl, letsencrypt error, certbot error, mixed content, ERR_CERT
os: linux
priority: 6
---
GOAL: Fix HTTPS with the least-risk path — usually a renewal or a config pointer, not a
new certificate from scratch.

DIAGNOSTIC ORDER (read-only first):
1. What does the cert actually say right now:
   `echo | openssl s_client -connect localhost:443 -servername <domain> 2>/dev/null | openssl x509 -noout -dates -subject -issuer`
   — expired? wrong domain (subject mismatch)? self-signed?
2. Certbot's view: `certbot certificates` — lists each cert, its domains, expiry, and
   the exact paths nginx/apache should point at.
3. Expired but certbot exists → try `certbot renew --dry-run` first. If dry-run passes,
   run the real `certbot renew`, then reload the web server.
4. Renewal FAILS → read the reason, it's almost always one of:
   - Port 80 blocked/busy (http-01 needs it): `ss -ltnp | grep :80` + firewall rules.
   - DNS no longer points at this server: `dig +short <domain>` vs this box's IP.
   - The webroot moved (webroot plugin) — re-issue with the current docroot.
5. Cert valid but browser says "not secure" → the web server serves the OLD file:
   check the `ssl_certificate` path in the site's server block matches certbot's
   "fullchain" path, then `nginx -t && systemctl reload nginx`.
6. "Mixed content" warnings = page loads http:// assets, not a cert issue — for
   WordPress, the site URL must be https in settings; don't touch the certificate.
7. Auto-renew health: `systemctl list-timers | grep certbot` — if no timer/cron exists,
   add it, or the same problem returns in 90 days.

PITFALLS:
- Don't delete /etc/letsencrypt or re-issue from scratch when a renew would do —
  Let's Encrypt rate limits (5 per week per domain set) can lock the user out for days.
- `--force-renewal` is for testing, not routine — it burns rate limit.
- Reload, don't restart, the web server for cert changes (zero downtime).
- Wildcard certs need dns-01 (API access to DNS) — don't attempt http-01 for them.

VERIFY: `curl -sSI https://<domain>` returns 200/301 with no cert error, and the dates
check from step 1 shows the new expiry. Mention the new expiry date to the user.

ROLLBACK: config edits keep a .bak; a reload after restoring it returns the previous
state. Certificates themselves are additive (old ones remain on disk under archive/).
