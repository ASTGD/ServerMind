# Staging sites — the plan

**Written 2026-08-02, to build next.** A customer gets a safe copy of a live website to
try changes on, and a controlled way to put those changes onto the live site.

Grounded in a live read of Ploi's own staging feature on the owner's trial account
(2026-08-02) and in our own code as it stands today.

---

## 1. What Ploi actually does — checked, not assumed

I opened the owner's Ploi account and walked every screen of both sites they created
(`laravel.firevps.net` and `staging.laravel.firevps.net`). Findings:

| | Main site | Staging site |
|---|---|---|
| Domain | `laravel.firevps.net` | `staging.laravel.firevps.net` |
| System user | `laravel-dbel2` | **the same user** |
| Folder | `/home/laravel-dbel2/laravel.firevps.net` | `/home/laravel-dbel2/staging.laravel.firevps.net` |
| Block robots | off | **on** — that is the "Robots blocked" badge |
| Created | 2026-08-02 11:43:32 | 2026-08-02 11:43:32 (the same second) |

**Ploi's "Create staging site" is a creation-time convenience and nothing more.** It makes a
second ordinary site with a `staging.` prefix, the same system user, and search engines
blocked. That is the whole feature.

Two things it does **not** do:

1. **The two sites do not know about each other.** There is no staging tab, no "push to
   live" button, and no link to the parent on either site — not on General, Manage,
   Settings, Repositories or Cronjobs. The panel stores no relationship. The form's promise
   *"you'll be able to push over the code to the main site"* is delivered only by the fact
   that both folders sit in one home under one user, so an ordinary `git` deploy or a file
   copy between them works. The nearest real button is **Manage → Clone site**, which is a
   different thing: it copies files, the repository and optionally the WordPress database
   with a URL search-replace, but it **creates a new site** — it never overwrites the main one.

2. **It copies nothing.** This is visible in the owner's own test. They asked for a Laravel
   site with staging; the staging site came out with **WordPress files half-installed**
   ("files are in place but the install isn't finished"), while the main site is Laravel.
   An empty staging site is not a staging site — it is a second empty site with a longer name.

**That second point is the design brief.** If we ship "staging" and it copies nothing, we
have shipped what the owner already has and did not find useful.

---

## 2. What we already have

More than it looks. Nearly every hard part is built.

| Piece | Where | What it gives us |
|---|---|---|
| Site rows with a real lifecycle | `backend/app/models/site.py` (`STATUSES`), `site_service.create/install/reconcile_installs` | A site is requested, built, observed, or honestly failed |
| Shared site guards | `playbook_service._SITE_GUARDS` (line 324) | Domain validated not escaped; refuses panel servers; refuses two web servers; refuses an existing config unless it carries our own marker; reads the real web user; tests the config **before** reload and undoes on failure |
| Installers | `create-site`, `wordpress-site`, `laravel-site`, `site-remove` | `/var/www/<domain>` with `public/` as the doc root, owned by the real web user |
| Deploy targets | `models/deployment.py` — and it **already has an `environment` column** | *"Staging is not a separate concept in the schema — it is a second target with a different branch and path."* Written on 2026-07-28, still true |
| Atomic release switch + rollback | `deploy_service.build_plan / switch_command / rollback_target` | A code change lands with no visible gap, and can be undone |
| Per-site everything | `site_cron_service`, `site_daemon_service`, `site_database_naming`, `php_service.config_for_site` | Cron, always-running processes, databases and PHP version, each scoped to one site |
| Backups | `backup_service` (`tar.gz`, `mysqldump`, `pg_dump`, retention, offsite) | We can take a real backup before a dangerous step |
| Honest status | `frontend/src/lib/siteStatus.ts` | `unpointed` already exists — a staging domain nobody pointed yet will read correctly on day one |
| DNS | Cloudflare account management, shipped | We can offer to add the `staging.` record instead of just telling them to |
| SSL readiness | `GET /api/sites/{id}/ssl-readiness` | We can say why a certificate cannot be issued yet |

