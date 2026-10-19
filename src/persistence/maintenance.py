"""Scheduled retention. Dry-run by default; deletion requires --apply."""

import argparse
import asyncio
import os
from src.common.database import connection, close_pools
from dotenv import load_dotenv


async def maintain(url, days, apply=False):
    if not 1 <= days <= 3650:
        raise ValueError("Retention days must be between 1 and 3650")
    async with connection(url) as db:
        async with db.transaction():
            sessions = await db.fetchval(
                "SELECT count(*) FROM sessions WHERE expires_at<now()"
            )
            quotas = await db.fetchval(
                "SELECT count(*) FROM quota_buckets WHERE expires_at<now()"
            )
            candidates = await db.fetch(
                """SELECT id FROM threads t WHERE t.created_at::timestamptz<now()-$1*interval '1 day'
                AND NOT EXISTS(SELECT 1 FROM messages m WHERE m.thread_id=t.id AND m.created_at::timestamptz>=now()-$1*interval '1 day')
                AND NOT EXISTS(SELECT 1 FROM turns x WHERE x.thread_id=t.id AND x.status='running') LIMIT 500""",
                days,
            )
            deleted = 0
            if apply:
                await db.execute("DELETE FROM sessions WHERE expires_at<now()")
                await db.execute("DELETE FROM quota_buckets WHERE expires_at<now()")
                for row in candidates:
                    if await db.fetchval(
                        "SELECT pg_try_advisory_xact_lock(hashtextextended($1,0))",
                        row["id"],
                    ):
                        result = await db.execute(
                            """DELETE FROM threads t WHERE id=$1
                            AND NOT EXISTS(SELECT 1 FROM messages m WHERE m.thread_id=t.id AND m.created_at::timestamptz>=now()-$2*interval '1 day')
                            AND NOT EXISTS(SELECT 1 FROM turns x WHERE x.thread_id=t.id AND x.status='running')""",
                            row["id"],
                            days,
                        )
                        deleted += int(result == "DELETE 1")
            return {
                "expired_sessions": sessions,
                "expired_quota_buckets": quotas,
                "thread_candidates": len(candidates),
                "threads_deleted": deleted,
                "dry_run": not apply,
            }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    try:
        print(await maintain(os.environ["DATABASE_URL"], args.days, args.apply))
    finally:
        await close_pools()


if __name__ == "__main__":
    asyncio.run(main())
