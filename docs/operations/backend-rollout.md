# Backend hardening rollout

This change fixes the confirmed code defects and adds bounded transport, durable turns, actor-scoped simulation tools, versioned knowledge, tests, and CI. It does not turn fixture commerce data into a real integration or certify the deployed environment.

## Rollout order

1. Back up the existing Postgres database and verify a restore in a disposable database. Take a Qdrant snapshot/record the old physical collection and alias. Preserve the old image for rollback; do not export secrets into it.
2. Install serving dependencies from `requirements.lock.txt` in Linux/Python 3.12. The lock includes hashes. `requirements.txt` pins direct dependencies for local development; `requirements-eval.txt` contains the additional live-evaluation dependency. Local embedding fallback packages remain development-only.
3. Run `python -m src.persistence.migrate` using the target DATABASE_URL. This adds tables/columns transactionally and records a migration version; it does not delete existing history. The server requires this migration before starting. No application database migration was applied by the agent; integration tests used a disposable local container.
4. In an ingestion environment, run `python -m src.ingestion.embed_qdrant`. It creates an immutable complete snapshot and atomically publishes KNOWLEDGE_ALIAS, default `flipkart_faqs_live`. It never deletes the old collection. A legacy collection with a conflicting alias name is rejected. Use the same embedding configuration as serving. The server pins the physical revision at startup and checks dimensions/model identity.
5. Configure the settings below, rebuild the image, and roll out the API and frontend together. Clients now send unique client_message_id values and explicit regeneration targets. Old clients receive validation errors. Existing JWTs require a new login because sessions are now revocable database records.
6. Check `/health/live` and `/health/ready`; then smoke-test registration/login/logout, an FAQ with citations, reconnect/history, a simulated action, and a real provider outage. Run `pytest -q tests` against a disposable database and live evaluations against isolated fixtures using the deployed configuration.
7. Configure provider-side billing limits and alerts, external monitoring, HTTPS termination, backups, restore rehearsal, and a retention schedule. Request reservations are conservative admission controls, not exact provider billing. Calibrate FAQ_MIN_RELEVANCE_SCORE with the real corpus before claiming answer-quality guarantees.

If rollback is needed, keep the additive migration and previous collections; switch the alias back to a known revision and restart compatible serving processes. Restore backups only under a separate recovery procedure. Old clients are incompatible with the new transport, and legacy images have the reviewed security defects: do not re-expose a vulnerable image publicly as a routine rollback.

## Configuration

- `APP_ENV=production` enables secure session cookies and shared Postgres quotas. JWT_SECRET must be at least 32 characters. Set DATABASE_URL, CHATGROQ_API_KEY, COHERE_API_KEY, and remote QDRANT_URL/QDRANT_API_KEY as runtime secrets.
- `TRUSTED_ORIGINS=https://your-host.example` is an exact comma-separated HTTPS allowlist. Configure `FORWARDED_ALLOW_IPS` for the actual reverse proxy addresses; application code ignores raw X-Forwarded-For. Never use a wildcard trust setting on an exposed server.
- `BUSINESS_BACKEND=demo` is the only implemented adapter. Any other value fails startup. All order/refund records are labeled examples; authenticated simulation notes/actions are actor-scoped; anonymous mutations are memory-only. No human is notified by a simulation ticket.
- `AGENT_TOOL_CALL_MODEL_KEY` defaults to `fallback` in production, avoiding a missing local Ollama daemon. Its fallback list is explicit and excludes guard/vision models.
- `DB_POOL_SIZE=12`, `MAX_CONCURRENT_TURNS=4`; pool size must be at least twice the turn concurrency plus two. Conversation leases use transaction-scoped PostgreSQL advisory locks, including through transaction-pooling proxies.
- `CHAT_PER_HOUR=60`, `DAILY_TURN_LIMIT=500`, `DAILY_RESERVED_TOKEN_LIMIT=10000000`, `ACCOUNT_DAILY_RESERVED_TOKEN_LIMIT=2000000`. Each new turn conservatively reserves 100,000 units without refunds; duplicate committed messages bypass work reservations. Image requests also have a per-actor daily cap. These are safe initial bounds to calibrate, not usage-price claims.
- `TURN_TIMEOUT_SECONDS=90`, `WS_IDLE_TIMEOUT_SECONDS=300`, `MAX_CONNECTIONS=50`, `MAX_FRAME_BYTES=6000000`. Active socket/concurrent-work caps are per process; request/work quotas are shared in Postgres. Test total cluster capacity before adding replicas.
- `ENABLE_SHARED_FAQ_CACHE=false` by default. Opt-in caching accepts only explicitly allowlisted public policy templates classified as FAQ and executes a stateless FAQ engine, never the account agent. Cache entries are scoped to the pinned knowledge revision and an exact public topic, preventing semantic matches across different policies. Old response_cache data is not read; securely retire any legacy cache containing customer data using an explicit operational data-deletion procedure.
- `ENABLE_CONTENT_TRACING=false` by default even when Langfuse keys exist. Turning it on sends content-bearing instrumentation to the tracing service; configure retention/redaction/consent before doing so. Production startup requires ENABLE_DEMO=false before it can be enabled; public-demo handshakes then fail closed.

