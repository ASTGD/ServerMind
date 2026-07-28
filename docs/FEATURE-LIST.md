# ServerAlly — Feature List

**Prepared 2026-07-27, updated 2026-07-28 · For executive review**

> This document lists everything ServerAlly can do today, in plain language, and shows which
> plan each feature belongs to. It is written from the product's actual configuration, not
> from a roadmap — every feature listed here is built and running.

---

## 1. What ServerAlly is

**A control panel sets a server up. ServerAlly keeps it running, and fixes it when it breaks.**

Our customers own servers and websites but do not have a system administrator. ServerAlly gives
them one: an AI assistant called **Ally** that watches their servers, notices problems, and
does the work to fix them — in plain English, in any of eight languages.

**Category:** server operations and incident response.
**Short version for a customer:** *the sysadmin you do not have.*

We are not a control panel and do not compete with one. A control panel manages one server;
ServerAlly manages all of them, across any provider, any operating system, and any panel.

---

## 2. The plans at a glance

| | **Free** | **Pro** | **Pro+** |
|---|---|---|---|
| **Price per month** | $0 | $9 | $19 |
| Servers | 2 | 10 | 50 |
| Ally requests per month | 20 | 50 | 100 |
| Your own runbooks | — | 5 | Unlimited |
| Public status pages | 1 | 3 | Unlimited |
| Team logins | — | 2 | 10 |
| Performance history kept | 7 days | 1 year | 1 year |
| Uptime history kept | 30 days | 1 year | 1 year |
| **All safety features** | ✅ | ✅ | ✅ |

**Who each plan is for**

- **Free** — someone with one or two servers who wants to try it. A real product, not a demo.
- **Pro** — a developer or small business running a handful of servers.
- **Pro+** — an agency or hosting provider managing servers on behalf of clients.

---

## 3. Our promise: safety is never behind a paywall

This is a deliberate commercial decision and a competitive weapon, so it is worth stating
clearly to executives.

**Every safety feature is included on every plan, including Free.** Backups, security scans,
malware detection, hack cleanup, uptime alerts, certificate warnings — a Free user gets all of
them. A Free user also gets the *same* Ally: the same AI model, the same expert procedures, the
same safety checks. Never a weaker version.

**Why:** our nearest competitors hide backups behind their paid tiers, and it is their loudest
customer complaint. A mechanic who withholds the brake check until you upgrade is not a
mechanic. We charge for **scale and audience** — how many servers, how much AI, how many
clients — never for capability and never for safety.

---

## 4. Feature list

Plan labels used below:

- **All plans** — included on Free, Pro and Pro+
- **Pro** — included on Pro and Pro+
- **Pro+** — top tier only

---

### A. Ally — the AI assistant

The core of the product. The customer types what they want in plain English and Ally does it.

| Feature | Plan | What it does |
|---|---|---|
| **Ally chat** | All plans | Ask a question or give an instruction in plain English. Ally looks at the real server, decides what to do, and does it. It runs safe checks itself instead of telling the customer to run commands. |
| **Missions** | All plans | For bigger jobs that cannot be planned in advance — "host a WordPress site", "clean up this hack". Ally works step by step, adapting as it learns, and asks permission before anything risky. |
| **Proof of work (verification gate)** | All plans | Ally is never trusted when it says "done". A second, independent check gathers fresh evidence that the job really worked. If it cannot prove success, it says so honestly instead of claiming a false win. No competitor does this. |
| **16 expert procedures** | All plans | Built-in specialist knowledge for high-stakes jobs — hacked site cleanup, WordPress rescue, slow server diagnosis, SSL problems, email delivery, and more. Ally follows the expert's method rather than improvising. |
| **Safety rules** | All plans | A hard list of catastrophic commands that can never run, plus a confirmation step before anything destructive. These cannot be switched off by any setting or by any AI decision. |
| **Attack resistance** | All plans | A hacked server can hide fake instructions in its own files and logs to trick an AI. Ally treats everything it reads from a server as information, never as orders. This has been tested against real attacks on a live compromised server. |
| **Memory** | All plans | Ally remembers facts about each server and what work it has already done, so it does not repeat questions or undo its own fixes. |
| **Eight languages** | All plans | Ally replies in the customer's own language: English, Bengali, Arabic, Spanish, French, Hindi, Portuguese, Turkish. |
| **Smart model routing** | All plans | Simple jobs use a fast, cheap AI model; hard or high-risk jobs automatically use our most capable one. Quality where it matters, cost control everywhere else. |
| **Ally on a schedule (Autopilot)** | **Pro** | Give Ally a standing job — "check the servers every night" — with a limit you choose: *only tell me*, *fix ordinary problems*, or *fix anything allowed*. It works while nobody is watching. |
| **Your own runbooks** | **Pro** | Teach Ally your company's own procedures, in your own words. Ally then follows your method instead of its general knowledge. Pro: 5. Pro+: unlimited. |

