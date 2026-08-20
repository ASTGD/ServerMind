# Blueprints — ready-made long jobs, started over MCP

**Status:** plan only. Nothing built. Written 2026-08-21.

A **Blueprint** is a long job we ship ready-made: a fixed list of steps that ServerAlly
already knows how to do. A customer says what they want in their own words, their AI picks
the matching blueprint and supplies the inputs, and ServerAlly runs the steps and shows
them filling in — in words the owner can read.

> **The name.** Not "mission" — that already means our own AI loop (a table, a page,
> resume, the verification gate), and two things with one name is the drift this project
> keeps getting caught by. `blueprint` appears in **zero** files today; `recipe`, `runbook`,
> `playbook`, `job` and `task` all already mean something here.

---

## 1. The one decision everything else follows from

**A blueprint step contains no AI.**

Every step is something ServerAlly already does deterministically: run a playbook, create a
site, create a database, turn on HTTPS, add a monitor, set up a backup, run a scan. None of
it needs a model.

That gives us four things at once:

| Property | Because |
|---|---|
| Our AI cost is **zero** | No model call anywhere in the run — the point of Platform + MCP |
| It is **repeatable** | The same inputs do the same thing, every time |
| It can be **resumed** | A fixed step list has a position; a conversation does not |
| The screen is **truthful** | We show what ran, not what a model said it would do |

The customer's AI is the **front desk**, not the engine: it understands the request,
matches a blueprint, collects the missing inputs, starts it, watches, explains, and decides
what to do if it stops. That is real work, and their AI subscription pays for it.

**The AI may not invent steps.** The blueprint is ours and fixed. If the AI could add
steps, we would lose the safety guarantees, the resumability and the honest screen — and we
would be back to an agent with a shell.

---

## 2. We have already built one of these

`setup_service` is a blueprint engine in everything but name. It has `Step`, `Recipe`,
`build_recipe`, `progress`, `summarise`, `check_server` (refuse before starting), optional
steps, a live screen and resume. Server setup runs 14 steps through it today.

Its one limit: **a step is a playbook slug**. A blueprint needs steps that are service calls
too — "create the site", "add an uptime monitor", "turn on HTTPS".

**Plan:** build the blueprint engine by generalising that shape, where a playbook is just
one kind of action. Do **not** rewrite server setup onto it first — it works and it sits on
the flagship path. Fold it in later, once the engine has run in anger.

---

## 3. What people will actually use

Ranked by (how often it is needed) × (how much of it we already have).

| # | Blueprint | Who | Why it hurts today |
|---|---|---|---|
| 1 | **Set up a website on a raw server** | everyone | The flagship flow. Today it is 8–10 separate screens and you must know the order |
| 2 | **Take over a server somebody else built** | agencies | Done on every new client. Nobody knows what is on the machine or who can log in |
| 3 | **Get a site ready to go live** | everyone | The pre-launch panic: is HTTPS on, are backups running, does it actually work |
| 4 | **Move a website to another server** | agencies | The most feared job in hosting. People pay others to do it |
| 5 | **Secure a server** | everyone | Known to matter, never done, easy to lock yourself out doing it |
| 6 | **Retire a server** | agencies | "Can I delete this box?" — nobody can answer without checking six things |

**Ship 1, 2 and 3 first.** #1 is the headline, #2 is the agency wedge, #3 is cheap,
read-mostly and demos the whole idea in 30 seconds. #4 comes next because it is the
scariest and deserves the engine to be proven first.

---

## 4. What a blueprint is made of

```
key                  set-up-website
title                Set up a website on a raw server
for                  "I have a fresh server and I want a site on it"
takes                the inputs, and which of them we can work out ourselves
refuses_when         the conditions that make it pointless or dangerous to start
steps                the fixed list — label, action, changes_anything, optional, proof
leaves_for_you       the parts only a human can do (DNS, nearly always)
does_not_do          stated plainly, so nobody expects it
```

Rules every step obeys — each one is a lesson this codebase already paid for:

- **Refuse before starting, not halfway.** A step that cannot succeed is refused up front.
  Stopping before a stack is installed is clean; stopping in the middle leaves a machine
  nobody can reason about.
