import json
import datetime
from typing import List, Dict, Any, Optional
from app.core.db import get_conn


class HandoffManager:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS handoffs (
                session_id TEXT PRIMARY KEY,
                user_name TEXT,
                user_phone TEXT,
                reason TEXT,
                channel TEXT,
                status TEXT DEFAULT 'pending',
                severity TEXT DEFAULT 'moderate',
                doctor_notes TEXT DEFAULT '',
                ai_summary TEXT DEFAULT '',
                created_at TEXT
            )
        """)
        # Safe migration for existing SQLite / Postgres tables
        for col_def in [
            ("severity", "TEXT DEFAULT 'moderate'"),
            ("doctor_notes", "TEXT DEFAULT ''"),
            ("ai_summary", "TEXT DEFAULT ''"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE handoffs ADD COLUMN {col_def[0]} {col_def[1]}")
                conn.commit()
            except Exception:
                pass

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
        conn.close()

    def add_transcript(self, session_id: str, sender: str, message: str):
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transcripts (session_id, sender, message, timestamp)
            VALUES (%s, %s, %s, %s)
        """, (session_id, sender, message, datetime.datetime.now().isoformat()))
        conn.commit()
        cursor.close()
        conn.close()

    def update_user_contact(self, session_id: str, user_name: Optional[str] = None, user_phone: Optional[str] = None):
        """Update contact info on an existing handoff record or initialize it."""
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT session_id, user_name, user_phone FROM handoffs WHERE session_id = %s", (session_id,))
        row = cursor.fetchone()

        if row:
            new_name = user_name if user_name and user_name != "Anonymous" else row["user_name"]
            new_phone = user_phone if user_phone else row["user_phone"]
            cursor.execute("""
                UPDATE handoffs SET user_name = %s, user_phone = %s WHERE session_id = %s
            """, (new_name, new_phone, session_id))
        else:
            created_at = datetime.datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO handoffs (session_id, user_name, user_phone, reason, channel, status, severity, doctor_notes, ai_summary, created_at)
                VALUES (%s, %s, %s, 'Lead Captured in Chat', 'website', 'pending', 'routine', '', '', %s)
            """, (session_id, user_name or "Anonymous", user_phone or "", created_at))

        conn.commit()
        cursor.close()
        conn.close()

    def create_handoff(
        self, session_id: str, user_name: str = "Anonymous", user_phone: Optional[str] = None,
        reason: str = "Human Agent Request", channel: str = "website",
        severity: str = "moderate", ai_summary: str = ""
    ) -> Dict[str, Any]:
        created_at = datetime.datetime.now().isoformat()
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO handoffs (session_id, user_name, user_phone, reason, channel, status, severity, doctor_notes, ai_summary, created_at)
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, '', %s, %s)
            ON CONFLICT (session_id) DO UPDATE
                SET user_name = EXCLUDED.user_name,
                    user_phone = EXCLUDED.user_phone,
                    reason = EXCLUDED.reason,
                    channel = EXCLUDED.channel,
                    status = 'pending',
                    severity = EXCLUDED.severity,
                    ai_summary = EXCLUDED.ai_summary,
                    created_at = EXCLUDED.created_at
        """, (session_id, user_name, user_phone, reason, channel, severity, ai_summary, created_at))
        conn.commit()
        cursor.close()
        conn.close()

        print(f"[HANDOFF] Escalated session {session_id} to Skin Coach: {reason} [{severity}]")
        return {
            "session_id": session_id,
            "status": "ESCALATED_TO_SKIN_COACH",
            "message": "Connected with human support queue. A Skin Coach will join shortly.",
            "created_at": created_at
        }

    def get_all_handoffs(self) -> List[Dict[str, Any]]:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM handoffs ORDER BY created_at DESC")
        rows = cursor.fetchall()

        handoffs = []
        for r in rows:
            sid = r["session_id"]
            cursor.execute(
                "SELECT sender, message, timestamp FROM transcripts WHERE session_id = %s ORDER BY id ASC",
                (sid,)
            )
            t_rows = cursor.fetchall()
            transcript = [{"sender": t["sender"], "message": t["message"], "timestamp": t["timestamp"]} for t in t_rows]

            # Safely extract optional columns
            r_dict = dict(r)
            handoffs.append({
                "session_id": sid,
                "user_name": r_dict.get("user_name"),
                "user_phone": r_dict.get("user_phone"),
                "reason": r_dict.get("reason"),
                "channel": r_dict.get("channel"),
                "status": r_dict.get("status") or "pending",
                "severity": r_dict.get("severity") or "moderate",
                "doctor_notes": r_dict.get("doctor_notes") or "",
                "ai_summary": r_dict.get("ai_summary") or "",
                "created_at": r_dict.get("created_at"),
                "transcript": transcript
            })
        cursor.close()
        conn.close()
        return handoffs

    def add_doctor_note(self, session_id: str, note: str):
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE handoffs SET doctor_notes = %s WHERE session_id = %s", (note, session_id))
        conn.commit()
        cursor.close()
        conn.close()

    def resolve_handoff(self, session_id: str, doctor_notes: Optional[str] = None):
        conn = get_conn()
        cursor = conn.cursor()
        if doctor_notes is not None:
            cursor.execute("UPDATE handoffs SET status = 'resolved', doctor_notes = %s WHERE session_id = %s", (doctor_notes, session_id))
        else:
            cursor.execute("UPDATE handoffs SET status = 'resolved' WHERE session_id = %s", (session_id,))
        conn.commit()
        cursor.close()
        conn.close()


handoff_manager = HandoffManager()
