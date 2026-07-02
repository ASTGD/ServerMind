---
slug: nginx-errors
title: Nginx 502/504/Config Errors
triggers: 502 bad gateway, 502 error, 504 gateway timeout, 504 error, nginx error, nginx not starting, nginx failed, bad gateway, gateway timeout, nginx config
os: linux
priority: 6
---
GOAL: Read the error from nginx's own logs and fix the actual upstream/config issue —
502/504 are nginx REPORTING a problem, almost never nginx BEING the problem.

DIAGNOSTIC ORDER (read-only first):
1. `nginx -t` — config syntax + which file/line if broken.
2. `systemctl status nginx` + `journalctl -u nginx -n 20 --no-pager` if not running.
3. For 502/504: read the site's error log (path in its server block; default
   /var/log/nginx/error.log): `tail -30 /var/log/nginx/error.log`. The line names the
   upstream and the reason:
   - "connect() failed (111: Connection refused)" → the upstream (PHP-FPM, node app,
     gunicorn…) is DOWN → `systemctl status` that service, start it, find why it died.
   - "connect() to unix:/run/php/....sock failed (2: No such file)" → socket path
     mismatch: compare fastcgi_pass in the server block with the fpm pool's `listen`.
   - "upstream timed out" (504) → the app is too slow: check the app's own logs/load
     first; only raise proxy_read_timeout when the slowness is legitimate (long jobs).
   - "(13: Permission denied)" on a socket → user/group mismatch between nginx and
     the upstream socket.
4. 413 (body too large) → client_max_body_size; 403 → docroot permissions or a missing
   index; too many open files in error.log → worker_rlimit_nofile.
5. After any fix: `nginx -t && systemctl reload nginx` — test-then-reload, never a
   blind restart.

PITFALLS:
- Never edit nginx configs without a .bak copy of the exact file changed.
- Raising timeouts to "fix" a 504 hides a real app problem — say so to the user.
- Multiple sites share the daemon: a broken config in ONE vhost blocks reloads for ALL
  — that's why `nginx -t` comes before every reload.
- Don't disable SELinux to fix a permission error (RHEL family) — use the right
  boolean (`setsebool -P httpd_can_network_connect 1` for proxying) instead.

VERIFY: `curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1/<affected path>`
returns the expected code, and the error log stays quiet while you re-test.

ROLLBACK: restore the .bak config, `nginx -t && systemctl reload nginx`. If an upstream
service was changed, its unit can be stopped/started back to the previous state.
