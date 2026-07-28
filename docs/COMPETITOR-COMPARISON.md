# ServerAlly vs the market

**Prepared 2026-07-28.** Condensed from our own research
([MARKET-RESEARCH-2026-07.md](MARKET-RESEARCH-2026-07.md),
[PRICING-METRIC-RESEARCH.md](PRICING-METRIC-RESEARCH.md),
[COMPETITOR-LANDSCAPE.md](COMPETITOR-LANDSCAPE.md)), which was compiled from vendors' own
pricing and documentation pages. Our own column is generated from the product's live
configuration, not from plans or notes.

---

## 1. The short version

Four days ago we were behind the established players on ordinary, expected features while
being far ahead on AI. **We have now closed ten of the twelve gaps our research found.**
On the standard checklist we are at or near parity. On what happens when something breaks,
nobody in this market is close.

The risk has moved. It is no longer "we are missing features" — it is **"nobody knows we
have them."** Our engineering lead is much bigger than our marketing lead.

---

## 2. Who we are actually compared against

| Group | Who | What they sell | Do they overlap with us? |
|---|---|---|---|
| **Deploy platforms** | Ploi, RunCloud, Laravel Forge, SpinupWP, GridPane | Blank server → working web server → deploy code | Partly. They build; we also repair. |
| **Managed hosts** | Cloudways, Hostinger, Kinsta, Rocket.net | Hosting, with a panel attached | Only on their own servers |
| **Control panels** | cPanel, Plesk, CyberPanel, aaPanel, CloudPanel | The panel installed on one server | Baseline features only |
| **AI-first rivals** | Panelica OpsAI, CtrlOps, Hostinger Kodee | The same promise we make | **Yes — directly** |
| **Free / open source** | servermind.dev | Fleet monitoring, free forever | Sets the price floor |

**One structural point matters more than any feature.** Every one of them is tied to one
place. A panel is licensed per server. A host's AI only touches that host's servers. An
agency with servers at five different providers cannot use any of them as a single view.
**We are the only one that is not tied to a provider.**

---

## 3. Feature comparison

✅ = has it · ⚠️ = partial or paid extra · ❌ = does not have it · — = not established in our research

| | **ServerAlly** | Ploi | RunCloud | Forge | SpinupWP | Cloudways | cPanel / Plesk | Panelica | servermind.dev |
|---|---|---|---|---|---|---|---|---|---|
| **Works across different providers** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ own only | ❌ per server | ❌ per server | ✅ |
| Deploy from a repository | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| Deploy on push | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| Rollback · zero-downtime | ✅ | ⚠️ paid | ⚠️ **$49 tier** | ✅ | ❌ | ⚠️ | ❌ | — | ❌ |
| Staging | ✅ | ⚠️ paid | ✅ | ❌ | ✅ best in class | ✅ | ⚠️ WordPress only | — | ❌ |
| Firewall screen | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ **add-on — their users' #1 request** | ✅ | ❌ |
| SSH key management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| DNS records | ✅ Cloudflare | ✅ Cloudflare | ⚠️ **$49 tier** | ❌ **none** | ❌ **none** | ⚠️ 3rd-party | ✅ full nameserver | ✅ Cloudflare | ❌ |
| Backups | ✅ **all plans** | ⚠️ **paid tier** | ✅ | ⚠️ **database only, paid** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Backups stored off the server** | ✅ 6 providers | ✅ 3 | ✅ | ⚠️ | ✅ **10 providers** | ⚠️ paid extra | ✅ | ✅ | ❌ |
| Uptime — "is the site down" | ✅ **all plans** | ⚠️ **top tier only** | ✅ | ✅ | ⚠️ **$1/site extra** | ✅ | ⚠️ | ✅ | ⚠️ server-level |
| Service monitoring + auto-restart | ✅ | — | — | ✅ | — | ⚠️ | ⚠️ | ✅ | ⚠️ |
| Certificate expiry warning | ✅ | — | — | — | — | — | ✅ Plesk | — | ✅ |
| Server log viewer | ✅ | ✅ | — | ✅ | ✅ | — | ✅ | ✅ | ❌ |
| On-call escalation, unanswered → next person | ✅ *(SMS/Telegram on Pro)* | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Public status pages | ✅ | ⚠️ **top tier** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| White-label / client reports | ✅ | ✅ *(Ploi Core, €30)* | ❌ | ❌ | ⚠️ | ⚠️ **invoices only** | ✅ | — | ❌ |
| API for customers | ✅ | ✅ all paid plans | ⚠️ **$49 tier** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Team logins with roles | ✅ | ⚠️ **€30 tier** | ⚠️ **$49 tier** | ✅ | ⚠️ **$2/user** | ✅ | ✅ | ✅ | ❌ |
| **Create / resize / destroy servers** | ✅ 2 providers | ✅ 8 providers | ✅ | ✅ | ✅ 6 providers | ✅ | ❌ | ❌ | ❌ |
| Email hosting, FTP, phpMyAdmin | ❌ *deliberate* | ⚠️ | ❌ | ❌ | ⚠️ | ⚠️ | ✅ | ✅ | ❌ |
| **AI that acts on the server** | ✅ | ❌ *(MCP only — no AI of their own)* | ❌ | ❌ | ❌ *("Assistant" is not AI)* | ⚠️ **server only, never the website** | ⚠️ roadmap — *"assist but not independently act"* | ✅ claimed | ⚠️ chat |
| **Checks its own work** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Long jobs that survive a disconnect** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Malware / intrusion detection** | ✅ | ❌ | ⚠️ | ❌ | ❌ | ⚠️ **$4/site extra** | ⚠️ add-on | ✅ | ❌ |
| **Guided hack cleanup + incident report** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Stops a hacked server tricking the AI** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Connect your own AI (MCP) | ✅ 22 tools | ✅ 60 tools | ⚠️ community | ⚠️ community | ⚠️ community | ❌ | ⚠️ roadmap | — | ⚠️ |
| Answers in 8 languages | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 4. Price comparison

