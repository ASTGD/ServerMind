"""Putting a staging copy live — both paths.

The Git path is safe because it is the existing deploy with one new idea: a pin. The file
path is the only operation in the product that can destroy a working website, so every rule
here is proven by RUNNING the copy against a real tree and asserting the file on the
destination is unchanged — not by finding `--exclude` in a command string, which is true
whether or not rsync honours it.
"""
import inspect
import pathlib
import shutil
import subprocess

import pytest

from app.services import deploy_service, promote_service as promote


class _Site:
    def __init__(self, **kw):
        self.environment = kw.pop("environment", "staging")
        self.domain = kw.pop("domain", "staging.shop.example.com")
        self.doc_root = kw.pop("doc_root", "/home/s/staging")
        self.server_id = kw.pop("server_id", "srv-1")
        self.parent_site_id = kw.pop("parent_site_id", "live-1")
        self.__dict__.update(kw)


class _Target:
    def __init__(self, repo="https://github.com/acme/shop", path="/home/s/app"):
        self.repo, self.path = repo, path


LIVE = _Site(environment="production", domain="shop.example.com",
             doc_root="/home/s/live", parent_site_id=None)


# ── P3: the pin ──────────────────────────────────────────────────────────────

def test_a_promotion_deploys_a_commit_not_a_branch():
    """The whole reason P3 is not just "press deploy on live".

    Between opening the page and pressing the button a teammate can push. Deploying the
    branch would put THAT live, while the screen said it was promoting what was reviewed.
    """
    kw = dict(path="/srv/app", repo="https://github.com/a/b", branch="main",
              stamp="20260811_120000")
    names = [s.name for s in deploy_service.build_plan(**kw, commit="a" * 40).steps]
    assert "Fetch the exact commit" in names
    # Straight after the clone, so everything downstream is the unchanged, proven path.
    assert names[names.index("Fetch the code") + 1] == "Fetch the exact commit"


def test_an_ordinary_deploy_is_completely_unchanged():
    """Promotion must not make every other deploy slower or different."""
    kw = dict(path="/srv/app", repo="https://github.com/a/b", branch="main",
              stamp="20260811_120000")
    assert [s.name for s in deploy_service.build_plan(**kw).steps] == [
        "Prepare folders", "Fetch the code", "Go live", "Tidy old releases"]


def test_the_checkout_is_verified_before_anything_goes_live():
    """A checkout that fails is loud. A checkout that silently lands elsewhere would put
    unreviewed code on a live site while reporting success."""
    steps = deploy_service.build_plan(
        path="/srv/app", repo="https://github.com/a/b", branch="main",
        stamp="20260811_120000", commit="b" * 40).steps
    names = [s.name for s in steps]
    verify = next(s for s in steps if s.name == "Check out what staging is running")
    assert "rev-parse HEAD" in verify.command and "exit 1" in verify.command
    assert names.index("Check out what staging is running") < names.index("Go live")


@pytest.mark.parametrize("bad", [
    "", "   ", "abc", "z" * 40, "a" * 41,
    "aaaaaaa; rm -rf /", "aaaaaaa $(id)", "aaaaaaa\nrm -rf /",
])
def test_a_commit_is_validated_not_escaped(bad):
    """It reaches a command line. A "commit" with a space in it is a second command."""
    with pytest.raises(promote.PromoteRefused):
        promote.valid_commit(bad)


def test_the_commit_is_read_from_what_is_actually_served():
    """Through `current`, the symlink a visitor's request follows — not the newest release
    folder, because those differ the moment somebody has rolled back."""
    cmd = promote.read_commit_command("/home/s/app")
    assert "/current" in cmd and "rev-parse HEAD" in cmd
    assert promote.parse_commit("f" * 40) == "f" * 40
    assert promote.parse_commit("NO-GIT") is None      # not a git checkout
    assert promote.parse_commit("") is None
    assert promote.parse_commit("not-a-sha") is None   # never guessed at


def test_two_repositories_that_differ_are_refused_by_name():
    """"Repositories do not match" leaves somebody comparing two URLs by eye."""
    with pytest.raises(promote.PromoteRefused) as exc:
        promote.check_git_promote(
            staging_site=_Site(), staging_target=_Target("https://github.com/acme/shop"),
            live_site=LIVE, live_target=_Target("https://github.com/acme/blog"))
    assert "acme/shop" in str(exc.value) and "acme/blog" in str(exc.value)


def test_the_same_repository_written_two_ways_is_not_refused():
    """`git@github.com:acme/shop.git` and the https URL are the same repository. Refusing
    that pair would block an ordinary setup for no reason."""
    promote.check_git_promote(
        staging_site=_Site(), staging_target=_Target("git@github.com:acme/shop.git"),
        live_site=LIVE, live_target=_Target("https://github.com/acme/shop/"))


