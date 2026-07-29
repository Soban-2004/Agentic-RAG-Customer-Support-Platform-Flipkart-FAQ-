"""
Semantic cache sublayer of the AI Gateway.

Caches (query embedding -> response) pairs in a dedicated Qdrant collection so
a repeated/paraphrased FAQ question ("how do I return an item" / "how to
return my order") can skip the LLM call entirely.

Fully async (AsyncQdrantClient) so it can share a single Qdrant connection
with the rest of the app -- required for local/embedded Qdrant mode, which
only allows one open client per storage folder (see src/common/qdrant_factory.py).

Deliberately NOT scoped automatically here -- the caller decides per-request
whether a query is cache-eligible (see app.py). Only FAQ/general-chat style
answers should ever be cached; order-status/refund-status/escalation answers
are per-user and dynamic (backed by an MCP tool call once Phase 3 lands) and
must never be served from cache.
"""

import asyncio
import logging
import time
import uuid
from typing import Optional

import qdrant_client
from qdrant_client.http import models as qmodels

logger = logging.getLogger("gateway.cache")

CACHE_COLLECTION = "response_cache"
SIMILARITY_THRESHOLD = 0.95
TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days

# Bump this whenever a prompt/template change would make old cached answers
# wrong or stale (e.g. the FAQ_QA_TEMPLATE/SYSTEM_PROMPT markdown-formatting
# change) -- a real incident, not hypothetical: a "modes of payment" answer
# cached before that change kept being served verbatim, unformatted, to every
# later session asking a semantically similar question, since nothing tied
# cache entries to the prompt that produced them. Stored in each entry's
# payload and checked on read, the same way the TTL is -- a version bump
# invalidates every existing entry without needing a manual collection wipe.
CACHE_VERSION = 2


class SemanticCache:
    def __init__(self, client: qdrant_client.AsyncQdrantClient, embed_model, vector_size: int):
        self.client = client
        self.embed_model = embed_model
        self.vector_size = vector_size
        self._ready = False
        self._init_lock = asyncio.Lock()

    async def _ensure_collection(self) -> None:
        if self._ready:
            return
        async with self._init_lock:
            if self._ready:
                return
            if not await self.client.collection_exists(CACHE_COLLECTION):
                await self.client.create_collection(
                    collection_name=CACHE_COLLECTION,
                    vectors_config=qmodels.VectorParams(
                        size=self.vector_size, distance=qmodels.Distance.COSINE
                    ),
                )
            self._ready = True

    async def get(self, query: str, embedding: Optional[list[float]] = None) -> Optional[str]:
        await self._ensure_collection()
        # Caller may already have embedded this exact text (chat_ws.py does,
        # for the cacheable-intent path) -- reuse it instead of a redundant
        # Cohere/embed-API round trip for the identical string.
        vector = embedding if embedding is not None else await self.embed_model.aget_query_embedding(query)
        result = await self.client.query_points(
            collection_name=CACHE_COLLECTION,
            query=vector,
            limit=1,
            score_threshold=SIMILARITY_THRESHOLD,
        )
        hits = result.points

        if not hits:
            logger.info("cache_miss query=%r", query[:80])
            return None

        payload = hits[0].payload or {}
        if time.time() - payload.get("cached_at", 0) > TTL_SECONDS:
            logger.info("cache_expired query=%r", query[:80])
            return None
        if payload.get("cache_version") != CACHE_VERSION:
            logger.info("cache_stale_version query=%r", query[:80])
            return None

        logger.info("cache_hit query=%r score=%.3f", query[:80], hits[0].score)
        return payload.get("response")

    async def set(self, query: str, response: str, embedding: Optional[list[float]] = None) -> None:
        await self._ensure_collection()
        vector = embedding if embedding is not None else await self.embed_model.aget_query_embedding(query)
        # Qdrant point IDs must be a UUID or an unsigned int -- uuid5 gives a
        # deterministic UUID from the query text, so re-caching the same query
        # (or a near-duplicate that hashes the same normalized text) upserts in place.
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, query.strip().lower()))
        await self.client.upsert(
            collection_name=CACHE_COLLECTION,
            points=[
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "query": query,
                        "response": response,
                        "cached_at": time.time(),
                        "cache_version": CACHE_VERSION,
                    },
                )
            ],
        )
