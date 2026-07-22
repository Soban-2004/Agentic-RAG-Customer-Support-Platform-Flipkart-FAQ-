"""
JWT session cookie helpers, shared by the REST auth routes (src/api/auth.py)
and the WebSocket chat endpoint (src/api/chat_ws.py -- the WS handshake can't
use a FastAPI `Depends`, since we need to reject before `websocket.accept()`,
so it calls `decode_access_token` directly).

Browsers can't attach an `Authorization` header to a WebSocket handshake, so
the token lives in an httpOnly cookie instead -- sent automatically on every
request/handshake as long as the frontend and API are same-origin (see the
Vite dev-server proxy in frontend/vite.config.ts, and the single-container
static-serving setup in main.py for prod).
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

COOKIE_NAME = "access_token"
_ALGORITHM = "HS256"
_TOKEN_TTL = timedelta(days=14)


def _secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "Missing JWT_SECRET -- see README.md's Auth & chat history section."
        )
    return secret


def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + _TOKEN_TTL,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_access_token(token: Optional[str]) -> Optional[str]:
    """Returns the username, or None if the token is missing/invalid/expired --
    callers treat None as "not authenticated", never raise from here."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")
