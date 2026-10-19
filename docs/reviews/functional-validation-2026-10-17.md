# Functional validation — 2026-10-17 to 2026-10-18

## Scope

This pass covered message boundaries, support-scope enforcement, FAQ retrieval,
order and refund tools, notes, handoff behavior, authentication, authorization,
thread ownership, persistence, retries, regeneration, rate limits, retention,
guardrails, cache isolation, WebSocket framing, and production health.

## Defects fixed

| Defect | Resolution |
| --- | --- |
| Unrelated questions reached the general-purpose model and received answers | Added an explicit `out_of_scope` intent and a deterministic scope response that never invokes the agent |
| Greetings and broad `general_chat` classifications could invoke the general-purpose model | General chat now returns a bounded capability response without invoking the agent |
| Classifier outages could fall into a generative route | Classification now fails closed to `out_of_scope` |
| Other-retailer questions could be mistaken for store FAQ questions | Strengthened the intent contract and added model-evaluation cases |
| Unknown but supplied order/refund IDs could cause the assistant to request the ID again | The agent now sends candidate IDs to the validating tool, which returns a clear not-found result |
| Questions about another retailer could be mistaken for supported store policy | Expanded the scope contract for named retailers while preserving support for product/manufacturer brands |
| A mixed support and off-topic request could pass through on its supported half | Any message containing an out-of-scope requested task now fails closed as a whole |
| Frustration alone could be interpreted as consent to create a handoff | Handoff now requires an explicit request to speak to, connect to, or notify a human |
| Natural-language order-note requests could be rejected as unrelated | Added an explicit `order_note` intent |
| Two account actions in one message could result in an ambiguous partial action | Added a deterministic `multi_action` route that asks for one action at a time and calls no tool |
| Pytest failed to parse `pytest.ini` because of a UTF-8 BOM | Recreated the configuration without the BOM |
| Pytest collected a Selenium scraper utility outside the application test suite | Restricted collection to `tests/` |
| PostgreSQL integration tests depended on one Windows ephemeral port | Test safety now requires a localhost, nondefault port and the dedicated `aster_test` database without hard-coding a port |

## Automated evidence

| Suite | Result |
| --- | --- |
| Full service suite with disposable PostgreSQL | 71 passed |
| Current scope, boundary, knowledge, and tool regression suite | 57 passed |
| Live LLM intent matrix | 24/24 passed |
| Python compile check | Passed |
| Ruff import/error checks | Passed |
| Frontend TypeScript and Vite production build | Passed |

The full PostgreSQL suite verifies session revocation, cross-account thread
isolation, atomic turn commits, idempotent replay, nondestructive regeneration,
conversation leases, account-scoped tool actions, shared quotas, WebSocket
reconnect behavior, retention, password reset, memory exclusion, commit failure,
timeouts, and capacity release.

## Production smoke evidence

The public deployment at `/aster/` passed:

- readiness through Caddy;
- malformed WebSocket frame rejection;
- cricket and other-retailer scope rejection;
- bounded greeting response;
- grounded FAQ answer with sources;
- valid order and refund fixture lookup;
- missing-ID guidance;
- prompt-injection rejection;
- session-local note write and readback;
- truthful simulated handoff disclosure;
- unknown order lookup with a clear not-found result;
- named other-retailer rejection;
- mixed support/off-topic rejection;
- frustration without unintended handoff creation;
- natural-language order-note routing;
- multi-action rejection before tool execution.

All three production containers were healthy after deployment, and the app log
contained no errors, exceptions, tracebacks, or failed operations during the
verification window.

## Product boundary

Order status, refund status, notes, and handoff remain clearly labeled
demonstrations. The application is not connected to a live commerce backend or
support desk. Production claims must continue to describe these actions as
simulated until real integrations replace the fixture services.
