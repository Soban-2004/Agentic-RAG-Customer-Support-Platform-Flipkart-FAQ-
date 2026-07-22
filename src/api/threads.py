"""Thread list/create/get/delete -- backs the React sidebar."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.config import DATABASE_URL
from src.api.deps import CurrentUser, get_current_user
from src.persistence import chat_store

router = APIRouter(prefix="/api/threads", tags=["threads"])

_TITLE_MAX_LEN = 40


class CreateThreadRequest(BaseModel):
    title: str = "New chat"


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
async def list_threads(user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return await chat_store.list_threads(DATABASE_URL, user.id)


@router.post("", response_model=ThreadOut)
async def create_thread(
    body: CreateThreadRequest, user: CurrentUser = Depends(get_current_user)
) -> dict:
    title = body.title.strip()[:_TITLE_MAX_LEN] or "New chat"
    return await chat_store.create_thread(DATABASE_URL, user.id, title)


@router.get("/{thread_id}", response_model=ThreadDetailOut)
async def get_thread(thread_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    thread = await chat_store.get_thread(DATABASE_URL, thread_id, user.id)
    if not thread:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
    messages = await chat_store.list_messages(DATABASE_URL, thread_id)
    return {**thread, "messages": messages}


@router.delete("/{thread_id}")
async def delete_thread(thread_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    deleted = await chat_store.delete_thread(DATABASE_URL, thread_id, user.id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
    return {"ok": True}


@router.post("/{thread_id}/regenerate-prep")
async def regenerate_prep(thread_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Called by the UI's "Regenerate" action right before it resends the
    prior question over the WS -- deletes that question's now-stale
    user+assistant row pair first, so the old answer doesn't reappear
    duplicated in history after a reload. See chat_store.delete_last_turn."""
    thread = await chat_store.get_thread(DATABASE_URL, thread_id, user.id)
    if not thread:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Thread not found")
    await chat_store.delete_last_turn(DATABASE_URL, thread_id)
    return {"ok": True}
