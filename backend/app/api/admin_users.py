"""
Clinderma — Admin Users Management API
GET    /api/admin/users          → list all users
POST   /api/admin/users          → create a user
PUT    /api/admin/users/{id}     → update user (role, name, active)
DELETE /api/admin/users/{id}     → delete user
"""

import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.auth import require_role, hash_password
from app.core.db import get_conn

router = APIRouter()

VALID_ROLES = ("admin", "doctor", "viewer")


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    full_name: Optional[str] = ""


class UserUpdate(BaseModel):
    role: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[int] = None
    password: Optional[str] = None


def _log_audit(conn, action_type: str, entity_id: str, entity_name: str,
                old_val: str, new_val: str, performed_by: str):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_log (action_type, entity_id, entity_name, old_value, new_value, performed_by, performed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (action_type, entity_id, entity_name, old_val, new_val, performed_by,
          datetime.datetime.now().isoformat()))
    cursor.close()


@router.get("/admin/users")
def list_users(user: dict = Depends(require_role("admin"))):
    """List all admin users (passwords excluded)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, full_name, is_active, created_at FROM admin_users ORDER BY created_at ASC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"users": [dict(r) for r in rows], "count": len(rows)}


@router.post("/admin/users")
def create_user(req: UserCreate, user: dict = Depends(require_role("admin"))):
    """Create a new admin panel user."""
    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {VALID_ROLES}")

    conn = get_conn()
    cursor = conn.cursor()
    # Check duplicate
    cursor.execute("SELECT id FROM admin_users WHERE username = %s", (req.username,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        raise HTTPException(status_code=409, detail=f"Username '{req.username}' already exists.")

    now = datetime.datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO admin_users (username, password_hash, role, full_name, is_active, created_at)
        VALUES (%s, %s, %s, %s, 1, %s)
    """, (req.username, hash_password(req.password), req.role, req.full_name or req.username, now))
    new_id = cursor.lastrowid
    conn.commit()

    _log_audit(conn, "user_create", str(new_id), req.username, "", req.role, user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "created", "id": new_id, "username": req.username, "role": req.role}


@router.put("/admin/users/{user_id}")
def update_user(user_id: int, req: UserUpdate, user: dict = Depends(require_role("admin"))):
    """Update a user's role, name, active status, or password."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="User not found.")

    old = dict(row)
    updates = {}
    if req.role is not None:
        if req.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}")
        updates["role"] = req.role
    if req.full_name is not None:
        updates["full_name"] = req.full_name
    if req.is_active is not None:
        updates["is_active"] = req.is_active
    if req.password is not None:
        updates["password_hash"] = hash_password(req.password)

    if not updates:
        cursor.close()
        conn.close()
        return {"status": "no_changes"}

    set_clause = ", ".join([f"{k} = %s" for k in updates])
    vals = list(updates.values()) + [user_id]
    cursor.execute(f"UPDATE admin_users SET {set_clause} WHERE id = %s", vals)
    conn.commit()

    _log_audit(conn, "user_update", str(user_id), old["username"],
               old.get("role", ""), req.role or old.get("role", ""), user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "updated", "id": user_id}


@router.delete("/admin/users/{user_id}")
def delete_user(user_id: int, user: dict = Depends(require_role("admin"))):
    """Delete a user (cannot delete yourself)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM admin_users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="User not found.")

    target = dict(row)["username"]
    if target == user["username"]:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")

    cursor.execute("DELETE FROM admin_users WHERE id = %s", (user_id,))
    conn.commit()
    _log_audit(conn, "user_delete", str(user_id), target, target, "", user["username"])
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "deleted", "id": user_id, "username": target}
