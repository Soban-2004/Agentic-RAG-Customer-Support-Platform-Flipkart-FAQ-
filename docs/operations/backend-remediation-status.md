# Backend remediation status

Implemented 2026-10-15. Numbers correspond to the historical [production review](../reviews/backend-production-review.md). Deployment steps and limitations are in the [rollout guide](backend-rollout.md).

| Findings | Changes | Remaining deployment or integration work |
| --- | --- | --- |
| 1-2: file exposure and image secrets | Contained public-file serving, explicit Docker copies, secret exclusions, nonroot runtime | Assess old images/logs and rotate any exposed credentials |
| 3: tool authorization | Trusted server context; actor-scoped demo notes/actions; session and thread checks; anonymous isolation | Real commerce adapter must verify resource ownership against its source of truth |
| 4, 21: cache privacy and outages | Default off; closed public-query allowlist; stateless FAQ synthesis; exact topic/revision/TTL filtering; bounded fail-open behavior | Explicitly retire legacy private cache data |
| 5: model routing | Role-specific fallback groups, timeouts and bounded agent iterations | Verify availability and answer quality with actual providers |
| 6-9: memory, regeneration and durability | Canonical Postgres memory with provenance, atomic commits, commit-before-done, request fingerprints, advisory locks, action ledger and safe regeneration | Investigate interrupted actions deliberately; do not replay failed requests blindly |
| 10-12: spending, quotas and transport | Shared Postgres request/token reservations, concurrency caps, strict frames, deadlines, bounded uploads and terminal errors | Configure billing caps and test cluster capacity/proxy settings |
| 13-14: sessions and passwords | Revocable sessions, exact origin checks, secure production cookies, immediate local logout closure, Argon2id offload and bounded legacy bcrypt migration | Verified self-service recovery needs an identity/delivery provider; secure admin reset is available |
| 15-16: guardrails and privacy | Fail-closed input checking, output filtering, tracing off by default, ephemeral demo state | Provider privacy/retention review and real adversarial evaluations |
| 17-18: knowledge and evidence | Immutable full snapshots and atomic alias publication; embedding compatibility checks; evidence gate and citations | Reingest knowledge and calibrate relevance on the actual corpus |
| 19: business and human support | Explicit simulation labels, disabled unsupported backend selection, no false human-notification claim | Real commerce and support-desk integration remain required |
| 20: photos | Verified format/size/pixel bounds, provider deadline, frontend upload and disclosure | Live vision evaluation and provider privacy configuration |
| 22: lifecycle | Bounded connection pools, shutdown cleanup, in-process typed tool adapters | Production load testing |
| 23: deployment and recovery | Versioned migrations, readiness, validated settings, hashed Linux dependency lock, hardened Docker, retention CLI and recovery instructions | Managed backups/PITR, monitoring, restore rehearsal and deployment secrets |
| 24: evaluation | Regression suite and CI; live evaluation uses serving knowledge/model configuration and isolated tool context | Paid provider evaluations and deployed smoke tests were not run |

These changes harden the application; they do not certify real customer commerce or external service behavior. Existing customer databases and provider services were not modified during implementation.
