# The site's Manage screen — copying Ploi, item by item

Captured from a live Ploi account on 2026-08-04 (`ploi.io/panel/servers/119405/sites/394137/manage`).
Their modals render outside `<main>`, which is why an earlier attempt to read them with a
text tool came back with the wrong panel — they have to be screenshotted.

Ploi has **ten** items. **Two are deliberately absent from ours**, not missed:

- **System user** — Ploi gives every site its own Linux user. Ours run as the web server's
  user, so the row would describe something this product does not have.
- **Tenants** — Ploi's multi-tenancy, built on that same per-site user.

That leaves **seven to build**. One is done (NGINX configuration → our vhost editor).

---

## 1. NGINX configuration — ✅ done

Shipped 2026-08-03 as `vhost_service` + the Manage page. Keep a copy, test the config
BEFORE reloading, confirm the site still answers, roll back on any failure.

## 2. Authentication (basic auth)

> "You can create basic auth users here to protect your website with a username and
> password. When you create a new user here, you will see a confirm window on your website
> to allow access. This can be useful for websites that are in development."

| Field | Notes |
|---|---|
| Name | the username |
| Password | with a **Generate** link |
| Path | optional — "You may define a route here that needs to be protected like: `/wp-admin`" |

Lists existing users; empty state "You do not have any basic auth users yet."

**Ours:** htpasswd file per site + `auth_basic` in the vhost. The password is hashed and
never stored by us. A path scopes it to one `location`.

**The trap:** getting this wrong locks the owner out of their own live site. It must follow
the redirects/vhost discipline — write, test the config, reload, verify the site still
answers, roll back on failure.

## 3. Domain aliases

> "Domain aliases make it possible to point multiple domains to one domain folder. Ploi
> manages your `server_name` variable inside the web server configuration to allow multiple
> aliases."

One field (Domain alias) + Add. Lists existing; empty state as above.

**Ours:** `sites.aliases` already exists as a column and the discovery scan already reads
`server_name`. So this is editing `server_name` in the vhost, with the same test-then-reload
rule. A certificate does NOT automatically cover the alias — say so.

## 4. File Backups

**Not a modal.** It navigates to Ploi's central backup area filtered to the site
(`/panel/backups/files?search=<domain>`).

**Ours:** we already have Backups at server level. This is a link into it scoped to this
site — plus, if it is missing, a per-site files backup target. Cheapest of the seven.

## 5. FastCGI Cache

Explanation + a single **Enable** button. Their own warning, worth keeping:

> "this feature is more advanced and can trigger unexpected behaviour. For example a page
> change that is not coming through because of the cache."

**Ours:** an nginx `fastcgi_cache` zone + directives in the site's vhost, and a way to purge
it. Enable/disable must be reversible in one click, because the failure mode is "my change
does not show up" and that is maddening without an off switch.

## 6. Clone site — a full page, not a modal

Fields: **Domain** (prefilled with the current one, editable), **Select server to clone to**,
**Start cloning process**. Runs in the background with a notification at the end.

Their honesty about scope is good and should be copied:

**Copied:** a new domain on the other server · all files · the repository if present · a
system user if needed.
**NOT copied:** modified NGINX files · SSL certificates · **databases**.

**Ours:** overlaps heavily with the staging work (docs/STAGING-SITES-PLAN.md) — a clone to
the same server with a different domain IS a staging copy. Build after the cheap ones, and
reuse whatever staging needs.

## 7. Reset permissions

A confirm dialog, and the writing is careful — worth matching:

> "the system will automatically reset the file and directory permissions for your site to a
> default, secure state... ownership for all applicable files and directories to
> predetermined user and group settings."

Considerations they list: **overwriting customizations** · **immediate impact** · **no undo**
· use judiciously.

**Ours:** `chown -R www-data:www-data` + sane file/dir modes on the site's folder. We already
learned the underlying lesson the hard way — a cron job run as root leaves root-owned files
under `storage/` and the site breaks days later — so this is the repair for exactly that.

## 8. Suspend site

| Field | Notes |
|---|---|
| Suspension message | "Custom message to display on the suspended page (default: 'Website is suspended')" |
| Reason | markdown allowed |
| HTTP response code | 200 · 403 · 404 · 410 · 451 · 503 |

> "This could especially be useful when your customer is late on paying the bills."

**Ours:** serve a static page from the vhost and return the chosen status. **503 is the right
default**, not 200: a suspended site returning 200 tells search engines the content is gone
for good, which damages a client's site permanently for a billing dispute that lasts a week.

---

## Build order

Cheapest and most-used first; the two that touch the most machinery last.

1. **Domain aliases** — smallest, and it reuses the redirects discipline exactly
2. **Authentication** — small, high value for staging sites
3. **Suspend site** — self-contained, fully specified above
4. **Reset permissions** — one command, all the care is in the writing
5. **File Backups** — mostly a link into what already exists
6. **FastCGI Cache** — needs an off switch and a purge
7. **Clone site** — biggest; fold into the staging work

Every one of them edits a live vhost, so every one follows the same rule already proven by
Redirects and NGINX configuration: **keep a copy → write → test the config → reload →
confirm the site still answers → roll back on any failure.**
