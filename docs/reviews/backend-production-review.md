> Remediation is implemented in the current working tree. See [rollout and remaining external requirements](../operations/backend-rollout.md). Findings below are the historical pre-fix assessment.

# Backend production readiness review

Reviewed 2026-10-15 against the current working tree, including the existing uncommitted backend work. This is a review, not a remediation release. Runtime backend files were not changed.

**Assessment: not ready for public production with real customer data or actions.** The architecture covers a useful demo, but several trust boundaries and durability guarantees are incomplete. Preserve the modular design; fix those boundaries before adding more agent autonomy.

## Scope and evidence

Reviewed the FastAPI entrypoint; authentication; WebSocket and thread routes; persistence and memory; planner and agent; MCP tools and mock backend; semantic cache; model gateway, guardrails, and vision; ingestion; evaluation; tracing; Python dependencies; Docker and Compose. Also checked frontend regeneration behavior where it affects backend correctness.

Local probes extracted the actual functions from source into isolated harnesses. They used synthetic files, an isolated SQLite database, fake model/cache/transport objects, and no real secrets. The full service was not started. No live provider calls, real customer records, production endpoint probes, database migrations, or container builds were performed. Provider availability, deployment proxy behavior, real concurrency performance, and restore procedures remain unverified.

Installed packages relevant to reproduction: bcrypt 5.0.0, FastAPI 0.139.2, Starlette 1.3.1, LiteLLM 1.91.4, llama-index-core 0.14.23, llama-index-tools-mcp 0.4.8. Most are not pinned in the deployment requirements, so a fresh build can differ.

Evidence:

- The exact SPA fallback served a synthetic private file outside the frontend directory with HTTP 200.
- An actual classifier failure returned `faq_lookup`; an account-tool response then reached `cache.set` in the exact `_run_turn` function with mocked dependencies.
- An order note could be retrieved solely by order ID without any actor identity.
- bcrypt rejected both a 73-character ASCII password and a 40-character password encoding to 80 bytes.
- Changing a forwarded-IP header allowed two requests from one synthetic peer through a one-request limit.
- Session creation omitted the Secure cookie attribute.
- Image validation accepted non-image bytes labeled image/png.
- Gateway construction included prompt_guard and vision models in ordinary answer-generation fallbacks.
- The regeneration deletion function removed an earlier assistant answer plus a pending user message, leaving an orphaned user message.

The original source-extraction probes were pre-fix diagnostics, not a production regression suite. Use `pytest -q tests` for the remediated implementation. The gateway and regeneration checks were additional isolated probes.

Severity: P0 is an immediate public-exposure blocker; P1 must be resolved before real customer traffic; P2 is operational hardening or capability work.

## Release blockers

### 1. P0: SPA file serving escapes its public directory

Evidence: `main.py:113` joins a user-controlled path to FRONTEND_DIST and calls is_file/FileResponse without verifying containment. The route exists when the frontend build is present. A locally encoded parent-directory request returned a synthetic file outside that directory. A deployment proxy may normalize some requests, but the application itself has no boundary.

Impact: readable application files, configuration, or local databases can become accessible without authentication. Secret exposure depends on which files exist in the deployed image.

Solution: serve assets through StaticFiles; explicitly allow public top-level files; use a tightly scoped index fallback. If resolving candidate files manually, resolve both root and candidate and reject any candidate outside the resolved root, including symlink escapes. Unknown API paths must return JSON 404 rather than SPA HTML/200. Add encoded-path and symlink regression tests.

### 2. P0 when built with local secrets: Docker copies .env into the runtime image

Evidence: `Dockerfile:20` uses COPY . /app; `.dockerignore` does not exclude .env or other secret files. A .env exists locally; its contents were not read during this review. Git ignore rules do not control a local Docker build context.

Impact: a local-context build can bake credentials into the image, compounding finding 1. This does not establish that a published image already contains secrets.

Solution: exclude .env, .env.*, credentials, local review output, and unnecessary source artifacts; allow a sanitized example file if needed. Prefer explicit runtime COPY paths and runtime secret injection. Use BuildKit secret mounts for any actual build-time secret. If an image was built and distributed with secrets, investigate exposure and rotate affected credentials.

