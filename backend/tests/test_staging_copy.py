"""Making a staging copy.

One rule shapes every test here: **a staging copy must never be left pointing at the live
database.** Copy a live site's files and leave the configuration alone and the copy is now
WRITING to live data — somebody "testing" a bulk delete deletes real orders. So a repoint
that fails removes the whole copy, and that is proved by RUNNING the script rather than by
reading it.
"""
import os
import subprocess

import pytest

from app.services import staging_service as st


def sh(cmd):
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)


def laravel_site(tmp_path, name="live"):
    app = tmp_path / name
    (app / "public").mkdir(parents=True)
    (app / "storage" / "framework" / "views").mkdir(parents=True)
    (app / "node_modules" / "big").mkdir(parents=True)
    (app / "artisan").write_text("#!/usr/bin/env php\n")
    (app / ".env").write_text(
        "APP_ENV=production\nAPP_DEBUG=false\nAPP_URL=https://shop.example.com\n"
        "DB_DATABASE=live_db\nDB_USERNAME=live_user\nDB_PASSWORD=live-secret\n")
    (app / "public" / "index.php").write_text("<?php echo 'site';")
    (app / "storage" / "framework" / "views" / "cached.php").write_text("cache")
    (app / "node_modules" / "big" / "x.js").write_text("x" * 500)
    return app


# ── The rule ─────────────────────────────────────────────────────────────────

def test_the_copy_is_repointed_at_its_own_database(tmp_path):
    src, dst = laravel_site(tmp_path), tmp_path / "staging"
    r = sh(st.build_stage_command(
        source=str(src), target=str(dst), domain="staging.shop.example.com",
        source_domain="shop.example.com", config="laravel",
        db_name="stg_db", db_user="stg_user", db_pass="stg-secret"))
    assert r.returncode == 0, r.stdout + r.stderr

    env = (dst / ".env").read_text()
    assert "DB_DATABASE=stg_db" in env
    assert "DB_USERNAME=stg_user" in env
    assert "DB_PASSWORD=stg-secret" in env
    # and nothing of the live connection survives
    assert "live_db" not in env and "live_user" not in env and "live-secret" not in env
    assert "APP_URL=https://staging.shop.example.com" in env
    assert "APP_ENV=staging" in env
    assert "APP_DEBUG=true" in env


def test_a_repoint_that_fails_removes_the_whole_copy(tmp_path):
    """THE test. A staging site connected to live data is worse than no staging site, so
    there must be no state in which one exists half-made."""
    src, dst = laravel_site(tmp_path), tmp_path / "staging"
    (src / ".env").unlink()          # nothing to repoint

    r = sh(st.build_stage_command(
        source=str(src), target=str(dst), domain="staging.shop.example.com",
        source_domain="shop.example.com", config="laravel",
        db_name="stg_db", db_user="u", db_pass="p"))
    assert r.returncode == 6
    assert not dst.exists(), "a copy that could not be repointed must not survive"
    ok, message = st.explain(r.returncode, r.stdout)
    assert ok is False
    assert "removed entirely" in message
    assert "worse than no staging site" in message


def test_the_repoint_is_proved_by_reading_the_file_back():
    """Writing is not the same as having written — sed can silently match nothing."""
    cmd = st.build_stage_command(
        source="/a", target="/b", domain="s.example.com", source_domain="example.com",
        config="laravel", db_name="stg_db", db_user="u", db_pass="p")
    assert 'grep -q "^DB_DATABASE=stg_db$"' in cmd


# ── What is and is not copied ────────────────────────────────────────────────

def test_caches_and_dependencies_are_not_copied(tmp_path):
    """They are rebuilt, and copying them spends the whole disk budget on files the copy
    does not need."""
    src, dst = laravel_site(tmp_path), tmp_path / "staging"
    assert sh(st.build_stage_command(
        source=str(src), target=str(dst), domain="s.example.com",
        source_domain="shop.example.com", config="laravel",
        db_name="d", db_user="u", db_pass="p")).returncode == 0
    assert not (dst / "node_modules").exists()
    assert not (dst / "storage" / "framework" / "views" / "cached.php").exists()
    # but the real site came across
    assert (dst / "public" / "index.php").exists()
    assert (dst / "artisan").exists()


