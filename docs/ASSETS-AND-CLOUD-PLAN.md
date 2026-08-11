# Assets, re-organised — and AWS reached without a key

**Status:** proposed, not started. Written 2026-08-10.
**Supersedes:** `AWS-SSM-PLAN.md` (deleted — this is the same work, correctly scoped).

**The story in one sentence:** a customer adds their cloud account once, sees their AWS things
in an AWS zone, and manages the servers inside them with **no SSH key, no open port 22 and
nothing to install**.

That is one story. The Assets re-organisation is the front of it; SSM is the back. Building
either alone leaves the other half looking wrong, which is why they are one plan.

---

## 1. Where this came from

Two things happened on the same day.

**A real onboarding.** An owner connected a live EC2 instance (`i-0dc3c7a19320bc519`, Ubuntu
22.04, CyberPanel, serving firevps.net and clients.firevps.net) and asked:

> *"I added my AWS IAM user. Why does ServerAlly still ask for an SSH key?"*

The honest answer today is that an AWS API key lets us **list** instances and never lets us
**enter** one. AWS hands the private key over once, at creation, and keeps only the public
half. Our import modal says exactly that, and it is true — but only because we have not built
the other door. AWS provides one. We do not support it.

The SSH path also carried far more friction than it should, on a completely ordinary AWS
server:

1. The key was a PuTTY `.ppk`, not an OpenSSH `.pem`
2. Ubuntu AMIs disable root, so the key reaches `ubuntu`
3. `root`'s `authorized_keys` carries AWS's forced command, so root "works" and gives no shell
4. Editing root's `authorized_keys` on a live production server is a step nobody enjoys

**A PM review of the Add screen.** Looking at the same product, the owner's verdict was that
the categories do not match how anyone thinks, and that one of them is a dead end.

---

## 2. The principle that decides the whole design

**Where an asset came from is a different question from what you can do with it.**

Today `category` tries to answer both, and answers neither cleanly:

| Category | What it actually answers |
|---|---|
| Bare Metal, VPS | where it lives |
| Hosting Panel | what software runs on it |
| Windows Server, Windows (RDP) | operating system and protocol |
| Cloud Account | not a server at all |

Three different questions in one list.

**The good news is that the code is already right.** Capability comes from `connection_type`,
never from `category` — `assetMenu.ts`:

```ts
if (c === "ssh") { caps.add("sftp"); caps.add("unix") }
if (server.panel_type || c === "hosting") caps.add("panel")
if (server.cloud_account_id) caps.add("cloud")
```

So an EC2 filed under **AWS** keeps every ability a VPS has, automatically. Nothing has to be
re-plumbed. **This is a grouping change, not a capability change** — and that is why it is
affordable.

Verified: `bare_metal` appears nowhere except as a label. Nothing in the backend or frontend
branches on it.

---

## Part A — Assets, re-organised

### A1. Bare Metal + VPS → **Server**
**Decision: owner, agreed.**

Two tiles for one thing. A customer does not care whether the machine is dedicated or
virtual — only that it is Linux and they have SSH. Two choices create doubt at the exact
moment of adding, and **nothing behaves differently** between them.

One tile: **Server** — *"A Linux machine you have SSH access to. Dedicated or virtual."*

### A2. Hosting Panel — remove the tile **and** the group; it becomes a chip
**Decision: owner, 2026-08-10.** Owner's words: *"I know Panel2 is a server but also a
CyberPanel."*

**The tile goes,** because it is a dead end. From a live CyberPanel on 2026-07-04:
CyberPanel's `adminUser/adminPass` API is a cloud-management surface only — `verifyConn`,
user CRUD, packages, remote transfer — with **no website list/create, no database, no SSL**.
Those are session+CSRF web routes, not API. The reliable surface is the `cyberpanel` CLI over
SSH, and the product already says so on screen. A tile leading there is a trap.

**The group goes too,** and this is the owner's improvement on my first draft. Three reasons:

