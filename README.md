# Aster

### A production-minded agentic RAG customer-support portfolio project

[![Live demo](https://img.shields.io/badge/live-demo-7C5CFC)](https://140.245.234.125/aster/)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-WebSocket-009688?logo=fastapi&logoColor=white)
![React 19](https://img.shields.io/badge/React_19-TypeScript-61DAFB?logo=react&logoColor=111)
![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-OCI_Free_Tier-2496ED?logo=docker&logoColor=white)

**Live application:** [https://140.245.234.125/aster/](https://140.245.234.125/aster/)

Aster is a full-stack customer-support assistant built to demonstrate more than a
single retrieval call. It combines a cinematic React interface with bounded intent
routing, grounded FAQ retrieval, account-scoped tools, durable conversations,
guardrails, citations, idempotent turns, and production deployment on Oracle Cloud.

The application uses a Flipkart help-centre dataset as its knowledge source. Order,
refund, note, and handoff operations are deliberately simulated and clearly labelled;
the project is not connected to Flipkart or any live commerce system.

## Highlights

- **Scope-controlled assistant:** sports, news, coding, recommendations, other
  retailers, and mixed off-topic requests never reach the general-purpose answer path.
- **Grounded RAG:** FAQ answers come from versioned Qdrant knowledge collections and
  include source metadata.
- **Safe agent tools:** order status, refund status, order notes, and handoff use a
  trusted actor context and allow at most one account action per turn.
- **Durable chat:** PostgreSQL stores users, revocable sessions, threads, messages,
  turns, quotas, and an idempotent action ledger.
- **Reliable WebSockets:** typed frames, bounded payloads, stable client message IDs,
  replay after reconnect, turn deadlines, and committed completion semantics.
- **Anonymous demo and accounts:** explore without signing in, or register to retain
  conversation history.
- **Image support:** JPEG, PNG, and WebP product-damage images are validated before a
  bounded vision-description step.
- **Accessible interface:** responsive layout, light/dark/system themes, keyboard
  navigation, reduced-motion support, clear connection states, and mobile-safe input.
- **Production controls:** secure cookies, origin checks, account/IP quotas, concurrency
  limits, security headers, health probes, non-root containers, backups, and log rotation.

## Architecture

```mermaid
flowchart LR
    Browser[React 19 SPA] -->|HTTPS / WebSocket| Caddy[Caddy]
    Caddy --> API[FastAPI]
    API --> Guard[Input guardrails]
    Guard --> Planner[Intent and scope planner]

    Planner -->|social / out of scope / multi-action| Fixed[Deterministic response]
    Planner -->|public FAQ| FAQ[FAQ query engine]
    Planner -->|account support| Agent[LlamaIndex FunctionAgent]

    FAQ --> Cache[(Qdrant semantic cache)]
    FAQ --> Knowledge[(Versioned Qdrant knowledge)]
    FAQ --> Cohere[Cohere embed + rerank]
    FAQ --> Groq[Groq synthesis]

    Agent --> Search[search_faq]
    Agent --> Tools[Actor-scoped support tools]
    Search --> FAQ
    Tools --> Fixtures[Simulated commerce records]
    Tools --> Postgres[(PostgreSQL action ledger)]

    API --> Postgres
    API -. optional traces .-> Langfuse[Langfuse]
```

### One chat turn

1. FastAPI validates the WebSocket frame, session, origin, quotas, payload size, and
   idempotency key.
2. Input guardrails reject clear dangerous requests and prompt-injection attempts.
3. The planner assigns one of eight bounded intents: FAQ, order status, refund status,
   order note, escalation, multiple actions, social chat, or out of scope.
4. Social, out-of-scope, and multi-action messages receive deterministic responses.
5. Exact public FAQ questions may use the namespaced semantic cache. Other supported
   requests use grounded retrieval or one authorized tool.
6. The full answer is reviewed before delivery. The server commits authenticated turns
   before sending the final completion event.

## Product behavior

| Area | Behavior |
| --- | --- |
| FAQ | Returns, refunds, payments, EMI, delivery, cancellation, account help, and other indexed policies |
| Orders | Looks up clearly labelled demonstration orders such as `FK1001` |
| Refunds | Looks up clearly labelled demonstration refunds such as `RF2001` |
| Notes | Stores an account-private simulation note; demo notes last only for that socket session |
| Handoff | Creates a deterministic simulation ticket and states that no real agent was notified |
| Images | Adds an unverified visual description to a support question; it is never treated as proof |
| General knowledge | Returns a fixed support-scope message without asking the answer model |
| Multiple actions | Requests one action at a time and executes no tool |

## Reliability and safety design

- **Fail closed:** unavailable input checking or intent classification cannot fall
  through to an unrestricted answer.
- **Least-privilege tools:** identity comes from a server-side context, never from an
  LLM argument. Every authenticated tool call rechecks the session and thread owner.
- **Idempotent mutations:** action keys combine the durable turn, action, and resource.
  Retries return the recorded result instead of duplicating the operation.
- **Regeneration safety:** regeneration is versioned and read-only; responses involving
  account actions cannot be replayed as mutations.
- **Private cache boundary:** only a closed vocabulary of public FAQ questions can enter
  the shared semantic cache. Account and conversation-specific content cannot.
- **Knowledge releases:** ingestion builds a complete immutable collection, validates
  it, and atomically moves the live alias. Previous revisions remain available for
  rollback.
- **Output hygiene:** unapproved external URLs, credentials, card-like numbers, email
  addresses, and Indian phone numbers are removed before delivery.

## Technology

| Concern | Implementation |
| --- | --- |
| Frontend | React 19, TypeScript 6, Vite 8, Tailwind CSS 4, Framer Motion |
| API | FastAPI, Uvicorn, typed REST and WebSocket contracts |
| Agent/RAG | LlamaIndex `FunctionAgent`, grounded query engine, source evidence |
| LLM gateway | LiteLLM with explicit Groq `gpt-oss-120b` to `gpt-oss-20b` fallback |
| Guardrails | Deterministic checks plus Meta Llama Prompt Guard 2 on Groq |
| Vision | Llama 4 Scout on Groq |
| Embeddings | Cohere `embed-english-v3.0` in production; FastEmbed local fallback |
| Reranking | Cohere `rerank-english-v3.0` in production; local cross-encoder fallback |
| Vector storage | Qdrant 1.16; dense production retrieval and hybrid local retrieval |
| Persistence | PostgreSQL 17 through bounded asyncpg pools |
| Authentication | Argon2id, legacy bcrypt verification, revocable 8-hour JWT sessions |
| Observability | Structured logs and optional Langfuse/OpenInference traces |
| Deployment | Multi-stage Docker image, Docker Compose, Caddy, OCI Always Free compute |

## Repository layout

```text
frontend/                     React application and design system
src/
  agent/                      Planner, grounded answer orchestration, agent tools
  api/                        Auth, threads, WebSockets, protocol, settings, limits
  auth/                       Argon2id user storage and admin user management
  common/                     Database, Qdrant, embedding, knowledge-release helpers
  gateway/                    LLM gateway, guardrails, semantic cache, vision
  ingestion/                  Immutable knowledge publication pipeline
  memory/                     Conversation-memory adapter
  persistence/                Chat store, atomic turns, migrations, maintenance
  tools/                      Actor-scoped service and optional MCP adapter
  eval/                       Intent, RAG, tool, and red-team evaluation suites
db/                           Base schema and additive migrations
deploy/                       OCI Compose, Caddy example, backup script
docs/operations/              Rollout and remediation notes
docs/reviews/                 Production review and validation evidence
tests/                        Deterministic backend and integration tests
main.py                       FastAPI bootstrap and application lifespan
Dockerfile                    Node build stage and non-root Python runtime
```

## Run locally

### Prerequisites

- Python **3.12**
- Node.js **22**
- Docker Desktop
- Groq API key
- Cohere API key, recommended for the same lightweight path used in production

### 1. Start PostgreSQL and Qdrant

```bash
docker run --name aster-postgres-dev \
  -e POSTGRES_PASSWORD=aster \
  -e POSTGRES_DB=aster \
  -p 5432:5432 -d postgres:17-alpine

docker compose up -d qdrant
```

### 2. Install dependencies

```bash
python -m venv venv

# Windows PowerShell
./venv/Scripts/Activate.ps1

# macOS/Linux
# source venv/bin/activate

pip install -r requirements-dev.txt
cd frontend
npm ci
cd ..
```

### 3. Configure the environment

Copy `.env.example` to `.env`, then set at least:

```env
APP_ENV=development
PUBLIC_BASE_PATH=/
DATABASE_URL=postgresql://postgres:aster@127.0.0.1:5432/aster
JWT_SECRET=generate-a-random-secret-with-at-least-32-characters
CHATGROQ_API_KEY=your-groq-key
COHERE_API_KEY=your-cohere-key
QDRANT_URL=http://127.0.0.1:6333
TRUSTED_ORIGINS=http://localhost:5173

# Use Groq for tool decisions without a local Ollama daemon.
AGENT_TOOL_CALL_MODEL_KEY=fallback
```

Generate a signing secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

If `COHERE_API_KEY` is omitted, the development requirements provide local embedding
and reranking models. Switching between local and Cohere embeddings requires publishing
a new knowledge release because their vector dimensions differ.

### 4. Prepare storage

```bash
python -m src.persistence.migrate
python -m src.ingestion.embed_qdrant
```

### 5. Start the application

Terminal one:

```bash
python -m uvicorn main:app --reload --reload-dir src --port 8000
```

Terminal two:

```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` and `/ws`
to FastAPI, keeping browser requests same-origin.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | PostgreSQL DSN for accounts, sessions, conversations, quotas, and actions |
| `JWT_SECRET` | Yes | Signs session tokens; production requires a strong non-placeholder value |
| `CHATGROQ_API_KEY` | Yes | Answer, planning, guardrail, tool-decision, and vision models |
| `COHERE_API_KEY` | Production | Hosted 1024-dimensional embeddings and reranking |
| `QDRANT_URL` | Production | Qdrant service URL; development may use embedded storage instead |
| `QDRANT_API_KEY` | Cloud only | Qdrant Cloud authentication |
| `KNOWLEDGE_ALIAS` | No | Live knowledge alias; defaults to `flipkart_faqs_live` |
| `TRUSTED_ORIGINS` | Production | Comma-separated exact HTTPS origins; wildcards are rejected |
| `PUBLIC_BASE_PATH` | No | Mount and cookie path; `/aster/` in the OCI deployment |
| `AGENT_TOOL_CALL_MODEL_KEY` | No | Model-config key used for agent tool decisions |
| `ENABLE_DEMO` | No | Enables the anonymous WebSocket demo |
| `ENABLE_SHARED_FAQ_CACHE` | No | Enables the tightly allowlisted cross-user FAQ cache |
| `ENABLE_CONTENT_TRACING` | No | Allows content in optional traces; keep `false` in production |
| `MAX_CONCURRENT_TURNS` | No | Process-wide work bound |
| `CHAT_PER_HOUR` | No | Per-account authenticated chat limit |
| `TURN_TIMEOUT_SECONDS` | No | End-to-end turn deadline |
| `WS_IDLE_TIMEOUT_SECONDS` | No | Idle WebSocket timeout |
| `MAX_FRAME_BYTES` | No | Transport frame limit |

See [`.env.example`](.env.example) for all operational defaults.

## Tests and evaluation

### Deterministic test suite

Integration tests refuse to run against a default PostgreSQL database. They require a
localhost instance on a nondefault port with the database name `aster_test`.

```bash
docker run --rm --name aster-backend-tests \
  -e POSTGRES_PASSWORD=aster-test-only \
  -e POSTGRES_DB=aster_test \
  -p 55478:5432 -d postgres:17-alpine
```

PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql://postgres:aster-test-only@127.0.0.1:55478/aster_test"
./venv/Scripts/python.exe -m pytest -q
```

Bash:

```bash
TEST_DATABASE_URL=postgresql://postgres:aster-test-only@127.0.0.1:55478/aster_test \
  python -m pytest -q
```

Frontend checks:

```bash
cd frontend
npm run build
npm run lint
```

### Live-model evaluation

The evaluation runner uses configured providers and consumes API quota:

```bash
pip install -r requirements-eval.txt
python -m src.eval.run_eval --suite intent
python -m src.eval.run_eval --suite guardrails
python -m src.eval.run_eval --suite tools
python -m src.eval.run_eval --suite rag
```

Latest final verification:

- **71/71** deterministic backend and PostgreSQL tests passed.
- **24/24** live intent cases passed, including off-topic, mixed-scope, consent,
  manufacturer/retailer ambiguity, order-note, and multi-action cases.
- Production WebSocket smoke tests passed for FAQ citations, tools, notes, simulated
  handoff, prompt injection, invalid frames, reconnect-safe IDs, and scope control.
- Frontend TypeScript/Vite build and lint passed.

Detailed evidence: [functional validation report](docs/reviews/functional-validation-2026-10-17.md).

## Production deployment

The live application runs on an **OCI Always Free A1** instance with **2 OCPUs, 12 GB
RAM, and a 45 GB boot volume**. Caddy terminates HTTPS using a publicly trusted,
automatically renewed Let's Encrypt IP certificate. PostgreSQL and Qdrant are private
Docker-network services with named volumes and no published host ports.

The stack is defined in [`deploy/compose.production.yml`](deploy/compose.production.yml):

- `aster-app` — FastAPI plus the compiled React SPA, internal port `8000`
- `aster-postgres` — PostgreSQL 17, internal port `5432`
- `aster-qdrant` — Qdrant 1.16, internal ports `6333/6334`
- shared Caddy gateway — public ports `80/443`, routing `/aster/`

Deployment order:

1. Copy secrets to `deploy/production.env` with mode `600`.
2. Start PostgreSQL and Qdrant.
3. Run the migration profile.
4. Publish a knowledge revision with the knowledge profile.
5. Start the application and verify `/health/live` and `/health/ready`.
6. Reload the shared Caddy configuration.

Read [the rollout guide](docs/operations/backend-rollout.md) before deploying schema or
knowledge changes. `deploy/backup.sh` creates compressed PostgreSQL backups and retains
14 days; production runs it daily through cron.

## API surface

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Create an account and revocable session |
| `POST` | `/api/auth/login` | Sign in |
| `POST` | `/api/auth/logout` | Revoke the session and close its sockets |
| `GET` | `/api/auth/me` | Return the current account |
| `GET/POST` | `/api/threads` | Paginate or create owned conversations |
| `GET/DELETE` | `/api/threads/{id}` | Read or delete an owned conversation |
| `GET` | `/api/threads/{id}/turns/{client_message_id}` | Recover authoritative turn status |
| `WS` | `/ws/chat/{thread_id}` | Authenticated durable chat |
| `WS` | `/ws/demo` | Anonymous ephemeral demo |
| `GET` | `/health/live` | Process liveness |
| `GET` | `/health/ready` | Dependency readiness |

In production these routes are mounted below `/aster/` by Caddy.

## Known boundary

Aster demonstrates the architecture and failure handling expected around support actions,
but its commerce records and handoff tickets are fixtures. Connecting real order, payment,
or support-desk systems would require provider-specific authorization, consent, delivery
acknowledgements, retries, reconciliation, and operational ownership. The UI and service
responses intentionally avoid claiming that those real-world actions occurred.

## Documentation

- [Product definition](PRODUCT.md)
- [Design system](DESIGN.md)
- [Backend rollout guide](docs/operations/backend-rollout.md)
- [Backend remediation status](docs/operations/backend-remediation-status.md)
- [Production review](docs/reviews/backend-production-review.md)
- [Functional validation](docs/reviews/functional-validation-2026-10-17.md)
