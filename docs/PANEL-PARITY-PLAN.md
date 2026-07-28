# Plan — everything the other providers have, plus Ally

**Prepared 2026-07-28.** Decision taken by the owner: ServerAlly moves toward a full
server-management product, matching what Ploi, RunCloud, Forge, SpinupWP and GridPane
offer — while keeping Ally as the thing none of them can copy.

Competitor facts are from [MARKET-RESEARCH-2026-07.md](MARKET-RESEARCH-2026-07.md) and
[COMPETITOR-PLOI-TEARDOWN.md](COMPETITOR-PLOI-TEARDOWN.md), both read from vendors' own
pages and one live trial account. Our own column was checked against the code on the day
this was written, not against older notes — three items previously assumed present turned
out to be absent.

---

## 1. The goal in one sentence

**A customer connects a blank server and, without touching a terminal, ends up with a
secured server running their websites — and ServerAlly keeps watching it afterwards.**

The first half is what competitors sell. The second half is ours alone.

---

## 2. Where we stand today

### Already done — no work needed

| | |
|---|---|
| Deploy from Git, deploy on push, rollback, staging target | Shipped 2026-07-28 |
| Firewall screen, with lockout protection | Shipped 2026-07-28 |
| SSH key management | Shipped 2026-07-28 |
| DNS records (Cloudflare) | Shipped 2026-07-28 |
| Cloud accounts — import, create, resize, delete | Shipped 2026-07-28 |
| Backups, including offsite to six storage providers | Shipped 2026-07-25 |
| Uptime, certificate expiry, service monitoring, alerts, on-call | Shipped 2026-07-25 |
| Server log viewer | Shipped 2026-07-25 |
| Scheduled jobs · Teams and roles · White-label · API · Terminal · File manager | Earlier |
| 41 one-click installers | Earlier |
| **Security scanning, malware detection, hack cleanup, incident reports** | **Nobody else has this** |

### Genuinely missing — verified in the code today

| Gap | Reality now | They have it |
|---|---|---|
| **Set up a fresh server** | 41 installers exist, but no single flow that runs them in order | All five |
| **Create a website on a plain server** | Works on CyberPanel only, through Ally | All five |
| **Create a database on a plain server** | Panel servers only | All five |
| **Certificate for one site** | A general installer, not per-site | All five |
| **Background workers (queues)** | Nothing | Ploi, RunCloud, Forge |
| **PHP version per site** | We detect it; we cannot change it | All five |
| **Copy a site for testing (staging/clone)** | Nothing | Ploi, RunCloud, SpinupWP |
| **Site isolation** (own user per site) | Nothing | Ploi, RunCloud |
| **Suspend a site** | Nothing | Ploi |
| **Command-line tool** | Nothing | Forge, SpinupWP, GridPane |

---

## 3. The rule that decides how each gap gets built

This is the most important section. It is what keeps us from becoming a slower copy of a
free product.

> **Code owns what ServerAlly knows. Ally owns what happens on the server.**

- **Code** holds the list of sites, the records, the monitors, the schedule, the screens.
  Deterministic, instant, free to run.
- **Ally** does the work on the machine: installing, configuring, fixing, and proving it
  worked. Nothing is hard-coded per distribution, per web server or per panel.

**Why this matters commercially.** Competitors write a template for every case, which only
works on a server they built themselves in a known state. Ally looks at the server first
and adapts, so it works on a server we have never seen — a client's inherited box, a
cPanel machine, someone else's mess. That is a capability they cannot add without
rewriting their product.

**Consequence:** most gaps below are a *runbook* — a written procedure Ally follows — plus
a screen. Very little is new server code.

---

## 4. The build plan

### Wave 1 — A blank server becomes a working server *(≈3 days)*

The panel entry point. Everything here already exists as parts; this assembles them.

1. **"Set up this server"** — one button on a fresh server. Runs our existing installers in
   order: updates → hardening → firewall → Fail2Ban → web server → PHP → database → SSL
   tooling → swap → timezone → monitoring. Around 12 steps, 8–12 minutes.
