import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app.core.db import _SQLiteConn, run_migrations
from app.providers.order_provider import DatabaseOrderProvider


class OperationalStorageTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()

        def connection_factory():
            return _SQLiteConn(sqlite3.connect(self.db_path))

        self.connection_factory = connection_factory
        with patch("app.core.db.get_conn", side_effect=connection_factory):
            run_migrations()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_fresh_migration_keeps_lifecycle_and_order_tables(self):
        raw = sqlite3.connect(self.db_path)
        tables = {
            row[0]
            for row in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        lifecycle_columns = {
            row[1] for row in raw.execute("PRAGMA table_info(chat_session_state)")
        }
        order_columns = {row[1] for row in raw.execute("PRAGMA table_info(orders)")}
        raw.close()

        self.assertIn("chat_session_state", tables)
        self.assertIn("orders", tables)
        self.assertIn("chat_metrics", tables)
        self.assertIn("last_user_activity_at", lifecycle_columns)
        self.assertIn("order_value", order_columns)

    def test_database_order_provider_returns_persisted_fulfilment(self):
        raw = sqlite3.connect(self.db_path)
        raw.execute(
            """
            INSERT INTO orders (
                order_id, status, customer_name, items,
                estimated_delivery, tracking_url, order_value,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CLIN-9001",
                "Shipped",
                "Test Customer",
                json.dumps(["Barrier Cream"]),
                "Tomorrow",
                "https://example.test/track/9001",
                999,
                "2026-10-13T10:00:00",
                "2026-10-13T10:00:00",
            ),
        )
        raw.commit()
        raw.close()

        with patch(
            "app.providers.order_provider.get_conn",
            side_effect=self.connection_factory,
        ):
            result = DatabaseOrderProvider().get_order_status("where is CLIN9001?")

        self.assertTrue(result["found"])
        self.assertEqual(result["status"], "Shipped")
        self.assertEqual(result["items"], ["Barrier Cream"])


if __name__ == "__main__":
    unittest.main()
