"""Copying a site to a new domain — Ploi's "Clone site".

The commands are tested by RUNNING them against real folders. A clone's failure modes are
all "the shell did something other than what the text implies" — a dotfile left behind, a
placeholder page outranking the copied site, a folder copied into itself — and none of them
show up in an assertion that the right words appear in the command.
"""
import os
import subprocess

import pytest

from app.services import clone_service as clone


def sh(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", command], capture_output=True, text=True)


class FakeServer:
    def __init__(self, id="s1", name="Server", connection_type="ssh", panel_type=None):
        self.id, self.name = id, name
        self.connection_type, self.panel_type = connection_type, panel_type


class FakeSite:
    def __init__(self, domain="shop.example.com", doc_root="/var/www/shop.example.com/public",
                 server_id="s1", app_type="wordpress"):
        self.domain, self.doc_root = domain, doc_root
        self.server_id, self.app_type = server_id, app_type


# ── What is refused before anything moves ────────────────────────────────────

def test_a_site_cannot_be_cloned_onto_itself():
    """Same server, same domain. The duplicate check downstream would call this "already
    exists", which reads as a bug rather than as what the customer actually asked for."""
    site, server = FakeSite(), FakeServer()
    with pytest.raises(clone.CloneError) as exc:
        clone.check_request(site, server, server, "shop.example.com")
    assert "same site" in str(exc.value)


def test_the_same_domain_on_another_server_is_allowed():
    """This is the migration case, and it is the main reason the field is prefilled."""
    site = FakeSite()
    assert clone.check_request(site, FakeServer(), FakeServer(id="s2"),
                               "shop.example.com") == "shop.example.com"


def test_a_control_panel_destination_is_refused():
    """A vhost written behind a panel's back is invisible to it and never gets a
    certificate renewed."""
    with pytest.raises(clone.CloneError) as exc:
        clone.check_request(FakeSite(), FakeServer(),
                            FakeServer(id="s2", panel_type="cyberpanel"), "copy.example.com")
    assert "cyberpanel" in str(exc.value)


@pytest.mark.parametrize("kind", ["winrm", "rdp", "hosting"])
def test_a_destination_we_have_no_shell_on_is_refused(kind):
    with pytest.raises(clone.CloneError):
        clone.check_request(FakeSite(), FakeServer(),
                            FakeServer(id="s2", connection_type=kind), "copy.example.com")


def test_a_site_whose_folder_we_do_not_know_is_refused():
    with pytest.raises(clone.CloneError) as exc:
        clone.check_request(FakeSite(doc_root=""), FakeServer(), FakeServer(id="s2"),
                            "copy.example.com")
    assert "nothing to copy" in str(exc.value)


@pytest.mark.parametrize("bad", ["not a domain", "", "shop", "//evil"])
def test_a_destination_that_is_not_a_domain_is_refused(bad):
    with pytest.raises(clone.CloneError):
        clone.check_request(FakeSite(), FakeServer(), FakeServer(id="s2"), bad)


def test_a_pasted_address_is_understood_as_the_domain_in_it():
    """Pasting the site's URL is what people actually do, and the existing domain rule
    already handles it — so the clone form inherits that rather than being fussier than
    every other place a domain is typed."""
    assert clone.check_request(FakeSite(), FakeServer(), FakeServer(id="s2"),
                               "HTTPS://Copy.Example.COM/") == "copy.example.com"


# ── PHP: the decision that can publish a database password ───────────────────

def test_a_site_containing_php_is_created_with_php_on():
    survey = clone.Survey(scope="docroot", source="/x", bytes=1, files=1, has_php=True)
    assert clone.site_type_for(survey) == "php"


def test_a_site_with_no_php_is_created_without_it():
    survey = clone.Survey(scope="docroot", source="/x", bytes=1, files=1, has_php=False)
    assert clone.site_type_for(survey) == "static"


def test_an_unreadable_php_answer_defaults_to_php_on():
    """The two ways of being wrong are not equal. PHP on for a static site costs nothing;
    PHP off for a WordPress site makes the web server hand out wp-config.php as text, and
    the database password with it."""
    survey = clone.parse_survey("SCOPE=docroot\nSRC=/var/www/x/public\nBYTES=10\nFILES=1\n")
    assert survey.has_php is True
    assert clone.site_type_for(survey) == "php"


# ── The survey, run for real ─────────────────────────────────────────────────

def test_a_framework_site_is_copied_from_above_the_folder_it_serves(tmp_path):
    """Laravel serves `public/` and keeps the application above it. Copying only the served
    folder produces a clone that is a 500 page."""
    app = tmp_path / "site"
    (app / "public").mkdir(parents=True)
    (app / "artisan").write_text("#!/usr/bin/env php\n")
    (app / "public" / "index.php").write_text("<?php\n")

    r = sh(clone.build_survey_command(str(app / "public")))
    assert r.returncode == 0, r.stderr
    survey = clone.parse_survey(r.stdout)
    assert survey.scope == "app"
    assert survey.source == str(app)
    assert survey.has_php is True
    assert survey.bytes > 0


def test_a_plain_site_is_copied_from_the_folder_it_serves(tmp_path):
    doc = tmp_path / "site" / "public"
    doc.mkdir(parents=True)
    (doc / "index.html").write_text("<h1>hi</h1>")

    survey = clone.parse_survey(sh(clone.build_survey_command(str(doc))).stdout)
    # `public` alone is not enough — the parent has to hold something saying an application
    # lives there. Widening on the name alone would copy a neighbour on a shared home.
    assert survey.scope == "docroot"
    assert survey.source == str(doc)
    assert survey.has_php is False


def test_a_missing_folder_is_reported_as_nothing_to_copy(tmp_path):
    r = sh(clone.build_survey_command(str(tmp_path / "gone")))
    with pytest.raises(clone.CloneError) as exc:
        clone.parse_survey(r.stdout, r.returncode)
    assert "not on the server" in str(exc.value)


def test_an_unmeasured_site_is_refused_rather_than_guessed():
    """The size is the only thing standing between a clone and a full disk on the
    destination, which stops every site on that machine."""
    with pytest.raises(clone.CloneError) as exc:
        clone.parse_survey("UNMEASURED", 4)
    assert "will not start copying" in str(exc.value)


# ── Room on the destination ──────────────────────────────────────────────────

def test_a_copy_with_nowhere_to_go_is_refused():
    with pytest.raises(clone.CloneError) as exc:
        clone.check_fit(1_000_000_000, 900_000_000)
    assert "not enough room" in str(exc.value)


def test_room_for_the_archive_as_well_as_the_copy_is_required():
    """The archive lands first and is unpacked beside itself, so a site needs more than its
    own size free — not exactly its own size."""
    size = 1_000_000_000
    clone.check_fit(size, int(size * clone.HEADROOM) + 1)
    with pytest.raises(clone.CloneError):
        clone.check_fit(size, size + 1)


def test_unknown_free_space_is_refused():
    with pytest.raises(clone.CloneError):
        clone.check_fit(1000, None)


def test_free_space_is_read_from_a_real_df():
    free = clone.parse_free(sh(clone.build_fit_command("/")).stdout)
    assert free is not None and free > 0


def test_free_space_is_asked_about_a_folder_that_does_not_exist_yet(tmp_path):
    """The new site's folder has not been made yet, so `df` has to be asked about the
    nearest parent that exists — asking about a missing path answers about nothing."""
    free = clone.parse_free(sh(clone.build_fit_command(str(tmp_path / "a" / "b" / "c"))).stdout)
    assert free is not None and free > 0


# ── The cross-server cap ─────────────────────────────────────────────────────

def test_a_big_site_can_still_be_cloned_on_the_same_server():
    """It never leaves the machine, so the transfer cap does not apply to it."""
    clone.check_transfer_size(50_000_000_000, same_server=True)


def test_a_big_site_is_refused_across_servers_with_the_alternative_named():
    from app.services.file_service import MAX_TRANSFER_BYTES

    with pytest.raises(clone.CloneError) as exc:
        clone.check_transfer_size(MAX_TRANSFER_BYTES + 1, same_server=False)
    assert "SAME server" in str(exc.value)


# ── Where the copy lands ─────────────────────────────────────────────────────

def test_an_app_scope_copy_lands_above_the_served_folder():
    assert clone.destination_target("app", "/var/www/copy.com/public") == "/var/www/copy.com"


def test_a_docroot_copy_lands_in_the_served_folder():
    assert clone.destination_target("docroot", "/var/www/copy.com/public") \
        == "/var/www/copy.com/public"


def test_a_layout_that_does_not_match_is_refused_rather_than_resolved():
    """Unpacking an application into the folder the web server serves publishes its source
    and its .env at a guessable address."""
    with pytest.raises(clone.CloneError) as exc:
        clone.destination_target("app", "/var/www/copy.com")
    assert "publish the application" in str(exc.value)


def test_the_document_root_is_read_off_a_real_config(tmp_path):
    conf = tmp_path / "nginx"
    conf.mkdir()
    (conf / "copy.com.conf").write_text(
        "server {\n  server_name copy.com;\n  root /var/www/copy.com/public;\n}\n")
    # The real command greps the system config folders; point it at this one instead, which
    # is the only substitution — the extraction it is being tested for is untouched.
    cmd = clone.build_docroot_command("copy.com").replace(
        "/etc/nginx /etc/apache2 /etc/httpd", str(conf))
    assert clone.parse_docroot(sh(cmd).stdout) == "/var/www/copy.com/public"


def test_a_site_whose_folder_cannot_be_read_stops_the_clone():
    with pytest.raises(clone.CloneError):
        clone.parse_docroot("NOCONFIG")


# ── The copy itself, run for real ────────────────────────────────────────────

def _placeholder(path):
    path.write_text("<h1>ready</h1><p>This website was created by ServerAlly and has "
                    "no content yet.</p>")


def test_the_copy_brings_the_dotfiles(tmp_path):
    """`.env`, `.htaccess` and `.git` are exactly the files that make a site work. A copy
    that quietly drops them is a clone that fails in a way nobody can see."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "public").mkdir(parents=True)
    dst.mkdir()
    (src / ".env").write_text("APP_KEY=secret\n")
    (src / "public" / ".htaccess").write_text("Deny from all\n")
    (src / "public" / "index.php").write_text("<?php echo 1;")

    r = sh(clone.build_local_copy_command(str(src), str(dst)))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dst / ".env").read_text() == "APP_KEY=secret\n"
    assert (dst / "public" / ".htaccess").exists()
    assert (dst / "public" / "index.php").exists()


def test_the_placeholder_page_is_removed_so_the_copy_is_what_gets_served(tmp_path):
    """`index index.php index.html` means a leftover index.html can outrank the copied
    site's own index — the clone then serves "this site is ready" for ever and looks like
    it failed silently."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    (dst / "public").mkdir(parents=True)
    _placeholder(dst / "public" / "index.html")
    (src / "public").mkdir()
    (src / "public" / "index.php").write_text("<?php echo 'real';")

    assert sh(clone.build_local_copy_command(str(src), str(dst))).returncode == 0
    assert not (dst / "public" / "index.html").exists()
    assert (dst / "public" / "index.php").exists()


def test_a_page_the_customer_wrote_is_never_deleted(tmp_path):
    """Recognised by the installer's own words, not by us remembering we wrote it."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (dst / "index.html").write_text("<h1>my own holding page</h1>")
    (src / "a.txt").write_text("x")

    assert sh(clone.build_local_copy_command(str(src), str(dst))).returncode == 0
    assert (dst / "index.html").read_text() == "<h1>my own holding page</h1>"


def test_the_placeholder_the_installer_actually_writes_is_the_one_recognised():
    """Pinned against the real installer — and specifically against the PAGE it writes.

    Looking anywhere in the script would pass on the "Created by ServerAlly" comment the
    same installer puts in the web-server config, which this never reads. A test that
    passes for the wrong reason stops protecting anything the day the page is reworded.
    """
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, _script_for

    script = next(_script_for(p) for p in OFFICIAL_PLAYBOOKS if p["slug"] == "create-site")
    page = script.split('index.html" <<HTMLEOF', 1)[1].split("HTMLEOF", 1)[0]
    assert clone.PLACEHOLDER_MARK in page


def test_the_folder_whose_ownership_is_repaired_is_the_one_the_files_landed_in():
    """For a framework site the served folder and the application folder are different, and
    repairing only the served one was proven on a real machine to leave `.env`, `artisan`
    and `storage/` owned by root — the site comes up, and then cannot write."""
    from app.services import permissions_service as perms

    target = clone.destination_target("app", "/var/www/copy.example.com/public")
    assert target == "/var/www/copy.example.com"
    assert perms.check_target(target) == target


def test_copying_a_folder_into_itself_is_refused(tmp_path):
    """It never terminates: the copy keeps finding what it has just written."""
    src = tmp_path / "site"
    (src / "public").mkdir(parents=True)
    r = sh(clone.build_local_copy_command(str(src), str(src / "public")))
    assert r.returncode == 5
    assert "inside itself" in r.stdout


def test_copying_a_folder_onto_its_own_parent_is_refused(tmp_path):
    src = tmp_path / "site" / "public"
    src.mkdir(parents=True)
    r = sh(clone.build_local_copy_command(str(src), str(tmp_path / "site")))
    assert r.returncode == 5


def test_a_missing_destination_stops_the_copy(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    r = sh(clone.build_local_copy_command(str(src), str(tmp_path / "nope")))
    ok, message = clone.explain(r.returncode, r.stdout)
    assert ok is False
    assert "was not created" in message


# ── The cross-server path, run for real ──────────────────────────────────────

def test_pack_and_unpack_reproduce_the_site(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "sub").mkdir(parents=True)
    (src / ".env").write_text("SECRET=1\n")
    (src / "sub" / "a.php").write_text("<?php")
    dst.mkdir()
    _placeholder(dst / "index.html")
    archive = str(tmp_path / "serverally-clone-x.tar.gz")

    assert sh(clone.build_pack_command(str(src), archive)).returncode == 0
    assert os.path.exists(archive)

    r = sh(clone.build_unpack_command(archive, str(dst)))
    assert r.returncode == 0, r.stdout
    assert (dst / ".env").read_text() == "SECRET=1\n"
    assert (dst / "sub" / "a.php").exists()
    assert not (dst / "index.html").exists()
    # A full copy of somebody's website does not stay in a temp folder.
    assert not os.path.exists(archive)


def test_the_archive_is_removed_even_when_unpacking_fails(tmp_path):
    archive = str(tmp_path / "serverally-clone-x.tar.gz")
    open(archive, "w").write("not a tar file at all")
    r = sh(clone.build_unpack_command(archive, str(tmp_path)))
    ok, message = clone.explain(r.returncode, r.stdout)
    assert ok is False
    assert "could not be unpacked" in message
    assert not os.path.exists(archive)


def test_only_our_own_staged_archive_can_be_discarded():
    r = sh(clone.build_discard_command("/etc/passwd"))
    assert r.returncode == 4
    assert "Refusing" in r.stdout


# ── What the customer is told ────────────────────────────────────────────────

def test_a_same_server_clone_says_the_copy_shares_the_live_database():
    """The credentials in the copied config still WORK on this machine, so the "staging"
    copy writes to the real site. This is the single most important sentence here."""
    note = clone.database_warning("wordpress", same_server=True)
    assert "ORIGINAL" in note and "changes the live site" in note


def test_a_cross_server_clone_says_the_copy_will_not_connect():
    note = clone.database_warning("wordpress", same_server=False)
    assert "will not connect" in note


def test_a_static_site_is_not_warned_about_a_database_it_does_not_have():
    assert clone.database_warning("static", same_server=True) is None


# ── The heartbeat ────────────────────────────────────────────────────────────

def test_a_slow_copy_keeps_talking_so_it_is_not_mistaken_for_a_dead_connection(tmp_path):
    """Our SSH channel gives up after 60 seconds of SILENCE, and copying files says nothing
    at all until it finishes — so without this, the clone big enough to be worth watching is
    exactly the one reported as a connection failure while it was working perfectly.

    Slow on purpose: proving it needs a step that outlasts the interval, and a shorter
    interval invented for the test would prove nothing about the real one.
    """
    import time

    start = time.monotonic()
    r = sh("set -e; " + clone._while_it_works("sleep 22", "... still copying",
                                              on_fail="it failed") + "echo done")
    elapsed = time.monotonic() - start
    assert r.returncode == 0, r.stdout + r.stderr
    ticks = [ln for ln in r.stdout.splitlines() if ln.startswith("... still")]
    assert ticks, "a copy this long said nothing for 22 seconds"
    # Nothing may go more than a minute without a word, or the channel is gone.
    assert elapsed / (len(ticks) + 1) < 60


def test_a_failure_inside_the_slow_step_is_still_a_failure():
    """The loop must not swallow it: the status comes from `wait`, not from the loop."""
    r = sh("set -e; " + clone._while_it_works("exit 9", "...", on_fail="it broke") + "echo done")
    assert r.returncode == 6
    assert "it broke" in r.stdout
    assert "done" not in r.stdout
