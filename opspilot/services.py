"""Data services; all tenant lookups are filtered by org_id."""
import csv
import io
import json
import sqlite3
from collections import Counter
from uuid import uuid4

from .db import utcnow


def record_audit(db, org: str, actor: str, tool: str, outcome: str, detail: dict):
    with db.connect() as con:
        con.execute("INSERT INTO audit VALUES(?,?,?,?,?,?,?)", (
            str(uuid4()), org, actor, tool, outcome, json.dumps(detail, sort_keys=True), utcnow()
        ))


def create_task(db, org: str, title: str, priority: str = "normal", source: str = "manual"):
    if priority not in {"normal", "high", "urgent"}:
        raise ValueError("invalid priority")
    title = title.strip()
    if not 1 <= len(title) <= 180:
        raise ValueError("title must contain 1-180 characters")
    item = dict(id=str(uuid4()), org_id=org, title=title, status="open",
                priority=priority, source=source, created_at=utcnow())
    with db.connect() as con:
        con.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?)", tuple(item.values()))
    return item


def list_tasks(db, org: str, status: str | None = None, limit: int = 50):
    limit = min(max(limit, 1), 200)
    with db.connect() as con:
        rows = con.execute(
            "SELECT * FROM tasks WHERE org_id=? AND (? IS NULL OR status=?) "
            "ORDER BY created_at DESC,id DESC LIMIT ?",
            (org, status, status, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def complete_task(db, org: str, task_id: str):
    with db.connect() as con:
        cur = con.execute("UPDATE tasks SET status='done' WHERE id=? AND org_id=?", (task_id, org))
        if cur.rowcount == 0:
            return None
        row = con.execute("SELECT * FROM tasks WHERE id=? AND org_id=?", (task_id, org)).fetchone()
    return dict(row)


def summary(db, org: str):
    with db.connect() as con:
        total = con.execute("SELECT count(*) FROM tasks WHERE org_id=?", (org,)).fetchone()[0]
        by_status = con.execute("SELECT status,count(*) n FROM tasks WHERE org_id=? GROUP BY status", (org,)).fetchall()
        by_priority = con.execute("SELECT priority,count(*) n FROM tasks WHERE org_id=? GROUP BY priority", (org,)).fetchall()
        by_source = con.execute("SELECT source,count(*) n FROM tasks WHERE org_id=? GROUP BY source", (org,)).fetchall()
        events = con.execute("SELECT count(*) FROM events WHERE org_id=?", (org,)).fetchone()[0]
        integrations = con.execute("SELECT count(*) FROM integrations WHERE org_id=?", (org,)).fetchone()[0]
        approvals = con.execute("SELECT count(*) FROM approvals WHERE org_id=? AND status='pending'", (org,)).fetchone()[0]
        trend_rows = con.execute("SELECT substr(created_at,1,10) day,count(*) n FROM events WHERE org_id=? "
                                 "GROUP BY day ORDER BY day DESC LIMIT 7", (org,)).fetchall()
    return {"total_tasks": total, "events": events, "integrations": integrations,
            "pending_approvals": approvals,
            "status": {r["status"]: r["n"] for r in by_status},
            "priority": {r["priority"]: r["n"] for r in by_priority},
            "sources": {r["source"]: r["n"] for r in by_source},
            "event_trend": [dict(r) for r in reversed(trend_rows)]}


def safe_csv(value):
    """Prevent spreadsheet formula injection in untrusted titles."""
    s = str(value)
    if s.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + s
    return s


def export_tasks(db, org: str):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["id", "title", "status", "priority", "source", "created_at"])
    with db.connect() as con:
        all_items = con.execute("SELECT id,title,status,priority,source,created_at FROM tasks WHERE org_id=? "
                                "ORDER BY created_at DESC,id DESC", (org,)).fetchall()
    for item in all_items:
        writer.writerow([safe_csv(item[k]) for k in ["id", "title", "status", "priority", "source", "created_at"]])
    return stream.getvalue()


class TriageAgent:
    """Deterministic classification makes auto-actions reproducible and auditable."""
    def interpret(self, kind: str, payload: dict):
        raw_title = str(payload.get("title") or payload.get("subject") or kind)
        title = raw_title[:180].strip() or "Untitled event"
        severity = str(payload.get("severity", "")).lower()
        priority = "urgent" if severity in {"critical", "urgent"} else "high" if severity in {"high", "major"} else "normal"
        return {"title": title, "priority": priority, "reason": "severity policy v1"}


def ingest_event(db, org: str, integration_id: str, external_id: str, kind: str, payload: dict):
    """Deduplicate events and create at most one task per external ID transactionally."""
    if not external_id or len(external_id) > 180 or len(kind) > 80:
        raise ValueError("invalid event ID or kind")
    triage = TriageAgent().interpret(kind, payload)
    event_id = str(uuid4())
    task_id = str(uuid4())
    with db.connect() as con:
        integration = con.execute("SELECT id FROM integrations WHERE id=? AND org_id=? AND enabled=1",
                                  (integration_id, org)).fetchone()
        if not integration:
            raise LookupError("integration not found")
        try:
            con.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",
                        (event_id, org, integration_id, external_id, kind,
                         json.dumps(payload, sort_keys=True), utcnow()))
        except sqlite3.IntegrityError:
            return {"deduplicated": True, "external_id": external_id}
        con.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?)",
                    (task_id, org, triage["title"], "open", triage["priority"],
                     integration_id, utcnow()))
    record_audit(db, org, "triage-agent", "event.triage", "success", {"event_id": event_id, **triage})
    return {"deduplicated": False, "event_id": event_id, "task_id": task_id, **triage}


def get_audit(db, org: str, limit: int = 50):
    with db.connect() as con:
        rows = con.execute("SELECT * FROM audit WHERE org_id=? ORDER BY created_at DESC,id DESC LIMIT ?",
                           (org, min(max(limit, 1), 100))).fetchall()
    return [dict(r) for r in rows]
