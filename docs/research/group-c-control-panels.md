# Group C — Traditional Server Control Panels
### Competitive research for ServerAlly · compiled 2026-07-25

**Vendors covered:** cPanel/WHM · Plesk · CyberPanel · HestiaCP · aaPanel · CloudPanel · DirectAdmin · Webmin/Virtualmin · CloudLinux OS + Imunify360 · ISPConfig

**Method:** vendor's own pricing/feature/docs pages treated as authority; forums and trade press used only for sentiment, migration trends and price history. Every factual claim carries a source URL. Anything not confirmed is marked **UNVERIFIED**.

**Research constraint (honest note):** the session's web-search budget ran out partway through, and three sites returned HTTP 403 to automated fetching (`webhostingtalk.com`, `support.plesk.com`, one bacloud article). Where this limited a claim it is flagged inline. Wayback Machine is not fetchable from this environment, so pre-2025 cPanel retail prices could not be read off archived vendor pages directly and are sourced from third-party trackers instead.

---

## 0. THE HEADLINE — read this first

Three findings dominate everything else in this group:

1. **The baseline is enormous and non-negotiable.** Ten panels built by unrelated teams over 25 years converged on the *same* ~20 capabilities. That convergence is the single most important output of this research and is set out in §5. A "server management product" that cannot create a website, issue an SSL cert, make a database, host email and run a backup is not, to this market, a product at all.

