"""Login/logout/me routes. No self-serve signup -- users are provisioned with
`python src/auth/manage_users.py create <user> <password>`, same as before."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from src.api import security
from src.api.config import DATABASE_URL
from src.api.deps import CurrentUser, get_current_user
from src.auth.store import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Cookie lifetime must match the JWT's own TTL (src/api/security.py) -- the
# cookie's Max-Age is just when the browser stops sending it, not the source
# of truth for validity, but there's no reason for them to disagree.
_COOKIE_MAX_AGE_SECONDS = 14 * 24 * 60 * 60


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    identifier: str


@router.post("/login", response_model=UserOut)
async def login(body: LoginRequest, response: Response) -> UserOut:
    if not await verify_password(DATABASE_URL, body.username, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    token = security.create_access_token(body.username)
    response.set_cookie(
        key=security.COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )
    return UserOut(identifier=body.username)


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(security.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser = Depends(get_current_user)) -> UserOut:
    return UserOut(identifier=user.identifier)
