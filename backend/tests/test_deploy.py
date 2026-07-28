"""Deployments — the properties that stop a deploy from becoming an outage.

Three things matter more than the rest and are tested hardest: the switch is atomic,
a failed build cannot reach the live site, and rollback goes somewhere that is actually
different from what is running.
"""
from __future__ import annotations

import json
import re
import shlex

import pytest

from app.services import deploy_service as d


# ── configuration that would be dangerous ─────────────────────────────────────
@pytest.mark.parametrize("bad", [
    "/", "/etc", "/usr", "/var", "/root", "/home", "/bin",
])
def test_a_system_folder_is_refused_as_a_deploy_root(bad):
    """The pruner deletes inside this folder. Pointing it at /etc would delete the
    system on the second deploy."""
    with pytest.raises(d.InvalidDeploy) as e:
        d.valid_path(bad)
    assert "system folder" in str(e.value)


@pytest.mark.parametrize("bad", [
    "relative/path", "/var/www/../../etc", "/var/www/app; rm -rf /",
    "/var/www/$(whoami)", "/var/www/`id`", "", "   ",
])
def test_a_path_that_could_escape_or_inject_is_refused(bad):
    with pytest.raises(d.InvalidDeploy):
        d.valid_path(bad)


@pytest.mark.parametrize("bad", [
    "not a url", "https://github.com/me/app.git; rm -rf /",
    "file:///etc/passwd", "ssh://x", "javascript:alert(1)", "",
])
def test_a_repo_that_is_not_a_repo_is_refused(bad):
    with pytest.raises(d.InvalidDeploy):
        d.valid_repo(bad)


@pytest.mark.parametrize("good", [
    "https://github.com/me/app.git", "https://github.com/me/app",
    "git@github.com:me/app.git", "https://gitlab.com/group/sub/app.git",
])
def test_real_repo_addresses_are_accepted(good):
    assert d.valid_repo(good) == good


@pytest.mark.parametrize("bad", ["/etc/passwd", "../../../etc/shadow", "a b", "x;y"])
def test_a_shared_path_cannot_reach_outside_the_project(bad):
    """An absolute shared path would symlink something from elsewhere on the server into
    the web root — which is how a deploy publishes /etc."""
    with pytest.raises(d.InvalidDeploy):
        d.valid_shared([bad])


def test_ordinary_shared_paths_are_accepted():
    assert d.valid_shared([".env", "storage/uploads", "public/media/"]) == \
        [".env", "storage/uploads", "public/media"]


def test_a_shared_path_always_lands_under_the_deploy_root():
    """The property that actually matters. Whatever is accepted, the link target is
    built as <root>/shared/<path>, so it can never point outside the deploy folder."""
    plan = d.build_plan(path="/var/www/app", repo="https://github.com/me/app.git",
                        branch="main", stamp="20260728_141530",
                        shared=[".env", "storage/uploads"])
    for s in (x for x in plan.steps if x.name.startswith("Link shared")):
        for token in s.command.split():
            cleaned = token.strip("';\"")
            if cleaned.startswith("/") and "shared" in cleaned:
                assert cleaned.startswith("/var/www/app/"), cleaned


# ── the switch: the single most important property ───────────────────────────
def test_the_switch_is_atomic_not_a_relink():
    """`ln -sfn` over an existing link unlinks then recreates, and a request landing in
    that gap sees no directory at all. A rename cannot be observed half-done."""
    cmd = d.switch_command("/var/www/app", "20260728_141530")
    assert "mv -Tf" in cmd, "the switch must be a rename, not a relink"
    assert "current.tmp" in cmd, "build the new link aside, then rename it over"
    # The dangerous shape: pointing at `current` directly with no temp+rename.
    assert not re.search(r"ln -sfn [^;]+/current(?!\.tmp)", cmd)


