"""Extra domains that answer for the same site.

The sharpest edge on the Manage screen: an alias is written into `server_name`, and that is
how the web server decides which site a visitor gets. Point it at a domain that already
belongs to a neighbour and their traffic silently arrives here instead — nothing on either
screen says why, which is what makes it worth refusing rather than warning about.

The apply command is RUN against real config files, because an `awk` pass that looks right
and edits the wrong line is exactly the bug this would produce.
"""
import subprocess

import pytest

from app.services import alias_service as al


NGINX = """\
server {
    listen 80;
    server_name shop.example.com;
    root /var/www/shop.example.com/public;
}
server {
    listen 443 ssl;
    server_name shop.example.com;
    root /var/www/shop.example.com/public;
}
"""

APACHE = """\
<VirtualHost *:80>
    ServerName shop.example.com
    ServerAlias old.example.com
    DocumentRoot /var/www/shop.example.com/public
</VirtualHost>
"""


def run(tmp_path, source: str, aliases: list[str], *, apache=False, answers=True):
    binstub = tmp_path / "bin"
    binstub.mkdir(exist_ok=True)
    for name, body in (
        ("nginx", "exit 0"), ("apachectl", "exit 0"), ("systemctl", "exit 0"),
        ("curl", f"echo {200 if answers else '000'}"),
    ):
        p = binstub / name
        p.write_text(f"#!/bin/sh\n{body}\n")
        p.chmod(0o755)
    cfg = tmp_path / "site.conf"
    cfg.write_text(source)
    cmd = al.build_apply_command(str(cfg), "shop.example.com", aliases, apache=apache)
    proc = subprocess.run(["bash", "-c", f'export PATH="{binstub}:$PATH"; {cmd}'],
                          capture_output=True, text=True)
    return proc.returncode, cfg.read_text(), proc.stdout + proc.stderr


# ── It really edits the file, and every block in it ──────────────────────────

def test_an_alias_is_added_to_every_server_name(tmp_path):
    """A site with separate http and https blocks has two. Updating one leaves the alias
    working on one scheme and 404ing on the other, which reads as "it half works"."""
    code, text, out = run(tmp_path, NGINX, ["www.example.com"])
    assert code == 0, out
    lines = [ln.strip() for ln in text.splitlines() if "server_name" in ln]
    assert len(lines) == 2, lines
    for ln in lines:
        assert ln == "server_name shop.example.com www.example.com;", ln


def test_the_sites_own_name_stays_first(tmp_path):
    """nginx uses the first name for redirects it builds itself. Losing that ordering
    changes what the site calls itself."""
    _code, text, _out = run(tmp_path, NGINX, ["a.example.com", "b.example.com"])
    assert "server_name shop.example.com a.example.com b.example.com;" in text


def test_removing_the_last_alias_restores_the_original_line(tmp_path):
    """Removal runs the same command as adding, so there is no second path to get wrong."""
    _c1, text, _o = run(tmp_path, NGINX, ["www.example.com"])
    tmp = tmp_path / "site.conf"
    tmp.write_text(text)
    code, after, out = run(tmp_path, text, [])
    assert code == 0, out
    assert after.count("server_name shop.example.com;") == 2
    assert "www.example.com" not in after


def test_indentation_is_preserved(tmp_path):
    """A config that comes back re-indented looks like something else edited it."""
    _code, text, _out = run(tmp_path, NGINX, ["www.example.com"])
    assert "    server_name shop.example.com www.example.com;" in text


def test_apache_uses_serveralias_not_servername(tmp_path):
    """Apache splits it in two: one canonical ServerName, the rest as ServerAlias.
    Writing several names onto ServerName is a config error, not a style choice."""
    code, text, out = run(tmp_path, APACHE, ["www.example.com"], apache=True)
    assert code == 0, out
    assert "ServerName shop.example.com" in text
    assert "ServerAlias www.example.com" in text
    # The old alias line is replaced, not appended to.
    assert text.count("ServerAlias") == 1
    assert "old.example.com" not in text


# ── And it puts the file back when anything objects ──────────────────────────

def test_a_config_the_web_server_refuses_is_rolled_back(tmp_path):
    binstub = tmp_path / "bin"
    binstub.mkdir(exist_ok=True)
    for name, body in (("nginx", "exit 1"), ("apachectl", "exit 1"),
                       ("systemctl", "exit 0"), ("curl", "echo 200")):
        p = binstub / name
        p.write_text(f"#!/bin/sh\n{body}\n")
        p.chmod(0o755)
    cfg = tmp_path / "site.conf"
    cfg.write_text(NGINX)
    cmd = al.build_apply_command(str(cfg), "shop.example.com", ["www.example.com"],
                                 apache=False)
    proc = subprocess.run(["bash", "-c", f'export PATH="{binstub}:$PATH"; {cmd}'],
                          capture_output=True, text=True)
    assert proc.returncode == 4
    assert cfg.read_text() == NGINX, "the refused configuration was left on disk"
    assert not list(tmp_path.glob("*.bak")) and not list(tmp_path.glob("*.tmp"))


