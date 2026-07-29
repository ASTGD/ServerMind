# Ploi's two-level navigation — captured from the live panel

Captured 2026-07-29 from a real Ploi account (server `testserver`, site `serverall.com`).
This is a description of what is on screen, for us to implement our own version of. No
code, no styling copied — the value is the *structure*, which is genuinely good.

---

## The idea in one line

**The second panel is the "you are inside a thing" panel.** It appears only when a specific
server or site is open, it carries that thing's identity and its own menu, and the main
panel stays where it was so you never lose your place.

---

## Level 1 — the main panel (always there)

Dark, ~183 px wide, full height.

```
ploi.io                      ← logo
[ Search…              ⌘K ]

  Dashboard
  Sharwat's Team          ⌄  ← team switcher
  ─────────────────────────
  Servers                    ← stays highlighted while you are inside a server
  Sites                      ← stays highlighted while you are inside a site
  Status pages
  Projects
  Scripts
  Backups
  Marketplace
  ─────────────────────────
  Profile
  Subscription
  Documentation
  Support

  [avatar] Sharwat Shafin  ⌄  ← pinned at the bottom
          ceo@astgd.com
```

Notes worth copying:
- Groups separated by thin dividers, no group labels.
- The account block is pinned to the bottom, not in the scroll.
- The active section keeps its highlight *even when the second panel is open*. That is what
  makes it feel like "inside", not "somewhere else".

---

## Level 2 — the context panel (only when a thing is open)

White, ~208 px wide, sits immediately right of the main panel, full height.

### For a SERVER

```
testserver                ☆   ← name + favourite toggle
● Server active               ← status dot + words

[ 170.205.52.132  ⧉ ] [ >_ SSH ]   ← IP with copy button, and an SSH button

  ▪ Sites                     ← active item has a tinted background
  ▪ PHP
  ▪ Databases
  ▪ Cronjobs
  ▪ Firewall
  ▪ SSH keys
  ▪ Daemons
  ▪ Monitor
  ▪ Insights
  ▪ Services
  ▪ Manage
  ▪ Logs
  ▪ Settings

  ────────────────────────    ← pinned to the bottom
  OS          Ubuntu 22.04 LTS
  Database    MySQL
  Specs       1 vCPU · 1 GB
```

### For a SITE

```
serverall.com             ☆
● testserver                  ← the PARENT is the subtitle, and it is a link
[ 170.205.52.132  ⧉ ] [ >_ SSH ]

  ▪ General
  ▪ SSL
  ▪ Cronjobs
  ▪ Notifications
  ▪ Redirects
  ▪ Manage
  ▪ Logs
  ▪ Settings
  ────────────────────────
  ↗ View                      ← separated: opens the real site in a new tab

  ────────────────────────
  PHP                    8.5
  System user           ploi
```

Notes worth copying:
- **Every item has an icon.** Text-only reads as a list; icon + text reads as navigation.
- **The footer is facts, not links.** Two or three lines that answer "what am I looking at"
  without a click. Different facts for a server and for a site — pick what matters for each
  asset type.
- **An outward action sits below a divider** (`View`). It leaves the panel, so it is visually
  separated from the tabs that stay inside it.
- The site panel shows the *server's* IP and SSH button — the child inherits the parent's
  connection shortcuts.

---

## The content area

Breadcrumb under the page title, and it grows as you go deeper:

```
Sites                                      ← page title
Dashboard / Servers / testserver           ← server page
Servers / testserver / serverall.com       ← site page
Servers / testserver / serverall.com / Manage / NGINX   ← sub-page of a tab
```

So a tab can have its own sub-pages (`/manage` → `/manage/nginx`) and the breadcrumb, not
the panel, carries that third level. The second panel keeps `Manage` highlighted.

---

## The list views (level 0)

Both lists share one toolbar: `Search…` · `Options ⌄` · `Order by ⌄` · `Reset filters` ·
and a **list / grid toggle** on the right.

**Servers list** — rows grouped under a project heading (`TestProject (1)`):

```
●  testserver · 170.205.52.132                                   [icon]
   1 site · Created 1 hour ago
```

**Sites list** — flat rows:

```
●  serverall.com
   ▤ testserver · 170.205.52.132 · 🐘 8.5
```

Notes worth copying:
- Two lines per row: **name on top, context underneath.** The second line is small and grey
  and answers "where does this live".
- A status dot leads the row, so scanning for a problem needs no reading.
- The site row names its server — the same job our server chips already do.

---

## How this maps to us

| Ploi | Ours |
|---|---|
| Servers list | **Assets** list (VPS, Windows, RDP, hosting, cloud) |
| Server context panel | Asset context panel |
| Sites list | Sites (already exists) |
| Site context panel | Site context panel |

Our asset panel has more to show than theirs, because we manage more kinds of thing. The
menu should change with the asset type — an RDP box has no shell, a hosting account has no
firewall — which is something Ploi never has to handle, since every one of their servers is
a machine they built themselves.

Candidate items we already have pages or APIs for:

- **Asset:** Overview · Sites · Terminal · Files · Databases · Cronjobs · Firewall ·
  SSH keys · Services · Deployments · Monitoring · Security · Threats · Backups · Logs ·
  Installed · Settings
- **Site:** Overview · SSL · Uptime · Mail health · Redirects · Logs · Backups · Settings

Footer facts for our asset panel: OS · category · last seen. For a site: server · PHP or
app type · certificate days left.

---

## What their structure does NOT have to solve, and ours does

Ploi builds every server itself, so a server is always in a shape it already knows. Ours can
be a machine that has been running for years, with a panel on it, or Windows, or an RDP box
with no shell at all. So:

- The context menu must be **built from what the asset actually supports**, not a fixed list.
- An item that does not apply should be **absent**, not shown broken. A greyed-out row that
  can never apply to this asset is noise on every visit.

---

## One thing I could not check

Ploi's **Create server** screen redirects to the subscription page on a free plan that is
already at its one-server limit, so I could not read the options it offers. What the evidence
does show: Ploi installed its own full stack on the machine, and owns the web server config
outright — the vhost begins `# Ploi Webserver Configuration, do not remove!` and pulls in
`/etc/nginx/ploi/<domain>/…`. That is consistent with a tool that expects to build the server,
not to adopt one that already has sites on it.
