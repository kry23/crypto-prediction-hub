"""Shared PostgreSQL connection pool for Streamlit pages."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import streamlit as st

try:
    import psycopg
    from psycopg_pool import ConnectionPool
except ImportError:  # pragma: no cover
    psycopg = None  # type: ignore
    ConnectionPool = None  # type: ignore


@st.cache_resource
def get_pool() -> "ConnectionPool":
    """Single global pool cached for the Streamlit process lifetime.

    Reads DATABASE_URL from env. Pool size 2..5 covers solo UI traffic
    plus the Ask Claude tool calls without saturating PG's max_connections.
    """
    if ConnectionPool is None:
        raise RuntimeError(
            "psycopg-pool not installed; run `pip install psycopg[binary] psycopg-pool`"
        )
    url = os.environ["DATABASE_URL"]
    return ConnectionPool(
        conninfo=url, min_size=2, max_size=5, open=True, timeout=10
    )


@contextmanager
def get_conn() -> Iterator["psycopg.Connection"]:
    """Convenience context manager for page code."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn
