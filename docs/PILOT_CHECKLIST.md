# From local MVP to a genuine pilot

This checklist deliberately distinguishes **implemented**, **locally verified**, and **not implemented**.

| Milestone | Status | Acceptance bar |
| --- | --- | --- |
| Typed REST APIs | Implemented/tested | Tasks, metrics, integrations and agent endpoints return tenant-isolated results |
| Role-based access control | Implemented/tested | Viewer/editor/owner; denial logged for agent tool actions |
| Signed webhooks | Implemented/tested | Invalid HMAC denied; same external ID is not processed twice |
| Connector sync | Implemented/tested | Mock pages, cursor checkpoints and replay-safe ingestion |
| Spreadsheet migration | Implemented/tested | 1000-row cap, validation, deduplication and CSV export |
| Agent approval flow | Implemented/tested | Task completion is pending until owner approves it |
| Real-time UI | Implemented/tested via WebSocket test | WebSocket emits scoped snapshots; no load testing |
| Official MCP stdio integration | Implemented; optional, not live-interoperability tested | Test with SDK v2 and host inspector |
| Real OAuth2 vendors | Not implemented | Vendor sandbox with PKCE, refresh, scopes and rotation |
| Multi-tenant PostgreSQL and RLS | Not implemented | Migrations, negative isolation tests at DB level |
| Durable scheduler / retries | Not implemented | Queue, dead letters, poison event handling and recovery |
| Observability | Basic audit only | OTel traces, logs, metrics, dashboards and alert thresholds |
| Production security | Not complete | Threat model review, key rotation, SSO, CSRF, rate limits, TLS |
| End-user pilot | Not started | Scoped users, consent, rollback, telemetry and success criteria |

## Suggested pilot acceptance metrics

- Cross-tenant data leakage: 0 in automated denial/isolation suite.
- Event replay processing: 0 duplicate tasks with stable external IDs.
- CSV import: deterministic mapping and visible rejected-row feedback.
- Agent safety: 100% of task completion requests routed through owner approval.
- Integration health: age of latest checkpoint and failed-provider request rate.
- Dashboard freshness: measure p95 event-to-render delay after production queue introduction; do not infer it from a 2-second refresh interval.

## Security prerequisites for any Internet deployment

1. Disable `DEMO_MODE`; rotate demo and bootstrap credentials.
2. Install an authenticated OIDC/SSO front end or gateway, use TLS, remove open `/docs` as appropriate, and maintain a tenant membership system.
3. Enforce request/body rate limits, webhook timestamp tolerance, replay windows and source allowlists.
4. Move to managed Postgres with tenant row-level security and a tested migration policy.
5. Encrypt/rotate secrets, use a secret manager, and adopt scoped per-integration credentials.
6. Use durable workers, concurrency leases, well-defined retry budgets and dead-letter queues.
7. Add structured telemetry, backup/restore tests, release rollbacks and documented incident response.
8. Perform an independent access-control and threat-model review before handling real customer data.
