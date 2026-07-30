"""Setting up a server — the properties that stop a helpful button from breaking a live box.

"Set up this server" does not look destructive, which is exactly why it is. On a machine
that already runs a control panel or serves websites, installing our own web server and
database takes real sites offline. Most of the tests here are about refusing.
"""
from __future__ import annotations

import pytest

from app.services import setup_service as s


class Srv:
    def __init__(self, **kw):
        self.connection_type = kw.get("connection_type", "ssh")
        self.panel_type = kw.get("panel_type")
        self.os_type = kw.get("os_type", "ubuntu")
        self.port = kw.get("port", 22)
        self.name = kw.get("name", "web-1")


# ── refusing to break something that works ───────────────────────────────────
def test_a_server_with_a_control_panel_is_refused():
    """The worst case. CyberPanel runs its own web server, PHP and database; installing
    ours alongside breaks both and the customer loses live websites."""
    with pytest.raises(s.SetupRefused) as e:
        s.check_server(Srv(panel_type="cyberpanel"))
    assert "cyberpanel" in str(e.value).lower()
    assert "offline" in str(e.value), "say what they would lose"


def test_a_server_already_serving_websites_is_refused():
    with pytest.raises(s.SetupRefused) as e:
        s.check_server(Srv(), installed={"sites": ["shop.com", "blog.com"]})
    assert "2 websites" in str(e.value)
    assert "Nothing has been changed" in str(e.value) or "could take them offline" in str(e.value)


def test_a_panel_found_by_scanning_is_refused_too():
    """The stored `panel_type` can be stale; what the scan finds now also counts."""
    with pytest.raises(s.SetupRefused):
        s.check_server(Srv(), installed={"panels": ["cPanel"]})


def test_the_customer_can_insist():
    """A refusal that cannot be overridden becomes a support ticket. The override is
    explicit and it is theirs to make."""
    assert s.check_server(Srv(), installed={"sites": ["a.com"]}, force=True) == ""


def test_a_control_panel_can_also_be_overridden_but_only_deliberately():
    assert s.check_server(Srv(panel_type="cyberpanel"), force=True) == ""


def test_a_blank_server_is_allowed():
    assert s.check_server(Srv(), installed={"sites": [], "panels": []}) == ""


def test_a_server_we_cannot_run_commands_on_is_refused():
    with pytest.raises(s.SetupRefused):
        s.check_server(Srv(connection_type="winrm"))
    with pytest.raises(s.SetupRefused):
        s.check_server(Srv(connection_type="rdp"))


def test_an_operating_system_the_installers_do_not_cover_is_refused_helpfully():
    with pytest.raises(s.SetupRefused) as e:
        s.check_server(Srv(os_type="freebsd"))
    assert "ask Ally" in str(e.value), "offer the way that does work"


@pytest.mark.parametrize("os_type", ["ubuntu", "debian", "almalinux", "rocky", "centos"])
def test_the_operating_systems_we_do_cover_are_allowed(os_type):
    assert s.check_server(Srv(os_type=os_type)) == ""


def test_an_unknown_operating_system_does_not_block_the_main_path():
    """A server we have not detected yet is common; refusing on absence of information
    would break the ordinary case."""
    assert s.check_server(Srv(os_type="")) == ""


# ── the firewall step, which is where a helpful button locks you out ─────────
def test_the_firewall_is_told_the_port_ssh_is_really_on():
    """The installer defaults to 22. On a server whose SSH is on 2222, enabling a firewall
    that only allows 22 ends every future connection — the same lockout the firewall
    screen refuses, arriving through a different door."""
    recipe = s.build_recipe("websites", ssh_port=2222)
    fw = next(x for x in recipe.steps if x.slug == "ufw-setup")
    assert fw.variables["SSH_PORT"] == "2222"
    hard = next(x for x in recipe.steps if x.slug == "initial-hardening")
    assert hard.variables["SSH_PORT"] == "2222"


def test_the_machine_is_secured_before_a_long_install_runs():
    """A fresh public server is being probed within minutes. The firewall must not be
    waiting behind a three-minute stack install."""
    slugs = [x.slug for x in s.build_recipe("websites").steps]
    assert slugs.index("ufw-setup") < slugs.index("lemp-stack")
    assert slugs.index("initial-hardening") < slugs.index("lemp-stack")
    assert slugs.index("fail2ban") < slugs.index("lemp-stack")


