"""WebSocket chat endpoint -- the direct FastAPI port of the old
`_handle_message` in app.py (Chainlit's `@cl.on_message`). Same
guardrail-scan -> intent-classify -> cache-check -> agent-stream ->
output-scan -> cache-set sequence, reusing the gateway/agent/memory/tracing
modules completely unchanged; only the transport (WS JSON frames instead of
`cl.Message`) and persistence (our own Postgres tables instead of Chainlit's)
are new.

WS protocol: client sends `{"content": "..."}`; server replies with a stream
of zero or more `{"type": "status", "label": "..."}` frames (transient
progress indicators -- "Searching FAQ policies...", not persisted, purely for
perceived latency -- see the note below), zero or more
`{"type": "token", "delta": "..."}` frames, then exactly one
`{"type": "done", "content": "..."}` carrying the final (possibly
output-scan-corrected) text -- the frontend should treat "done" as
authoritative and overwrite whatever it assembled from token deltas.

Every tool here is `return_direct=True` (see chat_agent.py), which means the
*normal* case for a real question (FAQ lookup, order/refund status) never
streams a single token -- the whole answer arrives atomically in one "done"
frame. Token streaming only ever fires for plain small talk with no tool
call. That makes the status frames below load-bearing, not cosmetic: without
them, the 2-5s a real question spends in guardrail scanning + retrieval/tool
execution is completely silent on the wire.
"""

import asyncio
import contextlib
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langfuse import propagate_attributes
from llama_index.core import Settings
from llama_index.core.agent.workflow import AgentStream, ToolCall
from workflows.errors import WorkflowRuntimeError

from src.agent.chat_agent import clear_precomputed_query_embedding, set_precomputed_query_embedding
from src.agent.planner import CACHEABLE_INTENTS, classify_intent
from src.api import security, state
from src.api.config import DATABASE_URL
from src.auth.store import get_user_by_identifier
from src.gateway.guardrails import GuardrailBlocked, scan_bot_output, scan_user_input
from src.memory.persistent_memory import build_session_memory
from src.observability.tracing import get_tracing_client, score_cache_result, score_guardrail_event
from src.persistence import chat_store

logger = logging.getLogger("api.chat_ws")

router = APIRouter()

# Friendly, per-tool progress labels for the ToolCall status frame below --
# keyed by the exact tool name the agent calls (see src/agent/chat_agent.py /
# src/tools/mcp_server.py). Deliberately per-request, read off the specific
# `handler.stream_events()` for *this* turn -- not a global/shared handler --
# so there's no cross-session state to worry about, unlike Chainlit's old
# per-session `Settings.callback_manager` reassignment (see the migration
# plan's concurrency notes for why that pattern was avoided here).
_TOOL_STATUS_LABELS = {
    "search_faq": "Searching Flipkart's policies...",
    "get_order_status": "Checking your order...",
    "get_refund_status": "Checking your refund...",
    "add_order_note": "Saving a note to your order...",
    "escalate_to_human": "Escalating to a human agent...",
}

_STREAM_CHUNK_DELAY_SECONDS = 0.015


async def _stream_text(websocket: WebSocket, text: str) -> None:
    """Paces out an already-complete response (a cache hit, a return_direct
    tool's answer, a canned fallback/refusal message) as a sequence of token
    frames for a live-streaming visual.

    Every tool here is return_direct=True (see chat_agent.py) and the
    semantic cache serves a complete string -- neither can stream for real
    without a genuine extra LLM round-trip (and, for search_faq specifically,
    reintroducing a previously-found bug where the agent re-invokes the tool
    across an extra synthesis step -- see README's Agent + Planning section).
    Simulating the reveal instead costs ~15ms/word (well under a second even
    for a long answer) rather than a real second LLM call, while giving every
    response the token-by-token feel that was missing before.
    """
    for chunk in re.findall(r"\S+\s*", text):
        await websocket.send_json({"type": "token", "delta": chunk})
        await asyncio.sleep(_STREAM_CHUNK_DELAY_SECONDS)


async def _handle_turn(websocket: WebSocket, thread_id: str, username: str, memory, content: str) -> None:
    await chat_store.add_message(DATABASE_URL, thread_id, "user", content)

    tracing_client = get_tracing_client()
    span_cm = (
        tracing_client.start_as_current_observation(name="chat_message", input=content)
        if tracing_client
        else contextlib.nullcontext()
    )
    with span_cm:
        attrs_cm = (
            propagate_attributes(user_id=username, session_id=thread_id, tags=["fastapi-ws"])
            if tracing_client
            else contextlib.nullcontext()
        )
        with attrs_cm:
            await _run_turn(websocket, thread_id, memory, content)


async def _persist_assistant_reply(thread_id: str, content: str) -> None:
    """Called AFTER the "done" frame is already on the wire -- the user
    already has their answer, so a persistence failure here isn't a turn
    failure to recover from, just something to log. Worst case on a real
    failure: a reload/thread-revisit is missing this one message, an
    acceptable rare trade against making every user wait on a Neon
    round-trip whose result they can't actually see."""
    try:
        await chat_store.add_message(DATABASE_URL, thread_id, "assistant", content)
    except Exception:
        logger.exception("chat_ws: failed to persist assistant reply after it was already sent")


