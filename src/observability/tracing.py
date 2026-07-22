"""
Observability: Langfuse Cloud tracing (not self-hosted -- see README's
Observability section for why). Wraps LlamaIndex's own operations via
OpenInference's OTEL instrumentor, so every agent step, tool call, retrieval,
rerank, and LLM generation shows up as one nested trace per request in
Langfuse -- not just the request-level cost/latency the Gateway already logs
locally (src/gateway/llm_gateway.py).

Additive, not a hard dependency: every function here is a safe no-op when
LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY aren't set, so the app runs the same
with or without a Langfuse account configured.
"""

import logging
import os
from typing import Optional

from langfuse import Langfuse

logger = logging.getLogger("observability.tracing")

_client: Optional[Langfuse] = None
_instrumented = False


def init_tracing() -> Optional[Langfuse]:
    """Idempotent -- safe to call from both app.py and src/eval/run_eval.py."""
    global _client, _instrumented

    if _client is not None:
        return _client

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        logger.warning(
            "observability: LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY not set -- tracing disabled"
        )
        return None

    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    _client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    if not _instrumented:
        # Instantiating Langfuse() above registers itself as the global OTEL
        # tracer provider; instrument() with no explicit provider argument
        # picks that up automatically -- every FunctionAgent step, tool call,
        # retriever, reranker, and LLM call llama_index runs from here on
        # gets captured as a nested span with zero manual instrumentation
        # anywhere in chat_agent.py.
        from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

        LlamaIndexInstrumentor().instrument()
        _instrumented = True

    logger.info("observability: Langfuse tracing enabled (host=%s)", host)
    return _client


def get_tracing_client() -> Optional[Langfuse]:
    return _client


def score_guardrail_event(layer: str, scanner: str) -> None:
    """Call on a block (input) or redaction (output) event. Gives the
    'guardrail catch rate' metric noted as a goal back in the original
    Gateway/guardrails planning -- only wired up now that tracing exists to
    hold it."""
    if _client is None:
        return
    try:
        _client.score_current_trace(
            name=f"guardrail_triggered_{layer}", value=1, data_type="BOOLEAN", comment=scanner
        )
    except Exception:
        logger.exception("observability: failed to score guardrail event")


def score_cache_result(hit: bool) -> None:
    """Call for every cache-eligible request (hit or miss) -- gives a
    Langfuse-native cache hit-rate metric alongside the semantic cache
    itself (src/gateway/cache.py)."""
    if _client is None:
        return
    try:
        _client.score_current_trace(name="cache_hit", value=1 if hit else 0, data_type="BOOLEAN")
    except Exception:
        logger.exception("observability: failed to score cache result")
