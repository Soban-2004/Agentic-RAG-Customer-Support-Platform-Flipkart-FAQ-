"""Actor-scoped simulation adapter. No claims of real commerce/support delivery."""

import hashlib
import json
from src.agent.context import current_context
from src.api.config import DATABASE_URL
from src.common.database import connection
from src.tools.mock_backend import SEED_ORDERS, SEED_REFUNDS


async def _authorize():
    from src.api.security import session_user

    context = current_context()
    if not context.demo:
        user = await session_user(DATABASE_URL, context.session_token)
        from src.persistence.chat_store import get_thread

        if (
            not user
            or user["id"] != context.actor_id
            or not await get_thread(DATABASE_URL, context.thread_id, context.actor_id)
        ):
            raise PermissionError("Session expired or revoked")
    return context


def _resource(value):
    import re

    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{1,40}", value):
        raise ValueError("Invalid resource ID")
    return value


async def get_order_status(order_id: str) -> str:
    """Read a clearly labeled example order; never accesses real customer records."""
    context = await _authorize()
    context.tool_calls.append("get_order_status")
    order_id = _resource(order_id)
    order = next((r for r in SEED_ORDERS if r[0] == order_id), None)
    if not order:
        return f"No demonstration order found with ID {order_id}."
    if context.demo:
        notes = context.demo_state.get(order_id, [])
    else:
        async with connection(DATABASE_URL) as db:
            rows = await db.fetch(
                "SELECT result FROM tool_actions WHERE actor_id=$1 AND resource_id=$2 AND action='add_order_note' ORDER BY created_at DESC LIMIT 20",
                context.actor_id,
                order_id,
            )
        notes = [
            json.loads(r["result"])["note"]
            if isinstance(r["result"], str)
            else r["result"]["note"]
            for r in rows
        ]
    suffix = (" Your saved simulation notes: " + "; ".join(notes)) if notes else ""
    return (
        f"Demonstration order {order[0]} ({order[1]}): {order[2]}. Example delivery date: {order[3]}. These are fixture records, not live tracking."
        + suffix
    )


async def get_refund_status(refund_id: str) -> str:
    """Read a clearly labeled sample refund; never accesses real payment data."""
    context = await _authorize()
    context.tool_calls.append("get_refund_status")
    refund_id = _resource(refund_id)
    refund = next((r for r in SEED_REFUNDS if r[0] == refund_id), None)
    return (
        f"Demonstration refund {refund[0]} for {refund[1]}: {refund[2]}, Rs.{refund[3]:.2f}. This is simulated data."
        if refund
        else f"No demonstration refund found with ID {refund_id}."
    )


async def _record(action, resource, payload):
    context = await _authorize()
    if context.read_only:
        raise PermissionError("Mutations are disabled for regenerated responses")
    key = f"{context.turn_id}:{action}:{resource}"
    if context.demo:
        results = context.demo_state.setdefault("_action_results", {})
        if key in results:
            if results[key] != payload:
                raise ValueError("Action arguments changed within one turn")
            return results[key]
        if len(context.tool_calls) > 1:
            raise PermissionError("Only one business action is allowed per turn")
        results[key] = payload
        return payload
    async with connection(DATABASE_URL) as db:
        async with db.transaction():
            from src.api.security import decode_session

            claims = decode_session(context.session_token)
            valid = await db.fetchval(
                "SELECT id FROM sessions WHERE id=$1 AND user_id=$2 AND NOT revoked AND expires_at>now() FOR SHARE",
                claims["jti"] if claims else "",
                context.actor_id,
            )
            if not valid:
                raise PermissionError("Session expired or revoked")
            old = await db.fetchval(
                "SELECT result FROM tool_actions WHERE id=$1 AND actor_id=$2",
                key,
                context.actor_id,
            )
            if old is not None:
                old = json.loads(old) if isinstance(old, str) else old
                if old != payload:
                    raise ValueError(
                        "This action was already executed with different arguments"
                    )
                return old
            if len(context.tool_calls) > 1:
                raise PermissionError("Only one business action is allowed per turn")
            await db.execute(
                "INSERT INTO tool_actions(id,actor_id,thread_id,action,resource_id,result) VALUES($1,$2,$3,$4,$5,$6::jsonb)",
                key,
                context.actor_id,
                context.thread_id,
                action,
                resource,
                json.dumps(payload),
            )
    return payload


async def add_order_note(order_id: str, note: str) -> str:
    """Save a private simulation note for the current actor, never another customer."""
    context = await _authorize()
    context.tool_calls.append("add_order_note")
    order_id = _resource(order_id)
    if not any(row[0] == order_id for row in SEED_ORDERS):
        return "That demonstration order does not exist."
    note = note.strip()
    if not 1 <= len(note) <= 500:
        raise ValueError("Notes must contain 1–500 characters")
    await _record("add_order_note", order_id, {"note": note})
    if context.demo:
        notes = context.demo_state.setdefault(order_id, [])
        if len(notes) >= 20:
            return "This demo session has reached its note limit."
        if note not in notes:
            notes.append(note)
    return f"Simulation note saved for {order_id}. " + (
        "It will be discarded when this demo connection closes."
        if context.demo
        else "It is private to your account; no real order was changed."
    )


async def escalate_to_human(summary: str, order_id: str = "") -> str:
    """Simulate a handoff; no human-support integration is configured."""
    context = await _authorize()
    context.tool_calls.append("escalate_to_human")
    summary = summary.strip()
    if not 1 <= len(summary) <= 1000:
        raise ValueError("Summary must contain 1–1000 characters")
    order_id = _resource(order_id) if order_id else ""
    ticket = "SIM-" + hashlib.sha256(context.turn_id.encode()).hexdigest()[:10].upper()
    await _record(
        "escalate_to_human",
        order_id,
        {"ticket_id": ticket, "summary": summary, "simulated": True},
    )
    return f"Simulation ticket {ticket} created. No human agent has been notified: this app is not connected to a live support desk. Use Flipkart’s official help center for an actual escalation."