def test_a_live_site_with_no_repository_says_what_to_do_instead():
    with pytest.raises(promote.PromoteRefused) as exc:
        promote.check_git_promote(staging_site=_Site(), staging_target=_Target(),
                                  live_site=LIVE, live_target=None)
    assert "file copy" in str(exc.value)


def test_an_orphaned_copy_cannot_be_promoted():
    """Removing the parent leaves the copy standing (SET NULL) — it just stops being a copy
    OF anything, and there is no longer a site to promote it onto."""
    with pytest.raises(promote.PromoteRefused):
        promote.check_git_promote(
            staging_site=_Site(parent_site_id=None), staging_target=_Target(),
            live_site=LIVE, live_target=_Target())


# ── P4: what must never be copied ────────────────────────────────────────────

class _Server:
    name, panel_type = "Web One", None


def _tree(base: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """A live site and a staging copy that differ in every way that matters."""
    live, stg = base / "live", base / "staging"
    for d in (live, stg):
        (d / "wp-content" / "uploads").mkdir(parents=True)
        (d / "storage" / "app" / "public").mkdir(parents=True)
        (d / ".git").mkdir()
    # The live values that must survive.
    (live / ".env").write_text("DB_DATABASE=live_shop\n")
    (live / "wp-config.php").write_text("<?php define('DB_NAME','live_shop');\n")
    (live / "wp-content" / "uploads" / "invoice.pdf").write_text("a real customer upload")
    (live / "storage" / "app" / "public" / "avatar.png").write_text("live avatar")
    (live / ".git" / "HEAD").write_text("live-head")
    (live / "index.php").write_text("OLD CODE")
    (live / "gone.php").write_text("removed in staging")
    # Staging's versions, which must NOT arrive.
    (stg / ".env").write_text("DB_DATABASE=stg_shop\n")
    (stg / "wp-config.php").write_text("<?php define('DB_NAME','stg_shop');\n")
    (stg / "wp-content" / "uploads" / "old.pdf").write_text("stale snapshot")
    (stg / "storage" / "app" / "public" / "stale.png").write_text("stale avatar")
    (stg / ".git" / "HEAD").write_text("staging-head")
    (stg / "index.php").write_text("NEW CODE")
    return live, stg


@pytest.mark.skipif(not shutil.which("rsync"), reason="needs rsync")
def test_the_copy_runs_and_leaves_every_dangerous_file_alone(tmp_path):
    """The rules, proven by running the real command against a real tree.

    Asserting `--exclude=.env` appears in the command would pass whether or not rsync
    honoured it, and whether or not the path were even spelled the way rsync expects.
    """
    live, stg = _tree(tmp_path)
    cmd = promote.build_file_promote_command(
        staging_root=str(stg), live_root=str(live), stamp="20260811_120000")
    result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"})
    assert result.returncode == 0, result.stdout + result.stderr

    # The new code arrived...
    assert (live / "index.php").read_text() == "NEW CODE"
    assert not (live / "gone.php").exists(), "--delete should remove what staging dropped"

    # ...and the live site is still pointed at the live database.
    assert "live_shop" in (live / ".env").read_text()
    assert "live_shop" in (live / "wp-config.php").read_text()
    # ...and the customer's uploads are still there.
    assert (live / "wp-content" / "uploads" / "invoice.pdf").exists()
    assert not (live / "wp-content" / "uploads" / "old.pdf").exists()
    assert (live / "storage" / "app" / "public" / "avatar.png").exists()


@pytest.mark.skipif(not shutil.which("rsync"), reason="needs rsync")
def test_the_live_site_is_backed_up_before_anything_moves(tmp_path):
    """There is no undo. A backup that did not happen is discovered when it is needed."""
    live, stg = _tree(tmp_path)
    cmd = promote.build_file_promote_command(
        staging_root=str(stg), live_root=str(live), stamp="20260811_120000")
    subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                   env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"})

    backups = list((tmp_path / "serverally-backups").glob("promote-*.tar.gz"))
    assert backups, "no backup was written"
    listed = subprocess.run(["tar", "-tzf", str(backups[0])], capture_output=True, text=True)
    assert "index.php" in listed.stdout
    # And the replaced files are still on disk under a name the message names.
    assert list(tmp_path.glob("live.replaced-*")), "the previous files were not kept"


@pytest.mark.skipif(not shutil.which("rsync"), reason="needs rsync")
def test_a_failed_backup_stops_before_the_site_is_touched(tmp_path):
    """The order is the safety, so it is worth proving rather than reading."""
    live, stg = _tree(tmp_path)
    cmd = promote.build_file_promote_command(
        staging_root=str(stg), live_root=str(live), stamp="20260811_120000")
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "tar").write_text("#!/bin/sh\nexit 1\n")     # the backup cannot be written
    (fake / "tar").chmod(0o755)

    result = subprocess.run(
        ["bash", "-c", cmd], capture_output=True, text=True,
        env={"HOME": str(tmp_path), "PATH": f"{fake}:/usr/bin:/bin:/usr/local/bin"})
    assert result.returncode != 0
    assert (live / "index.php").read_text() == "OLD CODE", "the live site was changed anyway"


