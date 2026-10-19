import asyncio
import os
import uuid
from contextlib import asynccontextmanager

import pytest

from src.api import security
from src.auth.store import get_user_by_identifier, register_user
from src.common.database import close_pools, connection
from src.persistence import chat_store, turns
from src.persistence.migrate import migrate

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL to an isolated disposable Postgres database",
)


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    if os.getenv("TEST_DATABASE_URL"):
        from urllib.parse import urlsplit

        parsed = urlsplit(os.environ["TEST_DATABASE_URL"])
        if (
            parsed.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"}
            or parsed.port in {None, 5432}
            or parsed.path != "/aster_test"
        ):
            pytest.fail(
                "Integration tests require a disposable localhost Postgres instance "
                "on a nondefault port with database name aster_test"
            )
        asyncio.run(migrate(os.environ["TEST_DATABASE_URL"]))


async def actor():
    url = os.environ["DATABASE_URL"]
    name = "user_" + uuid.uuid4().hex[:12]
    await register_user(url, name, "valid-test-password")
    user = await get_user_by_identifier(url, name)
    return user, await security.issue_session(url, name)


@pytest.mark.asyncio
async def test_revocation_and_ownership():
    url = os.environ["DATABASE_URL"]
    alice, token = await actor()
    bob, _ = await actor()
    thread = await chat_store.create_thread(url, alice["id"], "private")
    assert await chat_store.get_thread(url, thread["id"], bob["id"]) is None
    assert (await security.session_user(url, token))["id"] == alice["id"]
    await security.revoke_session(url, token)
    assert await security.session_user(url, token) is None


@pytest.mark.asyncio
async def test_turn_commit_retry_and_conflict():
    url = os.environ["DATABASE_URL"]
    alice, _ = await actor()
    thread = (await chat_store.create_thread(url, alice["id"], "test"))["id"]
    record, created = await turns.begin_turn(url, thread, "one", "question")
    assert created
    assert await chat_store.list_messages(url, thread) == []
    await turns.commit_turn(url, thread, record["id"], "question", "answer")
    messages = await chat_store.list_messages(url, thread)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    replay, created = await turns.begin_turn(url, thread, "one", "question")
    assert not created and replay["response"] == "answer"
    with pytest.raises(turns.MessageConflict):
        await turns.begin_turn(url, thread, "one", "different")


@pytest.mark.asyncio
async def test_nondestructive_regeneration_and_deletion():
    url = os.environ["DATABASE_URL"]
    alice, _ = await actor()
    thread = (await chat_store.create_thread(url, alice["id"], "test"))["id"]
    record, _ = await turns.begin_turn(url, thread, "one", "question")
    target = await turns.commit_turn(
        url, thread, record["id"], "question", "old answer"
    )
    content, context = await turns.regeneration_context(url, thread, target)
    assert content == "question" and context == []
    replacement, _ = await turns.begin_turn(
        url, thread, "two", "question", target=target
    )
    await turns.commit_turn(
        url, thread, replacement["id"], "question", "new answer", target=target
    )
    assert [m["content"] for m in await chat_store.list_messages(url, thread)] == [
        "question",
        "new answer",
    ]
    async with connection(url) as db:
        assert (
            await db.fetchval("SELECT content FROM messages WHERE id=$1", target)
            == "old answer"
        )
    await chat_store.delete_thread(url, thread, alice["id"])
    async with connection(url) as db:
        assert (
            await db.fetchval("SELECT count(*) FROM turns WHERE thread_id=$1", thread)
            == 0
        )


@pytest.mark.asyncio
async def test_cross_connection_lease():
    url = os.environ["DATABASE_URL"]
    async with turns.conversation_lock(url, "test-lease"):
        with pytest.raises(turns.ConversationBusy):
            async with turns.conversation_lock(url, "test-lease"):
                pass


@pytest.mark.asyncio
async def test_actor_scoped_notes_and_idempotent_action():
    from src.agent.context import ToolContext, tool_context
    from src.tools.service import add_order_note, get_order_status

    url = os.environ["DATABASE_URL"]
    alice, token = await actor()
    bob, token_b = await actor()
    thread = (await chat_store.create_thread(url, alice["id"], "notes"))["id"]
    turn, _ = await turns.begin_turn(url, thread, "one", "note")
    with tool_context(
        ToolContext(alice["id"], thread, turn["id"], session_token=token)
    ):
        await add_order_note("FK1001", "private-marker")
        await add_order_note("FK1001", "private-marker")
        assert "private-marker" in await get_order_status("FK1001")
    bob_thread = (await chat_store.create_thread(url, bob["id"], "private"))["id"]
    with tool_context(
        ToolContext(bob["id"], bob_thread, "other", session_token=token_b)
    ):
        assert "private-marker" not in await get_order_status("FK1001")
    async with connection(url) as db:
        assert (
            await db.fetchval(
                "SELECT count(*) FROM tool_actions WHERE actor_id=$1", alice["id"]
            )
            == 1
        )


