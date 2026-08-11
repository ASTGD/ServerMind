"""Putting a staging copy live.

Two paths, because a site either has a repository or it does not.

**The Git path (P3)** is the safe one, and it is mostly already built: deploy the commit
staging is serving to the live target. Everything that makes a deploy safe — build in a
folder nobody serves, atomic `mv -T` switch, shared paths preserved, a failed build never
reaching the live site, rollback afterwards — comes free, because it is the same deploy that
was proven on a real server on 28 July.

**The one genuinely new thing is the pin.** `deploy_service.build_plan` deploys a BRANCH.
Promotion has to deploy a COMMIT, or "put staging live" quietly means "deploy whatever is on
the branch right now" — which is not what the customer looked at and approved. Between them
opening the page and pressing the button, a teammate can push.

**And the plan's assumption about where to find that commit was wrong.**
`DeployTarget.current_release` sounds like a commit and holds a release-folder timestamp. So
the commit is read off the server, from the release staging is actually serving — which is
also the more honest source: it is what is *there*, not what we believe we deployed.
"""
from __future__ import annotations

import shlex

#: A commit as git prints it. Nothing else is ever accepted — this value reaches a command
#: line, and a "commit" containing a space is somebody's second command.
_SHA_CHARS = set("0123456789abcdefABCDEF")


class PromoteRefused(Exception):
    """Something the customer can read and act on."""


def valid_commit(sha: str) -> str:
    """A commit id, or a refusal. Validated rather than escaped."""
    text = (sha or "").strip()
    if not (7 <= len(text) <= 40) or not set(text) <= _SHA_CHARS:
        raise PromoteRefused(
            "That does not look like a commit id. It should be the 40-character hexadecimal "
            "id git shows, with nothing else in it.")
    return text.lower()


def read_commit_command(path: str) -> str:
    """Read the commit the live release directory is actually serving.

    Read-only, and deliberately reads through `current` — the symlink a visitor's request
    follows — rather than the newest release folder, because those differ the moment somebody
    has rolled back.
    """
    root = shlex.quote(path.rstrip("/"))
    return (f"set -e; cd {root}/current 2>/dev/null || cd {root}; "
            f"git rev-parse HEAD 2>/dev/null || echo NO-GIT")


def parse_commit(output: str) -> str | None:
    """The commit from that probe, or None when the directory is not a git checkout."""
    text = (output or "").strip().splitlines()
    if not text:
        return None
    last = text[-1].strip()
    if last == "NO-GIT" or not last:
        return None
    try:
        return valid_commit(last)
    except PromoteRefused:
        return None


def check_git_promote(*, staging_site, staging_target, live_site, live_target) -> None:
    """Everything decidable before a single command runs.

    Each refusal is a specific accident, not caution in general.
    """
    from app.services import staging_rules

    if not staging_rules.is_staging(staging_site):
        raise PromoteRefused(
            "This is not a staging copy, so there is nothing to promote from it.")

    if live_site is None or getattr(staging_site, "parent_site_id", None) is None:
        raise PromoteRefused(
            "This copy is not linked to a live site any more, so we cannot tell which site "
            "to put it on. That happens when the original was removed.")

    if staging_target is None:
        raise PromoteRefused(
            "This staging copy has no repository connected, so there is no commit to "
            "promote. Use the file copy instead.")

    if live_target is None:
        raise PromoteRefused(
            f"{live_site.domain} has no repository connected, so a commit cannot be deployed "
            f"to it. Connect the same repository to the live site first, or use the file "
            f"copy instead.")

    # Naming both is the point: "repositories do not match" leaves somebody comparing two
    # URLs by eye, which is how the wrong one gets fixed.
    if _norm(staging_target.repo) != _norm(live_target.repo):
        raise PromoteRefused(
            f"These deploy from different repositories — staging uses "
            f"{staging_target.repo} and {live_site.domain} uses {live_target.repo}. "
            f"Promoting would put code from one project onto the other.")


