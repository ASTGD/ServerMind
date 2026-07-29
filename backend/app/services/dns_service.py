"""DNS management — read and change records at the provider that hosts the domain.

Until now Ally could only *read* DNS. Pointing a new site, fixing a wrong A record or
adding a TXT record for mail meant leaving ServerAlly, which is exactly the moment a
non-technical owner gets stuck.

**Why this is the most dangerous screen in the product.** A wrong A record does not
break slowly — the site is unreachable worldwide within seconds, and the TTL keeps it
that way even after the mistake is spotted. So validation is not a nicety here, it is
the feature:

* every record type is checked against what it is actually allowed to contain, because
  providers accept plenty that does not work (a CNAME holding an IP is accepted by the
  API and silently breaks the domain);
* a CNAME at the zone apex is refused outright — it is invalid per RFC 1034 and takes
  down mail along with the website;
* NS and SOA records are read-only through us. Editing them is how a domain leaves your
  control entirely, and no owner-facing screen has business offering it.

Providers are adapters over one interface, following ``cloud_service``: credentials are
AES-256-GCM at rest, never returned by any endpoint, and every network call is wrapped
so a provider outage surfaces as a sentence rather than a stack trace.
"""
from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass

import requests

from app.models.dns_account import DnsAccount
from app.services.crypto_service import decrypt

# Types an owner can safely manage. NS and SOA are deliberately absent — see the module
# docstring. DNSSEC records are absent for the same reason.
EDITABLE_TYPES = ("A", "AAAA", "CNAME", "TXT", "MX", "SRV", "CAA", "NS_READONLY")
MANAGED_TYPES = ("A", "AAAA", "CNAME", "TXT", "MX", "SRV", "CAA")
READONLY_TYPES = ("NS", "SOA", "DNSKEY", "DS", "RRSIG")

_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-_]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-_]{1,63}(?<!-))*\.?$"
)

MAX_TXT = 2048
MIN_TTL = 60


class DnsError(Exception):
    """Something the owner can act on — never a raw provider exception."""


class InvalidRecord(ValueError):
    """The record would not work, or would break the domain."""


