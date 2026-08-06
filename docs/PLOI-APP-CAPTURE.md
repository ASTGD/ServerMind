# Ploi's per-application screens — captured live

Read from a live Ploi trial on 2026-08-06 (account `test2ploi`, server 119773, sites
395298/395299/395300). Read directly from the panel rather than screenshotted, so the wording
below is theirs verbatim.

**Caveat on completeness.** The three sites exist but no application was actually installed
on them, so sub-tabs that need the app present (WordPress → Themes/Plugins/Search & replace,
Laravel → Octane/Reverb/Setup) do not render their contents. Their *names* are captured; what
is inside them is not. Ploi says so itself: *"WP-CLI is required to manage themes and plugins
from the panel."*

---

## 1. The site menu — 10 items

```
General · Queue · SSL · Cronjobs · Notifications · [APP] · Redirects · Manage · Logs · Settings
```

`[APP]` is the per-application tab and is the subject of this document.

**How it appears is the important part.** It is NOT detected. Settings → *Project details*
has a **Project type** the customer picks by hand:

> "You can mark your project as a specific type here. This will enable additional options in
> our panel matching your type. For example, if you choose Laravel we will show an additional
> tab with Laravel options."

Types: **None (Static HTML or PHP) · Laravel · NodeJS · Statamic · Craft CMS · Symfony ·
WordPress · Redirect**.

ServerAlly does this from `sites.app_type`, which discovery sets by looking at the server. Ours
is better when detection works and has nothing to fall back on when it doesn't; theirs always
works and always asks.

---

## 2. Laravel tab

Tabs: **Edit environment · Custom commands · Commands · Octane · Reverb · Logs · Setup**

`Edit environment` is FIRST — the `.env` editor is the headline Laravel feature.

The Commands tab is a grid of artisan commands in 11 named groups:

| Group | Commands |
|---|---|
| About | `about` |
| Cache | `cache:clear` |
| Config | `config:clear` · `config:cache` |
| Database | `migrate:status` |
| General | `down` · `up` · `version` · `env` |
| Queue | `queue:failed` · `queue:flush` · `queue:restart` · `queue:retry all` |
| Optimize | `optimize` · `optimize:clear` |
| Route | `route:list` · `route:cache` · `route:clear` |
| Store | `storage:link` |
| Scheduler | `schedule:run` · `schedule:list` |
| View | `view:clear` · `view:cache` |

Note what is **absent**: no `migrate`. Ploi offers `migrate:status` only — the read. The
migration itself belongs to their deploy script.

---

## 3. WordPress tab

Tabs: **General · Themes · Plugins · Search & replace · WP-CLI**

General page, verbatim:

| Block | What it does |
|---|---|
| **Configuration** | "Edit wp-config.php" |
| **Cronjob** | Replaces WP's own timer with a real cron. Frequency: 1 / 2 / 5 / 10 / 15 minutes |
| **WP-CLI** | "WP-CLI is required to manage themes and plugins from the panel. Install it to unlock theme and plugin management." |
| **WP_DEBUG** | "Enable WordPress debug mode to log PHP errors and warnings. The debug log is stored outside the public directory so it is never accessible from the web." |
| **XML-RPC** | "XML-RPC is used by some plugins and apps but is a common attack vector for brute-force and DDoS attacks. Block it if you don't need it." |
| **Clone site** | "Clone this WordPress site to the same or a different server, **including the database with automatic URL replacement**." |

That last row matters: their generic Clone site does **not** copy a database, but their
WordPress clone does, and rewrites the URLs. Ours copies files only, for every type.

---

## 4. NodeJS tab

Tabs: **General · Settings**

General is a status panel:

```
Service                     pm2
Host                        localhost
Port                        3001
Restart after deployment    Yes
[Spawn]
```

With a note that PM2 needs extra setup to survive a reboot, linking to a guide.

---

## 5. Queue — a Laravel queue-worker builder

Its own top-level menu item, not part of the Laravel tab. Fields:

```
PHP version (CLI default / 8.5) · Connection · Queue
Maximum seconds per job   "The number of seconds a child process can run"
Sleep time                "Number of seconds to sleep when no job is available"
Processes                 "The number of processes to spawn"
Maximum tries             "Number of times to attempt a job before logging it failed"
Backoff                   "Seconds to wait before retrying a job that encountered an uncaught exception"
Memory                    "The memory limit in MB (default 128MB)"
Environment
```

