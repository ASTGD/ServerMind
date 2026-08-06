"""Editing a Laravel site's `.env` — the file that holds every credential it has.

Two properties matter more than anything else here and both are tested by running things
rather than reading them:

* **no credential ever reaches a command line.** An argument is visible in `ps` while the
  command runs and it is kept in the stored output of the run, so the content travels over
  SFTP and the shell only handles the backup, the ownership, the rename and the checks;
* **a bad edit puts the old file back.** Including the case that is easy to get wrong — the
  edit is fine but Laravel cannot rebuild its config from it.
"""
import os
import shutil
import subprocess

import pytest

from app.services import env_service as env


def sh(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", command], capture_output=True, text=True)


gnu_only = pytest.mark.skipif(
    subprocess.run(["bash", "-c", "stat -c %U . >/dev/null 2>&1"]).returncode != 0,
    reason="needs GNU stat -c; the product only runs on Linux",
)

SAMPLE = """APP_NAME=RCMAA
APP_ENV=production
APP_KEY=base64:aVeryRealLookingKey==
APP_DEBUG=false
APP_URL=https://rcmalumni.astgd.com

# the database
DB_CONNECTION=mysql
DB_PASSWORD="s3cr3t p@ss"
MAIL_MAILER=log
"""


def fake_bin(tmp_path, *, code="200", body="the real site", cache_ok=True):
    """Stands in for the web server and for artisan, so the file work can be tested."""
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    (b / "curl").write_text(
        "#!/bin/bash\nout=''\n"
        'while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; *) shift;; esac; done\n'
        f'[ -n "$out" ] && printf %s {body!r} > "$out"\nprintf %s {code!r}\n')
    # `su` is what runs artisan; failing it is how a broken config cache is simulated.
    (b / "su").write_text("#!/bin/bash\nexit %d\n" % (0 if cache_ok else 1))
    for f in ("curl", "su"):
        os.chmod(b / f, 0o755)
    return str(b)


def apply(tmp_path, root, *, rebuild=True, **binargs):
    cmd = env.build_apply_command(str(root), "shop.example.com",
                                  php_bin="/usr/bin/php8.4", rebuild_cache=rebuild)
    return sh(f'export PATH="{fake_bin(tmp_path, **binargs)}:$PATH"; {cmd}')


def site(tmp_path, content=SAMPLE, new="APP_DEBUG=true\n"):
    root = tmp_path / "app"
    root.mkdir(parents=True, exist_ok=True)
    if content is not None:
        (root / ".env").write_text(content)
    (root / env.TMP_NAME).write_text(new)
    return root


# ── What never happens ───────────────────────────────────────────────────────

def test_no_credential_ever_reaches_a_command_line():
    """The whole reason the content goes over SFTP. A command's arguments are visible in
    `ps` and are kept in the stored output of the run."""
    cmd = env.build_apply_command("/var/www/app", "shop.example.com",
                                  php_bin="/usr/bin/php", rebuild_cache=True)
    for secret in ("s3cr3t", "base64:", "APP_KEY", "DB_PASSWORD"):
        assert secret not in cmd
    assert "base64" not in cmd, "content must not be smuggled through the shell at all"


def test_the_facts_probe_carries_no_content_either():
    cmd = env.build_facts_command("/var/www/app", "shop.example.com")
    assert "cat " not in cmd and "base64" not in cmd
    # it may only ever ask ABOUT the file
    assert "stat -c" in cmd


@pytest.mark.parametrize("bad", ["", "relative/path", "/var/www/../../etc"])
def test_a_path_we_cannot_trust_is_refused(bad):
    with pytest.raises(env.EnvError):
        env.env_path(bad)


def test_something_too_large_to_be_a_settings_file_is_refused():
    with pytest.raises(env.EnvError) as exc:
        env.check_content("x" * (env.MAX_BYTES + 1))
    assert "refused" in str(exc.value)


def test_a_binary_upload_is_refused():
    with pytest.raises(env.EnvError):
        env.check_content("APP_ENV=production\x00\x01")


# ── Reading it for a human ───────────────────────────────────────────────────

def test_secrets_are_marked_by_their_key_not_by_what_the_value_looks_like():
    """A password that happens to look like an ordinary word is still a password."""
    rows = {r["key"]: r for r in env.summarise(SAMPLE)}
    assert rows["DB_PASSWORD"]["secret"] is True
    assert rows["APP_KEY"]["secret"] is True
    assert rows["APP_ENV"]["secret"] is False
    assert rows["APP_URL"]["secret"] is False


def test_the_app_key_is_called_out_as_critical():
    """Losing it makes every encrypted value and signed link in the database unreadable,
    which the name alone does not tell anyone."""
    rows = {r["key"]: r for r in env.summarise(SAMPLE)}
    assert rows["APP_KEY"]["critical"] is True
    assert rows["DB_PASSWORD"]["critical"] is False


def test_comments_and_blank_lines_are_not_settings():
    keys = [r["key"] for r in env.summarise(SAMPLE)]
    assert "# the database" not in keys and "" not in keys
    assert keys == ["APP_NAME", "APP_ENV", "APP_KEY", "APP_DEBUG", "APP_URL",
                    "DB_CONNECTION", "DB_PASSWORD", "MAIL_MAILER"]


def test_a_quoted_value_with_spaces_is_read_whole():
    rows = {r["key"]: r for r in env.summarise(SAMPLE)}
    assert rows["DB_PASSWORD"]["value"] == "s3cr3t p@ss"


# ── The exposure check ───────────────────────────────────────────────────────

def test_a_file_reachable_from_the_web_is_the_first_thing_said():
    facts = env.parse_facts("exists=yes\nowner=www-data:www-data\nmode=600\n"
                            "bytes=200\nweb=200\ncached=no")
    assert facts["web_readable"] is True
    warning = env.exposure_warning(facts)
    assert "downloadable from the internet right now" in warning
    assert "already leaked" in warning


@pytest.mark.parametrize("code", ["403", "404", "000"])
def test_a_refused_request_is_not_an_exposure(code):
    facts = env.parse_facts(f"exists=yes\nweb={code}\ncached=no")
    assert facts["web_readable"] is False
    assert env.exposure_warning(facts) is None


def test_a_cached_config_is_noticed():
    """Editing .env changes nothing while the config is cached — the most confusing
    failure this feature has."""
    assert env.parse_facts("cached=yes")["config_cached"] is True
    assert env.parse_facts("cached=no")["config_cached"] is False


# ── Saving it, run for real ──────────────────────────────────────────────────

@gnu_only
def test_the_new_settings_are_put_in_place_and_the_old_file_is_gone(tmp_path):
    root = site(tmp_path)
    r = apply(tmp_path, root)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (root / ".env").read_text() == "APP_DEBUG=true\n"
    assert not (root / env.TMP_NAME).exists()
    assert not list(root.glob("*.bak")), "the backup goes once the change is proven"


@gnu_only
def test_the_file_keeps_its_permissions(tmp_path):
    """A .env left world-readable is one any other account on the box can read; one left
    owned by root is one the application cannot read at all."""
    root = site(tmp_path)
    os.chmod(root / ".env", 0o600)
    assert apply(tmp_path, root).returncode == 0
    assert oct(os.stat(root / ".env").st_mode)[-3:] == "600"


@gnu_only
def test_a_site_that_stops_serving_gets_the_old_settings_back(tmp_path):
    root = site(tmp_path)
    r = apply(tmp_path, root, code="500", body="Whoops")
    assert r.returncode == 5
    ok, message = env.explain(r.returncode, r.stdout)
    assert ok is False and "put back" in message
    assert (root / ".env").read_text() == SAMPLE
    assert not list(root.glob("*.bak"))


@gnu_only
def test_a_blank_page_counts_as_not_serving(tmp_path):
    """The standing rule: content, not a status code."""
    root = site(tmp_path)
    assert apply(tmp_path, root, code="200", body="").returncode == 5
    assert (root / ".env").read_text() == SAMPLE


@gnu_only
def test_settings_laravel_cannot_read_are_reverted_before_the_site_is_even_checked(tmp_path):
    """A missing quote makes `config:cache` fail. That is the edit being wrong, and it is
    caught without waiting for visitors to see a broken site."""
    root = site(tmp_path)
    r = apply(tmp_path, root, cache_ok=False)
    assert r.returncode == 5
    assert "reverted=cache" in r.stdout
    ok, message = env.explain(r.returncode, r.stdout)
    assert ok is False and "missing quote" in message
    assert (root / ".env").read_text() == SAMPLE


@gnu_only
def test_a_site_with_no_cached_config_is_not_given_one(tmp_path):
    """Building a cache on a site that does not use one changes how it behaves, which is
    not what pressing Save means."""
    cmd = env.build_apply_command("/var/www/app", "shop.example.com",
                                  php_bin="/usr/bin/php", rebuild_cache=False)
    assert "config:cache" not in cmd


@gnu_only
def test_a_first_ever_settings_file_can_be_written(tmp_path):
    root = site(tmp_path, content=None)
    assert apply(tmp_path, root).returncode == 0
    assert (root / ".env").read_text() == "APP_DEBUG=true\n"


@gnu_only
def test_nothing_happens_when_the_upload_never_arrived(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    (root / ".env").write_text(SAMPLE)
    r = apply(tmp_path, root)
    assert r.returncode == 3
    assert (root / ".env").read_text() == SAMPLE


def test_only_our_own_temporary_file_can_be_discarded():
    cmd = env.build_discard_command("/var/www/app")
    assert env.TMP_NAME in cmd
    assert sh(env.build_discard_command("/var/www/app")).returncode == 0
