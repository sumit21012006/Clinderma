"""
Clinderma — Analytics API
Provides chatbot funnel metrics and orders/revenue analytics.

GET /api/admin/analytics/funnel       → 6-stage funnel with drop-offs
GET /api/admin/analytics/orders       → orders & revenue by Daily/Weekly/Monthly
GET /api/admin/analytics/export       → CSV export of analytics data
POST /api/analytics/visit             → public pixel endpoint for visitor tracking
POST /api/analytics/event             → public endpoint for funnel event tracking
"""

import json
import datetime
import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.core.auth import require_role
from app.core.db import get_conn

router = APIRouter()


# ─── Public tracking endpoints ────────────────────────────────────────────────

class EventRequest:
    pass

from pydantic import BaseModel

class TrackEvent(BaseModel):
    session_id: Optional[str] = ""
    event_type: str   # 'visitor'|'chat_opened'|'message_sent'|'lead_captured'|'checkout_initiated'|'order_placed'
    metadata: Optional[dict] = {}


@router.post("/analytics/visit")
def track_visit(session_id: Optional[str] = ""):
    """Public pixel: called by index.html on every page load to track visitors."""
    _emit_event(session_id or "", "visitor", {})
    return {"ok": True}


@router.post("/analytics/event")
def track_event(req: TrackEvent):
    """Public: track any funnel stage event from the frontend widget."""
    _emit_event(req.session_id or "", req.event_type, req.metadata or {})
    return {"ok": True}


