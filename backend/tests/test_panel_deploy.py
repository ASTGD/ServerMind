"""Deploying to a site on a control-panel server.

The ordinary deploy goes live by rewriting the document root. On a panel server the panel
owns that file and rewrites it on its own schedule, so the change is silently reverted
later — which is why it used to be refused outright. This goes live by making the panel's
OWN document root a symlink instead, leaving the vhost untouched.

The behaviour tests RUN the generated script against real folders, because every failure
mode here is "the shell did something other than what the text implies": a customer's site
deleted instead of moved, a rollback that does not roll back, a symlink that swallowed the
directory it was replacing. None of those show up in an assertion about command text.
"""
import os
import shutil
import subprocess

import pytest

from app.services import deploy_service as dep


def sh(command: str, env: dict | None = None) -> subprocess.CompletedProcess:
    e = {**os.environ, **(env or {})}
    return subprocess.run(["bash", "-c", command], capture_output=True, text=True, env=e)


#: `mv -T` and `stat -c` are GNU. The product only ever runs on Linux servers and CI is
#: ubuntu-latest, so these run where it matters — but they are SKIPPED rather than quietly
#: weakened on a developer's Mac, because `mv -T` is load-bearing: without it, moving the
#: new link over an existing symlink-to-directory moves it INSIDE that directory.
gnu_only = pytest.mark.skipif(
    shutil.which("mv") is None or subprocess.run(
        ["bash", "-c", "mv --version >/dev/null 2>&1"]).returncode != 0,
    reason="needs GNU coreutils (mv -T); the product only runs on Linux",
)


def fake_web(tmp_path, *, code="200", body="the real page"):
    """A bin directory that stands in for the web server, so the file work can be tested
    without one. Returns a PATH prefix."""
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    (b / "curl").write_text(
        "#!/bin/bash\n"
        "out=''\n"
        'while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; *) shift;; esac; done\n'
        f'[ -n "$out" ] && printf %s {body!r} > "$out"\n'
        f'printf %s {code!r}\n')
    (b / "systemctl").write_text("#!/bin/bash\nexit 0\n")
    (b / "lswsctrl").write_text("#!/bin/bash\nexit 0\n")
    for f in ("curl", "systemctl", "lswsctrl"):
        os.chmod(b / f, 0o755)
    return str(b)


def run_link(tmp_path, domain, root, web_dir="public", **web):
    cmd = dep.build_panel_link_command(
        str(tmp_path / "home" / domain / "public_html"), root, web_dir, domain)
    return sh(f'export PATH="{fake_web(tmp_path, **web)}:$PATH"; {cmd}')


# ── The paths, which become filesystem paths ─────────────────────────────────

def test_only_panels_whose_layout_we_know_are_offered():
    """A panel we guess about is a panel whose customer website we would replace."""
    assert dep.supports_panel_deploy("cyberpanel") is True
    for other in ("cpanel", "plesk", "directadmin", "", None):
        assert dep.supports_panel_deploy(other) is False


def test_releases_live_beside_the_served_folder_never_inside_it():
    """The served folder is about to BECOME a symlink to the releases. Keeping them inside
    it would put the target inside its own link."""
    link = dep.panel_link_path("shop.example.com")
    root = dep.panel_deploy_root("shop.example.com")
    assert not root.startswith(link + "/")
    assert root != link
    assert os.path.dirname(root) == os.path.dirname(link)


def test_the_served_path_is_the_current_release():
    root = dep.panel_deploy_root("shop.example.com")
    assert dep.served_path(root, "public") == \
        "/home/shop.example.com/deploy/current/public"
    assert dep.served_path(root, "") == "/home/shop.example.com/deploy/current"


@pytest.mark.parametrize("bad", [
    "../../etc", "shop.example.com/../..", "sh op.com", "", "shop", "/etc/passwd",
    "shop.example.com\nrm -rf /", ".hidden.com", "-shop.com",
])
def test_a_domain_that_is_not_a_domain_never_becomes_a_path(bad):
    """This value is interpolated into `/home/<domain>/public_html`, which is then replaced
    with a symlink. It is validated, never escaped."""
    with pytest.raises(dep.InvalidDeploy):
        dep.panel_link_path(bad)


