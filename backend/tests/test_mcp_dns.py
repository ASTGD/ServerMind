"""DNS over MCP — and the two accidents its shape exists to prevent.

The DNS feature was complete in the app (list, create, update, delete, a pre-flight check)
and reachable from nowhere else. A customer's AI could see their servers and their sites and
not the records that decide whether either is reachable.

The interesting part is not that DNS was exposed but HOW:

**One write tool, an upsert — not a create and an update.** Separate create/update is how the
most common DNS accident happens: a SECOND A record is added instead of the first being
changed, so half the visitors keep reaching the old server. That failure looks intermittent,
survives a cache flush, and is very hard to trace. `set` asks what the record SHOULD be.

**No delete tool at all.** MCP's standing rule is no shell, no delete, no restore, and DNS is
exactly why: removing an MX record stops mail with no undo anywhere in the system.
"""
import inspect

import pytest

from app.mcp import server as mcp
from app.services import dns_service as dns


def code(fn) -> str:
    """Executable lines only. A comment explaining why there is no delete tool contains the
    word 'delete' — the trap that has caught this codebase repeatedly."""
    return "\n".join(ln for ln in inspect.getsource(fn).splitlines()
                     if not ln.strip().startswith("#"))


# ── the shape ────────────────────────────────────────────────────────────────

def test_there_is_no_dns_delete_tool():
    """Removing a record — an MX above all — stops something working with no undo. Fixing a
    wrong value is what the write tool does; destroying one is not offered."""
    names = [n for n in dir(mcp) if n.startswith("serverally_") and "dns" in n]
    assert sorted(names) == [
        "serverally_list_dns_records",
        "serverally_list_dns_zones",
        "serverally_set_dns_record",
    ], names


def test_the_write_tool_is_an_upsert_not_a_blind_create():
    """It must look at what is already there. Creating without looking is how the duplicate
    A record appears."""
    body = code(mcp.serverally_set_dns_record)
    assert "list_records" in body
    assert body.index("list_records") < body.index("create_record")


def test_several_matching_records_are_refused_rather_than_guessed():
    """Legitimate for MX, TXT and round-robin A. Which one to replace is the owner's
    decision — a guess here silently deletes a record they wanted."""
    body = code(mcp.serverally_set_dns_record)
    assert "len(matches) > 1" in body
    # And it refuses BEFORE writing anything.
    assert body.index("len(matches) > 1") < body.index("update_record")


def test_it_refuses_when_it_cannot_read_the_existing_records():
    """Fails closed. Unable to look means unable to know whether this duplicates, and
    creating blind is the exact accident the upsert exists to avoid."""
    body = code(mcp.serverally_set_dns_record)
    listing = body.index("list_records")
    writing = body.index("create_record")
    between = body[listing:writing]
    assert "return" in between and "nothing was" in between


# ── the rules are reused, not restated ───────────────────────────────────────

def test_validation_comes_from_the_service():
    """`dns_service.validate` holds the rules that matter. A second copy in the MCP layer is
    how the two start disagreeing about what a valid record is."""
    body = code(mcp.serverally_set_dns_record)
    assert "dns.validate(" in body
    assert body.index("dns.validate(") < body.index("list_records")


def test_the_warning_reaches_the_caller():
    """`warn_for` exists because a correct-looking edit can still be the one that takes the
    site down. The caller's AI has to see it or it may as well not exist."""
    body = code(mcp.serverally_set_dns_record)
    assert "warn_for" in body and "warning" in body


@pytest.mark.parametrize("kind", dns.READONLY_TYPES)
def test_provider_managed_types_cannot_be_written(kind):
    """NS and SOA are how the domain is found at all. The service refuses them and the tool
    inherits that by using it."""
    with pytest.raises(dns.InvalidRecord):
        dns.validate(type_=kind, name="@", content="x", zone="example.com")


def test_the_accidents_the_validator_catches_are_still_caught():
    """Spot-check the two that a provider accepts and that break a domain quietly, so this
    stays true if the service is refactored."""
    with pytest.raises(dns.InvalidRecord):          # CNAME on the apex
        dns.validate(type_="CNAME", name="@", content="somewhere.example.net",
                     zone="example.com")
    with pytest.raises(dns.InvalidRecord):          # MX pointing at an IP
        dns.validate(type_="MX", name="@", content="203.0.113.10",
                     zone="example.com", priority=10)


