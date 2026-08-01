"""Site discovery (docs/POSITIONING-CATEGORY.md §8 — discover and operate, never provision).

The parser has to survive four different web-server dialects on servers we do not control, so
these tests feed it real config output rather than tidy fixtures. Two properties matter most:

1. **The probe cannot change the server.** It runs unattended across a whole fleet, so a
   mutating verb slipping into it would be a fleet-wide incident. Asserted the same way
   ``threat_service`` is.
2. **Junk never reaches the inventory.** nginx's ``server_name _`` catch-all, ``localhost`` and
   bare IPs are not sites. An inventory full of entries nobody can visit is worse than no
   inventory at all, because it destroys trust in the whole list.
"""
from __future__ import annotations

import re

import pytest

from app.services import site_service as sites
from app.services.site_service import is_real_domain, parse_discovery

S = "___SM_SITE___"


# ── The probe is read-only ───────────────────────────────────────────────────

def test_the_probe_contains_no_mutating_verb():
    """It runs unattended on every server in a fleet. Anything that could write, install,
    restart or reach the network has no business in an inventory scan."""
    cmd = sites.build_discovery_command()
    mutators = (
        "rm", "rmdir", "mv", "cp", "dd", "mkfs", "chmod", "chown", "chattr", "tee",
        "truncate", "install", "apt", "yum", "dnf", "systemctl", "service", "kill",
        "pkill", "reboot", "shutdown", "curl", "wget", "nc", "scp", "mysql", "psql",
        "crontab", "useradd", "usermod",
    )
    found = [m for m in mutators
             if re.search(r"(?<![\w-])" + re.escape(m) + r"(?![\w-])", cmd)]
    assert not found, f"mutating verb(s) in the discovery probe: {found}"
    assert "sed -i" not in cmd, "in-place edit in a read-only probe"


def test_the_probe_never_reads_application_config():
    """``wp-config.php`` holds database credentials. WordPress is detected from the presence of
    ``wp-includes`` instead, so the inventory can never carry a customer's DB password."""
    cmd = sites.build_discovery_command()
    assert "wp-config" not in cmd


