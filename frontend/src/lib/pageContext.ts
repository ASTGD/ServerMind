/**
 * Page context for Ally (the assistant).
 *
 * We deliberately do NOT scrape the rendered page. Instead, each known route declares a
 * short, safe description + starter templates here, and pages that have a focused entity
 * (e.g. an open script) publish a richer, hand-picked context via `usePublishPageContext`.
 * This gives Ally useful "what am I looking at" awareness without ever leaking on-screen
 * secrets, unrelated data, or hidden text — because we only ever share fields we chose.
 */
export interface PageContext {
  /** Short human label for the current page, e.g. "My Scripts". */
  label: string
  /** One-line advisory sent to Ally as background ("what the user is looking at"), or null. */
  context: string | null
  /** Clickable starter questions tailored to the page. */
  templates: string[]
}

const on = (label: string): string =>
  `The user is currently on the ${label} page of ServerAlly (an AI server-management app).`

/**
 * Static context for a route — used when a page doesn't publish a richer, entity-specific
 * one. Order matters: more specific paths are matched before their parents.
 */
export function staticPageContext(pathname: string): PageContext {
  const p = pathname

  if (p === "/" || p === "/dashboard")
    return {
      label: "Dashboard",
      context: on("Dashboard"),
      templates: [
        "Give me a health summary of my servers",
        "Which server needs attention?",
        "Is anything low on disk space?",
      ],
    }

  if (p === "/scripts/generate")
    return {
      label: "Script Generator",
      context: on("AI Script Generator"),
      templates: [
        "Write a script to back up MySQL every night",
        "Make a script to clean old log files",
        "Generate a script to set up a firewall",
      ],
    }

  if (p === "/scripts")
    return {
      label: "My Scripts",
      context: on("My Scripts"),
      templates: [
        "What can I automate with scripts?",
        "Write a script to back up a folder",
        "Explain what a bash script is",
      ],
    }

  if (p.startsWith("/playbooks/"))
    return {
      label: "Playbook",
      context: on("a playbook detail"),
      templates: [
        "What does this playbook do?",
        "Is this safe to run on my server?",
        "Which of my servers can run this?",
      ],
    }

  if (p === "/playbooks")
    return {
      label: "Playbooks",
      context: on("Playbooks library"),
      templates: [
        "Which playbook should I use for a Node.js app?",
        "What does the WordPress playbook do?",
        "Recommend playbooks for a new Ubuntu server",
      ],
    }

  // Nested server tabs (paths look like /servers/:id/security) — match the suffix first.
  if (p.includes("/security"))
    return {
      label: "Security",
      context: on("a server's Security report"),
      templates: ["Explain my security score", "What should I fix first?", "How do I harden SSH?"],
    }

  if (p.includes("/backups"))
    return {
      label: "Backups",
      context: on("a server's Backups"),
      templates: [
        "How do backups work here?",
        "Set up a nightly database backup",
        "How do I restore a backup?",
      ],
    }

  if (p.includes("/files"))
    return {
      label: "Files",
      context: on("a server's File Manager"),
      templates: [
        "How do I edit a file here?",
        "Where are the nginx config files?",
        "How do I change file permissions?",
      ],
    }

  if (p.includes("/scheduler"))
    return {
      label: "Scheduler",
      context: on("a server's Scheduler"),
      templates: [
        "Schedule a task every night at 2am",
        "How do cron schedules work?",
        "Run a cleanup every Sunday",
      ],
    }

  if (p.startsWith("/servers/"))
    return {
      label: "Server",
      context: on("a single server"),
      templates: ["Check disk space", "Install nginx", "Why is CPU high?"],
    }

  if (p === "/servers")
    return {
      label: "Servers",
      context: on("Servers list"),
      templates: [
        "Which server needs attention?",
        "How do I add a new server?",
        "Which servers are offline?",
      ],
    }

  if (p === "/logs")
    return {
      label: "Activity Log",
      context: on("Activity Log"),
      templates: [
        "Summarize my recent activity",
        "Did any commands fail recently?",
        "What changed on my servers today?",
      ],
    }

  if (p === "/team")
    return {
      label: "Team",
      context: on("Team management"),
      templates: ["How do team roles work?", "How do I invite a teammate?", "What can a viewer do?"],
    }

  if (p === "/settings")
    return {
      label: "Settings",
      context: on("Settings"),
      templates: [
        "How do I change my language?",
        "How do I turn on two-factor login?",
        "How do I update my password?",
      ],
    }

  // Unknown / assistant / terminal pages — no page hint, generic starters.
  return {
    label: "ServerAlly",
    context: null,
    templates: [
      "Which server needs attention?",
      "Recommend a playbook for a new server",
      "Give me a health summary",
    ],
  }
}
