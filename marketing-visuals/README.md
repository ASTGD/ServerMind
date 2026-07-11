# ServerAlly — marketing visuals

Captured live from the real product (account: Sharwat Shafin) on **2026-07-08**, during the
Phase-4 end-to-end verification of the "One Ally / Workspace" rebuild. Everything shown is a
**real mission on a real server** (TestServer4, Ubuntu + CyberPanel), not a mockup.

Window size 1440×783. All content is genuine Ally output.

## Hero stills (hand-picked)

| File | What it shows | Good for |
|---|---|---|
| `01-mission-offer.png` | Ally offers a mission from one sentence — "Host a WordPress site at demo.serverally.org" — with a runbook badge, the goal, and **Start mission**. It already knows TestServer4 hosts blog.serverally.org and flags the DNS/SSL caveat up front. | "Describe it in plain English → Ally plans the whole job." |
| `02-workspace-approval.png` | The **Workspace** — chat on the left, live work on the right. Step 1 done ✓, step 2 running, and the approval surfaces **inside the workspace card** (the real `cyberpanel createWebsite` command + Approve / Stop). | "You stay in control — risky steps ask first." |
| `03-workspace-verified.png` | The finished mission with the **verification gate**: "Verified — fresh evidence confirms the site is live (homepage 200, login 200, wp-content present)." Honest about DNS/SSL being skipped. Admin password saved server-side, never shown in chat. | "Ally proves the work is done — and is honest when something's pending." |
| `04-security-sweep-summary.png` | A one-message security investigation → a structured, plain-English **Security Sweep Summary** (web server, security monitoring, listeners), with an honest ⚠️ "what stands out." | "Ask Ally to check for hackers — get a clear, readable answer." |

## Full recording

`serverally-ally-workspace-demo.gif` — the whole session (a security sweep, then the
WordPress-hosting mission end to end), 36 frames, no watermark/overlays.

## All frames

`frames/frame-00.png … frame-35.png` — every captured frame, in order, if you want to pick
different moments (e.g. the server-name chips, the "Focused on TestServer4" indicator, the
step-by-step workspace progress).

## Notes / caveats
- `demo.serverally.org` is a **real** WordPress site created live on TestServer4 during this
  capture (verified from outside: homepage + wp-login return 200, title "ServerAlly Demo",
  WordPress 7.0). It serves over plain HTTP by IP/Host header because the domain's DNS isn't
  pointed at the server; point an A record to 91.109.20.155 and Ally can issue SSL.
- The IP addresses visible in `04-security-sweep-summary.png` (150.228.135.x) are ServerAlly's
  own management IPs — you may want to blur them before public use.