def _emit_event(session_id: str, event_type: str, metadata: dict):
    """Internal helper to write a funnel event to the DB."""
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO funnel_events (session_id, event_type, metadata, created_at)
            VALUES (%s, %s, %s, %s)
        """, (session_id, event_type, json.dumps(metadata), datetime.datetime.now().isoformat()))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[Analytics] Event tracking error: {e}")


# ─── Funnel analytics ─────────────────────────────────────────────────────────

FUNNEL_STAGES = [
    ("visitor",             "Visitors"),
    ("chat_opened",         "Opened chat"),
    ("message_sent",        "Started chat"),
    ("lead_captured",       "Engaged"),
    ("checkout_initiated",  "Added to cart"),
    ("order_placed",        "Converted"),
]


def _funnel_data(date_from: Optional[str], date_to: Optional[str]) -> dict:
    conn = get_conn()
    cursor = conn.cursor()

    stage_counts = {}
    for event_type, label in FUNNEL_STAGES:
        query = "SELECT COUNT(DISTINCT session_id) as cnt FROM funnel_events WHERE event_type = %s"
        params = [event_type]
        if date_from:
            query += " AND created_at >= %s"
            params.append(date_from)
        if date_to:
            query += " AND created_at <= %s"
            params.append(date_to + "T23:59:59")
        cursor.execute(query, params)
        row = cursor.fetchone()
        stage_counts[event_type] = row["cnt"] if row else 0

    cursor.close()
    conn.close()

    # Build funnel with drop-off
    funnel = []
    prev_count = None
    for event_type, label in FUNNEL_STAGES:
        count = stage_counts[event_type]
        if prev_count is None or prev_count == 0:
            dropoff_pct = 0.0
        else:
            dropoff_pct = round((1 - count / prev_count) * 100, 1)
        funnel.append({
            "stage": event_type,
            "label": label,
            "count": count,
            "dropoff_percent": dropoff_pct,
        })
        prev_count = count

    # Non-openers: visitors who never opened chat
    visitors = stage_counts.get("visitor", 0)
    opened = stage_counts.get("chat_opened", 0)
    non_openers = max(visitors - opened, 0)
    non_opener_pct = round((non_openers / max(visitors, 1)) * 100, 1)

    return {
        "funnel": funnel,
        "non_openers": non_openers,
        "non_opener_percent": non_opener_pct,
        "date_from": date_from,
        "date_to": date_to,
    }


@router.get("/admin/analytics/funnel")
def get_funnel(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(require_role("admin", "doctor", "viewer"))
):
    """Return the 6-stage chatbot conversion funnel with drop-off percentages."""
    return _funnel_data(date_from, date_to)


# ─── Orders & Revenue analytics ───────────────────────────────────────────────

@router.get("/admin/analytics/orders")
def get_orders_analytics(
    view: str = "daily",           # 'daily' | 'weekly' | 'monthly'
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: dict = Depends(require_role("admin", "doctor", "viewer"))
):
    """
    Return orders and revenue from customers who chatted.
    Groups by view: daily | weekly | monthly.
    Falls back to funnel order_placed events for counts, leads table for revenue estimate.
    """
    conn = get_conn()
    cursor = conn.cursor()

    # Get order events from funnel_events
    query = "SELECT created_at, metadata FROM funnel_events WHERE event_type = 'order_placed'"
    params = []
    if date_from:
        query += " AND created_at >= %s"
        params.append(date_from)
    if date_to:
        query += " AND created_at <= %s"
        params.append(date_to + "T23:59:59")
    query += " ORDER BY created_at ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()

    # Aggregate by view
    aggregated = {}
    total_orders = 0
    total_revenue = 0.0

    for r in rows:
        d = dict(r)
        try:
            meta = json.loads(d.get("metadata") or "{}")
        except Exception:
            meta = {}

        order_value = float(meta.get("order_value", 0))
        ts = d["created_at"][:10]   # YYYY-MM-DD

        if view == "weekly":
            dt = datetime.date.fromisoformat(ts)
            week_start = dt - datetime.timedelta(days=dt.weekday())
            key = week_start.isoformat()
        elif view == "monthly":
            key = ts[:7]   # YYYY-MM
        else:
            key = ts       # YYYY-MM-DD

        if key not in aggregated:
            aggregated[key] = {"period": key, "orders": 0, "revenue": 0.0}
        aggregated[key]["orders"] += 1
        aggregated[key]["revenue"] += order_value
        total_orders += 1
        total_revenue += order_value

    # Sort by period
    timeline = sorted(aggregated.values(), key=lambda x: x["period"])

    # Round revenue
    for item in timeline:
        item["revenue"] = round(item["revenue"], 2)

    cursor.close()
    conn.close()

    return {
        "view": view,
        "date_from": date_from,
        "date_to": date_to,
        "total_orders": total_orders,
        "total_revenue": round(total_revenue, 2),
        "timeline": timeline,
    }


# ─── CSV Export ───────────────────────────────────────────────────────────────

@router.get("/admin/analytics/export")
def export_analytics(
    type: str = "funnel",    # 'funnel' | 'orders'
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    view: str = "daily",
    user: dict = Depends(require_role("admin", "doctor", "viewer"))
):
    """Download analytics data as CSV spreadsheet."""
    output = io.StringIO()

    if type == "funnel":
        data = _funnel_data(date_from, date_to)
        writer = csv.DictWriter(output, fieldnames=["Stage", "Description", "Count", "Dropoff %"])
        writer.writeheader()
        for f in data["funnel"]:
            writer.writerow({
                "Stage": f["stage"],
                "Description": f["label"],
                "Count": f["count"],
                "Dropoff %": f["dropoff_percent"],
            })
        writer.writerow({
            "Stage": "non_openers",
            "Description": "Visitors (No Chat)",
            "Count": data["non_openers"],
            "Dropoff %": data["non_opener_percent"]
        })
        filename = "clinderma_funnel_analytics.csv"
    else:
        # orders
        conn = get_conn()
        cursor = conn.cursor()
        query = "SELECT created_at, metadata FROM funnel_events WHERE event_type = 'order_placed'"
        params = []
        if date_from:
            query += " AND created_at >= %s"
            params.append(date_from)
        if date_to:
            query += " AND created_at <= %s"
            params.append(date_to + "T23:59:59")
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        writer = csv.DictWriter(output, fieldnames=["Date & Time", "Session ID", "Order Value (INR)"])
        writer.writeheader()
        for r in rows:
            d = dict(r)
            try:
                meta = json.loads(d.get("metadata") or "{}")
            except Exception:
                meta = {}
            writer.writerow({
                "Date & Time": d["created_at"],
                "Session ID": meta.get("session_id", ""),
                "Order Value (INR)": meta.get("order_value", 0),
            })
        filename = "clinderma_orders_analytics.csv"

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
