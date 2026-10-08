"""
Clinderma — Audit Log (Change Log) API
GET /api/admin/audit-log  → paginated audit trail with filters
"""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from app.core.auth import require_role
from app.core.db import get_conn

router = APIRouter()


@router.get("/admin/audit-log")
def get_audit_log(
    action_type: Optional[str] = None,
    performed_by: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(require_role("admin"))
):
    """
    Return paginated audit log with optional filters.
    Filters:
      action_type   — e.g. 'kb_entry_create', 'offer_create', 'push_to_live', 'doctor_edit'
      performed_by  — username
      date_from     — ISO date string (inclusive)
      date_to       — ISO date string (inclusive)
    """
    conn = get_conn()
    cursor = conn.cursor()

    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []

    if action_type:
        query += " AND action_type = %s"
        params.append(action_type)
    if performed_by:
        query += " AND performed_by = %s"
        params.append(performed_by)
    if date_from:
        query += " AND performed_at >= %s"
        params.append(date_from)
    if date_to:
        # Include full day
        query += " AND performed_at <= %s"
        params.append(date_to + "T23:59:59")

    # Total count
    count_query = query.replace("SELECT *", "SELECT COUNT(*) as cnt")
    cursor.execute(count_query, params)
    count_row = cursor.fetchone()
    total = count_row["cnt"] if count_row else 0

    # Paginate
    offset = (page - 1) * page_size
    query += " ORDER BY performed_at DESC LIMIT %s OFFSET %s"
    params += [page_size, offset]
    cursor.execute(query, params)
    rows = cursor.fetchall()

    # Distinct action types for filter dropdown
    cursor.execute("SELECT DISTINCT action_type FROM audit_log ORDER BY action_type")
    action_types = [dict(r)["action_type"] for r in cursor.fetchall()]

    cursor.close()
    conn.close()

    return {
        "logs": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "action_types": action_types,
    }
