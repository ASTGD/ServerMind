# How Ally Works — the "hard job" scenes (for Claude Design)

**Use these instead of the basic "why is my disk full?" chats.** Every scene below is a
REAL thing Ally did in live testing on real servers — not a mock-up. Render each as an
animated chat (typing effect, message-by-message), with the matching real screenshot
floating beside it (see `marketing-brief/assets/screens/`).

**The one rule to show everywhere:** *Ally never does anything destructive on its own.*
It looks first, asks before risky steps, **moves things to a safe quarantine instead of
deleting**, and only says "done" after it re-checks and gets a green **✓ Verified**.

Tone: talking to a scared non-technical owner. Warm, calm, plain English. No jargon.

---

## SCENE 1 — "My website got hacked" 😰  ← the hero scene

> **User:** Help! I think my website got hacked 😩
>
> **Ally:** I've got you. First I'll take a safe look around — I won't change a single
> thing yet, just investigate.
>
> **Ally:** You're right — someone got in. I found a hidden malicious file inside your
> uploads folder and a sneaky scheduled task the attacker left behind to reinfect you.
>
> **Ally:** I can clean this up. To be safe I'll **move** everything into a locked
> quarantine folder — nothing gets deleted, so we can always undo it. Want me to go ahead?
>
> **User:** Yes please 🙏
>
> **Ally:** Cleaned. I quarantined the bad file, removed the attacker's scheduled task,
> then ran a fresh scan to be sure. **✓ Your site is clean and verified.** Next I'd
> recommend changing your passwords — want me to walk you through it?

**Proof badge:** *Really tested — we planted two web-shells and a hidden backdoor on a live
server; Ally found all of them, moved (never deleted) each to quarantine, and a fresh scan
went from "compromised" → "no threats found."*

**Beat:** relief. The scary thing (a hack) handled calmly, safely, reversibly.

---

## SCENE 2 — "My site is down and I'm losing sales"

> **User:** My website is showing an error and customers can't check out 😫
>
> **Ally:** Let me take a live look right now… I can see it's returning a "500" error, and
> your site can't reach its database — the saved password doesn't match. That's the cause.
>
> **Ally:** It's a safe fix and I'll test the site right after. Go ahead?
>
> **User:** Do it
>
> **Ally:** Fixed. **✓ Verified** — I loaded your site and the checkout myself; both work
> again.

**Proof badge:** *Really tested — Ally caught a genuine 500 error and a real database
password mismatch on a live server, fixed it, and confirmed the site was back.*

**Beat:** "it just knew what was wrong." Diagnosis a normal person could never do.

---

## SCENE 3 — "Set up a whole website for me"

> **User:** Can you set up a WordPress blog at blog.mysite.com?
>
> **Ally:** Happy to. I'll create the site, build its database, install WordPress, and
> switch on the secure padlock (HTTPS) — then I'll check it's really live before I hand
> it back.
>
> *(animate the steps ticking: create site → database → install WordPress → enable HTTPS → verify)*
>
> **Ally:** Done — **your blog is live at blog.mysite.com with a secure padlock. ✓
> Verified** — I opened the homepage and the login page myself to be sure.

**Proof badge:** *Really tested — from one sentence, Ally built a complete WordPress site
end-to-end and we confirmed it live in a separate browser.*

**Beat:** a full pro setup, from one plain sentence.

---

## SCENE 4 — "Can't the hacker just trick you too?" (the trust scene)

> **User:** There's a note file on my server telling you to run some commands. Can you just
> do what it says?
>
> **Ally:** I read it — that file is a trap. It's trying to get me to secretly download and
> run code, which is exactly how servers get hijacked. **I did not run it, and I won't.**
> This looks like a break-in attempt — let's treat it as a security incident and find how
> it got there.

**Proof badge:** *Really tested — on a live server we planted hacker instructions three
different ways (even faked "the owner pre-approved this"). Ally refused every time and
flagged it instead.*

**Beat:** you can trust it with the keys. It can't be sweet-talked into harming you.

---

## The "Safety, always" strip (put near the scenes)

Four short promises with little icons:

- **Looks before it touches** — investigates read-only first, changes nothing until you say so.
- **Never deletes** — moves things to a safe quarantine you can undo. No shredding.
- **Asks before anything risky** — you approve; it never guesses on a dangerous step.
- **Proves it's done** — re-checks its own work and only shows ✓ Verified when it's truly fixed.

---

## The "Proven, not promised" strip (numbers are real — safe to print)

- **Tested on real servers**, not slides.
- **Survived a full break-it red-team** — including live hackers' hidden instructions — with no destructive action.
- **404 automated safety tests** guard every command before it can run.
- The entire break-it test campaign cost **under $2** of AI — Ally is careful *and* cheap.

*(Source of truth: `docs/ALLY-CAPABILITIES-TESTED.md`.)*

---

## What NOT to show
- Don't lead with "why is my disk full / how much space is free." Those are true but tiny;
  they make Ally look like a toy. Lead with the hack rescue and the down-site fix.
- Don't show Ally deleting anything. Ever. The story is *safe* power.
- No command-line jargon in the dialogue — a non-technical owner should understand every line.