## Durability and recovery semantics

Postgres messages are the canonical history; model memory is rebuilt from the latest committed records. Old SQLite model memory is not read. Pre-migration messages and blocked/unverified turns remain visible in history but are excluded from model context because they lack safe-memory provenance. Keep any legacy SQLite files protected and retire them under the data-retention policy; the change intentionally does not silently delete existing local data.

A message ID binds the question, image digest, and regeneration target. Completed duplicates replay the committed response. Running/failed attempts are never automatically rerun because a tool action might already exist. Reload history and start a deliberate new request when appropriate. A transport disconnect can occur after commit: completion state in Postgres, rather than the last browser event, is authoritative.

Regeneration supports only the latest assistant response without recorded mutations. It preserves the prior answer as a superseded version and commits a replacement atomically. The old destructive preparation endpoint returns a conflict. Earlier/mutating answers require a new user question.

Original uploaded photos are intentionally not stored. The message fingerprint includes image content for idempotency; the reply/history contains the result. Images are verified for type, decoded size, and pixel bounds before provider calls. Photo descriptions remain unverified user-supplied evidence. Photos go to the configured vision provider, as disclosed in the composer.

## Retention, backup, and production integrations

Review a dry run with `python -m src.persistence.maintenance --days 90`; schedule `--apply` only after choosing the actual retention period. It cleans expired sessions/quotas and eligible inactive conversation trees, cascading to versions and actor actions. It skips running turns and leases candidate threads. Investigate crash-left running turns explicitly; never blindly replay their actions.

Use managed Postgres backups/PITR and Qdrant snapshots according to the host. For manual drills, use pg_dump against a nonproduction source copy and restore into a fresh isolated database; verify accounts, thread ordering, turn/action records, and the active knowledge revision. Backup encryption, access policy, recovery objectives, and automatic restore testing are deployment responsibilities, not validated merely by writing a command.

Before real customer use, implement a commerce adapter with verified identity/resource ownership and a real support-desk outbox/worker, recipient/contact verification, delivery acknowledgment, retries, and case status. The standalone MCP fixture server is read-only; the web agent now uses typed, trusted-context service adapters to prevent identity from being supplied by the model. A remote MCP connector must preserve the same authorization and idempotency boundary.

Self-service account recovery needs a verified delivery/identity provider; this change does not invent an email-reset channel for username-only accounts. Administrative password changes revoke existing sessions. Rotate any secrets previously distributed in images or exposed through the old static route, and assess existing logs/traces for sensitive data.

## Validation performed

On 2026-10-15, all 56 regression tests passed both locally and in the final Linux/Python 3.12 Docker image using disposable Postgres 17. The image built successfully and passed application-import, nonroot-user, and runtime .env-exclusion smoke checks. Frontend production build and lint completed successfully, with existing bundle-size and useAuth fast-refresh warnings. Python safety checks and git diff whitespace checks passed. CI was added; the hosted workflow has not yet run. See the [finding-by-finding status](backend-remediation-status.md). Tests exercise public-file containment, typed frames, long Unicode passwords/legacy bcrypt behavior, origins, quotas, guard outages, output filtering, real image validation, cache scoping/failover, immutable alias publication, actor-isolated notes, and real Postgres session/turn/WebSocket behavior. No paid model inference or deployed-environment certification is implied.