def test_the_live_site_is_untouched_until_everything_has_built():
    """A broken build must fail in a directory nothing points at."""
    plan = d.build_plan(path="/var/www/app", repo="https://github.com/me/app.git",
                        branch="main", stamp="20260728_141530",
                        build=["npm ci", "npm run build"])
    names = [s.name for s in plan.steps]
    go_live = names.index("Go live")
    builds = [i for i, n in enumerate(names) if n.startswith("Build")]
    assert builds, "expected build steps"
    assert max(builds) < go_live, "every build step must run BEFORE the switch"
    # And nothing before the switch may write to `current`.
    for s in plan.steps[:go_live]:
        assert "/current" not in s.command, f"{s.name} touches the live path"


def test_build_steps_are_fatal_but_the_restart_is_not():
    """A failed build must abort. A failed restart must not: the code is already live,
    and an automatic undo there would flap between two releases."""
    plan = d.build_plan(path="/var/www/app", repo="https://github.com/me/app.git",
                        branch="main", stamp="20260728_141530",
                        build=["npm ci"], after=["systemctl restart app"])
    by_name = {s.name: s for s in plan.steps}
    assert by_name["Build (1/1)"].fatal is True
    assert by_name["Go live"].fatal is True
    assert by_name["After deploy (1/1)"].fatal is False
    assert by_name["Tidy old releases"].fatal is False


def test_builds_run_inside_the_new_release_never_the_live_folder():
    plan = d.build_plan(path="/var/www/app", repo="https://github.com/me/app.git",
                        branch="main", stamp="20260728_141530", build=["npm ci"])
    build = next(s for s in plan.steps if s.name.startswith("Build"))
    assert "/var/www/app/releases/20260728_141530" in build.command
    assert "/current" not in build.command


# ── shared paths survive ─────────────────────────────────────────────────────
def test_shared_paths_are_linked_so_uploads_survive_a_deploy():
    """Replacing uploads/ on each deploy would destroy customer files."""
    plan = d.build_plan(path="/var/www/app", repo="https://github.com/me/app.git",
                        branch="main", stamp="20260728_141530",
                        shared=["storage/uploads"])
    link = next(s for s in plan.steps if s.name.startswith("Link shared"))
    assert "ln -s" in link.command
    assert "/var/www/app/shared/storage/uploads" in link.command


# ── pruning must never eat the release you need ──────────────────────────────
def test_pruning_keeps_the_newest_and_never_fewer_than_two():
    cmd = d.prune_command("/var/www/app", keep=5)
    assert "sort -r" in cmd and "tail -n +6" in cmd
    # Even asked for 1 or 0, keep two: one live and one to roll back to.
    for silly in (0, 1, -3):
        assert "tail -n +3" in d.prune_command("/var/www/app", keep=silly)


def test_pruning_is_scoped_to_the_releases_folder():
    cmd = d.prune_command("/var/www/app")
    assert "cd '/var/www/app'/releases" in cmd or "/var/www/app/releases" in cmd
    assert "rm -rf /" not in cmd


# ── rollback ─────────────────────────────────────────────────────────────────
def test_rollback_picks_the_newest_release_that_is_not_live():
    rels = ["20260728_150000", "20260728_140000", "20260727_120000"]
    assert d.rollback_target(rels, "20260728_150000") == "20260728_140000"


def test_rollback_refuses_when_there_is_nowhere_to_go():
    """Silently redeploying the same broken release is worse than an error, because the
    operator believes they have recovered."""
    with pytest.raises(d.InvalidDeploy):
        d.rollback_target(["only_one"], "only_one")
    with pytest.raises(d.InvalidDeploy):
        d.rollback_target([], None)


def test_reading_back_which_release_is_live():
    out = ("20260728_150000\n20260728_140000\n"
           "---CURRENT---\n/var/www/app/releases/20260728_150000\n")
    rels, live = d.parse_releases(out)
    assert rels == ["20260728_150000", "20260728_140000"]
    assert live == "20260728_150000"


def test_unreadable_release_listing_claims_nothing():
    assert d.parse_releases("") == ([], None)
    assert d.parse_releases("garbage") == ([], None)


# ── the webhook is a public URL, so the signature is the only gate ───────────
SECRET = "s3cret-webhook-key"