def _norm(repo: str) -> str:
    """Compare repositories by what they point at, not how they were typed.

    `git@github.com:acme/shop.git` and `https://github.com/acme/shop` are the same
    repository, and refusing that pair would block a perfectly ordinary setup.
    """
    text = (repo or "").strip().lower().rstrip("/")
    for prefix in ("https://", "http://", "ssh://", "git@"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    text = text.replace(":", "/", 1) if text.count(":") == 1 else text
    return text[:-4] if text.endswith(".git") else text


def pin_steps(rel_dir: str, commit: str) -> list[tuple[str, str]]:
    """The extra steps that turn a branch deploy into a commit deploy.

    Placed straight after the clone, so everything downstream — build, shared links, the
    atomic switch — is unchanged and still the code path proven on a real server.

    The clone is `--depth 1`, so the pinned commit is usually right there (promoting the tip
    is the common case) and occasionally is not (staging is a few commits behind). Deepening
    only when needed keeps the fast path fast without being wrong in the slow one.

    **The verification is the important line.** Checking out a commit that is not there fails
    loudly, but a checkout that silently lands somewhere else would put unreviewed code live
    while reporting success — so HEAD is compared to what was asked for, and the deploy stops
    before the switch if they differ.
    """
    d = shlex.quote(rel_dir)
    sha = shlex.quote(valid_commit(commit))
    return [
        ("Fetch the exact commit",
         f"set -e; cd {d}; "
         f"git cat-file -e {sha}^{{commit}} 2>/dev/null || git fetch --unshallow 2>&1 || "
         f"git fetch --depth 100 2>&1"),
        ("Check out what staging is running",
         f"set -e; cd {d}; git checkout --detach {sha} 2>&1; "
         f"GOT=$(git rev-parse HEAD); "
         f'case "$GOT" in {sha}*) ;; *) '
         f'echo "Asked for {commit} but the checkout is at $GOT — stopping before anything '
         f'goes live."; exit 1 ;; esac'),
    ]


# ── P4: the file-copy path ───────────────────────────────────────────────────
#
# For a site with no repository. Every rule below exists because of one specific way this
# destroys a customer's website, and each is written as a refusal rather than a warning —
# a warning is a thing people click through, and there is no undo for any of these.

#: Never copied from staging onto live. Each entry is a different disaster.
EXCLUDED = (
    # The config points at the STAGING database. Copying it makes the live site read and
    # write the copy — the single worst outcome this whole feature can produce.
    ".env",
    "wp-config.php",
    # Staging's uploads are a snapshot from the day it was made. Copying them over live
    # DELETES every file a customer has uploaded since.
    "wp-content/uploads",
    "storage/app/public",
    # Not a disaster, just pointless: megabytes of history and dependencies that the live
    # site either has already or rebuilds.
    ".git",
    "node_modules",
)

#: What a customer must be told BEFORE they press, not after they notice.
PLUGIN_CAVEAT = (
    "Plugin and theme FILES will be copied, but which plugins are switched on is stored in "
    "the database — and the database is deliberately not copied, because the live one holds "
    "your real orders and customers. So a plugin you installed on staging will arrive on the "
    "live site switched off, and you will need to enable it there."
)


def check_file_promote(*, staging_site, live_site, server, confirm_domain: str) -> None:
    """Everything decidable before a byte moves."""
    from app.services import staging_rules

    if not staging_rules.is_staging(staging_site):
        raise PromoteRefused("This is not a staging copy, so there is nothing to promote.")

    if live_site is None:
        raise PromoteRefused(
            "This copy is not linked to a live site any more, so we cannot tell which site "
            "to put it on.")

    if getattr(staging_site, "server_id", None) != getattr(live_site, "server_id", None):
        # A real limit, not caution: the cross-server transfer caps at 512 MB, and a site
        # that hits that cap would fail halfway with the live site already renamed.
        raise PromoteRefused(
            "The copy and the live site are on different servers. Promoting by file copy "
            "only works within one server at the moment.")

    if getattr(server, "panel_type", None):
        # Said here rather than letting somebody reach the confirm dialog first.
        raise PromoteRefused(
            f"{server.name} is managed by {server.panel_type}, which owns this site's "
            f"configuration and would undo the change on its own schedule. Promote by "
            f"deploying from your repository instead.")

    if not (staging_site.doc_root and live_site.doc_root):
        raise PromoteRefused(
            "We do not know where one of these sites keeps its files, so we cannot copy "
            "between them. Scan the server first.")

    # The same pattern as destroying a cloud instance: the loss is rarely "I meant not to",
    # it is "I did it to the wrong one". Compared against the domain the SERVER holds, so a
    # client cannot satisfy its own confirmation.
    if (confirm_domain or "").strip().lower() != live_site.domain.lower():
        raise PromoteRefused(
            f"Type {live_site.domain} exactly to confirm. This replaces the files of a live "
            f"website and cannot be undone from here.")


def build_file_promote_command(*, staging_root: str, live_root: str, stamp: str,
                               shared: list[str] | None = None) -> str:
    """Copy staging's files onto the live site, safely.

    The order is the safety, and it is the same shape the deploy uses: **build beside, then
    switch**. Nothing the visitor can reach changes until a complete copy is sitting ready.

    Two honest notes rather than a claim of atomicity. Replacing a DIRECTORY takes two
    renames — there is no portable atomic swap for directories the way `mv -T` gives one for
    a symlink — so there is a window of microseconds between them; and because the old
    directory is still there under a name we know, a failure in the second rename is put
    back rather than left broken.

    The backup happens first and its failure stops everything. A backup that did not happen
    is discovered only at the moment it is needed.

    **`--checksum`, and it is not a preference.** rsync's default quick check compares size
    and modification time, so a file changed on staging within the same second as the live
    copy, to the same length, is treated as identical and **silently not copied** — found by
    running this against a real tree, where a one-line edit produced exactly that. A
    promotion where one file quietly did not arrive is the worst kind of failure this feature
    can have: everything reports success and the site is subtly wrong. Comparing contents is
    slower and correct, and a promotion is a rare, deliberate act where that is the right
    trade.
    """
    q = shlex.quote
    src = q(staging_root.rstrip("/") + "/")     # trailing slash: copy the CONTENTS
    live = q(live_root.rstrip("/"))
    staged = q(f"{live_root.rstrip('/')}.promote-{stamp}")
    kept = q(f"{live_root.rstrip('/')}.replaced-{stamp}")

    excludes = " ".join(f"--exclude={q(p)}" for p in EXCLUDED)
    for extra in (shared or []):
        excludes += f" --exclude={q(extra)}"

    return f"""
set -e
BACKUP="$HOME/serverally-backups/promote-{stamp}.tar.gz"
mkdir -p "$(dirname "$BACKUP")"

# 1. The live site, saved, before anything else happens. `set -e` makes a failure here stop
#    the whole thing — which is the point: there is no undo for what follows.
tar -czf "$BACKUP" -C "$(dirname {live})" "$(basename {live})"
[ -s "$BACKUP" ] || {{ echo ">>> ERROR: the backup came out empty, so nothing was changed"; exit 1; }}
echo ">>> Backed up to $BACKUP"

# 2. Build the new version BESIDE the live one. Nothing served changes yet.
rm -rf {staged}
cp -a {live} {staged}
rsync -a --checksum --delete {excludes} {src} {staged}/

# 3. Switch. Two renames, and the old directory is kept under a name we know so the second
#    one failing can be undone rather than leaving the site missing.
mv {live} {kept}
mv {staged} {live} || {{ mv {kept} {live}; echo ">>> ERROR: the switch failed and the site was put back"; exit 1; }}

# 4. Ownership follows the live site's own directory, not staging's — a file owned by the
#    wrong account is a site that breaks days later with an error pointing nowhere near here.
OWNER=$(stat -c '%U:%G' {kept} 2>/dev/null || stat -f '%Su:%Sg' {kept})
chown -R "$OWNER" {live} 2>/dev/null || true

echo ">>> OK: promoted. The previous files are in {kept}"
"""
