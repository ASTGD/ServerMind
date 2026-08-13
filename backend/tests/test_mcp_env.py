"""A site's .env over MCP — built so the shell stops being borrowed for it.

`serverally_read_file` masks secrets over MCP, deliberately, because there is no
client-side redaction out here. The consequence showed up in real use: an AI that needs an
application's credentials cannot get them through the proper tool, so it asks for
`run_command` instead — a full shell, with none of ServerAlly's higher protections and no
rollback. Requesting a shell in order to read one file is a safety control being walked
around, and the fix is a tool for the job rather than a wider grant.

Two properties carry it, and both are about what a customer THINKS they agreed to:

1. **Reading needs Full access, not Read-only.** These return live credentials. Somebody who
   chose "Read-only" believes they granted something that cannot hurt them; handing it every
   database password would make that label a lie.
2. **The content never touches a command line.** Every line of the file is a credential, and
   a command's arguments are visible in `ps` and are kept in the stored output of the run.
"""
import inspect

import pytest

from app.mcp import server as mcp


def code(fn) -> str:
    """Executable lines only — a comment explaining why the content never reaches a command
    line naturally contains the words it warns about."""
    return "\n".join(ln for ln in inspect.getsource(fn).splitlines()
                     if not ln.strip().startswith("#"))


BOTH = (mcp.serverally_get_site_env, mcp.serverally_set_site_env)


# ── the promise a connection's label makes ───────────────────────────────────

@pytest.mark.parametrize("fn", BOTH, ids=lambda f: f.__name__)
def test_both_tools_require_full_access(fn):
    """Including the READ. It returns real credentials, so a Read-only connection must not
    reach it — that is the whole difference from `read_file`, which masks them."""
    body = code(fn)
    assert "_full_access_required()" in body
    # Checked before anything is resolved or read.
    assert body.index("_full_access_required()") < body.index("_resolve_caller")


def test_the_access_rule_is_shared_not_copied():
    """It guards DNS changes and both settings tools. A second copy is how one of them
    quietly stops enforcing it."""
    rule = code(mcp._full_access_required)                     # noqa: SLF001
    assert "SCOPE_WRITE" in rule
    for fn in BOTH:
        assert "SCOPE_WRITE" not in code(fn), f"{fn.__name__} re-implements the scope check"


def test_a_view_only_teammate_is_refused():
    """Rule 7. Access to the server is not the same as permission to change it, and this
    file is the application's credentials."""
    assert "can_execute" in code(mcp._env_target)               # noqa: SLF001


# ── the content is never an argument ─────────────────────────────────────────

@pytest.mark.parametrize("fn", BOTH, ids=lambda f: f.__name__)
def test_the_file_moves_over_sftp_not_through_a_shell(fn):
    body = code(fn)
    assert "file_service" in body, "the file must move over SFTP"


def test_the_content_is_never_interpolated_into_a_command():
    """The specific accident: a `content` that reaches `connection_manager.execute` is a
    credential in `ps` and in the stored output of the run.

    Parsed rather than pattern-matched. A first version slid a character window past each
    call and flagged `len(data)` in the RETURN message — a byte count, not a leak. Reading
    the call's actual arguments is the only version that answers the real question.
    """
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(mcp.serverally_set_site_env)))
    names_in_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = ast.unparse(node.func)
        if not target.endswith("connection_manager.execute"):
            continue
        for arg in list(node.args) + [k.value for k in node.keywords]:
            names_in_calls += [n.id for n in ast.walk(arg) if isinstance(n, ast.Name)]

    assert names_in_calls, "no execute() call found — has the tool been rewritten?"
    for forbidden in ("content", "data"):
        assert forbidden not in names_in_calls, (
            f"the settings content reaches a shell command via `{forbidden}`: "
            f"{names_in_calls}")


def test_a_failed_save_does_not_leave_the_copy_behind():
    """The temporary file sits beside the real one and holds the same credentials."""
    body = code(mcp.serverally_set_site_env)
    assert "build_discard_command" in body
    assert body.index("if not ok") < body.index("build_discard_command")


# ── the protections a shell would not have given ─────────────────────────────

def test_the_save_uses_the_services_apply_command():
    """`build_apply_command` is what keeps the old file, restores it if the site stops
    serving, carries ownership across, and rebuilds the config cache. Writing the file some
    other way silently drops all four."""
    assert "build_apply_command" in code(mcp.serverally_set_site_env)


def test_the_config_cache_is_rebuilt_only_when_it_was_in_use():
    """Building a cache on a site that does not use one changes how it behaves, which is not
    what "save" means."""
    body = code(mcp.serverally_set_site_env)
    assert "rebuild_cache=bool(app.get(\"cache_config\"))" in body


def test_the_app_root_comes_from_the_probe_not_the_caller():
    """This path decides which file gets rewritten. A caller-supplied one would make the
    tool able to overwrite any file on the server."""
    body = code(mcp._env_target)                               # noqa: SLF001
    assert "laravel_service.read(" in body
    assert "root = app[\"path\"]" in code(mcp.serverally_set_site_env)


def test_the_exposure_warning_reaches_the_caller():
    """A .env reachable over the internet means treat every credential in it as leaked. The
    caller has to be told, not just the browser."""
    assert "exposure_warning" in code(mcp.serverally_get_site_env)


# ── refusals ─────────────────────────────────────────────────────────────────

def test_a_non_laravel_site_is_refused_and_pointed_somewhere_useful():
    """A refusal that only says no teaches the caller the product is broken."""
    body = code(mcp._env_target)                               # noqa: SLF001
    assert 'app_type' in body and "read_file" in body


def test_one_domain_on_two_servers_is_refused_rather_than_guessed():
    """Which server holds the credentials being asked for is not a guess to make."""
    body = code(mcp._resolve_site)                             # noqa: SLF001
    assert "len(hits) > 1" in body


def test_only_the_callers_own_sites_are_reachable():
    body = code(mcp._resolve_site)                             # noqa: SLF001
    assert "Site.user_id == user.id" in body


def test_the_audit_records_that_it_changed_and_not_what():
    """The point of the audit is the timeline. Recording the content would put every
    credential in the audit log."""
    body = code(mcp.serverally_set_site_env)
    assert '_audit(db, user, "site_env_saved"' in body
    audit_line = next(ln for ln in body.splitlines() if "site_env_saved" in ln)
    for leak in ("content", "data", "meta"):
        assert leak not in audit_line