### 3. P1: authentication does not reach order/refund/tool authorization

Evidence: `src/tools/mcp_server.py:35`, `:51`, `:63`, `:76` accept resource IDs and text, without authenticated actor context. `src/tools/mock_backend.py` tables contain no customer ownership. Both demo and authenticated chat use the same agent/tool configuration. Thread ownership checks protect transcripts, not the business resources referenced inside them.

Impact: callers can inspect and modify the shared demo resources, including notes visible to other conversations. Substituting real orders under this interface would create an authorization gap. Model instructions cannot repair it.

Solution: inject an immutable actor/tenant context from the authenticated server request, outside model-controlled arguments. Enforce resource ownership and action permissions inside the service executing every tool. Separate demo fixtures and mutation storage from real resources. Add user A versus user B and anonymous-versus-authenticated negative tests. Require confirmation where an action materially changes a customer resource.

### 4. P1: private or dynamic responses can enter the global semantic cache

Evidence: `src/agent/planner.py:70` treats classifier errors as faq_lookup. `src/api/chat_ws.py:226` uses that label for cache eligibility. Its cache write at `:341` does not check `called_tool`, despite tracking it. `src/gateway/cache.py:107` keys by query rather than actor, context, or data scope. A synthetic get_order_status answer was cached after a classifier failure in the local probe.

Impact: a later similar query can receive a previous account-specific answer. Even correctly classified FAQ follow-ups can depend on conversation context, making a query-only cache unsafe.

Solution: default to noncacheable on classifier failure. Allow shared cache writes only from a successful, explicitly public, context-independent FAQ pipeline; deny all account tools and mutations regardless of intent. Restrict cache reads before the agent using a deterministic public-query gate. Include knowledge/prompt/embedding versions and applicable locale/product filters. Do not solve private semantic caching merely by adding a user ID without also accounting for context and authorization changes.

### 5. P1: model fallbacks cross incompatible roles

Evidence: `src/gateway/llm_gateway.py:128` adds every other configured model as a fallback. The resulting generation fallback list includes the prompt-attack classifier and the vision model, as confirmed by local construction. Fallback entries also omit their own temperature, output-budget, and reasoning configuration.

Impact: a generation or tool-calling outage may route requests to the wrong task model or a local Ollama daemon unavailable in production. Actual provider behavior was not called or validated.

Solution: declare explicit fallback groups for answer generation, structured classification, tools, and vision. Validate model capabilities/configuration at startup. Apply each fallback's supported parameters. Use bounded retry budgets and circuit breakers; distinguish unavailable service from a valid classification or answer.

## Conversation correctness and data durability

### 6. P1: history and model memory have different sources of truth

Evidence: transcripts live in Postgres (`src/persistence/chat_store.py`), while model memory lives in `data/chat_memory.db` (`src/memory/persistent_memory.py:26`). Thread deletion and regeneration affect only the Postgres tables. Docker/Compose provides no app-memory persistence volume.

Impact: deleted or regenerated content can remain in model memory; a container replacement can erase memory while visible history survives. Reconnection can therefore show one history to the user and another to the agent.

Solution: make Postgres the canonical conversation record. Reconstruct the context window from ordered, committed turns; treat summaries/embeddings as versioned derivatives. Cascade deletion and retention to all derived stores. If keeping LlamaIndex SQL memory, use an explicitly managed shared store and synchronize deletion/regeneration rather than assuming its session ID solves consistency.

### 7. P1: regeneration deletes the wrong rows and is destructive before success

Evidence: `src/api/threads.py:66` takes only a thread ID; `src/persistence/chat_store.py:89` deletes the newest two rows without validating roles or a target turn. Frontend regeneration can be invoked for older assistant messages. The operation does not update model memory or preserve the old answer until a replacement succeeds.

Impact: regenerating an old answer can delete a newer exchange. A pending turn can make the deleted rows an unrelated assistant answer and the latest user question. Failed regeneration loses history, and replaying a mutation can duplicate its effects.

Solution: address an explicit assistant/turn ID. Create a new response version or branch linked to the original user message; retain the old answer. Regenerate read-only responses without replaying side-effecting tools. Update memory from the canonical selected version and serialize conflicting writes.

