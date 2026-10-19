"""Bounded Postgres pools shared by auth, chat, sessions, and quotas."""

import asyncio
import os
from contextlib import asynccontextmanager
import asyncpg

_pools = {}
_lock = asyncio.Lock()


def dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def pool(url: str):
    async with _lock:
        if url not in _pools:
            _pools[url] = await asyncpg.create_pool(
                dsn(url),
                min_size=1,
                max_size=int(os.getenv("DB_POOL_SIZE", "12")),
                timeout=10,
                command_timeout=15,
                max_inactive_connection_lifetime=120,
            )
        return _pools[url]


class Lease:
    def __init__(self, owner, connection):
        self.owner, self.connection = owner, connection

    def __getattr__(self, name):
        return getattr(self.connection, name)

    async def close(self):
        if self.connection is not None:
            await self.owner.release(self.connection)
            self.connection = None


async def connect(url: str):
    owner = await pool(url)
    return Lease(owner, await owner.acquire(timeout=10))


@asynccontextmanager
async def connection(url: str):
    conn = await connect(url)
    try:
        yield conn
    finally:
        await conn.close()


async def close_pools():
    owners = list(_pools.values())
    _pools.clear()
    for owner in owners:
        try:
            await asyncio.wait_for(owner.close(), timeout=10)
        except asyncio.TimeoutError:
            owner.terminate()
