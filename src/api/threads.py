"""Thread list/create/get/delete -- backs the React sidebar."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel

from src.api.config import DATABASE_URL
from src.api.deps import CurrentUser, get_current_user
from src.persistence import chat_store, turns

router = APIRouter(prefix="/api/threads", tags=["threads"])

_TITLE_MAX_LEN = 40


class CreateThreadRequest(BaseModel):
    title: str = __import__("pydantic").Field(default="New chat", max_length=200)


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ThreadOut(BaseModel):
    id: str
    title: str | None
    created_at: str


class ThreadDetailOut(ThreadOut):
    messages: list[MessageOut]


@router.get("", response_model=list[ThreadOut])
async def list_threads(
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    return await chat_store.list_threads(DATABASE_URL, user.id, limit, offset)


@router.post("", response_model=ThreadOut)
async def create_thread(
    body: CreateThreadRequest, user: CurrentUser = Depends(get_current_user)
) -> dict:
    title = body.title.strip()[:_TITLE_MAX_LEN] or "New chat"
    return await chat_store.create_thread(DATABASE_URL, user.id, title)


@router.get("/{thread_id}", response_model=ThreadDetailOut)
async def get_thread(
    thread_id: str,
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    thread = await chat_store.get_thread(DATABASE_URL, thread_id, user.id)
    if not thread:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
    messages = await chat_store.list_messages(DATABASE_URL, thread_id, limit, offset)
    return {**thread, "messages": messages}


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: str, user: CurrentUser = Depends(get_current_user)
) -> dict:
    try:
        async with turns.conversation_lock(DATABASE_URL, thread_id):
            deleted = await chat_store.delete_thread(DATABASE_URL, thread_id, user.id)
    except turns.ConversationBusy:
        raise HTTPException(409, "A conversation turn is running; try again shortly")
    if not deleted:
        raise HTTPException(404, "Thread not found")
    return {"ok": True}


@router.post("/{thread_id}/regenerate-prep")
async def regenerate_prep(
    thread_id: str, user: CurrentUser = Depends(get_current_user)
) -> dict:
    """Deprecated destructive API. Clients must send an explicit WS target."""
    thread = await chat_store.get_thread(DATABASE_URL, thread_id, user.id)
    if not thread:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
    raise HTTPException(
        409,
        "Use regenerate_message_id on the chat WebSocket; history is never deleted in advance",
    )


@router.get("/{thread_id}/turns/{client_message_id}")
async def turn_status(
    thread_id: str,
    client_message_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    from src.common.database import connection

    if len(client_message_id) > 80:
        raise HTTPException(422, "Invalid message ID")
    if not await chat_store.get_thread(DATABASE_URL, thread_id, user.id):
        raise HTTPException(404, "Thread not found")
    async with connection(DATABASE_URL) as db:
        row = await db.fetchrow(
            "SELECT id,status,response,created_at,finished_at FROM turns WHERE thread_id=$1 AND client_message_id=$2",
            thread_id,
            client_message_id,
        )
        if not row:
            raise HTTPException(404, "Turn not found")
        actions = await db.fetch(
            "SELECT action,resource_id,result FROM tool_actions WHERE actor_id=$1 AND thread_id=$2 AND id LIKE $3",
            user.id,
            thread_id,
            row["id"] + ":%",
        )
    return {**dict(row), "actions": [dict(item) for item in actions]}