| Product | Price / month | What it buys | Meters usage? |
|---|---|---|---|
| **ServerAlly Free** | **$0** | **2 servers** · 20 AI actions · **every feature** | No |
| **ServerAlly Pro** | **$9** | **10 servers** · 50 AI actions · **every feature** | No |
| **ServerAlly Pro+** | **$19** | **50 servers** · 100 AI actions · **every feature** | No |
| Ploi Basic | €8 | 5 servers — **no backups, no monitoring, no support** | No |
| Ploi Pro | €13 | 10 servers — backups and monitoring start here | No |
| Ploi Unlimited | €30 | unlimited — status pages and teams start here | No |
| RunCloud | $9 / $19 / $49 / $399 | 1 / **50** / 100 / 500 servers — **API starts at $49** | No |
| Laravel Forge | $12 / $19 / $39 | **unlimited servers, flat** | No — *"Is Forge usage-based pricing? No."* |
| SpinupWP | $12 / $19 | 1 server, then +$1–10 each, +$2/user, **+$1 per site monitored** | Partly |
| GridPane | **$0** up to 25 sites, then $19+ | per managed server; backups and monitoring are paid | No |
| Cloudways | ~$11+ by server size | hosting + server, unlimited sites | Meters disk and bandwidth |
| ↳ Cloudways AI Copilot | **+$3.99 / $9.99 / $19.99–80** | **4 / 12 / 25–100 AI credits** — runs out, AI stops | **Yes — credits** |
| cPanel | **$29.99 → $69.99** | 1 / 5 / 30 / 100 accounts, then $0.49 each | No |
| Plesk | **$16.99 → $69.99** | 10 / 30 / unlimited domains | No |
| Panelica *(closest rival)* | **$0 / $4.99 / $9.99 / $24.99** | 3 / 15 / 50 / unlimited **domains**, AI included | No |
| Hostinger VPS + Kodee AI | **$6.49** | a VPS with a **free, unlimited AI assistant** | No |
| servermind.dev | **$0 forever** | fleet monitoring, free AI, open source | No |

**Three things to take from this table.**

1. **Nobody in this market charges by usage.** Every survivor prices on servers. The
   "requests per minute" figures visible in Ploi and RunCloud plans are rate limits, not
   prices. Our pricing follows the market; we should never invent a new unit.
2. **Our middle tier is the weak spot.** Our top tier at $19 matches RunCloud's 50 servers,
   but our **$9 Pro gives 10 servers against RunCloud's 50 at the same price**, and Forge
   gives unlimited for $19 flat. Servers cost us very little. **Raising the Pro count is the
   cheapest change we can make to stop looking worse than we are.**
3. **"Every feature on every plan" is a real, sayable advantage.** At €8 Ploi gives five
   servers with no backups, no monitoring, no file explorer and **no access to support**.
   We give a free account backups, malware scanning and incident response. That is a
   sentence we can put on the pricing page next to a named competitor.
