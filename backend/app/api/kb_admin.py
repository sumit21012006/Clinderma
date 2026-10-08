"""
Clinderma — Knowledge Base Admin API
Allows admins to CRUD FAQ entries, upload documents, manage draft/live workflow.

Endpoints:
  GET    /api/admin/kb             → list all entries
  POST   /api/admin/kb             → create entry
  PUT    /api/admin/kb/{id}        → update entry
  DELETE /api/admin/kb/{id}        → delete entry
  GET    /api/admin/kb/categories  → list all categories
  GET    /api/admin/kb/drafts      → list draft-only entries
  POST   /api/admin/push-to-live   → push all drafts live + rebuild FAISS
  POST   /api/admin/restore        → restore previous published version
  POST   /api/admin/kb/documents   → upload a document file
  GET    /api/admin/kb/documents   → list uploaded documents
  GET    /api/admin/test-chat      → run test chat against draft KB
"""

import json
import datetime
import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from app.core.auth import require_role
from app.core.db import get_conn

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

KB_CATEGORIES = [
    "Products", "Treatment", "Guarantee", "Delivery", "Payments",
    "Acne & Blemishes", "Pigmentation", "Skin Barrier", "Anti-Aging",
    "Ingredients", "Routines", "Doctor Corrections", "General"
]


class KBEntryCreate(BaseModel):
    category: str = "General"
    question: str
    answer: str


class KBEntryUpdate(BaseModel):
    category: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    status: Optional[str] = None


class TestChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "test_session_draft"


def _log_audit(conn, action_type: str, entity_id: str, entity_name: str,
                old_val: str, new_val: str, performed_by: str):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_log (action_type, entity_id, entity_name, old_value, new_value, performed_by, performed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (action_type, entity_id, entity_name, old_val, new_val, performed_by,
          datetime.datetime.now().isoformat()))
    cursor.close()


# ─── Categories ───────────────────────────────────────────────────────────────

@router.get("/admin/kb/categories")
def get_categories(user: dict = Depends(require_role("admin", "doctor", "viewer"))):
    """Return available KB categories."""
    return {"categories": KB_CATEGORIES}


# ─── List all entries ──────────────────────────────────────────────────────────

@router.get("/admin/kb")
def list_kb_entries(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(require_role("admin", "doctor", "viewer"))
):
    """List KB entries with optional category/status/search filters."""
    conn = get_conn()
    cursor = conn.cursor()
    query = "SELECT * FROM kb_entries WHERE 1=1"
    params = []
    if category:
        query += " AND category = %s"
        params.append(category)
    if status:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY updated_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()

    entries = [dict(r) for r in rows]
    if search:
        s = search.lower()
        entries = [e for e in entries if s in (e.get("question") or "").lower()
                   or s in (e.get("answer") or "").lower()
                   or s in (e.get("category") or "").lower()]

    cursor.close()
    conn.close()
    return {"entries": entries, "count": len(entries)}


# ─── Drafts only ──────────────────────────────────────────────────────────────

@router.get("/admin/kb/drafts")
def list_drafts(user: dict = Depends(require_role("admin", "doctor"))):
    """Return only draft entries (not yet pushed live)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kb_entries WHERE status = 'draft' ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"drafts": [dict(r) for r in rows], "count": len(rows)}


# ─── Create ───────────────────────────────────────────────────────────────────

@router.post("/admin/kb")
def create_kb_entry(req: KBEntryCreate, user: dict = Depends(require_role("admin"))):
    """Create a new KB entry (saved as draft by default)."""
    conn = get_conn()
    now = datetime.datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO kb_entries (category, question, answer, status, live_answer, created_by, updated_at, created_at)
        VALUES (%s, %s, %s, 'draft', '', %s, %s, %s)
    """, (req.category, req.question, req.answer, user["username"], now, now))
    new_id = cursor.lastrowid
    conn.commit()
    _log_audit(conn, "kb_entry_create", str(new_id), req.question[:60], "", req.answer[:100], user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "created", "id": new_id, "kb_status": "draft"}


# ─── Update ───────────────────────────────────────────────────────────────────

