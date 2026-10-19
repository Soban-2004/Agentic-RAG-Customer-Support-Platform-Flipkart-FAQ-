"""Validated, bounded chat transport with durable turn acknowledgments."""

import asyncio
import json
import logging
import time
import os
import uuid
from collections import Counter
from dataclasses import replace
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import ValidationError
from src.api import state, security
from src.api import connections
from src.api.config import DATABASE_URL
from src.api.settings import settings
from src.api.protocol import parse_frame
from src.api.rate_limit import enforce_rate_limit, _client_ip
from src.agent.context import ToolContext, tool_context
from src.agent.run_turn import answer_turn
from src.gateway.vision import ImageTooLarge, UnsupportedImageType
from src.memory.persistent_memory import build_session_memory
from src.persistence import chat_store, turns

logger = logging.getLogger(__name__)
router = APIRouter()
_connections = Counter()
_active = 0
_slots = None
_IMAGE_ONLY_DEFAULT_CONTENT = "Please take a look at this photo."


def _parse_image(data):
    image = data.get("image")
    return image if isinstance(image, dict) else None


async def _stream_text(websocket, text):
    # Reveal only reviewed, committed content, without artificial per-word latency.
    for start in range(0, len(text), 160):
        await websocket.send_json({"type": "token", "delta": text[start : start + 160]})


async def terminal_error(websocket, code, message, client_id=None):
    await websocket.send_json(
        {
            "type": "error",
            "code": code,
            "message": message,
            "client_message_id": client_id,
        }
    )


async def reserve_work(websocket, actor, has_image=False):
    identity = (
        actor.actor_id if not actor.demo else "anonymous:" + _client_ip(websocket)
    )
    await enforce_rate_limit(
        websocket,
        "daily_work",
        int(os.getenv("DAILY_TURN_LIMIT", "500")),
        86400,
        subject="global",
    )
    # A conservative reservation, not provider billing. Never refunded on errors:
    # failed/cancelled calls can still have incurred upstream costs.
    await enforce_rate_limit(
        websocket,
        "reserved_tokens",
        int(os.getenv("DAILY_RESERVED_TOKEN_LIMIT", "10000000")),
        86400,
        subject="global",
        units=100000,
    )
    await enforce_rate_limit(
        websocket,
        "actor_reserved_tokens",
        int(os.getenv("ACCOUNT_DAILY_RESERVED_TOKEN_LIMIT", "2000000")),
        86400,
        subject=identity,
        units=100000,
    )
    if has_image:
        await enforce_rate_limit(websocket, "images", 10, 86400, subject=identity)
        await enforce_rate_limit(
            websocket,
            "global_images",
            int(os.getenv("DAILY_IMAGE_LIMIT", "30")),
            86400,
            subject="global",
        )


