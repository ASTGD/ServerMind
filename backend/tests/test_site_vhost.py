"""Editing a site's web-server configuration by hand.

The escape hatch, and the most dangerous edit in the product: a vhost that does not parse
means the reload fails, and on a machine with forty sites that is forty sites' worth of
consequence for one typo. So the tests run the REAL generated command against a REAL file
with the web server stubbed, and check what is on disk afterwards — a save that is written
and then rolled back looks identical to one that worked if you only read the command text.
"""
import base64
import subprocess

import pytest

from app.services import vhost_service as vs


ORIGINAL = """\
# Created by ServerAlly for shop.example.com
server {
    listen 80;
    server_name shop.example.com;
    root /var/www/shop.example.com/public;
}
"""

NEW = """\
# Created by ServerAlly for shop.example.com
server {
    listen 80;
    server_name shop.example.com;
    root /var/www/shop.example.com/public;
    client_max_body_size 64m;
}
"""


def _stubs(tmp_path, *, config_ok=True, site_answers=True):
    binstub = tmp_path / "bin"
    binstub.mkdir(exist_ok=True)
    for name, body in (
        ("nginx", "exit 0" if config_ok else "exit 1"),
        ("apachectl", "exit 1"),
        ("systemctl", "exit 0"),
        ("curl", f"echo {200 if site_answers else '000'}"),
    ):
        p = binstub / name
        p.write_text(f"#!/bin/sh\n{body}\n")
        p.chmod(0o755)
    return binstub


def _save(tmp_path, content, **kw):
    cfg = tmp_path / "site.conf"
    cfg.write_text(ORIGINAL)
    binstub = _stubs(tmp_path, **kw)
    cmd = vs.build_save_command(str(cfg), "shop.example.com", content)
    proc = subprocess.run(["bash", "-c", f'export PATH="{binstub}:$PATH"; {cmd}'],
                          capture_output=True, text=True)
    return proc, cfg.read_text()


# ── It really writes ─────────────────────────────────────────────────────────

def test_a_good_configuration_is_saved(tmp_path):
    proc, text = _save(tmp_path, NEW)
    assert proc.returncode == 0, proc.stderr
    assert text == NEW


def test_nothing_is_left_behind(tmp_path):
    """A .bak or .tmp left in a config directory is not litter — nginx globs conf.d, so a
    leftover can be loaded as a second copy of the site."""
    _save(tmp_path, NEW)
    assert not list(tmp_path.glob("*.bak")) and not list(tmp_path.glob("*.tmp"))


def test_the_content_never_reaches_a_shell_unencoded(tmp_path):
    """A config file is arbitrary text — quotes, backslashes, dollars, newlines — so there
    is no quoting scheme worth arguing about. If the raw text ever appears in the command,
    some future edit has dropped the encoding."""
    nasty = 'server { root "/var/www/$(touch /tmp/pwned)`id`"; }\n'
    cmd = vs.build_save_command("/etc/nginx/sites-available/x", "x.example.com", nasty)
    assert nasty not in cmd and "touch /tmp/pwned" not in cmd
    assert base64.b64encode(nasty.encode()).decode() in cmd


# ── And it really puts it back ───────────────────────────────────────────────

def test_a_configuration_the_web_server_refuses_is_rolled_back(tmp_path):
    """The reason this cannot be a plain file write. A reload of a broken config does not
    break one site — it fails for the whole machine."""
    proc, text = _save(tmp_path, NEW, config_ok=False)
    assert proc.returncode == 4
    assert text == ORIGINAL, "the refused configuration was left on disk"
    assert not list(tmp_path.glob("*.bak"))


def test_a_site_that_stops_answering_is_rolled_back(tmp_path):
    """Parsing is not serving: a valid config can point at a folder that is not there."""
    proc, text = _save(tmp_path, NEW, site_answers=False)
    assert proc.returncode == 5
    assert text == ORIGINAL


def test_a_missing_file_changes_nothing(tmp_path):
    binstub = _stubs(tmp_path)
    cmd = vs.build_save_command(str(tmp_path / "nope.conf"), "shop.example.com", NEW)
    proc = subprocess.run(["bash", "-c", f'export PATH="{binstub}:$PATH"; {cmd}'],
                          capture_output=True, text=True)
    assert proc.returncode == 3


# ── Refused before it reaches the machine ────────────────────────────────────

@pytest.mark.parametrize("bad", ["", "   \n  ", None])
def test_an_empty_configuration_is_refused(bad):
    """Saving nothing would take the site off the server while looking like an edit. If
    that is what somebody wants, removing the site is the honest way to ask for it."""
    with pytest.raises(vs.VhostError):
        vs.check_content(bad)


def test_something_that_is_not_text_is_refused():
    with pytest.raises(vs.VhostError):
        vs.check_content("server {\x00}")


def test_an_enormous_paste_is_refused():
    with pytest.raises(vs.VhostError):
        vs.check_content("#" * (vs.MAX_BYTES + 1))


# ── The message is ours ──────────────────────────────────────────────────────

def test_a_rejected_configuration_says_the_other_sites_are_fine():
    """The first thing anyone thinks when a config is refused is "what did I just break".
    Answering that in the message is most of the value of having one."""
    ok, message = vs.explain(4, "nginx: [emerg] unexpected }")
    assert ok is False
    assert "put back" in message and "still running" in message


def test_success_says_what_was_actually_proven():
    ok, message = vs.explain(0, "saved")
    assert ok and "accepted" in message and "still answers" in message


# ── Blaming the right thing ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_server_we_cannot_connect_to_says_so_rather_than_blaming_the_site():
    """Found live. TestServer's host key changed, ServerAlly correctly refused the
    connection — and the Manage page reported "we could not work out which of this
    server's configuration files serves this site", which sent me looking at nginx for a
    problem that was on the connection. WHY it failed decides what the customer does next.
    """
    from app.services import php_service, ssh_service

    class _Server:
        id = "s"
        connection_type = "ssh"

    async def _boom(*_a, **_k):
        raise ssh_service.HostKeyMismatch("SHA256:old", "SHA256:new")

    original = php_service.connection_manager.execute
    php_service.connection_manager.execute = _boom
    try:
        state = await php_service.read(_Server())
    finally:
        php_service.connection_manager.execute = original

    assert state["unreachable"] is True
    assert "identity" in state["error"], state["error"]
    assert "PHP" not in state["error"], "a key mismatch is not a PHP problem"


@pytest.mark.asyncio
async def test_an_ordinary_probe_failure_still_reads_as_one():
    from app.services import php_service

    class _Server:
        id = "s"
        connection_type = "ssh"

    async def _boom(*_a, **_k):
        raise TimeoutError("no route")

    original = php_service.connection_manager.execute
    php_service.connection_manager.execute = _boom
    try:
        state = await php_service.read(_Server())
    finally:
        php_service.connection_manager.execute = original

    assert state["unreachable"] is True
    assert "identity" not in state["error"]
