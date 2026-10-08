"""
Clinderma — Offers Management API
All /api/admin/offers/* endpoints require JWT admin auth.
GET /api/offers/active is public (used by chatbot to inject active offers).
"""

import json
import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.auth import require_role, get_current_user
from app.core.db import get_conn

router = APIRouter()


class OfferCreate(BaseModel):
    name: str
    discount_code: Optional[str] = ""
    discount_type: str = "percentage"          # 'percentage' | 'flat_amount'
    discount_value: float = 0.0
    applicable_products: Optional[List[str]] = []
    conditions: Optional[dict] = {}
    start_date: str                             # ISO date string
    end_date: str


class OfferUpdate(BaseModel):
    name: Optional[str] = None
    discount_code: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    applicable_products: Optional[List[str]] = None
    conditions: Optional[dict] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None


def _compute_status(start_date: str, end_date: str, current_status: str) -> str:
    """Auto-compute offer status based on dates."""
    if current_status == "paused":
        return "paused"
    now = datetime.datetime.now().date().isoformat()
    if now < start_date:
        return "scheduled"
    elif start_date <= now <= end_date:
        return "active"
    else:
        return "expired"


def _log_audit(conn, action_type: str, entity_id: str, entity_name: str,
                old_val: str, new_val: str, performed_by: str):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_log (action_type, entity_id, entity_name, old_value, new_value, performed_by, performed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (action_type, str(entity_id), entity_name, old_val, new_val, performed_by, datetime.datetime.now().isoformat()))
    cursor.close()


# ─── Public endpoint ───────────────────────────────────────────────────────────

@router.get("/offers/active")
def get_active_offers():
    """Public: Returns currently active offers for chatbot context injection."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.datetime.now().date().isoformat()
    cursor.execute("""
        SELECT id, name, discount_code, discount_type, discount_value,
               applicable_products, conditions, start_date, end_date
        FROM offers
        WHERE start_date <= %s AND end_date >= %s AND status != 'paused'
    """, (now, now))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    offers = []
    for r in rows:
        d = dict(r)
        try:
            d["applicable_products"] = json.loads(d.get("applicable_products") or "[]")
        except Exception:
            d["applicable_products"] = []
        try:
            d["conditions"] = json.loads(d.get("conditions") or "{}")
        except Exception:
            d["conditions"] = {}
        offers.append(d)
    return {"offers": offers, "count": len(offers)}


# ─── Admin endpoints ───────────────────────────────────────────────────────────

@router.get("/admin/offers")
def list_offers(user: dict = Depends(require_role("admin", "doctor", "viewer"))):
    """List all offers with auto-computed status."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM offers ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        try:
            d["applicable_products"] = json.loads(d.get("applicable_products") or "[]")
        except Exception:
            d["applicable_products"] = []
        try:
            d["conditions"] = json.loads(d.get("conditions") or "{}")
        except Exception:
            d["conditions"] = {}
        # Auto-update computed status
        if d.get("start_date") and d.get("end_date"):
            d["status"] = _compute_status(d["start_date"], d["end_date"], d.get("status", "scheduled"))
        result.append(d)
    return {"offers": result, "count": len(result)}


@router.post("/admin/offers")
def create_offer(req: OfferCreate, user: dict = Depends(require_role("admin"))):
    """Create a new offer."""
    conn = get_conn()
    now_str = datetime.datetime.now().isoformat()
    status = _compute_status(req.start_date, req.end_date, "scheduled")

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO offers (name, discount_code, discount_type, discount_value,
                            applicable_products, conditions, start_date, end_date,
                            status, created_by, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        req.name, req.discount_code, req.discount_type, req.discount_value,
        json.dumps(req.applicable_products or []),
        json.dumps(req.conditions or {}),
        req.start_date, req.end_date,
        status, user["username"], now_str
    ))
    new_id = cursor.lastrowid
    conn.commit()

    _log_audit(conn, "offer_create", str(new_id), req.name, "", req.name, user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "created", "id": new_id, "offer_status": status}


@router.put("/admin/offers/{offer_id}")
def update_offer(offer_id: int, req: OfferUpdate, user: dict = Depends(require_role("admin"))):
    """Update an existing offer."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM offers WHERE id = %s", (offer_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Offer not found.")

    old = dict(row)
    updates = {}
    if req.name is not None: updates["name"] = req.name
    if req.discount_code is not None: updates["discount_code"] = req.discount_code
    if req.discount_type is not None: updates["discount_type"] = req.discount_type
    if req.discount_value is not None: updates["discount_value"] = req.discount_value
    if req.applicable_products is not None: updates["applicable_products"] = json.dumps(req.applicable_products)
    if req.conditions is not None: updates["conditions"] = json.dumps(req.conditions)
    if req.start_date is not None: updates["start_date"] = req.start_date
    if req.end_date is not None: updates["end_date"] = req.end_date
    if req.status is not None: updates["status"] = req.status

    if not updates:
        cursor.close()
        conn.close()
        return {"status": "no_changes"}

    set_clause = ", ".join([f"{k} = %s" for k in updates])
    vals = list(updates.values()) + [offer_id]
    cursor.execute(f"UPDATE offers SET {set_clause} WHERE id = %s", vals)
    conn.commit()

    _log_audit(conn, "offer_update", str(offer_id), old.get("name", ""), str(old), str(updates), user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "updated", "id": offer_id}


@router.patch("/admin/offers/{offer_id}/pause")
def pause_offer(offer_id: int, user: dict = Depends(require_role("admin"))):
    """Toggle pause/unpause on an offer."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT status, name, start_date, end_date FROM offers WHERE id = %s", (offer_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Offer not found.")

    d = dict(row)
    if d["status"] == "paused":
        new_status = _compute_status(d["start_date"], d["end_date"], "active")
    else:
        new_status = "paused"

    cursor.execute("UPDATE offers SET status = %s WHERE id = %s", (new_status, offer_id))
    conn.commit()
    _log_audit(conn, "offer_pause_toggle", str(offer_id), d["name"], d["status"], new_status, user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": new_status, "id": offer_id}


@router.delete("/admin/offers/{offer_id}")
def delete_offer(offer_id: int, user: dict = Depends(require_role("admin"))):
    """Delete an offer."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM offers WHERE id = %s", (offer_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Offer not found.")

    name = dict(row)["name"]
    cursor.execute("DELETE FROM offers WHERE id = %s", (offer_id,))
    conn.commit()
    _log_audit(conn, "offer_delete", str(offer_id), name, name, "", user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "deleted", "id": offer_id}
