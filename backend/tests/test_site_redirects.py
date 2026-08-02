"""Redirects for one website.

Two free-text fields end up inside a live web-server configuration, so the tests here are
about one question: can what somebody types become a directive we did not intend? They
answer it by RUNNING the generated command against real config files and reading the files
back, rather than by checking the command contains the right-looking words — a redirect that
is written but never reaches the file passes a text assertion perfectly.
"""
import base64
import re
import subprocess
import textwrap

import pytest

from app.services import redirect_service as rs


NGINX_CONF = """\
# Created by ServerAlly for shop.example.com
server {
    listen 80;
    server_name shop.example.com;
    root /var/www/shop.example.com/public;
    index index.php index.html;

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }
}
server {
    listen 443 ssl;
    server_name shop.example.com;
    root /var/www/shop.example.com/public;
}
"""

APACHE_CONF = """\
# Created by ServerAlly for shop.example.com
<VirtualHost *:80>
    ServerName shop.example.com
    DocumentRoot /var/www/shop.example.com/public
</VirtualHost>
"""


def _run(tmp_path, rules, *, apache=False, conf=None):
    """Run the REAL generated command against a REAL file, with the web server stubbed.

    nginx/apachectl/systemctl/curl are replaced by stubs on PATH so the script's control
    flow runs exactly as it would on a server — the file edit is the real thing.
    """
    cfg = tmp_path / ("site.conf")
    cfg.write_text(conf if conf is not None else (APACHE_CONF if apache else NGINX_CONF))

    binstub = tmp_path / "bin"
    binstub.mkdir(exist_ok=True)
    for name, body in (
        ("nginx", "exit 0"),
        ("apachectl", "exit 1"),
        ("systemctl", "exit 0"),
        # A redirect answers 3xx; the script accepts 2xx/3xx as "the site still answers".
        ("curl", 'for a in "$@"; do case "$a" in -o) shift;; esac; done; echo 301'),
    ):
        p = binstub / name
        p.write_text(f"#!/bin/sh\n{body}\n")
        p.chmod(0o755)

    cmd = rs.build_apply_command(str(cfg), "shop.example.com", rules, apache=apache)
    proc = subprocess.run(
        ["bash", "-c", f'export PATH="{binstub}:$PATH"; {cmd}'],
        capture_output=True, text=True)
    return proc, cfg.read_text()


# ── The block really lands in the file ───────────────────────────────────────

def test_a_redirect_is_written_into_every_server_block(tmp_path):
    """An http and an https block for one site is ordinary. A redirect that only worked on
    one of them looks broken in exactly the confusing way."""
    proc, text = _run(tmp_path, [
        {"from": "/old-page", "to": "https://example.com/new-page", "type": "permanent"},
    ])
    assert proc.returncode == 0, proc.stderr
    assert text.count('rewrite "/old-page" "https://example.com/new-page" permanent;') == 2
    assert text.count(rs.BEGIN) == 2


def test_the_apache_form_is_written_for_an_apache_site(tmp_path):
    proc, text = _run(tmp_path, [
        {"from": "/old", "to": "https://example.com/new", "type": "redirect"},
    ], apache=True)
    assert proc.returncode == 0, proc.stderr
    assert "RewriteEngine On" in text
    assert 'RewriteRule "/old" "https://example.com/new" [R=302,L]' in text


def test_applying_twice_does_not_stack_up(tmp_path):
    """Adding, changing and removing are all the same operation — write the whole set — so
    the old block has to go first or the file grows a copy on every edit."""
    rules = [{"from": "/a", "to": "https://example.com/a", "type": "redirect"}]
    proc, _ = _run(tmp_path, rules)
    assert proc.returncode == 0
    cfg = tmp_path / "site.conf"
    cmd = rs.build_apply_command(str(cfg), "shop.example.com", rules, apache=False)
    subprocess.run(["bash", "-c", f'export PATH="{tmp_path}/bin:$PATH"; {cmd}'],
                   capture_output=True, text=True)
    assert cfg.read_text().count(rs.BEGIN) == 2, "one block per server block, not four"


