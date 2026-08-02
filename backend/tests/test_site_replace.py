"""Replacing what is on a site.

Putting WordPress on a domain that currently runs Laravel means DELETING the Laravel site.
That is a legitimate thing to want and a terrible thing to do by accident, so the flag that
allows it is its own thing rather than a wider reading of the flag that lets an installer
adopt an EMPTY site.

The load-bearing property is that ``REPLACE`` on its own can do nothing. The folder is only
ever cleared through ``adopt_dir``, which runs only when ``TAKEOVER`` already adopted a
config carrying ServerAlly's own marker — so a site we did not build stays untouchable no
matter what is passed. Every test below runs the REAL guard text out of the REAL generated
script against a REAL directory, because a test that only checks the script CONTAINS the
word ``REPLACE`` passes just as happily when the branch around it is wrong.
"""
import subprocess
import textwrap

import pytest

from app.services import playbook_service as ps
from app.services import site_service as ss


# ── Running the real guard ───────────────────────────────────────────────────

def _generated(slug: str, *, replace: bool) -> str:
    """The script a real install would send to a real server."""
    item = next(i for i in ps.OFFICIAL_PLAYBOOKS if i["slug"] == slug)

    class _PB:
        variables = ps._variables_for(item)
        script_bash = ps._script_for(item)

    spec = next(s for s in ss.SITE_TYPES.values() if s["playbook"] == slug)
    variables = ss.install_variables(
        _PB, spec, "demo.example.com",
        {"DB_PASS": "x", "N8N_PASS": "x", "ADMIN_TOKEN": "x", "START_CMD": ""},
        takeover=True, replace=replace)
    return ps.substitute_variables(_PB.script_bash, variables)


def _adopt_dir_source(script: str) -> str:
    """Lift the real adopt_dir out of the generated script, so the tests run what ships."""
    start = script.index("adopt_dir() {")
    end = script.index("\n}\n", start) + len("\n}\n")
    return script[start:end]


def _run_adopt(tmp_path, *, replace: bool, adopted: bool, contents: dict[str, str]):
    """Run the shipped adopt_dir against a real folder. Returns (exit code, folder exists)."""
    script = _generated("wordpress-site", replace=replace)
    target = tmp_path / "site"
    target.mkdir()
    for name, text in contents.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    harness = tmp_path / "harness.sh"
    harness.write_text(textwrap.dedent(f"""\
        #!/bin/bash
        set -uo pipefail
        REPLACE="{'yes' if replace else 'no'}"
        _ADOPT="{'/etc/nginx/sites-available/demo.example.com' if adopted else ''}"
        """) + _adopt_dir_source(script) + f'\nadopt_dir "{target}"\nexit $?\n')

    proc = subprocess.run(["bash", str(harness)], capture_output=True, text=True)
    return proc.returncode, target.exists(), proc.stdout


PLACEHOLDER = {"public/index.html": "<h1>New site</h1>"}
A_REAL_SITE = {"artisan": "#!/usr/bin/env php", "public/index.php": "<?php",
               ".env": "APP_KEY=base64:secret"}


def test_the_flag_alone_cannot_delete_anything(tmp_path):
    """The security property the whole design rests on.

    ``_ADOPT`` is empty whenever TAKEOVER did not adopt a config carrying our own marker —
    which is every site we merely found. Passing REPLACE by hand must still change nothing.
    """
    code, still_there, _ = _run_adopt(tmp_path, replace=True, adopted=False,
                                      contents=A_REAL_SITE)
    assert code == 1, "adopt_dir must decline when nothing was adopted"
    assert still_there, "a site we never adopted was deleted by the replace flag alone"
    assert (tmp_path / "site" / ".env").read_text() == "APP_KEY=base64:secret"


def test_without_the_flag_a_site_with_files_in_it_is_refused(tmp_path):
    """The behaviour that existed before, unchanged: an ordinary install never overwrites."""
    code, still_there, _ = _run_adopt(tmp_path, replace=False, adopted=True,
                                      contents=A_REAL_SITE)
    assert code == 1
    assert still_there, "an ordinary install deleted a site that had files in it"