def test_a_site_that_stops_answering_is_rolled_back(tmp_path):
    """Parsing is not serving. This is the check that makes the whole thing safe to press."""
    code, text, _out = run(tmp_path, NGINX, ["www.example.com"], answers=False)
    assert code == 5
    assert text == NGINX


def test_a_missing_configuration_changes_nothing(tmp_path):
    cmd = al.build_apply_command(str(tmp_path / "nope.conf"), "shop.example.com", [],
                                 apache=False)
    proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    assert proc.returncode == 3


# ── Refused before it ever reaches the server ────────────────────────────────

@pytest.mark.parametrize("bad", [
    "", "   ", "not a domain", "https://www.example.com", "www.example.com/path",
    "example", "-bad.example.com", "bad-.example.com", "a" * 70 + ".com",
])
def test_something_that_is_not_a_domain_is_refused(bad):
    with pytest.raises(al.AliasError):
        al.clean(bad)


def test_a_wildcard_is_refused_with_the_reason():
    with pytest.raises(al.AliasError) as exc:
        al.clean("*.example.com")
    assert "every subdomain" in str(exc.value)


def test_a_url_is_refused_rather_than_quietly_repaired():
    """Repairing it silently gives the customer something they did not type, on a value
    that decides whose visitors land where."""
    with pytest.raises(al.AliasError) as exc:
        al.clean("https://www.example.com")
    assert "just the domain" in str(exc.value)


def test_it_is_normalised_the_way_a_web_server_reads_it():
    assert al.clean("  WWW.Example.COM.  ") == "www.example.com"


def test_the_sites_own_domain_is_refused():
    with pytest.raises(al.AliasError):
        al.check_new("shop.example.com", domain="shop.example.com", existing=[])


def test_a_duplicate_is_refused():
    with pytest.raises(al.AliasError):
        al.check_new("www.example.com", domain="shop.example.com",
                     existing=["www.example.com"])


def test_a_domain_another_site_already_answers_for_is_refused():
    """The one that matters. The web server hands the name to whichever block claims it, so
    the neighbour's visitors would arrive here with nothing on either screen saying why."""
    with pytest.raises(al.AliasError) as exc:
        al.check_new("blog.example.com", domain="shop.example.com", existing=[],
                     taken={"blog.example.com": "blog.example.com"})
    assert "already belongs to" in str(exc.value)
    assert "take that site's visitors" in str(exc.value)


def test_a_free_domain_is_accepted():
    assert al.check_new("WWW.Example.com", domain="shop.example.com", existing=[],
                        taken={"other.example.com": "other"}) == "www.example.com"


# ── The message says what still has to happen ────────────────────────────────

def test_success_says_dns_and_https_are_not_done_yet():
    """Adding the alias makes the SERVER answer for it. It does not point the domain here
    and it does not put it on the certificate — and a customer who is not told will report
    both as bugs."""
    ok, message = al.explain(0, "applied")
    assert ok
    assert "DNS" in message and "certificate" in message


def test_a_refusal_says_the_other_sites_are_fine():
    ok, message = al.explain(4, "")
    assert ok is False
    assert "unaffected" in message


# ── The endpoint refuses before it reaches the server ────────────────────────

def test_the_endpoint_builds_the_taken_map_from_this_server_only():
    """Scoped to the server, because the collision is a web-server one: a name only fights
    with other names on the same machine. Scoping it wider would refuse a legitimate alias
    the customer uses on a different server."""
    import inspect

    from app.routers import sites as router
    src = inspect.getsource(router.add_site_alias)
    assert "Site.server_id == server.id" in src
    assert "Site.id != site.id" in src
    # And every name that site answers for, not just its domain.
    assert "row.aliases" in src


def test_the_endpoint_checks_before_it_writes():
    import inspect

    from app.routers import sites as router
    src = inspect.getsource(router.add_site_alias)
    assert src.index("check_new") < src.index("_alias_apply")


def test_the_row_is_only_saved_after_the_server_accepted_it():
    """Saving first would leave the page showing an alias the web server never took —
    the same "we said it worked" failure the rest of the product exists to avoid."""
    import inspect

    from app.routers import sites as router
    src = inspect.getsource(router._alias_apply)
    assert src.index("if not ok:") < src.index("site.aliases = aliases")


def test_removing_something_that_is_not_an_alias_is_a_404():
    import inspect

    from app.routers import sites as router
    src = inspect.getsource(router.remove_site_alias)
    assert "not an alias of this site" in src
    assert "404" in src