1. **It makes the rule pure.** A group answers *where did this come from?* — a provider, or
   "I added it myself". "Has a panel" is a property of a machine, not a kind of machine.
   Removing it removes the last exception.
2. **It makes the panel treatment consistent.** We had already settled that a panel EC2 shows
   under AWS with a chip. With this change, a hand-added panel server gets **exactly the same
   treatment** — its own group by origin, a chip for the panel. No special case anywhere.
3. **It is how the owner already thinks about it**, in their own sentence above.

**What replaces it:** a chip on the row, named after the real panel — `CyberPanel`, not
"Hosting panel", per the 29 July decision that the panel section is named after the panel. And
inside the server, the Control-panel section, which already exists and already does this.

*Later:* cPanel (UAPI) and Plesk (REST) do have real APIs. If we ever support one without SSH,
the tile can come back — for that panel only.

### A3. Windows Server + Windows (RDP) → one **Windows Server** tile
**Decision: owner, agreed. Keep the capability, merge the choice.**

One tile. Inside it, one question: *"How will you connect — Remote Desktop, or command line?"*
— the same shape as choosing password or key.

Honest note: the two really are different connections (RDP 3389 vs WinRM 5985) with different
capabilities, and `capabilitiesOf` must keep treating them differently. **Merge the choice,
not the types.** An RDP box still gets *Open desktop* and no shell.

### A4. Provider zones — **Cloud** in the left menu, accounts inside
**Decision: owner's design and owner's rule. One refinement recommended.**

> **The rule, owner's words:** *each provider's assets show only under that provider* — as a
> menu item, or as that provider's group on the Assets page.

One rule, no exceptions. An asset that came from a cloud account appears **there and nowhere
else**; it is never also listed under Server. Everything else — added by hand — groups by what
it is.

When a customer connects AWS, they get an **AWS zone**: their imported EC2 instances, and in
time their other AWS resources. Same for DigitalOcean and Hetzner.

Why this is right:

- **It matches how people think.** Nobody thinks *"my VPS group"*. They think *"my AWS"*.
- **It makes room for things that are not servers** — S3, RDS — which will never fit in a
  server list (see Part C).
- **For an MSP, one zone per client account is exactly their mental model.**

**The refinement:** the owner's version puts each provider directly in the left menu. That
works for one or two accounts and breaks for an MSP with twenty — twenty menu items. Instead:

```
Cloud
 ├── AWS · ceo@astgd.com        (3 servers)
 ├── AWS · client-acme          (12 servers)
 └── Hetzner · personal         (2 servers)
```

One menu item. The zone idea is unchanged; the menu stays readable at any scale.

### A5. The group is DERIVED, never stored

The rule above is small enough to be a function, so it should be one:

```
group(server) =
    server.cloud_account_id   ?  that provider account
  : connection_type winrm/rdp ?  Windows server
  :                              Server
```

Three lines, and no exceptions. A panel does not appear here at all — it is a chip (A2), and
`panel_type` keeps driving the Control-panel section through `capabilitiesOf`, unchanged.

**Not a stored column.** This codebase already learned that lesson with the server role on
2 August: *"a column would go stale the day somebody installs a panel by hand, and the screen
would then insist we run a machine the panel has taken over."*

Two things fall out of deriving it, and both are free:

- **The import bug (A8) becomes impossible.** There is no `category` to hardcode, so the AWS
  import cannot file a CyberPanel EC2 as a VPS. The bug is designed out rather than fixed.
- **Open question 2 answers itself.** When a cloud account is disconnected,
  `cloud_account_id` becomes `NULL` (the FK is `SET NULL`), so the same rule re-files the
  server as Server or Hosting Panel automatically. No special case, no orphan.

The stored `servers.category` column stays only until the migration is done, then goes.

### A6. Filters slice across groups — they are not groups

A group answers *where did this come from?* A filter answers *show me only these.* Keeping
them apart is what stops the group list growing back into the mess in §2.

A chip row above the list, each one counting what it would show:

```
All 10 · Panels 2 · Windows 1 · Needs attention 1        [ search ]
```

