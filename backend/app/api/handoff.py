"""
Clinderma — Human Handoff API
Handles escalation queue, doctor notes, resolve, takeover, and handback.
"""
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.services.handoff_manager import handoff_manager
from app.services.session_manager import session_manager
from app.core.auth import require_role

router = APIRouter()


class ResolveRequest(BaseModel):
    session_id: str
    doctor_notes: Optional[str] = None


class NoteRequest(BaseModel):
    session_id: str
    doctor_notes: str


class TakeoverRequest(BaseModel):
    session_id: str


class AdminMessageRequest(BaseModel):
    session_id: str
    message: str


# ─── Existing endpoints (unchanged) ──────────────────────────────────────────

@router.get("/handoff")
def get_handoffs(_user: dict = Depends(require_role("doctor", "admin"))):
    """
    Protected endpoint: returns all human escalation tickets for the clinical dashboard.
    """
    handoffs = handoff_manager.get_all_handoffs()
    return {"handoffs": handoffs, "count": len(handoffs)}


@router.post("/handoff/resolve")
def resolve_handoff(req: ResolveRequest, _user: dict = Depends(require_role("doctor", "admin"))):
    """
    Protected endpoint: resolves an escalation ticket.
    """
    handoff_manager.resolve_handoff(req.session_id, doctor_notes=req.doctor_notes)
    return {"status": "success", "session_id": req.session_id}


@router.post("/handoff/note")
def save_doctor_note(req: NoteRequest, _user: dict = Depends(require_role("doctor", "admin"))):
    """
    Protected endpoint: saves clinical observations/notes on an escalation ticket.
    """
    handoff_manager.add_doctor_note(req.session_id, req.doctor_notes)
    return {"status": "success", "session_id": req.session_id, "note": req.doctor_notes}


# ─── New PRD endpoints (JWT auth) ─────────────────────────────────────────────

@router.get("/admin/chats")
def get_all_chats(
    status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime.date] = None,
    date_to: Optional[datetime.date] = None,
    user: dict = Depends(require_role("admin", "doctor", "viewer"))
):
    """
    JWT-protected: Returns ALL chat sessions (escalated + general), newest first.
    Supports status filter: 'live' | 'ended' | 'escalated' | 'takeover',
    text search by customer name/phone, and an inclusive chat-start date range.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=400,
            detail="date_from must be on or before date_to",
        )

    from app.core.db import get_conn
    conn = get_conn()
    cursor = conn.cursor()

    query = """
        SELECT sessions.session_id,
               COALESCE(h.user_name, 'Anonymous') AS user_name,
               h.user_phone,
               COALESCE(h.reason, 'General chat') AS reason,
               COALESCE(h.channel, 'website') AS channel,
               COALESCE(h.status, 'unassigned') AS status,
               COALESCE(h.severity, 'routine') AS severity,
               COALESCE(h.doctor_notes, '') AS doctor_notes,
               COALESCE(h.ai_summary, '') AS ai_summary,
               h.takeover_by,
               COALESCE(t.started_at, h.created_at, s.last_activity_at) AS created_at
        FROM (
            SELECT session_id FROM chat_session_state
            UNION
            SELECT session_id FROM handoffs
        ) sessions
        LEFT JOIN chat_session_state s ON s.session_id = sessions.session_id
        LEFT JOIN handoffs h ON h.session_id = sessions.session_id
        LEFT JOIN (
            SELECT session_id, MIN(timestamp) AS started_at
            FROM transcripts
            GROUP BY session_id
        ) t ON t.session_id = sessions.session_id
        WHERE 1=1
    """
    params = []

    if status == "takeover":
        query += " AND h.takeover_by IS NOT NULL"

    chat_started_at = "COALESCE(t.started_at, h.created_at, s.last_activity_at)"
    if date_from:
        query += f" AND {chat_started_at} >= %s"
        params.append(date_from.isoformat())
    if date_to:
        # An exclusive next-day boundary includes every time on date_to and
        # works for both SQLite and Postgres ISO timestamps.
        query += f" AND {chat_started_at} < %s"
        params.append((date_to + datetime.timedelta(days=1)).isoformat())

    query += " ORDER BY COALESCE(s.last_activity_at, h.created_at) DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        sid = d["session_id"]

        # Get transcript
        cursor.execute(
            "SELECT sender, message, timestamp FROM transcripts WHERE session_id = %s ORDER BY id ASC",
            (sid,)
        )
        t_rows = cursor.fetchall()
        transcript = [{"sender": t["sender"], "message": t["message"], "timestamp": t["timestamp"]}
                      for t in t_rows]

        d["transcript"] = transcript
        lifecycle = session_manager.get_session_state(sid)
        d["chat_status"] = lifecycle["status"]
        d["last_activity_at"] = lifecycle["last_activity_at"]
        d["is_live"] = lifecycle["status"] == "live"
        d["is_taken_over"] = bool(d.get("takeover_by"))
        d["is_escalated"] = (
            d.get("severity") in ("critical", "moderate")
            and not str(d.get("reason") or "").lower().startswith("lead captured")
        )
        d["message_count"] = len(transcript)

        if status == "live" and not d["is_live"]:
            continue
        if status == "ended" and lifecycle["status"] not in ("ended", "expired"):
            continue
        if status == "escalated" and not d["is_escalated"]:
            continue

        # Apply search filter
        if search:
            s = search.lower()
            name_match = s in (d.get("user_name") or "").lower()
            phone_match = s in (d.get("user_phone") or "").lower()
            if not (name_match or phone_match):
                continue

        results.append(d)

    cursor.close()
    conn.close()
    return {"chats": results, "count": len(results)}


@router.post("/admin/chats/takeover")
def take_over_chat(req: TakeoverRequest, user: dict = Depends(require_role("admin"))):
    """
    Admin/Doctor takes over a live chat session.
    The chatbot will be silenced for this session_id.
    """
    from app.core.db import get_conn
    conn = get_conn()
    cursor = conn.cursor()

    # Ensure the handoff record exists
    cursor.execute("SELECT session_id, status FROM handoffs WHERE session_id = %s", (req.session_id,))
    row = cursor.fetchone()

    if not row:
        # Create a minimal handoff record for sessions not yet escalated
        now = datetime.datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO handoffs (session_id, user_name, user_phone, reason, channel, status, severity, takeover_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (req.session_id, "Unknown", None, "Admin takeover", "website",
              "pending", "moderate", user["username"], now))
    else:
        cursor.execute(
            "UPDATE handoffs SET takeover_by = %s, status = 'pending' WHERE session_id = %s",
            (user["username"], req.session_id)
        )

    conn.commit()
    session_manager.touch_session(req.session_id, user_activity=False)

    # Log the admin "took over" message in transcript
    cursor.execute("""
        INSERT INTO transcripts (session_id, sender, message, timestamp)
        VALUES (%s, %s, %s, %s)
    """, (req.session_id, "system",
          f"🛡️ {user['username']} (Admin) has taken over this chat. Bot is paused.",
          datetime.datetime.now().isoformat()))
    conn.commit()

    # Audit log
    cursor.execute("""
        INSERT INTO audit_log (action_type, entity_id, entity_name, old_value, new_value, performed_by, performed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ("chat_takeover", req.session_id, req.session_id, "bot", user["username"],
          user["username"], datetime.datetime.now().isoformat()))
    conn.commit()
    cursor.close()
    conn.close()

    return {
        "status": "taken_over",
        "session_id": req.session_id,
        "by": user["username"],
        "message": "Bot is paused for this session. You can now type directly to the customer.",
    }


