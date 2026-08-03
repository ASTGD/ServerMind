"""Securing the login, on a socket-activated sshd.

Found live. The setup failed on step 5 with *"those SSH settings would not load, so nothing
was applied:"* — a sentence that ends in a colon and says nothing, about a config that was
perfectly fine.

Two separate faults:

* `sshd -t` needs `/run/sshd` to exist. On Ubuntu 24.04 sshd is **socket-activated**: that
  directory is created per connection and removed again, so the test fails with "Missing
  privilege separation directory" depending on whether a connection happens to be open.
  Intermittent — it passed on 1 August and failed today on the same machine.
* The reason was printed on the line BELOW `>>> ERROR:`, and `extract_failure_reason` keeps
  only the marker line. Everything explaining the failure was thrown away.

These run against a real Ubuntu 24.04 sshd in a container, because the whole bug is what
the real binary does when a directory is missing — nothing about it is visible in the text
of the script.
"""
import shutil
import subprocess

import pytest

from app.services import playbook_service as pb

docker = pytest.mark.skipif(
    shutil.which("docker") is None
    or subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
    reason="needs docker: the bug is in what a real sshd does, not in the script text")

PROBE = r"""set -e
apt-get update -qq >/dev/null 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq openssh-server >/dev/null 2>&1
rm -rf /run/sshd
mkdir -p /stub
printf '#!/bin/sh\ncase "$*" in *"is-active ssh.socket"*) echo active;; *) exit 0;; esac\n' > /stub/systemctl
chmod +x /stub/systemctl
export PATH=/stub:$PATH
. /tmp/layer.sh
%s
"""


def run_in_ubuntu(tmp_path, body: str) -> tuple[int, str]:
    layer = tmp_path / "layer.sh"
    layer.write_text(pb._SSH_SAFE)
    probe = tmp_path / "probe.sh"
    probe.write_text(PROBE % body)
    proc = subprocess.run(
        ["docker", "run", "--rm",
         "-v", f"{probe}:/tmp/p.sh", "-v", f"{layer}:/tmp/layer.sh",
         "ubuntu:24.04", "bash", "/tmp/p.sh"],
        capture_output=True, text=True, timeout=600)
    return proc.returncode, proc.stdout + proc.stderr


@docker
def test_a_good_setting_applies_even_with_no_privsep_directory(tmp_path):
    """The exact live failure. Before the fix this refused and told the owner their
    settings would not load — which was untrue."""
    code, out = run_in_ubuntu(tmp_path, """
ssh_set X11Forwarding no
ssh_apply || { echo "REFUSED"; exit 3; }
grep -q "X11Forwarding no" /etc/ssh/sshd_config.d/00-serverally.conf || exit 4
echo APPLIED
""")
    assert code == 0, out
    assert "APPLIED" in out
    assert "would not load" not in out


@docker
def test_a_genuinely_broken_setting_is_still_refused(tmp_path):
    """The guard has to keep working. Making the config test pass by weakening it would
    trade one bad outcome for a far worse one — a server nobody can log in to."""
    code, out = run_in_ubuntu(tmp_path, """
ssh_set X11Forwarding no
echo "ThisIsNotARealOption yes" >> /etc/ssh/sshd_config.d/00-serverally.conf
if ssh_apply; then echo "APPLIED-WRONGLY"; exit 5; fi
[ -f /etc/ssh/sshd_config.d/00-serverally.conf ] && { echo "LEFT-BEHIND"; exit 6; }
echo REFUSED-AND-CLEANED
""")
    assert code == 0, out
    assert "REFUSED-AND-CLEANED" in out


@docker
def test_the_refusal_says_what_was_actually_wrong(tmp_path):
    """The message used to end in a colon. The runner keeps only the ">>> ERROR" line, so
    a reason printed underneath it never reaches the customer."""
    _code, out = run_in_ubuntu(tmp_path, """
ssh_set X11Forwarding no
echo "ThisIsNotARealOption yes" >> /etc/ssh/sshd_config.d/00-serverally.conf
ssh_apply || true
""")
    line = next(ln for ln in out.splitlines() if ln.startswith(">>> ERROR:"))
    assert "Bad configuration option" in line, line
    assert not line.rstrip().endswith(":"), f"the reason is missing again: {line!r}"

    # And the runner really does keep only that line — so this is the line that matters.
    assert "Bad configuration option" in (pb.extract_failure_reason(out) or "")


def test_the_privsep_directory_is_created_before_the_test():
    """Ordering, not presence: creating it after `sshd -t` would change nothing."""
    layer = pb._SSH_SAFE
    apply_fn = layer[layer.index("ssh_apply()"):]
    # Executable lines only. The comment explaining this fix contains the words "sshd -t",
    # and a first version of this test matched THAT and failed — the same trap as the
    # `pgrep`-in-a-comment one on 1 August.
    code = [ln for ln in apply_fn.splitlines() if not ln.strip().startswith("#")]
    made = next(i for i, ln in enumerate(code) if "mkdir -p /run/sshd" in ln)
    tested = next(i for i, ln in enumerate(code) if "sshd -t" in ln)
    assert made < tested, "creating it after the test would change nothing"


def test_socket_activation_does_not_start_the_service():
    """On Ubuntu 24.04 ssh.socket owns port 22. Starting ssh.service alongside it is two
    things fighting for the same port, and the config is already live for new connections."""
    layer = pb._SSH_SAFE
    apply_fn = layer[layer.index("ssh_apply()"):]
    assert 'is-active ssh.socket' in apply_fn
    branch = apply_fn[apply_fn.index("is-active ssh.socket"):apply_fn.index("else")]
    assert "systemctl restart" not in branch and "systemctl reload" not in branch