---

## 6. Notifications — per site

* **Deploy notifications** — events *Deployment completed · started · failed*, plus a channel
* **Webhook URLs** — separate "deployment start" and "deployment" URLs, POSTed with
  `{server_id, site_id, latest_deploy_log, root_domain, status}`

---

## 7. Settings — everything on the page

Site domain (root domain · web directory · tags) · **Block robots** ·
**Test domain** ("try out your application before going live or switching DNS — you get a URL
from us") · Project type (above) · Project directory · **Configuration file location**
("if your configuration file (.env, wp-config.php) is outside of your project root") ·
Project grouping · **DNS settings** (Bunny · Cloudflare · DigitalOcean · Hetzner · Linode ·
Vultr) · PHP version · Site ID (for their API) · Site notes · Danger zone (delete).

## 8. SSL, Cronjobs, Logs

* **SSL** — Let's Encrypt · ZeroSSL · install existing · create signing request; multiple
  domains comma-separated; request via a DNS provider; force request (skip DNS verification);
  **HTTP/3** (opens 443 UDP in the firewall)
* **Cronjobs** — command · user · frequency (every minute / hourly / nightly 2AM / weekly /
  monthly / custom) · description
* **Logs** — one dropdown listing `[Ploi] System logs`, `[Ploi] Deploy logs`, and the site's
  own NGINX error log; "Clear all logs"

## 9. 1-click installers

**WordPress · Nextcloud · Statamic · Craft CMS · Matomo · phpMyAdmin.** There is no Laravel
installer — Laravel arrives through *Install Repository*.

---

# What this means for ServerAlly

## Menu coverage

| Ploi | ServerAlly | |
|---|---|---|
| General | Overview | ✓ ours also carries the installers + deploy |
| SSL | HTTPS | ✓ |
| Cronjobs | Scheduled jobs | ✓ |
| Redirects | Redirects | ✓ |
| Manage | Manage | ✓ 8 of their 10, 2 deliberately absent |
| Logs | Logs | ✓ ours discovers more log files |
| Settings | Settings | partial |
| Queue | Always running | partial — ours is a generic daemon, theirs is a queue builder |
| **Notifications** | — | **absent** |
| App tab | App section | partial, see below |

We additionally have, with no Ploi equivalent at site level: **Database · PHP settings ·
Uptime · Ally**.

## The real gaps, in the order I would fix them

1. **No NodeJS application section at all.** `app_registry` knows `wordpress`, `laravel`,
   `php`. Our Web-application installer writes the systemd unit and then the site has no page
   for it — no status, no restart, no port. Ploi's is thin (five facts and a Spawn button) so
   this is cheap and closes a whole missing type.
2. **WordPress is much thinner than theirs.** We do updates, activate/deactivate, maintenance
   and cache flush. We have no `wp-config.php` editor, no WP-cron replacement, no WP_DEBUG
   toggle, no XML-RPC block, no search-and-replace, no WP-CLI console. The two security
   toggles are the cheapest and the most valuable.
3. **Laravel commands are narrower.** We have 7 actions; they surface 24 reads and writes
   grouped by area, plus custom commands. Ours already covers the dangerous half (we offer
   `migrate`, they only offer `migrate:status`) — the gap is the safe reads: `about`,
   `route:list`, `schedule:list`, `queue:failed`, `env`.
4. **Queue workers.** Ours is a generic "Always running" daemon; a Laravel queue worker has
   real parameters (tries, backoff, memory, processes, sleep) that decide whether jobs get
   retried or silently lost.
5. **Settings is missing several things** — Block robots, Test domain, configuration-file
   location, per-site notes.
6. **Per-site deploy notifications and webhooks.** We have notification channels at server
   level and webhooks at account level, but nothing that says "tell me when THIS site
   deploys".

## Where we are ahead

Sites are **detected**, not declared. Ally. Uptime and certificate expiry per site. Database
management per site. Malware and security scanning. Panel servers work at all — Ploi cannot
manage a CyberPanel box, and our deploy now works on one.
