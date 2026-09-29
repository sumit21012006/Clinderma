import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from app.core.config import settings

security = HTTPBasic()


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Verify HTTP Basic Auth credentials for admin dashboard and protected APIs.
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