async def _run_turn(websocket: WebSocket, thread_id: str, memory, content: str) -> None:
    # 1. Guardrails: input scan. Blocked messages never reach the LLM/cache/tools.
    # Consistently the single biggest chunk of a turn's latency (several
    # ML scanners running in sequence, ~1.5-4.5s observed) -- worth its own
    # status frame rather than lumping it into a generic "thinking".
    await websocket.send_json({"type": "status", "label": "Checking your message..."})
    try:
        query = await scan_user_input(content)
    except GuardrailBlocked as exc:
        score_guardrail_event("input", exc.scanner)
        reply = (
            "Sorry, I can't help with that request. Please ask a Flipkart "
            "order, payment, refund, or returns question."
        )
        await _stream_text(websocket, reply)
        await websocket.send_json({"type": "done", "content": reply})
        await _persist_assistant_reply(thread_id, reply)
        return

    # 2. Planning: classify intent. Only FAQ/general_chat may use the semantic
    # cache -- order/refund/escalation answers are per-user and dynamic.
    intent = await classify_intent(Settings.llm, query)
    logger.info("intent=%s query=%r", intent.value, query[:80])
    cacheable = intent in CACHEABLE_INTENTS

    # Embedded once (if at all) and reused for the cache check below, the
    # cache write at the end of this turn, and -- when the agent happens to
    # call search_faq with this exact same text -- that retrieval too (see
    # _CachedQueryEngineTool in chat_agent.py). Each reuse skips a redundant
    # Cohere/embed-API round trip for text we've already embedded this turn.
    query_embedding: list[float] | None = None

    if cacheable and state.cache:
        query_embedding = await Settings.embed_model.aget_query_embedding(query)
        cached_response = await state.cache.get(query, embedding=query_embedding)
        score_cache_result(hit=cached_response is not None)
        if cached_response is not None:
            await _stream_text(websocket, cached_response)
            await websocket.send_json({"type": "done", "content": cached_response})
            await _persist_assistant_reply(thread_id, cached_response)
            return

    if query_embedding is not None:
        set_precomputed_query_embedding(query, query_embedding)
    else:
        clear_precomputed_query_embedding()

    # 3. Run the agent, streaming the response token-by-token.
    await websocket.send_json({"type": "status", "label": "Thinking..."})
    handler = state.agent.run(user_msg=query, memory=memory, max_iterations=6)
    full_response = ""
    did_stream = False  # True only if real AgentStream deltas were sent (small talk, no tool call)
    try:
        async for event in handler.stream_events():
            if isinstance(event, AgentStream) and event.delta:
                full_response += event.delta
                did_stream = True
                await websocket.send_json({"type": "token", "delta": event.delta})
            elif isinstance(event, ToolCall):
                label = _TOOL_STATUS_LABELS.get(event.tool_name, "Looking that up...")
                await websocket.send_json({"type": "status", "label": label})
        result = await handler
    except WorkflowRuntimeError:
        logger.exception("agent: max iterations exceeded")
        full_response = (
            "Sorry, I'm having trouble answering that right now. Could you try "
            "rephrasing, or asking a more specific question?"
        )
        result = None
    except Exception:
        logger.exception("agent: run failed")
        # Persist whatever streamed through before the failure rather than
        # silently discarding it -- covers both a genuine agent error and a
        # mid-stream client disconnect (send_json above raises here too).
        if full_response:
            await chat_store.add_message(DATABASE_URL, thread_id, "assistant", full_response)
        full_response = (
            "Sorry, something went wrong on my end processing that. Please try again "
            "in a moment."
        )
        result = None

    agent_succeeded = result is not None

    # return_direct tools short-circuit the workflow with no further LLM
    # generation, so nothing streams via AgentStream -- fall back to the final
    # result's content in that case.
    if not full_response and agent_succeeded:
        full_response = result.response.content or ""

    # 4. Guardrails: output scan. Redacts PII in place before it's persisted or
    # sent as the authoritative "done" content.
    await websocket.send_json({"type": "status", "label": "Finalizing response..."})
    sanitized_response, triggered_scanner = await scan_bot_output(query, full_response)
    if triggered_scanner:
        score_guardrail_event("output", triggered_scanner)

    # Real small talk already streamed live above; everything else (every
    # tool-routed answer, which is most turns) never emitted a single token,
    # so simulate the reveal now that the final text is known -- see
    # _stream_text.
    if not did_stream:
        await _stream_text(websocket, sanitized_response)

    await websocket.send_json({"type": "done", "content": sanitized_response})
    await _persist_assistant_reply(thread_id, sanitized_response)

    # 5. Cache only clean, cache-eligible, successful responses -- never cache
    # something an output scanner flagged, a tool-routed (dynamic) answer, or
    # an error message from a failed/overrun agent run.
    if cacheable and state.cache and triggered_scanner is None and agent_succeeded:
        await state.cache.set(query, sanitized_response, embedding=query_embedding)


@router.websocket("/ws/chat/{thread_id}")
async def chat_ws(websocket: WebSocket, thread_id: str) -> None:
    token = websocket.cookies.get(security.COOKIE_NAME)
    username = security.decode_access_token(token)
    if not username:
        await websocket.close(code=1008)
        return

    user_row = await get_user_by_identifier(DATABASE_URL, username)
    if not user_row:
        await websocket.close(code=1008)
        return

    thread = await chat_store.get_thread(DATABASE_URL, thread_id, user_row["id"])
    if not thread:
        await websocket.close(code=1008)
        return

    if state.agent is None:
        await websocket.close(code=1011)
        return

    await websocket.accept()
    # Built once per connection, not per message -- it's SQL-backed
    # (src/memory/persistent_memory.py), so state lives in SQLite keyed by
    # thread_id, not in this object; rebuilding it per turn would just be
    # redundant engine setup.
    memory = build_session_memory(session_id=thread_id)
    try:
        while True:
            data = await websocket.receive_json()
            content = (data.get("content") or "").strip()
            if not content:
                continue
            await _handle_turn(websocket, thread_id, username, memory, content)
    except WebSocketDisconnect:
        pass
