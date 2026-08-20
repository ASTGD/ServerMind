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
