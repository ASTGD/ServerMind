"""Creating a certificate signing request — Ploi's "create signing request".

The other half of installing a certificate you bought: a commercial authority will not issue
one until you send them a CSR, and a CSR is only meaningful together with the private key it
was generated from.

**Both are made on the SERVER and the key never leaves it.** Generating them here would mean
the private key passing through our process and our database, which is the exact thing the
install path avoids by using SFTP. The request itself is public — it is what you email to the
authority — so reading that back is safe.

The command is RUN against real openssl, because "does this produce a valid CSR with the
right names in it" is not a question a string can answer.
"""
import shutil
import subprocess

import pytest

from app.services import cert_install_service as ci
from app.services import ssl_service


openssl = pytest.mark.skipif(shutil.which("openssl") is None, reason="needs openssl")


# ── What goes in the subject ─────────────────────────────────────────────────

def test_only_the_domain_is_required():
    assert ci.subject_string("shop.com", {}) == "/CN=shop.com"


def test_the_fields_come_out_in_the_order_an_authority_expects():
    out = ci.subject_string("shop.com", {
        "country": "GB", "state": "London", "locality": "London",
        "organisation": "Acme Ltd", "unit": "IT"})
    assert out == "/C=GB/ST=London/L=London/O=Acme Ltd/OU=IT/CN=shop.com"


def test_the_common_name_is_last_because_that_is_where_people_look():
    assert ci.subject_string("shop.com", {"country": "GB"}).endswith("/CN=shop.com")


def test_a_country_is_two_letters_and_is_upper_cased():
    assert ci.check_subject({"country": "gb"})["country"] == "GB"
    for bad in ("GBR", "G", "12"):
        with pytest.raises(ci.CertError):
            ci.check_subject({"country": bad})


@pytest.mark.parametrize("payload", [
    "Acme/O=Evil", "Acme=Evil", "Acme\nO=Evil", "Acme'", 'Acme"', "Acme`id`", "Acme$(id)",
])
def test_a_field_cannot_start_another_field_or_another_command(payload):
    """`/` and `=` are openssl's own separators inside `-subj`, so either would silently add
    a field to the certificate. Refused rather than escaped, like the domain."""
    with pytest.raises(ci.CertError):
        ci.check_subject({"organisation": payload})


def test_the_validation_cannot_be_skipped_by_using_the_other_entry_point():
    """A second door that misses the check is how the check stops happening."""
    with pytest.raises(ci.CertError):
        ci.subject_string("shop.com", {"organisation": "Acme/O=Evil"})


def test_a_domain_that_is_not_a_hostname_is_refused():
    with pytest.raises(ssl_service.SslError):
        ci.build_csr_command("../../etc/passwd", {})


# ── Run it ───────────────────────────────────────────────────────────────────

def _run(tmp_path, domain="shop.com", fields=None, names=None):
    cmd = ci.build_csr_command(domain, fields or {}, names=names)
    cmd = cmd.replace(f"/etc/ssl/serverally/{domain}", str(tmp_path))
    proc = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


@openssl
def test_it_produces_a_real_signing_request(tmp_path):
    code, out = _run(tmp_path, fields={"country": "GB", "organisation": "Acme Ltd"})
    assert code == 0, out
    csr = ci.parse_csr(out)
    read = subprocess.run(["openssl", "req", "-noout", "-text"], input=csr,
                          capture_output=True, text=True)
    assert read.returncode == 0, read.stderr
    assert "CN = shop.com" in read.stdout or "CN=shop.com" in read.stdout
    assert "Acme Ltd" in read.stdout


@openssl
def test_every_name_the_site_answers_to_is_in_the_request(tmp_path):
    """A certificate that does not name `www` gives half the visitors a browser warning on a
    site whose owner has been told it is secure — the same reason the Let's Encrypt path
    covers the aliases."""
    code, out = _run(tmp_path, names=["www.shop.com", "shop.co.uk"])
    assert code == 0, out
    read = subprocess.run(["openssl", "req", "-noout", "-text"], input=ci.parse_csr(out),
                          capture_output=True, text=True)
    for name in ("shop.com", "www.shop.com", "shop.co.uk"):
        assert f"DNS:{name}" in read.stdout, read.stdout


@openssl
def test_the_private_key_is_written_readable_by_root_only_and_is_not_printed(tmp_path):
    import os
    import stat

    code, out = _run(tmp_path)
    assert code == 0, out
    key = tmp_path / ci.CSR_KEY
    assert key.exists()
    assert stat.S_IMODE(os.stat(key).st_mode) == 0o600, oct(os.stat(key).st_mode)
    assert "PRIVATE KEY" not in out, "the key must never reach our side"


@openssl
def test_the_key_has_no_passphrase(tmp_path):
    """nginx cannot be asked for one when it starts, so a protected key means the web server
    simply never comes up."""
    _code, _out = _run(tmp_path)
    read = subprocess.run(["openssl", "pkey", "-in", str(tmp_path / ci.CSR_KEY), "-noout"],
                          capture_output=True, text=True)
    assert read.returncode == 0, read.stderr


@openssl
def test_the_waiting_key_becomes_the_certificates_key(tmp_path):
    """What makes "make a request, then install what comes back" work without the private
    key ever leaving the server or being typed by anybody."""
    _code, _out = _run(tmp_path)
    for cmd in (ci.build_pending_key_check("shop.com"), ci.build_use_pending_key("shop.com")):
        proc = subprocess.run(
            ["bash", "-c", cmd.replace("/etc/ssl/serverally/shop.com", str(tmp_path))],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (tmp_path / "privkey.pem.new").read_bytes() == (tmp_path / ci.CSR_KEY).read_bytes()


def test_no_waiting_key_is_reported_as_such_not_guessed(tmp_path):
    proc = subprocess.run(
        ["bash", "-c", ci.build_pending_key_check("shop.com")
         .replace("/etc/ssl/serverally/shop.com", str(tmp_path))],
        capture_output=True, text=True)
    assert "pending=no" in proc.stdout


def test_a_request_that_fails_leaves_nothing_behind(tmp_path):
    """A half-made key sitting where the install path looks for one would be silently used
    for a certificate it does not match."""
    cmd = ci.build_csr_command("shop.com", {}).replace(
        "/etc/ssl/serverally/shop.com", str(tmp_path))
    # openssl that WRITES the key and then fails — which is what a real partial failure
    # looks like (an option it rejects after generating, or being killed part-way). A stub
    # that fails before writing anything proves nothing: a mutation run showed the cleanup
    # could be deleted entirely and this test still passed.
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "openssl").write_text(
        "#!/bin/sh\n"
        'k=""; c=""\n'
        'while [ $# -gt 0 ]; do case "$1" in -keyout) k="$2";; -out) c="$2";; esac; shift; done\n'
        '[ -n "$k" ] && echo "-----BEGIN PRIVATE KEY-----" > "$k"\n'
        '[ -n "$c" ] && echo "half" > "$c"\n'
        "echo 'openssl: boom' >&2\nexit 1\n")
    (stub / "openssl").chmod(0o755)
    proc = subprocess.run(["bash", "-c", f'export PATH="{stub}:$PATH"; {cmd}'],
                          capture_output=True, text=True)
    assert proc.returncode == 1
    assert not (tmp_path / ci.CSR_KEY).exists()
    assert not (tmp_path / ci.CSR_FILE).exists()


def test_output_without_a_request_is_refused_rather_than_returned_empty():
    with pytest.raises(ci.CertError):
        ci.parse_csr("openssl: command not found")
