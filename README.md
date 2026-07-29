# Flipkart FAQ Chatbot — Agentic RAG Customer Support Platform

An autonomous customer-support chatbot for Flipkart that doesn't just answer FAQ questions —
it takes real actions: checking order status, checking refund status, saving account notes,
and escalating unresolved issues to a human agent. Built as an end-to-end agentic RAG platform,
not a thin wrapper around a single LLM call: intent routing, tool-calling, a provider-agnostic
LLM gateway, guardrails, a semantic cache, hybrid retrieval with reranking, persistent memory,
automated evaluation, and full request tracing all sit between the chat UI and the model.

<p align="left">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-async%20API%20%2B%20WebSocket-009688?logo=fastapi&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React%2019-TypeScript-61DAFB?logo=react&logoColor=black">
  <img alt="LlamaIndex" src="https://img.shields.io/badge/LlamaIndex-agentic%20RAG-black">
  <img alt="Qdrant" src="https://img.shields.io/badge/Qdrant-hybrid%20vector%20search-DC244C">
  <img alt="LiteLLM" src="https://img.shields.io/badge/LiteLLM-gateway%20%2B%20fallback-6E56CF">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-multi--stage%20build-2496ED?logo=docker&logoColor=white">
  <img alt="Langfuse" src="https://img.shields.io/badge/Langfuse-observability-orange">
</p>

## 🎥 Demo

![Demo](assets/demo.gif)

**Full walkthrough:** https://github.com/your-repo/issues/1#issuecomment-xxxx

## Table of contents

