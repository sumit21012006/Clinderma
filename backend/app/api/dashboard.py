import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from app.core.db import get_conn
from app.core.auth import require_role

router = APIRouter()


@router.get("/dashboard/stats")
def get_dashboard_stats(_user: dict = Depends(require_role("doctor", "admin"))) -> Dict[str, Any]:
    """
    Protected endpoint: aggregated metrics and analytics for the Skin Coach Command Dashboard.
    Provides live KPI counts, clinical concern breakdown, and 7-day consultation trends.
    """
    conn = get_conn()
    cursor = conn.cursor()

    # 1. Total patient intakes
    cursor.execute("SELECT count(*) as total FROM leads")
    lead_row = cursor.fetchone()
    total_leads = lead_row["total"] if lead_row else 0

    # 2. Handoff stats
    cursor.execute("""
        SELECT 
            count(*) as total,
            sum(CASE WHEN status != 'resolved' THEN 1 ELSE 0 END) as pending,
            sum(CASE WHEN status != 'resolved' AND severity = 'critical' THEN 1 ELSE 0 END) as critical,
            sum(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) as resolved
        FROM handoffs
        WHERE LOWER(COALESCE(reason, '')) != 'lead captured in chat'
    """)
    handoff_row = cursor.fetchone()
    total_handoffs = handoff_row["total"] if handoff_row else 0
    pending_handoffs = handoff_row["pending"] if (handoff_row and handoff_row["pending"] is not None) else 0
    critical_handoffs = handoff_row["critical"] if (handoff_row and handoff_row["critical"] is not None) else 0
    resolved_handoffs = handoff_row["resolved"] if (handoff_row and handoff_row["resolved"] is not None) else 0

    # 3. Concern Distribution analysis
    cursor.execute("SELECT concern FROM leads")
    leads_concerns = cursor.fetchall()
    
    concern_counts = {
        "Acne & Blemishes": 0,
        "Pigmentation & Melasma": 0,
        "Barrier Repair & Eczema": 0,
        "Anti-Aging & Fine Lines": 0,
        "Routine & Product Layering": 0
    }

    for row in leads_concerns:
        text = (row["concern"] or "").lower()
        if any(w in text for w in ["acne", "pimple", "breakout", "salicylic", "clogged"]):
            concern_counts["Acne & Blemishes"] += 1
        elif any(w in text for w in ["dark spot", "pigment", "melasma", "tanning", "brightening", "tranexamic", "arbutin"]):
            concern_counts["Pigmentation & Melasma"] += 1
        elif any(w in text for w in ["barrier", "dry", "burn", "irritat", "redness", "eczema", "sensitive", "ceramide"]):
            concern_counts["Barrier Repair & Eczema"] += 1
        elif any(w in text for w in ["wrinkle", "age", "retinol", "tretinoin", "fine line", "firm"]):
            concern_counts["Anti-Aging & Fine Lines"] += 1
        else:
            concern_counts["Routine & Product Layering"] += 1

    # 4. Last 7 days of real clinical case intake
    today = datetime.date.today()
    days = [today - datetime.timedelta(days=(6 - i)) for i in range(7)]
    escalation_counts = {day.isoformat(): 0 for day in days}
    critical_counts = {day.isoformat(): 0 for day in days}

    cursor.execute("""
        SELECT created_at, severity FROM handoffs
        WHERE LOWER(COALESCE(reason, '')) != 'lead captured in chat'
    """)
    for row in cursor.fetchall():
        day_key = str(row["created_at"] or "")[:10]
        if day_key in escalation_counts:
            escalation_counts[day_key] += 1
            if row["severity"] == "critical":
                critical_counts[day_key] += 1

    daily_trends = []
    for day in days:
        day_label = day.strftime("%d %b")
        esc = escalation_counts[day.isoformat()]
        daily_trends.append({
            "date": day_label,
            "new_cases": esc,
            "critical_cases": critical_counts[day.isoformat()],
        })

    cursor.close()
    conn.close()

    return {
        "kpis": {
            "total_patients": total_leads,
            "total_handoffs": total_handoffs,
            "pending_handoffs": pending_handoffs,
            "critical_handoffs": critical_handoffs,
            "resolved_handoffs": resolved_handoffs,
        },
        "concerns": [
            {"name": k, "count": v} for k, v in concern_counts.items()
        ],
        "daily_trends": daily_trends
    }