### 8. P1: done is sent before durable assistant persistence

Evidence: `src/api/chat_ws.py:153` explicitly treats assistant persistence as best-effort after delivery, including cache hits. Persistence exceptions are logged and suppressed. An agent failure can save a partial assistant answer and subsequently save a separate generic error answer.

Impact: an answer the user saw as complete can disappear on reload; turn shapes become inconsistent, undermining retries and regeneration.

Solution: create durable turns with pending/running/completed/failed status. Persist the final response before sending a committed completion acknowledgment. If optimistic token delivery is retained, distinguish final content from durable commit. Keep partial output and failure metadata under the same turn rather than inserting unrelated assistant rows. Add a transactional outbox only when there is an external delivery requirement.

### 9. P1: no idempotency, cross-connection serialization, or action ledger

Evidence: the WebSocket loop serializes one connection, but accepts multiple connections for one thread. Frames have no client message ID, turn ID, or retry key. Tool mutations simply insert notes and tickets.

Impact: multiple tabs or reconnect/retry can interleave context and duplicate escalations/notes. A client disconnect cannot establish whether an action already occurred.

Solution: assign client_message_id and server turn_id, enforce unique constraints, and serialize turns per conversation using a durable lease/queue or database lock appropriate to the execution model. Record tool-call IDs, validated arguments, actor, outcome, and idempotency keys. On reconnect return the authoritative turn state; do not rerun completed mutations.

## API, authentication, and resource controls

### 10. P1: registered users have effectively unlimited model spending

Evidence: only login, registration, and anonymous demo messages use the limiter. Authenticated chat has no per-user/day/token budget or global concurrency bound. The demo explicitly advertises signup for unlimited use (`src/api/demo_ws.py:49`). Connections allocate memory before any message throttle.

Impact: a small number of accounts or many idle connections can consume provider quota, RAM, and database connections. The agent iteration cap is not a service-level spending cap.

Solution: per-account and per-IP request quotas, token/image budgets, connection caps, a global work semaphore, bounded queues, and a daily spend ceiling. Reserve budget before work; reconcile actual usage afterward. Put anonymous traffic in a separate budget pool.

### 11. P1: spoofable/deployment-dependent and nonshared rate limiting

Evidence: `src/api/rate_limit.py:29` trusts the first X-Forwarded-For value unconditionally. The probe bypassed a one-request limit by changing that header. Whether a remote client can do so depends on proxy sanitization. Buckets are process-local and never remove old IP keys.

Solution: trust forwarded metadata only from configured proxies and document their overwrite/append behavior. Use Redis-backed expiring counters or an equivalent gateway control for shared quotas. Bound bucket storage and return useful retry timing. Add account-based controls as well as IP controls.

### 12. P1: WebSocket input and failure handling are incomplete

Evidence: chat/demo use receive_json followed by data.get/content.strip without a typed schema. Arrays, integers, malformed JSON, provider/embedding/cache failures outside the agent try-block, and DB failures can escape the route; only WebSocketDisconnect is caught. Text length validation occurs after the authenticated user message is persisted. No application turn deadline, idle deadline, or explicit cancellation policy is configured. Uvicorn/library defaults still apply, but are not an intentional product policy.

Solution: validate bounded frames before persistence, tracing, or vision calls; reject invalid types with a stable error envelope. Set explicit transport limits and bounded image payloads. Add a turn-level exception boundary, stage-specific deadlines, cancellation propagation, and clear terminal error states. Use the same turn/message IDs in status, token, error, and committed-done frames.

### 13. P1: session security is incomplete

Evidence: `src/api/auth.py:42` sets HttpOnly and SameSite=Lax but omits Secure. JWTs last 14 days. Logout deletes the browser cookie but does not revoke a token or terminate an existing socket; WebSockets authenticate only at connect. Neither WebSocket route validates Origin.

Solution: Secure cookies in HTTPS production, explicit trusted origins, session records or revocable token versions, expiration/revocation checks for active sockets, and close-on-logout. Add issuer/audience and required-claim validation if using JWTs across services; validate signing-secret strength at startup. Keep SameSite and apply CSRF/origin protection appropriate to cookie-authenticated mutations. Missing Origin validation is a defense gap, not proof that SameSite=Lax is bypassed cross-site.

