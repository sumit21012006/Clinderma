import os
import sqlite3
import tempfile
import unittest
import datetime
from unittest.mock import patch

from app.core.db import _SQLiteConn
from app.services.session_manager import SessionManager


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self.row = None

    def execute(self, query, params=()):
        if "SELECT phone_required" in query:
            value = self.state.get(params[0])
            self.row = {"phone_required": value} if value is not None else None
        elif "INSERT INTO chat_session_state" in query:
            self.state[params[0]] = bool(params[1])

    def fetchone(self):
        return self.row

    def close(self):
        pass


class FakeConnection:
    def __init__(self, state):
        self.cursor_obj = FakeCursor(state)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        pass

    def close(self):
        pass


class SessionManagerStateTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.connection = FakeConnection(self.state)
        self.get_conn = patch("app.services.session_manager.get_conn", return_value=self.connection)
        self.get_conn.start()
        self.manager = SessionManager()

    def tearDown(self):
        self.get_conn.stop()

    def test_phone_gate_is_durable_and_can_be_cleared(self):
        self.assertFalse(self.manager.is_phone_required("session-1"))
        self.manager.set_phone_required("session-1", True)
        self.assertTrue(self.manager.is_phone_required("session-1"))

        reloaded = SessionManager()
        self.assertTrue(reloaded.is_phone_required("session-1"))
        reloaded.set_phone_required("session-1", False)
        self.assertFalse(self.manager.is_phone_required("session-1"))


class SessionLifecycleTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = handle.name
        handle.close()

        def connection_factory():
            return _SQLiteConn(sqlite3.connect(self.db_path))

        self.get_conn = patch("app.services.session_manager.get_conn", side_effect=connection_factory)
        self.get_conn.start()
        self.manager = SessionManager()

    def tearDown(self):
        self.get_conn.stop()
        os.unlink(self.db_path)

    def test_activity_prompt_and_end_are_persisted(self):
        self.assertEqual(self.manager.get_session_state("session-1")["status"], "new")

        self.manager.touch_session("session-1")
        self.assertEqual(self.manager.get_session_state("session-1")["status"], "live")

        self.manager.mark_awaiting_confirmation("session-1")
        self.assertEqual(
            self.manager.get_session_state("session-1", reconcile=False)["status"],
            "awaiting_confirmation",
        )

        self.manager.end_session("session-1")
        self.assertEqual(self.manager.get_session_state("session-1")["status"], "ended")

    def test_idle_and_expired_states_follow_user_activity(self):
        self.manager.touch_session("session-2")
        stale = (
            datetime.datetime.now() - datetime.timedelta(seconds=121)
        ).isoformat()
        raw = sqlite3.connect(self.db_path)
        raw.execute(
            "UPDATE chat_session_state SET last_user_activity_at = ? WHERE session_id = ?",
            (stale, "session-2"),
        )
        raw.commit()
        raw.close()

        # Admin activity updates the transcript/session but must not reset the
        # customer's inactivity clock.
        self.manager.touch_session("session-2", user_activity=False)
        self.assertEqual(self.manager.get_session_state("session-2")["status"], "idle")

        self.manager.mark_awaiting_confirmation("session-2")
        expired = (
            datetime.datetime.now() - datetime.timedelta(seconds=31)
        ).isoformat()
        raw = sqlite3.connect(self.db_path)
        raw.execute(
            "UPDATE chat_session_state SET inactivity_prompted_at = ? WHERE session_id = ?",
            (expired, "session-2"),
        )
        raw.commit()
        raw.close()

        self.assertEqual(self.manager.get_session_state("session-2")["status"], "ended")
        self.assertEqual(
            self.manager.get_session_state("session-2", reconcile=False)["status"],
            "ended",
        )
        self.manager.get_session_state("session-2")
        raw = sqlite3.connect(self.db_path)
        closure_count = raw.execute(
            "SELECT COUNT(*) FROM transcripts WHERE session_id = ? AND sender = 'system'",
            ("session-2",),
        ).fetchone()[0]
        raw.close()
        self.assertEqual(closure_count, 1)


if __name__ == "__main__":
    unittest.main()
