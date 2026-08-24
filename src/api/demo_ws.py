"""No-login demo WebSocket endpoint -- lets a recruiter/evaluator try the
system in a few seconds without creating an account.

Reuses the exact same guardrail -> intent -> cache -> agent -> output-scan
pipeline as the authenticated /ws/chat/{thread_id} route, via chat_ws.py's
shared _handle_turn/_run_turn (persist=False threads through them, so every
chat_store/Postgres call is skipped -- see that module). Two things are
deliberately different from a real session:

- No auth check at all -- this is the point.
- Conversation memory is a fresh, in-process-only SQLite `:memory:` database
  per connection (src/memory/persistent_memory.py's build_ephemeral_memory),
  not the shared chat_memory.db file real sessions persist to. It still gives
  the agent multi-turn coherence *within* one demo conversation, but nothing
  outlives the WebSocket -- close the tab and it's gone, matching the "try it,
  nothing is saved" promise on the frontend.

Rate-limited per-IP on message sends (not just on connect, since a client can
just reconnect and reset any connect-time counter) -- this is the one endpoint
in the whole app with zero auth gate, sitting directly on this app's own
Groq/Cohere/Qdrant free-tier quotas, so it needs its own throttle independent
of anything an account-holder does. The 429 is surfaced as an ordinary "done"
frame with a friendly message rather than a WS close/error -- the frontend
doesn't need any new frame-type handling for it, and the connection stays
open so the visitor can just wait out the window.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from src.api import state
from src.api.chat_ws import _handle_turn
from src.api.rate_limit import enforce_rate_limit
from src.memory.persistent_memory import build_ephemeral_memory

logger = logging.getLogger("api.demo_ws")

router = APIRouter()

# Looser than a real account needs (nothing to abuse across turns beyond API
# quota) but tight enough that a script can't hammer Groq/Cohere/Qdrant for
# free -- generous enough for a real evaluator working through the starter
# prompts a few times over.
_DEMO_MESSAGE_LIMIT = 15
_DEMO_WINDOW_SECONDS = 600  # 10 minutes

_RATE_LIMITED_REPLY = (
    "You're sending messages a little fast for the demo -- please wait a few "
    "minutes and try again. Sign up for unlimited use, no per-message limit."
)


@router.websocket("/ws/demo")
async def demo_ws(websocket: WebSocket) -> None:
    if state.agent is None:
        await websocket.close(code=1011)
        return

    await websocket.accept()
    # Only used for tracing (session_id) and log lines below -- never touches
    # Postgres, since _handle_turn(..., persist=False) skips every chat_store
    # call regardless of what's passed as thread_id.
    session_id = f"demo-{uuid.uuid4()}"
    memory = build_ephemeral_memory()
    try:
        while True:
            data = await websocket.receive_json()
            content = (data.get("content") or "").strip()
            if not content:
                continue
            try:
                enforce_rate_limit(
                    websocket, "demo_message", limit=_DEMO_MESSAGE_LIMIT, window_seconds=_DEMO_WINDOW_SECONDS
                )
            except HTTPException:
                await websocket.send_json({"type": "done", "content": _RATE_LIMITED_REPLY})
                continue
            await _handle_turn(websocket, session_id, "demo-guest", memory, content, persist=False)
    except WebSocketDisconnect:
        pass
