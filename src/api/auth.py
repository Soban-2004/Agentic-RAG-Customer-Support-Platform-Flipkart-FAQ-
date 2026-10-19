"""Login/logout/me/register routes. Self-serve signup (added for the public
demo deploy -- see README's Deployment section) provisions a user directly;
`python src/auth/manage_users.py create <user> <password>` still works too,
for admin-provisioned accounts."""

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from src.api import security
from src.api.config import DATABASE_URL
from src.api.deps import CurrentUser, get_current_user
from src.api.rate_limit import enforce_rate_limit
from src.auth.store import register_user, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Cookie lifetime must match the JWT's own TTL (src/api/security.py) -- the
# cookie's Max-Age is just when the browser stops sending it, not the source
# of truth for validity, but there's no reason for them to disagree.
_COOKIE_MAX_AGE_SECONDS = int(security._TOKEN_TTL.total_seconds())


def _cookie_path() -> str:
    value = os.getenv("PUBLIC_BASE_PATH", "/").strip()
    if not value.startswith("/") or ".." in value:
        raise ValueError("PUBLIC_BASE_PATH must be an absolute URL path")
    return value.rstrip("/") or "/"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    # Constrained beyond LoginRequest's bare strings -- this endpoint is
    # reachable by anyone on the public internet, not just an admin typing
    # into the CLI, so it validates what it accepts instead of trusting it.
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    identifier: str


async def _start_session(response: Response, username: str) -> None:
    token = await security.issue_session(DATABASE_URL, username)
    response.set_cookie(
        key=security.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=os.getenv("APP_ENV") == "production",
        samesite="lax",
        max_age=_COOKIE_MAX_AGE_SECONDS,
        path=_cookie_path(),
    )


@router.post("/login", response_model=UserOut)
async def login(body: LoginRequest, request: Request, response: Response) -> UserOut:
    # 10/15min -- generous enough for a legitimate user mistyping a password
    # a few times, tight enough to blunt scripted brute-forcing.
    await enforce_rate_limit(request, "login", limit=10, window_seconds=900)
    await enforce_rate_limit(
        request, "account_login", limit=10, window_seconds=900, subject=body.username
    )
    if not await verify_password(DATABASE_URL, body.username, body.password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid username or password"
        )

    await _start_session(response, body.username)
    return UserOut(identifier=body.username)


@router.post("/register", response_model=UserOut)
async def register(
    body: RegisterRequest, request: Request, response: Response
) -> UserOut:
    # 5/hour -- this is the one that actually matters: unlimited signups
    # would let someone script account creation against this app's own
    # Groq/Cohere/Qdrant free-tier quotas, not just spam the users table.
    await enforce_rate_limit(request, "register", limit=5, window_seconds=3600)
    created = await register_user(DATABASE_URL, body.username, body.password)
    if not created:
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is already taken")

    await _start_session(response, body.username)
    return UserOut(identifier=body.username)


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    await security.revoke_session(
        DATABASE_URL, request.cookies.get(security.COOKIE_NAME)
    )
    from src.api.connections import close_session

    await close_session(request.cookies.get(security.COOKIE_NAME))
    response.delete_cookie(
        security.COOKIE_NAME,
        path=_cookie_path(),
        secure=os.getenv("APP_ENV") == "production",
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser = Depends(get_current_user)) -> UserOut:
    return UserOut(identifier=user.identifier)
