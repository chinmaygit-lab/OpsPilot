"""Optional real MCP v2 stdio server for a trusted local MCP host.

Usage: OPSPILOT_MCP_KEY=<private-key> DATABASE_PATH=... python -m opspilot.mcp_server
The MCP process is scoped to the authenticated principal attached to that key.
"""
import os
from .db import Database
from .agents import invoke


def main():
    try:
        from mcp.server import MCPServer  # SDK v2 stable API
    except ImportError as exc:
        raise SystemExit("Install MCP support: pip install -e '.[mcp]'") from exc

    key = os.environ.get("OPSPILOT_MCP_KEY", "")
    db = Database(os.environ.get("DATABASE_PATH", "data/opspilot.db"))
    identity = db.identity(key)
    if not identity:
        raise SystemExit("OPSPILOT_MCP_KEY must be a valid tenant-scoped API key")
    server = MCPServer("OpsPilot Agent Tools")

    @server.tool()
    def list_tasks(status: str = "") -> dict:
        """Read current tenant tasks; status may be open, done or blank."""
        args = {"status": status} if status else {}
        return invoke(db, identity, "tasks.list", args)

    @server.tool()
    def analytics_summary() -> dict:
        """Read live task and event metrics in the authenticated tenant."""
        return invoke(db, identity, "analytics.summary", {})

    @server.tool()
    def create_task(title: str, priority: str = "normal") -> dict:
        """Create a new task if the authenticated principal has editor permissions."""
        return invoke(db, identity, "tasks.create", {"title": title, "priority": priority})

    @server.tool()
    def request_task_completion(task_id: str) -> dict:
        """Request human approval to mark a tenant task complete."""
        return invoke(db, identity, "tasks.complete", {"task_id": task_id})

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