### 14. P1: valid signup passwords can crash; signup hashing blocks the event loop

Evidence: registration accepts up to 128 characters (`src/api/auth.py:29`), while installed bcrypt 5 rejects inputs exceeding 72 UTF-8 bytes. Local probes reproduced the mismatch, including a shorter multibyte password. Login has unconstrained strings and can reach the same rejection for an existing account. `src/auth/store.py:51` calls hashpw synchronously inside an async request; verification is correctly offloaded.

Solution: immediately enforce compatible byte-length handling and catch expected validation failures; never silently truncate. Offload all password hashing through a bounded worker limiter. Prefer Argon2id for new hashes with verify-and-upgrade migration for existing bcrypt users. Add reset/recovery and session invalidation flows before serving real accounts. Account enumeration/timing protections and account-specific brute-force controls also need coverage.

## AI safety, knowledge, privacy, and actual features

### 15. P1: guardrails are not an authorization or output-safety boundary

Evidence: prompt checking fails open on provider error (`src/gateway/guardrails.py:83`); scan_bot_output returns text unchanged (`:126`). Agent tokens are delivered before that final scan. The claim that output only comes from controlled FAQ/fixed tools is incomplete: small talk can use model memory, and order notes are user-written. Images call a vision model before the input guard and are then flattened into text.

Solution: enforce business authorization and permitted actions independently of any classifier. Under guard-service failure, allow a safe read-only subset and disable sensitive mutations. Preserve untrusted-content provenance for retrieved text, notes, and photo descriptions; a vision description is not verified evidence. Validate outbound structures and URLs, minimize sensitive output, and choose either buffered review or a deliberate streaming-safety design. A no-op final scanner cannot protect already-emitted tokens.

### 16. P1: demo privacy promises exceed what the backend guarantees

Evidence: persist=False skips transcript writes, but still calls shared mutating tools, semantic cache, logs, and optional Langfuse tracing. `_handle_turn` traces raw input and tags username/session; query snippets are logged in chat/cache/guardrails. Demo-created order notes and tickets are written to SQLite. Thus ephemeral conversation memory does not mean no persistent side effects or third-party processing.

Solution: isolate demo tool storage; reset or expire fixture mutations. Disable or redact demo content tracing and define retention for logs, cache, notes, and uploaded data. Give users accurate, narrow privacy copy. Use pseudonymous trace identifiers, remove raw content by default, and implement deletion across data stores. This is an engineering/data-handling gap, not a legal-compliance determination.

### 17. P1: ingestion leaves obsolete policy chunks searchable

Evidence: `src/ingestion/embed_qdrant.py:114` assigns IDs from chunk text and upserts current nodes, but never removes chunks no longer in the source. Its content fingerprint is printed rather than becoming an active knowledge version. Runtime and response-cache versions are not tied to document publication.

Impact: changed or withdrawn policies can coexist with old chunks and old cached answers.

Solution: stable source IDs, source revision/effective dates, chunk manifests, reconciliation of removed nodes, and versioned collections with an atomic active-version switch. Invalidate cache by knowledge version. Validate collection dimension and embedding-model identity at startup and ingestion. Separate ingestion dependencies from the lean serving image; ingestion currently always builds sparse embeddings even when runtime uses Cohere dense-only retrieval.

### 18. P1: no explicit evidence gate, citations, or insufficient-information contract

Evidence: `src/agent/chat_agent.py:139` reranks and synthesizes retrieved text; the prompt asks for grounded answers, but there is no explicit evidence sufficiency gate or structured citation payload. `_CachedQueryEngineTool` converts the result to plain text and the WS schema exposes no source metadata. Prompt guidance alone cannot establish answer grounding.

Solution: return an answer plus source IDs, document revisions, page/section references, and a supportability status. Calibrate a no-answer decision using evaluations rather than treating similarity scores as probabilities. Request missing product/order details; route unresolved cases to a real handoff. Add adversarial, conflicting-policy, stale-policy, and multilingual cases relevant to the intended audience.