@router.put("/admin/kb/{entry_id}")
def update_kb_entry(entry_id: int, req: KBEntryUpdate, user: dict = Depends(require_role("admin"))):
    """Update a KB entry. Puts it back to draft if answer changes."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM kb_entries WHERE id = %s", (entry_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="KB entry not found.")

    old = dict(row)
    now = datetime.datetime.now().isoformat()
    updates = {"updated_at": now}

    if req.category is not None: updates["category"] = req.category
    if req.question is not None: updates["question"] = req.question
    if req.answer is not None:
        updates["answer"] = req.answer
        updates["status"] = "draft"   # answer changed → back to draft
    if req.status is not None and req.answer is None:
        updates["status"] = req.status

    set_clause = ", ".join([f"{k} = %s" for k in updates])
    vals = list(updates.values()) + [entry_id]
    cursor.execute(f"UPDATE kb_entries SET {set_clause} WHERE id = %s", vals)
    conn.commit()

    _log_audit(conn, "kb_entry_update", str(entry_id), old.get("question", "")[:60],
               old.get("answer", "")[:100], req.answer[:100] if req.answer else "(no change)", user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "updated", "id": entry_id}


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.delete("/admin/kb/{entry_id}")
def delete_kb_entry(entry_id: int, user: dict = Depends(require_role("admin"))):
    """Delete a KB entry."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT question FROM kb_entries WHERE id = %s", (entry_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="KB entry not found.")

    name = dict(row)["question"]
    cursor.execute("DELETE FROM kb_entries WHERE id = %s", (entry_id,))
    conn.commit()
    _log_audit(conn, "kb_entry_delete", str(entry_id), name[:60], name[:60], "", user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "deleted", "id": entry_id}


# ─── Push to Live ─────────────────────────────────────────────────────────────

@router.post("/admin/push-to-live")
def push_to_live(user: dict = Depends(require_role("admin"))):
    """Push all draft KB entries to live. Saves snapshot for undo. Triggers FAISS rebuild."""
    conn = get_conn()
    cursor = conn.cursor()

    # 1. Fetch all current live entries for snapshot
    cursor.execute("SELECT * FROM kb_entries WHERE status = 'live'")
    live_entries = [dict(r) for r in cursor.fetchall()]
    snapshot = json.dumps(live_entries)

    # 2. Save snapshot to publish_history
    now = datetime.datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO publish_history (snapshot, pushed_by, pushed_at)
        VALUES (%s, %s, %s)
    """, (snapshot, user["username"], now))

    # 3. Promote all drafts to live, save their answer as live_answer
    cursor.execute("""
        UPDATE kb_entries
        SET status = 'live', live_answer = answer, updated_at = %s
        WHERE status = 'draft'
    """, (now,))
    pushed_count = cursor.rowcount

    conn.commit()
    _log_audit(conn, "push_to_live", "all", f"{pushed_count} entries",
               "draft", "live", user["username"])
    conn.commit()
    cursor.close()
    conn.close()

    # 4. Trigger FAISS rebuild in background thread
    _trigger_faiss_rebuild()

    return {
        "status": "pushed_to_live",
        "entries_pushed": pushed_count,
        "message": f"{pushed_count} draft entries are now live. FAISS index rebuild triggered.",
    }


def _trigger_faiss_rebuild():
    """Rebuild the FAISS index from live KB entries + existing dataset."""
    import threading

    def _rebuild():
        try:
            from app.services.rag_engine import rag_engine
            from app.core.db import get_conn as gc
            conn = gc()
            cursor = conn.cursor()
            cursor.execute("SELECT category, question, answer FROM kb_entries WHERE status = 'live'")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            extra_docs = []
            for r in rows:
                d = dict(r)
                extra_docs.append({
                    "source": "admin_kb",
                    "category": d.get("category", "General"),
                    "text": f"Q: {d['question']}\nA: {d['answer']}"
                })

            if hasattr(rag_engine, "add_documents"):
                rag_engine.add_documents(extra_docs)
                print(f"[KB] FAISS hot-reload: {len(extra_docs)} admin KB entries added.")
            else:
                print("[KB] FAISS hot-reload: rag_engine.add_documents not available; skipping.")
        except Exception as e:
            print(f"[KB] FAISS rebuild error: {e}")

    t = threading.Thread(target=_rebuild, daemon=True)
    t.start()


# ─── Restore previous version ─────────────────────────────────────────────────

@router.post("/admin/restore")
def restore_previous(user: dict = Depends(require_role("admin"))):
    """Restore the most recent previous publish snapshot (undo last push-to-live)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM publish_history ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="No previous snapshot to restore.")

    d = dict(row)
    snapshot = json.loads(d["snapshot"])
    now = datetime.datetime.now().isoformat()

    # Set all current live entries back to draft
    cursor.execute("UPDATE kb_entries SET status = 'draft', updated_at = %s WHERE status = 'live'", (now,))

    # Re-insert snapshot entries as live
    for entry in snapshot:
        cursor.execute("""
            UPDATE kb_entries
            SET status = 'live', answer = %s, live_answer = %s, updated_at = %s
            WHERE id = %s
        """, (entry.get("live_answer", entry.get("answer", "")),
              entry.get("live_answer", entry.get("answer", "")),
              now, entry["id"]))

    # Remove this snapshot (consumed)
    cursor.execute("DELETE FROM publish_history WHERE id = %s", (d["id"],))
    conn.commit()
    _log_audit(conn, "restore", str(d["id"]), "publish_history",
               "current_live", "restored_snapshot", user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "restored", "snapshot_id": d["id"], "entries_restored": len(snapshot)}