# ── What happens on the server ───────────────────────────────────────────────

@gnu_only
def test_nothing_is_touched_until_something_has_been_deployed(tmp_path):
    """A first deploy can fail as many times as it needs to; the site keeps serving."""
    home = tmp_path / "home" / "shop.example.com"
    (home / "public_html").mkdir(parents=True)
    (home / "public_html" / "index.html").write_text("<h1>the live site</h1>")

    r = run_link(tmp_path, "shop.example.com", str(home / "deploy"))
    assert r.returncode == 3
    assert dep.PANEL_LINK_OUTCOMES[3] in dep.explain_panel_link(3, r.stdout)
    # the customer's site is exactly as it was
    assert (home / "public_html" / "index.html").read_text() == "<h1>the live site</h1>"
    assert not (home / "public_html").is_symlink()


@gnu_only
def test_the_customers_existing_files_are_moved_aside_never_deleted(tmp_path):
    """The single most important property here. A deploy that eats the site it was pointed
    at is not recoverable from a log message."""
    home = tmp_path / "home" / "shop.example.com"
    (home / "public_html").mkdir(parents=True)
    (home / "public_html" / "index.php").write_text("<?php echo 'their site';")
    (home / "public_html" / "uploads").mkdir()
    (home / "public_html" / "uploads" / "photo.jpg").write_text("x")
    rel = home / "deploy" / "releases" / "20260804_120000" / "public"
    rel.mkdir(parents=True)
    (rel / "index.php").write_text("<?php echo 'deployed';")
    (home / "deploy" / "current").symlink_to(rel.parent)

    r = run_link(tmp_path, "shop.example.com", str(home / "deploy"))
    assert r.returncode == 0, r.stdout + r.stderr

    moved = [p for p in home.iterdir() if p.name.startswith("public_html.serverally-")]
    assert len(moved) == 1, "the old site must be kept"
    assert (moved[0] / "index.php").read_text() == "<?php echo 'their site';"
    assert (moved[0] / "uploads" / "photo.jpg").exists()
    # and it is named in the message, or nobody can find it again
    assert str(moved[0]) in dep.explain_panel_link(0, r.stdout)
    # the served folder is now the link
    assert (home / "public_html").is_symlink()
    assert os.path.realpath(home / "public_html") == os.path.realpath(rel)