@router.post("/admin/chats/handback")
def hand_back_to_bot(req: TakeoverRequest, user: dict = Depends(require_role("admin"))):
    """
    Hand the chat back to the chatbot after admin takeover.
    """
    from app.core.db import get_conn
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE handoffs SET takeover_by = NULL WHERE session_id = %s",
        (req.session_id,)
    )
    conn.commit()

    # Log handback in transcript
    cursor.execute("""
        INSERT INTO transcripts (session_id, sender, message, timestamp)
        VALUES (%s, %s, %s, %s)
    """, (req.session_id, "system",
          f"🤖 Chat handed back to AI chatbot by {user['username']}.",
          datetime.datetime.now().isoformat()))
    conn.commit()

    # Audit log
    cursor.execute("""
        INSERT INTO audit_log (action_type, entity_id, entity_name, old_value, new_value, performed_by, performed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, ("chat_handback", req.session_id, req.session_id, user["username"], "bot",
          user["username"], datetime.datetime.now().isoformat()))
    conn.commit()
    session_manager.touch_session(req.session_id, user_activity=False)
    cursor.close()
    conn.close()

    return {
        "status": "handed_back",
        "session_id": req.session_id,
        "message": "Bot has resumed handling this chat session.",
    }


@router.post("/admin/chats/message")
def send_admin_message(req: AdminMessageRequest, user: dict = Depends(require_role("admin"))):
    """
    Send a direct message from admin to customer (while in takeover mode).
    Saves to transcript with sender='admin'.
    """
    from app.core.db import get_conn
    conn = get_conn()
    cursor = conn.cursor()

    # Verify takeover is active
    cursor.execute(
        "SELECT takeover_by FROM handoffs WHERE session_id = %s AND takeover_by IS NOT NULL",
        (req.session_id,)
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="This session is not in takeover mode. Use /admin/chats/takeover first."
        )

    cursor.execute("""
        INSERT INTO transcripts (session_id, sender, message, timestamp)
        VALUES (%s, %s, %s, %s)
    """, (req.session_id, f"admin:{user['username']}", req.message, datetime.datetime.now().isoformat()))
    conn.commit()
    session_manager.touch_session(req.session_id, user_activity=False)
    cursor.close()
    conn.close()

    return {
        "status": "sent",
        "session_id": req.session_id,
        "sender": user["username"],
        "message": req.message,
    }