---

### B. Knowing something is wrong

| Feature | Plan | What it does |
|---|---|---|
| **Uptime monitoring** | All plans | Checks whether a website actually loads, from outside the server — where a real visitor is. A check from the server itself would pass even when the site is unreachable. |
| **Real content checking** | All plans | A website can return "OK" while showing a blank page or an error. We check that the page really contains the site, not just that the server answered. |
| **Service monitoring** | All plans | Watches the services that keep a server working — web server, database, cache, mail, queue workers — and tells the customer when one stops. Previously a database could die on a quiet server and nothing was said, because alerts only worked on processor, memory and disk. |
| **Finds the services for you** | All plans | The customer does not need to know their database is called `mariadb`. We look at the server, list what is actually installed in plain names, and they tick the ones to watch. |
| **Automatic restart** | All plans | Off by default. Switched on per service, Ally restarts it when it stops and confirms it really came back. **With a hard limit:** a service that crashes on startup would otherwise be restarted forever — hammering the server and hiding the real fault behind something that looks like it keeps recovering. After a few tries ServerAlly stops and says a person is needed. |
| **Certificate expiry warnings** | All plans | An expired HTTPS certificate takes a site down completely, and always gives weeks of warning. We warn at 14 days and again at 3 days. |
| **Performance monitoring** | All plans | Continuous tracking of processor, memory and disk use, with charts and history. |
| **Custom alerts** | All plans | Email or webhook alerts when any measurement crosses a limit the customer sets. |
| **On-call escalation** | All plans | If the first person does not respond within a set time, alert the next person, then the next, until someone confirms. Nobody has to sit watching a screen. Free and Pro accounts escalate by email. |
| **Text and Telegram alerts** | **Pro** | Reach a person by SMS or Telegram instead of email, for problems that cannot wait for someone to check their inbox. |
| **Server log viewer** | All plans | Finds and reads the server's own logs — web server, database, system — and highlights the lines that look like problems. The customer does not need to know where logs live. |
| **Fleet health report** | All plans | One page giving every server a score out of 100 and a plain-English list of what needs attention, ordered by importance, with a one-click fix. |
| **Email digest** | All plans | A daily or weekly email summary of what needs attention. The customer chooses the frequency or turns it off. |

---

### C. Security and recovery from attacks

This group is our strongest differentiator. Competitors stop at a firewall.

| Feature | Plan | What it does |
|---|---|---|
| **Security audit** | All plans | A read-only inspection scoring the server 0–100 with a letter grade, and a list of exactly what to fix and how. |
| **Malware and intrusion detection** | All plans | Automatically scans every server twice a day for hacked files, hidden mining software, backdoor accounts and unauthorised scheduled jobs. Alerts only when a server newly gets worse — never repeated nagging. |
| **Guided hack cleanup** | All plans | When a server is compromised, Ally follows a careful procedure: confirm the problem, preserve evidence, contain, clean, then harden. It moves suspect files rather than deleting them, so a mistake can be undone. |
| **Detection, not silent auto-fix** | All plans | We deliberately do **not** clean a hack automatically. That would destroy evidence and a false alarm would break a healthy site. We detect and hand the decision to a person. |
| **Incident report** | All plans | After an incident, Ally writes the plain-language story of what happened — how they got in, a timeline, what was done, and what is still left for the customer. Downloadable as PDF. |
| **Whole-server report** | All plans | One report covering every job done on a server, suitable for sending to management. |
| **Two-factor login** | All plans | Standard app-based two-factor authentication on customer accounts. |
| **Encrypted credentials** | All plans | Every server password and key is encrypted with bank-grade encryption. They are never shown in the interface, never written to a log, and never sent to the AI. |

