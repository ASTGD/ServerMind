"""Keeping a site out of search engines.

The reason this is a header and not a robots.txt file is the whole feature, and the reason
success is judged by reading the header back is the rest of it.
"""
import os
import re
import subprocess

import pytest

from app.services import robots_service as r


def test_it_is_a_header_not_a_robots_txt_file():
    """robots.txt asks a crawler not to FETCH a page; it does not stop it being INDEXED —
    Google lists URLs it was told not to fetch, using links from elsewhere. And a file lives
    inside the site, so a deploy or a clone overwrites it and nobody notices."""
    cmd = r.build_command("/etc/nginx/conf.d/x", "x.com", block=True, apache=False)
    assert "X-Robots-Tag" in cmd and "noindex" in cmd
    assert "robots.txt" not in cmd


def test_nginx_gets_always_or_an_error_page_stays_indexable():
    """Without `always`, nginx only adds the header on 2xx and 3xx — so an error page,
    exactly the sort of half-built page a staging site serves, would be indexable."""
    assert 'always;' in r.render_block(apache=False)


def test_apache_gets_apache_syntax():
    block = r.render_block(apache=True)
    assert "Header always set X-Robots-Tag" in block
    assert "add_header" not in block


def test_success_is_judged_by_reading_the_header_back():
    """The write succeeding is not the same as a crawler seeing it. Reporting "done" without
    checking is how a staging site quietly gets indexed anyway."""
    cmd = r.build_command("/etc/nginx/conf.d/x", "x.com", block=True, apache=False)
    assert "curl -sI" in cmd and "x-robots-tag" in cmd


def test_a_saved_setting_whose_header_never_appears_is_not_a_success():
    ok, message = r.explain(0, "applied\nheader=", block=True)
    assert ok is False
    assert "would still index this site" in message


def test_a_confirmed_header_is_reported_honestly_as_a_request():
    ok, message = r.explain(0, "header=X-Robots-Tag: noindex, nofollow, noarchive\napplied",
                            block=True)
    assert ok is True
    assert "confirmed on a real request" in message
    # and it does not promise privacy it cannot give
    assert "not a lock" in message and "password" in message


def test_unblocking_says_the_opposite():
    ok, message = r.explain(0, "applied", block=False)
    assert ok is True and "allowed to index" in message


def sh(cmd, path):
    b = os.path.join(path, "bin")
    os.makedirs(b, exist_ok=True)
    for name, body in (("nginx", "exit 0"), ("systemctl", "exit 0"), ("apachectl", "exit 0")):
        open(os.path.join(b, name), "w").write(f"#!/bin/bash\n{body}\n")
    open(os.path.join(b, "curl"), "w").write(
        "#!/bin/bash\nout=''\n"
        'for a in "$@"; do case "$prev" in -o) out="$a";; esac; prev="$a"; done\n'
        'case " $* " in *" -sI "*) printf "X-Robots-Tag: noindex, nofollow, noarchive\\r\\n";;'
        ' *) [ -n "$out" ] && printf page > "$out"; printf 200;; esac\n')
    for f in ("nginx", "systemctl", "apachectl", "curl"):
        os.chmod(os.path.join(b, f), 0o755)
    return subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; {cmd}'],
                          capture_output=True, text=True)


def test_the_header_really_lands_in_the_config_and_comes_out_again(tmp_path):
    cfg = tmp_path / "site.conf"
    original = "server {\n    server_name x.com;\n    root /var/www/x;\n}\n"
    cfg.write_text(original)

    res = sh(r.build_command(str(cfg), "x.com", block=True, apache=False), str(tmp_path))
    assert res.returncode == 0, res.stdout + res.stderr
    assert "X-Robots-Tag" in cfg.read_text()
    ok, _ = r.explain(res.returncode, res.stdout, block=True)
    assert ok is True

    res = sh(r.build_command(str(cfg), "x.com", block=False, apache=False), str(tmp_path))
    assert res.returncode == 0
    assert cfg.read_text() == original, "removing it leaves the file exactly as it was"
    assert not list(tmp_path.glob("*.bak")) and not list(tmp_path.glob("*.tmp"))


def test_a_site_that_was_already_down_is_not_told_this_broke_it(tmp_path):
    """Same lesson the WordPress switches learned."""
    cfg = tmp_path / "site.conf"
    cfg.write_text("server {\n    server_name x.com;\n}\n")
    b = tmp_path / "bin"
    b.mkdir()
    for name in ("nginx", "systemctl"):
        (b / name).write_text("#!/bin/bash\nexit 0\n")
    (b / "curl").write_text("#!/bin/bash\nprintf 502\n")
    for f in ("nginx", "systemctl", "curl"):
        os.chmod(b / f, 0o755)
    res = subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; '
                          + r.build_command(str(cfg), "x.com", block=True, apache=False)],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "X-Robots-Tag" in cfg.read_text()


def test_a_refused_config_is_put_back(tmp_path):
    cfg = tmp_path / "site.conf"
    original = "server {\n    server_name x.com;\n}\n"
    cfg.write_text(original)
    b = tmp_path / "bin"
    b.mkdir()
    (b / "nginx").write_text("#!/bin/bash\nexit 1\n")
    (b / "apachectl").write_text("#!/bin/bash\nexit 1\n")
    (b / "systemctl").write_text("#!/bin/bash\nexit 0\n")
    (b / "curl").write_text("#!/bin/bash\nprintf 200\n")
    for f in ("nginx", "apachectl", "systemctl", "curl"):
        os.chmod(b / f, 0o755)
    res = subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; '
                          + r.build_command(str(cfg), "x.com", block=True, apache=False)],
                         capture_output=True, text=True)
    assert res.returncode == 4
    assert cfg.read_text() == original


def test_a_header_that_says_the_opposite_is_not_a_success():
    """Something else in the site's configuration can set a permissive value — a plugin, a
    CDN rule, another `add_header`. The header being PRESENT proves nothing; what it SAYS is
    the only thing that matters."""
    assert r.parse_result("header=X-Robots-Tag: all") is False
    assert r.parse_result("header=X-Robots-Tag: index, follow") is False
    assert r.parse_result("header=X-Robots-Tag: noindex, nofollow") is True

    ok, message = r.explain(0, "header=X-Robots-Tag: all\napplied", block=True)
    assert ok is False
    assert "would still index this site" in message
