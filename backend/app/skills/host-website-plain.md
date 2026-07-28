---
slug: host-website-plain
title: Host a Website on a Plain Server
triggers: host a website, host a site, create a website, new website, add a website, launch a website, publish a website, host my site, put my site live, set up a website, wordpress on this server, host a blog
os: linux
priority: 7
requires: no-panel
mode: mission
budget: 25
recipe: true
summary: Put a website live on a server with no control panel — folder, web server config, database, HTTPS, verified.
icon: globe
variables: domain:required, kind:optional:wordpress, email:optional:admin@{{domain}}
goal_template: Host a website at {{domain}} on this server ({{kind}}), admin email {{email}}
---
GOAL: Take a plain server — nginx or Apache, no control panel — and put a working
website on it at the requested domain. Created, secured, verified, and handed over
so the owner knows what they have.

APPLIES WHEN: there is NO control panel. If CyberPanel, cPanel or Plesk is installed,
STOP and say so — the panel owns the web server configuration and writing files behind
its back leaves a site the panel cannot see or renew certificates for. Use the panel's
own runbook instead.

WHY THIS EXISTS: a competitor fills in a stored template, which only works on a machine
they built themselves in a known state. You are looking at a real server that may have
anything on it. LOOK FIRST, then decide. That is the whole advantage — do not throw it
away by assuming a layout.

STAGE 0 — GATHER (use what the user already said; ask ONCE only if something is missing):
- domain (required — e.g. shop.example.com)
- what kind of site: WordPress (default), or a plain folder for their own files
- admin email (default: admin@<domain>)

STAGE 1 — LOOK BEFORE TOUCHING (all read-only, one pass):
- Which web server is running and enabled: `systemctl is-active nginx apache2 httpd`.
  If BOTH nginx and Apache are active, STOP — they are fighting over port 80 already and
  adding a site makes it worse. Report it and ask which one to use.
  If NEITHER is installed, say so and offer to set the server up first.
- Which family: `command -v apt` vs `command -v dnf`. Config lives in
  `/etc/nginx/sites-available` + `sites-enabled` on Debian/Ubuntu, `/etc/nginx/conf.d`
  on RHEL. Apache: `/etc/apache2/sites-available` vs `/etc/httpd/conf.d`.
- Is PHP there, and which version: `php -v`, and which FPM socket or port it listens on
  (`systemctl list-units 'php*fpm*'`). Never hardcode a version — read it.
- Is a database server running: `systemctl is-active mariadb mysql postgresql`.
- Does the domain ALREADY have a config anywhere? `grep -rl "<domain>" /etc/nginx
  /etc/apache2 /etc/httpd 2>/dev/null`. If it does, STOP — you would be taking over a
  site that already exists. Report what you found.
- Where do sites live on THIS server — is there an existing convention (`/var/www/*`,
  `/srv/*`, `/home/*/public_html`)? Follow the convention you find rather than imposing
  one. A server where every other site is under `/home` should not get one under `/var/www`.

STAGE 2 — PLAN AND CONFIRM: tell the owner in one short message what you found and what
you will do — which web server, which PHP, where the files will go, whether a database
will be created. Then proceed.

STAGE 3 — CREATE (each step verified before the next):
1. The folder, following the convention you found. Owned by the web server user
   (`www-data` on Debian/Ubuntu, `nginx` or `apache` on RHEL) — check which user the web
   server actually runs as rather than assuming.
2. The web server config for the domain. Keep it minimal and ordinary: server name, the
   document root, index files, and the PHP handler pointing at the socket you actually
   found. Do not invent tuning the owner did not ask for.
3. Enable it the way THIS server does it (symlink into sites-enabled, or a file in
   conf.d), then TEST the configuration before reloading: `nginx -t` or `apachectl
   configtest`. If the test fails, remove what you added and report — never reload a
   broken configuration, because that takes down every OTHER site on the server too.
   This is the single most damaging mistake available here.
4. Reload (not restart) the web server.

STAGE 4 — DATABASE (only if the site needs one):
- Create a database and a user with a password generated ON THE SERVER.
- WRITE THE PASSWORD TO A ROOT-ONLY FILE (`/root/<domain>_db.txt`, chmod 600).
  NEVER print a password into the chat. Tell the owner the file path instead.
- Grant that user rights to that database only. Never reuse the root database account
  for a website.

STAGE 5 — THE SITE ITSELF (if WordPress):
- Download WordPress into the folder, set its database details, and let it generate its
  own salts.
- Generate the admin password on the server and write it to `/root/<domain>_wp.txt`
  (chmod 600). Again: never in the chat.
- Set file ownership so the web server can serve it and updates can be applied.

STAGE 6 — HTTPS:
- Check whether the domain actually points at THIS server: `dig +short <domain>` and
  compare with the server's own public address.
- If it does NOT point here, DO NOT attempt a certificate. It will fail, and repeated
  failures can rate-limit the domain for a week. Say plainly: "point the domain here
  first, then ask me to add HTTPS."
- If it does point here, issue the certificate with certbot for that web server, and
  confirm it renews automatically.

STAGE 7 — VERIFY, THEN HAND OVER:
- Prove the site really serves, using a Host header so it works even before DNS moves:
  `curl -sI -H "Host: <domain>" http://127.0.0.1/`
- A 200 is NOT proof on its own. Fetch a sample of the body and confirm it is the real
  site — for WordPress, look for `wp-content`; for a plain site, the file you placed.
  A blank page or a PHP error behind a 200 means it is NOT working.
- Then tell the owner, in plain words: the address, where the files are, which file holds
  the passwords, whether HTTPS is on, and what they need to do next (usually: point the
  domain, then ask for HTTPS).

PITFALLS (each of these has broken a real server):
- Reloading a web server whose configuration does not parse takes EVERY site on that
  server offline, not just the new one. Always test the config first.
- A hardcoded PHP version or FPM socket path produces a site that serves the PHP source
  code as plain text — which leaks database credentials to anyone who visits. Read the
  real socket.
- `restart` drops live connections; `reload` does not. Use reload.
- Requesting a certificate for a domain that does not resolve here wastes a rate-limited
  attempt. Check DNS first.
- Do not touch any config file belonging to another site. If you must change something
  shared, say so and ask first.
- Never print a database or admin password into the chat. Write it to a root-only file
  and give the path.
