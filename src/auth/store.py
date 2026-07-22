"""Shared Postgres access for login: verifying credentials (src/api/auth.py's
login route) and provisioning users (manage_users.py).

Uses asyncpg directly against the `users` table (db/schema.sql) rather than an
ORM -- overkill for a handful of small queries.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import anyio
import asyncpg
import bcrypt


def _asyncpg_dsn(database_url: str) -> str:
    # asyncpg.connect() doesn't understand the "+asyncpg" driver suffix that
    # SQLAlchemy's async engine (used by the Chainlit data layer) requires.
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def verify_password(database_url: str, username: str, password: str) -> bool:
    conn = await asyncpg.connect(_asyncpg_dsn(database_url))
    try:
        row = await conn.fetchrow(
            'SELECT "password_hash" FROM users WHERE "identifier" = $1', username
        )
    finally:
        await conn.close()
    if not row or not row["password_hash"]:
        return False
    # bcrypt.checkpw is synchronous (and deliberately slow) -- off the event
    # loop so one login can't stall every other concurrently-connected user's
    # streamed chat response.
    return await anyio.to_thread.run_sync(
        bcrypt.checkpw, password.encode("utf-8"), row["password_hash"].encode("utf-8")
    )


async def create_user(database_url: str, username: str, password: str) -> None:
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = await asyncpg.connect(_asyncpg_dsn(database_url))
    try:
        existing = await conn.fetchrow(
            'SELECT "id" FROM users WHERE "identifier" = $1', username
        )
        if existing:
            await conn.execute(
                'UPDATE users SET "password_hash" = $1 WHERE "identifier" = $2',
                password_hash,
                username,
            )
        else:
            await conn.execute(
                'INSERT INTO users ("id", "identifier", "createdAt", "metadata", "password_hash") '
                "VALUES ($1, $2, $3, $4, $5)",
                str(uuid.uuid4()),
                username,
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "{}",
                password_hash,
            )
    finally:
        await conn.close()


async def get_user_by_identifier(database_url: str, username: str) -> Optional[dict[str, Any]]:
    """Looks up a user's stable `id` (a uuid) by login username -- needed
    wherever a foreign key (e.g. threads.user_id) must point at a user, since
    the JWT session cookie only carries the username."""
    conn = await asyncpg.connect(_asyncpg_dsn(database_url))
    try:
        row = await conn.fetchrow(
            'SELECT "id", "identifier" FROM users WHERE "identifier" = $1', username
        )
    finally:
        await conn.close()
    return dict(row) if row else None


async def list_users(database_url: str) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(_asyncpg_dsn(database_url))
    try:
        rows = await conn.fetch(
            'SELECT "identifier", "createdAt" FROM users ORDER BY "createdAt"'
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()
