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

### Wave 3 — Close the operational gaps *(≈3 days)*

8. **Background workers** — keep a queue running, restart it if it dies. Real new work.
9. **PHP version per site** — Ally runbook.
10. **Copy a site for testing** (staging/clone) — Ally runbook.
11. **Database and certificate per site on plain servers** — screens over Wave 1's runbook.

### Wave 4 — Optional parity *(later, only if asked for)*

12. Site isolation (a system user per site) · Suspend a site · Command-line tool.

---

## 5. What we will deliberately not build

Recorded so it is a decision, not an oversight.

- **Email hosting, FTP accounts, phpMyAdmin, reseller accounts.** These are control-panel
  territory, five free products do them, and email alone is reported as **42% of a hosting
  provider's support time.** We would inherit that cost and win nothing.
- **Our own configuration templates per distribution.** That is the competitors' method and
  the reason their products only work on servers they built.
- **A mobile app.** Ploi and RunCloud have one; it is not what loses us a sale.

---

## 6. What this changes about who we sell to

Worth stating plainly, because it follows from the decision:

**The person who pays us is now the same person who pays Ploi** — an agency, developer or
MSP with several servers, who is semi-technical. Not a beginner. They *could* do this
themselves; they pay to not spend the afternoon.

So we cannot win by being easier — they are already competent. We win on:

- **Speed** — one sentence instead of thirty minutes of clicking.
- **Safety** — it notices when a site breaks, and it can clean up a hack.

The free tier stays valuable as a way in, not as the business.

**The sentence that has to stay true:**

> *Anyone can set your server up. We set it up, watch it, and fix it when it breaks.*

If we finish this plan and that sentence stops being true, we have built a slower version
of something free.

---

## 7. Order and effort

| Wave | Delivers | Effort |
|---|---|---|
| **1** | Blank server → live website, no terminal | ~3 days |
| **2** | Sites becomes the daily screen | ~2 days |
| **3** | Operational parity | ~3 days |
| 4 | Optional extras | later |

**About eight working days to parity on everything that matters**, because the large parts
— deployment, firewall, backups, monitoring, DNS, cloud — were finished this week.

**Start with Wave 1.** It is the first thing every competitor's customer does, we already
own every piece, and it costs nothing to run.
