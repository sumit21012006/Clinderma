import traceback
import datetime
from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import ChatRequest, ChatResponse
from app.services.rag_engine import rag_engine
from app.core.rate_limiter import rate_limit_chat

router = APIRouter()


def _emit_funnel_event(session_id: str, event_type: str, metadata: dict = {}):
    """Fire-and-forget funnel event write."""
    try:
        import json
        from app.core.db import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO funnel_events (session_id, event_type, metadata, created_at)
            VALUES (%s, %s, %s, %s)
        """, (session_id, event_type, json.dumps(metadata), datetime.datetime.now().isoformat()))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass  # Never block chat for analytics errors


def _is_session_taken_over(session_id: str) -> bool:
    """Check if an admin has taken over this session (bot should be silent)."""
    try:
        from app.core.db import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT takeover_by FROM handoffs WHERE session_id = %s AND takeover_by IS NOT NULL",
            (session_id,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row is not None
    except Exception:
        return False


def _get_active_offers_text() -> str:
    """Get currently active offers to inject into chatbot context."""
    try:
        import json
        now = datetime.datetime.now().date().isoformat()
        from app.core.db import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, discount_code, discount_type, discount_value, conditions, end_date
            FROM offers
            WHERE start_date <= %s AND end_date >= %s AND status != 'paused'
        """, (now, now))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        if not rows:
            return ""
        lines = []
        for r in rows:
            d = dict(r)
            val = f"{d['discount_value']}%" if d["discount_type"] == "percentage" else f"₹{d['discount_value']}"
            code = f" (Code: {d['discount_code']})" if d.get("discount_code") else ""
            lines.append(f"- {d['name']}: {val} off{code}, valid until {d['end_date']}")
        return "ACTIVE OFFERS:\n" + "\n".join(lines)
    except Exception:
        return ""


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit_chat)])
def handle_chat(req: ChatRequest):
    # ── Takeover check: if admin has taken over, suppress bot ──────────────────
    if _is_session_taken_over(req.session_id):
        return ChatResponse(
            answer="",
            grounded=False,
            confidence=0.0,
            handoff_recommended=False,
            language=req.language or "en",
            session_id=req.session_id,
            suggested_questions=[],
        )

    # ── Funnel: track message_sent event ──────────────────────────────────────
    _emit_funnel_event(req.session_id, "message_sent", {"channel": req.channel})

    # ── Inject active offers into the request context ─────────────────────────
    offers_text = _get_active_offers_text()
    if offers_text and hasattr(req, "__dict__"):
        # Store on the request object so rag_engine can pick it up if it checks
        req.__dict__["_offers_context"] = offers_text

    try:
        res = rag_engine.process_chat(req)

        # ── Funnel: if phone was captured, mark lead_captured stage ───────────
        if res.get("captured_phone"):
            _emit_funnel_event(req.session_id, "lead_captured",
                               {"phone": res["captured_phone"]})

        return ChatResponse(**res)
    except Exception as e:
        print(f"[Chat API Error]: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
