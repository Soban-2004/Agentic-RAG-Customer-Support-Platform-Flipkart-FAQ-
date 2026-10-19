"""Generate a reviewed answer; transport/persistence own completion semantics."""

import asyncio
import logging
from dataclasses import dataclass

from llama_index.core import Settings
from llama_index.core.agent.workflow import AgentStream, ToolCall
from llama_index.core.llms import ChatMessage

from src.agent.context import current_context
from src.agent.evidence import grounded_text, public_faq_query
from src.agent.planner import IntentLabel, classify_intent
from src.api import state
from src.api.settings import settings
from src.gateway.guardrails import GuardrailBlocked, scan_bot_output, scan_user_input
from src.gateway.vision import describe_damage_photo, validate_image

logger = logging.getLogger(__name__)

_SOCIAL_RESPONSE = (
    "Hi! I can help with **orders, delivery, returns, refunds, payments, EMI, "
    "cancellations, account help,** and connecting you with support. What can I help "
    "you with?"
)
_OUT_OF_SCOPE_RESPONSE = (
    "I can only help with **shopping and customer-support questions** here, such as "
    "orders, delivery, returns, refunds, payments, cancellations, and account help."
)
_ONE_ACTION_RESPONSE = (
    "Please ask for **one account action at a time** so I can complete it safely—for "
    "example, check an order, check a refund, save an order note, or request a human."
)


@dataclass
class Answer:
    content: str
    sources: list
    memory_safe: bool = True


async def _cached(query):
    try:
        return await asyncio.wait_for(state.cache.get(query), timeout=3)
    except Exception:
        logger.warning("FAQ cache unavailable")
        return None


async def answer_turn(websocket, memory, query, image=None):
    context = current_context()
    await websocket.send_json({"type": "status", "label": "Checking your message…"})
    try:
        query = await scan_user_input(query)
    except GuardrailBlocked as exc:
        if exc.scanner == "GuardUnavailable":
            return Answer(
                "Message checking is temporarily unavailable. Please try again "
                "shortly.",
                [],
                False,
            )
        return Answer(
            "Please ask an order, refund, payment, or returns question.", [], False
        )
    if image:
        validate_image(image["data"], image["mime_type"])
        await websocket.send_json({"type": "status", "label": "Looking at your photo…"})
        try:
            description = await describe_damage_photo(image["data"], image["mime_type"])
        except Exception:
            return Answer(
                "I couldn't analyze the attached image. Please try again or send a "
                "text-only question.",
                [],
            )
        query = await scan_user_input(
            query
            + "\n[Unverified automated photo description; not proof of damage: "
            + description
            + "]"
        )
    intent = await classify_intent(Settings.llm, query)
    # These branches are deliberately deterministic. Unrelated questions never reach
    # the general-purpose model, and a classifier mistake into GENERAL_CHAT still
    # cannot produce a general-knowledge answer.
    if intent == IntentLabel.GENERAL_CHAT:
        return Answer(_SOCIAL_RESPONSE, [])
    if intent == IntentLabel.OUT_OF_SCOPE:
        return Answer(_OUT_OF_SCOPE_RESPONSE, [], False)
    if intent == IntentLabel.MULTI_ACTION:
        return Answer(_ONE_ACTION_RESPONSE, [], False)
    public = intent == IntentLabel.FAQ_LOOKUP and public_faq_query(query) and not image
    cache_allowed = (
        public
        and not context.demo
        and not context.read_only
        and settings().shared_cache
        and state.cache is not None
    )
    if cache_allowed:
        hit = await _cached(query)
        if hit:
            return Answer(hit["response"], hit.get("sources", []))
    if public:
        await websocket.send_json(
            {"type": "status", "label": "Searching policy documents…"}
        )
        response = await state.faq_engine.aquery(query)
        content, sources = grounded_text(response)
        content, flag = await scan_bot_output(query, content)
        if cache_allowed and sources and not flag:
            try:
                await asyncio.wait_for(
                    state.cache.set(query, content, sources=sources), timeout=3
                )
            except Exception:
                logger.warning("FAQ cache write unavailable")
        await memory.aput_messages(
            [
                ChatMessage(role="user", content=query),
                ChatMessage(role="assistant", content=content),
            ]
        )
        return Answer(content, sources)
    await websocket.send_json({"type": "status", "label": "Working on your question…"})
    handler = state.agent.run(user_msg=query, memory=memory, max_iterations=6)
    full = ""
    try:
        async for event in handler.stream_events():
            if isinstance(event, AgentStream) and event.delta:
                full += event.delta
                if len(full) > 24000:
                    raise ValueError("Response exceeds output limit")
            elif isinstance(event, ToolCall):
                await websocket.send_json(
                    {"type": "status", "label": "Checking the requested information…"}
                )
        result = await handler
        full = result.response.content or full or ""
    except BaseException:
        if hasattr(handler, "cancel_run"):
            try:
                await handler.cancel_run()
            except Exception:
                pass
        raise
    if not full.strip():
        raise ValueError("Empty model response")
    # No unreviewed model deltas leave the server.
    content, _ = await scan_bot_output(query, full)
    return Answer(content, context.sources)
