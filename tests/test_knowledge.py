import time
import uuid
from types import SimpleNamespace
import pytest
import qdrant_client
from qdrant_client.http import models
from src.gateway.cache import SemanticCache, CACHE_COLLECTION, CACHE_VERSION


class Embed:
    async def aget_query_embedding(self, query):
        return [1.0, 0.0]


@pytest.mark.asyncio
async def test_cache_versions_expiry_and_namespace():
    client = qdrant_client.AsyncQdrantClient(":memory:")
    first = SemanticCache(client, Embed(), 2, namespace="release-a")
    second = SemanticCache(client, Embed(), 2, namespace="release-b")
    await first.set("return policy", "public answer", sources=[{"title": "policy.pdf"}])
    assert (await first.get("return policy"))["response"] == "public answer"
    assert await second.get("return policy") is None
    await client.upsert(
        CACHE_COLLECTION,
        points=[
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=[1.0, 0.0],
                payload={
                    "namespace": "release-a",
                    "cache_version": CACHE_VERSION,
                    "cached_at": 0,
                    "response": "expired",
                },
            )
        ],
    )
    assert (await first.get("return policy"))["response"] == "public answer"
    await client.close()


@pytest.mark.asyncio
async def test_public_answer_survives_cache_outage(monkeypatch):
    from src.agent import run_turn
    from src.agent.context import tool_context, ToolContext
    from src.agent.planner import IntentLabel
    from src.memory.persistent_memory import build_ephemeral_memory

    class Socket:
        async def send_json(self, frame):
            pass

    class Engine:
        async def aquery(self, query):
            return "actual retrieved answer"

    class Cache:
        async def get(self, query):
            raise TimeoutError()

        async def set(self, *args, **kwargs):
            raise TimeoutError()

    async def scan(text):
        return text

    async def classify(*args):
        return IntentLabel.FAQ_LOOKUP

    monkeypatch.setattr(run_turn, "Settings", SimpleNamespace(llm=object()))
    monkeypatch.setenv("ENABLE_SHARED_FAQ_CACHE", "true")
    monkeypatch.setattr(run_turn, "scan_user_input", scan)
    monkeypatch.setattr(run_turn, "classify_intent", classify)
    monkeypatch.setattr(
        run_turn,
        "grounded_text",
        lambda response: (str(response), [{"title": "policy.pdf"}]),
    )
    monkeypatch.setattr(run_turn.state, "cache", Cache())
    monkeypatch.setattr(run_turn.state, "faq_engine", Engine())
    with tool_context(ToolContext("a", "t", "one")):
        answer = await run_turn.answer_turn(
            Socket(), build_ephemeral_memory(), "What is Flipkart's return policy?"
        )
    assert answer.content == "actual retrieved answer"


@pytest.mark.asyncio
async def test_personal_tool_path_never_reads_shared_cache(monkeypatch):
    from src.agent import run_turn
    from src.agent.context import tool_context, ToolContext
    from src.agent.planner import IntentLabel
    from src.memory.persistent_memory import build_ephemeral_memory

    class Socket:
        async def send_json(self, frame):
            pass

    class Cache:
        async def get(self, *args):
            pytest.fail("Private query reached shared cache")

    class Handler:
        async def stream_events(self):
            if False:
                yield None

        def __await__(self):
            async def result():
                return SimpleNamespace(
                    response=SimpleNamespace(content="account result")
                )

            return result().__await__()

    async def scan(text):
        return text

    async def classify(*args):
        return IntentLabel.FAQ_LOOKUP

    monkeypatch.setattr(run_turn, "Settings", SimpleNamespace(llm=object()))
    monkeypatch.setenv("ENABLE_SHARED_FAQ_CACHE", "true")
    monkeypatch.setattr(run_turn, "scan_user_input", scan)
    monkeypatch.setattr(run_turn, "classify_intent", classify)
    monkeypatch.setattr(run_turn.state, "cache", Cache())
    monkeypatch.setattr(
        run_turn.state, "agent", SimpleNamespace(run=lambda **kwargs: Handler())
    )
    with tool_context(ToolContext("a", "t", "one")):
        answer = await run_turn.answer_turn(
            Socket(), build_ephemeral_memory(), "Where is my order FK1001?"
        )
    assert answer.content == "account result"


def test_atomic_knowledge_release_switch():
    from src.common.knowledge import publish

    client = qdrant_client.QdrantClient(":memory:")
    for name in ["revision-one", "revision-two"]:
        client.create_collection(
            name,
            vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
        )
    publish(client, "revision-one", "public-policies")
    publish(client, "revision-two", "public-policies")
    assert client.get_aliases().aliases[0].collection_name == "revision-two"
    assert client.collection_exists("revision-one")
    client.close()


@pytest.mark.asyncio
async def test_guard_outage_and_invalid_verdict_fail_closed(monkeypatch):
    from src.gateway import guardrails

    async def invalid(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="NaN"))]
        )

    monkeypatch.setattr(guardrails.litellm, "acompletion", invalid)
    with pytest.raises(guardrails.GuardrailBlocked) as exc:
        await guardrails.scan_user_input("hello")
    assert exc.value.scanner == "GuardUnavailable"


@pytest.mark.asyncio
async def test_output_review_redacts_before_delivery():
    from src.gateway.guardrails import scan_bot_output

    text, flag = await scan_bot_output(
        "q", "Email john@example.com or call +91-9876543210. https://evil.example/steal"
    )
    assert flag == "OutputPolicy"
    assert (
        "john@example.com" not in text
        and "9876543210" not in text
        and "evil.example" not in text
    )
