"""
Clinderma — Auth API Endpoints
POST /api/auth/login   → returns JWT access token
GET  /api/auth/me      → returns current user info
POST /api/auth/logout  → client-side token discard (informational)
"""

import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.core.db import get_conn
from app.core.auth import (
    hash_password, verify_password, password_needs_rehash,
    create_access_token, get_current_user
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    full_name: str


def get_conn():
    from app.core.db import get_conn as _get_conn
    return _get_conn()


@router.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """Authenticate with username + password → returns JWT token."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, password_hash, role, full_name, is_active FROM admin_users WHERE username = %s",
        (req.username.strip(),)
    )
    user = cursor.fetchone()
    if not user:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    user_dict = dict(user)
    if not user_dict.get("is_active", 1):
        cursor.close()
        conn.close()
        raise HTTPException(status_code=403, detail="Account is disabled.")

    if not verify_password(req.password, user_dict["password_hash"]):
        cursor.close()
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    if password_needs_rehash(user_dict["password_hash"]):
        cursor.execute(
            "UPDATE admin_users SET password_hash = %s WHERE username = %s",
            (hash_password(req.password), user_dict["username"]),
        )
        conn.commit()

    cursor.close()
    conn.close()

    token = create_access_token(user_dict["username"], user_dict["role"])

    return LoginResponse(
        access_token=token,
        username=user_dict["username"],
        role=user_dict["role"],
        full_name=user_dict.get("full_name") or user_dict["username"],
    )


@router.get("/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    """Returns current authenticated user info."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, role, full_name, created_at FROM admin_users WHERE username = %s",
        (user["username"],)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row:
        return dict(row)
    return user


@router.post("/auth/logout")
def logout():
    """Informational endpoint — JWT is stateless; client should discard the token."""
    return {"message": "Logged out. Please discard your access token."}
