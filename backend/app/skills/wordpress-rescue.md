---
slug: wordpress-rescue
title: WordPress Site Down — Rescue
triggers: wordpress down, site is down, white screen, wsod, error establishing a database connection, wordpress broken, wordpress not working, wp site, 500 error on my site, my website is down, website not opening
os: linux
priority: 10
---
GOAL: Bring the WordPress site back safely and identify the real cause — never guess-fix.

DIAGNOSTIC ORDER (read-only first, one layer at a time):
1. Web server up? `systemctl status nginx` (or apache2/httpd/lsws). If down → check why
   BEFORE restarting: `journalctl -u nginx -n 30 --no-pager` and `nginx -t`.
2. From the box itself: `curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1/` —
   200/301 means the web layer is fine and the problem is upstream (PHP/DB) or DNS/CDN.
3. PHP running? `systemctl status php*-fpm` — a dead PHP-FPM is the #1 cause of
   white screens and 502s. Socket mismatch between nginx conf and fpm pool is #2.
4. Database up? `systemctl status mysql mariadb` (one will exist). Test the site's own
   credentials: read DB_USER/DB_NAME from wp-config.php (`grep -E "DB_(NAME|USER|HOST)" wp-config.php`
   — NEVER print DB_PASSWORD to the chat) and try a connection as that user.
5. "Error establishing a database connection" with DB up = wrong credentials, a
   crashed table, or DB disk full. Check `df -h` — full disk breaks MySQL silently.
6. Logs, in this order: the site's nginx error log (path is in the server block),
   PHP-FPM log (/var/log/php*-fpm.log), then WordPress debug: only if needed, enable
   WP_DEBUG_LOG in wp-config.php temporarily and read wp-content/debug.log.
7. White screen with everything running = usually a broken plugin/theme or PHP fatal.
   Confirm in the PHP/debug log, then disable ONLY the named plugin:
   `mv wp-content/plugins/<plugin> wp-content/plugins/<plugin>.off` (reversible).

PITFALLS:
- Back up wp-config.php before any edit (`cp wp-config.php wp-config.php.bak`).
- Never `rm` a plugin — rename it, so the fix is reversible.
- Don't restart MySQL as a first move; if the disk is full, restarting can make
  recovery harder. Free space first (logs, tmp), then restart.
- Don't chown the whole docroot blindly; note the current owner first (`stat -c %U .`).
- If a cache/CDN (Cloudflare) sits in front, the origin may be fine — test locally first.

VERIFY: `curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1/` returns 200, AND the
homepage HTML contains real content (`curl -s http://127.0.0.1/ | grep -i -m1 "<title>"`).
Then check wp-admin loads too — front page and admin can fail separately.

ROLLBACK: every change above is reversible — restore wp-config.php.bak, rename the
plugin back, re-enable services. State clearly what was changed and how to undo it.
