"""Whether a domain's email will actually arrive.

Email is 42% of a hosting provider's support time — more than any other category — and
almost none of that is "the mail server is down". It is *"my email goes to spam"*, which is
caused by DNS records nobody can see and nobody gets told about. A customer finds out when
an invoice never arrives.

So this is deliberately the half of email that is ours. We do not run mailboxes, webmail or
spam filtering — five free products do, and running them is where the support cost lives.
We check that mail from this domain will be believed, and say what to fix.

**Deterministic, like uptime and certificates.** No AI: an agency may act on this monthly,
so it must be reproducible, free to run, and unable to invent a problem.

Four things go wrong in the real world, and three of them are invisible:

- **Two SPF records.** Perfectly valid-looking, and the standard says a receiver must
  ignore BOTH. Mail starts failing with no error anywhere.
- **More than ten DNS lookups in SPF.** The limit is in the standard; past it the whole
  record is discarded. Adding one more mail service is all it takes, and nothing warns you.
- **`p=none` on DMARC.** Looks like protection, does nothing but report.
- **A blacklisted address**, which is at least visible once you look.

Absence is reported honestly. A missing DKIM record cannot be proven — the selector is
chosen by whoever set the mail up — so we say "could not find one", never "you have none".
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Checked in order; the first that answers wins. Kept short on purpose — every extra
# selector is another DNS query on every check, for a diminishing chance of a hit.
COMMON_DKIM_SELECTORS = (
    "default", "google", "selector1", "selector2", "k1", "mail", "dkim", "s1", "s2",
    "cyberpanel", "x",
)

# Small and well-established. A long list is worse, not better: several public blocklists
# are abandoned and answer "listed" to everything, which would tell a customer their mail
# is blocked when it is fine — and a false alarm here costs more than a missed one.
BLOCKLISTS = (
    ("zen.spamhaus.org", "Spamhaus"),
    ("bl.spamcop.net", "SpamCop"),
    ("b.barracudacentral.org", "Barracuda"),
)

# The mechanisms that cost a DNS lookup each. Past ten, the whole record is discarded.
_LOOKUP_MECHANISMS = ("include:", "a:", "mx:", "ptr", "exists:", "redirect=")
SPF_LOOKUP_LIMIT = 10

SEVERITY_ORDER = {"critical": 3, "warning": 2, "info": 1, "ok": 0}


@dataclass
class Finding:
    key: str
    severity: str            # critical | warning | info | ok
    title: str
    detail: str
    fix: str = ""


@dataclass
class MailHealth:
    domain: str
    has_mx: bool = False
    mx_hosts: list[str] = field(default_factory=list)
    spf: str | None = None
    dkim_selector: str | None = None
    dmarc: str | None = None
    sending_ip: str | None = None
    blocklisted_on: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        worst = max((SEVERITY_ORDER.get(f.severity, 0) for f in self.findings), default=0)
        return {3: "failing", 2: "at risk", 1: "ok", 0: "ok"}[worst]

    @property
    def score(self) -> int:
        """0–100, so a customer can see it improve. Weighted by what actually blocks mail."""
        points = 100
        for f in self.findings:
            points -= {"critical": 30, "warning": 12, "info": 3}.get(f.severity, 0)
        return max(0, min(100, points))


# ── the judgement, all pure ──────────────────────────────────────────────────
def spf_lookup_count(record: str) -> int:
    """How many DNS lookups this record costs.

    Counted because exceeding ten discards the record entirely, and the count is invisible
    to the person editing it — they add one more mail provider and everything silently
    stops being authorised.
    """
    text = (record or "").lower()
    count = 0
    for token in text.split():
        token = token.lstrip("+-~?")
        if token.startswith(("include:", "a:", "mx:", "exists:", "redirect=")):
            count += 1
        elif token in ("a", "mx", "ptr"):
            count += 1
    return count


def evaluate_spf(records: list[str]) -> list[Finding]:
    spf = [r for r in records if r.lower().startswith("v=spf1")]
    if not spf:
        return [Finding(
            "spf_missing", "critical", "No SPF record",
            "Nothing tells other mail servers which machines may send email as this "
            "domain, so anyone can pretend to be you and your own mail is more likely to "
            "be treated as spam.",
            "Add a TXT record for the domain, starting v=spf1, listing your mail server.")]
    if len(spf) > 1:
        # The one people never find on their own.
        return [Finding(
            "spf_duplicate", "critical", f"{len(spf)} SPF records — mail servers ignore all of them",
            "A domain may only have one. When there are two, the rule says receivers must "
            "discard every one, so the domain ends up with no protection at all even "
            "though the records look correct.",
            "Delete all but one, merging what they list into the record you keep.")]

    record = spf[0]
    out: list[Finding] = []
    lookups = spf_lookup_count(record)
    if lookups > SPF_LOOKUP_LIMIT:
        out.append(Finding(
            "spf_lookups", "critical",
            f"SPF needs {lookups} lookups — the limit is {SPF_LOOKUP_LIMIT}",
            "Past the limit the whole record is thrown away, so no sender is authorised. "
            "This usually happens after adding one more mail service, and nothing warns "
            "you when it does.",
            "Remove services you no longer use, or flatten the includes into addresses."))
    elif lookups == SPF_LOOKUP_LIMIT:
        out.append(Finding(
            "spf_lookups_near", "warning",
            f"SPF is at the limit of {SPF_LOOKUP_LIMIT} lookups",
            "Adding one more mail service will break it completely, with no error.",
            "Tidy it up before adding anything else."))

    tail = record.strip().split()[-1].lower() if record.strip().split() else ""
    if tail == "+all" or tail == "all":
        out.append(Finding(
            "spf_permissive", "critical", "SPF allows anyone to send as this domain",
            "The record ends in +all, which authorises every server on the internet. That "
            "is the same as having no SPF, and worse — it looks deliberate.",
            "End the record with -all (strict) or ~all (soft)."))
    elif tail == "?all":
        out.append(Finding(
            "spf_neutral", "warning", "SPF has no opinion about unknown senders",
            "The record ends in ?all, which tells receivers to treat forged mail exactly "
            "like real mail.", "End the record with -all or ~all."))
    return out


def evaluate_dmarc(record: str | None) -> list[Finding]:
    if not record:
        return [Finding(
            "dmarc_missing", "warning", "No DMARC record",
            "DMARC tells other mail servers what to do with mail that fails your checks, "
            "and sends you reports. Without it, forged mail in your name is handled by "
            "guesswork.",
            "Add a TXT record at _dmarc.<domain> — start with v=DMARC1; p=none to watch "
            "before enforcing.")]
    policy = ""
    m = re.search(r"\bp\s*=\s*(none|quarantine|reject)\b", record, re.I)
    if m:
        policy = m.group(1).lower()
    if policy == "none":
        return [Finding(
            "dmarc_monitor_only", "info", "DMARC is only watching, not protecting",
            "The policy is p=none, which asks for reports but tells receivers to do "
            "nothing about forged mail. It is the right place to start and the wrong "
            "place to stay.",
            "Once the reports look clean, move to p=quarantine, then p=reject.")]
    if not policy:
        return [Finding(
            "dmarc_malformed", "warning", "DMARC record has no policy",
            "There is a record but no p= setting, so receivers cannot tell what you want.",
            "Add p=none, p=quarantine or p=reject to the record.")]
    return []


def evaluate_dkim(selector: str | None) -> list[Finding]:
    if selector:
        return []
    # Deliberately not "you have no DKIM". The selector is chosen by whoever configured
    # the mail server, so a missing answer proves nothing — claiming otherwise would send
    # a customer to fix something that is not broken.
    # Severity is INFO, not warning, on purpose. A DKIM selector is an arbitrary name
    # chosen by whoever set the mail up — it is not discoverable, so failing to find one
    # says nothing about the domain. Grading a domain down for OUR inability to guess put
    # "at risk" on google.com in live testing, which means it would put "at risk" on most
    # domains an agency manages. A screen where nearly everything is amber is a screen
    # nobody reads, and the one domain genuinely at risk gets ignored with the rest.
    return [Finding(
        "dkim_unknown", "info", "Could not find a DKIM signature record",
        "DKIM signs your mail so receivers can tell it really came from you. We checked "
        "the usual names and found none — it may exist under a name we did not try.",
        "Check your mail server's DKIM settings for the selector it uses, and confirm "
        "that record is published.")]


def evaluate_mx(hosts: list[str]) -> list[Finding]:
    if not hosts:
        return [Finding(
            "mx_missing", "info", "This domain does not receive email",
            "There is no MX record, so nothing accepts mail for it. That is fine if the "
            "domain only sends, or only serves a website.",
            "")]
    return []


def classify_blocklist_answer(answers: list[str]) -> str:
    """What a blocklist's reply actually means: "listed", "clean" or "refused".

    The trap that nearly shipped. A blocklist answers in 127.0.0.0/8, and the last octet
    is the meaning — 127.0.0.2 upwards is a real listing, but 127.255.255.x means "we did
    not answer your question": usually because the query came through a public resolver,
    which is exactly how a hosted product asks. Treating any reply as a listing reported
    Google and GitHub as blocklisted, and would have told nearly every customer their mail
    was blocked. A false alarm here destroys trust in every other alert we send.
    """
    if not answers:
        return "clean"
    for a in answers:
        parts = a.split(".")
        if len(parts) != 4 or parts[0] != "127":
            continue
        if parts[1] == "255":            # 127.255.255.x — the query was refused
            return "refused"
        try:
            if int(parts[3]) >= 2:       # 127.0.0.2 and up — a genuine listing
                return "listed"
        except ValueError:
            continue
    return "refused"


def evaluate_blocklists(listed: list[str], ip: str | None,
                        unchecked: list[str] | None = None) -> list[Finding]:
    if not listed:
        # Silence would be a false all-clear, so say so — but only when NOTHING could be
        # checked. Mentioning one refused list every time would be noise.
        if unchecked and len(unchecked) >= len(BLOCKLISTS):
            return [Finding(
                "blocklist_unchecked", "info", "Could not check the spam blocklists",
                "The lists did not answer our queries, which usually means they refuse "
                "requests from shared resolvers. This is not a sign of a problem — we "
                "simply could not confirm either way.", "")]
        return []
    return [Finding(
        "blocklisted", "critical",
        f"This server's address is on {len(listed)} blocklist"
        f"{'' if len(listed) == 1 else 's'}",
        f"{ip} appears on {', '.join(listed)}. Mail from it is being rejected or sent "
        "straight to spam by anyone who uses those lists — which is most large providers.",
        "Find what sent the spam (often a hacked website or a compromised mailbox), fix "
        "it, then request removal on each list's website.")]


def summarise(health: MailHealth) -> str:
    """One sentence for the top of the panel."""
    bad = [f for f in health.findings if f.severity == "critical"]
    warn = [f for f in health.findings if f.severity == "warning"]
    if bad:
        return (f"Email from {health.domain} is likely to be rejected or land in spam — "
                f"{len(bad)} serious problem{'' if len(bad) == 1 else 's'} to fix.")
    if warn:
        return (f"Email from {health.domain} works, but {len(warn)} thing"
                f"{' is' if len(warn) == 1 else 's are'} weaker than it should be.")
    return f"Email from {health.domain} is set up correctly."


def should_alert(previous: str | None, current: str) -> bool:
    """Only when it gets worse.

    Same rule as uptime, certificates and threats. A domain that has been "at risk" for a
    month must not email about it every day, or the one that matters gets filtered.
    """
    rank = {"ok": 0, "at risk": 1, "failing": 2}
    return rank.get(current, 0) > rank.get(previous or "ok", 0)


# ── reading the real world ────────────────────────────────────────────────────
#
# Separated from the judgement above so every rule can be tested without a network, and so
# a resolver failure can never be mistaken for a finding.

def _resolver():
    import dns.resolver
    r = dns.resolver.Resolver()
    r.timeout = 4
    r.lifetime = 6
    return r


def _txt(name: str) -> list[str]:
    """TXT records, joined the way the standard requires (long ones arrive in chunks)."""
    import dns.resolver
    try:
        answers = _resolver().resolve(name, "TXT")
    except Exception:  # noqa: BLE001 — every failure means "nothing to report", not an error
        return []
    out = []
    for rdata in answers:
        parts = [p.decode() if isinstance(p, bytes) else str(p) for p in rdata.strings]
        out.append("".join(parts))
    return out


def _mx(domain: str) -> list[str]:
    try:
        return sorted(str(r.exchange).rstrip(".") for r in _resolver().resolve(domain, "MX"))
    except Exception:  # noqa: BLE001
        return []


def _a(name: str) -> str | None:
    try:
        return str(_resolver().resolve(name, "A")[0])
    except Exception:  # noqa: BLE001
        return None


def _find_dkim(domain: str) -> str | None:
    for selector in COMMON_DKIM_SELECTORS:
        for record in _txt(f"{selector}._domainkey.{domain}"):
            if "v=dkim1" in record.lower() or "p=" in record.lower():
                return selector
    return None


def _blocklist_check(ip: str) -> tuple[list[str], list[str]]:
    """Returns (lists this address is on, lists that would not answer).

    A list that does not answer is NOT a clean result and NOT a listing — it is a question
    we failed to ask, and the two must not be confused. Being wrong towards "not listed"
    costs a missed warning; being wrong the other way tells a customer their mail is
    blocked when it is fine.
    """
    listed: list[str] = []
    refused: list[str] = []
    try:
        reversed_ip = ".".join(reversed(ip.split(".")))
    except Exception:  # noqa: BLE001
        return [], []
    for zone, label in BLOCKLISTS:
        try:
            answers = [str(a) for a in _resolver().resolve(f"{reversed_ip}.{zone}", "A")]
        except Exception:  # noqa: BLE001 — no record at all is the "clean" answer
            continue
        verdict = classify_blocklist_answer(answers)
        if verdict == "listed":
            listed.append(label)
        elif verdict == "refused":
            refused.append(label)
    return listed, refused


async def check_domain(domain: str, *, sending_ip: str | None = None) -> MailHealth:
    """Everything, for one domain. Read-only and entirely off the customer's server."""
    import asyncio

    def work() -> MailHealth:
        health = MailHealth(domain=domain)
        health.mx_hosts = _mx(domain)
        health.has_mx = bool(health.mx_hosts)

        txt = _txt(domain)
        spf_records = [r for r in txt if r.lower().startswith("v=spf1")]
        health.spf = spf_records[0] if spf_records else None

        dmarc = [r for r in _txt(f"_dmarc.{domain}") if r.lower().startswith("v=dmarc1")]
        health.dmarc = dmarc[0] if dmarc else None

        health.dkim_selector = _find_dkim(domain)

        # Which address actually sends. The MX host is the best guess when the caller has
        # not told us — a domain's own A record is often a web server that never sends.
        ip = sending_ip or (_a(health.mx_hosts[0]) if health.mx_hosts else None)
        health.sending_ip = ip
        health.blocklisted_on, unchecked = _blocklist_check(ip) if ip else ([], [])

        health.findings = (
            evaluate_mx(health.mx_hosts)
            + evaluate_spf(spf_records)
            + evaluate_dkim(health.dkim_selector)
            + evaluate_dmarc(health.dmarc)
            + evaluate_blocklists(health.blocklisted_on, ip, unchecked)
        )
        return health

    return await asyncio.to_thread(work)


def clean_domain_for_mail(value: str) -> str:
    """The same cleaning the Sites page uses — one rule for what a domain is."""
    from app.services import site_service
    try:
        return site_service.clean_domain(value)
    except site_service.InvalidDomain as exc:
        raise ValueError(str(exc)) from exc
