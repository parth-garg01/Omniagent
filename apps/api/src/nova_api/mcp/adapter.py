"""MCP adapter boundary. Wraps an MCP-style client as internal ToolDefs so mock tools never
depend on MCP, and remote servers can only expose tools the operator explicitly allowlists.

No transport is implemented here and nothing connects to external servers by default.
"""
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from ..tools.registry import ToolContext, ToolDef, ToolFailure, ToolResult


class McpClient(Protocol):
    def list_tools(self) -> list[dict]: ...

    def call_tool(self, name: str, arguments: dict) -> dict: ...


class McpArgs(BaseModel):
    model_config = ConfigDict(extra="allow")


def _make_handler(client: McpClient, remote_name: str):
    def handler(ctx: ToolContext, args: BaseModel) -> ToolResult:
        res = client.call_tool(remote_name, args.model_dump())
        if res.get("isError"):
            raise ToolFailure("Remote tool reported an error")
        text = " ".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        return ToolResult(text[:1000] or "OK")

    return handler


def mcp_tools(client: McpClient, *, allowlist: set[str], permission: str = "tool:read",
              prefix: str = "mcp_", timeout_s: float = 5.0) -> list[ToolDef]:
    """Expose only allowlisted remote tools, read-only by default (least privilege)."""
    defs: list[ToolDef] = []
    for t in client.list_tools():
        name = t.get("name", "")
        if name not in allowlist:
            continue
        schema: dict[str, Any] = t.get("inputSchema") or {"type": "object"}
        model = type(f"{name}_args", (McpArgs,), {"model_json_schema": classmethod(lambda c, **k: schema)})
        defs.append(ToolDef(f"{prefix}{name}", t.get("description", "")[:300], model,
                            _make_handler(client, name), permission, risk="medium",
                            timeout_s=timeout_s))
    return defs