async def _handle_turn(
    websocket,
    thread_id,
    username,
    memory,
    content,
    *,
    persist=True,
    image=None,
    client_id=None,
    target=None,
    context=None,
    session_token=None,
):
    global _slots
    config = settings()
    if _slots is None:
        _slots = asyncio.Semaphore(config.max_concurrent)
    if _slots.locked():
        await terminal_error(
            websocket, "busy", "Support is busy. Try again shortly.", client_id
        )
        return
    await _slots.acquire()
    turn_id = None
    created = False
    started = time.monotonic()
    try:
        if persist:
            async with turns.conversation_lock(DATABASE_URL, thread_id):
                # Ownership can change after the initial handshake (e.g. deletion).
                user = await security.session_user(DATABASE_URL, session_token)
                if (
                    not user
                    or user["id"] != context.actor_id
                    or not await chat_store.get_thread(
                        DATABASE_URL, thread_id, user["id"]
                    )
                ):
                    raise PermissionError(
                        "This session or conversation is no longer available"
                    )
                if target:
                    original, history = await turns.regeneration_context(
                        DATABASE_URL, thread_id, target
                    )
                    if original != content:
                        raise turns.MessageConflict(
                            "Regeneration content does not match the original question"
                        )
                else:
                    history = await chat_store.list_messages(
                        DATABASE_URL, thread_id, limit=100, for_memory=True
                    )
                record, created = await turns.begin_turn(
                    DATABASE_URL,
                    thread_id,
                    client_id,
                    content,
                    image=image,
                    target=target,
                )
                turn_id = record["id"]
                if not created:
                    if record["status"] == "completed":
                        await websocket.send_json(
                            {
                                "type": "done",
                                "content": record["response"],
                                "client_message_id": client_id,
                                "replayed": True,
                                "reload_history": True,
                            }
                        )
                    else:
                        await terminal_error(
                            websocket,
                            "not_replayed",
                            "This message was already attempted. Reload history before starting a new request.",
                            client_id,
                        )
                    return
                await reserve_work(websocket, context, bool(image))
                memory = build_session_memory(thread_id, messages=history)
                actor = replace(
                    context,
                    turn_id=turn_id,
                    read_only=bool(target),
                    sources=[],
                    tool_calls=[],
                )
                with tool_context(actor):
                    answer = await asyncio.wait_for(
                        answer_turn(websocket, memory, content, image),
                        config.turn_timeout,
                    )
                # Re-check revocation before acknowledging/persisting an answer.
                if not await security.session_user(DATABASE_URL, session_token):
                    raise PermissionError("Your session ended. Sign in again.")
                assistant_id = await turns.commit_turn(
                    DATABASE_URL,
                    thread_id,
                    turn_id,
                    content,
                    answer.content,
                    sources=answer.sources,
                    target=target,
                    include_in_memory=answer.memory_safe,
                )
                await _stream_text(websocket, answer.content)
                await websocket.send_json(
                    {
                        "type": "done",
                        "content": answer.content,
                        "assistant_message_id": assistant_id,
                        "client_message_id": client_id,
                        "sources": answer.sources,
                    }
                )
        else:
            await reserve_work(websocket, context, bool(image))
            actor = replace(context, turn_id=client_id, sources=[], tool_calls=[])
            with tool_context(actor):
                answer = await asyncio.wait_for(
                    answer_turn(websocket, memory, content, image), config.turn_timeout
                )
            memory.set(memory.get())
            await _stream_text(websocket, answer.content)
            await websocket.send_json(
                {
                    "type": "done",
                    "content": answer.content,
                    "client_message_id": client_id,
                    "sources": answer.sources,
                }
            )
    except (
        turns.ConversationBusy,
        turns.MessageConflict,
        PermissionError,
        ValueError,
    ) as exc:
        if persist and created:
            await turns.fail_turn(DATABASE_URL, turn_id)
        await terminal_error(websocket, "rejected", str(exc), client_id)
    except HTTPException as exc:
        if persist and created:
            await turns.fail_turn(DATABASE_URL, turn_id)
        await terminal_error(websocket, "rate_limit", str(exc.detail), client_id)
    except asyncio.CancelledError:
        if persist and created:
            try:
                await asyncio.wait_for(
                    asyncio.shield(turns.fail_turn(DATABASE_URL, turn_id)), 5
                )
            except Exception:
                pass
        raise
    except WebSocketDisconnect:
        # Committed results are recovered through history or the same message ID.
        raise
    except Exception as exc:
        logger.error("Turn failed; turn_id=%s kind=%s", turn_id, type(exc).__name__)
        if persist and created:
            try:
                await turns.fail_turn(DATABASE_URL, turn_id)
            except Exception:
                logger.error("Could not mark failed turn; turn_id=%s", turn_id)
        await terminal_error(
            websocket,
            "unavailable",
            "The request could not be completed. Reload history before retrying an action.",
            client_id,
        )
    finally:
        logger.info(
            "turn_finished turn_id=%s duration_ms=%d",
            turn_id,
            int((time.monotonic() - started) * 1000),
        )
        _slots.release()


