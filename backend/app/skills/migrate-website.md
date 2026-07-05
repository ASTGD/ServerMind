---
slug: migrate-website
title: Migrate a Website to This Server
triggers: migrate a website, migrate the website, migrate a site, migrate my site, migrate my website, move a website, move the website, move a site, move my website, move my site, transfer a website, migrate wordpress, move wordpress, migrate a wordpress site
os: linux
priority: 9
mode: mission
budget: 40
recipe: true
summary: Move a website — its files and database — from another server onto this one, then verify it works here.
icon: migrate
variables: domain:required, source:required
goal_template: Migrate the website {{domain}} from server {{source}} to this server — move its files and database, wire it up, and verify it works here
---
GOAL: Copy a website (files + database) from a SOURCE server onto THIS (target) server,
restore it, rewire its config, and verify the copy actually serves — WITHOUT changing or
deleting anything on the source. A migration is a COPY: the source keeps running until the
user is happy and points DNS at the new box.

CROSS-SERVER JOB — you act on TWO servers:
- SOURCE = the server named in the request (where the site lives now). Read + dump only.
- TARGET = the server this mission is running on (where the site is going). All the
  building happens here.
Use the mission `transfer` action to move a file from SOURCE to TARGET (both must be in
your executable roster). Keep DB passwords in files/env, NEVER on the visible command line
or in chat.

STAGE 1 — UNDERSTAND THE SOURCE (read-only):
- Find the site on SOURCE by its domain: the document root (a panel puts it under
  /home/<domain>/public_html; a plain server under /var/www/<domain> or similar).
- If it's WordPress, read wp-config.php for DB_NAME, DB_USER, DB_HOST and the table prefix
  (you need these; treat the password as a secret — reference the file, don't echo it).
  For a non-WP app, find its config + database the same way.
- Note the file and DB sizes so nothing gets silently truncated later.

STAGE 2 — PACKAGE ON THE SOURCE (approval to write the archives):
- Dump the database on SOURCE with mysqldump into a file under /root (pass the password via
  a temp `--defaults-extra-file` or MYSQL_PWD env, never on argv).
- tar.gz the document root into a file under /root.
- Verify both archives exist and are non-empty before moving on.

STAGE 3 — TRANSFER TO THE TARGET (the `transfer` action):
- transfer the DB dump and the files archive from SOURCE to TARGET (into /root on TARGET).
- Confirm both arrived intact on TARGET (sizes match the source).

STAGE 4 — REBUILD ON THE TARGET (approval on each write):
- Create the destination site the right way for THIS server: if it runs CyberPanel, create
  the website through the `cyberpanel` CLI so the panel knows about it; otherwise make the
  document root + web-server vhost.
- Create a fresh database + user on TARGET; import the dumped SQL into it.
- Extract the files archive into the new document root; fix ownership/permissions to the
  site's user.
- Rewrite the app config for THIS server: point DB_HOST/DB_NAME/DB_USER/DB_PASSWORD at the
  new database. For WordPress, if the domain is unchanged keep siteurl/home; only rewrite
  them (wp-cli search-replace, AFTER a DB backup) if the site is moving to a new domain.

STAGE 5 — VERIFY + HAND OVER (status "done"):
- Prove the copy serves ON THE TARGET without needing DNS yet: curl the site over HTTP with
  a Host header for its domain and confirm it returns the real page (not an error, and no
  "error establishing a database connection").
- Be honest about DNS: the site isn't live for visitors until the domain's A record points
  at THIS server's IP — give the user the exact record to set, and note SSL should be
  issued AFTER DNS points here (offer the domain + SSL recipe).
- Confirm the SOURCE is untouched and still serving. Summarize what was copied and where
  the archives live.

PITFALLS:
- COPY, never move: never delete or edit the site on the SOURCE — if anything fails, the
  source is still the live site.
- Back up the TARGET's DB before any wp-cli search-replace (domain change).
- Never reboot. Keep DB passwords out of the visible command line and out of chat.
- A very large site may exceed the step budget — if so, say exactly where you got to and
  what's left; don't half-finish silently.
