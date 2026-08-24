"""
Persistent short-term (session) memory.

Wraps LlamaIndex's Memory class with SQL persistence (SQLite) instead of the
default in-process-only buffer -- conversation history for a given session_id
survives an app restart instead of vanishing with it (LlamaIndex creates and
manages its own schema, no setup needed).

`session_id` here should be a stable, long-lived identifier, not Chainlit's own
per-connection `session.id` (a fresh uuid every websocket connection). app.py
passes `cl.context.session.thread_id` instead -- with login + the Postgres
data layer wired up (see db/schema.sql, src/auth/), that thread_id is stable
across a hard refresh and across resuming an old thread from the sidebar, so
this memory genuinely follows the conversation rather than resetting on every
reconnect. See src/tools/mock_backend.py's order_notes for the other kind of
memory here: it survives across *separate* conversations entirely, anchored to
an order ID instead of any session/thread identity.
"""

import uuid
from pathlib import Path

from llama_index.core.memory import Memory

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "chat_memory.db"
DB_URI = f"sqlite+aiosqlite:///{DB_PATH}"


def build_session_memory(session_id: str, token_limit: int = 4000) -> Memory:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return Memory.from_defaults(
        session_id=session_id,
        token_limit=token_limit,
        async_database_uri=DB_URI,
    )


def build_ephemeral_memory(token_limit: int = 4000) -> Memory:
    """Demo-mode memory (see src/api/demo_ws.py) -- a fresh, in-process-only
    SQLite `:memory:` database per call instead of the shared chat_memory.db
    file real sessions persist to. Discarded along with the connection that
    created it, so a no-login demo conversation never touches disk and never
    outlives its WebSocket -- there's no thread to revisit, so nothing to
    persist in the first place."""
    return Memory.from_defaults(
        session_id=str(uuid.uuid4()),
        token_limit=token_limit,
        async_database_uri="sqlite+aiosqlite:///:memory:",
    )
