"""Matching a site to the configuration file that serves it.

Switching the wrong site's PHP version takes down a site nobody was touching, and on a
server with forty vhosts a near-miss is not unlikely. So the match has to be something
that actually decides the question, and when nothing does the answer is "we cannot tell"
rather than the closest thing.
"""
import pytest

from app.services import php_service as php


def _site(config, root=None, version="8.3"):
    return {"config": config, "name": config.rsplit("/", 1)[-1],
            "socket": f"/run/php/php{version}-fpm.sock", "root": root, "version": version}


SITES = [
    _site("/etc/nginx/sites-available/shop.example.com", "/var/www/shop/public"),
    _site("/etc/nginx/sites-available/blog.example.com", "/var/www/blog"),
    _site("/etc/nginx/sites-available/other", "/var/www/other"),
]


# ── The match that decides it ────────────────────────────────────────────────

def test_the_folder_a_config_serves_identifies_the_site():
    found = php.config_for_site(SITES, "/var/www/shop/public", "shop.example.com")
    assert found["config"] == "/etc/nginx/sites-available/shop.example.com"


def test_a_trailing_slash_is_the_same_folder():
    assert php.config_for_site(SITES, "/var/www/blog/", "blog.example.com")["root"] \
        == "/var/www/blog"


def test_the_domain_is_not_what_decides_it():
    """A vhost file can be called anything. The folder it serves cannot be two places."""
    found = php.config_for_site(SITES, "/var/www/other", "anything-at-all.com")
    assert found["config"] == "/etc/nginx/sites-available/other"


# ── Refusing rather than guessing ────────────────────────────────────────────

def test_a_folder_nothing_serves_is_not_matched_to_the_nearest_thing():
    assert php.config_for_site(SITES, "/var/www/somewhere-else", "new.example.com") is None


def test_two_configs_serving_one_folder_is_refused():
    """An http and an https vhost for the same site is ordinary. Picking one of them is
    how only half a site gets switched."""
    pair = [_site("/etc/nginx/sites-available/a", "/var/www/shop"),
            _site("/etc/nginx/sites-available/a-ssl", "/var/www/shop")]
    assert php.config_for_site(pair, "/var/www/shop", "shop.example.com") is None


def test_nothing_on_the_server_is_not_a_match():
    assert php.config_for_site([], "/var/www/shop", "shop.example.com") is None


def test_an_unknown_folder_does_not_fall_through_to_a_name_match():
    """The site's folder IS known and matches nothing here. Falling back to the filename
    would then hand back a config serving somewhere else entirely."""
    sites = [_site("/etc/nginx/sites-available/shop.example.com", "/var/www/DIFFERENT")]
    assert php.config_for_site(sites, "/var/www/shop", "shop.example.com") is None


# ── The fallback, for a config we cannot read a root out of ──────────────────

def test_a_config_with_no_readable_root_falls_back_to_its_name():
    sites = [_site("/etc/nginx/sites-available/shop.example.com", None)]
    assert php.config_for_site(sites, None, "shop.example.com") is not None
    sites = [_site("/etc/httpd/conf.d/shop.example.com.conf", None)]
    assert php.config_for_site(sites, None, "shop.example.com") is not None


def test_the_name_fallback_still_refuses_when_it_is_ambiguous():
    sites = [_site("/etc/nginx/sites-available/shop.example.com", None),
             _site("/etc/httpd/conf.d/shop.example.com", None)]
    assert php.config_for_site(sites, None, "shop.example.com") is None


def test_a_name_that_matches_nothing_is_not_matched():
    sites = [_site("/etc/nginx/sites-available/somebody-else.com", None)]
    assert php.config_for_site(sites, None, "shop.example.com") is None


# ── The probe has to supply what the match needs ─────────────────────────────

def test_the_probe_reports_the_folder_each_config_serves(tmp_path):
    """Run the real probe against real config files, because asserting that the extraction
    APPEARS in the script passed happily when the value it extracts was no longer being
    reported — the site would then have no root, and the match would fall back to the
    filename for every vhost on the server.
    """
    import subprocess

    (tmp_path / "shop.example.com").write_text(
        "server {\n  root /var/www/shop/public;\n"
        "  location ~ .php$ { fastcgi_pass unix:/run/php/php8.3-fpm.sock; }\n}\n")
    (tmp_path / "legacy.conf").write_text(
        "<VirtualHost *:80>\n  DocumentRoot /var/www/legacy\n"
        "  SetHandler proxy:unix:/run/php/php7.4-fpm.sock\n</VirtualHost>\n")

    probe = php.build_probe().replace(
        "/etc/nginx/sites-available /etc/nginx/conf.d "
        "/etc/apache2/sites-available /etc/httpd/conf.d", str(tmp_path))
    out = subprocess.run(["bash", "-c", probe], capture_output=True, text=True).stdout
    # The parser only keeps paths under /etc/, so read the raw lines here.
    lines = [ln for ln in out.splitlines() if "|site|" in ln]

    assert any(ln.endswith("|/var/www/shop/public") for ln in lines), lines
    assert any(ln.endswith("|/var/www/legacy") for ln in lines), lines


def test_a_probe_line_without_a_root_is_still_understood():
    """Older output, or a config we could not read a root from. It has to degrade to the
    name fallback rather than dropping the site out of the list."""
    line = f"{php._SENTINEL}|site|/etc/nginx/sites-available/x|/run/php/php8.3-fpm.sock"
    parsed = php.parse_probe(line)
    assert parsed["sites"] and parsed["sites"][0]["root"] is None
    assert parsed["sites"][0]["version"] == "8.3"


def test_the_probe_result_carries_the_root_when_there_is_one():
    line = (f"{php._SENTINEL}|site|/etc/nginx/sites-available/x"
            f"|/run/php/php8.3-fpm.sock|/var/www/x")
    assert php.parse_probe(line)["sites"][0]["root"] == "/var/www/x"


@pytest.mark.parametrize("version", ["8.3", "8.1", "7.4"])
def test_a_switch_only_ever_rewrites_the_config_it_was_given(version):
    cmd = php.build_switch_command("/etc/nginx/sites-available/shop", version, "shop.com")
    assert "/etc/nginx/sites-available/shop" in cmd
    # The safety that makes this survivable at all: a copy first, and the site proved to
    # still serve real content afterwards.
    assert ".bak" in cmd
