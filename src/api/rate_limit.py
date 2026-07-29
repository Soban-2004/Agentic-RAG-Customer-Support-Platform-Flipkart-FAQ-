"""
Simple in-memory per-IP rate limiter for auth endpoints (register, login).

In-memory, not Redis-backed -- fine specifically because this app runs
single-worker, single-process by design already (see main.py's docstring:
the FunctionAgent/Settings/session-memory singletons all assume it). A
second worker would mean a second, disconnected copy of this limiter's state
too, same caveat as everything else process-wide here -- not a new one.

Exists because /api/auth/register is reachable by anyone on the public
internet with no admin gate, unlike the old CLI-only user provisioning --
unlimited scripted account creation would hit this app's own Groq/Cohere/
Qdrant free-tier quotas, not just clutter the users table.
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_hits: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    # Render (and most PaaS hosts) put the app behind a reverse proxy --
    # request.client.host would be the proxy's own address, identical for
    # every request, which would make per-IP limiting meaningless in
    # production. X-Forwarded-For's first entry is the original client;
    # falls back to request.client.host for local dev, where there's no
    # proxy and the header is absent.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, bucket: str, limit: int, window_seconds: int) -> None:
    """Raises 429 if this client has hit `bucket` more than `limit` times in
    the last `window_seconds`. Call at the top of a route, before any real
    work happens."""
    key = f"{bucket}:{_client_ip(request)}"
    now = time.monotonic()
    cutoff = now - window_seconds

    hits = _hits[key]
    # Prune expired hits lazily on each check instead of running a separate
    # cleanup job -- fine at this traffic scale. (Known, accepted limit: an
    # IP's dict entry itself isn't ever removed, only its hit list drained to
    # empty -- a slow, unbounded-over-very-long-uptime memory creep that
    # doesn't matter at a portfolio demo's actual traffic level.)
    while hits and hits[0] < cutoff:
        hits.pop(0)

    if len(hits) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Please try again in a few minutes.",
        )
    hits.append(now)
