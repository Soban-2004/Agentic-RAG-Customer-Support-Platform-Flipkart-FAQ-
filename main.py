"""FastAPI entrypoint -- replaces the old Chainlit app.py. Same module-level
startup responsibilities Chainlit's app.py had (LLM/embedder settings, tracing
init, Qdrant + agent + cache setup), except the agent/cache are now built once
for the whole process (see src/api/state.py's docstring for why that's safe)
instead of being rebuilt on every Chainlit connection.

Run: `uvicorn main:app --reload` (dev, with `npm run dev` in frontend/ using
its Vite proxy) or via the Dockerfile (serves frontend/dist directly, single
container/port). Single worker only -- see README's "Auth & chat history" /
run-instructions notes on why.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Must run before any src.* import below -- several of them (src/api/config.py,
# src/gateway/llm_gateway.py's config/models.yaml env lookups) read env vars
# at import time, not lazily.
load_dotenv()
logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from llama_index.core import Settings, VectorStoreIndex  # noqa: E402
from llama_index.vector_stores.qdrant import QdrantVectorStore  # noqa: E402

from src.agent.chat_agent import build_agent  # noqa: E402
from src.api import state  # noqa: E402
from src.api.auth import router as auth_router  # noqa: E402
from src.api.chat_ws import router as chat_ws_router  # noqa: E402
from src.api.config import DATABASE_URL  # noqa: E402,F401 -- import validates it's set
from src.api.threads import router as threads_router  # noqa: E402
from src.common.embed_factory import build_embed_model, embed_dim  # noqa: E402
from src.common.qdrant_factory import get_async_qdrant_client, is_remote  # noqa: E402
from src.gateway.cache import SemanticCache  # noqa: E402
from src.gateway.llm_gateway import build_gateway_llm  # noqa: E402
from src.observability.tracing import init_tracing  # noqa: E402

COLLECTION_NAME = "flipkart_faqs"

if not os.getenv("CHATGROQ_API_KEY"):
    raise ValueError("Missing CHATGROQ_API_KEY -- see README.md.")
if not os.getenv("JWT_SECRET"):
    raise ValueError("Missing JWT_SECRET -- see README.md's Auth & chat history section.")

FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    embed_model = build_embed_model()
    Settings.embed_model = embed_model
    Settings.llm = build_gateway_llm()
    init_tracing()

    logging.info(
        "qdrant_mode=%s", "remote (QDRANT_URL set)" if is_remote() else "local (embedded, on-disk)"
    )
    aclient = get_async_qdrant_client()
    vector_store = QdrantVectorStore(
        aclient=aclient,
        collection_name=COLLECTION_NAME,
        enable_hybrid=True,
        fastembed_sparse_model="Qdrant/bm25",
    )
    index = VectorStoreIndex.from_vector_store(vector_store=vector_store)

    state.cache = SemanticCache(client=aclient, embed_model=embed_model, vector_size=embed_dim())
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
    agent_llm = build_gateway_llm(model_key=os.getenv("AGENT_TOOL_CALL_MODEL_KEY", "tool_call"))
    state.agent = await build_agent(index=index, llm=agent_llm)

    yield


app = FastAPI(lifespan=lifespan)

# Registered before the static/SPA mount below so API/WS paths always win.
app.include_router(auth_router)
app.include_router(threads_router)
app.include_router(chat_ws_router)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        """Serves the built React SPA; any non-API, non-asset path (client-side
        routes like /chat/<id>) falls back to index.html so a hard refresh
        doesn't 404."""
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