def test_the_git_history_is_kept():
    """A staging site with its history is more useful than one without — and it is what
    makes promoting through the repository possible later."""
    assert ".git" not in st.EXCLUDE
    assert "--exclude=.git" not in st.rsync_excludes()


def test_an_existing_target_is_never_overwritten(tmp_path):
    src, dst = laravel_site(tmp_path), tmp_path / "staging"
    dst.mkdir()
    (dst / "someones-work.txt").write_text("do not delete me")
    r = sh(st.build_stage_command(
        source=str(src), target=str(dst), domain="s.example.com",
        source_domain="shop.example.com", config="laravel",
        db_name="d", db_user="u", db_pass="p"))
    assert r.returncode == 4
    assert (dst / "someones-work.txt").read_text() == "do not delete me"


# ── WordPress ────────────────────────────────────────────────────────────────

def test_wordpress_credentials_are_rewritten(tmp_path):
    src = tmp_path / "live"
    src.mkdir()
    (src / "wp-config.php").write_text(
        "<?php\ndefine( 'DB_NAME', 'live_db' );\ndefine('DB_USER', 'live_user');\n"
        "define( 'DB_PASSWORD', 'live-secret' );\n")
    (src / "index.php").write_text("<?php")
    dst = tmp_path / "staging"

    r = sh(st.build_stage_command(
        source=str(src), target=str(dst), domain="staging.shop.example.com",
        source_domain="shop.example.com", config="wordpress",
        db_name="stg_db", db_user="stg_user", db_pass="stg-secret"))
    assert r.returncode == 0, r.stdout + r.stderr
    cfg = (dst / "wp-config.php").read_text()
    assert "'stg_db'" in cfg and "live_db" not in cfg
    assert "'stg_user'" in cfg and "'stg-secret'" in cfg


def test_wordpress_gets_a_search_replace_or_every_link_points_at_the_live_site():
    """Without it every link, image and redirect on the copy sends the visitor to the LIVE
    site — which looks like the copy working and is the copy doing nothing."""
    cmd = st.build_stage_command(
        source="/a", target="/b", domain="staging.shop.com", source_domain="shop.com",
        config="wordpress", db_name="d", db_user="u", db_pass="p")
    assert "search-replace" in cmd
    assert "--skip-columns=guid" in cmd, "rewriting guid breaks every feed reader"


# ── The refusal that gives the feature its meaning ───────────────────────────

@pytest.mark.parametrize("app_type", ["wordpress", "laravel", "php"])
def test_an_app_with_a_database_and_no_config_is_refused(app_type):
    with pytest.raises(st.StagingError) as exc:
        st.check_can_repoint(app_type, "none")
    msg = str(exc.value)
    assert "LIVE site's data" in msg
    assert "was not made" in msg


def test_a_static_site_needs_no_config_and_is_allowed():
    st.check_can_repoint("static", "none")
    assert st.needs_database("static") is False


@pytest.mark.parametrize("app_type", ["wordpress", "laravel", "php"])
def test_apps_that_store_everything_in_a_database_need_one(app_type):
    """A copy without one is an install wizard — exactly the half-built thing Ploi produced
    in the owner's own test."""
    assert st.needs_database(app_type) is True


# ── Room on the disk ─────────────────────────────────────────────────────────

def test_a_copy_that_will_not_fit_is_refused_with_the_real_numbers():
    with pytest.raises(st.StagingError) as exc:
        st.check_room(10_000_000_000, 4_000_000_000)
    msg = str(exc.value)
    assert "9.3 GB" in msg and "3.7 GB" in msg


def test_room_for_the_dump_as_well_as_the_files_is_required():
    size = 1_000_000_000
    st.check_room(size, int(size * st.HEADROOM) + 1)
    with pytest.raises(st.StagingError):
        st.check_room(size, size + 1)


def test_unknown_free_space_is_refused():
    """The guess is the only thing standing between a staging copy and an outage."""
    with pytest.raises(st.StagingError):
        st.check_room(1000, None)


# ── Reading the source ───────────────────────────────────────────────────────

