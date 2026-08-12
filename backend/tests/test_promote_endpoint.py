"""The door to promote — and the four things it must not let through.

`promote_service` was built and proven on a real server, and then shipped with no endpoint
at all: complete logic that nobody could reach. These tests are about the wiring, so the
same gap cannot come back, and about the guards that only exist once there IS a caller.

The dangerous ones are numbered by what they prevent, not by what they check:

1. **A commit chosen by the caller.** Promotion deploys a commit; if that commit could
   arrive in the request body, anyone who can reach the endpoint could deploy ANY revision
   to a live website. It is read off the server, always.
2. **A self-satisfying confirmation.** The file copy asks the customer to type the live
   domain. If the endpoint passed the live site's own domain to that check instead of what
   they typed, the confirmation would confirm itself.
3. **A mismatched layout.** A Laravel site keeps its application above the folder it
   serves. Copying one of those onto a site laid out the other way publishes `.env`.
4. **Two copies of one rule.** The page says why a promotion is unavailable and the button
   decides whether it is. If those are separate code, they drift and the customer is told
   one thing and refused for another.
"""
import inspect

import pytest

from app.routers import sites
from app.services import promote_service as pr


def code(fn) -> str:
    """The function's executable lines, with whole-line comments removed.

    Ordering assertions look for the first occurrence of a name, and a comment EXPLAINING
    a call sits above the call — so `body.index("start_deploy")` happily matches the
    sentence about it and compares two pieces of prose. That has now caught this codebase
    four times (`pgrep`, `sshd -t`, an import line, and this file). Docstrings are left
    alone: they are the function's own first statement, ahead of every call, so they cannot
    reorder anything.
    """
    return "\n".join(ln for ln in inspect.getsource(fn).splitlines()
                     if not ln.strip().startswith("#"))


# ── 3. the layout guard ──────────────────────────────────────────────────────

@pytest.mark.parametrize("scope", ["app", "docroot"])
def test_matching_layouts_are_allowed(scope):
    pr.check_layouts_match(scope, scope)          # no exception


@pytest.mark.parametrize("staging,live", [("app", "docroot"), ("docroot", "app")])
def test_a_mismatched_layout_is_refused_both_ways(staging, live):
    """Refused in BOTH directions, because they fail differently and both are bad.

    app → docroot publishes the application's own settings at a guessable address;
    docroot → app leaves the live site serving a folder with no index in it.
    """
    with pytest.raises(pr.PromoteRefused) as exc:
        pr.check_layouts_match(staging, live)
    assert "laid out differently" in str(exc.value)
    assert "nothing was changed" in str(exc.value)


def test_the_layout_refusal_does_not_talk_about_scopes():
    """The customer never chose a "scope" and cannot act on the word. The message has to be
    about their sites."""
    try:
        pr.check_layouts_match("app", "docroot")
    except pr.PromoteRefused as exc:
        assert "scope" not in str(exc).lower()


# ── 1. the commit is never the caller's to choose ────────────────────────────

def test_the_request_body_cannot_carry_a_commit():
    """The single most dangerous input this endpoint could accept.

    A commit in the body means anyone who can promote can deploy any revision of the
    repository to the live site — including one that was never reviewed, and one from a
    branch nobody watches.
    """
    fields = set(sites.PromoteIn.model_fields)
    assert fields == {"method", "confirm_domain"}, (
        f"PromoteIn grew a field: {fields}. If that field is a commit, a caller can now "
        f"choose what goes live.")


def test_the_commit_is_read_off_the_server():
    body = code(sites.promote_site)
    assert "read_commit_command" in body and "parse_commit" in body
    # Not merely present — it must be what feeds the deploy.
    assert body.index("parse_commit") < body.index("start_deploy")


def test_an_unreadable_commit_refuses_rather_than_deploying_the_branch():
    """The quiet failure this guards against: with no commit, `build_plan` would deploy the
    branch tip — so "put staging live" would silently mean "deploy whatever was pushed
    last", which is the one thing the pin exists to prevent."""
    body = code(sites.promote_site)
    head = body[:body.index("start_deploy")]
    assert "if not commit:" in head and "HTTPException" in head


def test_the_deploy_runner_passes_the_commit_to_the_plan():
    """The pin is only real if it reaches `build_plan`. Between the endpoint and the plan
    there is one function, and it used to drop it."""
    from app.workers import deploy_runner

    body = code(deploy_runner.start_deploy)
    assert "commit=commit" in body
    assert "commit" in inspect.signature(deploy_runner.start_deploy).parameters


