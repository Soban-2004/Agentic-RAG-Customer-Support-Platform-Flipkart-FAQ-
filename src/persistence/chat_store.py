"""Thread/message persistence -- the FastAPI backend's own replacement for
Chainlit's SQLAlchemyDataLayer. Same lightweight asyncpg-direct style as
src/auth/store.py (no ORM), against the `threads`/`messages` tables in
db/schema.sql.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg
from src.common.database import connect


def _asyncpg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def create_thread(database_url: str, user_id: str, title: str) -> dict[str, Any]:
    thread_id = str(uuid.uuid4())
    created_at = _now()
    conn = await connect(database_url)
    try:
        await conn.execute(
            'INSERT INTO threads ("id", "user_id", "title", "created_at") '
            "VALUES ($1, $2, $3, $4)",
            thread_id,
            user_id,
            title,
            created_at,
        )
    finally:
        await conn.close()
    return {
        "id": thread_id,
        "user_id": user_id,
        "title": title,
        "created_at": created_at,
    }


async def list_threads(
    database_url: str, user_id: str, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    conn = await connect(database_url)
    try:
        rows = await conn.fetch(
            'SELECT "id", "title", "created_at" FROM threads '
            'WHERE "user_id" = $1 ORDER BY "created_at" DESC, "id" DESC LIMIT $2 OFFSET $3',
            user_id,
            limit,
            offset,
        )
    finally:
        await conn.close()
    return [dict(r) for r in rows]


async def get_thread(
    database_url: str, thread_id: str, user_id: str
) -> Optional[dict[str, Any]]:
    """Scoped to user_id so one user can't fetch another's thread by guessing an id."""
    conn = await connect(database_url)
    try:
        row = await conn.fetchrow(
            'SELECT "id", "title", "created_at" FROM threads '
            'WHERE "id" = $1 AND "user_id" = $2',
            thread_id,
            user_id,
        )
    finally:
        await conn.close()
    return dict(row) if row else None


async def delete_thread(database_url: str, thread_id: str, user_id: str) -> bool:
    conn = await connect(database_url)
    try:
        result = await conn.execute(
            'DELETE FROM threads WHERE "id" = $1 AND "user_id" = $2',
            thread_id,
            user_id,
        )
    finally:
        await conn.close()
    return result != "DELETE 0"


async def list_messages(
    database_url: str,
    thread_id: str,
    limit: int = 500,
    offset: int = 0,
    for_memory: bool = False,
) -> list[dict[str, Any]]:
    conn = await connect(database_url)
    try:
        rows = await conn.fetch(
            'SELECT m."id", m."role", m."content", m."created_at" FROM messages m LEFT JOIN turns t ON t.id=m.turn_id '
            'WHERE m."thread_id" = $1 AND NOT m.superseded AND (NOT $4::boolean OR (t.status=\'completed\' AND t.include_in_memory)) ORDER BY m."created_at" DESC, m."id" DESC LIMIT $2 OFFSET $3',
            thread_id,
            limit,
            offset,
            for_memory,
        )
    finally:
        await conn.close()
    return [dict(r) for r in reversed(rows)]


async def delete_last_turn(database_url: str, thread_id: str) -> None:
    raise ValueError("Destructive regeneration is disabled; use a versioned turn")


async def add_message(
    database_url: str, thread_id: str, role: str, content: str
) -> dict[str, Any]:
    message_id = str(uuid.uuid4())
    created_at = _now()
    conn = await connect(database_url)
    try:
        await conn.execute(
            'INSERT INTO messages ("id", "thread_id", "role", "content", "created_at") '
            "VALUES ($1, $2, $3, $4, $5)",
            message_id,
            thread_id,
            role,
            content,
            created_at,
        )
    finally:
        await conn.close()
    return {
        "id": message_id,
        "role": role,
        "content": content,
        "created_at": created_at,
    }