# ── what each recipe contains ────────────────────────────────────────────────
def test_every_server_gets_the_safety_basics_whatever_it_is_for():
    for purpose in s.PURPOSES:
        slugs = {x.slug for x in s.build_recipe(purpose).steps}
        assert {"full-update", "initial-hardening", "ufw-setup", "fail2ban"} <= slugs, purpose


def test_a_website_server_gets_a_web_server_and_a_database():
    slugs = [x.slug for x in s.build_recipe("websites").steps]
    assert "lemp-stack" in slugs


def test_just_secure_it_installs_no_web_server():
    """Someone who is not ready for a website should not be given one."""
    slugs = [x.slug for x in s.build_recipe("basic").steps]
    assert "lemp-stack" not in slugs and "docker" not in slugs


def test_monitoring_can_be_left_out():
    assert "netdata" not in [x.slug for x in s.build_recipe("basic", monitoring=False).steps]


def test_optional_steps_are_the_ones_a_server_works_without():
    """Failing to install a dashboard must not abandon a half-built server; failing to
    install the web server must."""
    recipe = s.build_recipe("websites")
    by_slug = {x.slug: x for x in recipe.steps}
    assert by_slug["netdata"].optional is True
    assert by_slug["letsencrypt"].optional is True
    assert by_slug["lemp-stack"].optional is False
    assert by_slug["ufw-setup"].optional is False


def test_an_unknown_purpose_is_refused_rather_than_guessed():
    with pytest.raises(s.SetupRefused):
        s.build_recipe("mine-bitcoin")


# ── what the customer is told ────────────────────────────────────────────────
def test_the_steps_are_named_in_words_a_non_expert_reads():
    """The whole difference from a terminal. "Configuring firewall" is legible to anyone;
    an apt log is not."""
    for step in s.build_recipe("websites").steps:
        assert step.label[0].isupper(), step.label
        assert not any(tok in step.label.lower()
                       for tok in ("ufw", "apt", "sudo", "systemctl", "lemp", "netdata")), \
            f"{step.label} leaks jargon"


def test_the_choices_are_about_purpose_not_about_software():
    """A shop owner cannot answer "which stack"; they can answer "what is it for"."""
    for key, (title, _desc) in s.PURPOSES.items():
        assert not any(t in title.lower() for t in ("lemp", "lamp", "nginx", "stack")), title


def test_the_summary_says_how_long_it_will_take():
    summary = s.summarise(s.build_recipe("websites"))
    assert summary["minutes"] >= 1
    assert len(summary["steps"]) == len(s.build_recipe("websites").steps)


def test_progress_answers_the_only_question_a_waiting_person_has():
    assert s.progress(4, 12) == {"done": 4, "total": 12, "percent": 33}
    assert s.progress(0, 12)["percent"] == 0
    assert s.progress(12, 12)["percent"] == 100


def test_progress_never_divides_by_zero_or_exceeds_a_hundred():
    assert s.progress(0, 0)["percent"] == 0
    assert s.progress(99, 5)["percent"] == 100


# ── the gap a competitor's provision exposed ─────────────────────────────────
"""Ploi's 26-task provision was watched end to end on a real machine and then read back
over SSH. These lock what that comparison changed, and why."""

import shutil
import subprocess
import tempfile

from app.services.playbook_service import OFFICIAL_PLAYBOOKS, substitute_variables

_ADDED = ("composer", "supervisor", "redis-cache", "php-limits", "auto-updates")


def _script(slug: str) -> str:
    pb = next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == slug)
    return substitute_variables(
        pb["script_bash"], {v["name"]: v.get("default", "x")
                            for v in pb.get("variables", [])})


@pytest.mark.parametrize("slug", _ADDED)
def test_every_added_installer_is_registered(slug):
    assert any(p["slug"] == slug for p in OFFICIAL_PLAYBOOKS)


