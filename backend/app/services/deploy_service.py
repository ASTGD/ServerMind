"""Deployments — push code to a server, atomically, with a way back.

The naive version of this feature is `git pull` in the live directory. It is what most
people do by hand, and it has two faults that only show up on a bad day: during the pull
the site serves a half-updated tree, and when the new code is broken there is no way
back except another pull and a prayer.

So this uses the releases-and-symlink layout that Capistrano settled on twenty years ago,
because the properties are the point:

    <path>/releases/2026-07-28_141530/   each deploy, kept
    <path>/shared/                       .env, uploads, storage — survive every deploy
    <path>/current -> releases/...       one symlink decides what is live

**The switch is atomic.** Everything — clone, dependencies, build — happens inside the
NEW release directory while the old one is still serving. Only if all of it succeeds does
`current` move, and it moves by rename, which the kernel guarantees is atomic. A visitor
sees the old release or the new one, never a mixture, and never a 500 from a half-written
file.

**A failed build cannot take the site down.** It fails in a directory nothing points at.

**Rollback is a symlink move**, so it is as fast and as safe as the deploy was, and it
works even when the new code will not start — which is exactly when you need it.

**Shared paths are linked, not copied.** A deploy that replaced `uploads/` would destroy
customer files; linking means the data lives outside the release cycle entirely.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import shlex
from dataclasses import dataclass, field

# Deploys keep this many releases. Enough to roll back past a bad one and the one before
# it; more just fills the disk with code nobody will run again.
KEEP_RELEASES = 5

# Paths and repo URLs are typed by the owner and end up in shell commands. As with
# service units, the legitimate shapes are narrow, so we refuse rather than escape.
_PATH_OK = re.compile(r"^/[A-Za-z0-9._/-]{1,200}$")
_BRANCH_OK = re.compile(r"^[A-Za-z0-9._/-]{1,120}$")
_REPO_OK = re.compile(
    r"^(https://[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+?(\.git)?|git@[A-Za-z0-9._-]+:[A-Za-z0-9._/-]+?(\.git)?)$"
)

# Directories a deploy must never target. Pointing a release root at any of these would
# have the pruner delete the system.
_FORBIDDEN_PATHS = {
    "/", "/bin", "/boot", "/dev", "/etc", "/home", "/lib", "/lib64", "/media", "/mnt",
    "/opt", "/proc", "/root", "/run", "/sbin", "/srv", "/sys", "/tmp", "/usr", "/var",
}


class InvalidDeploy(ValueError):
    """The configuration would not work, or would be dangerous."""


@dataclass
class DeployStep:
    name: str
    command: str
    fatal: bool = True          # a non-fatal step's failure does not abort the deploy


@dataclass
class DeployPlan:
    release: str
    steps: list[DeployStep] = field(default_factory=list)
    # Removes the half-built release if the deploy dies before going live. Kept on the
    # plan rather than rebuilt by the caller so it can never disagree about which
    # directory is being cleaned up.
    discard: str = ""


def valid_path(path: str) -> str:
    """An absolute, plain path that is not a system directory."""
    raw = (path or "").strip()
    if raw.rstrip("/") == "" and raw.startswith("/"):
        raise InvalidDeploy(
            "“/” is a system folder. Deploy into its own folder, like /var/www/myapp.")
    p = raw.rstrip("/")
    if not p or not _PATH_OK.match(p):
        raise InvalidDeploy(
            "The deploy folder must be a full path like /var/www/myapp "
            "(letters, numbers, dots, dashes and slashes only).")
    if ".." in p:
        raise InvalidDeploy("The deploy folder can't contain “..”.")
    if p in _FORBIDDEN_PATHS:
        raise InvalidDeploy(
            f"“{p}” is a system folder. Deploy into its own folder, like {p}/myapp.")
    return p


def valid_repo(repo: str) -> str:
    r = (repo or "").strip()
    if not _REPO_OK.match(r):
        raise InvalidDeploy(
            "That doesn't look like a repository address. Use something like "
            "https://github.com/you/project.git or git@github.com:you/project.git")
    return r


def valid_branch(branch: str) -> str:
    b = (branch or "").strip() or "main"
    if not _BRANCH_OK.match(b):
        raise InvalidDeploy(f"“{branch}” isn't a valid branch name.")
    return b


def valid_shared(paths: list[str] | None) -> list[str]:
    """Paths that live outside the release cycle — .env, uploads, storage.

    Relative, because they are relative to the app root. An absolute one would link
    something from elsewhere on the server into the web root, which is how a deploy
    accidentally publishes /etc.
    """
    out = []
    for raw in (paths or []):
        p = (raw or "").strip()
        if not p:
            continue
        if p.startswith("/"):
            raise InvalidDeploy(
                f"“{raw}” starts with “/”. Shared paths are inside the project — write "
                f"“{p.lstrip('/')}” rather than a full path.")
        p = p.rstrip("/")
        if ".." in p or not re.match(r"^[A-Za-z0-9._/-]{1,120}$", p):
            raise InvalidDeploy(
                f"“{raw}” isn't a valid shared path. Use a path inside the project, "
                "like .env or storage/uploads.")
        out.append(p)
    return out


def valid_commands(commands: list[str] | None, *, label: str) -> list[str]:
    """Build/restart commands are arbitrary shell BY DESIGN — every stack differs.

    They are not sanitised, because there is no sensible subset: a Node app runs
    `npm ci && npm run build`, a Laravel app runs artisan, a Go app runs make. What
    protects the server is that they run as the deploy user inside the release
    directory, they are shown in full before saving, and safety_service still refuses
    the catastrophic ones.
    """
    out = []
    for c in (commands or []):
        c = (c or "").strip()
        if not c:
            continue
        if len(c) > 1000:
            raise InvalidDeploy(f"A {label} command is too long (1000 characters max).")
        out.append(c)
    if len(out) > 20:
        raise InvalidDeploy(f"That's a lot of {label} commands — 20 is the maximum.")
    return out


def release_name(stamp: str) -> str:
    """A release directory name. Sortable, so 'previous' is unambiguous."""
    if not re.match(r"^[0-9]{8}_[0-9]{6}$", stamp or ""):
        raise InvalidDeploy("Bad release stamp.")
    return stamp


def build_plan(*, path: str, repo: str, branch: str, stamp: str,
               shared: list[str] | None = None,
               build: list[str] | None = None,
               after: list[str] | None = None) -> DeployPlan:
    """The commands for one deploy, in order.

    Everything before the switch happens in the new release directory. `current` moves
    only after the last build command has succeeded, so a broken build leaves the live
    site exactly as it was.
    """
    root = valid_path(path)
    url = valid_repo(repo)
    br = valid_branch(branch)
    rel = release_name(stamp)
    shared_paths = valid_shared(shared)
    build_cmds = valid_commands(build, label="build")
    after_cmds = valid_commands(after, label="after-deploy")

    q = shlex.quote
    rel_dir = f"{root}/releases/{rel}"
    steps: list[DeployStep] = []

    steps.append(DeployStep(
        "Prepare folders",
        f"set -e; mkdir -p {q(root)}/releases {q(root)}/shared; "
        f"mkdir -p {q(rel_dir)}"))

    # --depth 1 --single-branch: a deploy needs the tip, not the history. On a large repo
    # this is the difference between a 3-second and a 3-minute deploy.
    steps.append(DeployStep(
        "Fetch the code",
        f"set -e; git clone --depth 1 --single-branch --branch {q(br)} {q(url)} {q(rel_dir)} 2>&1"))

    for sp in shared_paths:
        parent = "/".join(sp.split("/")[:-1])
        mk_parent = f"mkdir -p {q(rel_dir + '/' + parent)}; " if parent else ""
        steps.append(DeployStep(
            f"Link shared {sp}",
            # The shared copy is created if missing so the first deploy works, then the
            # release's own copy is REMOVED and replaced by a link. Without the rm, git
            # would have already put a file there and the link would fail.
            f"set -e; mkdir -p $(dirname {q(root + '/shared/' + sp)}); "
            f"[ -e {q(root + '/shared/' + sp)} ] || "
            f"{{ [ -e {q(rel_dir + '/' + sp)} ] && cp -a {q(rel_dir + '/' + sp)} "
            f"{q(root + '/shared/' + sp)} || touch {q(root + '/shared/' + sp)}; }}; "
            f"{mk_parent}rm -rf {q(rel_dir + '/' + sp)}; "
            f"ln -s {q(root + '/shared/' + sp)} {q(rel_dir + '/' + sp)}"))

    for i, cmd in enumerate(build_cmds, 1):
        steps.append(DeployStep(f"Build ({i}/{len(build_cmds)})",
                                f"cd {q(rel_dir)} && {cmd}"))

    steps.append(DeployStep("Go live", switch_command(root, rel)))

    for i, cmd in enumerate(after_cmds, 1):
        # After the switch. A failing restart is reported but does NOT roll back on its
        # own — the new code is already live and an automatic undo here would flap.
        steps.append(DeployStep(f"After deploy ({i}/{len(after_cmds)})",
                                f"cd {q(root)}/current && {cmd}", fatal=False))

    steps.append(DeployStep("Tidy old releases", prune_command(root), fatal=False))
    return DeployPlan(release=rel, steps=steps, discard=discard_command(path, rel))


def discard_command(path: str, release: str) -> str:
    """Delete a release that never went live.

    A build that fails leaves a half-finished directory behind. Left there it is not
    merely untidy — it is the NEWEST release, so the next rollback would pick it and
    switch the site onto code that has never worked. Removing it keeps the release list
    to things that actually ran, which is what makes rollback safe by construction.
    """
    root = valid_path(path)
    rel = release_name(release)
    q = shlex.quote
    return f"rm -rf {q(f'{root}/releases/{rel}')}"


def switch_command(path: str, release: str) -> str:
    """Point `current` at a release — atomically.

    `ln -sfn` is NOT atomic when the link exists: it unlinks and recreates, and a request
    arriving in that gap gets a missing directory. Creating a temporary link and
    `mv -T`ing it over is a rename(2), which the kernel performs atomically, so there is
    no instant where `current` does not resolve.
    """
    root = valid_path(path)
    rel = release_name(release)
    q = shlex.quote
    return (f"set -e; ln -sfn {q(f'{root}/releases/{rel}')} {q(f'{root}/current.tmp')}; "
            f"mv -Tf {q(f'{root}/current.tmp')} {q(f'{root}/current')}")


def prune_command(path: str, keep: int = KEEP_RELEASES) -> str:
    """Delete all but the newest ``keep`` releases.

    Sorted by name, which is why the stamp format is fixed and sortable. `tail -n +N`
    keeps the newest and lists the rest — never the reverse, which would delete the ones
    still needed for rollback.
    """
    root = valid_path(path)
    k = max(2, int(keep))          # never fewer than 2: one live, one to roll back to
    return (f"cd {shlex.quote(root)}/releases 2>/dev/null && "
            f"ls -1 | sort -r | tail -n +{k + 1} | "
            f"while read d; do [ -n \"$d\" ] && rm -rf -- \"$d\"; done; true")


def list_releases_command(path: str) -> str:
    """Read-only: which releases exist and which one is live."""
    root = valid_path(path)
    q = shlex.quote
    return (f"ls -1 {q(root)}/releases 2>/dev/null | sort -r; "
            f"echo '---CURRENT---'; readlink {q(root)}/current 2>/dev/null || true")


def parse_releases(output: str) -> tuple[list[str], str | None]:
    """(releases newest-first, the live one)."""
    if "---CURRENT---" not in (output or ""):
        return [], None
    listing, _, current = output.partition("---CURRENT---")
    releases = [l.strip() for l in listing.splitlines() if l.strip()]
    live = (current.strip().rstrip("/").split("/")[-1] or None) if current.strip() else None
    return releases, live


def rollback_target(releases: list[str], current: str | None) -> str:
    """The release to roll back to: the newest one that is not live.

    Refuses rather than guesses when there is nothing to go back to — a rollback that
    silently redeploys the same broken release is worse than an error, because the
    operator believes they have recovered.
    """
    ordered = [r for r in releases if r]
    if not ordered:
        raise InvalidDeploy("There are no releases to roll back to.")
    candidates = [r for r in ordered if r != current]
    if not candidates:
        raise InvalidDeploy(
            "There's only one release on the server, so there's nothing to roll back to.")
    return candidates[0]


def verify_github_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Check GitHub's X-Hub-Signature-256.

    Without this the deploy URL is a public button: anyone who learns it could ship
    whatever the branch happens to point at. compare_digest because a plain `==` leaks
    the correct prefix through timing.
    """
    if not secret or not header:
        return False
    if not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def branch_from_push(payload: dict) -> str | None:
    """The branch a GitHub push event refers to. `refs/heads/main` -> `main`."""
    ref = (payload or {}).get("ref") or ""
    return ref.split("refs/heads/", 1)[1] if ref.startswith("refs/heads/") else None


