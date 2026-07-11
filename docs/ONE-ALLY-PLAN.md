# One Ally — one chat, one workspace

> Locked 2026-07-08 after the design discussion that followed the TS4→TS3 file-move
> issue (`Issues-ss/AllyChatIssue/`). This is THE plan going forward. It absorbs the
> earlier proactivity plan ([ALLY-PROACTIVITY-PLAN.md](ALLY-PROACTIVITY-PLAN.md)) —
> Tracks A–D are already shipped; this doc carries the rest + the bigger vision.

## The vision (locked with the user)

**One Ally. One chat. The whole fleet in Ally's own memory.**

- The user never thinks "which server am I on." Which server a task runs on is decided
  by Ally, internally, from the user's words. The chat just SHOWS which server as
  information (a label / receipt), never as a mode the user picks.
- **Separate work = a separate conversation** — exactly like Claude threads. A new job
  → a new conversation. "Switch server" disappears from the product entirely.
- **Talk vs. work:** the user TALKS in the main chat (left). Ally WORKS in a
  **workspace** (right). The workspace shows the live work; its only controls are
  **Approve** and **Stop**, and any critical approval happens right there.
- The user should never have to learn how Ally works. They describe what they want;
  Ally figures out the rest and shows it clearly.

## Already shipped — Phase 0 (Tracks A–D)

Detail in [ALLY-PROACTIVITY-PLAN.md](ALLY-PROACTIVITY-PLAN.md); all tested, suite green.

- **A — Capability contract.** Ally knows missions span all servers and transfer files
  directly; never asks for SSH keys / scp; knows the user's other servers by name.
- **B — Pre-mission scout.** Read-only file recon before Ally asks/offers — finds the
  file + surveys web roots in one pass. Proven live on TestServer4.
- **C — Ask with options.** Tappable answer chips in chat + blocked missions; prompt
  rules to batch and never re-ask.
- **D — Autonomy modes.** Proactive / Normal / Careful (default Normal). Safety rails
  never change.

## The remaining build (in order)

### Phase 1 — Typography (do first)
Ally's replies render as one block of small plain text today. Fix, as the SHARED style
for both chat and workspace:
1. **Render markdown** — headings, **bold**, bullet/numbered lists, `code`, spaced
   paragraphs. Use a safe renderer (never runs raw HTML from AI output).
2. **Readable type** — comfortable body size + line spacing + gaps between sections.
3. **Ally writes structured** — prompts nudge replies into short sections (intro, bold
   headings, lists), not one run-on line.
Done first so the workspace inherits good typography for free.

### Phase 2 — One Ally brain
Merge the two brains (the "fleet" advisory brain + the "per-server" execution brain)
into ONE Ally that always has the whole fleet in memory, resolves the target server
itself, and acts on the right one (or asks with the existing server chips when truly
ambiguous). Server becomes a label, never a mode. **New conversation = the unit of
separate work** (the thread list already exists — make it primary; retire "switch
server"). Safety unchanged: no execution without a resolved target + per-command
validation per target.
- **Folds in old Track E (memory hygiene):** mission-created guardrail notes expire when
  their mission ends; a user contradiction updates the note instead of re-asking. (This
  was the real cause of the stale "don't touch TestServer3" block in the screenshots.)

### Phase 3 — Workspace UI
On the Ally page: **chat left, workspace right**, with a comfortable reading width.
- Chat = pure talk + short receipts ("Done on TestServer4 ✓").
- Workspace = the live work (steps, output, migration progress). Only **Approve** /
  **Stop**; critical approvals surface here.
- **Drawer behavior:** the drawer stays a quick way to talk to Ally from any page; when
  real work starts it shows a live "working…" pill with **Open workspace →** that takes
  the user to the full split-view Ally page.
- Backend is ~90% ready (missions already run detached, stream steps, have approve/stop,
  survive reload). This phase mostly MOVES the work out of chat bubbles into the pane.

### Phase 4 — Live end-to-end verify
Re-run the exact TS4→TS3 file move + a full migration, now in the workspace, counting
user turns. Target: ~3 taps instead of ~14 typed replies. Confirm fewer questions, clear
scope, readable replies.

## Dropped / changed from the old plan
- **Old Track F (File Manager as page context) — DROPPED.** The scout (Track B) already
  reads the files server-side, no matter what page the user is on — it does F's job
  better. No reason to build F.
- **Old "Track G – scope tags" — DROPPED.** A fleet/scope tag looked like a mode; the
  user correctly rejected it. Scope is shown as a plain label, folded into Phases 2–3.

## Acceptance
Suite stays green each phase; each phase verified live in the browser; CLAUDE.md
decisions log updated per phase.