# ── permission and secrecy ───────────────────────────────────────────────────

def test_a_read_only_connection_cannot_change_dns():
    """The server tools get this from `_executor`; DNS has no server to resolve, so the
    scope is checked on its own rather than quietly skipped."""
    body = code(mcp.serverally_set_dns_record)
    assert "_full_access_required()" in body
    # Before anything else — a permission check after the work is not a permission check.
    assert body.index("_full_access_required()") < body.index("_resolve_caller")
    assert "SCOPE_WRITE" in code(mcp._full_access_required)      # noqa: SLF001


def test_the_provider_token_never_leaves_the_server():
    """The API key can change every record the customer owns. `public_record` and
    `public_account` are allowlists; a model dump would publish the credential the first
    time somebody added a column."""
    for fn in (mcp.serverally_list_dns_zones, mcp.serverally_list_dns_records,
               mcp.serverally_set_dns_record):
        body = code(fn)
        for leak in ("encrypted_cred", "credential", "api_token", "decrypt("):
            assert leak not in body, f"{fn.__name__} touches {leak}"


def test_records_are_serialised_through_the_allowlist():
    body = code(mcp.serverally_list_dns_records)
    assert "dns.public_record(" in body


def test_a_zone_is_found_by_name_because_that_is_what_the_caller_knows():
    """An AI asked to fix example.com has no zone id and no account id."""
    body = code(mcp._dns_zone)                                # noqa: SLF001
    assert "list_zones" in body
    # An unreachable provider must not hide a zone held by another one.
    assert "continue" in body


def test_every_dns_change_is_audited():
    """"When did this break?" is usually answered by finding the record change that caused
    it, so the change has to be recorded."""
    assert "_audit(" in code(mcp.serverally_set_dns_record)


# ── the matching rule itself ─────────────────────────────────────────────────
#
# Pulled out of the tool and tested directly. Inline, the only thing a test could reach was
# "were the existing records READ" — and a mutation that read them and then ignored them,
# always creating, passed every test in this file. That mutation is the bug: a second A
# record beside the first, half the visitors served by the old server.

class _Rec:
    def __init__(self, type_, name, content, rid="r1"):
        self.type, self.name, self.content, self.record_id = type_, name, content, rid


def rec(type_="A", name="www.example.com", content="203.0.113.10"):
    return {"type": type_, "name": name, "content": content}


def test_an_existing_record_is_matched_so_it_is_changed_not_duplicated():
    """The whole point. One A record for www already exists, so the change replaces it."""
    existing = [_Rec("A", "www.example.com", "198.51.100.1")]
    assert mcp._dns_match(existing, rec()) == existing        # noqa: SLF001


def test_nothing_matching_means_it_is_created():
    existing = [_Rec("A", "api.example.com", "198.51.100.1")]
    assert mcp._dns_match(existing, rec()) == []              # noqa: SLF001


def test_the_same_name_with_a_different_type_is_not_the_same_record():
    """A TXT and an A on one name coexist perfectly well; replacing one with the other
    would delete something the customer needs."""
    existing = [_Rec("TXT", "www.example.com", "v=spf1 -all")]
    assert mcp._dns_match(existing, rec()) == []              # noqa: SLF001


def test_matching_ignores_case_because_dns_does():
    """A provider may hand the name back in a different case from the one we sent. Treating
    that as a different record is how the duplicate appears."""
    existing = [_Rec("A", "WWW.Example.COM", "198.51.100.1")]
    assert len(mcp._dns_match(existing, rec())) == 1          # noqa: SLF001


def test_several_matches_are_all_returned_so_the_caller_can_refuse():
    """Round-robin A records are legitimate. The rule reports all of them; the tool then
    refuses rather than picking one."""
    existing = [_Rec("A", "www.example.com", "198.51.100.1", "a"),
                _Rec("A", "www.example.com", "198.51.100.2", "b")]
    assert len(mcp._dns_match(existing, rec())) == 2          # noqa: SLF001
