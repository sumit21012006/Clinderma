import unittest
from unittest.mock import patch

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

        reloaded = SessionManager(self.db_path)
        self.assertTrue(reloaded.is_phone_required("session-1"))
        reloaded.set_phone_required("session-1", False)
        self.assertFalse(self.manager.is_phone_required("session-1"))


if __name__ == "__main__":
    unittest.main()
