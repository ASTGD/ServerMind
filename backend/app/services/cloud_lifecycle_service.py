"""Create, restart, resize and destroy cloud servers.

Until now a connected cloud account could only be *read* — discover what is there and
import it. This adds the other half, and it is the most dangerous thing in the product:
creating a server spends the customer's money, and destroying one deletes their data with
no undo anywhere in the system.

So the guards are the feature, and each is aimed at a specific real accident.

**Destroying the wrong server.** The classic loss is not "I meant not to destroy it", it
is "I destroyed the one next to it" — a stale list, a mis-click, an id that moved. So a
destroy re-reads the instance from the provider *at that moment* and refuses unless the
name the caller typed matches the name the provider just returned. A list loaded five
minutes ago cannot destroy anything, and a typo cannot either.

**Paying twice.** Neither DigitalOcean nor Hetzner offers an idempotency key on create, so
a retried request — a double click, a flaky connection, an impatient customer — makes a
second server that bills forever and that nobody is looking at. Before creating we check
the account for that exact name and refuse a duplicate.

**A resize that cannot be undone.** Both providers can grow a server's disk, and on both
that is permanent: the disk can never shrink again, so the server can never return to a
cheaper size. The same API call *without* the disk is fully reversible. Those two are one
checkbox apart and read almost identically, so `resize_plan` states plainly which one is
being asked for and refuses to describe a one-way change as reversible.

Only DigitalOcean and Hetzner are covered. AWS, Google Cloud and Azure need networks,
security groups, images and disks decided before a machine can exist at all — a half-built
version of that would fail in ways a customer could not recover from, so they stay
import-only and say so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import requests

from app.services.cloud_service import (
    CloudError, DigitalOceanAdapter, HetznerAdapter, Instance, _TokenAdapter,
)

LIFECYCLE_PROVIDERS = ("digitalocean", "hetzner")

REBOOT = "reboot"
POWER_ON = "power_on"
POWER_OFF = "power_off"
RESIZE = "resize"
DESTROY = "destroy"

# A name is shown back to the customer and sent to a provider that has its own rules.
# Refused rather than cleaned up: silently changing what someone typed means the server
# they look for later is not the one they made.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,62}$")


class InvalidRequest(ValueError):
    """The request is not something we are willing to send to a provider."""


class WouldDestroyWrongServer(Exception):
    """The confirmation does not match the server we are about to delete."""


@dataclass
class SizeOption:
    slug: str
    label: str
    vcpus: int
    memory_mb: int
    disk_gb: int
    price_monthly: float | None = None
    currency: str = "USD"
    available: bool = True


@dataclass
class Catalogue:
    regions: list[dict] = field(default_factory=list)
    sizes: list[SizeOption] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    ssh_keys: list[dict] = field(default_factory=list)


@dataclass
class ResizePlan:
    """What a resize will actually do — in the customer's terms, not the API's."""
    from_size: str
    to_size: str
    grows_disk: bool
    reversible: bool
    needs_power_off: bool
    warning: str = ""
    price_change: str = ""


# ── validation ────────────────────────────────────────────────────────────────
def valid_name(name: str) -> str:
    raw = (name or "").strip()
    if not _NAME_RE.match(raw):
        raise InvalidRequest(
            "A server name can use letters, numbers, dots and dashes, must start with a "
            "letter or number, and can be up to 63 characters.")
    return raw


def valid_slug(value: str, what: str) -> str:
    raw = (value or "").strip()
    if not raw or not re.match(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,63}$", raw):
        raise InvalidRequest(f"Choose a {what}.")
    return raw


# ── the guards ────────────────────────────────────────────────────────────────
def resize_plan(current: SizeOption | None, target: SizeOption | None,
                *, grow_disk: bool) -> ResizePlan:
    """Describe a resize honestly, before it happens.

    The disk is the whole point. Growing it is permanent on both providers — the server
    can never go back to a smaller, cheaper size — while the same call without it can be
    undone at any time. One checkbox apart, so it has to be said in words.
    """
    if current is None or target is None:
        raise InvalidRequest("That size is not offered for this server.")
    if current.slug == target.slug:
        raise InvalidRequest("That is the size it is already.")

    shrinking_disk = target.disk_gb < current.disk_gb
    if shrinking_disk and not grow_disk:
        # Keeping the existing disk while moving to a plan with a smaller one is what
        # both APIs actually do, and it is fine — but a customer reading "40 GB" on the
        # new plan and keeping 80 GB deserves to be told, not surprised on the invoice.
        pass
    if shrinking_disk and grow_disk:
        raise InvalidRequest(
            f"{target.label} has a smaller disk ({target.disk_gb} GB) than this server "
            f"already uses ({current.disk_gb} GB). A disk can be made bigger but never "
            "smaller, so this size cannot be applied with the disk included.")

    plan = ResizePlan(
        from_size=current.slug, to_size=target.slug,
        grows_disk=grow_disk,
        reversible=not grow_disk,
        needs_power_off=True,          # true on both providers, always
    )
    if grow_disk:
        plan.warning = (
            "This includes the bigger disk, which is permanent. The server can never be "
            "moved back to a smaller or cheaper size afterwards. Leave the disk out if "
            "you want to be able to undo this.")
    else:
        plan.warning = (
            "Only processor and memory change; the disk stays as it is. This can be "
            "undone later.")
    if current.price_monthly is not None and target.price_monthly is not None:
        diff = target.price_monthly - current.price_monthly
        word = "more" if diff > 0 else "less"
        plan.price_change = (
            f"About {abs(diff):.2f} {target.currency} a month {word} "
            f"({current.price_monthly:.2f} → {target.price_monthly:.2f}).")
    return plan


def check_destroy(live: Instance | None, typed_name: str) -> None:
    """Refuse unless the caller named the server the provider is showing us right now.

    Read fresh, on purpose. Matching against a list the browser loaded earlier would let
    a page that is minutes out of date delete something that has since been renamed or
    replaced — and the failure is not recoverable from anywhere in this product.
    """
    if live is None:
        raise WouldDestroyWrongServer(
            "That server is not in this cloud account any more. Reload the list — it may "
            "already have been deleted.")
    typed = (typed_name or "").strip()
    if not typed:
        raise WouldDestroyWrongServer(
            f"To delete a server, type its name exactly: {live.name}")
    if typed != live.name:
        raise WouldDestroyWrongServer(
            f"That name does not match. This server is called “{live.name}”. Deleting it "
            "erases its disk permanently, so the name has to match exactly.")


def check_duplicate_name(existing: list[Instance], name: str) -> None:
    """Refuse a second server with a name the account already uses.

    Neither provider offers an idempotency key on create, so a retried request bills a
    second machine forever. The name is the only thing we can match on, and a duplicate
    name is nearly always a repeat of the same click rather than an intention.
    """
    clash = next((i for i in existing if i.name == name), None)
    if clash:
        raise InvalidRequest(
            f"There is already a server called “{name}” in this account "
            f"({clash.public_ip or clash.instance_id}). Pick a different name — if you "
            "just pressed create, it may already have worked.")


# ── provider adapters ─────────────────────────────────────────────────────────
class _LifecycleAdapter(_TokenAdapter):
    def _send(self, method: str, url: str, payload: dict | None = None,
              timeout: int = 40) -> dict:
        try:
            r = requests.request(method, url, headers=self._headers(), json=payload,
                                 timeout=timeout)
        except requests.RequestException as exc:
            raise CloudError(f"Could not reach {self.PROVIDER}: {exc}")
        if r.status_code in (401, 403):
            raise CloudError(
                f"{self.PROVIDER} rejected this API token. Creating and deleting servers "
                "needs a token with WRITE access — a read-only token can list them but "
                "cannot change anything.")
        if r.status_code == 404:
            raise CloudError(f"{self.PROVIDER} does not have that server any more.")
        if r.status_code == 422 or r.status_code == 409:
            raise CloudError(f"{self.PROVIDER} refused: {_friendly(r.text)}")
        if r.status_code == 429:
            raise CloudError(
                f"{self.PROVIDER} is rate-limiting this account. Wait a minute and try again.")
        if r.status_code >= 400:
            raise CloudError(f"{self.PROVIDER} error {r.status_code}: {_friendly(r.text)}")
        if r.status_code == 204 or not (r.text or "").strip():
            return {}
        try:
            return r.json()
        except ValueError:
            raise CloudError(f"{self.PROVIDER} returned an unexpected response.")

    # Each provider implements these four.
    def catalogue(self) -> Catalogue: raise CloudError("not supported")
    def create(self, spec: dict) -> Instance: raise CloudError("not supported")
    def get(self, instance_id: str) -> Instance | None: raise CloudError("not supported")
    def act(self, instance_id: str, action: str, **kw) -> None: raise CloudError("not supported")
    def destroy(self, instance_id: str) -> None: raise CloudError("not supported")


def _friendly(body: str) -> str:
    """Providers return JSON errors; the message is the only part worth showing."""
    text = (body or "")[:400]
    m = re.search(r'"message"\s*:\s*"([^"]{3,300})"', text)
    return m.group(1) if m else text.strip() or "no reason given"


class DOLifecycle(_LifecycleAdapter, DigitalOceanAdapter):
    """Adds the write half to the existing read adapter.

    Inherited rather than reimplemented so `list_instances` is the real one. It
    was not, and the base class's polite "not supported" stub still satisfied a
    `hasattr` check — which quietly turned the duplicate-create guard off and let
    a repeated request bill a second server.
    """

    BASE = "https://api.digitalocean.com"
    PROVIDER = "DigitalOcean"

    def catalogue(self) -> Catalogue:
        regions = [
            {"slug": r["slug"], "label": r.get("name", r["slug"]),
             "available": bool(r.get("available", True)), "sizes": r.get("sizes", [])}
            for r in self._get(f"{self.BASE}/v2/regions?per_page=100").get("regions", [])
        ]
        sizes = [
            SizeOption(slug=s["slug"],
                       label=f'{s.get("vcpus")} vCPU · {int(s.get("memory", 0)) // 1024} GB RAM '
                             f'· {s.get("disk")} GB disk',
                       vcpus=int(s.get("vcpus") or 0),
                       memory_mb=int(s.get("memory") or 0),
                       disk_gb=int(s.get("disk") or 0),
                       price_monthly=s.get("price_monthly"),
                       available=bool(s.get("available", True)))
            for s in self._get(f"{self.BASE}/v2/sizes?per_page=300").get("sizes", [])
        ]
        images = [
            {"slug": i.get("slug") or str(i.get("id")),
             "label": f'{i.get("distribution", "")} {i.get("name", "")}'.strip()}
            for i in self._get(
                f"{self.BASE}/v2/images?type=distribution&per_page=200").get("images", [])
            if i.get("slug")
        ]
        keys = [{"id": str(k.get("id")), "label": k.get("name", "")}
                for k in self._get(f"{self.BASE}/v2/account/keys?per_page=200").get("ssh_keys", [])]
        return Catalogue(regions=regions, sizes=sizes, images=images, ssh_keys=keys)

    def create(self, spec: dict) -> Instance:
        body = {"name": spec["name"], "region": spec["region"], "size": spec["size"],
                "image": spec["image"], "monitoring": True}
        if spec.get("ssh_keys"):
            body["ssh_keys"] = spec["ssh_keys"]
        if spec.get("user_data"):
            body["user_data"] = spec["user_data"]
        d = self._send("POST", f"{self.BASE}/v2/droplets", body).get("droplet") or {}
        return self._map(d)

    def get(self, instance_id: str) -> Instance | None:
        try:
            d = self._send("GET", f"{self.BASE}/v2/droplets/{instance_id}").get("droplet")
        except CloudError as exc:
            if "any more" in str(exc):
                return None
            raise
        return self._map(d) if d else None

    def act(self, instance_id: str, action: str, **kw) -> None:
        url = f"{self.BASE}/v2/droplets/{instance_id}/actions"
        if action == REBOOT:
            self._send("POST", url, {"type": "reboot"})
        elif action == POWER_ON:
            self._send("POST", url, {"type": "power_on"})
        elif action == POWER_OFF:
            self._send("POST", url, {"type": "power_off"})
        elif action == RESIZE:
            # `disk` is the irreversible half; it is passed through explicitly so the
            # decision made in resize_plan is the one that reaches the API.
            self._send("POST", url, {"type": "resize", "size": kw["size"],
                                     "disk": bool(kw.get("grow_disk"))})
        else:
            raise InvalidRequest(f"Unknown action “{action}”.")

    def destroy(self, instance_id: str) -> None:
        self._send("DELETE", f"{self.BASE}/v2/droplets/{instance_id}")


class HetznerLifecycle(_LifecycleAdapter, HetznerAdapter):
    BASE = "https://api.hetzner.cloud"
    PROVIDER = "Hetzner"

    def catalogue(self) -> Catalogue:
        regions = [{"slug": l["name"], "label": f'{l.get("city", "")}, {l.get("country", "")}'.strip(", "),
                    "available": True}
                   for l in self._get(f"{self.BASE}/v1/locations").get("locations", [])]
        sizes = []
        for s in self._get(f"{self.BASE}/v1/server_types?per_page=100").get("server_types", []):
            price = None
            for p in (s.get("prices") or []):
                gross = (p.get("price_monthly") or {}).get("gross")
                if gross:
                    price = float(gross)
                    break
            sizes.append(SizeOption(
                slug=s["name"],
                label=f'{s.get("cores")} vCPU · {s.get("memory")} GB RAM · {s.get("disk")} GB disk',
                vcpus=int(s.get("cores") or 0),
                memory_mb=int(float(s.get("memory") or 0) * 1024),
                disk_gb=int(s.get("disk") or 0),
                price_monthly=price, currency="EUR",
                available=not s.get("deprecated")))
        images = [{"slug": i.get("name") or str(i.get("id")),
                   "label": i.get("description") or i.get("name", "")}
                  for i in self._get(
                      f"{self.BASE}/v1/images?type=system&per_page=100").get("images", [])]
        keys = [{"id": str(k.get("id")), "label": k.get("name", "")}
                for k in self._get(f"{self.BASE}/v1/ssh_keys?per_page=100").get("ssh_keys", [])]
        return Catalogue(regions=regions, sizes=sizes, images=images, ssh_keys=keys)

    def create(self, spec: dict) -> Instance:
        body = {"name": spec["name"], "server_type": spec["size"],
                "image": spec["image"], "location": spec["region"],
                "start_after_create": True}
        if spec.get("ssh_keys"):
            body["ssh_keys"] = [int(k) if str(k).isdigit() else k for k in spec["ssh_keys"]]
        if spec.get("user_data"):
            body["user_data"] = spec["user_data"]
        s = self._send("POST", f"{self.BASE}/v1/servers", body).get("server") or {}
        return self._map(s)

    def get(self, instance_id: str) -> Instance | None:
        try:
            s = self._send("GET", f"{self.BASE}/v1/servers/{instance_id}").get("server")
        except CloudError as exc:
            if "any more" in str(exc):
                return None
            raise
        return self._map(s) if s else None

    def act(self, instance_id: str, action: str, **kw) -> None:
        base = f"{self.BASE}/v1/servers/{instance_id}/actions"
        if action == REBOOT:
            self._send("POST", f"{base}/reboot")
        elif action == POWER_ON:
            self._send("POST", f"{base}/poweron")
        elif action == POWER_OFF:
            # Hetzner's `poweroff` is the equivalent of pulling the plug; `shutdown` asks
            # the operating system first. Asking first is the right default — a hard cut
            # can corrupt a database that was mid-write.
            self._send("POST", f"{base}/shutdown")
        elif action == RESIZE:
            self._send("POST", f"{base}/change_type",
                       {"server_type": kw["size"], "upgrade_disk": bool(kw.get("grow_disk"))})
        else:
            raise InvalidRequest(f"Unknown action “{action}”.")

    def destroy(self, instance_id: str) -> None:
        self._send("DELETE", f"{self.BASE}/v1/servers/{instance_id}")


_LIFECYCLE = {"digitalocean": DOLifecycle, "hetzner": HetznerLifecycle}


def supports_lifecycle(provider: str) -> bool:
    return (provider or "").lower() in _LIFECYCLE


def adapter(provider: str, cred: dict) -> _LifecycleAdapter:
    cls = _LIFECYCLE.get((provider or "").lower())
    if cls is None:
        raise InvalidRequest(
            f"ServerAlly can list servers on {provider} but cannot create or delete them "
            "there yet. That works on DigitalOcean and Hetzner today.")
    return cls(cred)


def size_by_slug(cat: Catalogue, slug: str) -> SizeOption | None:
    return next((s for s in cat.sizes if s.slug == slug), None)
