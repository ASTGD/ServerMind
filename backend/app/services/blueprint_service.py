"""Blueprints — ready-made long jobs, defined once and run step by step.

A blueprint is a FIXED list of steps ServerAlly already knows how to do: run an installer,
create a site, make a database, turn on HTTPS, add a monitor, run a scan. **A step contains
no AI.** That one decision is what makes our cost zero on the MCP path, the run repeatable,
the record resumable, and the screen truthful — it shows what ran, not what a model said it
would do. The customer's AI (or the app) is the front desk: it matches a blueprint,
collects the inputs, starts it and watches.

Deliberately NOT called a mission — that already means our own AI loop, and two things with
one name is the drift this project keeps getting caught by.

This module is the pure half: the catalogue, the input rules, and the refusals. The engine
that executes steps lives in ``app/workers/blueprint_runner.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class BlueprintError(Exception):
    """Refused before anything ran — the message is written for the customer."""


@dataclass(frozen=True)
class Input:
    name: str
    label: str                 # plain language, shown when we ask for it
    required: bool = True
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class BpStep:
    key: str                   # the action the runner executes
    label: str                 # plain language, shown on the checklist
    # A step that may fail without ending the run. Watching and backups are nice to have;
    # a web server is not — the rule the server setup already follows.
    optional: bool = False


@dataclass(frozen=True)
class Blueprint:
    key: str
    title: str
    description: str           # "I have … and I want …", in the customer's words
    inputs: tuple[Input, ...] = ()
    steps: tuple[BpStep, ...] = ()
    leaves_for_you: tuple[str, ...] = ()
    does_not_do: tuple[str, ...] = ()
    # A REPORT blueprint: a failed check stays red but the run continues — a pre-launch
    # report that stops at the first problem hides the rest. Build-type blueprints keep
    # the stop, because building past a failure leaves half a job.
    report: bool = False


def _site_type_choices() -> tuple[str, ...]:
    # The same catalogue the sites screen and the MCP tool draw from — one source, so a
    # type can never be offered here that site creation then refuses.
    from app.services.site_service import CHOOSABLE_TYPES
    return tuple(sorted(CHOOSABLE_TYPES))


CATALOGUE: dict[str, Blueprint] = {}


def _register(bp: Blueprint) -> Blueprint:
    CATALOGUE[bp.key] = bp
    return bp


SET_UP_WEBSITE = _register(Blueprint(
    key="set-up-website",
    title="Set up a website on a server",
    description=("You have a server — fresh or already prepared — and you want a website "
                 "on it: created, installed, secured, watched and backed up."),
    inputs=(
        # The human owns the domain; we NEVER invent one. Everything derivable (database
        # name, folder, credentials) is worked out by the installers — the decision of
        # 2026-08-21: ask for what is theirs, derive what is ours.
        Input("domain", "The website's domain name, like shop.example.com"),
        Input("site_type", "What to put on it", choices=("wordpress", "laravel", "php", "static")),
    ),
    steps=(
        BpStep("look",    "Look at the server"),
        BpStep("prepare", "Prepare the server"),
        BpStep("create",  "Create the website and install it"),
        BpStep("confirm", "Check it really answers"),
        BpStep("https",   "Turn on HTTPS"),
        BpStep("watch",   "Start watching it", optional=True),
        BpStep("backup",  "Start daily backups", optional=True),
        BpStep("safety",  "Check it is safe", optional=True),
    ),
    leaves_for_you=(
        "Point the domain at the server (an A record). HTTPS waits for that.",
        "The application's admin password is saved on the server, root-only — it is never shown in chat.",
    ),
    does_not_do=(
        "Buy a domain or change DNS records.",
        "Send email.",
    ),
))


def get(key: str) -> Blueprint:
    bp = CATALOGUE.get((key or "").strip())
    if bp is None:
        known = ", ".join(sorted(CATALOGUE))
        raise BlueprintError(f"There is no blueprint called '{key}'. Available: {known}.")
    return bp


def missing_inputs(bp: Blueprint, inputs: dict) -> list[Input]:
    """Which required inputs were not supplied — so the caller can ASK the human.

    Asking is the decided behaviour for anything the human owns. A missing input is never
    guessed, because a guessed domain is a website nobody wanted.
    """
    supplied = {k for k, v in (inputs or {}).items() if str(v or "").strip()}
    return [i for i in bp.inputs if i.required and i.name not in supplied]


def check_inputs(bp: Blueprint, inputs: dict) -> dict:
    """Validate and normalise. Raises ``BlueprintError`` naming exactly what to ask for."""
    missing = missing_inputs(bp, inputs)
    if missing:
        asks = "; ".join(f"{i.name} — {i.label}" for i in missing)
        raise BlueprintError(f"Before this can start, please provide: {asks}")
    clean: dict = {}
    for spec in bp.inputs:
        value = str((inputs or {}).get(spec.name, "") or "").strip()
        if not value:
            continue
        choices = spec.choices or (
            _site_type_choices() if spec.name == "site_type" else ())
        if choices and value not in choices:
            raise BlueprintError(
                f"'{value}' is not a valid {spec.name}. Choose one of: {', '.join(choices)}.")
        clean[spec.name] = value
    return clean


def check_server(bp: Blueprint, server) -> None:
    """Refuse BEFORE starting, never halfway. Stopping before a stack is installed is
    clean; stopping in the middle leaves a machine nobody can reason about."""
    if getattr(server, "connection_type", "") != "ssh":
        raise BlueprintError(
            f"'{bp.title}' needs a Linux server reached over SSH "
            f"(this one is '{getattr(server, 'connection_type', 'unknown')}').")
    if (getattr(server, "panel_type", "") or "").strip():
        raise BlueprintError(
            f"{getattr(server, 'name', 'This server')} is managed by its control panel "
            f"({server.panel_type}), which owns its own websites — this blueprint would "
            "write configuration behind the panel's back, and the panel would revert it.")


def build_steps(bp: Blueprint, inputs: dict) -> list[dict]:
    """The step rows written to the run record at start — the whole plan, visible before
    anything runs."""
    rows = []
    for s in bp.steps:
        label = s.label
        if s.key == "create" and inputs.get("site_type"):
            pretty = {"wordpress": "WordPress", "laravel": "Laravel",
                      "php": "a PHP site", "static": "a static site"}
            label = f"Create the website and install {pretty.get(inputs['site_type'], inputs['site_type'])}"
        row = {"key": s.key, "label": label, "state": "pending", "note": "",
               "optional": s.optional}
        if bp.report:
            row["report"] = True
        rows.append(row)
    return rows


def describe(bp: Blueprint) -> dict:
    """What a caller (the app, or a customer's AI reading a tool result) needs to offer it."""
    return {
        "key": bp.key,
        "title": bp.title,
        "description": bp.description,
        "needs": [{"name": i.name, "label": i.label, "required": i.required,
                   "choices": list(i.choices or (
                       _site_type_choices() if i.name == "site_type" else ()))}
                  for i in bp.inputs],
        "steps": [s.label for s in bp.steps],
        "leaves_for_you": list(bp.leaves_for_you),
        "does_not_do": list(bp.does_not_do),
    }


TAKE_OVER_SERVER = _register(Blueprint(
    key="take-over-server",
    title="Take over a server somebody else built",
    description=("A server was handed to you — a client's, or one built before your time — "
                 "and nobody knows what is on it, who can log in, or whether it is safe. "
                 "This finds out, starts watching it, and writes it down. Almost entirely "
                 "read-only."),
    inputs=(),                       # nothing beyond access — that is the point
    steps=(
        BpStep("look",       "Identify the machine"),
        BpStep("find_sites", "Find the websites"),
        BpStep("who_access", "Check who can get in"),
        BpStep("safety",     "Check it is safe"),
        BpStep("certs",      "Check the certificates", optional=True),
        BpStep("watch_all",  "Start watching its sites", optional=True),
    ),
    leaves_for_you=(
        "Removing access you do not recognise. We list every key and firewall opening; "
        "we never remove one on our own — that is how you lose a server.",
    ),
    does_not_do=(
        "Change, remove or fix anything. This looks and records; fixing is a decision.",
    ),
))


READY_TO_GO_LIVE = _register(Blueprint(
    key="site-ready-to-go-live",
    title="Get a site ready to go live",
    description=("The pre-launch check: does the domain point here, is HTTPS on, does the "
                 "page actually work, is it watched and backed up. Read-only — it reports, "
                 "and each failure names its fix."),
    inputs=(
        Input("domain", "The site's domain name"),
    ),
    steps=(
        BpStep("dns_check",   "Does the domain point here?"),
        BpStep("https_check", "Is HTTPS on and healthy?"),
        BpStep("page_check",  "Does the page actually work?"),
        BpStep("watch_check", "Is anything watching it?"),
        BpStep("backup_check", "Are backups running?"),
        BpStep("safety",      "Is the server safe?", optional=True),
    ),
    leaves_for_you=(
        "Any fix the report names — each one says where to do it.",
    ),
    does_not_do=("Change anything. A pre-launch check that edits the site is not a check.",),
    report=True,
))


MOVE_WEBSITE = _register(Blueprint(
    key="move-website",
    title="Move a website to another server",
    description=("The most feared job in hosting: the site's files AND its database move "
                 "to another of your servers, it is proven working there BEFORE any DNS "
                 "changes, and the old site keeps running until you switch the domain "
                 "over. Nothing is deleted, and DNS is never touched."),
    inputs=(
        Input("domain", "The website to move (its domain name)"),
        Input("to_server", "The server to move it to (its name in ServerAlly)"),
    ),
    steps=(
        BpStep("fit",        "Check the destination fits"),
        BpStep("copy_files", "Copy the website's files"),
        BpStep("move_db",    "Move the database"),
        BpStep("prove",      "Prove it works on the new server"),
        BpStep("handover",   "Hand over the DNS switch"),
    ),
    leaves_for_you=(
        "The DNS switch itself: change the domain's A record to the new server when you "
        "are ready. Until then the old site keeps serving.",
        "Removing the old site afterwards — from the old server's Sites page, once you "
        "have seen the new one take traffic.",
    ),
    does_not_do=(
        "Delete the old site. Ever.",
        "Change DNS records.",
        "Move email, cron jobs, or HTTPS (get a new certificate on the new server after "
        "the DNS switch).",
    ),
))
