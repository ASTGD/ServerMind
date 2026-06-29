"""Per-playbook OS guard (Update 21)."""
from types import SimpleNamespace

from app.services.playbook_service import infer_supported_os, os_matches


def test_infer_apt_is_debian_family():
    assert infer_supported_os("apt-get install -y nginx mysql-server") == ["ubuntu", "debian"]


def test_infer_dnf_is_rhel_family():
    s = infer_supported_os("dnf install -y nginx")
    assert s and "almalinux" in s and "ubuntu" not in s


def test_infer_agnostic_when_neither():
    assert infer_supported_os("curl -fsSL https://get.docker.com | sh") is None


def test_infer_prefers_explicit_case_guard():
    script = 'case "${ID:-}" in ubuntu|debian|almalinux) : ;; *) echo ERROR; exit 1 ;; esac\napt-get update'
    assert set(infer_supported_os(script)) == {"ubuntu", "debian", "almalinux"}


def test_os_matches():
    apt = ["ubuntu", "debian"]
    ssh = lambda os: SimpleNamespace(connection_type="ssh", os_type=os)
    assert os_matches(ssh("ubuntu"), apt) is True
    assert os_matches(ssh("almalinux"), apt) is False         # wrong family → blocked
    assert os_matches(ssh(None), apt) is True                 # unknown OS → don't block
    assert os_matches(ssh("ubuntu"), None) is True            # OS-agnostic playbook
    assert os_matches(SimpleNamespace(connection_type="winrm", os_type="windows"), apt) is True  # not ssh → skip
