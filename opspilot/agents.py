"""Policy-gated tool runtime and deterministic cooperating agents.

No LLM is required. Replace planner in future with a model only after a review layer.
"""
import json
from dataclasses import dataclass
from uuid import uuid4

from jsonschema import Draft202012Validator, ValidationError
from .db import utcnow
from .services import (complete_task, create_task, list_tasks, summary, record_audit)

ROLE_RANK = {"viewer": 0, "editor": 1, "owner": 2}


def schema(properties: dict, required: list[str] = None):
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_schema: dict
    min_role: str
    needs_approval: bool = False


TOOLS = {
    "tasks.list": Tool("tasks.list", "Read the current tenant's tasks", schema({"status": {"type": "string", "enum": ["open", "done"]}}), "viewer"),
    "tasks.create": Tool("tasks.create", "Create a new operation task", schema({"title": {"type": "string", "minLength": 1, "maxLength": 180}, "priority": {"type": "string", "enum": ["normal", "high", "urgent"]}}, ["title"]), "editor"),
    "tasks.complete": Tool("tasks.complete", "Mark a task complete (requires owner approval)", schema({"task_id": {"type": "string", "minLength": 1}}, ["task_id"]), "editor", True),
    "analytics.summary": Tool("analytics.summary", "Read cross-workflow tenant metrics", schema({}), "viewer"),
}


def discover_tools(role: str):
    return [{"name": t.name, "description": t.description, "inputSchema": t.args_schema,
             "requires_approval": t.needs_approval} for t in TOOLS.values() if ROLE_RANK[role] >= ROLE_RANK[t.min_role]]


def invoke(db, identity: dict, tool_name: str, args: dict, approval_granted: bool = False):
    org, actor, role = identity["org_id"], identity["name"], identity["role"]
    tool = TOOLS.get(tool_name)
    if tool is None:
        record_audit(db, org, actor, tool_name, "denied", {"reason": "unknown tool"})
        raise ValueError("unknown tool")
    if ROLE_RANK[role] < ROLE_RANK[tool.min_role]:
        record_audit(db, org, actor, tool_name, "denied", {"reason": "insufficient role"})
        raise PermissionError("insufficient role")
    try:
        Draft202012Validator(tool.args_schema).validate(args)
    except ValidationError as error:
        record_audit(db, org, actor, tool_name, "invalid", {"reason": error.message})
        raise ValueError("invalid tool arguments: " + error.message) from error
    if tool.needs_approval and not approval_granted:
        approval_id = str(uuid4())
        with db.connect() as con:
            con.execute("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?)", (
                approval_id, org, actor, tool_name, json.dumps(args), "pending", None, utcnow()
            ))
        record_audit(db, org, actor, tool_name, "pending_approval", {"approval_id": approval_id})
        return {"requires_approval": True, "approval_id": approval_id}
    if tool_name == "tasks.list":
        result = {"tasks": list_tasks(db, org, args.get("status"))}
    elif tool_name == "tasks.create":
        result = {"task": create_task(db, org, args["title"], args.get("priority", "normal"), "agent")}
    elif tool_name == "tasks.complete":
        task = complete_task(db, org, args["task_id"])
        if task is None:
            record_audit(db, org, actor, tool_name, "not_found", {"task_id": args["task_id"]})
            raise LookupError("task not found")
        result = {"task": task}
    else:
        result = {"metrics": summary(db, org)}
    record_audit(db, org, actor, tool_name, "success", {"arguments": args, "result_type": tool_name})
    return result


def get_approvals(db, identity: dict):
    if identity["role"] != "owner":
        raise PermissionError("owner role required")
    with db.connect() as con:
        rows = con.execute("SELECT * FROM approvals WHERE org_id=? ORDER BY created_at DESC,id DESC LIMIT 100",
                           (identity["org_id"],)).fetchall()
    return [dict(r) for r in rows]


def review(db, identity: dict, approval_id: str, decision: str):
    if identity["role"] != "owner":
        raise PermissionError("owner role required")
    if decision not in {"approve", "reject"}:
        raise ValueError("invalid decision")
    # Atomic claim blocks double approval / races. Execution is idempotent (complete_task).
    with db.connect() as con:
        row = con.execute("SELECT * FROM approvals WHERE id=? AND org_id=? AND status='pending'",
                          (approval_id, identity["org_id"])).fetchone()
        if not row:
            raise LookupError("approval missing or reviewed")
        updated = con.execute(
            "UPDATE approvals SET status=?, reviewed_by=? "
            "WHERE id=? AND org_id=? AND status='pending'",
            ("executing" if decision == "approve" else "rejected",
             identity["name"], approval_id, identity["org_id"])
        )
        if updated.rowcount != 1:
            raise LookupError("approval already reviewed")
    if decision == "reject":
        record_audit(db, identity["org_id"], identity["name"], row["tool"], "rejected", {"approval_id": approval_id})
        return {"status": "rejected"}
    try:
        result = invoke(db, identity, row["tool"], json.loads(row["arguments"]), approval_granted=True)
    except Exception:
        with db.connect() as con:
            con.execute("UPDATE approvals SET status='failed' WHERE id=? AND org_id=?", (approval_id, identity["org_id"]))
        raise
    with db.connect() as con:
        con.execute("UPDATE approvals SET status='approved' WHERE id=? AND org_id=?", (approval_id, identity["org_id"]))
    return {"status": "approved", "result": result}


class InsightAgent:
    def analyze(self, db, org: str):
        metrics = summary(db, org)
        urgent = metrics["priority"].get("urgent", 0)
        open_count = metrics["status"].get("open", 0)
        return {"agent": "insight-agent", "open_tasks": open_count, "urgent_tasks": urgent,
                "observation": f"{open_count} open tasks; {urgent} urgent in this tenant"}


class PlannerAgent:
    """Rule-based, bounded plan; not pretending to use a model or independently make decisions."""
    def plan(self, objective: str, insight: dict):
        objective = objective.strip()[:240]
        if not objective:
            raise ValueError("objective required")
        return {"agent": "planner-agent", "objective": objective,
                "steps": [{"tool": "analytics.summary", "arguments": {}},
                          {"tool": "tasks.list", "arguments": {}}],
                "note": "Read-only policy plan. Write actions need explicit requests and permissions."}


def run_agent_team(db, identity: dict, objective: str):
    """Insight -> planner -> guarded tool executor; only read-only calls are automatic."""
    insight = InsightAgent().analyze(db, identity["org_id"])
    plan = PlannerAgent().plan(objective, insight)
    results = []
    for step in plan["steps"]:  # bounded to two explicit, registered tools
        results.append({"tool": step["tool"], "result": invoke(db, identity, step["tool"], step["arguments"])})
    record_audit(db, identity["org_id"], identity["name"], "agent.team", "success", {"objective": objective})
    return {"agents": ["insight-agent", "planner-agent", "tool-executor"],
            "insight": insight, "plan": plan, "tool_results": results}