### 19. P1 for a real support launch: escalation and commerce integration remain demonstrations

Evidence: order/refund records are seeded SQLite fixtures; escalations create local rows and return a promise that a human will follow up (`src/tools/mcp_server.py:84`). No worker or external support system consumes those tickets. A one-tool-per-message system prompt also prevents many compound workflows, and current-message-only tool rules can mishandle an ID supplied in a follow-up reply.

Solution: keep demo responses explicitly marked simulated until real integrations exist. Add an owned case lifecycle, customer/contact linkage, delivery acknowledgment to a real support queue, status/resolution tracking, and retry/dead-letter handling. Use validated structured conversation state to resolve follow-ups and authorize bounded multistep plans. Let the model propose actions; let server policy execute them.

### 20. P2: vision is only partially validated and not integrated into the UI

Evidence: `src/gateway/vision.py:59` checks MIME label, encoded length, and base64 syntax; non-image bytes labeled PNG passed locally. The 4 MiB cap is on encoded data, so it corresponds to about 3 MiB of decoded bytes. The current frontend composer sends text only. Photo descriptions/attachments have no durable transcript representation or provenance.

Solution: bounded decoding; file-signature, dimension, and pixel-count checks; strip metadata where appropriate; restricted storage and expiry; independent vision budget/deadline. Decide whether the product supports attachments, then implement the frontend and an auditable attachment reference. On vision failure explicitly state that the image was not analyzed instead of silently continuing as if it was.

## Reliability, operations, and quality gates

### 21. P1: optional cache failures can terminate a chat turn

Evidence: embedding, cache.get, cache-hit memory writes, and cache.set in `_run_turn` are not inside a recovery boundary. A cache write after completion can close the socket even after the user received an answer. Cache lookup retrieves one hit before checking version/expiry, so an invalid nearest hit can hide a valid second hit. Old cache points are not removed merely because TTL checks reject them.

Solution: fail cache reads/writes open to the noncached FAQ pipeline, with bounded deadlines and circuit-breaker metrics. Filter version/expiry in Qdrant or examine multiple candidates; garbage-collect expired records. Include embedding/knowledge identity in collection metadata and validate schema rather than only checking collection existence.

### 22. P2: database and tool lifecycle impose avoidable overhead

Evidence: auth and chat-store methods call asyncpg.connect per operation. Listing returns all threads/messages without pagination. Memory creates SQL-backed objects per socket without explicit lifecycle cleanup in the route. In the installed llama-index-tools-mcp client, every call_tool/list_tools creates a session and stdio subprocess; the app uses BasicMCPClient this way. This is source-confirmed overhead, not a latency benchmark.

Solution: one bounded asyncpg pool per process, statement/connect timeouts, cursor pagination, explicit shared engine/client lifecycles, and indexed ordered message access. Use a managed long-lived MCP session or authenticated service transport, retaining MCP if interoperability is a product requirement. For this small monolith, typed in-process services can also be simpler; benchmark before choosing.

### 23. P1: deployment and recovery contracts are incomplete

Evidence: `main.py:56` initializes dependencies but has no shutdown cleanup after yield or independent liveness/readiness endpoints. Schema setup is manual SQL without migrations. The image runs as root, retains build tooling, uses a shell-form uvicorn command, and has no application healthcheck. Compose starts only Qdrant, with published ports and no authentication in that local configuration. Dependency ranges are largely unpinned; runtime requirements also include evaluation tooling.

Solution: validated typed settings, pooled resources created/closed in lifespan, liveness plus dependency readiness, proper SIGTERM delivery via exec, nonroot minimal runtime, locked/hashes-reviewed Python dependencies, separate development/evaluation groups, automated migrations, backups, and tested restores. Keep Compose explicitly development-only or secure/private its Qdrant ports. Externalize SQLite state before replicas or ephemeral hosting. Do not assume more workers solve these state and quota issues; the shared FunctionAgent alone is not evidence of a concurrency defect.

### 24. P1: evaluation does not establish production behavior