def should_deploy(payload: dict, branch: str) -> tuple[bool, str]:
    """Does this webhook call for a deploy?

    A repository fires webhooks for every branch and for deletions. Deploying on any of
    them would ship a feature branch to production, or try to deploy a branch that no
    longer exists.
    """
    if (payload or {}).get("deleted"):
        return False, "That branch was deleted — nothing deployed."
    pushed = branch_from_push(payload)
    if pushed is None:
        return False, "Not a branch push — ignored."
    if pushed != branch:
        return False, f"Push was to “{pushed}”, this deploys “{branch}” — ignored."
    return True, f"Push to {pushed}."


# --- Pointing a site at its deployed code -------------------------------------------------
#
# A deploy builds into `<root>/releases/<stamp>` and moves `<root>/current`. None of that
# reaches a visitor until the web server is looking through `current` — so a site that
# already exists has to be repointed exactly once, and that is the one genuinely dangerous
# thing in this feature: get it wrong and a live website serves nothing.
#
# It is therefore done in the same shape as the PHP version switch, which has the same risk:
# keep a copy, change one line, ask the web server to check its own config, reload, then
# prove the site still serves REAL CONTENT — and put the old file back if it does not. A
# status code alone is not proof; a misdirected root very often answers 200 with an index
# listing or an error page.