@pytest.mark.asyncio
async def test_shared_quota_atomic(monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException

    from src.api.rate_limit import enforce_rate_limit

    monkeypatch.setenv("APP_ENV", "production")
    conn = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    bucket = uuid.uuid4().hex
    results = await asyncio.gather(
        *(enforce_rate_limit(conn, bucket, 2, 60) for _ in range(8)),
        return_exceptions=True,
    )
    assert sum(result is None for result in results) == 2
    assert all(
        result is None
        or isinstance(result, HTTPException)
        and result.status_code == 429
        for result in results
    )


def test_websocket_validation_commit_and_idempotent_reconnect(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.agent.run_turn import Answer
    from src.api import chat_ws, state
    from src.api.auth import router as auth_router
    from src.api.rate_limit import _hits
    from src.api.threads import router as thread_router

    _hits.clear()
    calls = []

    async def answer(*args, **kwargs):
        calls.append(1)
        return Answer("Committed test answer", [])

    monkeypatch.setattr(chat_ws, "answer_turn", answer)
    monkeypatch.setattr(state, "agent", object())
    chat_ws._slots = None

    @asynccontextmanager
    async def lifespan(app):
        yield
        await close_pools()

    app = FastAPI(lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(thread_router)
    app.include_router(chat_ws.router)
    with TestClient(app) as client:
        account = "ws_" + uuid.uuid4().hex[:12]
        response = client.post(
            "/api/auth/register",
            json={"username": account, "password": "valid-test-password"},
        )
        assert response.status_code == 200, response.text
        thread = client.post("/api/threads", json={"title": "ws"}).json()["id"]
        payload = {"content": "test question", "client_message_id": "stable-one"}
        with client.websocket_connect("/ws/chat/" + thread) as ws:
            ws.send_json({"content": 42, "client_message_id": "bad"})
            assert ws.receive_json()["type"] == "error"
            ws.send_json(payload)
            while True:
                frame = ws.receive_json()
                assert frame["type"] != "error", frame
                if frame["type"] == "done":
                    break
            assert frame["assistant_message_id"]
            history = client.get("/api/threads/" + thread).json()["messages"]
            assert [message["role"] for message in history] == ["user", "assistant"]
            ws.send_json(payload)
            assert ws.receive_json()["replayed"] is True
        from fastapi import WebSocketDisconnect

        with client.websocket_connect("/ws/chat/" + thread) as resumed:
            client.post("/api/auth/logout")
            with pytest.raises(WebSocketDisconnect) as exc:
                resumed.receive_json()
            assert exc.value.code == 1008
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_retention_dry_run_and_leased_thread():
    from src.persistence.maintenance import maintain

    url = os.environ["DATABASE_URL"]
    alice, _ = await actor()
    thread = (await chat_store.create_thread(url, alice["id"], "old"))["id"]
    async with connection(url) as db:
        await db.execute(
            "UPDATE threads SET created_at=(now()-interval '365 days')::text "
            "WHERE id=$1",
            thread,
        )
    preview = await maintain(url, 90)
    assert preview["dry_run"]
    assert await chat_store.get_thread(url, thread, alice["id"])
    async with turns.conversation_lock(url, thread):
        await maintain(url, 90, apply=True)
        assert await chat_store.get_thread(url, thread, alice["id"])
    await maintain(url, 90, apply=True)
    assert await chat_store.get_thread(url, thread, alice["id"]) is None


@pytest.mark.asyncio
async def test_retention_keeps_recently_active_old_thread():
    from src.persistence.maintenance import maintain

    url = os.environ["DATABASE_URL"]
    alice, _ = await actor()
    thread = (await chat_store.create_thread(url, alice["id"], "old but active"))["id"]
    async with connection(url) as db:
        await db.execute(
            "UPDATE threads SET created_at=(now()-interval '365 days')::text "
            "WHERE id=$1",
            thread,
        )
    await chat_store.add_message(url, thread, "user", "recent activity")
    await maintain(url, 90, apply=True)
    assert await chat_store.get_thread(url, thread, alice["id"])


def test_application_lifespan_health_and_safe_headers(monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from llama_index.core.embeddings import MockEmbedding
    from llama_index.core.llms import MockLLM

    import main

    closed = []

    class Client:
        async def get_aliases(self):
            return SimpleNamespace(
                aliases=[
                    SimpleNamespace(
                        alias_name=main.COLLECTION_NAME, collection_name="test-release"
                    )
                ]
            )

        async def get_collection(self, name):
            return SimpleNamespace(
                config=SimpleNamespace(
                    metadata={"embedding_model": "embed-english-v3.0"},
                    params=SimpleNamespace(vectors=SimpleNamespace(size=1024)),
                )
            )

        async def close(self):
            closed.append(True)

    async def agent(**kwargs):
        return object()

    monkeypatch.setattr(main, "get_async_qdrant_client", lambda: Client())
    monkeypatch.setattr(
        main, "build_embed_model", lambda: MockEmbedding(embed_dim=1024)
    )
    monkeypatch.setattr(main, "build_gateway_llm", lambda **kwargs: MockLLM())
    monkeypatch.setattr(main, "QdrantVectorStore", lambda **kwargs: object())
    monkeypatch.setattr(
        main,
        "VectorStoreIndex",
        SimpleNamespace(from_vector_store=lambda **kwargs: object()),
    )
    monkeypatch.setattr(main, "build_faq_query_engine", lambda index: object())
    monkeypatch.setattr(main, "build_agent", agent)
    with TestClient(main.app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        assert client.get("/api/nonexistent").status_code == 404
        response = client.get("/login")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
    assert closed == [True]


@pytest.mark.asyncio
async def test_admin_password_reset_revokes_sessions():
    from src.auth.store import create_user, verify_password

    url = os.environ["DATABASE_URL"]
    alice, token = await actor()
    await create_user(url, alice["identifier"], "new-verified-password")
    assert await security.session_user(url, token) is None
    assert await verify_password(url, alice["identifier"], "new-verified-password")


@pytest.mark.asyncio
async def test_blocked_turns_remain_visible_but_never_enter_model_memory():
    url = os.environ["DATABASE_URL"]
    alice, _ = await actor()
    thread = (await chat_store.create_thread(url, alice["id"], "memory provenance"))[
        "id"
    ]
    bad, _ = await turns.begin_turn(url, thread, "blocked", "untrusted prompt")
    await turns.commit_turn(
        url,
        thread,
        bad["id"],
        "untrusted prompt",
        "request blocked",
        include_in_memory=False,
    )
    good, _ = await turns.begin_turn(url, thread, "safe", "legitimate question")
    await turns.commit_turn(
        url, thread, good["id"], "legitimate question", "supported answer"
    )
    assert len(await chat_store.list_messages(url, thread)) == 4
    memory = await chat_store.list_messages(url, thread, for_memory=True)
    assert [row["content"] for row in memory] == [
        "legitimate question",
        "supported answer",
    ]


@pytest.mark.asyncio
async def test_commit_failure_cannot_acknowledge_an_answer(monkeypatch):
    from src.agent.context import ToolContext
    from src.agent.run_turn import Answer
    from src.api import chat_ws

    url = os.environ["DATABASE_URL"]
    alice, token = await actor()
    thread = (await chat_store.create_thread(url, alice["id"], "commit failure"))["id"]
    frames = []
    called = []

    class Socket:
        async def send_json(self, frame):
            frames.append(frame)

    async def answer(*args, **kwargs):
        return Answer("not yet durable", [])

    async def failed_commit(*args, **kwargs):
        called.append(True)
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(chat_ws, "answer_turn", answer)
    monkeypatch.setattr(turns, "commit_turn", failed_commit)
    chat_ws._slots = None
    await chat_ws._handle_turn(
        Socket(),
        thread,
        alice["identifier"],
        None,
        "question",
        client_id="commit-failure",
        context=ToolContext(alice["id"], thread, "", session_token=token),
        session_token=token,
    )
    assert called
    assert not any(frame["type"] in {"done", "token"} for frame in frames)
    assert frames[-1]["type"] == "error"
    assert await chat_store.list_messages(url, thread) == []


@pytest.mark.asyncio
async def test_turn_timeout_fails_durably_and_releases_capacity(monkeypatch):
    from dataclasses import replace

    from src.agent.context import ToolContext
    from src.api import chat_ws

    url = os.environ["DATABASE_URL"]
    alice, token = await actor()
    thread = (await chat_store.create_thread(url, alice["id"], "timeout"))["id"]
    frames = []
    cancelled = []

    class Socket:
        async def send_json(self, frame):
            frames.append(frame)

    async def slow(*args, **kwargs):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    config = replace(chat_ws.settings(), turn_timeout=0.01, max_concurrent=1)
    monkeypatch.setattr(chat_ws, "settings", lambda: config)
    monkeypatch.setattr(chat_ws, "answer_turn", slow)
    chat_ws._slots = None
    await chat_ws._handle_turn(
        Socket(),
        thread,
        alice["identifier"],
        None,
        "question",
        client_id="timed-out",
        context=ToolContext(alice["id"], thread, "", session_token=token),
        session_token=token,
    )
    assert cancelled and chat_ws._slots._value == 1
    assert not any(frame["type"] == "done" for frame in frames)
    async with connection(url) as db:
        assert (
            await db.fetchval(
                "SELECT status FROM turns WHERE thread_id=$1 AND client_message_id=$2",
                thread,
                "timed-out",
            )
            == "failed"
        )
