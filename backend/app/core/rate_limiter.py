import time
from collections import defaultdict
from fastapi import Request, HTTPException, status

# In-memory sliding window rate limiter: client_ip -> list of timestamps
_request_counts = defaultdict(list)
_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 30  # 30 chat messages per minute per IP


def rate_limit_chat(request: Request):
    """
    Enforces rate limiting on /api/chat.
    Allows up to 30 requests per 60 seconds per client IP address.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    cutoff = now - _WINDOW_SECONDS

    # Filter out requests older than window
    timestamps = [t for t in _request_counts[client_ip] if t > cutoff]
    if len(timestamps) >= _MAX_REQUESTS_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a moment before sending another message.",
            headers={"Retry-After": str(int(_WINDOW_SECONDS - (now - timestamps[0])))}
        )

    timestamps.append(now)
    _request_counts[client_ip] = timestamps