@gnu_only
def test_an_empty_served_folder_is_replaced_without_leaving_a_copy(tmp_path):
    """Nothing to preserve, so no timestamped leftover to confuse anyone later."""
    home = tmp_path / "home" / "shop.example.com"
    (home / "public_html").mkdir(parents=True)
    rel = home / "deploy" / "releases" / "r1" / "public"
    rel.mkdir(parents=True)
    (rel / "index.html").write_text("hi")
    (home / "deploy" / "current").symlink_to(rel.parent)

    r = run_link(tmp_path, "shop.example.com", str(home / "deploy"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (home / "public_html").is_symlink()
    assert not [p for p in home.iterdir() if "serverally-" in p.name]


@gnu_only
def test_a_second_deploy_repoints_the_link_and_moves_nothing(tmp_path):
    """After the first serve the link exists. Every later deploy must be idempotent —
    a timestamped copy per deploy would fill the disk."""
    home = tmp_path / "home" / "shop.example.com"
    home.mkdir(parents=True)
    rel = home / "deploy" / "releases" / "r1" / "public"
    rel.mkdir(parents=True)
    (rel / "index.html").write_text("hi")
    (home / "deploy" / "current").symlink_to(rel.parent)
    (home / "public_html").symlink_to(home / "deploy" / "current" / "public")

    r = run_link(tmp_path, "shop.example.com", str(home / "deploy"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (home / "public_html").is_symlink()
    assert not [p for p in home.iterdir() if "serverally-" in p.name]


@gnu_only
def test_the_link_replaces_the_folder_rather_than_landing_inside_it(tmp_path):
    """`mv` without `-T` moves the new link INTO the directory it was meant to replace,
    leaving the site serving its old files while we report success."""
    home = tmp_path / "home" / "shop.example.com"
    home.mkdir(parents=True)
    rel = home / "deploy" / "releases" / "r1" / "public"
    rel.mkdir(parents=True)
    (rel / "index.html").write_text("deployed")
    (home / "deploy" / "current").symlink_to(rel.parent)
    (home / "public_html").symlink_to(home / "deploy" / "current" / "public")

    assert run_link(tmp_path, "shop.example.com", str(home / "deploy")).returncode == 0
    # nothing was nested inside the link's target
    assert not (rel / "public_html").exists()
    assert not (rel / "public_html.tmp").exists()
    assert not (home / "public_html.tmp").exists()


@gnu_only
def test_a_site_that_does_not_serve_is_put_back_exactly_as_it_was(tmp_path):
    """A web server that will not follow symlinks answers 403; a wrong web_dir answers a
    blank page. Both look fine to a status check and are total failures to a visitor."""
    home = tmp_path / "home" / "shop.example.com"
    (home / "public_html").mkdir(parents=True)
    (home / "public_html" / "index.php").write_text("<?php echo 'their site';")
    rel = home / "deploy" / "releases" / "r1" / "public"
    rel.mkdir(parents=True)
    (home / "deploy" / "current").symlink_to(rel.parent)

    r = run_link(tmp_path, "shop.example.com", str(home / "deploy"), code="403", body="")
    assert r.returncode == 5
    assert "put back" in dep.explain_panel_link(5, r.stdout)
    # the customer's site is back where it was, and is a real folder again
    assert not (home / "public_html").is_symlink()
    assert (home / "public_html").is_dir()
    assert (home / "public_html" / "index.php").read_text() == "<?php echo 'their site';"
    assert not [p for p in home.iterdir() if "serverally-" in p.name]


@gnu_only
def test_a_blank_200_counts_as_not_serving(tmp_path):
    """The standing rule: content, not a status code. A blank 200 is what a wrong web
    directory returns, and it is not a working site."""
    home = tmp_path / "home" / "shop.example.com"
    (home / "public_html").mkdir(parents=True)
    (home / "public_html" / "keep.txt").write_text("theirs")
    rel = home / "deploy" / "releases" / "r1" / "public"
    rel.mkdir(parents=True)
    (home / "deploy" / "current").symlink_to(rel.parent)

    r = run_link(tmp_path, "shop.example.com", str(home / "deploy"), code="200", body="")
    assert r.returncode == 5
    assert (home / "public_html" / "keep.txt").read_text() == "theirs"


@gnu_only
def test_a_redirect_counts_as_serving(tmp_path):
    """A site that redirects http to https answers 3xx with no body. That is the
    application responding, not a failure."""
    home = tmp_path / "home" / "shop.example.com"
    home.mkdir(parents=True)
    rel = home / "deploy" / "releases" / "r1" / "public"
    rel.mkdir(parents=True)
    (home / "deploy" / "current").symlink_to(rel.parent)

    r = run_link(tmp_path, "shop.example.com", str(home / "deploy"), code="301", body="")
    assert r.returncode == 0, r.stdout + r.stderr


@gnu_only
def test_a_file_where_the_folder_should_be_is_refused(tmp_path):
    home = tmp_path / "home" / "shop.example.com"
    home.mkdir(parents=True)
    (home / "public_html").write_text("not a folder")
    rel = home / "deploy" / "releases" / "r1" / "public"
    rel.mkdir(parents=True)
    (home / "deploy" / "current").symlink_to(rel.parent)

    r = run_link(tmp_path, "shop.example.com", str(home / "deploy"))
    assert r.returncode == 4
    assert (home / "public_html").read_text() == "not a folder"