- [Demo](#demo)
- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Request lifecycle: one chat turn](#request-lifecycle-one-chat-turn)
- [Ingestion pipeline](#ingestion-pipeline)
- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Evaluation](#evaluation)
- [Engineering deep dives](#engineering-deep-dives)
- [Deployment](#deployment)

## What it does

| Layer | What's implemented |
|---|---|
| **UI** | Custom React 19 + TypeScript SPA, WebSocket token streaming, FastAPI backend serving both |
| **Auth & chat history** | JWT cookie login + Postgres-backed thread list/resume (own schema, no vendor lock-in) |
| **AI Gateway** | LiteLLM-based routing across 3 models/2 providers, automatic fallback, cost/latency logging |
| **Guardrails** | 7 scanners (4 input + 3 output) via LLM Guard — jailbreak/prompt-injection blocking, PII redaction, parallelized |
| **Semantic cache** | Qdrant-backed, skips the LLM entirely on repeated/paraphrased FAQ questions |
| **Agent** | LlamaIndex `FunctionAgent` — tool-calling agent (`search_faq` + 4 MCP tools) |
| **Planning** | Intent classifier (FAQ / order status / refund / escalate / general chat) gates cache eligibility |
| **MCP tools** | Real MCP server (stdio) exposing order/refund/note/escalation tools over a mock SQLite backend |
| **Knowledge (RAG)** | Hybrid dense + BM25 sparse retrieval, cross-encoder reranking, idempotent ingestion |
| **Memory** | SQL-persisted session memory + cross-session long-term notes anchored to order IDs |
| **LLM** | Groq (Llama 3.3 70B / 3.1 8B) for generation, Ollama Cloud for tool-call decisions, via the Gateway |
| **Evaluation** | RAGAS (faithfulness, relevancy, context precision/recall) + tool-routing + red-team guardrail suites, 25 scenarios |
| **Observability** | Langfuse Cloud tracing (full request tree, per-user/session attribution, guardrail + cache scores) |

## Architecture

```mermaid
flowchart TD
    User(["Browser"]) -- React SPA --> UI["React frontend\nfrontend/"]
    UI -- "REST: login / threads" --> API["FastAPI backend\nmain.py + src/api/"]
    UI -- "WebSocket: /ws/chat/:id" --> API
    API -- auth / threads / messages --> PG[("PostgreSQL\nusers · threads · messages")]

    API --> InGuard["Guardrails — input scan\nPromptInjection · Toxicity · BanTopics · TokenLimit"]
    InGuard -- blocked --> Refusal(["Canned refusal"])
    InGuard -- clean --> Planner["Planner\nintent classification"]

    Planner --> CacheCheck{"cacheable intent\n+ cache hit?"}
    CacheCheck -- hit --> CachedReply(["Cached response"])
    CacheCheck -- miss --> Agent["FunctionAgent\nchat_agent.py"]

    Agent --> SearchFAQ["search_faq tool\nhybrid retrieval + rerank"]
    Agent --> MCP["4 MCP tools\nstdio subprocess"]
    SearchFAQ --> Qdrant[("Qdrant\nFAQ vectors + response cache")]
    MCP --> Backend[("SQLite\nmock orders / refunds / notes")]

    SearchFAQ --> Gateway["AI Gateway\nLiteLLM routing + fallback"]
    Agent --> Gateway
    Gateway --> Groq(["Groq\nLlama 3.3-70B / 3.1-8B"])
    Gateway --> Ollama(["Ollama Cloud\ngemma4:cloud — tool calls only"])

    Gateway --> OutGuard["Guardrails — output scan\nPII redaction · refusal / URL checks"]
    OutGuard --> FinalReply(["Final response"])

    API -.session memory.-> ChatMem[("SQLite\nchat_memory.db")]
    API -.traces.-> Langfuse[("Langfuse Cloud")]
    Gateway -.scored by.-> Eval["run_eval.py\nRAGAS + tools + red-team"]
```

## Request lifecycle: one chat turn

Every message runs the same five-stage pipeline, whether it resolves from cache, from the
knowledge base, or from an MCP tool call. Status frames over the WebSocket keep the UI honest
about *which* stage is running — guardrail scanning alone is typically 1.5–4.5s of otherwise
silent latency.

```mermaid
sequenceDiagram
    participant U as User (Browser)
    participant WS as chat_ws.py
    participant G as Guardrails
    participant P as Planner
    participant C as Semantic Cache
    participant A as FunctionAgent
    participant T as search_faq / MCP tools
    participant L as LLM Gateway (LiteLLM)

    U->>WS: {"content": "..."}
    WS->>G: scan_user_input()
    alt blocked
        G-->>U: canned refusal (no LLM call)
    else clean
        G-->>WS: sanitized query
        WS->>P: classify_intent()
        P-->>WS: intent label
        WS->>C: cacheable? get(query)
        alt cache hit
            C-->>U: cached response (simulated stream)
        else cache miss
            WS->>A: agent.run(query, memory)
            A->>T: tool call (0 or 1, return_direct)
            T-->>A: tool result
            A->>L: synthesis / tool-call decision
            L-->>A: completion
            A-->>WS: streamed / final response
            WS->>G: scan_bot_output()
            G-->>WS: PII-redacted response
            WS->>U: {"type":"done", "content": "..."}
            WS->>C: set(query, response) if cacheable & clean
        end
    end
```

## Ingestion pipeline

Offline, idempotent, run once and on every dataset change:

```mermaid
flowchart LR
    CSV["faq_data.csv\n~2,000 rows"] --> Chunk["Chunk + tag\nsource_type: faq"]
    PDF1["Flipkart-1.pdf"] --> Chunk
    PDF2["Flipkart-2.pdf"] --> Chunk2["Chunk + tag\nsource_type: policy_doc"]
    Chunk --> Embed["Dense embed\nbge-small-en-v1.5"]
    Chunk2 --> Embed
    Chunk --> Sparse["Sparse embed\nQdrant/bm25"]
    Chunk2 --> Sparse
    Embed --> Upsert["Upsert by uuid5(text)\nunchanged chunks are no-ops"]
    Sparse --> Upsert
    Upsert --> QdrantDB[("Qdrant: flipkart_faqs")]
```

## Tech stack

| Concern | Choice |
|---|---|
| Agent framework | LlamaIndex `FunctionAgent` (tool-calling agent workflow) |
| LLM gateway | LiteLLM — provider-agnostic routing, fallback, retries, cost/latency logging |
| LLMs | Groq `llama-3.3-70b-versatile` (primary) → `llama-3.1-8b-instant` (fallback); Ollama Cloud `gemma4:cloud` (agent tool-call decisions only) |
| Vector DB | Qdrant (self-hosted via Docker) — hybrid dense + sparse, one collection for FAQs, one for the semantic cache |
| Embeddings | `BAAI/bge-small-en-v1.5` (dense, FastEmbed) + `Qdrant/bm25` (sparse) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Guardrails | [LLM Guard](https://github.com/protectai/llm-guard) — PromptInjection, Toxicity, BanTopics, TokenLimit, Sensitive (Presidio PII), NoRefusal, MaliciousURLs |
| Tool protocol | [Model Context Protocol](https://modelcontextprotocol.io) — real stdio MCP server, not in-process function calls |
| Backend | FastAPI, WebSocket streaming, asyncpg (no ORM) |
| Frontend | React 19 + TypeScript, Vite, Tailwind CSS v4 (CSS-first theming), Framer Motion |
| Auth | JWT in an httpOnly cookie, bcrypt password hashing |
| Persistence | PostgreSQL (users/threads/messages), SQLite (session memory, mock backend) |
| Evaluation | [RAGAS](https://github.com/explodinggradients/ragas) + custom tool-routing and red-team suites |
| Observability | Langfuse Cloud via OpenInference's LlamaIndex instrumentor |
| Deployment | Docker (multi-stage: Node build → Python runtime) — see [Deployment](#deployment) |

## Project layout

```
main.py                    FastAPI entrypoint — agent/cache built once at process startup
frontend/                  React + TypeScript + Tailwind UI (Vite)
  src/pages/                 Login, Chat
  src/components/            Sidebar, MessageBubble, ChatInput, StarterPrompts, MessageActions
  src/hooks/                 useAuth, useChatSocket, useTheme
  src/api/client.ts          fetch wrapper (cookie-authenticated)
docker-compose.yml          Self-hosted Qdrant container
Dockerfile                  Multi-stage build: frontend (node:20-slim) → backend (python:3.10-slim)
db/schema.sql               Postgres schema: users / threads / messages
config/models.yaml          AI Gateway model routing config
src/
  api/                       FastAPI routers: auth.py, threads.py, chat_ws.py, security.py, deps.py, state.py
  persistence/chat_store.py  Thread/message persistence (asyncpg)
  auth/                      Password auth (store.py) + user-provisioning CLI (manage_users.py)
  common/qdrant_factory.py   Local-embedded vs remote/cloud Qdrant client
  gateway/                   AI Gateway: llm_gateway.py, guardrails.py, cache.py
  agent/                     planner.py (intent classifier), chat_agent.py (FunctionAgent + tools)
  tools/                     mcp_server.py (MCP server) + mock_backend.py (mock SQLite backend)
  memory/persistent_memory.py  SQL-persisted session memory
  ingestion/embed_qdrant.py  Offline chunk + hybrid-embed + upsert pipeline
  eval/run_eval.py           RAGAS + tool-calling + red-team eval suites (eval/data/, eval/results/)
  observability/tracing.py   Langfuse tracing (OpenInference LlamaIndex instrumentor)
data/
  dataset/                    FAQ CSV + Flipkart policy PDFs
  data_scraper/                Selenium scraper used to build the dataset
  data_pre.ipynb               Data prep notebook
```

## Getting started

1. **Start Qdrant** (self-hosted via Docker):
   ```bash
   docker compose up -d
   ```

2. **Backend dependencies**:
   ```bash
   python -m venv venv
   venv\Scripts\activate       # Windows
   pip install -r requirements.txt
   ```

3. **Frontend dependencies** (Node.js 20+):
   ```bash
   cd frontend && npm install && cd ..
   ```

4. **Set up Postgres** for login + chat history — create a database (e.g. `flipkart_chatbot`)
   and run [`db/schema.sql`](db/schema.sql) against it once:
   ```bash
   psql -d flipkart_chatbot -f db/schema.sql
   ```

5. **Install [Ollama](https://ollama.com)** and pull the agent's dedicated tool-calling model
   (not optional — see [Engineering deep dives](#engineering-deep-dives) for why):
   ```bash
   ollama signin
   ollama pull gemma4:cloud
   ```
   Leave the daemon running; `config/models.yaml`'s `tool_call` entry expects it at
   `http://localhost:11434`.

6. **Configure `.env`**:
   ```env
   CHATGROQ_API_KEY=...                # free at console.groq.com
   QDRANT_URL=http://localhost:6333
   DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@localhost:5432/flipkart_chatbot
   JWT_SECRET=...                      # e.g. python -c "import secrets; print(secrets.token_urlsafe(32))"
   # LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY=...   # optional, see Observability
   ```

7. **Create a login user** (no self-serve signup):
   ```bash
   python src/auth/manage_users.py create alice "some-password"
   ```

8. **Ingest the FAQ dataset**:
   ```bash
   python src/ingestion/embed_qdrant.py           # incremental upsert, safe to re-run
   python src/ingestion/embed_qdrant.py --reset    # full rebuild
   ```

9. **Run it** (two processes in dev):
   ```bash
   python -m uvicorn main:app --reload --reload-dir src
   cd frontend && npm run dev      # http://localhost:5173, proxies /api and /ws to :8000
   ```
   In production (or via Docker), FastAPI serves the built frontend itself on a single port.

   > **Windows note:** use `python -m uvicorn`, not the bare `uvicorn` executable — the
   > standalone launcher can lose track of the venv interpreter on reload. Also always pass
   > `--reload-dir src`: without it, uvicorn watches the whole project tree, including `venv/`
   > (a guardrail model's one-time download mid-request force-restarted the server during
   > testing) and `data/` (rewritten on every chat turn). Single worker only — the agent and
   > SQLite-backed session memory are process-wide singletons built once at startup.

10. **Or run via Docker**:
    ```bash
    docker build -t flipkart-chatbot .
    docker run -p 8000:8000 --env-file .env -e OLLAMA_API_BASE=http://host.docker.internal:11434 flipkart-chatbot
    ```

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `CHATGROQ_API_KEY` | Yes | Groq API key for the primary/fallback LLMs |
| `QDRANT_URL` | No (defaults to embedded/local) | Points at the Docker Qdrant container |
| `DATABASE_URL` | Yes | Postgres connection string (asyncpg) for auth + chat history |
| `JWT_SECRET` | Yes | Signs the login session cookie |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | No | Enables Langfuse tracing; every trace call is a no-op without them |
| `OLLAMA_API_BASE` | Only in Docker | Overrides `config/models.yaml`'s `localhost:11434` (which means *the container itself* otherwise) |
| `QDRANT_API_KEY` | Only for Qdrant Cloud | No API key needed for the default unsecured local/Docker Qdrant |
| `AGENT_TOOL_CALL_MODEL_KEY` | No (defaults to `tool_call`/Ollama) | Overrides which `config/models.yaml` entry the agent's tool-call step uses — set to `fallback` on a host that can't keep an `ollama signin`'d daemon running in the background (see [Deployment](#deployment)) |
| `PORT` | No (defaults to 8000) | Overrides the port the server listens on — some hosts assign their own and expect the container to read it |

## Evaluation

`src/eval/run_eval.py` — three independent suites run against the live stack (real Groq calls,
real Qdrant), no mocking:

```bash
python src/eval/run_eval.py                     # all three suites
python src/eval/run_eval.py --suite rag          # RAGAS only
python src/eval/run_eval.py --suite tools        # agent tool-routing only
python src/eval/run_eval.py --suite guardrails   # red-team only, no LLM calls
```

- **RAG (RAGAS)** — 6 golden questions through the real query engine, scored on faithfulness,
  answer relevancy, context precision, context recall. Deliberately small and throttled to
  `max_workers=1` — Groq's free-tier TPM budget can't absorb RAGAS's judge-call volume at
  higher concurrency.
- **Tool-calling** — 9 scenarios through the real agent, asserting the expected tool was (or
  wasn't) called and the answer contains the expected content. This is what actually catches
  routing regressions when a prompt or tool description changes — RAGAS alone only scores
  retrieval/generation.
- **Guardrails (red-team)** — 10 adversarial cases + PII-redaction checks against
  `guardrails.py` directly, verifying both that attacks are blocked *and* that legitimate
  questions aren't (a guardrail that blocks everything scores "safe" but is useless).

**Latest verified results:** guardrails **11/11**, tool-calling **9/9**, RAGAS faithfulness
**1.00**, answer relevancy **0.87**, context precision **0.78**, context recall **1.00**.

## Engineering deep dives

<details>
<summary><strong>Why the agent's tool-calling model isn't Groq</strong></summary>

Llama models on Groq occasionally emit a malformed tool-call that Groq's own API rejects with
`tool_use_failed` — and a bug in LiteLLM's Groq-specific streaming-error parser turns that
clean rejection into an unhandled crash instead of a catchable error, killing the turn.
`max_iterations` and gateway fallback don't help, since the crash happens *before* LiteLLM's
own retry logic runs.

Fixed by giving the agent's tool-call decision step a dedicated model
(`config/models.yaml`'s `tool_call` entry — `gemma4:cloud` via a local Ollama daemon proxying
to Ollama Cloud) instead of the primary Groq model. `Settings.llm` (Groq) still handles
RAG-answer synthesis and intent classification, both plain text generation and never the
actual problem. Two extra fixes were needed to make this work at all: `litellm.drop_params =
True` (Ollama rejects the `parallel_tool_calls` param LlamaIndex sends unconditionally), and
manually registering `gemma4:cloud` as function-calling-capable in LiteLLM's model registry
(it reports `False` purely because LiteLLM's static registry predates the model, not because
it can't do it — verified directly against Ollama's raw API). Verified live: 8/8 distinct FAQ
questions forcing fresh tool calls succeeded with zero crashes, where the same test previously
failed a meaningful fraction of the time.

This does mean the Ollama daemon is a real, non-optional dependency for local dev. For a
deployment target that can't keep one signed in and running in the background — true of most
free-tier hosts, which don't support a persistent authenticated background process alongside
the main server — `AGENT_TOOL_CALL_MODEL_KEY=fallback` (see [Configuration](#configuration))
routes tool-calling to Groq's fallback model instead, accepting the rare malformed-tool-call
failure this whole fix exists to avoid. That failure is already caught by `chat_ws.py`'s
try/except and degrades to one failed turn with a generic error message, not a crash — an
acceptable trade for a deployment that can't run Ollama at all, not a regression for local dev
where Ollama stays the default.

</details>

<details>
<summary><strong>Why guardrails run in parallel, not sequentially</strong></summary>

Four transformer-backed input scanners running one after another on CPU (~1.5–4.5s observed)
were the single biggest latency contributor in the request path. All four
(`PromptInjection`/`Toxicity`/`BanTopics`/`TokenLimit`) are pure detectors with no
cross-scanner data dependency — verified by reading each scanner's `.scan()` source, not
assumed — so they run concurrently via `asyncio.gather`, cutting wall-clock from the sum of
all four to roughly the slowest single one. Output scanning is only partially parallelized:
`Sensitive` (PII redaction) must run first since its redacted text is what the remaining
scanners should see.

</details>

<details>
<summary><strong>Why the semantic cache is versioned</strong></summary>

A real incident: a "modes of payment" answer got cached before the FAQ prompt was changed to
require Markdown formatting, and kept being served unformatted, verbatim, to every later
session asking a similar question — nothing tied a cache entry to the prompt/template that
produced it. `CACHE_VERSION` in `src/gateway/cache.py` fixes this: every entry carries the
version it was written with, checked on read the same way the 7-day TTL is. Bump the version
whenever a prompt change would make previously-cached answers wrong, and stale entries stop
being served automatically — no manual cache wipe.

</details>

<details>
<summary><strong>Why a real MCP server instead of in-process functions</strong></summary>

`src/tools/mcp_server.py` is a genuine [Model Context Protocol](https://modelcontextprotocol.io)
server (stdio transport, `FastMCP`), launched as a subprocess and spoken to over the actual MCP
client/server protocol — the same way the agent would talk to a real external tool server, not
a shortcut through plain Python function calls. It exposes `get_order_status`,
`get_refund_status`, `add_order_note`, and `escalate_to_human` against a mock SQLite backend.
Every tool (including `search_faq`) is `return_direct=True`: the result is returned to the user
with no further LLM synthesis round-trip, which halves token usage per turn and avoids a
failure mode found during testing where the agent would otherwise sometimes re-invoke a tool
across an extra synthesis step.

</details>

<details>
<summary><strong>Why a custom React/FastAPI UI replaced Chainlit</strong></summary>

The project originally ran on Chainlit (a batteries-included chat UI framework). Two concrete,
reproducible incidents forced the migration to a custom React + TypeScript frontend and FastAPI
backend: (1) a Chainlit version upgrade silently added columns to its internal persistence
schema that the reverse-engineered local schema didn't have, breaking tool-call step
persistence invisibly (fire-and-forget `asyncio.create_task`, no surfaced error); (2) a
long-standing, unresolved upstream Chainlit bug where reopening a past thread sometimes showed
only the user's messages, not the assistant's replies. Both are now structurally impossible —
`GET /api/threads/{id}` is the same code path for a fresh load and a sidebar resume, returning
exactly the rows in Postgres, with no separate vendor rendering layer that could disagree with
the database. Every other layer (agent, RAG, MCP tools, guardrails, cache, memory, eval,
tracing) was untouched — this was a UI/serving-layer swap, not a system rebuild.

</details>

<details>
<summary><strong>Observability: what actually gets traced</strong></summary>

`src/observability/tracing.py` registers OpenInference's `LlamaIndexInstrumentor`
(OpenTelemetry-based) against Langfuse Cloud, so one trace per chat message shows the whole
tree: agent step → tool call (or retrieval → rerank → synthesis) → the underlying LLM
generation, with latency and token usage on every span — a few lines of setup, not manual
instrumentation scattered through the agent code. Every turn is wrapped with
`propagate_attributes(user_id=..., session_id=...)` using the authenticated username and the
thread's stable ID, so traces are filterable by user or conversation. Guardrail
blocks/redactions and cache hits/misses are fired as Langfuse scores, and eval runs are tagged
`["eval", ...]` so they're visible in the same project without polluting production trace
views. Entirely optional — every function is a no-op without Langfuse keys set.

</details>

## Deployment

Single multi-stage `Dockerfile`: a `node:20-slim` stage builds the React frontend, a
`python:3.10-slim` stage runs the FastAPI app and serves the built static frontend directly —
one container, one port, no separate frontend process or CORS/proxy setup needed in production.
Qdrant and Postgres are external services either way, pointed to via `QDRANT_URL` and
`DATABASE_URL` — Docker Compose for local Qdrant, or any managed/cloud provider for either.

```bash
docker build -t flipkart-chatbot .
docker run -p 8000:8000 --env-file .env flipkart-chatbot
```

The listen port is read from `$PORT` (defaults to 8000) — hosts that assign their own port
just need it passed as an env var, no image rebuild. On a host that can't keep an `ollama
signin`'d daemon authenticated in the background (most free-tier hosts), set
`AGENT_TOOL_CALL_MODEL_KEY=fallback` to route the agent's tool-call step to Groq instead of
Ollama Cloud — see the "Why the agent's tool-calling model isn't Groq" deep dive above for why
that step normally avoids Groq, and why falling back to it here is an accepted, gracefully-caught
trade-off rather than a silent failure mode.

There's no permanently-hosted public instance right now — see the [Demo](#demo) section above
for a recorded walkthrough instead of a live link.