**Sites are not plan-limited** (`entitlements.PLANS` caps servers, actions, runbooks, status
pages and team seats — not sites). So a staging copy costs the customer nothing extra, which
is right: our value metric is the server, and staging lives on a server they already pay for.
**No new gate is needed.**

---

## 3. The design decision

> **Two features, built and shipped separately: making a staging copy, and putting it live.**
> The first is cheap and safe. The second overwrites a working website and has to earn its way in.

Bundling them would mean the dangerous half holds the safe half hostage, and the safe half is
most of the value.

### 3.1 The rule that shapes everything: an environment must never talk to the other one's data

Both directions of this feature have the same worst bug, and it is not a file bug — it is a
**configuration** bug:

* Copy a live site's files to staging and leave the config alone → **staging is now writing to
  the live database.** Someone "testing" a bulk delete deletes real orders.
* Copy staging's files over live and include `.env` / `wp-config.php` → **the live site is now
  reading the staging database.** Every visitor sees test data, and new real orders land in a
  database nobody backs up.

So two rules, and both are refusals rather than warnings:

1. **A staging copy must never be left pointing at the live database.** If we cannot give it
   its own database and repoint its configuration, we **do not create it**.
2. **A promotion must never copy the site's configuration file.** `.env`, `wp-config.php` and
   anything in the configured `shared_paths` are excluded — not "excluded by default", excluded.

Rule 1 has a consequence worth stating plainly: **for an app with a database, copying the
database is not optional.** A WordPress staging site with an empty database shows the install
wizard — which is exactly the half-built thing Ploi produced in the owner's test.

### 3.2 Promotion is a deploy when there is a repository, and a copy only when there is not

This is the second big call.

If the site has a deploy target, "put staging live" means **deploy the same commit to the live
target**. That path already gives us a build in a folder nobody is serving, an atomic symlink
switch, a rollback, shared paths that survive, and a failed build that never reaches the live
site. All of it exists and all of it is tested. Nothing new is invented.

Only a site with no repository — a WordPress site edited through wp-admin — needs a real file
copy, and that is where every guard in §6.2 goes.

### 3.3 Words

Call the action **"Copy staging over the live site"**. Not "push", not "publish", not "sync".
The name has to say that something gets overwritten, because that is the one thing the person
pressing it must already know.

---

## 4. What a staging site is, in our model

A staging site is **a real site row** — it has files, a vhost, a status, an uptime check, its
own PHP version — plus three facts:

| Field | Why it exists |
|---|---|
| `parent_site_id` (FK → `sites.id`, **ON DELETE SET NULL**) | Ploi's biggest gap. Without it we cannot offer promote, cannot group the list, and cannot stop someone removing the wrong one. `SET NULL` because deleting the parent must leave the staging site standing — it is a real website with real files. It simply stops being staging. |
| `environment` (`production` \| `staging`, default `production`) | Read by the list, the promote endpoint, and the rules in §7. Mirrors the column `deploy_targets` already has, deliberately. |
| `no_index` (bool) | Whether the vhost sends `X-Robots-Tag: noindex, nofollow`. A **header**, not a `robots.txt` file: it covers PDFs and images too, and it cannot be deleted by a deploy that overwrites the docroot. |

One migration, three columns, no new table. A staging site being an ordinary site is the point:
every screen we already built — Files, Logs, Cron, Database, PHP, Daemons, Deployments — works
on it the day it exists.

**Domain naming.** Default suggestion is `staging.<domain>`, with a leading `www.` stripped so
`www.shop.com` suggests `staging.shop.com`. The customer can type anything. The existing
duplicate rule in `site_service.create` already refuses a domain that exists on the server;
add one more refusal: the staging domain may not equal the parent's.

---

## 5. Phases

### P0 — Schema and the model (small)

* Migration: `sites.parent_site_id`, `sites.environment`, `sites.no_index`.
* `site_service`: `staging_domain_for(domain)` (pure), `is_staging(site)`, `parent_of(site)`.
* API: the three fields on the site payload; `GET /api/sites` and `/servers/{id}/sites` return
  them so the frontend can group without a second request.

