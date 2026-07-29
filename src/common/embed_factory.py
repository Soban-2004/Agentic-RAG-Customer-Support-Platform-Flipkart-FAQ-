"""
Embedding model factory: switches between Cohere's hosted embed API and a
locally-loaded FastEmbed model based on whether COHERE_API_KEY is set.

Used identically by main.py (runtime) and src/ingestion/embed_qdrant.py
(offline ingestion) -- these two MUST produce embeddings from the same model,
or retrieval silently degrades (query and stored vectors would live in
different vector spaces). Centralized here instead of duplicated in both
places so they can't drift out of sync.

Cohere's embed-english-v3.0 is 1024-dim vs bge-small's 384-dim -- switching
between the two isn't just a model swap, it changes the Qdrant collections'
vector size, which means a full re-ingest (`embed_qdrant.py --reset`) any
time this toggles, not an incremental upsert.
"""

import os

COHERE_MODEL = "embed-english-v3.0"
COHERE_DIM = 1024
LOCAL_MODEL = "BAAI/bge-small-en-v1.5"
LOCAL_DIM = 384


def use_cohere_embeddings() -> bool:
    return bool(os.getenv("COHERE_API_KEY"))


def embed_dim() -> int:
    return COHERE_DIM if use_cohere_embeddings() else LOCAL_DIM


def build_embed_model():
    if use_cohere_embeddings():
        from llama_index.embeddings.cohere import CohereEmbedding

        # input_type deliberately left unset (None) -- CohereEmbedding then
        # auto-selects "search_document" for indexing calls and
        # "search_query" for query calls, which is exactly right here:
        # ingestion embeds FAQ/policy chunks (documents), while retrieval
        # and the semantic cache (src/gateway/cache.py) both always embed a
        # user question (a query), never a document, via aget_query_embedding.
        return CohereEmbedding(api_key=os.getenv("COHERE_API_KEY"), model_name=COHERE_MODEL)

    from llama_index.embeddings.fastembed import FastEmbedEmbedding

    return FastEmbedEmbedding(model_name=LOCAL_MODEL)
