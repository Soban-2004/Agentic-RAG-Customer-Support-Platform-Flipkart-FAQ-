import base64
import io
import json
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.static import public_file
from src.api.protocol import parse_frame
from src.api import security
from src.api.rate_limit import enforce_rate_limit, _hits
from src.auth.store import hash_password, _verify
from src.agent.evidence import public_faq_query
from src.gateway.vision import validate_image
from PIL import Image


@pytest.mark.parametrize(
    "path", ["/%2e%2e/%2e%2e/secret.txt", "/%2e%2e/secret.txt", "/api/missing", "/.env"]
)
def test_static_never_serves_private_files(tmp_path, path):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("PUBLIC")
    (tmp_path / "secret.txt").write_text("PRIVATE")
    (dist / ".env").write_text("PRIVATE")
    app = FastAPI()

    @app.get("/{requested:path}")
    def serve(requested):
        return public_file(dist, requested)

    response = TestClient(app).get(path)
    assert response.status_code == 404
    assert "PRIVATE" not in response.text


def test_spa_and_public_asset(tmp_path):
    (tmp_path / "index.html").write_text("PUBLIC")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    assert public_file(tmp_path, "chat/123").path == tmp_path / "index.html"
    assert public_file(tmp_path, "favicon.svg").path == tmp_path / "favicon.svg"


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"content": 4, "client_message_id": "one"},
        {"content": "hi"},
        {"content": "x" * 16001, "client_message_id": "one"},
        {"content": "", "client_message_id": "one"},
        {"content": "hi", "client_message_id": "one", "actor_id": "other"},
    ],
)
def test_message_schema_rejects_invalid(data):
    with pytest.raises(ValueError):
        parse_frame(json.dumps(data))


def test_frame_bound_before_json(monkeypatch):
    monkeypatch.setenv("MAX_FRAME_BYTES", "16384")
    with pytest.raises(ValueError):
        parse_frame(" " * 16385)


@pytest.mark.parametrize(
    "query",
    [
        "Where is my order FK1001?",
        "Can I return it?",
        "What did I ask earlier?",
        "Refund for order 1234",
        "What is your refund policy?",
    ],
)
def test_personal_queries_are_never_shared(query):
    assert not public_faq_query(query)


def test_public_faq_gate():
    assert public_faq_query("What is Flipkart's return policy?")


@pytest.mark.asyncio
async def test_forwarded_header_cannot_bypass_limit():
    _hits.clear()
    for i in range(2):
        conn = SimpleNamespace(
            headers={"x-forwarded-for": str(i)},
            client=SimpleNamespace(host="192.0.2.1"),
        )
        if not i:
            await enforce_rate_limit(conn, "login", 1, 600)
        else:
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc:
                await enforce_rate_limit(conn, "login", 1, 600)
            assert exc.value.status_code == 429


@pytest.mark.asyncio
@pytest.mark.parametrize("password", ["a" * 128, "é" * 80])
async def test_argon_accepts_long_unicode_passwords(password):
    encoded = await hash_password(password)
    assert encoded.startswith("$argon2id$")
    assert _verify(password, encoded)
    assert not _verify(password + "x", encoded)


def test_legacy_bcrypt_is_not_truncated():
    import bcrypt

    encoded = bcrypt.hashpw(b"a" * 72, bcrypt.gensalt(rounds=4)).decode()
    assert _verify("a" * 72, encoded)
    assert not _verify("a" * 73, encoded)


def test_jwt_claims_and_invalid_tokens():
    token = security.create_access_token("alice", "session-one")
    assert security.decode_session(token)["jti"] == "session-one"
    assert security.decode_access_token(token) == "alice"
    assert security.decode_session(token + "broken") is None


def test_origin_allowlist(monkeypatch):
    monkeypatch.setenv("TRUSTED_ORIGINS", "https://app.example")
    for origin, allowed in [
        ("https://app.example", True),
        ("https://app.example.evil", False),
        ("https://evil.example", False),
    ]:
        conn = SimpleNamespace(headers={"origin": origin})
        assert security.origin_allowed(conn) == allowed


def test_image_requires_real_decodable_pixels():
    with pytest.raises(ValueError):
        validate_image(base64.b64encode(b"not pixels").decode(), "image/png")
    output = io.BytesIO()
    Image.new("RGB", (2, 2)).save(output, format="PNG")
    payload = base64.b64encode(output.getvalue()).decode()
    validate_image(payload, "image/png")
    with pytest.raises(ValueError):
        validate_image(payload, "image/jpeg")


@pytest.mark.asyncio
async def test_classifier_failure_is_not_cacheable():
    from src.agent.planner import classify_intent, IntentLabel, CACHEABLE_INTENTS

    class Broken:
        async def astructured_predict(self, *a, **kw):
            raise RuntimeError("offline")

    assert (
        await classify_intent(Broken(), "Where is my order?") not in CACHEABLE_INTENTS
    )


def test_fallbacks_exclude_classifiers(monkeypatch):
    from src.gateway import llm_gateway as gateway

    monkeypatch.setattr(gateway, "LiteLLM", lambda **kw: kw)
    monkeypatch.setattr(gateway, "_register_unknown_ollama_model", lambda model: None)
    config = gateway.build_gateway_llm()
    fallbacks = config["additional_kwargs"]["fallbacks"]
    assert len(fallbacks) == 1
    assert "gpt-oss-20b" in fallbacks[0]["model"]
    assert fallbacks[0]["max_tokens"] == 1024


@pytest.mark.parametrize("invalid", ["secret", "origin", "tracing"])
def test_production_rejects_unsafe_configuration(monkeypatch, invalid):
    from src.api.settings import validate_production

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "JWT_SECRET", "a-random-looking-configuration-secret-of-ample-length"
    )
    monkeypatch.setenv("TRUSTED_ORIGINS", "https://app.example")
    monkeypatch.setenv("QDRANT_URL", "https://vectors.example")
    monkeypatch.setenv("ENABLE_CONTENT_TRACING", "false")
    monkeypatch.setenv("BUSINESS_BACKEND", "demo")
    if invalid == "secret":
        monkeypatch.setenv(
            "JWT_SECRET", "replace-with-a-random-secret-at-least-32-characters"
        )
    elif invalid == "origin":
        monkeypatch.setenv("TRUSTED_ORIGINS", "http://app.example")
    else:
        monkeypatch.setenv("ENABLE_CONTENT_TRACING", "true")
        monkeypatch.setenv("ENABLE_DEMO", "true")
    with pytest.raises(ValueError):
        validate_production()


@pytest.mark.parametrize(
    "query",
    [
        "John wants the return policy",
        "refund policy secret abcdefghijklmnop",
        "return policy for customer Alice",
    ],
)
def test_arbitrary_customer_context_is_not_cacheable(query):
    assert not public_faq_query(query)
