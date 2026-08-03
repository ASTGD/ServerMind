"""Taking a site offline on purpose — Ploi's "Suspend site".

Their reason for it is blunt and correct: a lever an agency can pull when a client has not
paid, that is not "delete their website".

**The response code is the design.** Ploi offers 200 as a choice; we default to 503, because
the code is what search engines are told. 200 means "this IS the page now", so a client's
real pages get replaced in the index by a suspension notice — damage that outlives the
billing dispute by months. 503 means "come back later" and holds their rankings.
"""
import re
import shutil
import subprocess

import pytest

from app.services import suspend_service as ss


docker = pytest.mark.skipif(
    shutil.which("docker") is None
    or subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
    reason="needs docker: whether a suspension really covers every path is nginx's answer")

SITE = """\
server {
    listen 80 default_server;
    server_name shop.example.com;
    root /var/www/shop/public;
    index index.html;
    location / { try_files $uri $uri/ =404; }
    location ~ \\.php$ {
        include fastcgi_params;
        fastcgi_pass unix:/run/php/php8.3-fpm.sock;
    }
}
"""

PROBE = r"""set -e
apt-get update -qq >/dev/null 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx curl >/dev/null 2>&1
mkdir -p /var/www/shop/public/sub /stub
echo REAL-HOME > /var/www/shop/public/index.html
echo REAL-SUB > /var/www/shop/public/sub/index.html
echo '<?php echo 1;' > /var/www/shop/public/thing.php
cp /tmp/site.conf /etc/nginx/sites-available/shop.conf
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/shop.conf /etc/nginx/sites-enabled/shop.conf
printf '#!/bin/sh\nexit 0\n' > /stub/systemctl; chmod +x /stub/systemctl
export PATH=/stub:$PATH
nginx
hit () { curl -s -o /dev/null -w "%{http_code}" -m 5 -H "Host: shop.example.com" "http://127.0.0.1$1"; }
body () { curl -s -m 5 -H "Host: shop.example.com" "http://127.0.0.1$1"; }
bash /tmp/apply.sh >/dev/null 2>&1; echo "EXIT=$?"
nginx -s reload 2>/dev/null; sleep 1
echo "ROOT=$(hit /)"
echo "SUB=$(hit /sub/)"
echo "PHP=$(hit /thing.php)"
echo "SHOWS_REAL=$(body / | grep -c REAL-HOME || true)"
echo "TITLE=$(body / | grep -o '<title>[^<]*' | sed 's/<title>//' | head -1)"
echo "BOLD=$(body / | grep -c '<strong>' || true)"
echo "SCRIPT=$(body / | grep -c '<script>' || true)"
echo "NOINDEX=$(body / | grep -c 'noindex' || true)"
echo "LEFTOVERS=$(ls /etc/nginx/sites-available/ | grep -c serverally || true)"
echo "ROOTS=$(grep -c "root " /etc/nginx/sites-available/shop.conf || true)"
"""


def run(tmp_path, **kw) -> dict[str, str]:
    (tmp_path / "site.conf").write_text(SITE)
    (tmp_path / "probe.sh").write_text(PROBE)
    (tmp_path / "apply.sh").write_text(ss.build_apply_command(
        "/etc/nginx/sites-available/shop.conf", "shop.example.com", apache=False, **kw))
    proc = subprocess.run(
        ["docker", "run", "--rm",
         "-v", f"{tmp_path / 'probe.sh'}:/tmp/p.sh",
         "-v", f"{tmp_path / 'site.conf'}:/tmp/site.conf",
         "-v", f"{tmp_path / 'apply.sh'}:/tmp/apply.sh",
         "ubuntu:24.04", "bash", "/tmp/p.sh"],
        capture_output=True, text=True, timeout=900)
    out = dict(ln.split("=", 1) for ln in proc.stdout.splitlines() if "=" in ln)
    assert out.get("EXIT") == "0", proc.stdout + proc.stderr
    return out


@docker
def test_a_suspension_covers_every_path_including_php(tmp_path):
    """A suspension that misses one path is not a suspension. PHP is the one that gets
    missed, because it is matched by its own regex location."""
    r = run(tmp_path, suspended=True, message="Away", reason="", code=503)
    assert r["ROOT"] == "503" and r["SUB"] == "503" and r["PHP"] == "503"


@docker
def test_the_real_site_is_not_shown(tmp_path):
    r = run(tmp_path, suspended=True, message="Away", reason="", code=503)
    assert r["SHOWS_REAL"] == "0", "the suspended site was still serving its own pages"


