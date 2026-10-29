# Extending Nova

## Add an LLM provider
1. Implement `LLMProvider` (`llm/interfaces.py`): `name`, `model`, `supports_tools`, and `stream(request)` yielding `TextDelta`, `ToolCallEvent`, `UsageEvent`. Raise `LLMError` with a normalized code (`timeout|rate_limit|auth|unavailable|bad_request`) and never include provider response bodies in the message.
2. Register it in `llm/__init__.py::_make` and add its name to the validator in `config.py`.
3. Add mock-transport tests like `tests/test_anthropic_provider.py`. CI must not need a real key.

## Add a mock connector (tool)
1. Define a pydantic input model and a handler `(ToolContext, args) -> ToolResult`; raise `ToolFailure` for user-presentable errors.
2. Add a `ToolDef` in `tools/mock_tools.py::build_registry` with permission, risk, timeout, `requires_confirmation`, and `idempotency_fields` for state-changing tools. Use `redact_fields` for sensitive arguments.
3. Scope all data access by `ctx.user_id`. Add tests for authorization, validation and duplicates.
No orchestrator changes are needed.

## Add an MCP server
Wrap a client with `mcp/adapter.py::mcp_tools(client, allowlist={...})`. Only allowlisted tools are exposed, read-only by default. No transport ships in this repo; remote servers need an authenticated transport and an explicit allowlist before use.
