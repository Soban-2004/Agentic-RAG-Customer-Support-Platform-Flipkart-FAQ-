"""
Agent layer: replaces the old plain `index.as_chat_engine(chat_mode="context")`
with a real tool-calling agent (LlamaIndex FunctionAgent). The agent decides,
per turn, whether to search the FAQ knowledge base or call an account-specific
tool -- it is not hard-routed by the planner's intent classification.

order_status / refund_status / escalate are real MCP tools (src/tools/mcp_server.py,
a stdio Model Context Protocol server backed by a mock SQLite database in
src/tools/mock_backend.py) rather than plain Python functions -- the agent
talks to them over the actual MCP client/server protocol, the same way it
would talk to a real external tool server.
"""

import contextvars
import os
import sys
from pathlib import Path
from typing import Any, Optional

from llama_index.core import PromptTemplate, VectorStoreIndex
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.llms import LLM
from llama_index.core.schema import QueryBundle
from llama_index.core.tools import FunctionTool, QueryEngineTool
from llama_index.core.tools.types import ToolOutput
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec

from src.common.embed_factory import use_cohere_embeddings

MCP_SERVER_PATH = Path(__file__).resolve().parent.parent / "tools" / "mcp_server.py"

# Two-stage retrieval: cast a wide net with hybrid (dense + BM25 sparse) search,
# then rerank down to the few chunks actually worth putting in the prompt. The
# reranker (a cross-encoder, scores query+chunk pairs jointly) is slower per-item
# than embedding similarity but far more precise, which is exactly why it only
# runs on the already-narrowed candidate set rather than the whole collection.
HYBRID_CANDIDATES = 10
RERANK_TOP_N = 3
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Cohere's hosted rerank API instead of a locally-loaded cross-encoder --
# ~355MB of RAM the deployed process doesn't have to carry, at the cost of a
# network round-trip per query and Cohere's trial-key limits (1,000 calls/
# month, 10 rerank req/min -- see .env). COHERE_API_KEY unset (local dev)
# falls back to the local cross-encoder, so nothing changes there. Same flag
# src/common/embed_factory.py uses for the embedder -- both toggle off the
# same key, since there's currently no scenario wanting one without the other.
_USE_COHERE_RERANK = use_cohere_embeddings()


# Default query-engine QA prompt has no formatting guidance at all, which is
# why FAQ answers came back as one dense paragraph -- this is the template
# actually used for search_faq's synthesis (a separate LLM call from the
# agent's own system prompt below, so it needs its own formatting nudge).
FAQ_QA_TEMPLATE = PromptTemplate(
    "Context information from Flipkart's policy/FAQ documents is below.\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "Using the context above (not prior knowledge), answer the question. "
    "Format the answer in clean Markdown: **bold** key terms, numbers, "
    "timeframes, and IDs; use a numbered or bulleted list for any multi-step "
    "process or multiple items; keep prose in short paragraphs. Don't mention "
    "'the context' or that you're an AI -- answer directly and concisely.\n"
    "Question: {query_str}\n"
    "Answer: "
)


# Set by chat_ws.py right before agent.run() (task-local via contextvars,
# so concurrent WS connections/turns never see each other's value), read by
# _CachedQueryEngineTool.acall() below. Lets search_faq reuse the embedding
# already computed for that turn's semantic-cache check instead of a second,
# redundant Cohere/embed-API round trip for the identical text -- but ONLY
# when the agent's tool-call argument matches that text exactly. The agent
# can rephrase/consolidate the query before calling search_faq, and
# retrieving against a precomputed embedding for different text than what's
# actually being searched would be a silent correctness bug (wrong results,
# no error) -- the exact-match gate exists specifically to make that
# impossible, at the cost of only saving the round-trip on the common case
# where the agent passes the question through unchanged.
_precomputed_query_embedding: contextvars.ContextVar[Optional[tuple[str, list[float]]]] = (
    contextvars.ContextVar("precomputed_query_embedding", default=None)
)