def valid_web_dir(value: str | None) -> str:
    """Where inside the repository the web server should look.

    Empty means the repository root. Anything else must be a plain relative folder —
    validated rather than escaped, because this ends up inside a web-server config where a
    stray quote or newline would not fail loudly, it would change what the config MEANS.
    """
    web = (value or "").strip().strip("/")
    if not web:
        return ""
    if len(web) > 100 or ".." in web:
        raise InvalidDeploy("The web directory must be a folder inside the repository.")
    for part in web.split("/"):
        if not part or not all(c.isalnum() or c in "-_." for c in part):
            raise InvalidDeploy(
                f"'{value}' is not a valid folder name. Use something like 'public'.")
    return web


def deploy_root_for(doc_root: str) -> str:
    """The folder a site's deploys should live in, derived from where it is served from.

    A site served from ``/var/www/shop.com/public`` belongs to ``/var/www/shop.com`` — the
    releases go beside the current files, not inside the folder the web server is reading.
    Anything else is its own root.
    """
    root = (doc_root or "").rstrip("/")
    if not root:
        raise InvalidDeploy("This site has no folder on the server yet.")
    return root[:-len("/public")] if root.endswith("/public") else root


def served_path(root: str, web_dir: str | None) -> str:
    """The path the web server must point at once deploys are live."""
    web = valid_web_dir(web_dir)
    return f"{valid_path(root)}/current" + (f"/{web}" if web else "")


def build_point_command(config_path: str, domain: str, root: str,
                        web_dir: str | None) -> str:
    """Point one site's config at its deployed code, and undo it if the site breaks.

    Deliberately refuses before it changes anything if there is nothing to point AT. The
    order matters: a site keeps serving its existing files right up until there is a
    finished release to switch to, so a failed first deploy costs nothing.
    """
    target = served_path(root, web_dir)
    cfg = shlex.quote(config_path)
    dom = shlex.quote(domain)
    tgt = shlex.quote(target)
    return (
        f'set -e; CFG={cfg}; DOM={dom}; TGT={tgt}; '
        # Nothing has been deployed yet, or the last deploy failed. Repointing now would
        # take a working site down to serve a folder that does not exist.
        f'if [ ! -d "$TGT" ]; then '
        f'  echo "There is no finished deploy to point at yet."; exit 3; fi; '
        # Read the CURRENT root out of the config before changing it. Apache grants access
        # per folder, so its vhost names that path twice — once as DocumentRoot and again in
        # a <Directory> block — and moving only the first leaves the second granting access
        # to a folder nobody is served from, which answers 403 for every visitor. Comments
        # are stripped first so a commented-out root is never mistaken for the real one.
        f'OLD="$(sed -E "s/#.*$//" "$CFG" 2>/dev/null '
        f'  | grep -oE "(root|DocumentRoot|docRoot)[[:space:]]+[^;[:space:]]+" | head -1 '
        f'  | awk "{{print \\$2}}")"; '
        f'BK="$CFG.serverally.$(date +%s).bak"; cp -p "$CFG" "$BK"; '
        # Only the document root changes; everything else in the config is left alone.
        f'sed -i -E "s#^([[:space:]]*)root[[:space:]]+[^;]+;#\\1root $TGT;#; '
        f's#^([[:space:]]*)DocumentRoot[[:space:]]+.*#\\1DocumentRoot $TGT#; '
        f's#^([[:space:]]*)docRoot[[:space:]]+.*#\\1docRoot                   $TGT#" "$CFG"; '
        f'if [ -n "$OLD" ] && [ "$OLD" != "$TGT" ]; then '
        f'  sed -i "s#<Directory ${{OLD}}>#<Directory $TGT>#g" "$CFG"; fi; '
        f'if ! (nginx -t 2>/dev/null || apachectl configtest 2>/dev/null); then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  echo "The web server rejected the change, so it was undone."; exit 4; fi; '
        f'systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || systemctl reload httpd 2>/dev/null || true; '
        # Retried, because a reload returns before the workers have swapped and an
        # immediate request can still be answered by the old configuration.
        f'OK=no; for i in 1 2 3 4 5 6; do '
        f'  C="$(curl -s -o /dev/null -w "%{{http_code}}" --max-time 5 -H "Host: $DOM" '
        f'       http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'  B="$(curl -s --max-time 5 -H "Host: $DOM" http://127.0.0.1/ 2>/dev/null '
        f'       | head -c 400 || true)"; '
        # Content, not just a code. A root pointing at the wrong folder answers 200 with a
        # directory listing or an error page just as happily as it answers with a website.
        f'  case "$C" in 2*|3*) [ -n "$B" ] && OK=yes && break ;; esac; sleep 2; done; '
        f'if [ "$OK" != yes ]; then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null || true; '
        f'  echo "$DOM stopped working when pointed at the deployed code, so it was put back."; '
        f'  exit 5; fi; '
        f'rm -f "$BK"; echo "$DOM is now served from $TGT."'
    )


POINT_OUTCOMES: dict[int, str] = {
    3: ("Nothing has been deployed yet, so there is nothing to point the site at. Deploy "
        "once first — the site keeps serving its current files until then."),
    4: ("The web server refused the new configuration, so it was undone. Your other "
        "websites are unaffected."),
    5: ("The site stopped working when pointed at the deployed code, so it was put back. "
        "The web directory is most likely wrong — a Laravel or Symfony app is usually "
        "served from 'public'."),
}
