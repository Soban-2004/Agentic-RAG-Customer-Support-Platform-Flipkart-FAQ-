"""FastAPI bootstrap with validated configuration, pooled resources, and health checks.

Run schema migration and publish an immutable knowledge revision before startup.
Conversation state and quotas live in Postgres; process-level work/connection caps
remain bounded per replica. Remote Qdrant is required for production.
"""

import logging
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Must run before any src.* import below -- several of them (src/api/config.py,
# src/gateway/llm_gateway.py's config/models.yaml env lookups) read env vars
# at import time, not lazily.
load_dotenv()
logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from llama_index.core import Settings, VectorStoreIndex  # noqa: E402
from llama_index.vector_stores.qdrant import QdrantVectorStore  # noqa: E402

from src.agent.chat_agent import build_agent, build_faq_query_engine  # noqa: E402
from src.api import state  # noqa: E402
from src.api.static import public_file
from src.api.settings import validate_production
from src.api.security import origin_allowed
from src.common.database import connection, close_pools  # noqa: E402
from src.api.auth import router as auth_router  # noqa: E402
from src.api.chat_ws import router as chat_ws_router  # noqa: E402
from src.api.config import DATABASE_URL  # noqa: E402,F401 -- import validates it's set
from src.api.demo_ws import router as demo_ws_router  # noqa: E402
from src.api.threads import router as threads_router  # noqa: E402
from src.common.embed_factory import build_embed_model, embed_dim, use_cohere_embeddings  # noqa: E402
from src.common.qdrant_factory import get_async_qdrant_client, is_remote  # noqa: E402
from src.gateway.cache import SemanticCache  # noqa: E402
from src.gateway.llm_gateway import build_gateway_llm  # noqa: E402
from src.observability.tracing import init_tracing  # noqa: E402

from src.common.knowledge import knowledge_alias, embedding_identity

COLLECTION_NAME = knowledge_alias()

if not os.getenv("CHATGROQ_API_KEY"):
    raise ValueError("Missing CHATGROQ_API_KEY -- see README.md.")
if not os.getenv("JWT_SECRET"):
    raise ValueError(
        "Missing JWT_SECRET -- see README.md's Auth & chat history section."
    )

FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_production()
    _app.state.ready = False
    try:
        async with connection(DATABASE_URL) as db:
            if not await db.fetchval(
                "SELECT 1 FROM schema_migrations WHERE version='002_memory_provenance.sql'"
            ):
                raise RuntimeError(
                    "Run python -m src.persistence.migrate before starting the service"
                )
        embed_model = build_embed_model()
        Settings.embed_model = embed_model
        Settings.llm = build_gateway_llm()
        init_tracing()

        logging.info(
            "qdrant_mode=%s",
            "remote (QDRANT_URL set)" if is_remote() else "local (embedded, on-disk)",
        )
        aclient = get_async_qdrant_client()
        _app.state.qdrant = aclient
        # Pin this process to one physical knowledge revision for cache consistency.
        aliases = await aclient.get_aliases()
        physical = next(
            (
                a.collection_name
                for a in aliases.aliases
                if a.alias_name == COLLECTION_NAME
            ),
            COLLECTION_NAME,
        )
        info = await aclient.get_collection(physical)
        metadata = getattr(info.config, "metadata", None) or {}
        if metadata.get("embedding_model") != embedding_identity():
            raise RuntimeError(
                "Knowledge embedding identity is missing or incompatible; publish a fresh knowledge revision"
            )
        vectors = info.config.params.vectors
        configs = list(vectors.values()) if isinstance(vectors, dict) else [vectors]
        if any(v.size != embed_dim() for v in configs):
            raise RuntimeError(
                "Embedding dimensions do not match the knowledge collection"
            )
        state.knowledge_version = physical
        # Hybrid (dense + BM25 sparse) search is local-dev only -- the sparse
        # side loads its own model via `fastembed` regardless of which *dense*
        # embedder is active, so switching the dense embedder to Cohere alone
        # didn't remove it (measured: ~224MB, the actual cause of an early
        # deploy OOM on a free-tier host's 512MB limit). Collections built with
        # sparse vectors present still work fine queried dense-only -- the extra
        # vectors just go unused -- so this doesn't require re-ingesting.
        vector_store_kwargs = {"aclient": aclient, "collection_name": physical}
        if not use_cohere_embeddings():
            vector_store_kwargs["enable_hybrid"] = True
            vector_store_kwargs["fastembed_sparse_model"] = "Qdrant/bm25"
        vector_store = QdrantVectorStore(**vector_store_kwargs)
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store)

        state.cache = SemanticCache(
            client=aclient,
            embed_model=embed_model,
            vector_size=embed_dim(),
            namespace=physical,
        )
        # The agent's own tool-call decision step gets a dedicated model
        # (config/models.yaml's "tool_call" entry, currently Ollama Cloud's
        # gemma4:cloud) -- separate from Settings.llm (used for RAG-answer
        # synthesis and intent classification, plain text generation unaffected
        # by this) -- see that config entry's comment for why.
        #
        # AGENT_TOOL_CALL_MODEL_KEY overrides which config/models.yaml entry gets
        # used for this, e.g. "fallback" -- for deployments where a locally
        # ollama-signin'd daemon isn't available (no free host keeps one
        # authenticated in the background). Unset locally, so local dev keeps
        # using Ollama Cloud as before; a public deploy sets this to fall back to
        # Groq instead and accepts the rare malformed-tool-call failure, which is
        # already caught by chat_ws.py's try/except and degrades to one failed
        # turn, not a crash.
        agent_llm = build_gateway_llm(
            model_key=os.getenv(
                "AGENT_TOOL_CALL_MODEL_KEY",
                "fallback" if os.getenv("APP_ENV") == "production" else "tool_call",
            )
        )
        state.faq_engine = build_faq_query_engine(index)
        state.agent = await build_agent(
            index=index, llm=agent_llm, query_engine=state.faq_engine
        )
        _app.state.ready = True
        try:
            yield
        finally:
            _app.state.ready = False
            state.agent = state.faq_engine = state.cache = None
            from src.observability.tracing import get_tracing_client

            tracer = get_tracing_client()
            if tracer:
                await asyncio.to_thread(tracer.flush)
    finally:
        await close_pools()
        client = getattr(_app.state, "qdrant", None)
        if client is not None:
            await client.close()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method not in {
        "GET",
        "HEAD",
        "OPTIONS",
    }:
        if request.headers.get("origin") and not origin_allowed(request):
            return JSONResponse({"detail": "Origin is not allowed"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if os.getenv("APP_ENV") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.get("/health/live")
async def live():
    return {"status": "alive"}


@app.get("/health/ready")
async def ready():
    if not getattr(app.state, "ready", False):
        return JSONResponse({"status": "not_ready"}, status_code=503)
    try:
        async with connection(DATABASE_URL) as db:
            await db.fetchval("SELECT 1")
        await asyncio.wait_for(
            app.state.qdrant.get_collection(state.knowledge_version), 3
        )
        return {"status": "ready"}
    except Exception:
        return JSONResponse({"status": "not_ready"}, status_code=503)


# Registered before the static/SPA mount below so API/WS paths always win.
app.include_router(auth_router)
app.include_router(threads_router)
app.include_router(chat_ws_router)
app.include_router(demo_ws_router)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        """Serves the built React SPA; any non-API, non-asset path (client-side
        routes like /chat/<id>) falls back to index.html so a hard refresh
        doesn't 404."""
        return public_file(FRONTEND_DIST, full_path)