4. **We are the only one whose AI never stops working.** Cloudways sells AI credits — run
   out and the fixing stops. We include AI in the plan. Nobody else in this market sells
   AI by the unit, and the two that tried it in adjacent markets caused public refunds.

---

## 5. Where we clearly win

Verified across **15+ AI products** in our research. Not one of them has any of these:

1. **It proves its own work.** When Ally says a job is done, a second independent check
   gathers fresh evidence that it really worked. If it cannot prove it, it says so. Every
   other AI in this market simply reports success.
2. **It finishes long jobs.** Multi-step work that adapts as it goes, asks permission before
   anything risky, survives a lost connection and can be resumed. Everyone else's AI answers
   one question at a time.
3. **It handles a hack.** Detect, preserve evidence, contain, clean, harden — then write the
   plain-language story of what happened. The rest of the market stops at a firewall.
4. **A hacked server cannot turn our AI against the customer.** An attacker can hide fake
   instructions in a server's own files and logs. We treat everything read from a server as
   information, never as orders — tested against a real attack on a live compromised server.
   **No competitor even discusses this risk**, while all of them feed server logs to an AI.
5. **One place for every provider.** Nobody else does this. It is structural, not a feature
   they can add quickly — panels are licensed per server and hosts' AI belongs to the host.

**The one provable gap to name in a sales conversation:** Cloudways' AI fixes *server*
problems but **explicitly refuses to fix the website itself** — it only tells you what is
wrong with WordPress. Fixing a broken WordPress site is exactly what our rescue missions do,
proven live. Hostinger's free Kodee has no such limit, but it only ever works on Hostinger's
own servers.

**The honest framing:** "AI in a server panel" is no longer new — Hostinger, Cloudways,
aaPanel and others all ship it. **"AI that acts safely across a whole fleet, and proves what
it did"** is still ours alone.

---

## 6. Where we are still behind

Stated plainly so nobody is surprised.

| Gap | Detail | Plan |
|---|---|---|
| Creating servers covers 2 providers, not 5 | DigitalOcean and Hetzner are done. Amazon, Google and Azure need networks and disks decided before a machine exists, so they stay import-only for now. | Deliberate; revisit on demand |
| No command-line tool | We have an API; some buyers expect a CLI too. | Small; not scheduled |
| No email hosting, FTP accounts, phpMyAdmin | Control panels have these; we deliberately do not. | **Deliberate — we sit above the panel, not inside it** |
| DNS is Cloudflare only | The other providers use the same design and are quick to add. | On request |
| Payment path never run end to end | The billing module is written and our side is tested, but it has never executed against a real WHMCS. | **Largest untested item before launch** |
| Prices not yet public | Our measured AI cost is about double what the $9/$19 prices assumed — from our own heavy testing, not real customers. | Confirm with a small group of users first |

---

## 7. What changed in the last four days

Our research on 25 July listed twelve gaps against the market. **Nine are now closed.**

| Gap on 25 July | Status today |
|---|---|
| Backups stored on the same server they protect | ✅ Offsite, six storage providers |
| No "is the site down" monitoring | ✅ Uptime + real content checking |
| Cannot read the server's own logs | ✅ Log viewer with problem highlighting |
| No website list on ordinary servers | ✅ Sites view across the whole fleet |
| No DNS management | ✅ Cloudflare |
| No deploy pipeline, rollback or staging | ✅ All three, plus deploy-on-push |
| No firewall screen | ✅ With lockout protection |
| No SSH key screen | ✅ With lockout protection |
| No white-label or client reports | ✅ Both |
| No public API | ✅ API keys + signed webhooks |
| Cannot create/resize/destroy cloud servers | ✅ DigitalOcean + Hetzner |
| PHP version switching, queue workers | ❌ **deliberately dropped** — panel features, not ours |

---

## 8. How much to trust these numbers

- Competitor prices and features were read from **the vendors' own pricing and
  documentation pages** on 25 July 2026, with one correction on 17 July read from a **live
  Ploi trial account** — Ploi's real in-app plan page differs from its marketing page.
- Where a cell shows **—**, our research did not establish it either way. It should not be
  read as "they do not have it."
- Our own column comes from the product's live configuration, not from a plan document.
- Prices move. Anything quoted here should be re-checked before it goes into public
  marketing.

---

*Fuller detail, with sources: [MARKET-RESEARCH-2026-07.md](MARKET-RESEARCH-2026-07.md).
Our complete feature list: [FEATURE-LIST.md](FEATURE-LIST.md).*
