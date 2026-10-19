"""Expiring quotas. Production counters are atomic and shared in Postgres."""

import hashlib
import os
import time
from fastapi import HTTPException
from src.common.database import connection

_hits = {}


def _client_ip(conn):
    # Uvicorn handles forwarding only from configured trusted proxy peers.
    # Never parse attacker-controlled X-Forwarded-For in application code.
    return conn.client.host if conn.client else "unknown"


async def enforce_rate_limit(
    conn, bucket, limit, window_seconds, *, subject=None, units=1
):
    if units < 1 or units > limit:
        raise HTTPException(429, "Request exceeds the available budget")
    key = hashlib.sha256(f"{bucket}:{subject or _client_ip(conn)}".encode()).hexdigest()
    if os.getenv("APP_ENV") == "production":
        async with connection(os.environ["DATABASE_URL"]) as db:
            accepted = await db.fetchval(
                """INSERT INTO quota_buckets(key,hits,expires_at)
                VALUES($1,$4,now()+$2*interval '1 second')
                ON CONFLICT(key) DO UPDATE SET
                hits=CASE WHEN quota_buckets.expires_at<=now() THEN $4 ELSE quota_buckets.hits+$4 END,
                expires_at=CASE WHEN quota_buckets.expires_at<=now() THEN EXCLUDED.expires_at ELSE quota_buckets.expires_at END
                WHERE quota_buckets.expires_at<=now() OR quota_buckets.hits+$4<=$3 RETURNING hits""",
                key,
                window_seconds,
                limit,
                units,
            )
            # Bounded opportunistic cleanup; expiry is enforced above regardless.
            await db.execute(
                "DELETE FROM quota_buckets WHERE key IN (SELECT key FROM quota_buckets WHERE expires_at<now() LIMIT 100)"
            )
        if accepted is not None:
            return
    else:
        now = time.monotonic()
        for old in [k for k, (_, expiry) in _hits.items() if expiry <= now]:
            _hits.pop(old, None)
        if key not in _hits and len(_hits) >= 10000:
            raise HTTPException(503, "Quota storage is full; try later")
        count, expiry = _hits.get(key, (0, now + window_seconds))
        if count + units <= limit:
            _hits[key] = (count + units, expiry)
            return
    raise HTTPException(
        429,
        "Request limit reached. Please try later.",
        headers={"Retry-After": str(window_seconds)},
    )
