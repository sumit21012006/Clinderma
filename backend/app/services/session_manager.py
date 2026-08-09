"""
Clinderma Session Manager — Conversation Memory

Maintains a sliding window of conversation history per session,
enabling multi-turn context for the LLM provider.
"""

import sqlite3
from typing import List, Dict, Any
from app.core.config import settings


class SessionManager:
    """Manages per-session conversation history for multi-turn LLM context."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DB_PATH

    def get_history(self, session_id: str, max_turns: int = None) -> List[Dict[str, str]]:
        """Retrieve the last N conversation messages for a session."""
        max_turns = max_turns or settings.MAX_HISTORY_TURNS

        try:
            conn = sqlite3.connect(self.db_path)
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


session_manager = SessionManager()
