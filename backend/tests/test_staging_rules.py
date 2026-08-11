"""The four things a staging copy must not inherit.

A staging site is deliberately an ordinary site row, which is what makes Files, Logs,
Database and PHP work on it the day it exists. The cost of that decision is that four
ordinary abilities become incidents on a copy of a live site, and until now **nothing in the
codebase read `environment` at all** — a staging copy could be given a cron job that emails
real customers, a queue worker that drains the live queue, and a pager that fires at 3am.
"""
import inspect

import pytest

from app.services import staging_rules as rules


class _Site:
    def __init__(self, environment="production", domain="shop.example.com"):
        self.environment = environment
        self.domain = domain


def staging(**kw) -> _Site:
    return _Site(environment="staging", **kw)


# ── what makes a site staging ────────────────────────────────────────────────

def test_staging_is_the_column_not_the_name():
    """Somebody who called a site `staging.shop.com` by hand is not a copy of anything.

    Deciding by name would apply these refusals to a real production site whose owner simply
    liked the word — and would miss a genuine copy called something else.
    """
    assert rules.is_staging(staging()) is True
    assert rules.is_staging(_Site(domain="staging.shop.example.com")) is False


def test_a_site_with_no_environment_at_all_is_not_staging():
    """Fails toward the permissive answer on purpose: these are refusals, and refusing a
    production site's cron job because a field was missing would break a working setup."""
    class _Bare:
        domain = "x.example.com"

    assert rules.is_staging(_Bare()) is False


# ── the four refusals ────────────────────────────────────────────────────────

def test_cron_is_refused_on_staging_and_the_reason_says_what_it_protects():
    ok, why = rules.may_have_cron(staging())
    assert ok is False
    # A copied WordPress running the live schedule sends the same customer email twice.
    assert "customers" in why and "twice" in why


def test_daemons_are_refused_because_of_the_queue():
    """The one that loses work silently: a staging worker connected to the live queue
    CONSUMES jobs, so the live site's work stops happening with no error anywhere."""
    ok, why = rules.may_have_daemons(staging())
    assert ok is False
    assert "queue" in why


def test_push_to_deploy_is_refused_because_it_would_hit_both():
    ok, why = rules.may_auto_deploy(staging())
    assert ok is False
    assert "live site" in why


def test_staging_never_pages_anyone():
    assert rules.may_escalate(staging()) is False
    assert rules.may_escalate(_Site()) is True


def test_staging_still_gets_a_monitor():
    """Deliberately not "no monitor". With none, the Sites row reads "Not checked" — and a
    row that says nothing is worse than a row that says down. The customer should be able to
    SEE their copy is broken; they should not be woken about it."""
    doc = inspect.getdoc(rules.may_escalate) or ""
    assert "not \"no monitor" in doc or "not 'no monitor" in doc


@pytest.mark.parametrize("rule", ["may_have_cron", "may_have_daemons", "may_auto_deploy"])
def test_a_production_site_is_never_refused(rule):
    """These are staging defaults, not a new restriction on everybody."""
    ok, why = getattr(rules, rule)(_Site())
    assert ok is True and why == ""


@pytest.mark.parametrize("rule", ["may_have_cron", "may_have_daemons", "may_auto_deploy"])
def test_every_refusal_explains_itself(rule):
    """A refusal that only says no teaches the customer the product is broken. Each must say
    what it is protecting, in words about their site rather than ours."""
    _ok, why = getattr(rules, rule)(staging())
    assert len(why) > 80, f"{rule} refuses without explaining"
    assert "staging" in why.lower()


# ── the rules are actually wired in ──────────────────────────────────────────

def test_the_cron_endpoint_asks_before_creating():
    from app.routers import sites

    body = inspect.getsource(sites.add_site_cron)
    assert "staging_rules.may_have_cron" in body
    # Before the WRITE, not merely somewhere in the function: a job added to the crontab and
    # then refused is a job on the server. Anchored on the call that adds it — an earlier
    # attempt anchored on `cron_service`, which also appears in the import line at the top,
    # so it compared the guard against a line that touches nothing.
    assert body.index("may_have_cron") < body.index("cron_service.add_job")


def test_the_daemon_endpoint_asks_before_creating():
    from app.routers import sites

    body = inspect.getsource(sites.add_site_daemon)
    assert "staging_rules.may_have_daemons" in body
    assert body.index("may_have_daemons") < body.index("site_daemon_service.build_unit")


def test_push_to_deploy_is_checked_where_it_is_switched_on():
    """Not in the form — the form is not the only way in."""
    from app.routers import deployments

    body = inspect.getsource(deployments)
    assert "staging_rules.may_auto_deploy" in body


def test_the_uptime_worker_checks_before_raising_an_incident():
    from app.workers import uptime_worker

    body = inspect.getsource(uptime_worker._escalate_down)      # noqa: SLF001
    assert "may_escalate" in body
    assert body.index("may_escalate") < body.index("raise_for"), (
        "the incident is raised before the check, so staging would page anyway")
