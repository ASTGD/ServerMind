# Case study — Root compromise of a 51-site shared hosting server, detected & cleaned with ServerAlly

**Server:** `panel2.firevps.net` (51.79.149.130) — Ubuntu, CyberPanel / OpenLiteSpeed, 81 configured websites (51 primary + 23 child/sub-domains + 7 suspended), root access
**Incident date:** 14 July 2026
**Severity:** Critical (full root takeover, ~2 months of attacker access)
**Outcome:** Backdoor removed, three infected sites cleaned, all 51 sites swept, entry point identified — cleaned in place with a rebuild recommended for the worst site.

> A management-ready one-page version of this report is published as an Artifact (printable / shareable). This document is the fuller case-study write-up.

---

## 1. What happened, in one paragraph

An attacker got into `panel2.firevps.net` through an **outdated, vulnerable WordPress plugin** (`wp-file-manager`) on one hosted site, `richhome.com.bd`. They uploaded a hidden **webshell**, escalated to **root**, and installed a stealth **gsocket backdoor** (`initfs`) that phoned out on port 443 to defeat the firewall — giving them a hidden root shell they could return to at any time. The site had, in fact, been quietly compromised since **October 2022**. ServerAlly found it, removed the active backdoor, quarantined the malware across the affected sites, and swept all 51 sites — while being honest that a root-compromised box can only be *fully* trusted again after a rebuild.

## 2. The attack chain

```
Vulnerable WordPress plugin (wp-file-manager, richhome.com.bd)
   └─ automated exploit scanners (CVE-2017-9841 PHPUnit, CVE-2018-9206 jQuery-File-Upload)
       └─ webshell uploaded (2022; refreshed 19 May 2026 → fcefabhjea.php)
           └─ privilege escalation to root
               └─ gsocket backdoor "initfs" installed (21 May 2026)
                   └─ persistent hidden root access, beaconing 152.53.173.29:443
```

## 3. Timeline

| When | What happened |
|---|---|
| **Oct 2022** | First webshell planted on `richhome.com.bd` — site quietly compromised for years |
| **2023–2025** | More webshells added over time (`product.php`, `goods.php`, `715525/index.php`) |
| **19 May 2026** | Fresh upload webshell `fcefabhjea.php` dropped in `wp-content/uploads` |
| **21 May 2026** | **Root escalation** — gsocket `initfs` backdoor installed, faking a systemd service, beaconing on :443 |
| **10 Jul 2026 20:05** | Automated tool copies the same shell into **8 folders in 7 seconds** (redundant backdoors) |
| **14 Jul 2026** | **Detected, contained & cleaned by ServerAlly**; all 51 sites swept |

## 4. Scope

The full hosting footprint was assessed — not just the 51 primary site homes, but the 23 child/sub-domains that live under a parent account (the initial sweep's blind spot; one such child domain, `old.rmp.gov.bd`, held 22 of the webshells). The 7 suspended sites have no files on disk.

| Website | Panel account | Findings | State |
|---|---|---|---|
| `desktopit.net` (+ child domains) | `deskt7376` | Backdoor traces + fake-`crond` C2 beacon + 22 webshells in a child domain (`old.rmp.gov.bd`); its ~10 other child domains swept — clean | Cleaned |
| `richhome.com.bd` | `richh9509` | Long-standing infection (2022+): many webshells, 3 fake admins, hidden `index.php` shells, loose plugin-dir shells | **Rebuild recommended** |
| `nwdcr.edu.bd` | `nwdcr9384` | `goods.php` webshell + Python C2 beacon | Cleaned |
| All other sites | — | 48 primary + 22 child/sub-domains swept (7 suspended have no files) — none found | Verified clean |

## 5. Remediation completed

- **Root backdoor removed** — `initfs` process killed, systemd service disabled + masked, binary/`.img`/unit moved to quarantine, evidence preserved.
- **C2 blocked** — attacker callback `152.53.173.29` denied in CSF firewall.
- **Site malware quarantined** (moved, not deleted) on the three infected sites.
- **3 fake WordPress admins removed** from `richhome.com.bd`.
- **Whole-server sweep** — only `root` is uid-0; no crypto-miner, no `ld.so.preload`, no second implant.

## 6. Outstanding (needs owner/management authorisation)

1. **Rotate ALL credentials from a clean device** — root, all 51 CyberPanel accounts, SSH keys, every DB + WordPress admin password. A root compromise means every secret was exposed.
2. **Review the 4 root SSH keys**; remove any not recognised.
3. **Rebuild `richhome.com.bd`** from clean (compromised since 2022; keeps yielding malware). Its last 5 plugin-folder shells were quarantined 14 Jul — incl. a hidden-admin backdoor that recreates the rogue WordPress user `david.pueray@hotmail.com`; that DB account must be deleted (the rebuild handles it). Site is now file-clean (HTTP 200).
4. **Patch/remove `wp-file-manager`** and audit every site for outdated plugins.
5. **Consider a full server rebuild** — the only *fully certain* remediation after a root compromise.

## 7. Indicators of compromise (IOCs)

**Root backdoor**
- Binary: `/usr/sbin/initfs` (ran as `/sbin/initfs`) — gsocket / gs-netcat reverse shell
- SHA-256: `5bb332ff977919ccbab39a2b4ac91261c8f316628044c7473369d91cc78ade65`
- Persistence: `/lib/systemd/system/initfs.service` (description faked "D-Bus System Connection Bus")
- C2: `152.53.173.29:443` (outbound; spoofed rDNS `cdnjs.cloudflare.com`); timestamps backdated to 2015

**Webshell families**
- Password-protected shells disguised as `index.php` in plugin/theme folders (markers `secretyt` / `pwdyt`)
- "PHP File Manager v1.4" backdoor (`admin` / `phpfm`) as `wp-blog.php`
- Obfuscated `eval($_POST["command"])` shells (`ftde.php`, `wp-head.php`)
- `.phar` and image-disguised PHP payloads in upload/asset folders

**Entry vulnerabilities:** CVE-2017-9841 (PHPUnit `eval-stdin.php`), CVE-2018-9206 (jQuery-File-Upload), plugin `wp-file-manager`.

**Not on the server:** `desktopit.net`'s public casino-spam page was a DNS / Cloudflare cache issue, **not** files on the box.

## 8. What this case demonstrates about ServerAlly

- **Read-only forensics first** — Ally investigated (access-log analysis, timeline reconstruction, plugin enumeration, host-level persistence checks) before changing anything, and **surfaced malware a signature sweep had missed** (loose PHP shells in the plugin folder).
- **Honesty over false confidence** — Ally correctly refused to declare a root-compromised box "fully clean," recommended credential rotation + rebuild, and flagged the DNS-layer spam as *not* a server issue.
- **Evidence preservation** — every malicious file was **quarantined, not deleted**, keeping the forensic trail intact.
- **Plain-language reporting** — the whole incident is explainable to a non-technical owner (see the published one-page report), the core of the "Explain this incident" feature.

## 9. Lessons (product backlog)

1. **A whole-box incident report** should aggregate across many missions + forensic runs (this incident spanned several) — a "fleet / box-level report", not just per-mission.
2. **Webshell scanning must also cover loose `.php` files in plugin/theme roots and fake-plugin folders**, not only `uploads/`, `index.php`, and known families.
3. **Beacon / threat detection must not exclude outbound `:443`** — that is exactly where gsocket hides.

---

*Prepared by ServerAlly (AI-assisted). Confidential — internal / management use.*