async def _serve_connection(websocket, *, thread_id=None):
    global _active
    config = settings()
    if not thread_id and os.getenv("ENABLE_DEMO", "true").lower() == "false":
        await websocket.close(code=1008)
        return
    if not security.origin_allowed(websocket):
        await websocket.close(code=1008)
        return
    if state.agent is None:
        await websocket.close(code=1013)
        return
    user = None
    token = websocket.cookies.get(security.COOKIE_NAME)
    if thread_id:
        user = await security.session_user(DATABASE_URL, token)
        if not user or not await chat_store.get_thread(
            DATABASE_URL, thread_id, user["id"]
        ):
            await websocket.close(code=1008)
            return
    key = user["id"] if user else _client_ip(websocket)
    if _connections[key] >= 2 or _active >= config.max_connections:
        await websocket.close(code=1013)
        return
    try:
        await enforce_rate_limit(websocket, "connect", 30, 600, subject=key)
    except HTTPException:
        await websocket.close(code=1013)
        return
    if _connections[key] >= 2 or _active >= config.max_connections:
        await websocket.close(code=1013)
        return
    _connections[key] += 1
    _active += 1
    registered = None
    try:
        await websocket.accept()
        registered = connections.register(token, websocket) if user else None
        session = thread_id or "demo-" + str(uuid.uuid4())
        actor = ToolContext(
            actor_id=user["id"] if user else session,
            thread_id=session,
            turn_id="",
            session_token=token,
            demo=user is None,
        )
        memory = build_session_memory(session)
        seen = set()
        while True:
            try:
                claims = security.decode_session(token) if user else None
                if user and claims is None:
                    await websocket.close(code=1008)
                    return
                remaining = (
                    max(0.1, claims["exp"] - time.time())
                    if claims
                    else config.idle_timeout
                )
                raw = await asyncio.wait_for(
                    websocket.receive_text(), min(config.idle_timeout, remaining)
                )
                await enforce_rate_limit(
                    websocket,
                    "chat",
                    config.chat_per_hour if user else 15,
                    3600 if user else 600,
                    subject=key,
                )
                message = parse_frame(raw)
                if user and not await security.session_user(DATABASE_URL, token):
                    await websocket.close(code=1008)
                    return
                if message.image:
                    from src.gateway.vision import validate_image

                    validate_image(message.image.data, message.image.mime_type)
                if user is None:
                    if message.regenerate_message_id:
                        raise ValueError("Demo responses cannot be regenerated")
                    if message.client_message_id in seen:
                        raise ValueError("This demo message was already attempted")
                    seen.add(message.client_message_id)
                    if len(seen) > 100:
                        await websocket.close(code=1008)
                        return
                await asyncio.wait_for(
                    _handle_turn(
                        websocket,
                        session,
                        user["identifier"] if user else "demo",
                        memory,
                        message.content or _IMAGE_ONLY_DEFAULT_CONTENT,
                        persist=user is not None,
                        image=message.image.model_dump() if message.image else None,
                        client_id=message.client_message_id,
                        target=message.regenerate_message_id,
                        context=actor,
                        session_token=token,
                    ),
                    config.turn_timeout + 30,
                )
            except (
                ValidationError,
                ValueError,
                json.JSONDecodeError,
                KeyError,
                ImageTooLarge,
                UnsupportedImageType,
            ):
                await terminal_error(
                    websocket,
                    "invalid_message",
                    "Send a valid bounded message with a unique client_message_id.",
                )
            except HTTPException as exc:
                await terminal_error(websocket, "rate_limit", str(exc.detail))
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        logger.error("Chat connection failed")
    finally:
        connections.unregister(registered, websocket)
        _connections[key] -= 1
        if not _connections[key]:
            del _connections[key]
        _active -= 1
        try:
            await websocket.close()
        except RuntimeError:
            pass


async def serve_connection(websocket, *, thread_id=None):
    try:
        await _serve_connection(websocket, thread_id=thread_id)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WebSocket handshake unavailable: %s", type(exc).__name__)
        try:
            await websocket.close(code=1013)
        except RuntimeError:
            pass


@router.websocket("/ws/chat/{thread_id}")
async def chat_ws(websocket: WebSocket, thread_id: str):
    await serve_connection(websocket, thread_id=thread_id)
