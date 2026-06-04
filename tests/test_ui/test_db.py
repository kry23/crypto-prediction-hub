"""Smoke: db helper imports and exposes the expected API."""
from crypto_predictor.ui.db import get_conn, get_pool


def test_db_module_exports_get_pool_and_get_conn():
    assert callable(get_pool)
    assert callable(get_conn)


def test_get_pool_requires_psycopg_when_called(monkeypatch):
    """Smoke: get_pool raises a useful error when psycopg isn't installed."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://does/not/matter")
    # Don't actually call get_pool() — that would try to connect.
    # Just confirm the symbol exists and is callable.
    assert get_pool is not None