- **Never report success without checking the real thing.** A 200 is not proof — read the
  page. A service being "active" is not proof — see it answer.
- **A step that cannot apply here is absent, not failed.** On a control-panel server we do
  not write vhosts; that step is not in the list at all.
- **Safe to run twice.** Long jobs get resumed. A step that is once-only says so.
- **Failure stops the run and keeps everything before it.** No guessing past a failed step
  that later steps need. It says what happened, what to do, and offers to continue.
- **Destructive is gated or absent.** Nothing is deleted to make a blueprint work.

---

## 5. The templates

### 5.1 Set up a website on a raw server

**Takes:** the domain; what to run (WordPress / Laravel / plain PHP / static). Optional:
PHP version, database engine. Everything else is worked out.

**Refuses when:** not a Linux server over SSH; a control panel owns the machine; the domain
already exists on it.

| # | Step | Changes? | Done means |
|---|---|---|---|
| 1 | Look at the server | no | We know its OS, whether it is fresh, whether a panel owns it |
| 2 | Prepare the server *(skipped if already done)* | yes | Updates, timezone, swap, SSH hardening, firewall, fail2ban, Nginx + PHP + database, monitoring |
| 3 | Create the website | yes | The folder and the web-server config exist and a page is served |
| 4 | Give it its own database *(only if the type needs one)* | yes | Database and an account with rights to that one database |
| 5 | Install the application | yes | WordPress / Laravel actually answers, not just "installed" |
| 6 | Turn on HTTPS | yes | A real certificate covering the domain and `www` — **refused, not failed, if DNS is not pointed yet** |
| 7 | Watch it | yes | An uptime check exists and has run once |
| 8 | Back it up daily | yes | A backup job exists; the first run succeeded |
| 9 | Check it is safe | no | A security grade, and a malware scan verdict |

**Leaves for you:** point the domain at the server (step 6 waits for it). The application's
admin password is written on the server, root-only — never shown in chat.

**Does not do:** buy a domain, change DNS, or send email.

---

### 5.2 Take over a server somebody else built

The agency job: a client hands over a server and nobody knows what is on it.

**Takes:** nothing beyond access. **Refuses when:** we cannot log in.

| # | Step | Changes? | Done means |
|---|---|---|---|
| 1 | Identify the machine | no | OS, size, control panel, what is installed |
| 2 | Find the websites | no | Every site, its folder, what it runs, whether it answers |
| 3 | Check who can get in | no | SSH keys and firewall openings, listed in plain language |
| 4 | Check it is safe | no | Security grade with the findings ranked |
| 5 | Check it is clean | no | Malware scan — **states honestly if it could not see everything** |
| 6 | Check the certificates | no | Days left on every site |
| 7 | Start watching it | yes | An uptime check per site that answers |
| 8 | Start backing it up | yes | A daily job; the first run succeeded |
| 9 | Write it down | no | One report: what is here, who can get in, what to fix first |

**Leaves for you:** removing access you do not recognise. We list it; we never remove a key
or a firewall rule on our own — that is how you lose a server.

---

### 5.3 Get a site ready to go live

Fast, almost entirely read-only, and the best demo of the idea.

**Takes:** which site.

| # | Step | Changes? | Done means |
|---|---|---|---|
| 1 | Does the domain point here? | no | Both the bare name and `www` |
| 2 | Is HTTPS on and healthy? | no | A certificate covering every name, with days left |
| 3 | Does it actually work? | no | The page has real content — not blank, not an error |
| 4 | Are backups running? | no | A job exists and the last run succeeded |
| 5 | Is anything watching it? | no | An uptime check exists |
| 6 | Is it safe? | no | Security grade + malware verdict |
| 7 | Is the software current? | no | PHP version supported, not end-of-life |
| 8 | Will search engines find it? | no | Not accidentally blocked (or deliberately blocked, if staging) |

**Ends with:** a tick list, and each failure offering the exact fix — most of which are one
step we already have.

---

### 5.4 Move a website to another server *(next, not first)*