**Tests:** the domain suggester (leading `www.`, an already-`staging.` domain, a bare domain,
an IDN); `SET NULL` really leaves the child standing when the parent row is deleted.

---

### P1 — Create a staging copy (the safe half, and most of the value)

> **BUILT 2026-08-08, and NOT as a new playbook.** The plan below asked for a `site-stage`
> playbook; what shipped instead creates the staging site through **`site_service.create`** —
> the same door every other site uses — and then copies onto it (`staging_runner`). Every
> numbered step below is satisfied, and reusing the ordinary path is what gives the copy its
> vhost, its `installing` status, its `PlaybookRun`, `reconcile_installs`, and the
> content-not-status `verify_serves` — all things this plan wanted and would have had to
> re-implement in a second installer. A staging copy is a clone plus three things: its own
> database with the live data in it, a repointed configuration, and robots blocked.
>
> **Still outstanding from this phase:** the *Advanced settings* checkbox on the New site
> card (a second entry point, matching Ploi's creation-time flow). The button on the site
> page — the one Ploi cannot offer at all — is live on **Manage**.
>
> **One deliberate departure:** `COPY_DB` does not exist. For a site that keeps its content
> in a database, copying it is **not a choice** — with no database of its own there is
> nothing to repoint the copy at, so it would go on reading and writing the LIVE site's
> data. Anyone who wants only the files wants *Clone site*, which is exactly that.

Variables: `SOURCE_DOMAIN`, `DOMAIN`, `WEB_ROOT`, `COPY_DB`.

Steps, in order, each one a refusal rather than a guess when it cannot be satisfied:

1. **Find the source, do not assume it.** Read the live site's real document root out of its
   own web-server config — the same way `php_service.config_for_site` matches a config by the
   folder it serves. A site can be anywhere; `/var/www/<domain>` is our convention, not a law.
2. **Check free disk before copying anything.** Measure the source with `du -sb`, compare with
   `df`, and refuse with real numbers — *"this copy needs 12 GB and the disk has 4 GB free"* —
   rather than filling the disk and taking every site on the server down.
3. **Copy the files.** `rsync -a` into a new folder, excluding caches (`storage/framework`,
   `node_modules`, `.git` is kept — a staging site with its git history is more useful, not
   less). Ownership set from the real web user, the same as `create-site`.
4. **Give it its own database** when the app has one (§3.1 rule 1). New database and user
   named from the staging domain via `site_database_naming` — which already refuses a
   backslash and a quote in a generated password, because a real MariaDB taught us that
   lesson. Dump the live database, import it into the new one.
5. **Repoint the configuration.** Laravel: `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`,
   `APP_URL`, `APP_ENV=staging`, `APP_DEBUG=true`. WordPress: `wp-config.php` credentials,
   then `wp search-replace '<live>' '<staging>'` so the staging site does not send every
   visitor to the live domain. **If this step cannot complete, the whole thing is rolled back
   and nothing is left behind** — a staging site pointing at live data is worse than no
   staging site.
6. **Write the vhost** with `X-Robots-Tag: noindex, nofollow`, test the config, reload — the
   existing `apply_web_config` already undoes itself if the test fails.
7. **Verify it serves.** Fetch the staging site with a `Host:` header (no DNS needed) and
   confirm real content, not just a 200 — the same content-not-status rule the mission
   verification gate follows.

Endpoint: `POST /api/sites/{id}/staging` → creates the child row (`status="installing"`,
`environment="staging"`, `parent_site_id` set) and starts the run. It reuses
`reconcile_installs`, so a failure explains itself on the row exactly like any other install.

UI:
* **A "Create a staging copy" button on the site page** — this is the moment people actually
  want it, and it is the moment Ploi cannot serve at all (theirs is creation-time only).
* A checkbox in **Advanced settings** on the New site card, matching Ploi, for people who
  already know.

**Tests:** disk-check refusal with the numbers in the message; the config repoint is asserted
by **reading the written file back**, not by checking the script contains the word `sed`;
rollback leaves no folder, no database, no vhost, no row in a claiming state.
**Mutation tests:** removing the disk check, skipping the repoint, and letting the rollback be
partial must each fail exactly their own test.

---

### P2 — Robots blocked, as a control

The vhost header from P1, plus a toggle on the site page and `no_index` on the row so the UI
tells the truth after the fact. Small, and worth its own phase only because it applies to
ordinary sites too — a customer with a site that is not ready to be found should be able to
switch this on anywhere.

Honest wording, copied from what Ploi says because it is correct: *it is up to the search
engines to honour this request.*

---

### P3 — Promote: the Git path

When both the staging site and the live site have deploy targets, promoting is:

> deploy the commit that staging currently has, to the live target.

Read the release staging is serving (`DeployTarget.current_release`), then run the existing
deploy against the live target pinned to that commit. Everything else — build in a folder
nobody serves, atomic `mv -T` switch, `shared_paths` preserved, failed build never reaching
the live site, rollback afterwards — is already built and already proven on a real server.

**The one new thing is the pin.** `build_plan` currently deploys a branch. Promotion has to
deploy a *commit*, or "put staging live" quietly means "deploy whatever is on the branch now",
which is not what the customer just looked at and approved.

**Tests:** the generated plan checks out the exact commit; a live target with a different
repo than staging is refused, by name, before anything runs.

---

### P4 — Promote: the file-copy path (the dangerous one)

Only for a site with no repository. Every rule here exists because of a specific way this
destroys a customer's website.

| Guard | The accident it prevents |
|---|---|
| **Back up the live site first, and refuse if the backup fails** | There is no undo for this operation. A backup that did not happen is discovered only when it is needed. |
| **Never copy `.env`, `wp-config.php`, or anything in `shared_paths`** | The live site starts reading the staging database. §3.1. |
| **Never copy uploads from staging over live** | Staging's uploads are a stale snapshot; copying them deletes every file a customer uploaded since the copy was made. |
| **Never copy the database** | The live database holds real orders, real comments, real customers, all created since staging was made. Schema changes belong in migrations, which the deploy path already runs. |
| **Build beside, then switch** | The same `mv -T` rename the deploy uses, so no visitor ever sees a half-copied site. |
| **Same server only, in v1** | Cross-server is a different job with a real limit — `file_service.transfer_between` caps at 512 MB. |
| **Never on a panel server** | The panel owns the vhost. Already refused by `_SITE_GUARDS`; state it in the UI too, rather than letting someone get to the confirm dialog first. |
| **Type the live domain to confirm** | The same pattern as cloud destroy: the loss is rarely "I meant not to", it is "I did it to the wrong one". |

**An honest limitation to put in the UI, not in a footnote:** for WordPress, plugin and theme
*files* copy over, but which plugins are *active* is stored in the database — which we
deliberately do not copy. So a plugin installed on staging arrives on live switched off. Say
so on the confirm screen. Every WordPress staging tool has this problem; the difference is
whether the customer finds out from us or from their broken site.

**Tests:** each excluded path is proven by running the real copy against a real tree and
asserting the file on the destination is **unchanged**, not by asserting the command string
contains `--exclude`. **Mutation tests:** dropping any one exclusion, skipping the backup, and
replacing the atomic switch with a plain copy must each fail their own test.

---

### P5 — Housekeeping, and the things a staging site must not inherit

This phase is what stops staging from becoming an incident.

* **No cron jobs.** A staging Laravel scheduler hitting a payment API, or a staging WordPress
  firing real customer emails, is a genuine incident. Staging starts with none, and the cron
  page says why.
* **No daemons / queue workers.** A staging queue worker consuming the live queue is the same
  bug wearing different clothes.
* **No auto-deploy.** The webhook secret is not copied; push-to-deploy starts off.
* **It must never page anyone at 3am.** A staging site gets an uptime check so its row can
  show a real status, but it must not raise an escalation incident. Read `uptime_service` and
  the escalation wiring before choosing between "no monitor" and "a monitor that never
  escalates" — do not guess.
* **The list stays readable.** Twenty sites become forty if everyone makes a copy. Staging
  rows are shown under their parent with a **Staging** chip, and counted separately in the
  header the way `unfinished` and `not pointed here yet` already are.
* **Removing the parent.** `SET NULL` keeps the child alive; the confirm dialog says the
  staging copy will stay and stop being staging. Removing the staging copy is an ordinary
  removal and must never touch the parent — assert it.
* **DNS and SSL, offered rather than explained.** `staging.` is a separate hostname needing
  its own record and its own certificate. Where the domain sits on a connected DNS account we
  **offer to add the record**; otherwise the row already reads *"Not pointed here yet"*, which
  is the honest state and not an error. `ssl-readiness` already says why a certificate cannot
  be issued yet.

---

## 6. What can go wrong, and what we do about it

| Failure | Where it is handled |
|---|---|
| Staging writes to the live database | §3.1 rule 1 — refuse to create rather than create a trap |
| Live starts reading the staging database | §3.1 rule 2 — the config file is never copied |
| Copy fills the disk and takes every site on the server down | P1 step 2, refuse with real numbers |
| A half-copied site is served to visitors | P4 — build beside, atomic switch |
| Promote to the wrong site | P4 — type the live domain to confirm |
| Staging emails real customers / drains the live queue | P5 — no cron, no daemons |
| Staging pages the on-call at 3am | P5 — never escalates |
| The staging site redirects visitors to the live domain | P1 step 5 — `wp search-replace` / `APP_URL` |
| Plugins arrive on live switched off | P4 — said on the confirm screen, before the press |
| Customer deletes the parent and loses the staging work | §4 — `SET NULL`, and the dialog says so |

---

## 7. Live verification (the part that decides whether it shipped)

On the real Ubuntu TestServer, through the browser, not by unit test:

1. Take the existing Laravel site, press **Create a staging copy**, and watch it build.
2. Prove the staging site serves **its own** content with a `Host:` header — and prove it is
   using **its own database** by changing one row on staging and confirming the live site is
   unchanged. This is the whole feature; if this check is skipped, nothing has been verified.
3. Confirm the staging vhost really sends `X-Robots-Tag` (read the response headers, do not
   trust the config file).
4. Confirm staging has **no** cron jobs and **no** daemons.
5. Make a visible change on staging, promote it, and confirm the live site shows the change
   **and still has its own database, its own uploads and its own `.env`** — checked on the
   server, not inferred from a green tick.
6. Roll it back and confirm the live site returns to what it was.
7. Delete the parent and confirm the staging copy is still standing and still serving.

---

## 8. Deliberately not in v1

* **Cross-server staging** (staging on a different machine). Different job, real transfer
  limits, and nobody asked for it yet.
* **Promoting the database.** See §3.1. If it ever ships it is its own feature with its own
  confirmation, not a checkbox on this one.
* **Staging on a control-panel server.** The panel owns its vhosts; consistent with every
  other direct installer.
* **Multiple staging copies per site.** One parent, one staging, until someone needs more.

---

## 9. Open questions for the owner

1. **Should promote be a paid feature?** Making a staging copy should be on every plan — it is
   a safety feature, and §NEVER_GATED in `entitlements.py` says we do not gate safety. Promote
   is a workflow convenience and is the kind of thing agencies pay for. My recommendation:
   **both ungated in v1**, revisit once real usage exists — a gate on a feature nobody uses
   yet only makes the pricing page longer.
2. **Ploi puts sites in the system user's home; we use `/var/www`.** Not a problem to fix
   here, but worth deciding separately whether per-site system users are something we want —
   it is a real isolation improvement and it affects far more than staging.

---

## 10. Build order

**P0 → P1 → P2 → P5 → P3 → P4.**

P5 comes before either promote path on purpose: the rules that stop a staging site from
emailing customers and paging the on-call belong in place **before** anybody has a staging
site running for a week. P4 is last because it is the only step that can destroy a working
website, and it should be built on top of a feature that has already proven itself.