def test_removing_the_last_one_leaves_the_file_as_it_was(tmp_path):
    """The proof that the block is genuinely ours and bounded: with nothing left, the file
    is byte-for-byte what it was before the first redirect existed."""
    original = NGINX_CONF
    proc, _ = _run(tmp_path, [{"from": "/a", "to": "/b", "type": "redirect"}])
    assert proc.returncode == 0
    cfg = tmp_path / "site.conf"
    cmd = rs.build_apply_command(str(cfg), "shop.example.com", [], apache=False)
    subprocess.run(["bash", "-c", f'export PATH="{tmp_path}/bin:$PATH"; {cmd}'],
                   capture_output=True, text=True)
    assert cfg.read_text() == original


def test_a_hand_written_line_outside_the_block_is_never_touched(tmp_path):
    conf = NGINX_CONF.replace("    index index.php index.html;",
                              "    index index.php index.html;\n    client_max_body_size 64m;")
    proc, text = _run(tmp_path, [{"from": "/a", "to": "/b", "type": "redirect"}], conf=conf)
    assert proc.returncode == 0
    assert "client_max_body_size 64m;" in text


# ── What somebody types cannot become a directive ────────────────────────────

@pytest.mark.parametrize("payload", [
    '/old" ; root /etc; rewrite "/x',          # close our quote, add directives
    '/old\nroot /etc;',                        # a new line is a new directive
    '/old\r\nroot /etc;',
])
def test_a_pattern_that_could_break_out_is_refused(payload):
    with pytest.raises(rs.RedirectError):
        rs.valid_from(payload)


@pytest.mark.parametrize("payload", [
    'https://example.com/" ; root /etc; #',
    'https://example.com/\nroot /etc;',
    'https://example.com/\\',                  # escapes our closing quote
])
def test_a_destination_that_could_break_out_is_refused(payload):
    with pytest.raises(rs.RedirectError):
        rs.valid_to(payload)


def test_a_line_break_is_refused_by_name_not_as_a_stray_character():
    """A newline is caught twice over — by its own check and by the control-character
    check behind it — so the safety of the field does not depend on this line. What DOES
    depend on it is the message: "cannot contain a line break" tells someone who pasted a
    two-line value what to fix, and "contains a character that is not allowed" does not.
    """
    with pytest.raises(rs.RedirectError, match="line break"):
        rs.valid_from("/old\nroot /etc;")
    with pytest.raises(rs.RedirectError, match="line break"):
        rs.valid_to("https://example.com/\nroot /etc;")


def test_a_semicolon_survives_as_a_character_because_it_is_quoted(tmp_path):
    """The point of quoting rather than banning: `;` `{` `}` `$` all appear in real
    patterns. They are safe because they are inside quotes, and the file proves it."""
    src = "/old;page{2}"
    assert rs.valid_from(src) == src
    proc, text = _run(tmp_path, [
        {"from": src, "to": "https://example.com/$1", "type": "redirect"}])
    assert proc.returncode == 0, proc.stderr
    assert f'rewrite "{src}" "https://example.com/$1" redirect;' in text

    # The part that matters is not how it is spelled but that the `;` stayed INSIDE the
    # value: unquoted, nginx would read it as the end of the directive and everything after
    # it as a new one. One rule in, one directive out.
    block = text.split(rs.BEGIN)[1].split(rs.END)[0]
    assert len([l for l in block.splitlines() if l.strip()]) == 1


def test_a_whole_domain_move_is_accepted_unchanged():
    """The values our screen prints as the way to move a whole domain, and the unanchored
    form Ploi prints — both have to be accepted, because someone will paste either.

    Ours shows the anchored one. Against real nginx the unanchored pattern ALSO matches
    /.well-known/…, because a rewrite pattern is not anchored and the engine simply tries
    later positions until the lookahead passes — so it redirects away the exact path
    Let's Encrypt uses to prove the domain, and renewal starts failing weeks later with
    nothing on screen connecting it to a redirect. Verified by requesting both.
    """
    assert rs.valid_from(r"^/(?!\.well-known/)(.*)") == r"^/(?!\.well-known/)(.*)"
    assert rs.valid_from(r"/(?!\.well-known/)(.*)") == r"/(?!\.well-known/)(.*)"
    assert rs.valid_to("https://example.com/$1") == "https://example.com/$1"


