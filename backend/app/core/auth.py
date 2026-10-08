"""
Clinderma — Authentication Module (JWT + Role-Based Access Control)

Supports:
  - JWT Bearer token authentication (primary, for new admin panel)
  - HTTP Basic Auth (legacy, kept for backward compatibility)
  - Role enforcement: 'admin' | 'doctor' | 'viewer'

Seed admin user is created automatically on first startup if admin_users table is empty.
"""

import os
import secrets
import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

# ── Token secret (use env var in production) ──────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "clinderma_jwt_secret_2026_changeme")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# HTTP Basic kept for backward-compat on legacy /dashboard.html route
basic_security = HTTPBasic(auto_error=False)
bearer_security = HTTPBearer(auto_error=False)


# ── Password hashing (bcrypt-free: SHA256+salt for simplicity) ────────────────
import hashlib

def hash_password(password: str) -> str:
    salt = "clinderma_salt_2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed


# ── JWT helpers ───────────────────────────────────────────────────────────────
def _encode_token(payload: dict) -> str:
    """Simple JWT encoding without external library (base64 + HMAC-SHA256)."""
    import base64
    import hmac
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    signing_input = header + b"." + body
    sig = base64.urlsafe_b64encode(
        hmac.new(JWT_SECRET.encode(), signing_input, "sha256").digest()
    ).rstrip(b"=")
    return (signing_input + b"." + sig).decode()


def _decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token. Returns payload dict or None."""
    import base64
    import hmac
    import json

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b, body_b, sig_b = parts
        signing_input = f"{header_b}.{body_b}".encode()
        expected_sig = base64.urlsafe_b64encode(
            hmac.new(JWT_SECRET.encode(), signing_input, "sha256").digest()
        ).rstrip(b"=").decode()
        if not secrets.compare_digest(sig_b, expected_sig):
            return None
        # Add padding back
        body_padded = body_b + "=" * (-len(body_b) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body_padded))
        # Check expiry
        if payload.get("exp") and datetime.datetime.utcnow().timestamp() > payload["exp"]:
            return None
        return payload
    except Exception:
        return None


def create_access_token(username: str, role: str) -> str:
    """Create a signed JWT access token."""
    exp = datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "role": role,
        "exp": exp.timestamp(),
        "iat": datetime.datetime.utcnow().timestamp(),
    }
    return _encode_token(payload)


# ── Seed default admin user ────────────────────────────────────────────────────
def ensure_default_admin():
    """Create seed admin user from .env config if admin_users table is empty."""
    try:
        from app.core.db import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM admin_users")
        row = cursor.fetchone()
        count = row["cnt"] if row else 0
        if count == 0:
            now = datetime.datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO admin_users (username, password_hash, role, full_name, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                settings.ADMIN_USERNAME,
                hash_password(settings.ADMIN_PASSWORD),
                "admin",
                "Clinderma Admin",
                1,
                now
            ))
            # Also seed a demo doctor user
            cursor.execute("""
                INSERT INTO admin_users (username, password_hash, role, full_name, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                "doctor",
                hash_password("doctor@clinderma2026"),
                "doctor",
                "Dr. Consultant",
                1,
                now
            ))
            # Also seed a viewer
            cursor.execute("""
                INSERT INTO admin_users (username, password_hash, role, full_name, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                "viewer",
                hash_password("viewer@clinderma2026"),
                "viewer",
                "Analytics Viewer",
                1,
                now
            ))
            conn.commit()
            print("[AUTH] Seed users created: admin / doctor / viewer")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[AUTH] Could not seed admin user: {e}")


# ── Core auth dependency (JWT Bearer) ─────────────────────────────────────────
def get_current_user(
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(bearer_security),
) -> dict:
    """Extract and validate JWT Bearer token. Returns user dict {username, role}."""
    if bearer and bearer.credentials:
        payload = _decode_token(bearer.credentials)
        if payload:
            return {"username": payload["sub"], "role": payload.get("role", "viewer")}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(*allowed_roles: str):
    """Dependency factory: only allow users with specific roles.
    Usage: Depends(require_role('admin', 'doctor'))
    """
    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {list(allowed_roles)}. Your role: {user['role']}",
            )
        return user
    return _check


# ── Legacy HTTP Basic Auth (kept for /dashboard.html route backward-compat) ───
_basic = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(_basic)) -> str:
    """Legacy: Verify HTTP Basic Auth credentials for admin dashboard.
    Returns the authenticated username on success, or raises 401 Unauthorized.
    """
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.ADMIN_USERNAME.encode("utf-8")
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.ADMIN_PASSWORD.encode("utf-8")
    )
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin username or password",
            headers={"WWW-Authenticate": "Basic realm=\"Clinderma Admin Dashboard\""},
        )
    return credentials.username