def test_a_framework_site_is_copied_from_above_the_folder_it_serves(tmp_path):
    src = laravel_site(tmp_path)
    r = sh(st.build_survey_command(str(src / "public")))
    got = st.parse_survey(r.stdout, r.returncode)
    assert got["scope"] == "app"
    assert got["source"] == str(src)
    assert got["config"] == "laravel"
    assert got["bytes"] > 0 and got["free"] and got["free"] > 0


def test_a_wordpress_site_is_recognised_by_its_config(tmp_path):
    src = tmp_path / "wp"
    src.mkdir()
    (src / "wp-config.php").write_text("<?php")
    assert st.parse_survey(sh(st.build_survey_command(str(src))).stdout)["config"] \
        == "wordpress"


def test_a_missing_source_is_reported_as_nothing_to_copy(tmp_path):
    r = sh(st.build_survey_command(str(tmp_path / "gone")))
    with pytest.raises(st.StagingError) as exc:
        st.parse_survey(r.stdout, r.returncode)
    assert "nothing to copy" in str(exc.value)


def test_a_rewrite_that_silently_does_nothing_still_removes_the_copy(tmp_path):
    """The case the readback exists for, and the one my first test missed: `.env` is present
    — so the file check passes — but the rewrite does not take. A stubbed `awk` that exits 0
    without writing reproduces exactly that, and it is not far-fetched: a missing tool, a
    full disk, a read-only mount all produce it. Without reading the value back, the copy
    would survive still pointing at the LIVE database."""
    src, dst = laravel_site(tmp_path), tmp_path / "staging"
    b = tmp_path / "bin"
    b.mkdir()
    (b / "awk").write_text("#!/bin/bash\nexit 0\n")     # succeeds, writes nothing
    os.chmod(b / "awk", 0o755)

    cmd = st.build_stage_command(
        source=str(src), target=str(dst), domain="staging.shop.example.com",
        source_domain="shop.example.com", config="laravel",
        db_name="stg_db", db_user="u", db_pass="p")
    r = subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; {cmd}'],
                       capture_output=True, text=True)

    assert r.returncode == 6
    assert not dst.exists(), "a copy whose repoint silently failed must not survive"


# ── Copying the data ─────────────────────────────────────────────────────────

def test_the_dump_never_carries_a_password_and_is_always_removed():
    """Between being written and being removed, that file is a complete copy of the
    customer's data sitting on disk — so it is mode-600 and a trap removes it however the
    script ends, including every failure path below."""
    cmd = st.build_copy_data_command(engine="mysql", source_db="live", target_db="stg")
    assert "--password" not in cmd and "-p" not in cmd.replace("--quick", "")
    assert "chmod 600" in cmd
    assert "trap" in cmd and "rm -f" in cmd


def test_an_empty_dump_is_refused_rather_than_imported():
    """Importing zero bytes leaves a database that exists and holds nothing — which
    WordPress renders as the install wizard, the exact half-built thing this feature exists
    to avoid."""
    cmd = st.build_copy_data_command(engine="mysql", source_db="live", target_db="stg")
    assert "EMPTYDUMP" in cmd
    ok, message = st.explain_data(8, "EMPTYDUMP")
    assert ok is False
    assert "install wizard, not a copy" in message


def test_postgres_and_mysql_each_get_their_own_tools():
    my = st.build_copy_data_command(engine="mysql", source_db="a", target_db="b")
    pg = st.build_copy_data_command(engine="postgres", source_db="a", target_db="b")
    assert "mysqldump" in my and "pg_dump" not in my
    assert "pg_dump" in pg and "sudo -u postgres" in pg


def test_a_failed_dump_says_nothing_was_left_connected_to_live():
    ok, message = st.explain_data(7, "DUMPFAILED")
    assert ok is False
    assert "Nothing was left connected to the live database" in message


def test_the_data_copy_reports_how_much_came_across():
    ok, message = st.explain_data(0, "bytes=5242880\ncopied")
    assert ok is True and "5 MB" in message


