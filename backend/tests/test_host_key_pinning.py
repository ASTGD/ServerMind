"""Pinning a server's identity without accusing it of changing.

A server offers SEVERAL host keys — a fresh Ubuntu has RSA, ECDSA and ED25519 — and SSH
negotiates ONE of them per connection. Pinning the bare fingerprint of whichever key
happened to be chosen is therefore not a pin at all: the next connection can legitimately
negotiate a different key, produce a different fingerprint, and be refused as an impostor.

Seen live on a real server. It reported "Server identity changed — the connection may be
intercepted" on a machine nobody had touched, because the pin came from its RSA key while
ordinary connections negotiate ed25519. That is the worst kind of false alarm: it blocks
every action on the server AND it teaches people to click through the warning that exists
to catch a real interception.
"""
from __future__ import annotations

import pytest

from app.services import ssh_service as ssh


# ── Reading a pin ────────────────────────────────────────────────────────────

def test_a_pin_carries_the_key_type_it_came_from():
    assert ssh._split_pin("ssh-ed25519 SHA256:abc") == ("ssh-ed25519", "SHA256:abc")


def test_a_pin_written_before_this_fix_still_verifies():
    """Every existing customer has a bare fingerprint. It must keep working — just without
    being able to ask for the right key up front."""
    assert ssh._split_pin("SHA256:abc") == (None, "SHA256:abc")


def test_no_pin_means_nothing_to_check():
    assert ssh._split_pin(None) == (None, None)
    assert ssh._split_pin("  ") == (None, None)


# ── Asking for the pinned key ────────────────────────────────────────────────

def test_pinning_one_key_type_rules_out_the_others():
    """Otherwise the comparison is not like-for-like."""
    disabled = ssh._only("ssh-ed25519")["keys"]
    assert "ssh-ed25519" not in disabled
    for other in ("ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp521"):
        assert other in disabled


def test_pinning_rsa_keeps_its_modern_signature_variants():
    """`rsa-sha2-256` and `rsa-sha2-512` are signature algorithms over the SAME ssh-rsa
    key, not different keys. Disabling them alongside the others leaves the handshake with
    nothing to agree on, and a pinned-RSA server would simply stop connecting."""
    disabled = ssh._only("ssh-rsa")["keys"]
    assert "rsa-sha2-512" not in disabled
    assert "rsa-sha2-256" not in disabled
    assert "ssh-ed25519" in disabled


@pytest.mark.parametrize("keytype", ssh._KEY_TYPES)
def test_every_key_type_can_be_pinned_without_disabling_itself(keytype):
    assert keytype not in ssh._only(keytype)["keys"]


# ── The security property is unchanged ───────────────────────────────────────

def test_an_exact_fingerprint_match_is_still_required():
    """The healing path tries other key TYPES; it never relaxes the comparison. An impostor
    still has to produce a key whose fingerprint equals the pinned one, which is the entire
    protection. Asserted on the source because the alternative — a mismatch being accepted
    — is precisely the bug that must never be introduced here.
    """
    import inspect
    body = inspect.getsource(ssh._get_client)
    assert "raise HostKeyMismatch" in body, "a mismatch must still refuse"
    assert "alt_fp == want_fp" in body, "the retry must compare against the pin, not accept"
    # Nothing may skip the check when a pin exists.
    assert "if want_fp and fingerprint != want_fp" in body


def test_a_healed_connection_is_repinned_with_its_type_so_it_stops_happening():
    import inspect
    body = inspect.getsource(ssh._get_client)
    assert 'f"{keytype} {fingerprint}"' in body


def test_a_healed_pin_is_written_back_so_the_retry_is_a_one_time_cost():
    """An older bare pin makes every COLD connection try each key type before it can
    proceed. Recording the type turns that into a one-time cost.

    Safe by construction: the new value is only written when it ENDS WITH the fingerprint
    already stored — i.e. it is provably the same key, just labelled.
    """
    import inspect
    from app.routers import servers

    body = inspect.getsource(servers)
    assert "result.fingerprint.endswith(server.fingerprint)" in body, (
        "a pin may only be rewritten when it is demonstrably the same key"
    )
