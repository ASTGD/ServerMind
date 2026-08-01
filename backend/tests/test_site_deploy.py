"""Getting a repository onto a website.

The deploy machinery already existed per-server. What is new is tying it to a SITE, and
that brings one genuinely dangerous step: a deploy builds into ``releases/<stamp>`` and
moves a ``current`` symlink, and none of it reaches a visitor until the web server is
pointed through ``current``. Repointing a live website is the one action here that can
serve nothing to everybody.

So the order is the safety property, and these pin it:

    connect  →  deploy (site still serving its old files)  →  point the site at it

Nothing visitors see changes until there is a finished release AND the owner asks.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

import pytest

from app.services import deploy_service as ds


# ── Where a site's deploys belong ────────────────────────────────────────────

def test_a_site_served_from_public_deploys_beside_it_not_inside_it():
    """Releases must not land inside the folder the web server is reading."""
    assert ds.deploy_root_for("/var/www/shop.com/public") == "/var/www/shop.com"
    assert ds.deploy_root_for("/var/www/shop.com/public/") == "/var/www/shop.com"


def test_a_site_served_from_its_own_folder_deploys_there():
    assert ds.deploy_root_for("/var/www/shop.com") == "/var/www/shop.com"


def test_a_site_with_no_folder_yet_is_refused_rather_than_guessed_at():
    with pytest.raises(ds.InvalidDeploy):
        ds.deploy_root_for("")


def test_the_served_path_goes_through_current():
    """Everything rests on this: `current` is what makes a deploy atomic."""
    assert ds.served_path("/var/www/shop.com", "public") == "/var/www/shop.com/current/public"
    assert ds.served_path("/var/www/shop.com", "") == "/var/www/shop.com/current"
    assert ds.served_path("/var/www/shop.com", None) == "/var/www/shop.com/current"


@pytest.mark.parametrize("bad", [
    "../etc", "a b", "pub;lic", "pub\nlic", 'pub"lic', "x" * 200, "a/../b",
])
def test_a_web_directory_that_is_not_a_folder_name_is_refused_not_escaped(bad):
    """This ends up inside a web-server config, where a stray quote or newline does not
    fail loudly — it changes what the config MEANS."""
    with pytest.raises(ds.InvalidDeploy):
        ds.valid_web_dir(bad)


@pytest.mark.parametrize("good", ["public", "web", "dist", "public_html", "src/public", ""])
def test_real_web_directories_are_accepted(good):
    ds.valid_web_dir(good)


def test_a_leading_slash_is_normalised_rather_than_refused():
    """Somebody typing "/public" means the folder inside their repository, not the system
    root. Stripping it is what they meant; refusing would be pedantry."""
    assert ds.valid_web_dir("/public") == "public"
    assert ds.valid_web_dir("public/") == "public"


# ── Repointing a live site ───────────────────────────────────────────────────

def test_it_refuses_to_repoint_when_there_is_nothing_to_point_at():
    """The reason a failed first deploy costs nothing: the site keeps serving its existing
    files until a finished release exists."""
    cmd = ds.build_point_command("/etc/nginx/x.conf", "shop.com", "/var/www/shop.com", "public")
    assert 'if [ ! -d "$TGT" ]' in cmd
    assert "exit 3" in cmd
    assert 3 in ds.POINT_OUTCOMES


def test_it_keeps_a_copy_and_puts_it_back_when_the_site_stops_working():
    cmd = ds.build_point_command("/etc/nginx/x.conf", "shop.com", "/var/www/shop.com", "")
    assert 'cp -p "$CFG" "$BK"' in cmd, "a copy is kept before anything changes"
    assert cmd.count('cp -p "$BK" "$CFG"') >= 2, "restored on a bad config AND a dead site"
    assert "nginx -t" in cmd and "apachectl configtest" in cmd


def test_a_status_code_alone_is_not_accepted_as_proof():
    """A root pointing at the wrong folder answers 200 with a directory listing or an error
    page just as happily as it answers with a website. Same rule the mission verification
    gate follows."""
    cmd = ds.build_point_command("/etc/nginx/x.conf", "shop.com", "/var/www/shop.com", "")
    assert '[ -n "$B" ] && OK=yes' in cmd, "the body has to be non-empty too"


def test_the_command_is_valid_shell():
    for web in ("public", ""):
        cmd = ds.build_point_command("/etc/nginx/x.conf", "shop.com", "/var/www/s", web)
        r = subprocess.run(["bash", "-n"], input=cmd, text=True, capture_output=True)
        assert r.returncode == 0, r.stderr


#: The rewrite runs on a Linux server with GNU sed. macOS ships BSD sed, whose ``-i`` and
#: backreference handling differ, so running it here would prove something about the wrong
#: platform — and pass or fail for reasons that have nothing to do with the code. These run
#: it in a Linux container instead, and skip when there is not one.
_LINUX = subprocess.run(["docker", "image", "inspect", "ubuntu:22.04"],
                        capture_output=True).returncode == 0


def _rewrite(config_text: str, target: str) -> str:
    """Run the probe's OWN rewrite against a real config file, on real Linux.

    Re-implementing the sed in Python would prove nothing about what happens on the server,
    which is where every bug in this feature would live.
    """
    d = tempfile.mkdtemp()
    path = os.path.join(d, "vhost.conf")
    with open(path, "w") as fh:
        fh.write(config_text)

    cmd = ds.build_point_command("/cfg/vhost.conf", "shop.example.com",
                                 "/var/www/shop.example.com", "public")
    # Everything from reading the old root up to the config test: the file surgery, without
    # needing a web server present.
    fragment = cmd[cmd.index('OLD="$(sed'):cmd.index("if ! (nginx -t")]
    subprocess.run(
        ["docker", "run", "--rm", "-v", f"{d}:/cfg", "ubuntu:22.04", "bash", "-c",
         f'CFG=/cfg/vhost.conf; TGT={target}; ' + fragment],
        capture_output=True, text=True, timeout=120)
    with open(path) as fh:
        return fh.read()


@pytest.mark.skipif(not _LINUX, reason='needs Linux sed')
def test_an_nginx_root_is_moved_and_a_comment_mentioning_root_is_not():
    out = _rewrite(
        "server {\n"
        "    server_name shop.example.com;\n"
        "    root /var/www/shop.example.com/public;\n"
        "    # note: root /old/comment/path; must stay put\n"
        "    access_log /var/log/nginx/shop-access.log;\n"
        "}\n",
        "/var/www/shop.example.com/current/public")
    assert "root /var/www/shop.example.com/current/public;" in out
    assert "# note: root /old/comment/path;" in out, "a comment is not configuration"
    assert "/var/log/nginx/shop-access.log" in out, "unrelated paths are left alone"


@pytest.mark.skipif(not _LINUX, reason='needs Linux sed')
def test_apaches_directory_block_moves_with_its_document_root():
    """Found by reading a real diff. Apache grants access per FOLDER, so its vhost names the
    path twice — moving only DocumentRoot leaves the <Directory> block granting access to a
    folder nobody is served from, and every visitor gets 403."""
    out = _rewrite(
        "<VirtualHost *:80>\n"
        "    ServerName shop.example.com\n"
        "    DocumentRoot /var/www/shop.example.com/public\n"
        "    <Directory /var/www/shop.example.com/public>\n"
        "        Require all granted\n"
        "    </Directory>\n"
        "    ErrorLog /var/log/apache2/shop-error.log\n"
        "</VirtualHost>\n",
        "/var/www/shop.example.com/current/public")
    assert "DocumentRoot /var/www/shop.example.com/current/public" in out
    assert "<Directory /var/www/shop.example.com/current/public>" in out, \
        "the Directory block must move too, or Apache answers 403"
    assert "/var/log/apache2/shop-error.log" in out


@pytest.mark.skipif(not _LINUX, reason='needs Linux sed')
def test_an_openlitespeed_docroot_is_moved():
    out = _rewrite(
        "docRoot                   $VH_ROOT/public_html\n"
        "vhDomain                  shop.example.com\n",
        "/var/www/shop.example.com/current/public")
    assert "/var/www/shop.example.com/current/public" in out
    assert "vhDomain                  shop.example.com" in out


def test_every_way_this_can_fail_has_words_somebody_can_act_on():
    for code, text in ds.POINT_OUTCOMES.items():
        assert len(text) > 40, f"exit {code} has no real explanation"
        assert "error" not in text.lower() or "public" in text.lower()
