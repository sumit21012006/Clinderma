import hashlib
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.security import HTTPBasicCredentials

from app.api.auth_api import LoginRequest, login
from app.core.db import _SQLiteConn
from app.core.auth import (
    ensure_default_admin,
    hash_password,
    password_needs_rehash,
    verify_clinical_user,
    verify_password,
)


class PasswordHashTests(unittest.TestCase):
    def test_password_hashes_are_salted_and_verifiable(self):
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")

        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("correct horse battery staple", first))
        self.assertFalse(verify_password("wrong", first))
        self.assertFalse(password_needs_rehash(first))

    def test_legacy_hashes_remain_valid_for_login_migration(self):
        legacy = hashlib.sha256(
            "clinderma_salt_2026legacy-password".encode()
        ).hexdigest()

        self.assertTrue(verify_password("legacy-password", legacy))
        self.assertTrue(password_needs_rehash(legacy))

    def test_successful_legacy_login_rehashes_stored_password(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = handle.name
        handle.close()
        legacy = hashlib.sha256(
            "clinderma_salt_2026legacy-password".encode()
        ).hexdigest()
        raw = sqlite3.connect(db_path)
        raw.execute("""
            CREATE TABLE admin_users (
                username TEXT PRIMARY KEY, password_hash TEXT, role TEXT,
                full_name TEXT, is_active INTEGER
            )
        """)
        raw.execute(
            "INSERT INTO admin_users VALUES (?, ?, ?, ?, ?)",
            ("legacy-user", legacy, "admin", "Legacy User", 1),
        )
        raw.commit()
        raw.close()

        def connection_factory():
            return _SQLiteConn(sqlite3.connect(db_path))

        try:
            with patch("app.api.auth_api.get_conn", side_effect=connection_factory):
                response = login(LoginRequest(
                    username="legacy-user",
                    password="legacy-password",
                ))
            self.assertEqual(response.role, "admin")

            raw = sqlite3.connect(db_path)
            migrated = raw.execute(
                "SELECT password_hash FROM admin_users WHERE username = ?",
                ("legacy-user",),
            ).fetchone()[0]
            raw.close()
            self.assertTrue(migrated.startswith("pbkdf2_sha256$"))
            self.assertTrue(verify_password("legacy-password", migrated))
        finally:
            os.unlink(db_path)

    def test_doctor_account_can_open_clinical_console(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = handle.name
        handle.close()
        raw = sqlite3.connect(db_path)
        raw.execute("""
            CREATE TABLE admin_users (
                username TEXT PRIMARY KEY, password_hash TEXT, role TEXT,
                full_name TEXT, is_active INTEGER
            )
        """)
        raw.execute(
            "INSERT INTO admin_users VALUES (?, ?, ?, ?, ?)",
            ("doctor", hash_password("clinical-secret"), "doctor", "Doctor", 1),
        )
        raw.commit()
        raw.close()

        def connection_factory():
            return _SQLiteConn(sqlite3.connect(db_path))

        try:
            with patch("app.core.db.get_conn", side_effect=connection_factory):
                user = verify_clinical_user(HTTPBasicCredentials(
                    username="doctor",
                    password="clinical-secret",
                ))
            self.assertEqual(user, {"username": "doctor", "role": "doctor"})
        finally:
            os.unlink(db_path)

    def test_startup_seeds_missing_roles_without_overwriting_admin(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = handle.name
        handle.close()
        existing_hash = hash_password("custom-admin-password")
        raw = sqlite3.connect(db_path)
        raw.execute("""
            CREATE TABLE admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE, password_hash TEXT, role TEXT,
                full_name TEXT, is_active INTEGER, created_at TEXT
            )
        """)
        raw.execute(
            """
            INSERT INTO admin_users
                (username, password_hash, role, full_name, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("admin", existing_hash, "admin", "Existing Admin", 1, "2026-01-01"),
        )
        raw.commit()
        raw.close()

        def connection_factory():
            return _SQLiteConn(sqlite3.connect(db_path))

        try:
            with patch("app.core.db.get_conn", side_effect=connection_factory):
                ensure_default_admin()
            raw = sqlite3.connect(db_path)
            users = dict(raw.execute(
                "SELECT username, password_hash FROM admin_users"
            ).fetchall())
            raw.close()
            self.assertEqual(users["admin"], existing_hash)
            self.assertIn("doctor", users)
            self.assertIn("viewer", users)
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
