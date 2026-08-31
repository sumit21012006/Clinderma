"""
Clinderma Session Manager — Conversation Memory & State Tracking

Maintains:
  1. Multi-turn sliding window conversation history for LLM context.
  2. Per-session turn count tracking for natural lead timing (turns 2-3).
  3. Lead capture verification (ensuring users are not repeatedly asked for info).
"""

from typing import List, Dict, Any, Optional
from app.core.db import get_conn
from app.core.config import settings


class SessionManager:
    """Manages per-session conversation history and state for multi-turn conversational AI."""

    @staticmethod
    def _ensure_state_table(conn) -> None:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_session_state (
                session_id TEXT PRIMARY KEY,
                phone_required BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)
        conn.commit()
        cursor.close()

    def is_phone_required(self, session_id: str) -> bool:
        try:
            conn = get_conn()
            self._ensure_state_table(conn)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT phone_required FROM chat_session_state WHERE session_id = %s",
                (session_id,),
            )
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            return bool(row and row["phone_required"])
        except Exception:
            return False

    def set_phone_required(self, session_id: str, required: bool) -> None:
        conn = get_conn()
        try:
            self._ensure_state_table(conn)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_session_state (session_id, phone_required)
                VALUES (%s, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET phone_required = EXCLUDED.phone_required
            """, (session_id, required))
            conn.commit()
            cursor.close()
        finally:
            conn.close()
    def get_history(self, session_id: str, max_turns: int = None) -> List[Dict[str, str]]:
        """Retrieve the last N conversation messages for a session in chronological order."""
        max_turns = max_turns or settings.MAX_HISTORY_TURNS

        try:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sender, message FROM transcripts WHERE session_id = %s ORDER BY id DESC LIMIT %s",
                (session_id, max_turns)
            )
            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            # Reverse to chronological order
            history = [{"sender": r["sender"], "message": r["message"]} for r in reversed(rows)]
            return history
        except Exception:
            return []

    def get_turn_count(self, session_id: str) -> int:
        """Count the number of user messages sent in this session."""
        try:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM transcripts WHERE session_id = %s AND sender = 'user'",
                (session_id,)
            )
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            return int(row["cnt"]) if row else 1
        except Exception:
            return 1

    def is_lead_captured(self, session_id: str) -> bool:
        """Check whether the user's phone number has already been captured in this session."""
        try:
            conn = get_conn()
            cursor = conn.cursor()

            # Check handoffs table
            cursor.execute(
                "SELECT user_phone FROM handoffs WHERE session_id = %s AND user_phone IS NOT NULL AND user_phone != ''",
                (session_id,)
            )
            row = cursor.fetchone()
            if row and row["user_phone"]:
                cursor.close()
                conn.close()
                return True

            # Check leads table with session_id in concern
            cursor.execute(
                "SELECT phone_number FROM leads WHERE concern LIKE %s",
                (f"%{session_id}%",)
            )
            lead_row = cursor.fetchone()
            cursor.close()
            conn.close()
            if lead_row and lead_row["phone_number"]:
                return True

            return False
        except Exception:
            return False

    def get_captured_info(self, session_id: str) -> Dict[str, Optional[str]]:
        """Retrieve already captured name and phone if available."""
        info = {"name": None, "phone": None}
        try:
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_name, user_phone FROM handoffs WHERE session_id = %s",
                (session_id,)
            )
            row = cursor.fetchone()
            if row:
                info["name"] = row["user_name"] if row["user_name"] != "Anonymous" else None
                info["phone"] = row["user_phone"]
            cursor.close()
            conn.close()
        except Exception:
            pass
        return info


session_manager = SessionManager()