def test_the_promotion_is_confirmed_against_the_domain_the_server_holds():
    """The same rule as destroying a cloud instance: the loss is rarely "I meant not to", it
    is "I did it to the wrong one" — so a client cannot satisfy its own confirmation."""
    with pytest.raises(promote.PromoteRefused) as exc:
        promote.check_file_promote(staging_site=_Site(), live_site=LIVE, server=_Server(),
                                   confirm_domain="shop.example.co")   # one letter short
    assert "shop.example.com" in str(exc.value)
    promote.check_file_promote(staging_site=_Site(), live_site=LIVE, server=_Server(),
                               confirm_domain="  SHOP.example.com ")


def test_a_panel_server_is_refused_before_the_confirm_dialog():
    """The panel owns the configuration and would undo it on its own schedule. Said here
    rather than letting somebody get all the way to typing their domain first."""
    class _Panel:
        name, panel_type = "panel2", "cyberpanel"

    with pytest.raises(promote.PromoteRefused) as exc:
        promote.check_file_promote(staging_site=_Site(), live_site=LIVE, server=_Panel(),
                                   confirm_domain="shop.example.com")
    assert "cyberpanel" in str(exc.value)


def test_two_different_servers_are_refused_with_the_real_reason():
    """Not caution: the cross-server transfer caps at 512 MB, and a site that hit that would
    fail halfway with the live site already renamed."""
    with pytest.raises(promote.PromoteRefused) as exc:
        promote.check_file_promote(staging_site=_Site(server_id="srv-2"), live_site=LIVE,
                                   server=_Server(), confirm_domain="shop.example.com")
    assert "different servers" in str(exc.value)


def test_the_database_is_never_part_of_it():
    """The live database holds real orders and customers created since the copy was made.
    Schema changes belong in migrations, which the deploy path already runs."""
    source = inspect.getsource(promote.build_file_promote_command)
    for never in ("mysqldump", "mysql ", "psql", "pg_dump"):
        assert never not in source, f"the file copy touches the database ({never})"


def test_the_plugin_caveat_is_stated_rather_than_footnoted():
    """Every WordPress staging tool has this problem. The difference is whether the customer
    finds out from us before they press, or from their broken site afterwards."""
    assert "switched off" in promote.PLUGIN_CAVEAT
    assert "database" in promote.PLUGIN_CAVEAT


# ── proving the pin against real git, not against a string ───────────────────

@pytest.mark.skipif(not shutil.which("git"), reason="needs git")
def test_the_pin_actually_refuses_to_go_live_on_the_wrong_commit(tmp_path):
    """Asserting `rev-parse HEAD` appears in the command proves nothing about whether the
    comparison happens. This runs the real steps against a real repository.

    The disaster it prevents is quiet: a checkout that lands somewhere other than the commit
    that was reviewed, while every step reports success and the site goes live.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args, cwd=repo):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                              env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin",
                                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    git("init", "-q", "-b", "main")
    (repo / "a.txt").write_text("one")
    git("add", "-A"); git("commit", "-qm", "one")
    first = git("rev-parse", "HEAD").stdout.strip()
    (repo / "a.txt").write_text("two")
    git("add", "-A"); git("commit", "-qm", "two")
    second = git("rev-parse", "HEAD").stdout.strip()
    assert first != second

    def run_pin(commit: str):
        out = ""
        for _name, cmd in promote.pin_steps(str(repo), commit):
            r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                               env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
            out += r.stdout + r.stderr
            if r.returncode != 0:
                return r.returncode, out
        return 0, out

    # The older commit is reachable, so it checks out — and lands exactly there.
    code, _out = run_pin(first)
    assert code == 0
    assert git("rev-parse", "HEAD").stdout.strip() == first, "the pin did not move HEAD"

    # A commit that is not in this repository at all must stop, loudly, before anything
    # downstream runs.
    code, out = run_pin("0" * 40)
    assert code != 0, f"a nonexistent commit was accepted: {out}"


def test_a_production_site_cannot_be_promoted_from():
    """There is nothing to promote FROM a live site, and letting it through would deploy a
    site onto itself — or, with the wrong parent link, onto something else."""
    with pytest.raises(promote.PromoteRefused) as exc:
        promote.check_git_promote(
            staging_site=_Site(environment="production"), staging_target=_Target(),
            live_site=LIVE, live_target=_Target())
    assert "not a staging copy" in str(exc.value)

    with pytest.raises(promote.PromoteRefused):
        promote.check_file_promote(
            staging_site=_Site(environment="production"), live_site=LIVE,
            server=_Server(), confirm_domain="shop.example.com")
