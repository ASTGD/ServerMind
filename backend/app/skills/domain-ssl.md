---
slug: domain-ssl
title: Point a Domain + Get SSL
triggers: point a domain, point my domain, point the domain, set up ssl, setup ssl, set up free ssl, get ssl, install ssl, add ssl, free ssl, enable https, https for my site, https for the site, secure my domain
os: linux
priority: 7
mode: mission
budget: 20
recipe: true
summary: Get a domain serving over HTTPS on this server — check its DNS first, then issue a free SSL certificate.
icon: ssl
variables: domain:required
goal_template: Point the domain {{domain}} to this server and set up free SSL (HTTPS) for it
---
GOAL: Get {{domain}} served over HTTPS on THIS server with a free (Let's Encrypt)
certificate. A certificate can only be issued once the domain's DNS actually points at this
server, so CHECK DNS FIRST and be honest if it isn't pointing here yet.

STAGE 1 — DNS CHECK (read-only): find THIS server's public IP, then resolve {{domain}}
(dig / host) and compare.
- If {{domain}} already resolves to this server's IP → good, proceed.
- If it does NOT (or doesn't resolve) → STOP before issuing anything: tell the user the
  exact record to add at their registrar (an A record for {{domain}} → <this server's IP>),
  explain propagation can take a while, and offer to continue once it points here. Do NOT
  keep retrying against a domain that isn't pointed — that just burns Let's Encrypt rate
  limits.

STAGE 2 — SITE EXISTS? (read-only): confirm a web server is serving {{domain}} on this box
(a vhost / a panel website). If there's no site for it yet, say so — a certificate needs a
site to attach to (offer the host-a-website recipe first).

STAGE 3 — ISSUE THE CERTIFICATE (approval): issue it the right way for THIS server — if it
runs CyberPanel, use the panel's `cyberpanel issueSSL`; otherwise use certbot with the
matching web-server plugin (nginx / apache). Use a real contact email.

STAGE 4 — FORCE HTTPS + VERIFY (approval for the redirect): enable the HTTP→HTTPS redirect,
then VERIFY: curl https://{{domain}} and confirm a valid certificate + the real page (not a
certificate warning, not the default page). Confirm the auto-renewal timer/cron is present.

STAGE 5 — HAND OVER (status "done"): confirm HTTPS works and auto-renewal is set. If DNS
wasn't pointed and you stopped at STAGE 1, hand back the exact record to add and how to
resume — never report success you didn't achieve.

PITFALLS:
- Never issue or retry a certificate for a domain that doesn't resolve to this server —
  you'll hit Let's Encrypt rate limits. DNS first, always.
- Never reboot.
