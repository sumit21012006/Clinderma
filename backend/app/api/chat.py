import traceback
import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from app.models.schemas import ChatRequest, ChatResponse
from app.services.rag_engine import rag_engine
from app.services.handoff_manager import handoff_manager
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


@router.get("/chat/{session_id}/updates")
def get_live_chat_updates(session_id: str, after_id: int = Query(0, ge=0)):
    """Return customer-safe admin and system updates for a chat session."""
    try:
        from app.core.db import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, sender, message, timestamp
            FROM transcripts
            WHERE session_id = %s
              AND id > %s
              AND (sender = 'system' OR sender LIKE 'admin:%%')
            ORDER BY id ASC
        """, (session_id, after_id))
        updates = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return {
            "taken_over": _is_session_taken_over(session_id),
            "updates": updates,
            "last_id": updates[-1]["id"] if updates else after_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Unable to retrieve live chat updates") from e


def _get_active_offers() -> list[dict]:
    """Return active offers as structured, authoritative chat context."""
    try:
        import json
        now = datetime.datetime.now().date().isoformat()
        from app.core.db import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, discount_code, discount_type, discount_value,
                   applicable_products, conditions, end_date
            FROM offers
            WHERE start_date <= %s AND end_date >= %s AND status != 'paused'
        """, (now, now))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        offers = []
        for r in rows:
            d = dict(r)
            for field, default in (("applicable_products", []), ("conditions", {})):
                try:
                    d[field] = json.loads(d.get(field) or ("[]" if isinstance(default, list) else "{}"))
                except (TypeError, ValueError):
                    d[field] = default
            offers.append(d)
        return offers
    except Exception:
        return []


def _get_active_offers_text(offers: list[dict]) -> str:
    """Provide a readable representation for backwards-compatible chat context."""
    if not offers:
        return ""
    lines = []
    for offer in offers:
        value = f"{offer['discount_value']}%" if offer["discount_type"] == "percentage" else f"₹{offer['discount_value']}"
        code = f" (Code: {offer['discount_code']})" if offer.get("discount_code") else ""
        lines.append(f"- {offer['name']}: {value} off{code}, valid until {offer['end_date']}")
    return "ACTIVE OFFERS:\n" + "\n".join(lines)


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit_chat)])
def handle_chat(req: ChatRequest):
    # ── Takeover check: if admin has taken over, suppress bot ──────────────────
    if _is_session_taken_over(req.session_id):
        # Keep the bot quiet, while preserving customer messages for the
        # administrator who is handling this session.
        handoff_manager.add_transcript(req.session_id, "user", req.message)
        _emit_funnel_event(req.session_id, "message_sent", {"channel": req.channel, "handled_by": "admin"})
        return ChatResponse(
            answer="",
            grounded=False,
            confidence=0.0,
            handoff_recommended=False,
            language=req.language or "en",
            session_id=req.session_id,
            suggested_questions=[],
            taken_over=True,
        )

    # ── Funnel: track message_sent event ──────────────────────────────────────
    _emit_funnel_event(req.session_id, "message_sent", {"channel": req.channel})

    # ── Inject active offers into the request context ─────────────────────────
    active_offers = _get_active_offers()
    offers_text = _get_active_offers_text(active_offers)
    if active_offers and hasattr(req, "__dict__"):
        # Keep structured data for reliable product matching; text supports any
        # future prompt-based offer flow without another database query.
        req.__dict__["_active_offers"] = active_offers
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