def _looks_like_ip(value: str) -> bool:
    """True if the value parses as an IP address.

    A separate helper on purpose. InvalidRecord subclasses ValueError, so raising it
    inside a `try: ip_address(v) ... except ValueError` block means our own exception is
    swallowed by our own handler and the check quietly passes — which is exactly what
    happened, and what the CNAME/MX tests caught.
    """
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _is_ipv4(value: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError:
        return False


def _is_ipv6(value: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv6Address)
    except ValueError:
        return False


@dataclass
class Zone:
    zone_id: str
    name: str
    status: str = "active"
    records: int | None = None


@dataclass
class Record:
    record_id: str
    type: str
    name: str
    content: str
    ttl: int = 300
    priority: int | None = None
    proxied: bool | None = None      # Cloudflare-specific; None elsewhere
    editable: bool = True


def normalise_name(name: str, zone: str) -> str:
    """Return the fully-qualified record name.

    Owners type "www", "www.example.com" and "@" to mean the same three things, and a
    provider that receives the wrong one creates ``www.example.com.example.com`` without
    complaint. Normalising here means that mistake cannot be made through us.
    """
    n = (name or "").strip().rstrip(".").lower()
    z = (zone or "").strip().rstrip(".").lower()
    if not n or n == "@":
        return z
    if n == z or n.endswith("." + z):
        return n
    return f"{n}.{z}"


def is_apex(name: str, zone: str) -> bool:
    return normalise_name(name, zone) == (zone or "").strip().rstrip(".").lower()


def validate(*, type_: str, name: str, content: str, zone: str,
             ttl: int = 300, priority: int | None = None) -> dict:
    """Check a record would actually work. Raises ``InvalidRecord`` with a plain reason.

    Providers are permissive; this is where the real checking happens. Every rule below
    exists because the provider would have accepted the value and the domain would have
    broken quietly.
    """
    t = (type_ or "").strip().upper()
    if t in READONLY_TYPES:
        raise InvalidRecord(
            f"{t} records are managed by your DNS provider and can't be changed here. "
            "Editing them is how a domain stops working entirely.")
    if t not in MANAGED_TYPES:
        raise InvalidRecord(f"“{type_}” isn’t a record type we manage.")

    value = (content or "").strip()
    if not value:
        raise InvalidRecord("This record needs a value.")

    if ttl and int(ttl) != 1 and int(ttl) < MIN_TTL:   # 1 = "automatic" at Cloudflare
        raise InvalidRecord(f"TTL must be at least {MIN_TTL} seconds (or automatic).")

    # Parsed once, outside any try/except that could swallow our own InvalidRecord —
    # the same trap that silently disabled the CNAME and MX checks.
    if t == "A":
        if not _is_ipv4(value):
            raise InvalidRecord(
                f"“{value}” isn’t an IPv4 address. An A record points a name at an "
                "address like 203.0.113.10.")
    elif t == "AAAA":
        if not _is_ipv6(value):
            raise InvalidRecord(
                f"“{value}” isn’t an IPv6 address. An AAAA record needs one like "
                "2001:db8::1.")
    elif t == "CNAME":
        # Two failures a provider will happily accept and which break the domain.
        if is_apex(name, zone):
            raise InvalidRecord(
                "You can't put a CNAME on the domain itself — it breaks email and other "
                "records for the whole domain. Use an A record pointing at the server's "
                "IP address instead.")
        if _looks_like_ip(value):
            raise InvalidRecord(
                "A CNAME points at another NAME, not an IP address. Use an A record for "
                f"{value}.")
        if not _HOSTNAME.match(value):
            raise InvalidRecord(f"“{value}” isn’t a valid hostname.")
    elif t == "MX":
        if priority is None:
            raise InvalidRecord("An MX record needs a priority (10 is the usual choice).")
        if not 0 <= int(priority) <= 65535:
            raise InvalidRecord("MX priority must be between 0 and 65535.")
        if _looks_like_ip(value):
            raise InvalidRecord(
                "An MX record must point at a hostname, not an IP address — mail servers "
                "that receive an IP here will reject your mail.")
        if not _HOSTNAME.match(value):
            raise InvalidRecord(f"“{value}” isn’t a valid mail server hostname.")
    elif t == "TXT":
        if len(value) > MAX_TXT:
            raise InvalidRecord(f"TXT records can be up to {MAX_TXT} characters.")
    elif t == "CAA":
        if not re.match(r"^\d+\s+\S+\s+", value):
            raise InvalidRecord(
                'A CAA record looks like: 0 issue "letsencrypt.org".')
    elif t == "SRV":
        if priority is None:
            raise InvalidRecord("An SRV record needs a priority.")

    return {"type": t, "name": normalise_name(name, zone), "content": value,
            "ttl": int(ttl or 300), "priority": priority}


def warn_for(*, type_: str, name: str, zone: str, existing: list[Record] | None = None) -> str | None:
    """A heads-up shown BEFORE a change, not an error.

    The point is that a correct-looking edit can still be the one that takes the site
    down, and the owner deserves to know which of those they are about to make.
    """
    t = (type_ or "").upper()
    if t == "A" and is_apex(name, zone):
        return ("This is the main address for the whole domain. If it's wrong the site "
                "goes offline everywhere, and it can take up to the TTL to come back.")
    if t == "MX":
        return "Changing MX records affects where your email is delivered."
    if t == "A" and normalise_name(name, zone).startswith("www."):
        return "This is the address visitors reach at www — double-check the IP."
    return None


# ── providers ─────────────────────────────────────────────────────────────────
class _Adapter:
    def __init__(self, cred: dict):
        self.cred = cred or {}

    def verify(self) -> dict: raise NotImplementedError
    def list_zones(self) -> list[Zone]: raise NotImplementedError
    def list_records(self, zone_id: str) -> list[Record]: raise NotImplementedError
    def create_record(self, zone_id: str, rec: dict) -> Record: raise NotImplementedError
    def update_record(self, zone_id: str, record_id: str, rec: dict) -> Record:
        raise NotImplementedError
    def delete_record(self, zone_id: str, record_id: str) -> None: raise NotImplementedError


class CloudflareAdapter(_Adapter):
    """Cloudflare DNS. Free, and the provider this market actually uses."""

    BASE = "https://api.cloudflare.com/client/v4"
    PROVIDER = "Cloudflare"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.cred.get('api_token', '')}",
                "Content-Type": "application/json"}

    @staticmethod
    def _reason(response) -> str:
        """Cloudflare's own explanation, with a hint only where one genuinely helps."""
        try:
            errs = (response.json() or {}).get("errors") or []
        except ValueError:
            errs = []
        # Cloudflare nests the SPECIFIC reason inside error_chain and puts a generic one
        # on top: "Invalid request headers" outside, "Invalid format for Authorization
        # header" inside. The inner one is the only part a customer can act on.
        flat = []
        for e in errs:
            flat.append(e)
            flat.extend(e.get("error_chain") or [])
        codes = {e.get("code") for e in flat}
        seen, parts = set(), []
        for e in flat:
            m = (e.get("message") or "").strip()
            if m and m not in seen:
                seen.add(m)
                parts.append(m)
        msg = " — ".join(parts)
        if not msg:
            msg = f"HTTP {response.status_code} with no explanation."
        if 9109 in codes or 10000 in codes:
            msg += (" — the token is valid but not allowed to do this. Check it includes "
                    "Zone:Read and DNS:Edit for the zones you want to manage.")
        elif 6111 in codes or 1000 in codes:
            msg += (" — this usually means the value pasted is not the token itself. "
                    "Copy it again from Cloudflare; it is shown only once.")
        return msg

    def _call(self, method: str, path: str, body: dict | None = None,
              timeout: int = 20) -> dict:
        try:
            r = requests.request(method, f"{self.BASE}{path}", headers=self._headers(),
                                 json=body, timeout=timeout)
        except requests.RequestException as exc:
            raise DnsError(f"Could not reach {self.PROVIDER}: {exc}")
        if r.status_code in (401, 403):
            # Cloudflare says exactly what is wrong — an expired token, a revoked one, a
            # missing permission, an IP restriction — and each needs a different fix. The
            # old code threw that away and guessed "wrong permissions" for all of them,
            # which sent a customer with a perfectly good token to re-make it.
            raise DnsError(f"{self.PROVIDER} rejected this API token: {self._reason(r)}")
        try:
            data = r.json()
        except ValueError:
            raise DnsError(f"{self.PROVIDER} returned an unexpected response.")
        if not data.get("success", r.status_code < 400):
            # Same helper as the 401/403 path — Cloudflare returns a bad token as a 400
            # "Invalid request headers", which tells a customer nothing on its own.
            raise DnsError(f"{self.PROVIDER}: {self._reason(r)}")
        return data

    def verify(self) -> dict:
        """Prove the token can do what we need — by doing it.

        This used to call `/user/tokens/verify`, which asks Cloudflare about the token
        itself and needs permissions our feature never uses. A token scoped only to zones
        and DNS — exactly the token our own instructions ask for — was refused by that
        endpoint and reported as having the wrong permissions, while being perfectly
        capable of everything we do with it.

        Listing zones is the capability the whole feature rests on, so it is the honest
        test: if this works, the connection works.
        """
        data = self._call("GET", "/zones?per_page=1")
        info = data.get("result_info") or {}
        return {"provider": self.PROVIDER, "status": "active",
                "zones": info.get("total_count", len(data.get("result") or []))}

    def list_zones(self) -> list[Zone]:
        out, page = [], 1
        while True:
            data = self._call("GET", f"/zones?per_page=50&page={page}")
            for z in data.get("result", []):
                out.append(Zone(zone_id=z["id"], name=z["name"],
                                status=z.get("status", "active")))
            info = data.get("result_info") or {}
            if page >= (info.get("total_pages") or 1):
                break
            page += 1
        return out

    @staticmethod
    def _map(r: dict) -> Record:
        t = (r.get("type") or "").upper()
        return Record(
            record_id=r["id"], type=t, name=r.get("name", ""),
            content=r.get("content", ""), ttl=r.get("ttl", 300),
            priority=r.get("priority"), proxied=r.get("proxied"),
            # Read-only types are still SHOWN — an owner needs to see their nameservers
            # even though changing them here would be reckless.
            editable=t in MANAGED_TYPES,
        )

    def list_records(self, zone_id: str) -> list[Record]:
        out, page = [], 1
        while True:
            data = self._call("GET", f"/zones/{zone_id}/dns_records?per_page=100&page={page}")
            out.extend(self._map(r) for r in data.get("result", []))
            info = data.get("result_info") or {}
            if page >= (info.get("total_pages") or 1):
                break
            page += 1
        return out

    def _body(self, rec: dict) -> dict:
        b = {"type": rec["type"], "name": rec["name"], "content": rec["content"],
             "ttl": rec.get("ttl") or 300}
        if rec.get("priority") is not None:
            b["priority"] = int(rec["priority"])
        if rec.get("proxied") is not None:
            b["proxied"] = bool(rec["proxied"])
        return b

    def create_record(self, zone_id: str, rec: dict) -> Record:
        data = self._call("POST", f"/zones/{zone_id}/dns_records", self._body(rec))
        return self._map(data["result"])

    def update_record(self, zone_id: str, record_id: str, rec: dict) -> Record:
        data = self._call("PUT", f"/zones/{zone_id}/dns_records/{record_id}",
                          self._body(rec))
        return self._map(data["result"])

    def delete_record(self, zone_id: str, record_id: str) -> None:
        self._call("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")


