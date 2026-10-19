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
from src.agent.evidence import public_faq_topic

import qdrant_client
from qdrant_client.http import models as qmodels

logger = logging.getLogger("gateway.cache")

CACHE_COLLECTION = "response_cache_v5"
SIMILARITY_THRESHOLD = 0.95
TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days

# Bump this whenever a prompt/template change -- or a cache-*scoping* change
# like the one below -- would make old cached answers wrong or stale. Stored
# in each entry's payload and checked on read, the same way the TTL is -- a
# version bump invalidates every existing entry without needing a manual
# collection wipe. Two real incidents so far, not hypothetical:
#   v1->v2: a "modes of payment" answer cached before a prompt-formatting
#     change kept being served verbatim, unformatted, to later sessions.
#   v2->v3: CACHEABLE_INTENTS (src/agent/planner.py) used to include
#     general_chat, which let a session-referential answer ("you haven't
#     asked anything yet in this conversation") get cached globally and
#     served to a different session that actually had asked something --
#     narrowing that set doesn't retroactively un-cache what v2 already wrote.
CACHE_VERSION = 5


class SemanticCache:
    def __init__(
        self,
        client: qdrant_client.AsyncQdrantClient,
        embed_model,
        vector_size: int,
        namespace: str = "disabled",
    ):
        self.namespace = namespace
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
            info = await self.client.get_collection(CACHE_COLLECTION)
            if info.config.params.vectors.size != self.vector_size:
                raise ValueError("Cache embedding dimension mismatch")
            for field, kind in (
                ("namespace", qmodels.PayloadSchemaType.KEYWORD),
                ("topic", qmodels.PayloadSchemaType.KEYWORD),
                ("cache_version", qmodels.PayloadSchemaType.INTEGER),
                ("cached_at", qmodels.PayloadSchemaType.FLOAT),
            ):
                await self.client.create_payload_index(
                    CACHE_COLLECTION, field, field_schema=kind
                )
            self._ready = True

    async def get(
        self, query: str, embedding: Optional[list[float]] = None
    ) -> Optional[dict]:
        topic = public_faq_topic(query)
        if topic is None:
            return None
        await self._ensure_collection()
        # Caller may already have embedded this exact text (chat_ws.py does,
        # for the cacheable-intent path) -- reuse it instead of a redundant
        # Cohere/embed-API round trip for the identical string.
        vector = (
            embedding
            if embedding is not None
            else await self.embed_model.aget_query_embedding(query)
        )
        result = await self.client.query_points(
            collection_name=CACHE_COLLECTION,
            query=vector,
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="topic", match=qmodels.MatchValue(value=topic)
                    ),
                    qmodels.FieldCondition(
                        key="namespace", match=qmodels.MatchValue(value=self.namespace)
                    ),
                    qmodels.FieldCondition(
                        key="cache_version",
                        match=qmodels.MatchValue(value=CACHE_VERSION),
                    ),
                    qmodels.FieldCondition(
                        key="cached_at",
                        range=qmodels.Range(gte=time.time() - TTL_SECONDS),
                    ),
                ]
            ),
            limit=1,
            score_threshold=SIMILARITY_THRESHOLD,
        )
        hits = result.points

        if not hits:
            logger.info("cache_miss query=%r", "[public query]")
            return None

        payload = hits[0].payload or {}
        if time.time() - payload.get("cached_at", 0) > TTL_SECONDS:
            logger.info("cache_expired query=%r", "[public query]")
            return None
        if payload.get("cache_version") != CACHE_VERSION:
            logger.info("cache_stale_version query=%r", "[public query]")
            return None

        logger.info("cache_hit query=%r score=%.3f", "[public query]", hits[0].score)
        return (
            {"response": payload["response"], "sources": payload.get("sources", [])}
            if payload.get("response")
            else None
        )

    async def set(
        self,
        query: str,
        response: str,
        embedding: Optional[list[float]] = None,
        sources: Optional[list] = None,
    ) -> None:
        topic = public_faq_topic(query)
        if topic is None:
            raise ValueError("Only allowlisted public FAQ queries may be cached")
        await self._ensure_collection()
        vector = (
            embedding
            if embedding is not None
            else await self.embed_model.aget_query_embedding(query)
        )
        # Qdrant point IDs must be a UUID or an unsigned int -- uuid5 gives a
        # deterministic UUID from the query text, so re-caching the same query
        # (or a near-duplicate that hashes the same normalized text) upserts in place.
        point_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, self.namespace + ":" + query.strip().lower())
        )
        await self.client.upsert(
            collection_name=CACHE_COLLECTION,
            points=[
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "namespace": self.namespace,
                        "topic": topic,
                        "sources": sources or [],
                        "response": response,
                        "cached_at": time.time(),
                        "cache_version": CACHE_VERSION,
                    },
                )
            ],
        )

        expired = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="cached_at", range=qmodels.Range(lt=time.time() - TTL_SECONDS)
                )
            ]
        )
        await self.client.delete(
            CACHE_COLLECTION, points_selector=qmodels.FilterSelector(filter=expired)
        )
