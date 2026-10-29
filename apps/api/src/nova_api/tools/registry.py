import hashlib
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..audit import audit
from ..auth.security import has_permission
from ..db import new_session
from ..llm.interfaces import ToolCall, ToolSpec
from ..models import ToolExecution, User
from ..orchestration.types import ToolOutcome

MAX_OUTPUT_CHARS = 4000
_pool = ThreadPoolExecutor(max_workers=8)


class ToolFailure(Exception):
    """Expected, user-presentable failure (e.g. order not found)."""


@dataclass
class ToolContext:
    db: Session
    user_id: str
    email: str
    role: str


@dataclass
class ToolResult:
    message: str
    data: dict | None = None


@dataclass
class ToolDef:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[ToolContext, BaseModel], ToolResult]
    permission: str
    risk: str = "low"  # low | medium | high
    timeout_s: float = 5.0
    requires_confirmation: bool = False
    idempotency_fields: tuple[str, ...] | None = None  # set => state-changing, de-duplicated
    redact_fields: tuple[str, ...] = ()

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.input_model.model_json_schema())

    def describe(self) -> dict:
        return {"name": self.name, "description": self.description, "permission": self.permission,
                "risk": self.risk, "timeout_s": self.timeout_s,
                "requires_confirmation": self.requires_confirmation,
                "state_changing": self.idempotency_fields is not None,
                "input_schema": self.input_model.model_json_schema()}


def _content(status: str, message: str, data: dict | None = None, execution_id: str | None = None) -> str:
    return json.dumps({"status": status, "message": message, "data": data or {},
                       "execution_id": execution_id})


