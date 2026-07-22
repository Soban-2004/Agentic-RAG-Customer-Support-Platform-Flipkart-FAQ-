"""Shared `get_current_user` dependency for the REST routes (src/api/threads.py).
The WS chat endpoint (src/api/chat_ws.py) can't use this the same way -- it
needs to reject *before* `websocket.accept()`, which a normal `Depends` can't
do -- so it calls `security.decode_access_token` + `store.get_user_by_identifier`
directly instead."""

from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from src.api import security
from src.api.config import DATABASE_URL
from src.auth.store import get_user_by_identifier


@dataclass
class CurrentUser:
    id: str
    identifier: str


async def get_current_user(request: Request) -> CurrentUser:
    token = request.cookies.get(security.COOKIE_NAME)
    username = security.decode_access_token(token)
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    row = await get_user_by_identifier(DATABASE_URL, username)
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return CurrentUser(id=row["id"], identifier=row["identifier"])
