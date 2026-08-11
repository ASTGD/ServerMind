"""Being told that a site deployed — Ploi's per-site Notifications.

Two rules decide whether this is worth having.

**A failure to notify must never fail the deploy.** The deploy is the important thing;
being told about it is a side effect. A deploy that SUCCEEDED must not be reported as
failed because Slack was down, and a deploy that failed must not lose its own error behind
a second one.

**A rule that fires on nothing is worse than no rule**, because the customer believes they
are covered. So an empty event set is refused at the door rather than saved.
"""
import asyncio
import uuid

import pytest

from app.models.deployment import DEPLOY_EVENTS
from app.services import deploy_notify_service as dn


class Rule:
    def __init__(self, **kw):
        self.user_id = kw.get("user_id", uuid.uuid4())
        self.channel_id = kw.get("channel_id", uuid.uuid4())
        self.events = kw.get("events", list(DEPLOY_EVENTS))
        self.is_active = kw.get("is_active", True)
        self.last_sent_at = None
        self.last_error = None


# ── What may be asked for ────────────────────────────────────────────────────

def test_the_three_events_are_ploi_s_three():
    assert DEPLOY_EVENTS == ("started", "completed", "failed")


@pytest.mark.parametrize("event", DEPLOY_EVENTS)
def test_each_event_is_accepted(event):
    assert dn.clean_events([event]) == [event]


def test_the_order_is_stable_whatever_order_they_arrive_in():
    """So two rules meaning the same thing do not read as different ones."""
    assert dn.clean_events(["failed", "started"]) == ["started", "failed"]
    assert dn.clean_events(["started", "failed"]) == ["started", "failed"]


def test_an_unknown_event_is_refused_and_the_message_names_the_real_ones():
    with pytest.raises(dn.DeployNotifyError) as exc:
        dn.clean_events(["deployed"])
    msg = str(exc.value)
    for e in DEPLOY_EVENTS:
        assert e in msg


def test_choosing_nothing_is_refused():
    """A rule that fires on nothing looks configured and does nothing, which is worse than
    not having made one."""
    for empty in ([], None, [""], ""):
        with pytest.raises(dn.DeployNotifyError) as exc:
            dn.clean_events(empty)
        assert "never send anything" in str(exc.value)


# ── When it fires — fails closed at every ambiguity ──────────────────────────

def test_a_rule_fires_for_an_event_it_asked_for():
    assert dn.wants(Rule(events=["failed"]), "failed") is True


def test_a_rule_stays_quiet_for_an_event_it_did_not_ask_for():
    assert dn.wants(Rule(events=["failed"]), "completed") is False


def test_a_switched_off_rule_never_fires():
    assert dn.wants(Rule(is_active=False), "started") is False


def test_a_rule_whose_channel_was_deleted_never_fires():
    """The channel is SET NULL rather than CASCADE, so the rule survives to be repaired —
    but it must not try to send in the meantime."""
    assert dn.wants(Rule(channel_id=None), "started") is False


@pytest.mark.parametrize("broken", [None, "started", 42, {"started": True}])
def test_a_malformed_events_list_never_fires(broken):
    assert dn.wants(Rule(events=broken), "started") is False


def test_no_rule_at_all_never_fires():
    assert dn.wants(None, "started") is False


# ── What the message says ────────────────────────────────────────────────────

def test_the_message_names_the_site_first():
    """A notification that only says "deploy failed" makes somebody open the app to find out
    WHICH site — the work it was supposed to save."""
    subject, _ = dn.build_message(event="failed", site="shop.example.com",
                                  repo="git@github.com:me/shop.git", branch="main")
    assert "shop.example.com" in subject
    assert subject.startswith("Deploy FAILED")


def test_a_failure_says_which_step_it_stopped_on():
    _, body = dn.build_message(event="failed", site="s.com", repo="r", branch="main",
                               failed_step="Install dependencies")
    assert "Stopped at: Install dependencies" in body


def test_a_success_does_not_invent_a_failed_step():
    _, body = dn.build_message(event="completed", site="s.com", repo="r", branch="main",
                               failed_step="Install dependencies")
    assert "Stopped at" not in body


def test_the_message_says_who_started_it():
    _, push = dn.build_message(event="started", site="s.com", repo="r", branch="main",
                               trigger="push")
    _, hand = dn.build_message(event="started", site="s.com", repo="r", branch="main")
    assert "push" in push.lower()
    assert "by hand" in hand.lower()


# ── The summary line on the screen ───────────────────────────────────────────

def test_the_summary_is_words_not_field_names():
    assert dn.summarise(Rule(events=list(DEPLOY_EVENTS))) == \
        "Every deploy — started, finished and failed."
    assert dn.summarise(Rule(events=["failed"])) == "Only when one fails."


def test_a_rule_with_nothing_selected_says_so_rather_than_looking_fine():
    assert "sends nothing" in dn.summarise(Rule(events=[]))


# ── THE rule: notifying can never break the deploy ───────────────────────────