class ToolRegistry:
    def __init__(self, tools: list[ToolDef]):
        self._tools = {t.name: t for t in tools}

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def available(self, user: User) -> list[ToolDef]:
        return [t for t in self._tools.values() if has_permission(user.role, t.permission)]

    # --- ToolRunner protocol -------------------------------------------------
    def specs(self, user: User) -> list[ToolSpec]:
        return [t.spec() for t in self.available(user)]

    def execute(self, db: Session, user: User, conversation_id: str, message_id: str | None,
                call: ToolCall) -> ToolOutcome:
        """All checks here are server-side; nothing the model says bypasses them."""
        tool = self.get(call.name)
        if tool is None:
            return self._record(db, user, conversation_id, message_id, call.name, {}, "denied",
                                "Unknown tool", None)
        if not has_permission(user.role, tool.permission):
            return self._record(db, user, conversation_id, message_id, tool.name, {}, "denied",
                                "You do not have permission to use this tool", None)
        try:
            args = tool.input_model.model_validate(call.arguments)
        except ValidationError as e:
            fields = ", ".join(sorted({str(err["loc"][0]) for err in e.errors() if err["loc"]})) or "input"
            return self._record(db, user, conversation_id, message_id, tool.name, {}, "failed",
                                f"Invalid arguments: {fields}", None)

        key = None
        if tool.idempotency_fields is not None:
            canon = json.dumps({f: getattr(args, f) for f in tool.idempotency_fields}, sort_keys=True)
            key = hashlib.sha256(f"{user.id}|{tool.name}|{canon}".encode()).hexdigest()
            prior = db.query(ToolExecution).filter(
                ToolExecution.idempotency_key == key, ToolExecution.user_id == user.id,
                ToolExecution.status.in_(("succeeded", "pending_confirmation"))).first()
            if prior:
                return ToolOutcome(prior.status, _content(
                    prior.status, f"Duplicate request; existing result: {prior.result_summary}",
                    execution_id=prior.id), f"duplicate of {prior.id}", prior.id)

        stored = self._redact(tool, args)
        if tool.requires_confirmation:
            return self._record(db, user, conversation_id, message_id, tool.name, stored,
                                "pending_confirmation",
                                f"Awaiting user confirmation for {tool.name}", key)
        return self._run(db, user, conversation_id, message_id, tool, args, stored, key)

    # --- internals -----------------------------------------------------------
    @staticmethod
    def _redact(tool: ToolDef, args: BaseModel) -> dict:
        d = args.model_dump()
        for f in tool.redact_fields:
            if f in d:
                d[f] = f"[redacted:{len(str(d[f]))} chars]"
        return d

    def _record(self, db, user, conversation_id, message_id, name, args, status, summary, key,
                data=None) -> ToolOutcome:
        ex = ToolExecution(conversation_id=conversation_id, user_id=user.id, message_id=message_id,
                           tool_name=name, arguments=args, status=status, result_summary=summary,
                           idempotency_key=key)
        db.add(ex)
        db.commit()
        audit(db, user.id, f"tool.{name}", "tool_execution", ex.id, status)
        return ToolOutcome(status, _content(status, summary, data, ex.id), summary, ex.id)

    def _invoke(self, tool: ToolDef, args: BaseModel, user_id: str) -> tuple[str, ToolResult | str]:
        def work():
            with new_session() as wdb:
                u = wdb.get(User, user_id)
                ctx = ToolContext(wdb, u.id, u.email, u.role)
                return tool.handler(ctx, args)

        fut = _pool.submit(work)
        try:
            res = fut.result(timeout=tool.timeout_s)
        except FutureTimeout:
            return "failed", "Tool timed out"
        except ToolFailure as e:
            return "failed", str(e)
        except Exception:  # noqa: BLE001
            return "failed", "Tool failed unexpectedly"
        if len(json.dumps(res.data or {})) + len(res.message) > MAX_OUTPUT_CHARS:
            return "failed", "Tool output exceeded the size limit"
        return "succeeded", res

    def _run(self, db, user, conversation_id, message_id, tool, args, stored, key) -> ToolOutcome:
        status, res = self._invoke(tool, args, user.id)
        if status == "succeeded":
            return self._record(db, user, conversation_id, message_id, tool.name, stored, status,
                                res.message, key, res.data)
        return self._record(db, user, conversation_id, message_id, tool.name, stored, status, res, None)

    # --- confirmation flow ---------------------------------------------------
    def confirm(self, db: Session, user: User, execution_id: str) -> ToolExecution:
        ex = db.get(ToolExecution, execution_id)
        if ex is None or ex.user_id != user.id:
            raise LookupError("not found")
        tool = self.get(ex.tool_name)
        if tool is None or not has_permission(user.role, tool.permission):
            raise PermissionError("forbidden")
        # Atomic claim so a double-click or replay can never execute twice.
        claimed = db.execute(update(ToolExecution).where(
            ToolExecution.id == ex.id, ToolExecution.status == "pending_confirmation")
            .values(status="executing")).rowcount
        db.commit()
        if claimed != 1:
            raise ValueError("Execution is not awaiting confirmation")
        args = tool.input_model.model_validate(ex.arguments) if not tool.redact_fields else None
        if args is None:
            raise ValueError("Tool with redacted arguments cannot be confirmed")
        status, res = self._invoke(tool, args, user.id)
        db.refresh(ex)
        ex.status = status
        ex.result_summary = res.message if status == "succeeded" else res
        if status != "succeeded":
            ex.idempotency_key = None  # a failed attempt may be retried
        db.commit()
        audit(db, user.id, f"tool.{tool.name}.confirm", "tool_execution", ex.id, status)
        return ex

    def cancel(self, db: Session, user: User, execution_id: str) -> ToolExecution:
        ex = db.get(ToolExecution, execution_id)
        if ex is None or ex.user_id != user.id:
            raise LookupError("not found")
        claimed = db.execute(update(ToolExecution).where(
            ToolExecution.id == ex.id, ToolExecution.status == "pending_confirmation")
            .values(status="cancelled", idempotency_key=None)).rowcount
        db.commit()
        if claimed != 1:
            raise ValueError("Execution is not awaiting confirmation")
        db.refresh(ex)
        audit(db, user.id, f"tool.{ex.tool_name}.cancel", "tool_execution", ex.id, "cancelled")
        return ex