2. **The commercial panels are being repriced aggressively by a private-equity owner, and the market is visibly moving.** cPanel went from ~$20/mo unlimited-accounts (pre-2019) to $69.99/mo for 100 accounts + $0.49 per extra account (2026) — for a 500-account reseller that is roughly a 1,200% increase ([ServerPoint](https://www.serverpoint.com/en/articles/cpanel-price-increases-since-acquisition/)). cPanel's "engagement mindshare" fell 19.9% (Oct 2024) → 12.1% (Jan 2026) ([commandlinux](https://commandlinux.com/statistics/web-hosting-control-panel-market-share-cpanel-plesk-webmin-on-linux/)). Plesk — owned by the *same* company — raised prices ~26% in Jan 2026 ([webhosting.today](https://webhosting.today/2026/05/20/plesk-obsidian-18-0-77-ships-pricing-up-26-percent-ai-copilot-extension-coming/)).

3. **The AI lane is mostly announced-not-shipped by the *Western* incumbents — but one competitor has already shipped ServerAlly's exact architecture.**
   - **cPanel:** built-in AI is *roadmap* as of 2026-04-15, described as an in-product Q&A assistant, and cPanel explicitly states it will **"assist but not independently act"** ([cpanel.net](https://www.cpanel.net/blog/products/the-next-evolution-of-cpanel-built-in-ai-for-faster-smarter-hosting-management/)). Its 2026 roadmap also names **"MCP server support in WHM for more modern, prompt-driven admin interactions"** ([roadmap post](https://www.linkedin.com/posts/cpanel_cpanel-roadmap-2026-activity-7420496823657693184-2FAD)).
   - **Plesk:** "AI Copilot" natural-language management has **no committed ship date** as of 2026-05-20 ([webhosting.today](https://webhosting.today/2026/05/20/plesk-obsidian-18-0-77-ships-pricing-up-26-percent-ai-copilot-extension-coming/)). What *has* shipped is **Elvis Plesky**, a ChatGPT-powered *support/docs* assistant, and Sitejet's AI site generator — neither manages servers.
   - **DirectAdmin:** no first-party AI at all, no published AI roadmap.
   - ⚠️ **aaPanel has already shipped both halves of ServerAlly's bet:** an **AI Assistant plugin where the customer connects their own AI provider by API key** (chat-based nginx/MySQL diagnostics, performance analysis, security scanning, with granular permissions over System/Network/Databases) **and an official aaPanel MCP Server** exposing panel functions to any MCP-compatible AI ([aapanel.com/new/feature/ai.html](https://www.aapanel.com/new/feature/ai.html)). This is the same "bring your own AI" design as [PRICING-V3](../../../../../docs/PRICING-V3.md) Layer 2(a) and the same MCP lane ServerAlly shipped in July 2026 — from a panel with a very large install base.
   - **CyberPanel** ships a paid **AI WordPress Scanner** (pay-per-scan, undisclosed model) — narrow, WordPress-only, and priced on the exact per-use model PRICING-V3 forbids.

   **Read:** the *English-language, Western* incumbents have not shipped agentic AI. But "nobody has done this" is **not true** — aaPanel has. ServerAlly's differentiation must rest on **acting safely across a whole fleet**, not on being first to put an LLM in a hosting panel.

---

## 1. PRICING — the whole group at a glance

| Panel | Model | Free? | Entry price | Top price | Gates on |
|---|---|---|---|---|---|
| **cPanel/WHM** | Commercial, subscription | No | $29.99/mo (Solo, 1 acct) | $69.99/mo (Premier, 100) **+ $0.49/acct over 100** | **cPanel accounts** |
| **Plesk** | Commercial, subscription | 14-day trial | ~$16.99/mo (Web Admin, 10 domains) | ~$62.99–69.99/mo (Web Host, unlimited) | **Domains** |
| **DirectAdmin** | Commercial, subscription | 60-day trial (per trade press) | $5/mo (Personal PLUS, 2 acct/20 dom) | **$29/mo Standard = UNLIMITED accounts & domains** | Accounts + domains, then flat |
| **CyberPanel** | Open-source core + paid add-ons | **Yes — core free forever** | $0 | $59/yr add-on bundle · $99/yr everything | Add-on features only |
| **HestiaCP** | Open source (GPLv3) | **Yes — fully free** | $0 | $0 (donations) | Nothing |
| **aaPanel** | Freemium | **Yes — free tier** | $0 | $28.80/mo · $198/yr · $699 lifetime (Pro) | Pro features |
| **CloudPanel** | Free (MGT Commerce GmbH) | **Yes — fully free** | $0 | $0 | Nothing |
| **Virtualmin** | Open core (GPL) + Pro | **Yes — GPL free, unlimited domains** | $0 | Pro from $7.50/mo · $75/yr, tiered 10/50/100/250/unlimited domains | **Domains** (Pro only) |
| **ISPConfig** | Open source | **Yes — fully free** | $0 | Paid add-ons: billing module, migration toolkit, enterprise support | Add-ons only |
| **CloudLinux + Imunify360** | Commercial add-ons (not panels) | ImunifyAV free | Imunify360 from ~$12/mo/server | Tiered by user count per server | **Users per server** |

> **The single most important pricing fact for ServerAlly:** *five of the ten are free.* HestiaCP, CloudPanel, ISPConfig and Virtualmin-GPL are free with no meaningful cap, and CyberPanel's core is free forever. The floor price for "manage a server with a web UI" in this market is **$0**. Anything ServerAlly charges for must be priced against $0-for-the-baseline, not against cPanel's $69.99.

---

## 2. VENDOR-BY-VENDOR

### 2.1 cPanel & WHM

**Positioning:** the incumbent shared-hosting panel. Two interfaces — **WHM** (root/reseller server administration) and **cPanel** (end-user account). **Buyer = the hosting company / VPS owner**, licensed per server with account tiers; end users never buy it. Owner: **WebPros**. Commercial, closed source. Linux only — AlmaLinux 8/9/10, CloudLinux, Ubuntu 24.04 LTS. (Reports that Rocky Linux 8/9 is blocked for new installs from cPanel v134, Jan 2026, are **UNVERIFIED at vendor level**.)

| # | Capability | Verdict | Detail · source |
|---|---|---|---|
| 1 | Account/reseller mgmt | **YES** | WHM Account Functions; full reseller tier with packages + feature lists. Three-tier root → reseller → user. [docs.cpanel.net/whm](https://docs.cpanel.net/whm/) |
| 2 | Website/vhost creation | **YES** | cPanel » Domains (addon/sub/parked). [docs.cpanel.net/cpanel](https://docs.cpanel.net/cpanel/) |
| 3 | DNS server + records | **YES — real nameserver, with a choice** | **PowerDNS (default)** or **BIND** (also deprecated MyDNS/NSD) via WHM » Nameserver Selection. Free **cPanel DNSOnly™** license for dedicated DNS nodes. |
| 4 | Email — full stack | **YES** | Exim + Dovecot + Roundcube/Horde + SpamAssassin; SPF/DKIM in Exim Configuration Manager. DMARC = record creation yes, enforcement needs extra software (**UNVERIFIED** at vendor-doc level). |
| 5 | Databases + phpMyAdmin | **YES** | MySQL/MariaDB + Database Wizard; **phpMyAdmin bundled**. PostgreSQL supported. |
| 6 | FTP accounts | **YES** | FTP Accounts + Anonymous FTP. |
| 7 | SSL / Let's Encrypt | **YES** | **AutoSSL** auto-issue + auto-renew; provider selectable between cPanel-branded **Sectigo (default)** and **Let's Encrypt**. Bundled free. |
| 8 | PHP version + extensions | **YES** | **MultiPHP Manager** (per-domain version) + **MultiPHP INI Editor**; **EasyApache 4** builds versions/extensions. |
| 9 | Cron | **YES** | cPanel » Advanced » Cron Jobs. |
| 10 | Firewall | **PARTIAL — the notable gap** | **No general-purpose firewall manager.** Bundled = **cPHulk** brute-force + Host Access Control. Real firewall management = **ConfigServer CSF, third-party, separately installed.** *Matches the survey: 46.3% of cPanel's own users rank a native firewall manager their #1 request.* |
| 11 | Backups + offsite | **YES — best-in-group** | Daily/weekly/monthly + 1–9,999 retention. Destinations: **Additional Local Dir, Amazon S3, Backblaze B2, Custom, FTP, Google Drive, Rsync, S3-Compatible, SFTP, WebDAV.** [backup-configuration docs](https://docs.cpanel.net/whm/backup/backup-configuration/) |
| 12 | File manager | **YES** | Bundled. |
| 13 | Terminal in browser | **YES** | **Terminal** in both cPanel and WHM; needs shell access + feature enabled. [terminal docs](https://docs.cpanel.net/cpanel/advanced/terminal-in-cpanel/) |
| 14 | One-click apps | **PARTIAL** | **No general installer bundled.** Bundled = **WP Toolkit** (WordPress only) + **Sitejet Builder**. General installers are third-party paid: **Softaculous**, **Installatron**. Legacy "Site Software" deprecated. |
| 15 | Staging | **YES (WordPress only)** | WP Toolkit clone → staging. Was Deluxe-paid; free to licence holders since 15 Sep 2021. No generic site staging. |
| 16 | Git integration | **YES** | **Git™ Version Control** — host repos, clone remote, deploy via `.cpanel.yml`. Bundled. [git docs](https://docs.cpanel.net/cpanel/files/git-version-control/) |
| 17 | Monitoring / resource | **YES** | Analog/AWStats/Webalizer, Bandwidth, CPU & Concurrent Connection Usage, Site Quality Monitoring. Separate paid **Server Monitoring** product. |
| 18 | Security / malware / WAF | **PARTIAL** | **Bundled:** ModSecurity WAF (+optional OWASP CRS), cPHulk, IP Blocker, hotlink/leech protection. **Malware scanning NOT bundled** — ImunifyAV/Imunify360 (CloudLinux, third-party) or a ClamAV plugin. |
| 19 | Multi-server | **NO (native)** | **No native multi-server console.** Only **DNS Clustering** (zones only, not accounts/sites). Fleet management is done via **WHMCS** (separate WebPros product) or third-party tools. |
| 20 | API | **YES** | **UAPI** (user), **WHM API 1** (server), cPanel API 2 (legacy). JSON over HTTPS; **API Tokens** or Basic Auth. [api.docs.cpanel.net](https://api.docs.cpanel.net/) |
| 21 | CLI | **YES** | `whmapi1`, `uapi`, `cpapi2` + `/usr/local/cpanel/scripts/*`. |
| 22 | Mobile app | **NO (current)** | Official apps launched 2017, appear discontinued ~2019; no current vendor app page found. **UNVERIFIED at vendor level.** |
| 23 | AI | **PARTIAL / roadmap** | See §2.11 — in-product assistant + **MCP server support in WHM**, both roadmap not GA. Shipped adjacent: **WP Squared** (Extendify AI page generation), Sitejet AI. [webpros.com/ai-at-webpros](https://www.webpros.com/ai-at-webpros/) |

**Unique:** nameserver *choice*; richest native backup-destination list of any panel here; **WP Squared** ($84.99/mo, 10 sites) — a CloudLinux-built managed-WordPress layer bundling CageFS, Imunify360, AccelerateWP, Extendify, Patchstack.

### 2.2 Plesk

**Positioning:** the cross-platform, extension-driven "WebOps" panel — **the only one in this group that runs on Windows Server.** **Buyer = VPS owners, agencies, developers *and* hosts**; the 10 → 30 → unlimited domain ladder deliberately reaches small buyers, unlike cPanel's host-only framing. Owner: **WebPros** (same parent as cPanel). Commercial, closed source. Linux (Ubuntu 20.04/22.04, Debian 11, CentOS/RHEL/CloudLinux) **and Windows Server 2016/2019/2022/2025, NTFS only** ([system requirements](https://docs.plesk.com/release-notes/obsidian/system-requirements/)).

| # | Capability | Verdict | Detail · source |
|---|---|---|---|
| 1 | Account/reseller mgmt | **YES** | Customers, Resellers, Service Plans, Subscriptions + granular User Roles. [plesk.com/features](https://www.plesk.com/features/) |
| 2 | Website/vhost creation | **YES** | Domains/subdomains/aliases; Apache, NGINX (proxy or standalone), IIS on Windows. |
| 3 | DNS server + records | **YES — real nameserver** | **BIND on Linux**, **Microsoft DNS on Windows** (BIND installable as an alternative). **DNSSEC.** Can also run DNS-less with external DNS. [dns docs](https://docs.plesk.com/en-US/obsidian/administrator-guide/dns.59440/) |
| 4 | Email — full stack | **YES** | **Postfix** (Linux) / **MailEnable** (Windows); Horde + Roundcube; autodiscovery for Outlook/Thunderbird; **"Plesk supports DKIM, SPF, SRS, DMARC"**; SpamAssassin bundled. Optional paid Premium Email / Email Security extensions. |
| 5 | Databases + phpMyAdmin | **YES** | MySQL/MariaDB, PostgreSQL, MS SQL (Windows). **phpMyAdmin bundled.** Note **phpPgAdmin was dropped from Onyx 17.8** — PostgreSQL has no bundled web GUI. [KB](https://support.plesk.com/hc/en-us/articles/12377170988567-phpPgAdmin-is-not-available-for-installation-in-Plesk) |
| 6 | FTP accounts | **YES** | Per subscription (ProFTPD / IIS FTP). |
| 7 | SSL / Let's Encrypt | **YES** | **SSL It!** — LE issue + auto-renew, wildcard, HSTS, OCSP stapling, HTTPS redirect. Bundled free. |
| 8 | PHP version + extensions | **YES** | Multiple versions + handler types per site; per-domain PHP settings UI. Also Node.js, Python, Ruby, Perl, .NET, Docker. |
| 9 | Cron | **YES** | "Scheduled Tasks". |
| 10 | Firewall | **YES (bundled)** | **Plesk Firewall** extension manages iptables/nftables; **fail2ban active out of the box**. Paid third-party upgrade: Juggernaut Security & Firewall. [firewall docs](https://docs.plesk.com/en-US/obsidian/administrator-guide/plesk-administration/plesk-for-linux-the-plesk-firewall.72046/) |
| 11 | Backups + offsite | **YES** | **Incremental** scheduled backups; remote **S3, Google Drive, OneDrive** + Dropbox/FTP via extensions. Granular site/database restore. |
| 12 | File manager | **YES** | Bundled, with mass upload + file search. |
| 13 | Terminal in browser | **YES** | **SSH Terminal** extension — web-based SSH client. **Requires Plesk 18.0.61+, Unix only.** [ssh-terminal](https://www.plesk.com/extensions/ssh-terminal/) |
| 14 | One-click apps | **PARTIAL** | **WP Toolkit** + **Joomla! Toolkit** bundled; **Sitejet Builder** bundled in *every* edition. No bundled general installer — Softaculous/Installatron third-party paid. |
| 15 | Staging | **YES — best-in-group** | WP Toolkit clone → staging subdomain, plus **Smart Update**: clones the site, applies the update on the clone, analyses for breakage, *then* updates production. Smart Update is a **paid add-on/Deluxe feature**. [KB](https://www.plesk.com/kb/docs/wp-toolkit-smart-updates-2/) |
| 16 | Git integration | **YES** | Bundled — push to a local repo or pull from a remote. |
| 17 | Monitoring / resource | **YES** | Bundled resource reports, log parsing with warnings surfaced in the UI, per-subscription CPU/RAM/Disk-I/O limits. **Advanced Monitoring** extension adds **Grafana**. Plus 360 Monitoring (see #19). |
| 18 | Security / malware / WAF | **YES (WAF) / PARTIAL (malware)** | **ModSecurity WAF active out of the box** + fail2ban. Malware: old ImunifyAV extension **deprecated**, replaced by the unified **Imunify extension** — free tier bundled-available, paid ImunifyAV+/Imunify360. Plus **WP Guardian** + Patchstack-powered Site Vulnerability Scan. [deprecation notice](https://cloudlinux.zendesk.com/hc/en-us/articles/16021838084124) |
| 19 | Multi-server | **YES — two products, the strongest of the commercial three** | **(a) Plesk 360** — cloud dashboard to log into and monitor multiple Plesk servers from one account; includes **360 Monitoring** (CPU/mem/net/disk, uptime, SSL/HTTP status, TTFB, DNS time, full-site crawl). **(b) Plesk Multi Server extension** — true central management node + service nodes, centralised customers/subscriptions, load balancing, WHMCS integration; **paid ~$10/€9 per node/month** on top of Web Pro/Web Host. ⚠️ Multi Server docs are **Onyx-era (17.0/17.5)** — current Obsidian support status **UNVERIFIED**. [plesk-multi-server](https://www.plesk.com/extensions/plesk-multi-server/) |
| 20 | API | **YES — both** | **XML-RPC** (`:8443/enterprise/control/agent.php`, role-scoped) **and REST** (`:8443/api/v2/…`, **OpenAPI 3.0**, in-panel API Reference + Playground). ⚠️ **REST API is administrator-only.** [about-rest-api](https://docs.plesk.com/en-US/obsidian/api-rpc/about-rest-api.79359/) |
| 21 | CLI | **YES** | `plesk` wrapper + utilities in `/usr/local/psa/bin` (Linux) / `%plesk%\admin\bin` (Windows). |
| 22 | Mobile app | **YES — the only official one in the group** | **Plesk Mobile** iOS + Android: multi-server switching, file manager, editor, subscription stats; admin server info/health/services/logs/restart. Needs the Plesk Mobile Center extension per server. [plesk-mobile](https://www.plesk.com/extensions/plesk-mobile/) |
| 23 | AI | **YES — most advanced of the commercial three** | **(a) Elvis Plesky — SHIPPED**, a ChatGPT-powered support AI answering tickets from the KB/docs ([support.plesk.com](https://support.plesk.com/hc/en-us/articles/27070682202007-Introducing-AI-Assitant-Elvis-Plesky) — page returns 403 to automated fetch, **details UNVERIFIED beyond title**). **(b) Plesk AI Copilot — ROADMAP**, natural-language in-panel management, no ship date ([features.plesk.com/c/168](https://features.plesk.com/c/168-plesk-ai-copilot)). **(c) Sitejet AI Website Generator — SHIPPED.** **(d) Nova AI App Builder — roadmap.** **(e) SocialBee** AI social content. |

**Unique:** only Windows-capable panel; 32 languages; extension-catalog architecture (which cuts both ways — the base licence is thinner and key capability sits in paid extensions); Smart Update's clone-test-then-apply is genuinely differentiated.

### 2.3 DirectAdmin

**Positioning:** the lean, fast, cheap panel — the price-driven cPanel alternative. **Buyer = budget-conscious hosts, resellers and VPS owners**; the $5 Personal PLUS tier reaches individuals. Three tiers: Admin → Reseller → User. Commercial, closed source. Linux only (AlmaLinux 8+, Debian 9/10+, Ubuntu 16.04/18.04/20.04+, plus Ubuntu 24 / Debian 13 / RHEL 10 per Pro Pack notes). Min 4 GB RAM + 4 GB swap.

> ⚠️ **Benchmarking trap:** `directadmin.com/features_list.php` is **badly outdated**. The **"Pro Pack" was retired in August 2023 — "all licenses for sale automatically contain all features."** Git manager, Web Terminal, WordPress Manager, Redis and resource throttling are now in **every** licence. Use `docs.directadmin.com` as the authority. [pro-pack overview](https://docs.directadmin.com/getting-started/pro-pack/overview.html)

| # | Capability | Verdict | Detail · source |
|---|---|---|---|
| 1 | Account/reseller mgmt | **YES** | Explicit Admin/Reseller/User with Reseller + User Packages, per-reseller IP allocation, stats, custom nameservers. |
| 2 | Website/vhost creation | **YES** | Domains, subdomains, pointers. Web servers via **CustomBuild**: Apache, NGINX, NGINX+Apache, OpenLiteSpeed, LiteSpeed. |
| 3 | DNS server + records | **YES — real nameserver** | **BIND**. Full record CRUD at admin + user level, MX control, **DNS Clustering** built in. [dns docs](https://docs.directadmin.com/other-hosting-services/dns/maintaining-records.html) |
| 4 | Email — full stack | **YES** | **Exim** + **Dovecot** + **Roundcube**; POP/IMAP, catch-all, forwarders, mailing lists, autoresponders, vacation. Spam: **SpamAssassin or rspamd** + **BlockCracking** + ClamAV. DKIM signing built in. **In-panel DMARC generation UNVERIFIED.** [exim docs](https://docs.directadmin.com/other-hosting-services/exim/configuring-exim.html) |
| 5 | Databases + phpMyAdmin | **YES** | MariaDB 10.11–12.3 / MySQL 8.4; **phpMyAdmin bundled with single-sign-on** from the DA UI. DB Monitor included. [phpmyadmin docs](https://docs.directadmin.com/other-hosting-services/mariadb-mysql/phpmyadmin.html) |
| 6 | FTP accounts | **YES** | Creation, permissions, anonymous FTP. |
| 7 | SSL / Let's Encrypt | **YES** | ACME built in — **checked every 24 h, renews 30 days before expiry**, on-demand provisioning, admin notification on failure. Plus Admin SSL for hostname/service certs. [automatic-ssl docs](https://docs.directadmin.com/webservices/ssl/automatic-ssl-certificates.html) |
| 8 | PHP version + extensions | **YES** | Per-domain **PHP Selector**; versions + extensions built via **CustomBuild 2.0**. |
| 9 | Cron | **YES** | User-level cron under Advanced Tools. |
| 10 | Firewall | **PARTIAL** | **No first-party firewall.** Bundled **Brute Force Monitor (BFM)** watches DA :2222, Apache (xmlrpc/wp-login), Dovecot, Exim, FTP, SSH, webmail, phpMyAdmin — but **BFM detects and cannot block by itself**. **CSF is third-party**, though **directly integrated since DA 1.61.0** with a limited reseller UI. [BFM](https://docs.directadmin.com/directadmin/general-usage/securing-with-bfm.html) · [CSF](https://docs.directadmin.com/operation-system-level/securing/csf.html) |
| 11 | Backups + offsite | **PARTIAL — the clear weak point** | Admin Backup/Transfer + per-user Site Backup with selective restore. **Remote destinations: FTP only.** Vendor doc is explicit: *"the only one option is available for remote backups out of the box — transferring to remote FTP server."* **No native S3, SFTP or cloud storage** — requires script modification or third-party **JetBackup** / **Acronis** (separately licensed). [backup-to-remote](https://docs.directadmin.com/directadmin/backup-restore-migration/backup-to-remote.html) |
| 12 | File manager | **YES** | Bundled; Evolution skin adds drag-and-drop, inline editing, permissions. |
| 13 | Terminal in browser | **YES** | **Web Terminal** — interactive login shell, Connect/Disconnect states. Formerly Pro Pack, **now in all licences**. [web-terminal](https://docs.directadmin.com/other-hosting-services/web-terminal/general.html) |
| 14 | One-click apps | **PARTIAL** | **No bundled general installer.** Native **WordPress Manager** (needs `wp-cli`) — WordPress only. Softaculous / Installatron are third-party paid. |
| 15 | Staging | **NO (native)** | No native staging/clone found in DA docs. Achieved via **Softaculous "Create Staging"** (third-party paid). Still an open [feature request](https://forum.directadmin.com/threads/wordpress-staging-site-option.82218/). |
| 16 | Git integration | **YES** | **Git Manager** — local bare repos or remote sync (any git protocol; SSH for private repos). **Webhooks trigger automated fetch + deploy.** Now in all licences. [git docs](https://docs.directadmin.com/other-hosting-services/git/general.html) |
| 17 | Monitoring / resource | **YES** | Webalizer default, AWStats optional (**global on/off, not per-domain** — a real limitation); usage stats at all three tiers; **per-user resource throttling (CPU/RAM/IO)**; DB Monitor; service stop/start/restart. |
| 18 | Security / malware / WAF | **PARTIAL** | **Bundled:** ClamAV filesystem scanning, BFM, 2FA, automatic `security.txt`. **WAF not first-party** — ModSecurity via CustomBuild. Malware: ImunifyAV free / ImunifyAV+ / Imunify360 paid, or **cPGuard** (third-party paid). |
| 19 | Multi-server | **PARTIAL — more native than cPanel** | **Multi-Server Setup** does DNS clustering **and** a cross-server view: the user list gains a column showing which box each account is on, click-through opens that server's page. **Not a true single-pane console** (no central provisioning or load balancing). [multi-server-setup](https://docs.directadmin.com/directadmin/general-usage/multi-server-setup.html) |
| 20 | API | **YES — arguably the cleanest of the three** | Modern **JSON REST** (`/api/…`) + legacy `/CMD_API_…`. Auth: HTTP Basic, session cookies, **Login Keys** (restricted by action + IP), user impersonation. *"All the actions available in the DirectAdmin GUI interface can be also performed using API access."* **Publishes OpenAPI 2.0 at `/static/swagger.json` on every server.** [api docs](https://docs.directadmin.com/developer/api/) |
| 21 | CLI | **YES** | The **`da` binary** — admin, admin-backup, api-url, build, config/get/set, info, install, license, login-url, permissions, server, suspend-*, taskq, update. Plus CustomBuild. |
| 22 | Mobile app | **NO (official)** | Third-party only: "DA for iPhone & iPad" (EvanheckCreations, iOS+Android), WebAdmin Mobile (Android). |
| 23 | AI | **NO (first-party)** | **No official AI features as of 2026; no published AI roadmap.** Third-party only: an "AI Website Builder" plugin on DA's own plugins page, **CyberIA** (third-party natural-language/voice layer over the DA API), and a community DA AI agent (~100 tools) in development. [extras-plugins](https://www.directadmin.com/extras-plugins.php) · [forum](https://forum.directadmin.com/threads/developing-an-ai-agent-for-da-my-journey-100-tools-and-scalability-challenges.81764/) |

**Unique:** price; **an OpenAPI spec shipped on every server** — the most automation-friendly API here; **no feature-tier upsell at all** since the Pro Pack retirement. Weakest at backups (FTP-only remote) and staging (none native); zero first-party AI.

### 2.4 CyberPanel

**Positioning:** free OpenLiteSpeed-based panel giving cPanel-class features (email, DNS, resellers) at $0. **Buyer = budget hosts, WordPress agencies, self-hosters** who need a *full* stack, not a lightweight one. **License: GPL-3.0** ([GitHub](https://github.com/usmannasir/cyberpanel)). Web server: OpenLiteSpeed free, or LiteSpeed Enterprise (commercial licence sold by LiteSpeedTech, **not** by CyberPanel — price **UNVERIFIED**). OS: Ubuntu 24.04/22.04/20.04, AlmaLinux 8–10, Rocky 8/9, RHEL 8/9, CloudLinux 8, CentOS 9. Stack: PowerDNS · Postfix + Dovecot · SnappyMail · Pure-FTPd · MariaDB + phpMyAdmin · ModSecurity.

| # | Capability | Verdict | Detail · source |
|---|---|---|---|
| 1 | Accounts/reseller | **YES** | admin / **reseller** / user ACL presets + custom ACLs. [KB](https://cyberpanel.net/KnowledgeBase/home/acl-management/) |
| 2 | Website/vhost | **YES** | Unlimited domains + subdomains. |
| 3 | DNS | **YES — real nameserver** | **PowerDNS** bundled, DNSSEC. |
| 4 | Email — full stack | **YES** | Postfix + Dovecot + **SnappyMail** + Rspamd; DKIM manager in UI. *SPF/DMARC auto-generation **UNVERIFIED***. Note the **Rspamd Manager UI is a PAID add-on**. |
| 5 | DB + phpMyAdmin | **YES** | MariaDB + phpMyAdmin bundled. |
| 6 | FTP | **YES** | Pure-FTPd. |
| 7 | SSL / Let's Encrypt | **YES** | One-click LE + auto-renew. Enhanced **"SSL V2" (wildcard, DNS verification) is a PAID add-on**. |
| 8 | PHP per site + extensions | **YES** | PHP 7.4 / 8.0–8.5 per site + extension manager. |
| 9 | Cron | **YES** | Bundled. |
| 10 | Firewall | **YES** | FirewallD **+ CSF** integration. |
| 11 | Backups + offsite | **YES** | Local, SFTP, **S3**, **Google Drive**. **Incremental "Backup V2" (rustic + rclone) is a PAID add-on.** [KB](https://cyberpanel.net/KnowledgeBase/home/backup-v2-in-cyberpanel/) |
| 12 | File manager | **YES** | Bundled; **Root File Manager = PAID add-on**. |
| 13 | Terminal in browser | **YES** | SSH Manager / web terminal. |
| 14 | One-click apps | **YES** | WordPress, Joomla, PrestaShop, Magento + **Docker Manager** and n8n deploy. |
| 15 | Staging | **YES** | WordPress staging + cloning; full **WordPress Manager Pro = PAID add-on**. |
| 16 | Git | **YES** | Git Manager — GitHub/GitLab repos + webhook deploys. |
| 17 | Monitoring | **PARTIAL** | Dashboard CPU/RAM/disk + per-website resource usage; no historical graphing or alerting depth. |
| 18 | Security / malware / WAF | **YES bundled + paid tiers** | **ModSecurity WAF bundled**, fail2ban, CSF. ImunifyAV free / Imunify360 paid (third-party). |
| 19 | Multi-server | **PARTIAL** | "CyberPanel Cloud" HA clusters (≥2 instances, Docker-backed) — **clustering, not a unified multi-server admin console**. [community](https://community.cyberpanel.net/t/1-setting-up-highly-available-cluster-from-cloud-platform/158) |
| 20 | API | **YES** | Per-user API access toggle; docs at go.cyberpanel.net/API. *Full REST-ness / endpoint list **UNVERIFIED***. [KB](https://cyberpanel.net/KnowledgeBase/home/cyberpanel-api/) |
| 21 | CLI | **YES** | `cyberpanel` — createWebsite, issueSSL, createDatabase, listWebsitesJson… *(this is exactly the surface ServerAlly's H1 work drives over SSH.)* |
| 22 | Mobile app | **NO** | No official app; third-party web wrappers only. |
| 23 | AI | **YES — real, and PAID PER SCAN** | **AI WordPress Scanner**: vulnerabilities, malware, backdoors, SEO spam, zero-days, with plain-English severity + AI remediation steps. **Pay-per-scan**; free limited scans for VPS customers of participating providers. **Model/LLM not disclosed.** [AIScannerDocs.md](https://github.com/usmannasir/cyberpanel/blob/stable/guides/AIScannerDocs.md) · [ai-wordpress-scanner](https://cyberpanel.net/ai-wordpress-scanner) |

### 2.5 HestiaCP

**Positioning:** the clean, actively-maintained VestaCP fork — genuinely free, full-featured shared-hosting panel with the **strongest mail stack in the group**. **Buyer = self-hosters and small hosts** wanting cPanel parity at zero cost with no upsell. **License: GPLv3.** Web server: **NGINX + Apache2** (nginx as reverse proxy/cache) with PHP-FPM; nginx-only supported. OS: Debian 12/11, Ubuntu 24.04/22.04 LTS, 64-bit only. Stack: BIND · Exim + Dovecot + SpamAssassin + ClamAV + Sieve · Roundcube (+ optional SnappyMail) · MariaDB/MySQL 8/PostgreSQL · vsftpd/ProFTPD · iptables + ipset + fail2ban.

| # | Capability | Verdict | Detail · source |
|---|---|---|---|
| 1 | Accounts/reseller | **PARTIAL** | Multi-user + hosting **packages** with per-user resource limits = yes. **Reseller tier NOT native** — devs: *"would need some basic rewrites of the hestia cli infrastructure… there isnt a release date."* A third-party reseller plugin entered public testing June 2026. [forum](https://forum.hestiacp.com/t/reseller-accounts-support/282) |
| 2 | Website/vhost | **YES** | Web domains + MultiIP for Web/Mail/DNS. |
| 3 | DNS | **YES — real nameserver** | **BIND**; create your own nameservers, **DNS clustering**, **DNSSEC**. [features](https://hestiacp.com/features) |
| 4 | Email — full stack | **YES — strongest in group** | Exim + Dovecot, **Roundcube** + optional SnappyMail, **SpamAssassin**, **ClamAV**, Sieve, DKIM, per-domain TLS, **Let's Encrypt for mail domains**, SMTP relay, per-user rate limits. |
| 5 | DB + phpMyAdmin | **YES** | MariaDB/MySQL 8 **and PostgreSQL**; **phpMyAdmin + phpPgAdmin** bundled. |
| 6 | FTP | **YES** | vsftpd/ProFTPD + SFTP & SSH chroot jails. |
| 7 | SSL / Let's Encrypt | **YES** | Auto-issue + auto-renew, per-domain, also for mail domains. |
| 8 | PHP per site + extensions | **YES / partial** | PHP 5.6 → 8.4 per domain (8.3 default in 1.9.x). *Per-version extension management via UI **UNVERIFIED***. |
| 9 | Cron | **YES** | Documented. |
| 10 | Firewall | **YES** | iptables + ipset + **fail2ban** + brute-force detection. |
| 11 | Backups + offsite | **YES** | Local `/backup`, **FTP**, **SFTP**, and **Rclone → 50+ cloud providers** (B2, R2 etc.). [backup docs](https://hestiacp.com/docs/server-administration/backup-restore.html) |
| 12 | File manager | **YES — bundled, free** | *"In a new install, the file manager will be enabled by default."* [docs](https://hestiacp.com/docs/server-administration/file-manager.html) |
| 13 | Terminal in browser | **YES** | Web Terminal via Plugins (`v-add-web-terminal`). Some install-specific breakage reported. [issue #4757](https://github.com/hestiacp/hestiacp/issues/4757) |
| 14 | One-click apps | **YES** | Quick Install Apps: **WordPress, Drupal, Laravel, NextCloud, Joomla** + others. |
| 15 | Staging | **NO** | Not in docs or feature page. |
| 16 | Git | **NO** | Not in docs or feature page. |
| 17 | Monitoring | **PARTIAL** | Per-domain web stats + server stats; no alerting/graphing suite. |
| 18 | Security / malware / WAF | **PARTIAL — weakest here** | fail2ban, brute-force protection, 2FA, ClamAV (**mail scanning only**). **No bundled ModSecurity/WAF, no site malware scanner.** |
| 19 | Multi-server | **PARTIAL** | **DNS clustering only** — no unified console. |
| 20 | API | **YES — REST** | Documented "Rest API" section. [docs](https://hestiacp.com/docs/) |
| 21 | CLI | **YES — best-in-class** | `v-add-*`, `v-delete-*`, `v-change-*`, `v-list-*`, `v-check-*` — **300+ commands**; effectively every panel function is scriptable. [CLI ref](https://hestiacp.com/docs/reference/cli) |
| 22 | Mobile app | **NO** | None found. |
| 23 | AI | **NO** | No AI/LLM feature in docs or feature page. |

**Cost:** 100% free, GPLv3, no paid tier, no add-on store. Ships a **cPanel/DirectAdmin importer** since 1.9 — i.e. it is explicitly built to receive migrations. Latest stable ~1.9.7.

### 2.6 aaPanel

**Positioning:** the international edition of China's dominant panel — app-store-driven, plugin-everything, the broadest feature surface of the free panels. **Buyer = devs/hosts** wanting a huge one-click catalogue and comfortable with a freemium plugin model.

> **Chinese origin, explicitly:** aaPanel is the international version of **BaoTa / 宝塔 (bt.cn)**, developed in China since 2014. The official iOS app's App Store seller is **"Guangdong Baota Safety Technology Co., Ltd." (广东堡塔安全技术有限公司)**. [aaPanel forum](https://www.aapanel.com/forum/d/7-who-is-aapanel) · [App Store](https://apps.apple.com/us/app/aapanel/id1558006442)

**License: UNVERIFIED.** The GitHub repo references a `license.txt` whose contents were not retrievable; third-party aggregators claim MIT, which could **not** be confirmed against the vendor's own repo. Pro plugins are unambiguously proprietary/commercial. Web server: NGINX or Apache (LNMP/LAMP one-click). OS: Ubuntu 22.04/24.04, Debian 11/12, CentOS 9, Rocky/AlmaLinux 8/9, plus OpenEuler per vendor site.

| # | Capability | Verdict | Detail · source |
|---|---|---|---|
| 1 | Accounts/reseller | **PARTIAL — PAID** | "Multi-user accounts / shared hosting" is **Pro-only**. True reseller tier **UNVERIFIED**. |
| 2 | Website/vhost | **YES** | Unlimited website creation on the free tier. |
| 3 | DNS | **PARTIAL — plugin** | "aaPanelDns" / DNS Manager plugin runs a self-hosted DNS server (port 53), SOA + NS records. Not core; **daemon UNVERIFIED**. [docs](https://www.aapanel.com/docs/Function/Tutorial/build_dns_server.html) |
| 4 | Email | **YES** | Mail Server: SMTP/IMAP + spam protection. DKIM/SPF/DMARC handling **partially UNVERIFIED**. Bulk email sending = **Pro**. |
| 5 | DB + phpMyAdmin | **YES** | MySQL management + phpMyAdmin (port 888). |
| 6 | FTP | **YES** | Free tier. |
| 7 | SSL / Let's Encrypt | **YES** | One-click SSL deployment. |
| 8 | PHP per site + extensions | **YES** | Multi-version PHP + per-version extension installer — a genuine strength. |
| 9 | Cron | **YES** | Scheduled tasks. |
| 10 | Firewall | **YES** | System firewall extension + **Nginx WAF**. |
| 11 | Backups + offsite | **YES — via plugins, some paid** | Local + FTP Storage, **Google Drive**, Dropbox, S3, OneDrive. *Free/paid split per plugin **UNVERIFIED***. |
| 12 | File manager | **YES** | With built-in code editor. |
| 13 | Terminal in browser | **YES** | **aaTerm** — terminal **plus RDP access**. |
| 14 | One-click apps | **YES — largest catalogue in the group** | App Store one-click LNMP/LAMP + **Docker Manager with 200+ apps** + WP Toolkit. |
| 15 | Staging | **PARTIAL** | WP Toolkit does backup/**cloning**; a true staging→production workflow **UNVERIFIED**. |
| 16 | Git | **YES** | Git-based deployment. |
| 17 | Monitoring | **YES** | CPU, RAM, network, disk/network IO; website analytics = **Pro**. |
| 18 | Security / malware / WAF | **YES basic + PAID advanced** | Free Nginx WAF + SSH login alerts + system firewall. **Advanced WAF = Pro**; a standalone paid Nginx WAF plugin has sold at ~$9.50–$18.90. File protection & tamper-proofing = Pro. |
| 19 | Multi-server | **UNVERIFIED** | "aaCloud" appears in site nav; scope not confirmed. |
| 20 | API | **PARTIAL — not REST** | Custom single-endpoint API; auth = `request_time` + MD5(timestamp + hashed API key) + **IP whitelist**. Docs self-described as *"unfinished"* — only Website-PHP and MySQL categories documented. [API docs](https://www.aapanel.com/docs/api/api-list.html) |
| 21 | CLI | **YES** | `bt` command. |
| 22 | Mobile app | **YES — official iOS** | App Store app (iOS/iPadOS/macOS/visionOS/watchOS): sites, FTP, DB, files, SSH, firewall, monitoring, SSL, backups. **Android not listed there — UNVERIFIED.** |
| 23 | AI | **YES — and the most directly competitive with ServerAlly** | **(a) aaPanel AI Assistant** plugin: chat-based diagnostics (nginx/MySQL errors), performance analysis, security scanning + conversational audit reports; **you connect your own AI provider via API key**; granular permissions over System/Network/Databases. **(b) An official aaPanel MCP Server (Go)** exposing panel functions to any MCP-compatible AI. Free-vs-Pro tier for the assistant **UNVERIFIED**. [aapanel.com/new/feature/ai.html](https://www.aapanel.com/new/feature/ai.html) |

**Community-raised concerns (reported, not vendor-confirmed):** the BaoTa/China linkage and data-jurisdiction questions; alleged "phoning home" with no documented way to fully disable telemetry; no independent security audit; a CVE history including authenticated RCE via the cron "Script Content" box through v6.6.6. ([LowEndTalk](https://lowendtalk.com/discussion/178921/opinions-on-aapanel) · [CVE Details](https://www.cvedetails.com/vendor/23472/Aapanel.html) · [GitHub issue #74](https://github.com/aaPanel/aaPanel/issues/74)) **No specific telemetry endpoint or data-collection claim could be verified from vendor documentation — treat as reported concern, not established fact.**

### 2.7 CloudPanel

**Positioning:** deliberately minimal, performance-first NGINX panel for **cloud VPS app hosting** (WordPress/Laravel/Magento/Node/Python). **Buyer = developers and agencies running their own apps on AWS/Hetzner/DO — explicitly not shared-hosting operators.** Made by **MGT-COMMERCE GmbH**, Berlin.

> ⚠️ **License correction — CloudPanel is PROPRIETARY, free-of-charge, NOT open source.** *"The Software is licensed and not sold."* It bundles GPL components but CloudPanel itself is proprietary, and **reselling or hosting-for-third-parties is forbidden without written MGT-COMMERCE permission**; MGT-COMMERCE *"may, in the case of a Software license provided free of charge, at all times amend these Terms."* Several third-party sites incorrectly call it open source. [license terms](https://www.cloudpanel.io/license-terms/)

Web server: **NGINX only.** OS: Debian 12/11, Ubuntu 24.04/22.04 LTS — **x86 and ARM64**.

| # | Capability | Verdict | Detail · source |
|---|---|---|---|
| 1 | Accounts/reseller | **PARTIAL — RBAC, no reseller** | Admin / Site Manager / User roles. Access control, **not** a reseller or billing tier. [docs](https://www.cloudpanel.io/docs/v2/admin-area/users/) |
| 2 | Website/vhost | **YES** | Isolated PHP / Node.js / Python / static sites; 30+ vhost templates. |
| 3 | DNS | **NO** | No DNS server, no BIND integration, no zone editor, no record management — absent from the docs TOC entirely. |
| 4 | Email | **NO — confirmed by vendor** | *"CloudPanel doesn't provide E-Mail because of performance. We want to keep it clean and lightweight."* Recommends Google Workspace / Zoho / Amazon WorkMail / self-hosted Mailcow. No mailboxes, IMAP, webmail or SMTP relay. [docs](https://www.cloudpanel.io/docs/v2/frontend-area/e-mail/) |
| 5 | DB + phpMyAdmin | **YES** | MySQL/MariaDB + **phpMyAdmin**. PostgreSQL **UNVERIFIED**. |
| 6 | FTP | **YES** | FTP users + firewall rules for ports 20-21 and passive range; plus SFTP/SSH. |
| 7 | SSL / Let's Encrypt | **YES** | Free Let's Encrypt certs. |
| 8 | PHP per site + extensions | **YES / partial** | Multiple versions, one-click switching, PHP-FPM parameter config. *Per-version extension management via UI **UNVERIFIED***. |
| 9 | Cron | **YES** | Dedicated section. |
| 10 | Firewall | **YES** | Built-in rule management (ufw-based). |
| 11 | Backups + offsite | **YES remote-first, but ⚠️ restore is manual** | **Rclone**-powered: S3, Wasabi, DO Spaces, Dropbox, Google Drive, Hetzner Storage Box, SFTP, or any Rclone provider. Nightly local DB dumps. **Restore requires downloading `backup.tar` and extracting via File Manager (<2 GB) or SFTP/SSH (>2 GB) — no one-click restore.** [docs](https://www.cloudpanel.io/docs/v2/admin-area/backups/) |
| 12 | File manager | **YES** | Dedicated section. |
| 13 | Terminal in browser | **NO / UNVERIFIED** | Not in the docs TOC; access is via SSH. |
| 14 | One-click apps | **YES** | One-click **WordPress** + 20+ documented app guides (Laravel, Symfony, Drupal, Magento…) and 30+ vhost templates. |
| 15 | Staging | **PARTIAL** | Only indirectly — **Basic Authentication** is documented as a way to gate "test/staging environments". No clone/push workflow in core. |
| 16 | Git | **NO (in core)** | Git/"DPLOY" deployment appears in CloudPanel blog/marketing content but is **not a core panel feature in the docs TOC**. Treat as **not bundled — UNVERIFIED as a panel feature**. |
| 17 | Monitoring | **PARTIAL** | Events + Logs sections; CPU/RAM/bandwidth/uptime cited in vendor blog. No alerting suite documented. |
| 18 | Security / malware / WAF | **PARTIAL — no WAF** | Built-in IP blocking, **bot blocking by name**, Basic Auth, Cloudflare-only traffic. **No ModSecurity by default** — must be installed manually as an nginx module. **No malware scanner.** [docs](https://www.cloudpanel.io/docs/v2/frontend-area/security/) |
| 19 | Multi-server | **NO** | Single-server panel; per-cloud install guides (AWS, DO, Hetzner, GCE, Azure, Oracle, Vultr) but no central console. |
| 20 | API | **NO** | **No official REST API.** Open community requests: ["Add Official REST API Support"](https://feature-requests.cloudpanel.io/posts/447/request-add-official-rest-api-support-for-cloudpanel), ["Panel rest API"](https://feature-requests.cloudpanel.io/posts/286/panel-rest-api). Automation = CLI only. |
| 21 | CLI | **YES** | **`clpctl`** — backups, DB import/export, password resets, permission resets, security config. |
| 22 | Mobile app | **NO** | None found. |
| 23 | AI | **NO** | No AI/LLM feature documented. |

### 2.11 Cross-panel comparison

| | cPanel | Plesk | DirectAdmin | CyberPanel | HestiaCP | aaPanel | CloudPanel |
|---|---|---|---|---|---|---|---|
| License | commercial | commercial | commercial | GPL-3.0 | GPLv3 | **UNVERIFIED** | **proprietary, free** |
| Windows | ❌ | ✅ (only one) | ❌ | ❌ | ❌ | ❌ | ❌ |
| Real DNS server | ✅ PowerDNS/BIND | ✅ BIND/MS DNS | ✅ BIND | ✅ PowerDNS | ✅ BIND | ⚠️ plugin | ❌ **none** |
| Full mail stack | ✅ | ✅ | ✅ | ✅ | ✅ strongest | ✅ | ❌ **none, by design** |
| Reseller tier | ✅ | ✅ | ✅ | ✅ | ❌ plugin only | ⚠️ Pro | ❌ RBAC only |
| Native firewall mgr | ❌ CSF 3rd-party | ✅ bundled | ❌ CSF 3rd-party | ✅ FirewallD+CSF | ✅ iptables | ✅ | ✅ ufw |
| Remote backup targets | **10** (S3/B2/GDrive/SFTP/rsync/WebDAV…) | S3/GDrive/OneDrive+ | ⚠️ **FTP only** | S3/GDrive/SFTP | Rclone → 50+ | plugins | Rclone (⚠️ manual restore) |
| Bundled WAF | ✅ ModSecurity | ✅ ModSecurity | ❌ via CustomBuild | ✅ ModSecurity | ❌ | ✅ Nginx WAF | ❌ |
| Bundled malware scan | ❌ | ⚠️ Imunify free tier | ❌ | ⚠️ ImunifyAV | ❌ | ⚠️ Pro | ❌ |
| General app installer | ❌ 3rd-party | ❌ 3rd-party | ❌ 3rd-party | ✅ | ✅ | ✅ 200+ | ⚠️ WP only |
| Staging | WP only | ✅ **Smart Update** | ❌ | ✅ (Pro add-on) | ❌ | ⚠️ | ⚠️ |
| Git | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| Multi-server | ❌ DNS cluster only | ✅ **360 + Multi Server** | ⚠️ DNS + cross-view | ⚠️ HA cluster | ⚠️ DNS cluster | UNVERIFIED | ❌ |
| API | ✅ UAPI/WHM | ✅ XML-RPC + REST (admin-only) | ✅ **REST + OpenAPI per server** | ✅ | ✅ REST | ⚠️ non-REST, "unfinished" | ❌ **none** |
| CLI | ✅ | ✅ | ✅ `da` | ✅ `cyberpanel` | ✅ **300+ `v-*`** | ✅ `bt` | ✅ `clpctl` |
| Mobile app | ❌ | ✅ **Plesk Mobile** | ❌ 3rd-party | ❌ | ✅ iOS | ❌ | ❌ |
| **First-party AI** | ⚠️ roadmap (+MCP) | ✅ **Elvis shipped**, Copilot roadmap | ❌ **none** | ✅ paid WP scanner | ❌ | ✅ **assistant + MCP server** | ❌ |
| Paid tier | $29.99–$69.99/mo | ~$16.99–$62.99/mo | $5–$29/mo | $59/yr add-ons | none | $198/yr–$699 | none |

**Universally third-party and separately licensed across the commercial three:** Softaculous, Installatron, Imunify360/ImunifyAV+, JetBackup, Acronis, CloudLinux, LiteSpeed, ConfigServer CSF. **None of cPanel, Plesk or DirectAdmin bundles a general-purpose app installer or a real malware scanner.**

---

## 3. PRICING IN DETAIL

### 3.1 cPanel/WHM — the price-increase story

**Current retail (cpanel.net, fetched 2026-07-25):** source — <https://cpanel.net/pricing/>

| Tier | Accounts | Monthly | Annual (per mo) | Environment |
|---|---|---|---|---|
| Solo | 1 | **$29.99** | $27.46 | Cloud/VPS only |
| Admin | up to 5 | **$35.99** | $32.96 | Cloud/VPS only |
| Pro | up to 30 | **$53.99** | $49.46 | Cloud/VPS only |
| Premier | up to 100 | **$69.99** | monthly only | Cloud/VPS **and** Metal/Dedicated |
| — overage | >100 | **+$0.49 / account / mo** | | |
| WP Squared | 10 WordPress sites | **$84.99** | | +$0.40 per extra site |

All tiers include WP Toolkit, Website Builder, email accounts, unlimited websites, SSL, self-guided migration, website monitoring. Premier adds custom branding. WP Squared bundles AccelerateWP, CloudLinux Max Cache, Patchstack, Imunify360, Extendify AI, WHMCS integration, staging/cloning. (<https://cpanel.net/pricing/>)

**Price history.** Pre-2019 cPanel was a flat ~$20/month for *unlimited* accounts ([ServerPoint](https://www.serverpoint.com/en/articles/cpanel-price-increases-since-acquisition/)). In **June 2019**, after the Oakley Capital acquisition, cPanel switched to per-account tiering — the event that started the exodus. Documented increases took effect **1 Sept 2019, 1 Jan 2021, 1 Jan 2022 and 1 Jan 2023** ([Brontobytes](https://www.brontobytes.com/blog/new-prices-for-cpanel-licenses/)).

Premier (100 accounts) tier, the best-documented line ([ColossusCloud](https://www.colossuscloud.com/en/articles/cpanel-pricing-increases-oakley-capital/)):

| Period | Premier /mo | Change |
|---|---|---|
| Jun 2019 – Dec 2020 | $45.00 | (restructure) |
| Jan 2021 – Nov 2021 | $48.50 | +7.8% |
| Dec 2021 – Nov 2022 | $53.99 | +11.3% |
| Dec 2022 – Nov 2023 | $59.99 | +11.1% |
| Dec 2023 – Feb 2024 | $60.99 | +1.7% |
| 2025 | $65.99 | +8.2% |
| 2026 | **$69.99** | +6.1% |

2026 retail increases across the board: Solo $26.99→$29.99, Admin $32.99→$35.99, Pro $46.99→$53.99, Premier $65.99→$69.99, overage $0.45→$0.49 ([DEV/HostingSeekers](https://dev.to/hostingseekers/preparing-for-2026-what-the-cpanel-plesk-whmcs-price-hikes-mean-for-you-54ek); consistent with [ColossusCloud](https://www.colossuscloud.com/en/articles/cpanel-pricing-increases-oakley-capital/)).

**Cumulative effect (ServerPoint's worked examples):** a 200-account dedicated server went from ~$20/mo pre-2019 to $118.99/mo in 2026 (≈**+495%**); a 500-account reseller from ~$20 to $265.99/mo (≈**+1,200%**). Source: <https://www.serverpoint.com/en/articles/cpanel-price-increases-since-acquisition/>

> ⚠️ **Critical nuance — retail ≠ what hosts actually pay.** Hosting companies with a PartnerNOC bundling agreement pay far less. 2025→2026 NOC prices: Solo $16.00→$18.00, Admin Cloud $19.75→$21.00, Pro Cloud $27.25→$32.00, Plus Cloud (50) $39.25→$42.00, Premier $47.00→$49.50, overage $0.30→$0.35 ([bacloud](https://www.bacloud.com/en/blog/219/cpanel-noc-license-costs-keep-rising-a-20252026-price-comparison-for-hosting-providers.html)). A second hosting provider's customer announcement lists near-identical figures with an effective date of **1 January 2026** ([H4Y](https://h4y.us/my/announcements/14/2026-cPanel-Plesk-and-WHMCS-license-cost-increases.html)). Note H4Y also shows a **"Plus Cloud" 50-account tier that does not appear on the public retail page** — a partner-only SKU.
>
> **Implication for ServerAlly:** when a hosting company says "cPanel costs us $49.50/server for 100 accounts", that is ~$0.50/account/month. Any per-server ServerAlly price is competing against that number, not against $69.99.

### 3.2 Plesk

Owned by **WebPros**, the same group that owns cPanel and WHMCS — a fact hosting operators cite as the reason they will *not* treat Plesk as an escape route (see §4).

**Editions gate on DOMAINS, not accounts** (a materially different metric from cPanel): Web Admin = 10 domains, Web Pro = 30 domains, Web Host = unlimited. Plesk states there is **no feature difference between VPS and dedicated licences** — only the operating environment differs. (<https://www.plesk.com/pricing/>)

**Feature deltas between editions** are small: all three include Sitejet Builder, subscription/account management, PostgreSQL & MSSQL modules and reseller management; **Web Admin gets "WP Toolkit SE" while Pro and Host get the full WP Toolkit** (<https://www.plesk.com/pricing/>).

**Prices — reported honestly, because the vendor page resisted clean extraction.** plesk.com/pricing renders in EUR with a VPS/Dedicated toggle crossed with a Monthly/Yearly toggle; three separate automated reads of the page returned mutually inconsistent axis labels (one pass reported yearly *dearer* than monthly, which cannot be right). **The EUR figures present on the page are 6.60 / 9.90 / 16.50 and 12.04 / 18.29 / 31.38 per month for Web Admin / Web Pro / Web Host respectively — but which set belongs to VPS-yearly vs Dedicated is UNVERIFIED.** Do not quote the EUR numbers without re-checking the live page in a browser.

**USD figures are solid** — two independent sources agree exactly:

| Edition | Domains | 2025 | 2026 |
|---|---|---|---|
| Web Admin | 10 | $15.00 | **$16.99** |
| Web Pro | 30 | $26.00 | **$29.99** |
| Web Host (cloud/VPS) | unlimited | $48.00 | **$62.99** (+31%) |
| Web Host (bare metal) | unlimited | $65.50 | **$69.99** |

Sources: [H4Y announcement](https://h4y.us/my/announcements/14/2026-cPanel-Plesk-and-WHMCS-license-cost-increases.html) (effective 1 Jan 2026) and [CostBench, verified 2026-07-19](https://costbench.com/software/cloud-infrastructure/plesk/).

**2026 increase ≈ 26% on average across all editions**, effective 1 January 2026, applied to both monthly renewals and existing annual plans — and **annual plans are being phased out** ([webhosting.today, 2026-05-20](https://webhosting.today/2026/05/20/plesk-obsidian-18-0-77-ships-pricing-up-26-percent-ai-copilot-extension-coming/); [webhosting.today, 2025-10-16](https://webhosting.today/2025/10/16/plesk-announces-price-and-billing-model-changes-effective-january-2026/)). WebPros also raised the **surcharge for servers running EOL operating systems** (CentOS 6/7, CloudLinux 6/7). The pricing page itself carries the notice: *"effective January 1, 2026, license subscriptions will be subject to a revised pricing structure."*

A 2025 user complaint quoted by CostBench: *"They increased their pricing for Plesk Web Pro Edition already with 45% for January 2025 and Web Host Edition even more than 50%."*

**Partner/Business plans:** minimum commitment €250/$250 per month, discounts up to 45%, includes all editions + extensions + Sitejet + 24/7 priority support + dedicated account manager (<https://www.plesk.com/pricing/>). **14-day free trial, no card required** ([CostBench](https://costbench.com/software/cloud-infrastructure/plesk/)).

**Ecosystem note — WHMCS also went up in 2026** (same owner): Starter $15.95 (unchanged), Plus $24.99→$30.00, Professional $45.00→$50.00, Business 1000 $60.00→$80.00 (+33%) ([H4Y](https://h4y.us/my/announcements/14/2026-cPanel-Plesk-and-WHMCS-license-cost-increases.html)). Relevant to ServerAlly because ServerAlly's own billing rides on FireVPS's WHMCS.

### 3.3 DirectAdmin — the price escape valve

Retail (<https://directadmin.com/pricing.php>, fetched 2026-07-25):

| Tier | Accounts | Domains | Monthly |
|---|---|---|---|
| Personal PLUS | 2 | 20 | **$5** |
| Lite | 10 | 50 | **$15** |
| Standard | **Unlimited** | **Unlimited** | **$29** |

Annual pricing is not published on that page. All tiers carry "protection against price increases" and automatic updates — **an explicit, marketed contrast with cPanel's annual hikes.** Bulk discounts: automatic 15% after 4 Standard-equivalent licences, scaling to 40% at 35+; requires prepaid balance; above ~20 licences, custom sales pricing. Trade press reports an effective bulk/OEM rate near **$2/month per licence** at volume ([ispmanager](https://www.ispmanager.com/blog/cpanel-vs-directadmin-2026), 2025-11-20) and a **60-day free trial** ([DEV](https://dev.to/hugovalters/directadmin-in-2025-the-lightweight-alternative-to-cpanel-and-plesk-1jii)) — the 60-day trial is **UNVERIFIED against directadmin.com itself**.

**The killer line: $29/month buys unlimited accounts and unlimited domains.** The equivalent cPanel bill for 500 accounts is $265.99/month. That single ratio is the engine of the whole migration story in §4.

DirectAdmin lists third-party add-ons rather than bundling them: Acronis Backup from $3/mo (30-day trial), JetBackup from $8.95/mo (10-day trial), Imunify360 from $12/mo (14-day trial) — ordered from and supported by the respective vendors (<https://directadmin.com/pricing.php>).

### 3.4 CyberPanel

**Core is free forever and open source** — "unlimited websites, free SSL, email, DNS, and backups included" (<https://cyberpanel.net/>). Free core covers website management, email server, DNS, PHP, basic SSL, file manager, database tools, Docker, FTP, basic firewall, WordPress install, OpenLiteSpeed (<https://cyberpanel.net/cyberpanel-addons>).

Paid add-ons (<https://cyberpanel.net/cyberpanel-addons>):

| Product | Price |
|---|---|
| Add-ons bundle (SSL V2, WordPress Manager Pro, Backup V2, Email Debugger, Root File Manager, Rspamd Manager) | **$59/yr** or **$169 lifetime** (listed at 25% off → $126.75) |
| .htaccess Module (Apache .htaccess compatibility for OpenLiteSpeed) | **$59/yr** or **$199 lifetime** |
| Bundle of both | **$99/yr** |

Note what the add-ons reveal: **incremental backups, scheduled/remote backups, one-click restore, WordPress staging/cloning, wildcard SSL automation and modern spam filtering are all *paid* upgrades** in CyberPanel. The free tier's backup and SSL are the basic versions. This is a useful precedent — CyberPanel monetises exactly the "second-order" reliability features, not the baseline.

### 3.5 aaPanel

International edition of the Chinese **BaoTa (宝塔)** panel. Freemium (<https://www.aapanel.com/new/pricing.html>):

| Tier | Price |
|---|---|
| Free | **$0 forever** — unlimited websites, website/database/FTP/Docker management, unlimited SSL, 100+ apps |
| Pro monthly | **$28.80/mo** |
| Pro yearly | **$198/yr** |
| Pro lifetime | **$699 one-time** (promoted at **$399** in a "9th Anniversary" sale) |

Pro adds: WAF / advanced website protection, professional website analytics, multi-user accounts with role-based access, file sync, tamper-proof file protection, bulk email sending, 20+ exclusive extensions, priority support (<https://www.aapanel.com/new/index.html>, <https://www.aapanel.com/new/pricing.html>). 14-day Pro trial.

### 3.6 HestiaCP · CloudPanel · ISPConfig — the genuinely free tier

- **HestiaCP** — free and open source, **GPLv3**, community-donation funded, no paid tier of any kind. Version 1.9.7 at time of fetch. (<https://hestiacp.com/>)
- **CloudPanel** — free, made by **MGT Commerce GmbH**, open source on GitHub, explicitly marketed as a "Free Hosting Control Panel"; built on NGINX + PHP-FPM + Redis + Node.js, 11+ pre-configured components, 30+ vhost templates, multiple PHP versions, ARM support. (<https://www.cloudpanel.io/>)
- **ISPConfig** — "Open Source, transparent, free"; single **and multi-server**; four access levels (Administrator / Reseller / Client / Email Login); Apache2 or nginx, Postfix + Dovecot, BIND or PowerDNS, MariaDB/MySQL; websites, email, FTP users, databases, cron, shell users, DNS records; IPv4 + IPv6; 20+ languages. Supports Debian 11–13, Ubuntu 22.04–24.04, AlmaLinux 8–10, Rocky 8–10, CentOS 8. Paid extras exist: **billing module, migration toolkit, enterprise support.** (<https://www.ispconfig.org/>)

### 3.7 Virtualmin

- **Virtualmin GPL** — free, **unlimited domains**, includes Apache/Nginx, MySQL/PostgreSQL, multiple PHP versions, basic mail management, community support. (<https://www.virtualmin.com/shop/>, <https://www.virtualmin.com/product/virtualmin-gpl/>)
- **Virtualmin Professional** — from **$7.50/month** or **$75/year**, tiered by domain count: 10 / 50 / 100 / 250 / unlimited. Pro adds: priority support, 60+ install scripts, reseller accounts, WP Workbench, advanced user management, multiple SSL providers with auto-renewal, resource limits, DNS provider integrations (Cloudflare, Google, Namecheap, Bunny), cloud backup targets (Google, Backblaze, Dropbox), GPG-encrypted backups, Amazon SES mail delivery, mail redundancy control, extended system stats. (<https://www.virtualmin.com/shop/>, <https://www.virtualmin.com/docs/professional-features/>)
- **Cloudmin Professional** is a separate product (VM/virtualisation management) at the same $7.50/mo · $75/yr entry, tiered 10/50/100/250/500 VMs. (<https://www.virtualmin.com/shop/>)

Virtualmin's stated philosophy, worth noting for ServerAlly's own free/paid split: features reserved for Pro are *"those really only useful in a commercial environment"* — i.e. **they gate the money-making features (resellers, install scripts, offsite backups), not the baseline.**

### 3.8 CloudLinux OS + Imunify360

See §2 matrix for capability detail. Pricing (from the licensing docs and vendor pricing page): Imunify360 is billed **monthly per server** in four bands — single user, up to 30 users, up to 250 users, and unlimited (>250) — supporting cPanel, Plesk, DirectAdmin or standalone; bulk pricing at 5+ servers; **14-day trial with $1 card authorisation** (<https://docs.imunify360.com/billing/>, <https://imunify360.com/pricing/>). Entry point commonly quoted as **$12/month** (matching DirectAdmin's own add-on listing at <https://directadmin.com/pricing.php>). **ImunifyAV** is a free basic antivirus scanner; Imunify360 is the paid full suite (WAF, proactive defence, reputation management).

---

## 4. USER COMPLAINTS & MIGRATION TRENDS

### 4.1 What people actually say

WebHostingTalk is the industry's primary venue and its threads are the clearest signal. **These pages return HTTP 403 to automated fetching**, so the quotes below come from search-engine summaries of those threads, not from a direct read — treat the wording as reported rather than verbatim-verified. Threads: ["Massive cPanel price rises [merged]"](https://www.webhostingtalk.com/showthread.php?t=1770316&page=62) (62+ pages), ["cPanel price increase, will you be moving to Plesk?"](https://www.webhostingtalk.com/showthread.php?t=1771259), ["Price increase yet again from Cpanel"](https://www.webhostingtalk.com/showthread.php?t=1832009), ["CPanel new prices out"](https://www.webhostingtalk.com/showthread.php?t=1927875) (5+ pages).

Recurring themes:
- **"cPanel has become more expensive than the actual server."** For low-end VPS hosting the licence now exceeds the hardware cost.
- **"55% increase for cPanel Solo is laughable."** The Solo tier — 1 account, the smallest possible customer — took the largest proportional hit.
- **Plesk is NOT seen as the escape hatch, because of common ownership.** Operators explicitly say they *"won't recommend Plesk as an alternative"* because Plesk is owned by WebPros, who also own cPanel, and ask *"how long until WebPros changes Plesk's pricing model to match cPanel's"* — a question the January 2026 26% Plesk increase has now answered.
- **Successful DirectAdmin migrations are reported with low customer friction:** one provider moved all shared and reseller hosting to DirectAdmin and reported *"not a single user complained."*

### 4.2 Migration experience — the honest picture

From [HostingDiscussion, Apr 2024 – Mar 2026](https://hostingdiscussion.com/threads/migrating-from-cpanel-to-directadmin-your-experiences.84919/):

- **Motivation is cost, unambiguously** — *"The cost saving… especially with their per-domain licensing model if you're running a lot of accounts"* (May 2025).
- **The mechanics work.** *"Importing existing sites wasn't too bad using their migration tools"* (May 2025); *"Backups restored properly, and DNS settings transferred without major issues"* (Mar 2026).
- **The friction is human, not technical.** *"Initial learning curve for some of my users — DA's interface is clean but feels a bit different"* (Apr 2025); *"I did have to manually tweak a couple DNS zones and PHP settings"*; *"If you've gotten used to cPanel… going to DirectAdmin might be a bit of a shock"* (May 2025).
- **End-users resist.** One operator gave clients the *choice* to switch because *"many people prefer to use cPanel"*, and flagged the risk of *"loss of customers as well."*

> **This is the most transferable insight in §4 for ServerAlly:** the barrier to leaving cPanel is *not* the technical migration — that is solved. It is **end-user familiarity**. cPanel's moat is muscle memory, not features.

### 4.3 Where the market is going — quantified

- **cPanel engagement mindshare: 19.9% (Oct 2024) → 13.7% (Oct 2025) → 12.1% (Jan 2026)** ([commandlinux](https://commandlinux.com/statistics/web-hosting-control-panel-market-share-cpanel-plesk-webmin-on-linux/), citing PeerSpot).
- **Among Linux-specific panels, ISPConfig now leads engagement at 21.2%, Virtualmin 14.6%, cPanel 11.9–12.1%** — i.e. *free open-source panels out-engage cPanel in its own segment* (same source).
- **W3Techs (Mar 2026): Plesk ≈46% of *detected* panels; hPanel 49.2%; RunCloud ≈1%; GridPane <1%.** Critically, **"over 91% of websites show no detectable commercial control panel"** — the addressable market is mostly *not* running a commercial panel at all (same source).
- **Datanyze (2026): cPanel 22–23% commercial installed base.** 6sense reports cPanel 94.04% vs DirectAdmin 5.13% — a wildly different figure that shows how methodology-dependent these numbers are. **Treat all panel market-share numbers as directional only.**
- **DirectAdmin reported to have "grown 35% in 2026"** ([search summary of DirectAdmin comparison articles]) — **UNVERIFIED**, no primary source located; do not cite.

### 4.4 The counter-trend nobody advertises: free panels have a security problem

The strongest argument *against* the free tier, and worth understanding because it is ServerAlly's opening:

- **CyberPanel, October 2024: ~22,000 instances compromised in hours by PSAUX ransomware** via CVE-2024-51378, a command-injection flaw rated **CVSS 10.0**. Related CVEs: CVE-2024-51567 (auth bypass in `databases/views.py` → arbitrary command execution via `/dataBases/upgrademysqlstatus`), CVE-2024-51568. Also used to deploy C3RB3R and a Babuk variant. Roughly **200,000 websites** affected. The flaw was disclosed 23 Oct 2024 and **patched in 2.3.8 within thirty minutes** — but by 29 Oct the count of online instances had collapsed *not because they were patched but because they were hacked and unreachable*. Added to CISA's Known Exploited Vulnerabilities catalogue. Sources: [BleepingComputer](https://www.bleepingcomputer.com/news/security/massive-psaux-ransomware-attack-targets-22-000-cyberpanel-instances/), [Censys advisory](https://censys.com/advisory/cve-2024-51378/), [SecurityWeek](https://www.securityweek.com/cyberpanel-vulnerabilities-exploited-in-ransomware-attacks-shortly-after-disclosure/), [CSO Online](https://www.csoonline.com/article/3595130/psaux-ransomware-takes-down-22000-cyberpanel-servers-in-massive-zero-day-attack/), [SecurityAffairs/CISA KEV](https://securityaffairs.com/171736/hacking/u-s-cisa-adds-cyberpanel-flaw-known-exploited-vulnerabilities-catalog.html).
- **HestiaCP 1.9.3 RCE**, exploit published 6 March 2025 ([Vulners/PacketStorm](https://vulners.com/packetstorm/PACKETSTORM:189606), [GitHub issue #5229](https://github.com/hestiacp/hestiacp/issues/5229)).

**Reading:** free panels win on price and lose on assurance. A free panel is a large, internet-exposed, root-privileged web application maintained by a small team. This is precisely the anxiety ServerAlly's threat-detection and incident-response work speaks to — and it is why "free" has not simply won.

### 4.5 What cPanel's own users are asking for (the best-quality demand signal available)

cPanel surveyed **3,300 users**, published 2026-07-21 (<https://www.cpanel.net/blog/announcements/cpanel-whm-2025-survey-results/>). NPS **28** (45.9% promoters / 36.3% passives / 17.8% detractors) — mediocre for an incumbent with this much lock-in.

**Top requests for 2026+:**

| Rank | Request | Signal |
|---|---|---|
| 1 | **Native Firewall Manager** | **46.3%** |
| 2 | Security & performance advisory | high |
| 3 | Backup management (incremental) | high |
| 4 | Webmail modernisation | high |

Pain points: 15.5% UI/UX modernisation, 7.5% security/firewall gaps; dark mode the most-requested cosmetic change.

**On AI (1,727 responses):** the single most-requested capability is **a log-reading assistant that identifies problem sources and explains solutions.** Users want AI that is **opt-in, contextual and actionable — "not gimmicks."** Only **57 respondents (3.3%)** opposed AI outright, on privacy/cost grounds.

And from cPanel's provider-side survey, 2026-06-12 (<https://www.cpanel.net/blog/products/from-automation-to-intelligence-what-hosting-providers-expect-from-ai/>):

- **36%** of providers call AI/automation the single biggest innovation gap in modern control panels; **53%** expect AI-driven automation to have the biggest industry impact; **27%** have implemented no AI at all.
- Where they want AI, ranked: **automated security/malware detection 65%**, predictive performance monitoring 48%, AI customer support 37%, AI-assisted onboarding/migration 23%, billing anomaly detection 19%.
- Top support burdens: **email issues 42% of support time**, CMS/application problems 39%, performance 35%, security incidents 35%.

> Two direct reads for ServerAlly. **(1) The #1 wanted AI feature — "read my logs, tell me what's wrong and how to fix it" — is exactly what Ally's Live Look + explain_output already does.** **(2) The #1 wanted security feature (65%) is automated malware detection — exactly `threat_service`.** ServerAlly has already built the two things this market says it wants most, and the incumbent has not shipped either.

---

## 5. ⭐ THE BASELINE — what "complete" means in this market

This is the most important section. Ten independently-built panels agree on this list. **A product that misses items in Tier 1 is not perceived as a server-management product at all**, regardless of how good its AI is.

### Tier 1 — UNIVERSAL. Present in essentially every panel; absence is disqualifying.

| # | Capability | Why it is baseline |
|---|---|---|
| 1 | **Website / vhost creation** | The atomic unit of the product |
| 2 | **DNS records + a real nameserver** (BIND / PowerDNS) | Panels *are* the DNS server for most shared hosts |
| 3 | **Email hosting — full stack** (SMTP/IMAP, webmail, spam, DKIM/SPF/DMARC) | 42% of provider support time ([cPanel](https://www.cpanel.net/blog/products/from-automation-to-intelligence-what-hosting-providers-expect-from-ai/)). CloudPanel's omission of email is its single most-cited limitation |
| 4 | **Databases + phpMyAdmin** | phpMyAdmin specifically — users expect that exact tool |
| 5 | **SSL / Let's Encrypt automation** (auto-issue *and* auto-renew) | Went from premium to table stakes in ~5 years |
| 6 | **FTP accounts** | Legacy but universally present; clients still hand FTP details to designers |
| 7 | **File manager (web)** | The non-technical user's only file access |
| 8 | **PHP version management per site** | Multi-tenant hosting is unworkable without it |
| 9 | **Cron jobs** | |
| 10 | **Backups + restore** | |
| 11 | **Account / user management, with a reseller tier** | The multi-tenant model the whole industry sells on |
| 12 | **Monitoring / resource usage** | |
| 13 | **One-click app installer, WordPress first** (Softaculous / WP Toolkit / equivalent) | WordPress *is* the workload |

### Tier 2 — EXPECTED. Present in most; absence is a real objection but not fatal.

| # | Capability | Note |
|---|---|---|
| 14 | **Firewall management** | **cPanel's own users rank a native firewall manager their #1 request at 46.3%** — the incumbent doesn't have one; CSF is third-party |
| 15 | **Offsite/remote backup targets** (S3, SFTP, Google Drive) | Often the first paid upgrade (CyberPanel Backup V2, Virtualmin Pro) |
| 16 | **Security scanning / malware / WAF** | Usually a paid add-on (Imunify360) rather than bundled |
| 17 | **Terminal / SSH in browser** | |
| 18 | **API** | Every serious panel has one; it is how WHMCS provisions |
| 19 | **CLI** | |
| 20 | **Staging / cloning** | Increasingly expected for WordPress; frequently paid |

### Tier 3 — DIFFERENTIATORS. Sparse across the group — this is open ground.

| # | Capability | State of the market |
|---|---|---|
| 21 | **Multi-server management from one place** | The great structural weakness: panels are licensed and installed **per server**. ISPConfig's genuine multi-server is a headline differentiator; Plesk 360 and WHM clustering are partial. **This is ServerAlly's strongest structural advantage.** |
| 22 | **Git integration** | Inconsistent |
| 23 | **Mobile app** | Rare |
| 24 | **AI features** | **NOT SHIPPED by cPanel or Plesk as of mid-2026.** cPanel's is roadmap and explicitly *"assist but not independently act"*; Plesk's AI Copilot has no ship date |

### The three-sentence version

> **Baseline = sites, DNS, email, databases, SSL, FTP, files, PHP versions, cron, backups, users/resellers, monitoring, one-click WordPress.** All ten panels do essentially all of it, and five of them do it for **$0**. Therefore ServerAlly cannot win on baseline coverage and must not price as if it could — it must either cover the baseline *as a floor* or sit deliberately above it, and win on the three things no incumbent has: **multi-server, AI that actually acts, and security response.**

---

## 6. KEY INSIGHTS FOR SERVERALLY

**1. The AI window is open but narrowing, and the incumbents have publicly picked the *weaker* side of the design.** cPanel's AI will *"assist but not independently act"* and "operates within existing permission models" (<https://www.cpanel.net/blog/products/the-next-evolution-of-cpanel-built-in-ai-for-faster-smarter-hosting-management/>, 2026-04-15). ServerAlly's missions *do* act — with a safety blocklist, per-step approval, a verification gate and injection defence. That is a genuine product difference, not a marketing one. But note the flip side: cPanel has chosen the position that is *easier to trust*, and trust is the actual buying objection.

**2. cPanel is putting an MCP server in WHM.** *"MCP server support in WHM for more modern, prompt-driven admin interactions"* is on the published 2026 roadmap ([cPanel roadmap](https://www.linkedin.com/posts/cpanel_cpanel-roadmap-2026-activity-7420496823657693184-2FAD)). ServerAlly shipped its MCP connector in July 2026. **The lead is months, not years — and cPanel's version will be pre-installed on a large installed base.** ServerAlly's defensible edge is *cross-server* MCP (one connection, whole fleet) versus cPanel's inevitably per-server scope.

**3. Do not try to be a control panel.** Building the Tier-1 baseline means a mail stack, a nameserver, phpMyAdmin, FTP and a WordPress installer — years of work, competing against free, in a category whose *own users* rate it NPS 28. ServerAlly should sit **on top of** panels (it already does: CyberPanel CLI-over-SSH, hosting adapters) rather than replace them. The right frame is *"ServerAlly manages your servers **and** your panels"*, not *"ServerAlly instead of your panel."*

**4. The two features this market most wants are ones ServerAlly already has.** #1 requested AI capability = a log-reading assistant that finds the problem and explains the fix (Live Look + `explain_output`). #1 requested security capability, at 65% of providers = automated malware detection (`threat_service`). Lead with these two in any positioning aimed at hosts.

**5. Multi-server is the structural gap.** Every panel here is per-server by architecture and by licence. ISPConfig's multi-server is *why* it out-engages cPanel among Linux panels. ServerAlly is fleet-native by design — that is worth more emphasis than the AI in front of a professional buyer.

**6. Price against $0, and against $0.50/account.** Five free panels set the floor for baseline management; hosts on PartnerNOC deals pay ~$49.50 per 100 accounts. This corroborates [PRICING-V3](../../../../../docs/PRICING-V3.md)'s conclusion that the per-server platform layer must be modest and the AI layer must be separable — and it strengthens the BYO-AI lane, since a host already paying $49.50 + $12 Imunify + $8.95 JetBackup per server has a hard cost ceiling.

**7. The migration barrier is familiarity, not technology.** Operators report clean cPanel→DirectAdmin migrations whose only real cost was retraining end users, and some kept cPanel purely because *"many people prefer to use cPanel."* ServerAlly's plain-English interface is a *migration-friction eliminator*: if the interface is conversation, there is nothing to relearn. That is a sharper wedge than any feature comparison.

**8. Free panels have a credible security liability, and that is an opening.** 22,000 CyberPanel servers ransomwared in hours in Oct 2024; a HestiaCP RCE in Mar 2025. The person running a free panel has the most exposure and the least support. ServerAlly's threat scanning + guided incident response speaks directly to that buyer — and they are *not* currently paying anyone anything, so the whole budget is available.

---

## 7. CONFIDENCE & GAPS

**High confidence:** cPanel retail pricing (vendor page), DirectAdmin retail pricing (vendor page), CyberPanel add-on pricing (vendor page), aaPanel pricing (vendor page), HestiaCP/CloudPanel/ISPConfig free status (vendor pages), Virtualmin GPL-vs-Pro split (vendor pages), cPanel AI roadmap + survey data (cPanel's own blog), CyberPanel CVE incident (multiple security outlets + CISA KEV).

**Medium confidence:** cPanel historical prices by year (third-party trackers, not archived vendor pages); PartnerNOC pricing (two independent hosting providers agree); Plesk USD 2026 pricing (two sources agree, but not read off plesk.com).

**Flagged / unresolved:**
- **Plesk EUR pricing axes (VPS vs Dedicated × Monthly vs Yearly) — UNVERIFIED.** Automated extraction of plesk.com/pricing returned contradictory axis labels across three passes. Re-check in a browser before quoting EUR figures.
- **DirectAdmin 60-day trial — UNVERIFIED** against directadmin.com.
- **"DirectAdmin grew 35% in 2026" — UNVERIFIED**, no primary source. Do not cite.
- **Panel market-share figures are wildly methodology-dependent** (W3Techs vs PeerSpot vs Datanyze vs 6sense give 46% / 12% / 22% / 94% for overlapping questions). Use only the *direction* — cPanel declining — not the levels.
- **WebHostingTalk threads return HTTP 403** to automated fetch; quotes in §4.1 are from search-engine summaries and are reported, not verbatim-verified.
- **Reddit is not accessible** to this environment's search tooling, so r/webhosting sentiment is not represented.
