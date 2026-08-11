---
slug: github-deploy
title: Deploy a GitHub Repo to This Server
triggers: deploy from github, host github, github repo, github.com/, deploy my repo, deploy this repo, host my project, deploy my project, host a repo, deploy a repository, host everything from github
os: linux
priority: 9
mode: mission
budget: 25
recipe: true
summary: Take a GitHub repo and make it live on this server — auto-detected, secured, and verified.
icon: github
variables: repo:required
goal_template: Deploy the GitHub repo {{repo}} to this server
---
GOAL: Take a GitHub repository and make it live on this server — detect what the app
is, host it the right way for THIS server (panel-aware), secure it, verify it, and
leave a clean redeploy path.

STAGE 0 — GATHER (ask, don't guess):
You need: the repo URL, the domain (or "use the server IP for now"), and whether the
repo is private (private → ask the user to add a deploy key or use a token URL — never
ask them to paste a password/token into chat; they can place it on the server file
themselves). If the domain's DNS doesn't point at this server yet, say so — SSL will
have to wait until it does.

STAGE 1 — DISCOVER THE SERVER:
- Web stack present? nginx / apache / OpenLiteSpeed: `systemctl list-units --type=service | grep -Ei "nginx|apache|httpd|lsws|lscpd"`.
- CyberPanel? (`ls /usr/local/CyberCP` exists) → websites live at
  /home/<domain>/public_html, PHP via lsphp, OLS restart: `systemctl restart lsws`.
  Prefer creating the site through the panel the user already uses; on plain servers
  create an nginx vhost instead.
- Runtimes available: `command -v git node npm php composer python3 docker | xargs -n1 echo`.
- **On LiteSpeed/CyberPanel, `command -v php` is the WRONG PHP.** It answers with the
  distribution's old CLI (often 7.4 or 8.3) while the sites run a much newer lsphp. Find the
  real one, newest first, and prove it before using it:
  `ls -d /usr/local/lsws/lsphp*/bin/php /usr/bin/php8* /usr/local/bin/php8* /usr/bin/php
  /usr/local/bin/php 2>/dev/null | sort -rV`
  then `"$c" -v` on each until one is new enough. This is the same list
  `laravel_service` uses — keep the two in step.

STAGE 2 — DISCOVER THE APP (clone first, shallow):
Clone to a staging path, NOT the docroot: `git clone --depth 1 <repo> /opt/deploy/<name>`.
Then look at the top level and decide the TYPE:
- `index.html`, no build files            → STATIC
- `package.json`                          → NODE: read "scripts" — a "build" that
  outputs dist/build/out (vite/react) = STATIC-AFTER-BUILD; a "start" server
  (express/next start) = NODE SERVICE (needs a port + reverse proxy + process manager)
- `composer.json` / `artisan` / `*.php`   → PHP (Laravel: docroot is /public)
- `requirements.txt` / `manage.py`        → PYTHON SERVICE (venv + gunicorn/uvicorn + proxy)
- `docker-compose.yml` / `Dockerfile`     → prefer the container path: compose up and
  reverse-proxy to its port
State the detected type to the user before continuing.

STAGE 3 — HOST IT BY TYPE:
- STATIC / STATIC-AFTER-BUILD: run the build if any (`npm ci && npm run build`), copy
  the OUTPUT (dist/build/out or the files themselves) into the site docroot.
- NODE SERVICE: `npm ci` (+ build if the app has one); run under pm2
  (`pm2 start <entry> --name <name> && pm2 save && pm2 startup systemd`) on an internal
  port (3000+; check it's free: `ss -ltn`); reverse-proxy the domain to it.
- PHP/Laravel: `$PHP /usr/local/bin/composer install --no-dev` using the PHP you resolved
  in STAGE 1 — **never the bare `composer`**, which picks up the wrong PHP. Docroot to
  /public; `cp .env.example .env` + `$PHP artisan key:generate`; DB if required (create
  db+user, put creds in .env on the server — never echo them); `$PHP artisan migrate` only
  with user approval.
  If Composer reports a dependency needing a NEWER PHP than any binary here, say which
  version is needed and stop — installing a whole new PHP on a live shared server is the
  owner's decision, not a workaround to improvise. Note that `composer.json` and
  `composer.lock` can disagree: the lock is what Composer enforces.
- PYTHON: venv + pip install; gunicorn/uvicorn behind the proxy; a systemd unit so it
  survives reboots.
- DOCKER: `docker compose up -d`, then proxy to the exposed port.

STAGE 4 — SECURE + VERIFY:
- SSL once DNS points here: certbot (or the panel's SSL action on CyberPanel).
- Verify like a user: `curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1/ -H "Host: <domain>"`
  expect 200/301, then the https URL after SSL. A service type also gets its port
  checked directly first.
- Show the user the URL and what was installed where.

STAGE 5 — LEAVE A REDEPLOY PATH:
Tell the user: updates = `git pull` in the app directory + the same build/restart
step; offer to save it as a script in My Scripts. Remember (memory) what was deployed
and where.

PITFALLS:
- NEVER build inside the live docroot — build in /opt/deploy, then move the output.
- **`lsphp` is the web server's PHP, not a command-line PHP.** Composer refuses it outright
  ("cannot be run safely on non-CLI SAPIs"), and NO combination of `-d register_argc_argv`,
  `-c`, or a php.ini edit will change that — it is the SAPI, not the setting. The CLI build
  sits beside it: `/usr/local/lsws/lsphp84/bin/php` (note: `php`, not `lsphp`). Use that.
- **`lsphp` prints its usage banner and exits 0 when given a flag it does not support**
  (it accepts only `-b -c -n -h -i -q -s -v -?`). A usage banner means YOUR ARGUMENT WAS
  REFUSED, not that the command ran and failed — do not retry variants of that argument.
  Treat any help/usage output plus exit 0 the same way, from any tool.
- **Never edit shared web-server configuration to make a command-line tool run.** A panel's
  `php.ini` serves every site on the machine, so a change there is a change to sites that
  have nothing to do with this deploy. If a shared config genuinely must change, that is a
  destructive step: ask first, and restore it in the same step that changes it.
- Don't overwrite an existing site: if the docroot is non-empty, STOP and ask.
- `npm ci`/builds can OOM small VPSes — if RAM < 2GB, check `free -h` first and warn;
  a temporary swap file is the fix, with the user's OK.
- Secrets (.env, API keys, DB passwords) are written on the server, never printed to
  chat, never committed to the repo.
- Ports: never expose the app's internal port through the firewall — only 80/443; the
  proxy does the rest.
- If anything needs the user's account choices (which domain, DB name), ASK — one
  clear question, not assumptions.
