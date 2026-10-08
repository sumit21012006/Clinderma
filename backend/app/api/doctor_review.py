"""
Clinderma — Doctor Review Queue API
Allows tagging chatbot answers for medical review, approval, and correction.
"""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.auth import require_role
from app.core.db import get_conn

router = APIRouter()


class TagReviewRequest(BaseModel):
    session_id: str
    customer_question: str
    chatbot_answer: str
    tag_note: Optional[str] = ""


class ApproveRequest(BaseModel):
    reviewed_by: Optional[str] = None


class EditRequest(BaseModel):
    corrected_answer: str
    reviewed_by: Optional[str] = None


def _log_audit(conn, action_type: str, entity_id: str, entity_name: str,
                old_val: str, new_val: str, performed_by: str):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_log (action_type, entity_id, entity_name, old_value, new_value, performed_by, performed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (action_type, entity_id, entity_name, old_val, new_val, performed_by, datetime.datetime.now().isoformat()))
    cursor.close()


@router.get("/admin/reviews")
def list_reviews(
    status: Optional[str] = None,
    user: dict = Depends(require_role("admin", "doctor", "viewer"))
):
    """List all items in the doctor review queue, optionally filtered by status."""
    conn = get_conn()
    cursor = conn.cursor()

    if status and status in ("pending", "approved", "edited"):
        cursor.execute(
            "SELECT * FROM doctor_reviews WHERE status = %s ORDER BY created_at DESC",
            (status,)
        )
    else:
        cursor.execute("SELECT * FROM doctor_reviews ORDER BY created_at DESC")

    rows = cursor.fetchall()

    # Count pending
    cursor.execute("SELECT COUNT(*) as cnt FROM doctor_reviews WHERE status = 'pending'")
    pending_row = cursor.fetchone()
    pending_count = pending_row["cnt"] if pending_row else 0

    cursor.close()
    conn.close()

    return {
        "reviews": [dict(r) for r in rows],
        "count": len(rows),
        "pending_count": pending_count,
    }


@router.post("/admin/reviews/tag")
def tag_for_review(req: TagReviewRequest, user: dict = Depends(require_role("admin", "doctor"))):
    """Tag a chatbot answer as needing doctor review."""
    conn = get_conn()
    now = datetime.datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO doctor_reviews
            (session_id, customer_question, chatbot_answer, tagged_by, tag_note, status, created_at)
        VALUES (%s, %s, %s, %s, %s, 'pending', %s)
    """, (
        req.session_id, req.customer_question, req.chatbot_answer,
        user["username"], req.tag_note or "", now
    ))
    new_id = cursor.lastrowid
    conn.commit()

    _log_audit(conn, "review_tagged", str(new_id), req.session_id,
               "", req.chatbot_answer[:100], user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "tagged", "id": new_id, "review_id": new_id}


@router.post("/admin/reviews/{review_id}/approve")
def approve_review(review_id: int, req: ApproveRequest, user: dict = Depends(require_role("admin", "doctor"))):
    """Mark a review item as approved — answer is medically correct."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT status, chatbot_answer FROM doctor_reviews WHERE id = %s", (review_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Review item not found.")

    now = datetime.datetime.now().isoformat()
    reviewer = req.reviewed_by or user["username"]
    cursor.execute("""
        UPDATE doctor_reviews
        SET status = 'approved', reviewed_by = %s, reviewed_at = %s
        WHERE id = %s
    """, (reviewer, now, review_id))
    conn.commit()

    _log_audit(conn, "review_approved", str(review_id), "",
               "pending", "approved", reviewer)
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "approved", "review_id": review_id, "reviewed_by": reviewer}


@router.post("/admin/reviews/{review_id}/edit")
def edit_review(review_id: int, req: EditRequest, user: dict = Depends(require_role("admin", "doctor"))):
    """Doctor edits/corrects a chatbot answer. Corrected answer updates the KB."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, chatbot_answer, customer_question FROM doctor_reviews WHERE id = %s",
        (review_id,)
    )
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Review item not found.")

    d = dict(row)
    now = datetime.datetime.now().isoformat()
    reviewer = req.reviewed_by or user["username"]

    cursor.execute("""
        UPDATE doctor_reviews
        SET status = 'edited', reviewed_by = %s, corrected_answer = %s, reviewed_at = %s
        WHERE id = %s
    """, (reviewer, req.corrected_answer, now, review_id))
    conn.commit()

    # Update kb_entries if a matching entry exists, or create a new live draft
    cursor.execute(
        "SELECT id FROM kb_entries WHERE question LIKE %s LIMIT 1",
        (f"%{d['customer_question'][:30]}%",)
    )
    kb_row = cursor.fetchone()
    if kb_row:
        kb_id = dict(kb_row)["id"]
        cursor.execute("""
            UPDATE kb_entries SET answer = %s, status = 'draft', updated_at = %s WHERE id = %s
        """, (req.corrected_answer, now, kb_id))
    else:
        cursor.execute("""
            INSERT INTO kb_entries (category, question, answer, status, created_by, updated_at, created_at)
            VALUES ('Doctor Corrections', %s, %s, 'draft', %s, %s, %s)
        """, (d["customer_question"], req.corrected_answer, reviewer, now, now))
    conn.commit()

    _log_audit(conn, "doctor_edit", str(review_id), "chatbot_answer",
               d["chatbot_answer"][:100], req.corrected_answer[:100], reviewer)
    conn.commit()
    cursor.close()
    conn.close()
    return {
        "status": "edited",
        "review_id": review_id,
        "corrected_answer": req.corrected_answer,
        "reviewed_by": reviewer,
        "kb_updated": True,
    }
