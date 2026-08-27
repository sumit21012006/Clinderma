"""
Clinderma Session Manager — Conversation Memory & State Tracking

Maintains:
  1. Multi-turn sliding window conversation history for LLM context.
  2. Per-session turn count tracking for natural lead timing (turns 2-3).
  3. Lead capture verification (ensuring users are not repeatedly asked for info).
"""

import sqlite3
from typing import List, Dict, Any, Optional
from app.core.config import settings

class SessionManager:
    """Manages per-session conversation history and state for multi-turn conversational AI."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DB_PATH

    def _get_conn(self):
        return sqlite3.connect(self.db_path, timeout=30.0)

    def get_history(self, session_id: str, max_turns: int = None) -> List[Dict[str, str]]:
        """Retrieve the last N conversation messages for a session in chronological order."""
        max_turns = max_turns or settings.MAX_HISTORY_TURNS

        try:
            conn = self._get_conn()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sender, message FROM transcripts WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, max_turns)
            )
            rows = cursor.fetchall()
            conn.close()

            # Reverse to chronological order
            history = [{"sender": r["sender"], "message": r["message"]} for r in reversed(rows)]
            return history
        except Exception:
            return []

    def get_turn_count(self, session_id: str) -> int:
        """Count the number of user messages sent in this session."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM transcripts WHERE session_id = ? AND sender = 'user'",
                (session_id,)
            )
            count = cursor.fetchone()[0]
            conn.close()
            return int(count)
        except Exception:
            return 1

    def is_lead_captured(self, session_id: str) -> bool:
        """Check whether the user's phone number has already been captured in this session."""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()

            # Check handoffs table
            cursor.execute(
                "SELECT user_phone FROM handoffs WHERE session_id = ? AND user_phone IS NOT NULL AND user_phone != ''",
                (session_id,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                conn.close()
                return True

            # Check leads table with session_id in concern
            cursor.execute(
                "SELECT phone_number FROM leads WHERE concern LIKE ?",
                (f"%{session_id}%",)
            )
            lead_row = cursor.fetchone()
            conn.close()
            if lead_row and lead_row[0]:
                return True

            return False
        except Exception:
            return False

    def get_captured_info(self, session_id: str) -> Dict[str, Optional[str]]:
        """Retrieve already captured name and phone if available."""
        info = {"name": None, "phone": None}
        try:
            conn = self._get_conn()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_name, user_phone FROM handoffs WHERE session_id = ?",
                (session_id,)
            )
            row = cursor.fetchone()
            if row:
                info["name"] = row["user_name"] if row["user_name"] != "Anonymous" else None
                info["phone"] = row["user_phone"]
            conn.close()
        except Exception:
            pass
        return info

session_manager = SessionManager()
