"""
Clinderma Session Manager — Conversation Memory & State Tracking

Maintains:
  1. Multi-turn sliding window conversation history for LLM context.
  2. Per-session turn count tracking for natural lead timing (turns 2-3).
  3. Lead capture verification (ensuring users are not repeatedly asked for info).
"""

import datetime
from typing import List, Dict, Any, Optional
from app.core.db import get_conn
from app.core.config import settings


class SessionManager:
    """Manages per-session conversation history and state for multi-turn conversational AI."""

    INACTIVITY_PROMPT_SECONDS = 120
    INACTIVITY_END_SECONDS = 30
    INACTIVITY_END_MESSAGE = (
        "This chat has ended due to inactivity. Start a new chat whenever you need help."
    )

    @staticmethod
    def _ensure_state_table(conn) -> None:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_session_state (
                session_id TEXT PRIMARY KEY,
                phone_required BOOLEAN NOT NULL DEFAULT FALSE,
                chat_status TEXT NOT NULL DEFAULT 'live',
                last_activity_at TEXT,
                last_user_activity_at TEXT,
                inactivity_prompted_at TEXT,
                ended_at TEXT
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

    def touch_session(self, session_id: str, user_activity: bool = True) -> None:
        """Record activity while tracking customer presence independently."""
        now = datetime.datetime.now().isoformat()
        user_activity_at = now if user_activity else None
        conn = get_conn()
        try:
            self._ensure_state_table(conn)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_session_state (
                    session_id, phone_required, chat_status, last_activity_at,
                    last_user_activity_at, inactivity_prompted_at, ended_at
                )
                VALUES (%s, FALSE, 'live', %s, %s, NULL, NULL)
                ON CONFLICT (session_id) DO UPDATE
                SET chat_status = 'live',
                    last_activity_at = EXCLUDED.last_activity_at,
                    last_user_activity_at = COALESCE(
                        EXCLUDED.last_user_activity_at,
                        chat_session_state.last_user_activity_at
                    ),
                    inactivity_prompted_at = NULL,
                    ended_at = NULL
            """, (session_id, now, user_activity_at))
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    def mark_awaiting_confirmation(self, session_id: str) -> Dict[str, Any]:
        """Mark that the two-minute inactivity continuation prompt was sent."""
        now = datetime.datetime.now().isoformat()
        conn = get_conn()
        try:
            self._ensure_state_table(conn)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_session_state (
                    session_id, phone_required, chat_status, last_activity_at,
                    inactivity_prompted_at, ended_at
                )
                VALUES (%s, FALSE, 'awaiting_confirmation', %s, %s, NULL)
                ON CONFLICT (session_id) DO UPDATE
                SET chat_status = 'awaiting_confirmation',
                    inactivity_prompted_at = EXCLUDED.inactivity_prompted_at,
                    ended_at = NULL
            """, (session_id, now, now))
            conn.commit()
            cursor.close()
        finally:
            conn.close()
        return self.get_session_state(session_id, reconcile=False)

    def end_session(
        self,
        session_id: str,
        system_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """End a chat session while leaving its clinical ticket state untouched."""
        now = datetime.datetime.now().isoformat()
        conn = get_conn()
        try:
            self._ensure_state_table(conn)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT chat_status FROM chat_session_state WHERE session_id = %s",
                (session_id,),
            )
            existing = cursor.fetchone()
            was_ended = bool(existing and dict(existing).get("chat_status") == "ended")
            cursor.execute("""
                INSERT INTO chat_session_state (
                    session_id, phone_required, chat_status, last_activity_at,
                    inactivity_prompted_at, ended_at
                )
                VALUES (%s, FALSE, 'ended', %s, NULL, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET chat_status = 'ended',
                    ended_at = EXCLUDED.ended_at
            """, (session_id, now, now))
            if system_message and not was_ended:
                cursor.execute("""
                    INSERT INTO transcripts (session_id, sender, message, timestamp)
                    VALUES (%s, 'system', %s, %s)
                """, (session_id, system_message, now))
            conn.commit()
            cursor.close()
        finally:
            conn.close()
        return self.get_session_state(session_id, reconcile=False)

    @staticmethod
    def _parse_timestamp(value: Optional[str]) -> Optional[datetime.datetime]:
        if not value:
            return None
        try:
            return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except (TypeError, ValueError):
            return None

    def get_session_state(self, session_id: str, reconcile: bool = True) -> Dict[str, Any]:
        """Return persisted lifecycle state and derive stale/expired presence."""
        conn = get_conn()
        try:
            self._ensure_state_table(conn)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chat_status, last_activity_at, last_user_activity_at,
                       inactivity_prompted_at, ended_at
                FROM chat_session_state
                WHERE session_id = %s
            """, (session_id,))
            row = cursor.fetchone()
            cursor.close()
        finally:
            conn.close()

        if not row:
            return {
                "status": "new",
                "last_activity_at": None,
                "last_user_activity_at": None,
                "inactivity_prompted_at": None,
                "ended_at": None,
            }

        state = dict(row)
        status = state.get("chat_status") or "ended"
        now = datetime.datetime.now()
        last_activity = self._parse_timestamp(
            state.get("last_user_activity_at") or state.get("last_activity_at")
        )
        prompted_at = self._parse_timestamp(state.get("inactivity_prompted_at"))

        if reconcile and status == "awaiting_confirmation" and prompted_at:
            if (now - prompted_at).total_seconds() >= self.INACTIVITY_END_SECONDS:
                return self.end_session(
                    session_id,
                    system_message=self.INACTIVITY_END_MESSAGE,
                )
        elif status == "live" and last_activity:
            if (now - last_activity).total_seconds() >= self.INACTIVITY_PROMPT_SECONDS:
                status = "idle"

        return {
            "status": status,
            "last_activity_at": state.get("last_activity_at"),
            "last_user_activity_at": state.get("last_user_activity_at"),
            "inactivity_prompted_at": state.get("inactivity_prompted_at"),
            "ended_at": state.get("ended_at"),
        }

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
