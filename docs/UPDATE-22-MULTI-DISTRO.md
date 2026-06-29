# Update 22 — Multi-distro web stacks (Tier 2)

> Tier 1 stopped cryptic cross-OS failures by *blocking* incompatible servers. Tier 2
> makes the three most-used web-stack playbooks — **WordPress, LAMP, LEMP** — genuinely
> run on Ubuntu/Debian (any version) **and** AlmaLinux/Rocky/CentOS, fixing the
> within-family failures too (`mysql-server` on Debian, `php8.2` on newer Ubuntu).

## Root causes fixed

- **`mysql-server` has no candidate on Debian** → use **MariaDB** (`mariadb-server`), a
  drop-in MySQL replacement present in every default repo (Ubuntu, Debian, RHEL).
- **`php8.2` missing on Ubuntu 22.04 / 24.04** → install **unversioned** PHP
  meta-packages (`php-fpm`, `php-mysql` / `php-mysqlnd`, …) that resolve to each distro's
  default PHP; the PHP-FPM **service name and socket are detected at runtime**, not
  hard-coded. No `ppa:ondrej/php`.
- **`apt-get: command not found` on AlmaLinux** → a shared **multi-distro layer** detects
  the OS family from `/etc/os-release` and routes to `apt` or `dnf`.

## The multi-distro layer (`_DISTRO`)

A reusable preamble injected after `set -euo pipefail` in each script. It detects
`FAMILY` (debian/rhel) and exposes helpers used by the body:

- `pkg_refresh` / `pkg_install` — apt or dnf/yum.
- `svc_enable` / `svc_restart` — systemd.
- `php_fpm_service` / `php_fpm_socket` — runtime-detected (e.g. `php8.1-fpm` +
  `/run/php/php8.1-fpm.sock` on Debian; `php-fpm` + `/run/php-fpm/www.sock` on RHEL).
- `open_firewall <port>` — ufw **or** firewalld, whichever is active.

RHEL specifics handled: php-fpm pool switched to the `nginx` user, EPEL for certbot,
SELinux (`httpd_can_network_connect`, content context on the web root), firewalld ports,
`httpd` vs `apache2`, and `conf.d` vs `sites-available`. An unsupported OS aborts with a
plain `>>> ERROR:` message.

## Result

`supported_os` for all three is now `ubuntu, debian, almalinux, rocky, centos, rhel,
fedora` — so the Tier 1 guard now **allows** an AlmaLinux server for WordPress instead of
blocking it.

## Verified

- `bash -n` clean on all three generated scripts; DB resynced (50 playbooks); 70 backend
  tests pass.
- The stored WordPress script contains the multi-distro layer + MariaDB and **no** legacy
  `mysql-server` / `php8.2` / `add-apt-repository`.
- `os_matches()` now returns `True` for TestServer2 (AlmaLinux) on WordPress/LAMP/LEMP.

## ⚠️ Caveat — the RHEL path needs a live smoke test

The Ubuntu/Debian path is high-confidence and fixes the observed failures directly. The
RHEL/dnf path follows documented AlmaLinux/Rocky practice but — like the control-panel
playbooks — has **not** been run end-to-end. SELinux, firewalld, and the php-fpm pool are
exactly where untested scripts break. Smoke-test on a fresh AlmaLinux box (e.g.
TestServer2) before relying on it; every step echoes a clear `>>>` line so any failure
surfaces a plain reason rather than a cryptic crash.

## Not yet covered

Other apt-based playbooks (e.g. `nodejs-pm2`, `python-env`, app deploys) are still
Debian/Ubuntu-only and remain correctly guarded by Tier 1. They can get the same
`_DISTRO` treatment incrementally.