def test_a_channel_that_explodes_does_not_raise(monkeypatch):
    """A deploy that SUCCEEDED must not be reported as failed because Slack was down."""
    # Deliberately SYNC. My first version made this async, so it never raised — it returned
    # a coroutine that failed to unpack a line later, and the test passed for a reason that
    # had nothing to do with what it claims to check.
    def boom(*a, **k):
        raise RuntimeError("slack is on fire")

    import app.services.deploy_notify_service as mod
    monkeypatch.setattr(mod, "build_message", boom)

    sent = asyncio.run(mod.notify(uuid.uuid4(), "completed", user_id=uuid.uuid4(),
                                  site="s.com", repo="r", branch="main"))
    assert sent == 0


def test_a_database_that_is_unreachable_does_not_raise(monkeypatch):
    """Same rule, one layer down: the notification reads the database, and that read
    failing must not take the deploy's own outcome with it."""
    import app.services.deploy_notify_service as mod

    class _Boom:
        def __call__(self):
            raise RuntimeError("no database")

    monkeypatch.setattr("app.database.AsyncSessionLocal", _Boom())
    sent = asyncio.run(mod.notify(uuid.uuid4(), "failed", user_id=uuid.uuid4(),
                                  site="s.com", repo="r", branch="main"))
    assert sent == 0


# ── Ploi's webhook half, done through the system we already have ─────────────

def test_deploy_events_are_in_the_webhook_catalogue():
    """Ploi POSTs a raw body to a per-site URL. Ours go through endpoints that already sign,
    retry and log every delivery — the same event, auditable."""
    from app.models.integration import WEBHOOK_EVENTS

    assert "deploy.started" in WEBHOOK_EVENTS
    assert "deploy.finished" in WEBHOOK_EVENTS


def test_the_runner_tells_people_at_the_start_and_at_the_end():
    """Started has to be sent BEFORE the work, or it arrives after the thing it announces."""
    import inspect

    from app.workers import deploy_runner

    src = inspect.getsource(deploy_runner.start_deploy)
    started = src.index('notify.notify(target_id, "started"')
    executed = src.index("_execute(run_id")
    assert started < executed, "the start notice must go out before the deploy runs"
    assert '"completed" if ok else "failed"' in src


# ── The endpoints, against the real database ─────────────────────────────────
#
# Deliberately NOT asserted by reading the router's source. On 3 August a mutation deleted
# a real comparison in exactly this shape of check and the source-grep test still passed,
# because both strings it looked for were still in the file. A security property has to be
# exercised.

@pytest.mark.asyncio
async def test_a_channel_belonging_to_someone_else_cannot_be_used():
    """Without the ownership filter, a guessed channel id would send THIS customer's deploy
    notices to somebody else's Slack."""
    import uuid as _uuid

    from fastapi import HTTPException

    # Import the whole model package: Server carries a foreign key to escalation_policies,
    # and SQLAlchemy cannot resolve it unless that model has been registered too.
    import app.models  # noqa: F401
    import app.models.escalation  # noqa: F401  — servers.escalation_policy_id points here
    from app.database import AsyncSessionLocal
    from app.models.deployment import DeployTarget
    from app.models.notification_channel import NotificationChannel
    from app.models.server import Server
    from app.models.site import Site
    from app.models.user import User
    from app.routers.sites import DeployNotifyIn, add_deploy_notification
    from app.services import channel_service, crypto_service

    tag = _uuid.uuid4().hex[:8]
    made = []
    async with AsyncSessionLocal() as db:
        mine = User(email=f"mine-{tag}@example.com", password_hash="x", is_verified=True)
        theirs = User(email=f"theirs-{tag}@example.com", password_hash="x", is_verified=True)
        db.add_all([mine, theirs])
        await db.flush()

        server = Server(user_id=mine.id, name=f"srv-{tag}", host="10.0.0.1", port=22,
                        username="root", auth_type="password", connection_type="ssh",
                        encrypted_cred=crypto_service.encrypt("pw"))
        db.add(server)
        await db.flush()

        site = Site(user_id=mine.id, server_id=server.id, domain=f"{tag}.example.com",
                    aliases=[], doc_root="/var/www/x", source="manual", app_type="php",
                    has_ssl=False, is_present=True, status="live")
        db.add(site)
        await db.flush()

        db.add(DeployTarget(user_id=mine.id, server_id=server.id, site_id=site.id,
                            name=site.domain, repo="git@example.com:a/b.git",
                            branch="main", path="/var/www/x",
                            webhook_secret=crypto_service.encrypt("s")))
        # A channel that belongs to the OTHER account.
        not_mine = NotificationChannel(
            user_id=theirs.id, kind="slack", label="Their Slack",
            encrypted_config=crypto_service.encrypt(
                '{"webhook_url": "https://hooks.slack.com/services/A/B/C"}'))
        db.add(not_mine)
        await db.commit()
        made = [mine.id, theirs.id, server.id, site.id, not_mine.id]
        site_id, other_channel = str(site.id), str(not_mine.id)

        with pytest.raises(HTTPException) as exc:
            await add_deploy_notification(
                site_id, DeployNotifyIn(channel_id=other_channel, events=["failed"]),
                db, mine)
        assert exc.value.status_code == 404

    # Leave the database as it was found.
    async with AsyncSessionLocal() as db:
        for model, pk in ((Site, made[3]), (Server, made[2]),
                          (NotificationChannel, made[4]),
                          (User, made[0]), (User, made[1])):
            row = await db.get(model, pk)
            if row is not None:
                await db.delete(row)
        await db.commit()