def set_precomputed_query_embedding(query: str, embedding: list[float]) -> None:
    _precomputed_query_embedding.set((query, embedding))


def clear_precomputed_query_embedding() -> None:
    _precomputed_query_embedding.set(None)


class _CachedQueryEngineTool(QueryEngineTool):
    """QueryEngineTool that reuses a precomputed query embedding (see above)
    when the agent's tool-call argument matches the text it was computed for
    exactly. Any mismatch falls back to QueryEngineTool's normal behavior --
    a fresh, correctness-safe re-embed."""

    async def acall(self, *args: Any, **kwargs: Any) -> ToolOutput:
        query_str = self._get_query_str(*args, **kwargs)
        cached = _precomputed_query_embedding.get()
        query_input = (
            QueryBundle(query_str=query_str, embedding=cached[1])
            if cached is not None and cached[0] == query_str
            else query_str
        )
        response = await self._query_engine.aquery(query_input)
        return ToolOutput(
            content=str(response),
            tool_name=self.metadata.get_name(),
            raw_input={"input": query_str},
            raw_output=response,
        )


def _build_reranker():
    if _USE_COHERE_RERANK:
        from llama_index.postprocessor.cohere_rerank import CohereRerank

        return CohereRerank(
            api_key=os.getenv("COHERE_API_KEY"), model="rerank-english-v3.0", top_n=RERANK_TOP_N
        )
    from llama_index.core.postprocessor import SentenceTransformerRerank

    return SentenceTransformerRerank(model=RERANKER_MODEL, top_n=RERANK_TOP_N)


def build_faq_query_engine(index: VectorStoreIndex) -> BaseQueryEngine:
    # Hybrid (dense+sparse) query mode only works against a vector store that
    # was actually opened with enable_hybrid=True (see main.py) -- which is
    # itself conditional on not using Cohere, see that comment for why.
    query_kwargs = {"similarity_top_k": HYBRID_CANDIDATES}
    if not use_cohere_embeddings():
        query_kwargs["vector_store_query_mode"] = "hybrid"
        query_kwargs["sparse_top_k"] = HYBRID_CANDIDATES
    return index.as_query_engine(
        node_postprocessors=[_build_reranker()],
        text_qa_template=FAQ_QA_TEMPLATE,
        **query_kwargs,
    )

SYSTEM_PROMPT = (
    "You are a helpful Flipkart customer support assistant. Judge each tool call "
    "strictly by the user's CURRENT message -- ignore what tools were called earlier "
    "in the conversation; a new message is a new decision.\n\n"
    "Tool rules:\n"
    "- search_faq: for policy/how-to questions (returns, refunds policy, payments, EMI, "
    "shipping, etc). Call it at most once per question. As soon as you get results, "
    "answer directly from them -- do not call any other tool afterward.\n"
    "- get_order_status: ONLY if the current message explicitly asks about the status "
    "of a specific order and gives an order ID.\n"
    "- get_refund_status: ONLY if the current message explicitly asks about the status "
    "of a specific refund already requested and gives a refund ID.\n"
    "- add_order_note: ONLY if the current message shares something about a specific "
    "order worth remembering for future conversations (a preference, a recurring "
    "complaint, a special request) -- NOT for a plain status question. Summarize it in "
    "one short sentence for the `note` argument. Do not call this at the same time as "
    "get_order_status; pick whichever one the message is actually asking for.\n"
    "- escalate_to_human: ONLY if the current message explicitly asks to speak to a "
    "human/agent, or clearly demands escalation. Summarize the issue in one sentence "
    "for the `summary` argument.\n"
    "- If a question needs an order/refund ID that wasn't given, ask the user for it "
    "instead of calling a tool.\n"
    "- Greetings, small talk, or anything not matching the above: answer directly, "
    "call NO tool at all.\n\n"
    "Never call more than one tool for a single message. Keep answers under 200 words. "
    "Provide step-by-step guidance when relevant.\n\n"
    "Formatting: always answer in clean Markdown. Use **bold** for key terms, "
    "numbers, order/refund IDs, and dates. Use a numbered or bulleted list for "
    "any multi-step process or multiple items instead of one dense paragraph. "
    "Keep any prose in short paragraphs."
)