PROVIDERS = {"cloudflare": CloudflareAdapter}


def adapter_for(provider: str, cred: dict) -> _Adapter:
    cls = PROVIDERS.get((provider or "").lower())
    if not cls:
        raise DnsError(f"“{provider}” isn’t a DNS provider we support yet.")
    return cls(cred)


def _adapter(account: DnsAccount) -> _Adapter:
    return adapter_for(account.provider, json.loads(decrypt(account.encrypted_credential)))


# ── async wrappers: requests is blocking, the app is not ──────────────────────
async def _run(fn, *args):
    import asyncio
    return await asyncio.to_thread(fn, *args)


async def verify_credential(provider: str, cred: dict) -> dict:
    return await _run(adapter_for(provider, cred).verify)


async def list_zones(account: DnsAccount) -> list[Zone]:
    return await _run(_adapter(account).list_zones)


async def list_records(account: DnsAccount, zone_id: str) -> list[Record]:
    return await _run(_adapter(account).list_records, zone_id)


async def create_record(account: DnsAccount, zone_id: str, rec: dict) -> Record:
    return await _run(_adapter(account).create_record, zone_id, rec)


async def update_record(account: DnsAccount, zone_id: str, record_id: str,
                        rec: dict) -> Record:
    return await _run(_adapter(account).update_record, zone_id, record_id, rec)


async def delete_record(account: DnsAccount, zone_id: str, record_id: str) -> None:
    await _run(_adapter(account).delete_record, zone_id, record_id)


def public_account(a: DnsAccount) -> dict:
    """What an endpoint may return. An allowlist, not a model dump — the credential must
    never leave the server, and a field-by-field list is the only way that stays true
    when someone adds a column later."""
    return {"id": str(a.id), "provider": a.provider, "label": a.label,
            "created_at": a.created_at.isoformat() if a.created_at else None}


def public_record(r: Record) -> dict:
    return {"id": r.record_id, "type": r.type, "name": r.name, "content": r.content,
            "ttl": r.ttl, "priority": r.priority, "proxied": r.proxied,
            "editable": r.editable}
