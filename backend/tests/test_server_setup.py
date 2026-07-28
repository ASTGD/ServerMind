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