The most feared job. Design notes now so the engine is built with it in mind.

Steps: check the destination fits (space, PHP version, database engine) → prepare it if raw
→ create the site there → copy the files → copy the database → repoint the config at the
new database → **prove it serves the real page using a Host header, before any DNS
changes** → hand over the DNS change → after DNS, HTTPS.

**Never** deletes the old site, and **never** touches DNS. The old one keeps running until
the owner says otherwise. The rule that makes it safe already exists in `staging_service`:
a copy that cannot be repointed at its own database is removed rather than left pointing at
live data.

---

## 6. How it feels to use

Over MCP, in the owner's own words:

> **Owner:** set up a WordPress site on my new server for shop.com
> **Their AI:** *(matches the blueprint, sees what it needs)* "That will prepare the server,
> create the site with its own database, install WordPress, turn on HTTPS, start daily
> backups and start watching it. About 15 minutes. Shall I?"
> **Owner:** yes
> **Their AI:** *(starts it, gets an id, polls)* "Step 3 of 9 — creating the website."

And in ServerAlly, on screen, at the same time: the goal at the top, the nine steps as a
checklist, the current one working, each finished one with its own plain sentence, and a
**Stop** button.

The comfort rules:

1. **They never learn a blueprint name.** They speak normally; the AI matches.
2. **They see the whole plan before anything runs**, and what it needs from them.
3. **Nothing destructive happens** without a clear yes — or at all.
4. **It says what is left for them.** DNS, nearly always.
5. **It can be stopped, and continued.**
6. **It never says done without checking the real thing.**

**Stop** must be honest about its limits: it refuses everything further, it cannot undo what
already ran, and it cannot stop their AI from thinking. Say that on the button's own
confirmation, not in a help page.

---

## 7. The MCP surface (shape only)

Four tools, following the start-and-poll pattern already proven by `run_playbook` — a tool
call must never block, because clients time out in minutes.

- **list what is available** — each with what it does, what it needs, and what it will not do
- **start one** — with the inputs; returns an id immediately
- **check on it** — the goal, every step with its state, what it is waiting for, what is left for you
- **stop it**

`list` is read-only. `start` and `stop` need execute permission, like every other write.

---

## 8. Open questions

1. **Where do inputs the AI did not supply come from?** Stop and ask (safe, slower), or
   work them out (fast, sometimes wrong)? Leaning: work out what is genuinely derivable
   (database name, folder), stop for anything a human owns (the domain).
2. **Does the screen also show blueprints started inside the app?** It should — the same
   engine, one screen, whichever door it came in by.
3. **Per-blueprint approval gates.** #4 (moving a site) wants one before the cutover. That
   needs a step that can wait for a human without holding a tool call open — the same
   start-and-poll shape, applied to approval.
4. **Do we let customers write their own?** Powerful, and a different product with a
   different safety story. Not now; do not design it out.

---

## 9. One screen, and where it lives

### 9.1 It replaces the MCP drawer — but not one-for-one

The top-bar drawer does two jobs at once, and only one of them is worth keeping.

- **Telling you something is happening** — worth keeping, and it must stay global. You should
  learn that your AI is working from any page.
- **Being the place you read it** — wrong. It is a small panel that covers the page, and a
  long job needs a page of its own: one you can link to, come back to, and read afterwards.

So: **the drawer's list goes; a live indicator stays.** The top bar shows a compact pill —
*"Setting up shop.com · 3 of 9"* with a spinner — that clicks through to the run. When nothing
is running the pill is **absent, not greyed out**, the same rule the menus already follow.

### 9.2 Two modes, one screen

An MCP action is not always part of a plan. The screen handles both, and the only difference
is the header.

| | We know the plan | We are following along |
|---|---|---|
| When | A blueprint was started | The AI just did things |
| Title | The blueprint's goal | What the AI said it was doing, else "Work on TestServerNew" |
| Progress | Checklist, "3 of 9", time left | A growing list, "4 steps so far" |
| Bar | Yes | **No** |

**Never show a progress bar we cannot honour.** A bar with no known end is a lie, and it is
the first thing that makes a screen untrustworthy. Steps that belong to nothing still appear —
under "other work" — because losing them is worse than not grouping them.

