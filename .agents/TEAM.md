# Build-with-agents collaboration guide

These are **work roles and instructions** for AI coding assistants in future iterations, not evidence that independent hosted agents were deployed. One agent can assume a role at a time, submit a patch, and hand it off with evidence.

## 1. Architect Agent
Own `docs/ARCHITECTURE.md`, system boundaries, database migrations and design records. Do not change tenant scoping without tests. Deliver: decision, risks, migration plan.

## 2. Backend Agent
Own `opspilot/api.py`, `db.py`, `services.py`. Every query/mutation must explicitly constrain `org_id`. Deliver: typed routes, tests, negative isolation cases.

## 3. Integration Agent
Own `opspilot/connectors.py` and real provider adapters. Require reliable idempotency, pagination, rate-limit handling, credential rotation, cursor recovery, SSRF prevention. Deliver: provider sandbox test and failure matrix.

## 4. Agent Runtime Agent
Own `opspilot/agents.py`, `mcp_server.py`. Never dispatch arbitrary names to Python functions; use explicit registry only. Validate input schema, check identity and require human approval for mutations classified as high impact. Deliver: tool contract tests and prompt-injection red-team fixtures before adding LLMs.

## 5. Frontend Agent
Own `opspilot/static/`. Escape untrusted data, show loading/errors and never place API keys in URL query strings or persistent storage. Deliver: responsive and accessible UI, browser tests.

## 6. QA/Security Agent
Own `tests/` and threat analysis. Attempt cross-tenant reads, privilege escalation, request forgery, duplicate side effects, race conditions, CSV formula injection and excessive payloads. A patch is not complete without reproducing the failure first.

## 7. Release Agent
Own `Dockerfile`, `compose.yaml`, CI and release docs. Require `pytest`, source compilation and fresh install tests. Never expose demo mode outside loopback, commit keys or claim production readiness before pilot verification.

## Change handoff contract

Every agent turn hands off: **changed files**, **why**, **tests run**, **output**, **remaining risks**, **next patch**. Avoid "done" claims without output. Use small PRs and review each other's work. Real-world service credentials or deployments require the account owner to configure and authorize them.