def test_a_real_dump_and_import_round_trip(tmp_path):
    """Run it, with the engine's tools stubbed, to prove the file handling — that the dump
    is created, checked for emptiness, fed to the importer, and gone afterwards."""
    b = tmp_path / "bin"
    b.mkdir()
    (b / "mysqldump").write_text("#!/bin/bash\nprintf 'CREATE TABLE orders (id INT);\\n'\n")
    (b / "mysql").write_text(f"#!/bin/bash\ncat > {tmp_path}/imported.sql\n")
    for f in ("mysqldump", "mysql"):
        os.chmod(b / f, 0o755)

    cmd = st.build_copy_data_command(engine="mysql", source_db="live", target_db="stg")
    r = subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; {cmd}'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CREATE TABLE orders" in (tmp_path / "imported.sql").read_text()
    ok, message = st.explain_data(r.returncode, r.stdout)
    assert ok is True and "of data" in message


def test_an_empty_source_database_stops_before_importing(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    (b / "mysqldump").write_text("#!/bin/bash\nexit 0\n")           # writes nothing
    (b / "mysql").write_text(f"#!/bin/bash\ntouch {tmp_path}/IMPORTED\n")
    for f in ("mysqldump", "mysql"):
        os.chmod(b / f, 0o755)

    cmd = st.build_copy_data_command(engine="mysql", source_db="live", target_db="stg")
    r = subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; {cmd}'],
                       capture_output=True, text=True)
    assert r.returncode == 8
    assert not (tmp_path / "IMPORTED").exists(), "nothing may be imported from an empty dump"


# ── The copy has to be SERVED ────────────────────────────────────────────────

def test_the_copy_is_created_as_php_when_the_files_contain_any(tmp_path):
    """Answered by the FILES, not by what we believe this site is. A PHP site served with
    no PHP handler does not fail — it hands the SOURCE of every file to anyone who asks,
    and wp-config.php holds the database password in clear text."""
    src = laravel_site(tmp_path)
    got = st.parse_survey(sh(st.build_survey_command(str(src / "public"))).stdout)
    assert got["has_php"] is True
    assert st.site_type_for(got) == "php"


def test_a_site_with_no_php_is_created_as_a_static_one(tmp_path):
    src = tmp_path / "brochure"
    src.mkdir()
    (src / "index.html").write_text("<h1>hello</h1>")
    got = st.parse_survey(sh(st.build_survey_command(str(src))).stdout)
    assert got["has_php"] is False
    assert st.site_type_for(got) == "static"


def test_php_stays_on_when_the_answer_is_not_a_clear_no():
    """Being wrong the other way publishes a database password, so anything unreadable
    leaves PHP on."""
    assert st.site_type_for({}) == "php"
    assert st.site_type_for({"has_php": True}) == "php"


def test_the_copy_is_never_created_as_the_live_site_s_own_type(tmp_path):
    """Creating it as `wordpress` would run the WordPress installer and build a fresh site
    we are about to overwrite — slower, and able to fail on its own."""
    got = st.parse_survey(sh(st.build_survey_command(str(laravel_site(tmp_path)))).stdout)
    assert st.site_type_for(got) in ("php", "static")


# ── Copying onto the site that was just created ──────────────────────────────

def _created_site(tmp_path, name="staging"):
    """What `create-site` leaves behind: a folder holding nothing but the placeholder."""
    d = tmp_path / name
    (d / "public").mkdir(parents=True)
    (d / "public" / "index.html").write_text("<h1>staging.shop.example.com is ready</h1>")
    return d


def test_the_copy_lands_on_the_site_that_was_just_created(tmp_path):
    """The whole reason the copy is served at all: it goes onto a real site with a virtual
    host, which exists and holds a placeholder by the time the files arrive."""
    src, dst = laravel_site(tmp_path), _created_site(tmp_path)
    r = sh(st.build_stage_command(
        source=str(src), target=str(dst), domain="staging.shop.example.com",
        source_domain="shop.example.com", config="laravel",
        db_name="stg_db", db_user="u", db_pass="p"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dst / "artisan").exists()
    assert "DB_DATABASE=stg_db" in (dst / ".env").read_text()


def test_the_placeholder_page_never_survives_the_copy(tmp_path):
    """A live site brings an index.php, and a leftover index.html WINS — so the staging
    site would serve "your site is ready" while the copy reported success."""
    src = tmp_path / "live"
    src.mkdir()
    (src / "index.php").write_text("<?php echo 'the real site';")
    dst = _created_site(tmp_path)
    (dst / "index.html").write_text("<h1>ready</h1>")   # the docroot-scope shape

    r = sh(st.build_stage_command(
        source=str(src), target=str(dst), domain="s.example.com",
        source_domain="shop.example.com", config="none",
        db_name="", db_user="", db_pass=""))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dst / "index.php").exists()
    assert not (dst / "index.html").exists(), "the placeholder would be served instead"