def _extract_mcp_text(result: Any) -> str:
    """MCP tool calls return a CallToolResult (content=[TextContent(...), ...]) rather
    than a plain string -- pull the text out so it isn't shown to the user as a raw
    Python repr of the result object."""
    content = getattr(result, "content", None)
    if content:
        texts = [block.text for block in content if hasattr(block, "text")]
        if texts:
            return "\n".join(texts)
    return str(result)


def _wrap_mcp_tool(tool: FunctionTool) -> FunctionTool:
    """Rebuild an MCP-derived FunctionTool so its output is clean text and it's
    return_direct (consistent with every other tool here -- see build_agent)."""
    original_async_fn = tool.async_fn

    async def wrapped(**kwargs: Any) -> str:
        raw = await original_async_fn(**kwargs)
        return _extract_mcp_text(raw)

    return FunctionTool.from_defaults(
        async_fn=wrapped,
        name=tool.metadata.name,
        description=tool.metadata.description,
        fn_schema=tool.metadata.fn_schema,
        return_direct=True,
    )


async def _load_mcp_tools() -> list[FunctionTool]:
    # Launched as a subprocess over stdio (see MCP_SERVER_PATH) -- uses sys.executable
    # so it runs with this venv's interpreter/dependencies, not whatever "python" is
    # first on PATH. Each tool call opens a fresh subprocess+session under the hood
    # (llama-index-tools-mcp's BasicMCPClient design); fine for a demo's call volume,
    # but a persistent session or an HTTP-based MCP server would avoid that overhead
    # in a higher-throughput deployment.
    client = BasicMCPClient(sys.executable, args=[str(MCP_SERVER_PATH)])
    spec = McpToolSpec(
        client=client,
        allowed_tools=[
            "get_order_status",
            "get_refund_status",
            "add_order_note",
            "escalate_to_human",
        ],
    )
    tools = await spec.to_tool_list_async()
    return [_wrap_mcp_tool(t) for t in tools]


async def build_agent(index: VectorStoreIndex, llm: LLM) -> FunctionAgent:
    # return_direct=True on every tool here, including search_faq: the query
    # engine already synthesizes a coherent answer from the retrieved FAQ
    # chunks (its default response_mode does its own LLM call over the
    # retrieved nodes), so a further "let the agent re-synthesize the tool
    # result" step is redundant -- it doubles token usage per FAQ turn for no
    # quality gain, and empirically made the agent noticeably more likely to
    # call search_faq repeatedly (each extra round-trip is another chance to
    # hit Groq's occasional malformed-tool-call quirk and retry/re-decide).
    search_faq_tool = _CachedQueryEngineTool.from_defaults(
        query_engine=build_faq_query_engine(index),
        name="search_faq",
        description=(
            "Search Flipkart's FAQ knowledge base for policy and how-to questions "
            "(returns, refunds, payments, EMI, shipping, etc). Call this AT MOST ONCE "
            "per user question, with one consolidated query covering everything asked -- "
            "it returns a complete synthesized answer in a single call, so there is no "
            "need to call it again for sub-aspects of the same question."
        ),
        return_direct=True,
    )

    mcp_tools = await _load_mcp_tools()

    return FunctionAgent(
        tools=[search_faq_tool, *mcp_tools],
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        # Re-enabled after re-testing live: this used to be False because of a
        # Groq+litellm bug where a streamed response containing a tool call
        # crashed litellm's error parser mid-stream. Retested against the
        # current litellm version across small-talk (plain streaming),
        # search_faq (tool call), and an MCP tool call -- the crash didn't
        # reproduce (litellm's since had many releases); the only failure seen
        # was an ordinary RateLimitError, already handled by the try/except
        # around agent.run() in app.py. Revert to False if the original
        # mid-stream crash resurfaces.
        streaming=True,
    )
