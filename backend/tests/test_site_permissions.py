"""Putting a site's file ownership back — Ploi's "Reset permissions".

The whole feature is one recursive `chown`, so the whole risk is the path. An empty or
shallow document root would hand the web server ownership of the operating system, or of
every other customer's site on the machine. That is not a warning to show; it is a command
not to run.

The refusals are tested by RUNNING the generated command against real folders, because a
guard that exists in the text and not in the shell is not a guard.
"""
import os
import subprocess

import pytest

from app.services import permissions_service as ps


# ── The refusals ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", "   ", None])
def test_an_unknown_folder_is_refused(bad):
    """We do not know where the site lives, so there is nothing safe to reset."""
    with pytest.raises(ps.PermissionsError):
        ps.check_target(bad)


@pytest.mark.parametrize("bad", ["/", "/var", "/var/www", "/home", "/etc", "/usr", "/root"])
def test_a_system_or_shared_folder_is_refused(bad):
    """`/var/www` is the one that would actually happen: it is the parent of every site on
    a normal server, so resetting there hands the web server all of them."""
    with pytest.raises(ps.PermissionsError) as exc:
        ps.check_target(bad)
    assert "refused" in str(exc.value).lower() or "system folder" in str(exc.value)


@pytest.mark.parametrize("bad", ["/var/x", "/opt/app", "/a/b"])
def test_anything_too_shallow_to_be_one_site_is_refused(bad):
    with pytest.raises(ps.PermissionsError):
        ps.check_target(bad)


def test_a_relative_path_is_refused():
    with pytest.raises(ps.PermissionsError):
        ps.check_target("var/www/shop/public")


def test_a_traversal_is_refused():
    with pytest.raises(ps.PermissionsError):
        ps.check_target("/var/www/shop/../../etc")


def test_a_real_site_folder_is_accepted():
    assert ps.check_target("/var/www/shop.example.com/public") == \
        "/var/www/shop.example.com/public"
    assert ps.check_target("/var/www/shop.example.com/") == "/var/www/shop.example.com"


# ── The guard is on the machine too, not only in Python ─────────────────────

@pytest.mark.parametrize("bad", ["/var/www", "/home", "/"])
def test_the_command_itself_refuses_a_shallow_path(bad, tmp_path):
    """Belt and braces. The Python check runs here; this one runs on the machine about to
    be changed. If a path ever reached the command without passing the first check, it
    still must not run."""
    # Built by hand, bypassing check_target exactly as a future bug might.
    cmd = ps.build_command("/var/www/shop.example.com/public").replace(
        "T='/var/www/shop.example.com/public'", f"T='{bad}'")
    proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    assert proc.returncode != 0, f"{bad} was not refused by the command itself"
    assert "Refusing" in proc.stdout or "not on this server" in proc.stdout


# ── What it actually does ────────────────────────────────────────────────────

def _sandbox(tmp_path):
    """A folder deep enough to pass the guard, holding files with wrong ownership modes."""
    root = tmp_path / "var" / "www" / "shop.example.com" / "public"
    (root / "sub").mkdir(parents=True)
    (root / "index.php").write_text("<?php")
    (root / "sub" / "page.php").write_text("<?php")
    (root.parent / "artisan").write_text("#!/usr/bin/env php")
    os.chmod(root / "index.php", 0o777)
    os.chmod(root / "sub", 0o700)
    os.chmod(root.parent / "artisan", 0o600)
    return root


def test_files_and_folders_get_their_normal_permissions(tmp_path):
    """Run for real against real files. `chown` will not work without root, so the command
    is run with the ownership step neutralised — the modes are what this asserts."""
    root = _sandbox(tmp_path)
    cmd = ps.build_command(str(root)).replace('chown -R "$OWNER":"$OWNER" "$T"', "true")
    # `id -u` must find something, so point the user list at one that exists here.
    cmd = cmd.replace("for u in www-data nginx apache", f"for u in {os.environ.get('USER','root')}")
    proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert oct(os.stat(root / "index.php").st_mode)[-3:] == "644"
    assert oct(os.stat(root / "sub").st_mode)[-3:] == "755"


def test_the_runner_a_framework_needs_stays_executable(tmp_path):
    """Laravel's `artisan` has to keep running. A repair that stops it looks exactly like
    the repair having broken the site."""
    root = _sandbox(tmp_path)
    cmd = ps.build_command(str(root)).replace('chown -R "$OWNER":"$OWNER" "$T"', "true")
    cmd = cmd.replace("for u in www-data nginx apache", f"for u in {os.environ.get('USER','root')}")
    subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    assert oct(os.stat(root.parent / "artisan").st_mode)[-3:] == "755"


def test_it_never_reaches_outside_the_site(tmp_path):
    """The neighbour test. Everything above the site's folder must be untouched."""
    root = _sandbox(tmp_path)
    neighbour = tmp_path / "var" / "www" / "other.example.com"
    neighbour.mkdir(parents=True)
    (neighbour / "secret").write_text("x")
    os.chmod(neighbour / "secret", 0o600)
    cmd = ps.build_command(str(root)).replace('chown -R "$OWNER":"$OWNER" "$T"', "true")
    cmd = cmd.replace("for u in www-data nginx apache", f"for u in {os.environ.get('USER','root')}")
    subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    assert oct(os.stat(neighbour / "secret").st_mode)[-3:] == "600", "it touched another site"


# ── What the customer is told ────────────────────────────────────────────────

def test_it_says_how_many_files_it_actually_changed():
    ok, message = ps.explain(0, "owner=www-data fixed=12 remaining=0")
    assert ok and "12" in message and "www-data" in message


def test_nothing_to_do_says_so_rather_than_claiming_a_repair():
    ok, message = ps.explain(0, "owner=www-data fixed=0 remaining=0")
    assert ok and "Nothing needed changing" in message


def test_a_refusal_says_nothing_was_changed():
    for code in (3, 4, 5):
        ok, message = ps.explain(code, "")
        assert ok is False and "nothing was changed" in message.lower()
