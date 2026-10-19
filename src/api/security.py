"""Signed, revocable sessions; JWT possession alone is insufficient."""

import os
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from src.common.database import connection

COOKIE_NAME = "aster_access_token"
_ALGORITHM = "HS256"
_TOKEN_TTL = timedelta(hours=8)


def _secret():
    value = os.getenv("JWT_SECRET")
    if not value:
        raise RuntimeError("JWT_SECRET is required")
    return value


def create_access_token(username: str, session_id: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": username,
            "jti": session_id or str(uuid.uuid4()),
            "iat": now,
            "exp": now + _TOKEN_TTL,
            "iss": "aster",
            "aud": "aster-web",
        },
        _secret(),
        algorithm=_ALGORITHM,
    )


def decode_session(token):
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            _secret(),
            algorithms=[_ALGORITHM],
            issuer="aster",
            audience="aster-web",
            options={"require": ["sub", "jti", "iat", "exp"]},
        )
        if not isinstance(claims.get("sub"), str) or not isinstance(
            claims.get("jti"), str
        ):
            return None
        return claims
    except jwt.PyJWTError:
        return None


def decode_access_token(token):
    claims = decode_session(token)
    return claims["sub"] if claims else None


async def issue_session(url, username):
    session_id = str(uuid.uuid4())
    async with connection(url) as conn:
        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE identifier=$1", username
        )
        if user_id is None:
            raise ValueError("Unknown user")
        await conn.execute(
            "INSERT INTO sessions(id,user_id,expires_at) VALUES($1,$2,$3)",
            session_id,
            user_id,
            datetime.now(timezone.utc) + _TOKEN_TTL,
        )
    return create_access_token(username, session_id)


async def session_user(url, token):
    claims = decode_session(token)
    if not claims:
        return None
    async with connection(url) as conn:
        row = await conn.fetchrow(
            "SELECT u.id,u.identifier FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=$1 AND u.identifier=$2 AND NOT s.revoked AND s.expires_at>now()",
            claims["jti"],
            claims["sub"],
        )
    return dict(row) if row else None


async def revoke_session(url, token):
    claims = decode_session(token)
    if claims:
        async with connection(url) as conn:
            await conn.execute(
                "UPDATE sessions SET revoked=TRUE WHERE id=$1", claims["jti"]
            )


def origin_allowed(conn):
    from src.api.settings import settings

    config = settings()
    origin = conn.headers.get("origin")
    if not origin:
        return not config.production
    if config.origins:
        return origin.rstrip("/") in config.origins
    scheme = "https" if conn.url.scheme in {"https", "wss"} else "http"
    return origin.rstrip("/") == f"{scheme}://{conn.url.netloc}"