**Why a filter and not a group.** An agency with forty CyberPanel servers might want to see
them together — but they would all sit under Server anyway, so a "Panels" group would just be
"most of my servers", which sorts nothing. A filter finds them **wherever they live**,
including inside a provider zone, which a group by definition cannot.

Rules:

- **Derived, like the groups.** `Panels` = `panel_type` is set. `Windows` = winrm or rdp.
  `Needs attention` = the existing health verdict. Nothing new is stored.
- **A filter with a count of zero is not shown.** A customer with no Windows server should
  never see a Windows filter — the same "absent, not disabled" rule the menus already follow.
- **Filters compose with search**, and both work across every group at once.
- **Groups stay visible while filtering**, so a filtered view still says where each result
  lives. Otherwise filtering flattens the page and loses the thing this redesign is for.

### A7. What must not break

- **Capabilities stay driven by `connection_type`.** An EC2 in the AWS zone must keep every
  Server ability. If the menu ever starts reading `category`, this design has failed.
- **Existing rows must not be orphaned.** The stored `category` is going away entirely, so
  the migration is a deletion rather than a remapping — the group is computed from
  `cloud_account_id` and `connection_type` on every read. A server currently filed as
  `hosting` becomes a Server with a `CyberPanel` chip; `bare_metal` and `vps` both become
  Server; `windows_rdp` becomes Windows server. No row needs editing for this to be true.
- **A cloud account can be disconnected.** `servers.cloud_account_id` is `SET NULL` on
  delete, so an asset would lose its zone. It must fall back to **Server**, not vanish.
  *(Open question 2.)*

### A8. The bug this designs out

The AWS import writes a database row and **never probes** — `cloud_accounts.py:205`:

```python
category="windows" if t["connection_type"] == "winrm" else "vps",   # hardcoded
```

No `test_connection`, no `detect_os`, no `panel_type`. Compare the manual add
(`servers.py:104`), which does all three and re-files a panel server as hosting.

So importing a CyberPanel EC2 from the AWS section produces a plain VPS with no OS, no panel
and no Control-panel section — while adding the *same server* by hand produces the right
thing. **Two doors, one does half the job.** The import must call the same probe as the manual
add — the same code, not a copy, or they will drift again.

---

## Part B — AWS Systems Manager (SSM) as a connection type

### B1. Why it is worth building

**It removes the worst operational pain for the buyer we want.** An MSP with fifty client
accounts does not want fifty `.pem` files. Key custody — who holds them, where they live, what
happens when someone leaves — is the most annoying part of the job. SSM removes it: access is
IAM, granted and revoked centrally, with no artefact to lose.

For the record, the key in the onboarding above was **the only copy, in a personal OneDrive,
on an account with no MFA**. That is not unusual. That is normal.

**It opens customers we cannot serve at all today.**

- **Port 22 closed.** PCI, HIPAA and SOC 2 environments routinely forbid inbound SSH. For
  those customers SSM is the only sanctioned path — so today we cannot be used at all.
- **Private instances.** We need a reachable address. Our own import form carries a *"Connect
  over the private IP (use inside a VPN / same VPC)"* checkbox, which is a workaround. With
  SSM, an instance with **no public IP whatsoever** is reachable, because the agent dials out
  rather than us dialling in.

**It gives the MSP something to sell.** Every command is recorded in **the client's own
CloudTrail**. The MSP can point the client at an audit trail the client controls, and the
client can revoke access by detaching a role.

**It solves the root problem for free.** The SSM agent runs as root, so commands run as root.
Every difficulty in §1 items 2–4 disappears. No `authorized_keys` editing on any server, ever.

### B2. The correction that shapes it

**AWS partners do not receive an IAM user in a client's account. They receive a role they
assume, with an external ID.** Our AWS adapter supports **access keys only** — there is no
`assume_role` anywhere in `cloud_service.py`.

So this is two pieces, and the second is what makes it an MSP product:

| Piece | What it gives |
|---|---|
| **SSM transport** | reach inside a server with no key and no open port |
| **Cross-account role** | connect a *client's* account without holding a credential in it |

