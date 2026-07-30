# Servers and Sites — the structural plan

**Decided 2026-07-30.** Simpler, stronger control-panel features for Servers and Sites.
Hosting panels and cloud accounts are explicitly **out of scope for now** — they stay
working, they stop shaping the design.

---

## 1. The model we are building

> A user adds a **Linux server**. Under it they create **sites**. A site is a website
> (WordPress, Laravel), an application (Next.js / Node), or a ready-made app (Nextcloud and
> friends). One server holds many sites of different kinds. Installing is one click.

Everything below serves that sentence.

---

## 2. What we already have — more than it looks

**59 official playbooks**, and the twelve that matter here already exist:

| Already asks for a domain — is a site today | Port-only — needs a domain to become a site |
|---|---|
| WordPress · Laravel · Ghost · Nextcloud | Gitea · n8n · Uptime Kuma · Vaultwarden |
| Empty website · Web application | Portainer · Node app from GitHub |

For comparison, Ploi ships **six** built-in one-click installers (WordPress, Nextcloud,
Statamic, Craft CMS, Matomo, phpMyAdmin). Their marketplace looks larger but is thin on
inspection: twelve community items, Cloudron listed three times, almost all unrated.

**We are not short of installers. We are short of a shape to put them in.**

And the bridge for the port-only half already exists: `create-app`, built today, points a
domain at a running program through a reverse proxy. That is precisely what turns
"Gitea on port 3000" into "git.example.com".

---

## 3. The three things that are structurally wrong

### 3.1 "Bare Metal" and "VPS" are the same thing, and the code already knows it

Both categories are `connectionType: "ssh"`, and `inferCategory()` **can never return
`bare_metal`** — every SSH server falls through to `"vps"`. A customer picks "Bare Metal"
when adding a server and it displays as "VPS" forever after.

So merging is not simplification for its own sake. It removes a distinction that is already
fiction, and a choice that is already ignored.

→ **One category: "Linux Server".** Windows, RDP, Hosting Panel and Cloud stay, but move out
of the primary path.

### 3.2 A site is something we FIND, never something you MAKE

`sites` is a discovery table: `source`, `is_present`, `first_seen`, `last_seen`. It is
filled by SSHing in and reading the web server's config. There is no code path that creates
a site row.

That is why "create a website" currently feels bolted on: the installer writes a vhost, and
the site appears minutes later when discovery next runs — with no record in between of what
was asked for, whether it worked, or why it failed.

→ **Creating a site must write the row immediately** (`installing` → `live` / `failed`),
with discovery demoted to reconciliation: it confirms what we created and picks up sites
made outside ServerAlly.

This is the keystone. The catalogue is worthless without it.

### 3.3 "Install WordPress" and "create a site" are two unrelated features

Today installing WordPress is a **playbook** — a script you run against a *server*. Creating
a site is a *different* thing, with a different screen. Same outcome, two mental models.

→ **One catalogue of site types**, in three groups the customer already thinks in:

| Group | Contents |
|---|---|
| **Websites** | WordPress · Laravel · Empty site (static or PHP) |
| **Applications** | Node.js / Next.js · Python · from a Git repo |
| **Ready-made apps** | Nextcloud · Ghost · Gitea · n8n · Uptime Kuma · Vaultwarden · Portainer |

The playbooks stay exactly as they are underneath. What changes is that they are presented
as *"what do you want to put here"*, not *"which script shall I run"*.

---

## 4. The phases

**P1 — One Linux Server category.** Merge `bare_metal` into `vps`, relabel to "Linux
Server", keep existing rows working. Small, and directly removes a lie.

**P2 — A site is something you create.** Site rows written at request time with a status,
progress streamed, failures kept and explained. Discovery becomes reconciliation. *This is
the foundation; nothing else is worth building first.*

**P3 — One installer catalogue.** The three groups above, driven by the playbooks we
already have, on the server's Sites page.

**P4 — Give the port-only apps a front door.** Wrap Gitea, n8n, Uptime Kuma, Vaultwarden,
Portainer and the Git-repo app with `create-app`'s domain + reverse proxy, so installing one
produces a real site at a real address rather than an IP and a port number.

**P5 — Per-site management.** Partly built already (SSL, logs, PHP version). Fill the gaps:
databases, cron, deploy.

---

## 5. Deliberately not doing

- **Hosting panels and cloud accounts** — working, and out of the way. Per the owner.
- **A community marketplace.** Ploi's is the weakest part of their offering: unrated,
  duplicated, unmaintained. A short list we actually test beats a long list we do not.
- **Chasing every framework.** Statamic, Craft, OctoberCMS and CakePHP are Ploi's list, not
  evidence of demand. WordPress, Laravel and Node cover the overwhelming majority.

---

## 6. What makes this different from a control panel

A panel installs the thing and stops. Ours installs it, then **watches it** — uptime,
certificate expiry, malware every five minutes, alerts that reach a real person — and can
**fix it**, because Ally is already there. The installer is the entry point to that, not the
product.
