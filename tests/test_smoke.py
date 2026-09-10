"""M0 smoke test."""

from app.main import main


def test_main_returns_success() -> None:
    assert main() == 0
