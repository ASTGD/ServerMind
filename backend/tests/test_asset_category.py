"""Assets Phase A — the only new backend logic is inferring a category from the transport
when the client didn't send one (older clients / backfill). Lock it."""
import pytest

from app.routers.servers import infer_category


@pytest.mark.parametrize(
    "conn,panel,expected",
    [
        ("winrm", None, "windows"),
        ("winrm", None, "windows"),
        ("hosting", "cpanel", "hosting"),
        ("hosting", None, "hosting"),
        ("ssh", "cyberpanel", "hosting"),  # an SSH box that carries a panel → Hosting
        ("ssh", None, "vps"),              # plain SSH → VPS (bare-metal can't be inferred)
    ],
)
def test_infer_category(conn, panel, expected):
    assert infer_category(conn, panel) == expected
