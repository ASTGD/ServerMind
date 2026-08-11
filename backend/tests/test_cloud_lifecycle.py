"""Cloud lifecycle — the properties that stop a click from spending or deleting.

This is the only place in the product where a mistake costs money or erases a disk with
no undo. Three accidents are worth more testing than everything else combined: destroying
the wrong server, paying for a server nobody meant to make, and a resize that cannot be
reversed being presented as though it can.
"""
from __future__ import annotations

import pytest

from app.services import cloud_lifecycle_service as cl
from app.services.cloud_service import CloudError, Instance

from tests.routes import all_routes


def size(slug, vcpu=1, mem=1024, disk=25, price=6.0):
    return cl.SizeOption(slug=slug, label=slug, vcpus=vcpu, memory_mb=mem,
                         disk_gb=disk, price_monthly=price)


def inst(name="web-1", iid="123", ip="203.0.113.5"):
    return Instance(instance_id=iid, name=name, public_ip=ip, private_ip=None,
                    os="linux", state="running")


# ── destroy: the one that cannot be undone ───────────────────────────────────
def test_destroying_needs_the_exact_name():
    cl.check_destroy(inst("prod-db"), "prod-db")          # matches — allowed
    with pytest.raises(cl.WouldDestroyWrongServer):
        cl.check_destroy(inst("prod-db"), "prod-d")
    with pytest.raises(cl.WouldDestroyWrongServer):
        cl.check_destroy(inst("prod-db"), "PROD-DB")      # case is not close enough
    with pytest.raises(cl.WouldDestroyWrongServer):
        cl.check_destroy(inst("prod-db"), "")


def test_the_name_must_match_what_the_provider_says_right_now():
    """The real accident is deleting the server *next to* the one you meant. A list the
    browser loaded five minutes ago must not be able to delete anything."""
    live = inst("web-2")                                  # renamed since the page loaded
    with pytest.raises(cl.WouldDestroyWrongServer) as e:
        cl.check_destroy(live, "web-1")                   # what the stale page showed
    assert "web-2" in str(e.value), "tell them what it is actually called now"


def test_a_server_that_is_already_gone_is_not_treated_as_a_match():
    with pytest.raises(cl.WouldDestroyWrongServer) as e:
        cl.check_destroy(None, "web-1")
    assert "not in this cloud account" in str(e.value)


def test_the_refusal_says_the_disk_is_erased():
    """Someone typing a name into a delete box should be told what it costs them."""
    with pytest.raises(cl.WouldDestroyWrongServer) as e:
        cl.check_destroy(inst("shop"), "wrong")
    assert "permanently" in str(e.value)


# ── create: paying twice ─────────────────────────────────────────────────────
def test_a_repeated_create_is_refused_rather_than_billed():
    """Neither provider has an idempotency key, so a double-click makes a second server
    that bills forever and nobody watches."""
    existing = [inst("web-1"), inst("db-1", iid="9")]
    with pytest.raises(cl.InvalidRequest) as e:
        cl.check_duplicate_name(existing, "web-1")
    assert "already" in str(e.value)
    assert "may already have worked" in str(e.value), "say what probably happened"


def test_a_genuinely_new_name_is_allowed():
    cl.check_duplicate_name([inst("web-1")], "web-2")


@pytest.mark.parametrize("bad", [
    "", "   ", "-starts-with-dash", "has space", "a" * 64, "semi;colon",
    "quote'name", "$(id)", "../etc",
])
def test_a_name_a_provider_would_reject_is_refused_here_first(bad):
    with pytest.raises(cl.InvalidRequest):
        cl.valid_name(bad)


@pytest.mark.parametrize("good", ["web-1", "db.prod", "a", "A1", "x" * 63])
def test_ordinary_names_are_accepted(good):
    assert cl.valid_name(good) == good


def test_a_name_is_never_quietly_rewritten():
    """Cleaning up someone's typing means the server they look for later is not the one
    they made."""
    with pytest.raises(cl.InvalidRequest):
        cl.valid_name("my server")          # not silently turned into "my-server"


# ── resize: reversible or not ────────────────────────────────────────────────
def test_a_resize_without_the_disk_is_reversible():
    plan = cl.resize_plan(size("s-1vcpu", disk=25, price=6),
                          size("s-2vcpu", vcpu=2, disk=50, price=12), grow_disk=False)
    assert plan.reversible is True
    assert "undone" in plan.warning
    assert plan.needs_power_off is True, "both providers require it"


def test_a_resize_that_grows_the_disk_is_permanent_and_says_so():
    """One checkbox apart from the reversible one, and the difference is that the server
    can never move back to a cheaper size."""
    plan = cl.resize_plan(size("s-1vcpu", disk=25, price=6),
                          size("s-2vcpu", vcpu=2, disk=50, price=12), grow_disk=True)
    assert plan.reversible is False
    assert "permanent" in plan.warning
    assert "never" in plan.warning


