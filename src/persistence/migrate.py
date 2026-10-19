"""Versioned, transactional schema migration. Run explicitly before deployment."""

import asyncio
import os
from pathlib import Path
import asyncpg
from dotenv import load_dotenv
from src.common.database import dsn


async def migrate(url: str):
    conn = await asyncpg.connect(dsn(url), timeout=10)
    try:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(8230415)")
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            await conn.execute(
                (Path(__file__).resolve().parents[2] / "db/schema.sql").read_text(
                    encoding="utf-8-sig"
                )
            )
            for file in sorted(
                (Path(__file__).resolve().parents[2] / "db/migrations").glob("*.sql")
            ):
                if not await conn.fetchval(
                    "SELECT 1 FROM schema_migrations WHERE version=$1", file.name
                ):
                    await conn.execute(file.read_text(encoding="utf-8-sig"))
                    await conn.execute(
                        "INSERT INTO schema_migrations(version) VALUES($1)", file.name
                    )
    finally:
        await conn.close()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(migrate(os.environ["DATABASE_URL"]))