---

### D. Backups

| Feature | Plan | What it does |
|---|---|---|
| **Scheduled backups** | All plans | Automatic backups of files, MySQL and PostgreSQL databases, on a schedule the customer describes in plain English ("every night at 2am"). |
| **Offsite backups** | All plans | Sends each backup off the server it protects, to Amazon S3, Cloudflare R2, Backblaze, DigitalOcean, Wasabi or similar. A backup stored on the same server is not really a backup. |
| **Credentials never touch the server** | All plans | The managed server never receives the storage account password. It gets a temporary one-hour link for one file only. If the server is hacked, the attacker cannot read or delete the backup history. |
| **Restore** | All plans | Restore from any backup, including fetching it back from offsite storage if the local copy is gone. |
| **Automatic cleanup** | All plans | Old backups are removed automatically, on the server and in offsite storage, so storage does not grow forever. |

---

### E. Servers and websites

| Feature | Plan | What it does |
|---|---|---|
| **Any server, one place** | All plans | Linux, Windows, and shared hosting panels side by side. No competitor manages across providers — they are each locked to one host. |
| **Sites view** | All plans | Every website across every server, searchable by domain name. When a client calls about their site, nobody needs to remember which server it is on. Shows whether it is up, its certificate status, and what it runs. |
| **Create and delete servers** | All plans | Build a new server in a connected DigitalOcean or Hetzner account without leaving ServerAlly — choose the size, see the monthly price before pressing the button — then start, restart, shut down, resize or delete it. |
| **Protection against costly mistakes** | All plans | Creating and deleting are the only actions that spend money or erase a disk. Deleting requires typing the server's exact name, checked against the provider at that instant so a stale page cannot delete anything; a repeated create is refused rather than billed twice; and a resize that permanently enlarges the disk is clearly marked as one that can never be undone. |
| **Cloud account import** | All plans | Connect an Amazon, DigitalOcean, Hetzner, Google Cloud or Azure account and import the servers automatically instead of adding them one by one. |
| **50 one-click installers** | All plans | Ready-made scripts for WordPress, Docker, LAMP/LEMP, Node.js, Nextcloud, monitoring tools, security hardening, control panels and more. |
| **AI script writer** | All plans | Describe what a script should do and Ally writes it, ready to review, save and reuse. |
| **File manager** | All plans | Browse and edit files on the server in the browser, with a proper code editor. Passwords and keys inside files are hidden before anything is sent to the AI. |
| **Terminal** | All plans | A full command-line session in the browser for customers who want direct control. |
| **Remote desktop** | All plans | View and control a Windows desktop in the browser, with no software to install. |
| **Scheduled tasks** | All plans | Run any command, script or installer on a repeating schedule, described in plain English. |
| **Hosting panel support** | All plans | Manage websites, databases and SSL certificates on CyberPanel, cPanel, Plesk and DirectAdmin. |

---

### F. For agencies and resellers

| Feature | Plan | What it does |
|---|---|---|
| **Public status pages** | All plans (count limited) | A public web page an agency gives its clients so they can check for themselves whether a site is up, instead of phoning. Free: 1 page. Pro: 3. Pro+: unlimited. |
| **Client reports** | **Pro+** | A monthly report for each client: was my site up, is it safe, what did you do for me. Generated from real records, with no AI involved, so it is reproducible, free to produce and cannot invent anything. |
| **Your own branding** | **Pro+** | Put the agency's company name, logo and colour on everything their client sees, and remove ours completely. |
| **Team logins** | **Pro** | Invite colleagues with three permission levels: view only, can run things, or full admin. Access can be granted server by server. Pro: 2 people. Pro+: 10. |

---

### G. For developers and integrations