def _sig(body: bytes, secret: str = SECRET) -> str:
    import hashlib, hmac
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_a_correctly_signed_push_is_accepted():
    body = json.dumps({"ref": "refs/heads/main"}).encode()
    assert d.verify_github_signature(SECRET, body, _sig(body))


@pytest.mark.parametrize("header", [
    None, "", "sha256=deadbeef", "wrong-format",
    "sha1=aaaa",                       # the old algorithm must not be honoured
])
def test_an_unsigned_or_wrongly_signed_push_is_refused(header):
    """Without this the deploy URL is a public button: anyone who learns it ships code."""
    body = b'{"ref":"refs/heads/main"}'
    assert not d.verify_github_signature(SECRET, body, header)


def test_a_signature_from_a_different_secret_is_refused():
    body = b'{"ref":"refs/heads/main"}'
    assert not d.verify_github_signature(SECRET, body, _sig(body, "someone-elses-secret"))


def test_a_tampered_body_is_refused():
    body = json.dumps({"ref": "refs/heads/main"}).encode()
    good = _sig(body)
    assert not d.verify_github_signature(SECRET, body + b" ", good)


def test_no_secret_configured_means_nothing_is_accepted():
    body = b"{}"
    assert not d.verify_github_signature("", body, _sig(body, ""))


# ── which pushes actually deploy ─────────────────────────────────────────────
def test_a_push_to_another_branch_does_not_deploy():
    """A repo fires webhooks for every branch. Deploying on any of them ships a feature
    branch to production."""
    ok, why = d.should_deploy({"ref": "refs/heads/feature-x"}, "main")
    assert not ok and "feature-x" in why


def test_a_push_to_the_watched_branch_deploys():
    ok, _ = d.should_deploy({"ref": "refs/heads/main"}, "main")
    assert ok


def test_a_branch_deletion_does_not_deploy():
    ok, why = d.should_deploy({"ref": "refs/heads/main", "deleted": True}, "main")
    assert not ok and "deleted" in why


def test_a_tag_or_other_event_does_not_deploy():
    ok, _ = d.should_deploy({"ref": "refs/tags/v1.0"}, "main")
    assert not ok
    assert not d.should_deploy({}, "main")[0]


# ── everything user-typed that reaches a shell is quoted ─────────────────────
def test_paths_reach_the_shell_quoted():
    plan = d.build_plan(path="/var/www/my-app.v2", repo="https://github.com/me/app.git",
                        branch="release/1.0", stamp="20260728_141530")
    for s in plan.steps:
        # Re-parse the way a shell would; the path must survive as ONE argument.
        if "git clone" in s.command:
            parts = shlex.split(s.command.split("git clone", 1)[1])
            assert "/var/www/my-app.v2/releases/20260728_141530" in parts
            assert "release/1.0" in parts


# ── a failed release must not become the rollback candidate ──────────────────
def test_a_failed_deploy_removes_its_own_release_directory():
    """The subtle one. A build that fails leaves a half-finished directory that is the
    NEWEST release — so the next rollback would switch the site onto code that has never
    worked. The plan carries the command to bin it."""
    plan = d.build_plan(path="/var/www/app", repo="https://github.com/me/app.git",
                        branch="main", stamp="20260728_141530", build=["exit 1"])
    assert plan.discard, "the plan must know how to discard a failed release"
    assert "/var/www/app/releases/20260728_141530" in plan.discard
    assert "rm -rf" in plan.discard


@pytest.mark.parametrize("path", ["/", "/etc", "/var"])
def test_the_discard_command_cannot_be_aimed_at_the_system(path):
    """It is an `rm -rf`, so it runs through the same path validation as everything else."""
    with pytest.raises(d.InvalidDeploy):
        d.discard_command(path, "20260728_141530")


def test_the_discard_command_is_scoped_to_one_release():
    cmd = d.discard_command("/var/www/app", "20260728_141530")
    args = shlex.split(cmd)
    assert args[0] == "rm"
    targets = [a for a in args if not a.startswith("-") and a != "rm"]
    assert targets == ["/var/www/app/releases/20260728_141530"], targets
