# Update 21 — Per-playbook OS guard (Tier 1)

> Running a Debian/Ubuntu playbook on an AlmaLinux box gave a cryptic
> "`apt-get: command not found`". Now ServerMind knows which OS each playbook supports
> and won't run it on an incompatible server — it says so plainly instead. (Tier 1 of
> the "wrong OS" problem; Tier 2 = make popular playbooks multi-distro; Tier 3 =
> AI-tailored installs.)

## What changed

- **`playbook_service`:** `infer_supported_os(script)` — the OS families a playbook
  supports, from an explicit `case "${ID}"` guard, else inferred from the package
  manager it uses (apt → Debian/Ubuntu, dnf/yum → RHEL family), else `None`
  (agnostic). Plus `supported_os_for(playbook)` (declared field or inferred) and
  `os_matches(server, supported)` (never blocks on an unknown OS or a non-ssh server).
  The playbook API now returns the computed `supported_os`; the readiness check uses it.
- **Guards (defense in depth):** the single-run WebSocket path refuses an
  OS-incompatible run with a clear message; `run-multi` skips incompatible servers and
  reports the reason ("needs ubuntu/debian — this is almalinux"). Skipped servers now
  carry a reason (OS-incompatible vs already-running vs no-script-for-OS).
- **Picker (`RunPlaybookModal`):** incompatible servers are disabled with a red
  "Needs ubuntu/debian" badge and dropped from the run.
- **Readiness:** the "Check readiness" button now shows for OS-specific app playbooks
  (not just control panels), and the checklist judges the OS via the inferred families.

## Verified

On the real WordPress playbook (apt-based → `ubuntu/debian`): AlmaLinux is flagged
incompatible, Debian/Ubuntu pass, an unknown OS is not blocked. 70 backend tests pass;
build clean.

## Note — what Tier 1 does *not* fix

This guards the **gross** mismatch (apt on RHEL). The **within-family** failures we also
saw — `mysql-server` on Debian, `php8.2` on a non-PPA Ubuntu — need **Tier 2**: making
the popular playbooks genuinely multi-distro / version-robust (detect the distro + use
the right package names and PHP version).
