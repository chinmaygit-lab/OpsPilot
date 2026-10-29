"""Connector adapters with paginated, retry-safe cursor checkpoints.

The bundled connector is deliberately offline: no third-party credentials required.
Replace MockTicketConnector with a provider that implements fetch_page.
"""
import json
from pathlib import Path
from uuid import uuid4
from .services import ingest_event

SAMPLE_TICKETS = [
    {"external_id": "t-001", "kind": "ticket.created", "title": "Invoice mismatch", "severity": "high"},
    {"external_id": "t-002", "kind": "ticket.created", "title": "Customer onboarding", "severity": "normal"},
    {"external_id": "t-003", "kind": "ticket.created", "title": "Production integration outage", "severity": "critical"},
    {"external_id": "t-004", "kind": "ticket.created", "title": "New access request", "severity": "low"},
    {"external_id": "t-005", "kind": "ticket.created", "title": "Renewal follow-up", "severity": "high"},
]


class MockTicketConnector:
    kind = "mock_tickets"

    def fetch_page(self, cursor: int, size: int = 2):
        if cursor < 0:
            raise ValueError("invalid cursor")
        return SAMPLE_TICKETS[cursor:cursor + size], min(cursor + size, len(SAMPLE_TICKETS))


CONNECTORS = {MockTicketConnector.kind: MockTicketConnector}
REGISTERED_KINDS = set(CONNECTORS) | {"csv_upload"}


def create_integration(db, org: str, name: str, kind: str = "mock_tickets"):
    if kind not in REGISTERED_KINDS:
        raise ValueError("unsupported connector")
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("invalid name")
    item = {"id": str(uuid4()), "org_id": org, "kind": kind, "name": name, "cursor": 0, "enabled": 1}
    with db.connect() as con:
        con.execute("INSERT INTO integrations VALUES(?,?,?,?,?,?)", tuple(item.values()))
    return item


def list_integrations(db, org: str):
    with db.connect() as con:
        rows = con.execute("SELECT * FROM integrations WHERE org_id=? ORDER BY name", (org,)).fetchall()
    return [dict(r) for r in rows]


def sync_integration(db, org: str, integration_id: str, max_pages: int = 10):
    if not 1 <= max_pages <= 20:
        raise ValueError("max_pages must be between 1 and 20")
    with db.connect() as con:
        row = con.execute("SELECT * FROM integrations WHERE id=? AND org_id=? AND enabled=1",
                          (integration_id, org)).fetchone()
    if row is None:
        raise LookupError("integration not found")
    if row["kind"] not in CONNECTORS:
        raise ValueError("this connector uses CSV import, not pull sync")
    connector = CONNECTORS[row["kind"]]()
    cursor = row["cursor"]
    created = duplicates = pages = 0
    for _ in range(max_pages):
        batch, next_cursor = connector.fetch_page(cursor)
        if not batch:
            break
        for raw in batch:
            result = ingest_event(db, org, integration_id, raw["external_id"], raw["kind"], raw)
            if result["deduplicated"]:
                duplicates += 1
            else:
                created += 1
        with db.connect() as con:
            con.execute("UPDATE integrations SET cursor=MAX(cursor, ?) WHERE id=? AND org_id=?", (next_cursor, integration_id, org))
        cursor = next_cursor
        pages += 1
    return {"created": created, "deduplicated": duplicates, "pages": pages, "cursor": cursor}


def import_csv(db, org: str, integration_id: str, data: bytes):
    """Import a spreadsheet of tasks as repeat-safe events, with preflight validation."""
    import csv
    import hashlib
    import io
    if len(data) > 262144:
        raise ValueError("CSV larger than 256 KiB")
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        if reader.fieldnames is None or "title" not in reader.fieldnames:
            raise ValueError("CSV must have a title column")
        rows = list(reader)
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8") from exc
    if len(rows) > 1000:
        raise ValueError("maximum 1000 rows per import")
    with db.connect() as con:
        found = con.execute("SELECT id FROM integrations WHERE org_id=? AND id=? AND kind='csv_upload' AND enabled=1",
                            (org, integration_id)).fetchone()
        if not found:
            raise LookupError("CSV integration not found")
    validated = []
    for index, item in enumerate(rows, start=2):
        if None in item:
            raise ValueError(f"Malformed row {index}")
        title = (item.get("title") or "").strip()
        severity = (item.get("severity") or "normal").lower()
        if not 1 <= len(title) <= 180:
            raise ValueError(f"Invalid title at row {index}")
        if severity not in {"normal", "low", "high", "critical", "urgent", "major"}:
            raise ValueError(f"Invalid severity at row {index}")
        external_id = (item.get("external_id") or "").strip()
        if not external_id:
            external_id = "csv-" + hashlib.sha256(
                json.dumps({"title":title,"severity":severity}, sort_keys=True).encode()).hexdigest()[:24]
        if len(external_id) > 180:
            raise ValueError(f"Invalid external_id at row {index}")
        validated.append((external_id, {"title": title, "severity": severity}))
    created = duplicates = 0
    for external_id, item in validated:
        result = ingest_event(db, org, integration_id, external_id, "spreadsheet.import", item)
        created += not result["deduplicated"]
        duplicates += result["deduplicated"]
    return {"created": created, "deduplicated": duplicates, "rows": len(rows)}