# ── 2. the confirmation must be the customer's words ─────────────────────────

def test_the_file_promote_confirms_against_what_was_typed():
    """`check_file_promote` compares the typed domain with the domain the SERVER holds — so
    passing the live site's own domain here would make the check confirm itself, and the
    typed field would become decoration."""
    body = code(sites.promote_site)
    call = body[body.index("check_file_promote"):]
    assert "confirm_domain=body.confirm_domain" in call[:400], (
        "the confirmation is not taken from the request body")


def test_the_options_page_asks_without_pretending_to_confirm():
    """The GET passes the live domain deliberately — it is asking "would this be offered",
    not "is this confirmed" — and must never start any work."""
    body = code(sites.promote_options)
    assert "confirm_domain=live.domain" in body
    assert "create_task" not in body and "start_deploy" not in body


# ── 4. one rule, one place ───────────────────────────────────────────────────

def test_the_page_and_the_button_share_the_same_checks():
    """The page explains why a promotion is unavailable; the button decides. A second copy
    of those rules is how the two start giving different answers — this is the seam that
    cost a live deploy ten wasted steps when a rule lived in code and in a prompt."""
    page = code(sites.promote_options)
    assert "check_git_promote" in page
    assert "check_file_promote" in page
    # Not reimplemented alongside them.
    assert "_norm" not in page, "the page compares repositories itself instead of asking"


# ── ordering: nothing moves before the refusals ──────────────────────────────

def test_every_refusal_happens_before_the_work_starts():
    """All four checks come before the background task. A guard that runs after the copy
    has started is not a guard — the files are already moving."""
    body = code(sites.promote_site)
    start = body.index("create_task")
    for guard in ("check_file_promote", "check_layouts_match"):
        assert body.index(guard) < start, f"{guard} runs after the copy starts"


def test_promoting_requires_permission_to_change_the_server():
    """Rule 7. Replacing a live website's files is the most consequential write in the
    product; a viewer must never reach it.

    Named down to the call, not `"need_execute=True" in body`. That looser version passed
    while the permission on the STAGING site had been removed, because the check on the LIVE
    site's server — added later — happens to contain the same string. A guard proven by a
    string that another guard also carries is proven by nothing.
    """
    body = code(sites.promote_site)
    assert ("_site_and_server(site_id, current_user, db, need_execute=True)" in body), (
        "the staging site is resolved without requiring permission to change it")


def test_the_live_site_is_looked_up_as_the_callers_own():
    """`parent_site_id` decides what gets WRITTEN TO. Loading it by id alone would mean a
    row pointing elsewhere leads straight to somebody else's website."""
    body = code(sites._live_site)
    assert "Site.user_id == current_user.id" in body
    for fn in (sites.promote_site, sites.promote_options):
        src = code(fn)
        assert "_live_site(" in src
        assert "db.get(Site, staging.parent_site_id)" not in src, (
            f"{fn.__name__} loads the live site by id, bypassing the scoping")


def test_permission_is_checked_on_the_site_being_written_to():
    """The Git path deploys to the LIVE site's target, and `deploy_runner.start_deploy`
    performs no access check of its own — the deployments router does it before calling. So
    it has to happen here, on the live site's server, or this endpoint is a way around it.
    """
    body = code(sites.promote_site)
    assert "resolve_server(str(live.server_id), current_user, db, need_execute=True)" in body
    assert body.index("live.server_id") < body.index("start_deploy")


def test_an_unknown_method_is_refused_rather_than_guessed():
    """The two paths do very different things. Defaulting to either one when the request is
    unclear picks the outcome on the customer's behalf."""
    body = code(sites.promote_site)
    assert 'body.method != "files"' in body


# ── the runner tells the truth about a failure ───────────────────────────────

def test_a_failed_promotion_says_the_live_site_was_not_changed():
    """The command switches last, so a failure means the live site is untouched. Saying so
    matters more than it sounds: the alternative is somebody assuming their site is
    half-replaced and restoring a backup they do not need."""
    from app.workers import promote_runner

    body = code(promote_runner.run_promote)
    assert "was not changed" in body


def test_the_runner_does_not_build_its_own_command():
    """The command was proven on a real server. A runner that assembled its own would be a
    second, unproven version of the most destructive operation we have."""
    from app.workers import promote_runner

    body = inspect.getsource(promote_runner)
    assert "build_file_promote_command" in body
    assert "rsync" not in body and "tar " not in body
