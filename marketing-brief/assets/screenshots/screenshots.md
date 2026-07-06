# Screenshots — real product screens (capture guide)

> **Honest note on files:** these screens are all **built and live** — I viewed each one in the
> running app while writing this brief. The actual PNG binaries are **not committed here** because
> the build environment couldn't reliably export them to disk. Every screen below can be captured
> from the running app in seconds: start the frontend (`localhost:5190`), log in, and open the
> route listed. Descriptions are exact (real content, real layout) so the design tool can either
> use a fresh capture or recreate the screen faithfully. **Do not treat these as mockups — they
> are descriptions of shipped UI.** Nothing here is "not yet built."

The UI is a clean **light theme**: white canvas, soft slate borders, indigo→violet accents, a
left sidebar (ServerAlly logo top-left; nav: Dashboard · Ally · Assets · Playbooks · My Scripts ·
Terminal · Missions · Logs · Team · Settings; "Upgrade to Pro" pinned bottom), and a top bar with
an "Ask Ally" button + the user's avatar menu. A dark theme also exists.

---

### 1. `dashboard-fleet-report` — **HERO shot** · route `/dashboard`
The single best screenshot for the landing page — it shows the "it watches your servers for you"
value instantly. Content: heading **"Welcome back, {name}"** / "Here's how your fleet is doing
today." Four stat cards: **Total servers 5 · Online 4 (80% of fleet) · Needs attention 1 ·
Playbooks 50 ready to run**. Below, a panel titled **"Ally's fleet report — 1 needs attention"**
with per-server cards, each showing a **letter grade + score** (e.g. `F · 33/100`, `B · 78/100`)
and ranked plain-English findings, each with a **one-click action button** on the right:
- "This server may be compromised" → **Review & respond**
- "Security needs attention — Last security scan graded this D (46/100)…" → **See the fixes**
- "No backups configured — one bad day could lose it." → **Set up backups**

*Illustrates:* Proactive Fleet Intelligence (feature #4).

### 2. `ally-chat` — **HERO shot** · route `/assistant`
The product's soul: plain-English server management. Left column = saved conversation threads.
Main = the chat. A **user bubble** (indigo, right-aligned) — *"On TestServer1, what is the current
disk usage? Just check, do not change anything."* — carries a small green **TestServer1** chip.
**Ally's reply** (left, sparkle avatar, also TestServer1-chipped) reads in plain language:
*"Great! Your disk space check completed successfully. TestServer1 is in good shape — your main
drive has used about 15% of its 35GB capacity, leaving you plenty of room. Everything looks
normal, so no action needed right now."* Below it, suggestion chips ("Want me to check memory and
CPU too?"). The composer shows a **"Focused on TestServer1"** pill and placeholder *"Message Ally
about TestServer1…"*.

*Illustrates:* Ally the AI companion (the hero feature) — natural language, real result, plain
explanation, per-server attribution.

### 3. `assets-list` · route `/servers` (labeled "Assets")
Heading **"Assets"** + an **"Add Asset"** button. A responsive grid of asset cards. Each card: a
rounded category-icon avatar, the name (TestServer1…), `host:port`, a colored status dot +
**Online/Offline**, and small badges — OS (`ubuntu 22.04 · x86_64`), category (**VPS**, **Hosting
Panel**), and panel type (**Cyberpanel**). Shows the "any kind of server, one place" story.

*Illustrates:* Assets & categories (feature #2).

### 4. `add-asset-categories` · route `/servers` → **Add Asset**
A modal titled **"Add Asset"** opening with **"What are you adding?"** and five tiles, each with an
icon: **Bare Metal · VPS · Hosting Panel · Windows Server · Cloud Account**. Picking a tile reveals
a tailored form (Display Name, Auth Type, Host/IP, Port, Username, Password, Notes). Shows the
"category-first, not protocol-first" onboarding — friendly for non-technical users.

### 5. `cloud-connect` · route `/servers` → Add Asset → **Cloud Account**
Modal **"Connect a cloud account"** with a cloud icon. A **provider picker** with five buttons:
**Amazon Web Services (EC2) · DigitalOcean · Hetzner Cloud · Google Cloud · Microsoft Azure**.
Below, an "Account name" field + provider-specific credential fields, and a **shield-icon nudge
box**: *"Use a read-only IAM key… We store it encrypted (AES-256-GCM)…"*. Primary button:
**Connect & discover**. Great for the "bring your whole cloud" section.

*Illustrates:* Cloud account import (feature #6).

### 6. `missions` · route `/missions`
Mission history: a list of jobs Ally has run, each with a status chip — **running · Verified
(green) · interrupted** — the home server, step count, and an expandable transcript of every step.
Running missions show **View**; interrupted ones show **Resume**. Shows "Ally does the whole job,
durably, and proves it."

*Illustrates:* Missions + the verification gate (feature #1, #3).

### 7. `security-audit` · route `/servers/{id}/security`
A server's security tab: a big **score ring + A–F grade**, severity count chips, grouped findings
each with a **copyable fix command**, a "Threat scan" panel (verdict banner: clean / suspicious /
compromised + plain-English evidence + a "Respond with Ally" button), and scan history. Great for
the "safe & watched" section.

*Illustrates:* Security audit + threat monitoring (feature #3, #4).

---

## Suggested use on the landing page
- **Hero visual:** `ally-chat` (the plain-English magic) or a clean composite of the chat + a
  fleet-report card.
- **"It watches for you" section:** `dashboard-fleet-report`.
- **"Any server" section:** `assets-list` + `cloud-connect`.
- **"Does the whole job / safe" section:** `missions` + `security-audit`.