def test_the_probe_is_valid_shell():
    """It is assembled from four dialect-specific fragments; a quoting slip would make the
    whole scan silently return nothing, which reads as "this server has no sites"."""
    import subprocess
    result = subprocess.run(["bash", "-n"], input=sites.build_discovery_command(),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_the_probe_survives_a_server_with_no_timeout_binary():
    """`_t` must fall back to running unbounded. A missing binary emitting nothing would look
    exactly like a server with no websites — the same fail-open reasoning as the threat scan."""
    cmd = sites.build_discovery_command()
    assert "command -v timeout" in cmd
    assert 'else "$@"' in cmd


# ── Junk never becomes a site ────────────────────────────────────────────────

@pytest.mark.parametrize("junk", [
    "_",              # nginx's catch-all — the most common false site
    "localhost", "localhost.localdomain", "default", "default_server",
    "*", "", "   ", "0.0.0.0", "127.0.0.1", "::1",
    "192.168.1.10",   # an IP is not a domain
    "server",         # no dot
    "not a domain",
    "-leading-hyphen.com",
    "a" * 300 + ".com",
])
def test_junk_is_not_a_site(junk):
    assert is_real_domain(junk) is False


@pytest.mark.parametrize("good", [
    "acmeshop.com", "www.acmeshop.com", "shop.acme.co.uk",
    "news.rmp.gov.bd", "a-b.example.com", "*.wildcard.com",
    "ACMESHOP.COM",           # case is normalised
    "trailing-dot.com.",      # a config may end an FQDN with a dot
])
def test_a_real_domain_is_accepted(good):
    assert is_real_domain(good) is True


# ── nginx ────────────────────────────────────────────────────────────────────

def test_nginx_vhosts_are_parsed_with_root_and_ssl():
    output = "\n".join([
        f"{S}|nginx|acmeshop.com,www.acmeshop.com|/var/www/acmeshop|yes",
        f"{S}|nginx|blog.acme.com|/var/www/blog|no",
    ])
    found, truncated = parse_discovery(output)
    assert not truncated
    assert [s.domain for s in found] == ["acmeshop.com", "blog.acme.com"]

    shop = found[0]
    assert shop.aliases == ["www.acmeshop.com"]
    assert shop.doc_root == "/var/www/acmeshop"
    assert shop.has_ssl is True
    assert found[1].has_ssl is False


def test_the_nginx_catch_all_block_is_dropped():
    """`server_name _;` is on nearly every nginx install. Without this the first "site" in the
    list is one nobody can visit."""
    found, _ = parse_discovery(f"{S}|nginx|_|/usr/share/nginx/html|no")
    assert found == []


def test_a_block_with_both_a_real_name_and_junk_keeps_the_real_one():
    found, _ = parse_discovery(f"{S}|nginx|_,acmeshop.com,localhost|/var/www/x|no")
    assert len(found) == 1 and found[0].domain == "acmeshop.com"
    assert "localhost" not in found[0].aliases


# ── Apache, OpenLiteSpeed, CyberPanel ────────────────────────────────────────

def test_apache_namevhosts_are_parsed():
    found, _ = parse_discovery(f"{S}|apache|clientsite.org||no")
    assert len(found) == 1
    assert found[0].domain == "clientsite.org" and found[0].source == "apache"


def test_cyberpanel_child_domains_are_parsed():
    """CyberPanel puts child domains under the account home, and they were being missed by an
    earlier scan for exactly this reason (see the 2026-07-15 threat-scope fix)."""
    output = "\n".join([
        f"{S}|cyberpanel|desktopit.net||no",
        f"{S}|cyberpanel|news.rmp.gov.bd||no",
    ])
    found, _ = parse_discovery(output)
    assert {s.domain for s in found} == {"desktopit.net", "news.rmp.gov.bd"}


def test_a_domain_reported_by_two_sources_appears_once():
    """A CyberPanel box reports the same domain through the CLI *and* nginx. Listing it twice
    would make the whole inventory look broken."""
    output = "\n".join([
        f"{S}|cyberpanel|acmeshop.com||no",
        f"{S}|nginx|acmeshop.com|/home/acmeshop.com/public_html|yes",
    ])
    found, _ = parse_discovery(output)
    assert len(found) == 1
    merged = found[0]
    # The first source wins the label, but facts the second source knew are filled in.
    assert merged.source == "cyberpanel"
    assert merged.doc_root == "/home/acmeshop.com/public_html"
    assert merged.has_ssl is True


# ── What each site runs ──────────────────────────────────────────────────────

def test_wordpress_is_detected_with_its_version():
    output = "\n".join([
        f"{S}|nginx|acmeshop.com|/var/www/acmeshop|yes",
        f"{S}APP|/var/www/acmeshop|wordpress|6.9.1",
    ])
    found, _ = parse_discovery(output)
    assert found[0].app_type == "wordpress"
    assert found[0].app_version == "6.9.1"


def test_an_app_one_level_below_the_doc_root_is_still_matched():
    """Laravel serves from ``/public``, so the doc root and the app root differ by a level.
    Matching only on an exact path would report every Laravel site as plain PHP."""
    output = "\n".join([
        f"{S}|nginx|api.acme.com|/var/www/api/public|yes",
        f"{S}APP|/var/www/api|laravel|",
    ])
    found, _ = parse_discovery(output)
    assert found[0].app_type == "laravel"


def test_a_site_with_a_doc_root_but_no_known_app_is_php_not_unknown():
    found, _ = parse_discovery(f"{S}|nginx|acmeshop.com|/var/www/acmeshop|no")
    assert found[0].app_type == "php"


def test_a_site_with_no_doc_root_stays_unknown():
    """Apache's ``-S`` gives a name without a path, so guessing would be inventing."""
    found, _ = parse_discovery(f"{S}|apache|clientsite.org||no")
    assert found[0].app_type == "unknown"


# ── Robustness on servers we do not control ──────────────────────────────────

def test_empty_output_is_no_sites_not_a_crash():
    assert parse_discovery("") == ([], False)
    assert parse_discovery(None) == ([], False)  # type: ignore[arg-type]


def test_unrelated_output_is_ignored():
    """A login banner, an SSH warning or a stray shell error must not become a site."""
    noise = "\n".join([
        "Welcome to Ubuntu 24.04 LTS",
        "nginx: [warn] duplicate MIME type",
        "bash: line 1: apachectl: command not found",
        "Last login: Sat Jul 26 09:12:01 2026",
    ])
    assert parse_discovery(noise) == ([], False)


def test_a_truncated_or_malformed_line_is_skipped():
    output = "\n".join([
        f"{S}|nginx",                                     # too few fields
        f"{S}|",
        f"{S}|nginx|good.example.com|/var/www/g|no",
    ])
    found, _ = parse_discovery(output)
    assert [s.domain for s in found] == ["good.example.com"]


def test_the_list_is_capped_and_says_so():
    """A shared host can have hundreds of vhosts. Silently returning the first 200 would read
    as a complete inventory — the caller has to be told."""
    output = "\n".join(
        f"{S}|nginx|site{i}.example.com|/var/www/{i}|no" for i in range(sites.MAX_SITES + 25)
    )
    found, truncated = parse_discovery(output)
    assert len(found) == sites.MAX_SITES
    assert truncated is True


def test_a_list_within_the_cap_is_not_marked_truncated():
    output = "\n".join(f"{S}|nginx|s{i}.example.com||no" for i in range(5))
    _found, truncated = parse_discovery(output)
    assert truncated is False


def test_sites_come_back_in_a_stable_order():
    """The page is searched and compared between scans, so the order must not wobble."""
    output = "\n".join([
        f"{S}|nginx|zebra.com||no", f"{S}|nginx|alpha.com||no", f"{S}|nginx|middle.com||no",
    ])
    found, _ = parse_discovery(output)
    assert [s.domain for s in found] == ["alpha.com", "middle.com", "zebra.com"]


def test_a_trailing_slash_on_the_doc_root_is_normalised():
    """Otherwise the same site scanned twice looks like two different paths, and app matching
    against ``/var/www/x`` would miss ``/var/www/x/``."""
    output = "\n".join([
        f"{S}|nginx|acmeshop.com|/var/www/acmeshop/|no",
        f"{S}APP|/var/www/acmeshop|wordpress|6.9",
    ])
    found, _ = parse_discovery(output)
    assert found[0].doc_root == "/var/www/acmeshop"
    assert found[0].app_type == "wordpress"


@pytest.mark.asyncio
async def test_discovery_refuses_a_server_without_ssh():
    """Windows and hosting-panel connections have no shell to run this in; saying so beats a
    confusing empty result."""
    class Srv:
        connection_type = "winrm"
        name = "win-01"

    found, truncated, error = await sites.discover(Srv())
    assert found == [] and truncated is False
    assert "SSH" in error


@pytest.mark.asyncio
async def test_an_unreachable_server_reports_a_reason_not_an_exception(monkeypatch):
    """One offline server must not stop a fleet-wide scan."""
    async def boom(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr(sites.connection_manager, "execute", boom)

    class Srv:
        connection_type = "ssh"
        name = "web-01"

    found, _truncated, error = await sites.discover(Srv())
    assert found == []
    assert "web-01" in error


# ── The probe → parser contract, proven by actually running the probe ─────────
# The bug this catches: the probe's fragments drifted to three different field layouts, so an
# nginx line's doc root was read out of the ssl column. String inspection did not catch it and
# the unit tests did not either, because I had aligned the FIXTURES with my intent rather than
# with what the probe emits. Running the real probe is the only check that closes that gap.

def _run_probe_with_fakes(tmp_path, nginx_dump: str = "", apache_dump: str = "") -> str:
    """Execute the real discovery command with fake nginx/apachectl on PATH."""
    import os
    import subprocess

    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "nginx").write_text(f"#!/bin/sh\ncat <<'EOF'\n{nginx_dump}\nEOF\n")
    (fake / "apachectl").write_text(f"#!/bin/sh\ncat <<'EOF'\n{apache_dump}\nEOF\n")
    for name in ("nginx", "apachectl"):
        os.chmod(fake / name, 0o755)

    env = {**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"}
    result = subprocess.run(["bash", "-c", sites.build_discovery_command()],
                            capture_output=True, text=True, env=env, timeout=60)
    return result.stdout


def test_the_real_probe_output_parses_into_the_right_columns(tmp_path):
    """End-to-end: real awk over a real nginx -T dump, straight into the real parser.

    This is the test that would have caught the field-layout drift immediately.
    """
    nginx_dump = """
http {
    server {
        listen 443 ssl;
        server_name acmeshop.com www.acmeshop.com;
        root /var/www/acmeshop;
        ssl_certificate /etc/letsencrypt/live/acmeshop.com/fullchain.pem;
    }
    server {
        listen 80;
        server_name _;
        root /usr/share/nginx/html;
    }
    server {
        listen 80;
        server_name blog.acme.com;
        root /var/www/blog;
    }
}
"""
    output = _run_probe_with_fakes(tmp_path, nginx_dump=nginx_dump)
    found, _truncated = parse_discovery(output)

    domains = {s.domain: s for s in found}
    assert "acmeshop.com" in domains, f"probe output was: {output!r}"
    assert "blog.acme.com" in domains
    assert "_" not in domains, "the nginx catch-all became a site"

    shop = domains["acmeshop.com"]
    # The columns that were previously crossed.
    assert shop.doc_root == "/var/www/acmeshop", "doc root is in the wrong column"
    assert shop.has_ssl is True, "ssl flag is in the wrong column"
    assert shop.aliases == ["www.acmeshop.com"]
    assert domains["blog.acme.com"].has_ssl is False


def test_the_real_probe_parses_apache_vhosts(tmp_path):
    apache_dump = """VirtualHost configuration:
*:443                  is a NameVirtualHost
         port 443 namevhost clientsite.org (/etc/apache2/sites-enabled/client.conf:1)
         port 443 namevhost second.example.com (/etc/apache2/sites-enabled/two.conf:1)
"""
    output = _run_probe_with_fakes(tmp_path, apache_dump=apache_dump)
    found, _ = parse_discovery(output)
    domains = {s.domain for s in found}
    assert {"clientsite.org", "second.example.com"} <= domains, f"probe output: {output!r}"


def test_every_line_the_real_probe_emits_has_five_fields(tmp_path):
    """The invariant the parser depends on, checked against real output rather than the
    docstring that claimed it."""
    nginx_dump = """
server {
    server_name a.example.com;
    root /var/www/a;
}
"""
    apache_dump = "         port 80 namevhost b.example.com (/etc/apache2/x.conf:1)\n"
    output = _run_probe_with_fakes(tmp_path, nginx_dump=nginx_dump, apache_dump=apache_dump)

    site_lines = [ln for ln in output.splitlines() if ln.startswith(f"{S}|")]
    assert site_lines, f"probe emitted no site lines: {output!r}"
    for line in site_lines:
        assert len(line.split("|")) == 5, f"wrong field count: {line!r}"


# ── The per-site detail probe ────────────────────────────────────────────────
#
# One site's facts: where its files are, who owns them, which PHP, how big. Same three
# guarantees as every other probe in this file — read-only, valid shell, fail-open — plus
# the parsing, because two web servers write a document root two different ways.

def test_the_detail_probe_contains_no_mutating_verb():
    """It runs whenever anyone opens a site page. Looking at a website must never change it."""
    cmd = sites.build_detail_command("shop.example.com", "/var/www/shop")
    mutators = (
        "rm", "rmdir", "mv", "cp", "dd", "mkfs", "chmod", "chown", "chattr", "tee",
        "truncate", "install", "apt", "yum", "dnf", "systemctl", "service", "kill",
        "pkill", "reboot", "shutdown", "curl", "wget", "nc", "scp", "mysql", "psql",
        "crontab", "useradd", "usermod",
    )
    found = [m for m in mutators
             if re.search(r"(?<![\w-])" + re.escape(m) + r"(?![\w-])", cmd)]
    assert not found, f"mutating verb(s) in the detail probe: {found}"
    assert "sed -i" not in cmd, "in-place edit in a read-only probe"


def test_the_detail_probe_is_valid_shell():
    import subprocess
    result = subprocess.run(
        ["bash", "-n"], text=True, capture_output=True,
        input=sites.build_detail_command("shop.example.com", "/var/www/shop"))
    assert result.returncode == 0, result.stderr


def test_the_detail_probe_survives_a_server_with_no_timeout_binary():
    """`du` is the one bounded call here. If `timeout` is absent the probe must still run —
    silently emitting nothing would show the site as having no files at all."""
    cmd = sites.build_detail_command("shop.example.com", "/var/www/shop")
    assert "command -v timeout" in cmd and 'else "$@"' in cmd


def test_a_domain_with_shell_characters_cannot_become_a_second_command():
    """The domain is the one piece of customer input that reaches this probe.

    Asserting the payload is ABSENT from the command would be the wrong test — quoting
    keeps the text and removes its power. So parse the generated line the way a shell
    does and check the payload arrives as ONE argument to grep, with no second command
    behind it.
    """
    import shlex
    payload = "evil.com; touch /tmp/pwned"
    line = next(ln for ln in sites.build_detail_command(payload, None).splitlines()
                if ln.startswith("CONF="))
    inner = line[line.index("(") + 1:line.rindex("|")]      # the grep, before the pipe
    argv = shlex.split(inner)
    assert payload in argv, f"the domain did not survive as one argument: {argv}"
    assert "touch" not in argv, f"the payload became its own command: {argv}"


def test_it_reads_an_nginx_document_root_and_php_version():
    out = "\n".join([
        "___SM_SITEDETAIL___|config|/etc/nginx/sites-enabled/shop.conf",
        "___SM_SITEDETAIL___|public|/var/www/shop.example.com/public",
        "___SM_SITEDETAIL___|path|/var/www/shop.example.com",
        "___SM_SITEDETAIL___|user|www-data",
        "___SM_SITEDETAIL___|sizekb|20480",
        "___SM_SITEDETAIL___|php|8.3",
    ])
    d = sites.parse_detail(out)
    assert d["public_path"] == "/var/www/shop.example.com/public"
    assert d["server_path"] == "/var/www/shop.example.com"
    assert d["system_user"] == "www-data"
    assert d["size_kb"] == 20480
    assert d["php_version"] == "8.3"


def test_a_fact_the_server_could_not_answer_is_absent_rather_than_wrong():
    """A static site has no PHP and an unreadable folder has no size. Reporting a default —
    "PHP 8.1", "0 MB" — would be a made-up number someone acts on."""
    d = sites.parse_detail("___SM_SITEDETAIL___|public|/var/www/x\n"
                           "___SM_SITEDETAIL___|sizekb|\n")
    assert d["public_path"] == "/var/www/x"
    assert d["php_version"] is None
    assert d["size_kb"] is None
    assert d["system_user"] is None


def test_junk_output_never_raises():
    """An unreachable-mid-command server returns half a line. The page must still draw."""
    assert sites.parse_detail("")["public_path"] is None
    assert sites.parse_detail("bash: nginx: not found")["public_path"] is None
    assert sites.parse_detail("___SM_SITEDETAIL___|sizekb|not-a-number")["size_kb"] is None
    assert sites.parse_detail("___SM_SITEDETAIL___|truncated")["public_path"] is None


# ── Apache prints its vhosts three different ways ────────────────────────────
#
# Captured from a real Ubuntu 24.04 box. `namevhost` only appears once a port carries
# SEVERAL name-based vhosts, so matching that word alone reported ZERO sites on a server
# with exactly one — the first site on a fresh server, which is the case that matters most.
# Live testing found it; no offline test had a single-vhost sample to notice it.

_APACHE_ONE = """VirtualHost configuration:
*:80                   pass1.example.com (/etc/apache2/sites-enabled/pass1.example.com.conf:2)
ServerRoot: "/etc/apache2"
Main DocumentRoot: "/var/www/html"
Mutex default: dir="/var/run/apache2/" mechanism=default
User: name="www-data" id=33
"""

_APACHE_MANY = """VirtualHost configuration:
*:80                   is a NameVirtualHost
         default server a.example.com (/etc/apache2/sites-enabled/a.conf:1)
         port 80 namevhost a.example.com (/etc/apache2/sites-enabled/a.conf:1)
         port 80 namevhost b.example.com (/etc/apache2/sites-enabled/b.conf:1)
ServerRoot: "/etc/apache2"
"""


def _apache_probe(sample: str) -> list[str]:
    """Run the probe's OWN awk program over a sample, the way the server runs it.

    Re-implementing the extraction in Python here would prove nothing about the shell that
    actually runs on the box — which is exactly how the single-vhost case slipped through.
    """
    import re
    import subprocess
    prog = re.search(r"\| awk '(\{ for.*?\})'", sites.build_discovery_command(), re.S).group(1)
    out = subprocess.run(["awk", prog], input=sample, text=True, capture_output=True).stdout
    found, _ = sites.parse_discovery(out)
    return sorted(s.domain for s in found)


def test_a_server_with_exactly_one_apache_site_reports_that_site():
    assert _apache_probe(_APACHE_ONE) == ["pass1.example.com"]


def test_a_server_with_several_apache_sites_reports_all_of_them_once():
    assert _apache_probe(_APACHE_MANY) == ["a.example.com", "b.example.com"]


def test_apaches_own_noise_is_not_mistaken_for_a_site():
    """`ServerRoot`, `Main DocumentRoot` and the NameVirtualHost header all sit in the same
    output. A site list full of things nobody can visit is worse than a short one."""
    for junk in ("NameVirtualHost", "ServerRoot", "DocumentRoot", "default", "*:80"):
        assert junk not in _apache_probe(_APACHE_ONE) + _apache_probe(_APACHE_MANY)
