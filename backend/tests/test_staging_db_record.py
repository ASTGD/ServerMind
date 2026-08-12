"""BUG-021 — a staging copy must record its own database, or removing it orphans one.

Found by running the whole thing on a real server: `promo.firevps.net` and its staging copy
were both removed with `drop_database: true`, the LIVE site's database was dropped, and the
copy's survived. The removal was not at fault — it said *"No database was recorded for this
site, so none was removed"* rather than guessing a name to drop, which is right. Nothing had
written the record.

**The tests run the generated shell and read the file back**, rather than asserting the
right words appear in a command. A `printf ... > file` that appears in a string is true
whether or not the file it writes can be read by the thing that has to read it — and the
thing that has to read it is a *different script*, which is where this broke.
"""
import os
import shlex
import subprocess
import sys

import pytest

from app.services import playbook_service, staging_service as st

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX shell")

PW = "p@ss w0rd$`%&|\\'\"x"      # every character a shell or printf could misread


def run(script: str, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)


def remover_extraction() -> tuple[str, str]:
    """The two lines `site-remove` uses to read the record — taken from the script itself.

    Copying them here would let the two sides drift silently, which is the entire bug: one
    place writes a record and another place reads one, and nothing checked they agreed.
    """
    pb = next(p for p in playbook_service.OFFICIAL_PLAYBOOKS if p["slug"] == "site-remove")
    body = pb["script_bash"]
    lines = [ln.strip() for ln in body.splitlines()]
    name = next(ln for ln in lines if ln.startswith("DB_NAME=") and "CREDS" in ln)
    user = next(ln for ln in lines if ln.startswith("DB_USER=") and "CREDS" in ln)
    return name, user


# ── the record is written, and the remover can read it ───────────────────────

def test_the_remover_reads_back_exactly_what_we_wrote(tmp_path):
    """The whole bug in one test: write the record the way staging does, then extract it
    the way the REMOVER does, and require the same values out."""
    script = st.build_record_db("staging.shop.example.com", "stg_shop", "stg_user", PW)
    creds = tmp_path / "record.txt"
    # Same content, written to a path the test can reach rather than /root.
    script = script.replace(st.creds_path("staging.shop.example.com"), str(creds))
    assert run(script, tmp_path).returncode == 0

    name_line, user_line = remover_extraction()
    out = run(f'CREDS={shlex.quote(str(creds))}\n{name_line}\n{user_line}\n'
              f'printf "%s|%s" "$DB_NAME" "$DB_USER"', tmp_path)
    assert out.stdout == "stg_shop|stg_user", (
        f"the remover read {out.stdout!r} out of the record staging wrote")


def test_the_password_survives_every_character_a_shell_could_eat(tmp_path):
    """The password is generated, so it is never typed — but it still passes through
    `printf` and a shell, and a mangled one is a record that cannot be used to get back
    into the database it names."""
    creds = tmp_path / "record.txt"
    script = st.build_record_db("s.example.com", "n", "u", PW).replace(
        st.creds_path("s.example.com"), str(creds))
    assert run(script, tmp_path).returncode == 0
    written = [ln for ln in creds.read_text().splitlines() if ln.startswith("password:")]
    assert written == [f"password: {PW}"], written


def test_the_record_is_root_only(tmp_path):
    """It holds a working database password. World-readable, every account on the server
    can take the copy's data."""
    creds = tmp_path / "record.txt"
    script = st.build_record_db("s.example.com", "n", "u", "x").replace(
        st.creds_path("s.example.com"), str(creds))
    run(script, tmp_path)
    assert oct(os.stat(creds).st_mode)[-3:] == "600"


def test_a_copy_with_no_database_records_nothing(tmp_path):
    """A site with no database gets no record. A file claiming one would have the remover
    try to drop a database called nothing."""
    assert st.build_record_db("s.example.com", "", "", "") == ""
    assert st.build_record_db("s.example.com", "only_a_name", "", "") == ""


def test_the_path_is_the_one_the_remover_looks_at():
    """`site-remove` reads /root/<domain>_db.txt. Any other path is a record nobody reads."""
    pb = next(p for p in playbook_service.OFFICIAL_PLAYBOOKS if p["slug"] == "site-remove")
    assert 'CREDS="/root/${DOMAIN}_db.txt"' in pb["script_bash"]
    assert st.creds_path("shop.example.com") == "/root/shop.example.com_db.txt"


# ── when it is written, and when it is taken away ────────────────────────────

def test_the_record_is_written_only_after_the_repoint_is_known_good():
    """A record written before the guard would survive a copy that was torn down for
    pointing at the live database — naming a database that gets dropped seconds later."""
    cmd = st.build_stage_command(
        source="/var/www/a", target="/var/www/b", domain="b.example.com",
        source_domain="a.example.com", config="wordpress",
        db_name="n", db_user="u", db_pass="p")
    assert "_db.txt" in cmd
    # The guard that removes the whole copy comes first.
    assert cmd.index('if [ -n "$FAILED" ]') < cmd.index("_db.txt")


def test_undoing_a_copy_takes_its_record_with_it():
    import inspect

    from app.workers import staging_runner

    body = inspect.getsource(staging_runner._undo)          # noqa: SLF001
    assert "build_forget_db_record" in body
    # Only alongside the database it names — a record with no database is not the case
    # this handles, and removing files nobody asked about is its own surprise.
    assert body.index("drop_database") < body.index("build_forget_db_record")


def test_forgetting_the_record_names_the_right_file(tmp_path):
    creds = tmp_path / "record.txt"
    creds.write_text("database: x\n")
    cmd = st.build_forget_db_record("s.example.com").replace(
        st.creds_path("s.example.com"), str(creds))
    assert run(cmd, tmp_path).returncode == 0
    assert not creds.exists()


def test_a_domain_cannot_break_out_of_the_filename(tmp_path):
    """The domain reaches a path. It is validated long before here, but this file is written
    as root, so the quoting is asserted rather than assumed."""
    cmd = st.build_forget_db_record("a.com; rm -rf /tmp/sentinel")
    assert "; rm -rf" not in cmd.replace(shlex.quote("/root/a.com; rm -rf /tmp/sentinel_db.txt"), "")
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("still here")
    run(cmd.replace("/root/", str(tmp_path) + "/"), tmp_path)
    assert sentinel.read_text() == "still here"