def test_the_heartbeat_keeps_the_connection_from_being_cut(tmp_path):
    """Our SSH channel gives up after 60 seconds of SILENCE, and an rsync of a real site
    says nothing until it finishes — so the copy big enough to be worth watching is exactly
    the one that would be reported as a connection failure while working perfectly."""
    import time

    src, dst = laravel_site(tmp_path), tmp_path / "staging"
    b = tmp_path / "bin"
    b.mkdir()
    (b / "rsync").write_text("#!/bin/bash\nsleep 22\n")
    os.chmod(b / "rsync", 0o755)

    started = time.monotonic()
    r = subprocess.run(
        ["bash", "-c", f'export PATH="{b}:$PATH"; ' + st.build_stage_command(
            source=str(src), target=str(dst), domain="s.example.com",
            source_domain="shop.example.com", config="none",
            db_name="", db_user="", db_pass="")],
        capture_output=True, text=True)
    elapsed = time.monotonic() - started

    ticks = [ln for ln in r.stdout.splitlines() if "still copying" in ln]
    assert ticks, "a long copy must say something, or the channel is cut mid-copy"
    # The longest gap between two things being said, including the silence before the first.
    assert elapsed / (len(ticks) + 1) < 60


# ── Taking a copy away ───────────────────────────────────────────────────────

def test_a_failed_copy_is_removed_and_says_so(tmp_path):
    src, dst = laravel_site(tmp_path), tmp_path / "staging"
    r = sh(st.build_discard_command(str(dst)))
    assert "discarded" in r.stdout


def test_the_discard_refuses_a_system_folder():
    """The only destructive command in the feature. A guard that exists in Python but not
    in the shell is not a guard, so the path is checked on the machine as well."""
    for path in ("/", "/home", "/var", "/var/www", "/etc", "/root", "/usr"):
        r = sh(st.build_discard_command(path))
        assert "REFUSED" in r.stdout, path
        assert r.returncode != 0, path


def test_the_discard_removes_a_real_copy(tmp_path):
    d = tmp_path / "a" / "b" / "staging.shop.com"
    (d / "public").mkdir(parents=True)
    (d / "public" / "index.php").write_text("<?php")
    r = sh(st.build_discard_command(str(d)))
    assert r.returncode == 0 and not d.exists()


# ── Which database the live site uses ────────────────────────────────────────

def test_the_live_database_is_read_from_the_site_s_own_config(tmp_path):
    """Without it the copy's own database is created and left EMPTY — which for WordPress
    is the install wizard, the exact half-built thing this feature exists to avoid."""
    src = laravel_site(tmp_path)
    (src / ".env").write_text('DB_DATABASE="live_db"\nDB_USERNAME=u\n')
    assert st.parse_survey(
        sh(st.build_survey_command(str(src / "public"))).stdout)["source_db"] == "live_db"

    wp = tmp_path / "blog"
    wp.mkdir()
    (wp / "wp-config.php").write_text("<?php\ndefine( 'DB_NAME', 'wp_live' );\n")
    assert st.parse_survey(
        sh(st.build_survey_command(str(wp))).stdout)["source_db"] == "wp_live"


def test_a_site_with_no_database_config_reports_none(tmp_path):
    src = tmp_path / "brochure"
    src.mkdir()
    (src / "index.html").write_text("hi")
    got = st.parse_survey(sh(st.build_survey_command(str(src))).stdout)
    assert got["source_db"] == "" and got["config"] == "none"


# ── The twin refusal: a copy with an EMPTY database ──────────────────────────