@docker
def test_the_notice_is_the_customers_own_words(tmp_path):
    r = run(tmp_path, suspended=True, message="We are away",
            reason="**Payment overdue**", code=503)
    assert r["TITLE"] == "We are away"
    assert r["BOLD"] == "1", "the Markdown was not rendered"


@docker
def test_html_in_the_reason_cannot_execute(tmp_path):
    """This text is written by one customer and shown to ANOTHER customer's visitors, on a
    page an agency puts its own name on. Everything is escaped first and four Markdown
    constructs are added back by hand, rather than trusting a parser."""
    r = run(tmp_path, suspended=True, message="Away",
            reason="<script>alert(1)</script>", code=503)
    assert r["SCRIPT"] == "0", "a script tag reached the page"


@docker
def test_the_notice_asks_not_to_be_indexed(tmp_path):
    r = run(tmp_path, suspended=True, message="Away", reason="", code=503)
    assert r["NOINDEX"] == "1"


@docker
def test_restoring_brings_the_real_site_back(tmp_path):
    r = run(tmp_path, suspended=False)
    assert r["ROOT"] == "200"
    assert r["SHOWS_REAL"] == "1"
    assert r["LEFTOVERS"] == "0"


@docker
@pytest.mark.parametrize("code", [403, 404, 410, 451, 200])
def test_every_offered_code_is_one_nginx_really_sends(tmp_path, code):
    """An option that produces a different status than it promises is worse than no option."""
    r = run(tmp_path, suspended=True, message="Away", reason="", code=code)
    assert r["ROOT"] == str(code)


# ── Without a server ─────────────────────────────────────────────────────────

def test_503_is_the_default():
    """Because it is the only one that holds a client's search rankings through a dispute
    that will be settled in a week."""
    assert ss.DEFAULT_CODE == 503


def test_every_code_says_what_it_costs():
    for c in ss.CODES:
        assert c["note"], f"{c['value']} is offered with no explanation"
    note = next(c["note"] for c in ss.CODES if c["value"] == 200)
    assert "not recommended" in note.lower()


def test_choosing_a_code_that_is_not_offered_is_refused():
    with pytest.raises(ss.SuspendError):
        ss.check_code(418)


def test_a_link_in_the_reason_can_only_be_http():
    """A `javascript:` link on somebody else's visitors is not ours to allow."""
    out = ss.render_markdown("[click](javascript:alert(1)) and [ok](https://example.com)")
    assert "javascript:" not in out or "<a" not in out.split("javascript:")[0][-30:]
    assert '<a href="https://example.com"' in out


def test_the_page_needs_nothing_from_the_network():
    """A suspended site should not depend on fonts, scripts, or anything else that could
    itself be down."""
    page = ss.render_page("shop.example.com", "Away", "why")
    assert "<script" not in page
    assert "http://" not in page and "https://" not in page


def test_the_success_message_warns_when_the_code_is_a_poor_one():
    ok, message = ss.explain(0, "", suspended=True, status=200)
    assert ok and "503 is" in message
    ok, message = ss.explain(0, "", suspended=True, status=503)
    assert ok and "503 is" not in message


# ── The one-way door, found by pressing the button ───────────────────────────

def test_the_block_never_adds_a_second_root():
    """Found live and it was serious. A `root` inside the suspend block gave the file TWO
    root directives — and the resolver that finds a site's configuration reads exactly
    that, so it started answering "/var/www/serverally-suspended", matched no site, and
    reported that it could not work out which config serves this site.

    The consequence is the bad part: a suspended site could no longer be FOUND, so it could
    not be un-suspended. A one-way door, on the feature whose whole promise is "putting it
    back is one click".
    """
    for code in (503, 200):
        cmd = ss.build_apply_command("/etc/nginx/x.conf", "shop.example.com",
                                     suspended=True, message="m", reason="", code=code,
                                     apache=False)
        import base64
        blocks = re.findall(r"printf %s '?([A-Za-z0-9+/=]{40,})'?", cmd)
        rendered = "".join(base64.b64decode(b).decode(errors="replace") for b in blocks)
        assert "root " not in rendered, f"code {code} still claims a folder with `root`"
        assert "alias " in rendered


@docker
def test_a_suspended_site_can_still_be_found_and_restored(tmp_path):
    """The regression that matters, exercised rather than asserted: suspend, then confirm
    the configuration still declares exactly one document root — which is what the resolver
    needs in order to give the customer the button back."""
    r = run(tmp_path, suspended=True, message="Away", reason="", code=503)
    assert r["ROOT"] == "503"
    assert r["ROOTS"] == "1", "the suspended config no longer names one document root"
