# 01 — Features (ranked, with LIVE / ROADMAP status)

Status key: **LIVE** = built and working (most proven on real Linux servers + a live CyberPanel).
**PARTIAL** = built, but only validated with mocks / not yet proven end-to-end on live infra.
**ROADMAP** = designed/foundation shipped, not yet finished. *Do not present PARTIAL/ROADMAP as
finished.*

---

## 🥇 THE HERO (launch priority #1)

### Ally — your AI companion for any server  — **LIVE**
*Describe what you want in plain English; Ally plans it, runs it safely, and explains it.*

This is the whole product in one sentence and the thing the landing page should lead with. You
chat with Ally the way you'd message a sysadmin friend ("install WordPress," "why is my site
slow," "set up a firewall"). Ally reads your server's real state, proposes a plan, runs each
step with your approval, streams the live output, and tells you in plain language what happened.
It answers in **8 languages**. Everything else below is in service of this.

---

## Supporting features (priority order)

### 1. Missions — Ally does multi-step jobs on its own  — **LIVE**
*Approve once; Ally works step-by-step until the job is done — and proves it.*
For bigger jobs ("host this WordPress site," "clean up this hacked server"), Ally runs an
agentic loop: plan a step → run it → look at the result → decide the next step. It has a
**verification gate** (an independent check that the goal is actually met — it won't claim
"done" without proof), pauses for approval on risky steps, and missions are **durable** — they
survive a dropped connection or a page refresh and can be resumed or watched live.

### 2. Any server, any OS — one place  — **mixed**
*Linux, Windows, hosting panels, and cloud accounts — all managed from one companion.*
- **Linux (SSH)** — **LIVE**, proven on real Ubuntu/Debian/AlmaLinux servers.
- **Hosting panels** — **CyberPanel is LIVE** (create sites, databases, SSL via the panel).
  **cPanel / Plesk / DirectAdmin** adapters are built but **PARTIAL** (validated against the
  documented APIs; cPanel reaches a real panel, full validation pending a license).
- **Windows Server (WinRM)** — **PARTIAL** (built; live validation in progress).
- **Cloud accounts** — see #6.

### 3. Safe by design  — **LIVE**
*Ally asks before anything risky, checks its own work, and can't be tricked by a hacked server.*
Every command is checked against a safety layer (dangerous commands are blocked; risky ones
need explicit approval). Missions verify their result with read-only checks before finishing.
Ally treats everything it reads on a server as **data, not instructions** — so a compromised box
that hides "run this malware" in a log file can't trick it (validated with live red-team +
prompt-injection tests). Credentials are **AES-256-GCM encrypted** and never shown back.

### 4. Proactive intelligence — it tells you before you ask  — **LIVE**
*A fleet health report, threat monitoring, and an email digest that flag what needs attention.*
- **Fleet Intelligence** — a health score (0–100) + ranked, plain-English findings per server,
  each with a one-click fix. Zero AI cost (reads data you already have).
- **Threat monitoring** — scheduled read-only scans for signs of compromise (webshells, miners,
  rogue cron, backdoor accounts); alerts you the moment a server newly worsens. Detection-only
  by design — cleanup is always a human-approved mission.
- **Guided incident response** — when something's found, Ally runs a careful, evidence-preserving
  cleanup mission (quarantine, don't delete; never reboot; honest hand-over).
- **Fleet-health email digest** — a weekly/daily email of what needs attention.

### 5. Recipes & one-click jobs  — **LIVE**
*Common jobs as guided, repeatable recipes — plus a library of scripts and an AI script generator.*
- **Recipes** — packaged expert procedures (host a WordPress site, migrate a site, harden a
  server, set up backups, SSL) Ally runs as a mission.
- **Playbooks** — a script library (LAMP/LEMP, Docker, WordPress, security hardening, backups,
  monitoring, control-panel installers) with live output and a post-run access card.
- **AI Script Generator** — describe a task, get a production-ready bash/PowerShell script.

### 6. Cloud account import — bring your whole cloud  — **PARTIAL**
*Connect AWS, DigitalOcean, Hetzner, Google Cloud, or Azure and import your instances as assets.*
Connect a provider with a read-only key, discover your instances, and import the ones you pick.
**All 5 providers are built; the credential/error paths are live-verified.** The discover→import
happy-path is mock-tested and needs one real account per provider to fully prove — so present
cloud import as **available** but note it's newest.

### 7. Automation  — **LIVE**
*Schedules, backups, monitoring, and alerts — set once, runs itself.*
- **Scheduler** — natural language → cron ("every night at 2am"), with a live preview.
- **Backups** — files / MySQL / PostgreSQL, scheduled, with retention + one-click restore.
- **Monitoring & alerts** — CPU/RAM/disk history, threshold alerts by email/webhook/Slack.

### 8. Team management  — **LIVE**
*Invite people, give per-server access, and control who can run what.*
Roles (owner / admin / operator / viewer) with per-server access. A viewer can **never** execute
— enforced on every action path.

### 9. Supporting tools  — **LIVE**
Full browser **terminal** (xterm.js), **file manager** (browse/edit/upload), **security audit**
(A–F grade + fix commands), and a unified **activity log** of everything Ally has done.

### 10. Remote Desktop for Windows  — **ROADMAP**
*Open a Windows desktop in the browser when a job needs a real screen.*
The secure foundation is shipped (opt-in per asset, access-checked, credential-free session).
The live pixel-streaming viewer (Apache Guacamole) is **not yet finished** — mark as "coming soon."

---

## Pricing model (for context, not necessarily on the launch page)
Two simple plans, **every feature on every plan** — they differ only in two numbers:
- **Free** — 2 servers, ~30 AI actions/month.
- **Pro** — 15 servers, 1,000 AI actions/month.
(Enforcement exists behind a flag; billing integration is built for FireVPS/WHMCS. Treat exact
prices as **ROADMAP/ TBD** — confirm before publishing numbers.)
