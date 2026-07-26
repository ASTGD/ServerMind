# What category are we in, and how do we sell it

> **Created 2026-07-26.** The owner asked: *"if we do not have these control panel type
> functionality how we market this? what will the category of our product then?"*
>
> Builds on [MARKET-RESEARCH-2026-07.md](MARKET-RESEARCH-2026-07.md) §8.1 (*do not become a
> control panel*) and §8.3 (the positioning line). This doc answers the question that was
> left open: if not a panel, then **what**, and whose money does it come from.

---

## 1. The answer in one line

**A control panel sets a server up. We keep it running, and fix it when it breaks.**

Those are two different jobs, bought at two different moments, out of two different budgets.

---

## 2. The category we are not, and why that is good news

Being a control panel is a bad business:

- **Five of the ten panels are free** (CyberPanel, HestiaCP, aaPanel, CloudPanel, Webmin).
- The paid ones need a mail stack, a nameserver, phpMyAdmin, FTP accounts and a reseller
  hierarchy — **years of work** to reach the starting line.
- The category's own users rate it **NPS 28**. People do not love their panel; they tolerate it.

Competing there means years of work to arrive at parity with something free that nobody
likes. That is not caution — that is the wrong game.

---

## 3. The category we are in

Say it as a job, not as a software genre:

> ### The sysadmin you do not have.

Industry label, for anyone who needs one: **server operations and incident response**. But
never lead with that phrase to a customer — lead with the job.

**The analogy that makes it click:**

| | |
|---|---|
| A control panel is the **garage and its tools** | You use it to build and configure |
| ServerAlly is the **mechanic on call** | Notices the problem, diagnoses it, fixes it, hands you the report |

**Nobody asks a mechanic why they cannot manufacture a car.** The moment the category is
right, the missing panel features stop being embarrassing and become simply *not our job*.

---

## 4. ⭐ The commercial reason this matters — whose budget we come from

This is the real answer to *"how do we market this"*, and it is a pricing argument as much as
a marketing one.

| If we are positioned as… | We are compared against | Our $19 looks… |
|---|---|---|
| A control panel | Free panels, Ploi €13, RunCloud $19 | **Expensive**, and feature-poor |
| The sysadmin you do not have | Paying a person, or an agency retainer | **Almost free** |

**Same product. Same price. Opposite conclusion.** The category we claim decides which
comparison the buyer runs in their head.

> ⚠️ **Before this goes on the website:** get a real, citable figure for what a freelance
> sysadmin or a managed-server retainer actually costs in our target markets. The argument is
> sound, but the number must be verified, not estimated. Everything else in
> [MARKET-RESEARCH](MARKET-RESEARCH-2026-07.md) was adversarially verified; this claim should
> be too.

---

## 5. How we talk about panels — with, never instead of

This is a genuine strength and currently unmarketed.

**A panel manages one server. We manage all of them, whatever is on them.** Plain Ubuntu,
cPanel, CyberPanel, Plesk, Windows, a Raspberry Pi, five different cloud providers. Panels
are licensed and installed *per server*, which is the structural weakness of the entire panel
category — none of them can see across a fleet.

So the line is **"ServerAlly manages your servers *and* your panels"** — never *"instead of
your panel"*. If a prospect asks *"do I still need my panel?"*, the honest answer is **yes,
keep it — we sit above it.**

---

## 6. What we say, in the customer's words

Three claims, all true today, all currently unmarketed:

1. **"Every server in one place."** Any provider, any operating system, any panel. Nobody
   else does cross-provider — Kodee, Rocket.net and every panel are locked to one host.
2. **"It does the work, and proves it worked."** Ally does not suggest; it acts, then checks
   its own result and refuses to claim success it cannot demonstrate. No competitor verifies
   outcomes.
3. **"It notices you were hacked, and helps you clean up."** The category ceiling is a
   firewall and Fail2Ban. We detect, preserve evidence, and guide the cleanup.

And the one that only makes sense once the category is right:

4. **"Your safety is never behind a paywall."** Backups, scans, malware detection and
   incident response on every plan, including free. A mechanic who withholds the brake check
   until you upgrade is not a mechanic.

---

## 7. The honest limitation — say it, do not hide it

**We are not the first thing a customer buys.**

Someone purchasing their very first VPS, with nothing running on it yet, should install a free
panel. They have nothing to keep running. We become worth paying for at the point where:

- they have **more than one server**, or
- **something has already broken** and they did not know why, or
- they have **clients** who ask whether the site is up.

Our free tier is the on-ramp for that person, but our real buyer **already has servers
running.** Marketing that pretends otherwise will attract the wrong signups and a bad
conversion rate.

---

## 8. What follows for the product

The category makes the roadmap arguments decide themselves:

| Question | Answer, given the category |
|---|---|
| Build a Sites section? | ✅ **Shipped 2026-07-26** — the discover-and-operate version. Seeing every site you run is the mechanic's job; creating one is the garage's. |
| Build deploy-from-git? | Not yet. That is launching, not running. Revisit only if paying customers ask. |
| Build DNS, PHP switching, email, phpMyAdmin? | **No.** Panel work. |
| Build cloud server creation? | No. Someone else's setup step. |
| Keep safety ungated? | Yes — it is the category's core promise, not a feature. |
