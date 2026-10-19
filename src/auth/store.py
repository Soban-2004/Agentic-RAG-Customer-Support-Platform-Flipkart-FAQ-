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
from src.common.database import connect
import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_hash_limiter = anyio.CapacityLimiter(4)


def _verify(password, encoded):
    try:
        if encoded.startswith("$argon2"):
            return _hasher.verify(encoded, password)
        if len(password.encode("utf-8")) > 72:
            return False
        return bcrypt.checkpw(password.encode("utf-8"), encoded.encode("utf-8"))
    except (ValueError, VerificationError, InvalidHashError):
        return False


async def hash_password(password):
    return await anyio.to_thread.run_sync(_hasher.hash, password, limiter=_hash_limiter)


def _asyncpg_dsn(database_url: str) -> str:
    # asyncpg.connect() doesn't understand the "+asyncpg" driver suffix that
    # SQLAlchemy's async engine (used by the Chainlit data layer) requires.
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def verify_password(database_url: str, username: str, password: str) -> bool:
    conn = await connect(database_url)
    try:
        row = await conn.fetchrow(
            'SELECT "password_hash" FROM users WHERE "identifier" = $1', username
        )
    finally:
        await conn.close()
    if not row or not row["password_hash"]:
        # Equalize the expensive verification path for unknown accounts.
        await hash_password(password)
        return False
    encoded = row["password_hash"]
    valid = await anyio.to_thread.run_sync(
        _verify, password, encoded, limiter=_hash_limiter
    )
    if valid and (
        not encoded.startswith("$argon2") or _hasher.check_needs_rehash(encoded)
    ):
        upgraded = await hash_password(password)
        conn = await connect(database_url)
        try:
            await conn.execute(
                "UPDATE users SET password_hash=$1 WHERE identifier=$2 AND password_hash=$3",
                upgraded,
                username,
                encoded,
            )
        finally:
            await conn.close()
    return valid


async def register_user(database_url: str, username: str, password: str) -> bool:
    """Public self-serve signup (src/api/auth.py's /register route) --
    insert-only, returns False if the username is already taken rather than
    silently overwriting it. Deliberately separate from create_user() below:
    that one upserts (resets the password on an existing username), which is
    the right behavior for an admin deliberately resetting a demo/admin
    account via the CLI, but would be an account-takeover bug if reused here
    -- anyone could "register" someone else's existing username to silently
    hijack their password.
    """
    password_hash = await hash_password(password)
    conn = await connect(database_url)
    try:
        # The UNIQUE constraint on "identifier" (db/schema.sql) is the real
        # guard against a race between two concurrent signups for the same
        # username -- caught here rather than relied on as a pre-check alone,
        # since a plain SELECT-then-INSERT has a TOCTOU gap a public,
        # uncontrolled-concurrency endpoint can actually hit.
        try:
            await conn.execute(
                'INSERT INTO users ("id", "identifier", "createdAt", "metadata", "password_hash") '
                "VALUES ($1, $2, $3, $4, $5)",
                str(uuid.uuid4()),
                username,
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "{}",
                password_hash,
            )
            return True
        except asyncpg.UniqueViolationError:
            return False
    finally:
        await conn.close()


async def create_user(database_url: str, username: str, password: str) -> None:
    password_hash = await hash_password(password)
    conn = await connect(database_url)
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
            await conn.execute(
                "UPDATE sessions SET revoked=TRUE WHERE user_id=$1", existing["id"]
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


async def get_user_by_identifier(
    database_url: str, username: str
) -> Optional[dict[str, Any]]:
    """Looks up a user's stable `id` (a uuid) by login username -- needed
    wherever a foreign key (e.g. threads.user_id) must point at a user, since
    the JWT session cookie only carries the username."""
    conn = await connect(database_url)
    try:
        row = await conn.fetchrow(
            'SELECT "id", "identifier" FROM users WHERE "identifier" = $1', username
        )
    finally:
        await conn.close()
    return dict(row) if row else None


async def list_users(database_url: str) -> list[dict[str, Any]]:
    conn = await connect(database_url)
    try:
        rows = await conn.fetch(
            'SELECT "identifier", "createdAt" FROM users ORDER BY "createdAt"'
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()
