import sqlite3
import json
import datetime
from typing import List, Dict, Any, Optional
from app.core.config import settings

class HandoffManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DB_PATH
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, timeout=30.0)

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS handoffs (
                session_id TEXT PRIMARY KEY,
                user_name TEXT,
                user_phone TEXT,
                reason TEXT,
                channel TEXT,
                status TEXT DEFAULT 'pending',
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
        conn.commit()
        conn.close()

    def add_transcript(self, session_id: str, sender: str, message: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transcripts (session_id, sender, message, timestamp)
            VALUES (?, ?, ?, ?)
        """, (session_id, sender, message, datetime.datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def update_user_contact(self, session_id: str, user_name: Optional[str] = None, user_phone: Optional[str] = None):
        """Update contact info on an existing handoff record or initialize it."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT session_id, user_name, user_phone FROM handoffs WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()

        if row:
            new_name = user_name if user_name and user_name != "Anonymous" else row[1]
            new_phone = user_phone if user_phone else row[2]
            cursor.execute("""
                UPDATE handoffs SET user_name = ?, user_phone = ? WHERE session_id = ?
            """, (new_name, new_phone, session_id))
        else:
            created_at = datetime.datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO handoffs (session_id, user_name, user_phone, reason, channel, status, created_at)
                VALUES (?, ?, ?, 'Lead Captured in Chat', 'website', 'pending', ?)
            """, (session_id, user_name or "Anonymous", user_phone or "", created_at))

        conn.commit()
        conn.close()

    def create_handoff(
        self, session_id: str, user_name: str = "Anonymous", user_phone: Optional[str] = None, reason: str = "Human Agent Request", channel: str = "website"
    ) -> Dict[str, Any]:
        created_at = datetime.datetime.now().isoformat()
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO handoffs (session_id, user_name, user_phone, reason, channel, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """, (session_id, user_name, user_phone, reason, channel, created_at))
        conn.commit()
        conn.close()

        print(f"[HANDOFF] Escalated session {session_id} to Skin Coach: {reason}")
        return {
            "session_id": session_id,
            "status": "ESCALATED_TO_SKIN_COACH",
            "message": "Connected with human support queue. A Skin Coach will join shortly.",
            "created_at": created_at
        }

    def get_all_handoffs(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM handoffs ORDER BY created_at DESC")
        rows = cursor.fetchall()

        handoffs = []
        for r in rows:
            sid = r["session_id"]
            cursor.execute("SELECT sender, message, timestamp FROM transcripts WHERE session_id = ? ORDER BY id ASC", (sid,))
            t_rows = cursor.fetchall()
            transcript = [{"sender": t["sender"], "message": t["message"], "timestamp": t["timestamp"]} for t in t_rows]

            handoffs.append({
                "session_id": sid,
                "user_name": r["user_name"],
                "user_phone": r["user_phone"],
                "reason": r["reason"],
                "channel": r["channel"],
                "status": r["status"],
                "created_at": r["created_at"],
                "transcript": transcript
            })
        conn.close()
        return handoffs

    def resolve_handoff(self, session_id: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE handoffs SET status = 'resolved' WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()

handoff_manager = HandoffManager()