| Feature | Plan | What it does |
|---|---|---|
| **Firewall manager** | All plans | See what is open on a server in plain words — "Secure web traffic", "Database" — and open or close ports without typing commands. Works with both firewall systems in common use. |
| **Lockout protection** | All plans | The dangerous part of any firewall change is cutting your own connection: the command works, and the server is gone for good. ServerAlly knows how it reaches each server and **refuses** any change that would close that door — it does not just warn. |
| **SSH key manager** | All plans | Shows exactly who can sign in to a server, with a name for each key, and lets the customer add or remove people. The key ServerAlly itself uses is marked and cannot be removed by accident. |
| **Deployments** | All plans | Ships a repository to a server. Each deploy is built in a folder of its own and only goes live once it has finished, so a broken build leaves the site running exactly as it was. One click goes back to the previous version. |
| **Deploy on push** | All plans | Pushing to the chosen branch deploys automatically. The webhook is signed, so knowing the address is not enough to trigger a deploy. |
| **Staging** | All plans | The same repository can be deployed twice — a staging copy from one branch and the live site from another — so changes are tried somewhere safe first. |
| **API keys** | **Pro** | A documented interface so customers can connect ServerAlly to their own tools and scripts. |
| **Webhooks** | **Pro** | ServerAlly notifies the customer's own systems when something happens, with signed and verified messages, automatic retries, and protection against being tricked into calling internal addresses. |
| **Connect your own AI (MCP)** | **Pro** | A customer can connect their existing Claude or ChatGPT subscription and manage their whole fleet by chatting there. 22 available operations. **This costs us nothing in AI charges** — their subscription pays for the thinking. |

---

### H. Platform support

| | Status |
|---|---|
| Ubuntu, Debian, CentOS, AlmaLinux, Rocky, Fedora | Fully proven on live servers |
| Windows Server (remote management) | Built and tested in simulation; awaiting one live Windows server to confirm |
| Windows (remote desktop) | The full pipeline is proven; awaiting one live Windows desktop to confirm |
| CyberPanel | Fully proven on live servers |
| cPanel / WHM, Plesk, DirectAdmin | Built and tested against the published specifications; awaiting a licensed panel to confirm |
| Amazon, DigitalOcean, Hetzner, Google Cloud, Azure | Import: connection proven, final step awaiting one API key per provider |
| Creating/deleting servers — DigitalOcean and Hetzner | Built and proven against a stand-in provider; awaiting one API key to confirm against the real one |

---

## 5. What sets us apart

Four things no competitor in our market offers today:

1. **Every server in one place** — any provider, any operating system, any control panel.
   Competitors are each locked to a single host.
2. **It does the work and proves it worked.** Ally acts, then independently verifies its own
   result and refuses to claim success it cannot demonstrate.
3. **It notices a hack and helps clean it up.** The rest of the market stops at a firewall.
4. **Safety is free.** Backups, scans, malware detection and incident response on every plan.

---

## 6. Status notes — for internal use, not for customers

Included so nobody is surprised. These are known and tracked, not gaps we have missed.

- **Plan limits are built but not yet switched on.** Every account currently has unlimited
  servers and AI. This is deliberate — we will not enforce limits until the payment path has
  been tested end to end.
- **The payment connection has never been run.** The billing module for WHMCS is fully written
  and our side is fully tested, but the module itself has never executed against a real WHMCS
  system. This is the single largest untested piece and should be proven before launch.
- **Prices are approved but not final in public.** Our measured AI cost is about double the
  figure the $9 and $19 prices were based on. That measurement comes from our own heavy
  development use, not from customers, so it is a warning rather than a verdict. We should
  confirm it with a small group of real users before publishing prices.
- **The marketing site is live but has no prices on it.** Five pages are published at
  serverally.firevps.net. The pricing page cannot be finished until the point above is
  settled.
- **Items awaiting live confirmation** are listed in the platform table above. In each case
  the feature is built and tested — what is missing is one live system to confirm it against.

---

*Source: this document is generated from the product's own configuration
(`backend/app/services/entitlements.py` defines every plan boundary listed here) and from the
live production system. Plan tiers approved 2026-07-26 — see
[PRICING-TIERS-AND-GATES.md](PRICING-TIERS-AND-GATES.md). Positioning — see
[POSITIONING-CATEGORY.md](POSITIONING-CATEGORY.md).*