# ─── Document Upload ──────────────────────────────────────────────────────────

@router.post("/admin/kb/documents")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(default="General"),
    user: dict = Depends(require_role("admin"))
):
    """Upload a product sheet, policy doc, or FAQ document."""
    allowed = {".pdf", ".docx", ".txt", ".xlsx"}
    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Use: {allowed}")

    # Save file
    safe_name = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Record in DB
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO kb_documents (filename, original_filename, category, status, file_path, uploaded_by, uploaded_at)
        VALUES (%s, %s, %s, 'draft', %s, %s, %s)
    """, (safe_name, file.filename, category, file_path, user["username"], now))
    doc_id = cursor.lastrowid
    conn.commit()
    _log_audit(conn, "document_upload", str(doc_id), file.filename, "", file.filename, user["username"])
    conn.commit()
    cursor.close()
    conn.close()

    return {
        "status": "uploaded",
        "document_id": doc_id,
        "filename": file.filename,
        "size_bytes": len(content),
        "category": category,
    }


@router.get("/admin/kb/documents")
def list_documents(user: dict = Depends(require_role("admin", "doctor", "viewer"))):
    """List all uploaded KB documents."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, original_filename, category, status, uploaded_by, uploaded_at FROM kb_documents ORDER BY uploaded_at DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"documents": [dict(r) for r in rows], "count": len(rows)}


# ─── Test Chat (draft KB) ──────────────────────────────────────────────────────

@router.post("/admin/test-chat")
def test_chat(req: TestChatRequest, user: dict = Depends(require_role("admin", "doctor"))):
    """Run a chat message against DRAFT KB entries (not live FAISS).
    Returns the answer from draft content for testing before push-to-live.
    """
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT question, answer, category FROM kb_entries WHERE status = 'draft'")
    drafts = [dict(r) for r in cursor.fetchall()]
    cursor.close()
    conn.close()

    msg_lower = req.message.lower()
    best_match = None
    best_score = 0

    for entry in drafts:
        q = (entry.get("question") or "").lower()
        a = (entry.get("answer") or "").lower()
        # Simple keyword overlap scoring
        msg_words = set(msg_lower.split())
        q_words = set(q.split())
        overlap = len(msg_words & q_words)
        if overlap > best_score:
            best_score = overlap
            best_match = entry

    if best_match and best_score >= 1:
        return {
            "mode": "draft",
            "matched_question": best_match["question"],
            "answer": best_match["answer"],
            "category": best_match["category"],
            "confidence": min(round(best_score / max(len(msg_lower.split()), 1), 2), 1.0),
            "note": "This answer comes from DRAFT content. Push to Live to make it available to customers.",
        }
    else:
        return {
            "mode": "draft",
            "matched_question": None,
            "answer": "No matching draft content found. The live chatbot would fall back to the FAISS knowledge base.",
            "confidence": 0.0,
            "note": "No draft match. Try adding or editing draft KB entries.",
        }
