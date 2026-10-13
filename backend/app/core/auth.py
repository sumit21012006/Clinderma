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
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# HTTP Basic kept for backward-compat on legacy /dashboard.html route
basic_security = HTTPBasic(auto_error=False)
bearer_security = HTTPBearer(auto_error=False)


# ── Password hashing (bcrypt-free: SHA256+salt for simplicity) ────────────────
import base64
import hashlib
import hmac

PBKDF2_ITERATIONS = 310_000
PASSWORD_SCHEME = "pbkdf2_sha256"


def _legacy_password_hash(password: str) -> str:
    """Return the hash produced before per-user salts were added."""
    return hashlib.sha256(f"clinderma_salt_2026{password}".encode()).hexdigest()


def hash_password(password: str) -> str:
    """Create a slow, independently salted password hash for storage."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "$".join((
        PASSWORD_SCHEME,
        str(PBKDF2_ITERATIONS),
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    ))


def verify_password(plain: str, hashed: str) -> bool:
    if not isinstance(hashed, str):
        return False
    if not hashed.startswith(f"{PASSWORD_SCHEME}$"):
        return hmac.compare_digest(_legacy_password_hash(plain), hashed)

    try:
        _, iterations, salt_encoded, digest_encoded = hashed.split("$", 3)
        salt = base64.urlsafe_b64decode(salt_encoded.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_encoded.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", plain.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, UnicodeError):
        return False


def password_needs_rehash(hashed: str) -> bool:
    """Flag legacy or lower-cost hashes for transparent migration on login."""
    try:
        scheme, iterations, _, _ = hashed.split("$", 3)
        return scheme != PASSWORD_SCHEME or int(iterations) < PBKDF2_ITERATIONS
    except (AttributeError, TypeError, ValueError):
        return True


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
        if payload.get("exp") and datetime.datetime.now(datetime.timezone.utc).timestamp() > payload["exp"]:
            return None
        return payload
    except Exception:
        return None


def create_access_token(username: str, role: str) -> str:
    """Create a signed JWT access token."""
    now = datetime.datetime.now(datetime.timezone.utc)
    exp = now + datetime.timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "role": role,
        "exp": exp.timestamp(),
        "iat": now.timestamp(),
    }
    return _encode_token(payload)


# ── Seed default admin user ────────────────────────────────────────────────────
def ensure_default_admin():
    """Create each missing development seed account without overwriting users."""
    try:
        from app.core.db import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        seed_users = (
            (
                settings.ADMIN_USERNAME,
                settings.ADMIN_PASSWORD,
                "admin",
                "Clinderma Admin",
            ),
            ("doctor", "doctor@clinderma2026", "doctor", "Dr. Consultant"),
            ("viewer", "viewer@clinderma2026", "viewer", "Analytics Viewer"),
        )
        created = []
        for username, password, role, full_name in seed_users:
            cursor.execute(
                "SELECT username FROM admin_users WHERE username = %s",
                (username,),
            )
            if cursor.fetchone():
                continue
            cursor.execute("""
                INSERT INTO admin_users (username, password_hash, role, full_name, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                username,
                hash_password(password),
                role,
                full_name,
                1,
                now,
            ))
            created.append(username)
        conn.commit()
        if created:
            print(f"[AUTH] Missing seed users created: {', '.join(created)}")
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


def verify_clinical_user(
    credentials: HTTPBasicCredentials = Depends(_basic),
) -> dict:
    """Allow active admin/doctor accounts into the legacy clinical console."""
    from app.core.db import get_conn

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT username, password_hash, role, is_active
        FROM admin_users WHERE username = %s
        """,
        (credentials.username,),
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if row:
        user = dict(row)
        authenticated = (
            bool(user.get("is_active", 1))
            and user.get("role") in ("admin", "doctor")
            and verify_password(credentials.password, user.get("password_hash"))
        )
        if authenticated:
            return {"username": user["username"], "role": user["role"]}

    # Preserve access for a configured admin on deployments created before
    # role-based users were introduced.
    configured_admin = (
        secrets.compare_digest(credentials.username, settings.ADMIN_USERNAME)
        and secrets.compare_digest(credentials.password, settings.ADMIN_PASSWORD)
    )
    if configured_admin:
        return {"username": credentials.username, "role": "admin"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin or doctor credentials required",
        headers={"WWW-Authenticate": "Basic realm=\"Clinderma Clinical Console\""},
    )

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