def test_the_values_never_reach_a_shell_unencoded():
    """Base64 is the layer that makes shell quoting a non-question. If the raw pattern ever
    appears in the command text, some future edit has dropped it."""
    weird = "/old$(touch /tmp/pwned)`id`"
    cmd = rs.build_apply_command("/etc/nginx/sites-available/x", "x.example.com",
                                 [{"from": weird, "to": "/new", "type": "redirect"}],
                                 apache=False)
    assert weird not in cmd
    # shlex.quote leaves base64 unquoted, because every character in it is already safe —
    # which is the point being made here, so the quotes are optional in the match.
    encoded = re.search(r"printf %s '?([A-Za-z0-9+/=]+)'?", cmd)
    assert encoded, "the block should be delivered base64-encoded"
    assert weird in base64.b64decode(encoded.group(1)).decode()


# ── Refusing the input that is simply wrong ──────────────────────────────────

@pytest.mark.parametrize("bad", ["", "   ", "old-page", "https://example.com/x"])
def test_a_from_that_is_not_a_path_on_this_site_is_refused(bad):
    with pytest.raises(rs.RedirectError):
        rs.valid_from(bad)


@pytest.mark.parametrize("bad", ["", "example.com/new", "ftp://example.com"])
def test_a_destination_that_is_not_an_address_is_refused(bad):
    with pytest.raises(rs.RedirectError):
        rs.valid_to(bad)


def test_only_ploi_two_types_exist():
    assert set(rs.TYPES) == {"redirect", "permanent"}
    assert rs.valid_type("Permanent") == "permanent"
    with pytest.raises(rs.RedirectError):
        rs.valid_type("308")


# ── The config is tested before the reload, and put back if it fails ─────────

def test_a_config_the_web_server_refuses_is_restored(tmp_path):
    """The reason this cannot be a plain file write: a configuration that does not parse
    takes down EVERY site on the machine when it reloads, not just this one."""
    cfg = tmp_path / "site.conf"
    cfg.write_text(NGINX_CONF)
    binstub = tmp_path / "bin"
    binstub.mkdir()
    for name, body in (("nginx", "exit 1"), ("apachectl", "exit 1"),
                       ("systemctl", "exit 0"), ("curl", "echo 200")):
        p = binstub / name
        p.write_text(f"#!/bin/sh\n{body}\n")
        p.chmod(0o755)

    cmd = rs.build_apply_command(str(cfg), "shop.example.com",
                                 [{"from": "/a", "to": "/b", "type": "redirect"}],
                                 apache=False)
    proc = subprocess.run(["bash", "-c", f'export PATH="{binstub}:$PATH"; {cmd}'],
                          capture_output=True, text=True)

    assert proc.returncode == 4
    assert cfg.read_text() == NGINX_CONF, "the refused config was left in place"
    assert not list(tmp_path.glob("*.bak")), "the backup was left behind"


def test_a_site_that_stops_answering_is_put_back(tmp_path):
    cfg = tmp_path / "site.conf"
    cfg.write_text(NGINX_CONF)
    binstub = tmp_path / "bin"
    binstub.mkdir()
    for name, body in (("nginx", "exit 0"), ("apachectl", "exit 1"),
                       ("systemctl", "exit 0"), ("curl", "echo 000")):
        p = binstub / name
        p.write_text(f"#!/bin/sh\n{body}\n")
        p.chmod(0o755)

    cmd = rs.build_apply_command(str(cfg), "shop.example.com",
                                 [{"from": "/a", "to": "/b", "type": "redirect"}],
                                 apache=False)
    proc = subprocess.run(["bash", "-c", f'export PATH="{binstub}:$PATH"; {cmd}'],
                          capture_output=True, text=True)

    assert proc.returncode == 5
    assert cfg.read_text() == NGINX_CONF


def test_the_message_for_a_failure_is_ours_not_the_scripts_last_line():
    ok, message = rs.explain(4, "some shell noise\nThe web server refused it.")
    assert ok is False
    assert "undone" in message and "unaffected" in message


def test_success_says_so_plainly():
    ok, message = rs.explain(0, "applied")
    assert ok and message == "Saved."