2. **Borrow their waiting-room experience.** Named steps in plain words (*"Configuring
   firewall"*, never terminal output), a **"4 of 12 · 33%"** counter, a timer on the current
   step, and the line **"It is safe to leave this page — this continues in the background."**
   Our missions genuinely survive a closed tab; we have simply never said so.
3. **"Add a website" that works on any server**, not just CyberPanel — a new Ally runbook
   covering plain nginx and Apache: create the folder, write the config, set permissions,
   create the database, issue the certificate, verify the site really loads.

**After Wave 1 a customer can go from a blank VPS to a live website without a terminal.**
That is the whole of what a competitor sells on day one.

### Wave 2 — Sites becomes the screen people open every morning *(≈2 days)*

4. **"Create website" button on the Sites page**, using the recipe form that already exists.
5. **"Add a website I already own"** — track and monitor a site anywhere, even on a server
   we do not manage. **No competitor offers this.**
6. **Automatically monitor a site the moment it is discovered or created** — today a customer
   with 77 sites would have to add 77 monitors by hand, so nobody would.
7. **Fill in the blanks** — what each site runs and where it lives. Both are empty today
   because the panel path returns the domain only.

### Wave 3 — Email, done our way *(≈2 days)*

8. **Set up mail on a server** — Ally runbook, on request.
9. **Manage mailboxes** where a panel already runs mail (CyberPanel, cPanel, Plesk).
10. **Mail health** — the part that is actually ours: check SPF, DKIM and DMARC, watch for
    blacklisting, warn before delivery starts failing, and diagnose "my email goes to spam".
    Ally's `email-deliverability` runbook already exists.

### Wave 4 — Close the operational gaps *(≈3 days)*

11. **Background workers** — keep a queue running, restart it if it dies. Real new work.
12. **PHP version per site** — Ally runbook.
13. **Copy a site for testing** (staging/clone) — Ally runbook.
14. **Database and certificate per site on plain servers** — screens over Wave 1's runbook.

### Wave 5 — Optional parity *(later, only if asked for)*

15. Site isolation (a system user per site) · Suspend a site · Command-line tool.

---

## 5. What we will deliberately not build

Recorded so it is a decision, not an oversight.

- **FTP accounts, phpMyAdmin, reseller accounts.** Control-panel territory, five free
  products do them, and they win us nothing.

> ### Email — included, but not the way a panel does it
>
> **Owner's decision (2026-07-28): email is in.** Recorded here with the trade stated, so
> the choice is deliberate.
>
> The cost is real: cPanel's own survey of 3,300 users found **email is 42% of a hosting
> provider's support time** — more than any other category. Running mailboxes means
> inheriting that. And the cost that does *not* show up in a feature list is
> **deliverability**: a customer's mail lands in spam, and the cause is DNS records, a
> blacklisted address or a neighbour on the same machine. Installing the software is a day;
> that support burden is permanent.
>
> But the omission is also real: **CloudPanel's single most-cited weakness is having no
> email at all.**
>
> **So we take the half that is genuinely ours: we do not run mail — we set it up, watch it
> and fix it.**
>
> | We build | We do not build |
> |---|---|
> | Set up a mail server on request (Ally runbook) | Our own webmail |
> | Manage mailboxes and forwarders where a panel already runs mail | Our own spam filtering |
> | **Check SPF, DKIM and DMARC are correct** | Our own mail storage to support |
> | **Watch for blacklisting, and warn before delivery fails** | |
> | **Diagnose "my email goes to spam" and fix it** | |
>
> The last three are the actual pain, no competitor in Group A does any of them, and
> **Ally already has an `email-deliverability` runbook** written for exactly this. This
> makes email a strength rather than a support liability.
- **Our own configuration templates per distribution.** That is the competitors' method and
  the reason their products only work on servers they built.
- **A mobile app.** Ploi and RunCloud have one; it is not what loses us a sale.

---

## 6. Who we sell to — two buyers, one product

An earlier draft of this plan said *"we cannot win by being easier — they are already
competent."* **That was wrong, and the owner corrected it.** Ease is not the opposite of
competence: Forge's customers are developers who could do every one of these jobs by hand,
and they pay precisely so they do not have to. Ease is the whole category's value.

The accurate version is that ease has to be measured against the right thing.

| | **Agency / developer / MSP** | **Business owner** |
|---|---|---|
| Knows the words (vhost, PHP version, queue) | Yes | **No** |
| Buys | Speed and safety | **Being able to do it at all** |
| Competitors serve them | Yes, well | **No** |

**The opening is the second column.** Ploi and RunCloud are easy *for someone who already
knows the vocabulary*. Their screens ask which PHP version, which web root, which worker
count. A shop owner with four sites and no developer cannot answer any of that — so they
are not really served by anyone today.

Ally is what makes that column reachable. The customer does not need the words; they say
what they want.

### The design rule this creates — every feature gets two doors

Each screen in this plan must work both ways:

- **A form** for the person who knows exactly what they want — fast, precise, no AI cost.
- **A sentence to Ally** for the person who does not — *"put a WordPress site on this
  server for my shop"*.

We already have this pattern working: the recipe form collects a few fields, writes a plain
sentence, and hands it to Ally. Nothing new is needed architecturally — it just has to be
applied consistently rather than once.

**And the vocabulary is part of the product.** The interface says *"website"*, not vhost;
*"background job"*, not supervisor worker; *"copy for testing"*, not staging clone. That
alone puts us somewhere no competitor is standing.

**The sentence that has to stay true, updated:**

> *Anyone can set your server up. We set it up so a non-expert can, watch it, and fix it
> when it breaks.*

---

## 7. Order and effort

| Wave | Delivers | Effort |
|---|---|---|
| **1** | Blank server → live website, no terminal | ~3 days |
| **2** | Sites becomes the daily screen | ~2 days |
| **3** | Email — set up, manage, and keep it delivering | ~2 days |
| **4** | Operational parity — workers, PHP version, staging | ~3 days |
| 5 | Optional extras | later |

**About ten working days to parity on everything that matters**, because the large parts
— deployment, firewall, backups, monitoring, DNS, cloud — were finished this week.

**Start with Wave 1.** It is the first thing every competitor's customer does, we already
own every piece, and it costs nothing to run.