@pytest.mark.parametrize("app_type", ["wordpress", "laravel", "php"])
def test_a_copy_that_would_get_an_empty_database_is_refused(app_type):
    """The twin of check_can_repoint. That one stops a copy that would WRITE to live data;
    this one stops a copy that would read from nothing — which WordPress renders as the
    install wizard, the exact half-built thing Ploi's version produced."""
    with pytest.raises(st.StagingError) as exc:
        st.check_can_copy_data(app_type, "")
    msg = str(exc.value)
    assert "install wizard, not a copy" in msg
    assert "Nothing was created" in msg


def test_a_copy_with_a_database_we_can_find_gets_one():
    assert st.check_can_copy_data("wordpress", "wp_live") is True


def test_a_site_that_stores_nothing_in_a_database_needs_none():
    assert st.check_can_copy_data("static", "") is False


def test_a_whitespace_only_database_name_counts_as_missing():
    with pytest.raises(st.StagingError):
        st.check_can_copy_data("wordpress", "   ")


# ── Which engine, and the one that has no server database at all ─────────────

def test_the_copy_uses_the_engine_the_live_site_uses():
    """A copy on a different engine is not a copy — so it is read from the site rather than
    chosen, and an unreadable answer falls back to the one nearly every site uses."""
    assert st.normalise_engine("pgsql") == "postgres"
    assert st.normalise_engine("postgresql") == "postgres"
    assert st.normalise_engine("mysql") == "mysql"
    assert st.normalise_engine("mariadb") == "mysql"
    assert st.normalise_engine("") == "mysql"


def test_a_sqlite_site_needs_no_database_because_its_database_is_a_file():
    """The database is a FILE inside the site, so the copy has its own the moment the files
    land. Making one would be pointless, and repointing DB_DATABASE — which holds a file
    PATH — at a database name would break the copy outright."""
    assert st.check_can_copy_data("laravel", "database.sqlite", engine="sqlite") is False
    # and it is not refused for having no database name we recognise
    st.check_can_copy_data("laravel", "", engine="sqlite")


def test_the_engine_is_read_from_the_site_s_own_config(tmp_path):
    src = laravel_site(tmp_path)
    (src / ".env").write_text("DB_CONNECTION=pgsql\nDB_DATABASE=live_db\n")
    got = st.parse_survey(sh(st.build_survey_command(str(src / "public"))).stdout)
    assert got["engine"] == "postgres"

    (src / ".env").write_text("DB_CONNECTION=sqlite\nDB_DATABASE=database.sqlite\n")
    got = st.parse_survey(sh(st.build_survey_command(str(src / "public"))).stdout)
    assert got["engine"] == "sqlite"


def test_wordpress_is_always_mysql(tmp_path):
    wp = tmp_path / "wp"
    wp.mkdir()
    (wp / "wp-config.php").write_text("<?php\ndefine( 'DB_NAME', 'wp_live' );\n")
    assert st.parse_survey(sh(st.build_survey_command(str(wp))).stdout)["engine"] == "mysql"


def test_a_sqlite_copy_keeps_its_own_database_path(tmp_path):
    """Blanking DB_DATABASE here would break a copy that was working: it holds the path to
    the SQLite file that came across with the files."""
    src, dst = laravel_site(tmp_path), tmp_path / "staging"
    (src / ".env").write_text(
        "APP_ENV=production\nDB_CONNECTION=sqlite\nDB_DATABASE=database.sqlite\n")
    (src / "database.sqlite").write_text("sqlite-bytes")

    r = sh(st.build_stage_command(
        source=str(src), target=str(dst), domain="staging.shop.example.com",
        source_domain="shop.example.com", config="laravel",
        db_name="", db_user="", db_pass=""))
    assert r.returncode == 0, r.stdout + r.stderr
    env = (dst / ".env").read_text()
    assert "DB_DATABASE=database.sqlite" in env, "the copy's own SQLite file must stay named"
    assert (dst / "database.sqlite").exists()
    # the rest of the repoint still happened
    assert "APP_ENV=staging" in env
    assert "APP_URL=https://staging.shop.example.com" in env
