"""FastAPI app: tenant-scoped APIs, live WebSockets, signed webhooks and agent runtime."""
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agents import discover_tools, get_approvals, invoke, review, run_agent_team
from .connectors import create_integration, list_integrations, sync_integration, import_csv
from .db import Database
from .services import (create_task, export_tasks, get_audit, list_tasks,
                       record_audit, summary, ingest_event)

STATIC_DIR = Path(__file__).parent / "static"


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    priority: Literal["normal", "high", "urgent"] = "normal"


class IntegrationIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["mock_tickets", "csv_upload"] = "mock_tickets"


class ToolCallIn(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class AgentIn(BaseModel):
    objective: str = Field(min_length=1, max_length=240)


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject"]


def create_app(db_path: str = "data/opspilot.db", demo_mode: bool = False,
               webhook_secret: str | None = None, bootstrap_key: str | None = None):
    app = FastAPI(title="OpsPilot Agent Platform", version="0.1.0",
                  description="Independent, multi-tenant operations platform prototype")
    app.state.db = Database(db_path)
    app.state.webhook_secret = webhook_secret
    app.state.demo_mode = demo_mode

    if demo_mode:
        app.state.db.add_org("acme", "Acme Demo Operations")
        app.state.db.add_org("nova", "Nova Demo Operations")
        for org, name, role, key in [
            ("acme", "Acme Admin", "owner", "demo-acme-owner"),
            ("acme", "Acme Viewer", "viewer", "demo-acme-viewer"),
            ("nova", "Nova Admin", "owner", "demo-nova-owner"),
        ]:
            app.state.db.add_key(org, name, role, key)
        app.state.webhook_secret = webhook_secret or "DEMO-WEBHOOK-SECRET-NEVER-DEPLOY"
    elif bootstrap_key:
        app.state.db.add_org("default", "Default Organization")
        app.state.db.add_key("default", "Bootstrap Owner", "owner", bootstrap_key)

    def identity(request: Request, x_api_key: str | None = Header(default=None)):
        principal = request.app.state.db.identity(x_api_key or "")
        if not principal:
            raise HTTPException(401, "Invalid or missing X-API-Key")
        return principal

    def require_editor(principal=Depends(identity)):
        if principal["role"] not in {"editor", "owner"}:
            raise HTTPException(403, "editor or owner role required")
        return principal

    def require_owner(principal=Depends(identity)):
        if principal["role"] != "owner":
            raise HTTPException(403, "owner role required")
        return principal

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "opspilot"}

    @app.get("/")
    def page():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/me")
    def me(principal=Depends(identity)):
        return principal

    @app.get("/api/summary")
    def metrics(request: Request, principal=Depends(identity)):
        return summary(request.app.state.db, principal["org_id"])

    @app.get("/api/tasks")
    def tasks(request: Request, status: Literal["open", "done"] | None = None,
              principal=Depends(identity)):
        return list_tasks(request.app.state.db, principal["org_id"], status)

    @app.post("/api/tasks", status_code=201)
    def add_task(body: TaskIn, request: Request, principal=Depends(require_editor)):
        task = create_task(request.app.state.db, principal["org_id"], body.title, body.priority)
        record_audit(request.app.state.db, principal["org_id"], principal["name"], "task.create", "success", {"task_id": task["id"]})
        return task

    @app.get("/api/tasks.csv")
    def tasks_csv(request: Request, principal=Depends(identity)):
        data = export_tasks(request.app.state.db, principal["org_id"])
        return PlainTextResponse(data, media_type="text/csv",
                                 headers={"Content-Disposition": 'attachment; filename="tasks.csv"'})

    @app.get("/api/integrations")
    def integrations(request: Request, principal=Depends(identity)):
        return list_integrations(request.app.state.db, principal["org_id"])

    @app.post("/api/integrations", status_code=201)
    def add_integration(body: IntegrationIn, request: Request, principal=Depends(require_editor)):
        try:
            return create_integration(request.app.state.db, principal["org_id"], body.name, body.kind)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/api/integrations/{integration_id}/sync")
    def sync(integration_id: str, request: Request, principal=Depends(require_editor)):
        try:
            result = sync_integration(request.app.state.db, principal["org_id"], integration_id)
            record_audit(request.app.state.db, principal["org_id"], principal["name"], "integration.sync", "success", result)
            return result
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/api/integrations/{integration_id}/import-csv")
    async def csv_upload(integration_id: str, request: Request, principal=Depends(require_editor)):
        body = await request.body()
        try:
            result = import_csv(request.app.state.db, principal["org_id"], integration_id, body)
            record_audit(request.app.state.db, principal["org_id"], principal["name"],
                         "integration.csv_import", "success", result)
            return result
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/webhooks/{org_id}/{integration_id}")
    async def webhook(org_id: str, integration_id: str, request: Request,
                      x_event_id: str | None = Header(default=None),
                      x_signature: str | None = Header(default=None)):
        secret = request.app.state.webhook_secret
        if not secret:
            raise HTTPException(503, "Webhooks require WEBHOOK_SIGNING_SECRET")
        raw = await request.body()
        if len(raw) > 32768:
            raise HTTPException(413, "Payload too large")
        # Derive an integration-specific signing key from a deployment secret.
        derived = hmac.new(secret.encode(), f"{org_id}:{integration_id}".encode(), hashlib.sha256).digest()
        expected = "sha256=" + hmac.new(derived, raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(x_signature or "", expected):
            raise HTTPException(401, "Invalid signature")
        if not x_event_id:
            raise HTTPException(400, "Missing X-Event-ID")
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            result = ingest_event(request.app.state.db, org_id, integration_id, x_event_id,
                                  str(payload.get("kind", "external.event")), payload)
        except (ValueError, UnicodeDecodeError) as e:
            raise HTTPException(422, str(e)) from e
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
        return result

    @app.get("/api/tools")
    def tools(principal=Depends(identity)):
        return discover_tools(principal["role"])

    @app.post("/api/tools/call")
    def call_tool(body: ToolCallIn, request: Request, principal=Depends(identity)):
        try:
            return invoke(request.app.state.db, principal, body.name, body.arguments)
        except PermissionError as e:
            raise HTTPException(403, str(e)) from e
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        except LookupError as e:
            raise HTTPException(404, str(e)) from e

    @app.post("/api/agent/run")
    def agent(body: AgentIn, request: Request, principal=Depends(identity)):
        return run_agent_team(request.app.state.db, principal, body.objective)

    @app.get("/api/approvals")
    def approvals(request: Request, principal=Depends(require_owner)):
        return get_approvals(request.app.state.db, principal)

    @app.post("/api/approvals/{approval_id}/review")
    def decide(approval_id: str, body: ReviewIn, request: Request,
               principal=Depends(require_owner)):
        try:
            return review(request.app.state.db, principal, approval_id, body.decision)
        except LookupError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/api/audit")
    def audit(request: Request, principal=Depends(require_owner)):
        return get_audit(request.app.state.db, principal["org_id"])

    @app.websocket("/ws/live")
    async def live(ws: WebSocket):
        await ws.accept()
        try:
            # Authentication is sent as the first frame, never in a URL query string.
            frame = await asyncio.wait_for(ws.receive_json(), timeout=6)
            principal = ws.app.state.db.identity(str(frame.get("api_key", "")))
            if not principal:
                await ws.close(code=1008)
                return
            while True:
                await ws.send_json({"type": "snapshot", "summary": summary(ws.app.state.db, principal["org_id"]),
                                    "tasks": list_tasks(ws.app.state.db, principal["org_id"], limit=15)})
                await asyncio.sleep(2)
        except (Exception, asyncio.CancelledError):
            # Lost connections are normal. Client reconnects if desired.
            try:
                await ws.close()
            except Exception:
                pass

    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")
    return app


app = create_app(
    db_path=os.getenv("DATABASE_PATH", "data/opspilot.db"),
    demo_mode=os.getenv("DEMO_MODE", "0") == "1",
    webhook_secret=os.getenv("WEBHOOK_SIGNING_SECRET"),
    bootstrap_key=os.getenv("BOOTSTRAP_API_KEY"),
)
