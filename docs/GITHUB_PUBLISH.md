# Publish OpsPilot to your GitHub

OpsPilot was created as an independent repository artifact. No GitHub push was performed by this session.

## PowerShell (after extracting the ZIP)

```powershell
cd "path\to\opspilot_agent_platform"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest -q

git init
git branch -M main
git add .
git diff --cached --check
git commit -m "feat: build OpsPilot agent operations platform MVP"

# Install/authenticate GitHub CLI separately, then create remote and push:
gh auth login
gh repo create opspilot-agent-platform --public --source . --remote origin --push
```

Before publishing: review README claims, check `.gitignore`, ensure no real API keys, sensitive data, demo DB files, or client information are included. The sample CSV contains only synthetic examples.

## Suggested GitHub description

> Tenant-aware operations control plane with live dashboards, CSV and webhook ingestion, paginated connectors, human-approved agent tools and an optional MCP v2 adapter. FastAPI, SQLite, WebSockets, pytest and Docker.

## Strong interview demo story

1. Show how one tenant cannot retrieve another tenant's tasks or metrics.
2. Import the CSV twice and demonstrate that the second import creates zero duplicate tasks.
3. Sync the mock connector and discuss cursor semantics and provider rate limiting.
4. Trigger `tasks.complete`; prove the task remains open until explicit owner approval.
5. Run the agent team and explain which actions are deterministic rather than pretending it is an LLM.
6. Contrast tested MVP state with the production roadmap: OIDC, Postgres RLS, durable queue, real OAuth2 connectors, traces and incident readiness.
