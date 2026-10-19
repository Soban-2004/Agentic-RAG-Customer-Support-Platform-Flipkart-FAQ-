"""Turn leases and atomic conversation commits. No destructive regeneration."""

import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from src.common.database import connection
from src.persistence.chat_store import _now


class ConversationBusy(Exception):
    pass


class MessageConflict(Exception):
    pass


@asynccontextmanager
async def conversation_lock(url, thread_id):
    async with connection(url) as conn:
        # Transaction-scoped advisory locks also work through transaction-pooling
        # proxies. Never rely on session locks surviving PgBouncer handoffs.
        async with conn.transaction():
            from src.api.settings import settings

            await conn.execute(
                "SELECT set_config('idle_in_transaction_session_timeout',$1,true)",
                str((settings().turn_timeout + 30) * 1000),
            )
            locked = await conn.fetchval(
                "SELECT pg_try_advisory_xact_lock(hashtextextended($1,0))", thread_id
            )
            if not locked:
                raise ConversationBusy(
                    "Another operation is running in this conversation"
                )
            yield


async def begin_turn(url, thread_id, client_id, content, *, image=None, target=None):
    fingerprint = hashlib.sha256(
        json.dumps(
            {"content": content, "image": image, "target": target}, sort_keys=True
        ).encode()
    ).hexdigest()
    async with connection(url) as conn:
        # A crashed turn is never automatically reexecuted: a mutation might have run.
        old = await conn.fetchrow(
            "SELECT * FROM turns WHERE thread_id=$1 AND client_message_id=$2",
            thread_id,
            client_id,
        )
        if old:
            if old["request_hash"] != fingerprint:
                raise MessageConflict("Message ID was reused with different content")
            return dict(old), False
        turn_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO turns(id,thread_id,client_message_id,request_hash,status,content,target_message_id) VALUES($1,$2,$3,$4,'running',$5,$6)",
            turn_id,
            thread_id,
            client_id,
            fingerprint,
            content,
            target,
        )
        return {"id": turn_id, "status": "running"}, True


async def commit_turn(
    url,
    thread_id,
    turn_id,
    content,
    response,
    *,
    sources=None,
    target=None,
    include_in_memory=True,
):
    user_id, assistant_id = str(uuid.uuid4()), str(uuid.uuid4())
    async with connection(url) as conn:
        async with conn.transaction():
            turn = await conn.fetchrow(
                "SELECT status FROM turns WHERE id=$1 AND thread_id=$2 FOR UPDATE",
                turn_id,
                thread_id,
            )
            if not turn or turn["status"] != "running":
                raise MessageConflict("Turn is no longer running")
            if target:
                old = await conn.fetchrow(
                    "SELECT id FROM messages WHERE id=$1 AND thread_id=$2 AND role='assistant' AND NOT superseded",
                    target,
                    thread_id,
                )
                if not old:
                    raise MessageConflict("Original response is no longer current")
                await conn.execute(
                    "UPDATE messages SET superseded=TRUE WHERE id=$1", target
                )
            else:
                await conn.execute(
                    "INSERT INTO messages(id,thread_id,role,content,created_at,turn_id) VALUES($1,$2,'user',$3,$4,$5)",
                    user_id,
                    thread_id,
                    content,
                    _now(),
                    turn_id,
                )
            await conn.execute(
                "INSERT INTO messages(id,thread_id,role,content,created_at,turn_id) VALUES($1,$2,'assistant',$3,$4,$5)",
                assistant_id,
                thread_id,
                response,
                _now(),
                turn_id,
            )
            await conn.execute(
                "UPDATE turns SET status='completed',response=$2,sources=$3::jsonb,finished_at=now(),include_in_memory=$4 WHERE id=$1",
                turn_id,
                response,
                json.dumps(sources or []),
                include_in_memory,
            )
    return assistant_id


async def fail_turn(url, turn_id):
    async with connection(url) as conn:
        await conn.execute(
            "UPDATE turns SET status='failed',finished_at=now() WHERE id=$1 AND status='running'",
            turn_id,
        )


async def regeneration_context(url, thread_id, message_id):
    async with connection(url) as conn:
        rows = await conn.fetch(
            "SELECT m.id,m.role,m.content,m.created_at,m.turn_id,t.include_in_memory FROM messages m LEFT JOIN turns t ON t.id=m.turn_id WHERE m.thread_id=$1 AND NOT m.superseded ORDER BY m.created_at,m.id",
            thread_id,
        )
        messages = [dict(r) for r in rows]
        index = next(
            (
                i
                for i, m in enumerate(messages)
                if m["id"] == message_id and m["role"] == "assistant"
            ),
            None,
        )
        if index is None:
            raise MessageConflict("Response not found")
        # Regenerate only the latest answer: later turns already depend on older answers.
        if (
            index != len(messages) - 1
            or index == 0
            or messages[index - 1]["role"] != "user"
        ):
            raise MessageConflict(
                "Only the latest complete response can be regenerated"
            )
        turn_id = messages[index]["turn_id"]
        actions = (
            await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM tool_actions WHERE thread_id=$1 AND id LIKE $2)",
                thread_id,
                f"{turn_id}:%",
            )
            if turn_id
            else True
        )
        if actions:
            raise MessageConflict("Responses involving actions cannot be regenerated")
        return messages[index - 1]["content"], [
            m for m in messages[: index - 1] if m.get("include_in_memory")
        ]
