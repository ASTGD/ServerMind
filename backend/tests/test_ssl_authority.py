"""Choosing the certificate authority — Ploi's Let's Encrypt / ZeroSSL.

The reason to have a second one is narrow but real: Let's Encrypt allows five certificates
per domain per week, and an agency adding subdomains to one domain reaches that in an
afternoon — after which every attempt fails for days with an error that reads like a
configuration problem.

**The HMAC key is a credential, so the test that matters records what certbot actually
received.** A stub certbot dumps its own argv; the key must be absent from it and present
only in a mode-600 file that is gone afterwards.
"""
import os
import stat
import subprocess

import pytest

from app.services import playbook_service as pb
from app.services import ssl_service as sv


KID = "eab-kid-9f2c"
HMAC = "SUPERSECRET-hmac-key-value"


def _script(**over):
    spec = next(p for p in pb.OFFICIAL_PLAYBOOKS if p["slug"] == "site-ssl")
    variables = {"DOMAIN": "shop.test", "EMAIL": "a@b.com", "DOMAIN_FLAGS": "-d shop.test",
                 "ACME_SERVER": "", "EAB_KID": "", "EAB_KEY": ""}
    variables.update(over)
    return pb.substitute_variables(spec["script_bash"], variables)


def _run(tmp_path, **over):
    """Run the real generated script with certbot and the web server stubbed."""
    binstub = tmp_path / "bin"
    binstub.mkdir(exist_ok=True)
    argv = tmp_path / "certbot-argv"
    seen = tmp_path / "certbot-conf-seen"
    # Records what certbot was given, AND a copy of any config file it was pointed at —
    # so the test can prove the secret was in the file and not in the arguments.
    (binstub / "certbot").write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{argv}"\n'
        'p=""; while [ $# -gt 0 ]; do case "$1" in -c) p="$2";; esac; shift; done\n'
        f'[ -n "$p" ] && cat "$p" > "{seen}"\n'
        # `stat -c` is GNU and `stat -f` is BSD; the first version recorded nothing at all
        # on this machine, which made the permission assertion pass for no reason.
        f'[ -n "$p" ] && {{ stat -c %a "$p" 2>/dev/null || stat -f %Lp "$p" 2>/dev/null; }} '
        f'>> "{seen}"\n'
        "exit 0\n")
    for name, body in (("systemctl", "exit 0"), ("nginx", "exit 0"), ("apachectl", "exit 0"),
                       ("apt-get", "exit 0"), ("ufw", "exit 0"), ("grep", None)):
        if body is None:
            continue
        (binstub / name).write_text(f"#!/bin/sh\n{body}\n")
    (binstub / "curl").write_text('#!/bin/sh\nprintf "200"\n')
    for f in binstub.iterdir():
        f.chmod(0o755)

    script = _script(**over)
    # The distro layer reads /etc/os-release, which does not exist on the machine this test
    # runs on. It is not what these tests are about — the multi-distro behaviour has its own
    # tests — so it is answered rather than skipped, and the script below is otherwise the
    # real one.
    script = script.replace("if [ -r /etc/os-release ]; then . /etc/os-release; fi",
                            'OS_ID=ubuntu; ID_LIKE=debian; ID=ubuntu')
    # The parts that need a real machine are stubbed out: package installs, the
    # already-configured check, and the final verification.
    script = script.replace("pkg_refresh", "true").replace("pkg_install", "true ")
    script = script.replace(
        'if ! grep -rq -- "$DOMAIN" /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null; then',
        "if false; then")
    script = script.replace("systemctl is-active --quiet nginx 2>/dev/null && NGINX=yes",
                            "NGINX=yes")
    proc = subprocess.run(["bash", "-c", f'export PATH="{binstub}:$PATH"; {script}'],
                          capture_output=True, text=True)
    return (proc.returncode, proc.stdout + proc.stderr,
            argv.read_text() if argv.exists() else "",
            seen.read_text() if seen.exists() else "")


# ── The credential never reaches a command line ──────────────────────────────

