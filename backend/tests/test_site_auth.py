"""A username and password in front of a site.

The interesting part is not the password file — it is nginx's location precedence. A plain
`location /wp-admin` does NOT protect `/wp-admin/index.php`: the regex `location ~ \.php$`
wins for anything ending in `.php`, so anyone who guessed a PHP path would walk straight
past the password while the screen said the path was protected.

That cannot be verified by reading the generated config. It is a fact about what nginx does
with two locations, so the test runs REAL nginx and asks for the URL.
"""
import re
import shutil
import subprocess

import pytest

from app.services import site_auth_service as sa


docker = pytest.mark.skipif(
    shutil.which("docker") is None
    or subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
    reason="needs docker: location precedence is a fact about nginx, not about our text")

SITE = """\
server {
    listen 80 default_server;
    server_name shop.example.com;
    root /var/www/shop/public;
    index index.html index.php;
    location / { try_files $uri $uri/ /index.php?$query_string; }
    location ~ \\.php$ {
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_pass unix:/run/php/php8.3-fpm.sock;
    }
}
"""

PROBE = r"""set -e
apt-get update -qq >/dev/null 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx curl >/dev/null 2>&1
mkdir -p /var/www/shop/public/wp-admin /stub
echo PUBLIC > /var/www/shop/public/index.html
echo SECRET > /var/www/shop/public/wp-admin/index.html
echo '<?php echo 1;' > /var/www/shop/public/wp-admin/index.php
cp /tmp/site.conf /etc/nginx/sites-available/shop.conf
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/shop.conf /etc/nginx/sites-enabled/shop.conf
printf '#!/bin/sh\nexit 0\n' > /stub/systemctl; chmod +x /stub/systemctl
export PATH=/stub:$PATH
nginx
bash /tmp/apply.sh >/dev/null 2>&1; echo "EXIT=$?"
nginx -s reload 2>/dev/null; sleep 1
hit () { curl -s -o /dev/null -w "%{http_code}" -m 5 ${2:+-u "$2"} -H "Host: shop.example.com" "http://127.0.0.1$1"; }
echo "ROOT=$(hit /)"
echo "ADMIN=$(hit /wp-admin/)"
echo "ADMINPHP=$(hit /wp-admin/index.php)"
echo "GOODPW=$(hit /wp-admin/ demo:hunter2demo)"
echo "GOODPW_ROOT=$(hit / demo:hunter2demo)"
echo "BADPW=$(hit /wp-admin/ demo:wrongwrong)"
echo "PWFILE=$([ -f /etc/nginx/serverally-auth/shop.example.com ] && echo yes || echo no)"
echo "LEFTOVERS=$(ls /etc/nginx/sites-available/ | grep -c serverally || true)"
"""


def run(tmp_path, users: list[str], path: str) -> dict[str, str]:
    (tmp_path / "site.conf").write_text(SITE)
    (tmp_path / "probe.sh").write_text(PROBE)
    (tmp_path / "apply.sh").write_text(sa.build_apply_command(
        "/etc/nginx/sites-available/shop.conf", "shop.example.com", users, path,
        apache=False))
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
def test_a_php_path_cannot_walk_past_the_password(tmp_path):
    """THE test. Without `^~` the regex PHP location wins and /wp-admin/index.php is served
    with no password at all — while the screen says the path is protected."""
    line = sa.htpasswd_line("demo", "hunter2demo")
    r = run(tmp_path, [line], "/wp-admin")
    assert r["ADMIN"] == "401"
    assert r["ADMINPHP"] == "401", "a PHP path inside the protected folder was NOT protected"


@docker
def test_protecting_a_path_leaves_the_rest_of_the_site_open(tmp_path):
    line = sa.htpasswd_line("demo", "hunter2demo")
    r = run(tmp_path, [line], "/wp-admin")
    assert r["ROOT"] == "200", "protecting one path closed the whole site"


