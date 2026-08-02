"""Which of the two ServerAlly is on a given server.

The one decision on this page that a customer cannot walk back: our own setup installs
nginx, PHP and a database, and a control panel wants a clean machine — so once either has
happened, the other door is shut until the server is rebuilt. Everything below is about
never showing that choice as open when it is not.
"""
import pytest

from app.services import server_role as sr


def role(**kw):
    base = {"connection_type": "ssh", "panel_type": None,
            "setup_done": False, "site_count": 0}
    return sr.decide(**{**base, **kw})


# ── A clean server is the only place the choice exists ───────────────────────

def test_a_fresh_linux_server_still_has_the_choice():
    out = role()
    assert out["role"] == "undecided" and out["can_choose"] is True


def test_a_panel_that_is_installed_decides_it():
    out = role(panel_type="cyberpanel")
    assert out["role"] == "panel"
    assert out["can_choose"] is False
    assert out["panel_label"] == "CyberPanel"


def test_our_own_setup_having_run_closes_the_panel_door():
    """The irreversible one. Setup put nginx, PHP and MariaDB on the machine; a control
    panel installing on top of that is the thing that ends in a rebuild."""
    out = role(setup_done=True)
    assert out["role"] == "serverally"
    assert out["can_choose"] is False
    assert "rebuilt" in out["why"]


def test_a_server_already_serving_sites_is_not_a_clean_machine():
    """Even sites we only FOUND. The box is in use, and a panel install would take over
    what is serving them."""
    out = role(site_count=3)
    assert out["role"] == "serverally"
    assert out["can_choose"] is False
    assert "clean machine" in out["why"]


def test_a_panel_wins_over_our_own_setup():
    """Both can be true — somebody sets a server up with us and later installs a panel by
    hand. What is ON the machine is the fact; what we believe about it is not."""
    out = role(panel_type="cpanel", setup_done=True, site_count=9)
    assert out["role"] == "panel" and out["panel_label"] == "cPanel"


# ── The question does not arise everywhere ───────────────────────────────────

@pytest.mark.parametrize("kind", ["winrm", "rdp", "hosting"])
def test_a_server_we_cannot_host_through_is_not_asked(kind):
    """Saying "not applicable" is honest. Picking one of two answers to a question that was
    never asked is how a Windows box ends up being offered a LAMP stack."""
    out = role(connection_type=kind)
    assert out["applies"] is False and out["role"] is None


def test_every_answer_is_one_of_the_three_roles():
    for kw in ({}, {"panel_type": "plesk"}, {"setup_done": True}, {"site_count": 1}):
        out = role(**kw)
        assert out["role"] in sr.ROLES


# ── Naming ───────────────────────────────────────────────────────────────────

def test_a_panel_we_have_no_name_for_is_not_shown_raw():
    """A customer should never read a database value. 'A control panel' is vague and true;
    'directadmin_v2' is precise and meaningless."""
    assert sr.panel_label("something_we_never_heard_of") == "A control panel"
    assert sr.panel_label(None) == "A control panel"
    assert sr.panel_label("DirectAdmin") == "DirectAdmin"


def test_the_reason_is_always_given_when_the_choice_is_closed():
    """A door that is shut without a reason reads as a bug. Each closed case has to say
    which of the two things happened, because they need different next steps."""
    for kw in ({"panel_type": "cyberpanel"}, {"setup_done": True}, {"site_count": 2}):
        out = role(**kw)
        assert out["can_choose"] is False
        assert out["why"] and len(out["why"]) > 20


def test_a_setup_that_is_running_does_not_ask_again():
    """The customer picked a door and the work started. Showing the two doors again would
    ask them to choose something they have already chosen, while it is happening — and the
    setup panel behind that door is where the progress is."""
    out = role(setup_running=True)
    assert out["role"] == "undecided", "nothing is installed yet, so it is not ours yet"
    assert out["can_choose"] is False
    assert "running" in out["why"]


def test_a_finished_setup_beats_a_running_one():
    """A re-run on a server we already set up must not reopen the question."""
    out = role(setup_done=True, setup_running=True)
    assert out["role"] == "serverally" and out["can_choose"] is False


# ── Is the machine actually empty? ───────────────────────────────────────────
#
# The page's whole first sentence turns on this. Somebody adds a server they have been
# running for a year and being told "this is a clean server" is the page being confidently
# wrong about the one thing it exists to decide.

def _found(**kw):
    base = {"os": "Ubuntu 22.04", "web_servers": [], "databases": [], "containers": [],
            "runtimes": [], "panels": []}
    return {**base, **kw}


def test_a_genuinely_empty_machine_is_fresh():
    assert sr.is_fresh(_found()) is True


def test_python_and_an_open_port_do_not_make_a_server_dirty():
    """Every Ubuntu that has ever booted has python3 and sshd. Counting them would mean no
    server is ever fresh, and the word would stop meaning anything."""
    assert sr.is_fresh(_found(runtimes=["python 3.10.12"], ports=["22"])) is True


@pytest.mark.parametrize("kw", [
    {"containers": ["some-worker (ghcr.io/x:tag)"]},   # the Docker box that started this
    {"web_servers": ["nginx 1.24"]},
    {"databases": ["mariadb 10.11"]},
    {"panels": ["cyberpanel"]},
])
def test_anything_either_path_would_fight_with_makes_it_not_fresh(kw):
    assert sr.is_fresh(_found(**kw)) is False


def test_not_looking_is_not_the_same_as_finding_nothing():
    """"We could not check" and "there is nothing here" lead somewhere different, so the
    page must be able to tell them apart."""
    assert sr.is_fresh(None) is None