### B3. Why it fits our architecture

Every connection goes through one contract in `connection_manager.py`:

```python
async def execute(server, command) -> tuple[str, str, int]   # stdout, stderr, exit code
```

**SSM's `SendCommand` + `GetCommandInvocation` produce exactly that shape.** No WebSocket, no
session protocol, no `session-manager-plugin` binary.

Adding `connection_type == "ssm"` makes all of this work unchanged: OS detection, metrics,
site discovery, security and malware scans, log discovery, databases, cron, daemons, PHP
version, firewall, SSH keys, playbooks, Ally and missions.

### B4. What is genuinely hard

**File transfer has no SSM equivalent.** SFTP does not exist there. These need a second
mechanism: File Manager, the `.env` editor, the `wp-config.php` editor, certificate install,
site clone and staging copy.

| Option | Cost |
|---|---|
| base64 through `SendCommand` | simple, but content becomes a command argument — visible in `ps`, kept in SSM's command history, and **breaks the exact rule the certificate and `.env` work was built on** |
| via S3 | AWS's own pattern; needs a bucket, a presigned URL and lifecycle cleanup, but keeps secrets off the command line |

**S3 is the correct answer**, and it is the same shape as `offsite_service`: the backend mints
a short-lived presigned URL, the server uses it, the credential never lands on the server.

**The interactive terminal needs the session protocol.** `/ws/terminal` needs a live stream —
AWS's session channel, or their plugin binary. Hardest piece, least important; Ally covers
most of what people open a terminal for.