@docker
def test_the_right_password_gets_in_and_a_wrong_one_does_not(tmp_path):
    """Both halves. A password that never works and a password that always works are the
    same bug wearing different clothes."""
    line = sa.htpasswd_line("demo", "hunter2demo")
    r = run(tmp_path, [line], "/wp-admin")
    assert r["GOODPW"] == "200", "the correct password was refused"
    assert r["BADPW"] == "401", "a wrong password was let in"


@docker
def test_protecting_the_whole_site(tmp_path):
    line = sa.htpasswd_line("demo", "hunter2demo")
    r = run(tmp_path, [line], "")
    assert r["ROOT"] == "401"
    assert r["GOODPW_ROOT"] == "200"


@docker
def test_removing_every_user_opens_the_site_and_deletes_the_file(tmp_path):
    """An empty password file would refuse every login while the screen showed the site as
    open — worse than either state on its own."""
    r = run(tmp_path, [], "")
    assert r["ROOT"] == "200"
    assert r["PWFILE"] == "no"
    assert r["LEFTOVERS"] == "0"


# ── Things that never reach a server ─────────────────────────────────────────

def test_the_password_is_hashed_here_and_never_sent(tmp_path):
    """It must not appear in a command: that is shell history, `ps`, and the stored output
    of the run. The same reason database passwords go in through a file."""
    line = sa.htpasswd_line("demo", "hunter2demo")
    cmd = sa.build_apply_command("/etc/nginx/x.conf", "shop.example.com", [line], "",
                                 apache=False)
    assert "hunter2demo" not in cmd
    assert line.split(":", 1)[1] not in cmd, "even the hash is only there base64-encoded"


def test_the_hash_is_one_nginx_understands_everywhere():
    """apr1 rather than bcrypt: nginx only takes bcrypt when the C library under it happens
    to support it, so it would work on one distribution and reject every login on another —
    indistinguishable from the customer typing the wrong password."""
    assert sa.hash_password("hunter2demo").startswith("$apr1$")


def test_hashes_are_never_returned_to_the_screen():
    users = sa.parse_users("demo:$apr1$abc$def\nother:$apr1$xyz$123\n")
    assert users == ["demo", "other"]


def test_a_user_added_by_hand_on_the_server_is_kept():
    """This file is one an administrator may well have touched. Rewriting it from a list we
    hold would silently drop theirs."""
    existing = "byhand:$apr1$aaa$bbb\ndemo:$apr1$ccc$ddd\n"
    out = sa.replace_user(existing, "demo", "demo:$apr1$new$hash")
    assert any(l.startswith("byhand:") for l in out)
    assert sum(1 for l in out if l.startswith("demo:")) == 1


@pytest.mark.parametrize("bad", ["", "  ", "has space", "a" * 33, "semi;colon", "quote'"])
def test_a_username_that_is_not_a_username_is_refused(bad):
    with pytest.raises(sa.AuthError):
        sa.clean_name(bad)


@pytest.mark.parametrize("bad", ["", "short", "1234567"])
def test_a_password_too_weak_to_bother_with_is_refused(bad):
    with pytest.raises(sa.AuthError):
        sa.check_password(bad)


@pytest.mark.parametrize("bad", ["/../etc", "/a b", "/x\ny", "/a;rm -rf /"])
def test_a_path_that_is_not_a_path_is_refused(bad):
    with pytest.raises(sa.AuthError):
        sa.clean_path(bad)


def test_a_path_is_normalised_not_guessed():
    assert sa.clean_path("wp-admin") == "/wp-admin"
    assert sa.clean_path("/wp-admin/") == "/wp-admin"
    assert sa.clean_path("") == ""


def test_the_generated_block_uses_the_precedence_stopper():
    """Pinned in the text as well as in behaviour: someone reading this later needs to see
    that `^~` is load-bearing and not decoration."""
    cmd = sa.build_apply_command("/etc/nginx/x.conf", "shop.example.com",
                                 ["demo:$apr1$a$b"], "/wp-admin", apache=False)
    assert "^~" in cmd
    assert re.search(r"location ~ .{0,4}\\\\?\.php", cmd), "no PHP handler inside the block"