def test_the_price_change_is_stated_in_money():
    plan = cl.resize_plan(size("small", price=6.0), size("big", vcpu=4, disk=80, price=24.0),
                          grow_disk=False)
    assert "18.00" in plan.price_change and "more" in plan.price_change


def test_a_downgrade_reads_as_cheaper_not_as_a_negative_number():
    plan = cl.resize_plan(size("big", vcpu=4, disk=80, price=24.0),
                          size("small", disk=80, price=6.0), grow_disk=False)
    assert "18.00" in plan.price_change and "less" in plan.price_change


def test_moving_to_a_smaller_disk_with_the_disk_included_is_refused():
    """A disk can grow and never shrink, so this combination cannot work — better to
    refuse with the reason than to let the provider fail halfway through."""
    with pytest.raises(cl.InvalidRequest) as e:
        cl.resize_plan(size("big", disk=160), size("small", disk=40), grow_disk=True)
    assert "never smaller" in str(e.value)


def test_keeping_a_bigger_disk_on_a_smaller_plan_is_allowed():
    """Both APIs do exactly this, and it is how a customer downgrades."""
    plan = cl.resize_plan(size("big", disk=160), size("small", disk=40), grow_disk=False)
    assert plan.reversible is True


def test_resizing_to_the_size_it_already_is_is_refused():
    with pytest.raises(cl.InvalidRequest):
        cl.resize_plan(size("s-1vcpu"), size("s-1vcpu"), grow_disk=False)


def test_an_unknown_size_is_refused_rather_than_guessed():
    with pytest.raises(cl.InvalidRequest):
        cl.resize_plan(size("s-1vcpu"), None, grow_disk=False)


# ── which providers ──────────────────────────────────────────────────────────
def test_only_the_two_providers_we_actually_built_are_offered():
    assert cl.supports_lifecycle("digitalocean") and cl.supports_lifecycle("hetzner")
    for p in ("aws", "gcp", "azure", "", "linode"):
        assert not cl.supports_lifecycle(p)


def test_an_unsupported_provider_is_explained_not_silently_ignored():
    """A half-built AWS path would fail in ways a customer could not recover from, so we
    say what does work instead."""
    with pytest.raises(cl.InvalidRequest) as e:
        cl.adapter("aws", {})
    assert "DigitalOcean and Hetzner" in str(e.value)


# ── the requests we actually send ────────────────────────────────────────────
class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text or "{}"

    def json(self):
        return self._payload


class Recorder:
    """Stands in for `requests`, so the request we would really send can be asserted."""

    def __init__(self, payload=None, status=200):
        self.calls: list[tuple] = []
        self.payload = payload or {}
        self.status = status

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append((method, url, json))
        return FakeResponse(self.status, self.payload)

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, None))
        return FakeResponse(self.status, self.payload)

    @property
    def last(self):
        return self.calls[-1]


@pytest.fixture
def rec(monkeypatch):
    r = Recorder()
    monkeypatch.setattr(cl, "requests", r)
    monkeypatch.setattr("app.services.cloud_service.requests", r, raising=False)
    return r


def test_the_irreversible_flag_reaches_digitalocean_exactly_as_decided(rec):
    """The decision made in resize_plan has to be the one that lands in the API call —
    a default flipped somewhere in between is how a reversible resize becomes permanent."""
    a = cl.DOLifecycle({"api_token": "t"})
    a.act("123", cl.RESIZE, size="s-2vcpu-4gb", grow_disk=False)
    assert rec.last[2] == {"type": "resize", "size": "s-2vcpu-4gb", "disk": False}
    a.act("123", cl.RESIZE, size="s-2vcpu-4gb", grow_disk=True)
    assert rec.last[2]["disk"] is True


def test_the_irreversible_flag_reaches_hetzner_exactly_as_decided(rec):
    a = cl.HetznerLifecycle({"api_token": "t"})
    a.act("42", cl.RESIZE, size="cx22", grow_disk=False)
    assert rec.last[1].endswith("/servers/42/actions/change_type")
    assert rec.last[2] == {"server_type": "cx22", "upgrade_disk": False}


def test_powering_off_asks_the_operating_system_first(rec):
    """Hetzner's `poweroff` is pulling the plug. A database mid-write does not survive
    that intact, so the polite call is the default."""
    cl.HetznerLifecycle({"api_token": "t"}).act("42", cl.POWER_OFF)
    assert rec.last[1].endswith("/actions/shutdown")
    assert not rec.last[1].endswith("/actions/poweroff")


def test_destroy_is_a_delete_against_the_one_id(rec):
    cl.DOLifecycle({"api_token": "t"}).destroy("999")
    method, url, _ = rec.last
    assert method == "DELETE" and url.endswith("/v2/droplets/999")


