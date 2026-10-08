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


def run_migrations():
    """Create all tables (original + new PRD tables) if they don't exist.
    Safe to call on every startup — uses IF NOT EXISTS throughout.
    """
    conn = get_conn()
    cursor = conn.cursor()

    # ─── Original Tables ──────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            lead_id TEXT PRIMARY KEY,
            name TEXT,
            phone_number TEXT,
            concern TEXT,
            channel TEXT DEFAULT 'website',
            kylas_synced INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS handoffs (
            session_id TEXT PRIMARY KEY,
            user_name TEXT,
            user_phone TEXT,
            reason TEXT,
            channel TEXT,
            status TEXT DEFAULT 'pending',
            severity TEXT DEFAULT 'moderate',
            doctor_notes TEXT DEFAULT '',
            ai_summary TEXT DEFAULT '',
            takeover_by TEXT DEFAULT NULL,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            sender TEXT,
            message TEXT,
            timestamp TEXT
        )
    """)

    # ─── PRD Phase 1: New Tables ──────────────────────────────────────────────

    # Admin-editable Knowledge Base entries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kb_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            question TEXT,
            answer TEXT,
            status TEXT DEFAULT 'draft',
            live_answer TEXT DEFAULT '',
            created_by TEXT DEFAULT 'admin',
            updated_at TEXT,
            created_at TEXT
        )
    """)

    # Uploaded KB documents
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kb_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            original_filename TEXT,
            category TEXT DEFAULT 'General',
            status TEXT DEFAULT 'draft',
            file_path TEXT,
            uploaded_by TEXT DEFAULT 'admin',
            uploaded_at TEXT
        )
    """)

    # Publish history snapshots (for undo/restore)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS publish_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot TEXT,
            pushed_by TEXT DEFAULT 'admin',
            pushed_at TEXT
        )
    """)

    # Offers management
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            discount_code TEXT,
            discount_type TEXT DEFAULT 'percentage',
            discount_value REAL DEFAULT 0,
            applicable_products TEXT DEFAULT '[]',
            conditions TEXT DEFAULT '{}',
            start_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT 'scheduled',
            created_by TEXT DEFAULT 'admin',
            created_at TEXT
        )
    """)

    # Doctor review queue
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctor_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            customer_question TEXT,
            chatbot_answer TEXT,
            tagged_by TEXT DEFAULT 'admin',
            tag_note TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            reviewed_by TEXT DEFAULT NULL,
            corrected_answer TEXT DEFAULT NULL,
            reviewed_at TEXT DEFAULT NULL,
            created_at TEXT
        )
    """)

    # Audit / Change log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT,
            entity_id TEXT DEFAULT '',
            entity_name TEXT DEFAULT '',
            old_value TEXT DEFAULT '',
            new_value TEXT DEFAULT '',
            performed_by TEXT DEFAULT 'admin',
            performed_at TEXT
        )
    """)

    # Funnel events for analytics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS funnel_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT DEFAULT '',
            event_type TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TEXT
        )
    """)

    # Admin users with roles (JWT auth)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'viewer',
            full_name TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    # ─── Safe column migrations for older deployments ─────────────────────────
    for col_def in [
        ("severity", "TEXT DEFAULT 'moderate'"),
        ("doctor_notes", "TEXT DEFAULT ''"),
        ("ai_summary", "TEXT DEFAULT ''"),
        ("takeover_by", "TEXT DEFAULT NULL"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE handoffs ADD COLUMN {col_def[0]} {col_def[1]}")
            conn.commit()
        except Exception:
            pass

    conn.commit()
    cursor.close()
    conn.close()
    print("[DB] Migrations complete — all tables ready.")
