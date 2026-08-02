"""The scheduled jobs one site needs.

A crontab belongs to the SERVER, not to a site, so everything here is a scoped adapter over
``cron_service`` — the same validation, the same concurrent-edit guard, the same install
path. What it adds is the two things a site owner cannot be expected to know: which job
their application needs, and which user it has to run as.

That second one is not cosmetic. Laravel's scheduler writes into ``storage/`` and
``bootstrap/cache`` every time it runs; run it as root and those files become root-owned,
the web server can no longer write them, and the site breaks days later with an error that
points nowhere near cron. So a job added here runs as the owner of the site's files, the
same rule the installers already follow.
"""
from __future__ import annotations

import shlex

#: A minute is the interval both of these are designed around: Laravel decides for itself
#: what is actually due, and WordPress queues work that a visitor would otherwise pay for.
_EVERY_MINUTE = "* * * * *"


def app_root(app_type: str, doc_root: str) -> str:
    """The folder the application lives in, which is not always the one it serves from.

    Laravel serves ``public/`` and keeps ``artisan`` one level above it, so a job that runs
    from the served folder cannot find the thing it is meant to run.
    """
    path = (doc_root or "").rstrip("/")
    if app_type == "laravel" and path.endswith("/public"):
        return path[: -len("/public")]
    return path


def suggested_job(app_type: str, doc_root: str) -> dict | None:
    """The job this application needs, or nothing if it does not need one.

    Offered rather than assumed: a site with no suggestion gets the custom form instead of
    a made-up job, because inventing work for someone's server is worse than asking.
    """
    root = app_root(app_type, doc_root)
    if not root:
        return None
    quoted = shlex.quote(root)

    if app_type == "laravel":
        return {
            "schedule": _EVERY_MINUTE,
            "command": f"cd {quoted} && php artisan schedule:run >> /dev/null 2>&1",
            "title": "Run Laravel's scheduler",
            "why": ("Laravel does its scheduled work — sending queued email, clearing old "
                    "records, whatever this app schedules — only when this runs. Without "
                    "it none of that ever happens, silently."),
        }
    if app_type == "wordpress":
        # Deliberately `php wp-cron.php` rather than wp-cli: a site we merely discovered
        # may not have wp-cli installed, and a suggested job that fails on half of the
        # sites it is offered for is worse than no suggestion.
        return {
            "schedule": _EVERY_MINUTE,
            "command": f"cd {quoted} && php wp-cron.php > /dev/null 2>&1",
            "title": "Run WordPress's scheduled tasks on a timer",
            "why": ("By default WordPress runs this during someone's visit, so it is late "
                    "on a quiet site and slow on a busy one. On a timer it is neither."),
        }
    return None


#: What a job has to mention for the application's scheduled work to be running at all.
#: Matched on this rather than on the whole command, because somebody who wrote their own
#: version — a different redirect, a `flock` wrapper, a full path to php — has already
#: solved the problem, and offering to add ours again would be nagging about a job that
#: is right there in the list above.
#: More than one per application, because there is more than one right answer. WordPress's
#: work runs either by calling wp-cron.php or through wp-cli, and a site doing it the other
#: way has already solved the problem.
_ALREADY_DOING_IT = {
    "laravel": ("artisan schedule:run",),
    "wordpress": ("wp-cron.php", "wp cron event"),
}


def already_scheduled(app_type: str, jobs: list[dict]) -> bool:
    markers = _ALREADY_DOING_IT.get(app_type)
    if not markers:
        return False
    return any(m in (job.get("command") or "") for job in jobs for m in markers)


def build_owner_command(doc_root: str) -> str:
    """Who owns this site's files. One cheap read, so the job runs as the right user."""
    return f"stat -c %U {shlex.quote(doc_root)} 2>/dev/null || true"


def parse_owner(stdout: str) -> str | None:
    """The owner, or nothing — never a guess.

    Returning a default here would be the bug this exists to prevent: falling back to root
    is exactly the outcome that leaves root-owned files inside a site.
    """
    name = (stdout or "").strip().splitlines()
    if not name:
        return None
    first = name[0].strip()
    if not first or " " in first or len(first) > 32:
        return None
    return first