def test_an_unknown_action_never_reaches_a_provider(rec):
    with pytest.raises(cl.InvalidRequest):
        cl.DOLifecycle({"api_token": "t"}).act("1", "self_destruct")
    assert rec.calls == [], "nothing should have been sent"


# ── error messages a non-technical owner can act on ──────────────────────────
def test_a_read_only_token_is_named_as_the_problem(monkeypatch):
    """The likeliest real failure: they connected the account with a read token, which
    lists servers perfectly and cannot create one. "403" does not tell them that."""
    r = Recorder(status=403)
    monkeypatch.setattr(cl, "requests", r)
    with pytest.raises(CloudError) as e:
        cl.DOLifecycle({"api_token": "t"}).destroy("1")
    assert "WRITE access" in str(e.value) and "read-only" in str(e.value)


def test_rate_limiting_says_to_wait_rather_than_showing_a_number(monkeypatch):
    r = Recorder(status=429)
    monkeypatch.setattr(cl, "requests", r)
    with pytest.raises(CloudError) as e:
        cl.HetznerLifecycle({"api_token": "t"}).act("1", cl.REBOOT)
    assert "Wait a minute" in str(e.value)


def test_a_gone_server_reads_as_gone_not_as_a_failure(monkeypatch):
    r = Recorder(status=404)
    monkeypatch.setattr(cl, "requests", r)
    assert cl.DOLifecycle({"api_token": "t"}).get("1") is None


def test_the_providers_own_reason_is_shown_not_a_raw_body(monkeypatch):
    r = Recorder(status=422)
    r.payload = {}
    monkeypatch.setattr(cl, "requests", r)
    def request(method, url, headers=None, json=None, timeout=None):
        return FakeResponse(422, {}, '{"id":"unprocessable","message":"size is not available in this region"}')
    r.request = request
    with pytest.raises(CloudError) as e:
        cl.DOLifecycle({"api_token": "t"}).act("1", cl.REBOOT)
    assert "size is not available in this region" in str(e.value)
    assert '"id"' not in str(e.value), "show the sentence, not the JSON"


# ── the routes must be reachable, not shadowed ───────────────────────────────
def test_every_lifecycle_route_resolves_to_its_own_handler():
    """A `{action}` catch-all sits at the same depth as /resize and /destroy and, being
    registered first, swallowed both — the two most consequential routes in the feature
    were unreachable and answered "unknown action". Registration order is not something
    to remember, so this asserts it."""
    import main
    from starlette.routing import Match

    base = "/api/cloud-accounts/11111111-1111-1111-1111-111111111111/instances/42"
    expected = {
        f"{base}/reboot": "reboot",
        f"{base}/power-on": "power_on",
        f"{base}/power-off": "power_off",
        f"{base}/resize": "resize",
        f"{base}/resize/preview": "preview_resize",
        f"{base}/destroy": "destroy",
    }
    for path, want in expected.items():
        scope = {"type": "http", "method": "POST", "path": path, "headers": [],
                 "root_path": "", "query_string": b""}
        hit = next((r for r in all_routes(main.app)
                    if r.matches(scope)[0] == Match.FULL), None)
        assert hit is not None, f"{path} matches no route at all"
        assert hit.name == want, f"{path} was handled by {hit.name}, not {want}"


def test_a_made_up_action_is_not_a_route():
    """The catch-all also meant any word became a valid-looking endpoint."""
    import main
    from starlette.routing import Match
    scope = {"type": "http", "method": "POST", "root_path": "", "headers": [],
             "query_string": b"",
             "path": "/api/cloud-accounts/11111111-1111-1111-1111-111111111111"
                     "/instances/42/wipe-everything"}
    assert not any(r.matches(scope)[0] == Match.FULL for r in all_routes(main.app))


# ── the guard has to be able to run at all ───────────────────────────────────
def test_a_lifecycle_adapter_can_really_list_the_account():
    """Found by driving the real router against a fake provider: the write adapters did
    not implement listing, and the base class's polite "not supported" stub still passed
    a `hasattr` check — so the duplicate-create guard was skipped and a repeated request
    billed a second server. The guard is only as real as its ability to look."""
    for cls in (cl.DOLifecycle, cl.HetznerLifecycle):
        fn = cls.list_instances
        assert fn is not cl._TokenAdapter.list_instances, f"{cls.__name__} inherits the stub"
        from app.services.cloud_service import _CloudAdapter
        assert fn is not _CloudAdapter.list_instances, f"{cls.__name__} cannot list"


def test_listing_actually_returns_instances(rec):
    rec.payload = {"droplets": [{"id": 7, "name": "web-1", "status": "active",
                                 "size_slug": "s-1vcpu-1gb", "region": {"slug": "lon1"},
                                 "image": {"distribution": "Ubuntu"},
                                 "networks": {"v4": []}}], "links": {}}
    got = cl.DOLifecycle({"api_token": "t"}).list_instances()
    assert [i.name for i in got] == ["web-1"]