### 9.3 Where it shows

| Place | What appears | Status |
|---|---|---|
| **Top bar** | The live pill; absent when nothing runs | Replaces the MCP drawer |
| **Nav → Activity** | The list: running first, then finished. Badge when something needs you | New item |
| **`/activity/:id`** | The full screen | New page |
| **Dashboard** | Feeds the existing `RunningTasks` card | Already there |
| **A server's page** | A strip when something is running on *that* server | Small addition |
| **A site's page** | The same, for a run about that site | Small addition |

### 9.4 The thing to be careful about

We already have three places that answer "what happened": **Missions** (in the nav),
**`/logs`** (a real page with no nav item, reached from a Dashboard tile), and the **MCP
drawer**. Adding a fourth would be the fragmentation this product keeps having to undo.

From the owner's side there is only one idea: *a long job running on my servers.* Whether the
steps came from a blueprint, from Ally, or from their own AI is our implementation detail, and
nobody should have to learn it to find their work.

**So the destination is ONE page — Activity — and we walk to it, not jump:**

1. Build the run screen and the Activity list. Blueprint runs live there.
2. Move MCP actions in. Delete the drawer's list; keep the pill.
3. Fold in playbook runs and deployments — they are already runs with steps.
4. Last, and only once the screen has proven itself: missions join, and the Missions nav item
   goes. Its history and reports stay reachable; they just stop being a separate place.

Step 4 is the one to leave alone for now. Missions carry approval, resume and the verification
gate, and moving them is a change to a working flagship path.

---

## 10. Phases

Six. Each one is useful on its own and can be stopped after.

| # | Phase | Ends when | Size |
|---|---|---|---|
| 1 | **The engine + one blueprint** | *Set up a website* runs end to end on a real raw server, started from the app | Large |
| 2 | **The screen** | The run page, the Activity list, the top-bar pill, the strips | Medium |
| 3 | **Over MCP** | A customer's AI starts it by name, watches it, and stops it | Small |
| 4 | **Two more blueprints** | *Take over a server* and *Get a site ready to go live* | Medium |
| 5 | **Absorb MCP actions** | Loose AI actions appear as runs; the drawer's list is deleted | Small |
| 6 | **Move a website** | A site moves between servers, proven both ways on real machines | Large |

**Phase 1 is deliberately app-first.** Building the engine and exposing it over MCP at the
same time means debugging two new things through each other. Start it from a button, prove it
on a real server, then hand the same thing to an AI in phase 3 — which is then genuinely small,
because it is four thin tools over an engine that already works.

### The hard part in each phase

1. **Resume.** A fifteen-minute job will cross a backend restart. Missions already solved
   this (`recover_orphaned` flips anything left running to interrupted); copy the lesson
   rather than rediscovering it. Also: every step must decide what "already done" means, so
   a resumed run skips what it should and repeats what is safe.
2. **Not looking frozen.** A step can be silent for minutes. Service steps get a written
   line per step; playbook steps can stream. Either way a heartbeat, because the apt-lock
   work already proved that silence reads as a hang.
3. **Never block a tool call.** Start returns an id immediately and the AI polls — the
   pattern `run_playbook` already uses, because MCP clients time out in minutes.
4. Mostly data, once the engine is right. *Take over a server* is almost all read-only, so
   it is the safest place to widen the action list.
5. Deciding what an ungrouped action looks like — and resisting the temptation to give it a
   progress bar.
6. The cutover. Prove the copy serves the real page with a Host header **before** any DNS
   change, never delete the old site, never touch DNS.

### A third status, needed from day one

A step can succeed, fail, or **wait for the human**. HTTPS on a domain that is not pointed yet
is not a failure, and the flagship blueprint cannot finish honestly without that state. Build
it in phase 1, not later.

### One decision needed before phase 1

**A missing input: stop and ask, or work it out?** Leaning — work out what is genuinely ours
to know (the database name, the folder, the PHP version), and always stop for anything the
human owns (the domain). It needs to be settled first because it changes the shape of `start`.
