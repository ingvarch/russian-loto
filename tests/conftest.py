"""Shared test fixtures. Redirects the card registry to a temp file."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path, monkeypatch):
    """Ensure tests never touch the real registry."""
    fake_path = str(tmp_path / "test_printed.json")
    monkeypatch.setenv("RUSSIAN_LOTO_REGISTRY", fake_path)
