"""
Clinderma — Central Database Connection Module

All services use this module to get a database connection.
- Production (Render): Reads DATABASE_URL from environment (PostgreSQL via psycopg2).
- Local Dev fallback: Uses SQLite if DATABASE_URL is not set.
"""

import os
import sqlite3


class _DictCursor:
    """Minimal cursor wrapper that makes sqlite3 rows behave like psycopg2 RealDictCursor."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=None):
        # Convert %s placeholders (psycopg2 style) to ? (sqlite3 style)
        query = query.replace("%s", "?")
        self._cursor.execute(query, params or [])

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._cursor.close()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid


class _SQLiteConn:
    """Minimal connection wrapper around sqlite3 to mimic psycopg2 interface."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        self._conn.row_factory = sqlite3.Row
        return _DictCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *args):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()


def get_conn():
    """Return a database connection.

    Uses PostgreSQL (psycopg2) when DATABASE_URL is set (production on Render),
    otherwise falls back to a local SQLite file for development.
    """
    url = os.environ.get("DATABASE_URL")

    if url:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn

    # --- Local dev fallback: SQLite ---
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "clinderma.db")
    db_path = os.path.abspath(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return _SQLiteConn(conn)
