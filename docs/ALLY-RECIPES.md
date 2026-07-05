# Ally Recipes — pre-loaded workflow missions (planning doc, 2026-07-05)

> Not built yet. A **Recipe** is a curated, one-click-launchable Mission: pick it from
> a gallery, fill in a few fields, and Ally runs the same staged runbook
> `cyberpanel-host-website` and `github-deploy` already prove out — no new execution
> engine. Companion to [ALLY-MISSIONS.md](ALLY-MISSIONS.md) (the engine) and the
> skills system (`backend/app/skills/`, `skill_service.py`).

## The core insight

`cyberpanel-host-website.md` and `github-deploy.md` are already staged, multi-part,
mission-mode workflows with their own step budget — everything this idea needs already
exists as a *pattern*. What's missing is discoverability: today a mission only starts
when a chat message happens to match a skill's `triggers`, or the model picks one off
a menu. Recipes make the good mission-mode skills **browsable and launchable by name**
instead of only reachable by phrasing a sentence right.

## Design decision: compose a sentence, don't bypass the pipeline

There's no "start mission by slug" entry point today — missions are born from chat
planning (`skill_service.match()` or the Phase B menu), which then produces a mission
offer the user clicks Start on. Deliberately **not** building a bypass. Instead, a
Recipe card collects a few variables and composes a natural-language sentence from a
template, then sends it exactly like the user typed it. It rides the unchanged
chat → mission-offer → Start pipeline, so `_run_mission`, per-step safety validation,
the verification gate, budgets, persistence, and detached execution all keep working
exactly as already built and tested. A Recipe is a smart form that writes a good
message for you — not a new way to run commands.

## Frontmatter additions (mission-mode skills only)

Kept as plain-text frontmatter (no YAML), consistent with how `triggers` already works:

```
recipe: true
summary: Get a full WordPress site live on this CyberPanel server, secured and verified.
icon: wordpress
variables: domain:required, title:optional:{{domain}}, email:optional:admin@{{domain}}
goal_template: Host a WordPress site at {{domain}}, title '{{title}}'
```

- `recipe: true` — opts a `mode: mission` skill into the gallery. Everything else about
  it (triggers, priority, budget, OS gate) is untouched — a Recipe-eligible skill can
  still also be discovered the normal way, from a chat message.
- `summary` — the user-facing one-liner for the card (the `title`/GOAL text is written
  for Ally, not a person).
- `variables` — `name:required|optional[:default]`; defaults may reference other
  variables (`{{domain}}`).
- `goal_template` — filled with the submitted variables to build the actual chat
  message that gets sent.

## What's new

- `skill_service.list_recipes(os_type)` — same OS-gating `menu_for()` already does,
  filtered to `mode="mission" and recipe=true`.
- `GET /api/recipes` (new, read-only router, mirrors `/api/playbooks`) — title, summary,
  icon, variables per eligible skill, OS-filtered against the selected target.
- Frontend: a Recipes gallery at the **top of the Missions page** (per your instinct),
  above the existing history list — `RecipeCard`/`RecipeLibrary` reusing the visual
  pattern of `PlaybookCard`/`PlaybookLibrary`, and a `RunRecipeModal` reusing
  `RunPlaybookModal`'s variable-collection form. Submit → compose `goal_template` →
  send as a normal chat message on the chosen server/fleet conversation.
- Completion hand-over reuses `AccessCard.tsx` — a finished Recipe ends with the same
  "here's your URL/login" card a Playbook run already produces.

## Catalog rule: proactive only

Only *goal-oriented* mission skills belong in the gallery (host a site, deploy a repo,
migrate a site, harden a server). Reactive/diagnostic mission skills — `security-
incident-response` and anything like it later — stay chat- or finding-triggered only.
Nobody browses-and-clicks "respond to a security incident" when nothing's wrong; that
one is correctly wired from the Security page's flagged findings already, and should
stay that way.

## Starter recipes

| Recipe | Status | Notes |
|---|---|---|
| Host a WordPress Site (CyberPanel) | Promote as-is | `cyberpanel-host-website`, budget 25 |
| Deploy a GitHub Repo | Promote as-is | `github-deploy`, budget 25 |
| Host a WordPress Site (plain server) | New | LEMP/LAMP path for servers without a panel |
| Migrate an Existing Website | New | The "move data to web dir" case — dump DB, transfer files + dump via the existing cross-server `transfer` mission action, restore, rewrite config, verify |
| Harden This Server | New | UFW + fail2ban + SSH-key-only + updates, guided + verified |
| Set Up Automatic Backups | New | Wire a backup job AND verify a restore actually works |
| Point a Domain + Get SSL | New | DNS check → certbot/panel SSL, smallest recipe |

## Constraints to design around

- **Budget ceiling: 40 steps** (`MISSION_BUDGET_MAX`). A maximal "install + migrate +
  harden + backup + verify everything" mega-recipe in one mission may not fit. Keep
  each recipe scoped to ~25–40 steps, matching what the two existing runbooks already
  declare. Treat literally chaining several missions back-to-back as Phase 2, not v1.
- **Hosting-mode guard is a hard wall.** Missions require shell access;
  `connection_type='hosting'` (API-only cPanel/Plesk/DirectAdmin) connections already
  refuse to run mission steps. A recipe can target CyberPanel-on-SSH (as today) but not
  a pure API-only hosting connection — that needs its own SSH/WP-CLI path first,
  unrelated to this feature.

## Relationship to the batch runner

Orthogonal, not competing: the batch runner is *the same action, fanned out across
many servers in parallel*; a Recipe is *depth on one target*. They compose later
without a redesign — once a Recipe is a clean parameterized unit, running one across
the whole fleet via the batch runner is a natural follow-on.

## Naming

Considered Blueprints, Kits, Recipes — picked **Recipes**. Distinctive versus direct
competitors, plain enough not to need translation gymnastics, and a nice bonus: in
several launch languages the word for "recipe" doubles as "formula/prescription"
(Hindi *nuskha*, Arabic *wasfa*) — which reads rather well for "Ally's prescription to
fix or build this."

## Recommended sequencing

1. Frontmatter additions + `list_recipes` + `GET /api/recipes` + promote the 2 existing
   mission skills — smallest slice, proves the pipeline end to end with zero new
   execution risk.
2. Recipes gallery UI on the Missions page + `RunRecipeModal` + `AccessCard` reuse.
3. Author the 4-5 new starter recipes (Migrate is the one most worth prioritizing —
   it's the specific case you called out, and nothing today covers it).
4. (Later, only if needed) true multi-mission chaining for mega-workflows that outgrow
   a single 40-step budget.