Evidence: no backend API/integration test directory or CI workflow was found. There is a useful live-model evaluation runner with real failure thresholds, but it always installs/uses FastEmbed and hybrid retrieval (`src/eval/run_eval.py:116`, `:316`) while the Cohere production path uses a different embedding model/dimension and dense-only retrieval. The tool suite uses Settings.llm rather than the configured production tool-calling model, checks the first tool name and loose answer substrings, and can mutate the same mock tool database. Red-team expectations cover output redaction although scan_bot_output is a no-op.

Solution: deterministic unit/API/WebSocket security tests for these findings; integration tests with isolated Postgres/Qdrant/tool fixtures; failure/cancellation/reconnect and concurrent-tab tests; dependency/container checks; CI quality gates. Make live-model eval use exactly the deployed embedding/retrieval/model configuration and isolated data. Assert tool arguments, ownership, side effects, all tool calls, and idempotency, not just the first tool name. Keep live RAG/agent evaluation as an additional scheduled/release gate; record model, prompt, dataset, and knowledge versions. Measure p50/p95 stage latency, time to first answer, completed/committed turns, reconnect failures, cost per resolved case, and action failures. Current tracing scores and artificial word pacing are not those service guarantees.

## Recommended target and delivery order

Keep a modular FastAPI application initially. Separate transport from a reusable conversation service, then give that service typed boundaries for identity/policy, turn storage, knowledge retrieval, and tool execution. A generic chat controller should not own persistence, tracing, image processing, cache policy, and agent lifecycle in one function.

A production turn should follow this sequence:

1. Validate session/origin, frame size/schema, identity, quotas, and message idempotency.
2. Create a durable turn and serialize it within its conversation.
3. Retrieve committed context and validate resource references against the actor.
4. Route a public FAQ read or a bounded authorized tool plan. Sensitive writes require policy approval and, when appropriate, user confirmation.
5. Preserve evidence, action results, errors, and data provenance as structured records.
6. Persist the final answer/version, then send a completion event carrying its durable ID.
7. Cache only explicitly public/context-independent results and emit redacted telemetry.

Use Postgres for accounts, sessions, conversations, turns, action ledger, cases, and ingestion manifests; Qdrant for versioned public knowledge and eligible public cache. Introduce Redis for shared quotas, short-lived locks/leases, and budgets when running multiple instances. Introduce an outbox/worker for actual support handoff and other durable external effects. Avoid a microservice split until traffic or organizational ownership warrants it.

Delivery order:

- **Contain exposure first:** findings 1–5; isolate/disable shared demo mutations; add exact regression tests. Audit published images if local secrets were included.
- **Establish correctness:** canonical memory/history, nondestructive regeneration, committed turn semantics, idempotency, action authorization, and concurrency control.
- **Bound operations:** schema/frame validation, auth/session controls, password handling, quotas, pooling, deadlines, cache degradation, and resource cleanup.
- **Make support trustworthy:** versioned knowledge, citations and no-answer behavior, real case handoff, accurate privacy/feature claims, and attachment completion if retained.
- **Gate the release:** deployed-configuration evaluations, CI integration/security tests, load tests with real latency/cost measurements, and a backup/restore plus rollout/rollback rehearsal.

Do not start with a provider/model switch or more elaborate agent prompting: neither addresses the confirmed security and state-integrity defects.

## Existing strengths to preserve

Parameterized SQL; ownership-scoped thread lookups/deletion; insert-only public registration protected by a unique constraint; bcrypt verification off the event loop; HttpOnly/SameSite cookies; per-call memory passed to the agent; context-local embedding reuse; image-enriched cache exclusion; cache versioning; and evaluation thresholds that return nonzero on failure. These are useful foundations, but do not extend automatically to business-resource authorization or conversation durability.

## Primary references

These support the remediation principles; project findings above come from local code and probes.

- [OWASP WebSocket Security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): origin/session validation, message authorization and resource controls.
- [OWASP Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): authorization must apply to resource access, independently of interface visibility.
- [Docker build context](https://docs.docker.com/build/concepts/context/): COPY uses the build context and .dockerignore excludes content.
- [bcrypt project](https://pypi.org/project/bcrypt/): current long-password behavior and byte limit.
- [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): Argon2id and legacy bcrypt input handling.
