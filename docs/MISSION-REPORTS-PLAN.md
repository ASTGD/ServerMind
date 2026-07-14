# Mission Reports — plan

> Export/download a professional report when Ally finishes a mission, and a dedicated
> **Reports** area to browse every report card. Started 2026-07-14.

## Why

Agencies/MSPs (our target user) run Ally missions on client servers — clean a hacked site,
respond to an incident, install a stack, host a site. After the work, they need a
**professional, shareable report** to (1) send the client, (2) keep for records/audit, and
(3) show their team. Today the outcome lives only as the in-workspace result card; there's
no way to browse or export it.

## The core decision — three areas, ONE data source (no new store)

The user wants a clean separation (their words: *"Missions only show the Mission. Log and
Reports will be a separate area."*). We honor that at the **presentation** layer, but the
data stays single-sourced — **every mission already IS a report.** The `missions` table
already stores `goal`, `server_name`, `status`, `verified`, `summary`, the structured
`result` (`{subject, headline, found[], did[], left[]}`, migration 032), and the full step
`steps` transcript. `command_logs` + `/api/activity` hold the raw command history.

**So we do NOT create a "Task Report" table.** We add three *views* of the same data, split
by level of detail:

| Area | Shows | Reads | Purpose |
|---|---|---|---|
| **Missions** (slim the existing page) | Only the mission — goal, site/server, status (running/verified/blocked/failed), resume/stop. **No transcript, no report clutter.** | `missions` (high-level fields) | Operational — what's running / what I ran |
| **Reports** (NEW area) | The **report cards** (Found / Ally did / Left + verdict) + **Export ▾** + a full print view | `missions.result` (finished ones) | Polished, shareable, client-facing, audit |
| **Log** (separate area) | The raw detail — every command/step + output, secret-redacted | `command_logs` + mission `steps` + `/api/activity` | Forensic "what exactly ran" |

Benefit: clean separation **without** duplicating data or risking drift. Reports = missions
that have a `result`. Log = the detailed step/command feed. Missions = the high-level list.

### Separate but cross-linked (so nothing is a dead end)

- A **Mission** card links to **"View report"** (Reports) and **"View log"** (Log).
- A **Report** links to **"View full log"** and back to its mission.

## Data / backend — already 90% there

- `GET /api/missions` → list with each mission's `result` (feeds the Reports list — filter
  to `result != null`).
- `GET /api/missions/{id}` → `to_dict(..., include_steps=True)` = `result` + full `steps`
  (feeds the report view + the redacted appendix).
- **P1 needs NO backend change** — the data is already exposed. (P2 may add a slim
  `GET /api/reports` projection + a server-side-redacted `/report` payload for hardening.)

## Report content (what's in a report)

- **Header** — title, **site + server**, date/duration, **status badge**
  (Verified / Needs-you / Stopped / Failed), *"Prepared by {user/agency} via ServerAlly"*
  (white-label hook — matches the agency backlog).
- **Summary** — the result: **Found / Ally did / Left for you** + the plain headline.
- **Verification** — what the gate proved (fresh evidence) → client trust.
- **Technical appendix** (collapsible / page 2) — the step timeline + key outputs,
  **secret-redacted**.
- **Footer** — generated timestamp + mission id (audit trail).

## Export formats

- **PDF (headline)** — P1: **print-optimized report route + browser print-to-PDF**
  (`window.print()` + a dedicated print stylesheet). Zero new infra, WYSIWYG.
  ⚠️ The report view uses a **light / print theme** (the dark result card wastes ink on
  paper). P3: server-side PDF only if scheduled/emailed reports need it.
- **Markdown** — for tickets/email/Slack (build client-side from `result`).
- **JSON** — records/audit/programmatic (the `result` is already JSON).
- **Copy** — MD to clipboard.

## Non-negotiables (safety)

1. **Secret redaction** on anything in Reports/Log — command outputs can carry passwords,
   keys, `.env`/DB creds. Reuse `frontend/src/lib/redactSecrets.ts` on the appendix before
   display **and** export. (P2/P3: also redact server-side so the API never emits a secret.)
2. **Access control** — reports are user/team-scoped (the missions endpoints already scope
   to the signed-in user; keep it). Public share links = **P3** (tokenized, expiring,
   redacted — they name a site + its vulnerabilities).

## Phasing

### P1 — Reports area (build now; non-breaking, frontend-only)
1. `api/reports.ts` — `listReports()` (GET /api/missions, keep `result != null`),
   `getReport(id)` (GET /api/missions/{id}).
2. `routes/Reports.tsx` — report-card list + filters (server / status / search), each row →
   the report view. New `/reports` route + **Reports** sidebar item.
3. `routes/ReportView.tsx` (`/reports/:id`) — print-optimized/light report + collapsible
   **redacted** appendix + **Export ▾** (PDF via print, Markdown, JSON, Copy).
4. Build clean + live-verify against this session's real missions.

### P2 — Log area + slim Missions (done together, so the transcript is never orphaned)
- Promote/repurpose the existing `Logs` page into the **Log** area: mission `steps` +
  `command_logs` + `/api/activity`, **redacted**, with a sidebar item.
- **Then** slim `routes/Missions.tsx` — remove the inline transcript (it now lives in Log);
  keep mission cards only. Add the cross-links (View report / View log).

### P3 — advanced
- Tokenized **public share link** (send a client a report without login) — expiring +
  redacted.
- **Server-side PDF** + **emailed/scheduled reports** (reuse `digest_service` /
  `notification_service` plumbing).
- **White-label** agency branding (logo + name on the report).
- Bulk export.

## Open decisions
- **Scope of "report-worthy":** show reports for any mission with a `result` (verified,
  needs-you, stopped, failed) — running missions aren't reports yet. ✅ (default)
- **Chat-plan cleanups** (richhome quarantine, containment) were chat plans, not missions —
  they have no `missions` row/`result`, so they won't appear in mission reports. A unified
  **"session/activity report"** spanning `missions` + `command_logs` is a future item; P1
  stays mission-reports-only.