**The customer has a prerequisite.** The instance needs the SSM agent (preinstalled on Amazon
Linux and Canonical's Ubuntu AMIs — usually already there) and an instance role with
`AmazonSSMManagedInstanceCore` (usually **not** there — the instance we onboarded had no role
at all), plus egress to the SSM endpoints or VPC endpoints. `ssm:DescribeInstanceInformation`
tells us whether an instance is genuinely managed; absence is the normal case, not an error.

**`SendCommand` is not a shell.** Output is truncated at **24,000 characters** unless sent to
S3 — several of our probes exceed that. It is poll-based, so every command carries latency SSH
does not. And `execute_stream` (live playbook output, the terminal) has no direct equivalent.

---

## Part B2 — other providers: considered, and deliberately not built

**Decision: owner, 2026-08-10, after testing DigitalOcean.** *"DigitalOcean droplets connect
with SSH fine with the current design, so keep them as they are — just change how they show."*

Worth writing down, because it will be asked again.

**SSM cannot be copied.** Only AWS and Azure built an agent the control plane can talk to:

| Provider | Run a command with only the API key |
|---|---|
| AWS | ✅ SSM Run Command |
| Azure | ✅ VM Run Command |
| Google Cloud | ❌ |
| DigitalOcean, Hetzner, Vultr, Linode | ❌ |

*(Not verified by us — check before relying on it.)*

**An alternative was considered and rejected:** ServerAlly could generate a keypair and upload
the public half to the customer's DigitalOcean or Hetzner account, so the customer never
handles a key. It was rejected for two reasons:

1. **SSH already works there**, and adding a mechanism that is not needed is cost with no gain
2. **It moves the risk to us.** With SSM nobody holds a key, so a breach of our database gives
   an attacker nothing. With generated keys, it gives them the servers.

So: **other providers keep SSH exactly as they are.** Only their *grouping* changes, under the
one rule in A4.

**The consequence for the pitch** — two sentences, not one:

- *"You never handle an SSH key"* — achievable on every provider
- *"No SSH key exists at all, and port 22 can be closed"* — **AWS and Azure only**

The second is the stronger claim and the one for AWS partners. It must not appear on a page
that also lists DigitalOcean.

---

## Part C — the things that are not servers (deferred, 2026-08-10)

**Decision: owner.** *"EC2 is enough to start, skip S3 and RDS for now."*

Kept in the plan because the reasoning is what stops someone bolting it on later.

**EC2 is a server. S3 and RDS are not.**

A `Server` row has a host, a port, a username, a credential and metrics. An S3 bucket has none
of those. Forcing buckets into that table would break every list, every scan and every metrics
query in the product.

So *"all AWS services under AWS"* is two features:

| | Size |
|---|---|
| **Servers grouped under their cloud account** | small — Part A |
| **Non-server resources (S3, RDS) listed in the zone** | large — a new read-only *cloud resource* concept |

**It must not be bolted onto the server model.** A `Server` row assumes a host, a port, a
credential and metrics; an S3 bucket has none of those, and forcing it in breaks every list,
scan and metrics query in the product. When this is built it needs its own read-only concept.

**Consequence for the UI, and it follows the owner's own rule:** the "Other resources" section
must be **absent from the AWS zone, not shown greyed out**. The mockup drew it dimmed; that was
wrong. Same rule the menus already follow — a section that cannot work here is absent, not
disabled — and the same rule A6 applies to a zero-count filter.

---

## Part D — the honesty bug, which is independent and should go first

Found while measuring what a non-root connection can actually see on the onboarded server.

Our probes are inconsistent about privilege:

| Service | `sudo` uses |
|---|---|
| `security_service` | 29 |
| `log_service` | 2 |
| `site_service` | **0** |
| `threat_service` | **0** |
| `metrics_service` | 0 |

Connected as a non-root user with sudo — **the default on every AWS, GCP and Azure image** —
the malware scan reads nothing and reports **"No threats found."** Not *"I could not look."*
Clean.

That is a false all-clear on the most safety-critical feature we ship, and it is the same
shape as a bug this codebase already has a written rule against: the `_t` helper in
`threat_service` was deliberately made to fail *open* because "an empty webshell section reads
as clean, i.e. a silent false all-clear on a critical check".

Measured on the real server, as `ubuntu`:

| Path | Result |
|---|---|
| `/usr/local/lsws/conf/vhosts` (site configs) | denied |
| `/home/firevps.net`, `/home/clients.firevps.net` | denied |
| `/var/log/nginx`, `/usr/local/lsws/logs` | denied |
| `[ -x /usr/bin/cyberpanel ]` (panel detection) | **silently false** — cannot traverse `/usr/local/CyberCP` |

Two fixes:

1. **Refuse to lie.** Detect that we are not root and mark affected checks *not performed*,
   never *passed*.
2. **Escalate with `sudo -n` where available**, so `ubuntu` / `ec2-user` work as well as root.

Fix 2 also removes the need to edit root's `authorized_keys` during onboarding — worth having
whether or not SSM is ever built.

---

## Security model

Guarantees this must hold, written so they can be tested:

1. **No AWS credential ever reaches a managed server.** The backend calls AWS; the server
   receives only a command or a presigned URL. Same rule as `offsite_service`.
2. **The external ID is mandatory for cross-account roles**, generated by us, unique per
   connection, never chosen by the customer — otherwise a role trusting our account is open to
   the confused-deputy problem, and any other customer of ours could ask us to assume it.
3. **Assumed-role credentials are short-lived and never stored.** We keep the role ARN and
   external ID; we call `AssumeRole` per operation and hold the result in memory only.
4. **Rule 7 still applies.** SSM is a transport, not a permission model.
5. **The safety blocklist still applies.** `safety_service.validate_command` runs before
   anything reaches `SendCommand`.
6. **What we cannot do is said, not hidden** — an unmanaged instance is reported as *not
   reachable this way, and here is the fix*, never as a server with no sites and no findings.

### Least privilege, for the customer's own IAM

Worth shipping as copy-pasteable guidance, because the account we onboarded had
`IAMFullAccess + PowerUserAccess` — effectively administrator — and was about to be handed to
an application. The interesting part is the tag condition:

```json
{
  "Effect": "Allow",
  "Action": ["ssm:SendCommand"],
  "Resource": "arn:aws:ec2:*:*:instance/*",
  "Condition": { "StringEquals": { "aws:ResourceTag/ManagedBy": "ServerAlly" } }
}
```

The customer tags the instances we may touch. We cannot reach the others even if we wanted to.
For an MSP that is exactly the control their client will ask for.

---

## Phases

| Phase | Work | Size |
|---|---|---|
| **0** | Part D — non-root honesty and `sudo -n` escalation | small, benefits every existing customer |
| **1** | A1 Server merge · A3 Windows merge · A2 panel becomes a chip (tile and group both go) · A6 filter row | small, makes the Add screen and the list honest |
| **2** | A8 — the import runs the same probe as the manual add | small, removes a real gap |
| **3** | A4 — Cloud zone, accounts inside, servers grouped by account | real design work |
| **4** | B — SSM as a connection type (`SendCommand`) | the transport |
| **5** | B2 — cross-account roles with external ID | **this is what makes it an MSP product** |
| **6** | Files via S3 | unblocks File Manager, editors, certificates, clone, staging |
| **7** | Interactive terminal | possibly never |

**Stop after Phase 5 and test whether it sells.**

---

## Positioning — and a caution

AWS partners already have Session Manager and Fleet Manager, free, from AWS. If the pitch is
*"manage your AWS servers"*, the honest reply is *"why not use the free AWS tool?"* and we
lose.

The pitch has to be what sits **on top** of access:

> **Manage your clients' websites on AWS — malware scanning, WordPress and site management,
> backups, uptime, and an assistant that explains problems in plain English — without ever
> handling an SSH key.**

Access is the enabler. AWS gives access away; nobody gives away the rest.

And per B2: *"no key exists"* is an AWS and Azure claim only. On DigitalOcean and Hetzner the
honest claim is *"you never handle a key"* — which is still true, and still worth saying.

---

## Open questions

1. ~~Does the Hosting Panel tile go?~~ **Decided 2026-08-10 — owner.** Both the tile and the
   group go; it becomes a chip on the row plus the section inside the server (A2).
2. ~~What happens to an EC2 when its AWS account is disconnected?~~ **Answered by A5.**
   Deriving the group means `cloud_account_id` going `NULL` re-files it as Server
   automatically — no special case.
3. ~~Does Part C (S3, RDS) matter for the first release?~~ **Decided 2026-08-10 — owner.**
   EC2 only. S3 and RDS are deferred, and the AWS zone shows no placeholder for them.
4. **Does SSM change the pricing story?** An MSP connecting one account with forty instances
   is forty servers under a per-server plan. Decide before it exists.
5. **Whose S3 bucket for file transfer?** Ours is simpler; theirs is correct, for the same
   reason offsite backups go server → storage directly. Leaning theirs.
6. **Windows.** SSM handles Windows too, and would be a better transport than WinRM — which we
   support but have never validated against a live Windows host. Possibly a bigger win than it
   looks.

---

## How it gets validated

Proven by running it, not by reading it:

- **A real EC2 in a private subnet with no public IP**, managed end to end. That single test
  proves the thing SSH cannot do.
- The same instance with **port 22 closed entirely**.
- An instance **without** a role — must report *not reachable this way, here is the fix*, and
  must never report an empty scan as clean.
- A cross-account role from a second AWS account, with a **wrong external ID refused**.
- **Output larger than 24 KB** — must arrive complete or say it was truncated. Silent
  truncation on a malware scan is the same false all-clear as Part D.
- **Existing assets after the category migration** — no asset loses its menu, and an EC2 in the
  AWS zone still has every Server section.

---

## Deliberately not in scope

- **Managing AWS itself** — creating instances, editing security groups, managing IAM. A
  different product. `cloud_lifecycle_service` already records why AWS stays import-only:
  networks, security groups, images and disks must all be decided before a machine can exist,
  and a half-built version fails in ways a customer cannot recover from.
- **Replacing SSH.** SSM is an additional door. Most servers ServerAlly manages are not on AWS.
- **GCP and Azure equivalents.** Both have agent-based access. Out of scope until AWS proves
  itself.
