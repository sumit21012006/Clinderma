"""
Clinderma — Central PostgreSQL Connection Module

All services use this module to get a database connection.
Reads DATABASE_URL from environment (set in Render dashboard or .env).
"""

import os
import psycopg2
import psycopg2.extras


def get_conn():
    """Return a new psycopg2 connection with RealDictCursor factory."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Add it in the Render dashboard or your .env file."
        )
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn
