# ServerMind — Manual QA / Dogfooding Checklist

> Use the app like a brand-new, non-technical customer. For anything that doesn't
> match **Expect**, note: the item number, what you saw, what you expected. That
> list becomes the priority queue.

**Before you start**
- Make sure the app is running (the two terminals from OPS.md: backend + frontend).
- Open **http://localhost:5190** in your browser.
- Have your test server handy (the VPS you already added).
- ⚠️ Safety: stick to the **read-only / safe** playbooks suggested below on a server
  you care about. Avoid "restore", "remove/purge", and firewall-disable actions
  unless you're sure.

---

## PART A — Core journeys (do these first)

### A1. Login & Dashboard
- **Do:** Open the app. Log in if needed.
- **Expect:** You land on the **Dashboard**. It shows your server(s), a few summary
  cards (counts/health), and a recent-activity area. No blank boxes, no spinners
  stuck forever, icons visible.

### A2. Your server
- **Do:** Go to **Servers** → open your VPS.
- **Expect:** Status shows **online**; OS detected (e.g. Ubuntu); live **CPU / RAM /
  disk** numbers. Quick links to Chat, Terminal, Files, Monitoring, Security,
  Backups are visible.
- **Do:** Click **Test connection** (or re-test).
- **Expect:** Success message within a few seconds.
- **Do:** (Optional) Add a *second* server with a wrong password on purpose.
- **Expect:** A clear, friendly error — not a raw crash or a frozen dialog.

### A3. AI Chat — the headline feature
- **Do:** Open **AI Chat** for your server. Type a safe, read-only request:
  *"How much free disk space and memory do I have?"*
- **Expect:** A brief "thinking" state → a short plan in plain English → it runs and
  **streams output live** → ends with a friendly explanation. Low-risk commands may
  run automatically.
- **Do:** Ask for something that changes the system: *"Install htop."*
- **Expect:** It shows a plan and **waits for your approval** (an Approve button)
  before running. After approving, output streams and it confirms success.
- **Do:** Ask something nonsensical: *"make my server faster."*
- **Expect:** It asks a clarifying question rather than doing something random.
- **Do:** (If your language isn't English) set your language in Settings, then chat.
- **Expect:** Replies come back in your language.

### A4. Playbooks — one-click installs
- **Do:** Open **Playbooks**. Try the OS filter, category tabs, and search.
- **Expect:** A library of cards; filters and search narrow the list.
- **Do:** Run a **safe, read-only** one first — e.g. **"Large Files Report"** or
  **"Security Audit"**. Pick your server, fill any fields, Run.
- **Expect:** A console opens with **live output**, an **ETA/progress bar**, and a
  clear **success** state at the end.
- **Do:** Run a real install — e.g. **Docker**, **Node.js + PM2**, or a control panel
  (CyberPanel/CloudPanel; note these take a while).
- **Expect:** Live output the whole time (never frozen), and on success a **"service
  ready" card** with the URL / login where relevant. A real failure should say so
  clearly (not falsely report success).
- **Do:** While an install is running, watch it — then try closing and reopening the
  dialog.
- **Expect:** With durability OFF (current default) closing can lose the view — that's
  expected for now; just note if the *behavior* is confusing.

---

## PART B — Everything else

### B1. Terminal
- **Do:** Open **Terminal** for the server. Run `ls`, `whoami`, `top` (press `q` to exit).
- **Expect:** A real, responsive shell. Resizing the window reflows correctly.

### B2. File Manager
- **Do:** Browse folders, use the breadcrumb, open a text file (e.g. a config) in the editor.
- **Expect:** File list loads; you can view/edit; download works. ⚠️ Don't delete system files.

### B3. Monitoring & Alerts
- **Do:** Open **Monitoring**. Look at the CPU / RAM / disk charts; change the time window.
- **Expect:** Charts render. **Note:** history may be sparse if the backend started
  recently (data is sampled every few minutes) — that's expected, not a bug.
- **Do:** Create an alert rule (e.g. CPU above 90%).
- **Expect:** It saves and appears in the list.

### B4. Security Audit
- **Do:** Open **Security** → run a scan.
- **Expect:** A **score (0–100)** and **grade (A–F)**, findings grouped by severity
  with copy-able fix commands, and a toggle to show passing checks.

### B5. Backups
- **Do:** Create a backup job (start with a **files** backup of a small folder). Run it.
- **Expect:** A job card; running it produces a backup; history lists the run.
- ⚠️ **Restore overwrites data** — only test restore on something disposable.

### B6. Scheduler
- **Do:** Create a scheduled task using plain English: *"every night at 2am."*
- **Expect:** It shows the translated schedule (a cron preview) before saving, then saves.

### B7. Activity Log
- **Do:** Open **Logs / Activity**.
- **Expect:** A combined, newest-first feed of your AI commands and playbook runs,
  with status and timing.

### B8. Settings
- **Do:** Change your display language; change your password; edit your profile.
- **Expect:** Each change saves with confirmation; the layout is clean (multi-column,
  not one cramped column).
- **Do:** Enable **Two-Factor Authentication (2FA)**.
- **Expect:** A **QR code** to scan with an authenticator app, then a 6-digit verify
  step, then a set of **recovery codes** shown once. Log out and back in → it asks
  for the 6-digit code.

### B9. Team (optional — needs a second email)
- **Do:** Invite a teammate, set their role (viewer/operator/admin) and which servers
  they can access.
- **Expect:** An invite link/email; a **viewer** can look but **cannot run** commands.

---

## Skip for now
- **Windows servers (WinRM)** and **hosting panels (cPanel/Plesk/CyberPanel API mode)**
  unless you actually have one — these were only tested with mocks and need a live box.

## How to report back
For each problem: **item # → what you did → what you saw → what you expected.**
Screenshots help. "Small/confusing" counts — note it.