def test_the_hmac_key_is_never_an_argument(tmp_path):
    """An argument is visible in `ps` for as long as the command runs, and is kept in this
    run's stored output. The same rule the offsite-backup URL follows."""
    code, out, argv, conf = _run(tmp_path, ACME_SERVER=sv.AUTHORITIES["zerossl"]["server"],
                                 EAB_KID=KID, EAB_KEY=HMAC)
    assert code == 0, out
    assert argv, "certbot was never called"
    assert HMAC not in argv, f"the HMAC key was passed as an argument: {argv}"
    assert KID not in argv
    assert HMAC in conf, "…and it must actually have reached certbot, in the file"
    assert f"eab-kid = {KID}" in conf
    assert "acme.zerossl.com" in conf


def test_the_config_file_is_readable_only_by_us(tmp_path):
    _code, _out, _argv, conf = _run(tmp_path, ACME_SERVER="https://acme.zerossl.com/v2/DV90",
                                    EAB_KID=KID, EAB_KEY=HMAC)
    assert conf.strip().endswith("600"), conf


def test_the_config_file_does_not_survive_the_run(tmp_path):
    """It holds the HMAC key. A trap removes it however the script ends.

    Scoped to the files THIS run creates rather than "is /tmp clean": /tmp is shared, and a
    mutation run that deliberately broke the trap left files behind that then failed this
    test for a reason that had nothing to do with the code under it.
    """
    import pathlib as _pl

    before = set(_pl.Path("/tmp").glob("sa_acme.*"))
    _code, _out, _argv, _conf = _run(tmp_path, ACME_SERVER="https://acme.zerossl.com/v2/DV90",
                                     EAB_KID=KID, EAB_KEY=HMAC)
    left = set(_pl.Path("/tmp").glob("sa_acme.*")) - before
    assert not left, f"a file holding the HMAC key was left behind: {left}"


def test_the_secret_is_not_echoed_into_the_run_output(tmp_path):
    _code, out, _argv, _conf = _run(tmp_path, ACME_SERVER="https://acme.zerossl.com/v2/DV90",
                                    EAB_KID=KID, EAB_KEY=HMAC)
    assert HMAC not in out and KID not in out


# ── Let's Encrypt is untouched ───────────────────────────────────────────────

def test_the_default_path_passes_no_config_at_all(tmp_path):
    """Adding a second authority must not change what every existing caller does."""
    code, out, argv, conf = _run(tmp_path)
    assert code == 0, out
    assert " -c " not in argv, argv
    assert conf == ""
    assert "Let's Encrypt" in out


def test_an_authority_that_needs_no_account_binding_does_not_abort(tmp_path):
    """`[ -n "$X" ] && printf …` at the end of a list returns non-zero when X is empty, and
    under `set -e` that exits the script — silently, before certbot is ever called. Found by
    reading, kept by running."""
    code, out, argv, conf = _run(tmp_path, ACME_SERVER="https://acme.example.com/dir")
    assert code == 0, out
    assert argv, "the script exited before calling certbot"
    assert "server = https://acme.example.com/dir" in conf
    assert "eab-" not in conf


# ── The choice itself ────────────────────────────────────────────────────────

def test_zerossl_without_its_credentials_is_refused_before_anything_runs():
    with pytest.raises(sv.SslError) as exc:
        sv.check_authority("zerossl")
    assert "ZeroSSL" in str(exc.value) and "Developer" in str(exc.value)


def test_lets_encrypt_needs_nothing():
    assert sv.check_authority("letsencrypt") == {"server": "", "eab_kid": "", "eab_key": ""}


def test_an_unknown_authority_is_refused():
    with pytest.raises(sv.SslError):
        sv.check_authority("someone-else")


@pytest.mark.parametrize("bad", ["with space", "line\nbreak", "carriage\rreturn", "x" * 600])
def test_a_credential_that_could_add_a_line_to_the_file_is_refused(bad):
    """These reach a config file rather than a shell — but a newline would end the line they
    are on and start a directive of its own."""
    with pytest.raises(sv.SslError):
        sv.check_authority("zerossl", eab_kid="ok", eab_key=bad)


def test_both_authorities_say_what_they_are_for_in_plain_words():
    for spec in sv.AUTHORITIES.values():
        assert spec["label"] and spec["blurb"]
        assert "ACME" not in spec["blurb"], "nobody buying this knows what ACME is"