@pytest.mark.parametrize("slug", _ADDED)
def test_every_added_installer_parses_as_a_shell_would(slug):
    """A script that does not parse fails at the first line, on a customer's server,
    halfway through a build."""
    if not shutil.which("bash"):
        pytest.skip("no bash")
    script = _script(slug)
    assert "{{" not in script, "a placeholder was left unsubstituted"
    with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
        f.write(script)
        f.flush()
        r = subprocess.run(["bash", "-n", f.name], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_a_website_server_gets_composer_and_node():
    """The sharp edge of the gap: our OWN deploy pipeline runs `composer install` and
    `npm ci` as its build step. Without these, deploying to a server our OWN wizard had
    just finished would fail on a command that does not exist."""
    slugs = [s.slug for s in s.build_recipe("websites").steps]
    assert "composer" in slugs
    assert "nodejs-pm2" in slugs
    assert slugs.index("lemp-stack") < slugs.index("composer"), \
        "Composer is a PHP program — PHP has to exist first"


def test_a_website_server_can_accept_a_normal_upload():
    """PHP's 2 MB default is the single reason a media upload fails on a fresh server."""
    step = next(s for s in s.build_recipe("websites").steps if s.slug == "php-limits")
    assert step.variables["UPLOAD_MAX"] == "64M"


def test_every_server_keeps_getting_security_patches():
    """A machine set up once and never updated again is the ordinary route to a
    compromised server, and it is silent the whole way."""
    for purpose in s.PURPOSES:
        assert "auto-updates" in [s.slug for s in s.build_recipe(purpose).steps]


def test_the_extras_never_halt_a_whole_server_build():
    """None of them makes the machine incoherent by its absence. Stopping a build over a
    cache daemon would be the wrong trade — a skipped step still shows its reason."""
    for step in s.build_recipe("websites").steps:
        if step.slug in ("redis-cache", "supervisor", "php-limits", "composer",
                         "auto-updates", "nodejs-pm2"):
            assert step.optional, f"{step.slug} would stop the entire setup"


def test_composer_is_verified_before_it_is_run_as_root():
    """The installer is downloaded and then executed with full privileges. Piping it in
    unchecked would hand the server to anyone who could tamper with that download."""
    s = _script("composer")
    assert "composer.github.io/installer.sig" in s
    assert "hash_file('sha384'" in s or 'hash_file(\\\'sha384\\\'' in s or "sha384" in s
    fail = s.split("did not match its published")[1]
    assert "exit 1" in fail, "a mismatch must stop, not continue"


def test_redis_and_memcached_are_never_exposed_to_the_internet():
    """An open Redis with no password is one of the most reliably exploited holes there
    is — a large share of crypto-miner infections arrive that way."""
    s = _script("redis-cache")
    assert "bind 127.0.0.1" in s
    assert "protected-mode yes" in s
    assert "-l 127.0.0.1" in s, "memcached listens on all interfaces on some images"


def test_automatic_updates_clear_the_list_before_setting_it():
    """APT list directives APPEND rather than replace, and stock Ubuntu ships the WHOLE
    archive enabled, not only security. Found by reading `apt-config dump` on a real
    box: without #clear, every feature update kept applying itself unattended while we
    told the customer "security only" — a server that wakes up with a new major PHP and
    a dead website."""
    s = _script("auto-updates")
    assert '#clear "Unattended-Upgrade::Allowed-Origins"' in s
    body = s.split("#clear")[1].split("EOF")[0]
    assert "${distro_id}:${distro_codename}\";" not in body, \
        "that is the whole archive, not security"


def test_a_server_never_reboots_itself():
    """A reboot nobody expected, in the middle of the working day, is worse than a patch
    that waits a few hours."""
    assert 'Unattended-Upgrade::Automatic-Reboot "false"' in _script("auto-updates")


def test_php_limits_never_hardcodes_a_version_path():
    """A guessed path edits a file nothing loads: the limit looks changed while uploads
    keep failing, which is worse than not trying."""
    s = _script("php-limits")
    assert "Loaded Configuration File" in s, "ask PHP which ini it actually reads"
    assert "/etc/php/8." not in s, "a hardcoded version breaks on every other server"


def test_upload_and_post_limits_move_together():
    """post_max_size below upload_max_filesize rejects the upload before PHP ever looks
    at the file-size limit — so raising only one of them changes nothing."""
    s = _script("php-limits")
    assert 'set_ini post_max_size "$UPLOAD_MAX"' in s


def test_raising_php_uploads_raises_the_web_server_limit_too():
    """nginx rejects a body over ITS OWN limit — 1 MB by default — before the request
    ever reaches PHP. Raising php.ini alone leaves the visitor with a 413 while the
    setting reads 64M: the limit looks changed and uploads keep failing. Found by
    reading a competitor's finished machine, which sets both together."""
    s = _script("php-limits")
    assert "client_max_body_size" in s


def test_a_broken_web_server_config_is_never_reloaded():
    """Reloading nginx with a configuration that does not parse takes down every OTHER
    site on the server. An upload limit is not worth that."""
    s = _script("php-limits")
    assert "nginx -t" in s, "test the configuration before reloading it"
    after = s.split("nginx -t")[1]
    assert "rm -f /etc/nginx/conf.d/serverally-upload.conf" in after, \
        "our own file must be removed when the test fails, not left to be loaded later"


# ── the create-site primitive ────────────────────────────────────────────────
"""Ploi's "Add site" makes a folder, a web-server config and a placeholder page — nothing
more; WordPress is a separate installer run into that site. We only had the WordPress-shaped
path, so "give me a website for my own files" had no code route at all.

Writing a web-server config is the one thing here that can take down sites which have
nothing to do with the one being added, so the guards are the substance.
"""


def test_create_site_is_registered_and_parses():
    if not shutil.which("bash"):
        pytest.skip("no bash")
    script = _script("create-site")
    assert "{{" not in script
    with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
        f.write(script)
        f.flush()
        r = subprocess.run(["bash", "-n", f.name], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_a_domain_is_validated_not_escaped():
    """The domain lands inside a config file AND a filesystem path. Escaping it correctly in
    both places is harder than refusing anything that is not a hostname, so it is refused —
    proven live: `evil;rm -rf /` is rejected before a single file is written."""
    s = _script("create-site")
    assert '*[!a-zA-Z0-9.-]*' in s, "anything outside hostname characters must be refused"
    assert "is not a valid domain name" in s


def test_a_panel_server_is_refused():
    """A control panel owns its web-server config. A vhost written behind its back is
    invisible to the panel, never gets its certificate renewed, and may be overwritten on
    the panel's next change."""
    s = _script("create-site")
    for panel_dir in ("/usr/local/CyberCP", "/usr/local/cpanel", "/opt/psa"):
        assert panel_dir in s
    assert "Add this through the panel" in s


def test_an_existing_domain_is_never_taken_over():
    """Otherwise creating a site would silently repoint a live one."""
    s = _script("create-site")
    assert "already configured on this server" in s
    before_write = s.split("mkdir -p")[0]
    assert "already configured on this server" in before_write, \
        "the check must come before anything is created"


def test_the_config_is_tested_before_the_reload_and_removed_if_bad():
    """Reloading a configuration that does not parse takes EVERY site on the server offline,
    not just the new one. Proven live: with nginx already broken by someone else, the run
    refused, removed both its config and its symlink, never reloaded, and the other site
    kept answering 200."""
    s = _script("create-site")
    test_at = s.index("$TEST_CMD >/tmp/sm_conftest.log")
    reload_at = s.index('systemctl reload "$RELOAD_SVC"')
    assert test_at < reload_at, "the config must be tested before the server is reloaded"
    failure = s[test_at:reload_at]
    assert 'rm -f "$SITE_CONF"' in failure, "a rejected config must not be left behind"
    assert "exit 1" in failure


def test_the_php_socket_is_never_hardcoded():
    """A wrong socket makes the server hand out PHP SOURCE as plain text, which leaks
    database credentials to anyone who visits."""
    s = _script("create-site")
    assert "php_fpm_socket" in s
    assert "/run/php/php8" not in s, "a hardcoded version breaks on every other server"


def test_the_verification_retries_instead_of_racing_the_reload():
    """Found by running it: `systemctl reload` returns BEFORE nginx finishes swapping
    workers, so an immediate request is still answered by the OLD config. A single shot
    reported "could not verify" on a site that was serving perfectly, and a false warning
    like that teaches people to ignore the real ones."""
    s = _script("create-site")
    assert "for _try in" in s
    assert "grep -qF" in s, "a domain is full of dots, which grep treats as wildcards"


def test_it_reloads_rather_than_restarts():
    """A restart drops live connections that the server's OTHER sites are serving."""
    s = _script("create-site")
    assert 'systemctl reload "$RELOAD_SVC"' in s


def test_no_database_is_created():
    """Matching the primitive: Ploi's Add site creates none, and a database nobody asked for
    is a credential to look after for no reason."""
    s = _script("create-site").lower()
    for verb in ("create database", "mysql -e", "createdb"):
        assert verb not in s


# ── hosting a web application ────────────────────────────────────────────────
"""A website is files the web server reads; an application is a program that keeps running
and answers on a port. It needs a reverse proxy and something to keep it alive — Deployments
already covers the build step."""


def test_create_app_is_registered_and_parses():
    if not shutil.which("bash"):
        pytest.skip("no bash")
    s = _script("create-app")
    assert "{{" not in s
    with tempfile.NamedTemporaryFile("w", suffix=".sh") as f:
        f.write(s)
        f.flush()
        r = subprocess.run(["bash", "-n", f.name], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_both_site_installers_share_one_set_of_guards():
    """Writing a web-server config is the one thing here that can take down sites unrelated
    to the one being added. Copying those checks means the third copy is the one that forgets
    to test the config before reloading, so there is exactly one definition."""
    from app.services.playbook_service import _SITE_GUARDS
    assert "shared site guards" in _SITE_GUARDS
    for slug in ("create-site", "create-app"):
        assert "shared site guards" in _script(slug), f"{slug} does not use the shared guards"
    # And the guards still carry the properties that matter.
    for needed in ("is not a valid domain name", "runs a control panel",
                   "already configured on this server", "apply_web_config"):
        assert needed in _SITE_GUARDS


def test_the_app_port_can_never_be_the_web_server_s_own():
    """The web server is about to proxy TO the app. Pointing it at itself is an infinite
    loop that takes the whole web server down, not just this site."""
    s = _script("create-app")
    assert '"$APP_PORT" = 80' in s and '"$APP_PORT" = 443' in s
    assert "the web server's own port" in s


def test_the_app_port_is_validated_not_escaped():
    s = _script("create-app")
    assert '*[!0-9]*' in s, "anything that is not digits must be refused"
    assert "-gt 65535" in s


def test_a_missing_run_as_user_is_refused_before_anything_is_written():
    """systemd would accept the unit and then fail to start it with a confusing error."""
    s = _script("create-app")
    check = s.index('id -u "$RUN_AS"')
    assert check < s.index("mkdir -p \"$APP_ROOT\""), "check the user before creating anything"


def test_the_start_limit_is_in_the_unit_section_where_systemd_reads_it():
    """Found by running it: under [Service] systemd logs "Unknown key name … ignoring", so
    the crash-loop protection LOOKS present and does nothing. A test kill showed 12 restarts
    with no limit ever applied; after the fix systemd gave up after 5, as intended."""
    lines = _script("create-app").split("\n")
    section, by_section = None, {}
    for line in lines:
        bare = line.strip()
        if bare in ("[Unit]", "[Service]", "[Install]"):
            section = bare
        elif section and not bare.startswith("#"):
            by_section.setdefault(section, []).append(bare)
    unit = "\n".join(by_section.get("[Unit]", []))
    service = "\n".join(by_section.get("[Service]", []))
    assert "StartLimitBurst=" in unit, "systemd only reads it here"
    assert "StartLimitIntervalSec=" in unit
    assert "StartLimitBurst=" not in service, "under [Service] it is silently ignored"


def test_the_app_is_the_service_s_main_process_not_a_shell_wrapper():
    """Without `exec`, bash stays as the main process and the app is only its child: systemd
    then watches the wrapper rather than the program, and stopping the service orphans the
    app, which keeps holding the port so the restart fails with "address already in use".
    Verified live — after the fix the main process is the app itself."""
    s = _script("create-app")
    assert "exec $START_CMD" in s


def test_websockets_are_not_silently_broken():
    """Without the upgrade headers a realtime app connects, gets upgraded, and is cut off —
    which looks like an application bug rather than a proxy setting."""
    s = _script("create-app")
    assert "proxy_set_header Upgrade" in s
    assert 'proxy_set_header Connection "upgrade"' in s


def test_the_visitor_s_address_reaches_the_app():
    """Otherwise every request appears to come from the proxy, which breaks rate limiting,
    audit logs and anything geographic."""
    s = _script("create-app")
    for h in ("X-Real-IP", "X-Forwarded-For", "X-Forwarded-Proto"):
        assert h in s


def test_a_502_is_explained_rather_than_left_as_a_number():
    """It is the single most likely outcome on first run, and it means one specific thing:
    the domain works, the app is not listening yet."""
    s = _script("create-app")
    assert "502" in s and "nothing is listening on port" in s


def test_no_database_is_created_for_an_app_either():
    s = _script("create-app").lower()
    for verb in ("create database", "mysql -e", "createdb"):
        assert verb not in s