def test_with_the_flag_the_folder_is_cleared(tmp_path):
    """And when it IS asked for, it actually happens — otherwise the button is a lie."""
    code, still_there, out = _run_adopt(tmp_path, replace=True, adopted=True,
                                        contents=A_REAL_SITE)
    assert code == 0
    assert not still_there
    assert "database is left alone" in out, (
        "a replace must say what it did NOT delete; the database is the only way back")


def test_an_empty_site_is_still_adopted_without_the_flag(tmp_path):
    """The normal 'add a domain, then choose what goes on it' path must be untouched."""
    code, still_there, _ = _run_adopt(tmp_path, replace=False, adopted=True,
                                      contents=PLACEHOLDER)
    assert code == 0
    assert not still_there


# ── The variable reaches every script that reads it ──────────────────────────

SITE_PLAYBOOKS = sorted(ss.takes_over())


@pytest.mark.parametrize("slug", SITE_PLAYBOOKS)
def test_every_playbook_carrying_the_guards_declares_replace(slug):
    """Declared centrally, from the script itself.

    The guards are INJECTED into every playbook, so a per-playbook declaration is wiring
    somebody has to remember. Nobody remembered ``apt_wait`` either, and that shipped as a
    command-not-found on a real customer's first server.
    """
    item = next(i for i in ps.OFFICIAL_PLAYBOOKS if i["slug"] == slug)
    assert "REPLACE" in {v["name"] for v in ps._variables_for(item)}


@pytest.mark.parametrize("slug", SITE_PLAYBOOKS)
@pytest.mark.parametrize("replace", [False, True])
def test_no_placeholder_survives_into_a_real_script(slug, replace):
    """An unsubstituted ``{{REPLACE}}`` is not "no" — it is a literal string in a shell
    comparison, and the one thing this flag must never be is accidentally true."""
    script = _generated(slug, replace=replace)
    assert "{{" not in script
    assert f'REPLACE="{"yes" if replace else "no"}"' in script


def test_creating_a_site_never_asks_to_replace():
    item = next(i for i in ps.OFFICIAL_PLAYBOOKS if i["slug"] == "laravel-site")

    class _PB:
        variables = ps._variables_for(item)
        script_bash = ps._script_for(item)

    values = ss.install_variables(_PB, ss.SITE_TYPES["laravel"], "new.example.com", None,
                                  takeover=False)
    assert values["REPLACE"] == "no"
    assert values["TAKEOVER"] == "no"


def test_replace_is_never_a_question_on_the_form():
    """It decides whether the customer's files are deleted. That is ours to ask about in
    words, on a confirmation, not to put in a form as a text field called REPLACE."""
    playbooks = {}
    for item in ps.OFFICIAL_PLAYBOOKS:
        class _PB:
            slug = item["slug"]
            variables = ps._variables_for(item)
            est_runtime_sec = item.get("est_runtime_sec")
        playbooks[item["slug"]] = _PB

    for entry in ss.catalogue(playbooks):
        names = {f["name"] for f in entry["fields"]}
        assert "REPLACE" not in names and "TAKEOVER" not in names, entry["id"]


# ── Is there anything there to replace? ──────────────────────────────────────

class _Site:
    def __init__(self, source="manual", requested_type="static"):
        self.source = source
        self.requested_type = requested_type
        self.domain = "demo.example.com"
        self.status = "live"


def test_an_empty_site_we_made_is_not_occupied():
    assert ss.occupied(_Site()) is False


def test_a_site_running_something_is_occupied():
    assert ss.occupied(_Site(requested_type="laravel")) is True


def test_a_site_we_only_found_is_occupied_whatever_it_looks_like():
    """It was there before we were. `requested_type` is empty because we never asked for
    it — reading that as "nothing is here" is how an offer to overwrite a real website
    reaches the screen."""
    assert ss.occupied(_Site(source="nginx", requested_type=None)) is True
