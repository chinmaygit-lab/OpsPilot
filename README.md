# OpsPilot — Agent Operations Control Plane

> A working, independent **AI-native operations platform foundation** inspired by the engineering capabilities described in the public Mercor *Software Engineer (AI-Native Platform & Integrations)* role. **Not Mercor's application, internal code, or an authorized client deliverable.**

[![Tests](https://img.shields.io/badge/tests-16%20passing-198754)](#verification) [![Python](https://img.shields.io/badge/python-3.11%2B-blue)](#run-it) [![Stage](https://img.shields.io/badge/stage-tested%20local%20MVP-orange)](#what-is-built)

## What is built

- **Multi-tenant core**: tenant-scoped tasks, event streams, integrations, approval records and audit events in SQLite. Three roles: `viewer`, `editor`, `owner`. API keys stored as SHA-256 hashes, not plaintext.
- **Spreadsheet replacement entrypoint**: CSV-import connector with UTF-8 validation, row preflight, per-source external IDs, deduplication and tenant-scoped exports that neutralize spreadsheet formulas.
- **Connector framework**: a swappable `MockTicketConnector` with bounded pagination, cursor checkpointing and retry-safe deduplication. Demo data contains five tickets of various severities.
- **Signed webhook intake**: HMAC-SHA256 verification with per-integration derived keys and an idempotent event ID. A triage agent turns each novel event into a task.
- **Agent collaboration**: an `InsightAgent`, a bounded `PlannerAgent`, a permission-enforcing tool executor, and a severity-based `TriageAgent`. All are deterministic in this MVP: **no paid LLM calls and no pretense of generative AI**.
- **MCP integration**: optional local **official MCP Python SDK v2 stdio server** with registered tools scoped by `OPSPILOT_MCP_KEY`. *The MCP runtime requires the optional `mcp` package; the current automated tests verify the REST registry/tool layer, not live MCP client interoperability.*
- **Live web dashboard**: responsive, branded HTML/CSS/JS UI, in-app connection, current work queue, approvals, task export, connector controls, and server-pushed WebSocket snapshots every two seconds.
- **Governance**: JSON Schema argument validation; role checks; explicit human approval before task completion; bounded execution; tool invocation audit logs, including permission denials.
- **Engineering**: pytest suite, GitHub Actions, Dockerfile, localhost-only demo Compose file, explicit security/pilot checklist, and architecture docs.

### What this MVP deliberately does **not** claim

- No live Slack, Salesforce, Google or other OAuth2 provider account integration; OAuth2/PKCE and provider-specific token refresh are **next-stage** work.
- Not a horizontally scalable, fully production-hardened SaaS: SQLite single-writer, short-lived WebSocket state, no Redis/job queue, no PostgreSQL migrations, no distributed tracing or HA.
- Not a generative-LLM autonomous worker: the first agent pipeline is deterministic, bounded and independently testable. A model can later propose actions through the same registry/approval checks.
- No real enterprise authentication/SSO, metering, paid hosting, on-call rotation or live-user pilot completed.

## Run it

### Python development (Windows PowerShell)

```powershell
cd opspilot_agent_platform
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:DEMO_MODE = "1"
uvicorn opspilot.api:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Connect with `demo-acme-owner`. For isolation, use `demo-nova-owner`; for restricted access, use `demo-acme-viewer`.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
DEMO_MODE=1 uvicorn opspilot.api:app --host 127.0.0.1 --port 8000
```

### Docker Compose (local development only)

```bash
docker compose up --build
```

Open http://localhost:8000. Compose binds **127.0.0.1** and enables insecure **demo accounts**. Never expose it to a network or cloud with demo mode enabled.

## Guided walkthrough

1. Connect using `demo-acme-owner`. The dashboard will initialize live metrics.
2. In **Integrations**, choose **+ Demo connector** and **Sync now**. Five source events become five work items and the cursor reaches 5. Re-sync adds zero duplicates.
3. Create a task directly in the **Work queue**. Use **Request completion**, then visit **Approvals & audit** to approve or reject it. Completion does not occur before approval.
4. Choose **+ CSV source**, then **Import CSV**, selecting [`samples/spreadsheet_tasks.csv`](samples/spreadsheet_tasks.csv). Importing again is deduplicated.
5. Run the **agent team** with objective `Summarize current operations`. Inspect the Insight Agent findings, the Planner's limited plan, and the Tool Executor results.
6. Switch to `demo-nova-owner`. Acme tasks, analytics, integrations and approvals should **not** appear; this isolation is tested.
7. API docs: `http://127.0.0.1:8000/docs`.

## REST example

```bash
curl -H "X-API-Key: demo-acme-owner" http://127.0.0.1:8000/api/summary

curl -X POST http://127.0.0.1:8000/api/integrations \
  -H 'X-API-Key: demo-acme-owner' -H 'Content-Type: application/json' \
  -d '{"name":"Demo CRM","kind":"mock_tickets"}'

curl -X POST http://127.0.0.1:8000/api/agent/run \
  -H 'X-API-Key: demo-acme-owner' -H 'Content-Type: application/json' \
  -d '{"objective":"Summarize my open tasks"}'
```

To generate the webhook signature, see [`scripts/send_webhook.py`](scripts/send_webhook.py). Webhooks require `WEBHOOK_SIGNING_SECRET` when not in demo mode.

## MCP server (optional)

```bash
pip install -e '.[mcp]'
# Windows PowerShell (after demo DB has been initialized by launching the app):
$env:DATABASE_PATH = "data/opspilot.db"
$env:OPSPILOT_MCP_KEY = "demo-acme-owner"
python -m opspilot.mcp_server
```

Configure an MCP host to launch `python -m opspilot.mcp_server` with those environment variables. It exposes `list_tasks`, `analytics_summary`, `create_task`, and `request_task_completion` tools. **Use a private key and never expose this stdio server as a public unauthenticated network endpoint.** See [MCP v2 documentation](https://py.sdk.modelcontextprotocol.io/).

## Non-demo / provisioning

For an initial local key, use `python -m opspilot.manage --org company-x --org-name "Company X" --user admin --role owner`, then start with `DEMO_MODE=0`. The CLI prints a random key once and stores only its digest. Repeating with a new user adds that principal. With no demo or provisioned key, endpoints correctly reject all authenticated API requests.

For non-demo webhooks, set a long random `WEBHOOK_SIGNING_SECRET` (do not commit it) and follow the sender example. HTTPS, stronger credential hashing/HMAC pepper, key rotation and enterprise identity must be added before real production traffic.

## Tests and verification

```bash
python -m pytest -q
python -m compileall -q opspilot
```

The test suite covers isolated tenants, role enforcement, schema rejection, approvals, audit records, repeated event ingestion, signed/unsigned webhooks, pagination checkpoints, CSV import/export safety, agent team execution, and WebSocket snapshots. A locally verified run on **29 October 2026** passed all 16 tests. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/PILOT_CHECKLIST.md`](docs/PILOT_CHECKLIST.md).

## Repository map

```text
opspilot/
  api.py           FastAPI + live WebSocket API
  db.py            schema and tenant/key persistence
  services.py      task/event/analytics and triage agent
  connectors.py    connector registry, paginated sync, CSV import
  agents.py        tool registry, Insight/Planner agents, approval flow
  mcp_server.py    optional MCP v2 stdio adapter
  manage.py        tenant/key bootstrap CLI
  static/          no-build dashboard
samples/           example input spreadsheet
scripts/           webhook demonstration
tests/             isolated logic and HTTP API tests
docs/              design, pilot-hardening steps
.agents/           development agent work instructions
```

## Licensing and ethics

This repository is **MIT licensed**. It demonstrates competencies that appear in a publicly posted job description. Use it as an original portfolio project, and do not represent it as a Mercor client project or as proof of live production ownership.
