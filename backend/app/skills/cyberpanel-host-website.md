---
slug: cyberpanel-host-website
title: Host a Website / WordPress on CyberPanel
triggers: host a wordpress, wordpress site, host a website, host a site, host a blog, new wordpress, install wordpress, create a website, launch a website, publish a website, host my website, set up wordpress, setup wordpress
os: linux
priority: 8
mode: mission
budget: 25
---
GOAL: Put a complete, working website (WordPress by default) live on this CyberPanel
server — created through the panel's own CLI so it shows up in CyberPanel, secured,
verified, and handed over cleanly.

APPLIES WHEN: CyberPanel is installed (`/usr/local/CyberCP` exists / `command -v
cyberpanel`). If it is NOT installed, say so — this runbook is panel-specific
(a plain-server WordPress needs the normal LEMP path instead).

STAGE 0 — GATHER (use what the user already said; ask ONCE only if missing):
- domain (required — e.g. blog.example.com)
- site title (default: the domain), admin email (default: admin@<domain>), PHP (default 8.1)

STAGE 1 — PRECONDITIONS (read-only first):
- `cyberpanel listWebsitesJson` — the domain must NOT already be there.
- CRITICAL (learned live): CyberPanel's CLI can print {"success": 1} while actually
  failing. NEVER trust the success message — after every write, VERIFY the result in
  the list before moving on. One write at a time; never create two things back-to-back.

STAGE 2 — CREATE THE WEBSITE:
`cyberpanel createWebsite --package Default --owner admin --domainName <domain> --email <email> --php 8.1`
Then verify: `cyberpanel listWebsitesJson` now contains <domain>.
If it is missing: `tail -3 /home/cyberpanel/error-logs.txt` ("Websites matching query
does not exist" = the create silently failed), wait ~10 seconds, retry ONCE. Still
missing → report honestly and stop. A domain that failed before may keep failing
(residual state) — deleting it first (`cyberpanel deleteWebsite --domainName <domain>`,
needs approval) or a fresh name usually clears it.

STAGE 3 — INSTALL WORDPRESS (it creates its own database — no createDatabase needed):
Generate the admin password ON THE SERVER — never type, print, or echo a password:
`umask 077 && openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 20 > /root/wp_creds_<domain>.txt`
Then install, reading the password from that file:
`cyberpanel installWordPress --domainName <domain> --email <email> --userName admin --password "$(cat /root/wp_creds_<domain>.txt)" --siteTitle "<title>"`
Verify files landed: `ls /home/<domain>/public_html/wp-config.php`.

STAGE 4 — SSL (be honest about DNS):
Let's Encrypt only works when the domain's DNS points at this server. Check:
`dig +short <domain>` (compare to the server's IP). If DNS does not point here, SKIP
`issueSSL`, keep the site on HTTP/self-signed, and tell the user exactly what to do
later (point DNS → then `cyberpanel issueSSL --domainName <domain>`). If DNS is
correct: `cyberpanel issueSSL --domainName <domain>`.

STAGE 5 — VERIFY THE SITE WORKS (no DNS needed):
`curl -s -o /dev/null -w '%{http_code}' -H "Host: <domain>" http://127.0.0.1/` → 200/301/302
`curl -s -H "Host: <domain>" http://127.0.0.1/ | grep -io "wp-content" | head -1` → WordPress is serving
`curl -s -o /dev/null -w '%{http_code}' -H "Host: <domain>" http://127.0.0.1/wp-login.php` → 200

STAGE 6 — HAND OVER (status "done" summary):
- Site: http://<domain> (note if DNS is still pending — until then it only answers by IP/Host header)
- WordPress admin: http://<domain>/wp-admin — username `admin`
- Password: saved in `/root/wp_creds_<domain>.txt` (root-only) — tell the user to read
  it in the File Manager and delete the file after saving it. NEVER show it in chat.
- If SSL was skipped: say the exact next step after DNS points here.

PITFALLS:
- OpenLiteSpeed serves the sites (NOT nginx): service is `lsws`; restart with
  `systemctl restart lsws` only if needed.
- installWordPress needs the website to exist first (Stage 2) — it installs into it.
- Keep the budget in mind (20 steps): no detours, verify and move on.
