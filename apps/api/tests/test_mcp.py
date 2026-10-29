from sqlalchemy import select
from test_tools import seeded

from nova_api import db
from nova_api.llm.interfaces import ToolCall
from nova_api.mcp.adapter import mcp_tools
from nova_api.models import User
from nova_api.tools.registry import ToolRegistry


class LocalMcpServer:
    """In-process stand-in for a controlled MCP test server (no network)."""

    def __init__(self):
        self.calls = []

    def list_tools(self):
        return [{"name": "echo", "description": "Echo text", "inputSchema": {"type": "object"}},
                {"name": "dangerous", "description": "Not allowlisted", "inputSchema": {}}]

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "fail":
            return {"isError": True, "content": []}
        return {"content": [{"type": "text", "text": f"echo:{arguments.get('text')}"}]}


def test_only_allowlisted_tools_exposed():
    defs = mcp_tools(LocalMcpServer(), allowlist={"echo"})
    assert [d.name for d in defs] == ["mcp_echo"] and defs[0].permission == "tool:read"


def test_mcp_tool_runs_through_registry_with_policy(client):
    seeded()
    server = LocalMcpServer()
    reg = ToolRegistry(mcp_tools(server, allowlist={"echo"}))
    with next(db.get_db()) as s:
        alice = s.scalar(select(User).where(User.email == "alice@example.com"))
        out = reg.execute(s, alice, "c", None, ToolCall("1", "mcp_echo", {"text": "hi"}))
        assert out.status == "succeeded" and "echo:hi" in out.content
        denied = reg.execute(s, alice, "c", None, ToolCall("2", "mcp_dangerous", {}))
        assert denied.status == "denied" and len(server.calls) == 1
        evaluator = s.scalar(select(User).where(User.email == "eval@example.com"))
        assert reg.execute(s, evaluator, "c", None, ToolCall("3", "mcp_echo", {})).status == "denied"
