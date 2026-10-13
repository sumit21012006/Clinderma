import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.chat import handle_chat
from app.models.schemas import ChatRequest


class LiveTakeoverTests(unittest.TestCase):
    @patch("app.api.chat._emit_funnel_event")
    @patch("app.api.chat.handoff_manager.add_transcript")
    @patch("app.api.chat._is_session_taken_over", return_value=True)
    def test_takeover_records_customer_message_and_marks_response(self, _taken_over, add_transcript, emit_event):
        request = ChatRequest(message="I need help", session_id="live-session", channel="website")

        response = handle_chat(request)

        self.assertTrue(response.taken_over)
        self.assertEqual(response.answer, "")
        add_transcript.assert_called_once_with("live-session", "user", "I need help")
        emit_event.assert_called_once_with(
            "live-session", "message_sent", {"channel": "website", "handled_by": "admin"}
        )


if __name__ == "__main__":
    unittest.main()
